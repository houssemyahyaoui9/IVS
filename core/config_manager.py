"""
config_manager — TS2I IVS v7.0
Config chargée UNE SEULE FOIS au démarrage — GR-06
Jamais rechargée dans la boucle d'inspection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigManager:
    """
    Accès à config.yaml via notation pointée.
    GR-06 : load() idempotent — appels ultérieurs ignorés.
    """

    def __init__(self, config_path: str | Path = "config/config.yaml") -> None:
        self._path   = Path(config_path)
        self._data   : dict[str, Any] = {}
        self._loaded : bool = False

    # ── chargement ────────────────────────────────────────────────────────────

    def load(self) -> "ConfigManager":
        """Charge le fichier YAML une fois. Re-appel silencieusement ignoré."""
        if self._loaded:
            return self
        if not self._path.exists():
            raise FileNotFoundError(f"config.yaml introuvable : {self._path}")
        with self._path.open(encoding="utf-8") as fh:
            self._data = yaml.safe_load(fh) or {}
        self._loaded = True
        return self

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ── accès clé pointée ─────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        Accès avec notation pointée.
        Ex : config.get("camera.type", "fake")
            config.get("tier_engine.critical_confidence_min", 0.80)
        """
        node: Any = self._data
        for part in key.split("."):
            if not isinstance(node, dict):
                return default
            node = node.get(part)
            if node is None:
                return default
        return node

    def require(self, key: str) -> Any:
        """Comme get() mais lève KeyError si absent."""
        value = self.get(key)
        if value is None:
            raise KeyError(f"Clé config manquante : '{key}'")
        return value

    # ── propriétés de premier niveau ──────────────────────────────────────────

    @property
    def deployment_mode(self) -> str:
        return self.get("deployment_mode", "DEV")

    @property
    def station_id(self) -> str:
        return self.get("station_id", "STATION-001")

    def __repr__(self) -> str:
        return (
            f"ConfigManager(path={self._path!r}, "
            f"loaded={self._loaded}, "
            f"mode={self.deployment_mode!r})"
        )


# ── Singleton module-level (GR-06) ────────────────────────────────────────────

_singleton: ConfigManager | None = None


def get_config(path: str | Path = "config/config.yaml") -> ConfigManager:
    """
    Retourne le ConfigManager singleton.
    Premier appel charge le fichier. Appels suivants retournent la même instance.
    GR-06 : jamais recharger dans la boucle.
    """
    global _singleton
    if _singleton is None:
        _singleton = ConfigManager(path).load()
    return _singleton


def reset_config() -> None:
    """Réinitialise le singleton — usage TESTS uniquement."""
    global _singleton
    _singleton = None
