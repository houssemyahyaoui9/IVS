"""
FullscreenGridWindow — vue plein écran §36.3
QSplitter : ZoomableGridView (gauche) + DefectDetailPanel (droite).

GR-03 : les mises à jour viennent UNIQUEMENT d'UIBridge (signaux Qt).
GR-05 : opérations Qt dans le thread principal.
"""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeyEvent, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from ts2i_ivs.ui.components.zoomable_grid_view import ZoomableGridView


_TIER_COLORS: dict[str, str] = {
    "CRITICAL": "#FF4444",
    "MAJOR":    "#FF8800",
    "MINOR":    "#FFCC00",
}


# ─────────────────────────────────────────────────────────────────────────────
#  DefectDetailPanel — colonne droite
# ─────────────────────────────────────────────────────────────────────────────

class DefectDetailPanel(QScrollArea):
    """
    Affiche : détails par TierVerdict (passed/score/fail_reasons/signals)
    + LLM explanation (display only — GR-04).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background:#0d0d0d; border:none; }")

        self._inner  = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(8)

        self._title = QLabel("Détails défaut")
        self._title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self._title.setStyleSheet("color:#fff;")

        self._llm_box = QLabel("")
        self._llm_box.setWordWrap(True)
        self._llm_box.setTextFormat(Qt.TextFormat.RichText)
        self._llm_box.setStyleSheet(
            "QLabel { background:#1c2230; color:#eee; padding:10px;"
            " border-left:4px solid #4FC3F7; border-radius:4px; }"
        )

        self._tiers_container = QWidget()
        self._tiers_layout    = QVBoxLayout(self._tiers_container)
        self._tiers_layout.setContentsMargins(0, 0, 0, 0)
        self._tiers_layout.setSpacing(8)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._llm_box)
        self._layout.addWidget(self._tiers_container)
        self._layout.addStretch(1)

        self.setWidget(self._inner)

    # ── API publique ─────────────────────────────────────────────────────────

    def update_data(
        self,
        tier_verdicts  : Optional[dict]   = None,
        llm_explanation: Optional[Any]    = None,
    ) -> None:
        """Met à jour le panneau (slot UIBridge.inspection_result)."""
        self._update_llm(llm_explanation)
        self._update_tiers(tier_verdicts or {})

    def clear(self) -> None:
        self._llm_box.setText("")
        self._llm_box.setVisible(False)
        self._clear_tiers()

    # ── Internes ─────────────────────────────────────────────────────────────

    def _update_llm(self, llm: Any) -> None:
        info = _llm_to_dict(llm)
        summary = info.get("summary")
        if not summary:
            self._llm_box.setText("")
            self._llm_box.setVisible(False)
            return
        cause   = info.get("probable_cause") or ""
        reco    = info.get("recommendation") or ""
        detail  = info.get("defect_detail")  or ""
        bits = [f"<p><b>💬 {_html(summary)}</b></p>"]
        if detail:
            bits.append(f"<p><i>{_html(detail)}</i></p>")
        if cause:
            bits.append(f"<p><b>Cause probable :</b> {_html(cause)}</p>")
        if reco:
            bits.append(f"<p><b>Recommandation :</b> {_html(reco)}</p>")
        self._llm_box.setText("".join(bits))
        self._llm_box.setVisible(True)

    def _update_tiers(self, tier_verdicts: dict) -> None:
        self._clear_tiers()
        if not tier_verdicts:
            empty = QLabel("Aucun TierVerdict disponible.")
            empty.setStyleSheet("color:#888;")
            self._tiers_layout.addWidget(empty)
            return
        for tier_name in ("CRITICAL", "MAJOR", "MINOR"):
            tv = tier_verdicts.get(tier_name)
            if tv is None and tier_name in tier_verdicts:
                continue
            if tv is None:
                # Tier absent — affiche placeholder discret
                continue
            self._tiers_layout.addWidget(_TierBlock(tier_name, tv))

    def _clear_tiers(self) -> None:
        while self._tiers_layout.count():
            item = self._tiers_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()


class _TierBlock(QFrame):
    """Carte d'un Tier dans le panneau de détails."""

    def __init__(self, tier_name: str, verdict: Any, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        color = _TIER_COLORS.get(tier_name, "#888")
        self.setStyleSheet(
            "QFrame { background:#1a1a1a; color:#eee;"
            f" border-left:4px solid {color}; border-radius:4px; }}"
            " QLabel { color:#eee; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        passed       = bool(getattr(verdict, "passed", False))
        score        = getattr(verdict, "tier_score", None)
        completed    = getattr(verdict, "completed", None)
        latency_ms   = getattr(verdict, "latency_ms", None)
        fail_reasons = list(getattr(verdict, "fail_reasons", ()) or [])
        signals      = list(getattr(verdict, "signals", ()) or [])

        head = QLabel(
            f'<b style="color:{color};">'
            f'{"✅" if passed else "❌"}  Tier {tier_name}</b>'
        )
        head.setTextFormat(Qt.TextFormat.RichText)
        head.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(head)

        meta_bits = []
        if score is not None:
            meta_bits.append(f"score = {float(score):.2f}")
        if latency_ms is not None:
            meta_bits.append(f"{float(latency_ms):.0f} ms")
        if completed is not None:
            meta_bits.append("complété" if completed else "background")
        if meta_bits:
            meta = QLabel("  ·  ".join(meta_bits))
            meta.setStyleSheet("color:#bbb; font-size:9pt;")
            layout.addWidget(meta)

        if fail_reasons:
            reasons = QLabel("Fail reasons : " + ", ".join(_html(r) for r in fail_reasons))
            reasons.setWordWrap(True)
            reasons.setStyleSheet(f"color:{color}; font-weight:bold;")
            layout.addWidget(reasons)

        if signals:
            sig_label = QLabel("Signals :")
            sig_label.setStyleSheet("color:#aaa; font-size:9pt; margin-top:4px;")
            layout.addWidget(sig_label)
            for s in signals:
                obs   = getattr(s, "observer_id", "?")
                ok    = bool(getattr(s, "passed", False))
                value = getattr(s, "value", None)
                conf  = getattr(s, "confidence", None)
                line  = (
                    f"  {'✓' if ok else '✗'} {_html(obs)}"
                    f"  · v={float(value):.3f}" if value is not None else f"  {'✓' if ok else '✗'} {_html(obs)}"
                )
                if conf is not None:
                    line += f"  · conf={float(conf):.2f}"
                lab = QLabel(line)
                lab.setStyleSheet("color:#ddd; font-family:Monospace; font-size:9pt;")
                layout.addWidget(lab)


# ─────────────────────────────────────────────────────────────────────────────
#  FullscreenGridWindow
# ─────────────────────────────────────────────────────────────────────────────

class FullscreenGridWindow(QWidget):
    """
    Fenêtre plein écran (ESC pour fermer).
    Layout : QSplitter(ZoomableGridView | DefectDetailPanel).
    """

    def __init__(
        self,
        pixmap         : QPixmap,
        label          : str           = "",
        tier_verdicts  : Optional[dict] = None,
        llm_explanation: Optional[Any]  = None,
        ui_bridge      : Optional[Any]  = None,
        snapshot_dir   : Optional[str]  = None,
        parent         = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"IVS · {label}" if label else "IVS · Grid")
        self.setStyleSheet("background:#000; color:#fff;")
        self.setWindowFlag(Qt.WindowType.Window, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar(label))

        # Splitter ZoomableGridView | DefectDetailPanel
        self._view  = ZoomableGridView(label=label, snapshot_dir=snapshot_dir, parent=self)
        self._view.set_pixmap(pixmap)
        self._panel = DefectDetailPanel()
        self._panel.update_data(tier_verdicts, llm_explanation)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._view)
        splitter.addWidget(self._panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1200, 380])
        outer.addWidget(splitter, 1)

        # Câblage UIBridge optionnel — GR-03
        self._bridge = ui_bridge
        if ui_bridge is not None:
            ui_bridge.inspection_result.connect(self._on_inspection_result)

    # ── API publique ─────────────────────────────────────────────────────────

    @property
    def view(self) -> ZoomableGridView:
        return self._view

    @property
    def panel(self) -> DefectDetailPanel:
        return self._panel

    def show_fullscreen(self) -> None:
        self.showFullScreen()

    # ── Événements ───────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._bridge is not None:
            try:
                self._bridge.inspection_result.disconnect(self._on_inspection_result)
            except (TypeError, RuntimeError):
                pass
        super().closeEvent(event)

    # ── Slot UIBridge ────────────────────────────────────────────────────────

    def _on_inspection_result(self, result: Any) -> None:
        # Live update : panel + verdict NOK auto-zoom
        tvs = getattr(result, "tier_verdicts", None) or {}
        llm = getattr(result, "llm_explanation", None)
        self._panel.update_data(tvs, llm)
        verdict = getattr(result, "verdict", None)
        if hasattr(verdict, "value"):
            verdict = verdict.value
        self._view.set_verdict(verdict)

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_topbar(self, label: str) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet("background:#0a0a0a; border-bottom:1px solid #2a2a2a;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)

        title = QLabel(label or "Grid")
        title.setStyleSheet("font-weight:bold; color:#fff;")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))

        btn_close = QPushButton("✕  Fermer (Echap)")
        btn_close.setStyleSheet(
            "QPushButton { background:#222; color:#fff; padding:4px 10px;"
            " border:1px solid #444; }"
        )
        btn_close.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(btn_close)
        return bar


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _llm_to_dict(llm: Any) -> dict:
    if llm is None:
        return {}
    if isinstance(llm, dict):
        return dict(llm)
    return {
        "summary"        : getattr(llm, "summary",        None),
        "defect_detail"  : getattr(llm, "defect_detail",  None),
        "probable_cause" : getattr(llm, "probable_cause", None),
        "recommendation" : getattr(llm, "recommendation", None),
        "fail_tier"      : getattr(llm, "fail_tier",      None),
    }


def _html(s: Any) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                  .replace('"', "&quot;"))
