"""
RuleEngine — décideur unique — §7
GR-02 : seul RuleEngine produit TierVerdict et verdict final
GR-08 : RuleEngine n'apprend JAMAIS — aucune méthode learn/train/update
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from core.exceptions import RuleEngineError
from core.models import ProductRules, SeverityLevel
from core.tier_result import ObserverSignal, TierLevel, TierVerdict

logger = logging.getLogger(__name__)

# Seuil de confiance en-dessous duquel un signal est "incertain" (§7.3)
_CONFIDENCE_UNCERTAIN = 0.50


class RuleEngine:
    """
    Décideur unique du système v7.0 — §7.

    evaluate_tier  : évalue un Tier → TierVerdict
    evaluate_final : verdict global depuis les TierVerdicts → (verdict, severity, fail_tier)

    GR-02 : seul ce composant produit des verdicts.
    GR-08 : AUCUNE méthode learn / train / update.
    """

    # ── evaluate_tier — §7.3 ──────────────────────────────────────────────────

    def evaluate_tier(
        self,
        tier:    TierLevel,
        signals: list[ObserverSignal],
        rules:   ProductRules,
    ) -> TierVerdict:
        """
        Évalue tous les critères actifs d'un Tier — §7.3.

        Règles appliquées (ordre strict) :
          1. signal absent              → fail  + score 0.0
          2. signal.error_msg non None  → fail  + score 0.0
          3. confidence < 0.50          → score seulement, continue (REVIEW via evaluate_final)
          4. passed=False + mandatory   → fail  + score value/threshold
          5. passed=False + optionnel   → warn  + score value/threshold
          6. passed=True                → score = confidence

        TierVerdict.passed = (aucun fail_reason)
        """
        t0 = time.monotonic()

        signal_map: dict[str, ObserverSignal] = {s.observer_id: s for s in signals}

        # Sélectionner les critères actifs du Tier
        if tier == TierLevel.CRITICAL:
            criteria = [c for c in rules.critical_criteria if c.enabled]
        elif tier == TierLevel.MAJOR:
            criteria = [c for c in rules.major_criteria if c.enabled]
        else:
            criteria = [c for c in rules.minor_criteria if c.enabled]

        fail_reasons: list[str]   = []
        tier_scores:  list[float] = []

        for criterion in criteria:
            signal = signal_map.get(criterion.observer_id)

            # Règle 1 — signal absent
            if signal is None:
                fail_reasons.append(f"{criterion.criterion_id}_SIGNAL_MISSING")
                tier_scores.append(0.0)
                logger.warning(
                    "RuleEngine: signal absent pour observer '%s' (critère '%s')",
                    criterion.observer_id, criterion.criterion_id,
                )
                continue

            # Règle 2 — observer en erreur
            if signal.error_msg:
                fail_reasons.append(f"{criterion.criterion_id}_OBSERVER_ERROR")
                tier_scores.append(0.0)
                logger.warning(
                    "RuleEngine: observer '%s' en erreur — %s",
                    criterion.observer_id, signal.error_msg,
                )
                continue

            # Règle 3 — confiance insuffisante → REVIEW différé, pas fail direct
            if signal.confidence < _CONFIDENCE_UNCERTAIN:
                tier_scores.append(signal.confidence)
                logger.debug(
                    "RuleEngine: '%s' confiance faible %.2f → REVIEW possible en evaluate_final",
                    criterion.criterion_id, signal.confidence,
                )
                continue

            # Règle 4 & 5 — verdict du signal
            if not signal.passed and criterion.mandatory:
                fail_reasons.append(f"{criterion.criterion_id.upper()}_FAIL")
                logger.debug(
                    "RuleEngine: critère mandatory '%s' échoué (value=%.3f threshold=%.3f)",
                    criterion.criterion_id, signal.value, signal.threshold,
                )

            score = (
                signal.confidence
                if signal.passed
                else signal.value / max(signal.threshold, 1e-9)
            )
            tier_scores.append(score)

        tier_score = float(np.mean(tier_scores)) if tier_scores else 0.0
        passed     = len(fail_reasons) == 0
        latency_ms = (time.monotonic() - t0) * 1000.0

        logger.debug(
            "RuleEngine: Tier %s — passed=%s score=%.3f fail_reasons=%s",
            tier.value, passed, tier_score, fail_reasons,
        )

        return TierVerdict(
            tier=tier,
            passed=passed,
            fail_reasons=tuple(fail_reasons),
            signals=tuple(signals),
            tier_score=round(tier_score, 3),
            completed=True,
            latency_ms=round(latency_ms, 2),
        )

    # ── evaluate_final — §7.1 ─────────────────────────────────────────────────

    def evaluate_final(
        self,
        tier_verdicts: dict[str, TierVerdict],
    ) -> tuple[str, SeverityLevel, Optional[TierLevel]]:
        """
        Produit le verdict final depuis les TierVerdicts disponibles — §7.1.

        Ordre de priorité strict :
          1. CRITICAL fail                       → "NOK" / REJECT
          2. MAJOR fail                          → "NOK" / DEFECT_1
          3. MINOR fail + critère mandatory      → "NOK" / DEFECT_2
          4. MINOR fail + critères optionnels    → "REVIEW" / REVIEW
          5. Score tier < 0.50 (AI incertaine)  → "REVIEW" / REVIEW
          6. Tout OK + score moyen >= 0.90       → "OK" / EXCELLENT
          7. Tout OK sinon                       → "OK" / ACCEPTABLE

        Returns:
            (verdict, severity, fail_tier)
            verdict  : "OK" | "NOK" | "REVIEW"
            severity : SeverityLevel
            fail_tier: TierLevel | None
        """
        critical = tier_verdicts.get("CRITICAL")
        major    = tier_verdicts.get("MAJOR")
        minor    = tier_verdicts.get("MINOR")

        if critical is None:
            raise RuleEngineError("evaluate_final : TierVerdict CRITICAL manquant")

        # ── 1. CRITICAL fail ──────────────────────────────────────────────────
        if not critical.passed:
            return "NOK", SeverityLevel.REJECT, TierLevel.CRITICAL

        # ── 2. MAJOR fail ─────────────────────────────────────────────────────
        if major is not None and not major.passed:
            return "NOK", SeverityLevel.DEFECT_1, TierLevel.MAJOR

        # ── 3 & 4. MINOR fail ─────────────────────────────────────────────────
        if minor is not None and not minor.passed:
            # fail_reasons non vides = au moins un critère mandatory a échoué.
            # Format produit par evaluate_tier : "{CRITERION_ID}_FAIL".
            # Un reason se terminant par "_OPTIONAL" indiquerait un fail non-mandatory
            # (réservé pour extension future — actuellement jamais produit).
            has_mandatory_fail = any(
                "MANDATORY" in r or not r.endswith("_OPTIONAL")
                for r in (minor.fail_reasons or [])
            )
            if has_mandatory_fail:
                return "NOK", SeverityLevel.DEFECT_2, TierLevel.MINOR
            else:
                return "REVIEW", SeverityLevel.REVIEW, TierLevel.MINOR

        # ── 5. Incertitude AI (score < 0.50 dans un Tier) ─────────────────────
        all_scores = [tv.tier_score for tv in tier_verdicts.values() if tv is not None]
        if any(s < _CONFIDENCE_UNCERTAIN for s in all_scores):
            return "REVIEW", SeverityLevel.REVIEW, None

        # ── 6 & 7. Tout OK ────────────────────────────────────────────────────
        overall_score = float(np.mean(all_scores)) if all_scores else 1.0
        severity = (
            SeverityLevel.EXCELLENT if overall_score >= 0.90
            else SeverityLevel.ACCEPTABLE
        )
        return "OK", severity, None
