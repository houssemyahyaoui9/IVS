"""
LuminosityIndicator — pastille verte/jaune/rouge + valeur — §42.
GR-03 : update via UIBridge.luminosity_update signal.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget


class LuminosityIndicator(QWidget):
    """Affiche : pastille colorée + valeur (0-255) + delta% par rapport à la réf."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self._dot.setStyleSheet("color:#888;")

        self._text = QLabel("Lum : —")
        self._text.setFont(QFont("Arial", 9))

        layout.addWidget(self._dot)
        layout.addWidget(self._text)

    def update_luminosity(self, lum: Optional[object]) -> None:
        """Reçoit un LuminosityResult (ou objet équivalent : value/delta_percent/ok/warning/critical)."""
        if lum is None:
            self._dot.setStyleSheet("color:#888;")
            self._text.setText("Lum : —")
            return

        value         = float(getattr(lum, "value", 0.0))
        delta_percent = float(getattr(lum, "delta_percent", 0.0))
        critical      = bool(getattr(lum, "critical", False))
        warning       = bool(getattr(lum, "warning", False))

        if critical:
            color = "#E53935"
        elif warning:
            color = "#FBC02D"
        else:
            color = "#43A047"

        self._dot.setStyleSheet(f"color:{color};")
        self._text.setText(f"Lum : {value:.0f}  Δ {delta_percent:.1f}%")
