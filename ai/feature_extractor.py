"""
FeatureExtractor — HOG 128-dim + Color HSV 128-dim = 256-dim float32
GR-01 : déterministe — pas de stochastique ici
scikit-image absent → HOG implémenté en numpy pur avec Sobel cv2
"""
from __future__ import annotations

import cv2
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
#  Constantes publiques (importées par DatasetManager et BackgroundTrainer)
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_DIM    = 256   # dimension totale du vecteur
HOG_DIM        = 128   # HOG seul
COLOR_DIM      = 128   # histogramme HSV seul

_HOG_TARGET_H  = 64   # hauteur image redimensionnée pour HOG
_HOG_TARGET_W  = 64   # largeur
_HOG_ORI       = 8    # orientations
_HOG_PPC       = 16   # pixels_per_cell
_HOG_CELLS_Y   = _HOG_TARGET_H // _HOG_PPC  # 4
_HOG_CELLS_X   = _HOG_TARGET_W // _HOG_PPC  # 4

_HIST_H_BINS   = 64   # teinte H  [0, 180)
_HIST_S_BINS   = 32   # saturation S [0, 256)
_HIST_V_BINS   = 32   # valeur V  [0, 256)

assert HOG_DIM   == _HOG_CELLS_Y * _HOG_CELLS_X * _HOG_ORI, "HOG dim incohérente"
assert COLOR_DIM == _HIST_H_BINS + _HIST_S_BINS + _HIST_V_BINS, "Color dim incohérente"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers privés
# ─────────────────────────────────────────────────────────────────────────────

def _hog_numpy(gray: np.ndarray) -> np.ndarray:
    """
    HOG 128-dim — numpy pur (scikit-image non requis).

    Paramètres : orientations=8, pixels_per_cell=(16,16), cells_per_block=(1,1)
    Image redimensionnée en 64×64 avant traitement.

    Soft binning : magnitude du gradient interpolée entre deux bins adjacents.
    """
    img = cv2.resize(gray, (_HOG_TARGET_W, _HOG_TARGET_H),
                     interpolation=cv2.INTER_AREA).astype(np.float32)

    # Gradients Sobel (ksize=1 = [-1,0,1] sans lissage)
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=1)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=1)

    mag   = np.sqrt(gx ** 2 + gy ** 2)
    # Angle non signé [0°, 180°)
    angle = np.abs(np.degrees(np.arctan2(gy, gx))) % 180.0

    bin_width = 180.0 / _HOG_ORI

    # Indices bins + poids pour soft binning
    bin_f   = angle / bin_width               # indice flottant [0, 8)
    bin0    = np.floor(bin_f).astype(np.int32) % _HOG_ORI
    bin1    = (bin0 + 1) % _HOG_ORI
    w1      = (bin_f - np.floor(bin_f)).astype(np.float32)
    w0      = 1.0 - w1

    histograms = np.zeros((_HOG_CELLS_Y, _HOG_CELLS_X, _HOG_ORI), dtype=np.float32)

    for cy in range(_HOG_CELLS_Y):
        for cx in range(_HOG_CELLS_X):
            y0 = cy * _HOG_PPC;  y1 = y0 + _HOG_PPC
            x0 = cx * _HOG_PPC;  x1 = x0 + _HOG_PPC

            m  = mag[y0:y1, x0:x1].ravel()
            b0 = bin0[y0:y1, x0:x1].ravel()
            b1 = bin1[y0:y1, x0:x1].ravel()

            np.add.at(histograms[cy, cx], b0, m * w0[y0:y1, x0:x1].ravel())
            np.add.at(histograms[cy, cx], b1, m * w1[y0:y1, x0:x1].ravel())

    return histograms.ravel()   # (128,) float32


def _color_histogram_hsv(frame: np.ndarray) -> np.ndarray:
    """
    Histogramme couleur HSV 128-dim.
      H : 64 bins [0, 180)
      S : 32 bins [0, 256)
      V : 32 bins [0, 256)
    """
    hsv    = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist_h = np.histogram(hsv[:, :, 0], bins=_HIST_H_BINS, range=(0, 180))[0]
    hist_s = np.histogram(hsv[:, :, 1], bins=_HIST_S_BINS, range=(0, 256))[0]
    hist_v = np.histogram(hsv[:, :, 2], bins=_HIST_V_BINS, range=(0, 256))[0]
    return np.concatenate([hist_h, hist_s, hist_v]).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  FeatureExtractor
# ─────────────────────────────────────────────────────────────────────────────

class FeatureExtractor:
    """
    Extrait un vecteur 256-dim float32 depuis une frame BGR.

    Architecture :
      HOG 128-dim   : gradient orienté sur image 64×64 niveaux de gris
      Color 128-dim : histogramme HSV (64 bins H + 32 S + 32 V)

    Normalisation :
      hog_norm   = hog_feat   / (‖hog_feat‖₂  + 1e-6)
      color_norm = color_feat / (color_feat.sum() + 1e-6)

    Déterministe (GR-01) : aucune composante stochastique.
    """

    def extract(self, frame: np.ndarray) -> np.ndarray:
        """
        Args:
            frame : image BGR uint8, toute résolution.

        Returns:
            np.ndarray (256,) float32 normalisé.
        """
        gray       = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hog_feat   = _hog_numpy(gray)
        color_feat = _color_histogram_hsv(frame)

        hog_norm   = hog_feat   / (np.linalg.norm(hog_feat)   + 1e-6)
        color_norm = color_feat / (color_feat.sum()            + 1e-6)

        features = np.concatenate([hog_norm, color_norm], dtype=np.float32)
        return features

    @staticmethod
    def feature_dim() -> int:
        """Dimension du vecteur retourné — toujours 256."""
        return FEATURE_DIM
