"""
RoiEditorWidget · RoiZone — Éditeur visuel zones d'inspection (S17-A · §12.2)

ROI Zone     → Tier assigné par utilisateur (couleur selon Tier)
OCR Zone     → toujours MINOR → vert
Caliper Line → toujours MAJOR → violet
Color Zone   → toujours MAJOR → orange

GR-03  UI via Controller         (rules user-defined, pas de logique pipeline ici)
GR-05  Qt main thread uniquement
GR-12  Édition FORBIDDEN pendant RUNNING (set_editable(False))
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ts2i_ivs.core.models import BoundingBox, CriterionRule
from ts2i_ivs.core.tier_result import TierLevel


# ─────────────────────────────────────────────────────────────────────────────
#  Couleurs de référence (§12.2)
# ─────────────────────────────────────────────────────────────────────────────

_TIER_COLORS: dict[TierLevel, str] = {
    TierLevel.CRITICAL: "#FF4444",
    TierLevel.MAJOR:    "#FF8800",
    TierLevel.MINOR:    "#FFCC00",
}

_ZONE_TYPE_COLORS: dict[str, str] = {
    "ocr":     "#44CC44",
    "caliper": "#9944FF",
}

_TIER_FORCED_BY_TYPE: dict[str, TierLevel] = {
    "ocr":     TierLevel.MINOR,
    "caliper": TierLevel.MAJOR,
    "color":   TierLevel.MAJOR,
}

_OBSERVER_ID_BY_TYPE: dict[str, str] = {
    "ocr":     "ocr_tesseract",
    "color":   "color_delta_e",
}

_OBSERVER_ID_BY_TIER: dict[TierLevel, str] = {
    TierLevel.CRITICAL: "yolo_sift",
    TierLevel.MAJOR:    "color_delta_e",
    TierLevel.MINOR:    "surface_isoforest",
}


def _observer_id_for(zone_type: str, tier: TierLevel, zone_id: str) -> str:
    """Mapping zone → observer_id pour CriterionRule."""
    if zone_type == "caliper":
        return f"caliper_{zone_id}"
    if zone_type in _OBSERVER_ID_BY_TYPE:
        return _OBSERVER_ID_BY_TYPE[zone_type]
    return _OBSERVER_ID_BY_TIER.get(tier, "yolo_sift")


# ─────────────────────────────────────────────────────────────────────────────
#  RoiZone — dataclass frozen
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RoiZone:
    """
    Zone d'inspection définie par l'utilisateur — §12.2.

    bbox_rel  : BoundingBox normalisée [0, 1] (x, y, w, h relatifs).
    zone_type : "roi" | "ocr" | "caliper" | "color"
    tier      : TierLevel — forcé selon zone_type pour ocr/caliper/color.
    """
    zone_id   : str
    zone_type : str
    bbox_rel  : BoundingBox
    tier      : TierLevel
    label     : str
    threshold : float
    mandatory : bool
    details   : dict = field(default_factory=dict, hash=False, compare=False)

    @staticmethod
    def make(
        zone_type : str,
        bbox_rel  : BoundingBox,
        tier      : TierLevel = TierLevel.MINOR,
        label     : str       = "",
        threshold : float     = 0.80,
        mandatory : bool      = False,
        details   : Optional[dict] = None,
    ) -> "RoiZone":
        """Factory : ID auto-généré, Tier forcé pour ocr/caliper/color."""
        effective_tier = _TIER_FORCED_BY_TYPE.get(zone_type, tier)
        zone_id        = f"{zone_type}_{uuid.uuid4().hex[:8]}"
        return RoiZone(
            zone_id   = zone_id,
            zone_type = zone_type,
            bbox_rel  = bbox_rel,
            tier      = effective_tier,
            label     = label or zone_id,
            threshold = threshold,
            mandatory = mandatory,
            details   = dict(details) if details else {},
        )

    def to_criterion_rules(self) -> list[CriterionRule]:
        """
        Convertit la zone en CriterionRule pour sauvegarde config.json — §12.2.
        Une zone produit une CriterionRule (déterministe : même zone → mêmes règles).
        """
        observer_id = _observer_id_for(self.zone_type, self.tier, self.zone_id)
        rule = CriterionRule(
            criterion_id = self.zone_id,
            label        = self.label,
            tier         = self.tier,
            observer_id  = observer_id,
            threshold    = self.threshold,
            enabled      = True,
            mandatory    = self.mandatory,
            details      = {
                "zone_type": self.zone_type,
                "bbox_rel": {
                    "x": self.bbox_rel.x,
                    "y": self.bbox_rel.y,
                    "w": self.bbox_rel.w,
                    "h": self.bbox_rel.h,
                },
                **self.details,
            },
        )
        return [rule]


# ─────────────────────────────────────────────────────────────────────────────
#  RoiEditorWidget
# ─────────────────────────────────────────────────────────────────────────────

class RoiEditorWidget(QWidget):
    """
    Canvas dessin zones d'inspection — §12.2.

    Signals :
        zone_selected(object)  — RoiZone sélectionnée (None si désélection)
        zone_created(object)   — nouvelle RoiZone ajoutée
        zones_changed()        — toute modification de la liste

    GR-12 : set_editable(False) bloque toute modification (RUNNING).
    """

    zone_selected = pyqtSignal(object)
    zone_created  = pyqtSignal(object)
    zones_changed = pyqtSignal()

    MAX_ZONES   : int = 20
    MIN_SIZE_PX : int = 10

    def __init__(
        self,
        parent:      Optional[QWidget] = None,
        canvas_size: tuple[int, int]   = (800, 600),
        max_zones:   int               = 20,
        min_size_px: int               = 10,
    ) -> None:
        super().__init__(parent)
        self._canvas_w, self._canvas_h = canvas_size
        self._max_zones   = max_zones
        self._min_size_px = min_size_px

        self._pixmap        : Optional[QPixmap] = None
        self._zones         : list[RoiZone]     = []
        self._selected_zone_id : Optional[str]  = None
        self._editable      : bool              = True
        self._draw_mode     : bool              = True
        self._current_type  : str               = "roi"
        self._current_tier  : TierLevel         = TierLevel.CRITICAL
        self._draw_start    : Optional[QPoint]  = None
        self._draw_current  : Optional[QPoint]  = None

        self.setMinimumSize(self._canvas_w, self._canvas_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._update_cursor()

    # ── API publique ─────────────────────────────────────────────────────────

    @property
    def zones(self) -> list[RoiZone]:
        return list(self._zones)

    @property
    def selected_zone(self) -> Optional[RoiZone]:
        if self._selected_zone_id is None:
            return None
        for z in self._zones:
            if z.zone_id == self._selected_zone_id:
                return z
        return None

    def set_editable(self, editable: bool) -> None:
        """GR-12 : False = lecture seule (inspection RUNNING)."""
        self._editable = bool(editable)
        self._update_cursor()
        self.update()

    def set_reference_image(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def set_draw_mode(self, draw: bool) -> None:
        self._draw_mode    = bool(draw)
        self._draw_start   = None
        self._draw_current = None
        self._update_cursor()
        self.update()

    def set_zone_type(self, zone_type: str) -> None:
        self._current_type = zone_type

    def set_default_tier(self, tier: TierLevel) -> None:
        self._current_tier = tier

    def add_zone(
        self,
        zone_type : str,
        bbox_rel  : BoundingBox,
        tier      : TierLevel = TierLevel.MINOR,
        label     : str       = "",
        threshold : float     = 0.80,
        mandatory : bool      = False,
        details   : Optional[dict] = None,
    ) -> RoiZone:
        """
        Ajoute une zone.

        Raises:
            RuntimeError si non éditable (GR-12).
            ValueError si dimensions < MIN_SIZE_PX.
            ValueError si len(zones) >= max_zones.
        """
        if not self._editable:
            raise RuntimeError(
                "Édition zones FORBIDDEN — set_editable(False) actif (GR-12)"
            )
        if len(self._zones) >= self._max_zones:
            raise ValueError(
                f"Max zones atteint : {self._max_zones} (§12.2 max_count)"
            )

        w_px = bbox_rel.w * self._canvas_w
        h_px = bbox_rel.h * self._canvas_h
        if w_px < self._min_size_px or h_px < self._min_size_px:
            raise ValueError(
                f"Zone trop petite : {w_px:.1f}×{h_px:.1f}px "
                f"(min {self._min_size_px}×{self._min_size_px}px §12.2)"
            )

        zone = RoiZone.make(
            zone_type = zone_type,
            bbox_rel  = bbox_rel,
            tier      = tier,
            label     = label,
            threshold = threshold,
            mandatory = mandatory,
            details   = details,
        )
        self._zones.append(zone)
        self._selected_zone_id = zone.zone_id
        self.zone_created.emit(zone)
        self.zone_selected.emit(zone)
        self.zones_changed.emit()
        self.update()
        return zone

    def remove_zone(self, zone_id: str) -> bool:
        """Supprime la zone par ID. Retourne True si supprimée."""
        if not self._editable:
            return False
        for i, z in enumerate(self._zones):
            if z.zone_id == zone_id:
                self._zones.pop(i)
                if self._selected_zone_id == zone_id:
                    self._selected_zone_id = None
                    self.zone_selected.emit(None)
                self.zones_changed.emit()
                self.update()
                return True
        return False

    def delete_selected(self) -> bool:
        """Supprime la zone sélectionnée (Delete key)."""
        if not self._editable or self._selected_zone_id is None:
            return False
        return self.remove_zone(self._selected_zone_id)

    def clear_all(self) -> None:
        if not self._editable:
            return
        self._zones.clear()
        self._selected_zone_id = None
        self.zone_selected.emit(None)
        self.zones_changed.emit()
        self.update()

    def set_zones(self, zones: list[RoiZone]) -> None:
        self._zones = list(zones)
        self._selected_zone_id = None
        self.zone_selected.emit(None)
        self.zones_changed.emit()
        self.update()

    def get_all_criterion_rules(self) -> list[CriterionRule]:
        """Agrège to_criterion_rules() de toutes les zones — sauvegarde config.json."""
        rules: list[CriterionRule] = []
        for z in self._zones:
            rules.extend(z.to_criterion_rules())
        return rules

    # ── Couleurs ─────────────────────────────────────────────────────────────

    def get_tier_color(self, tier: TierLevel) -> QColor:
        """Couleur overlay par Tier — §12.2."""
        return QColor(_TIER_COLORS.get(tier, "#888888"))

    def get_zone_type_color(self, zone_type: str) -> QColor:
        """Couleur overlay par type de zone — §12.2 (ocr=vert, caliper=violet)."""
        return QColor(_ZONE_TYPE_COLORS.get(zone_type, "#888888"))

    def _zone_color(self, zone: RoiZone) -> QColor:
        if zone.zone_type in _ZONE_TYPE_COLORS:
            return self.get_zone_type_color(zone.zone_type)
        return self.get_tier_color(zone.tier)

    # ── Événements souris ────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if not self._editable:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if self._draw_mode:
                self._draw_start   = pos
                self._draw_current = pos
            else:
                self._try_select(pos)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._draw_mode and self._draw_start is not None:
            self._draw_current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self._editable:
            return
        if event.button() == Qt.MouseButton.LeftButton and self._draw_mode:
            if self._draw_start is not None and self._draw_current is not None:
                self._finalize_draw(self._draw_start, event.position().toPoint())
            self._draw_start   = None
            self._draw_current = None
            self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selected()
            return
        super().keyPressEvent(event)

    # ── Rendu ────────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        img_rect = self._image_rect()

        if self._pixmap is not None:
            painter.drawPixmap(img_rect, self._pixmap)
        else:
            painter.fillRect(img_rect, QColor(60, 60, 60))
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(
                img_rect, Qt.AlignmentFlag.AlignCenter, "Aucune image de référence"
            )

        for zone in self._zones:
            self._draw_zone(painter, zone, img_rect)

        if self._draw_start is not None and self._draw_current is not None:
            self._draw_preview(painter, self._draw_start, self._draw_current)

        if not self._editable:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
            painter.setPen(QColor(255, 200, 0))
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Édition BLOQUÉE\n(inspection en cours — GR-12)",
            )

    def _draw_zone(self, painter: QPainter, zone: RoiZone, img_rect: QRect) -> None:
        rect     = self._rel_to_widget_rect(zone.bbox_rel, img_rect)
        color    = self._zone_color(zone)
        selected = (zone.zone_id == self._selected_zone_id)

        fill = QColor(color)
        fill.setAlpha(60)
        painter.fillRect(rect, fill)

        pen_color = QColor(color)
        pen_color.setAlpha(220 if selected else 200)
        pen = QPen(pen_color, 3 if selected else 2)
        if selected:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect)

        painter.setPen(color)
        painter.setFont(QFont("Arial", 8))
        label_rect = QRect(rect.x(), rect.y() - 16, max(rect.width(), 60), 16)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft, zone.label)

    def _draw_preview(self, painter: QPainter, p1: QPoint, p2: QPoint) -> None:
        rect = QRect(p1, p2).normalized()
        if self._current_type in _ZONE_TYPE_COLORS:
            color = self.get_zone_type_color(self._current_type)
        else:
            color = self.get_tier_color(self._current_tier)
        fill = QColor(color)
        fill.setAlpha(80)
        painter.fillRect(rect, fill)
        painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
        painter.drawRect(rect)

    # ── Helpers coordonnées ──────────────────────────────────────────────────

    def _image_rect(self) -> QRect:
        """Rectangle d'affichage de l'image (letterbox dans le widget)."""
        if self._pixmap is None:
            return self.rect()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        if pw == 0 or ph == 0:
            return self.rect()
        scale  = min(ww / pw, wh / ph)
        iw, ih = int(pw * scale), int(ph * scale)
        x      = (ww - iw) // 2
        y      = (wh - ih) // 2
        return QRect(x, y, iw, ih)

    def _widget_to_rel(self, pos: QPoint, img_rect: QRect) -> tuple[float, float]:
        if img_rect.width() <= 0 or img_rect.height() <= 0:
            return 0.0, 0.0
        x = (pos.x() - img_rect.x()) / img_rect.width()
        y = (pos.y() - img_rect.y()) / img_rect.height()
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))

    def _rel_to_widget_rect(self, bbox: BoundingBox, img_rect: QRect) -> QRect:
        x = int(img_rect.x() + bbox.x * img_rect.width())
        y = int(img_rect.y() + bbox.y * img_rect.height())
        w = max(1, int(bbox.w * img_rect.width()))
        h = max(1, int(bbox.h * img_rect.height()))
        return QRect(x, y, w, h)

    # ── Logique dessin / sélection ───────────────────────────────────────────

    def _finalize_draw(self, p1: QPoint, p2: QPoint) -> None:
        img_rect = self._image_rect()
        rect     = QRect(p1, p2).normalized()
        if rect.width() < self._min_size_px or rect.height() < self._min_size_px:
            return

        rx1, ry1 = self._widget_to_rel(rect.topLeft(),     img_rect)
        rx2, ry2 = self._widget_to_rel(rect.bottomRight(), img_rect)
        rw, rh   = rx2 - rx1, ry2 - ry1
        if rw <= 0 or rh <= 0:
            return

        try:
            bbox = BoundingBox(x=rx1, y=ry1, w=rw, h=rh)
            self.add_zone(
                zone_type = self._current_type,
                bbox_rel  = bbox,
                tier      = self._current_tier,
            )
        except (ValueError, RuntimeError):
            return

    def _try_select(self, pos: QPoint) -> None:
        img_rect = self._image_rect()
        hit: Optional[RoiZone] = None
        for zone in self._zones:
            r = self._rel_to_widget_rect(zone.bbox_rel, img_rect)
            if r.contains(pos):
                hit = zone
        if hit is not None:
            self._selected_zone_id = hit.zone_id
            self.zone_selected.emit(hit)
        else:
            self._selected_zone_id = None
            self.zone_selected.emit(None)

    def _update_cursor(self) -> None:
        if not self._editable:
            self.setCursor(QCursor(Qt.CursorShape.ForbiddenCursor))
        elif self._draw_mode:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
