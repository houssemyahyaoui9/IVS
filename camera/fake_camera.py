"""
fake_camera — TS2I IVS v7.0
FakeCamera DEV uniquement — frames synthétiques DÉTERMINISTES seed=42
INTERDIT en deployment_mode=PRODUCTION (GR-01)
"""
from __future__ import annotations

import time

import numpy as np

from camera.camera_manager import CameraBackend, RawFrame
from core.config_manager import ConfigManager
from core.exceptions import ConfigValidationError


# Dimensions fixes §21
_W, _H = 1920, 1080

# Palette BGR
_GRAY_BG      = 200
_GRAY_PRODUCT = 175
_BLUE_BGR     = (220,  60,  60)   # zone logo gauche
_RED_BGR      = ( 60,  60, 220)   # zone logo droite
_NOISE_STD    = 4                 # écart-type bruit gaussien
_SEED_BASE    = 42                # GR-01 déterminisme


class FakeCamera(CameraBackend):
    """
    Caméra synthétique reproductible.
    Chaque frame N est générée avec seed=42+N → même entrée = même image.
    INTERDIT en PRODUCTION (vérifié à l'instanciation).
    """

    def __init__(self, config: ConfigManager) -> None:
        if config.deployment_mode == "PRODUCTION":
            raise ConfigValidationError(
                "FakeCamera FORBIDDEN in PRODUCTION mode"
            )
        self._frame_count = 0
        self._running     = False

    # ── CameraBackend interface ───────────────────────────────────────────────

    def start(self) -> None:
        self._frame_count = 0
        self._running     = True

    def stop(self) -> None:
        self._running = False

    def is_connected(self) -> bool:
        return self._running

    def grab_frame(self) -> RawFrame:
        n        = self._frame_count
        frame_id = f"FAKE_{n:06d}"
        image    = _build_frame(n)
        self._frame_count += 1
        return RawFrame(frame_id=frame_id, image=image, timestamp=time.time())

    @property
    def frame_count(self) -> int:
        return self._frame_count


# ─────────────────────────────────────────────────────────────────────────────
#  Génération d'image déterministe
# ─────────────────────────────────────────────────────────────────────────────

def _build_frame(n: int) -> np.ndarray:
    """
    Construit la frame N.
    Déterministe : même N → même pixel array, garanti par seed=_SEED_BASE+N.

    Structure visuelle :
      - Fond gris uniforme  (200)
      - Rectangle produit (tapis) gris 175 : marges 140/160 px
      - Zone logo gauche  (bleu  BGR 220,60,60)
      - Zone logo droite  (rouge BGR 60,60,220)
      - Bruit gaussien std=4
    """
    rng = np.random.default_rng(_SEED_BASE + n)

    img = np.full((_H, _W, 3), _GRAY_BG, dtype=np.uint8)

    # rectangle produit (tapis)
    img[140:940, 160:1760] = _GRAY_PRODUCT

    # zone logo gauche (bleu BGR)
    img[200:350, 250:500, 0] = _BLUE_BGR[0]
    img[200:350, 250:500, 1] = _BLUE_BGR[1]
    img[200:350, 250:500, 2] = _BLUE_BGR[2]

    # zone logo droite (rouge BGR)
    img[200:350, 1420:1670, 0] = _RED_BGR[0]
    img[200:350, 1420:1670, 1] = _RED_BGR[1]
    img[200:350, 1420:1670, 2] = _RED_BGR[2]

    # bruit gaussien
    noise = rng.standard_normal((_H, _W, 3)) * _NOISE_STD
    img   = np.clip(
        img.astype(np.int16) + noise.astype(np.int16), 0, 255
    ).astype(np.uint8)

    return img
