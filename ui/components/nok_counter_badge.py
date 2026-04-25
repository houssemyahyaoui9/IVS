"""
NOKCounterBadge — §18.2 / §41
QFrame compact pour ResultBand affichant le compteur de NOK consécutifs.

Couleurs (compteur courant) :
  0-2 → gris
  3-4 → orange (pré-alerte)
  ≥5  → rouge (alerte / stop)

Bandeau plein écran (NOKStopBanner) émis si stop_threshold (≥10) atteint —
contient le bouton [✓ Reprendre] qui demande un identifiant opérateur,
puis émet `reset_requested(operator)`.

GR-03 : aucun appel direct au pipeline. Le parent (InspectionScreen) câble
        reset_requested → SystemController/Watcher.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_COLOR_GREY   = "#666666"
_COLOR_ORANGE = "#E67E22"
_COLOR_RED    = "#C0392B"

_THRESHOLD_ORANGE = 3   # 3-4 → orange
_THRESHOLD_RED    = 5   # ≥5  → rouge


# ─────────────────────────────────────────────────────────────────────────────
#  Bandeau plein écran (stop_threshold)
# ─────────────────────────────────────────────────────────────────────────────

class NOKStopBanner(QDialog):
    """
    Bandeau modal plein écran affiché quand stop_threshold est atteint.
    Bloque l'inspection jusqu'à `[✓ Reprendre]`.

    Émet `reset_requested(operator_id)` après saisie d'un identifiant non vide.
    """

    reset_requested = pyqtSignal(str)

    def __init__(
        self,
        count   : int,
        parent  : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NOKStopBanner")
        self.setWindowTitle("ARRÊT LIGNE — NOK consécutifs")
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog#NOKStopBanner {{ background-color: {_COLOR_RED}; }}"
            "QLabel { color: white; font-weight: bold; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        title = QLabel("⛔ ARRÊT LIGNE")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 48px;")

        detail = QLabel(f"{count} NOK consécutifs détectés.\n"
                        "Vérifier la ligne avant de reprendre.")
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail.setStyleSheet("font-size: 22px;")

        self._resume_btn = QPushButton("✓ Reprendre")
        self._resume_btn.setMinimumHeight(60)
        self._resume_btn.setStyleSheet(
            "QPushButton { background-color: white; color: black; "
            "font-size: 24px; font-weight: bold; padding: 10px 30px; }"
            "QPushButton:hover { background-color: #EEEEEE; }"
        )
        self._resume_btn.clicked.connect(self._on_resume)

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addStretch(1)
        layout.addWidget(self._resume_btn, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def _on_resume(self) -> None:
        op, ok = QInputDialog.getText(
            self, "Reset opérateur",
            "Identifiant opérateur (obligatoire pour traçabilité) :",
        )
        if not ok:
            return
        op = (op or "").strip()
        if not op:
            return
        logger.info("NOKStopBanner: reset demandé par '%s'", op)
        self.reset_requested.emit(op)
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
#  Badge compact (ResultBand)
# ─────────────────────────────────────────────────────────────────────────────

class NOKCounterBadge(QFrame):
    """
    Badge compact "NOK : N" pour ResultBand.

    Slots :
      - update_count(n)  : met à jour le compteur (couleur recalculée)
      - on_alert(n)      : feedback visuel pré-alerte (logue, couleur recalculée)
      - on_stop(n)       : ouvre NOKStopBanner modal
      - on_reset(op)     : remet à 0 et masque le bandeau

    Signal :
      reset_requested(operator) — émis quand l'opérateur valide [✓ Reprendre].
    """

    reset_requested = pyqtSignal(str)

    def __init__(
        self,
        alert_threshold : int = 5,
        stop_threshold  : int = 10,
        parent          : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NOKCounterBadge")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._alert_threshold = alert_threshold
        self._stop_threshold  = stop_threshold
        self._count           = 0
        self._banner          : Optional[NOKStopBanner] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        self._label = QLabel("NOK : 0")
        self._label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(self._label)

        self._apply_color()

    # ── Slots compteur ────────────────────────────────────────────────────────

    def update_count(self, count: int) -> None:
        self._count = max(0, int(count))
        self._label.setText(f"NOK : {self._count}")
        self._apply_color()

    def on_alert(self, count: int) -> None:
        self.update_count(count)
        logger.warning("NOKCounterBadge: ALERT count=%d", count)

    def on_stop(self, count: int) -> None:
        self.update_count(count)
        logger.error("NOKCounterBadge: STOP count=%d — ouverture bandeau", count)
        self._show_banner(count)

    def on_reset(self, operator: str) -> None:
        logger.info("NOKCounterBadge: reset reçu de '%s'", operator)
        self.update_count(0)
        if self._banner is not None:
            self._banner.close()
            self._banner = None

    # ── Visuel ────────────────────────────────────────────────────────────────

    def _apply_color(self) -> None:
        if self._count >= _THRESHOLD_RED:
            color = _COLOR_RED
        elif self._count >= _THRESHOLD_ORANGE:
            color = _COLOR_ORANGE
        else:
            color = _COLOR_GREY
        self.setStyleSheet(
            f"QFrame#NOKCounterBadge {{ background-color: {color}; "
            "border-radius: 4px; }}"
        )

    def _show_banner(self, count: int) -> None:
        if self._banner is not None:
            return  # déjà ouvert
        self._banner = NOKStopBanner(count, parent=self.window())
        self._banner.reset_requested.connect(self._on_banner_reset)
        # showFullScreen() pour stations tactiles, .show() suffit en desktop dev.
        self._banner.showFullScreen()

    def _on_banner_reset(self, operator: str) -> None:
        # Relaie au parent (InspectionScreen) qui appellera le watcher (GR-03).
        self.reset_requested.emit(operator)

    # ── Lecture (utile aux tests) ─────────────────────────────────────────────

    @property
    def count(self) -> int:
        return self._count

    @property
    def color_state(self) -> str:
        if self._count >= _THRESHOLD_RED:
            return "red"
        if self._count >= _THRESHOLD_ORANGE:
            return "orange"
        return "grey"
