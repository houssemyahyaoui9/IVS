"""
ProductCreationScreen — Wizard 8 étapes v7.0 — §12.

Étapes :
  1. Métadonnées        (nom, ID, version, barcode)
  2. Images référence   (GOOD ≥ 1, BAD optionnel)
  3. Dimensions         (width_mm, height_mm)
  4. Canvas Logos       (ProductCanvas §37)
  5. TierPriorityWidget (§12 — clef v7.0)
  6. Zones ROI          (RoiEditorWidget §17)
  7. Calibration        (CalibrationEngine §10)
  8. Entraînement       (TierBackgroundTrainer §16)

GR-03 : aucune action pipeline ici — la création remonte la ProductDefinition
        + ProductRules au caller (SystemController) via le signal product_ready.
GR-12 : non concerné (la création ne s'effectue pas en RUNNING).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWizard, QWizardPage,
)

from ts2i_ivs.core.models import (
    BoundingBox, LogoDefinition, ProductDefinition, ProductRules,
)
from ts2i_ivs.ui.tier_priority_widget import TierPriorityWidget

# RoiEditorWidget peut être absent — fallback en placeholder
try:
    from ts2i_ivs.ui.components.roi_editor_widget import RoiEditorWidget
    _ROI_EDITOR_AVAILABLE = True
except Exception:
    RoiEditorWidget = None       # type: ignore[assignment,misc]
    _ROI_EDITOR_AVAILABLE = False

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
#  Pages du wizard
# ═════════════════════════════════════════════════════════════════════════════

class _MetadataPage(QWizardPage):
    """Étape 1 — Métadonnées : nom, product_id, version, barcode."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("1 / 8 — Métadonnées produit")
        self.setSubTitle("Identification du produit dans le registre.")

        self._name    = QLineEdit()
        self._pid     = QLineEdit()
        self._version = QLineEdit("1.0")
        self._barcode = QLineEdit()
        self._barcode.setPlaceholderText("(optionnel — code-barres associé)")

        layout = QFormLayout(self)
        layout.addRow("Nom *",       self._name)
        layout.addRow("Product ID *", self._pid)
        layout.addRow("Version *",   self._version)
        layout.addRow("Barcode",     self._barcode)

        self.registerField("name*",    self._name)
        self.registerField("pid*",     self._pid)
        self.registerField("version*", self._version)
        self.registerField("barcode",  self._barcode)


class _ImagesPage(QWizardPage):
    """Étape 2 — Images référence GOOD (≥ 1) + BAD (optionnel)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("2 / 8 — Images de référence")
        self.setSubTitle("Au moins 1 image GOOD requise. Images BAD optionnelles.")

        self._good_paths: list[str] = []
        self._bad_paths : list[str] = []

        self._good_list = QListWidget()
        self._bad_list  = QListWidget()

        btn_add_good = QPushButton("+ Ajouter GOOD")
        btn_add_bad  = QPushButton("+ Ajouter BAD")
        btn_add_good.clicked.connect(self._add_good)
        btn_add_bad.clicked.connect(self._add_bad)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Images GOOD :"))
        layout.addWidget(self._good_list)
        layout.addWidget(btn_add_good)
        layout.addSpacing(10)
        layout.addWidget(QLabel("Images BAD (optionnelles) :"))
        layout.addWidget(self._bad_list)
        layout.addWidget(btn_add_bad)

    def _add_good(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Sélection images GOOD", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        for f in files:
            if f not in self._good_paths:
                self._good_paths.append(f)
                self._good_list.addItem(f)
        self.completeChanged.emit()

    def _add_bad(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Sélection images BAD", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        for f in files:
            if f not in self._bad_paths:
                self._bad_paths.append(f)
                self._bad_list.addItem(f)

    def isComplete(self) -> bool:  # type: ignore[override]
        return len(self._good_paths) >= 1

    @property
    def good_paths(self) -> list[str]:
        return list(self._good_paths)

    @property
    def bad_paths(self) -> list[str]:
        return list(self._bad_paths)


class _DimensionsPage(QWizardPage):
    """Étape 3 — Dimensions (width_mm, height_mm)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("3 / 8 — Dimensions")
        self.setSubTitle("Dimensions physiques du produit en millimètres.")

        self._w = QDoubleSpinBox()
        self._w.setRange(1.0, 5000.0)
        self._w.setDecimals(2)
        self._w.setSuffix(" mm")
        self._w.setValue(800.0)

        self._h = QDoubleSpinBox()
        self._h.setRange(1.0, 5000.0)
        self._h.setDecimals(2)
        self._h.setSuffix(" mm")
        self._h.setValue(600.0)

        layout = QFormLayout(self)
        layout.addRow("Largeur (width_mm) *",  self._w)
        layout.addRow("Hauteur (height_mm) *", self._h)

    @property
    def width_mm(self) -> float:
        return float(self._w.value())

    @property
    def height_mm(self) -> float:
        return float(self._h.value())


class _CanvasLogosPage(QWizardPage):
    """Étape 4 — ProductCanvas §37 (placeholder · vraies logos via fichier)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("4 / 8 — Canvas Logos")
        self.setSubTitle("Définir les logos à inspecter (sera remplacé par ProductCanvas §37).")

        self._logos: list[LogoDefinition] = []
        self._list  = QListWidget()
        btn_add     = QPushButton("+ Ajouter logo (placeholder)")
        btn_clear   = QPushButton("Effacer")

        btn_add.clicked.connect(self._add_dummy_logo)
        btn_clear.clicked.connect(self._clear)

        actions = QHBoxLayout()
        actions.addWidget(btn_add)
        actions.addWidget(btn_clear)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(actions)

    def _add_dummy_logo(self) -> None:
        idx   = len(self._logos) + 1
        logo  = LogoDefinition(
            logo_id      = f"logo_{idx}",
            name         = f"Logo {idx}",
            expected_zone= BoundingBox(x=10.0 * idx, y=10.0 * idx, w=80.0, h=40.0),
            class_name   = f"logo_{idx}",
            tolerance_mm = 5.0,
        )
        self._logos.append(logo)
        self._list.addItem(f"{logo.logo_id} · {logo.name} · zone={logo.expected_zone}")

    def _clear(self) -> None:
        self._logos.clear()
        self._list.clear()

    @property
    def logos(self) -> list[LogoDefinition]:
        return list(self._logos)


class _TierPriorityPage(QWizardPage):
    """Étape 5 — TierPriorityWidget — §12."""

    def __init__(self, get_product_def, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("5 / 8 — Priorité des Tiers")
        self.setSubTitle("Définir la criticité de chaque critère (CRITICAL / MAJOR / MINOR).")
        self._get_product_def = get_product_def
        self._widget : Optional[TierPriorityWidget] = None
        self._layout = QVBoxLayout(self)

    def initializePage(self) -> None:  # type: ignore[override]
        # Reconstruit le widget à partir de la dernière définition produit
        if self._widget is not None:
            self._layout.removeWidget(self._widget)
            self._widget.deleteLater()
        product_def  = self._get_product_def()
        self._widget = TierPriorityWidget(product_def=product_def)
        self._layout.addWidget(self._widget)

    @property
    def widget(self) -> Optional[TierPriorityWidget]:
        return self._widget

    def to_product_rules(self) -> Optional[ProductRules]:
        return self._widget.to_product_rules() if self._widget is not None else None


class _RoiEditorPage(QWizardPage):
    """Étape 6 — Zones ROI (§17)."""

    def __init__(self, get_reference_pixmap, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("6 / 8 — Zones ROI")
        self.setSubTitle("Dessiner les zones ROI / OCR / Caliper / Color sur l'image de référence.")
        self._get_reference_pixmap = get_reference_pixmap

        layout = QVBoxLayout(self)
        if _ROI_EDITOR_AVAILABLE:
            self._editor = RoiEditorWidget()
            layout.addWidget(self._editor)
        else:
            self._editor = None
            note = QLabel(
                "RoiEditorWidget indisponible (S17-A non chargé). "
                "Étape skippée."
            )
            note.setStyleSheet("color:#FFC107;")
            layout.addWidget(note)

    def initializePage(self) -> None:  # type: ignore[override]
        if self._editor is not None:
            pix = self._get_reference_pixmap()
            if pix is not None and not pix.isNull():
                self._editor.set_reference_image(pix)
            self._editor.set_editable(True)


class _CalibrationPage(QWizardPage):
    """Étape 7 — Calibration (CalibrationEngine §10) — barre de progression."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("7 / 8 — Calibration (7 étapes §10)")
        self.setSubTitle("Calibration via CalibrationEngine — exécutée par le SystemController.")

        layout = QVBoxLayout(self)
        self._progress = QProgressBar()
        self._progress.setRange(0, 7)
        self._progress.setValue(0)
        self._log = QTextEdit()
        self._log.setReadOnly(True)

        btn_run = QPushButton("Lancer la calibration (placeholder)")
        btn_run.clicked.connect(self._simulate)

        layout.addWidget(QLabel("État de la calibration :"))
        layout.addWidget(self._progress)
        layout.addWidget(self._log, 1)
        layout.addWidget(btn_run)

    def _simulate(self) -> None:
        for i in range(1, 8):
            self._progress.setValue(i)
            self._log.append(f"Étape {i}/7 — placeholder OK")
        self._log.append("✅ Calibration terminée (placeholder).")


class _TrainingPage(QWizardPage):
    """Étape 8 — TierBackgroundTrainer §16 — placeholder."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("8 / 8 — Entraînement")
        self.setSubTitle("Démarrage du TierBackgroundTrainer (§16) après création.")

        layout = QVBoxLayout(self)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setText(
            "ℹ Le produit sera persisté.\n"
            "Le TierBackgroundTrainer démarre automatiquement après "
            "création — son état est visible dans l'AI Monitoring."
        )
        layout.addWidget(self._log)


# ═════════════════════════════════════════════════════════════════════════════
#  ProductCreationScreen (QWizard)
# ═════════════════════════════════════════════════════════════════════════════

class ProductCreationScreen(QWizard):
    """
    Wizard 8 étapes — émet `product_ready(ProductDefinition, ProductRules)`
    lorsque l'utilisateur clique « Terminer ».

    Sauvegarde JSON dans `products/{product_id}/config.json`.
    """

    product_ready = pyqtSignal(object, object)   # (ProductDefinition, ProductRules)

    def __init__(
        self,
        products_dir : str = "products",
        parent       = None,
    ) -> None:
        super().__init__(parent)
        self._products_dir = products_dir
        self.setWindowTitle("TS2I IVS v7.0 — Création produit")
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setMinimumSize(1100, 720)

        # Pages
        self._p1_meta   = _MetadataPage()
        self._p2_images = _ImagesPage()
        self._p3_dims   = _DimensionsPage()
        self._p4_canvas = _CanvasLogosPage()
        self._p5_tiers  = _TierPriorityPage(self._build_temp_product_def)
        self._p6_roi    = _RoiEditorPage(self._first_good_pixmap)
        self._p7_calib  = _CalibrationPage()
        self._p8_train  = _TrainingPage()

        for page in (
            self._p1_meta, self._p2_images, self._p3_dims, self._p4_canvas,
            self._p5_tiers, self._p6_roi, self._p7_calib, self._p8_train,
        ):
            self.addPage(page)

        self.finished.connect(self._on_finished)

    # ── API publique ─────────────────────────────────────────────────────────

    @property
    def tier_priority_widget(self) -> Optional[TierPriorityWidget]:
        return self._p5_tiers.widget

    # ── Construction ProductDefinition / ProductRules ────────────────────────

    def _build_temp_product_def(self) -> ProductDefinition:
        """ProductDefinition partielle pour alimenter le TierPriorityWidget."""
        pid = (self.field("pid") or "TEMP_PRODUCT").strip()
        return ProductDefinition(
            product_id       = pid,
            name             = (self.field("name")    or "Produit").strip(),
            version          = (self.field("version") or "1.0").strip(),
            width_mm         = self._p3_dims.width_mm,
            height_mm        = self._p3_dims.height_mm,
            logo_definitions = tuple(self._p4_canvas.logos),
            product_barcode  = (self.field("barcode") or None) or None,
        )

    def _first_good_pixmap(self) -> Optional[QPixmap]:
        if not self._p2_images.good_paths:
            return None
        path = self._p2_images.good_paths[0]
        pix  = QPixmap(path)
        return pix if not pix.isNull() else None

    def _on_finished(self, code: int) -> None:
        if code != QWizard.DialogCode.Accepted:
            return
        try:
            product_def = self._build_temp_product_def()
            rules       = self._p5_tiers.to_product_rules()
        except Exception as e:
            logger.exception("Construction ProductDefinition/Rules échouée : %s", e)
            return

        if rules is None:
            logger.warning("Aucune règle produit : abandon de la persistance.")
            return

        self._persist(product_def, rules)
        self.product_ready.emit(product_def, rules)

    # ── Persistance ──────────────────────────────────────────────────────────

    def _persist(self, product_def: ProductDefinition, rules: ProductRules) -> None:
        dir_path = os.path.join(self._products_dir, product_def.product_id)
        os.makedirs(dir_path, exist_ok=True)
        config = {
            "product_id"      : product_def.product_id,
            "name"            : product_def.name,
            "version"         : product_def.version,
            "width_mm"        : product_def.width_mm,
            "height_mm"       : product_def.height_mm,
            "product_barcode" : product_def.product_barcode,
            "station_id"      : product_def.station_id,
            "logo_definitions": [_logo_to_dict(l) for l in product_def.logo_definitions],
            "criteria"        : [_rule_to_dict(c) for c in rules.criteria],
        }
        path = os.path.join(dir_path, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info("Produit persisté : %s", path)


# ═════════════════════════════════════════════════════════════════════════════
#  Sérialisation
# ═════════════════════════════════════════════════════════════════════════════

def _logo_to_dict(l: LogoDefinition) -> dict:
    z = l.expected_zone
    return {
        "logo_id"     : l.logo_id,
        "name"        : l.name,
        "class_name"  : l.class_name,
        "tolerance_mm": l.tolerance_mm,
        "expected_zone": {"x": z.x, "y": z.y, "w": z.w, "h": z.h},
    }


def _rule_to_dict(c: Any) -> dict:
    return {
        "criterion_id": c.criterion_id,
        "label"       : c.label,
        "tier"        : c.tier.value if hasattr(c.tier, "value") else c.tier,
        "observer_id" : c.observer_id,
        "threshold"   : c.threshold,
        "enabled"     : c.enabled,
        "mandatory"   : c.mandatory,
        "details"     : c.details,
    }
