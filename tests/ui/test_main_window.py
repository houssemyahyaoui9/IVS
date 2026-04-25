"""
MainWindow — navigation tests
"""
from __future__ import annotations

from typing import Iterable

import pytest
from PyQt6.QtWidgets import QMenu, QToolBar

from camera.gpio_stub import GpioStubBackend
from core.gpio_manager import GpioManager
from core.pipeline_controller import SystemController
from core.ui_bridge import UIBridge
from ui.main_window import MainWindow, _PlaceholderTab


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def bridge():
    return UIBridge()


@pytest.fixture
def controller(bridge, tmp_path):
    products = tmp_path / "products"
    products.mkdir()
    return SystemController(bridge, products_dir=products, start_watchdog=False)


@pytest.fixture
def gpio(bridge):
    return GpioManager(
        {"gpio": {"enabled": True, "backend": "stub",
                  "pin_green": 17, "pin_red": 18}},
        bridge, backend=GpioStubBackend(),
    )


@pytest.fixture
def window(qapp, controller, bridge, gpio):
    win = MainWindow(controller=controller, ui_bridge=bridge,
                     gpio_manager=gpio, config={})
    yield win
    win.close()


def _menu(window: MainWindow, label: str) -> QMenu:
    return next(m for m in window.menuBar().findChildren(QMenu)
                if label in m.title())


def _action_texts(actions: Iterable) -> list[str]:
    return [a.text() for a in actions if a.text()]


# ─────────────────────────────────────────────────────────────────────────────
#  Onglets
# ─────────────────────────────────────────────────────────────────────────────

class TestTabs:
    def test_seven_tabs_present_in_order(self, window: MainWindow) -> None:
        assert window.tab_titles == (
            "Inspection", "Historique", "Analytics",
            "AI Monitoring", "GPIO Dashboard", "Fleet", "Paramètres",
        )

    def test_inspection_is_default(self, window: MainWindow) -> None:
        assert window.current_tab_title == "Inspection"

    def test_show_tab_switches(self, window: MainWindow) -> None:
        window.show_tab("GPIO Dashboard")
        assert window.current_tab_title == "GPIO Dashboard"
        window.show_tab("Inspection")
        assert window.current_tab_title == "Inspection"

    def test_show_tab_unknown_noop(self, window: MainWindow) -> None:
        window.show_tab("Inexistant")
        assert window.current_tab_title == "Inspection"

    def test_inspection_screen_mounted(self, window: MainWindow) -> None:
        from ui.screens.inspection_screen import InspectionScreen
        widget = window._tabs.widget(window._tab_indices["Inspection"])
        assert isinstance(widget, InspectionScreen)

    def test_gpio_dashboard_mounted_when_manager_provided(
        self, window: MainWindow,
    ) -> None:
        from ui.screens.gpio_dashboard_screen import GpioDashboardScreen
        widget = window._tabs.widget(window._tab_indices["GPIO Dashboard"])
        assert isinstance(widget, GpioDashboardScreen)

    def test_gpio_placeholder_when_no_manager(
        self, qapp, controller, bridge,
    ) -> None:
        win = MainWindow(controller=controller, ui_bridge=bridge,
                         gpio_manager=None)
        widget = win._tabs.widget(win._tab_indices["GPIO Dashboard"])
        assert isinstance(widget, _PlaceholderTab)

    def test_real_tab_implementations_mounted(self, window: MainWindow) -> None:
        # Historique / Analytics / AI Monitoring / Paramètres : implémentations réelles.
        from ui.tabs.ai_monitoring_tab import AIMonitoringTab
        from ui.tabs.analytics_tab import AnalyticsTab
        from ui.tabs.history_tab import HistoryTab
        from ui.tabs.settings_tab import SettingsTab

        expected = {
            "Historique":    HistoryTab,
            "Analytics":     AnalyticsTab,
            "AI Monitoring": AIMonitoringTab,
            "Paramètres":    SettingsTab,
        }
        for title, cls in expected.items():
            widget = window._tabs.widget(window._tab_indices[title])
            assert isinstance(widget, cls), (
                f"{title}: attendu {cls.__name__}, reçu {type(widget).__name__}"
            )
            assert not isinstance(widget, _PlaceholderTab), title


# ─────────────────────────────────────────────────────────────────────────────
#  Menu Fichier
# ─────────────────────────────────────────────────────────────────────────────

class TestFileMenu:
    def test_file_menu_present(self, window: MainWindow) -> None:
        menu = _menu(window, "Fichier")
        assert menu is not None

    def test_file_menu_contents(self, window: MainWindow) -> None:
        menu = _menu(window, "Fichier")
        labels = _action_texts(menu.actions())
        assert any("Nouveau produit" in l for l in labels)
        assert any("ROI Editor"      in l for l in labels)
        assert any("Formation"       in l for l in labels)
        assert any("Quitter"         in l for l in labels)

    def test_view_menu_has_tab_shortcuts(self, window: MainWindow) -> None:
        menu = _menu(window, "Affichage")
        labels = _action_texts(menu.actions())
        for title in window.TAB_TITLES:
            assert title in labels

    def test_view_menu_navigates(self, window: MainWindow) -> None:
        menu = _menu(window, "Affichage")
        gpio_action = next(a for a in menu.actions() if a.text() == "GPIO Dashboard")
        gpio_action.trigger()
        assert window.current_tab_title == "GPIO Dashboard"


# ─────────────────────────────────────────────────────────────────────────────
#  Toolbar
# ─────────────────────────────────────────────────────────────────────────────

class TestToolbar:
    def test_main_toolbar_present(self, window: MainWindow) -> None:
        bars = window.findChildren(QToolBar)
        assert any(tb.objectName() == "MainToolbar" for tb in bars)

    def test_toolbar_contains_plus_product(self, window: MainWindow) -> None:
        tb = next(t for t in window.findChildren(QToolBar)
                  if t.objectName() == "MainToolbar")
        labels = _action_texts(tb.actions())
        assert any("Produit" in l for l in labels)

    def test_toolbar_product_label_updates_on_signal(
        self, window: MainWindow, bridge: UIBridge,
    ) -> None:
        bridge.product_switched.emit("P208")
        assert "P208" in window._tb_product_label.text()


# ─────────────────────────────────────────────────────────────────────────────
#  Status bar
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusBar:
    def test_state_label_initial(self, window: MainWindow) -> None:
        assert "État" in window._sb_state.text()

    def test_state_label_updates_on_signal(
        self, window: MainWindow, bridge: UIBridge,
    ) -> None:
        bridge.state_changed.emit("RUNNING")
        assert "RUNNING" in window._sb_state.text()


# ─────────────────────────────────────────────────────────────────────────────
#  ROI Editor entry point
# ─────────────────────────────────────────────────────────────────────────────

class TestRoiEditorEntry:
    def test_roi_without_active_product_shows_info(
        self, window: MainWindow, monkeypatch,
    ) -> None:
        from PyQt6.QtWidgets import QMessageBox
        called: list[tuple] = []
        monkeypatch.setattr(
            QMessageBox, "information",
            lambda *args, **kw: called.append(args) or QMessageBox.StandardButton.Ok,
        )
        window._open_roi_editor()
        assert called, "QMessageBox.information aurait dû être appelé"
