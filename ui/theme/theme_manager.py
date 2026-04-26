"""
ui/theme/theme_manager.py — TS2I IVS v9.0
ThemeManager singleton — applique le thème global.

GR-V9-2 : apply() DOIT être appelé AVANT QMainWindow.show().
GR-V8-5 : commutable à chaud sans redémarrage (signal themeChanged).
GR-05  : signal Qt cross-thread safe.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from ui.theme.colors import ThemePalette
from ui.theme.presets.dark import DarkPalette
from ui.theme.presets.light import LightPalette
from ui.theme.styles import generate_qss


class ThemeManager(QObject):
    """
    Singleton — un seul ThemeManager par processus.

    Usage :
        theme = ThemeManager.instance()
        theme.apply("light")           # AVANT window.show() — GR-V9-2
        theme.themeChanged.connect(my_widget.refresh)
    """

    THEMES: dict[str, type[ThemePalette]] = {
        "light": LightPalette,
        "dark": DarkPalette,
    }

    themeChanged = pyqtSignal(str)
    """Émis après chaque apply() — argument = nom du thème courant."""

    _instance: Optional["ThemeManager"] = None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current: str = "light"

    # ── Singleton ──────────────────────────────────────────────────────────

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        """Tests uniquement — réinitialise le singleton."""
        cls._instance = None

    # ── API publique ───────────────────────────────────────────────────────

    def apply(self, theme_name: str) -> None:
        """
        Applique un thème globalement à l'application Qt.

        GR-V9-2 : appeler AVANT QMainWindow.show().
        GR-V8-5 : commutable à chaud — émet themeChanged après application.
        Si le nom est inconnu, fallback silencieux sur LightPalette.
        """
        palette_cls = self.THEMES.get(theme_name, LightPalette)
        palette = palette_cls()
        qss = generate_qss(palette)

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)

        self._current = palette.name
        self.themeChanged.emit(self._current)

    def current_theme(self) -> str:
        """Nom du thème actuellement appliqué."""
        return self._current

    def available_themes(self) -> list[str]:
        """Liste des thèmes disponibles (clés du dict THEMES)."""
        return list(self.THEMES.keys())

    def palette(self, theme_name: str | None = None) -> ThemePalette:
        """Retourne l'instance ThemePalette du thème (défaut : courant)."""
        name = theme_name or self._current
        return self.THEMES.get(name, LightPalette)()
