"""
api_router — 15 endpoints REST v7.0 + WebSocket /ws
GR-03 : web → SystemController (jamais d'accès direct au pipeline).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Path,
    Query,
    UploadFile,
    WebSocket,
    status,
)
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from ts2i_ivs.web.ws_broadcaster import WSBroadcaster, build_inspection_message

logger = logging.getLogger(__name__)

# python-multipart est requis par FastAPI pour les endpoints multipart/form-data.
# S'il manque, on dégrade proprement : l'endpoint /products/import renverra 503.
try:
    import multipart  # noqa: F401  (python-multipart)
    _MULTIPART_AVAILABLE = True
except ImportError:
    _MULTIPART_AVAILABLE = False


# ═════════════════════════════════════════════════════════════════════════════
#  Protocols (dépendances injectées — découplent web/ du reste du système)
# ═════════════════════════════════════════════════════════════════════════════

class ControllerProto(Protocol):
    def get_state(self) -> Any: ...
    def start_inspection(self) -> None: ...
    def stop_inspection(self) -> None: ...
    def activate_product(self, product_id: str) -> None: ...
    @property
    def active_product_id(self) -> Optional[str]: ...


class DatabaseProto(Protocol):
    def get_last_result(self) -> Optional[Any]: ...
    def get_history(self, limit: int, product_id: Optional[str]) -> list[Any]: ...


class ProductRegistryProto(Protocol):
    def list_products(self) -> list[Any]: ...
    def get(self, product_id: str) -> Optional[Any]: ...


class FleetManagerProto(Protocol):
    def import_package(self, ivs_file_path: str) -> Any: ...
    def export_package(self, product_id: str, output_path: str) -> str: ...


class SPCServiceProto(Protocol):
    def get_metrics(self) -> dict: ...


class SystemMonitorProto(Protocol):
    def get_snapshot(self) -> Any: ...


class ReportGeneratorProto(Protocol):
    def generate(self, **kwargs: Any) -> str: ...
    def get_pdf_path(self, report_id: str) -> Optional[str]: ...


class AuthManagerProto(Protocol):
    def authenticate(self, username: str, password: str) -> Optional[str]: ...
    def issue_token(self, username: str) -> tuple[str, int]: ...
    def decode_token(self, token: str) -> dict: ...


# ═════════════════════════════════════════════════════════════════════════════
#  WebDeps : conteneur de dépendances injectées
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class WebDeps:
    controller       : Optional[ControllerProto]      = None
    database         : Optional[DatabaseProto]        = None
    product_registry : Optional[ProductRegistryProto] = None
    fleet_manager    : Optional[FleetManagerProto]    = None
    spc_service      : Optional[SPCServiceProto]      = None
    system_monitor   : Optional[SystemMonitorProto]   = None
    report_generator : Optional[ReportGeneratorProto] = None
    auth_manager     : Optional[AuthManagerProto]     = None
    auth_required    : bool                           = True
    station_id       : str                            = "STATION-001"
    started_at       : float                          = field(default_factory=time.time)


# ═════════════════════════════════════════════════════════════════════════════
#  Models Pydantic
# ═════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username : str
    password : str


class LoginResponse(BaseModel):
    token      : str
    expires_in : int


# ═════════════════════════════════════════════════════════════════════════════
#  Sérialiseurs (FinalResult / TierVerdict / SystemSnapshot → dict)
# ═════════════════════════════════════════════════════════════════════════════

def _enum_value(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


def _serialize_tier_verdict(tv: Any) -> dict:
    if tv is None:
        return None  # type: ignore[return-value]
    if isinstance(tv, dict):
        return tv
    return {
        "tier"        : _enum_value(getattr(tv, "tier", None)),
        "passed"      : getattr(tv, "passed", None),
        "fail_reasons": list(getattr(tv, "fail_reasons", []) or []),
        "tier_score"  : getattr(tv, "tier_score", None),
        "completed"   : getattr(tv, "completed", None),
        "latency_ms"  : getattr(tv, "latency_ms", None),
    }


def _serialize_final_result(r: Any) -> dict:
    if r is None:
        return None  # type: ignore[return-value]
    if isinstance(r, dict):
        return r

    verdict       = getattr(r, "verdict", None)
    tier_verdicts = {
        k: _serialize_tier_verdict(v)
        for k, v in (getattr(r, "tier_verdicts", {}) or {}).items()
    }
    fail_tier = getattr(r, "fail_tier", None)
    severity  = getattr(r, "severity", None)
    llm       = getattr(r, "llm_explanation", None)

    out: dict[str, Any] = {
        "frame_id"            : getattr(r, "frame_id", None),
        "product_id"          : getattr(r, "product_id", None),
        "verdict"             : verdict,
        "severity"            : _enum_value(severity),
        "fail_tier"           : _enum_value(fail_tier),
        "tier_scores"         : dict(getattr(r, "tier_scores", {}) or {}),
        "tier_verdicts"       : tier_verdicts,
        "pipeline_ms"         : getattr(r, "pipeline_ms", None),
        "background_complete" : getattr(r, "background_complete", None),
        "timestamp"           : getattr(r, "timestamp", None),
        "model_versions"      : dict(getattr(r, "model_versions", {}) or {}),
        "llm_summary"         : getattr(llm, "summary", None) if llm is not None else None,
    }
    # fail_reasons exclu si verdict == OK
    if verdict != "OK":
        out["fail_reasons"] = list(getattr(r, "fail_reasons", []) or [])
    return out


def _serialize_snapshot(s: Any) -> dict:
    if s is None:
        return None  # type: ignore[return-value]
    if isinstance(s, dict):
        return s
    return {k: _enum_value(v) for k, v in vars(s).items() if not k.startswith("_")}


# ═════════════════════════════════════════════════════════════════════════════
#  Dépendance auth — vérifie JWT si auth_required
# ═════════════════════════════════════════════════════════════════════════════

def _make_auth_dependency(deps: WebDeps):
    def _auth(
        authorization: Optional[str] = Header(default=None),
    ) -> Optional[dict]:
        if not deps.auth_required:
            return None
        if deps.auth_manager is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="auth_manager non configuré",
            )
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token manquant")
        token = authorization.split(" ", 1)[1].strip()
        try:
            return deps.auth_manager.decode_token(token)
        except Exception as e:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"Token invalide : {e}")
    return _auth


def _require(dep: Any, name: str) -> None:
    if dep is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Dépendance non configurée : {name}",
        )


# ═════════════════════════════════════════════════════════════════════════════
#  Builder principal
# ═════════════════════════════════════════════════════════════════════════════

def build_router(
    deps        : WebDeps,
    broadcaster : WSBroadcaster,
) -> tuple[APIRouter, WSBroadcaster]:
    """
    Construit l'APIRouter v7.0 + retourne le broadcaster WS associé.

    Returns:
        (router, broadcaster) — à monter sur l'app FastAPI.
    """
    router    = APIRouter(prefix="/api/v1")
    auth_dep  = _make_auth_dependency(deps)

    # ── 1. GET /status (public) ──────────────────────────────────────────────
    @router.get("/status")
    def get_status() -> dict:
        state = None
        product_id = None
        if deps.controller is not None:
            try:
                state = _enum_value(deps.controller.get_state())
                product_id = deps.controller.active_product_id
            except Exception as e:
                logger.warning("controller.get_state failed: %s", e)
        return {
            "state"     : state,
            "product_id": product_id,
            "station_id": deps.station_id,
            "uptime"    : time.time() - deps.started_at,
            "version"   : "v7.0",
        }

    # ── 2. POST /inspection/start ────────────────────────────────────────────
    @router.post("/inspection/start")
    def post_start(_user: Optional[dict] = Depends(auth_dep)) -> dict:
        _require(deps.controller, "controller")
        try:
            deps.controller.start_inspection()
        except Exception as e:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
        return {"success": True, "state": _enum_value(deps.controller.get_state())}

    # ── 3. POST /inspection/stop ─────────────────────────────────────────────
    @router.post("/inspection/stop")
    def post_stop(_user: Optional[dict] = Depends(auth_dep)) -> dict:
        _require(deps.controller, "controller")
        try:
            deps.controller.stop_inspection()
        except Exception as e:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
        return {"success": True, "state": _enum_value(deps.controller.get_state())}

    # ── 4. GET /results/last ─────────────────────────────────────────────────
    @router.get("/results/last")
    def get_last_result(_user: Optional[dict] = Depends(auth_dep)) -> dict:
        _require(deps.database, "database")
        result = deps.database.get_last_result()
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aucun résultat")
        return _serialize_final_result(result)

    # ── 5. GET /results/history ──────────────────────────────────────────────
    @router.get("/results/history")
    def get_history(
        limit      : int           = Query(50, ge=1, le=1000),
        product_id : Optional[str] = Query(None),
        _user      : Optional[dict] = Depends(auth_dep),
    ) -> list[dict]:
        _require(deps.database, "database")
        rows = deps.database.get_history(limit=limit, product_id=product_id)
        return [_serialize_final_result(r) for r in rows]

    # ── 6. GET /tier_verdicts/last (NOUVEAU v7.0) ────────────────────────────
    @router.get("/tier_verdicts/last")
    def get_last_tier_verdicts(_user: Optional[dict] = Depends(auth_dep)) -> dict:
        _require(deps.database, "database")
        result = deps.database.get_last_result()
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aucun résultat")
        tvs = getattr(result, "tier_verdicts", {}) or {}
        return {k: _serialize_tier_verdict(v) for k, v in tvs.items()}

    # ── 7. GET /products ─────────────────────────────────────────────────────
    @router.get("/products")
    def list_products(_user: Optional[dict] = Depends(auth_dep)) -> list[dict]:
        _require(deps.product_registry, "product_registry")
        active = deps.controller.active_product_id if deps.controller else None
        products = deps.product_registry.list_products()
        out: list[dict] = []
        for p in products:
            pid = getattr(p, "product_id", None) if not isinstance(p, dict) else p.get("product_id")
            out.append({
                "product_id": pid,
                "name"      : getattr(p, "name", None)    if not isinstance(p, dict) else p.get("name"),
                "version"   : getattr(p, "version", None) if not isinstance(p, dict) else p.get("version"),
                "active"    : pid == active,
            })
        return out

    # ── 8. POST /products/{id}/activate ──────────────────────────────────────
    @router.post("/products/{product_id}/activate")
    def activate_product(
        product_id : str = Path(...),
        _user      : Optional[dict] = Depends(auth_dep),
    ) -> dict:
        _require(deps.controller, "controller")
        try:
            deps.controller.activate_product(product_id)
        except Exception as e:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))
        return {"success": True, "product_id": product_id}

    # ── 9. POST /products/import (Fleet §Fleet.4) ────────────────────────────
    if _MULTIPART_AVAILABLE:
        @router.post("/products/import")
        async def import_product(
            file  : UploadFile = File(...),
            _user : Optional[dict] = Depends(auth_dep),
        ) -> dict:
            _require(deps.fleet_manager, "fleet_manager")
            import tempfile
            import os
            suffix = ".ivs" if not (file.filename or "").endswith(".ivs") else ""
            tmp_path = ""
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp_path = tmp.name
                    while True:
                        chunk = await file.read(1 << 20)
                        if not chunk:
                            break
                        tmp.write(chunk)
                result = deps.fleet_manager.import_package(tmp_path)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Import échoué : {e}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                await file.close()

            success = bool(
                getattr(result, "success", False) or getattr(result, "passed", False)
            )
            return {
                "success"           : success,
                "product_id"        : getattr(result, "product_id", None),
                "validation_report" : getattr(result, "validation_report", None)
                                      or getattr(result, "validation", None),
            }
    else:
        @router.post("/products/import")
        def import_product_unavailable(_user: Optional[dict] = Depends(auth_dep)) -> dict:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="python-multipart non installé : pip install python-multipart",
            )

    # ── 10. GET /products/{id}/export (Fleet §Fleet.4) ───────────────────────
    @router.get("/products/{product_id}/export")
    def export_product(
        product_id : str = Path(...),
        _user      : Optional[dict] = Depends(auth_dep),
    ) -> FileResponse:
        _require(deps.fleet_manager, "fleet_manager")
        import tempfile
        import os
        out_dir  = tempfile.mkdtemp(prefix="ivs_export_")
        out_path = os.path.join(out_dir, f"{product_id}.ivs")
        try:
            path = deps.fleet_manager.export_package(product_id, out_path)
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Export échoué : {e}")
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=f"{product_id}.ivs",
        )

    # ── 11. GET /spc ─────────────────────────────────────────────────────────
    @router.get("/spc")
    def get_spc(_user: Optional[dict] = Depends(auth_dep)) -> dict:
        _require(deps.spc_service, "spc_service")
        try:
            metrics = deps.spc_service.get_metrics() or {}
        except Exception as e:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        return {
            "cp"       : metrics.get("cp"),
            "cpk"      : metrics.get("cpk"),
            "tier_cp"  : metrics.get("tier_cp", {}),
            "samples"  : metrics.get("samples"),
        }

    # ── 12. GET /system/snapshot ─────────────────────────────────────────────
    @router.get("/system/snapshot")
    def get_system_snapshot(_user: Optional[dict] = Depends(auth_dep)) -> dict:
        _require(deps.system_monitor, "system_monitor")
        snap = deps.system_monitor.get_snapshot()
        return _serialize_snapshot(snap)

    # ── 13. POST /reports/generate ───────────────────────────────────────────
    @router.post("/reports/generate")
    def generate_report(
        product_id : Optional[str] = Query(None),
        _user      : Optional[dict] = Depends(auth_dep),
    ) -> dict:
        _require(deps.report_generator, "report_generator")
        try:
            report_id = deps.report_generator.generate(product_id=product_id)
        except Exception as e:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        return {"report_id": report_id, "status": "generating"}

    # ── 14. GET /reports/{id} ────────────────────────────────────────────────
    @router.get("/reports/{report_id}")
    def get_report(
        report_id : str = Path(...),
        _user     : Optional[dict] = Depends(auth_dep),
    ) -> Response:
        _require(deps.report_generator, "report_generator")
        path = deps.report_generator.get_pdf_path(report_id)
        if not path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport introuvable")
        return FileResponse(path, media_type="application/pdf",
                            filename=f"{report_id}.pdf")

    # ── 15. POST /auth/login ─────────────────────────────────────────────────
    @router.post("/auth/login", response_model=LoginResponse)
    def login(req: LoginRequest) -> LoginResponse:
        _require(deps.auth_manager, "auth_manager")
        user = deps.auth_manager.authenticate(req.username, req.password)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credentials invalides")
        token, expires_in = deps.auth_manager.issue_token(user)
        return LoginResponse(token=token, expires_in=expires_in)

    return router, broadcaster


# ═════════════════════════════════════════════════════════════════════════════
#  WebSocket endpoint factory
# ═════════════════════════════════════════════════════════════════════════════

def make_ws_endpoint(broadcaster: WSBroadcaster):
    """
    Renvoie l'handler à monter via `app.websocket("/ws")(make_ws_endpoint(...))`.
    """
    async def _endpoint(ws: WebSocket) -> None:
        await broadcaster.serve(ws)
    return _endpoint


# ═════════════════════════════════════════════════════════════════════════════
#  Hook pipeline → WebSocket
# ═════════════════════════════════════════════════════════════════════════════

def push_inspection_result(broadcaster: WSBroadcaster, result: Any) -> None:
    """
    À appeler depuis un callback pipeline (UIBridge.inspection_result).
    Fire-and-forget — GR-09 — jamais bloquant.
    """
    try:
        msg = build_inspection_message(result)
        broadcaster.broadcast(msg)
    except Exception as e:
        logger.warning("push_inspection_result failed: %s", e)
