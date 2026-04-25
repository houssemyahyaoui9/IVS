"""
SystemStatusBar — §18.4 / §43
QFrame compact pour TopBar :
  [CPU: 42%] [RAM: 3.2/8GB] [TEMP: 58°C] [DISK: 45GB] [UP: 4h32m]

Couleur par cellule : vert (OK) / jaune (WARNING) / rouge (CRITICAL).
Click → SystemDetailWindow modal affichant l'historique 1h récent.

GR-03 : pas d'accès pipeline. Branchement standard :
        ui_bridge.system_health_update.connect(bar.on_health_update)
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from monitoring.system_monitor import HostMetricsSnapshot

logger = logging.getLogger(__name__)

_COLOR_GREEN  = "#27AE60"
_COLOR_YELLOW = "#F1C40F"
_COLOR_RED    = "#C0392B"

_CELL_STYLE = (
    "QLabel {{ background-color: {bg}; color: white; "
    "padding: 4px 10px; border-radius: 4px; "
    "font-weight: bold; font-size: 13px; }}"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Cellule colorée
# ─────────────────────────────────────────────────────────────────────────────

class _MetricCell(QLabel):
    """Étiquette colorée (vert/jaune/rouge) — recolor via set_state()."""

    def __init__(self, initial: str = "—") -> None:
        super().__init__(initial)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state = "OK"
        self._apply()

    def set_state(self, state: str) -> None:
        self._state = state if state in ("OK", "WARNING", "CRITICAL") else "OK"
        self._apply()

    def _apply(self) -> None:
        bg = (
            _COLOR_RED if self._state == "CRITICAL"
            else _COLOR_YELLOW if self._state == "WARNING"
            else _COLOR_GREEN
        )
        self.setStyleSheet(_CELL_STYLE.format(bg=bg))

    @property
    def state(self) -> str:
        return self._state


# ─────────────────────────────────────────────────────────────────────────────
#  SystemDetailWindow — historique
# ─────────────────────────────────────────────────────────────────────────────

class SystemDetailWindow(QDialog):
    """
    Fenêtre détail (modale) — table des derniers HostMetricsSnapshot (1h).
    Source des données : `provider()` au moment de l'ouverture (snapshot tuple).
    """

    _COLS = ("Heure", "CPU%", "RAM (GB)", "Temp (°C)",
             "Disk (GB)", "Uptime", "Sévérité")

    def __init__(
        self,
        snapshots : List[HostMetricsSnapshot],
        parent    : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Système — historique 1h")
        self.setModal(True)
        self.resize(720, 480)

        layout = QVBoxLayout(self)

        self._table = QTableWidget(len(snapshots), len(self._COLS), self)
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._fill(snapshots)

    def _fill(self, snapshots: List[HostMetricsSnapshot]) -> None:
        import time as _t
        for row, s in enumerate(snapshots):
            ts = _t.strftime("%H:%M:%S", _t.localtime(s.timestamp))
            ram = f"{s.ram_used_gb:.1f}/{s.ram_total_gb:.1f}"
            temp = f"{s.temp_c:.1f}" if s.temp_c is not None else "—"
            disk = f"{s.disk_used_gb:.0f}/{s.disk_total_gb:.0f}"
            up = _format_uptime(s.uptime_s)
            values = (ts, f"{s.cpu_percent:.0f}", ram, temp, disk, up, s.severity)
            for col, v in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(v))


# ─────────────────────────────────────────────────────────────────────────────
#  SystemStatusBar
# ─────────────────────────────────────────────────────────────────────────────

class SystemStatusBar(QFrame):
    """
    Barre statut système compacte avec 5 cellules colorées.

    Slot principal :
      on_health_update(HostMetricsSnapshot)
        ← UIBridge.system_health_update.

    Click sur la barre → SystemDetailWindow alimentée par
    `monitor.history()` (si `monitor` injecté) sinon liste interne.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        monitor : Optional[Any] = None,    # SystemMonitor avec .history()
        parent  : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SystemStatusBar")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._monitor   : Optional[Any] = monitor
        self._history   : List[HostMetricsSnapshot] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._cpu  = _MetricCell("CPU: —")
        self._ram  = _MetricCell("RAM: —")
        self._temp = _MetricCell("TEMP: —")
        self._disk = _MetricCell("DISK: —")
        self._up   = _MetricCell("UP: —")
        for cell in (self._cpu, self._ram, self._temp, self._disk, self._up):
            layout.addWidget(cell)

    # ── Slot ──────────────────────────────────────────────────────────────────

    def on_health_update(self, snap: HostMetricsSnapshot) -> None:
        if snap is None:
            return
        self._history.append(snap)
        # Garder ~1h à 5s = 720 entrées
        if len(self._history) > 720:
            self._history = self._history[-720:]

        self._cpu.setText(f"CPU: {snap.cpu_percent:.0f}%")
        self._cpu.set_state(self._classify_cpu(snap.cpu_percent))

        self._ram.setText(
            f"RAM: {snap.ram_used_gb:.1f}/{snap.ram_total_gb:.1f}GB"
        )
        self._ram.set_state(self._classify_ram(snap))

        if snap.temp_c is not None:
            self._temp.setText(f"TEMP: {snap.temp_c:.0f}°C")
            self._temp.set_state(self._classify_temp(snap.temp_c))
        else:
            self._temp.setText("TEMP: —")
            self._temp.set_state("OK")

        free = snap.disk_total_gb - snap.disk_used_gb
        self._disk.setText(f"DISK: {free:.0f}GB")
        self._disk.set_state(self._classify_disk(snap))

        self._up.setText(f"UP: {_format_uptime(snap.uptime_s)}")
        self._up.set_state("OK")

    # ── Click → fenêtre détail ────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self._open_detail_window()

    def _open_detail_window(self) -> None:
        snapshots: List[HostMetricsSnapshot]
        if self._monitor is not None and hasattr(self._monitor, "history"):
            snapshots = list(self._monitor.history())
        else:
            snapshots = list(self._history)
        if not snapshots:
            logger.debug("SystemStatusBar: aucun historique disponible")
            return
        win = SystemDetailWindow(snapshots, parent=self.window())
        win.exec()

    # ── Classification (seuils §43 — défauts alignés sur SystemMonitor) ──────

    @staticmethod
    def _classify_cpu(cpu: float) -> str:
        if cpu >= 95.0:
            return "CRITICAL"
        if cpu >= 80.0:
            return "WARNING"
        return "OK"

    @staticmethod
    def _classify_ram(snap: HostMetricsSnapshot) -> str:
        if snap.ram_total_gb <= 0:
            return "OK"
        pct = snap.ram_used_gb / snap.ram_total_gb * 100.0
        if pct >= 95.0:
            return "CRITICAL"
        if pct >= 85.0:
            return "WARNING"
        return "OK"

    @staticmethod
    def _classify_temp(temp: float) -> str:
        if temp >= 85.0:
            return "CRITICAL"
        if temp >= 75.0:
            return "WARNING"
        return "OK"

    @staticmethod
    def _classify_disk(snap: HostMetricsSnapshot) -> str:
        if snap.disk_total_gb <= 0:
            return "OK"
        pct = snap.disk_used_gb / snap.disk_total_gb * 100.0
        if pct >= 95.0:
            return "CRITICAL"
        if pct >= 85.0:
            return "WARNING"
        return "OK"

    # ── Lecture (tests) ───────────────────────────────────────────────────────

    @property
    def cpu_state(self)  -> str: return self._cpu.state
    @property
    def ram_state(self)  -> str: return self._ram.state
    @property
    def temp_state(self) -> str: return self._temp.state
    @property
    def disk_state(self) -> str: return self._disk.state


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_uptime(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, _   = divmod(rem, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        return f"{d}d{h:02d}h"
    return f"{h}h{m:02d}m"
