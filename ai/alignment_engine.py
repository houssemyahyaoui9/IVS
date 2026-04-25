"""
AlignmentEngine — SIFT 5000 kp + BFMatcher + RANSAC homography
Utilisé par S3 (alignement global) et SiftObserver (matching logos)
GR-01 : SIFT est déterministe — seed non requis
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from core.exceptions import AlignmentError
from pipeline.frames import AlignedFrame

logger = logging.getLogger(__name__)

_SIFT_NFEATURES    = 5000
_LOWE_RATIO        = 0.75
_MIN_GOOD_MATCHES  = 10
_RANSAC_THRESH     = 5.0


# ─────────────────────────────────────────────────────────────────────────────
#  SiftTemplate — sérialisé par CalibrationEngine
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SiftTemplate:
    """
    Template SIFT chargé depuis le disque (.pkl produit par CalibrationEngine §10).
    keypoints sont des cv2.KeyPoint désérialisés (pickle ne les supporte pas nativement).
    """
    keypoints   : list          # liste de cv2.KeyPoint
    descriptors : np.ndarray    # (N, 128) float32
    shape       : tuple         # (H, W) ou (H, W, C) de l'image template

    @classmethod
    def from_file(cls, path: Path) -> "SiftTemplate":
        """
        Charge un template depuis le .pkl écrit par CalibrationEngine.

        Raises:
            FileNotFoundError : si le fichier est absent
            ValueError        : si le format est invalide
        """
        if not path.exists():
            raise FileNotFoundError(f"SiftTemplate: fichier introuvable — {path}")
        with open(path, "rb") as fh:
            data = pickle.load(fh)

        kps   = _deserialize_keypoints(data["keypoints"])
        descs = np.asarray(data["descriptors"], dtype=np.float32)
        shape = data["shape"]

        if descs.ndim != 2 or descs.shape[1] != 128:
            raise ValueError(
                f"SiftTemplate: descripteurs invalides shape={descs.shape} dans {path}"
            )
        return cls(keypoints=kps, descriptors=descs, shape=shape)

    def __len__(self) -> int:
        return len(self.keypoints)


def _deserialize_keypoints(data: list) -> list:
    """Reconstruit des cv2.KeyPoint depuis les tuples sérialisés."""
    return [
        cv2.KeyPoint(
            x=d[0][0], y=d[0][1],
            size=d[1], angle=d[2],
            response=d[3], octave=d[4], class_id=d[5],
        )
        for d in data
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  AlignmentEngine
# ─────────────────────────────────────────────────────────────────────────────

class AlignmentEngine:
    """
    Alignement SIFT global — §6.3 · utilisé par S3.

    align(frame, template, ...) → AlignedFrame
      1. detectAndCompute sur la frame
      2. knnMatch BFMatcher L2 vs template
      3. Lowe ratio test (< 0.75)
      4. RANSAC homography si ≥ 10 good matches
      5. warpPerspective → AlignedFrame

    GR-01 : SIFT est déterministe — aucune seed requise.
    """

    def __init__(self) -> None:
        self._sift    = cv2.SIFT_create(nfeatures=_SIFT_NFEATURES)
        self._matcher = cv2.BFMatcher(cv2.NORM_L2)

    # ── Alignement global ─────────────────────────────────────────────────────

    def align(
        self,
        frame:     np.ndarray,
        template:  SiftTemplate,
        frame_id:  str   = "",
        timestamp: float = 0.0,
    ) -> AlignedFrame:
        """
        Aligne frame sur template via homographie SIFT+RANSAC.

        Args:
            frame     : image BGR uint8 (sortie S2)
            template  : SiftTemplate chargé depuis calibration
            frame_id  : identifiant de frame (pour AlignedFrame)
            timestamp : timestamp source (pour AlignedFrame)

        Returns:
            AlignedFrame — jamais None (GR-11).
            Si alignement échoue → AlignedFrame avec homography=None, score=0.
        """
        gray = _to_gray(frame)
        kp_frame, des_frame = self._sift.detectAndCompute(gray, None)

        if des_frame is None or len(kp_frame) < _MIN_GOOD_MATCHES:
            logger.warning("AlignmentEngine: kp insuffisants (%d) pour frame '%s'",
                           len(kp_frame or []), frame_id)
            return _passthrough_frame(frame, frame_id, timestamp)

        good = self._lowe_filter(template.descriptors, des_frame)

        if len(good) < _MIN_GOOD_MATCHES:
            logger.warning("AlignmentEngine: good matches insuffisants (%d/%d) frame '%s'",
                           len(good), _MIN_GOOD_MATCHES, frame_id)
            return AlignedFrame(
                frame_id=frame_id,
                image=frame,
                homography=None,
                alignment_score=float(len(good)) / _MIN_GOOD_MATCHES,
                timestamp=timestamp,
            )

        # Points source = template, destination = frame
        src_pts = np.float32([template.keypoints[m.queryIdx].pt
                              for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_frame[m.trainIdx].pt
                              for m in good]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, _RANSAC_THRESH)

        if H is None:
            logger.warning("AlignmentEngine: RANSAC homography nulle pour frame '%s'", frame_id)
            return _passthrough_frame(frame, frame_id, timestamp)

        h, w = template.shape[:2]
        aligned_img = cv2.warpPerspective(frame, H, (w, h))
        inliers     = int(mask.sum()) if mask is not None else 0
        score       = min(1.0, inliers / max(len(good), 1))

        logger.debug("AlignmentEngine: frame '%s' score=%.3f inliers=%d/%d",
                     frame_id, score, inliers, len(good))
        return AlignedFrame(
            frame_id=frame_id,
            image=aligned_img,
            homography=H,
            alignment_score=round(score, 4),
            timestamp=timestamp,
        )

    # ── Matching seul (utilisé par SiftObserver per-logo) ────────────────────

    def match(
        self,
        query_gray: np.ndarray,
        template:   SiftTemplate,
    ) -> tuple[list, list]:
        """
        Détecte et matche les keypoints de query_gray vs template.

        Returns:
            (kp_query, good_matches) — good_matches filtrés par ratio test Lowe.
            kp_query est vide si détection impossible.
        """
        kp_q, des_q = self._sift.detectAndCompute(query_gray, None)
        if des_q is None or len(kp_q) < 2:
            return [], []

        good = self._lowe_filter(template.descriptors, des_q)
        return kp_q, good

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _lowe_filter(
        self,
        des_template: np.ndarray,
        des_query:    np.ndarray,
    ) -> list:
        """knnMatch (k=2) + Lowe ratio test < 0.75."""
        if len(des_template) < 2 or len(des_query) < 2:
            return []
        try:
            pairs = self._matcher.knnMatch(des_template, des_query, k=2)
        except cv2.error:
            return []
        return [m for m, n in pairs if m.distance < _LOWE_RATIO * n.distance]


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _passthrough_frame(
    frame: np.ndarray,
    frame_id: str,
    timestamp: float,
) -> AlignedFrame:
    """AlignedFrame identité — utilisé quand l'alignement échoue."""
    return AlignedFrame(
        frame_id=frame_id,
        image=frame,
        homography=None,
        alignment_score=0.0,
        timestamp=timestamp,
    )
