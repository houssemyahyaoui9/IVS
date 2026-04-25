"""
MainWindow — fenêtre principale TS2I IVS v7.0.
Héberge l'InspectionScreen comme central widget.
GR-05 : Qt thread principal.
"""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import QMainWindow

from ts2i_ivs.core.ui_bridge import UIBridge
from ts2i_ivs.ui.screens.inspection_screen import InspectionScreen


class MainWindow(QMainWindow):
    """
    Fenêtre principale : InspectionScreen central + menu fichier minimal.
    Sur close → demande controller.shutdown() si fourni.
    """

    def __init__(
        self,
        ui_bridge        : UIBridge,
        system_controller: Optional[Any] = None,
        product_id       : str           = "—",
        snapshot_dir     : Optional[str] = None,
        parent           = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("TS2I IVS v7.0 — Rule-Governed Hierarchical Inspection")
        self.resize(1280, 800)
        self.setStyleSheet("QMainWindow { background:#0d0d0d; }")

        self._controller = system_controller
        self._inspection_screen = InspectionScreen(
            ui_bridge         = ui_bridge,
            system_controller = system_controller,
            product_id        = product_id,
            snapshot_dir      = snapshot_dir,
            parent            = self,
        )
        self.setCentralWidget(self._inspection_screen)

        self._build_menu()

    # ── API publique ─────────────────────────────────────────────────────────

    @property
    def inspection_screen(self) -> InspectionScreen:
        return self._inspection_screen

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Fichier")

        act_quit = QAction("&Quitter", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

    # ── Fermeture propre ─────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._controller is not None:
            try:
                self._controller.shutdown()
            except Exception:
                pass
        super().closeEvent(event)
