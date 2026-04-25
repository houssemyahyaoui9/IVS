"""
LuminosityIndicator — §18.3 / §42
QFrame compact pour la TopBar : "☀ 187" coloré selon la sévérité.

Couleurs (LuminosityResult.severity) :
  OK       → vert
  WARNING  → jaune
  CRITICAL → rouge

Tooltip : valeurs numériques (mean, ref, delta_percent).

GR-03 : aucun appel direct au pipeline. Branchement standard :
        ui_bridge.luminosity_update.connect(indicator.on_luminosity_update)
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from core.models import LuminosityResult

logger = logging.getLogger(__name__)

_COLOR_GREEN  = "#27AE60"
_COLOR_YELLOW = "#F1C40F"
_COLOR_RED    = "#C0392B"


class LuminosityIndicator(QFrame):
    """
    Indicateur compact "☀ <value>" pour TopBar.

    Slot principal :
      on_luminosity_update(LuminosityResult)
        ← UIBridge.luminosity_update (émis par S2 via SystemController).

    Lecture de tests : `severity_color`, `value`, `text`.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("LuminosityIndicator")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        self._label = QLabel("☀ —")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "color: white; font-weight: bold; font-size: 14px;"
        )
        layout.addWidget(self._label)

        self._severity = "OK"
        self._value    = 0.0
        self._apply_color()
        self.setToolTip("Luminosité — en attente de la première frame.")

    # ── Slot principal ────────────────────────────────────────────────────────

    def on_luminosity_update(self, result: LuminosityResult) -> None:
        if result is None:
            return
        self._value    = float(result.value)
        self._severity = result.severity
        self._label.setText(f"☀ {int(round(self._value))}")
        self._apply_color()
        self.setToolTip(
            f"Luminosité : {result.value:.1f}\n"
            f"Référence  : {result.ref_mean:.1f}\n"
            f"Écart      : {result.delta_percent:.1f}%\n"
            f"Sévérité   : {result.severity}"
        )
        if result.critical:
            logger.warning(
                "LuminosityIndicator: CRITICAL value=%.1f delta=%.1f%%",
                result.value, result.delta_percent,
            )

    # ── Visuel ────────────────────────────────────────────────────────────────

    def _apply_color(self) -> None:
        if self._severity == "CRITICAL":
            color = _COLOR_RED
        elif self._severity == "WARNING":
            color = _COLOR_YELLOW
        else:
            color = _COLOR_GREEN
        self.setStyleSheet(
            f"QFrame#LuminosityIndicator {{ background-color: {color}; "
            "border-radius: 4px; }}"
        )

    # ── Lecture (tests) ───────────────────────────────────────────────────────

    @property
    def severity(self) -> str:
        return self._severity

    @property
    def value(self) -> float:
        return self._value

    @property
    def severity_color(self) -> str:
        return {
            "OK":       "green",
            "WARNING":  "yellow",
            "CRITICAL": "red",
        }[self._severity]

    @property
    def text(self) -> str:
        return self._label.text()
