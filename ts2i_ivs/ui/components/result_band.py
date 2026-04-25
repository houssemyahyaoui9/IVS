"""
ResultBand — bandeau verdict v7.0 — §12.
v7.0 : JAMAIS fused_score · JAMAIS ensemble weights · Tier-based uniquement.
GR-03 : update via UIBridge.inspection_result signal.
GR-05 : Qt thread principal.
"""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ts2i_ivs.core.models import SeverityLevel
from ts2i_ivs.ui.components.severity_badge import SeverityBadge


_VERDICT_BG: dict[str, str] = {
    "OK"     : "#1B5E20",   # vert foncé
    "NOK"    : "#B71C1C",   # rouge foncé
    "REVIEW" : "#F57F17",   # jaune foncé
}

_VERDICT_DOT: dict[str, str] = {
    "OK"     : "#A5D6A7",
    "NOK"    : "#EF9A9A",
    "REVIEW" : "#FFE082",
}


class ResultBand(QFrame):
    """
    Bandeau résultat sous les grilles d'inspection — §12.

    Contenu (4 lignes) :
      L1 : [●] verdict + SeverityBadge
      L2 : "Tier {fail_tier} échoué" + fail_reasons (si NOK)
      L3 : [💬 LLM] explication
      L4 : [✓ Valider OK] [✗ Rejeter NOK]   (si REVIEW)

    Signals :
      review_validated_ok()
      review_rejected_nok()
    """

    review_validated_ok = pyqtSignal()
    review_rejected_nok = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(120)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(4)

        # ── Ligne 1 : verdict + severity
        row1 = QHBoxLayout()
        self._dot = QLabel("●")
        self._dot.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self._verdict = QLabel("—")
        self._verdict.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self._severity_badge = SeverityBadge()
        row1.addWidget(self._dot)
        row1.addWidget(self._verdict)
        row1.addStretch(1)
        row1.addWidget(self._severity_badge)
        outer.addLayout(row1)

        # ── Ligne 2 : fail_tier + fail_reasons
        self._fail_line = QLabel("")
        self._fail_line.setFont(QFont("Arial", 11))
        self._fail_line.setWordWrap(True)
        outer.addWidget(self._fail_line)

        # ── Ligne 3 : LLM
        self._llm_line = QLabel("")
        self._llm_line.setFont(QFont("Arial", 10))
        self._llm_line.setWordWrap(True)
        self._llm_line.setStyleSheet("color:#eee; font-style: italic;")
        outer.addWidget(self._llm_line)

        # ── Ligne 4 : actions REVIEW
        self._actions = QWidget()
        actions_layout = QHBoxLayout(self._actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(8)
        self._btn_ok  = QPushButton("✓ Valider OK")
        self._btn_nok = QPushButton("✗ Rejeter NOK")
        self._btn_ok.setStyleSheet(
            "QPushButton { background:#2E7D32; color:#fff; padding:4px 12px;"
            " border-radius:4px; font-weight:bold; }"
        )
        self._btn_nok.setStyleSheet(
            "QPushButton { background:#C62828; color:#fff; padding:4px 12px;"
            " border-radius:4px; font-weight:bold; }"
        )
        self._btn_ok.clicked.connect(self.review_validated_ok)
        self._btn_nok.clicked.connect(self.review_rejected_nok)
        actions_layout.addWidget(self._btn_ok)
        actions_layout.addWidget(self._btn_nok)
        actions_layout.addStretch(1)
        outer.addWidget(self._actions)
        self._actions.setVisible(False)

        self._reset_visuals()

    # ── API publique ─────────────────────────────────────────────────────────

    def update(self, final_result: Optional[Any]) -> None:  # type: ignore[override]
        """
        Met à jour depuis FinalResult — slot UIBridge.inspection_result.
        Appelé dans le thread Qt principal (GR-05).
        """
        if final_result is None:
            self._reset_visuals()
            return

        verdict = _enum_value(getattr(final_result, "verdict", None)) or "—"
        bg      = _VERDICT_BG.get(verdict, "#333")
        dot_col = _VERDICT_DOT.get(verdict, "#aaa")

        self.setStyleSheet(
            f"ResultBand {{ background:{bg}; border-radius:8px; }}"
            " QLabel { color:#fff; }"
        )
        self._dot.setStyleSheet(f"color:{dot_col};")
        self._verdict.setText(verdict)

        # SeverityBadge
        sev = getattr(final_result, "severity", None)
        if sev is not None and not isinstance(sev, SeverityLevel):
            sev = _coerce_severity(_enum_value(sev))
        self._severity_badge.set_severity(sev)

        # Ligne 2 : fail_tier + fail_reasons (uniquement si NOK)
        if verdict == "NOK":
            ft     = _enum_value(getattr(final_result, "fail_tier", None))
            reasons = list(getattr(final_result, "fail_reasons", ()) or [])
            head    = f"Tier {ft} échoué" if ft else "Échec d'inspection"
            tail    = " · ".join(reasons) if reasons else ""
            self._fail_line.setText(f"{head}  —  {tail}" if tail else head)
            self._fail_line.setVisible(True)
        else:
            self._fail_line.setText("")
            self._fail_line.setVisible(False)

        # Ligne 3 : LLM (display only — GR-04)
        llm = getattr(final_result, "llm_explanation", None)
        summary = getattr(llm, "summary", None) if llm is not None else None
        if summary:
            self._llm_line.setText(f"💬  {summary}")
            self._llm_line.setVisible(True)
        else:
            self._llm_line.setText("")
            self._llm_line.setVisible(False)

        # Ligne 4 : actions REVIEW
        self._actions.setVisible(verdict == "REVIEW")

    def reset(self) -> None:
        self._reset_visuals()

    # ── Internes ─────────────────────────────────────────────────────────────

    def _reset_visuals(self) -> None:
        self.setStyleSheet(
            "ResultBand { background:#202020; border-radius:8px; }"
            " QLabel { color:#ddd; }"
        )
        self._dot.setStyleSheet("color:#888;")
        self._verdict.setText("—")
        self._severity_badge.set_severity(None)
        self._fail_line.setText("")
        self._fail_line.setVisible(False)
        self._llm_line.setText("")
        self._llm_line.setVisible(False)
        self._actions.setVisible(False)


def _enum_value(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


def _coerce_severity(name: Any) -> Optional[SeverityLevel]:
    if name is None:
        return None
    try:
        return SeverityLevel(name)
    except (ValueError, TypeError):
        return None
