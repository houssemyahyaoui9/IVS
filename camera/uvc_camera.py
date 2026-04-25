"""
uvc_camera — TS2I IVS v7.0
UVC/V4L2 backend — implémentation Phase caméra production
"""
from __future__ import annotations

from camera.camera_manager import CameraBackend, RawFrame
from core.config_manager import ConfigManager
from core.exceptions import CameraError


class UvcCamera(CameraBackend):
    """
    Backend UVC/V4L2 pour caméra USB industrielle.
    Implémentation complète : Phase caméra production.
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config   = config
        self._cap      = None
        self._running  = False

    def start(self) -> None:
        try:
            import cv2  # type: ignore[import]
            device_id = self._config.get("camera.device_id", 0)
            self._cap  = cv2.VideoCapture(device_id)
            if not self._cap.isOpened():
                raise CameraError(f"UvcCamera : impossible d'ouvrir device {device_id}")
            w = self._config.get("camera.resolution.width",  1920)
            h = self._config.get("camera.resolution.height", 1080)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            fps = self._config.get("camera.fps", 5)
            self._cap.set(cv2.CAP_PROP_FPS, fps)
            self._running = True
        except ImportError as e:
            raise CameraError(f"OpenCV non disponible : {e}") from e

    def stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._running = False

    def grab_frame(self) -> RawFrame:
        import time
        if self._cap is None or not self._running:
            raise CameraError("UvcCamera : start() non appelé")
        ret, img = self._cap.read()
        if not ret or img is None:
            raise CameraError("UvcCamera : grab_frame() échec lecture")
        return RawFrame(
            frame_id  = f"UVC_{id(img):016x}",
            image     = img,
            timestamp = time.time(),
        )

    def is_connected(self) -> bool:
        return self._running and self._cap is not None
