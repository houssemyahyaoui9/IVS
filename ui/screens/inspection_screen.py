"""
InspectionScreen v7.0 — 3 grilles + TopBar produit actif (auto-switch §35).

GR-03 : aucun accès direct au pipeline. Toute communication passe par
        SystemController + UIBridge (signaux Qt cross-thread §GR-05).
GR-05 : signaux UIBridge déclenchés depuis le thread du scanner sont reçus
        par défaut en QueuedConnection dans le thread Qt principal.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.pipeline_controller import SystemController
from core.ui_bridge import UIBridge
from ui.components.zoomable_grid_view import ZoomableGridView

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  TopBar produit actif
# ─────────────────────────────────────────────────────────────────────────────

class _ActiveProductBar(QFrame):
    """
    Barre supérieure affichant le produit actif et l'état FSM.
    Mise à jour via signaux UIBridge — jamais d'appel direct au pipeline (GR-03).
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ActiveProductBar")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(16)

        self._product_label = QLabel("Produit : —")
        self._product_label.setObjectName("ProductLabel")

        self._switch_hint = QLabel("")
        self._switch_hint.setObjectName("SwitchHint")
        self._switch_hint.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self._state_label = QLabel("État : IDLE_NO_PRODUCT")
        self._state_label.setObjectName("StateLabel")

        layout.addWidget(self._product_label, 1)
        layout.addWidget(self._state_label, 0)
        layout.addWidget(self._switch_hint, 1)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def on_product_switched(self, product_id: str) -> None:
        self._product_label.setText(f"Produit : {product_id}")
        self._switch_hint.setText("")
        logger.info("UI: produit actif → %s", product_id)

    def on_auto_switch_started(self, product_id: str) -> None:
        self._switch_hint.setText(f"⟳ auto-switch → {product_id}")

    def on_state_changed(self, state_value: str) -> None:
        self._state_label.setText(f"État : {state_value}")


# ─────────────────────────────────────────────────────────────────────────────
#  InspectionScreen
# ─────────────────────────────────────────────────────────────────────────────

class InspectionScreen(QWidget):
    """
    Écran d'inspection v7.0 — TopBar produit actif + zone 3 grilles (placeholder).

    Construction :
        screen = InspectionScreen(controller, controller._ui_bridge)
    """

    def __init__(
        self,
        controller : SystemController,
        ui_bridge  : UIBridge,
        parent     : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._bridge     = ui_bridge

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._topbar = _ActiveProductBar(self)
        root.addWidget(self._topbar)

        # Placeholder pour la zone 3 grilles (renseignée par P22-A ZoomableGridView).
        self._grids_placeholder = QLabel("[3 grilles — référence / brute / corrigée]")
        self._grids_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grids_placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        root.addWidget(self._grids_placeholder, 1)

        self._connect_signals()
        self._sync_initial_state()

    # ── Câblage signaux UIBridge (GR-03) ──────────────────────────────────────

    def _connect_signals(self) -> None:
        self._bridge.product_switched.connect(self._topbar.on_product_switched)
        self._bridge.auto_switch_started.connect(self._topbar.on_auto_switch_started)
        self._bridge.state_changed.connect(self._topbar.on_state_changed)

    def _sync_initial_state(self) -> None:
        active = self._controller.active_product_id
        if active:
            self._topbar.on_product_switched(active)
        self._topbar.on_state_changed(self._controller.get_state().value)
