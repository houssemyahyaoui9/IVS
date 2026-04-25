"""
ProductCanvas — éditeur tapis + logos + zones — §37.1 · §37.3.

Rendu :
  - Fond gris foncé + grille mm (lignes tous les 50mm, fortes tous les 100mm)
  - Règles horizontale + verticale graduées en mm
  - Tapis : rectangle marron à hachures
  - Logos : rectangle coloré + numéro + label
  - Preview du shape en cours de dessin

Règles métier :
  - Max 10 logos (refus silencieux au-delà)
  - Min 10×10 mm pour tout shape (refus silencieux)
  - Un Logo doit être inscrit dans le Tapis (refus silencieux)
  - GR-12 : édition désactivée si RUNNING (set_running_state(True))

GR-05 : opérations Qt dans le thread principal.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QCursor, QFont, QPainter, QPen,
)
from PyQt6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ts2i_ivs.core.models import BoundingBox, LogoDefinition

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Modèle
# ─────────────────────────────────────────────────────────────────────────────

class DrawMode(Enum):
    NONE  = "NONE"
    TAPIS = "TAPIS"
    LOGO  = "LOGO"
    ZONE  = "ZONE"


@dataclass
class CanvasShape:
    """Shape dessiné sur le canvas — coordonnées normalisées [0,1]."""
    shape_type         : str
    bbox_rel           : tuple[float, float, float, float]   # (x, y, w, h)
    color              : QColor
    label              : str            = ""
    logo_index         : Optional[int]  = None
    mandatory          : bool           = True
    tolerance_mm       : float          = 5.0
    color_tolerance_de : float          = 8.0
    color_hex          : str            = "#FFD200"

    @property
    def x(self) -> float: return self.bbox_rel[0]
    @property
    def y(self) -> float: return self.bbox_rel[1]
    @property
    def w(self) -> float: return self.bbox_rel[2]
    @property
    def h(self) -> float: return self.bbox_rel[3]


# ─────────────────────────────────────────────────────────────────────────────
#  Constantes visuelles
# ─────────────────────────────────────────────────────────────────────────────

_RULER_PX        : int = 24
_GRID_MINOR_MM   : float = 50.0
_GRID_MAJOR_MM   : float = 100.0
_TAPIS_COLOR     : QColor = QColor("#7A4B1F")
_TAPIS_HATCH_BG  : QColor = QColor("#5D3915")
_LOGO_PALETTE    : list[str] = [
    "#FFD200", "#4FC3F7", "#FF8A65", "#9CCC65", "#BA68C8",
    "#FFAB40", "#80DEEA", "#F06292", "#A1887F", "#90CAF9",
]
_MAX_LOGOS       : int = 10
_MIN_SIZE_MM     : float = 10.0


# ─────────────────────────────────────────────────────────────────────────────
#  ProductCanvas
# ─────────────────────────────────────────────────────────────────────────────

class ProductCanvas(QWidget):
    """
    Éditeur visuel : 1 tapis + N logos (≤ 10) + zones — §37.1.

    Signals :
      shapes_changed()              — toute modif (ajout / suppr / propriété)
      shape_selected(object)        — CanvasShape | None
    """

    shapes_changed = pyqtSignal()
    shape_selected = pyqtSignal(object)

    def __init__(
        self,
        width_mm  : float = 800.0,
        height_mm : float = 600.0,
        parent    = None,
    ) -> None:
        super().__init__(parent)
        self._width_mm   = float(width_mm)
        self._height_mm  = float(height_mm)
        self._editable   = True
        self._mode       : DrawMode = DrawMode.NONE
        self._shapes     : list[CanvasShape] = []
        self._tapis      : Optional[CanvasShape] = None
        self._draw_start : Optional[QPoint] = None
        self._draw_curr  : Optional[QPoint] = None
        self._selected   : Optional[CanvasShape] = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Colonne gauche : toolbar + canvas
        left_col = QVBoxLayout()
        left_col.setContentsMargins(8, 8, 8, 8)
        left_col.setSpacing(6)

        left_col.addWidget(self._build_toolbar())

        self._canvas_area = _CanvasArea(self)
        self._canvas_area.setSizePolicy(QSizePolicy.Policy.Expanding,
                                        QSizePolicy.Policy.Expanding)
        left_col.addWidget(self._canvas_area, 1)

        left_wrap = QWidget()
        left_wrap.setLayout(left_col)
        outer.addWidget(left_wrap, 3)

        # Colonne droite : panneau propriétés
        outer.addWidget(self._build_properties_panel(), 1)

        self.setStyleSheet("ProductCanvas { background:#0d0d0d; color:#eee; }")

    # ─────────────────────────────────────────────────────────────────────────
    #  API publique
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def width_mm(self) -> float:  return self._width_mm
    @property
    def height_mm(self) -> float: return self._height_mm
    @property
    def shapes(self) -> list[CanvasShape]: return list(self._shapes)
    @property
    def tapis(self) -> Optional[CanvasShape]: return self._tapis
    @property
    def selected_shape(self) -> Optional[CanvasShape]: return self._selected
    @property
    def logos(self) -> list[CanvasShape]:
        return [s for s in self._shapes if s.shape_type == "logo"]

    def set_running_state(self, running: bool) -> None:
        """GR-12 : désactive l'édition pendant RUNNING."""
        self._editable = not running
        self._toolbar.setEnabled(self._editable)
        self._props_frame.setEnabled(self._editable)
        self._canvas_area.update_cursor()
        self._canvas_area.update()

    def set_dimensions(self, width_mm: float, height_mm: float) -> None:
        self._width_mm  = float(width_mm)
        self._height_mm = float(height_mm)
        self._canvas_area.update()

    def set_mode(self, mode: DrawMode) -> None:
        if not self._editable:
            return
        self._mode = mode
        self._canvas_area.update_cursor()

    def clear_all(self) -> None:
        if not self._editable:
            return
        self._shapes.clear()
        self._tapis = None
        self._selected = None
        self.shapes_changed.emit()
        self.shape_selected.emit(None)
        self._refresh_props_panel()
        self._canvas_area.update()

    def to_logo_definitions(self) -> list[LogoDefinition]:
        """
        Convertit les logos canvas → LogoDefinition (mm via product dims).
        bbox_rel × dims = position en mm ; class_name = f"logo_{index}".
        """
        out: list[LogoDefinition] = []
        for shape in self.logos:
            x_mm = shape.x * self._width_mm
            y_mm = shape.y * self._height_mm
            w_mm = max(_MIN_SIZE_MM, shape.w * self._width_mm)
            h_mm = max(_MIN_SIZE_MM, shape.h * self._height_mm)
            idx  = shape.logo_index if shape.logo_index is not None else (len(out) + 1)
            out.append(LogoDefinition(
                logo_id      = f"logo_{idx}",
                name         = shape.label or f"Logo {idx}",
                expected_zone= BoundingBox(x=x_mm, y=y_mm, w=w_mm, h=h_mm),
                class_name   = f"logo_{idx}",
                tolerance_mm = float(shape.tolerance_mm),
            ))
        return out

    def to_canvas_metadata(self) -> list[dict]:
        """Métadonnées riches (pour persistance complète config.json)."""
        meta: list[dict] = []
        for shape in self._shapes:
            meta.append({
                "shape_type"        : shape.shape_type,
                "bbox_rel"          : list(shape.bbox_rel),
                "label"             : shape.label,
                "logo_index"        : shape.logo_index,
                "mandatory"         : shape.mandatory,
                "tolerance_mm"      : shape.tolerance_mm,
                "color_hex"         : shape.color_hex,
                "color_tolerance_de": shape.color_tolerance_de,
            })
        return meta

    # ─────────────────────────────────────────────────────────────────────────
    #  Toolbar
    # ─────────────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.Shape.NoFrame)
        bar.setStyleSheet("QFrame { background:#181818; border-bottom:1px solid #2a2a2a; }")
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bar.setMinimumHeight(40)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._btn_tapis = QPushButton("🟫 Tapis")
        self._btn_logo  = QPushButton("⭐ Logo")
        self._btn_zone  = QPushButton("🔲 Zone")
        self._btn_color = QPushButton("■ Couleur")
        self._btn_clear = QPushButton("🗑")
        self._btn_reset = QPushButton("🔄")

        for btn, mode in (
            (self._btn_tapis, DrawMode.TAPIS),
            (self._btn_logo,  DrawMode.LOGO),
            (self._btn_zone,  DrawMode.ZONE),
        ):
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, m=mode, b=btn: self._on_mode_btn(m, b))
            layout.addWidget(btn)

        self._btn_color.clicked.connect(self._on_color_picker)
        self._btn_clear.clicked.connect(self._delete_selected)
        self._btn_reset.clicked.connect(self.clear_all)
        layout.addWidget(self._btn_color)
        layout.addWidget(self._btn_clear)
        layout.addWidget(self._btn_reset)
        layout.addStretch(1)

        self._toolbar = bar
        return bar

    def _on_mode_btn(self, mode: DrawMode, btn: QPushButton) -> None:
        for b in (self._btn_tapis, self._btn_logo, self._btn_zone):
            b.setChecked(b is btn and mode != self._mode)
        self.set_mode(mode if btn.isChecked() else DrawMode.NONE)

    def _on_color_picker(self) -> None:
        if not self._selected:
            return
        from PyQt6.QtWidgets import QColorDialog
        col = QColorDialog.getColor(self._selected.color, self,
                                    "Couleur logo")
        if col.isValid():
            self._selected.color    = col
            self._selected.color_hex = col.name()
            self._refresh_props_panel()
            self.shapes_changed.emit()
            self._canvas_area.update()

    # ─────────────────────────────────────────────────────────────────────────
    #  Panneau propriétés (droite)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_properties_panel(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
        frame.setMinimumWidth(240)
        frame.setStyleSheet(
            "QFrame { background:#161616; border:1px solid #2a2a2a; }"
            " QLabel { color:#eee; }"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Propriétés logo sélectionné")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        self._lbl_no_sel = QLabel("(aucune sélection)")
        self._lbl_no_sel.setStyleSheet("color:#888; font-style:italic;")
        layout.addWidget(self._lbl_no_sel)

        self._props_form_widget = QWidget()
        form = QFormLayout(self._props_form_widget)
        form.setContentsMargins(0, 6, 0, 0)
        form.setSpacing(4)

        self._fld_label     = QLineEdit()
        self._fld_index     = QLineEdit()
        self._fld_index.setReadOnly(True)
        self._fld_tolerance = QDoubleSpinBox()
        self._fld_tolerance.setRange(0.0, 200.0)
        self._fld_tolerance.setSuffix(" mm")
        self._fld_tolerance.setDecimals(1)
        self._fld_color_de  = QDoubleSpinBox()
        self._fld_color_de.setRange(0.0, 100.0)
        self._fld_color_de.setSuffix(" ΔE")
        self._fld_color_de.setDecimals(1)
        self._fld_color_hex = QLineEdit()
        self._fld_color_hex.setReadOnly(True)
        self._fld_mandatory = QCheckBox("Critère obligatoire")

        form.addRow("Label",          self._fld_label)
        form.addRow("Index",          self._fld_index)
        form.addRow("Tolérance pos.", self._fld_tolerance)
        form.addRow("Tol. couleur",   self._fld_color_de)
        form.addRow("Couleur (hex)",  self._fld_color_hex)
        form.addRow("",               self._fld_mandatory)

        layout.addWidget(self._props_form_widget)
        layout.addStretch(1)

        # Connexions
        self._fld_label.textChanged.connect(self._on_prop_label_changed)
        self._fld_tolerance.valueChanged.connect(self._on_prop_tolerance_changed)
        self._fld_color_de.valueChanged.connect(self._on_prop_color_de_changed)
        self._fld_mandatory.stateChanged.connect(self._on_prop_mandatory_changed)

        self._props_frame = frame
        self._refresh_props_panel()
        return frame

    def _refresh_props_panel(self) -> None:
        s = self._selected
        if s is None or s.shape_type != "logo":
            self._lbl_no_sel.setVisible(True)
            self._props_form_widget.setVisible(False)
            return
        self._lbl_no_sel.setVisible(False)
        self._props_form_widget.setVisible(True)
        self._fld_label.blockSignals(True)
        self._fld_tolerance.blockSignals(True)
        self._fld_color_de.blockSignals(True)
        self._fld_mandatory.blockSignals(True)
        try:
            self._fld_label.setText(s.label)
            self._fld_index.setText(str(s.logo_index or "—"))
            self._fld_tolerance.setValue(float(s.tolerance_mm))
            self._fld_color_de.setValue(float(s.color_tolerance_de))
            self._fld_color_hex.setText(s.color_hex)
            self._fld_color_hex.setStyleSheet(
                f"QLineEdit {{ background:{s.color_hex}; color:#000; }}"
            )
            self._fld_mandatory.setChecked(s.mandatory)
        finally:
            self._fld_label.blockSignals(False)
            self._fld_tolerance.blockSignals(False)
            self._fld_color_de.blockSignals(False)
            self._fld_mandatory.blockSignals(False)

    def _on_prop_label_changed(self, txt: str) -> None:
        if self._selected:
            self._selected.label = txt
            self.shapes_changed.emit()
            self._canvas_area.update()

    def _on_prop_tolerance_changed(self, val: float) -> None:
        if self._selected:
            self._selected.tolerance_mm = float(val)
            self.shapes_changed.emit()

    def _on_prop_color_de_changed(self, val: float) -> None:
        if self._selected:
            self._selected.color_tolerance_de = float(val)
            self.shapes_changed.emit()

    def _on_prop_mandatory_changed(self, state: int) -> None:
        if self._selected:
            self._selected.mandatory = bool(state)
            self.shapes_changed.emit()

    # ─────────────────────────────────────────────────────────────────────────
    #  Logique dessin / sélection (déléguée par _CanvasArea)
    # ─────────────────────────────────────────────────────────────────────────

    def _start_draw(self, pos: QPoint) -> None:
        if not self._editable or self._mode == DrawMode.NONE:
            self._try_select(pos)
            return
        self._draw_start = pos
        self._draw_curr  = pos

    def _update_draw(self, pos: QPoint) -> None:
        if self._draw_start is not None:
            self._draw_curr = pos
            self._canvas_area.update()

    def _finish_draw(self, pos: QPoint) -> None:
        if not self._editable or self._draw_start is None:
            self._draw_start = None
            self._draw_curr  = None
            return
        rect = QRect(self._draw_start, pos).normalized()
        self._draw_start = None
        self._draw_curr  = None
        self._try_create_shape(rect)
        self._canvas_area.update()

    def _try_create_shape(self, widget_rect: QRect) -> None:
        canvas_rect = self._canvas_area.canvas_rect()
        if canvas_rect.width() <= 0 or canvas_rect.height() <= 0:
            return
        bbox_rel = self._widget_to_rel(widget_rect, canvas_rect)
        if bbox_rel is None:
            return
        x, y, w, h = bbox_rel
        # Min size 10×10 mm
        if w * self._width_mm < _MIN_SIZE_MM or h * self._height_mm < _MIN_SIZE_MM:
            logger.debug("Shape rejeté : trop petit (< %.0f mm)", _MIN_SIZE_MM)
            return

        if self._mode == DrawMode.TAPIS:
            self._tapis = CanvasShape(
                shape_type="tapis",
                bbox_rel=(x, y, w, h),
                color=_TAPIS_COLOR,
                label="Tapis",
                mandatory=True,
                tolerance_mm=0.0,
                color_hex=_TAPIS_COLOR.name(),
            )
            # Maintient un seul tapis : retire l'ancien tapis des shapes
            self._shapes = [s for s in self._shapes if s.shape_type != "tapis"]
            self._shapes.insert(0, self._tapis)
            self._select(self._tapis)
        elif self._mode == DrawMode.LOGO:
            if len(self.logos) >= _MAX_LOGOS:
                logger.debug("Logo rejeté : max %d atteint", _MAX_LOGOS)
                return
            if not self._inside_tapis(x, y, w, h):
                logger.debug("Logo rejeté : hors tapis")
                return
            idx     = len(self.logos) + 1
            color   = QColor(_LOGO_PALETTE[(idx - 1) % len(_LOGO_PALETTE)])
            shape = CanvasShape(
                shape_type="logo",
                bbox_rel=(x, y, w, h),
                color=color,
                label=f"Logo {idx}",
                logo_index=idx,
                mandatory=True,
                tolerance_mm=5.0,
                color_tolerance_de=8.0,
                color_hex=color.name(),
            )
            self._shapes.append(shape)
            self._select(shape)
        elif self._mode == DrawMode.ZONE:
            shape = CanvasShape(
                shape_type="zone",
                bbox_rel=(x, y, w, h),
                color=QColor("#80DEEA"),
                label=f"Zone {sum(1 for s in self._shapes if s.shape_type == 'zone') + 1}",
                mandatory=False,
                tolerance_mm=0.0,
                color_hex="#80DEEA",
            )
            self._shapes.append(shape)
            self._select(shape)
        else:
            return

        self.shapes_changed.emit()

    def _inside_tapis(self, x: float, y: float, w: float, h: float) -> bool:
        if self._tapis is None:
            return False
        tx, ty, tw, th = self._tapis.bbox_rel
        return (x >= tx and y >= ty
                and x + w <= tx + tw + 1e-6
                and y + h <= ty + th + 1e-6)

    def _try_select(self, pos: QPoint) -> None:
        canvas_rect = self._canvas_area.canvas_rect()
        hit: Optional[CanvasShape] = None
        for shape in reversed(self._shapes):
            r = self._rel_to_widget(shape.bbox_rel, canvas_rect)
            if r.contains(pos):
                hit = shape
                break
        self._select(hit)

    def _select(self, shape: Optional[CanvasShape]) -> None:
        self._selected = shape
        self.shape_selected.emit(shape)
        self._refresh_props_panel()
        self._canvas_area.update()

    def _delete_selected(self) -> None:
        if not self._editable or self._selected is None:
            return
        if self._selected is self._tapis:
            self._tapis = None
        if self._selected in self._shapes:
            self._shapes.remove(self._selected)
        self._selected = None
        self.shapes_changed.emit()
        self.shape_selected.emit(None)
        self._refresh_props_panel()
        self._canvas_area.update()

    # ─────────────────────────────────────────────────────────────────────────
    #  Coordonnées widget ↔ relatives [0,1] dans le canvas (hors règles)
    # ─────────────────────────────────────────────────────────────────────────

    def _widget_to_rel(
        self,
        rect       : QRect,
        canvas_rect: QRect,
    ) -> Optional[tuple[float, float, float, float]]:
        if canvas_rect.width() <= 0 or canvas_rect.height() <= 0:
            return None
        rx = max(0.0, (rect.x() - canvas_rect.x()) / canvas_rect.width())
        ry = max(0.0, (rect.y() - canvas_rect.y()) / canvas_rect.height())
        rw = min(1.0 - rx, rect.width()  / canvas_rect.width())
        rh = min(1.0 - ry, rect.height() / canvas_rect.height())
        if rw <= 0 or rh <= 0:
            return None
        return (rx, ry, rw, rh)

    def _rel_to_widget(
        self,
        bbox       : tuple[float, float, float, float],
        canvas_rect: QRect,
    ) -> QRect:
        x, y, w, h = bbox
        return QRect(
            int(canvas_rect.x() + x * canvas_rect.width()),
            int(canvas_rect.y() + y * canvas_rect.height()),
            max(1, int(w * canvas_rect.width())),
            max(1, int(h * canvas_rect.height())),
        )


# ─────────────────────────────────────────────────────────────────────────────
#  _CanvasArea : zone de rendu + capture souris
# ─────────────────────────────────────────────────────────────────────────────

class _CanvasArea(QWidget):
    """Sous-widget de rendu — délègue les actions au ProductCanvas parent."""

    def __init__(self, owner: ProductCanvas) -> None:
        super().__init__(owner)
        self._owner = owner
        self.setMinimumSize(560, 420)
        self.setMouseTracking(True)
        self.setStyleSheet("background:#0a0a0a;")
        self.update_cursor()

    def update_cursor(self) -> None:
        if not self._owner._editable:
            self.setCursor(QCursor(Qt.CursorShape.ForbiddenCursor))
        elif self._owner._mode == DrawMode.NONE:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def canvas_rect(self) -> QRect:
        """Rectangle du canvas (hors règles)."""
        ww = self.width()  - _RULER_PX
        wh = self.height() - _RULER_PX
        if ww <= 0 or wh <= 0:
            return QRect(_RULER_PX, _RULER_PX, 1, 1)
        # Ratio physique : on conserve le ratio width_mm/height_mm
        ratio_phys = self._owner._width_mm / max(1.0, self._owner._height_mm)
        ratio_box  = ww / max(1.0, wh)
        if ratio_box > ratio_phys:
            ch = wh
            cw = int(ch * ratio_phys)
        else:
            cw = ww
            ch = int(cw / ratio_phys)
        x = _RULER_PX + (ww - cw) // 2
        y = _RULER_PX + (wh - ch) // 2
        return QRect(x, y, cw, ch)

    # ── Events souris → délégation ───────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner._start_draw(event.position().toPoint())
            self.update()

    def mouseMoveEvent(self, event) -> None:
        self._owner._update_draw(event.position().toPoint())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._owner._finish_draw(event.position().toPoint())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self._owner._delete_selected()
        else:
            super().keyPressEvent(event)

    # ── paintEvent ───────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Fond
        painter.fillRect(self.rect(), QColor("#0a0a0a"))

        canvas_rect = self.canvas_rect()
        # Cadre canvas
        painter.setPen(QPen(QColor("#333"), 1))
        painter.drawRect(canvas_rect)

        # Grille mm
        self._draw_grid_mm(painter, canvas_rect)

        # Règles
        self._draw_rulers(painter, canvas_rect)

        # Shapes
        for shape in self._owner._shapes:
            self._draw_shape(painter, shape, canvas_rect)

        # Preview
        if (self._owner._draw_start is not None
                and self._owner._draw_curr is not None
                and self._owner._mode != DrawMode.NONE):
            self._draw_preview(painter,
                               self._owner._draw_start,
                               self._owner._draw_curr,
                               self._owner._mode)

        # Overlay RUNNING
        if not self._owner._editable:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
            painter.setPen(QColor(255, 200, 0))
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.drawText(self.rect(),
                             Qt.AlignmentFlag.AlignCenter,
                             "Édition BLOQUÉE\n(GR-12 — RUNNING)")

    # ── Helpers de rendu ─────────────────────────────────────────────────────

    def _draw_grid_mm(self, p: QPainter, canvas_rect: QRect) -> None:
        if canvas_rect.width() <= 0 or canvas_rect.height() <= 0:
            return
        px_per_mm_x = canvas_rect.width()  / self._owner._width_mm
        px_per_mm_y = canvas_rect.height() / self._owner._height_mm

        # Lignes mineures
        pen_min = QPen(QColor("#202020"), 1)
        pen_maj = QPen(QColor("#3a3a3a"), 1)
        for mm in _frange(0.0, self._owner._width_mm, _GRID_MINOR_MM):
            x = canvas_rect.x() + int(mm * px_per_mm_x)
            p.setPen(pen_maj if (round(mm) % int(_GRID_MAJOR_MM)) == 0 else pen_min)
            p.drawLine(x, canvas_rect.y(), x, canvas_rect.y() + canvas_rect.height())
        for mm in _frange(0.0, self._owner._height_mm, _GRID_MINOR_MM):
            y = canvas_rect.y() + int(mm * px_per_mm_y)
            p.setPen(pen_maj if (round(mm) % int(_GRID_MAJOR_MM)) == 0 else pen_min)
            p.drawLine(canvas_rect.x(), y, canvas_rect.x() + canvas_rect.width(), y)

    def _draw_rulers(self, p: QPainter, canvas_rect: QRect) -> None:
        # Bandes règles
        p.fillRect(QRect(0, 0, self.width(), _RULER_PX), QColor("#181818"))
        p.fillRect(QRect(0, 0, _RULER_PX, self.height()), QColor("#181818"))

        p.setPen(QColor("#aaa"))
        p.setFont(QFont("Monospace", 7))

        px_per_mm_x = canvas_rect.width()  / self._owner._width_mm
        px_per_mm_y = canvas_rect.height() / self._owner._height_mm

        # Graduation horizontale (mm)
        for mm in _frange(0.0, self._owner._width_mm + 1, _GRID_MAJOR_MM):
            x = canvas_rect.x() + int(mm * px_per_mm_x)
            p.drawLine(x, _RULER_PX - 6, x, _RULER_PX)
            p.drawText(x + 2, _RULER_PX - 8, f"{int(mm)}")

        # Graduation verticale (mm)
        for mm in _frange(0.0, self._owner._height_mm + 1, _GRID_MAJOR_MM):
            y = canvas_rect.y() + int(mm * px_per_mm_y)
            p.drawLine(_RULER_PX - 6, y, _RULER_PX, y)
            p.drawText(2, y - 2, f"{int(mm)}")

    def _draw_shape(self, p: QPainter, shape: CanvasShape, canvas_rect: QRect) -> None:
        rect = self._owner._rel_to_widget(shape.bbox_rel, canvas_rect)
        selected = (shape is self._owner._selected)

        if shape.shape_type == "tapis":
            # Hachures marron
            p.fillRect(rect, _TAPIS_HATCH_BG)
            brush = QBrush(_TAPIS_COLOR, Qt.BrushStyle.BDiagPattern)
            p.fillRect(rect, brush)
            pen = QPen(QColor("#A86A2C"), 3 if selected else 2)
            if selected:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(rect)
            p.setPen(QColor("#FFE0B2"))
            p.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            p.drawText(rect.x() + 6, rect.y() + 14, "TAPIS")
        elif shape.shape_type == "logo":
            fill = QColor(shape.color)
            fill.setAlpha(80)
            p.fillRect(rect, fill)
            pen = QPen(shape.color, 3 if selected else 2)
            if selected:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(rect)
            # Numéro + label
            p.setPen(shape.color)
            p.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            tag = f"#{shape.logo_index or '?'}  {shape.label}"
            p.drawText(rect.x() + 4, rect.y() - 4 if rect.y() > 16 else rect.y() + 14, tag)
        else:  # "zone"
            fill = QColor(shape.color)
            fill.setAlpha(50)
            p.fillRect(rect, fill)
            pen = QPen(shape.color, 2)
            pen.setStyle(Qt.PenStyle.DotLine if not selected else Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(rect)
            p.setPen(shape.color)
            p.setFont(QFont("Arial", 8))
            p.drawText(rect.x() + 4, rect.y() + 12, shape.label)

    def _draw_preview(self, p: QPainter, p1: QPoint, p2: QPoint, mode: DrawMode) -> None:
        rect = QRect(p1, p2).normalized()
        color = {
            DrawMode.TAPIS: QColor("#A86A2C"),
            DrawMode.LOGO:  QColor("#FFD200"),
            DrawMode.ZONE:  QColor("#80DEEA"),
        }.get(mode, QColor("#888"))
        fill = QColor(color); fill.setAlpha(60)
        p.fillRect(rect, fill)
        pen = QPen(color, 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(rect)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _frange(start: float, stop: float, step: float):
    v = start
    while v < stop:
        yield v
        v += step
