"""
TierOrchestrator — Fail-Fast Hybride — §8
GR-10 : CRITICAL fail → verdict NOK immédiat + background Full-Check
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Callable, Optional

from core.models import CriterionRule, ProductDefinition, ProductRules
from core.rule_engine import RuleEngine
from core.tier_result import ObserverSignal, TierLevel, TierOrchestratorResult, TierVerdict
from pipeline.frames import AlignedFrame

if TYPE_CHECKING:
    from core.ai_observer import AIObserver

logger = logging.getLogger(__name__)

_OBSERVER_TIMEOUT_S   = 5.0    # timeout par observer individuel (§8.1)
_BACKGROUND_TIMEOUT_S = 30.0   # timeout global job background (§8.2)
_OBS_MAX_WORKERS      = 4      # threads parallèles par Tier
_BG_MAX_WORKERS       = 2      # threads pool background persistant


# ─────────────────────────────────────────────────────────────────────────────
#  ObserverRegistry
# ─────────────────────────────────────────────────────────────────────────────

class ObserverRegistry:
    """
    Registre des observers par Tier — §8.1.

    Découple TierOrchestrator des listes concrètes d'observers.
    get_for_tier() retourne les observers dans le même ordre que les critères
    de ProductRules pour permettre le zip dans _run_tier_observers.
    """

    def __init__(
        self,
        critical: list["AIObserver"],
        major:    list["AIObserver"],
        minor:    list["AIObserver"],
    ) -> None:
        self._critical = list(critical)
        self._major    = list(major)
        self._minor    = list(minor)

    def get_for_tier(
        self,
        tier:        TierLevel,
        product_def: ProductDefinition,   # réservé pour filtrage produit-spécifique futur
    ) -> list["AIObserver"]:
        """Retourne les observers actifs pour ce Tier."""
        if tier == TierLevel.CRITICAL:
            return self._critical
        elif tier == TierLevel.MAJOR:
            return self._major
        return self._minor


# ─────────────────────────────────────────────────────────────────────────────
#  TierOrchestrator
# ─────────────────────────────────────────────────────────────────────────────

class TierOrchestrator:
    """
    Orchestre les 3 Tiers selon la logique Fail-Fast Hybride — §8.

    Fail-Fast Hybride (GR-10) :
      - CRITICAL toujours dans le thread principal (latence temps-réel)
      - CRITICAL fail → TierOrchestratorResult immédiat + background MAJOR+MINOR
      - MAJOR    fail → TierOrchestratorResult immédiat + background MINOR
      - Tout passe    → pipeline complet dans le thread principal, pas de background

    Observers exécutés en parallèle par Tier (ThreadPoolExecutor, max 4 threads).
    Background via pool dédié persistant (_executor, max 2 threads, §8.2).
    GR-11 : observer timeout / exception → ObserverSignal(confidence=0, error_msg=...).
    """

    def __init__(
        self,
        observer_registry:      ObserverRegistry,
        rule_engine:            RuleEngine,
        on_tier_complete:       Optional[Callable[[str, TierVerdict], None]] = None,
        on_background_complete: Optional[Callable[[str, dict[str, TierVerdict]], None]] = None,
        max_bg_workers:         int = _BG_MAX_WORKERS,
    ) -> None:
        self._observer_registry = observer_registry
        self._rule_engine       = rule_engine
        self._on_tier           = on_tier_complete          # → UIBridge.tier_verdict_ready
        self._on_bg_complete    = on_background_complete    # → DB save + UIBridge.background_complete

        # Pool persistant pour les jobs background (§8.2)
        self._executor = ThreadPoolExecutor(
            max_workers=max_bg_workers,
            thread_name_prefix="TierOrchestrator-BG",
        )
        # Suivi des futures background actifs : frame_id → Future
        self._pending_backgrounds: dict[str, cf.Future] = {}

    @classmethod
    def from_lists(
        cls,
        critical_observers:     list["AIObserver"],
        major_observers:        list["AIObserver"],
        minor_observers:        list["AIObserver"],
        rule_engine:            RuleEngine,
        on_tier_complete:       Optional[Callable[[str, TierVerdict], None]] = None,
        on_background_complete: Optional[Callable[[str, dict[str, TierVerdict]], None]] = None,
    ) -> TierOrchestrator:
        """Factory — construit depuis les trois listes d'observers."""
        registry = ObserverRegistry(critical_observers, major_observers, minor_observers)
        return cls(
            observer_registry=registry,
            rule_engine=rule_engine,
            on_tier_complete=on_tier_complete,
            on_background_complete=on_background_complete,
        )

    def shutdown(self, wait: bool = True) -> None:
        """Arrête proprement le pool background (appelé au shutdown système)."""
        self._executor.shutdown(wait=wait)

    # ── Point d'entrée principal ───────────────────────────────────────────────

    def run(
        self,
        aligned_frame: AlignedFrame,
        product_def:   ProductDefinition,
        product_rules: ProductRules,
    ) -> TierOrchestratorResult:
        """
        Exécute la chaîne 3-Tiers avec logique Fail-Fast Hybride — §8.

        Returns:
            TierOrchestratorResult — major/minor peuvent être None si fail_fast=True.
        """
        # ── CRITICAL (toujours thread principal) ──────────────────────────────
        critical_signals = self._run_tier_observers(
            TierLevel.CRITICAL, aligned_frame, product_def, product_rules
        )
        critical_verdict = self._rule_engine.evaluate_tier(
            TierLevel.CRITICAL, critical_signals, product_rules
        )
        self._notify_tier("CRITICAL", critical_verdict)

        if not critical_verdict.passed:
            # Fail-Fast : verdict NOK immédiat + background MAJOR+MINOR (GR-10)
            bg_future = self._executor.submit(
                self._background_complete,
                aligned_frame, product_def, product_rules,
                True,   # skip_critical
                False,  # skip_major
            )
            self._pending_backgrounds[aligned_frame.frame_id] = bg_future
            logger.info(
                "Fail-Fast CRITICAL: %s → background lancé pour rapport complet",
                critical_verdict.fail_reasons,
            )
            return TierOrchestratorResult(
                critical=critical_verdict,
                major=None,
                minor=None,
                fail_fast=True,
            )

        # ── MAJOR ─────────────────────────────────────────────────────────────
        major_signals = self._run_tier_observers(
            TierLevel.MAJOR, aligned_frame, product_def, product_rules
        )
        major_verdict = self._rule_engine.evaluate_tier(
            TierLevel.MAJOR, major_signals, product_rules
        )
        self._notify_tier("MAJOR", major_verdict)

        if not major_verdict.passed:
            bg_future = self._executor.submit(
                self._background_complete,
                aligned_frame, product_def, product_rules,
                True,   # skip_critical
                True,   # skip_major
            )
            self._pending_backgrounds[aligned_frame.frame_id] = bg_future
            return TierOrchestratorResult(
                critical=critical_verdict,
                major=major_verdict,
                minor=None,
                fail_fast=True,
            )

        # ── MINOR ─────────────────────────────────────────────────────────────
        minor_signals = self._run_tier_observers(
            TierLevel.MINOR, aligned_frame, product_def, product_rules
        )
        minor_verdict = self._rule_engine.evaluate_tier(
            TierLevel.MINOR, minor_signals, product_rules
        )
        self._notify_tier("MINOR", minor_verdict)

        return TierOrchestratorResult(
            critical=critical_verdict,
            major=major_verdict,
            minor=minor_verdict,
            fail_fast=False,
        )

    # ── Background Full-Check ──────────────────────────────────────────────────

    def _background_complete(
        self,
        frame:         AlignedFrame,
        product_def:   ProductDefinition,
        rules:         ProductRules,
        skip_critical: bool = False,
        skip_major:    bool = False,
    ) -> None:
        """
        Complète les Tiers manquants pour le rapport complet — §8.2.

        MINOR toujours exécuté (rapport complet systématique).
        Timeout global 30s — résultats envoyés via on_background_complete.
        """
        t_start = time.monotonic()
        results: dict[str, TierVerdict] = {}

        def _elapsed_ok() -> bool:
            return (time.monotonic() - t_start) < _BACKGROUND_TIMEOUT_S

        try:
            if not skip_critical:
                if not _elapsed_ok():
                    logger.warning("TierOrchestrator BG[%s]: timeout avant CRITICAL", frame.frame_id)
                    return
                sigs = self._run_tier_observers(TierLevel.CRITICAL, frame, product_def, rules)
                results["CRITICAL"] = self._rule_engine.evaluate_tier(
                    TierLevel.CRITICAL, sigs, rules
                )
                self._notify_tier("CRITICAL", results["CRITICAL"])

            if not skip_major:
                if not _elapsed_ok():
                    logger.warning("TierOrchestrator BG[%s]: timeout avant MAJOR", frame.frame_id)
                    return
                sigs = self._run_tier_observers(TierLevel.MAJOR, frame, product_def, rules)
                results["MAJOR"] = self._rule_engine.evaluate_tier(
                    TierLevel.MAJOR, sigs, rules
                )
                self._notify_tier("MAJOR", results["MAJOR"])

            if not _elapsed_ok():
                logger.warning("TierOrchestrator BG[%s]: timeout avant MINOR", frame.frame_id)
                return
            sigs = self._run_tier_observers(TierLevel.MINOR, frame, product_def, rules)
            results["MINOR"] = self._rule_engine.evaluate_tier(
                TierLevel.MINOR, sigs, rules
            )
            self._notify_tier("MINOR", results["MINOR"])

        except Exception:
            logger.exception("TierOrchestrator BG[%s]: erreur non gérée", frame.frame_id)
        finally:
            elapsed_ms = (time.monotonic() - t_start) * 1000.0
            logger.debug("TierOrchestrator BG[%s]: complété en %.1fms", frame.frame_id, elapsed_ms)
            if elapsed_ms > _BACKGROUND_TIMEOUT_S * 1000:
                logger.warning(
                    "TierOrchestrator BG[%s]: dépassement %.1fms (limite %ds)",
                    frame.frame_id, elapsed_ms, _BACKGROUND_TIMEOUT_S,
                )
            # Nettoyer la future du suivi
            self._pending_backgrounds.pop(frame.frame_id, None)
            # Callback → DB save + UIBridge.background_complete
            if self._on_bg_complete is not None and results:
                try:
                    self._on_bg_complete(frame.frame_id, results)
                except Exception:
                    logger.exception(
                        "TierOrchestrator BG[%s]: erreur callback on_background_complete",
                        frame.frame_id,
                    )

    # ── Exécution parallèle des observers d'un Tier ───────────────────────────

    def _run_tier_observers(
        self,
        tier:        TierLevel,
        frame:       AlignedFrame,
        product_def: ProductDefinition,
        rules:       ProductRules,
    ) -> list[ObserverSignal]:
        """
        Lance tous les observers du Tier en parallèle — §8.1.

        Appariement observer ↔ critère par observer_id (robuste).
        Timeout individuel : 5s par observer.
        GR-11 : timeout / exception → ObserverSignal(confidence=0, error_msg=...).
        """
        observers = self._observer_registry.get_for_tier(tier, product_def)
        criteria  = rules.criteria_for_tier(tier)

        # Appariement robuste par observer_id (résiste aux désalignements)
        crit_by_obs: dict[str, CriterionRule] = {
            c.observer_id: c for c in criteria if c.enabled
        }
        pairs: list[tuple[AIObserver, CriterionRule]] = [
            (obs, crit_by_obs[obs.observer_id])
            for obs in observers
            if obs.observer_id in crit_by_obs
        ]

        if not pairs:
            return []

        # Exécution parallèle via pool temporaire
        pool = ThreadPoolExecutor(
            max_workers=_OBS_MAX_WORKERS,
            thread_name_prefix=f"TierObs-{tier.value}",
        )
        future_to_pair: dict[cf.Future, tuple[AIObserver, CriterionRule]] = {
            pool.submit(obs.observe, frame.image, product_def, crit): (obs, crit)
            for obs, crit in pairs
        }

        done, not_done = cf.wait(future_to_pair.keys(), timeout=_OBSERVER_TIMEOUT_S)
        pool.shutdown(wait=False)   # ne pas bloquer — les futures restantes finissent en BG

        signals: list[ObserverSignal] = []
        for future, (obs, crit) in future_to_pair.items():
            if future in not_done:
                logger.error(
                    "TierOrchestrator: observer '%s' timeout %.1fs (Tier %s)",
                    obs.observer_id, _OBSERVER_TIMEOUT_S, tier.value,
                )
                signals.append(ObserverSignal(
                    observer_id=obs.observer_id,
                    tier=tier,
                    passed=False,
                    confidence=0.0,
                    value=0.0,
                    threshold=crit.threshold,
                    latency_ms=_OBSERVER_TIMEOUT_S * 1000.0,
                    error_msg=f"observer timeout {_OBSERVER_TIMEOUT_S}s",
                ))
            else:
                try:
                    sig = future.result()
                    if sig is None:
                        # GR-11 : observer ne peut pas retourner None
                        raise ValueError(
                            f"observer '{obs.observer_id}' retourné None — violation GR-11"
                        )
                    signals.append(sig)
                except Exception as exc:
                    logger.error(
                        "TierOrchestrator: observer '%s' exception — %s",
                        obs.observer_id, exc,
                    )
                    signals.append(ObserverSignal(
                        observer_id=obs.observer_id,
                        tier=tier,
                        passed=False,
                        confidence=0.0,
                        value=0.0,
                        threshold=crit.threshold,
                        latency_ms=0.0,
                        error_msg=str(exc),
                    ))

        return signals

    # ── Helper ────────────────────────────────────────────────────────────────

    def _notify_tier(self, tier_name: str, verdict: TierVerdict) -> None:
        if self._on_tier is not None:
            try:
                self._on_tier(tier_name, verdict)
            except Exception:
                logger.exception(
                    "TierOrchestrator: erreur callback on_tier_complete '%s'", tier_name
                )
