"""
spc_service — Statistiques SPC par Tier v7.0 — §19
Cp/Cpk · X-bar/R · distribution fails par Tier.

L'accès BDD est injecté via un Protocol (DatabaseProto) — découple le
service de l'implémentation SQLite (storage/database.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import numpy as np

from ts2i_ivs.core.tier_result import TierLevel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Dataclasses résultat
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TierStats:
    """Statistiques SPC d'un Tier — §19."""
    tier        : TierLevel
    samples     : int
    mean        : float
    std         : float
    cp          : float
    cpk         : float
    xbar        : tuple[float, ...]   # X-bar par sous-groupe de 5
    r           : tuple[float, ...]   # range par sous-groupe
    ucl_xbar    : float
    lcl_xbar    : float
    fail_count  : int


@dataclass(frozen=True)
class SpcResult:
    """Résultat global SPC sur N inspections — §19."""
    product_id        : str
    total             : int
    ok_count          : int
    nok_count         : int
    review_count      : int
    tier_stats        : dict[str, TierStats]   # "CRITICAL" | "MAJOR" | "MINOR"
    fail_distribution : dict[str, int]         # idem
    period_hours      : Optional[float] = None
    generated_at      : float           = field(default_factory=lambda: __import__("time").time())

    @property
    def conformity_rate(self) -> float:
        """Taux de conformité OK / total."""
        if self.total == 0:
            return 0.0
        return self.ok_count / self.total


# ─────────────────────────────────────────────────────────────────────────────
#  Protocol DB
# ─────────────────────────────────────────────────────────────────────────────

class DatabaseProto(Protocol):
    def get_history(self, limit: int, product_id: Optional[str]) -> list[Any]: ...


# ─────────────────────────────────────────────────────────────────────────────
#  Seuils par défaut (config.tier_engine.*_confidence_min — §21)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TIER_THRESHOLDS: dict[TierLevel, float] = {
    TierLevel.CRITICAL: 0.80,
    TierLevel.MAJOR:    0.70,
    TierLevel.MINOR:    0.60,
}

_TIER_KEYS: tuple[str, ...] = ("CRITICAL", "MAJOR", "MINOR")
_EPS: float = 1e-9


# ─────────────────────────────────────────────────────────────────────────────
#  SpcService
# ─────────────────────────────────────────────────────────────────────────────

class SpcService:
    """
    Calcule les indicateurs SPC v7.0 par Tier — §19.

    GR-08 : ne modifie jamais l'état du système, lecture seule.
    """

    def __init__(
        self,
        database         : DatabaseProto,
        tier_thresholds  : Optional[dict[TierLevel, float]] = None,
        subgroup_size    : int = 5,
        usl              : float = 1.0,
    ) -> None:
        self._db        = database
        self._thresh    = dict(tier_thresholds or DEFAULT_TIER_THRESHOLDS)
        self._n_sg      = max(2, int(subgroup_size))
        self._usl       = float(usl)

    # ── API publique ─────────────────────────────────────────────────────────

    def threshold_for_tier(self, tier: TierLevel) -> float:
        return float(self._thresh.get(tier, 0.60))

    def compute_spc(
        self,
        product_id : str,
        n          : int            = 100,
        period_hours: Optional[float] = None,
    ) -> SpcResult:
        """
        Calcule SpcResult sur les `n` derniers FinalResult du produit donné.
        """
        results = list(self._db.get_history(limit=n, product_id=product_id) or [])
        return self._compute_from_results(
            results=results,
            product_id=product_id,
            n=n,
            period_hours=period_hours,
        )

    def get_metrics(self, product_id: Optional[str] = None) -> dict:
        """Forme compacte pour l'API web `/api/v1/spc` — §21 web."""
        result = self.compute_spc(product_id=product_id or "", n=100)
        return {
            "cp"      : _safe_mean([s.cp  for s in result.tier_stats.values()]),
            "cpk"     : _safe_mean([s.cpk for s in result.tier_stats.values()]),
            "tier_cp" : {k: s.cp for k, s in result.tier_stats.items()},
            "samples" : result.total,
        }

    # ── Calculs internes ─────────────────────────────────────────────────────

    def _compute_from_results(
        self,
        results     : list[Any],
        product_id  : str,
        n           : int,
        period_hours: Optional[float] = None,
    ) -> SpcResult:
        ok    = sum(1 for r in results if _verdict_of(r) == "OK")
        nok   = sum(1 for r in results if _verdict_of(r) == "NOK")
        rev   = sum(1 for r in results if _verdict_of(r) == "REVIEW")

        # Extraction tier_scores : {CRITICAL: [...], MAJOR: [...], MINOR: [...]}
        scores_by_tier: dict[str, list[float]] = {k: [] for k in _TIER_KEYS}
        for r in results:
            tier_scores = getattr(r, "tier_scores", {}) or {}
            for k in _TIER_KEYS:
                v = tier_scores.get(k)
                if v is None:
                    continue
                try:
                    scores_by_tier[k].append(float(v))
                except (TypeError, ValueError):
                    continue

        # Distribution fails par Tier
        fail_distribution: dict[str, int] = {k: 0 for k in _TIER_KEYS}
        for r in results:
            ft = getattr(r, "fail_tier", None)
            ft_name = ft.value if hasattr(ft, "value") else ft
            if ft_name in fail_distribution:
                fail_distribution[ft_name] += 1

        # Stats par Tier
        tier_stats: dict[str, TierStats] = {}
        for tier in (TierLevel.CRITICAL, TierLevel.MAJOR, TierLevel.MINOR):
            key    = tier.value
            scores = scores_by_tier[key]
            tier_stats[key] = self._compute_tier_stats(
                tier        = tier,
                scores      = scores,
                fail_count  = fail_distribution[key],
            )

        return SpcResult(
            product_id        = product_id,
            total             = len(results),
            ok_count          = ok,
            nok_count         = nok,
            review_count      = rev,
            tier_stats        = tier_stats,
            fail_distribution = fail_distribution,
            period_hours      = period_hours,
        )

    def _compute_tier_stats(
        self,
        tier       : TierLevel,
        scores     : list[float],
        fail_count : int,
    ) -> TierStats:
        if not scores:
            return TierStats(
                tier=tier, samples=0, mean=0.0, std=0.0,
                cp=0.0, cpk=0.0, xbar=(), r=(),
                ucl_xbar=0.0, lcl_xbar=0.0, fail_count=fail_count,
            )

        arr   = np.asarray(scores, dtype=float)
        mean  = float(np.mean(arr))
        std   = float(np.std(arr))
        usl   = self._usl
        lsl   = self.threshold_for_tier(tier)

        cp  = (usl - lsl) / (6.0 * std + _EPS)
        cpk = float(min(
            (usl  - mean) / (3.0 * std + _EPS),
            (mean - lsl ) / (3.0 * std + _EPS),
        ))

        # X-bar / R par sous-groupes de size n_sg
        n_sg      = self._n_sg
        subgroups = [
            arr[i:i + n_sg] for i in range(0, len(arr), n_sg)
            if len(arr[i:i + n_sg]) == n_sg
        ]
        if subgroups:
            xbar = tuple(float(np.mean(sg))             for sg in subgroups)
            r    = tuple(float(np.max(sg) - np.min(sg)) for sg in subgroups)
            xbar_arr = np.asarray(xbar, dtype=float)
            xbar_mean = float(np.mean(xbar_arr))
            xbar_std  = float(np.std(xbar_arr))
            ucl_xbar  = xbar_mean + 3.0 * (xbar_std + _EPS)
            lcl_xbar  = xbar_mean - 3.0 * (xbar_std + _EPS)
        else:
            xbar = ()
            r    = ()
            ucl_xbar = 0.0
            lcl_xbar = 0.0

        return TierStats(
            tier        = tier,
            samples     = len(arr),
            mean        = mean,
            std         = std,
            cp          = float(cp),
            cpk         = cpk,
            xbar        = xbar,
            r           = r,
            ucl_xbar    = ucl_xbar,
            lcl_xbar    = lcl_xbar,
            fail_count  = fail_count,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _verdict_of(r: Any) -> Optional[str]:
    v = getattr(r, "verdict", None)
    return v.value if hasattr(v, "value") else v


def _safe_mean(xs: list[float]) -> float:
    return float(np.mean(xs)) if xs else 0.0
