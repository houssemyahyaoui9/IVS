"""
NokCounterBadge — compteur NOK persistant par session — §41.
GR-03 : update via UIBridge.nok_counter_update signal.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QSizePolicy


class NokCounterBadge(QLabel):
    """Pastille rouge affichant le nombre de NOK depuis le démarrage."""

    def __init__(self, count: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.setMinimumSize(64, 28)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._count = 0
        self.set_count(count)

    @property
    def count(self) -> int:
        return self._count

    def set_count(self, count: int) -> None:
        self._count = max(0, int(count))
        self.setText(f"NOK · {self._count}")
        # Couleur : grise si 0, rouge sinon (intensité légère selon volume)
        if self._count == 0:
            bg, fg = "#2a2a2a", "#888"
        elif self._count < 5:
            bg, fg = "#8E0000", "#fff"
        else:
            bg, fg = "#B71C1C", "#fff"
        self.setStyleSheet(
            f"QLabel {{ background:{bg}; color:{fg};"
            " border-radius:14px; padding:2px 12px; }"
        )

    def reset(self) -> None:
        self.set_count(0)
