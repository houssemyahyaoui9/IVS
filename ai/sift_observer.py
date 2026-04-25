"""
SiftObserver — inspection logo par logo via SIFT matching
§6.3 · Tier CRITICAL
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
GR-11 : jamais None — échec → ObserverSignal(confidence=0, error_msg=...)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ai.alignment_engine import AlignmentEngine, SiftTemplate
from core.ai_observer import AIObserver
from core.models import CriterionRule, LogoDefinition, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel

logger = logging.getLogger(__name__)

_DEFAULT_PPM = 1.0   # pixel_per_mm par défaut si JSON absent


class SiftObserver(AIObserver):
    """
    Observer SIFT par logo — §6.3.

    Pour chaque LogoDefinition du produit :
      1. Charge le template depuis calibration/logo_{idx}_template.pkl (lazy, mis en cache)
      2. Recadre la frame à la zone attendue + buffer de tolérance
      3. SIFT match via AlignmentEngine.match() → good_matches
      4. match_score = len(good) / len(template_kps), plafonné à 1.0
      5. Calcule position_delta_mm (centroïde des kp matchés vs centre du recadrage)

    Agrégation :
      confidence = min(match_score par logo)   ← worst-case logo
      value      = confidence
      passed     = True si tous les logos ≥ rule.threshold

    GR-04 : passed/confidence sont des observations numériques brutes.
            Le verdict OK/NOK est EXCLUSIVEMENT du ressort de RuleEngine.
    """

    def __init__(self, engine: Optional[AlignmentEngine] = None) -> None:
        self._engine           = engine or AlignmentEngine()
        # Caches stables pendant RUNNING (GR-12 : pas de modification en cours d'inspection)
        self._template_cache: dict[str, Optional[SiftTemplate]] = {}
        self._ppm_cache:      dict[str, float]                  = {}

    # ── ABC ───────────────────────────────────────────────────────────────────

    @property
    def observer_id(self) -> str:
        return "sift"

    @property
    def tier(self) -> TierLevel:
        return TierLevel.CRITICAL

    # ── Point d'entrée principal ──────────────────────────────────────────────

    def observe(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
    ) -> ObserverSignal:
        """
        GR-04 : retourne UNIQUEMENT ObserverSignal — jamais de verdict.
        GR-11 : capture toutes les exceptions → ObserverSignal(confidence=0, error_msg=...).
        """
        t0 = time.perf_counter()
        try:
            return self._observe_impl(frame, product_def, rule, t0)
        except Exception as exc:
            logger.error("SiftObserver: exception non gérée — %s", exc, exc_info=True)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=rule.threshold,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error_msg=str(exc),
            )

    # ── Implémentation ────────────────────────────────────────────────────────

    def _observe_impl(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
        t0:          float,
    ) -> ObserverSignal:
        ppm   = self._load_ppm(product_def.product_id)
        logos = product_def.logo_definitions

        if not logos:
            logger.debug("SiftObserver: aucun logo défini pour '%s' — pass automatique",
                         product_def.product_id)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=True,
                confidence=1.0,
                value=1.0,
                threshold=rule.threshold,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                details={"logos": [], "note": "no logos defined"},
            )

        logo_results = [
            self._check_logo(frame, product_def.product_id, idx, logo_def, ppm)
            for idx, logo_def in enumerate(logos)
        ]

        scores     = [r["match_score"] for r in logo_results]
        min_score  = min(scores)
        all_passed = all(s >= rule.threshold for s in scores)

        logger.debug(
            "SiftObserver: '%s' logos=%d min_score=%.3f threshold=%.3f passed=%s",
            product_def.product_id, len(logos), min_score, rule.threshold, all_passed,
        )

        return ObserverSignal(
            observer_id=self.observer_id,
            tier=self.tier,
            passed=all_passed,
            confidence=min_score,
            value=min_score,
            threshold=rule.threshold,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={"logos": logo_results},
        )

    # ── Vérification d'un logo ────────────────────────────────────────────────

    def _check_logo(
        self,
        frame:      np.ndarray,
        product_id: str,
        idx:        int,
        logo_def:   LogoDefinition,
        ppm:        float,
    ) -> dict:
        """Retourne un dict de résultat pour ce logo (jamais None — GR-11)."""
        template = self._load_template(product_id, idx)
        if template is None:
            return {
                "logo_id":      logo_def.logo_id,
                "match_score":  0.0,
                "good_matches": 0,
                "pos_delta_mm": 0.0,
                "error": (
                    f"template absent — products/{product_id}"
                    f"/calibration/logo_{idx}_template.pkl"
                ),
            }

        # Zone attendue en pixels + buffer de tolérance
        zone_px = logo_def.expected_zone.to_pixel(ppm)
        buf_px  = max(2, int(logo_def.tolerance_mm * ppm))

        fh, fw = frame.shape[:2]
        x0 = max(0, int(zone_px.x) - buf_px)
        y0 = max(0, int(zone_px.y) - buf_px)
        x1 = min(fw, int(zone_px.x + zone_px.w) + buf_px)
        y1 = min(fh, int(zone_px.y + zone_px.h) + buf_px)

        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return {
                "logo_id":      logo_def.logo_id,
                "match_score":  0.0,
                "good_matches": 0,
                "pos_delta_mm": 0.0,
                "error":        f"recadrage vide — zone ({x0},{y0})-({x1},{y1}) hors frame",
            }

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        kp_q, good = self._engine.match(gray, template)

        n_good      = len(good)
        match_score = min(1.0, n_good / max(1, len(template)))

        pos_delta_mm = _position_delta_mm(kp_q, good, x0, y0, x1, y1, ppm)

        return {
            "logo_id":      logo_def.logo_id,
            "match_score":  round(match_score, 4),
            "good_matches": n_good,
            "pos_delta_mm": round(pos_delta_mm, 3),
        }

    # ── Chargement paresseux ──────────────────────────────────────────────────

    def _load_template(self, product_id: str, idx: int) -> Optional[SiftTemplate]:
        """
        Charge logo_{idx}_template.pkl depuis calibration/, mis en cache.
        Retourne None si absent ou illisible.
        """
        key = f"{product_id}/logo_{idx}"
        if key not in self._template_cache:
            path = (Path("products") / product_id / "calibration"
                    / f"logo_{idx}_template.pkl")
            if not path.exists():
                logger.warning("SiftObserver: template absent — %s", path)
                self._template_cache[key] = None
            else:
                try:
                    tpl = SiftTemplate.from_file(path)
                    self._template_cache[key] = tpl
                    logger.info("SiftObserver: template chargé — %s (%d kp)", path, len(tpl))
                except Exception as exc:
                    logger.error("SiftObserver: échec chargement %s — %s", path, exc)
                    self._template_cache[key] = None
        return self._template_cache[key]

    def _load_ppm(self, product_id: str) -> float:
        """
        Charge pixel_per_mm depuis calibration/pixel_per_mm.json, mis en cache.
        Retourne _DEFAULT_PPM si absent ou illisible.
        """
        if product_id not in self._ppm_cache:
            path = (Path("products") / product_id / "calibration"
                    / "pixel_per_mm.json")
            if not path.exists():
                logger.warning("SiftObserver: pixel_per_mm absent — %s — défaut %.1f",
                               path, _DEFAULT_PPM)
                self._ppm_cache[product_id] = _DEFAULT_PPM
            else:
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    self._ppm_cache[product_id] = float(
                        data.get("pixel_per_mm", _DEFAULT_PPM)
                    )
                except Exception as exc:
                    logger.error("SiftObserver: échec lecture %s — %s", path, exc)
                    self._ppm_cache[product_id] = _DEFAULT_PPM
        return self._ppm_cache[product_id]


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _position_delta_mm(
    kp_q: list,
    good: list,
    x0:   int,
    y0:   int,
    x1:   int,
    y1:   int,
    ppm:  float,
) -> float:
    """Delta entre centroïde des kp matchés et centre du recadrage, en mm."""
    if not good or not kp_q:
        return 0.0
    pts     = np.array([kp_q[m.trainIdx].pt for m in good], dtype=np.float32)
    cx_det  = float(pts[:, 0].mean())
    cy_det  = float(pts[:, 1].mean())
    cx_exp  = (x1 - x0) / 2.0
    cy_exp  = (y1 - y0) / 2.0
    delta_px = float(np.hypot(cx_det - cx_exp, cy_det - cy_exp))
    return delta_px / max(ppm, 1e-6)
