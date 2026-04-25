"""
IsoForest n=1000 seed=42 + ONNX export (skl2onnx) ou joblib fallback
§6.5 · §11 — GR-01 : random_state=42 garanti
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from ai.feature_extractor import FEATURE_DIM
from core.tier_result import TierLevel

logger = logging.getLogger(__name__)

_ISO_N_ESTIMATORS = 1000
_ISO_SEED         = 42   # GR-01 : déterminisme garanti


# ─────────────────────────────────────────────────────────────────────────────
#  IsoForestModel — wrapper runtime (ONNX ou pkl)
# ─────────────────────────────────────────────────────────────────────────────

class IsoForestModel:
    """
    Wrapper runtime autour d'un IsolationForest sauvegardé (.onnx ou .pkl).

    score(features) → float [0, 1]
      0 = clairement normal (inlier)
      1 = clairement anomalie (outlier)
      Utilisé par SurfaceObserver (§6.5) : anomaly_score = 0.45 × iso_score.

    predict(features) → np.ndarray de -1 (anomalie) ou 1 (inlier)
      Utilisé par ModelValidator.

    Chargement paresseux : le fichier est lu une fois au premier appel.
    """

    def __init__(
        self,
        path:       Path,
        tier:       TierLevel = TierLevel.MINOR,
        version:    str       = "v1",
        n_features: int       = FEATURE_DIM,
    ) -> None:
        self.path       = Path(path)
        self.tier       = tier
        self.version    = version
        self.n_features = n_features

        self._clf:     Optional[IsolationForest]    = None
        self._session: Any                          = None   # onnxruntime.InferenceSession
        self._loaded   = False

    # ── API publique ──────────────────────────────────────────────────────────

    def score(self, features: np.ndarray) -> float:
        """
        Anomaly score ∈ [0, 1].
        Basé sur decision_function (négatif = outlier) mappé via sigmoid.
        """
        self._ensure_loaded()
        feat = np.atleast_2d(features.astype(np.float32))

        if self._clf is not None:
            # decision_function : positif = inlier, négatif = outlier
            df = float(self._clf.decision_function(feat).mean())
            # sigmoid(-df*6) : df=0→0.5, df>0→<0.5 (normal), df<0→>0.5 (anomalie)
            return float(1.0 / (1.0 + math.exp(df * 6.0)))

        if self._session is not None:
            inp_name = self._session.get_inputs()[0].name
            labels   = self._session.run(None, {inp_name: feat})[0]
            # Label -1 = anomalie, 1 = inlier → score binaire
            return float(np.mean(labels == -1))

        raise RuntimeError(f"IsoForestModel: modèle non chargé — {self.path}")

    def predict(self, features: np.ndarray) -> np.ndarray:
        """
        Prédit -1 (anomalie) ou 1 (inlier) pour chaque sample.
        Utilisé par ModelValidator.
        """
        self._ensure_loaded()
        feat = np.atleast_2d(features.astype(np.float32))

        if self._clf is not None:
            return self._clf.predict(feat)

        if self._session is not None:
            inp_name = self._session.get_inputs()[0].name
            return self._session.run(None, {inp_name: feat})[0]

        raise RuntimeError(f"IsoForestModel: modèle non chargé — {self.path}")

    # ── Chargement ────────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if not self.path.exists():
            raise FileNotFoundError(f"IsoForestModel: fichier absent — {self.path}")

        if self.path.suffix == ".onnx":
            try:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.log_severity_level = 3   # ERROR uniquement
                self._session = ort.InferenceSession(str(self.path), sess_options=opts)
            except ImportError:
                logger.warning("IsoForestModel: onnxruntime absent — fallback pkl non disponible")
                raise
        else:
            self._clf = joblib.load(self.path)

        self._loaded = True
        logger.debug("IsoForestModel: chargé depuis %s", self.path)

    def __repr__(self) -> str:
        return (
            f"IsoForestModel(path={self.path.name!r}, "
            f"tier={self.tier.value}, version={self.version!r})"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  IsolationForestBuilder
# ─────────────────────────────────────────────────────────────────────────────

class IsolationForestBuilder:
    """
    Entraîne et sauvegarde un IsolationForest pour un produit/Tier donné.

    build(features, product_id, tier) :
      1. Fit IsolationForest(n=1000, contamination='auto', bootstrap=True, seed=42)
      2. Export ONNX via skl2onnx (target_opset=12) si disponible
      3. Fallback joblib .pkl avec WARNING si skl2onnx absent
      4. Sauvegarde dans products/{product_id}/models/iso_forest_{tier}.onnx
      5. Retourne IsoForestModel pointant vers le fichier

    GR-01 : random_state=42 — déterministe.
    GR-09 : entraînement uniquement ici — DatasetManager ne fait que du I/O.
    """

    def build(
        self,
        features:   np.ndarray,
        product_id: str,
        tier:       TierLevel = TierLevel.MINOR,
    ) -> IsoForestModel:
        """
        Args:
            features   : (N, 256) float32 — features des frames GOOD
            product_id : identifiant produit
            tier       : Tier cible (par défaut MINOR pour SurfaceObserver)

        Returns:
            IsoForestModel prêt à l'emploi.

        Raises:
            ValueError : si features invalides (ndim ≠ 2 ou dim ≠ FEATURE_DIM)
        """
        if features.ndim != 2:
            raise ValueError(
                f"IsolationForestBuilder: features doit être 2D, shape={features.shape}"
            )
        if features.shape[1] != FEATURE_DIM:
            raise ValueError(
                f"IsolationForestBuilder: features dim={features.shape[1]} ≠ {FEATURE_DIM}"
            )
        if len(features) < 2:
            raise ValueError(
                f"IsolationForestBuilder: minimum 2 samples requis, got {len(features)}"
            )

        logger.info(
            "IsolationForestBuilder: fit IsoForest n=%d samples / tier=%s / product='%s'",
            len(features), tier.value, product_id,
        )

        iso = IsolationForest(
            n_estimators=_ISO_N_ESTIMATORS,
            contamination="auto",
            bootstrap=True,
            random_state=_ISO_SEED,   # GR-01
            n_jobs=-1,
        )
        iso.fit(features)

        model_dir = Path("products") / product_id / "models"
        model_dir.mkdir(parents=True, exist_ok=True)

        save_path = self._save_model(iso, model_dir, tier, features.shape[1])

        logger.info("IsolationForestBuilder: modèle sauvegardé → %s", save_path)

        return IsoForestModel(
            path=save_path,
            tier=tier,
            version="v1",
            n_features=features.shape[1],
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _save_model(
        iso:        IsolationForest,
        model_dir:  Path,
        tier:       TierLevel,
        n_features: int,
    ) -> Path:
        """
        Sauvegarde en ONNX si skl2onnx disponible, sinon pkl.
        target_opset=12 requis par §6.5.
        """
        try:
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType

            initial_types = [("float_input", FloatTensorType([None, n_features]))]
            onnx_model    = convert_sklearn(
                iso,
                initial_types=initial_types,
                target_opset=12,
            )
            path = model_dir / f"iso_forest_{tier.value}.onnx"
            with open(path, "wb") as fh:
                fh.write(onnx_model.SerializeToString())
            return path

        except ImportError:
            logger.warning(
                "IsolationForestBuilder: skl2onnx absent — "
                "IsolationForest sauvegardé en .pkl "
                "(installer skl2onnx pour export ONNX target_opset=12)"
            )
            path = model_dir / f"iso_forest_{tier.value}.pkl"
            joblib.dump(iso, path, compress=3)
            return path
