"""
S3 Alignment — SIFT homography + correction perspective
Entrée : ProcessedFrame
Sortie : AlignedFrame
Délègue entièrement à AlignmentEngine (§6.3).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ai.alignment_engine import AlignmentEngine, SiftTemplate
from core.config_manager import ConfigManager
from pipeline.frames import AlignedFrame, ProcessedFrame

logger = logging.getLogger(__name__)


class S3Alignment:
    """
    Stage 3 — Alignement SIFT global.

    Aligne la frame sur le template de référence via AlignmentEngine.align().
    Si pas de template chargé → retourne la frame telle quelle (alignment_score=0).
    """

    def __init__(self, config: ConfigManager) -> None:
        self._engine   = AlignmentEngine()
        self._template: Optional[SiftTemplate] = None

        product_id = config.get("active_product.product_id", "")
        if product_id:
            path = Path(f"products/{product_id}/calibration/sift_template.pkl")
            if path.exists():
                self.load_template(path)

    def load_template(self, path: Path) -> None:
        """Charge un template SIFT depuis le disque (appelé après calibration)."""
        try:
            self._template = SiftTemplate.from_file(path)
            logger.info("S3: template chargé (%d kp) depuis %s",
                        len(self._template), path)
        except Exception as exc:
            logger.warning("S3: impossible de charger le template %s : %s", path, exc)
            self._template = None

    def process(self, proc: ProcessedFrame) -> AlignedFrame:
        """
        Aligne la frame sur le template via AlignmentEngine.

        Returns:
            AlignedFrame — jamais None (GR-11).
        """
        if self._template is None:
            logger.debug("S3: pas de template — frame transmise sans alignement")
            return AlignedFrame(
                frame_id=proc.frame_id,
                image=proc.image,
                homography=None,
                alignment_score=0.0,
                timestamp=proc.timestamp,
            )

        return self._engine.align(
            frame=proc.image,
            template=self._template,
            frame_id=proc.frame_id,
            timestamp=proc.timestamp,
        )
