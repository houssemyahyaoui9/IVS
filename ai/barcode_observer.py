"""
BarcodeObserver MINOR tier — §15
pyzbar (1D/QR) + pylibdmtx (DataMatrix) fallback · 4 rotations.
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
GR-11 : jamais None — import manquant / exception → ObserverSignal(confidence=0, error_msg=...)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

from core.ai_observer import AIObserver
from core.models import CriterionRule, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel

logger = logging.getLogger(__name__)

_ROTATIONS = [0, 90, 180, 270]
_DMTX_TIMEOUT_MS = 200


class BarcodeObserver(AIObserver):
    """
    Observer Barcode/QR/DataMatrix — §15. Tier MINOR.

    Pour chaque appel observe() :
      1. Recadre la zone barcode normalisée (rule.details["barcode_zone"])
      2. Convertit en niveaux de gris
      3. Tente 4 rotations [0°, 90°, 180°, 270°] :
         a. pyzbar.decode() — 1D (EAN, Code128, …) + QR Code
         b. pylibdmtx.decode() — DataMatrix (fallback, timeout 200ms)
      4. Compare au code attendu (rule.details["expected_code"])

    pyzbar et pylibdmtx optionnels — absents → ObserverSignal(error_msg=...).
    GR-04 : passed/confidence = observations numériques, pas de verdict.
    """

    # ── ABC ───────────────────────────────────────────────────────────────────

    @property
    def observer_id(self) -> str:
        return "barcode_pyzbar"

    @property
    def tier(self) -> TierLevel:
        return TierLevel.MINOR

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def observe(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
    ) -> ObserverSignal:
        """
        GR-04 : retourne UNIQUEMENT ObserverSignal.
        GR-11 : toutes les exceptions sont capturées (y compris ImportError).
        """
        t0 = time.monotonic()
        try:
            return self._observe_impl(frame, rule, t0)
        except Exception as exc:
            logger.error("BarcodeObserver: exception non gérée — %s", exc, exc_info=True)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=1.0,
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                error_msg=str(exc),
            )

    # ── Implémentation ────────────────────────────────────────────────────────

    def _observe_impl(
        self,
        frame: np.ndarray,
        rule:  CriterionRule,
        t0:    float,
    ) -> ObserverSignal:
        try:
            from pyzbar import pyzbar as _pyzbar
        except ImportError:
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=1.0,
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                error_msg="pyzbar non installé (pip install pyzbar)",
            )

        details       = rule.details or {}
        expected_code = str(details.get("expected_code", ""))
        barcode_zone  = details.get("barcode_zone")

        crop = self._extract_zone(frame, barcode_zone)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop

        found_code  = ""
        found_angle = None

        for angle in _ROTATIONS:
            rotated = self._rotate_gray(gray, angle)

            # pyzbar : 1D barcodes + QR Code
            barcodes = _pyzbar.decode(rotated)
            if barcodes:
                found_code  = barcodes[0].data.decode("utf-8", errors="replace").strip()
                found_angle = angle
                break

            # pylibdmtx : DataMatrix fallback
            dmtx_code = self._try_dmtx(rotated)
            if dmtx_code:
                found_code  = dmtx_code
                found_angle = angle
                break

        found   = bool(found_code)
        matches = (found_code == expected_code) if expected_code else found
        passed  = found and matches

        logger.debug(
            "BarcodeObserver: found='%s' expected='%s' matches=%s passed=%s angle=%s",
            found_code, expected_code, matches, passed, found_angle,
        )

        return ObserverSignal(
            observer_id=self.observer_id,
            tier=TierLevel.MINOR,
            passed=passed,
            confidence=1.0 if found else 0.0,
            value=1.0 if found else 0.0,
            threshold=1.0,
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            details={
                "code_found":      found_code,
                "expected_code":   expected_code,
                "matches":         matches,
                "rotations_tried": list(_ROTATIONS),
                "found_at_angle":  found_angle,
            },
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _try_dmtx(self, gray: np.ndarray) -> str:
        """pylibdmtx DataMatrix decode avec timeout. Retourne '' si absent/erreur."""
        try:
            from pylibdmtx import pylibdmtx as _dmtx
            results = _dmtx.decode(gray, timeout=_DMTX_TIMEOUT_MS)
            if results:
                return results[0].data.decode("utf-8", errors="replace").strip()
        except ImportError:
            pass  # pylibdmtx optionnel — pyzbar suffit pour 1D/QR
        except Exception as exc:
            logger.debug("BarcodeObserver: pylibdmtx erreur — %s", exc)
        return ""

    def _rotate_gray(self, gray: np.ndarray, angle: int) -> np.ndarray:
        """Rotation par multiple de 90°. 0° → no-op."""
        if angle == 0:
            return gray
        if angle == 90:
            return cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)
        if angle == 180:
            return cv2.rotate(gray, cv2.ROTATE_180)
        if angle == 270:
            return cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return gray

    def _extract_zone(self, frame: np.ndarray, bbox: Optional[dict]) -> np.ndarray:
        """Recadre selon bbox normalisée {x, y, w, h} ∈ [0,1]. None → frame entière."""
        if bbox is None:
            return frame
        h, w = frame.shape[:2]
        x1 = max(0, int(bbox["x"] * w))
        y1 = max(0, int(bbox["y"] * h))
        x2 = min(w, int((bbox["x"] + bbox["w"]) * w))
        y2 = min(h, int((bbox["y"] + bbox["h"]) * h))
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size > 0 else frame
