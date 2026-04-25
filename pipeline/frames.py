"""
Types de frames internes au pipeline v7.0
S1 → RawFrame (camera_manager)
S2 → ProcessedFrame
S3 → AlignedFrame
ErrorResult → retourné par ExecutionGuard si stage échoue (GR-11)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.models import LuminosityResult


@dataclass
class ProcessedFrame:
    """
    Sortie de S2 PreProcess.
    Image après CLAHE + résultat du contrôle de luminosité.
    Non-frozen : np.ndarray non hashable.
    """
    frame_id         : str
    image            : np.ndarray   # CLAHE appliqué
    luminosity       : LuminosityResult
    timestamp        : float = field(default_factory=time.time)


@dataclass
class AlignedFrame:
    """
    Sortie de S3 Alignment.
    Image recadrée et alignée sur le template de référence.
    Non-frozen : np.ndarray non hashable.
    """
    frame_id         : str
    image            : np.ndarray   # alignée sur template
    homography       : Optional[np.ndarray]  # matrice 3×3, None si identité
    alignment_score  : float        # qualité de l'alignement [0,1]
    timestamp        : float = field(default_factory=time.time)


@dataclass(frozen=True)
class ErrorResult:
    """
    Retourné par ExecutionGuard quand un stage lève une exception (GR-11).
    Jamais None — garantit que la chaîne ne casse pas silencieusement.
    """
    stage     : str
    error_msg : str
    timestamp : float = field(default_factory=time.time)
