"""
ModelValidator — Gate anti-régression §11.3 Gate ②
GR-13 : ModelValidator.validate() obligatoire avant activation de tout nouveau modèle.
golden_pass_rate ≥ 0.95
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ai.model_builder import IsoForestModel
from ai.feature_extractor import FEATURE_DIM

logger = logging.getLogger(__name__)

_PASS_RATE_MIN = 0.95   # §11.3 Gate ② — seuil anti-régression


# ─────────────────────────────────────────────────────────────────────────────
#  GoldenDataset
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GoldenDataset:
    """
    Dataset de référence doré utilisé par ModelValidator.

    features   : (N, FEATURE_DIM) float32
    labels     : (N,) int — 1 = inlier (GOOD), -1 = anomalie (BAD)
    product_id : produit associé (traçabilité)

    Construit une seule fois à partir des samples validés par opérateur.
    Jamais modifié (frozen) — GR-07.
    """
    features:   np.ndarray
    labels:     np.ndarray
    product_id: str

    def __post_init__(self) -> None:
        if self.features.ndim != 2:
            raise ValueError(
                f"GoldenDataset.features doit être 2D, shape={self.features.shape}"
            )
        if self.features.shape[1] != FEATURE_DIM:
            raise ValueError(
                f"GoldenDataset.features dim={self.features.shape[1]} ≠ {FEATURE_DIM}"
            )
        if len(self.features) != len(self.labels):
            raise ValueError(
                f"GoldenDataset: features ({len(self.features)}) "
                f"et labels ({len(self.labels)}) de longueurs différentes"
            )
        unique = set(self.labels.tolist())
        if not unique.issubset({1, -1}):
            raise ValueError(
                f"GoldenDataset.labels doit contenir uniquement 1 et -1, got {unique}"
            )
        if not self.product_id:
            raise ValueError("GoldenDataset.product_id vide")

    def __len__(self) -> int:
        return len(self.features)

    @classmethod
    def good_only(cls, features: np.ndarray, product_id: str) -> "GoldenDataset":
        """Crée un dataset golden avec uniquement des samples GOOD (label=1)."""
        labels = np.ones(len(features), dtype=np.int32)
        return cls(features=features, labels=labels, product_id=product_id)


# ─────────────────────────────────────────────────────────────────────────────
#  ModelValidator
# ─────────────────────────────────────────────────────────────────────────────

class ModelValidator:
    """
    Gate anti-régression §11.3 Gate ② — GR-13.

    validate(new_model, golden_dataset, current_model) → bool :
      new_rate = evaluate(new_model, golden_dataset)
      cur_rate = evaluate(current_model, golden_dataset) si fourni
      return (new_rate ≥ 0.95) and (new_rate ≥ cur_rate)

    evaluate(model, dataset) :
      Applique model.predict() sur dataset.features
      Calcule la fraction correctement classifiée vs dataset.labels
      Retourne float ∈ [0.0, 1.0]

    GR-13 : appelé AVANT toute activation de modèle retrain.
            Échec → BackgroundTrainer discard le modèle + log WARNING.
    """

    def validate(
        self,
        new_model:      IsoForestModel,
        golden_dataset: GoldenDataset,
        current_model:  Optional[IsoForestModel] = None,
    ) -> bool:
        """
        Valide le nouveau modèle contre le dataset golden.

        Args:
            new_model      : modèle candidat (issu du retrain)
            golden_dataset : dataset de référence figé
            current_model  : modèle actuellement en production (pour Gate anti-régression)
                             Si None → seule la gate 0.95 est appliquée.

        Returns:
            True si le nouveau modèle passe TOUTES les gates.
        """
        new_rate = self._evaluate(new_model, golden_dataset)

        if current_model is None:
            passed = new_rate >= _PASS_RATE_MIN
            logger.info(
                "ModelValidator [%s]: new_rate=%.3f ≥ %.2f → %s",
                golden_dataset.product_id, new_rate, _PASS_RATE_MIN,
                "PASS" if passed else "FAIL",
            )
            return passed

        cur_rate = self._evaluate(current_model, golden_dataset)
        passed   = (new_rate >= _PASS_RATE_MIN) and (new_rate >= cur_rate)

        logger.info(
            "ModelValidator [%s]: new_rate=%.3f cur_rate=%.3f "
            "min=%.2f anti-regression=%s → %s",
            golden_dataset.product_id,
            new_rate, cur_rate, _PASS_RATE_MIN,
            "OK" if new_rate >= cur_rate else "FAIL",
            "PASS" if passed else "FAIL",
        )
        return passed

    # ── Évaluation ────────────────────────────────────────────────────────────

    def _evaluate(
        self,
        model:   IsoForestModel,
        dataset: GoldenDataset,
    ) -> float:
        """
        Calcule le taux de classification correcte sur le dataset golden.

        Pass rate = fraction de samples où model.predict() == dataset.labels.
        Pour les samples GOOD (label=1)  : le modèle doit prédire 1 (inlier).
        Pour les samples BAD  (label=-1) : le modèle doit prédire -1 (outlier).

        Returns:
            float ∈ [0.0, 1.0]
        """
        try:
            predictions = model.predict(dataset.features.astype(np.float32))
            correct     = predictions == dataset.labels
            rate        = float(np.mean(correct))
            logger.debug(
                "ModelValidator._evaluate [%s/%s]: %d/%d correct → %.3f",
                dataset.product_id, model.path.name,
                int(correct.sum()), len(correct), rate,
            )
            return rate
        except Exception as exc:
            logger.error(
                "ModelValidator._evaluate: exception sur %s — %s",
                model.path, exc, exc_info=True,
            )
            return 0.0
