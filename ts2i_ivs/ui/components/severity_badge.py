"""
SeverityBadge — pastille colorée par SeverityLevel — §12.
GR-05 : opérations Qt dans le thread principal.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QSizePolicy

from ts2i_ivs.core.models import SeverityLevel


_SEVERITY_STYLE: dict[SeverityLevel, tuple[str, str]] = {
    SeverityLevel.EXCELLENT  : ("#0E5C2F", "#FFFFFF"),
    SeverityLevel.ACCEPTABLE : ("#1B5E20", "#FFFFFF"),
    SeverityLevel.REVIEW     : ("#F57F17", "#000000"),
    SeverityLevel.DEFECT_2   : ("#E65100", "#FFFFFF"),
    SeverityLevel.DEFECT_1   : ("#BF360C", "#FFFFFF"),
    SeverityLevel.REJECT     : ("#B71C1C", "#FFFFFF"),
}


class SeverityBadge(QLabel):
    """Affiche un SeverityLevel avec couleur de fond dédiée."""

    def __init__(self, severity: Optional[SeverityLevel] = None, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(28)
        self.setMinimumWidth(110)
        self.setContentsMargins(8, 4, 8, 4)
        self.set_severity(severity)

    def set_severity(self, severity: Optional[SeverityLevel]) -> None:
        if severity is None:
            self.setText("—")
            self.setStyleSheet(
                "QLabel { background:#444; color:#ddd; border-radius:6px;"
                " padding:4px 10px; }"
            )
            return
        bg, fg = _SEVERITY_STYLE.get(severity, ("#444", "#ddd"))
        self.setText(severity.value)
        self.setStyleSheet(
            f"QLabel {{ background:{bg}; color:{fg};"
            " border-radius:6px; padding:4px 10px; }"
        )
