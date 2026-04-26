"""
ui/theme/colors.py — TS2I IVS v9.0
Palette ABC frozen — base des thèmes Light / Dark (S25-v9).
GR-V8-2 : tous les écrans héritent du thème global (pas de styles inline).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    """
    Palette de base — tous les thèmes héritent de cette structure.
    Tous les champs sont des chaînes CSS (hex, rgba, etc).
    """

    name: str = "base"

    bg_primary: str = "#ffffff"
    bg_secondary: str = "#f0f0f0"
    bg_tertiary: str = "#e8e8e8"
    bg_grid: str = "#fafafa"

    text_primary: str = "#000000"
    text_secondary: str = "#333333"
    text_muted: str = "#777777"
    text_disabled: str = "#aaaaaa"

    success: str = "#16a34a"
    warning: str = "#ea580c"
    danger: str = "#dc2626"
    review: str = "#7c3aed"
    info: str = "#1d4ed8"

    accent_primary: str = "#1d4ed8"
    accent_secondary: str = "#2563eb"

    border_subtle: str = "#e0e0e0"
    border_default: str = "#c0c0c0"
    border_strong: str = "#a0a0a0"

    shadow: str = "rgba(0,0,0,0.1)"
    glow: str = "none"
