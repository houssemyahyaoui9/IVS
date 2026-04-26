"""
ui.theme — TS2I IVS v9.0
Système de thème centralisé (S25-v9).
GR-V9-2 / GR-V8-2 / GR-V8-5 / GR-V9-8.
"""
from ui.theme.colors import ThemePalette
from ui.theme.presets.dark import DarkPalette
from ui.theme.presets.light import LightPalette
from ui.theme.styles import generate_qss
from ui.theme.theme_manager import ThemeManager

__all__ = [
    "ThemeManager",
    "ThemePalette",
    "LightPalette",
    "DarkPalette",
    "generate_qss",
]
