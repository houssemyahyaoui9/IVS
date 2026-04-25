"""
DatasetManager — gestion dataset per-Tier versioning + backup
§11 Apprentissage Autonome v7.0
GR-09 : aucun entraînement ici — uniquement stockage + lecture features
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np

from ai.feature_extractor import FEATURE_DIM, FeatureExtractor
from core.tier_result import TierLevel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Types
# ─────────────────────────────────────────────────────────────────────────────

class SampleLabel(str, Enum):
    GOOD    = "GOOD"
    BAD     = "BAD"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DatasetStats:
    """Statistiques d'un slot (label, tier, product_id)."""
    product_id : str
    tier       : TierLevel
    label      : SampleLabel
    count      : int
    version    : int
    dataset_dir: Path


# ─────────────────────────────────────────────────────────────────────────────
#  DatasetManager
# ─────────────────────────────────────────────────────────────────────────────

class DatasetManager:
    """
    Stockage et lecture des features par produit, Tier et label.

    Structure sur disque :
        products/{product_id}/dataset/{LABEL}/{TIER}/
            features.npy       ← (N, 256) float32, écriture atomique
            metadata.jsonl     ← une ligne JSON par sample
            version.json       ← {"version": N, "count": N}

    Thread-safe via RLock global (hypothèse mono-processus).
    GR-09 : aucun entraînement — uniquement I/O features.
    """

    _FEATURES_FILE  = "features.npy"
    _METADATA_FILE  = "metadata.jsonl"
    _VERSION_FILE   = "version.json"
    _BACKUP_PREFIX  = "features_v"

    def __init__(
        self,
        products_root:     Path = Path("products"),
        feature_extractor: Optional[FeatureExtractor] = None,
    ) -> None:
        self._root      = Path(products_root)
        self._extractor = feature_extractor or FeatureExtractor()
        self._lock      = threading.RLock()

    # ── Écriture ─────────────────────────────────────────────────────────────

    def add_sample(
        self,
        frame:      np.ndarray,
        label:      SampleLabel | str,
        tier:       TierLevel,
        product_id: str,
    ) -> None:
        """
        Extrait les features de frame et les ajoute au dataset.

        Args:
            frame      : image BGR uint8 (toute résolution)
            label      : "GOOD" | "BAD" | "UNKNOWN" ou SampleLabel
            tier       : TierLevel.CRITICAL | MAJOR | MINOR
            product_id : identifiant produit

        Raises:
            ValueError : si label invalide
        """
        label = SampleLabel(label)   # valide ou ValueError
        feat  = self._extractor.extract(frame)   # (256,) float32

        with self._lock:
            slot_dir = self._slot_dir(product_id, label, tier)
            slot_dir.mkdir(parents=True, exist_ok=True)

            # Charger features existantes + append
            existing = self._load_features_unsafe(slot_dir)     # (N, 256) ou (0, 256)
            updated  = np.vstack([existing, feat[np.newaxis, :]]) if len(existing) else \
                       feat[np.newaxis, :]                       # (N+1, 256)

            # Écriture atomique (tmp → rename)
            self._save_features_atomic(slot_dir, updated)

            # Metadata JSONL
            meta = {
                "timestamp":  time.time(),
                "tier":       tier.value,
                "label":      label.value,
                "product_id": product_id,
                "version":    self._read_version(slot_dir) + 1,
            }
            with open(slot_dir / self._METADATA_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(meta, ensure_ascii=False) + "\n")

            # Incrémenter version
            self._write_version(slot_dir, len(updated))

        logger.debug("DatasetManager: +1 %s/%s/%s → count=%d",
                     product_id, tier.value, label.value, len(updated))

    # ── Lecture ───────────────────────────────────────────────────────────────

    def get_features(
        self,
        label:      SampleLabel | str,
        tier:       TierLevel,
        product_id: str,
    ) -> np.ndarray:
        """
        Retourne toutes les features (N, 256) float32 pour le slot.

        Returns:
            np.ndarray (N, 256) float32.
            Tableau vide (0, 256) si aucun sample disponible.
        """
        label    = SampleLabel(label)
        slot_dir = self._slot_dir(product_id, label, tier)

        with self._lock:
            return self._load_features_unsafe(slot_dir)

    def get_count(
        self,
        label:      SampleLabel | str,
        tier:       TierLevel,
        product_id: str,
    ) -> int:
        """Nombre de samples dans le slot."""
        label    = SampleLabel(label)
        slot_dir = self._slot_dir(product_id, label, tier)
        with self._lock:
            return self._read_version(slot_dir)

    def get_stats(
        self,
        label:      SampleLabel | str,
        tier:       TierLevel,
        product_id: str,
    ) -> DatasetStats:
        """Retourne les statistiques du slot."""
        label    = SampleLabel(label)
        slot_dir = self._slot_dir(product_id, label, tier)
        with self._lock:
            count   = len(self._load_features_unsafe(slot_dir))
            version = self._read_version_meta(slot_dir).get("version", 0)
        return DatasetStats(
            product_id=product_id,
            tier=tier,
            label=label,
            count=count,
            version=version,
            dataset_dir=slot_dir,
        )

    def get_all_stats(self, product_id: str) -> list[DatasetStats]:
        """Retourne les stats de tous les slots d'un produit."""
        result = []
        for label in SampleLabel:
            for tier in TierLevel:
                stats = self.get_stats(label, tier, product_id)
                if stats.count > 0:
                    result.append(stats)
        return result

    # ── Backup avant retrain ──────────────────────────────────────────────────

    def backup(
        self,
        label:      SampleLabel | str,
        tier:       TierLevel,
        product_id: str,
    ) -> Optional[Path]:
        """
        Copie features.npy en features_v{N}.npy (backup avant retrain).

        Returns:
            Path vers le backup, ou None si aucun features.npy existant.
        """
        label    = SampleLabel(label)
        slot_dir = self._slot_dir(product_id, label, tier)
        src      = slot_dir / self._FEATURES_FILE

        with self._lock:
            if not src.exists():
                logger.debug("DatasetManager backup: %s absent — skip", src)
                return None

            meta    = self._read_version_meta(slot_dir)
            version = meta.get("version", 0)
            dst     = slot_dir / f"{self._BACKUP_PREFIX}{version}.npy"
            shutil.copy2(src, dst)
            logger.info("DatasetManager backup: %s → %s", src.name, dst.name)
            return dst

    def backup_tier(
        self,
        tier:       TierLevel,
        product_id: str,
    ) -> list[Path]:
        """Backup tous les labels d'un Tier (appelé par BackgroundTrainer)."""
        paths = []
        for label in SampleLabel:
            p = self.backup(label, tier, product_id)
            if p is not None:
                paths.append(p)
        return paths

    def list_backups(
        self,
        label:      SampleLabel | str,
        tier:       TierLevel,
        product_id: str,
    ) -> list[Path]:
        """Liste les backups disponibles dans l'ordre chronologique."""
        label    = SampleLabel(label)
        slot_dir = self._slot_dir(product_id, label, tier)
        if not slot_dir.exists():
            return []
        backups = sorted(slot_dir.glob(f"{self._BACKUP_PREFIX}*.npy"))
        return backups

    # ── Helpers I/O ───────────────────────────────────────────────────────────

    def _slot_dir(
        self, product_id: str, label: SampleLabel, tier: TierLevel
    ) -> Path:
        """Chemin : products/{product_id}/dataset/{LABEL}/{TIER}/"""
        return self._root / product_id / "dataset" / label.value / tier.value

    def _load_features_unsafe(self, slot_dir: Path) -> np.ndarray:
        """Charge features.npy. Retourne (0, 256) si absent. Pas de lock."""
        path = slot_dir / self._FEATURES_FILE
        if not path.exists():
            return np.empty((0, FEATURE_DIM), dtype=np.float32)
        arr = np.load(path)
        if arr.ndim == 1:
            arr = arr[np.newaxis, :]   # compat single-row sauvegardé à plat
        return arr.astype(np.float32)

    @staticmethod
    def _save_features_atomic(slot_dir: Path, arr: np.ndarray) -> None:
        """Écriture atomique : tmp.npy → rename pour éviter la corruption.
        np.save ajoute automatiquement .npy → le tmp doit déjà se terminer par .npy."""
        final = slot_dir / DatasetManager._FEATURES_FILE
        tmp   = slot_dir / "features.tmp.npy"
        np.save(tmp, arr)
        os.replace(tmp, final)   # atomique sur Linux/Windows

    def _read_version_meta(self, slot_dir: Path) -> dict:
        path = slot_dir / self._VERSION_FILE
        if not path.exists():
            return {"version": 0, "count": 0}
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def _read_version(self, slot_dir: Path) -> int:
        return self._read_version_meta(slot_dir).get("count", 0)

    def _write_version(self, slot_dir: Path, count: int) -> None:
        meta = self._read_version_meta(slot_dir)
        meta["version"] = meta.get("version", 0) + 1
        meta["count"]   = count
        path = slot_dir / self._VERSION_FILE
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
