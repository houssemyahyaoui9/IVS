"""
ui/theme/presets/light.py — TS2I IVS v9.0
Palette Light industrielle (S25-v9). Blanc / texte noir.
"""
from __future__ import annotations

from dataclasses import dataclass

from ui.theme.colors import ThemePalette


@dataclass(frozen=True)
class LightPalette(ThemePalette):
    name: str = "light"

    bg_primary: str = "#ffffff"
    bg_secondary: str = "#f6f6f6"
    bg_tertiary: str = "#f0f0f0"
    bg_grid: str = "#fafafa"

    text_primary: str = "#111111"
    text_secondary: str = "#444444"
    text_muted: str = "#888888"
    text_disabled: str = "#bbbbbb"

    success: str = "#16a34a"
    warning: str = "#ea580c"
    danger: str = "#dc2626"
    review: str = "#7c3aed"
    info: str = "#1d4ed8"

    accent_primary: str = "#1d4ed8"
    accent_secondary: str = "#2563eb"

    border_subtle: str = "#e8e8e8"
    border_default: str = "#d0d0d0"
    border_strong: str = "#b0b0b0"

    shadow: str = "rgba(0,0,0,0.1)"
    glow: str = "none"
