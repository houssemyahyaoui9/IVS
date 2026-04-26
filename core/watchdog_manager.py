"""
WatchdogManager — §18.1 / §40
Surveille la vitalité du pipeline d'inspection :
  - heartbeat(frame_id) appelé par S8 après chaque FinalResult
  - timeout=60s · check_interval=30s · max_recoveries=3
  - timeout dépassé → emergency_stop + attente IDLE_READY (15s)
  - max_recoveries dépassé → SystemController.transition(ERROR)

Démarré par SystemController.__init__() — thread daemon.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Optional

from core.exceptions import SystemStateError
from core.models import SystemState

if TYPE_CHECKING:
    from core.pipeline_controller import SystemController

logger = logging.getLogger(__name__)

_RECOVERY_WAIT_S = 15.0
_RECOVERY_POLL_S = 0.1


class WatchdogManager:
    """
    Watchdog du pipeline — §18.1.

    Le timer ne court QUE pendant l'état RUNNING ; tout autre état remet
    à zéro la baseline (pas de fausse alarme pendant CALIBRATING/TRAINING).
    """

    def __init__(
        self,
        controller       : "SystemController",
        timeout_s        : float = 60.0,
        check_interval_s : float = 30.0,
        max_recoveries   : int   = 3,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError(f"timeout_s={timeout_s} doit être > 0")
        if check_interval_s <= 0:
            raise ValueError(f"check_interval_s={check_interval_s} doit être > 0")
        if max_recoveries < 0:
            raise ValueError(f"max_recoveries={max_recoveries} doit être >= 0")

        self._controller       = controller
        self._timeout_s        = timeout_s
        self._check_interval_s = check_interval_s
        self._max_recoveries   = max_recoveries

        self._lock             = threading.RLock()
        self._last_heartbeat   = time.monotonic()
        self._last_frame_id    : Optional[str] = None
        self._recovery_count   = 0

        self._stop_evt = threading.Event()
        self._thread   : Optional[threading.Thread] = None

    # ── Heartbeat (appelé par S8) ─────────────────────────────────────────────

    def heartbeat(self, frame_id: str) -> None:
        with self._lock:
            self._last_heartbeat = time.monotonic()
            self._last_frame_id  = frame_id

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_evt.clear()
        with self._lock:
            self._last_heartbeat = time.monotonic()
            self._recovery_count = 0
        self._thread = threading.Thread(
            target=self._run, name="WatchdogManager", daemon=True,
        )
        self._thread.start()
        logger.info(
            "WatchdogManager démarré (timeout=%.0fs, check=%.0fs, max_recoveries=%d)",
            self._timeout_s, self._check_interval_s, self._max_recoveries,
        )

    def stop(self, timeout_s: float = 2.0) -> None:
        self._stop_evt.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_s)
        self._thread = None
        logger.info("WatchdogManager arrêté")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def recovery_count(self) -> int:
        with self._lock:
            return self._recovery_count

    # ── Boucle ────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._check()
            except Exception as exc:
                logger.error(
                    "WatchdogManager: erreur check — %s", exc, exc_info=True,
                )
            if self._stop_evt.wait(self._check_interval_s):
                break

    def _check(self) -> None:
        state = self._controller.get_state()

        # Timer ne court que pendant RUNNING — tout autre état réinitialise.
        if state != SystemState.RUNNING:
            with self._lock:
                self._last_heartbeat = time.monotonic()
            return

        with self._lock:
            elapsed = time.monotonic() - self._last_heartbeat

        if elapsed <= self._timeout_s:
            return

        # ── Timeout déclenché ─────────────────────────────────────────────────
        with self._lock:
            self._recovery_count += 1
            recovery_n = self._recovery_count

        if recovery_n > self._max_recoveries:
            logger.error(
                "Watchdog: %d récupérations dépassées — transition ERROR",
                self._max_recoveries,
            )
            try:
                self._controller.transition(SystemState.ERROR)
            except SystemStateError as exc:
                logger.error("Watchdog: transition ERROR refusée — %s", exc)
            return

        logger.info(
            "Watchdog recovery #%d (elapsed=%.1fs > timeout=%.0fs)",
            recovery_n, elapsed, self._timeout_s,
        )
        self._controller.emergency_stop()

        if self._wait_state(SystemState.IDLE_READY, _RECOVERY_WAIT_S):
            with self._lock:
                self._last_heartbeat = time.monotonic()
            logger.info("Watchdog: IDLE_READY atteint après recovery #%d", recovery_n)
        else:
            logger.warning(
                "Watchdog: IDLE_READY non atteint en %.0fs après recovery #%d",
                _RECOVERY_WAIT_S, recovery_n,
            )

    def _wait_state(self, target: SystemState, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._stop_evt.is_set():
                return False
            if self._controller.get_state() == target:
                return True
            time.sleep(_RECOVERY_POLL_S)
        return self._controller.get_state() == target
