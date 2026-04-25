"""
ws_broadcaster — WebSocket broadcaster v7.0
GR-09 : daemon thread / fire-and-forget — jamais bloquer le pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

logger = logging.getLogger(__name__)


class WSBroadcaster:
    """
    Diffuseur WebSocket multi-clients — §21 web.

    `broadcast(message)` est fire-and-forget : appelable depuis n'importe quel
    thread (callback pipeline, etc.). Aucun client → no-op silencieux.
    """

    def __init__(self) -> None:
        self._clients : set[WebSocket]                = set()
        self._loop    : Optional[asyncio.AbstractEventLoop] = None

    # ── Cycle de vie ─────────────────────────────────────────────────────────

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture la boucle uvicorn (appelé au démarrage du serveur)."""
        self._loop = loop

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ── Connexions clients (depuis l'endpoint /ws) ───────────────────────────

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info("WS client connecté (%d total)", len(self._clients))

    async def unregister(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info("WS client déconnecté (%d total)", len(self._clients))

    async def serve(self, ws: WebSocket) -> None:
        """
        Boucle de service d'un client : on attend simplement la déconnexion.
        Les messages sont push-only — aucune commande n'est consommée du client.
        """
        await self.register(ws)
        try:
            while True:
                # Drain : ignore les messages clients, sortir si déconnecté
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("WS client erreur : %s", e)
        finally:
            await self.unregister(ws)

    # ── Diffusion (fire-and-forget) ──────────────────────────────────────────

    def broadcast(self, message: dict[str, Any]) -> None:
        """
        Émet `message` à tous les clients connectés.

        Thread-safe · fire-and-forget · jamais bloquant.
        Si aucune boucle attachée ou aucun client → silencieux (GR-09).
        """
        if not self._clients:
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast_async(message), loop)
        except Exception as e:
            logger.warning("WS broadcast scheduling failed: %s", e)

    async def _broadcast_async(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        payload = json.dumps(message, default=_json_default)
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                if ws.client_state != WebSocketState.CONNECTED:
                    dead.append(ws)
                    continue
                await ws.send_text(payload)
            except Exception as e:
                logger.debug("WS send failed: %s", e)
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _json_default(obj: Any) -> Any:
    """Sérialise enums et dataclasses tier_verdicts."""
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def build_inspection_message(result: Any) -> dict[str, Any]:
    """
    Construit le message WS standard à partir d'un FinalResult — §21 web.
    Tolérant aux objets minimaux / mocks.
    """
    def g(name: str, default: Any = None) -> Any:
        return getattr(result, name, default)

    tier_verdicts_in = g("tier_verdicts", {}) or {}
    tier_verdicts_out: dict[str, dict[str, Any]] = {}
    for tier_key, tv in tier_verdicts_in.items():
        tier_verdicts_out[tier_key] = {
            "passed":       getattr(tv, "passed", None),
            "fail_reasons": list(getattr(tv, "fail_reasons", []) or []),
        }

    fail_tier = g("fail_tier")
    if fail_tier is not None and hasattr(fail_tier, "value"):
        fail_tier = fail_tier.value

    severity = g("severity")
    if severity is not None and hasattr(severity, "value"):
        severity = severity.value

    llm = g("llm_explanation")
    llm_summary = getattr(llm, "summary", None) if llm is not None else None

    return {
        "type":          "inspection_result",
        "verdict":       g("verdict"),
        "severity":      severity,
        "fail_tier":     fail_tier,
        "fail_reasons":  list(g("fail_reasons", []) or []),
        "tier_scores":   dict(g("tier_scores", {}) or {}),
        "tier_verdicts": tier_verdicts_out,
        "llm_summary":   llm_summary,
        "pipeline_ms":   g("pipeline_ms"),
        "timestamp":     g("timestamp"),
    }
