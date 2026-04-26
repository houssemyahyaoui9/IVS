"""
ProductRegistry — §35
Index barcode → product_id, construit en scannant products/<id>/config.json.
Rechargé via reload() si un nouveau produit est ajouté.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProductRegistry:
    """
    Index thread-safe barcode → product_id pour l'auto-switch.

    Un produit n'est indexé que si son config.json contient :
      - "auto_switch_enabled": true
      - "product_barcode": "<code non vide>"

    Les autres produits restent connus de la registry (`has_product`)
    mais ne déclenchent pas de bascule automatique.
    """

    def __init__(self, products_dir: str | Path = "products") -> None:
        self._dir          = Path(products_dir)
        self._lock         = threading.RLock()
        self._index        : dict[str, str] = {}   # barcode → product_id
        self._product_ids  : set[str]       = set()
        self.reload()

    # ── Reload ────────────────────────────────────────────────────────────────

    def reload(self) -> int:
        """
        Rescanne le répertoire products/ et reconstruit l'index.
        Retourne le nombre de barcodes indexés.
        """
        new_index : dict[str, str] = {}
        new_ids   : set[str]       = set()

        if not self._dir.exists():
            logger.warning("ProductRegistry: répertoire %s inexistant", self._dir)
            with self._lock:
                self._index       = new_index
                self._product_ids = new_ids
            return 0

        for product_dir in sorted(self._dir.iterdir()):
            if not product_dir.is_dir():
                continue
            config_file = product_dir / "config.json"
            if not config_file.exists():
                continue
            try:
                with config_file.open(encoding="utf-8") as fh:
                    cfg = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error(
                    "ProductRegistry: lecture %s échouée — %s", config_file, exc,
                )
                continue

            product_id = cfg.get("product_id") or product_dir.name
            new_ids.add(product_id)

            if not cfg.get("auto_switch_enabled", False):
                continue
            barcode = (cfg.get("product_barcode") or "").strip()
            if not barcode:
                continue
            existing = new_index.get(barcode)
            if existing is not None and existing != product_id:
                logger.warning(
                    "ProductRegistry: barcode '%s' dupliqué — '%s' écrase '%s'",
                    barcode, product_id, existing,
                )
            new_index[barcode] = product_id

        with self._lock:
            self._index       = new_index
            self._product_ids = new_ids
        logger.info(
            "ProductRegistry: %d barcodes indexés sur %d produits",
            len(new_index), len(new_ids),
        )
        return len(new_index)

    # ── Lookup ────────────────────────────────────────────────────────────────

    def lookup(self, barcode: str) -> Optional[str]:
        """Retourne le product_id associé au barcode, ou None si inconnu."""
        if not barcode:
            return None
        key = barcode.strip()
        with self._lock:
            return self._index.get(key)

    def has_product(self, product_id: str) -> bool:
        """True si product_id existe sous products/ (auto-switch ou non)."""
        with self._lock:
            return product_id in self._product_ids

    @property
    def product_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._product_ids))

    @property
    def barcodes(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._index.keys()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._index)

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"ProductRegistry(dir={self._dir!r}, "
                f"products={len(self._product_ids)}, "
                f"indexed={len(self._index)})"
            )
