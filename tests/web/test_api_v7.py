"""
tests/web/test_api_v7.py
Gate G-18 — Web API v7.0
TS2I IVS v7.0

Checks (S18-A) :
  - GET /api/v1/status → 200 + version:"v7.0"
  - GET /api/v1/tier_verdicts/last → dict avec 3 tiers
  - POST /api/v1/products/import → 200 (Fleet endpoint présent)
  - WebSocket : message contient tier_verdicts
  - JWT auth : sans token → 401 sur endpoints protégés
  - 15 endpoints tous répondent (liste exhaustive)
"""
from __future__ import annotations

import io
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from ts2i_ivs.web.api_router import (
    WebDeps,
    _serialize_final_result,
    build_router,
)
from ts2i_ivs.web.web_server import WebServer
from ts2i_ivs.web.ws_broadcaster import WSBroadcaster, build_inspection_message


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures partagées — fakes minimaux pour les Protocols injectés
# ═══════════════════════════════════════════════════════════════════════════

class _FakeEnum:
    """Mime un enum (.value)."""
    def __init__(self, value: str) -> None:
        self.value = value


class FakeTierVerdict:
    def __init__(self, tier: str, passed: bool, fail_reasons: tuple[str, ...] = ()) -> None:
        self.tier         = _FakeEnum(tier)
        self.passed       = passed
        self.fail_reasons = fail_reasons
        self.signals      = ()
        self.tier_score   = 0.94 if passed else 0.22
        self.completed    = True
        self.latency_ms   = 10.0


class FakeFinalResult:
    def __init__(self, verdict: str = "NOK") -> None:
        self.frame_id        = "frame-001"
        self.product_id      = "P208"
        self.model_versions  = {"yolo": "v3", "sift": "v1"}
        self.verdict         = verdict
        self.severity        = _FakeEnum("DEFECT_1" if verdict == "NOK" else "ACCEPTABLE")
        self.fail_tier       = _FakeEnum("MAJOR") if verdict == "NOK" else None
        self.fail_reasons    = ("LOGO_208_COLOR_MISMATCH",) if verdict == "NOK" else ()
        self.tier_verdicts   = {
            "CRITICAL": FakeTierVerdict("CRITICAL", True),
            "MAJOR":    FakeTierVerdict("MAJOR",    verdict != "NOK", self.fail_reasons),
            "MINOR":    FakeTierVerdict("MINOR",    True),
        }
        self.tier_scores     = {"CRITICAL": 0.94, "MAJOR": 0.22, "MINOR": 0.91}
        self.llm_explanation = type("LLM", (), {"summary": "Tier MAJOR échoué : couleur incorrecte."})()
        self.pipeline_ms     = 2150.0
        self.background_complete = True
        self.luminosity_result   = None
        self.timestamp       = 1_700_000_000.0


class FakeProduct:
    def __init__(self, product_id: str, name: str, version: str = "1.0") -> None:
        self.product_id = product_id
        self.name       = name
        self.version    = version


class FakeAuthManager:
    """Auth manager minimal — token = 'good-token-for:{user}'."""
    VALID_TOKEN = "valid-jwt-token"

    def authenticate(self, username: str, password: str) -> str | None:
        return username if (username == "admin" and password == "admin") else None

    def issue_token(self, username: str) -> tuple[str, int]:
        return (self.VALID_TOKEN, 3600)

    def decode_token(self, token: str) -> dict:
        if token != self.VALID_TOKEN:
            raise ValueError("token invalide")
        return {"sub": "admin"}


class FakeFleetManager:
    def __init__(self) -> None:
        self.imported_paths: list[str] = []

    def import_package(self, ivs_file_path: str) -> Any:
        self.imported_paths.append(ivs_file_path)
        return type("ImportResult", (), {
            "success":           True,
            "passed":            True,
            "product_id":        "P-IMPORTED",
            "validation_report": {"checks": ["sha256_ok", "model_ok"], "passed": True},
        })()

    def export_package(self, product_id: str, output_path: str) -> str:
        with open(output_path, "wb") as f:
            f.write(b"\x50\x4B\x03\x04fake.ivs.zip")  # ZIP magic
        return output_path


# ═══════════════════════════════════════════════════════════════════════════
# Builder TestClient
# ═══════════════════════════════════════════════════════════════════════════

def _make_deps(*, auth_required: bool = False) -> tuple[WebDeps, dict]:
    """Construit un WebDeps complet avec mocks pour tous les Protocols."""
    ctrl = MagicMock()
    ctrl.get_state.return_value = _FakeEnum("IDLE_READY")
    ctrl.active_product_id = "P208"

    db = MagicMock()
    db.get_last_result.return_value = FakeFinalResult(verdict="NOK")
    db.get_history.return_value     = [FakeFinalResult("NOK"), FakeFinalResult("OK")]

    registry = MagicMock()
    registry.list_products.return_value = [
        FakeProduct("P208", "Tapis 208"),
        FakeProduct("P209", "Tapis 209"),
    ]

    spc = MagicMock()
    spc.get_metrics.return_value = {
        "cp": 1.42, "cpk": 1.31, "samples": 250,
        "tier_cp": {"CRITICAL": 1.55, "MAJOR": 1.30, "MINOR": 1.18},
    }

    sysmon = MagicMock()
    class _Snap:
        def __init__(self) -> None:
            self.cpu_percent  = 23.4
            self.ram_percent  = 41.2
            self.temp_c       = 47.1
            self.disk_free_gb = 102.5
            self.uptime_s     = 1234.0
    sysmon.get_snapshot.return_value = _Snap()

    rep = MagicMock()
    rep.generate.return_value = "rpt-001"
    pdf_path = os.path.join(tempfile.gettempdir(), "rpt-001.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4 fake")
    rep.get_pdf_path.return_value = pdf_path

    auth_mgr = FakeAuthManager()
    fleet    = FakeFleetManager()

    deps = WebDeps(
        controller       = ctrl,
        database         = db,
        product_registry = registry,
        fleet_manager    = fleet,
        spc_service      = spc,
        system_monitor   = sysmon,
        report_generator = rep,
        auth_manager     = auth_mgr,
        auth_required    = auth_required,
        station_id       = "STATION-TEST",
    )
    handles = {
        "ctrl": ctrl, "db": db, "registry": registry, "spc": spc,
        "sysmon": sysmon, "rep": rep, "auth": auth_mgr, "fleet": fleet,
        "pdf_path": pdf_path,
    }
    return deps, handles


@pytest.fixture
def client_no_auth() -> TestClient:
    deps, _ = _make_deps(auth_required=False)
    server  = WebServer(deps, host="127.0.0.1", port=0)
    return TestClient(server.app)


@pytest.fixture
def client_with_auth():
    deps, handles = _make_deps(auth_required=True)
    server  = WebServer(deps, host="127.0.0.1", port=0)
    return TestClient(server.app), handles


@pytest.fixture
def auth_header(client_with_auth) -> dict:
    _, handles = client_with_auth
    return {"Authorization": f"Bearer {handles['auth'].VALID_TOKEN}"}


# ═══════════════════════════════════════════════════════════════════════════
# G-18-01  Liste exhaustive des 15 endpoints + /ws
# ═══════════════════════════════════════════════════════════════════════════

EXPECTED_ENDPOINTS = {
    ("GET",       "/api/v1/status"),
    ("POST",      "/api/v1/inspection/start"),
    ("POST",      "/api/v1/inspection/stop"),
    ("GET",       "/api/v1/results/last"),
    ("GET",       "/api/v1/results/history"),
    ("GET",       "/api/v1/tier_verdicts/last"),
    ("GET",       "/api/v1/products"),
    ("POST",      "/api/v1/products/{product_id}/activate"),
    ("POST",      "/api/v1/products/import"),
    ("GET",       "/api/v1/products/{product_id}/export"),
    ("GET",       "/api/v1/spc"),
    ("GET",       "/api/v1/system/snapshot"),
    ("POST",      "/api/v1/reports/generate"),
    ("GET",       "/api/v1/reports/{report_id}"),
    ("POST",      "/api/v1/auth/login"),
}


class TestEndpointRegistration:

    def test_all_15_endpoints_registered(self, client_no_auth: TestClient) -> None:
        registered = set()
        for route in client_no_auth.app.routes:
            path    = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if not path or not methods or not path.startswith("/api/v1"):
                continue
            for m in methods:
                if m in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                    registered.add((m, path))
        missing = EXPECTED_ENDPOINTS - registered
        assert not missing, f"Endpoints manquants : {missing}"

    def test_websocket_route_registered(self, client_no_auth: TestClient) -> None:
        ws_paths = [r.path for r in client_no_auth.app.routes
                    if getattr(r, "path", "") == "/ws"]
        assert ws_paths == ["/ws"]


# ═══════════════════════════════════════════════════════════════════════════
# G-18-02  GET /api/v1/status → 200 + version "v7.0"
# ═══════════════════════════════════════════════════════════════════════════

class TestStatusEndpoint:

    def test_status_returns_200(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/status")
        assert r.status_code == 200

    def test_status_version_v7(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/status")
        assert r.json()["version"] == "v7.0"

    def test_status_payload_keys(self, client_no_auth: TestClient) -> None:
        body = client_no_auth.get("/api/v1/status").json()
        for key in ("state", "product_id", "station_id", "uptime", "version"):
            assert key in body, f"clé manquante : {key}"

    def test_status_station_id_propagated(self, client_no_auth: TestClient) -> None:
        body = client_no_auth.get("/api/v1/status").json()
        assert body["station_id"] == "STATION-TEST"


# ═══════════════════════════════════════════════════════════════════════════
# G-18-03  POST /inspection/start | /stop
# ═══════════════════════════════════════════════════════════════════════════

class TestInspectionControl:

    def test_start_returns_success(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.post("/api/v1/inspection/start")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "state" in body

    def test_stop_returns_success(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.post("/api/v1/inspection/stop")
        assert r.status_code == 200
        assert r.json()["success"] is True


# ═══════════════════════════════════════════════════════════════════════════
# G-18-04  GET /results/last + /history
# ═══════════════════════════════════════════════════════════════════════════

class TestResults:

    def test_results_last_200_with_tier_verdicts(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/results/last")
        assert r.status_code == 200
        body = r.json()
        assert "tier_verdicts" in body
        assert "tier_scores"   in body

    def test_results_last_includes_fail_reasons_when_NOK(self, client_no_auth: TestClient) -> None:
        body = client_no_auth.get("/api/v1/results/last").json()
        assert body["verdict"] == "NOK"
        assert "fail_reasons" in body
        assert "LOGO_208_COLOR_MISMATCH" in body["fail_reasons"]

    def test_results_serializer_excludes_fail_reasons_when_OK(self) -> None:
        out = _serialize_final_result(FakeFinalResult(verdict="OK"))
        assert out["verdict"] == "OK"
        assert "fail_reasons" not in out  # exclu si OK — §21

    def test_history_with_limit(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/results/history?limit=10")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_history_with_product_filter(self, client_no_auth: TestClient, monkeypatch) -> None:
        r = client_no_auth.get("/api/v1/results/history?limit=5&product_id=P208")
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# G-18-05  GET /tier_verdicts/last → dict avec 3 tiers
# ═══════════════════════════════════════════════════════════════════════════

class TestTierVerdictsEndpoint:

    def test_tier_verdicts_returns_200(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/tier_verdicts/last")
        assert r.status_code == 200

    def test_tier_verdicts_contains_three_tiers(self, client_no_auth: TestClient) -> None:
        body = client_no_auth.get("/api/v1/tier_verdicts/last").json()
        assert set(body.keys()) == {"CRITICAL", "MAJOR", "MINOR"}

    def test_tier_verdicts_passed_field(self, client_no_auth: TestClient) -> None:
        body = client_no_auth.get("/api/v1/tier_verdicts/last").json()
        for tier in ("CRITICAL", "MAJOR", "MINOR"):
            assert "passed" in body[tier]
            assert "fail_reasons" in body[tier]


# ═══════════════════════════════════════════════════════════════════════════
# G-18-06  GET /products + POST /products/{id}/activate
# ═══════════════════════════════════════════════════════════════════════════

class TestProducts:

    def test_list_products(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/products")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 2
        ids = {p["product_id"] for p in body}
        assert ids == {"P208", "P209"}

    def test_active_flag_set(self, client_no_auth: TestClient) -> None:
        body = client_no_auth.get("/api/v1/products").json()
        actives = [p for p in body if p["active"]]
        assert len(actives) == 1
        assert actives[0]["product_id"] == "P208"

    def test_activate_product(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.post("/api/v1/products/P209/activate")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["product_id"] == "P209"


# ═══════════════════════════════════════════════════════════════════════════
# G-18-07  POST /products/import (Fleet) — 200 + endpoint présent
# ═══════════════════════════════════════════════════════════════════════════

class TestFleetImport:

    def test_import_endpoint_present(self, client_no_auth: TestClient) -> None:
        paths = [(getattr(r, "path", None), getattr(r, "methods", set()))
                 for r in client_no_auth.app.routes]
        assert any(p == "/api/v1/products/import" and "POST" in (m or set())
                   for p, m in paths), "POST /products/import non enregistré"

    def test_import_uploads_file_and_returns_200(self, client_no_auth: TestClient) -> None:
        fake_ivs = io.BytesIO(b"\x50\x4B\x03\x04fake.ivs payload")
        r = client_no_auth.post(
            "/api/v1/products/import",
            files={"file": ("tapis_p208.ivs", fake_ivs, "application/octet-stream")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["product_id"] == "P-IMPORTED"
        assert "validation_report" in body

    def test_export_endpoint_present(self, client_no_auth: TestClient) -> None:
        paths = [(getattr(r, "path", None), getattr(r, "methods", set()))
                 for r in client_no_auth.app.routes]
        assert any(p == "/api/v1/products/{product_id}/export"
                   and "GET" in (m or set()) for p, m in paths)

    def test_export_returns_file(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/products/P208/export")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        # ZIP magic bytes
        assert r.content[:4] == b"\x50\x4B\x03\x04"


# ═══════════════════════════════════════════════════════════════════════════
# G-18-08  GET /spc + /system/snapshot
# ═══════════════════════════════════════════════════════════════════════════

class TestSPCAndSystem:

    def test_spc_returns_metrics(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/spc")
        assert r.status_code == 200
        body = r.json()
        assert body["cp"]  == 1.42
        assert body["cpk"] == 1.31
        assert body["samples"] == 250
        assert set(body["tier_cp"].keys()) == {"CRITICAL", "MAJOR", "MINOR"}

    def test_system_snapshot(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/system/snapshot")
        assert r.status_code == 200
        body = r.json()
        assert "cpu_percent" in body
        assert "ram_percent" in body


# ═══════════════════════════════════════════════════════════════════════════
# G-18-09  POST /reports/generate + GET /reports/{id}
# ═══════════════════════════════════════════════════════════════════════════

class TestReports:

    def test_generate_returns_id_and_status(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.post("/api/v1/reports/generate")
        assert r.status_code == 200
        body = r.json()
        assert body["report_id"] == "rpt-001"
        assert body["status"] == "generating"

    def test_get_report_pdf(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.get("/api/v1/reports/rpt-001")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")

    def test_get_report_unknown_returns_404(self, client_no_auth: TestClient) -> None:
        # On force le mock à renvoyer None
        deps, _ = _make_deps(auth_required=False)
        deps.report_generator.get_pdf_path = MagicMock(return_value=None)
        srv = WebServer(deps, host="127.0.0.1", port=0)
        r = TestClient(srv.app).get("/api/v1/reports/unknown")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# G-18-10  POST /auth/login
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthLogin:

    def test_login_returns_token(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["token"] == FakeAuthManager.VALID_TOKEN
        assert body["expires_in"] == 3600

    def test_login_invalid_credentials_401(self, client_no_auth: TestClient) -> None:
        r = client_no_auth.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# G-18-11  JWT auth — sans token → 401 sur endpoints protégés
# ═══════════════════════════════════════════════════════════════════════════

PROTECTED_GETS = [
    "/api/v1/results/last",
    "/api/v1/results/history",
    "/api/v1/tier_verdicts/last",
    "/api/v1/products",
    "/api/v1/spc",
    "/api/v1/system/snapshot",
]

PROTECTED_POSTS = [
    "/api/v1/inspection/start",
    "/api/v1/inspection/stop",
    "/api/v1/products/P208/activate",
    "/api/v1/reports/generate",
]


class TestJWTAuth:

    @pytest.mark.parametrize("path", PROTECTED_GETS)
    def test_protected_get_without_token_401(self, client_with_auth, path: str) -> None:
        client, _ = client_with_auth
        r = client.get(path)
        assert r.status_code == 401, f"{path} aurait dû renvoyer 401"

    @pytest.mark.parametrize("path", PROTECTED_POSTS)
    def test_protected_post_without_token_401(self, client_with_auth, path: str) -> None:
        client, _ = client_with_auth
        r = client.post(path)
        assert r.status_code == 401, f"{path} aurait dû renvoyer 401"

    def test_protected_with_valid_token_200(
        self, client_with_auth, auth_header: dict,
    ) -> None:
        client, _ = client_with_auth
        r = client.get("/api/v1/tier_verdicts/last", headers=auth_header)
        assert r.status_code == 200

    def test_invalid_token_401(self, client_with_auth) -> None:
        client, _ = client_with_auth
        r = client.get(
            "/api/v1/tier_verdicts/last",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
        assert r.status_code == 401

    def test_status_does_not_require_auth(self, client_with_auth) -> None:
        client, _ = client_with_auth
        r = client.get("/api/v1/status")
        assert r.status_code == 200

    def test_login_does_not_require_auth(self, client_with_auth) -> None:
        client, _ = client_with_auth
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# G-18-12  WebSocket — message contient tier_verdicts
# ═══════════════════════════════════════════════════════════════════════════

class TestWebSocketBroadcast:

    def test_message_format_full(self) -> None:
        msg = build_inspection_message(FakeFinalResult(verdict="NOK"))
        expected = {
            "type", "verdict", "severity", "fail_tier", "fail_reasons",
            "tier_scores", "tier_verdicts", "llm_summary", "pipeline_ms",
            "timestamp",
        }
        assert set(msg.keys()) == expected

    def test_message_type_is_inspection_result(self) -> None:
        msg = build_inspection_message(FakeFinalResult())
        assert msg["type"] == "inspection_result"

    def test_message_contains_tier_verdicts_dict(self) -> None:
        msg = build_inspection_message(FakeFinalResult(verdict="NOK"))
        assert "tier_verdicts" in msg
        assert set(msg["tier_verdicts"].keys()) == {"CRITICAL", "MAJOR", "MINOR"}
        # passed + fail_reasons par tier
        for tier in ("CRITICAL", "MAJOR", "MINOR"):
            assert "passed"       in msg["tier_verdicts"][tier]
            assert "fail_reasons" in msg["tier_verdicts"][tier]

    def test_message_tier_scores_dict(self) -> None:
        msg = build_inspection_message(FakeFinalResult())
        assert msg["tier_scores"] == {"CRITICAL": 0.94, "MAJOR": 0.22, "MINOR": 0.91}

    def test_message_enum_values_serialized(self) -> None:
        """fail_tier / severity → string, jamais l'objet enum."""
        msg = build_inspection_message(FakeFinalResult(verdict="NOK"))
        assert msg["fail_tier"] == "MAJOR"
        assert msg["severity"]  == "DEFECT_1"

    def test_broadcast_no_clients_no_loop_silent(self) -> None:
        """Aucun client + aucune boucle → no-op silencieux (GR-09)."""
        br = WSBroadcaster()
        # Ne doit jamais lever
        br.broadcast({"type": "test"})
        assert br.client_count == 0

    def test_broadcaster_attach_loop(self) -> None:
        import asyncio
        br   = WSBroadcaster()
        loop = asyncio.new_event_loop()
        try:
            br.attach_loop(loop)
            assert br._loop is loop
        finally:
            loop.close()

    def test_websocket_endpoint_connects_and_receives(
        self, client_no_auth: TestClient,
    ) -> None:
        """
        Connexion WS via TestClient + push d'un FinalResult →
        le client reçoit le payload JSON conforme.
        """
        # Le broadcaster est attaché à la loop dans on_event("startup").
        # TestClient déclenche les events de cycle de vie via context manager.
        with client_no_auth as c:
            with c.websocket_connect("/ws") as ws:
                # Récupère le serveur via l'app pour pousser un message
                # NB : TestClient ne fournit pas l'instance WebServer ; on
                # localise le broadcaster en remontant les routes.
                broadcaster = None
                for route in c.app.routes:
                    handler = getattr(route, "endpoint", None)
                    if handler and hasattr(handler, "__closure__") and handler.__closure__:
                        for cell in handler.__closure__:
                            if isinstance(cell.cell_contents, WSBroadcaster):
                                broadcaster = cell.cell_contents
                                break
                    if broadcaster:
                        break
                assert broadcaster is not None, "broadcaster introuvable"

                msg = build_inspection_message(FakeFinalResult(verdict="NOK"))
                broadcaster.broadcast(msg)

                received = ws.receive_json()
                assert received["type"] == "inspection_result"
                assert "tier_verdicts" in received
                assert set(received["tier_verdicts"].keys()) == {"CRITICAL", "MAJOR", "MINOR"}
