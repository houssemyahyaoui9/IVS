"""
TierPriorityWidget — Tableau critères + Preview résumé — §12.

GR-08 : ce widget définit les ProductRules ; il NE prend AUCUNE décision verdict.
GR-12 : modifications interdites pendant RUNNING (set_running_state(True)).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ts2i_ivs.core.models import CriterionRule, ProductRules
from ts2i_ivs.core.tier_result import TierLevel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Mapping observer_id par type de critère — §12
# ─────────────────────────────────────────────────────────────────────────────

_OBSERVER_PRESENCE = "yolo_v8x"
_OBSERVER_COLOR    = "color_de2000"
_OBSERVER_POSITION = "sift"
_OBSERVER_TEXTURE  = "surface_mini_ensemble"
_OBSERVER_OCR      = "ocr_tesseract"
_OBSERVER_BARCODE  = "barcode_pyzbar"


_TIER_COMBO_LABELS: dict[TierLevel, str] = {
    TierLevel.CRITICAL: "CRITICAL — NOK immédiat",
    TierLevel.MAJOR:    "MAJOR    — NOK retouchable",
    TierLevel.MINOR:    "MINOR    — REVIEW",
}

_TIER_LIST: tuple[TierLevel, ...] = (
    TierLevel.CRITICAL, TierLevel.MAJOR, TierLevel.MINOR,
)

_COL_LABEL     = 0
_COL_ENABLED   = 1
_COL_TIER      = 2
_COL_THRESHOLD = 3
_COL_MANDATORY = 4

_COLS = ("Critère", "Activé", "Tier", "Seuil", "Obligatoire")


# ─────────────────────────────────────────────────────────────────────────────
#  Spec d'un critère pré-rempli
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _CriterionSpec:
    label             : str
    default_tier      : TierLevel
    default_enabled   : bool
    default_threshold : str          # texte affiché ("—", "ΔE ≤ 8.0", "±5mm", "0.30")
    default_mandatory : bool
    observer_id       : str
    extra_details     : dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
#  TierPriorityWidget
# ─────────────────────────────────────────────────────────────────────────────

class TierPriorityWidget(QWidget):
    """
    Tableau critères (gauche) + preview résumé (droite) — §12.

    Construction :
        widget = TierPriorityWidget(product_def=product_def)
        widget.set_running_state(False)
        rules = widget.to_product_rules()
    """

    def __init__(
        self,
        product_def : Optional[Any] = None,
        parent      = None,
    ) -> None:
        super().__init__(parent)
        self._product_def = product_def
        self._product_id  = getattr(product_def, "product_id", "PRODUCT") if product_def else "PRODUCT"
        self._is_running  = False

        self._specs : list[_CriterionSpec] = self._build_specs(product_def)

        # Layout principal — splitter
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._table    = self._build_table()
        self._preview  = self._build_preview()
        self._splitter.addWidget(self._table)
        self._splitter.addWidget(self._preview)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        outer.addWidget(self._splitter)

        self._populate_table()
        self._refresh_preview()
        self._table.cellChanged.connect(self._on_cell_changed)

    # ─────────────────────────────────────────────────────────────────────────
    #  API publique
    # ─────────────────────────────────────────────────────────────────────────

    def set_running_state(self, running: bool) -> None:
        """GR-12 : si RUNNING → widget entier désactivé (lecture seule visuelle)."""
        self._is_running = bool(running)
        self.setEnabled(not self._is_running)
        # Bandeau visuel sur le preview
        self._refresh_preview()

    @property
    def product_id(self) -> str:
        return self._product_id

    def to_product_rules(self) -> ProductRules:
        """Construit ProductRules depuis l'état courant du tableau."""
        criteria: list[CriterionRule] = []
        for row, spec in enumerate(self._specs):
            if not self._row_enabled(row):
                continue
            tier      = self._row_tier(row)
            threshold = self._row_threshold_value(row)
            mandatory = self._row_mandatory(row)

            criteria.append(CriterionRule(
                criterion_id = self._make_criterion_id(spec.label),
                label        = spec.label,
                tier         = tier,
                observer_id  = spec.observer_id,
                threshold    = float(threshold),
                enabled      = True,
                mandatory    = mandatory,
                details      = {
                    "raw_threshold": self._row_threshold_text(row),
                    **spec.extra_details,
                },
            ))
        return ProductRules(product_id=self._product_id, criteria=tuple(criteria))

    @property
    def table(self) -> QTableWidget:
        return self._table

    # ─────────────────────────────────────────────────────────────────────────
    #  Construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_specs(self, product_def: Optional[Any]) -> list[_CriterionSpec]:
        specs: list[_CriterionSpec] = []
        logos = list(getattr(product_def, "logo_definitions", []) or [])

        for logo in logos:
            label_logo = getattr(logo, "name", None) or getattr(logo, "label", None) \
                         or getattr(logo, "logo_id", "logo")
            logo_id    = getattr(logo, "logo_id", label_logo)
            specs.append(_CriterionSpec(
                label=f"Présence {label_logo}",
                default_tier=TierLevel.CRITICAL,
                default_enabled=True,
                default_threshold="—",
                default_mandatory=True,
                observer_id=_OBSERVER_PRESENCE,
                extra_details={"logo_id": logo_id, "kind": "presence"},
            ))
            specs.append(_CriterionSpec(
                label=f"Couleur {label_logo}",
                default_tier=TierLevel.MAJOR,
                default_enabled=True,
                default_threshold="ΔE ≤ 8.0",
                default_mandatory=True,
                observer_id=_OBSERVER_COLOR,
                extra_details={"logo_id": logo_id, "kind": "color"},
            ))
            specs.append(_CriterionSpec(
                label=f"Position {label_logo}",
                default_tier=TierLevel.MAJOR,
                default_enabled=True,
                default_threshold="±5mm",
                default_mandatory=True,
                observer_id=_OBSERVER_POSITION,
                extra_details={"logo_id": logo_id, "kind": "position"},
            ))

        # Critères optionnels (désactivés par défaut)
        specs.append(_CriterionSpec(
            label="Caliper largeur",  default_tier=TierLevel.MAJOR,
            default_enabled=False, default_threshold="±2mm", default_mandatory=True,
            observer_id="caliper_width",
            extra_details={"measurement_id": "width", "kind": "caliper"},
        ))
        specs.append(_CriterionSpec(
            label="Caliper hauteur", default_tier=TierLevel.MAJOR,
            default_enabled=False, default_threshold="±2mm", default_mandatory=True,
            observer_id="caliper_height",
            extra_details={"measurement_id": "height", "kind": "caliper"},
        ))
        specs.append(_CriterionSpec(
            label="Texture surface", default_tier=TierLevel.MINOR,
            default_enabled=False, default_threshold="0.30", default_mandatory=False,
            observer_id=_OBSERVER_TEXTURE,
            extra_details={"kind": "texture"},
        ))
        specs.append(_CriterionSpec(
            label="OCR numéro série", default_tier=TierLevel.MINOR,
            default_enabled=False, default_threshold="—", default_mandatory=False,
            observer_id=_OBSERVER_OCR,
            extra_details={"kind": "ocr"},
        ))
        specs.append(_CriterionSpec(
            label="Barcode", default_tier=TierLevel.MINOR,
            default_enabled=False, default_threshold="—", default_mandatory=False,
            observer_id=_OBSERVER_BARCODE,
            extra_details={"kind": "barcode"},
        ))
        return specs

    def _build_table(self) -> QTableWidget:
        t = QTableWidget(len(self._specs), len(_COLS))
        t.setHorizontalHeaderLabels(list(_COLS))
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
        )
        header = t.horizontalHeader()
        header.setSectionResizeMode(_COL_LABEL,     QHeaderView.ResizeMode.Stretch)
        for col in (_COL_ENABLED, _COL_TIER, _COL_THRESHOLD, _COL_MANDATORY):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        return t

    def _build_preview(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame.setStyleSheet(
            "QFrame { background:#161616; border:1px solid #2a2a2a; border-radius:6px; }"
            " QLabel { color:#eee; }"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Résumé Tier-based")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        self._lbl_critical = QLabel("")
        self._lbl_major    = QLabel("")
        self._lbl_minor    = QLabel("")
        for lbl in (self._lbl_critical, self._lbl_major, self._lbl_minor):
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(lbl)

        self._lbl_warn = QLabel("")
        self._lbl_warn.setWordWrap(True)
        self._lbl_warn.setStyleSheet(
            "QLabel { background:#3a2a00; color:#FFC107; padding:6px;"
            " border:1px solid #FFC107; border-radius:4px; }"
        )
        layout.addWidget(self._lbl_warn)
        layout.addStretch(1)

        return frame

    # ─────────────────────────────────────────────────────────────────────────
    #  Population du tableau
    # ─────────────────────────────────────────────────────────────────────────

    def _populate_table(self) -> None:
        self._table.blockSignals(True)
        try:
            for row, spec in enumerate(self._specs):
                # Col 0 : Critère (texte non éditable)
                item = QTableWidgetItem(spec.label)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, _COL_LABEL, item)

                # Col 1 : Activé (checkbox centrée)
                self._table.setCellWidget(
                    row, _COL_ENABLED,
                    _checkbox_cell(spec.default_enabled, self._on_widget_changed),
                )

                # Col 2 : Tier (combobox)
                combo = QComboBox()
                for tier in _TIER_LIST:
                    combo.addItem(_TIER_COMBO_LABELS[tier], tier)
                combo.setCurrentIndex(_TIER_LIST.index(spec.default_tier))
                combo.currentIndexChanged.connect(self._on_widget_changed)
                self._table.setCellWidget(row, _COL_TIER, combo)

                # Col 3 : Seuil (lineedit avec validation)
                edit = QLineEdit(spec.default_threshold)
                edit.setProperty("row", row)
                edit.textChanged.connect(self._on_threshold_changed)
                self._table.setCellWidget(row, _COL_THRESHOLD, edit)

                # Col 4 : Obligatoire (checkbox)
                self._table.setCellWidget(
                    row, _COL_MANDATORY,
                    _checkbox_cell(spec.default_mandatory, self._on_widget_changed),
                )
        finally:
            self._table.blockSignals(False)

        # Validation initiale (couleur bordure)
        for row in range(len(self._specs)):
            self._validate_threshold_field(row)

    # ─────────────────────────────────────────────────────────────────────────
    #  Slots
    # ─────────────────────────────────────────────────────────────────────────

    def _on_cell_changed(self, *_: Any) -> None:
        self._refresh_preview()

    def _on_widget_changed(self, *_: Any) -> None:
        self._refresh_preview()

    def _on_threshold_changed(self, _text: str) -> None:
        sender = self.sender()
        row = sender.property("row") if sender is not None else None
        if isinstance(row, int):
            self._validate_threshold_field(row)
        self._refresh_preview()

    # ─────────────────────────────────────────────────────────────────────────
    #  Lecture lignes
    # ─────────────────────────────────────────────────────────────────────────

    def _row_enabled(self, row: int) -> bool:
        return _checkbox_value(self._table.cellWidget(row, _COL_ENABLED))

    def _row_mandatory(self, row: int) -> bool:
        return _checkbox_value(self._table.cellWidget(row, _COL_MANDATORY))

    def _row_tier(self, row: int) -> TierLevel:
        combo = self._table.cellWidget(row, _COL_TIER)
        if isinstance(combo, QComboBox):
            data = combo.currentData()
            if isinstance(data, TierLevel):
                return data
        return TierLevel.MINOR

    def _row_threshold_text(self, row: int) -> str:
        edit = self._table.cellWidget(row, _COL_THRESHOLD)
        if isinstance(edit, QLineEdit):
            return edit.text()
        return ""

    def _row_threshold_value(self, row: int) -> float:
        return _parse_threshold(self._row_threshold_text(row))

    def _row_label(self, row: int) -> str:
        item = self._table.item(row, _COL_LABEL)
        return item.text() if item is not None else self._specs[row].label

    # ─────────────────────────────────────────────────────────────────────────
    #  Validation seuil
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_threshold_field(self, row: int) -> bool:
        edit = self._table.cellWidget(row, _COL_THRESHOLD)
        if not isinstance(edit, QLineEdit):
            return True
        text = edit.text().strip()
        # "—" ou vide acceptés (placeholder pas de seuil applicable)
        if text in ("", "—", "-"):
            edit.setStyleSheet("")
            return True
        ok = _parse_threshold(text) > 0.0 or text in ("auto",)
        if ok:
            edit.setStyleSheet("")
        else:
            edit.setStyleSheet("QLineEdit { border:1px solid #E53935; background:#3a0000;"
                               " color:#fff; }")
        return ok

    # ─────────────────────────────────────────────────────────────────────────
    #  Preview
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_preview(self) -> None:
        groups: dict[TierLevel, list[str]] = {t: [] for t in _TIER_LIST}
        for row in range(len(self._specs)):
            if not self._row_enabled(row):
                continue
            groups[self._row_tier(row)].append(self._row_label(row))

        self._lbl_critical.setText(self._fmt_group(
            "🔴", "CRITICAL", "NOK immédiat si fail",  groups[TierLevel.CRITICAL], "#FF6B6B"))
        self._lbl_major.setText(self._fmt_group(
            "🟠", "MAJOR",    "NOK retouchable si fail", groups[TierLevel.MAJOR],    "#FFA94D"))
        self._lbl_minor.setText(self._fmt_group(
            "🟡", "MINOR",    "REVIEW si fail",         groups[TierLevel.MINOR],    "#FFD166"))

        if not groups[TierLevel.CRITICAL]:
            self._lbl_warn.setText(
                "⚠ Aucun critère CRITICAL défini.\n"
                "Sans critère bloquant, le système ne pourra pas émettre de NOK immédiat."
            )
            self._lbl_warn.setVisible(True)
        else:
            self._lbl_warn.setText("")
            self._lbl_warn.setVisible(False)

    @staticmethod
    def _fmt_group(icon: str, name: str, subtitle: str,
                   items: list[str], color: str) -> str:
        head = f'<p><b style="color:{color};">{icon} {name} ({len(items)} critères)</b>' \
               f' <span style="color:#aaa;">— {subtitle}</span></p>'
        if not items:
            return head + '<p style="color:#888; margin-left:14px;">(aucun)</p>'
        body = "".join(f'<li style="color:#ddd;">{html_escape(it)}</li>' for it in items)
        return head + f'<ul style="margin:0 0 6px 14px;">{body}</ul>'

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _make_criterion_id(self, label: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").lower()
        return f"{self._product_id.lower()}_{slug}" if slug else f"{self._product_id.lower()}_crit"


# ═════════════════════════════════════════════════════════════════════════════
#  Helpers cellule
# ═════════════════════════════════════════════════════════════════════════════

def _checkbox_cell(checked: bool, on_change) -> QWidget:
    """Cellule contenant une QCheckBox centrée (le QTableWidget ne le fait pas seul)."""
    container = QWidget()
    layout    = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cb = QCheckBox()
    cb.setChecked(bool(checked))
    cb.stateChanged.connect(on_change)
    layout.addWidget(cb)
    container.setProperty("checkbox", cb)
    return container


def _checkbox_value(cell: Optional[QWidget]) -> bool:
    if cell is None:
        return False
    cb = cell.property("checkbox") if hasattr(cell, "property") else None
    if isinstance(cb, QCheckBox):
        return cb.isChecked()
    return False


_THRESHOLD_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _parse_threshold(text: str) -> float:
    """Extrait la première valeur numérique du texte ('ΔE ≤ 8.0' → 8.0, '±5mm' → 5.0)."""
    if not text:
        return 0.0
    if text.strip() in ("—", "-"):
        return 0.0
    if text.strip() == "auto":
        return 0.0
    m = _THRESHOLD_NUM_RE.search(text)
    if not m:
        return 0.0
    try:
        return abs(float(m.group(0).replace(",", ".")))
    except ValueError:
        return 0.0


def html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))
