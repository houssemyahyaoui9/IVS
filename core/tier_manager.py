"""
TierManager — §5.4
Charge et valide les ProductRules depuis products/{id}/config.json
GR-06 : config chargée une fois, mise en cache, jamais rechargée en boucle
GR-12 : ProductRules immuables — modification interdite pendant RUNNING
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core.exceptions import ConfigValidationError
from core.models import CriterionRule, ProductRules
from core.tier_result import TierLevel

logger = logging.getLogger(__name__)


class TierManager:
    """
    Charge et valide les ProductRules pour un produit — §5.4.

    Méthodes publiques :
      get_rules(product_id)   → ProductRules
      validate_rules(rules)   → bool  (avertissement seul si CRITICAL vide)

    GR-06 : règles mises en cache après le premier chargement.
    GR-12 : ProductRules frozen — aucune modification possible.
    """

    def __init__(self, products_dir: str = "products") -> None:
        self._products_dir = Path(products_dir)
        self._cache: dict[str, ProductRules] = {}

    # ── API publique ──────────────────────────────────────────────────────────

    def get_rules(self, product_id: str) -> ProductRules:
        """
        Retourne les ProductRules pour un produit, depuis le cache ou le disque.

        Raises:
            ConfigValidationError : config.json absent ou structure invalide.
        """
        if product_id in self._cache:
            return self._cache[product_id]

        rules = self._load_rules(product_id)
        self.validate_rules(rules)
        self._cache[product_id] = rules
        logger.info(
            "TierManager: règles chargées pour '%s' — %d critères (%d actifs)",
            product_id,
            len(rules.criteria),
            sum(1 for c in rules.criteria if c.enabled),
        )
        return rules

    def validate_rules(self, rules: ProductRules) -> bool:
        """
        Valide la cohérence des ProductRules.

        - CRITICAL vide → avertissement non bloquant
        - criterion_id dupliqué → ConfigValidationError
        - threshold < 0 → ConfigValidationError

        Returns True si tout est cohérent.
        """
        if not rules.criteria:
            logger.warning(
                "TierManager: aucun critère défini pour '%s'", rules.product_id
            )

        critical_enabled = [c for c in rules.critical_criteria if c.enabled]
        if not critical_enabled:
            logger.warning(
                "TierManager: Tier CRITICAL sans critère actif pour '%s'"
                " — le Tier CRITICAL passera toujours (score=0, passed=True)",
                rules.product_id,
            )

        # Unicité des criterion_id
        seen: set[str] = set()
        for c in rules.criteria:
            if c.criterion_id in seen:
                raise ConfigValidationError(
                    f"TierManager: criterion_id dupliqué '{c.criterion_id}'"
                    f" dans les règles de '{rules.product_id}'"
                )
            seen.add(c.criterion_id)

        # Thresholds valides
        for c in rules.criteria:
            if c.threshold < 0:
                raise ConfigValidationError(
                    f"TierManager: threshold={c.threshold} < 0"
                    f" pour critère '{c.criterion_id}'"
                )

        return True

    # ── Chargement interne ────────────────────────────────────────────────────

    def _load_rules(self, product_id: str) -> ProductRules:
        """Charge config.json et retourne ProductRules."""
        config_path = self._products_dir / product_id / "config.json"

        if not config_path.exists():
            raise ConfigValidationError(
                f"TierManager: config.json absent — {config_path}"
            )

        try:
            with open(config_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise ConfigValidationError(
                f"TierManager: lecture config.json échouée — {config_path}: {exc}"
            ) from exc

        return self._parse_rules(product_id, data)

    def _parse_rules(self, product_id: str, data: dict) -> ProductRules:
        """Parse le dict JSON vers ProductRules."""
        raw_rules    = data.get("product_rules", {})
        raw_criteria = raw_rules.get("criteria", [])

        if not isinstance(raw_criteria, list):
            raise ConfigValidationError(
                f"TierManager: 'product_rules.criteria' doit être une liste"
                f" dans '{product_id}'"
            )

        criteria: list[CriterionRule] = []
        for i, raw in enumerate(raw_criteria):
            try:
                tier_str = raw.get("tier", "")
                try:
                    tier = TierLevel[tier_str]
                except KeyError:
                    raise ConfigValidationError(
                        f"TierManager: tier invalide '{tier_str}'"
                        f" au critère {i} de '{product_id}'"
                    )

                criteria.append(CriterionRule(
                    criterion_id=raw["criterion_id"],
                    label=raw.get("label", raw["criterion_id"]),
                    tier=tier,
                    observer_id=raw["observer_id"],
                    threshold=float(raw["threshold"]),
                    enabled=bool(raw.get("enabled", True)),
                    mandatory=bool(raw.get("mandatory", True)),
                    details=dict(raw.get("details", {})),
                ))
            except ConfigValidationError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise ConfigValidationError(
                    f"TierManager: critère {i} invalide dans '{product_id}': {exc}"
                ) from exc

        return ProductRules(
            product_id=product_id,
            criteria=tuple(criteria),
        )
