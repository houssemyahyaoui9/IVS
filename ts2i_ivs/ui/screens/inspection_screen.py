"""
InspectionScreen — écran d'inspection v7.0 — §12.
Layout : topbar · sidebar + 3 ZoomableGridView · TierVerdictBadgeRow ·
         ResultBand · SystemStatusBar.

GR-03 : UI → SystemController (boutons start/stop) ; états reçus via UIBridge.
GR-05 : Qt thread principal · signaux UIBridge auto-queued cross-thread.
Anti-pattern : pas de QLabel pour les grilles (ZoomableGridView).
"""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSplitter,
    QVBoxLayout, QWidget,
)

from ts2i_ivs.core.ui_bridge import UIBridge
from ts2i_ivs.ui.components.fullscreen_grid_window import FullscreenGridWindow
from ts2i_ivs.ui.components.luminosity_indicator import LuminosityIndicator
from ts2i_ivs.ui.components.nok_counter_badge import NokCounterBadge
from ts2i_ivs.ui.components.result_band import ResultBand
from ts2i_ivs.ui.components.system_status_bar import SystemStatusBar
from ts2i_ivs.ui.components.tier_verdict_badge import TierVerdictBadgeRow
from ts2i_ivs.ui.components.zoomable_grid_view import ZoomableGridView


class InspectionScreen(QWidget):
    """
    Écran principal d'inspection — câble UIBridge → composants.

    Le SystemController est optionnel : si fourni, les boutons sidebar
    appellent start/stop ; sinon ils ne font rien (mode preview).
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
        self._bridge     = ui_bridge
        self._controller = system_controller
        self._product_id = product_id
        self._fullscreen_windows: list[FullscreenGridWindow] = []

        self.setStyleSheet("InspectionScreen { background:#0d0d0d; color:#eee; }")

        # ── Layout racine ────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_topbar())
        root.addWidget(self._build_body(snapshot_dir), 1)
        root.addWidget(self._build_tier_badges_and_band())
        root.addWidget(self._build_status_bar())

        self._wire_bridge()
        self._refresh_state_label("—")

    # ── Topbar ───────────────────────────────────────────────────────────────

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.Shape.NoFrame)
        bar.setStyleSheet("QFrame { background:#1a1a1a; border-bottom:1px solid #333; }"
                          " QLabel { color:#eee; }")
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bar.setMinimumHeight(40)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(14)

        title = QLabel("IVS")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))

        self._lbl_product = QLabel(f"Produit : {self._product_id}")
        self._lbl_product.setFont(QFont("Arial", 10))

        self._lbl_state = QLabel("État : —")
        self._lbl_state.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        self._lum = LuminosityIndicator()

        self._nok_counter = NokCounterBadge()

        self._lbl_clock = QLabel("--:--:--")
        self._lbl_clock.setFont(QFont("Monospace", 10))

        layout.addWidget(title)
        layout.addWidget(self._lbl_product)
        layout.addWidget(self._lbl_state)
        layout.addStretch(1)
        layout.addWidget(self._lum)
        layout.addWidget(self._nok_counter)
        layout.addWidget(self._lbl_clock)

        # Horloge auto-refresh
        from PyQt6.QtCore import QTimer
        timer = QTimer(self)
        timer.timeout.connect(self._tick_clock)
        timer.start(1000)
        self._tick_clock()

        return bar

    def _tick_clock(self) -> None:
        from time import strftime
        self._lbl_clock.setText(strftime("%H:%M:%S"))

    # ── Body : sidebar + 3 grilles ───────────────────────────────────────────

    def _build_body(self, snapshot_dir: Optional[str]) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet("QFrame { background:#161616; border:1px solid #2a2a2a; }"
                              " QPushButton { padding:6px; }")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(8, 8, 8, 8)
        side_layout.setSpacing(8)

        self._btn_start = QPushButton("▶ Démarrer")
        self._btn_stop  = QPushButton("■ Arrêter")
        self._btn_start.setStyleSheet(
            "QPushButton { background:#2E7D32; color:#fff; font-weight:bold; }"
        )
        self._btn_stop.setStyleSheet(
            "QPushButton { background:#C62828; color:#fff; font-weight:bold; }"
        )
        self._btn_start.clicked.connect(self._on_start_clicked)
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        side_layout.addWidget(self._btn_start)
        side_layout.addWidget(self._btn_stop)
        side_layout.addStretch(1)

        # 3 grilles
        self._grid_live      = ZoomableGridView(label="Live",      snapshot_dir=snapshot_dir)
        self._grid_critical  = ZoomableGridView(label="CRITICAL",  snapshot_dir=snapshot_dir)
        self._grid_corrected = ZoomableGridView(label="Corrigé",   snapshot_dir=snapshot_dir)

        for grid in (self._grid_live, self._grid_critical, self._grid_corrected):
            grid.fullscreen_requested.connect(self._open_fullscreen)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._grid_live)
        splitter.addWidget(self._grid_critical)
        splitter.addWidget(self._grid_corrected)
        splitter.setSizes([1, 1, 1])

        layout.addWidget(sidebar)
        layout.addWidget(splitter, 1)
        return body

    # ── Bandeau Tier badges + ResultBand ────────────────────────────────────

    def _build_tier_badges_and_band(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._tier_badges = TierVerdictBadgeRow()
        self._result_band = ResultBand()

        layout.addWidget(self._tier_badges)
        layout.addWidget(self._result_band)
        return wrap

    def _build_status_bar(self) -> QWidget:
        self._status_bar = SystemStatusBar()
        return self._status_bar

    # ── Câblage UIBridge ────────────────────────────────────────────────────

    def _wire_bridge(self) -> None:
        b = self._bridge
        b.state_changed.connect(self._on_state_changed)
        b.inspection_result.connect(self._on_inspection_result)
        b.tier_verdict_ready.connect(self._on_tier_verdict_ready)
        b.background_complete.connect(self._on_inspection_result)
        b.nok_counter_update.connect(self._nok_counter.set_count)
        b.luminosity_update.connect(self._lum.update_luminosity)
        b.system_snapshot.connect(self._status_bar.update_snapshot)
        b.auto_switch_started.connect(self._on_auto_switch)

    # ── Slots UIBridge ───────────────────────────────────────────────────────

    def _on_state_changed(self, state_value: str) -> None:
        self._refresh_state_label(state_value)

    def _on_auto_switch(self, product_id: str) -> None:
        self._product_id = product_id
        self._lbl_product.setText(f"Produit : {product_id}")
        # Reset visuels d'inspection
        self._tier_badges.reset()
        self._result_band.reset()

    def _on_tier_verdict_ready(self, tier_name: str, verdict: object) -> None:
        # Mise à jour incrémentale (Fail-Fast Hybride : tiers complétés un à un)
        self._tier_badges.update({tier_name: verdict})

    def _on_inspection_result(self, result: Any) -> None:
        # ResultBand
        self._result_band.update(result)

        # TierBadges complets
        tvs = getattr(result, "tier_verdicts", None) or {}
        if tvs:
            self._tier_badges.update(tvs)

        # Auto-zoom NOK + propagation tier_verdicts/llm aux grilles (§36)
        verdict = getattr(result, "verdict", None)
        if hasattr(verdict, "value"):
            verdict = verdict.value
        llm = getattr(result, "llm_explanation", None)
        for grid in (self._grid_live, self._grid_critical, self._grid_corrected):
            grid.set_result(
                pixmap          = None,           # pixmap déjà mis à jour ailleurs
                tier_verdicts   = tvs,
                verdict         = verdict,
                llm_explanation = llm,
            )

    # ── Boutons sidebar (GR-03 : passent par le controller) ──────────────────

    def _on_start_clicked(self) -> None:
        if self._controller is None:
            return
        try:
            self._controller.start_inspection()
        except Exception as e:
            self._lbl_state.setText(f"État : ERROR ({e})")

    def _on_stop_clicked(self) -> None:
        if self._controller is None:
            return
        try:
            self._controller.stop_inspection()
        except Exception as e:
            self._lbl_state.setText(f"État : ERROR ({e})")

    # ── Helpers d'API publique pour tests / câblage caméra ───────────────────

    def set_live_pixmap(self, pixmap: QPixmap) -> None:
        self._grid_live.set_pixmap(pixmap)

    def set_critical_pixmap(self, pixmap: QPixmap) -> None:
        self._grid_critical.set_pixmap(pixmap)

    def set_corrected_pixmap(self, pixmap: QPixmap) -> None:
        self._grid_corrected.set_pixmap(pixmap)

    @property
    def grids(self) -> tuple[ZoomableGridView, ZoomableGridView, ZoomableGridView]:
        return (self._grid_live, self._grid_critical, self._grid_corrected)

    @property
    def result_band(self) -> ResultBand:
        return self._result_band

    @property
    def tier_badges(self) -> TierVerdictBadgeRow:
        return self._tier_badges

    @property
    def status_bar(self) -> SystemStatusBar:
        return self._status_bar

    @property
    def nok_counter(self) -> NokCounterBadge:
        return self._nok_counter

    @property
    def luminosity(self) -> LuminosityIndicator:
        return self._lum

    # ── Internes ─────────────────────────────────────────────────────────────

    def _refresh_state_label(self, state_value: str) -> None:
        color = {
            "RUNNING"        : "#43A047",
            "REVIEW"         : "#F9A825",
            "ERROR"          : "#E53935",
            "IDLE_READY"     : "#90CAF9",
            "IDLE_NO_PRODUCT": "#888",
            "SHUTTING_DOWN"  : "#888",
        }.get(state_value, "#eee")
        self._lbl_state.setText(f"État : {state_value}")
        self._lbl_state.setStyleSheet(f"color:{color};")

    def _open_fullscreen(
        self,
        pixmap         : QPixmap,
        label          : str,
        tier_verdicts  : Optional[dict] = None,
        llm_explanation: Optional[Any]  = None,
    ) -> None:
        win = FullscreenGridWindow(
            pixmap,
            label           = label,
            tier_verdicts   = tier_verdicts,
            llm_explanation = llm_explanation,
            ui_bridge       = self._bridge,
        )
        # Garde une référence pour éviter le GC immédiat
        self._fullscreen_windows.append(win)
        win.destroyed.connect(lambda *_: self._fullscreen_windows.remove(win)
                              if win in self._fullscreen_windows else None)
        win.show_fullscreen()
