"""
CalibrationEngine — 7 étapes — §10
GR-01 : seed=42 dans KMeans + IsolationForest
GR-06 : résultats figés après calibration — jamais recalculés en boucle
"""
from __future__ import annotations

import json
import logging
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from core.exceptions import CalibrationError
from core.models import LogoDefinition, ProductDefinition

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────────────────────

_SIFT_NFEATURES        = 5000
_SIFT_MIN_KP           = 1000          # étape 4 : seuil minimal keypoints
_KMEANS_K              = 5
_KMEANS_SEED           = 42            # GR-01
_ISO_N_ESTIMATORS      = 1000
_ISO_SEED              = 42            # GR-01
_WARNING_PERCENT       = 15.0
_CRITICAL_PERCENT      = 30.0
_GLCM_LEVELS           = 64
_GLCM_DISTANCES        = [1, 2, 4]    # §6.5 TextureAnalyzer distances
_GLCM_ANGLES_DEG       = [0, 45, 90, 135]
_LBP_P                 = 8            # P=8 (scikit-image P=24 nécessite skimage)
_LBP_R                 = 1.0          # R=1 (spec R=3 — scalé pour cohérence)
_FFT_BINS              = 32


# ─────────────────────────────────────────────────────────────────────────────
#  CalibrationResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CalibrationResult:
    """Résultat de calibration 7 étapes — §10."""
    product_id            : str
    calibration_dir       : Path
    pixel_per_mm_x        : float
    pixel_per_mm_y        : float
    brightness_ref_mean   : float
    brightness_ref_std    : float
    brightness_ref_min_ok : float
    brightness_ref_max_ok : float
    noise_floor           : float
    sift_template_path    : Path
    logo_template_paths   : dict[str, Path]   # logo_id → .pkl
    color_reference_path  : Path
    texture_reference_path: Path
    iso_forest_path       : Path
    num_reference_images  : int
    timestamp             : float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers SIFT serialization (cv2.KeyPoint non-picklable directement)
# ─────────────────────────────────────────────────────────────────────────────

def _serialize_keypoints(kps: list) -> list:
    return [(kp.pt, kp.size, kp.angle, kp.response, kp.octave, kp.class_id)
            for kp in kps]


def _deserialize_keypoints(data: list) -> list:
    return [cv2.KeyPoint(x=d[0][0], y=d[0][1], size=d[1], angle=d[2],
                         response=d[3], octave=d[4], class_id=d[5])
            for d in data]


def _save_sift_template(path: Path, kps: list, descs: np.ndarray,
                        shape: tuple) -> None:
    with open(path, "wb") as fh:
        pickle.dump({
            "keypoints":   _serialize_keypoints(kps),
            "descriptors": descs,
            "shape":       shape,
        }, fh, protocol=pickle.HIGHEST_PROTOCOL)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers texture features (GLCM + LBP + FFT — numpy pur)
# Note : spec cible scikit-image P=24/R=3 ; fallback numpy P=8/R=1
# ─────────────────────────────────────────────────────────────────────────────

def _compute_glcm(gray: np.ndarray, distance: int, angle_deg: float) -> np.ndarray:
    """GLCM normalisé — niveaux quantisés à _GLCM_LEVELS."""
    levels = _GLCM_LEVELS
    g = (gray.astype(np.float32) / 255.0 * (levels - 1)).astype(np.int32).clip(0, levels - 1)
    H, W = g.shape

    angle_rad = np.radians(angle_deg)
    dy = -int(round(distance * np.sin(angle_rad)))
    dx =  int(round(distance * np.cos(angle_rad)))

    r0 = max(0, -dy);  r1 = H - max(0, dy)
    c0 = max(0, -dx);  c1 = W - max(0, dx)

    if r1 <= r0 or c1 <= c0:
        return np.zeros((levels, levels), dtype=np.float64)

    i_vals = g[r0:r1, c0:c1].ravel()
    j_vals = g[r0 + dy:r1 + dy, c0 + dx:c1 + dx].ravel()

    glcm = np.zeros((levels, levels), dtype=np.float64)
    np.add.at(glcm, (i_vals, j_vals), 1.0)
    glcm += glcm.T       # symétrie
    total = glcm.sum()
    if total > 0:
        glcm /= total
    return glcm


def _glcm_props(glcm: np.ndarray) -> np.ndarray:
    """[contrast, homogeneity, energy, correlation] depuis GLCM."""
    levels = glcm.shape[0]
    I, J = np.meshgrid(np.arange(levels, dtype=np.float64),
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
    correlation = float(np.sum(glcm * (I - mu_i) * (J - mu_j)) / sigma) if sigma > 1e-10 else 0.0
    return np.array([contrast, homogeneity, energy, correlation], dtype=np.float64)


def _compute_lbp_histogram(gray: np.ndarray) -> np.ndarray:
    """LBP histogram P=_LBP_P, R=_LBP_R avec scipy.ndimage."""
    from scipy import ndimage as ndi

    P, R = _LBP_P, _LBP_R
    H, W = gray.shape
    gray_f = gray.astype(np.float64)
    lbp = np.zeros((H, W), dtype=np.uint32)

    gy, gx = np.mgrid[0:H, 0:W]

    for k in range(P):
        angle = 2.0 * np.pi * k / P
        dy = -R * np.sin(angle)
        dx =  R * np.cos(angle)
        neighbor = ndi.map_coordinates(gray_f,
                                       [gy + dy, gx + dx],
                                       order=1, mode="nearest")
        lbp += (neighbor >= gray_f).astype(np.uint32) << k

    hist, _ = np.histogram(lbp, bins=2 ** P, range=(0, 2 ** P))
    total = hist.sum()
    return hist.astype(np.float64) / (total + 1e-10)


def _compute_fft_features(gray: np.ndarray) -> np.ndarray:
    """Spectre FFT radialement moyenné (_FFT_BINS bins)."""
    gray_f = gray.astype(np.float32) / 255.0
    F      = np.fft.fft2(gray_f)
    mag    = np.abs(np.fft.fftshift(F))

    H, W   = mag.shape
    cy, cx = H // 2, W // 2
    Y, X   = np.ogrid[:H, :W]
    r      = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(int)
    r_max  = min(cy, cx)

    bins     = np.linspace(0, r_max, _FFT_BINS + 1, dtype=int)
    features = np.zeros(_FFT_BINS, dtype=np.float64)
    for i in range(_FFT_BINS):
        mask = (r >= bins[i]) & (r < bins[i + 1])
        if mask.any():
            features[i] = float(mag[mask].mean())

    total = features.sum()
    return features / (total + 1e-10)


def _extract_texture_features(gray: np.ndarray) -> np.ndarray:
    """
    Vecteur de features texture complet pour un patch en niveaux de gris.
    Concatenation : GLCM (48) + LBP (256) + FFT (32) = 336 features.
    """
    # GLCM : 4 propriétés × 3 distances × 4 angles = 48
    glcm_feats: list[np.ndarray] = []
    for d in _GLCM_DISTANCES:
        for a in _GLCM_ANGLES_DEG:
            glcm = _compute_glcm(gray, d, a)
            glcm_feats.append(_glcm_props(glcm))
    glcm_vec = np.concatenate(glcm_feats)   # (48,)

    lbp_vec = _compute_lbp_histogram(gray)   # (256,)
    fft_vec = _compute_fft_features(gray)    # (32,)

    return np.concatenate([glcm_vec, lbp_vec, fft_vec])  # (336,)


def _extract_logo_crop(image: np.ndarray,
                       logo_def: LogoDefinition,
                       ppm_x: float, ppm_y: float) -> Optional[np.ndarray]:
    """Extrait le crop zone logo en pixels depuis les coordonnées mm."""
    H, W = image.shape[:2]
    bbox = logo_def.expected_zone
    x  = int(round(bbox.x * ppm_x))
    y  = int(round(bbox.y * ppm_y))
    bw = int(round(bbox.w * ppm_x))
    bh = int(round(bbox.h * ppm_y))

    x, y   = max(0, x), max(0, y)
    bw, bh = min(bw, W - x), min(bh, H - y)

    if bw <= 0 or bh <= 0:
        logger.warning("CalibrationEngine: crop logo '%s' hors image", logo_def.logo_id)
        return None

    return image[y:y + bh, x:x + bw]


# ─────────────────────────────────────────────────────────────────────────────
#  CalibrationEngine
# ─────────────────────────────────────────────────────────────────────────────

class CalibrationEngine:
    """
    Calibration automatique 7 étapes — §10.

    calibrate(reference_images, product_def) → CalibrationResult

    Artefacts sauvegardés dans :
      products/{product_id}/calibration/
    """

    def __init__(self, products_root: Path = Path("products")) -> None:
        self._products_root = products_root
        self._sift = cv2.SIFT_create(nfeatures=_SIFT_NFEATURES)

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def calibrate(
        self,
        reference_images: list[np.ndarray],
        product_def: ProductDefinition,
    ) -> CalibrationResult:
        """
        Lance les 7 étapes de calibration.

        Args:
            reference_images : liste de frames BGR (au moins 1, idéalement 5+)
            product_def      : définition produit

        Returns:
            CalibrationResult avec chemins vers tous les artefacts sauvegardés.

        Raises:
            CalibrationError : si une étape échoue (ex. < 1000 keypoints step 4)
        """
        if not reference_images:
            raise CalibrationError("Calibration : au moins une image de référence requise")

        calib_dir = self._products_root / product_def.product_id / "calibration"
        calib_dir.mkdir(parents=True, exist_ok=True)
        logger.info("CalibrationEngine: début 7 étapes → %s", calib_dir)

        ref_img = reference_images[0]  # image primaire

        # ── Étape 1 ────────────────────────────────────────────────────────────
        ppm_x, ppm_y = self._step1_pixel_per_mm(ref_img, product_def, calib_dir)

        # ── Étape 2 ────────────────────────────────────────────────────────────
        mean_b, std_b, min_ok, max_ok = self._step2_brightness_reference(
            reference_images, calib_dir)

        # ── Étape 3 ────────────────────────────────────────────────────────────
        noise_floor = self._step3_noise_reference(reference_images, calib_dir)

        # ── Étape 4 ────────────────────────────────────────────────────────────
        sift_path = self._step4_sift_alignment(ref_img, calib_dir)

        # ── Étape 5 ────────────────────────────────────────────────────────────
        logo_paths = self._step5_logo_templates(
            ref_img, product_def, ppm_x, ppm_y, calib_dir)

        # ── Étape 6 ────────────────────────────────────────────────────────────
        color_path = self._step6_color_reference(
            ref_img, product_def, ppm_x, ppm_y, calib_dir)

        # ── Étape 7 ────────────────────────────────────────────────────────────
        texture_path, iso_path = self._step7_texture_reference(
            reference_images, calib_dir)

        result = CalibrationResult(
            product_id=product_def.product_id,
            calibration_dir=calib_dir,
            pixel_per_mm_x=ppm_x,
            pixel_per_mm_y=ppm_y,
            brightness_ref_mean=mean_b,
            brightness_ref_std=std_b,
            brightness_ref_min_ok=min_ok,
            brightness_ref_max_ok=max_ok,
            noise_floor=noise_floor,
            sift_template_path=sift_path,
            logo_template_paths=logo_paths,
            color_reference_path=color_path,
            texture_reference_path=texture_path,
            iso_forest_path=iso_path,
            num_reference_images=len(reference_images),
        )
        logger.info("CalibrationEngine: calibration terminée — %s", calib_dir)
        return result

    # ── Étape 1 : pixel_per_mm ────────────────────────────────────────────────

    def _step1_pixel_per_mm(
        self,
        image: np.ndarray,
        product_def: ProductDefinition,
        calib_dir: Path,
    ) -> tuple[float, float]:
        H, W = image.shape[:2]
        ppm_x = W / product_def.width_mm
        ppm_y = H / product_def.height_mm

        # Vérifier cohérence (ratio ≤ 5% d'écart)
        ratio = ppm_x / ppm_y if ppm_y > 0 else 0.0
        if not (0.90 <= ratio <= 1.10):
            logger.warning(
                "CalibrationEngine §10 étape 1 : pixel_per_mm incohérent "
                "X=%.3f Y=%.3f ratio=%.3f", ppm_x, ppm_y, ratio)

        data = {"pixel_per_mm_x": ppm_x, "pixel_per_mm_y": ppm_y,
                "image_width": W, "image_height": H,
                "product_width_mm": product_def.width_mm,
                "product_height_mm": product_def.height_mm}
        _write_json(calib_dir / "pixel_per_mm.json", data)
        logger.info("§10 Étape 1 : pixel_per_mm X=%.3f Y=%.3f", ppm_x, ppm_y)
        return ppm_x, ppm_y

    # ── Étape 2 : brightness_reference ────────────────────────────────────────

    def _step2_brightness_reference(
        self,
        images: list[np.ndarray],
        calib_dir: Path,
    ) -> tuple[float, float, float, float]:
        means = []
        for img in images:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            means.append(float(np.mean(gray)))

        mean_b = float(np.mean(means))
        std_b  = float(np.std(means)) if len(means) > 1 else 0.0

        # Prendre std depuis la première image (variabilité intra-image)
        gray0 = cv2.cvtColor(images[0], cv2.COLOR_BGR2GRAY)
        std_b  = float(np.std(gray0))

        min_ok = mean_b * (1.0 - _WARNING_PERCENT / 100.0)
        max_ok = mean_b * (1.0 + _WARNING_PERCENT / 100.0)

        data = {"mean": mean_b, "std": std_b,
                "min_ok": min_ok, "max_ok": max_ok,
                "warn_percent": _WARNING_PERCENT,
                "critical_percent": _CRITICAL_PERCENT}
        _write_json(calib_dir / "brightness_reference.json", data)
        logger.info("§10 Étape 2 : brightness mean=%.1f std=%.1f min_ok=%.1f max_ok=%.1f",
                    mean_b, std_b, min_ok, max_ok)
        return mean_b, std_b, min_ok, max_ok

    # ── Étape 3 : noise_reference ─────────────────────────────────────────────

    def _step3_noise_reference(
        self,
        images: list[np.ndarray],
        calib_dir: Path,
    ) -> float:
        floors = []
        for img in images:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            floors.append(float(np.percentile(gray, 5)))

        noise_floor = float(np.mean(floors))
        data = {"noise_floor": noise_floor, "percentile": 5,
                "n_images": len(images)}
        _write_json(calib_dir / "noise_reference.json", data)
        logger.info("§10 Étape 3 : noise_floor=%.2f", noise_floor)
        return noise_floor

    # ── Étape 4 : SIFT alignment template ────────────────────────────────────

    def _step4_sift_alignment(
        self,
        image: np.ndarray,
        calib_dir: Path,
    ) -> Path:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        kps, descs = self._sift.detectAndCompute(gray, None)

        if descs is None or len(kps) < _SIFT_MIN_KP:
            n = len(kps) if kps else 0
            raise CalibrationError(
                f"§10 Étape 4 : SIFT insuffisant ({n} keypoints < {_SIFT_MIN_KP}). "
                "Vérifier l'éclairage et la mise au point."
            )

        path = calib_dir / "alignment_template.pkl"
        _save_sift_template(path, kps, descs, gray.shape)
        logger.info("§10 Étape 4 : SIFT template sauvegardé (%d kp) → %s",
                    len(kps), path)
        return path

    # ── Étape 5 : Logo templates ──────────────────────────────────────────────

    def _step5_logo_templates(
        self,
        image: np.ndarray,
        product_def: ProductDefinition,
        ppm_x: float,
        ppm_y: float,
        calib_dir: Path,
    ) -> dict[str, Path]:
        logo_paths: dict[str, Path] = {}

        if not product_def.logo_definitions:
            logger.info("§10 Étape 5 : aucun logo défini — skip")
            return logo_paths

        for idx, logo_def in enumerate(product_def.logo_definitions):
            crop = _extract_logo_crop(image, logo_def, ppm_x, ppm_y)
            if crop is None or crop.size == 0:
                logger.warning("§10 Étape 5 : crop vide pour logo '%s'", logo_def.logo_id)
                continue

            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            kps, descs = self._sift.detectAndCompute(gray_crop, None)

            if descs is None:
                descs = np.zeros((0, 128), dtype=np.float32)
                kps   = []

            path = calib_dir / f"logo_{idx}_template.pkl"
            _save_sift_template(path, kps, descs, gray_crop.shape)
            logo_paths[logo_def.logo_id] = path
            logger.info("§10 Étape 5 : logo '%s' → %d kp → %s",
                        logo_def.logo_id, len(kps), path)

        _write_json(calib_dir / "logo_template_index.json",
                    {lid: str(p) for lid, p in logo_paths.items()})
        return logo_paths

    # ── Étape 6 : Color reference ─────────────────────────────────────────────

    def _step6_color_reference(
        self,
        image: np.ndarray,
        product_def: ProductDefinition,
        ppm_x: float,
        ppm_y: float,
        calib_dir: Path,
    ) -> Path:
        color_ref: dict[str, dict] = {}

        if not product_def.logo_definitions:
            logger.info("§10 Étape 6 : aucun logo — color_reference vide")
        else:
            from sklearn.cluster import KMeans

            for logo_def in product_def.logo_definitions:
                crop = _extract_logo_crop(image, logo_def, ppm_x, ppm_y)
                if crop is None or crop.size == 0:
                    logger.warning("§10 Étape 6 : crop vide logo '%s'", logo_def.logo_id)
                    continue

                lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
                pixels = lab.reshape(-1, 3).astype(np.float32)

                if len(pixels) < _KMEANS_K:
                    logger.warning("§10 Étape 6 : trop peu de pixels pour K-means logo '%s'",
                                   logo_def.logo_id)
                    continue

                km = KMeans(n_clusters=_KMEANS_K, random_state=_KMEANS_SEED,
                            n_init="auto")
                km.fit(pixels)
                counts    = np.bincount(km.labels_)
                dominant  = km.cluster_centers_[counts.argmax()]

                # LAB → BGR → hex
                lab_px    = np.uint8([[dominant.clip(0, 255).astype(np.uint8)]])
                bgr_px    = cv2.cvtColor(lab_px, cv2.COLOR_LAB2BGR)
                r_hex     = int(bgr_px[0, 0, 2])
                g_hex     = int(bgr_px[0, 0, 1])
                b_hex     = int(bgr_px[0, 0, 0])
                ref_hex   = f"#{r_hex:02x}{g_hex:02x}{b_hex:02x}"

                color_ref[logo_def.logo_id] = {
                    "lab_mean":    dominant.tolist(),
                    "lab_clusters": km.cluster_centers_.tolist(),
                    "lab_counts":  counts.tolist(),
                    "ref_hex":     ref_hex,
                }
                logger.info("§10 Étape 6 : logo '%s' dominant LAB=%s hex=%s",
                            logo_def.logo_id,
                            [round(v, 1) for v in dominant.tolist()], ref_hex)

        path = calib_dir / "color_reference.json"
        _write_json(path, color_ref)
        logger.info("§10 Étape 6 : color_reference → %s", path)
        return path

    # ── Étape 7 : Texture reference + IsolationForest ─────────────────────────

    def _step7_texture_reference(
        self,
        images: list[np.ndarray],
        calib_dir: Path,
    ) -> tuple[Path, Path]:
        """
        Calcule les features texture de référence (GLCM + LBP + FFT)
        et entraîne un IsolationForest initial sur les frames GOOD.

        GR-01 : seed=42 pour IsolationForest.
        """
        feature_matrix: list[np.ndarray] = []

        for img in images:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            feats = _extract_texture_features(gray)
            feature_matrix.append(feats)

        X = np.vstack(feature_matrix)     # (n_images, 336)

        # Référence statistique
        ref_mean = X.mean(axis=0)
        ref_std  = X.std(axis=0) + 1e-10

        texture_path = calib_dir / "texture_reference.npz"
        np.savez_compressed(
            texture_path,
            ref_mean=ref_mean,
            ref_std=ref_std,
            feature_matrix=X,
            glcm_distances=np.array(_GLCM_DISTANCES),
            glcm_angles=np.array(_GLCM_ANGLES_DEG),
            lbp_p=np.array([_LBP_P]),
            lbp_r=np.array([_LBP_R]),
            fft_bins=np.array([_FFT_BINS]),
        )
        logger.info("§10 Étape 7 : texture_reference.npz sauvegardé (%d images)", len(images))

        # IsolationForest initial (fit sur frames GOOD)
        iso = IsolationForest(
            n_estimators=_ISO_N_ESTIMATORS,
            contamination="auto",
            bootstrap=True,
            random_state=_ISO_SEED,   # GR-01
            n_jobs=-1,
        )
        iso.fit(X)

        # Export : ONNX si skl2onnx disponible, sinon pkl
        iso_path = _save_iso_forest(iso, X.shape[1], calib_dir)
        logger.info("§10 Étape 7 : IsolationForest → %s", iso_path)

        return texture_path, iso_path


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers I/O
# ─────────────────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _save_iso_forest(iso: IsolationForest, n_features: int, calib_dir: Path) -> Path:
    """Sauvegarde IsolationForest en ONNX (skl2onnx) ou pkl (fallback)."""
    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
        onnx_model = convert_sklearn(
            iso,
            initial_types=[("input", FloatTensorType([None, n_features]))],
        )
        path = calib_dir / "isolation_forest_init.onnx"
        with open(path, "wb") as fh:
            fh.write(onnx_model.SerializeToString())
        return path
    except ImportError:
        logger.warning(
            "skl2onnx non installé — IsolationForest sauvegardé en .pkl "
            "(installer skl2onnx pour export .onnx)"
        )
        path = calib_dir / "isolation_forest_init.pkl"
        joblib.dump(iso, path, compress=3)
        return path
