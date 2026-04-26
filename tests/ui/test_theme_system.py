"""
tests/ui/test_theme_system.py — TS2I IVS v9.0
Gate G-S25-v9 : ThemeManager + Light/Dark palettes + QSS coverage.
"""
from __future__ import annotations

import pytest

from ui.theme.colors import ThemePalette
from ui.theme.presets.dark import DarkPalette
from ui.theme.presets.light import LightPalette
from ui.theme.styles import generate_qss
from ui.theme.theme_manager import ThemeManager


# ─────────────────────────────────────────────────────────────────────────────
#  QApplication fixture (fallback — pytest-qt non installé)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_theme_singleton():
    ThemeManager._reset()
    yield
    ThemeManager._reset()


# ─────────────────────────────────────────────────────────────────────────────
#  Palettes
# ─────────────────────────────────────────────────────────────────────────────

class TestPalettes:
    def test_light_palette_frozen(self):
        p = LightPalette()
        assert p.name == "light"
        with pytest.raises(Exception):
            p.bg_primary = "#000000"  # frozen=True

    def test_dark_palette_frozen(self):
        p = DarkPalette()
        assert p.name == "dark"
        with pytest.raises(Exception):
            p.bg_primary = "#ffffff"

    def test_light_has_required_fields(self):
        p = LightPalette()
        for field in ["bg_primary", "bg_secondary", "bg_tertiary", "bg_grid",
                      "text_primary", "text_secondary", "text_muted", "text_disabled",
                      "success", "warning", "danger", "review", "info",
                      "accent_primary", "accent_secondary",
                      "border_subtle", "border_default", "border_strong",
                      "shadow", "glow"]:
            assert hasattr(p, field), f"Light palette manque {field}"
            assert getattr(p, field), f"Light palette {field} vide"

    def test_dark_has_required_fields(self):
        p = DarkPalette()
        for field in ["bg_primary", "bg_secondary", "bg_tertiary", "bg_grid",
                      "text_primary", "text_secondary", "text_muted", "text_disabled",
                      "success", "warning", "danger", "review", "info",
                      "accent_primary", "accent_secondary",
                      "border_subtle", "border_default", "border_strong",
                      "shadow", "glow"]:
            assert hasattr(p, field), f"Dark palette manque {field}"
            assert getattr(p, field), f"Dark palette {field} vide"

    def test_light_dark_have_distinct_colors(self):
        l, d = LightPalette(), DarkPalette()
        assert l.bg_primary != d.bg_primary
        assert l.text_primary != d.text_primary
        assert l.accent_primary != d.accent_primary


# ─────────────────────────────────────────────────────────────────────────────
#  QSS generation (Gate G-S25-v9)
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_WIDGETS = [
    "QPushButton", "QLabel", "QTableWidget", "QTabWidget",
    "QLineEdit", "QScrollBar", "QComboBox",
]


class TestQssGeneration:
    @pytest.mark.parametrize("palette_cls", [LightPalette, DarkPalette])
    def test_qss_length_minimum(self, palette_cls):
        qss = generate_qss(palette_cls())
        assert len(qss) > 3000, f"{palette_cls.__name__} QSS trop court : {len(qss)}"

    @pytest.mark.parametrize("palette_cls", [LightPalette, DarkPalette])
    def test_qss_covers_all_widgets(self, palette_cls):
        qss = generate_qss(palette_cls())
        for w in REQUIRED_WIDGETS:
            assert w in qss, f"{w} manquant dans QSS {palette_cls.__name__}"

    @pytest.mark.parametrize("palette_cls", [LightPalette, DarkPalette])
    def test_qss_tabs_north_alignment(self, palette_cls):
        """GR-V9-8 : tabs en position North uniquement."""
        qss = generate_qss(palette_cls())
        assert "QTabWidget::tab-bar" in qss
        assert "alignment: left" in qss

    @pytest.mark.parametrize("palette_cls", [LightPalette, DarkPalette])
    def test_qss_uses_palette_colors(self, palette_cls):
        p = palette_cls()
        qss = generate_qss(p)
        # Au moins quelques couleurs clés doivent être présentes
        assert p.bg_primary in qss
        assert p.text_primary in qss
        assert p.accent_primary in qss


# ─────────────────────────────────────────────────────────────────────────────
#  ThemeManager singleton + apply()
# ─────────────────────────────────────────────────────────────────────────────

class TestThemeManager:
    def test_singleton_returns_same_instance(self, qapp):
        a = ThemeManager.instance()
        b = ThemeManager.instance()
        assert a is b

    def test_available_themes(self, qapp):
        tm = ThemeManager.instance()
        themes = tm.available_themes()
        assert sorted(themes) == ["dark", "light"]
        assert len(themes) == 2  # GR : exactement 2 thèmes en v9

    def test_apply_light_sets_current(self, qapp):
        tm = ThemeManager.instance()
        tm.apply("light")
        assert tm.current_theme() == "light"

    def test_apply_dark_sets_current(self, qapp):
        tm = ThemeManager.instance()
        tm.apply("dark")
        assert tm.current_theme() == "dark"

    def test_apply_unknown_falls_back_light(self, qapp):
        tm = ThemeManager.instance()
        tm.apply("does_not_exist")
        assert tm.current_theme() == "light"

    def test_apply_emits_signal(self, qapp):
        tm = ThemeManager.instance()
        received: list[str] = []
        tm.themeChanged.connect(received.append)
        tm.apply("dark")
        # Forcer le traitement des évènements pour signal direct
        qapp.processEvents()
        assert "dark" in received

    def test_apply_actually_sets_stylesheet(self, qapp):
        tm = ThemeManager.instance()
        tm.apply("dark")
        ss = qapp.styleSheet()
        assert len(ss) > 3000
        assert "QPushButton" in ss

    def test_palette_returns_correct_instance(self, qapp):
        tm = ThemeManager.instance()
        assert isinstance(tm.palette("light"), LightPalette)
        assert isinstance(tm.palette("dark"), DarkPalette)

    def test_hot_swap_light_to_dark(self, qapp):
        """GR-V8-5 : commutable à chaud."""
        tm = ThemeManager.instance()
        tm.apply("light")
        ss_light = qapp.styleSheet()
        tm.apply("dark")
        ss_dark = qapp.styleSheet()
        assert ss_light != ss_dark
        assert tm.current_theme() == "dark"
