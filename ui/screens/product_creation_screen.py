"""
ProductCreationScreen — Wizard 8 étapes v7.0
Création produit complète avec définition Tiers.

GR-03 : UI → SystemController → Pipeline
GR-12 : FORBIDDEN pendant RUNNING
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────────────────────

TIER_OPTIONS = ["CRITICAL — NOK immédiat", "MAJOR — NOK retouchable", "MINOR — REVIEW"]
TIER_MAP = {
    "CRITICAL — NOK immédiat": "CRITICAL",
    "MAJOR — NOK retouchable": "MAJOR",
    "MINOR — REVIEW": "MINOR",
}
OBSERVER_MAP = {
    "Présence": "yolo_v8x",
    "Couleur":  "color_de2000",
    "Position": "sift",
    "Caliper":  "caliper",
    "Texture":  "surface_mini_ensemble",
    "OCR":      "ocr_tesseract",
    "Barcode":  "barcode_pyzbar",
}


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 1 — Métadonnées
# ─────────────────────────────────────────────────────────────────────────────

class _Step1Metadata(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("Étape 1 — Informations produit")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        form = QGroupBox("Métadonnées")
        form_layout = QVBoxLayout(form)

        self._name    = self._field(form_layout, "Nom du produit *", "Ex: Tapis Voiture P208")
        self._id      = self._field(form_layout, "ID produit *",     "Ex: P208")
        self._version = self._field(form_layout, "Version",          "1.0")
        self._barcode = self._field(form_layout, "Barcode / QR",     "Ex: TAPIS208")

        layout.addWidget(form)
        layout.addStretch()

        # auto-generate ID from name
        self._name.textChanged.connect(self._auto_id)

    def _field(self, layout, label: str, placeholder: str) -> QLineEdit:
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(160)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        row.addWidget(lbl)
        row.addWidget(edit)
        layout.addLayout(row)
        return edit

    def _auto_id(self, text: str) -> None:
        if not self._id.text():
            slug = text.upper().replace(" ", "_")[:12]
            self._id.setText(slug)

    def data(self) -> dict:
        return {
            "product_name":    self._name.text().strip(),
            "product_id":      self._id.text().strip(),
            "product_version": self._version.text().strip() or "1.0",
            "product_barcode": self._barcode.text().strip(),
        }

    def is_valid(self) -> bool:
        d = self.data()
        return bool(d["product_name"]) and bool(d["product_id"])


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 2 — Images référence
# ─────────────────────────────────────────────────────────────────────────────

class _Step2Images(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("Étape 2 — Images de référence")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Image OK (obligatoire)
        ok_group = QGroupBox("Image GOOD (obligatoire)")
        ok_layout = QVBoxLayout(ok_group)
        self._ok_label = QLabel("Aucune image sélectionnée")
        self._ok_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ok_label.setStyleSheet("border: 2px dashed #555; min-height: 120px;")
        btn_ok = QPushButton("📁 Choisir image GOOD…")
        btn_ok.clicked.connect(self._choose_ok)
        ok_layout.addWidget(self._ok_label)
        ok_layout.addWidget(btn_ok)
        layout.addWidget(ok_group)

        # Image NOK (optionnelle)
        nok_group = QGroupBox("Image BAD (optionnelle)")
        nok_layout = QVBoxLayout(nok_group)
        self._nok_label = QLabel("Optionnel — améliore l'entraînement")
        self._nok_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._nok_label.setStyleSheet("border: 2px dashed #555; min-height: 80px;")
        btn_nok = QPushButton("📁 Choisir image BAD…")
        btn_nok.clicked.connect(self._choose_nok)
        nok_layout.addWidget(self._nok_label)
        nok_layout.addWidget(btn_nok)
        layout.addWidget(nok_group)
        layout.addStretch()

        self._ok_path  : str = ""
        self._nok_path : str = ""

    def _choose_ok(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Image GOOD", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._ok_path = path
            pix = QPixmap(path).scaledToHeight(
                100, Qt.TransformationMode.SmoothTransformation
            )
            self._ok_label.setPixmap(pix)

    def _choose_nok(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Image BAD", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._nok_path = path
            self._nok_label.setText(f"✅ {Path(path).name}")

    def data(self) -> dict:
        return {"ref_image_ok": self._ok_path, "ref_image_nok": self._nok_path}

    def is_valid(self) -> bool:
        return bool(self._ok_path)


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 3 — Dimensions physiques
# ─────────────────────────────────────────────────────────────────────────────

class _Step3Dimensions(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("Étape 3 — Dimensions physiques")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        group = QGroupBox("Dimensions réelles du produit (mm)")
        g_layout = QVBoxLayout(group)

        row_w = QHBoxLayout()
        row_w.addWidget(QLabel("Largeur (mm) *"))
        self._width = QDoubleSpinBox()
        self._width.setRange(1.0, 5000.0)
        self._width.setValue(300.0)
        self._width.setSuffix(" mm")
        row_w.addWidget(self._width)
        g_layout.addLayout(row_w)

        row_h = QHBoxLayout()
        row_h.addWidget(QLabel("Hauteur (mm) *"))
        self._height = QDoubleSpinBox()
        self._height.setRange(1.0, 5000.0)
        self._height.setValue(200.0)
        self._height.setSuffix(" mm")
        row_h.addWidget(self._height)
        g_layout.addLayout(row_h)

        info = QLabel(
            "ℹ Ces dimensions servent au calcul pixel/mm lors de la calibration."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888;")
        g_layout.addWidget(info)

        layout.addWidget(group)
        layout.addStretch()

    def data(self) -> dict:
        return {
            "physical_dimensions": {
                "width_mm":  self._width.value(),
                "height_mm": self._height.value(),
            }
        }

    def is_valid(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 4 — Logos (simplifié sans canvas complet)
# ─────────────────────────────────────────────────────────────────────────────

class _Step4Logos(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("Étape 4 — Définition des logos")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "Définissez les logos à inspecter. Chaque logo génère automatiquement "
            "des critères CRITICAL (présence) et MAJOR (couleur, position)."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._logos_layout = QVBoxLayout()
        layout.addLayout(self._logos_layout)

        btn_add = QPushButton("➕ Ajouter un logo")
        btn_add.clicked.connect(self._add_logo)
        layout.addWidget(btn_add)
        layout.addStretch()

        self._logo_rows: list[dict] = []
        self._add_logo()  # logo par défaut

    def _add_logo(self) -> None:
        idx = len(self._logo_rows)
        row_widget = QGroupBox(f"Logo {idx + 1}")
        row_layout = QHBoxLayout(row_widget)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Nom logo (ex: Logo central)")
        name_edit.setText(f"Logo {idx + 1}")

        class_edit = QLineEdit()
        class_edit.setPlaceholderText("Classe YOLO (ex: logo)")
        class_edit.setText("logo")

        btn_remove = QPushButton("🗑")
        btn_remove.setFixedWidth(36)
        btn_remove.clicked.connect(lambda: self._remove_logo(row_widget))

        row_layout.addWidget(QLabel("Nom:"))
        row_layout.addWidget(name_edit)
        row_layout.addWidget(QLabel("Classe:"))
        row_layout.addWidget(class_edit)
        row_layout.addWidget(btn_remove)

        self._logos_layout.addWidget(row_widget)
        self._logo_rows.append({
            "widget": row_widget,
            "name":   name_edit,
            "class":  class_edit,
        })

    def _remove_logo(self, widget: QWidget) -> None:
        self._logo_rows = [r for r in self._logo_rows if r["widget"] != widget]
        widget.deleteLater()

    def data(self) -> dict:
        logos = []
        for i, row in enumerate(self._logo_rows):
            logos.append({
                "logo_id":       f"logo_{i}",
                "name":          row["name"].text().strip() or f"Logo {i+1}",
                "class_name":    row["class"].text().strip() or "logo",
                "tolerance_mm":  5.0,
                "expected_zone": {"x": 100.0, "y": 60.0, "w": 100.0, "h": 80.0},
            })
        return {"logo_definitions": logos}

    def is_valid(self) -> bool:
        return len(self._logo_rows) > 0


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 5 — TierPriorityWidget
# ─────────────────────────────────────────────────────────────────────────────

class _Step5Tiers(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("Étape 5 — Priorités Tier (GR-02)")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Tableau gauche ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Critères d'inspection :"))

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Critère", "Activé", "Tier", "Seuil", "Obligatoire"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 200)
        self._table.setColumnWidth(1, 60)
        self._table.setColumnWidth(2, 180)
        self._table.setColumnWidth(3, 80)
        self._table.cellChanged.connect(self._update_preview)
        left_layout.addWidget(self._table)
        splitter.addWidget(left)

        # ── Preview droite ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Résumé par Tier :"))
        self._preview = QLabel()
        self._preview.setWordWrap(True)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._preview.setStyleSheet(
            "background: #1a1a1a; padding: 12px; border-radius: 6px;"
        )
        right_layout.addWidget(self._preview)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    def populate_from_logos(self, logos: list[dict]) -> None:
        """Pré-remplit le tableau selon les logos définis à l'étape 4."""
        self._table.setRowCount(0)
        self._table.blockSignals(True)

        rows = []
        for logo in logos:
            name = logo.get("name", "Logo")
            rows += [
                (f"Présence {name}", True,  "CRITICAL — NOK immédiat",   "—",    True),
                (f"Couleur {name}",  True,  "MAJOR — NOK retouchable",   "8.0",  True),
                (f"Position {name}", True,  "MAJOR — NOK retouchable",   "5mm",  True),
            ]

        rows += [
            ("Caliper largeur",  False, "MAJOR — NOK retouchable", "2mm",  True),
            ("Caliper hauteur",  False, "MAJOR — NOK retouchable", "2mm",  True),
            ("Texture surface",  True,  "MINOR — REVIEW",          "0.30", False),
            ("OCR numéro série", False, "MINOR — REVIEW",          "—",    False),
            ("Barcode",          False, "MINOR — REVIEW",          "—",    False),
        ]

        for critere, active, tier, seuil, mandatory in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)

            self._table.setItem(r, 0, QTableWidgetItem(critere))

            chk_active = QCheckBox()
            chk_active.setChecked(active)
            chk_active.stateChanged.connect(self._update_preview)
            self._table.setCellWidget(r, 1, chk_active)

            combo = QComboBox()
            combo.addItems(TIER_OPTIONS)
            combo.setCurrentText(tier)
            combo.currentTextChanged.connect(self._update_preview)
            self._table.setCellWidget(r, 2, combo)

            self._table.setItem(r, 3, QTableWidgetItem(seuil))

            chk_mand = QCheckBox()
            chk_mand.setChecked(mandatory)
            chk_mand.stateChanged.connect(self._update_preview)
            self._table.setCellWidget(r, 4, chk_mand)

        self._table.blockSignals(False)
        self._update_preview()

    def _update_preview(self) -> None:
        tiers: dict[str, list[str]] = {"CRITICAL": [], "MAJOR": [], "MINOR": []}

        for r in range(self._table.rowCount()):
            chk = self._table.cellWidget(r, 1)
            if not (chk and chk.isChecked()):
                continue
            item = self._table.item(r, 0)
            combo = self._table.cellWidget(r, 2)
            if item and combo:
                tier_key = TIER_MAP.get(combo.currentText(), "MINOR")
                tiers[tier_key].append(item.text())

        lines = []
        icons = {"CRITICAL": "🔴", "MAJOR": "🟠", "MINOR": "🟡"}
        for tier, criteres in tiers.items():
            lines.append(
                f"<b>{icons[tier]} {tier} ({len(criteres)} critères)</b>"
            )
            for c in criteres:
                lines.append(f"&nbsp;&nbsp;• {c}")
            lines.append("")

        if not tiers["CRITICAL"]:
            lines.append(
                "<span style='color:#FF8800'>⚠ Aucun critère CRITICAL défini.<br>"
                "Le système ne pourra pas émettre de NOK immédiat.</span>"
            )

        self._preview.setText("<br>".join(lines))

    def data(self) -> dict:
        criteria = []
        for r in range(self._table.rowCount()):
            chk = self._table.cellWidget(r, 1)
            if not (chk and chk.isChecked()):
                continue
            item  = self._table.item(r, 0)
            combo = self._table.cellWidget(r, 2)
            seuil = self._table.item(r, 3)
            mand  = self._table.cellWidget(r, 4)

            if not (item and combo):
                continue

            label    = item.text()
            tier_key = TIER_MAP.get(combo.currentText(), "MINOR")
            obs_id   = next(
                (v for k, v in OBSERVER_MAP.items() if label.startswith(k)),
                "yolo_v8x",
            )

            try:
                threshold = float(seuil.text().replace("mm", "").replace("—", "0"))
            except (ValueError, AttributeError):
                threshold = 0.0

            criteria.append({
                "criterion_id": f"{obs_id}_{r}",
                "label":        label,
                "tier":         tier_key,
                "observer_id":  obs_id,
                "threshold":    threshold,
                "mandatory":    mand.isChecked() if mand else True,
                "enabled":      True,
            })

        return {"product_rules": {"criteria": criteria}}

    def is_valid(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 6 — ROI (simplifié)
# ─────────────────────────────────────────────────────────────────────────────

class _Step6ROI(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("Étape 6 — Zones d'inspection (ROI)")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "Les zones ROI permettent de limiter l'inspection à des régions précises.\n"
            "L'éditeur ROI complet est disponible depuis le menu après création du produit.\n\n"
            "Par défaut : zone complète de l'image (100%)."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        group = QGroupBox("Zone par défaut")
        g_layout = QVBoxLayout(group)

        self._full_zone = QCheckBox("Utiliser zone complète (recommandé)")
        self._full_zone.setChecked(True)
        g_layout.addWidget(self._full_zone)

        layout.addWidget(group)
        layout.addStretch()

    def data(self) -> dict:
        return {"roi_full_frame": self._full_zone.isChecked()}

    def is_valid(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 7 — Calibration
# ─────────────────────────────────────────────────────────────────────────────

class _Step7Calibration(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("Étape 7 — Calibration")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "La calibration calcule le ratio pixel/mm et les références de couleur/texture.\n"
            "Elle sera lancée automatiquement à la première activation du produit.\n\n"
            "✅ Calibration automatique activée (7 étapes — §10)"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        group = QGroupBox("Paramètres calibration")
        g_layout = QVBoxLayout(group)

        row = QHBoxLayout()
        row.addWidget(QLabel("Luminosité référence (0-255) :"))
        self._brightness = QSpinBox()
        self._brightness.setRange(50, 240)
        self._brightness.setValue(180)
        row.addWidget(self._brightness)
        g_layout.addLayout(row)

        layout.addWidget(group)
        layout.addStretch()

    def data(self) -> dict:
        return {"calibration": {"brightness_reference": self._brightness.value()}}

    def is_valid(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
#  Étape 8 — Entraînement
# ─────────────────────────────────────────────────────────────────────────────

class _Step8Training(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("Étape 8 — Entraînement des modèles")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "L'entraînement initial sera déclenché automatiquement après la calibration.\n\n"
            "Modèles qui seront entraînés :\n"
            "  🔴 CRITICAL : YOLOv8x (présence logo) + SIFT (position)\n"
            "  🟠 MAJOR    : ColorObserver (ΔE2000) + CaliperObserver\n"
            "  🟡 MINOR    : SurfaceObserver (Texture + IsoForest)"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        group = QGroupBox("Options entraînement")
        g_layout = QVBoxLayout(group)

        self._auto_train = QCheckBox("Lancer l'entraînement automatiquement (recommandé)")
        self._auto_train.setChecked(True)
        g_layout.addWidget(self._auto_train)

        row = QHBoxLayout()
        row.addWidget(QLabel("Nombre d'images minimum :"))
        self._min_images = QSpinBox()
        self._min_images.setRange(10, 1000)
        self._min_images.setValue(50)
        row.addWidget(self._min_images)
        g_layout.addLayout(row)

        layout.addWidget(group)

        # Résumé final
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(
            "background: #1a1a1a; padding: 12px; border-radius: 6px;"
        )
        layout.addWidget(QLabel("📋 Résumé produit :"))
        layout.addWidget(self._summary)
        layout.addStretch()

    def set_summary(self, data: dict) -> None:
        lines = [
            f"<b>Produit :</b> {data.get('product_name', '—')} ({data.get('product_id', '—')})",
            f"<b>Version :</b> {data.get('product_version', '1.0')}",
            f"<b>Dimensions :</b> {data.get('physical_dimensions', {}).get('width_mm', '?')} × "
            f"{data.get('physical_dimensions', {}).get('height_mm', '?')} mm",
            f"<b>Logos :</b> {len(data.get('logo_definitions', []))}",
            f"<b>Critères :</b> {len(data.get('product_rules', {}).get('criteria', []))}",
        ]
        self._summary.setText("<br>".join(lines))

    def data(self) -> dict:
        return {
            "training": {
                "auto_train": self._auto_train.isChecked(),
                "min_images": self._min_images.value(),
            }
        }

    def is_valid(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
#  ProductCreationScreen — Dialog principal
# ─────────────────────────────────────────────────────────────────────────────

class ProductCreationScreen(QDialog):
    """
    Wizard 8 étapes de création produit.
    GR-03 : sauvegarde via SystemController.
    GR-12 : FORBIDDEN pendant RUNNING.
    """

    product_created = pyqtSignal(str)  # émet product_id après création

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Wizard de création produit")
        self.setMinimumSize(900, 650)
        self.setModal(True)

        root = QVBoxLayout(self)

        # ── Header ──
        self._header = QLabel("Étape 1 / 8")
        self._header.setStyleSheet(
            "background: #2C3E50; color: white; padding: 8px 16px; "
            "font-size: 14px; font-weight: bold;"
        )
        root.addWidget(self._header)

        # ── Steps indicator ──
        self._steps_bar = self._make_steps_bar()
        root.addWidget(self._steps_bar)

        # ── Stacked pages ──
        self._stack = QStackedWidget()
        self._step1 = _Step1Metadata()
        self._step2 = _Step2Images()
        self._step3 = _Step3Dimensions()
        self._step4 = _Step4Logos()
        self._step5 = _Step5Tiers()
        self._step6 = _Step6ROI()
        self._step7 = _Step7Calibration()
        self._step8 = _Step8Training()

        for step in (
            self._step1, self._step2, self._step3, self._step4,
            self._step5, self._step6, self._step7, self._step8,
        ):
            self._stack.addWidget(step)

        root.addWidget(self._stack, 1)

        # ── Navigation ──
        nav = QHBoxLayout()
        self._btn_back = QPushButton("◀ Précédent")
        self._btn_back.clicked.connect(self._go_back)
        self._btn_back.setEnabled(False)

        self._btn_next = QPushButton("Suivant ▶")
        self._btn_next.clicked.connect(self._go_next)
        self._btn_next.setStyleSheet(
            "QPushButton { background: #2ECC71; color: white; "
            "font-weight: bold; padding: 8px 24px; border-radius: 4px; }"
            "QPushButton:hover { background: #27AE60; }"
        )

        self._btn_cancel = QPushButton("Annuler")
        self._btn_cancel.clicked.connect(self.reject)

        nav.addWidget(self._btn_cancel)
        nav.addStretch()
        nav.addWidget(self._btn_back)
        nav.addWidget(self._btn_next)
        root.addLayout(nav)

        self._current = 0
        self._update_nav()

    def _make_steps_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        self._step_labels: list[QLabel] = []
        steps = [
            "1.Métadonnées", "2.Images", "3.Dimensions", "4.Logos",
            "5.Tiers", "6.ROI", "7.Calibration", "8.Entraînement",
        ]
        for i, name in enumerate(steps):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 11px; color: #888; padding: 4px;")
            layout.addWidget(lbl)
            self._step_labels.append(lbl)
        return bar

    def _update_nav(self) -> None:
        self._stack.setCurrentIndex(self._current)
        self._header.setText(f"Étape {self._current + 1} / 8")

        # met à jour la barre d'étapes
        for i, lbl in enumerate(self._step_labels):
            if i == self._current:
                lbl.setStyleSheet(
                    "font-size: 11px; font-weight: bold; color: #2ECC71; "
                    "border-bottom: 2px solid #2ECC71; padding: 4px;"
                )
            elif i < self._current:
                lbl.setStyleSheet("font-size: 11px; color: #2ECC71; padding: 4px;")
            else:
                lbl.setStyleSheet("font-size: 11px; color: #555; padding: 4px;")

        self._btn_back.setEnabled(self._current > 0)

        if self._current == 7:
            self._btn_next.setText("✅ Créer le produit")
            self._btn_next.setStyleSheet(
                "QPushButton { background: #3498DB; color: white; "
                "font-weight: bold; padding: 8px 24px; border-radius: 4px; }"
            )
        else:
            self._btn_next.setText("Suivant ▶")
            self._btn_next.setStyleSheet(
                "QPushButton { background: #2ECC71; color: white; "
                "font-weight: bold; padding: 8px 24px; border-radius: 4px; }"
            )

    def _go_back(self) -> None:
        if self._current > 0:
            self._current -= 1
            self._update_nav()

    def _go_next(self) -> None:
        step = self._stack.currentWidget()

        if hasattr(step, "is_valid") and not step.is_valid():
            QMessageBox.warning(self, "Champ requis", "Veuillez remplir les champs obligatoires (*)")
            return

        # Passage étape 4 → 5 : pré-remplir TierWidget depuis logos
        if self._current == 3:
            logos = self._step4.data().get("logo_definitions", [])
            self._step5.populate_from_logos(logos)

        # Passage → étape 8 : afficher résumé
        if self._current == 6:
            self._step8.set_summary(self._collect_data())

        if self._current < 7:
            self._current += 1
            self._update_nav()
        else:
            self._create_product()

    def _collect_data(self) -> dict:
        data: dict = {}
        for step in (
            self._step1, self._step2, self._step3, self._step4,
            self._step5, self._step6, self._step7, self._step8,
        ):
            data.update(step.data())
        return data

    def _create_product(self) -> None:
        data = self._collect_data()
        product_id = data.get("product_id", "").strip()

        if not product_id:
            QMessageBox.critical(self, "Erreur", "ID produit manquant.")
            return

        # Création du dossier produit
        product_dir = Path("products") / product_id
        try:
            product_dir.mkdir(parents=True, exist_ok=True)
            (product_dir / "calibration").mkdir(exist_ok=True)
            (product_dir / "dataset").mkdir(exist_ok=True)
            (product_dir / "logos").mkdir(exist_ok=True)

            # Copier image de référence
            ref_ok = data.get("ref_image_ok", "")
            if ref_ok and Path(ref_ok).exists():
                import shutil
                dest = product_dir / "dataset" / "reference_ok.jpg"
                shutil.copy2(ref_ok, dest)
                data["ref_image_ok"] = str(dest)

            # Sauvegarder config.json
            config_path = product_dir / "config.json"
            config = {
                "product_id":          product_id,
                "product_name":        data.get("product_name", product_id),
                "product_version":     data.get("product_version", "1.0"),
                "product_barcode":     data.get("product_barcode", ""),
                "physical_dimensions": data.get("physical_dimensions", {"width_mm": 300.0, "height_mm": 200.0}),
                "logo_definitions":    data.get("logo_definitions", []),
                "auto_switch_enabled": bool(data.get("product_barcode", "")),
                "station_id":          "STATION-001",
                "product_rules":       data.get("product_rules", {"criteria": []}),
            }

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info("Produit '%s' créé : %s", product_id, config_path)

            # Activer via SystemController (GR-03)
            if self._controller is not None:
                try:
                    self._controller.activate_product(product_id)
                    logger.info("Produit '%s' activé", product_id)
                except Exception as e:
                    logger.warning("activate_product() échoué : %s", e)

            QMessageBox.information(
                self, "Produit créé",
                f"✅ Produit '{data.get('product_name')}' créé avec succès.\n"
                f"ID : {product_id}\n"
                f"Chemin : products/{product_id}/config.json"
            )

            self.product_created.emit(product_id)
            self.accept()

        except Exception as e:
            logger.error("Création produit échouée : %s", e)
            QMessageBox.critical(self, "Erreur", f"Création échouée :\n{e}")