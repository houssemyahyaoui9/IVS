"""
ConsecutiveNOKWatcher — §18.2 / §41
Compte les NOK consécutifs et déclenche :
  - alert_threshold (5)  → callback on_alert(count) — WARNING
  - stop_threshold  (10) → callback on_stop(count)  + stop_inspection
                            → reset opérateur OBLIGATOIRE pour repartir

Aucune dépendance Qt — callbacks injectés (testable, GR-03 respecté côté UI).
Branchement typique : SystemController.on_inspection_result()
                      → watcher.on_result(final.verdict)
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from core.pipeline_controller import SystemController

logger = logging.getLogger(__name__)

CountCallback = Callable[[int], None]


class ConsecutiveNOKWatcher:
    """
    Watcher des NOK consécutifs — §18.2.

    on_result("OK"|"NOK"|"REVIEW") :
      - "NOK"             → counter++
      - "OK" ou "REVIEW"  → counter=0 (les REVIEW interrompent la série)
      - counter >= alert_threshold → on_alert(count)  (à chaque dépassement)
      - counter >= stop_threshold  → on_stop(count) + controller.stop_inspection()
                                     puis état "stopped" jusqu'à reset opérateur

    L'état "stopped" empêche un nouveau on_stop avant reset_counter(operator).
    """

    def __init__(
        self,
        alert_threshold : int = 5,
        stop_threshold  : int = 10,
        controller      : Optional["SystemController"] = None,
        on_alert        : Optional[CountCallback] = None,
        on_stop         : Optional[CountCallback] = None,
    ) -> None:
        if alert_threshold <= 0:
            raise ValueError(f"alert_threshold={alert_threshold} doit être > 0")
        if stop_threshold <= 0:
            raise ValueError(f"stop_threshold={stop_threshold} doit être > 0")
        if stop_threshold < alert_threshold:
            raise ValueError(
                f"stop_threshold={stop_threshold} doit être >= alert_threshold={alert_threshold}"
            )

        self._alert_threshold = alert_threshold
        self._stop_threshold  = stop_threshold
        self._controller      = controller
        self._on_alert        = on_alert
        self._on_stop         = on_stop

        self._lock     = threading.RLock()
        self._counter  = 0
        self._stopped  = False  # True après stop_threshold — bloque jusqu'à reset

    # ── Évènement principal ───────────────────────────────────────────────────

    def on_result(self, verdict: str) -> None:
        """Appelé par SystemController.on_inspection_result()."""
        verdict = (verdict or "").upper()

        with self._lock:
            if self._stopped:
                # Ligne arrêtée — on ignore tout jusqu'au reset opérateur.
                return

            if verdict != "NOK":
                if self._counter > 0:
                    logger.debug(
                        "ConsecutiveNOK: série interrompue par '%s' (count=%d)",
                        verdict, self._counter,
                    )
                self._counter = 0
                return

            self._counter += 1
            count = self._counter

            stop_triggered  = count >= self._stop_threshold
            alert_triggered = (
                not stop_triggered and count >= self._alert_threshold
            )

            if stop_triggered:
                self._stopped = True

        # Callbacks émis hors du lock pour éviter les inversions de verrou.
        if alert_triggered:
            logger.warning(
                "ConsecutiveNOK: ALERT — %d NOK consécutifs (seuil %d)",
                count, self._alert_threshold,
            )
            self._safe_call(self._on_alert, count)
        elif stop_triggered:
            logger.error(
                "ConsecutiveNOK: STOP — %d NOK consécutifs (seuil %d) — arrêt ligne",
                count, self._stop_threshold,
            )
            self._safe_call(self._on_stop, count)
            self._stop_line()

    # ── Reset opérateur ───────────────────────────────────────────────────────

    def reset_counter(self, operator: str) -> None:
        """
        Reset obligatoire après stop_threshold.
        `operator` doit être un identifiant non vide — tracé dans les logs.
        """
        op = (operator or "").strip()
        if not op:
            raise ValueError("reset_counter: 'operator' obligatoire (traçabilité)")
        with self._lock:
            prev_count   = self._counter
            prev_stopped = self._stopped
            self._counter = 0
            self._stopped = False
        logger.info(
            "ConsecutiveNOK: reset par '%s' (count=%d, stopped=%s)",
            op, prev_count, prev_stopped,
        )

    # ── Lecture état ──────────────────────────────────────────────────────────

    @property
    def counter(self) -> int:
        with self._lock:
            return self._counter

    @property
    def is_stopped(self) -> bool:
        with self._lock:
            return self._stopped

    @property
    def alert_threshold(self) -> int:
        return self._alert_threshold

    @property
    def stop_threshold(self) -> int:
        return self._stop_threshold

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _stop_line(self) -> None:
        if self._controller is None:
            return
        try:
            self._controller.stop_inspection()
        except Exception as exc:
            logger.error("ConsecutiveNOK: stop_inspection a échoué — %s", exc)

    @staticmethod
    def _safe_call(cb: Optional[CountCallback], count: int) -> None:
        if cb is None:
            return
        try:
            cb(count)
        except Exception as exc:
            logger.error("ConsecutiveNOK: callback %r a levé %s",
                         cb, exc, exc_info=True)
