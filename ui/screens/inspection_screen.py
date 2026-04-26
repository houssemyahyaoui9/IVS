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
    QPushButton,
    QSizePolicy,
    QSplitter,
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
#  ControlBar — Start / Stop
# ─────────────────────────────────────────────────────────────────────────────

class _ControlBar(QFrame):
    """Barre de contrôle Start/Stop — GR-03 : passe par SystemController."""

    def __init__(self, controller: "SystemController", parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setObjectName("ControlBar")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        self._btn_start = QPushButton("▶  Démarrer")
        self._btn_start.setObjectName("BtnStart")
        self._btn_start.setFixedHeight(40)
        self._btn_start.setStyleSheet(
            "QPushButton { background-color: #2ECC71; color: white; "
            "font-weight: bold; font-size: 14px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #27AE60; }"
            "QPushButton:disabled { background-color: #95A5A6; }"
        )

        self._btn_stop = QPushButton("■  Arrêter")
        self._btn_stop.setObjectName("BtnStop")
        self._btn_stop.setFixedHeight(40)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(
            "QPushButton { background-color: #E74C3C; color: white; "
            "font-weight: bold; font-size: 14px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #C0392B; }"
            "QPushButton:disabled { background-color: #95A5A6; }"
        )

        self._status_label = QLabel("En attente d'un produit…")
        self._status_label.setObjectName("StatusLabel")

        layout.addWidget(self._btn_start)
        layout.addWidget(self._btn_stop)
        layout.addStretch(1)
        layout.addWidget(self._status_label)

        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)

    def _on_start(self) -> None:
        try:
            self._controller.start_inspection()
            logger.info("UI: start_inspection()")
        except Exception as e:
            logger.error("start_inspection() échoué : %s", e)

    def _on_stop(self) -> None:
        try:
            self._controller.stop_inspection()
            logger.info("UI: stop_inspection()")
        except Exception as e:
            logger.error("stop_inspection() échoué : %s", e)

    def on_state_changed(self, state_value: str) -> None:
        """Met à jour l'état des boutons selon la FSM."""
        running = state_value == "RUNNING"
        ready   = state_value == "IDLE_READY"
        self._btn_start.setEnabled(ready)
        self._btn_stop.setEnabled(running)
        self._status_label.setText(f"État : {state_value}")

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

        self._controlbar = _ControlBar(self._controller, self)
        root.addWidget(self._controlbar)

        # 3 grilles — Référence (statique) · Brute (live S1) · Corrigée (post-S3).
        # Splitter horizontal pour permettre à l'opérateur de redimensionner.
        self._grids_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._grids_splitter.setChildrenCollapsible(False)

        self._grid_reference = self._make_titled_grid("Référence")
        self._grid_live      = self._make_titled_grid("Brute (live)")
        self._grid_corrected = self._make_titled_grid("Corrigée")

        for w in (self._grid_reference, self._grid_live, self._grid_corrected):
            self._grids_splitter.addWidget(w)
        self._grids_splitter.setStretchFactor(0, 1)
        self._grids_splitter.setStretchFactor(1, 1)
        self._grids_splitter.setStretchFactor(2, 1)
        self._grids_splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        root.addWidget(self._grids_splitter, 1)

        self._connect_signals()
        self._sync_initial_state()

    # ── Helpers grille ────────────────────────────────────────────────────────

    def _make_titled_grid(self, title: str) -> QWidget:
        """Encadre un ZoomableGridView dans une boîte titrée."""
        container = QGroupBox(title, self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(2)
        view = ZoomableGridView(title=title, parent=container)
        layout.addWidget(view, 1)
        # Garde une référence directe sur le ZoomableGridView via l'attribut .view
        container.view = view  # type: ignore[attr-defined]
        return container

    @property
    def _grid_live_view(self) -> ZoomableGridView:
        return self._grid_live.view  # type: ignore[attr-defined]

    @property
    def _grid_reference_view(self) -> ZoomableGridView:
        return self._grid_reference.view  # type: ignore[attr-defined]

    @property
    def _grid_corrected_view(self) -> ZoomableGridView:
        return self._grid_corrected.view  # type: ignore[attr-defined]

    # ── Câblage signaux UIBridge (GR-03) ──────────────────────────────────────

    def _connect_signals(self) -> None:
        self._bridge.product_switched.connect(self._topbar.on_product_switched)
        self._bridge.auto_switch_started.connect(self._topbar.on_auto_switch_started)
        self._bridge.state_changed.connect(self._topbar.on_state_changed)
        self._bridge.state_changed.connect(self._controlbar.on_state_changed)
        # Live grid : alimentée par PipelineRunner.S1_Acquisition → UIBridge.frame_ready
        # GR-05 : connexion auto QueuedConnection si émis depuis le thread pipeline.
        if hasattr(self._bridge, "frame_ready"):
            self._bridge.frame_ready.connect(self._grid_live_view.set_frame)

    def _sync_initial_state(self) -> None:
        active = self._controller.active_product_id
        if active:
            self._topbar.on_product_switched(active)
        self._topbar.on_state_changed(self._controller.get_state().value)
        self._controlbar.on_state_changed(self._controller.get_state().value)
