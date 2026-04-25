"""
TextureAnalyzer GLCM+LBP+FFT — §6.5
Implémentation numpy+scipy pure (scikit-image absent).
Miroir exact des helpers de CalibrationEngine §10 Étape 7 pour cohérence avec
texture_reference.npz.
GR-01 : aucune composante stochastique.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

logger = logging.getLogger(__name__)

# ── Constantes GLCM/LBP/FFT — doivent correspondre à CalibrationEngine ────────
_GLCM_LEVELS     = 64
_GLCM_DISTANCES  = [1, 2, 4]
_GLCM_ANGLES_DEG = [0, 45, 90, 135]
_N_GLCM_PROPS    = 4      # contrast, homogeneity, energy, correlation
_GLCM_DIM        = len(_GLCM_DISTANCES) * len(_GLCM_ANGLES_DEG) * _N_GLCM_PROPS  # 48

_LBP_P_DEFAULT   = 8     # P=8 (spec P=24 nécessite scikit-image absent)
_LBP_R_DEFAULT   = 1     # R=1 (cohérent avec CalibrationEngine)
_FFT_BINS_DEFAULT = 32


# ─────────────────────────────────────────────────────────────────────────────
#  TextureReference — chargé depuis texture_reference.npz
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TextureReference:
    """
    Référence texture chargée depuis calibration/texture_reference.npz.

    Les vecteurs sont découpés depuis ref_mean (336-dim) selon les paramètres
    stockés dans le npz (glcm_distances, lbp_p, fft_bins).

    glcm_props   : (N_d × N_a × 4,) = (48,) — vecteur GLCM de référence
    lbp_hist     : (2^P,) = (256,)  — histogramme LBP de référence
    fft_spectrum : (B,)   = (32,)   — spectre FFT radialement moyenné de référence
    """
    glcm_props:   np.ndarray
    lbp_hist:     np.ndarray
    fft_spectrum: np.ndarray

    @classmethod
    def from_npz(cls, path: Path) -> "TextureReference":
        """
        Charge et décode texture_reference.npz produit par CalibrationEngine §10 Étape 7.

        Raises:
            FileNotFoundError : si path absent
            ValueError        : si format npz invalide
        """
        if not Path(path).exists():
            raise FileNotFoundError(f"TextureReference: fichier absent — {path}")

        data = np.load(path)
        ref_mean = data["ref_mean"].astype(np.float64)  # (336,)

        # Dériver les dimensions depuis les paramètres stockés
        n_dist   = len(data["glcm_distances"])
        n_angles = len(data["glcm_angles"])
        lbp_p    = int(data["lbp_p"][0])
        fft_bins = int(data["fft_bins"][0])

        glcm_dim = n_dist * n_angles * _N_GLCM_PROPS   # 48
        lbp_dim  = 2 ** lbp_p                          # 256 pour P=8
        fft_dim  = fft_bins                            # 32

        expected = glcm_dim + lbp_dim + fft_dim
        if len(ref_mean) != expected:
            raise ValueError(
                f"TextureReference: ref_mean dim={len(ref_mean)} ≠ "
                f"glcm({glcm_dim})+lbp({lbp_dim})+fft({fft_dim})={expected}"
            )

        glcm_end = glcm_dim
        lbp_end  = glcm_end + lbp_dim

        return cls(
            glcm_props=ref_mean[:glcm_end],
            lbp_hist=ref_mean[glcm_end:lbp_end],
            fft_spectrum=ref_mean[lbp_end:],
        )


# ─────────────────────────────────────────────────────────────────────────────
#  TextureAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class TextureAnalyzer:
    """
    Analyse de texture par comparaison GLCM + LBP + FFT vs référence calibrée.

    analyze(frame, reference) → float [0, 1]
      0 = très anormal (surface défectueuse)
      1 = identique à la référence (surface parfaite)

    Pondération : GLCM×0.40 + LBP×0.35 + FFT×0.25 (§6.5).
    Implémentation numpy+scipy (scikit-image non requis).
    """

    def analyze(self, frame: np.ndarray, reference: TextureReference) -> float:
        """
        Args:
            frame     : image BGR uint8
            reference : TextureReference chargé depuis texture_reference.npz

        Returns:
            float ∈ [0, 1] — score de similarité (1 = parfait, 0 = anormal).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        glcm_score = self._glcm_score(gray, reference.glcm_props)
        lbp_score  = self._lbp_score(gray, reference.lbp_hist)
        fft_score  = self._fft_score(gray, reference.fft_spectrum)

        score = 0.40 * glcm_score + 0.35 * lbp_score + 0.25 * fft_score
        return float(np.clip(score, 0.0, 1.0))

    # ── GLCM ─────────────────────────────────────────────────────────────────

    def _glcm_score(self, gray: np.ndarray, ref_props: np.ndarray) -> float:
        """Cosine similarity entre vecteur GLCM courant et référence (48-dim)."""
        props = _compute_glcm_vector(gray)    # (48,)
        return float(_cosine_similarity(props, ref_props))

    # ── LBP ──────────────────────────────────────────────────────────────────

    def _lbp_score(self, gray: np.ndarray, ref_hist: np.ndarray) -> float:
        """1 - chi2_distance entre histogramme LBP courant et référence."""
        P = len(ref_hist).bit_length() - 1   # 256 bins → P=8
        P = max(P, _LBP_P_DEFAULT)
        hist = _compute_lbp_histogram(gray, P=P, R=_LBP_R_DEFAULT)
        chi2 = _chi2_distance(hist, ref_hist)
        return float(np.clip(1.0 - chi2, 0.0, 1.0))

    # ── FFT ───────────────────────────────────────────────────────────────────

    def _fft_score(self, gray: np.ndarray, ref_spectrum: np.ndarray) -> float:
        """Corrélation de Pearson entre spectre FFT radial courant et référence."""
        n_bins  = len(ref_spectrum)
        current = _compute_fft_spectrum(gray, n_bins=n_bins)
        score   = _safe_corrcoef(current, ref_spectrum)
        return float(np.clip(score, 0.0, 1.0))


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers internes — miroir de CalibrationEngine pour cohérence
# ─────────────────────────────────────────────────────────────────────────────

def _compute_glcm(gray: np.ndarray, distance: int, angle_deg: float) -> np.ndarray:
    """GLCM normalisé, niveaux quantisés à _GLCM_LEVELS, symétrique."""
    g = (gray.astype(np.float32) / 255.0 * (_GLCM_LEVELS - 1)
         ).astype(np.int32).clip(0, _GLCM_LEVELS - 1)
    H, W = g.shape

    angle_rad = np.radians(angle_deg)
    dy = -int(round(distance * np.sin(angle_rad)))
    dx =  int(round(distance * np.cos(angle_rad)))

    r0 = max(0, -dy);  r1 = H - max(0, dy)
    c0 = max(0, -dx);  c1 = W - max(0, dx)

    if r1 <= r0 or c1 <= c0:
        return np.zeros((_GLCM_LEVELS, _GLCM_LEVELS), dtype=np.float64)

    i_vals = g[r0:r1, c0:c1].ravel()
    j_vals = g[r0 + dy:r1 + dy, c0 + dx:c1 + dx].ravel()

    glcm = np.zeros((_GLCM_LEVELS, _GLCM_LEVELS), dtype=np.float64)
    np.add.at(glcm, (i_vals, j_vals), 1.0)
    glcm += glcm.T          # symétrie
    total = glcm.sum()
    if total > 0:
        glcm /= total
    return glcm


def _glcm_props(glcm: np.ndarray) -> np.ndarray:
    """[contrast, homogeneity, energy, correlation] depuis GLCM normalisé."""
    levels = glcm.shape[0]
    I, J   = np.meshgrid(np.arange(levels, dtype=np.float64),
                         np.arange(levels, dtype=np.float64), indexing="ij")
    diff2       = (I - J) ** 2
    contrast    = float(np.sum(glcm * diff2))
    homogeneity = float(np.sum(glcm / (1.0 + diff2)))
    energy      = float(np.sqrt(np.sum(glcm ** 2)))
    mu_i        = float(np.sum(I * glcm))
    mu_j        = float(np.sum(J * glcm))
    var_i       = float(np.sum(glcm * (I - mu_i) ** 2))
    var_j       = float(np.sum(glcm * (J - mu_j) ** 2))
    sigma       = np.sqrt(var_i * var_j)
    corr        = (float(np.sum(glcm * (I - mu_i) * (J - mu_j)) / sigma)
                   if sigma > 1e-10 else 0.0)
    return np.array([contrast, homogeneity, energy, corr], dtype=np.float64)


def _compute_glcm_vector(gray: np.ndarray) -> np.ndarray:
    """Vecteur GLCM complet (48-dim) pour tous distances × angles."""
    parts: list[np.ndarray] = []
    for d in _GLCM_DISTANCES:
        for a in _GLCM_ANGLES_DEG:
            parts.append(_glcm_props(_compute_glcm(gray, d, a)))
    return np.concatenate(parts)   # (48,)


def _compute_lbp_histogram(gray: np.ndarray, P: int, R: float) -> np.ndarray:
    """LBP histogram P×R via scipy.ndimage — même algo que CalibrationEngine."""
    H, W    = gray.shape
    gray_f  = gray.astype(np.float64)
    lbp     = np.zeros((H, W), dtype=np.uint32)
    gy, gx  = np.mgrid[0:H, 0:W]

    for k in range(P):
        angle    = 2.0 * np.pi * k / P
        dy       = -R * np.sin(angle)
        dx       =  R * np.cos(angle)
        neighbor = ndi.map_coordinates(gray_f, [gy + dy, gx + dx],
                                       order=1, mode="nearest")
        lbp     += (neighbor >= gray_f).astype(np.uint32) << k

    n_bins = 2 ** P
    hist, _ = np.histogram(lbp, bins=n_bins, range=(0, n_bins))
    total   = hist.sum()
    return hist.astype(np.float64) / (total + 1e-10)


def _compute_fft_spectrum(gray: np.ndarray, n_bins: int = _FFT_BINS_DEFAULT) -> np.ndarray:
    """Spectre FFT radialement moyenné en n_bins bins — même algo que CalibrationEngine."""
    gray_f = gray.astype(np.float32) / 255.0
    F      = np.fft.fft2(gray_f)
    mag    = np.abs(np.fft.fftshift(F))

    H, W   = mag.shape
    cy, cx = H // 2, W // 2
    Y, X   = np.ogrid[:H, :W]
    r      = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(int)
    r_max  = min(cy, cx)

    bins     = np.linspace(0, r_max, n_bins + 1, dtype=int)
    features = np.zeros(n_bins, dtype=np.float64)
    for i in range(n_bins):
        mask = (r >= bins[i]) & (r < bins[i + 1])
        if mask.any():
            features[i] = float(mag[mask].mean())

    total = features.sum()
    return features / (total + 1e-10)


# ─────────────────────────────────────────────────────────────────────────────
#  Métriques de similarité
# ─────────────────────────────────────────────────────────────────────────────

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity ∈ [0, 1]. Retourne 0 si l'un des vecteurs est nul."""
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    cos = float(np.dot(a, b) / (norm_a * norm_b))
    return float(np.clip((cos + 1.0) / 2.0, 0.0, 1.0))   # [-1,1] → [0,1]


def _chi2_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Chi2 distance : 0.5 × Σ (a-b)² / (a+b+ε). Retourne 0 si vecteurs nuls."""
    denom = a + b + 1e-10
    return float(0.5 * np.sum((a - b) ** 2 / denom))


def _safe_corrcoef(a: np.ndarray, b: np.ndarray) -> float:
    """Corrélation de Pearson — retourne 0 si variance nulle (vecteur constant)."""
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return 0.0
    r = np.corrcoef(a, b)
    val = float(r[0, 1])
    return 0.0 if np.isnan(val) else val
