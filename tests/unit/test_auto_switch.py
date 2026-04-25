"""
AutoSwitch — Gate G-22E
Couvre :
  - ProductRegistry.lookup() → product_id correct (et None si inconnu)
  - ProductScanner.start + subscribe + debounce
  - AutoSwitchManager.handle_scan() → ALREADY_ACTIVE / SUCCESS / FAILED
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.auto_switch_manager import AutoSwitchManager
from core.models import SwitchResult, SystemState
from core.product_registry import ProductRegistry
from core.product_scanner import ProductScanner


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _write_product(root: Path, product_id: str, *, barcode: str,
                   auto_switch: bool = True) -> None:
    pdir = root / product_id
    pdir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "product_id":          product_id,
        "product_name":        product_id.title(),
        "product_version":     "1.0",
        "physical_dimensions": {"width_mm": 100.0, "height_mm": 100.0},
        "logo_definitions":    [],
        "product_barcode":     barcode,
        "auto_switch_enabled": auto_switch,
        "product_rules":       {"criteria": []},
    }
    (pdir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


@pytest.fixture
def products_dir(tmp_path: Path) -> Path:
    root = tmp_path / "products"
    _write_product(root, "alpha", barcode="ABC-001")
    _write_product(root, "bravo", barcode="ABC-002")
    _write_product(root, "charlie", barcode="ABC-003", auto_switch=False)
    return root


@pytest.fixture
def registry(products_dir: Path) -> ProductRegistry:
    return ProductRegistry(products_dir)


# ─────────────────────────────────────────────────────────────────────────────
#  ProductRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestProductRegistry:
    def test_lookup_returns_correct_product_id(self, registry: ProductRegistry) -> None:
        assert registry.lookup("ABC-001") == "alpha"
        assert registry.lookup("ABC-002") == "bravo"

    def test_lookup_unknown_barcode_returns_none(self, registry: ProductRegistry) -> None:
        assert registry.lookup("UNKNOWN") is None
        assert registry.lookup("") is None

    def test_lookup_strips_whitespace(self, registry: ProductRegistry) -> None:
        assert registry.lookup("  ABC-001  ") == "alpha"

    def test_auto_switch_disabled_not_indexed(self, registry: ProductRegistry) -> None:
        # 'charlie' a auto_switch_enabled=False → barcode non indexé
        assert registry.lookup("ABC-003") is None
        # mais le produit reste connu
        assert registry.has_product("charlie") is True

    def test_reload_picks_up_new_product(
        self, products_dir: Path, registry: ProductRegistry,
    ) -> None:
        assert registry.lookup("ABC-999") is None
        _write_product(products_dir, "delta", barcode="ABC-999")
        n = registry.reload()
        assert n == 3
        assert registry.lookup("ABC-999") == "delta"


# ─────────────────────────────────────────────────────────────────────────────
#  AutoSwitchManager
# ─────────────────────────────────────────────────────────────────────────────

def _mock_controller(state: SystemState, active: str | None = None) -> MagicMock:
    ctrl = MagicMock()
    ctrl.get_state.return_value = state
    type(ctrl).active_product_id = property(lambda self: active)
    return ctrl


class TestAutoSwitchManager:
    def test_already_active_returns_already_active(
        self, registry: ProductRegistry,
    ) -> None:
        ctrl = _mock_controller(SystemState.IDLE_READY, active="alpha")
        mgr  = AutoSwitchManager(ctrl, registry)
        assert mgr.handle_scan("alpha") == SwitchResult.ALREADY_ACTIVE
        ctrl.activate_product.assert_not_called()
        ctrl.stop_inspection.assert_not_called()

    def test_unknown_product_returns_failed(
        self, registry: ProductRegistry,
    ) -> None:
        ctrl = _mock_controller(SystemState.IDLE_READY, active="alpha")
        mgr  = AutoSwitchManager(ctrl, registry)
        assert mgr.handle_scan("zulu") == SwitchResult.FAILED
        ctrl.activate_product.assert_not_called()

    def test_idle_ready_activates_product(
        self, registry: ProductRegistry,
    ) -> None:
        ctrl = _mock_controller(SystemState.IDLE_READY, active="alpha")
        mgr  = AutoSwitchManager(ctrl, registry)
        result = mgr.handle_scan("bravo")
        assert result == SwitchResult.SUCCESS
        ctrl.activate_product.assert_called_once_with("bravo")
        ctrl.stop_inspection.assert_not_called()

    def test_training_state_refused(self, registry: ProductRegistry) -> None:
        ctrl = _mock_controller(SystemState.TRAINING, active="alpha")
        mgr  = AutoSwitchManager(ctrl, registry)
        assert mgr.handle_scan("bravo") == SwitchResult.FAILED
        ctrl.activate_product.assert_not_called()

    def test_calibrating_state_refused(self, registry: ProductRegistry) -> None:
        ctrl = _mock_controller(SystemState.CALIBRATING, active="alpha")
        mgr  = AutoSwitchManager(ctrl, registry)
        assert mgr.handle_scan("bravo") == SwitchResult.FAILED
        ctrl.activate_product.assert_not_called()

    def test_running_stops_then_switches_under_3s(
        self, registry: ProductRegistry,
    ) -> None:
        # ctrl simule une transition RUNNING → IDLE_READY après stop_inspection
        ctrl = MagicMock()
        ctrl._state = SystemState.RUNNING
        type(ctrl).active_product_id = property(lambda self: "alpha")
        ctrl.get_state.side_effect = lambda: ctrl._state

        def _stop():
            ctrl._state = SystemState.IDLE_READY
        ctrl.stop_inspection.side_effect = _stop

        mgr = AutoSwitchManager(ctrl, registry)
        t0 = time.monotonic()
        result = mgr.handle_scan("bravo")
        elapsed = time.monotonic() - t0

        assert result == SwitchResult.SUCCESS
        assert elapsed < 3.0
        ctrl.stop_inspection.assert_called_once()
        ctrl.activate_product.assert_called_once_with("bravo")


# ─────────────────────────────────────────────────────────────────────────────
#  ProductScanner
# ─────────────────────────────────────────────────────────────────────────────

class _StubDecoder:
    def __init__(self, code: str | None) -> None:
        self.code = code
        self.calls = 0

    def decode(self, frame: np.ndarray):  # noqa: ARG002
        self.calls += 1
        return self.code


class TestProductScanner:
    def _frame(self) -> np.ndarray:
        return np.zeros((100, 100, 3), dtype=np.uint8)

    def test_start_subscribe_and_emit(self, registry: ProductRegistry) -> None:
        decoder = _StubDecoder("ABC-001")
        seen: list[str] = []
        evt = threading.Event()

        def cb(pid: str) -> None:
            seen.append(pid)
            evt.set()

        scanner = ProductScanner(
            frame_source = self._frame,
            registry     = registry,
            decoder      = decoder,
            interval_ms  = 50,
            debounce_s   = 0.0,
        )
        scanner.subscribe(cb)
        scanner.start()
        try:
            assert evt.wait(timeout=2.0), "callback non appelé"
            assert "alpha" in seen
            assert scanner.is_running
        finally:
            scanner.stop()
        assert not scanner.is_running

    def test_unknown_barcode_does_not_emit(self, registry: ProductRegistry) -> None:
        decoder = _StubDecoder("UNKNOWN-CODE")
        seen: list[str] = []
        scanner = ProductScanner(
            frame_source = self._frame,
            registry     = registry,
            decoder      = decoder,
            interval_ms  = 30,
            debounce_s   = 0.0,
        )
        scanner.subscribe(seen.append)
        scanner.start()
        try:
            time.sleep(0.2)
        finally:
            scanner.stop()
        assert seen == []
        assert decoder.calls > 0

    def test_debounce_blocks_repeated_emissions(
        self, registry: ProductRegistry,
    ) -> None:
        decoder = _StubDecoder("ABC-001")
        seen: list[str] = []
        scanner = ProductScanner(
            frame_source = self._frame,
            registry     = registry,
            decoder      = decoder,
            interval_ms  = 30,
            debounce_s   = 5.0,   # debounce long → une seule émission
        )
        scanner.subscribe(seen.append)
        scanner.start()
        try:
            time.sleep(0.4)
        finally:
            scanner.stop()
        assert seen == ["alpha"]   # une seule émission malgré plusieurs ticks

    def test_invalid_interval_rejected(self, registry: ProductRegistry) -> None:
        with pytest.raises(ValueError):
            ProductScanner(
                frame_source=self._frame, registry=registry, interval_ms=0,
            )
