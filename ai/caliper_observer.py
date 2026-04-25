"""
CaliperObserver MAJOR tier — §13
Mesure sub-pixel d'un bord via Sobel + Gaussian fit, 10 lectures + filtre 2-sigma.
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
GR-11 : jamais None — échec → ObserverSignal(confidence=0, error_msg=...)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit

from core.ai_observer import AIObserver
from core.models import CriterionRule, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel

logger = logging.getLogger(__name__)

_DEFAULT_PPM = 1.0
_N_READINGS  = 10


# ─────────────────────────────────────────────────────────────────────────────
#  MeasurementDefinition
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MeasurementDefinition:
    """
    Définit une ligne de mesure pour le caliper optique — §13.

    roi_x/roi_y  : coin haut-gauche de la ROI en pixels
    roi_w/roi_h  : dimensions ROI en pixels
    direction    : "horizontal" (profil sur X) | "vertical" (profil sur Y)
    tolerance_mm : tolérance admissible autour de la dimension attendue
    """
    roi_x        : int
    roi_y        : int
    roi_w        : int
    roi_h        : int
    direction    : str    # "horizontal" | "vertical"
    tolerance_mm : float

    def __post_init__(self) -> None:
        if self.roi_w <= 0:
            raise ValueError(f"MeasurementDefinition.roi_w={self.roi_w} doit être > 0")
        if self.roi_h <= 0:
            raise ValueError(f"MeasurementDefinition.roi_h={self.roi_h} doit être > 0")
        if self.direction not in ("horizontal", "vertical"):
            raise ValueError(
                f"MeasurementDefinition.direction='{self.direction}'"
                " — doit être 'horizontal' ou 'vertical'"
            )
        if self.tolerance_mm < 0.0:
            raise ValueError(
                f"MeasurementDefinition.tolerance_mm={self.tolerance_mm} doit être >= 0"
            )


# ─────────────────────────────────────────────────────────────────────────────
#  CaliperObserver
# ─────────────────────────────────────────────────────────────────────────────

class CaliperObserver(AIObserver):
    """
    Pied à coulisse optique — §13. Tier MAJOR.

    Pour chaque appel observe() :
      1. Extrait 10 profils 1D perpendiculaires à la direction de mesure (scan-lines distincts)
      2. Gradient Sobel 1D sur chaque profil
      3. Fit Gaussien sub-pixel pour localiser le bord (µ = position sub-pixel)
      4. Filtre 2-sigma sur les 10 lectures
      5. Conversion pixel → mm via pixel_per_mm calibré (products/{id}/calibration/)
      6. Comparaison à rule.threshold (dimension attendue) avec measurement_def.tolerance_mm

    GR-04 : passed/confidence sont des mesures numériques brutes — verdict exclusif du RuleEngine.
    """

    def __init__(
        self,
        measurement_id : str,
        measurement_def: MeasurementDefinition,
    ) -> None:
        self._measurement_id  = measurement_id
        self._measurement_def = measurement_def
        self._ppm_cache: dict[str, float] = {}

    # ── ABC ───────────────────────────────────────────────────────────────────

    @property
    def observer_id(self) -> str:
        return f"caliper_{self._measurement_id}"

    @property
    def tier(self) -> TierLevel:
        return TierLevel.MAJOR

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def observe(
        self,
        frame      : np.ndarray,
        product_def: ProductDefinition,
        rule       : CriterionRule,
    ) -> ObserverSignal:
        """
        GR-04 : retourne UNIQUEMENT ObserverSignal — jamais de verdict.
        GR-11 : capture toutes les exceptions → ObserverSignal(confidence=0, error_msg=...).
        """
        t0 = time.perf_counter()
        try:
            return self._observe_impl(frame, product_def, rule, t0)
        except Exception as exc:
            logger.error(
                "CaliperObserver[%s]: exception non gérée — %s",
                self._measurement_id, exc, exc_info=True,
            )
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
        frame      : np.ndarray,
        product_def: ProductDefinition,
        rule       : CriterionRule,
        t0         : float,
    ) -> ObserverSignal:
        mdef        = self._measurement_def
        ppm         = self._load_ppm(product_def.product_id)
        expected_mm = rule.threshold      # threshold = dimension attendue (mm)
        tolerance   = mdef.tolerance_mm

        gray = _to_gray(frame)
        roi  = _extract_roi(gray, mdef)

        readings: list[float] = []
        for i in range(_N_READINGS):
            try:
                profile  = _extract_edge_profile(roi, mdef.direction, i, _N_READINGS)
                smoothed = gaussian_filter1d(profile.astype(float), sigma=1.5)
                gradient = np.gradient(smoothed)
                edge_px  = _fit_gaussian_edge(gradient)
                if edge_px is not None:
                    readings.append(edge_px)
            except Exception as exc:
                logger.debug(
                    "CaliperObserver[%s]: lecture %d échouée — %s",
                    self._measurement_id, i, exc,
                )

        if not readings:
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=expected_mm,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error_msg="aucune lecture valide — gradient ou fit Gaussien échoués",
                details={"delta_mm": None, "tolerance_mm": tolerance, "readings_count": 0},
            )

        # Filtre 2-sigma
        arr     = np.array(readings, dtype=float)
        mean_r  = float(np.mean(arr))
        std_r   = float(np.std(arr))
        filtered = [r for r in readings if abs(r - mean_r) <= 2.0 * std_r]
        if not filtered:
            filtered = readings   # std ≈ 0 → toutes les lectures sont identiques

        measured_px  = float(np.mean(filtered))
        measured_mm  = measured_px / max(ppm, 1e-9)
        delta_mm     = abs(measured_mm - expected_mm)
        in_tolerance = delta_mm <= tolerance

        # confidence ∈ [0, 1] : 1.0 si delta=0, 0.0 si delta = 3×tolerance
        denom      = tolerance * 3.0
        confidence = max(0.0, 1.0 - delta_mm / denom) if denom > 0.0 else 1.0

        logger.debug(
            "CaliperObserver[%s]: measured=%.4fmm expected=%.4fmm "
            "delta=%.4fmm tol=%.4fmm passed=%s readings=%d",
            self._measurement_id, measured_mm, expected_mm,
            delta_mm, tolerance, in_tolerance, len(filtered),
        )

        return ObserverSignal(
            observer_id=self.observer_id,
            tier=TierLevel.MAJOR,
            passed=in_tolerance,
            confidence=confidence,
            value=measured_mm,
            threshold=expected_mm,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={
                "delta_mm"      : round(delta_mm, 4),
                "tolerance_mm"  : tolerance,
                "readings_count": len(filtered),
            },
        )

    # ── Chargement paresseux ──────────────────────────────────────────────────

    def _load_ppm(self, product_id: str) -> float:
        """Charge pixel_per_mm depuis calibration/pixel_per_mm.json, mis en cache."""
        if product_id not in self._ppm_cache:
            path = (
                Path("products") / product_id / "calibration" / "pixel_per_mm.json"
            )
            if not path.exists():
                logger.warning(
                    "CaliperObserver[%s]: pixel_per_mm absent — %s — défaut %.1f",
                    self._measurement_id, path, _DEFAULT_PPM,
                )
                self._ppm_cache[product_id] = _DEFAULT_PPM
            else:
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    self._ppm_cache[product_id] = float(
                        data.get("pixel_per_mm", _DEFAULT_PPM)
                    )
                except Exception as exc:
                    logger.error(
                        "CaliperObserver[%s]: échec lecture %s — %s",
                        self._measurement_id, path, exc,
                    )
                    self._ppm_cache[product_id] = _DEFAULT_PPM
        return self._ppm_cache[product_id]


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _gaussian(x: np.ndarray, amp: float, mu: float, sigma: float) -> np.ndarray:
    """Gaussienne 1D pour le fit sub-pixel."""
    return amp * np.exp(-((x - mu) ** 2) / (2.0 * sigma ** 2))


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


def _extract_roi(gray: np.ndarray, mdef: MeasurementDefinition) -> np.ndarray:
    fh, fw = gray.shape[:2]
    x0 = max(0, mdef.roi_x)
    y0 = max(0, mdef.roi_y)
    x1 = min(fw, mdef.roi_x + mdef.roi_w)
    y1 = min(fh, mdef.roi_y + mdef.roi_h)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        raise ValueError(
            f"ROI vide — frame {fw}×{fh}, roi ({x0},{y0})-({x1},{y1})"
        )
    return roi


def _extract_edge_profile(
    roi      : np.ndarray,
    direction: str,
    index    : int,
    total    : int,
) -> np.ndarray:
    """
    Extrait le profil 1D d'un scan-line perpendiculaire à la direction de mesure.

    direction="horizontal" : mesure sur l'axe X → profil = ligne Y[i]
    direction="vertical"   : mesure sur l'axe Y → profil = colonne X[i]

    Les 'total' scan-lines sont distribués uniformément sur la ROI pour
    couvrir l'ensemble de la zone et améliorer la robustesse statistique.
    """
    h, w = roi.shape[:2]
    if direction == "horizontal":
        row = int(round((index + 0.5) / total * h))
        row = max(0, min(h - 1, row))
        return roi[row, :].astype(float)
    else:
        col = int(round((index + 0.5) / total * w))
        col = max(0, min(w - 1, col))
        return roi[:, col].astype(float)


def _fit_gaussian_edge(gradient: np.ndarray) -> Optional[float]:
    """
    Fit Gaussien sur le gradient 1D pour localiser le bord avec précision sub-pixel.

    Retourne µ (position du pic) ou None si :
      - profil trop court (< 5 pts)
      - convergence curve_fit échouée
      - µ hors bornes du profil
    """
    n = len(gradient)
    if n < 5:
        return None

    x        = np.arange(n, dtype=float)
    peak_idx = int(np.argmax(np.abs(gradient)))
    amp0     = float(gradient[peak_idx])
    mu0      = float(peak_idx)
    sig0     = max(1.0, n / 10.0)

    try:
        popt, _ = curve_fit(
            _gaussian,
            x, gradient,
            p0=[amp0, mu0, sig0],
            maxfev=1000,
        )
        mu_fit = float(popt[1])
        if not (0.0 <= mu_fit <= n - 1):
            return None
        return mu_fit
    except RuntimeError:
        return None
