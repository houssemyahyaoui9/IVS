"""
HistoryTab v7.0 — Historique des inspections de la session

Souscrit à UIBridge.inspection_result et accumule les FinalResult dans une
table filtrable (produit, verdict, sévérité, fail_tier).

Bornage : ring-buffer à _MAX_ROWS entrées (les plus anciennes sont écartées).
GR-03 : aucun accès au pipeline — données reçues uniquement via signaux Qt.
GR-07 : FinalResult est immuable — la table reflète une vue read-only.
"""
from __future__ import annotations

import csv
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_MAX_ROWS = 2000

_COLUMNS = (
    "Horodatage", "Frame", "Produit", "Verdict",
    "Sévérité", "Fail Tier", "Pipeline (ms)", "Raisons",
)

# Couleur de fond par verdict
_BG = {
    "OK":     QColor("#1F3F2A"),
    "NOK":    QColor("#4A1F1F"),
    "REVIEW": QColor("#3F3A1F"),
}
_FG = QColor("#EAEAEA")


# ─────────────────────────────────────────────────────────────────────────────
#  HistoryTab
# ─────────────────────────────────────────────────────────────────────────────

class HistoryTab(QWidget):
    """
    Onglet Historique — vue tabulaire des inspections récentes.

    Construction :
        HistoryTab(controller=system_controller, ui_bridge=ui_bridge)
    """

    def __init__(
        self,
        controller : Any                = None,
        ui_bridge  : Any                = None,
        parent     : Optional[QWidget]  = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._bridge     = ui_bridge

        # Stocke les FinalResult bruts pour pouvoir refiltrer / exporter.
        self._results: deque[Any] = deque(maxlen=_MAX_ROWS)

        self._build_ui()

        if self._bridge is not None and hasattr(self._bridge, "inspection_result"):
            self._bridge.inspection_result.connect(self._on_inspection_result)
        if self._bridge is not None and hasattr(self._bridge, "background_complete"):
            self._bridge.background_complete.connect(self._on_inspection_result)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addLayout(self._build_filters_bar())
        root.addWidget(self._build_table(), 1)
        root.addLayout(self._build_actions_bar())

    def _build_filters_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        bar.addWidget(QLabel("Produit :"))
        self._f_product = QLineEdit()
        self._f_product.setPlaceholderText("ex : SKU-001 (vide = tous)")
        self._f_product.setClearButtonEnabled(True)
        self._f_product.textChanged.connect(self._refresh_view)
        bar.addWidget(self._f_product, 1)

        bar.addWidget(QLabel("Verdict :"))
        self._f_verdict = QComboBox()
        self._f_verdict.addItems(("Tous", "OK", "NOK", "REVIEW"))
        self._f_verdict.currentTextChanged.connect(self._refresh_view)
        bar.addWidget(self._f_verdict)

        bar.addWidget(QLabel("Sévérité :"))
        self._f_severity = QComboBox()
        self._f_severity.addItems((
            "Toutes", "EXCELLENT", "ACCEPTABLE", "REVIEW",
            "DEFECT_2", "DEFECT_1", "REJECT",
        ))
        self._f_severity.currentTextChanged.connect(self._refresh_view)
        bar.addWidget(self._f_severity)

        bar.addWidget(QLabel("Fail Tier :"))
        self._f_tier = QComboBox()
        self._f_tier.addItems(("Tous", "—", "CRITICAL", "MAJOR", "MINOR"))
        self._f_tier.currentTextChanged.connect(self._refresh_view)
        bar.addWidget(self._f_tier)

        return bar

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        return self._table

    def _build_actions_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self._counter_lbl = QLabel("0 inspection(s)")
        self._counter_lbl.setStyleSheet("color:#aaa;")
        bar.addWidget(self._counter_lbl)
        bar.addStretch(1)

        clear_btn = QPushButton("🗑 Vider l'historique")
        clear_btn.clicked.connect(self._on_clear_clicked)
        bar.addWidget(clear_btn)

        export_btn = QPushButton("⬇ Exporter CSV…")
        export_btn.clicked.connect(self._on_export_clicked)
        bar.addWidget(export_btn)
        return bar

    # ── Réception résultats ──────────────────────────────────────────────────

    def _on_inspection_result(self, result: Any) -> None:
        if result is None:
            return
        # Évite le doublon Fail-Fast → background_complete pour le même frame_id
        frame_id = getattr(result, "frame_id", None)
        if frame_id and self._results and getattr(
            self._results[-1], "frame_id", None,
        ) == frame_id:
            self._results[-1] = result
        else:
            self._results.append(result)
        self._refresh_view()

    # ── Vue ───────────────────────────────────────────────────────────────────

    def _refresh_view(self) -> None:
        product_q  = self._f_product.text().strip().lower()
        verdict_q  = self._f_verdict.currentText()
        severity_q = self._f_severity.currentText()
        tier_q     = self._f_tier.currentText()

        # Désactive le tri pendant le repeuplement
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        shown = 0
        for r in reversed(self._results):
            if not self._matches(r, product_q, verdict_q, severity_q, tier_q):
                continue
            self._append_row(r)
            shown += 1

        self._table.setSortingEnabled(True)
        self._counter_lbl.setText(
            f"{shown} affiché(s) · {len(self._results)} en mémoire "
            f"(plafond {_MAX_ROWS})"
        )

    @staticmethod
    def _matches(
        r           : Any,
        product_q   : str,
        verdict_q   : str,
        severity_q  : str,
        tier_q      : str,
    ) -> bool:
        if product_q:
            pid = str(getattr(r, "product_id", "")).lower()
            if product_q not in pid:
                return False
        if verdict_q != "Tous" and getattr(r, "verdict", "") != verdict_q:
            return False
        if severity_q != "Toutes":
            sev = getattr(r, "severity", None)
            sv  = getattr(sev, "value", str(sev) if sev is not None else "")
            if sv != severity_q:
                return False
        if tier_q != "Tous":
            ft = getattr(r, "fail_tier", None)
            ftv = "—" if ft is None else getattr(ft, "value", str(ft))
            if ftv != tier_q:
                return False
        return True

    def _append_row(self, r: Any) -> None:
        ts        = float(getattr(r, "timestamp", time.time()))
        ts_str    = time.strftime("%H:%M:%S", time.localtime(ts))
        frame_id  = str(getattr(r, "frame_id",   ""))
        prod_id   = str(getattr(r, "product_id", ""))
        verdict   = str(getattr(r, "verdict",    ""))
        sev_obj   = getattr(r, "severity", None)
        sev       = getattr(sev_obj, "value", str(sev_obj) if sev_obj else "")
        fail_tier = getattr(r, "fail_tier", None)
        ft_str    = "—" if fail_tier is None else getattr(
            fail_tier, "value", str(fail_tier),
        )
        ms        = float(getattr(r, "pipeline_ms", 0.0))
        reasons   = ", ".join(getattr(r, "fail_reasons", ()) or ())

        bg = _BG.get(verdict)
        row = self._table.rowCount()
        self._table.insertRow(row)

        for col, text in enumerate((
            ts_str, frame_id, prod_id, verdict,
            sev, ft_str, f"{ms:.1f}", reasons,
        )):
            item = QTableWidgetItem(text)
            item.setForeground(QBrush(_FG))
            if bg is not None:
                item.setBackground(QBrush(bg))
            if col in (3, 4, 5, 6):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, col, item)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_clear_clicked(self) -> None:
        if not self._results:
            return
        ret = QMessageBox.question(
            self, "Vider l'historique",
            f"Effacer {len(self._results)} inspection(s) en mémoire ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._results.clear()
            self._refresh_view()

    def _on_export_clicked(self) -> None:
        if not self._results:
            QMessageBox.information(self, "Export", "Aucune inspection à exporter.")
            return
        default = Path("data/snapshots") / time.strftime(
            "history_%Y%m%d_%H%M%S.csv",
        )
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Exporter l'historique", str(default),
            "Fichiers CSV (*.csv)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(_COLUMNS + (
                    "tier_scores", "background_complete",
                ))
                for r in self._results:
                    sev_obj = getattr(r, "severity", None)
                    sev     = getattr(sev_obj, "value",
                                      str(sev_obj) if sev_obj else "")
                    ft      = getattr(r, "fail_tier", None)
                    ft_str  = "" if ft is None else getattr(
                        ft, "value", str(ft),
                    )
                    scores  = getattr(r, "tier_scores", {}) or {}
                    writer.writerow((
                        time.strftime(
                            "%Y-%m-%d %H:%M:%S",
                            time.localtime(float(getattr(r, "timestamp", 0.0))),
                        ),
                        getattr(r, "frame_id", ""),
                        getattr(r, "product_id", ""),
                        getattr(r, "verdict", ""),
                        sev, ft_str,
                        f"{float(getattr(r, 'pipeline_ms', 0.0)):.2f}",
                        " | ".join(getattr(r, "fail_reasons", ()) or ()),
                        " ".join(f"{k}={v:.3f}" for k, v in scores.items()),
                        bool(getattr(r, "background_complete", False)),
                    ))
        except Exception as exc:
            logger.error("HistoryTab: export CSV échoué — %s", exc)
            QMessageBox.critical(self, "Export", f"Échec :\n{exc}")
            return
        QMessageBox.information(self, "Export", f"Exporté vers :\n{path}")

    # ── API tests ─────────────────────────────────────────────────────────────

    @property
    def row_count(self) -> int:
        return self._table.rowCount()

    @property
    def stored_count(self) -> int:
        return len(self._results)
