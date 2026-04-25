"""
GpioManager + GpioStubBackend — Gate G-30 (P24-A)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from camera.gpio_stub import GpioStubBackend
from core.gpio_manager import GpioBackend, GpioManager


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

class _DictConfig:
    """Adaptateur dict → API ConfigManager.get()."""
    def __init__(self, data: dict) -> None:
        self._data = data

    def get(self, key: str, default=None):
        node = self._data
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node


def _config(enabled=True, pin_green=17, pin_red=18, backend="stub"):
    return _DictConfig({"gpio": {
        "enabled": enabled,
        "pin_green": pin_green,
        "pin_red": pin_red,
        "backend": backend,
    }})


def _bridge():
    """Mock UIBridge avec un signal MagicMock()."""
    b = MagicMock()
    b.inspection_result = MagicMock()
    return b


def _final(verdict: str):
    obj = MagicMock()
    obj.verdict = verdict
    return obj


# ─────────────────────────────────────────────────────────────────────────────
#  GpioStubBackend
# ─────────────────────────────────────────────────────────────────────────────

class TestGpioStubBackend:
    def test_setup_output_then_write_read(self) -> None:
        b = GpioStubBackend()
        b.setup_output(17)
        b.write(17, True)
        assert b.read(17) is True
        b.write(17, False)
        assert b.read(17) is False

    def test_write_without_setup_warns_but_works(self) -> None:
        b = GpioStubBackend()
        b.write(22, True)  # ne plante pas
        assert b.read(22) is True
        assert 22 in b.outputs

    def test_setup_input_recorded(self) -> None:
        b = GpioStubBackend()
        b.setup_input(23)
        assert b.read(23) is False  # défaut

    def test_cleanup_clears_state(self) -> None:
        b = GpioStubBackend()
        b.setup_output(17)
        b.write(17, True)
        b.cleanup()
        assert b.is_cleaned_up
        assert b.state == {}

    def test_implements_abc(self) -> None:
        assert isinstance(GpioStubBackend(), GpioBackend)


# ─────────────────────────────────────────────────────────────────────────────
#  GpioManager — disabled
# ─────────────────────────────────────────────────────────────────────────────

class TestGpioManagerDisabled:
    def test_disabled_does_not_build_backend(self) -> None:
        mgr = GpioManager(_config(enabled=False), _bridge())
        assert mgr.backend is None

    def test_disabled_start_is_noop(self) -> None:
        bridge = _bridge()
        mgr = GpioManager(_config(enabled=False), bridge)
        mgr.start()
        bridge.inspection_result.connect.assert_not_called()
        assert not mgr.is_connected

    def test_disabled_on_result_does_nothing(self) -> None:
        mgr = GpioManager(_config(enabled=False), _bridge())
        mgr.on_result(_final("OK"))  # ne lève pas


# ─────────────────────────────────────────────────────────────────────────────
#  GpioManager — enabled (stub backend)
# ─────────────────────────────────────────────────────────────────────────────

class TestGpioManagerEnabled:
    def test_setup_outputs_and_initial_state_off(self) -> None:
        mgr = GpioManager(_config(), _bridge())
        backend = mgr.backend
        assert isinstance(backend, GpioStubBackend)
        assert {17, 18} <= backend.outputs
        # Reset après setup
        assert backend.read(17) is False
        assert backend.read(18) is False

    def test_start_connects_signal(self) -> None:
        bridge = _bridge()
        mgr = GpioManager(_config(), bridge)
        mgr.start()
        bridge.inspection_result.connect.assert_called_once_with(mgr.on_result)
        assert mgr.is_connected

    def test_start_idempotent(self) -> None:
        bridge = _bridge()
        mgr = GpioManager(_config(), bridge)
        mgr.start()
        mgr.start()
        assert bridge.inspection_result.connect.call_count == 1

    def test_on_result_ok_turns_green_on_red_off(self) -> None:
        mgr = GpioManager(_config(), _bridge())
        backend = mgr.backend
        backend.write(18, True)  # rouge déjà allumé
        mgr.on_result(_final("OK"))
        assert backend.read(17) is True
        assert backend.read(18) is False

    def test_on_result_nok_turns_red_on_green_off(self) -> None:
        mgr = GpioManager(_config(), _bridge())
        backend = mgr.backend
        backend.write(17, True)  # vert déjà allumé
        mgr.on_result(_final("NOK"))
        assert backend.read(18) is True
        assert backend.read(17) is False

    def test_on_result_review_keeps_all_off(self) -> None:
        mgr = GpioManager(_config(), _bridge())
        backend = mgr.backend
        backend.write(17, True)
        backend.write(18, True)
        mgr.on_result(_final("REVIEW"))
        assert backend.read(17) is False
        assert backend.read(18) is False

    def test_invalid_verdict_ignored(self) -> None:
        mgr = GpioManager(_config(), _bridge())
        backend = mgr.backend
        backend.write(17, True)
        mgr.on_result(_final("UNKNOWN"))
        # État inchangé (pas de reset)
        assert backend.read(17) is True

    def test_custom_pins(self) -> None:
        mgr = GpioManager(_config(pin_green=5, pin_red=6), _bridge())
        assert mgr.pin_green == 5
        assert mgr.pin_red == 6
        backend = mgr.backend
        mgr.on_result(_final("OK"))
        assert backend.read(5) is True
        assert backend.read(6) is False

    def test_invalid_backend_raises(self) -> None:
        with pytest.raises(ValueError):
            GpioManager(_config(backend="unknown"), _bridge())

    def test_stop_disconnects_and_cleans(self) -> None:
        bridge = _bridge()
        mgr = GpioManager(_config(), bridge)
        mgr.start()
        backend = mgr.backend
        mgr.on_result(_final("OK"))
        assert backend.read(17) is True

        mgr.stop()
        bridge.inspection_result.disconnect.assert_called_once_with(mgr.on_result)
        assert not mgr.is_connected
        assert backend.is_cleaned_up

    def test_injected_backend_used(self) -> None:
        custom = GpioStubBackend()
        mgr = GpioManager(_config(), _bridge(), backend=custom)
        assert mgr.backend is custom


# ─────────────────────────────────────────────────────────────────────────────
#  Compatibilité config dict (pas seulement ConfigManager)
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigCompat:
    def test_plain_dict_supported(self) -> None:
        cfg_dict = {"gpio": {"enabled": True, "pin_green": 17,
                             "pin_red": 18, "backend": "stub"}}
        mgr = GpioManager(cfg_dict, _bridge())
        assert mgr.backend is not None
        assert mgr.pin_green == 17

    def test_missing_keys_use_defaults(self) -> None:
        mgr = GpioManager({"gpio": {"enabled": True}}, _bridge())
        assert mgr.pin_green == 17
        assert mgr.pin_red == 18
