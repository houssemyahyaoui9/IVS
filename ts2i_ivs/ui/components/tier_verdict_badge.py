"""
TierVerdictBadge — un badge par Tier · TierVerdictBadgeRow regroupe les 3.
GR-04 : observe ; aucune logique verdict ici.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from ts2i_ivs.core.tier_result import TierLevel, TierVerdict


_TIER_BORDER: dict[TierLevel, str] = {
    TierLevel.CRITICAL: "#FF4444",
    TierLevel.MAJOR:    "#FF8800",
    TierLevel.MINOR:    "#FFCC00",
}


class TierVerdictBadge(QFrame):
    """Badge d'un Tier : icône ✅/❌/⏳ + score interne en petit (analytics)."""

    def __init__(self, tier: TierLevel, parent=None) -> None:
        super().__init__(parent)
        self._tier = tier
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(140, 64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        header = QHBoxLayout()
        self._label_tier = QLabel(tier.value)
        self._label_tier.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self._label_icon = QLabel("⏳")
        self._label_icon.setFont(QFont("Arial", 16))
        self._label_icon.setAlignment(Qt.AlignmentFlag.AlignRight)
        header.addWidget(self._label_tier)
        header.addStretch(1)
        header.addWidget(self._label_icon)

        self._label_score = QLabel("score : —")
        self._label_score.setFont(QFont("Arial", 8))
        self._label_score.setStyleSheet("color:#bbb;")

        layout.addLayout(header)
        layout.addWidget(self._label_score)

        self._set_active(False)

    @property
    def tier(self) -> TierLevel:
        return self._tier

    def update_verdict(self, verdict: Optional[TierVerdict]) -> None:
        """Met à jour l'affichage selon TierVerdict (peut être None = en attente)."""
        if verdict is None:
            self._label_icon.setText("⏳")
            self._label_score.setText("score : —")
            self._set_active(False)
            return
        self._label_icon.setText("✅" if verdict.passed else "❌")
        self._label_score.setText(f"score : {verdict.tier_score:.2f}")
        self._set_active(True)

    def _set_active(self, active: bool) -> None:
        border = _TIER_BORDER.get(self._tier, "#888")
        if active:
            self.setStyleSheet(
                "QFrame { background:#202020; color:#fff;"
                f" border:2px solid {border}; border-radius:6px; }}"
            )
        else:
            self.setStyleSheet(
                "QFrame { background:#181818; color:#888;"
                f" border:1px dashed {border}; border-radius:6px; }}"
            )


class TierVerdictBadgeRow(QWidget):
    """Conteneur horizontal des 3 TierVerdictBadge."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._badges: dict[TierLevel, TierVerdictBadge] = {}
        for tier in (TierLevel.CRITICAL, TierLevel.MAJOR, TierLevel.MINOR):
            badge = TierVerdictBadge(tier)
            self._badges[tier] = badge
            layout.addWidget(badge)

    def update(self, tier_verdicts: dict) -> None:  # type: ignore[override]
        """
        Met à jour les 3 badges depuis {tier_name: TierVerdict}.
        tier_name accepte 'CRITICAL' | TierLevel.CRITICAL.
        """
        normalized: dict[TierLevel, Optional[TierVerdict]] = {
            t: None for t in self._badges
        }
        for k, v in (tier_verdicts or {}).items():
            tier = k if isinstance(k, TierLevel) else _coerce_tier(k)
            if tier is not None and tier in normalized:
                normalized[tier] = v
        for tier, badge in self._badges.items():
            badge.update_verdict(normalized[tier])

    def reset(self) -> None:
        for badge in self._badges.values():
            badge.update_verdict(None)

    def badge(self, tier: TierLevel) -> TierVerdictBadge:
        return self._badges[tier]


def _coerce_tier(name: str) -> Optional[TierLevel]:
    try:
        return TierLevel(name)
    except (ValueError, TypeError):
        return None
