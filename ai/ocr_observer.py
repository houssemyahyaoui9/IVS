"""
OcrObserver MINOR tier — §14
Lecture texte Tesseract, 3 angles, preprocessing Otsu.
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
GR-11 : jamais None — import manquant / exception → ObserverSignal(confidence=0, error_msg=...)
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

import cv2
import numpy as np

from core.ai_observer import AIObserver
from core.models import CriterionRule, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel

logger = logging.getLogger(__name__)


class OcrObserver(AIObserver):
    """
    Observer OCR Tesseract — §14. Tier MINOR.

    Pour chaque appel observe() :
      1. Recadre la zone OCR normalisée (rule.details["ocr_zone"])
      2. Tente 3 angles [0°, +2°, -2°] — meilleure lecture retenue
      3. Preprocessing : bilateral filter → Otsu threshold → upscale ×2
      4. pytesseract PSM 6 → texte + confiance mot-par-mot
      5. Compare au pattern (rule.details["expected_pattern"])

    GR-04 : passed/confidence = observations numériques brutes, pas de verdict.
    pytesseract optionnel — absent → ObserverSignal(error_msg=...).
    """

    _ANGLES = [0, 2, -2]

    def __init__(self, config: Optional[Any] = None) -> None:
        cfg = config or {}
        if hasattr(cfg, "get"):
            self._confidence_threshold = float(
                cfg.get("observers.ocr.confidence_threshold", 0.70)
            )
            self._language = str(cfg.get("observers.ocr.language", "fra+eng"))
        else:
            self._confidence_threshold = 0.70
            self._language = "fra+eng"

    # ── ABC ───────────────────────────────────────────────────────────────────

    @property
    def observer_id(self) -> str:
        return "ocr_tesseract"

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
            logger.error("OcrObserver: exception non gérée — %s", exc, exc_info=True)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=self._confidence_threshold,
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
            import pytesseract
        except ImportError:
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=self._confidence_threshold,
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                error_msg="pytesseract non installé (pip install pytesseract)",
            )

        details          = rule.details or {}
        expected_pattern = str(details.get("expected_pattern", r".*"))
        ocr_zone         = details.get("ocr_zone")

        best_text = ""
        best_conf = 0.0

        crop = self._extract_ocr_crop(frame, ocr_zone)
        for angle in self._ANGLES:
            rotated      = self._rotate_frame(crop, angle)
            preprocessed = self._preprocess_for_ocr(rotated)

            data = pytesseract.image_to_data(
                preprocessed,
                lang=self._language,
                config="--psm 6",
                output_type=pytesseract.Output.DICT,
            )
            text, conf = self._best_reading(data)
            if conf > best_conf:
                best_text, best_conf = text, conf

        matches_pattern = (
            bool(re.match(expected_pattern, best_text.strip()))
            if best_text else False
        )
        passed = (
            bool(best_text)
            and matches_pattern
            and best_conf >= self._confidence_threshold
        )

        logger.debug(
            "OcrObserver: text='%s' conf=%.2f pattern='%s' matches=%s passed=%s",
            best_text, best_conf, expected_pattern, matches_pattern, passed,
        )

        return ObserverSignal(
            observer_id=self.observer_id,
            tier=TierLevel.MINOR,
            passed=passed,
            confidence=round(best_conf, 3),
            value=round(best_conf, 3),
            threshold=self._confidence_threshold,
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            details={
                "text_found":       best_text,
                "matches_pattern":  matches_pattern,
                "expected_pattern": expected_pattern,
                "angles_tried":     list(self._ANGLES),
            },
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _preprocess_for_ocr(self, img: np.ndarray) -> np.ndarray:
        """Bilateral filter → Otsu threshold → upscale ×2."""
        gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        smooth = cv2.bilateralFilter(gray, 9, 75, 75)
        _, thresh = cv2.threshold(
            smooth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        return cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    def _best_reading(self, data: dict) -> tuple[str, float]:
        """Agrège texte + confiance depuis le dict pytesseract."""
        words: list[str]  = []
        confs: list[float] = []
        for text, conf in zip(data["text"], data["conf"]):
            c = int(conf)
            if c > 0 and text.strip():
                words.append(text.strip())
                confs.append(c / 100.0)
        if not words:
            return "", 0.0
        return " ".join(words), float(np.mean(confs))

    def _extract_ocr_crop(self, frame: np.ndarray, bbox: Optional[dict]) -> np.ndarray:
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

    def _rotate_frame(self, img: np.ndarray, angle: float) -> np.ndarray:
        """Rotation par angle (degrés). 0° → no-op."""
        if angle == 0:
            return img
        h, w = img.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
