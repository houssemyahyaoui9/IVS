"""
S8 Output — LLM + Learning + GPIO + WebSocket + DB
Entrée : FinalResult
Sortie : None (effets de bord uniquement)
GR-09  : BackgroundTrainer dans thread daemon — jamais dans le pipeline
"""
from __future__ import annotations

import logging

from core.models import FinalResult

logger = logging.getLogger(__name__)


class S8Output:
    """
    Stage 8 — Sortie multicanal.

    Dispatcher : envoie FinalResult vers tous les canaux de sortie.
    Chaque canal est optionnel (None si non configuré).

    Canaux :
      - LLM explainer (stub)
      - Learning buffer (stub — GR-09)
      - GPIO controller (stub)
      - WebSocket broadcaster (stub)
      - DB writer (stub)
    """

    def __init__(
        self,
        llm_explainer=None,
        learning_buffer=None,
        gpio_controller=None,
        ws_broadcaster=None,
        db_writer=None,
        watchdog=None,
    ) -> None:
        self._llm      = llm_explainer
        self._learning = learning_buffer
        self._gpio     = gpio_controller
        self._ws       = ws_broadcaster
        self._db       = db_writer
        self._watchdog = watchdog

    def process(self, result: FinalResult) -> None:
        """
        Dispatche FinalResult vers tous les canaux actifs.
        Chaque canal failure est loggé mais n'arrête pas les autres.
        """
        self._send_gpio(result)
        self._send_db(result)
        self._send_ws(result)
        self._send_learning(result)
        # LLM est asynchrone — lancé en dernier (le plus lent)
        self._send_llm(result)
        # Heartbeat watchdog — §18.1 (toujours après dispatch, même si un canal a échoué)
        self._send_heartbeat(result)

    # ── Watchdog heartbeat ───────────────────────────────────────────────────

    def _send_heartbeat(self, result: FinalResult) -> None:
        if self._watchdog is None:
            return
        try:
            self._watchdog.heartbeat(result.frame_id)
        except Exception as exc:
            logger.error("S8: watchdog heartbeat error — %s", exc)

    # ── GPIO ─────────────────────────────────────────────────────────────────

    def _send_gpio(self, result: FinalResult) -> None:
        """
        Mapping verdict → GPIO (CLAUDE.md) :
          OK     → lampe VERTE ON
          NOK    → lampe ROUGE ON
          REVIEW → rien (opérateur décide)
        """
        if self._gpio is None:
            return
        try:
            if result.verdict == "OK":
                self._gpio.set_green(True)
                self._gpio.set_red(False)
            elif result.verdict == "NOK":
                self._gpio.set_green(False)
                self._gpio.set_red(True)
            # REVIEW : pas de GPIO
        except Exception as exc:
            logger.error("S8: GPIO error — %s", exc)

    # ── DB ───────────────────────────────────────────────────────────────────

    def _send_db(self, result: FinalResult) -> None:
        if self._db is None:
            return
        try:
            self._db.write(result)
        except Exception as exc:
            logger.error("S8: DB write error — %s", exc)

    # ── WebSocket ─────────────────────────────────────────────────────────────

    def _send_ws(self, result: FinalResult) -> None:
        if self._ws is None:
            return
        try:
            self._ws.broadcast(result)
        except Exception as exc:
            logger.error("S8: WebSocket error — %s", exc)

    # ── Learning buffer (GR-09) ───────────────────────────────────────────────

    def _send_learning(self, result: FinalResult) -> None:
        """
        Soumet FinalResult au TierLearningBuffer.
        L'entraînement lui-même est dans un thread daemon (GR-09).
        """
        if self._learning is None:
            return
        try:
            self._learning.submit(result)
        except Exception as exc:
            logger.error("S8: Learning buffer error — %s", exc)

    # ── LLM explainer ────────────────────────────────────────────────────────

    def _send_llm(self, result: FinalResult) -> None:
        """LLM explication asynchrone — display only (GR-04)."""
        if self._llm is None:
            return
        try:
            self._llm.explain_async(result)
        except Exception as exc:
            logger.error("S8: LLM error — %s", exc)
