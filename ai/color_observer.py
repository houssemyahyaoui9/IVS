"""
ColorObserver MAJOR tier — §6.4
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
GR-11 : jamais None — échec → ObserverSignal(confidence=0, error_msg=...)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from ai.color_inspector import ColorInspector
from core.ai_observer import AIObserver
from core.models import CriterionRule, LogoDefinition, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel

logger = logging.getLogger(__name__)

_DEFAULT_PPM       = 1.0
_DE_CONFIDENCE_MAX = 30.0   # ΔE2000 au-delà duquel confidence = 0


class ColorObserver(AIObserver):
    """
    Observer couleur ΔE2000 — §6.4.

    Pour chaque LogoDefinition du produit :
      1. Extrait le crop de la zone attendue (expected_zone × ppm_x/ppm_y)
      2. Calcule la couleur dominante via K-means k=5 CIE LAB
      3. Compare à la référence calibrée (color_reference.json) via ΔE2000
      4. passed = delta_e ≤ rule.threshold (threshold = ΔE max, défaut 8.0)

    Agrégation multi-logo :
      value      = max(delta_e)   ← pire logo
      confidence = max(0, 1 - max_delta_e / 30)
      passed     = all delta_e ≤ threshold
      details    = {"logos": [...], "max_delta_e": ...}

    GR-04 : retourne UNIQUEMENT ObserverSignal — jamais "OK", "NOK", True, False.
    GR-11 : try/except global → ObserverSignal(confidence=0, error_msg=...).
    """

    def __init__(self, inspector: Optional[ColorInspector] = None) -> None:
        self._inspector = inspector or ColorInspector()
        # Caches stables pendant RUNNING (GR-12)
        self._color_ref_cache: dict[str, dict] = {}   # product_id → color_reference
        self._ppm_cache:       dict[str, tuple[float, float]] = {}  # id → (ppm_x, ppm_y)

    # ── ABC ───────────────────────────────────────────────────────────────────

    @property
    def observer_id(self) -> str:
        return "color_de2000"

    @property
    def tier(self) -> TierLevel:
        return TierLevel.MAJOR

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
            logger.error("ColorObserver: exception non gérée — %s", exc, exc_info=True)
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
        logos     = product_def.logo_definitions
        color_ref = self._load_color_reference(product_def.product_id)
        ppm_x, ppm_y = self._load_ppm(product_def.product_id)

        if not logos:
            logger.debug("ColorObserver: aucun logo défini pour '%s' — pass automatique",
                         product_def.product_id)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=True,
                confidence=1.0,
                value=0.0,
                threshold=rule.threshold,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                details={"logos": [], "note": "no logos defined"},
            )

        logo_results = [
            self._check_logo(frame, logo_def, color_ref, ppm_x, ppm_y, rule.threshold)
            for logo_def in logos
        ]

        delta_es   = [r["delta_e"] for r in logo_results]
        max_de     = max(delta_es)
        all_passed = all(r["passed"] for r in logo_results)
        confidence = max(0.0, 1.0 - max_de / _DE_CONFIDENCE_MAX)

        logger.debug(
            "ColorObserver: '%s' logos=%d max_ΔE=%.2f threshold=%.2f passed=%s",
            product_def.product_id, len(logos), max_de, rule.threshold, all_passed,
        )

        return ObserverSignal(
            observer_id=self.observer_id,
            tier=self.tier,
            passed=all_passed,
            confidence=confidence,
            value=round(max_de, 4),
            threshold=rule.threshold,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={
                "logos":       logo_results,
                "max_delta_e": round(max_de, 4),
            },
        )

    # ── Vérification d'un logo ────────────────────────────────────────────────

    def _check_logo(
        self,
        frame:     np.ndarray,
        logo_def:  LogoDefinition,
        color_ref: dict,
        ppm_x:     float,
        ppm_y:     float,
        threshold: float,
    ) -> dict:
        """Mesure le ΔE2000 pour ce logo. Retourne un dict (jamais None — GR-11)."""
        # Référence calibrée
        ref_entry = color_ref.get(logo_def.logo_id)
        if ref_entry is None:
            logger.warning(
                "ColorObserver: pas de référence pour logo '%s' — ΔE=0 pass forcé",
                logo_def.logo_id,
            )
            return {
                "logo_id": logo_def.logo_id,
                "delta_e": 0.0,
                "passed":  True,
                "error":   "reference absente — color_reference.json",
                "measured_lab": None,
                "ref_lab":      None,
            }

        ref_lab = ref_entry["lab_mean"]

        # Crop de la zone attendue
        crop = _extract_logo_crop(frame, logo_def, ppm_x, ppm_y)
        if crop is None or crop.size == 0:
            logger.warning(
                "ColorObserver: crop vide pour logo '%s' — ΔE=oo",
                logo_def.logo_id,
            )
            return {
                "logo_id":      logo_def.logo_id,
                "delta_e":      _DE_CONFIDENCE_MAX,
                "passed":       False,
                "error":        "crop vide — zone hors frame",
                "measured_lab": None,
                "ref_lab":      ref_lab,
            }

        measured_lab = self._inspector.dominant_color_lab(crop, k=5)
        delta_e      = self._inspector.delta_e_2000(measured_lab, ref_lab)

        return {
            "logo_id":      logo_def.logo_id,
            "delta_e":      round(delta_e, 4),
            "passed":       delta_e <= threshold,
            "measured_lab": measured_lab.tolist(),
            "ref_lab":      ref_lab,
        }

    # ── Chargement paresseux ──────────────────────────────────────────────────

    def _load_color_reference(self, product_id: str) -> dict:
        """Charge color_reference.json depuis calibration/, mis en cache."""
        if product_id not in self._color_ref_cache:
            path = (Path("products") / product_id / "calibration"
                    / "color_reference.json")
            if not path.exists():
                logger.warning(
                    "ColorObserver: color_reference absent — %s — références vides",
                    path,
                )
                self._color_ref_cache[product_id] = {}
            else:
                try:
                    with open(path, encoding="utf-8") as fh:
                        self._color_ref_cache[product_id] = json.load(fh)
                except Exception as exc:
                    logger.error("ColorObserver: échec lecture %s — %s", path, exc)
                    self._color_ref_cache[product_id] = {}
        return self._color_ref_cache[product_id]

    def _load_ppm(self, product_id: str) -> tuple[float, float]:
        """
        Charge pixel_per_mm_x et pixel_per_mm_y depuis calibration/pixel_per_mm.json.
        Retourne (_DEFAULT_PPM, _DEFAULT_PPM) si absent.
        """
        if product_id not in self._ppm_cache:
            path = (Path("products") / product_id / "calibration"
                    / "pixel_per_mm.json")
            if not path.exists():
                logger.warning(
                    "ColorObserver: pixel_per_mm absent — %s — défaut %.1f",
                    path, _DEFAULT_PPM,
                )
                self._ppm_cache[product_id] = (_DEFAULT_PPM, _DEFAULT_PPM)
            else:
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    ppm_x = float(data.get("pixel_per_mm_x", _DEFAULT_PPM))
                    ppm_y = float(data.get("pixel_per_mm_y", _DEFAULT_PPM))
                    self._ppm_cache[product_id] = (ppm_x, ppm_y)
                except Exception as exc:
                    logger.error("ColorObserver: échec lecture %s — %s", path, exc)
                    self._ppm_cache[product_id] = (_DEFAULT_PPM, _DEFAULT_PPM)
        return self._ppm_cache[product_id]


# ─────────────────────────────────────────────────────────────────────────────
#  Helper crop — identique à CalibrationEngine._extract_logo_crop (§10 Étape 6)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_logo_crop(
    image:    np.ndarray,
    logo_def: LogoDefinition,
    ppm_x:    float,
    ppm_y:    float,
) -> Optional[np.ndarray]:
    """
    Extrait le crop de la zone logo en pixels depuis les coordonnées mm.
    Logique identique à CalibrationEngine._extract_logo_crop pour cohérence.
    """
    H, W = image.shape[:2]
    bbox = logo_def.expected_zone

    x  = int(round(bbox.x * ppm_x))
    y  = int(round(bbox.y * ppm_y))
    bw = int(round(bbox.w * ppm_x))
    bh = int(round(bbox.h * ppm_y))

    x, y   = max(0, x), max(0, y)
    bw, bh = min(bw, W - x), min(bh, H - y)

    if bw <= 0 or bh <= 0:
        return None

    return image[y:y + bh, x:x + bw]
