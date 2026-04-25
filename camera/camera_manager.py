"""
camera_manager — TS2I IVS v7.0
CameraBackend ABC · RawFrame · CameraManager pluggable
§21 : camera.type = fake | uvc | gige | rtsp
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from core.config_manager import ConfigManager
from core.exceptions import ConfigValidationError


# ─────────────────────────────────────────────────────────────────────────────
#  RawFrame — sortie de grab_frame()
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RawFrame:
    """
    Frame brute issue de la caméra.
    Non-frozen : np.ndarray n'est pas hashable.
    Immutabilité garantie par convention pipeline (jamais modifié après création).
    """
    frame_id  : str
    image     : np.ndarray   # 1920×1080×3 uint8
    timestamp : float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  CameraBackend — ABC
# ─────────────────────────────────────────────────────────────────────────────

class CameraBackend(ABC):
    """
    Contrat minimal pour tout backend caméra.
    Toute implémentation doit être substituable (Liskov).
    """

    @abstractmethod
    def start(self) -> None:
        """Initialise le backend (ouverture port, allocation buffer...)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Libère les ressources proprement."""
        ...

    @abstractmethod
    def grab_frame(self) -> RawFrame:
        """
        Acquiert une frame.
        GR-11 : jamais retourner None — lever CameraError si échec.
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """True si le backend est prêt à capturer."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
#  Stubs backends production (implémentation future)
# ─────────────────────────────────────────────────────────────────────────────

class _StubBackend(CameraBackend):
    """Base commune pour les stubs non implémentés."""

    _name: str = "stub"

    def start(self) -> None:
        raise NotImplementedError(f"{self._name} : backend non implémenté")

    def stop(self) -> None:
        pass

    def grab_frame(self) -> RawFrame:
        raise NotImplementedError(f"{self._name} : backend non implémenté")

    def is_connected(self) -> bool:
        return False


class GigECamera(_StubBackend):
    """GigE Vision backend — implémentation Phase P-GigE."""
    _name = "GigECamera"


class RtspCamera(_StubBackend):
    """RTSP stream backend — implémentation Phase P-RTSP."""
    _name = "RtspCamera"


# ─────────────────────────────────────────────────────────────────────────────
#  CameraManager — façade pluggable
# ─────────────────────────────────────────────────────────────────────────────

_BACKEND_REGISTRY: dict[str, type[CameraBackend]] = {}


def register_backend(cam_type: str, cls: type[CameraBackend]) -> None:
    """Enregistre un backend externe (pour tests ou plugins)."""
    _BACKEND_REGISTRY[cam_type] = cls


class CameraManager:
    """
    Façade unique caméra.
    Sélectionne le backend via config.camera.type.
    Le backend est injectable directement (tests, mock).
    """

    def __init__(
        self,
        config: ConfigManager | None = None,
        backend: CameraBackend | None = None,
    ) -> None:
        if backend is not None:
            self._backend = backend
        elif config is not None:
            self._backend = self._create_backend(config)
        else:
            raise ValueError("CameraManager requiert config ou backend")

    # ── factory ───────────────────────────────────────────────────────────────

    @staticmethod
    def _create_backend(config: ConfigManager) -> CameraBackend:
        cam_type = config.get("camera.type", "fake")

        # Import lazy pour éviter les dépendances circulaires
        from camera.fake_camera import FakeCamera
        from camera.uvc_camera  import UvcCamera

        builtin: dict[str, type[CameraBackend]] = {
            "fake": FakeCamera,
            "uvc":  UvcCamera,
            "gige": GigECamera,
            "rtsp": RtspCamera,
        }
        # Les backends enregistrés ont la priorité sur les builtins
        registry = {**builtin, **_BACKEND_REGISTRY}

        cls = registry.get(cam_type)
        if cls is None:
            raise ConfigValidationError(
                f"camera.type='{cam_type}' inconnu. "
                f"Valeurs valides : {list(registry.keys())}"
            )
        return cls(config)

    # ── délégation ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._backend.start()

    def stop(self) -> None:
        self._backend.stop()

    def grab_frame(self) -> RawFrame:
        return self._backend.grab_frame()

    def is_connected(self) -> bool:
        return self._backend.is_connected()

    @property
    def backend(self) -> CameraBackend:
        return self._backend

    def swap_backend(self, new_backend: CameraBackend) -> None:
        """Remplace le backend à chaud — usage tests/fail-over."""
        self._backend = new_backend
