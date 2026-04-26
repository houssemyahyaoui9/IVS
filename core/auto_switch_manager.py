"""
AutoSwitchManager — §35
Reçoit un product_id détecté par ProductScanner et arbitre la bascule
selon l'état FSM courant (SystemController).

Politique :
  IDLE_NO_PRODUCT / IDLE_READY → activate_product() direct       → SUCCESS
  RUNNING / REVIEW             → stop_inspection + wait + switch → SUCCESS (< 3s)
  TRAINING                     → refus + log WARNING             → FAILED
  CALIBRATING                  → refus + log WARNING             → FAILED
  IMAGE_CAPTURE / ERROR / SHUTTING_DOWN → refus                  → FAILED
  Produit déjà actif           → ALREADY_ACTIVE
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from core.exceptions import SystemStateError
from core.models import SwitchResult, SystemState
from core.product_registry import ProductRegistry

if TYPE_CHECKING:
    from core.pipeline_controller import SystemController

logger = logging.getLogger(__name__)

_STOP_TIMEOUT_S = 3.0
_STOP_POLL_S    = 0.05

_REFUSAL_STATES = frozenset({
    SystemState.TRAINING,
    SystemState.CALIBRATING,
    SystemState.IMAGE_CAPTURE,
    SystemState.ERROR,
    SystemState.SHUTTING_DOWN,
})

_STOP_FIRST_STATES = frozenset({
    SystemState.RUNNING,
    SystemState.REVIEW,
})


class AutoSwitchManager:
    """
    Orchestrateur de bascule produit déclenchée par scan.

    Brancher en abonnant `handle_scan` au signal product_detected
    de `ProductScanner` :
        scanner.subscribe(auto_switch_manager.handle_scan)

    Sérialise les bascules concurrentes via un RLock interne.
    """

    def __init__(
        self,
        controller : "SystemController",
        registry   : ProductRegistry,
    ) -> None:
        self._controller = controller
        self._registry   = registry
        self._lock       = threading.RLock()

    # ── Point d'entrée ────────────────────────────────────────────────────────

    def handle_scan(self, product_id: str) -> SwitchResult:
        """Slot appelé par ProductScanner. Sérialisé."""
        with self._lock:
            return self._handle(product_id)

    # ── Implémentation ────────────────────────────────────────────────────────

    def _handle(self, product_id: str) -> SwitchResult:
        if not product_id:
            logger.warning("AutoSwitch: product_id vide — ignoré")
            return SwitchResult.FAILED

        if not self._registry.has_product(product_id):
            logger.warning("AutoSwitch: produit '%s' inconnu — ignoré", product_id)
            return SwitchResult.FAILED

        if self._controller.active_product_id == product_id:
            logger.debug("AutoSwitch: '%s' déjà actif", product_id)
            return SwitchResult.ALREADY_ACTIVE

        state = self._controller.get_state()

        if state in _REFUSAL_STATES:
            logger.warning(
                "AutoSwitch: refus bascule vers '%s' — état %s",
                product_id, state.value,
            )
            return SwitchResult.FAILED

        if state in _STOP_FIRST_STATES:
            if not self._stop_and_wait():
                return SwitchResult.FAILED

        # IDLE_NO_PRODUCT ou IDLE_READY : activate_product autorisé.
        try:
            self._controller.activate_product(product_id)
        except (SystemStateError, ValueError) as exc:
            logger.error("AutoSwitch: activate_product '%s' échoué — %s",
                         product_id, exc)
            return SwitchResult.FAILED

        logger.info("AutoSwitch: bascule vers '%s' OK", product_id)
        return SwitchResult.SUCCESS

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _stop_and_wait(self) -> bool:
        """Arrête l'inspection puis attend IDLE_READY (< 3s)."""
        t0 = time.monotonic()
        try:
            self._controller.stop_inspection()
        except SystemStateError as exc:
            logger.error("AutoSwitch: stop_inspection a échoué — %s", exc)
            return False

        if not self._wait_state(SystemState.IDLE_READY, _STOP_TIMEOUT_S):
            logger.error(
                "AutoSwitch: stop n'a pas atteint IDLE_READY en %.1fs (état %s)",
                _STOP_TIMEOUT_S, self._controller.get_state().value,
            )
            return False

        logger.info(
            "AutoSwitch: stop_inspection terminé en %.0fms",
            (time.monotonic() - t0) * 1000,
        )
        return True

    def _wait_state(self, target: SystemState, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._controller.get_state() == target:
                return True
            time.sleep(_STOP_POLL_S)
        return self._controller.get_state() == target
