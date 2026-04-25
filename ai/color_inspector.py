"""
ColorInspector ΔE2000 CIE LAB — §6.4
CIEDE2000 complète (kL=kC=kH=1).
K-means k=5 seed=42 pour couleur dominante.
GR-01 : random_state=42 garanti.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

_25_POW_7 = 25.0 ** 7   # 6 103 515 625 — constant CIEDE2000


class ColorInspector:
    """
    Utilitaires d'inspection couleur pour ColorObserver.

    dominant_color_lab(crop, k=5) → np.ndarray (3,) float32
      Couleur dominante en LAB échelle OpenCV uint8 [0-255, 0-255, 0-255].

    delta_e_2000(lab1, lab2) → float
      Différence colorimétrique CIEDE2000.
      Entrées : LAB échelle OpenCV uint8 (L∈[0,255], a∈[0,255], b∈[0,255]).
      Conversion interne → CIE LAB standard avant calcul.
      kL = kC = kH = 1 (poids standard).
    """

    def dominant_color_lab(self, crop: np.ndarray, k: int = 5) -> np.ndarray:
        """
        Calcule la couleur dominante d'un crop BGR via K-means LAB.

        Args:
            crop : image BGR uint8
            k    : nombre de clusters (défaut 5, §6.4)

        Returns:
            np.ndarray (3,) float32 — LAB échelle OpenCV [0-255, 0-255, 0-255].
            Tableau nul si crop trop petit ou K-means échoue.
        """
        from sklearn.cluster import KMeans

        if crop is None or crop.size == 0:
            return np.zeros(3, dtype=np.float32)

        lab    = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
        pixels = lab.reshape(-1, 3)

        n_clusters = min(k, len(pixels))
        if n_clusters < 1:
            return np.zeros(3, dtype=np.float32)

        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        kmeans.fit(pixels)

        dominant_idx = np.bincount(kmeans.labels_).argmax()
        return kmeans.cluster_centers_[dominant_idx].astype(np.float32)

    def delta_e_2000(
        self,
        lab1: np.ndarray,
        lab2: np.ndarray,
    ) -> float:
        """
        Différence colorimétrique CIEDE2000 entre deux couleurs LAB.

        Args:
            lab1, lab2 : np.ndarray (3,) ou list[float]
                         Valeurs en échelle OpenCV uint8
                         (L∈[0,255], a∈[0,255], b∈[0,255]).

        Returns:
            ΔE2000 ≥ 0.0.
            0.0 = couleurs identiques ; ~1.0 = différence imperceptible ;
            ≥ 8.0 = différence nette (seuil par défaut §6.4).
        """
        L1, a1, b1 = _ocv_to_cie(lab1)
        L2, a2, b2 = _ocv_to_cie(lab2)
        return _ciede2000(L1, a1, b1, L2, a2, b2)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers internes
# ─────────────────────────────────────────────────────────────────────────────

def _ocv_to_cie(lab_ocv) -> tuple[float, float, float]:
    """Convertit LAB échelle OpenCV uint8 vers CIE LAB standard."""
    arr = np.asarray(lab_ocv, dtype=np.float64).ravel()
    L   = float(arr[0]) * 100.0 / 255.0
    a   = float(arr[1]) - 128.0
    b   = float(arr[2]) - 128.0
    return L, a, b


def _ciede2000(
    L1: float, a1: float, b1: float,
    L2: float, a2: float, b2: float,
) -> float:
    """
    CIEDE2000 — formule complète, kL=kC=kH=1.

    Référence : Sharma, Wu & Dalal (2005),
    "The CIEDE2000 Color-Difference Formula."
    """
    # ── Étape 1 : C*ab et ajustement a' ──────────────────────────────────────
    C1 = math.sqrt(a1 * a1 + b1 * b1)
    C2 = math.sqrt(a2 * a2 + b2 * b2)
    C_avg = (C1 + C2) / 2.0
    C_avg7 = C_avg ** 7

    G   = 0.5 * (1.0 - math.sqrt(C_avg7 / (C_avg7 + _25_POW_7)))
    a1p = a1 * (1.0 + G)
    a2p = a2 * (1.0 + G)

    C1p = math.sqrt(a1p * a1p + b1 * b1)
    C2p = math.sqrt(a2p * a2p + b2 * b2)

    h1p = math.degrees(math.atan2(b1, a1p)) % 360.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360.0

    # ── Étape 2 : ΔL', ΔC', ΔH' ──────────────────────────────────────────────
    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0.0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180.0:
        dhp = h2p - h1p
    elif h2p - h1p > 180.0:
        dhp = h2p - h1p - 360.0
    else:
        dhp = h2p - h1p + 360.0

    dHp = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

    # ── Étape 3 : moyennes L', C', h' ────────────────────────────────────────
    Lp_avg = (L1 + L2) / 2.0
    Cp_avg = (C1p + C2p) / 2.0

    if C1p * C2p == 0.0:
        hp_avg = h1p + h2p
    elif abs(h1p - h2p) <= 180.0:
        hp_avg = (h1p + h2p) / 2.0
    elif h1p + h2p < 360.0:
        hp_avg = (h1p + h2p + 360.0) / 2.0
    else:
        hp_avg = (h1p + h2p - 360.0) / 2.0

    # ── Étape 4 : pondérations SL, SC, SH, RT ────────────────────────────────
    T = (1.0
         - 0.17 * math.cos(math.radians(hp_avg - 30.0))
         + 0.24 * math.cos(math.radians(2.0 * hp_avg))
         + 0.32 * math.cos(math.radians(3.0 * hp_avg + 6.0))
         - 0.20 * math.cos(math.radians(4.0 * hp_avg - 63.0)))

    SL = 1.0 + 0.015 * (Lp_avg - 50.0) ** 2 / math.sqrt(
        20.0 + (Lp_avg - 50.0) ** 2
    )
    SC = 1.0 + 0.045 * Cp_avg
    SH = 1.0 + 0.015 * Cp_avg * T

    Cp_avg7 = Cp_avg ** 7
    RC      = 2.0 * math.sqrt(Cp_avg7 / (Cp_avg7 + _25_POW_7))
    dtheta  = 30.0 * math.exp(-((hp_avg - 275.0) / 25.0) ** 2)
    RT      = -math.sin(math.radians(2.0 * dtheta)) * RC

    # ── Étape 5 : ΔE2000 ─────────────────────────────────────────────────────
    term_L = dLp / SL
    term_C = dCp / SC
    term_H = dHp / SH

    return math.sqrt(term_L ** 2 + term_C ** 2 + term_H ** 2
                     + RT * term_C * term_H)
