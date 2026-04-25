"""
ModelVersionManager rollback per-Tier — §11.4
Symlinks active/ + registry JSON pour rollback < 1 s.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from core.tier_result import TierLevel

logger = logging.getLogger(__name__)

_REGISTRY_FILE = "version_registry.json"
_ACTIVE_DIR    = "active"


class ModelVersionManager:
    """
    Gestion des versions actives de modèles par observer.

    Structure sur disque :
        products/{product_id}/models/
            active/
                {observer_id} → symlink vers le fichier modèle actif
            version_registry.json
                {"surface": {"tier": "MINOR", "active": "/abs/path", "previous": "/abs/path"}}

    Thread-safe via RLock.
    Durée rollback < 1 s (symlinks — §11.4).
    """

    def __init__(
        self,
        products_root: Path = Path("products"),
        product_id:    str  = "",
    ) -> None:
        self._root       = Path(products_root)
        self._product_id = product_id
        self._lock       = threading.RLock()

    # ── Activation ────────────────────────────────────────────────────────────

    def activate_version(
        self,
        observer_id:  str,
        version_path: Path,
        tier:         Optional[TierLevel] = None,
        product_id:   str                 = "",
    ) -> None:
        """
        Active version_path pour observer_id en créant/mettant à jour le symlink.

        Sauvegarde l'ancienne version active comme "previous" pour rollback.

        Args:
            observer_id  : identifiant de l'observer ("sift", "surface", ...)
            version_path : chemin absolu ou relatif vers le nouveau fichier modèle
            tier         : TierLevel optionnel — stocké dans le registre pour rollback
            product_id   : override produit (utilise self._product_id si vide)
        """
        pid      = product_id or self._product_id
        abs_path = Path(version_path).resolve()

        with self._lock:
            active_dir = self._active_dir(pid)
            active_dir.mkdir(parents=True, exist_ok=True)

            link = active_dir / observer_id

            registry = self._read_registry(pid)
            entry    = registry.get(observer_id, {})

            # Sauvegarder l'actuel comme previous avant de remplacer
            if link.is_symlink():
                entry["previous"] = str(link.resolve())
            elif "active" in entry:
                entry["previous"] = entry["active"]

            # Supprimer l'ancien symlink
            if link.is_symlink() or link.exists():
                link.unlink()

            # Créer le nouveau symlink
            link.symlink_to(abs_path)

            # Mettre à jour le registre
            entry["active"] = str(abs_path)
            if tier is not None:
                entry["tier"] = tier.value
            registry[observer_id] = entry

            self._write_registry(pid, registry)

        logger.info(
            "ModelVersionManager: '%s' activé → %s",
            observer_id, abs_path.name,
        )

    # ── Rollback ──────────────────────────────────────────────────────────────

    def rollback_tier(
        self,
        tier:       TierLevel,
        product_id: str = "",
    ) -> None:
        """
        Rollback tous les observers du tier donné vers leur version précédente.

        Swaps symlinks active ↔ previous pour chaque observer du tier.
        Durée < 1 s (§11.4) : opérations symlink uniquement.

        Args:
            tier       : Tier à rollback (CRITICAL | MAJOR | MINOR)
            product_id : override produit
        """
        pid = product_id or self._product_id

        with self._lock:
            registry = self._read_registry(pid)
            active_dir = self._active_dir(pid)

            # Filtrer les observers appartenant au tier
            observers_in_tier = [
                obs_id
                for obs_id, entry in registry.items()
                if entry.get("tier") == tier.value
            ]

            if not observers_in_tier:
                logger.warning(
                    "ModelVersionManager: aucun observer enregistré pour tier=%s "
                    "(avez-vous appelé activate_version avec tier= ?)",
                    tier.value,
                )
                return

            for obs_id in observers_in_tier:
                entry    = registry[obs_id]
                v_active = entry.get("active")
                v_prev   = entry.get("previous")

                if not v_prev:
                    logger.warning(
                        "ModelVersionManager: rollback '%s' — pas de version précédente",
                        obs_id,
                    )
                    continue

                link = active_dir / obs_id

                # Swap symlink
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(v_prev)

                # Swap dans le registre
                entry["active"]   = v_prev
                entry["previous"] = v_active
                registry[obs_id]  = entry

                logger.info(
                    "ModelVersionManager: Rollback Tier %s — '%s' : %s → %s",
                    tier.value,
                    obs_id,
                    Path(v_active).name if v_active else "?",
                    Path(v_prev).name,
                )

            self._write_registry(pid, registry)

    # ── Lecture ───────────────────────────────────────────────────────────────

    def get_active_path(
        self,
        observer_id: str,
        product_id:  str = "",
    ) -> Optional[Path]:
        """
        Retourne le chemin résolu du modèle actif pour observer_id.
        Retourne None si aucun symlink actif.
        """
        pid  = product_id or self._product_id
        link = self._active_dir(pid) / observer_id

        with self._lock:
            if link.is_symlink():
                return link.resolve()
            return None

    def get_registry(self, product_id: str = "") -> dict:
        """Retourne une copie du registre de versions pour le produit."""
        pid = product_id or self._product_id
        with self._lock:
            return dict(self._read_registry(pid))

    def list_observers(
        self,
        tier:       Optional[TierLevel] = None,
        product_id: str                 = "",
    ) -> list[str]:
        """Liste les observer_ids enregistrés, filtrés par tier si fourni."""
        pid      = product_id or self._product_id
        registry = self._read_registry(pid)
        if tier is None:
            return list(registry.keys())
        return [
            obs_id
            for obs_id, entry in registry.items()
            if entry.get("tier") == tier.value
        ]

    # ── Helpers I/O ───────────────────────────────────────────────────────────

    def _active_dir(self, product_id: str) -> Path:
        return self._root / product_id / "models" / _ACTIVE_DIR

    def _registry_path(self, product_id: str) -> Path:
        return self._root / product_id / "models" / _REGISTRY_FILE

    def _read_registry(self, product_id: str) -> dict:
        path = self._registry_path(product_id)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("ModelVersionManager: registre illisible %s — %s", path, exc)
            return {}

    def _write_registry(self, product_id: str, data: dict) -> None:
        path = self._registry_path(product_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
