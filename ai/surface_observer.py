"""
SurfaceObserver MINOR tier Mini Ensemble — §6.5
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
GR-11 : jamais None — échec → ObserverSignal(confidence=0, error_msg=...)

ANTI-PATTERN INTERDIT : fusion de scores de tiers différents.
La fusion Texture×IsoForest ici est INTERNE à l'observer MINOR.
Le RuleEngine ne voit qu'un seul ObserverSignal.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from ai.feature_extractor import FeatureExtractor
from ai.model_builder import IsoForestModel
from ai.texture_analyzer import TextureAnalyzer, TextureReference
from core.ai_observer import AIObserver
from core.models import CriterionRule, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel

logger = logging.getLogger(__name__)

_TEXTURE_W  = 0.55   # poids anomalie texture dans le mini-ensemble
_ISO_W      = 0.45   # poids anomalie IsoForest

# Chemins de modèles — ordre de priorité (le plus récent d'abord)
_ISO_MODEL_CANDIDATES = [
    "models/iso_forest_MINOR.onnx",
    "models/iso_forest_MINOR.pkl",
    "calibration/isolation_forest_init.onnx",
    "calibration/isolation_forest_init.pkl",
]


class SurfaceObserver(AIObserver):
    """
    Observer de surface — Mini Ensemble interne GLCM+LBP+FFT + IsolationForest — §6.5.

    Architecture Mini Ensemble (SEUL endroit autorisé de fusion — CLAUDE.md) :
      texture_anomaly = 1.0 - TextureAnalyzer.analyze(frame, reference)
      iso_anomaly     = IsoForestModel.score(features)       [0,1]
      anomaly_score   = 0.55 × texture_anomaly + 0.45 × iso_anomaly
      passed          = anomaly_score ≤ rule.threshold        (défaut 0.30)

    Le RuleEngine ne voit qu'un seul ObserverSignal avec une seule valeur.
    La décomposition texture/iso est dans details (display only).

    GR-04 : retourne UNIQUEMENT ObserverSignal — jamais "OK", "NOK", True, False.
    GR-11 : try/except global → ObserverSignal(confidence=0, error_msg=...) si crash.
    """

    def __init__(
        self,
        texture_analyzer:  Optional[TextureAnalyzer]  = None,
        feature_extractor: Optional[FeatureExtractor] = None,
    ) -> None:
        self._texture   = texture_analyzer  or TextureAnalyzer()
        self._extractor = feature_extractor or FeatureExtractor()
        # Caches stables pendant RUNNING (GR-12)
        self._ref_cache: dict[str, Optional[TextureReference]] = {}
        self._iso_cache: dict[str, Optional[IsoForestModel]]   = {}

    # ── ABC ───────────────────────────────────────────────────────────────────

    @property
    def observer_id(self) -> str:
        return "surface_mini_ensemble"

    @property
    def tier(self) -> TierLevel:
        return TierLevel.MINOR

    # ── Point d'entrée principal ──────────────────────────────────────────────

    def observe(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
    ) -> ObserverSignal:
        """
        GR-04 : retourne UNIQUEMENT ObserverSignal — jamais de verdict.
        GR-11 : capture toutes les exceptions → ObserverSignal(confidence=0, error_msg=...).
        """
        t0 = time.perf_counter()
        try:
            return self._observe_impl(frame, product_def, rule, t0)
        except Exception as exc:
            logger.error("SurfaceObserver: exception non gérée — %s", exc, exc_info=True)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=rule.threshold,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error_msg=str(exc),
            )

    # ── Implémentation ────────────────────────────────────────────────────────

    def _observe_impl(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
        t0:          float,
    ) -> ObserverSignal:
        pid       = product_def.product_id
        reference = self._load_reference(pid)
        iso_model = self._load_iso_model(pid)

        # ── Score texture ─────────────────────────────────────────────────────
        if reference is not None:
            texture_score   = self._texture.analyze(frame, reference)
            texture_anomaly = float(np.clip(1.0 - texture_score, 0.0, 1.0))
        else:
            logger.warning(
                "SurfaceObserver: texture_reference absent pour '%s' — texture_anomaly=0.5",
                pid,
            )
            texture_score   = 0.5
            texture_anomaly = 0.5

        # ── Score IsoForest ───────────────────────────────────────────────────
        if iso_model is not None:
            features    = self._extractor.extract(frame)   # (256,) float32
            iso_anomaly = float(np.clip(iso_model.score(features), 0.0, 1.0))
        else:
            logger.warning(
                "SurfaceObserver: IsoForestModel absent pour '%s' — iso_anomaly=0.5",
                pid,
            )
            iso_anomaly = 0.5

        # ── Mini Ensemble interne ─────────────────────────────────────────────
        # SEUL endroit autorisé de fusion — CLAUDE.md anti-pattern §6.5
        anomaly_score = _TEXTURE_W * texture_anomaly + _ISO_W * iso_anomaly
        anomaly_score = float(np.clip(anomaly_score, 0.0, 1.0))
        passed        = anomaly_score <= rule.threshold

        logger.debug(
            "SurfaceObserver: '%s' tex_anom=%.3f iso_anom=%.3f "
            "anomaly=%.3f threshold=%.3f passed=%s",
            pid, texture_anomaly, iso_anomaly, anomaly_score,
            rule.threshold, passed,
        )

        return ObserverSignal(
            observer_id=self.observer_id,
            tier=self.tier,
            passed=passed,
            confidence=float(np.clip(1.0 - anomaly_score, 0.0, 1.0)),
            value=round(anomaly_score, 4),
            threshold=rule.threshold,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={
                "texture_anomaly": round(texture_anomaly, 4),
                "iso_anomaly":     round(iso_anomaly, 4),
                "anomaly_score":   round(anomaly_score, 4),
                "texture_model":   "present" if reference is not None else "absent",
                "iso_model":       "present" if iso_model  is not None else "absent",
            },
        )

    # ── Chargement paresseux ──────────────────────────────────────────────────

    def _load_reference(self, product_id: str) -> Optional[TextureReference]:
        """
        Charge texture_reference.npz depuis calibration/, mis en cache.
        Retourne None si absent — l'observer continue avec texture_anomaly=0.5.
        """
        if product_id not in self._ref_cache:
            path = (Path("products") / product_id / "calibration"
                    / "texture_reference.npz")
            if not path.exists():
                logger.warning("SurfaceObserver: texture_reference absent — %s", path)
                self._ref_cache[product_id] = None
            else:
                try:
                    self._ref_cache[product_id] = TextureReference.from_npz(path)
                    logger.info("SurfaceObserver: texture_reference chargée — %s", path)
                except Exception as exc:
                    logger.error("SurfaceObserver: échec chargement %s — %s", path, exc)
                    self._ref_cache[product_id] = None
        return self._ref_cache[product_id]

    def _load_iso_model(self, product_id: str) -> Optional[IsoForestModel]:
        """
        Charge l'IsoForestModel disponible (retrain > init) pour le produit.
        Ordre de priorité : models/iso_forest_MINOR.{onnx,pkl} > calibration/isolation_forest_init.{onnx,pkl}
        Retourne None si aucun modèle disponible.
        """
        if product_id not in self._iso_cache:
            model = None
            for candidate in _ISO_MODEL_CANDIDATES:
                path = Path("products") / product_id / candidate
                if path.exists():
                    try:
                        model = IsoForestModel(
                            path=path,
                            tier=TierLevel.MINOR,
                            version="calibration" if "calibration" in candidate else "trained",
                        )
                        # Force eager load to catch errors now
                        model._ensure_loaded()
                        logger.info("SurfaceObserver: IsoForest chargé — %s", path)
                    except Exception as exc:
                        logger.error("SurfaceObserver: échec chargement %s — %s",
                                     path, exc)
                        model = None
                    if model is not None:
                        break

            if model is None:
                logger.warning(
                    "SurfaceObserver: aucun IsoForestModel disponible pour '%s'",
                    product_id,
                )
            self._iso_cache[product_id] = model
        return self._iso_cache[product_id]
