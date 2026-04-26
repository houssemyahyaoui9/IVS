"""
tier_result — TS2I IVS v7.0
ObserverSignal · TierVerdict · TierOrchestratorResult
§5.1 · §5.2 — GR-04 : observer observe, jamais verdict
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TierLevel(Enum):
    CRITICAL = "CRITICAL"
    MAJOR    = "MAJOR"
    MINOR    = "MINOR"


@dataclass(frozen=True)
class ObserverSignal:
    """
    Output unique de tout AI Observer — §5.1
    Jamais un verdict, uniquement une observation (GR-04).
    """
    observer_id : str
    tier        : TierLevel
    passed      : bool
    confidence  : float
    value       : float
    threshold   : float
    latency_ms  : float
    details     : dict          = field(default_factory=dict)
    error_msg   : Optional[str] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"ObserverSignal.confidence {self.confidence} hors [0,1]"
            )
        if self.value < 0.0:
            raise ValueError(
                f"ObserverSignal.value {self.value} doit être >= 0"
            )
        if self.latency_ms < 0.0:
            raise ValueError(
                f"ObserverSignal.latency_ms {self.latency_ms} doit être >= 0"
            )
        if not self.observer_id:
            raise ValueError("ObserverSignal.observer_id vide")


@dataclass(frozen=True)
class TierVerdict:
    """
    Verdict d'un Tier produit par RuleEngine — §5.2
    completed=False si background (Fail-Fast).
    """
    tier        : TierLevel
    passed      : bool
    fail_reasons: tuple[str, ...]
    signals     : tuple[ObserverSignal, ...]
    tier_score  : float
    completed   : bool
    latency_ms  : float

    def __post_init__(self) -> None:
        if not (0.0 <= self.tier_score <= 1.0):
            raise ValueError(
                f"TierVerdict.tier_score {self.tier_score} hors [0,1]"
            )
        if self.latency_ms < 0.0:
            raise ValueError(
                f"TierVerdict.latency_ms {self.latency_ms} doit être >= 0"
            )


@dataclass(frozen=True)
class TierOrchestratorResult:
    """
    Résultat de l'orchestration 3-Tiers — §8
    fail_fast=True si CRITICAL a échoué (GR-10).
    major et minor sont None si fail_fast et pas encore complétés.
    """
    critical  : TierVerdict
    major     : Optional[TierVerdict]
    minor     : Optional[TierVerdict]
    fail_fast : bool

    def __post_init__(self) -> None:
        if self.fail_fast and (self.major is None and self.minor is None):
            return  # normal : fail-fast avant MAJOR/MINOR
        # Si pas fail_fast, tous les tiers doivent être présents
        if not self.fail_fast:
            if self.major is None:
                raise ValueError(
                    "TierOrchestratorResult.major requis si fail_fast=False"
                )
            if self.minor is None:
                raise ValueError(
                    "TierOrchestratorResult.minor requis si fail_fast=False"
                )
