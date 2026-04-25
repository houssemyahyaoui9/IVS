"""
S1 Acquisition — capture frame depuis CameraManager
Sortie : RawFrame
GR-11 : lève CameraError si acquisition échoue (jamais None)
"""
from __future__ import annotations

import logging

from camera.camera_manager import CameraManager, RawFrame
from core.exceptions import CameraError

logger = logging.getLogger(__name__)


class S1Acquisition:
    """
    Stage 1 — Acquisition.
    Capture une frame brute depuis le backend caméra actif.
    """

    def __init__(self, camera: CameraManager) -> None:
        self._camera = camera

    def process(self, _: None = None) -> RawFrame:
        """
        Capture une frame.

        Returns:
            RawFrame — jamais None (GR-11).

        Raises:
            CameraError : si le backend caméra est indisponible.
        """
        if not self._camera.is_connected():
            raise CameraError("S1: caméra non connectée")
        frame = self._camera.grab_frame()
        if frame is None:
            raise CameraError("S1: grab_frame a retourné None — violation GR-11")
        logger.debug("S1: frame acquise frame_id=%s", frame.frame_id)
        return frame
