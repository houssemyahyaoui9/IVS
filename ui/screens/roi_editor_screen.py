"""
RoiEditorScreen — Éditeur de zones ROI — §12.2
GR-03 : UI → SystemController (jamais pipeline direct).
GR-12 : FORBIDDEN pendant SystemState.RUNNING.
GR-05 : toutes les opérations Qt dans le thread principal.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.models import BoundingBox, CriterionRule
from core.tier_result import TierLevel
from ui.components.roi_editor_widget import RoiEditorWidget, RoiZone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  PropertiesPanel — panneau droite
# ─────────────────────────────────────────────────────────────────────────────

class _PropertiesPanel(QWidget):
    """
    Panneau de propriétés d'une zone sélectionnée/créée.
    Émet zone_changed(RoiZone) quand l'utilisateur applique les changements.
    """

    zone_changed = pyqtSignal(object)   # RoiZone

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_zone: Optional[RoiZone] = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Propriétés de la zone")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        root.addWidget(title)

        form_group = QGroupBox("Général")
        form = QFormLayout(form_group)

        self._label_edit = QLineEdit()
        form.addRow("Nom :", self._label_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["roi", "ocr", "caliper", "color"])
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addRow("Type :", self._type_combo)

        self._tier_combo = QComboBox()
        self._tier_combo.addItems(["CRITICAL", "MAJOR", "MINOR"])
        form.addRow("Tier :", self._tier_combo)

        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.0, 1.0)
        self._threshold_spin.setSingleStep(0.05)
        self._threshold_spin.setDecimals(2)
        self._threshold_spin.setValue(0.80)
        form.addRow("Seuil :", self._threshold_spin)

        self._mandatory_cb = QCheckBox("Critère mandatory")
        form.addRow("", self._mandatory_cb)

        root.addWidget(form_group)

        # Details dynamiques selon le type
        self._details_group = QGroupBox("Détails")
        self._details_layout = QFormLayout(self._details_group)
        root.addWidget(self._details_group)

        # Champs détails (visibles selon le type)
        self._ocr_pattern  = QLineEdit()
        self._ocr_pattern.setPlaceholderText(r"ex : \d{4}-[A-Z]+")
        self._details_layout.addRow("Pattern regex :", self._ocr_pattern)

        self._cal_expected = QDoubleSpinBox()
        self._cal_expected.setRange(0.0, 9999.0)
        self._cal_expected.setDecimals(2)
        self._cal_expected.setSuffix(" mm")
        self._details_layout.addRow("Dimension attendue :", self._cal_expected)

        self._cal_tolerance = QDoubleSpinBox()
        self._cal_tolerance.setRange(0.0, 999.0)
        self._cal_tolerance.setDecimals(2)
        self._cal_tolerance.setSuffix(" mm")
        self._details_layout.addRow("Tolérance (±mm) :", self._cal_tolerance)

        self._cal_direction = QComboBox()
        self._cal_direction.addItems(["horizontal", "vertical"])
        self._details_layout.addRow("Direction :", self._cal_direction)

        self._color_delta_e = QDoubleSpinBox()
        self._color_delta_e.setRange(0.0, 100.0)
        self._color_delta_e.setDecimals(1)
        self._color_delta_e.setValue(8.0)
        self._details_layout.addRow("ΔE tolérance :", self._color_delta_e)

        # Bouton Appliquer
        apply_btn = QPushButton("Appliquer")
        apply_btn.clicked.connect(self._apply)
        root.addWidget(apply_btn)

        root.addStretch()

        # Affichage initial
        self.set_zone(None)

    # ── API publique ──────────────────────────────────────────────────────────

    def set_zone(self, zone: Optional[RoiZone]) -> None:
        """Remplit le formulaire depuis une zone (None = vide + désactivé)."""
        self._current_zone = zone
        enabled            = zone is not None
        self.setEnabled(enabled)

        if zone is None:
            return

        self._label_edit.setText(zone.label)
        idx = self._type_combo.findText(zone.zone_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        idx = self._tier_combo.findText(zone.tier.value)
        if idx >= 0:
            self._tier_combo.setCurrentIndex(idx)
        self._threshold_spin.setValue(zone.threshold)
        self._mandatory_cb.setChecked(zone.mandatory)

        # Details
        self._ocr_pattern.setText(zone.details.get("expected_pattern", ""))
        self._cal_expected.setValue(float(zone.details.get("expected_mm", 0.0)))
        self._cal_tolerance.setValue(float(zone.details.get("tolerance_mm", 0.5)))
        d_idx = self._cal_direction.findText(zone.details.get("direction", "horizontal"))
        if d_idx >= 0:
            self._cal_direction.setCurrentIndex(d_idx)
        self._color_delta_e.setValue(float(zone.details.get("delta_e_tolerance", 8.0)))

        self._on_type_changed(zone.zone_type)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_type_changed(self, zone_type: str) -> None:
        """Adapte les champs détails et verrouille le Tier si nécessaire."""
        fixed_tier = {"ocr": "MINOR", "caliper": "MAJOR", "color": "MAJOR"}
        if zone_type in fixed_tier:
            t_idx = self._tier_combo.findText(fixed_tier[zone_type])
            self._tier_combo.setCurrentIndex(t_idx)
            self._tier_combo.setEnabled(False)
        else:
            self._tier_combo.setEnabled(True)

        is_ocr     = zone_type == "ocr"
        is_caliper = zone_type == "caliper"
        is_color   = zone_type == "color"

        self._ocr_pattern.setVisible(is_ocr)
        self._details_layout.labelForField(self._ocr_pattern) and (
            self._details_layout.labelForField(self._ocr_pattern).setVisible(is_ocr)
        )
        for w in [self._cal_expected, self._cal_tolerance, self._cal_direction]:
            w.setVisible(is_caliper)
        for label in ["Dimension attendue :", "Tolérance (±mm) :", "Direction :"]:
            lbl = self._details_layout.labelForField
            # Labels gérés via setVisible des widgets — Qt masque les lignes vides
        for w in [self._cal_expected, self._cal_tolerance, self._cal_direction]:
            lbl = self._details_layout.labelForField(w)
            if lbl:
                lbl.setVisible(is_caliper)
        self._color_delta_e.setVisible(is_color)
        lbl = self._details_layout.labelForField(self._color_delta_e)
        if lbl:
            lbl.setVisible(is_color)

        self._details_group.setVisible(is_ocr or is_caliper or is_color)

    def _apply(self) -> None:
        if self._current_zone is None:
            return

        zone_type = self._type_combo.currentText()
        tier_str  = self._tier_combo.currentText()
        tier      = TierLevel[tier_str]

        details: dict = {}
        if zone_type == "ocr":
            pat = self._ocr_pattern.text().strip()
            if pat:
                details["expected_pattern"] = pat
        elif zone_type == "caliper":
            details["expected_mm"]   = self._cal_expected.value()
            details["tolerance_mm"]  = self._cal_tolerance.value()
            details["direction"]     = self._cal_direction.currentText()
        elif zone_type == "color":
            details["delta_e_tolerance"] = self._color_delta_e.value()

        updated = RoiZone(
            zone_id   = self._current_zone.zone_id,
            zone_type = zone_type,
            bbox_rel  = self._current_zone.bbox_rel,
            tier      = tier,
            label     = self._label_edit.text().strip() or self._current_zone.zone_id,
            threshold = self._threshold_spin.value(),
            mandatory = self._mandatory_cb.isChecked(),
            details   = details,
        )
        self._current_zone = updated
        self.zone_changed.emit(updated)


# ─────────────────────────────────────────────────────────────────────────────
#  RoiEditorScreen
# ─────────────────────────────────────────────────────────────────────────────

class RoiEditorScreen(QDialog):
    """
    Éditeur de zones ROI — §12.2.

    Ouvrable depuis ProductCreationScreen et depuis menu Produits.
    GR-12 : FORBIDDEN si system_state callable retourne SystemState.RUNNING.
    GR-03 : la sauvegarde appelle on_save(rules) — jamais le pipeline directement.

    Args :
        product_id       : identifiant du produit
        products_root    : racine products/
        system_state_fn  : callable() → SystemState | None — pour GR-12
        on_save          : callable(list[CriterionRule]) → None — via controller
        config           : dict-like config système
    """

    zones_saved = pyqtSignal(list)   # list[CriterionRule]

    def __init__(
        self,
        product_id:      str,
        products_root:   Path              = Path("products"),
        system_state_fn: Callable | None   = None,
        on_save:         Callable | None   = None,
        config:          Any               = None,
        parent:          QWidget | None    = None,
    ) -> None:
        super().__init__(parent)
        cfg  = config or {}
        _get = cfg.get if hasattr(cfg, "get") else lambda k, d=None: d

        self._product_id    = product_id
        self._products_root = Path(products_root)
        self._state_fn      = system_state_fn
        self._on_save       = on_save
        self._max_zones     = int(_get("config.observers.roi.max_count",   20))
        self._min_size_px   = int(_get("config.observers.roi.min_size_px", 10))

        self.setWindowTitle(f"Éditeur ROI — {product_id}")
        self.setMinimumSize(1000, 650)

        self._build_ui()
        self._check_running_lock()
        self._load_reference_image()
        self._load_existing_zones()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Toolbar ──
        toolbar = self._build_toolbar()
        root.addWidget(toolbar)

        # ── RUNNING warning banner ──
        self._running_banner = QLabel(
            "⛔  Arrêter l'inspection avant d'éditer les zones"
        )
        self._running_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._running_banner.setStyleSheet(
            "background:#FF4444; color:white; font-weight:bold; padding:6px;"
        )
        self._running_banner.setVisible(False)
        root.addWidget(self._running_banner)

        # ── Splitter canvas | propriétés ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._canvas = RoiEditorWidget(
            max_zones=self._max_zones,
            min_size_px=self._min_size_px,
        )
        self._canvas.zone_selected.connect(self._on_zone_selected)
        self._canvas.zone_created.connect(self._on_zone_created)
        self._canvas.zones_changed.connect(self._on_zones_changed)

        splitter.addWidget(self._canvas)

        # Scroll area pour propriétés
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(260)
        scroll.setMaximumWidth(320)

        self._props = _PropertiesPanel()
        self._props.zone_changed.connect(self._on_zone_property_changed)
        scroll.setWidget(self._props)
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

        # ── Status bar ──
        self._status = QLabel("Prêt — Mode dessin actif")
        self._status.setStyleSheet("color:#aaa; padding:2px 6px;")
        root.addWidget(self._status)

        # ── Boutons dialog ──
        btn_box = QDialogButtonBox()
        self._save_btn   = btn_box.addButton("Sauvegarder",  QDialogButtonBox.StandardButton.AcceptRole)
        self._cancel_btn = btn_box.addButton("Annuler",      QDialogButtonBox.StandardButton.RejectRole)
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        h   = QHBoxLayout(bar)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)

        # Mode
        self._draw_btn   = QPushButton("✏ Dessiner")
        self._select_btn = QPushButton("☞ Sélectionner")
        self._draw_btn.setCheckable(True)
        self._select_btn.setCheckable(True)
        self._draw_btn.setChecked(True)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self._draw_btn)
        mode_group.addButton(self._select_btn)
        self._draw_btn.toggled.connect(
            lambda checked: self._canvas.set_draw_mode(checked)
        )

        h.addWidget(QLabel("Mode :"))
        h.addWidget(self._draw_btn)
        h.addWidget(self._select_btn)
        h.addSpacing(12)

        # Type de zone
        h.addWidget(QLabel("Type :"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["roi", "ocr", "caliper", "color"])
        self._type_combo.currentTextChanged.connect(self._on_toolbar_type_changed)
        h.addWidget(self._type_combo)
        h.addSpacing(12)

        # Tier (pour type "roi")
        h.addWidget(QLabel("Tier :"))
        self._tier_combo = QComboBox()
        self._tier_combo.addItems(["CRITICAL", "MAJOR", "MINOR"])
        self._tier_combo.currentTextChanged.connect(
            lambda t: self._canvas.set_default_tier(TierLevel[t])
        )
        h.addWidget(self._tier_combo)
        h.addSpacing(12)

        # Supprimer / Tout effacer
        del_btn  = QPushButton("🗑 Supprimer")
        del_btn.clicked.connect(self._canvas.delete_selected)
        clear_btn = QPushButton("Effacer tout")
        clear_btn.clicked.connect(self._confirm_clear)
        h.addWidget(del_btn)
        h.addWidget(clear_btn)

        h.addStretch()

        # Compteur
        self._zone_count_lbl = QLabel("0 / 20 zones")
        h.addWidget(self._zone_count_lbl)

        return bar

    # ── GR-12 : vérification état RUNNING ────────────────────────────────────

    def _check_running_lock(self) -> None:
        """Applique GR-12 : bloque l'édition si RUNNING."""
        from core.models import SystemState

        is_running = False
        if self._state_fn is not None:
            try:
                state      = self._state_fn()
                is_running = state == SystemState.RUNNING
            except Exception:
                pass

        self._canvas.set_editable(not is_running)
        self._running_banner.setVisible(is_running)
        if hasattr(self, "_save_btn"):
            self._save_btn.setEnabled(not is_running)
        if hasattr(self, "_draw_btn"):
            self._draw_btn.setEnabled(not is_running)
            self._select_btn.setEnabled(not is_running)

    # ── Chargement image de référence ─────────────────────────────────────────

    def _load_reference_image(self) -> None:
        candidates = [
            self._products_root / self._product_id / "reference.jpg",
            self._products_root / self._product_id / "reference.png",
            self._products_root / self._product_id / "calibration" / "reference.jpg",
        ]
        for path in candidates:
            if path.exists():
                pm = QPixmap(str(path))
                if not pm.isNull():
                    self._canvas.set_reference_image(pm)
                    logger.debug("RoiEditorScreen: image référence chargée %s", path)
                    return
        logger.info("RoiEditorScreen: aucune image de référence trouvée pour '%s'", self._product_id)

    # ── Chargement zones existantes depuis config.json ───────────────────────

    def _load_existing_zones(self) -> None:
        config_path = self._products_root / self._product_id / "config.json"
        if not config_path.exists():
            return
        try:
            with open(config_path, encoding="utf-8") as fh:
                data = json.load(fh)
            criteria = data.get("criteria", [])
            zones    = []
            for c in criteria:
                details  = dict(c.get("details", {}))
                bbox_raw = details.pop("bbox_rel", None)
                if bbox_raw is None:
                    continue
                try:
                    bbox = BoundingBox(
                        x=float(bbox_raw["x"]),
                        y=float(bbox_raw["y"]),
                        w=float(bbox_raw["w"]),
                        h=float(bbox_raw["h"]),
                    )
                except (KeyError, ValueError):
                    continue

                # Déduire zone_type depuis observer_id
                obs_id    = c.get("observer_id", "")
                zone_type = _observer_id_to_zone_type(obs_id)

                tier_str = c.get("tier", "MINOR")
                try:
                    tier = TierLevel[tier_str]
                except KeyError:
                    tier = TierLevel.MINOR

                zones.append(RoiZone(
                    zone_id   = c.get("criterion_id", f"zone_{len(zones)}"),
                    zone_type = zone_type,
                    bbox_rel  = bbox,
                    tier      = tier,
                    label     = c.get("label", ""),
                    threshold = float(c.get("threshold", 0.80)),
                    mandatory = bool(c.get("mandatory", False)),
                    details   = details,
                ))
            self._canvas.set_zones(zones)
            self._update_zone_count()
            logger.info(
                "RoiEditorScreen: %d zones chargées depuis config.json", len(zones)
            )
        except Exception as exc:
            logger.error("RoiEditorScreen: erreur chargement zones — %s", exc)

    # ── Sauvegarde ────────────────────────────────────────────────────────────

    def _save(self) -> None:
        """Sauvegarde via on_save callback (GR-03 — jamais pipeline direct)."""
        rules = self._canvas.to_criterion_rules()

        if self._on_save is not None:
            try:
                self._on_save(rules)
            except Exception as exc:
                QMessageBox.critical(self, "Erreur sauvegarde", str(exc))
                return
        else:
            # Sauvegarde directe dans config.json si pas de controller
            self._save_to_config(rules)

        self.zones_saved.emit(rules)
        logger.info(
            "RoiEditorScreen: %d règles sauvegardées pour '%s'",
            len(rules), self._product_id,
        )
        self.accept()

    def _save_to_config(self, rules: list[CriterionRule]) -> None:
        """Fallback : écrit directement dans products/{id}/config.json."""
        config_path = self._products_root / self._product_id / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                pass

        data["criteria"] = [
            {
                "criterion_id": r.criterion_id,
                "label":        r.label,
                "tier":         r.tier.value,
                "observer_id":  r.observer_id,
                "threshold":    r.threshold,
                "enabled":      r.enabled,
                "mandatory":    r.mandatory,
                "details":      r.details,
            }
            for r in rules
        ]

        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_zone_selected(self, zone: Optional[RoiZone]) -> None:
        self._props.set_zone(zone)
        if zone:
            self._status.setText(
                f"Zone sélectionnée : {zone.label} ({zone.zone_type} / {zone.tier.value})"
            )
        else:
            self._status.setText("Aucune zone sélectionnée")

    def _on_zone_created(self, zone: RoiZone) -> None:
        self._props.set_zone(zone)
        self._update_zone_count()
        self._status.setText(f"Zone créée : {zone.zone_id}")

    def _on_zones_changed(self) -> None:
        self._update_zone_count()

    def _on_zone_property_changed(self, zone: RoiZone) -> None:
        self._canvas.update_selected_zone(zone)

    def _on_toolbar_type_changed(self, zone_type: str) -> None:
        self._canvas.set_zone_type(zone_type)
        fixed_tier = {"ocr": "MINOR", "caliper": "MAJOR", "color": "MAJOR"}
        if zone_type in fixed_tier:
            idx = self._tier_combo.findText(fixed_tier[zone_type])
            self._tier_combo.setCurrentIndex(idx)
            self._tier_combo.setEnabled(False)
            self._canvas.set_default_tier(TierLevel[fixed_tier[zone_type]])
        else:
            self._tier_combo.setEnabled(True)

    def _confirm_clear(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmation",
            "Supprimer toutes les zones ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._canvas.clear_all()

    def _update_zone_count(self) -> None:
        n = len(self._canvas.zones)
        color = "#FF4444" if n >= self._max_zones else "#aaa"
        self._zone_count_lbl.setStyleSheet(f"color:{color};")
        self._zone_count_lbl.setText(f"{n} / {self._max_zones} zones")
        self._status.setText(f"{n} zone(s) définies")


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _observer_id_to_zone_type(observer_id: str) -> str:
    """Déduit le zone_type depuis l'observer_id (lecture config.json)."""
    if "tesseract" in observer_id or observer_id.startswith("ocr"):
        return "ocr"
    if "caliper" in observer_id:
        return "caliper"
    if "color" in observer_id or "delta_e" in observer_id:
        return "color"
    return "roi"
