"""
GlobalGates — 3 Gates globales d'apprentissage — §11.3
Protègent le système avant toute activation d'un nouveau modèle.
GR-08 : aucune interaction avec RuleEngine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.tier_result import TierLevel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  GateResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GateResult:
    """Résultat d'une gate de validation — §11.3."""
    gate_id : str
    passed  : bool
    details : dict = field(default_factory=dict, hash=False, compare=False)


# ─────────────────────────────────────────────────────────────────────────────
#  GoldenSample — format attendu par GlobalGates._evaluate_model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GoldenSample:
    """
    Sample du dataset de référence pour évaluation anti-régression — §11.3.
    features : vecteur numpy float32 (shape dépend du modèle)
    label    : 1 = OK (normal), 0 = NOK (anomalie)
    """
    features : Any   # np.ndarray
    label    : int   # 1 OK · 0 NOK


# ─────────────────────────────────────────────────────────────────────────────
#  GlobalGates
# ─────────────────────────────────────────────────────────────────────────────

class GlobalGates:
    """
    3 Gates globales de protection — §11.3.

    Gate ① confiance : dans TierLearningBuffer (par Tier)
    Gate ② anti-régression : nouveau modèle ≥ actuel ET ≥ golden_pass_rate_min
    Gate ③ drift KS-test : KS-stat < drift_threshold par Tier

    Appliquées AVANT toute activation d'un nouveau modèle.
    GR-08 : aucune interaction avec RuleEngine.
    """

    def __init__(self, config: Any = None) -> None:
        cfg  = config or {}
        _get = cfg.get if hasattr(cfg, "get") else lambda k, d=None: d

        self._golden_pass_min  = float(_get("learning.golden_pass_rate_min", 0.95))
        self._drift_threshold  = float(_get("learning.drift_threshold",       0.15))

    # ── Gate ② — Anti-régression ──────────────────────────────────────────────

    def check_anti_regression(
        self,
        new_model_path:     str,
        golden_dataset:     list[GoldenSample],
        current_model_path: Any,   # str | Path | None
    ) -> GateResult:
        """
        Gate ② — Anti-régression : nouveau modèle ≥ actuel ET ≥ golden_pass_rate_min.

        Évalue les deux modèles sur golden_dataset (accuracy).
        Si le dataset est vide ou le modèle actuel absent → compare seulement à la constante.

        Returns GateResult(passed=True) si nouvelle version acceptable.
        """
        if not golden_dataset:
            logger.warning("GlobalGates anti_regression: dataset vide → gate acceptée par défaut")
            return GateResult(
                gate_id="anti_regression",
                passed=True,
                details={"reason": "empty_golden_dataset"},
            )

        new_rate = self._evaluate_model(str(new_model_path), golden_dataset)

        current_rate = 0.0
        if current_model_path and Path(str(current_model_path)).exists():
            current_rate = self._evaluate_model(str(current_model_path), golden_dataset)
        else:
            logger.debug("GlobalGates anti_regression: pas de modèle actuel — compare à 0.0")

        passed = new_rate >= self._golden_pass_min and new_rate >= current_rate

        if not passed:
            logger.warning(
                "GlobalGates gate② anti_regression: REJETÉ new=%.3f current=%.3f min=%.3f",
                new_rate, current_rate, self._golden_pass_min,
            )
        else:
            logger.info(
                "GlobalGates gate② anti_regression: ACCEPTÉ new=%.3f current=%.3f",
                new_rate, current_rate,
            )

        return GateResult(
            gate_id="anti_regression",
            passed=passed,
            details={
                "new_rate":     round(new_rate, 3),
                "current_rate": round(current_rate, 3),
                "min_required": self._golden_pass_min,
            },
        )

    # ── Gate ③ — Drift KS-test ────────────────────────────────────────────────

    def check_drift(
        self,
        tier:             TierLevel,
        recent_scores:    list[float],
        reference_scores: list[float],
    ) -> GateResult:
        """
        Gate ③ — Drift Kolmogorov-Smirnov par Tier.

        KS-stat < drift_threshold → pas de dérive → gate passée.
        Données insuffisantes (< 10 de chaque côté) → accepté par défaut.
        """
        gate_id = f"drift_{tier.value}"

        if len(recent_scores) < 10 or len(reference_scores) < 10:
            return GateResult(
                gate_id=gate_id,
                passed=True,
                details={"reason": "insufficient_data",
                         "recent_n": len(recent_scores),
                         "reference_n": len(reference_scores)},
            )

        try:
            from scipy import stats
        except ImportError:
            logger.warning("GlobalGates: scipy absent — gate③ drift acceptée par défaut")
            return GateResult(
                gate_id=gate_id,
                passed=True,
                details={"reason": "scipy_unavailable"},
            )

        ks_stat, p_value = stats.ks_2samp(recent_scores, reference_scores)
        passed = ks_stat < self._drift_threshold

        if not passed:
            logger.warning(
                "GlobalGates gate③ drift Tier %s: DÉRIVE DÉTECTÉE KS=%.3f > seuil=%.3f",
                tier.value, ks_stat, self._drift_threshold,
            )
        else:
            logger.debug(
                "GlobalGates gate③ drift Tier %s: OK KS=%.3f < %.3f",
                tier.value, ks_stat, self._drift_threshold,
            )

        return GateResult(
            gate_id=gate_id,
            passed=passed,
            details={
                "ks_statistic": round(ks_stat, 3),
                "threshold":    self._drift_threshold,
                "p_value":      round(float(p_value), 4),
            },
        )

    # ── Évaluation modèle ─────────────────────────────────────────────────────

    def _evaluate_model(self, model_path: str, golden_dataset: list[GoldenSample]) -> float:
        """
        Évalue le golden_pass_rate d'un modèle sur le dataset de référence.

        Supporte ONNX (onnxruntime) et pickle/joblib.
        Retourne 0.0 si le modèle ne peut pas être chargé.
        """
        import numpy as np

        path = Path(model_path)
        if not path.exists():
            logger.warning("GlobalGates._evaluate_model: chemin absent — %s", model_path)
            return 0.0

        try:
            if path.suffix == ".onnx":
                return self._evaluate_onnx(model_path, golden_dataset)
            else:
                return self._evaluate_pickle(model_path, golden_dataset)
        except Exception as exc:
            logger.error("GlobalGates._evaluate_model: erreur — %s — %s", model_path, exc)
            return 0.0

    def _evaluate_onnx(self, model_path: str, golden_dataset: list[GoldenSample]) -> float:
        """Évaluation via onnxruntime."""
        import numpy as np
        import onnxruntime as ort

        session      = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        input_name   = session.get_inputs()[0].name
        correct      = 0

        for sample in golden_dataset:
            features = np.array(sample.features, dtype=np.float32).reshape(1, -1)
            outputs  = session.run(None, {input_name: features})
            pred     = int(outputs[0][0]) if outputs else -1
            if pred == sample.label:
                correct += 1

        return correct / len(golden_dataset)

    def _evaluate_pickle(self, model_path: str, golden_dataset: list[GoldenSample]) -> float:
        """Évaluation via joblib (IsolationForest ou autre sklearn)."""
        import joblib
        import numpy as np

        model   = joblib.load(model_path)
        correct = 0

        for sample in golden_dataset:
            features = np.array(sample.features, dtype=np.float32).reshape(1, -1)
            # IsolationForest : predict retourne 1 (normal) ou -1 (anomalie)
            pred_raw = model.predict(features)[0]
            pred     = 1 if pred_raw == 1 else 0
            if pred == sample.label:
                correct += 1

        return correct / len(golden_dataset)
