"""
LLMExplainer Mistral 7B v7.0 — §16
Génère une explication qualité en langage naturel via llama.cpp.
seed=42 · temperature=0.1 → déterministe (GR-01).
DISPLAY ONLY — jamais dans la logique de décision (GR-04).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from core.models import FinalResult, LLMExplanation

logger = logging.getLogger(__name__)


class LLMExplainer:
    """
    Génère une explication qualité en langage naturel — §16.

    Utilise Mistral 7B Q4 local via llama.cpp (subprocess).
    seed=42, temperature=0.1 → résultats déterministes (GR-01).

    Dégradation gracieuse :
      - LLM indisponible (modèle absent / binaire manquant)  → fallback textuel
      - Timeout                                               → fallback textuel
      - JSON mal formé dans la réponse                        → fallback textuel

    DISPLAY ONLY — GR-04 : cette explication n'entre JAMAIS dans evaluate_tier
    ou evaluate_final. Elle est destinée exclusivement à l'affichage opérateur.

    Appelée via explain_async() depuis S8Output (non-bloquant, thread daemon).
    """

    def __init__(
        self,
        config:   Any                                  = None,
        callback: Optional[Callable[[LLMExplanation, str], None]] = None,
    ) -> None:
        """
        Args:
            config   : dict-like avec get(key, default) — ou None pour tout utiliser par défaut.
            callback : appelé avec (explanation, frame_id) quand explain_async() termine.
        """
        cfg = config or {}
        _get = cfg.get if hasattr(cfg, "get") else lambda k, d=None: d

        self._enabled      = bool(_get("llm.enabled",       True))
        self._timeout_ms   = float(_get("llm.timeout_ms",   3000))
        self._language     = str(_get("llm.language",        "fr"))
        self._model_path   = str(_get("llm.model_path",      "data/llm/mistral-7b-q4.gguf"))
        self._llama_bin    = str(_get("llm.llama_bin",        "/opt/llama.cpp/main"))
        self._temperature  = float(_get("llm.temperature",   0.1))
        self._seed         = 42      # GR-01 : déterminisme absolu
        self._callback     = callback
        self._available    = self._check_available()

        if not self._available:
            logger.info(
                "LLMExplainer: LLM indisponible (enabled=%s model=%s bin=%s) "
                "— fallback textuel actif",
                self._enabled, self._model_path, self._llama_bin,
            )

    # ── API publique ──────────────────────────────────────────────────────────

    def explain(self, final_result: FinalResult) -> LLMExplanation:
        """
        Génère une explication depuis FinalResult — §16.

        Synchrone. Timeout → fallback automatique.
        DISPLAY ONLY — GR-04.
        """
        t0 = time.monotonic()
        if not self._available:
            return self._fallback(final_result, t0)

        prompt = self._build_prompt(final_result)
        try:
            raw         = self._call_llama(prompt, timeout_s=self._timeout_ms / 1000.0)
            parsed      = self._parse_output(raw, final_result)
            elapsed     = round((time.monotonic() - t0) * 1000.0, 1)
            return LLMExplanation(
                summary        = parsed["summary"],
                defect_detail  = parsed["defect_detail"],
                probable_cause = parsed["probable_cause"],
                recommendation = parsed["recommendation"],
                fail_tier      = parsed["fail_tier"],
                latency_ms     = elapsed,
                fallback_used  = False,
            )
        except Exception as exc:
            logger.warning("LLMExplainer: erreur/timeout — %s — fallback activé", exc)
            return self._fallback(final_result, t0)

    def explain_async(
        self,
        final_result: FinalResult,
        callback: Optional[Callable[[LLMExplanation, str], None]] = None,
    ) -> None:
        """
        Lance explain() dans un thread daemon — non-bloquant.

        Le résultat est transmis via :
          1. callback local (paramètre)
          2. callback global (enregistré dans __init__)

        Appelé par S8Output._send_llm() — ne doit jamais bloquer le pipeline.
        """
        cb = callback or self._callback

        def _worker() -> None:
            try:
                explanation = self.explain(final_result)
                if cb is not None:
                    cb(explanation, final_result.frame_id)
                logger.debug(
                    "LLMExplainer: explication prête (frame=%s fallback=%s latency=%.0fms)",
                    final_result.frame_id, explanation.fallback_used, explanation.latency_ms,
                )
            except Exception as exc:
                logger.error("LLMExplainer: erreur thread async — %s", exc, exc_info=True)

        t = threading.Thread(target=_worker, daemon=True, name="LLMExplainer")
        t.start()

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _build_prompt(self, result: FinalResult) -> str:
        """Construit le prompt Mistral [INST]...[/INST] — §16."""
        tier_info = ""
        if result.fail_tier:
            reasons   = ", ".join(result.fail_reasons) or "—"
            tier_info = f"Le Tier {result.fail_tier.value} a échoué : {reasons}."

        tier_scores_str = ""
        if result.tier_scores:
            parts           = [f"{k}={v:.2f}" for k, v in result.tier_scores.items()]
            tier_scores_str = "Scores par Tier : " + ", ".join(parts) + "."

        lang_instruction = {
            "fr": "Réponds en français.",
            "en": "Reply in English.",
            "ar": "أجب بالعربية.",
        }.get(self._language, "Réponds en français.")

        return (
            "[INST]\n"
            "Tu es un expert en qualité industrielle pour un système de vision IVS v7.0.\n\n"
            f"Produit : {result.product_id}\n"
            f"Verdict : {result.verdict}\n"
            f"Sévérité : {result.severity.value if result.severity else 'N/A'}\n"
            f"{tier_info}\n"
            f"{tier_scores_str}\n\n"
            f"{lang_instruction}\n"
            "Réponds UNIQUEMENT en JSON valide avec exactement ces 4 clés :\n"
            "{\n"
            '  "summary": "résumé en 1 phrase courte",\n'
            '  "defect_detail": "description précise du défaut",\n'
            '  "probable_cause": "cause probable en usine",\n'
            '  "recommendation": "action recommandée pour l\'opérateur"\n'
            "}\n"
            "[/INST]"
        )

    # ── Appel llama.cpp ───────────────────────────────────────────────────────

    def _call_llama(self, prompt: str, timeout_s: float) -> str:
        """Appelle llama.cpp en subprocess avec timeout strict."""
        cmd = [
            self._llama_bin,
            "-m",          self._model_path,
            "--seed",      str(self._seed),
            "--temp",      str(self._temperature),
            "--n-predict", "300",
            "--threads",   "4",
            "--prompt",    prompt,
            "--no-mmap",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return result.stdout.strip()

    # ── Parsing JSON ──────────────────────────────────────────────────────────

    def _parse_output(self, raw: str, result: FinalResult) -> dict:
        """
        Extrait le JSON depuis la sortie llama.cpp.

        Cherche le premier { ... } valide. Lève ValueError si introuvable.
        Tronque les champs longs pour protéger l'affichage UI.
        """
        match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if match:
            try:
                data     = json.loads(match.group())
                required = {"summary", "defect_detail", "probable_cause", "recommendation"}
                if required.issubset(data.keys()):
                    return {
                        "summary":        str(data["summary"])[:200],
                        "defect_detail":  str(data["defect_detail"])[:300],
                        "probable_cause": str(data["probable_cause"])[:200],
                        "recommendation": str(data["recommendation"])[:200],
                        "fail_tier":      (
                            result.fail_tier.value if result.fail_tier else "NONE"
                        ),
                    }
            except json.JSONDecodeError:
                pass
        raise ValueError(f"LLM output non parseable — raw={raw[:120]!r}")

    # ── Fallback textuel ──────────────────────────────────────────────────────

    def _fallback(self, result: FinalResult, t0: float) -> LLMExplanation:
        """
        Explication textuelle déterministe quand LLM indisponible ou timeout.

        Basée uniquement sur FinalResult — jamais sur un modèle ML.
        DISPLAY ONLY — GR-04.
        """
        if result.verdict == "OK":
            scores_str = ", ".join(
                f"{k}={v:.2f}" for k, v in (result.tier_scores or {}).items()
            )
            summary = "Produit conforme."
            detail  = f"Tous les Tiers ont passé. Scores : {scores_str or '—'}."
            cause   = "Aucun défaut détecté."
            reco    = "Continuer la production."
        elif result.fail_tier:
            reasons  = ", ".join(result.fail_reasons) or "—"
            tier_val = result.fail_tier.value
            summary  = f"Tier {tier_val} échoué : {reasons}."
            detail   = f"Critère(s) défaillant(s) : {reasons}."
            cause    = "Vérifier la qualité de production."
            reco     = {
                "CRITICAL": "Retirer le produit immédiatement.",
                "MAJOR":    "Envoyer en atelier de retouche.",
                "MINOR":    "Inspection manuelle recommandée.",
            }.get(tier_val, "Contacter le responsable qualité.")
        else:
            summary = f"Verdict {result.verdict} — inspection manuelle requise."
            detail  = "Résultat ambigu ou incertitude AI détectée."
            cause   = "Accord AI insuffisant (confidence < 0.50)."
            reco    = "Validation opérateur."

        return LLMExplanation(
            summary        = summary,
            defect_detail  = detail,
            probable_cause = cause,
            recommendation = reco,
            fail_tier      = result.fail_tier.value if result.fail_tier else "NONE",
            latency_ms     = round((time.monotonic() - t0) * 1000.0, 1),
            fallback_used  = True,
        )

    # ── Introspection ─────────────────────────────────────────────────────────

    def _check_available(self) -> bool:
        """Retourne True si LLM activé et les deux chemins existent."""
        return (
            self._enabled
            and Path(self._model_path).exists()
            and Path(self._llama_bin).exists()
        )
