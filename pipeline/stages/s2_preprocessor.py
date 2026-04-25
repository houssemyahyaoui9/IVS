"""
S2 PreProcess — CLAHE + LuminosityChecker
Entrée : RawFrame
Sortie : ProcessedFrame
"""
from __future__ import annotations

import logging

import cv2

from camera.camera_manager import RawFrame
from core.config_manager import ConfigManager
from pipeline.frames import ProcessedFrame
from pipeline.stages.luminosity_checker import LuminosityChecker

logger = logging.getLogger(__name__)


class S2Preprocessor:
    """
    Stage 2 — Prétraitement.

    1. Contrôle de luminosité via LuminosityChecker (§42)
    2. CLAHE sur canal L (CIE LAB) pour normaliser l'éclairage

    LuminosityChecker est injecté et doit être pré-chargé depuis la
    référence de calibration avant la boucle d'inspection (GR-06).
    """

    def __init__(
        self,
        luminosity_checker: LuminosityChecker,
        config: ConfigManager,
    ) -> None:
        self._lum_checker = luminosity_checker

        # Chargé une fois à l'init (GR-06)
        clip_limit = config.get("preprocessing.clahe_clip_limit", 2.0)
        tile_grid  = config.get("preprocessing.clahe_tile_grid", 8)
        self._clahe = cv2.createCLAHE(
            clipLimit=float(clip_limit),
            tileGridSize=(int(tile_grid), int(tile_grid)),
        )

    def process(self, raw: RawFrame) -> ProcessedFrame:
        """
        Applique CLAHE et contrôle la luminosité.

        Returns:
            ProcessedFrame — jamais None (GR-11).
        """
        # ── Luminosité ────────────────────────────────────────────────────────
        lum_result = self._lum_checker.check(raw)
        logger.debug("S2: luminosité=%.1f delta=%.1f%% ok=%s",
                     lum_result.value, lum_result.delta_percent, lum_result.ok)

        # ── CLAHE ─────────────────────────────────────────────────────────────
        lab   = cv2.cvtColor(raw.image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_eq  = self._clahe.apply(l)
        lab_eq = cv2.merge([l_eq, a, b])
        processed = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)

        return ProcessedFrame(
            frame_id=raw.frame_id,
            image=processed,
            luminosity=lum_result,
            timestamp=raw.timestamp,
        )
