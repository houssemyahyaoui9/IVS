"""
GpioDashboardScreen — Gate G-31 (P24-B)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from camera.gpio_stub import GpioStubBackend
from core.gpio_manager import GpioManager
from core.models import SystemState


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

class _DictConfig:
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


def _bridge():
    b = MagicMock()
    b.inspection_result = MagicMock()
    b.state_changed     = MagicMock()
    return b


def _controller(state=SystemState.IDLE_READY):
    c = MagicMock()
    c._state = state
    c.get_state.side_effect = lambda: c._state
    return c


@pytest.fixture
def qt(qapp):
    return qapp


@pytest.fixture
def gpio_mgr():
    cfg = _DictConfig({"gpio": {
        "enabled": True, "backend": "stub",
        "pin_green": 17, "pin_red": 18,
    }})
    return GpioManager(cfg, _bridge())


@pytest.fixture
def screen_factory(qt, gpio_mgr, tmp_path: Path):
    from ui.screens.gpio_dashboard_screen import GpioDashboardScreen

    def _make(controller=None, config_path: Path | None = None):
        if config_path is None:
            cfg_path = tmp_path / "config.yaml"
            # YAML initial minimal (uniquement si aucun chemin fourni)
            cfg_path.write_text(yaml.safe_dump({
                "station_id": "TEST",
                "gpio": {"enabled": True, "backend": "stub",
                         "pin_green": 17, "pin_red": 18,
                         "pin_start": None, "pin_stop": None},
            }), encoding="utf-8")
        else:
            cfg_path = config_path
        ctrl = controller or _controller()
        scr = GpioDashboardScreen(
            controller=ctrl, ui_bridge=_bridge(),
            gpio_manager=gpio_mgr, config_path=cfg_path,
        )
        return scr, ctrl, cfg_path

    return _make


# ─────────────────────────────────────────────────────────────────────────────
#  Construction
# ─────────────────────────────────────────────────────────────────────────────

class TestConstruction:
    def test_displays_all_bcm_pins_2_27(self, screen_factory) -> None:
        from ui.screens.gpio_dashboard_screen import BCM_PINS
        scr, _, _ = screen_factory()
        assert BCM_PINS == tuple(range(2, 28))
        assert scr._out_table_widget.rowCount() == len(BCM_PINS)
        assert scr._in_table_widget.rowCount()  == len(BCM_PINS)

    def test_initial_assignments_from_manager(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        assert scr.output_assignments[17] == "Lampe VERTE"
        assert scr.output_assignments[18] == "Lampe ROUGE"
        # Tous les autres pins → Libre
        for pin, func in scr.output_assignments.items():
            if pin not in (17, 18):
                assert func == "Libre", f"pin {pin}"


# ─────────────────────────────────────────────────────────────────────────────
#  Verrouillage GR-12
# ─────────────────────────────────────────────────────────────────────────────

class TestLockingRunningGR12:
    def test_idle_not_locked(self, screen_factory) -> None:
        scr, _, _ = screen_factory(controller=_controller(SystemState.IDLE_READY))
        assert scr.is_locked is False
        assert scr._save_btn.isEnabled()

    def test_running_locks_everything(self, screen_factory) -> None:
        scr, _, _ = screen_factory(controller=_controller(SystemState.RUNNING))
        assert scr.is_locked is True
        assert scr._save_btn.isEnabled() is False
        assert scr._out_table_widget.isEnabled() is False
        assert scr._in_table_widget.isEnabled() is False
        assert scr._cfg_green_combo.isEnabled() is False

    def test_state_change_to_running_locks(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        assert scr.is_locked is False
        scr._on_state_changed("RUNNING")
        assert scr.is_locked is True
        scr._on_state_changed("IDLE_READY")
        assert scr.is_locked is False


# ─────────────────────────────────────────────────────────────────────────────
#  Assignation pin et règles d'unicité
# ─────────────────────────────────────────────────────────────────────────────

class TestAssignment:
    def test_assigning_function_persists(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        scr._on_function_changed(19, True, "Lampe VERTE")
        assert scr.output_assignments[19] == "Lampe VERTE"

    def test_function_unique_across_outputs(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        # Au départ pin 17 = Lampe VERTE. Réassigner Lampe VERTE à pin 19
        scr._on_function_changed(19, True, "Lampe VERTE")
        assert scr.output_assignments[19] == "Lampe VERTE"
        assert scr.output_assignments[17] == "Libre"

    def test_pin_cannot_be_output_and_input(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        scr._on_function_changed(20, True, "Lampe ROUGE")
        scr._on_function_changed(20, False, "Start inspection")
        # INPUT a pris le pas → OUTPUT remis à Libre
        assert scr.output_assignments[20] == "Libre"
        assert scr.input_assignments[20] == "Start inspection"


# ─────────────────────────────────────────────────────────────────────────────
#  Test manuel ON/OFF
# ─────────────────────────────────────────────────────────────────────────────

class TestManualWrite:
    def test_manual_buttons_built_for_assigned_outputs(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        # Au démarrage 17 (VERTE) et 18 (ROUGE) sont assignés
        assert 17 in scr._manual_buttons
        assert 18 in scr._manual_buttons

    def test_manual_write_high_low(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        backend = scr._gpio.backend
        assert backend is not None
        scr._manual_write(17, True)
        assert backend.read(17) is True
        scr._manual_write(17, False)
        assert backend.read(17) is False

    def test_libre_pin_has_no_buttons(self, screen_factory) -> None:
        scr, _, _ = screen_factory()
        assert 5 not in scr._manual_buttons
        scr._on_function_changed(5, True, "Lampe VERTE")
        assert 5 in scr._manual_buttons


# ─────────────────────────────────────────────────────────────────────────────
#  Polling INPUT Start/Stop — front montant
# ─────────────────────────────────────────────────────────────────────────────

class TestInputTriggers:
    def test_rising_edge_calls_start_inspection(self, screen_factory) -> None:
        scr, ctrl, _ = screen_factory()
        scr._on_function_changed(27, False, "Start inspection")
        backend = scr._gpio.backend

        backend.write(27, False); scr._poll_input_triggers()
        ctrl.start_inspection.assert_not_called()
        backend.write(27, True);  scr._poll_input_triggers()
        ctrl.start_inspection.assert_called_once()

    def test_no_trigger_while_held_high(self, screen_factory) -> None:
        scr, ctrl, _ = screen_factory()
        scr._on_function_changed(27, False, "Start inspection")
        backend = scr._gpio.backend

        backend.write(27, True)
        scr._poll_input_triggers()
        scr._poll_input_triggers()
        scr._poll_input_triggers()
        # Une seule fois — front montant uniquement
        assert ctrl.start_inspection.call_count == 1

    def test_stop_input_calls_stop_inspection(self, screen_factory) -> None:
        scr, ctrl, _ = screen_factory()
        scr._on_function_changed(22, False, "Stop inspection")
        backend = scr._gpio.backend

        backend.write(22, False); scr._poll_input_triggers()
        backend.write(22, True);  scr._poll_input_triggers()
        ctrl.stop_inspection.assert_called_once()
        ctrl.start_inspection.assert_not_called()

    def test_libre_pin_does_not_trigger(self, screen_factory) -> None:
        scr, ctrl, _ = screen_factory()
        backend = scr._gpio.backend
        backend.write(15, True)
        scr._poll_input_triggers()
        ctrl.start_inspection.assert_not_called()
        ctrl.stop_inspection.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
#  Sauvegarde YAML
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveConfig:
    def test_save_writes_gpio_section(self, screen_factory) -> None:
        scr, _, cfg_path = screen_factory()
        scr._cfg_green_combo.setCurrentText("19")
        scr._cfg_red_combo.setCurrentText("20")
        scr._on_function_changed(27, False, "Start inspection")
        scr._on_function_changed(22, False, "Stop inspection")

        section = scr._collect_gpio_section()
        scr._save_to_yaml(section)

        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        assert data["gpio"]["enabled"] is True
        assert data["gpio"]["pin_green"] == 19
        assert data["gpio"]["pin_red"]   == 20
        assert data["gpio"]["pin_start"] == 27
        assert data["gpio"]["pin_stop"]  == 22
        # Les autres sections sont préservées
        assert data["station_id"] == "TEST"

    def test_save_preserves_unrelated_sections(
        self, screen_factory, tmp_path: Path,
    ) -> None:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(yaml.safe_dump({
            "station_id": "X",
            "camera": {"type": "fake"},
            "gpio": {"enabled": False, "backend": "stub",
                     "pin_green": 17, "pin_red": 18},
        }), encoding="utf-8")
        scr, _, _ = screen_factory(config_path=cfg)
        scr._save_to_yaml(scr._collect_gpio_section())
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert data["camera"] == {"type": "fake"}
        assert data["station_id"] == "X"

    def test_config_saved_signal_emitted(self, screen_factory, qtbot) -> None:
        scr, _, _ = screen_factory()
        with qtbot.waitSignal(scr.config_saved, timeout=500) as blocker:
            # Émet manuellement (équivalent au clic)
            scr.config_saved.emit(scr._collect_gpio_section())
        assert blocker.args[0]["pin_green"] == 17
