"""
SystemStatusBar — barre basse CPU/RAM/TEMP/DISK/UPTIME/Pipeline avg — §43.
GR-03 : update via UIBridge.system_snapshot signal (toutes les ~5s).
GR-05 : Qt thread principal.
"""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy


# Seuils §43 — vert / jaune / rouge
_CPU_THRESHOLDS  : tuple[float, float] = (60.0, 85.0)
_RAM_THRESHOLDS  : tuple[float, float] = (60.0, 85.0)
_TEMP_THRESHOLDS : tuple[float, float] = (60.0, 75.0)
_DISK_THRESHOLDS : tuple[float, float] = (75.0, 90.0)


def _color_for(value: float, warn: float, crit: float) -> str:
    if value >= crit:
        return "#E53935"
    if value >= warn:
        return "#FBC02D"
    return "#43A047"


class SystemStatusBar(QFrame):
    """Barre de statut système (footer) avec mise à jour cadencée."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(28)
        self.setStyleSheet(
            "SystemStatusBar { background:#101010; border-top:1px solid #333; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(14)

        font = QFont("Monospace", 9)

        self._cpu      = self._make_label(font)
        self._ram      = self._make_label(font)
        self._temp     = self._make_label(font)
        self._disk     = self._make_label(font)
        self._uptime   = self._make_label(font)
        self._pipeline = self._make_label(font)

        for w in (self._cpu, self._ram, self._temp, self._disk,
                  self._uptime, self._pipeline):
            layout.addWidget(w)
        layout.addStretch(1)

        self._set_default()

    # ── API publique ─────────────────────────────────────────────────────────

    def update_snapshot(self, snapshot: Optional[Any]) -> None:
        """
        Met à jour la barre depuis un SystemSnapshot (ou objet équivalent).
        Champs attendus (tous optionnels) :
          cpu_percent, ram_percent, ram_used_gb, ram_total_gb,
          temp_c, disk_percent, disk_used_gb, disk_total_gb,
          uptime_s, pipeline_avg_ms.
        """
        if snapshot is None:
            self._set_default()
            return

        g = lambda name, default=None: getattr(snapshot, name, default)

        # CPU
        cpu_pct = g("cpu_percent")
        if cpu_pct is not None:
            color = _color_for(float(cpu_pct), *_CPU_THRESHOLDS)
            self._set(self._cpu, f"CPU : {float(cpu_pct):4.1f}%", color)

        # RAM
        ram_pct = g("ram_percent")
        ram_u, ram_t = g("ram_used_gb"), g("ram_total_gb")
        if ram_u is not None and ram_t is not None:
            color = _color_for(float(ram_pct or 0.0), *_RAM_THRESHOLDS)
            self._set(self._ram, f"RAM : {float(ram_u):.1f}/{float(ram_t):.1f}GB", color)
        elif ram_pct is not None:
            color = _color_for(float(ram_pct), *_RAM_THRESHOLDS)
            self._set(self._ram, f"RAM : {float(ram_pct):4.1f}%", color)

        # TEMP
        temp = g("temp_c")
        if temp is not None:
            color = _color_for(float(temp), *_TEMP_THRESHOLDS)
            self._set(self._temp, f"TEMP : {float(temp):.0f}°C", color)

        # DISK
        disk_pct = g("disk_percent")
        disk_u, disk_t = g("disk_used_gb"), g("disk_total_gb")
        disk_free = g("disk_free_gb")
        if disk_u is not None and disk_t is not None:
            pct = (float(disk_u) / float(disk_t) * 100.0) if disk_t else 0.0
            color = _color_for(pct, *_DISK_THRESHOLDS)
            self._set(self._disk, f"DISK : {float(disk_u):.0f}/{float(disk_t):.0f}GB", color)
        elif disk_pct is not None:
            color = _color_for(float(disk_pct), *_DISK_THRESHOLDS)
            self._set(self._disk, f"DISK : {float(disk_pct):4.1f}%", color)
        elif disk_free is not None:
            self._set(self._disk, f"DISK free : {float(disk_free):.0f}GB", "#cfcfcf")

        # UPTIME
        uptime_s = g("uptime_s")
        if uptime_s is not None:
            self._set(self._uptime, f"UP : {_fmt_uptime(float(uptime_s))}", "#cfcfcf")

        # Pipeline avg
        pipeline_avg_ms = g("pipeline_avg_ms")
        if pipeline_avg_ms is not None:
            self._set(self._pipeline, f"Pipe : {float(pipeline_avg_ms):.0f}ms", "#cfcfcf")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_label(self, font: QFont) -> QLabel:
        lab = QLabel("—")
        lab.setFont(font)
        lab.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return lab

    def _set(self, label: QLabel, text: str, color: str) -> None:
        label.setText(text)
        label.setStyleSheet(f"color:{color};")

    def _set_default(self) -> None:
        for lab, txt in (
            (self._cpu,      "CPU : —"),
            (self._ram,      "RAM : —"),
            (self._temp,     "TEMP : —"),
            (self._disk,     "DISK : —"),
            (self._uptime,   "UP : —"),
            (self._pipeline, "Pipe : —"),
        ):
            self._set(lab, txt, "#888")


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, _   = divmod(rem, 60)
    if h >= 24:
        d, hh = divmod(h, 24)
        return f"{d}d{hh:02d}h"
    return f"{h}h{m:02d}"
