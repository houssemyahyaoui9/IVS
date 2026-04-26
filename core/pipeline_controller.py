"""
SystemController + FSM 9 états — §4
GR-03 : UI → SystemController → Pipeline (jamais direct)
Auto-Switch §35 : possède ProductRegistry + AutoSwitchManager + ProductScanner.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

import numpy as np

from core.auto_switch_manager import AutoSwitchManager
from core.exceptions import SystemStateError
from core.models import SystemSnapshot, SystemState
from core.product_registry import ProductRegistry
from core.product_scanner import BarcodeDecoder, ProductScanner
from core.ui_bridge import UIBridge
from core.watchdog_manager import WatchdogManager

if TYPE_CHECKING:
    from pipeline.pipeline_runner import PipelineRunner

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Table des transitions légales — §4
# ─────────────────────────────────────────────────────────────────────────────

_TRANSITIONS: dict[SystemState, frozenset[SystemState]] = {
    SystemState.IDLE_NO_PRODUCT: frozenset({SystemState.IMAGE_CAPTURE}),
    SystemState.IMAGE_CAPTURE:   frozenset({SystemState.CALIBRATING}),
    SystemState.CALIBRATING:     frozenset({SystemState.TRAINING,   SystemState.ERROR}),
    SystemState.TRAINING:        frozenset({SystemState.IDLE_READY,  SystemState.ERROR}),
    SystemState.IDLE_READY:      frozenset({SystemState.RUNNING,     SystemState.CALIBRATING}),
    SystemState.RUNNING:         frozenset({SystemState.REVIEW,      SystemState.IDLE_READY,
                                            SystemState.ERROR}),
    SystemState.REVIEW:          frozenset({SystemState.RUNNING,     SystemState.IDLE_READY}),
    SystemState.ERROR:           frozenset({SystemState.IDLE_READY}),
    SystemState.SHUTTING_DOWN:   frozenset(),   # état terminal
}


# ─────────────────────────────────────────────────────────────────────────────
#  SystemController
# ─────────────────────────────────────────────────────────────────────────────

class SystemController:
    """
    Contrôleur central du système IVS v7.0.

    Gère la FSM 9 états et sert de seul point d'accès entre UI et Pipeline.
    Toutes les demandes UI passent par ici (GR-03).
    Thread-safe via RLock.
    """

    def __init__(
        self,
        ui_bridge        : UIBridge,
        products_dir     : str | Path = "products",
        scanner_interval_ms : int      = 500,
        scanner_debounce_s  : float    = 3.0,
        watchdog_timeout_s     : float = 60.0,
        watchdog_check_interval_s : float = 30.0,
        watchdog_max_recoveries : int  = 3,
        start_watchdog          : bool = True,
    ) -> None:
        self._ui_bridge        = ui_bridge
        self._state            = SystemState.IDLE_NO_PRODUCT
        self._lock             = threading.RLock()
        self._active_product_id: Optional[str] = None
        self._pipeline_runner : Optional["PipelineRunner"] = None
        self._ok_count         = 0
        self._nok_count        = 0
        self._review_count     = 0

        # Auto-switch §35 — registry + manager créés à l'init,
        # scanner instancié uniquement quand start_scanner() reçoit une frame_source.
        self._product_registry  = ProductRegistry(products_dir)
        self._auto_switch_mgr   = AutoSwitchManager(self, self._product_registry)
        self._scanner           : Optional[ProductScanner] = None
        self._scanner_interval_ms = scanner_interval_ms
        self._scanner_debounce_s  = scanner_debounce_s

        # Watchdog §18.1 — démarré immédiatement (thread daemon).
        self._watchdog = WatchdogManager(
            controller       = self,
            timeout_s        = watchdog_timeout_s,
            check_interval_s = watchdog_check_interval_s,
            max_recoveries   = watchdog_max_recoveries,
        )
        if start_watchdog:
            self._watchdog.start()

    # ── Lecture état ──────────────────────────────────────────────────────────

    def get_state(self) -> SystemState:
        with self._lock:
            return self._state

    @property
    def active_product_id(self) -> Optional[str]:
        with self._lock:
            return self._active_product_id

    # ── Transition FSM ────────────────────────────────────────────────────────

    def transition(self, new_state: SystemState) -> None:
        """
        Effectue une transition FSM.

        Raises:
            SystemStateError : si la transition n'est pas dans le tableau §4.
        """
        with self._lock:
            allowed = _TRANSITIONS.get(self._state, frozenset())
            if new_state not in allowed:
                raise SystemStateError(
                    f"Transition illégale {self._state.value} → {new_state.value}. "
                    f"Autorisées : {[s.value for s in allowed]}"
                )
            old = self._state
            self._state = new_state
            logger.info("FSM %s → %s", old.value, new_state.value)
            self._ui_bridge.state_changed.emit(new_state.value)

    # ── Actions publiques ─────────────────────────────────────────────────────

    def activate_product(self, product_id: str) -> None:
        """
        Définit le produit actif.

        - Depuis IDLE_NO_PRODUCT : transition vers IMAGE_CAPTURE.
        - Depuis IDLE_READY : changement de produit (auto-switch), reste en IDLE_READY
          et émet auto_switch_started.

        Raises:
            SystemStateError : si l'état courant ne permet pas l'activation.
        """
        with self._lock:
            if self._state not in (SystemState.IDLE_NO_PRODUCT, SystemState.IDLE_READY):
                raise SystemStateError(
                    f"activate_product interdit depuis {self._state.value}"
                )
            if not product_id:
                raise ValueError("product_id ne peut pas être vide")

            old_product = self._active_product_id
            self._active_product_id = product_id

            if self._state == SystemState.IDLE_NO_PRODUCT:
                self.transition(SystemState.IMAGE_CAPTURE)
                logger.info("Produit activé : %s", product_id)
            else:
                # Auto-switch depuis IDLE_READY — reste dans IDLE_READY
                logger.info("Auto-switch produit : %s → %s", old_product, product_id)
                self._ui_bridge.auto_switch_started.emit(product_id)

            self._ui_bridge.product_switched.emit(product_id)

    def start_inspection(self) -> None:
        """
        Démarre la boucle d'inspection.
        Transition IDLE_READY → RUNNING.

        Raises:
            SystemStateError : si pas en IDLE_READY.
        """
        with self._lock:
            self.transition(SystemState.RUNNING)
            if self._pipeline_runner is not None:
                self._pipeline_runner.start()

    def stop_inspection(self) -> None:
        """
        Arrête proprement la boucle d'inspection.
        Transition RUNNING ou REVIEW → IDLE_READY.

        Raises:
            SystemStateError : si pas en RUNNING / REVIEW.
        """
        with self._lock:
            if self._state not in (SystemState.RUNNING, SystemState.REVIEW):
                raise SystemStateError(
                    f"stop_inspection interdit depuis {self._state.value}"
                )
            if self._pipeline_runner is not None:
                self._pipeline_runner.request_stop()
            self.transition(SystemState.IDLE_READY)

    def emergency_stop(self) -> None:
        """
        Arrêt d'urgence : force ERROR depuis n'importe quel état non-terminal.
        Ne lève jamais SystemStateError — sécurité absolue.
        """
        with self._lock:
            if self._state == SystemState.SHUTTING_DOWN:
                return
            if self._pipeline_runner is not None:
                self._pipeline_runner.request_stop()
            old = self._state
            self._state = SystemState.ERROR
            logger.warning("emergency_stop depuis %s → ERROR", old.value)
            self._ui_bridge.state_changed.emit(SystemState.ERROR.value)

    def shutdown(self) -> None:
        """
        Arrêt propre du système. État terminal SHUTTING_DOWN.
        Peut être appelé depuis IDLE_READY ou ERROR.
        """
        with self._lock:
            if self._state == SystemState.SHUTTING_DOWN:
                return
            if self._pipeline_runner is not None:
                self._pipeline_runner.request_stop()
            old = self._state
            self._state = SystemState.SHUTTING_DOWN
            logger.info("shutdown depuis %s → SHUTTING_DOWN", old.value)
            self._ui_bridge.state_changed.emit(SystemState.SHUTTING_DOWN.value)

    # ── Intégration pipeline ──────────────────────────────────────────────────

    def set_pipeline_runner(self, runner: "PipelineRunner") -> None:
        """Injecte le PipelineRunner (appelé une seule fois à l'init)."""
        with self._lock:
            self._pipeline_runner = runner

    # ── Callbacks résultat (appelés par PipelineRunner) ───────────────────────

    def on_inspection_result(self, result: object) -> None:
        """
        Appelé par PipelineRunner après chaque FinalResult.
        Met à jour les compteurs et émet les signaux UI.
        """
        from core.models import FinalResult
        if not isinstance(result, FinalResult):
            return
        with self._lock:
            if result.verdict == "NOK":
                self._nok_count += 1
                self._ui_bridge.nok_counter_update.emit(self._nok_count)
            elif result.verdict == "OK":
                self._ok_count += 1
            else:
                self._review_count += 1

            # Si résultat REVIEW → basculer en état REVIEW
            if result.verdict == "REVIEW" and self._state == SystemState.RUNNING:
                self._state = SystemState.REVIEW
                self._ui_bridge.state_changed.emit(SystemState.REVIEW.value)

        self._ui_bridge.inspection_result.emit(result)
        self._emit_snapshot()

    def on_tier_verdict(self, tier_name: str, verdict: object) -> None:
        """Relaye un TierVerdict vers l'UI (émis depuis S4 background aussi)."""
        self._ui_bridge.tier_verdict_ready.emit(tier_name, verdict)

    def on_background_complete(self, result: object) -> None:
        """Relaye le FinalResult complet (background terminé)."""
        self._ui_bridge.background_complete.emit(result)

    def on_luminosity_update(self, lum: object) -> None:
        """Relaye la LuminosityResult vers l'UI."""
        self._ui_bridge.luminosity_update.emit(lum)

    def on_frame_acquired(self, frame: object) -> None:
        """
        Relaye une frame brute (RawFrame ou ndarray) vers l'UI via
        UIBridge.frame_ready. Appelé par PipelineRunner après S1_Acquisition.
        """
        # Accepte soit une RawFrame (avec attribut .image) soit directement un
        # np.ndarray. L'UI gère les deux dans ZoomableGridView.set_frame().
        payload = getattr(frame, "image", frame)
        self._ui_bridge.frame_ready.emit(payload)

    def on_watchdog_triggered(self) -> None:
        """Watchdog pipeline déclenché — passe en ERROR."""
        self.emergency_stop()
        self._ui_bridge.watchdog_triggered.emit()

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def _emit_snapshot(self) -> None:
        snap = SystemSnapshot(
            state=self._state,
            active_product_id=self._active_product_id,
            ok_count=self._ok_count,
            nok_count=self._nok_count,
            review_count=self._review_count,
            timestamp=time.time(),
        )
        self._ui_bridge.system_snapshot.emit(snap)

    # ── Auto-Switch §35 ───────────────────────────────────────────────────────

    @property
    def watchdog(self) -> WatchdogManager:
        return self._watchdog

    @property
    def product_registry(self) -> ProductRegistry:
        return self._product_registry

    @property
    def auto_switch_manager(self) -> AutoSwitchManager:
        return self._auto_switch_mgr

    @property
    def scanner(self) -> Optional[ProductScanner]:
        return self._scanner

    def start_scanner(
        self,
        frame_source : Callable[[], Optional[np.ndarray]],
        decoder      : Optional[BarcodeDecoder] = None,
    ) -> ProductScanner:
        """
        Instancie (si besoin) puis démarre le ProductScanner.
        `frame_source` : callable thread-safe qui renvoie une frame BGR ou None.
        Le scanner s'abonne automatiquement à AutoSwitchManager.handle_scan.
        """
        with self._lock:
            if self._scanner is None:
                self._scanner = ProductScanner(
                    frame_source = frame_source,
                    registry     = self._product_registry,
                    decoder      = decoder,
                    interval_ms  = self._scanner_interval_ms,
                    debounce_s   = self._scanner_debounce_s,
                )
                self._scanner.subscribe(self._auto_switch_mgr.handle_scan)
            self._scanner.start()
            return self._scanner

    def stop_scanner(self) -> None:
        with self._lock:
            if self._scanner is not None:
                self._scanner.stop()
