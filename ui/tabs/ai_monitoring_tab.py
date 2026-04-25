"""
AIMonitoringTab v7.0 — Suivi des observers par Tier

Trois tables (CRITICAL · MAJOR · MINOR) qui listent les observers vus
au moins une fois pendant la session, avec :

  • observer_id, dernier passed/échec, dernière confiance,
  • dernière latence (ms), erreur éventuelle (GR-11),
  • horodatage du dernier signal et compteur passes/échecs.

Source : signaux UIBridge (tier_verdict_ready + background_complete).
La table se construit à la volée — aucune introspection du pipeline (GR-03).

Si un ObserverRegistry est passé via `observer_registry=`, la liste initiale
des observers (mêmes vides) y est pré-remplie pour donner un état "attendu".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_REFRESH_MS = 1000

_COLUMNS = (
    "Observer", "Statut", "Confiance", "Latence (ms)",
    "Passes", "Échecs", "Vu il y a", "Erreur",
)

_TIER_BG = {
    "CRITICAL": QColor("#2B1A1A"),
    "MAJOR":    QColor("#2B241A"),
    "MINOR":    QColor("#1A222B"),
}
_OK_FG    = QColor("#2ECC71")
_NOK_FG   = QColor("#E74C3C")
_IDLE_FG  = QColor("#7F8C8D")
_ERR_FG   = QColor("#F39C12")
_BASE_FG  = QColor("#EAEAEA")


# ─────────────────────────────────────────────────────────────────────────────
#  Modèle interne par observer
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _ObserverRow:
    observer_id : str
    tier        : str
    last_passed : Optional[bool] = None
    last_conf   : Optional[float] = None
    last_lat_ms : Optional[float] = None
    pass_count  : int = 0
    fail_count  : int = 0
    last_err    : Optional[str] = None
    last_seen   : Optional[float] = None
    details     : dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
#  Table par Tier
# ─────────────────────────────────────────────────────────────────────────────

class _TierTable(QGroupBox):
    """Table des observers d'un Tier — refresh périodique pour 'vu il y a'."""

    def __init__(
        self,
        tier_name : str,
        parent    : Optional[QWidget] = None,
    ) -> None:
        super().__init__(tier_name, parent)
        self._tier_name = tier_name
        self._rows: dict[str, _ObserverRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 14, 6, 6)
        layout.setSpacing(4)

        self._table = QTableWidget(0, len(_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        layout.addWidget(self._table, 1)

        self._summary = QLabel("0 observer(s)")
        self._summary.setStyleSheet("color:#aaa;")
        layout.addWidget(self._summary)

    def ensure_observer(self, observer_id: str) -> _ObserverRow:
        row = self._rows.get(observer_id)
        if row is None:
            row = _ObserverRow(observer_id=observer_id, tier=self._tier_name)
            self._rows[observer_id] = row
        return row

    def push_signal(self, signal: Any) -> None:
        """Met à jour la ligne correspondant à un ObserverSignal."""
        observer_id = getattr(signal, "observer_id", None)
        if not observer_id:
            return
        row = self.ensure_observer(observer_id)
        passed = bool(getattr(signal, "passed", False))
        if passed:
            row.pass_count += 1
        else:
            row.fail_count += 1
        row.last_passed = passed
        row.last_conf   = float(getattr(signal, "confidence", 0.0))
        row.last_lat_ms = float(getattr(signal, "latency_ms", 0.0))
        row.last_err    = getattr(signal, "error_msg", None)
        row.last_seen   = time.time()
        details         = getattr(signal, "details", None)
        if isinstance(details, dict):
            row.details = dict(details)

    def reset(self) -> None:
        self._rows.clear()
        self.refresh()

    def refresh(self) -> None:
        # Construit l'affichage en triant par observer_id
        ordered = sorted(self._rows.values(), key=lambda r: r.observer_id)
        self._table.setRowCount(len(ordered))
        bg = _TIER_BG.get(self._tier_name)

        now = time.time()
        active = 0
        for r, row in enumerate(ordered):
            if row.last_passed is True:
                status_text, status_fg = "● PASS", _OK_FG
            elif row.last_passed is False:
                status_text, status_fg = "● FAIL", _NOK_FG
            else:
                status_text, status_fg = "○ idle", _IDLE_FG

            conf_text = "—" if row.last_conf is None else f"{row.last_conf:.3f}"
            lat_text  = "—" if row.last_lat_ms is None else f"{row.last_lat_ms:.1f}"
            seen_text = "—" if row.last_seen is None else self._fmt_age(now - row.last_seen)
            err_text  = row.last_err or ""

            cells = (
                row.observer_id, status_text, conf_text, lat_text,
                str(row.pass_count), str(row.fail_count), seen_text, err_text,
            )
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setForeground(QBrush(_BASE_FG))
                if bg is not None:
                    item.setBackground(QBrush(bg))
                if c == 1:
                    item.setForeground(QBrush(status_fg))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c in (2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 7 and err_text:
                    item.setForeground(QBrush(_ERR_FG))
                self._table.setItem(r, c, item)
            if row.last_seen is not None and (now - row.last_seen) < 5.0:
                active += 1

        self._summary.setText(
            f"{len(ordered)} observer(s) — {active} actif(s) <5s",
        )

    @staticmethod
    def _fmt_age(seconds: float) -> str:
        if seconds < 1.0:
            return "<1 s"
        if seconds < 60.0:
            return f"{seconds:.0f} s"
        if seconds < 3600.0:
            return f"{seconds / 60.0:.1f} min"
        return f"{seconds / 3600.0:.1f} h"


# ─────────────────────────────────────────────────────────────────────────────
#  AIMonitoringTab
# ─────────────────────────────────────────────────────────────────────────────

class AIMonitoringTab(QWidget):
    """
    Onglet AI Monitoring — vue temps réel des observers par Tier.

    Construction :
        AIMonitoringTab(
            controller        = system_controller,
            ui_bridge         = ui_bridge,
            observer_registry = optional ObserverRegistry,
        )
    """

    def __init__(
        self,
        controller        : Any                = None,
        ui_bridge         : Any                = None,
        observer_registry : Any                = None,
        parent            : Optional[QWidget]  = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._bridge     = ui_bridge
        self._registry   = observer_registry

        self._build_ui()

        if self._bridge is not None:
            if hasattr(self._bridge, "tier_verdict_ready"):
                self._bridge.tier_verdict_ready.connect(self._on_tier_verdict)
            if hasattr(self._bridge, "background_complete"):
                self._bridge.background_complete.connect(self._on_background_complete)

        self._preload_from_registry()

        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        header = QLabel(
            "Vue par Tier des AI Observers — chaque ligne reflète le "
            "dernier signal reçu (ObserverSignal). Aucune décision UI (GR-04)."
        )
        header.setStyleSheet("color:#888; padding:4px;")
        header.setWordWrap(True)
        root.addWidget(header)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(8)
        self._tables: dict[str, _TierTable] = {}
        for tier in ("CRITICAL", "MAJOR", "MINOR"):
            t = _TierTable(tier, self)
            t.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)
            tables_row.addWidget(t, 1)
            self._tables[tier] = t
        root.addLayout(tables_row, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        reset_btn = QPushButton("⟳ Réinitialiser")
        reset_btn.clicked.connect(self._on_reset_clicked)
        actions.addWidget(reset_btn)
        root.addLayout(actions)

    # ── Pré-remplissage depuis ObserverRegistry (optionnel) ───────────────────

    def _preload_from_registry(self) -> None:
        if self._registry is None:
            return
        # Tente plusieurs API plausibles (registre v7.0)
        from core.tier_result import TierLevel
        for tier_enum, tier_name in (
            (TierLevel.CRITICAL, "CRITICAL"),
            (TierLevel.MAJOR,    "MAJOR"),
            (TierLevel.MINOR,    "MINOR"),
        ):
            observers: list[Any] = []
            for getter in ("get_for_tier", "for_tier", "list_for_tier"):
                fn = getattr(self._registry, getter, None)
                if callable(fn):
                    try:
                        observers = list(fn(tier_enum)) or list(fn(tier_enum, None))
                        break
                    except TypeError:
                        try:
                            observers = list(fn(tier_enum))
                            break
                        except Exception:
                            continue
                    except Exception:
                        continue
            for obs in observers:
                obs_id = getattr(obs, "observer_id", None) or obs.__class__.__name__
                self._tables[tier_name].ensure_observer(str(obs_id))

    # ── Slots signaux ─────────────────────────────────────────────────────────

    def _on_tier_verdict(self, tier_name: str, verdict: Any) -> None:
        if verdict is None:
            return
        table = self._tables.get(str(tier_name))
        if table is None:
            return
        for sig in getattr(verdict, "signals", ()) or ():
            table.push_signal(sig)

    def _on_background_complete(self, result: Any) -> None:
        if result is None:
            return
        verdicts = getattr(result, "tier_verdicts", None) or {}
        for tier_name, tv in verdicts.items():
            table = self._tables.get(str(tier_name))
            if table is None:
                continue
            for sig in getattr(tv, "signals", ()) or ():
                table.push_signal(sig)

    # ── Refresh / reset ───────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        for t in self._tables.values():
            t.refresh()

    def _on_reset_clicked(self) -> None:
        for t in self._tables.values():
            t.reset()
        self._preload_from_registry()
        self._refresh_all()

    # ── API tests ─────────────────────────────────────────────────────────────

    def observers_in_tier(self, tier_name: str) -> tuple[str, ...]:
        t = self._tables.get(tier_name)
        return () if t is None else tuple(sorted(t._rows.keys()))
