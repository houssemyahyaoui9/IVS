"""
LogoInspectionEngine — helper d'inspection logo par logo — §37.2.

⚠️ Note v7.0 :
    LogoInspectionEngine n'est PAS un AIObserver — c'est un HELPER.
    Ses LogoResult sont consommés par YoloObserver / SiftObserver /
    ColorObserver qui les transforment en ObserverSignal (GR-04).

Pipeline par logo :
    1. Crop = frame[expected_zone ± tolerance_mm]
    2. SIFT match contre template du logo → match_score, center_px
    3. ΔE2000 entre couleur dominante du crop et couleur référence
    4. position_delta_mm = distance(center détecté, expected center)
    5. passed = (sift ≥ 0.70) AND (ΔE ≤ tol_de) AND (delta_pos ≤ tol_mm)

GR-01 : déterministe (SIFT déterministe ; K-means seed=42 ColorInspector).
GR-04 : aucune émission ObserverSignal, retourne uniquement des LogoResult.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  LogoResult — frozen dataclass v7.0
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LogoResult:
    """
    Résultat d'inspection d'un logo individuel — §37.2.

    Champs :
      logo_id           — identifiant texte du logo (LogoDefinition.logo_id)
      logo_index        — index 1-based dans la liste des logos
      found             — vrai si le logo a été détecté avec un score utile
      match_score       — score SIFT [0,1] (inliers/keypoints)
      color_delta_e     — ΔE2000 entre crop et référence couleur (0.0 si pas de réf)
      position_delta_mm — distance (mm) entre centre détecté et centre attendu
      passed            — verdict booléen combiné (utilisé par les observers)
      fail_reasons      — raisons d'échec (codes courts en MAJUSCULES)
    """
    logo_id           : str
    logo_index        : int
    found             : bool
    match_score       : float
    color_delta_e     : float
    position_delta_mm : float
    passed            : bool
    fail_reasons      : tuple[str, ...]


# ─────────────────────────────────────────────────────────────────────────────
#  Protocols pour injection de dépendances
# ─────────────────────────────────────────────────────────────────────────────

class _ColorInspectorProto(Protocol):
    def dominant_color_lab(self, crop: np.ndarray, k: int = 5) -> np.ndarray: ...
    def delta_e_2000(self, lab1: np.ndarray, lab2: np.ndarray) -> float: ...


class _SiftMatcherProto(Protocol):
    def match(
        self,
        crop_bgr   : np.ndarray,
        template   : Any,
    ) -> tuple[float, Optional[tuple[float, float]]]:
        """Retourne (match_score [0,1], center_px (x, y) | None)."""


# ─────────────────────────────────────────────────────────────────────────────
#  SIFT matcher inline (par défaut) — utilisé si aucun injecté
# ─────────────────────────────────────────────────────────────────────────────

class _DefaultSiftMatcher:
    """Matcher SIFT minimal (cv2.SIFT_create + BFMatcher + Lowe ratio)."""

    _LOWE_RATIO     : float = 0.75
    _MIN_GOOD       : int   = 4

    def __init__(self) -> None:
        try:
            import cv2
            self._cv2     = cv2
            self._sift    = cv2.SIFT_create()
            self._matcher = cv2.BFMatcher(cv2.NORM_L2)
        except Exception as e:
            logger.warning("SIFT indisponible : %s — score sera 0.0", e)
            self._cv2 = None

    def match(
        self,
        crop_bgr : np.ndarray,
        template : Any,
    ) -> tuple[float, Optional[tuple[float, float]]]:
        if self._cv2 is None or template is None or crop_bgr is None or crop_bgr.size == 0:
            return 0.0, None

        # Template peut être : np.ndarray (image), ou objet ayant .descriptors+.keypoints
        tpl_kp, tpl_desc = _extract_template_features(template, self._sift, self._cv2)
        if tpl_desc is None or len(tpl_kp) < self._MIN_GOOD:
            return 0.0, None

        gray = self._cv2.cvtColor(crop_bgr, self._cv2.COLOR_BGR2GRAY) \
               if crop_bgr.ndim == 3 else crop_bgr
        kp_crop, desc_crop = self._sift.detectAndCompute(gray, None)
        if desc_crop is None or len(kp_crop) < self._MIN_GOOD:
            return 0.0, None

        try:
            matches = self._matcher.knnMatch(tpl_desc, desc_crop, k=2)
        except Exception:
            return 0.0, None

        good = []
        for pair in matches:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.distance < self._LOWE_RATIO * n.distance:
                good.append(m)

        if len(good) < self._MIN_GOOD:
            return 0.0, None

        # Centroïde des keypoints crop matchés (en pixels du crop)
        cx = float(np.mean([kp_crop[m.trainIdx].pt[0] for m in good]))
        cy = float(np.mean([kp_crop[m.trainIdx].pt[1] for m in good]))

        score = min(1.0, len(good) / max(len(tpl_kp), 1))
        return score, (cx, cy)


def _extract_template_features(template: Any, sift: Any, cv2_mod: Any):
    """Retourne (keypoints, descriptors) que le template soit image ou objet pré-calculé."""
    kp = getattr(template, "keypoints", None)
    desc = getattr(template, "descriptors", None)
    if desc is not None and kp is not None:
        return kp, desc
    if isinstance(template, np.ndarray):
        gray = cv2_mod.cvtColor(template, cv2_mod.COLOR_BGR2GRAY) \
               if template.ndim == 3 else template
        return sift.detectAndCompute(gray, None)
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
#  ColorInspector inline (fallback si aucun injecté)
# ─────────────────────────────────────────────────────────────────────────────

class _DefaultColorInspector:
    """Wrapper paresseux qui essaye core/color_inspector.ColorInspector."""

    def __init__(self) -> None:
        self._impl: Optional[_ColorInspectorProto] = None
        # Tentatives d'import (inner package vide → fallback outer)
        for path in (
            "ts2i_ivs.ai.color_inspector",
            "ai.color_inspector",
        ):
            try:
                mod = __import__(path, fromlist=["ColorInspector"])
                cls = getattr(mod, "ColorInspector", None)
                if cls is not None:
                    self._impl = cls()
                    break
            except Exception:
                continue

    def dominant_color_lab(self, crop: np.ndarray, k: int = 5) -> np.ndarray:
        if self._impl is not None:
            return self._impl.dominant_color_lab(crop, k=k)
        return _inline_dominant_color_lab(crop, k=k)

    def delta_e_2000(self, lab1: np.ndarray, lab2: np.ndarray) -> float:
        if self._impl is not None:
            return self._impl.delta_e_2000(lab1, lab2)
        return _inline_delta_e_simple(lab1, lab2)


def _inline_dominant_color_lab(crop: np.ndarray, k: int = 5) -> np.ndarray:
    """Fallback : moyenne LAB du crop (sans K-means)."""
    if crop is None or crop.size == 0:
        return np.zeros(3, dtype=np.float32)
    try:
        import cv2
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    except Exception:
        return np.zeros(3, dtype=np.float32)
    return lab.reshape(-1, 3).mean(axis=0)


def _inline_delta_e_simple(lab1: np.ndarray, lab2: np.ndarray) -> float:
    """Fallback : ΔE76 (distance euclidienne LAB) — moins précis que ΔE2000."""
    a = np.asarray(lab1, dtype=np.float64).ravel()
    b = np.asarray(lab2, dtype=np.float64).ravel()
    if a.size < 3 or b.size < 3:
        return 0.0
    # Conversion échelle OpenCV (0-255) → CIE LAB
    a_cie = np.array([a[0] * 100.0 / 255.0, a[1] - 128.0, a[2] - 128.0])
    b_cie = np.array([b[0] * 100.0 / 255.0, b[1] - 128.0, b[2] - 128.0])
    return float(math.sqrt(float(np.sum((a_cie - b_cie) ** 2))))


# ─────────────────────────────────────────────────────────────────────────────
#  LogoInspectionEngine
# ─────────────────────────────────────────────────────────────────────────────

class LogoInspectionEngine:
    """
    Inspecte chaque logo défini dans `product_def.logo_definitions`.

    Construction :
        engine = LogoInspectionEngine(
            templates       = {"logo_1": <ndarray|template>, ...},
            reference_lab   = {"logo_1": np.array([L,a,b]), ...},
            pixel_per_mm    = 2.40,    # depuis CalibrationEngine étape 4
            sift_threshold  = 0.70,
        )
        results = engine.inspect_all_logos(frame, product_def)
    """

    DEFAULT_SIFT_THRESHOLD : float = 0.70
    DEFAULT_COLOR_TOL_DE   : float = 8.0
    DEFAULT_POS_TOL_MM     : float = 5.0

    def __init__(
        self,
        templates        : Optional[dict[str, Any]]        = None,
        reference_lab    : Optional[dict[str, np.ndarray]] = None,
        pixel_per_mm     : float                           = 1.0,
        sift_threshold   : float                           = 0.70,
        color_inspector  : Optional[_ColorInspectorProto]  = None,
        sift_matcher     : Optional[_SiftMatcherProto]     = None,
    ) -> None:
        self._templates       = dict(templates or {})
        self._reference_lab   = dict(reference_lab or {})
        self._pixel_per_mm    = max(1e-6, float(pixel_per_mm))
        self._sift_threshold  = float(sift_threshold)
        self._color_inspector = color_inspector or _DefaultColorInspector()
        self._sift_matcher    = sift_matcher    or _DefaultSiftMatcher()

    # ── API publique ─────────────────────────────────────────────────────────

    def inspect_all_logos(
        self,
        frame       : np.ndarray,
        product_def : Any,
    ) -> list[LogoResult]:
        """
        Pour chaque logo_def dans product_def.logo_definitions → LogoResult.
        Tolérant aux frames vides / templates manquants (LogoResult dégradé).
        """
        if frame is None or frame.size == 0:
            logger.warning("inspect_all_logos: frame vide — retour list vide")
            return []
        logos = list(getattr(product_def, "logo_definitions", []) or [])
        results: list[LogoResult] = []
        for idx, logo_def in enumerate(logos, start=1):
            results.append(self._inspect_one(frame, logo_def, idx))
        return results

    # ── Inspection d'un logo ─────────────────────────────────────────────────

    def _inspect_one(
        self,
        frame      : np.ndarray,
        logo_def   : Any,
        logo_index : int,
    ) -> LogoResult:
        logo_id  = getattr(logo_def, "logo_id", f"logo_{logo_index}")
        zone_mm  = getattr(logo_def, "expected_zone", None)
        tol_mm   = float(getattr(logo_def, "tolerance_mm", self.DEFAULT_POS_TOL_MM))
        tol_de   = float(getattr(logo_def, "color_tolerance_de", self.DEFAULT_COLOR_TOL_DE))

        if zone_mm is None:
            return LogoResult(
                logo_id=logo_id, logo_index=logo_index, found=False,
                match_score=0.0, color_delta_e=0.0, position_delta_mm=0.0,
                passed=False, fail_reasons=("ZONE_MISSING",),
            )

        # 1) Crop frame[zone ± tolerance]
        crop, crop_origin_px, expected_center_px = self._crop_zone(frame, zone_mm, tol_mm)
        if crop is None or crop.size == 0:
            return LogoResult(
                logo_id=logo_id, logo_index=logo_index, found=False,
                match_score=0.0, color_delta_e=0.0, position_delta_mm=0.0,
                passed=False, fail_reasons=("CROP_EMPTY",),
            )

        # 2) SIFT match
        template = self._templates.get(logo_id)
        match_score, center_in_crop = self._sift_matcher.match(crop, template)
        found = match_score >= max(0.01, self._sift_threshold * 0.5)

        # 3) ΔE2000 si référence connue
        ref_lab = self._reference_lab.get(logo_id)
        if ref_lab is not None:
            crop_lab = self._color_inspector.dominant_color_lab(crop)
            color_de = float(self._color_inspector.delta_e_2000(crop_lab, ref_lab))
        else:
            color_de = 0.0

        # 4) position_delta_mm = distance(center détecté, expected center)
        if center_in_crop is not None:
            cx_px = crop_origin_px[0] + center_in_crop[0]
            cy_px = crop_origin_px[1] + center_in_crop[1]
            dx_px = cx_px - expected_center_px[0]
            dy_px = cy_px - expected_center_px[1]
            position_delta_px = math.hypot(dx_px, dy_px)
            position_delta_mm = position_delta_px / self._pixel_per_mm
        else:
            position_delta_mm = float("inf")

        # 5) Verdict combiné
        fails: list[str] = []
        if match_score < self._sift_threshold:
            fails.append(f"SIFT_LOW_{match_score:.2f}")
        if ref_lab is not None and color_de > tol_de:
            fails.append(f"COLOR_DE_{color_de:.1f}_GT_{tol_de:.1f}")
        if not math.isfinite(position_delta_mm):
            fails.append("POSITION_NOT_FOUND")
        elif position_delta_mm > tol_mm:
            fails.append(f"POS_DELTA_{position_delta_mm:.1f}MM_GT_{tol_mm:.1f}MM")

        passed = (
            match_score       >= self._sift_threshold
            and (ref_lab is None or color_de <= tol_de)
            and math.isfinite(position_delta_mm)
            and position_delta_mm <= tol_mm
        )

        return LogoResult(
            logo_id           = logo_id,
            logo_index        = logo_index,
            found             = bool(found),
            match_score       = float(match_score),
            color_delta_e     = float(color_de),
            position_delta_mm = float(position_delta_mm if math.isfinite(position_delta_mm)
                                     else 0.0),
            passed            = bool(passed),
            fail_reasons      = tuple(fails),
        )

    # ── Crop avec tolérance ─────────────────────────────────────────────────

    def _crop_zone(
        self,
        frame   : np.ndarray,
        zone_mm : Any,
        tol_mm  : float,
    ) -> tuple[Optional[np.ndarray], tuple[float, float], tuple[float, float]]:
        """
        Renvoie (crop_BGR, origin_px (x0, y0), expected_center_px (cx, cy)).
        Toutes les coordonnées en pixels frame.
        """
        ppm = self._pixel_per_mm
        x_mm = float(getattr(zone_mm, "x", 0.0))
        y_mm = float(getattr(zone_mm, "y", 0.0))
        w_mm = float(getattr(zone_mm, "w", 0.0))
        h_mm = float(getattr(zone_mm, "h", 0.0))

        x_px  = x_mm * ppm
        y_px  = y_mm * ppm
        w_px  = max(1.0, w_mm * ppm)
        h_px  = max(1.0, h_mm * ppm)
        tol_px = tol_mm * ppm

        x0 = int(round(max(0, x_px - tol_px)))
        y0 = int(round(max(0, y_px - tol_px)))
        x1 = int(round(min(frame.shape[1], x_px + w_px + tol_px)))
        y1 = int(round(min(frame.shape[0], y_px + h_px + tol_px)))

        if x1 <= x0 or y1 <= y0:
            return None, (0.0, 0.0), (0.0, 0.0)

        crop          = frame[y0:y1, x0:x1].copy()
        center_px     = (x_px + w_px / 2.0, y_px + h_px / 2.0)
        return crop, (float(x0), float(y0)), center_px
