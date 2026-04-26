"""
ui/theme/presets/dark.py — TS2I IVS v9.0
Palette Dark industrielle (S25-v9). Fond #0d1117 / accent cyan.
REMPLACE cognex/keyence/halcon de v8.
"""
from __future__ import annotations

from dataclasses import dataclass

from ui.theme.colors import ThemePalette


@dataclass(frozen=True)
class DarkPalette(ThemePalette):
    name: str = "dark"

    bg_primary: str = "#0d1117"
    bg_secondary: str = "#161b22"
    bg_tertiary: str = "#21262d"
    bg_grid: str = "#010409"

    text_primary: str = "#e6edf3"
    text_secondary: str = "#c9d1d9"
    text_muted: str = "#8b949e"
    text_disabled: str = "#484f58"

    success: str = "#4ade80"
    warning: str = "#fb923c"
    danger: str = "#f87171"
    review: str = "#c084fc"
    info: str = "#06b6d4"

    accent_primary: str = "#06b6d4"
    accent_secondary: str = "#0891b2"

    border_subtle: str = "#21262d"
    border_default: str = "#30363d"
    border_strong: str = "#484f58"

    shadow: str = "rgba(0,0,0,0.4)"
    glow: str = "0 0 8px rgba(6,182,212,0.3)"
