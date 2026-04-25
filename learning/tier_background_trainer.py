"""
TierBackgroundTrainer per-Tier — §11.1
Entraîne les modèles du Tier en thread daemon.
Valide via GlobalGates avant activation.
GR-09 : jamais dans le pipeline — thread daemon uniquement.
GR-01 : random_state=42 sur tous les modèles sklearn.
GR-08 : aucune interaction avec RuleEngine.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from core.tier_result import TierLevel
from learning.global_gates import GlobalGates, GoldenSample
from learning.tier_learning_buffer import LearningEntry

logger = logging.getLogger(__name__)

_MODELS_SUBDIR = "models"
_VERSIONS_SUBDIR = "versions"


class TierBackgroundTrainer:
    """
    Réentraîne les modèles d'un Tier en background — §11.1.

    Un trainer par Tier (CRITICAL / MAJOR / MINOR).
    Tourne dans un thread daemon via ThreadPoolExecutor(max_workers=1).

    Flux :
      1. trigger_retrain(entries) → submit _retrain_loop()
      2. _prepare_data()    → features + labels numpy
      3. _retrain_<type>()  → entraîne + sauve le modèle → chemin
      4. GlobalGates.check_anti_regression() + check_drift()
      5. Si gates passées → ModelVersionManager.activate_version()
      6. Si gates rejetées → log WARNING + discard

    GR-09 : trigger_retrain() ne bloque JAMAIS le pipeline.
    GR-01 : random_state=42 sur IsolationForest et KMeans.
    """

    # Observer IDs par Tier — utilisés pour activate_version
    _OBSERVER_IDS: dict[TierLevel, str] = {
        TierLevel.CRITICAL: "yolo_sift",
        TierLevel.MAJOR:    "color_reference",
        TierLevel.MINOR:    "surface_isoforest",
    }

    def __init__(
        self,
        tier:          TierLevel,
        product_id:    str,
        model_manager: Any,                   # ModelVersionManager
        global_gates:  GlobalGates,
        config:        Any = None,
        products_root: Path = Path("products"),
    ) -> None:
        cfg  = config or {}
        _get = cfg.get if hasattr(cfg, "get") else lambda k, d=None: d

        self._tier          = tier
        self._product_id    = product_id
        self._model_manager = model_manager
        self._global_gates  = global_gates
        self._products_root = Path(products_root)
        self._contamination = float(_get("learning.if_contamination", 0.05))
        self._n_estimators  = int(_get("learning.if_n_estimators",    100))
        self._kmeans_k      = int(_get("learning.kmeans_clusters",    8))
        self._golden_dataset: list[GoldenSample] = []

        self._is_training = threading.Event()
        self._executor    = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"Trainer-{tier.value}",
        )

    # ── API publique ──────────────────────────────────────────────────────────

    def trigger_retrain(self, entries: list[LearningEntry]) -> None:
        """
        Soumet un retrain en background — GR-09.

        Si un retrain est déjà en cours → ignoré (log DEBUG).
        Ne bloque jamais.
        """
        if self._is_training.is_set():
            logger.debug(
                "TierBackgroundTrainer [%s]: retrain en cours — trigger ignoré (%d samples)",
                self._tier.value, len(entries),
            )
            return

        logger.info(
            "TierBackgroundTrainer [%s]: retrain déclenché — %d samples",
            self._tier.value, len(entries),
        )
        self._executor.submit(self._retrain_loop, list(entries))

    def set_golden_dataset(self, samples: list[GoldenSample]) -> None:
        """Met à jour le golden dataset pour la gate anti-régression."""
        self._golden_dataset = list(samples)

    def shutdown(self, wait: bool = True) -> None:
        """Arrête le pool d'entraînement proprement."""
        self._executor.shutdown(wait=wait)

    # ── Boucle d'entraînement ─────────────────────────────────────────────────

    def _retrain_loop(self, entries: list[LearningEntry]) -> None:
        """
        Boucle principale de réentraînement — daemon.

        Appelée uniquement via trigger_retrain() → jamais bloquant pour le pipeline.
        """
        self._is_training.set()
        t0 = time.monotonic()
        try:
            features, labels, recent_scores = self._prepare_data(entries)
            if features is None or len(features) == 0:
                logger.warning(
                    "TierBackgroundTrainer [%s]: données insuffisantes — retrain annulé",
                    self._tier.value,
                )
                return

            new_model_path = self._train_for_tier(features, labels, entries)
            if new_model_path is None:
                return

            # Gate ② anti-régression
            current_path = self._model_manager.get_active_path(
                self._OBSERVER_IDS[self._tier],
                self._product_id,
            )
            gate_reg = self._global_gates.check_anti_regression(
                new_model_path=str(new_model_path),
                golden_dataset=self._golden_dataset,
                current_model_path=str(current_path) if current_path else None,
            )

            if not gate_reg.passed:
                logger.warning(
                    "TierBackgroundTrainer [%s]: gate② anti-régression REJETÉE — %s",
                    self._tier.value, gate_reg.details,
                )
                return

            # Gate ③ drift (scores récents vs. scores du buffer)
            reference_scores = [e.tier_score for e in entries[: len(entries) // 2]]
            gate_drift = self._global_gates.check_drift(
                tier=self._tier,
                recent_scores=recent_scores,
                reference_scores=reference_scores,
            )

            if not gate_drift.passed:
                logger.warning(
                    "TierBackgroundTrainer [%s]: gate③ drift REJETÉE — %s",
                    self._tier.value, gate_drift.details,
                )
                return

            # Gates passées → activation
            self._model_manager.activate_version(
                observer_id=self._OBSERVER_IDS[self._tier],
                version_path=new_model_path,
                tier=self._tier,
                product_id=self._product_id,
            )

            elapsed = round((time.monotonic() - t0) * 1000.0)
            logger.info(
                "TierBackgroundTrainer [%s]: modèle activé '%s' en %dms",
                self._tier.value, Path(new_model_path).name, elapsed,
            )

        except Exception as exc:
            logger.error(
                "TierBackgroundTrainer [%s]: erreur retrain — %s",
                self._tier.value, exc, exc_info=True,
            )
        finally:
            self._is_training.clear()

    # ── Dispatch par Tier ─────────────────────────────────────────────────────

    def _train_for_tier(
        self,
        features:      Any,
        labels:        Any,
        entries:       list[LearningEntry],
    ) -> Optional[Path]:
        """Route vers la méthode de training selon le Tier."""
        if self._tier == TierLevel.MINOR:
            return self._retrain_isoforest(features)
        elif self._tier == TierLevel.MAJOR:
            return self._retrain_color_reference(entries)
        elif self._tier == TierLevel.CRITICAL:
            return self._retrain_yolo(entries)
        return None

    # ── Préparation des données ───────────────────────────────────────────────

    def _prepare_data(
        self,
        entries: list[LearningEntry],
    ) -> tuple[Any, Any, list[float]]:
        """
        Extrait features (float32) et labels depuis les LearningEntry.

        Retourne (features_array, labels_array, recent_scores).
        None si données insuffisantes ou numpy absent.
        """
        try:
            import numpy as np
        except ImportError:
            logger.error("TierBackgroundTrainer: numpy requis pour _prepare_data")
            return None, None, []

        feature_rows = []
        label_list   = []
        recent_scores: list[float] = []

        for entry in entries:
            if entry.tier_verdict is None or not entry.tier_verdict.signals:
                continue

            # Construit un vecteur de features à partir des confidences des signals
            sig_confs = [
                s.confidence
                for s in entry.tier_verdict.signals
                if s.confidence is not None
            ]
            if not sig_confs:
                continue

            row = np.array(sig_confs, dtype=np.float32)
            # Répète le vecteur pondéré par weight (opérateur = ×2)
            reps = max(1, int(entry.weight))
            for _ in range(reps):
                feature_rows.append(row)
                # label : 1=OK (normal), 0=NOK (anomalie)
                label_list.append(1 if entry.verdict == "OK" else 0)

            recent_scores.append(entry.tier_score)

        if not feature_rows:
            return None, None, recent_scores

        # Pad / truncate pour homogénéiser la taille des vecteurs
        max_len = max(len(r) for r in feature_rows)
        padded  = np.zeros((len(feature_rows), max_len), dtype=np.float32)
        for i, row in enumerate(feature_rows):
            padded[i, : len(row)] = row

        return padded, np.array(label_list, dtype=np.int32), recent_scores

    # ── IsolationForest (MINOR) ───────────────────────────────────────────────

    def _retrain_isoforest(self, features: Any) -> Optional[Path]:
        """
        Réentraîne IsolationForest — Tier MINOR.
        Sauvegarde via joblib (.pkl).
        GR-01 : random_state=42.
        """
        try:
            import joblib
            from sklearn.ensemble import IsolationForest
        except ImportError as exc:
            logger.error("TierBackgroundTrainer: sklearn/joblib requis — %s", exc)
            return None

        model = IsolationForest(
            n_estimators=self._n_estimators,
            contamination=self._contamination,
            random_state=42,
            n_jobs=1,
        )
        model.fit(features)

        out_path = self._version_path("surface_isoforest", ".pkl")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, out_path)

        logger.debug(
            "TierBackgroundTrainer [MINOR]: IsolationForest sauvegardé → %s",
            out_path.name,
        )
        return out_path

    # ── KMeans color reference (MAJOR) ────────────────────────────────────────

    def _retrain_color_reference(self, entries: list[LearningEntry]) -> Optional[Path]:
        """
        Réentraîne la référence couleur — Tier MAJOR.
        KMeans sur les features des samples OK uniquement.
        GR-01 : random_state=42.
        """
        try:
            import joblib
            import numpy as np
            from sklearn.cluster import KMeans
        except ImportError as exc:
            logger.error("TierBackgroundTrainer: sklearn/joblib requis — %s", exc)
            return None

        ok_entries = [e for e in entries if e.verdict == "OK"]
        if not ok_entries:
            logger.warning(
                "TierBackgroundTrainer [MAJOR]: aucun sample OK — color reference ignorée"
            )
            return None

        feature_rows = []
        for entry in ok_entries:
            if not entry.tier_verdict or not entry.tier_verdict.signals:
                continue
            row = [
                s.confidence
                for s in entry.tier_verdict.signals
                if s.confidence is not None
            ]
            if row:
                feature_rows.append(row)

        if not feature_rows:
            return None

        max_len = max(len(r) for r in feature_rows)
        X = np.zeros((len(feature_rows), max_len), dtype=np.float32)
        for i, row in enumerate(feature_rows):
            X[i, : len(row)] = row

        k = min(self._kmeans_k, len(X))
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        model.fit(X)

        out_path = self._version_path("color_reference", ".pkl")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, out_path)

        logger.debug(
            "TierBackgroundTrainer [MAJOR]: KMeans(k=%d) sauvegardé → %s",
            k, out_path.name,
        )
        return out_path

    # ── YOLO fine-tune (CRITICAL) ─────────────────────────────────────────────

    def _retrain_yolo(self, entries: list[LearningEntry]) -> Optional[Path]:
        """
        Fine-tune YOLO — Tier CRITICAL.

        Nécessite des annotations dans tier_verdict.signals[*].details["annotation"].
        Si aucune annotation disponible → log WARNING + retourne None.
        Cette méthode est un stub — le fine-tune YOLO réel nécessite
        un environnement GPU dédié hors-pipeline.
        """
        annotated = [
            e for e in entries
            if e.tier_verdict and any(
                s.details.get("annotation") for s in e.tier_verdict.signals
            )
        ]

        if not annotated:
            logger.warning(
                "TierBackgroundTrainer [CRITICAL]: aucune annotation disponible "
                "— fine-tune YOLO ignoré"
            )
            return None

        logger.warning(
            "TierBackgroundTrainer [CRITICAL]: fine-tune YOLO non implémenté "
            "(%d annotations disponibles) — nécessite GPU dédié",
            len(annotated),
        )
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _version_path(self, observer_id: str, suffix: str) -> Path:
        """Génère un chemin versionné basé sur le timestamp (ms)."""
        ts      = int(time.time() * 1000)
        dirname = (
            self._products_root
            / self._product_id
            / _MODELS_SUBDIR
            / _VERSIONS_SUBDIR
            / observer_id
        )
        return dirname / f"{observer_id}_{ts}{suffix}"
