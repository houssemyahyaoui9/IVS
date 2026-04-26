"""
AIObserver — ABC §6.1
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from core.models import CriterionRule, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel


class AIObserver(ABC):
    """
    Contrat strict pour tous les observers v7.0 — §6.1.

    Un observer observe — il ne décide JAMAIS.
    GR-04 : observe() retourne uniquement ObserverSignal.
    INTERDIT : retourner "OK", "NOK", True/False directement, ou un verdict quelconque.
    """

    @property
    @abstractmethod
    def observer_id(self) -> str:
        """Identifiant unique de l'observer — ex : "sift", "color_de2000"."""
        ...

    @property
    @abstractmethod
    def tier(self) -> TierLevel:
        """Tier d'appartenance — CRITICAL | MAJOR | MINOR."""
        ...

    @abstractmethod
    def observe(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
    ) -> ObserverSignal:
        """
        Observe le frame et retourne un signal structuré.

        GR-04 — règles absolues :
          - Retourner UNIQUEMENT ObserverSignal
          - INTERDIT : retourner "OK", "NOK", True, False, None, dict, str
          - INTERDIT : logique de verdict (if score > threshold: return "OK")
          - GR-11 : jamais None — si échec → ObserverSignal(confidence=0, error_msg=...)

        Args:
            frame       : image BGR uint8 alignée (sortie S3)
            product_def : définition produit (logos, dimensions, ...)
            rule        : règle produit pour cet observer (threshold, enabled, ...)

        Returns:
            ObserverSignal — signal pur sans verdict.
        """
        ...
