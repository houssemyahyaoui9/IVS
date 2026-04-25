"""
web_server — FastAPI app + Uvicorn server v7.0
GR-03 : web → SystemController uniquement.
GR-09 : Uvicorn dans daemon thread — jamais dans le thread pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ts2i_ivs.web.api_router import (
    WebDeps,
    build_router,
    make_ws_endpoint,
    push_inspection_result,
)
from ts2i_ivs.web.ws_broadcaster import WSBroadcaster

logger = logging.getLogger(__name__)


class WebServer:
    """
    Serveur web v7.0 — FastAPI + Uvicorn dans un thread daemon (GR-09).

    Usage :
        server = WebServer(deps, host="0.0.0.0", port=8765)
        server.start()                       # daemon thread
        server.broadcaster.broadcast({...})  # fire-and-forget
        server.stop()
    """

    def __init__(
        self,
        deps           : WebDeps,
        host           : str            = "0.0.0.0",
        port           : int            = 8765,
        cors_origins   : Optional[list] = None,
    ) -> None:
        self._deps        = deps
        self._host        = host
        self._port        = port
        self._app         = FastAPI(title="TS2I IVS v7.0 API", version="7.0")
        self._broadcaster = WSBroadcaster()

        # CORS
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins if cors_origins is not None else ["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Routes REST + WebSocket
        router, _ = build_router(deps, self._broadcaster)
        self._app.include_router(router)
        self._app.websocket("/ws")(make_ws_endpoint(self._broadcaster))

        # Hooks de cycle de vie : capter la boucle uvicorn pour le broadcaster
        @self._app.on_event("startup")
        async def _on_startup() -> None:
            self._broadcaster.attach_loop(asyncio.get_running_loop())
            logger.info("WebServer démarré · auth_required=%s", deps.auth_required)

        # Thread + Uvicorn server
        self._thread        : Optional[threading.Thread] = None
        self._uvicorn_server: Optional[Any]              = None

    # ── Propriétés ───────────────────────────────────────────────────────────

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def broadcaster(self) -> WSBroadcaster:
        return self._broadcaster

    @property
    def deps(self) -> WebDeps:
        return self._deps

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    # ── Démarrage / arrêt ────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre Uvicorn dans un thread daemon (GR-09)."""
        if self.is_running:
            logger.warning("WebServer déjà démarré")
            return

        try:
            import uvicorn
        except ImportError as e:
            raise RuntimeError(
                "uvicorn non installé — pip install uvicorn>=0.27"
            ) from e

        config = uvicorn.Config(
            app       = self._app,
            host      = self._host,
            port      = self._port,
            log_level = "info",
            access_log= False,
            lifespan  = "on",
        )
        self._uvicorn_server = uvicorn.Server(config)

        def _run() -> None:
            try:
                self._uvicorn_server.run()
            except Exception as e:
                logger.exception("Uvicorn crash : %s", e)

        self._thread = threading.Thread(target=_run, name="WebServer", daemon=True)
        self._thread.start()
        logger.info("WebServer thread démarré sur %s:%d", self._host, self._port)

    def stop(self, timeout: float = 5.0) -> None:
        """Demande l'arrêt propre du serveur uvicorn."""
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.info("WebServer arrêté")

    # ── Pont pipeline → WS (à brancher sur UIBridge.inspection_result) ───────

    def on_inspection_result(self, result: Any) -> None:
        """Callback à brancher : pousse le FinalResult vers les clients WS."""
        push_inspection_result(self._broadcaster, result)
