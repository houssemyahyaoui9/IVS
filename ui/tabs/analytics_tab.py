"""
AnalyticsTab v7.0 — Suivi des tier_scores et indicateurs SPC

Souscrit à UIBridge.inspection_result et tier_verdict_ready, agrège les
tier_scores des trois Tiers (CRITICAL / MAJOR / MINOR) dans un buffer
borné, et affiche :

  • Sparklines QPainter par Tier (sans dépendance externe).
  • Statistiques rapides : moyenne, σ, min/max, Cpk simplifié vs. seuil.
  • Compteurs OK / NOK / REVIEW de la session (avec %).

GR-03 : aucun accès direct au pipeline — données via UIBridge.
GR-04 : affichage uniquement, jamais réinjecté dans la chaîne de décision.
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_BUFFER_LEN = 500     # nombre max de scores conservés par Tier
_REPAINT_MS = 750     # rafraîchissement périodique (compteurs / sparkline)

_TIER_COLORS = {
    "CRITICAL": QColor("#E74C3C"),
    "MAJOR":    QColor("#E67E22"),
    "MINOR":    QColor("#3498DB"),
}

# Seuils de référence par défaut — alignés avec config.tier_engine.*_confidence_min
_TIER_THRESHOLDS_DEFAULT = {
    "CRITICAL": 0.80,
    "MAJOR":    0.70,
    "MINOR":    0.60,
}


# ─────────────────────────────────────────────────────────────────────────────
#  Sparkline minimaliste — QWidget + QPainter
# ─────────────────────────────────────────────────────────────────────────────

class _Sparkline(QWidget):
    """Tracé de tendance compact, fond sombre, ligne de seuil discrète."""

    def __init__(
        self,
        color     : QColor,
        threshold : float,
        parent    : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._color     = color
        self._threshold = threshold
        self._values    : list[float] = []
        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)

    def set_values(self, values: list[float]) -> None:
        self._values = values
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(4, 4, -4, -4)
        p.fillRect(self.rect(), QColor("#0d0d0d"))

        # Cadre
        p.setPen(QPen(QColor("#222"), 1))
        p.drawRect(rect)

        if not self._values:
            p.setPen(QColor("#666"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "—")
            return

        # Ligne de seuil
        thr_y = rect.bottom() - int(rect.height() * self._threshold)
        p.setPen(QPen(QColor("#555"), 1, Qt.PenStyle.DashLine))
        p.drawLine(rect.left(), thr_y, rect.right(), thr_y)

        # Tracé (clamp [0,1])
        n = len(self._values)
        if n == 1:
            p.setPen(QPen(self._color, 2))
            y = rect.bottom() - int(rect.height() * max(0.0, min(1.0, self._values[0])))
            p.drawLine(rect.left(), y, rect.right(), y)
            return

        step = rect.width() / max(1, (n - 1))
        p.setPen(QPen(self._color, 2))
        prev_x: Optional[float] = None
        prev_y: Optional[float] = None
        for i, v in enumerate(self._values):
            v = max(0.0, min(1.0, v))
            x = rect.left() + i * step
            y = rect.bottom() - rect.height() * v
            if prev_x is not None:
                p.drawLine(int(prev_x), int(prev_y), int(x), int(y))
            prev_x, prev_y = x, y


# ─────────────────────────────────────────────────────────────────────────────
#  Carte par Tier
# ─────────────────────────────────────────────────────────────────────────────

class _TierCard(QGroupBox):
    """Cadre par Tier : sparkline + statistiques."""

    def __init__(
        self,
        tier_name : str,
        threshold : float,
        parent    : Optional[QWidget] = None,
    ) -> None:
        super().__init__(f"{tier_name}", parent)
        self._tier_name = tier_name
        self._threshold = threshold
        self._scores: deque[float] = deque(maxlen=_BUFFER_LEN)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(6)

        color = _TIER_COLORS.get(tier_name, QColor("#888888"))
        self._spark = _Sparkline(color, threshold, self)
        layout.addWidget(self._spark, 1)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(12)
        stats_grid.setVerticalSpacing(2)
        self._lbl_n     = QLabel("N : 0")
        self._lbl_mean  = QLabel("μ : —")
        self._lbl_sigma = QLabel("σ : —")
        self._lbl_min   = QLabel("min : —")
        self._lbl_max   = QLabel("max : —")
        self._lbl_thr   = QLabel(f"seuil : {threshold:.2f}")
        self._lbl_cpk   = QLabel("Cpk : —")

        for lbl in (self._lbl_n, self._lbl_mean, self._lbl_sigma,
                    self._lbl_min, self._lbl_max, self._lbl_thr,
                    self._lbl_cpk):
            lbl.setStyleSheet("color:#ddd;")
        stats_grid.addWidget(self._lbl_n,     0, 0)
        stats_grid.addWidget(self._lbl_mean,  0, 1)
        stats_grid.addWidget(self._lbl_sigma, 0, 2)
        stats_grid.addWidget(self._lbl_min,   1, 0)
        stats_grid.addWidget(self._lbl_max,   1, 1)
        stats_grid.addWidget(self._lbl_thr,   1, 2)
        stats_grid.addWidget(self._lbl_cpk,   2, 0, 1, 3)
        layout.addLayout(stats_grid)

    def push_score(self, value: float) -> None:
        if value is None:
            return
        try:
            self._scores.append(float(value))
        except (TypeError, ValueError):
            return

    def clear(self) -> None:
        self._scores.clear()
        self.refresh()

    def refresh(self) -> None:
        values = list(self._scores)
        self._spark.set_values(values)
        n = len(values)
        self._lbl_n.setText(f"N : {n}")
        if n == 0:
            self._lbl_mean.setText("μ : —")
            self._lbl_sigma.setText("σ : —")
            self._lbl_min.setText("min : —")
            self._lbl_max.setText("max : —")
            self._lbl_cpk.setText("Cpk : —")
            return
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        sigma = math.sqrt(variance)
        self._lbl_mean.setText(f"μ : {mean:.3f}")
        self._lbl_sigma.setText(f"σ : {sigma:.3f}")
        self._lbl_min.setText(f"min : {min(values):.3f}")
        self._lbl_max.setText(f"max : {max(values):.3f}")
        # Cpk simplifié one-sided contre le seuil bas — display only.
        if sigma > 1e-9:
            cpk = (mean - self._threshold) / (3.0 * sigma)
            self._lbl_cpk.setText(f"Cpk(↓{self._threshold:.2f}) : {cpk:+.2f}")
        else:
            self._lbl_cpk.setText("Cpk : (σ≈0)")


# ─────────────────────────────────────────────────────────────────────────────
#  Compteur global
# ─────────────────────────────────────────────────────────────────────────────

class _CounterStrip(QFrame):
    """Bandeau compteurs OK / NOK / REVIEW + débit / dernier verdict."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("AnalyticsCounter")
        self.setStyleSheet(
            "QFrame#AnalyticsCounter { background:#1a1a1a; "
            "border-radius:4px; padding:6px; }"
            "QLabel { color:white; font-weight:bold; padding:0 8px; }"
        )
        self._ok = self._nok = self._review = 0
        self._total_ms = 0.0
        self._last_ts  : Optional[float] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self._lbl_ok     = QLabel("OK : 0")
        self._lbl_nok    = QLabel("NOK : 0")
        self._lbl_review = QLabel("REVIEW : 0")
        self._lbl_rate   = QLabel("Cadence : —")
        self._lbl_avg    = QLabel("Pipeline μ : —")
        self._lbl_ok.setStyleSheet("color:#2ECC71; font-weight:bold;")
        self._lbl_nok.setStyleSheet("color:#E74C3C; font-weight:bold;")
        self._lbl_review.setStyleSheet("color:#F1C40F; font-weight:bold;")
        layout.addWidget(self._lbl_ok)
        layout.addWidget(self._lbl_nok)
        layout.addWidget(self._lbl_review)
        layout.addStretch(1)
        layout.addWidget(self._lbl_rate)
        layout.addWidget(self._lbl_avg)

    def reset(self) -> None:
        self._ok = self._nok = self._review = 0
        self._total_ms = 0.0
        self._last_ts  = None
        self.refresh()

    def add_result(self, verdict: str, pipeline_ms: float, ts: float) -> None:
        if verdict == "OK":
            self._ok += 1
        elif verdict == "NOK":
            self._nok += 1
        else:
            self._review += 1
        self._total_ms += float(pipeline_ms or 0.0)
        self._last_ts = ts
        self.refresh()

    def refresh(self) -> None:
        total = self._ok + self._nok + self._review
        self._lbl_ok.setText(self._fmt("OK", self._ok, total, "#2ECC71"))
        self._lbl_nok.setText(self._fmt("NOK", self._nok, total, "#E74C3C"))
        self._lbl_review.setText(self._fmt("REVIEW", self._review, total, "#F1C40F"))
        if total == 0:
            self._lbl_avg.setText("Pipeline μ : —")
        else:
            self._lbl_avg.setText(f"Pipeline μ : {self._total_ms / total:.1f} ms")
        if self._last_ts is None:
            self._lbl_rate.setText("Cadence : —")
        else:
            age = max(0.0, time.time() - self._last_ts)
            self._lbl_rate.setText(f"Dernière inspection : il y a {age:.1f}s")

    @staticmethod
    def _fmt(label: str, n: int, total: int, color: str) -> str:
        if total <= 0:
            return f"<span style='color:{color}'>{label} : {n}</span>"
        pct = 100.0 * n / total
        return f"<span style='color:{color}'>{label} : {n} ({pct:.1f}%)</span>"


# ─────────────────────────────────────────────────────────────────────────────
#  AnalyticsTab
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsTab(QWidget):
    """
    Onglet Analytics — sparklines tier_scores + compteurs SPC.

    Construction :
        AnalyticsTab(controller=system_controller, ui_bridge=ui_bridge,
                     config=ConfigManager | dict | None)
    """

    def __init__(
        self,
        controller : Any                = None,
        ui_bridge  : Any                = None,
        config     : Any                = None,
        parent     : Optional[QWidget]  = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._bridge     = ui_bridge
        self._config     = config

        thresholds = self._read_thresholds()

        self._build_ui(thresholds)

        if self._bridge is not None:
            if hasattr(self._bridge, "inspection_result"):
                self._bridge.inspection_result.connect(self._on_inspection_result)
            if hasattr(self._bridge, "background_complete"):
                self._bridge.background_complete.connect(self._on_inspection_result)
            if hasattr(self._bridge, "tier_verdict_ready"):
                self._bridge.tier_verdict_ready.connect(self._on_tier_verdict)

        self._timer = QTimer(self)
        self._timer.setInterval(_REPAINT_MS)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start()

    # ── Configuration ─────────────────────────────────────────────────────────

    def _read_thresholds(self) -> dict[str, float]:
        thr = dict(_TIER_THRESHOLDS_DEFAULT)
        cfg = self._config
        if cfg is None:
            return thr
        get = cfg.get if hasattr(cfg, "get") else None
        if get is None and isinstance(cfg, dict):
            def get(key: str, default=None):  # noqa: E306
                node: Any = cfg
                for part in key.split("."):
                    if not isinstance(node, dict):
                        return default
                    node = node.get(part)
                    if node is None:
                        return default
                return node
        if get is None:
            return thr
        try:
            thr["CRITICAL"] = float(get("tier_engine.critical_confidence_min",
                                        thr["CRITICAL"]))
            thr["MAJOR"]    = float(get("tier_engine.major_confidence_min",
                                        thr["MAJOR"]))
            thr["MINOR"]    = float(get("tier_engine.minor_confidence_min",
                                        thr["MINOR"]))
        except (TypeError, ValueError):
            pass
        return thr

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self, thresholds: dict[str, float]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._counters = _CounterStrip(self)
        root.addWidget(self._counters)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self._cards: dict[str, _TierCard] = {}
        for tier in ("CRITICAL", "MAJOR", "MINOR"):
            card = _TierCard(tier, thresholds.get(tier, 0.5), self)
            self._cards[tier] = card
            cards_row.addWidget(card, 1)
        root.addLayout(cards_row, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        reset_btn = QPushButton("⟳ Réinitialiser")
        reset_btn.clicked.connect(self._on_reset_clicked)
        actions.addWidget(reset_btn)
        root.addLayout(actions)

    # ── Slots signaux ─────────────────────────────────────────────────────────

    def _on_inspection_result(self, result: Any) -> None:
        if result is None:
            return
        verdict = str(getattr(result, "verdict", ""))
        ms      = float(getattr(result, "pipeline_ms", 0.0))
        ts      = float(getattr(result, "timestamp",   time.time()))
        self._counters.add_result(verdict, ms, ts)

        scores = getattr(result, "tier_scores", None) or {}
        for tier, value in scores.items():
            card = self._cards.get(str(tier))
            if card is not None:
                card.push_score(value)

    def _on_tier_verdict(self, tier_name: str, verdict: Any) -> None:
        card = self._cards.get(str(tier_name))
        if card is None or verdict is None:
            return
        score = getattr(verdict, "tier_score", None)
        if score is not None:
            card.push_score(score)

    # ── Refresh / actions ─────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._counters.refresh()
        for card in self._cards.values():
            card.refresh()

    def _on_reset_clicked(self) -> None:
        self._counters.reset()
        for card in self._cards.values():
            card.clear()

    # ── Tests ─────────────────────────────────────────────────────────────────

    def tier_buffer_size(self, tier_name: str) -> int:
        card = self._cards.get(tier_name)
        return 0 if card is None else len(card._scores)
