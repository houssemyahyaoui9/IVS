"""
RoiEditorWidget — Canvas dessin zones ROI — §12.2
Color-coded par Tier/Type. Sauvegarde → CriterionRule list.
GR-05 : opérations Qt dans thread principal uniquement.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from core.models import BoundingBox, CriterionRule
from core.tier_result import TierLevel


# ─────────────────────────────────────────────────────────────────────────────
#  RoiZone
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RoiZone:
    """
    Zone d'inspection définie par l'utilisateur — §12.2.
    bbox_rel : BoundingBox normalisée [0,1] (x,y,w,h relatifs à l'image).
    zone_type : "roi" | "ocr" | "caliper" | "color"
    """
    zone_id   : str
    zone_type : str         # "roi" | "ocr" | "caliper" | "color"
    bbox_rel  : BoundingBox
    tier      : TierLevel
    label     : str
    threshold : float
    mandatory : bool
    details   : dict = field(default_factory=dict)

    def to_criterion_rules(self) -> list["CriterionRule"]:
        """
        Convertit cette zone en liste CriterionRule.
        Appelé depuis les tests et depuis RoiEditorWidget.
        """
        from core.models import CriterionRule
        observer_map = {
            "ocr"    : "ocr_tesseract",
            "caliper": "caliper_measure",
            "color"  : "color_de2000",
            "roi"    : "surface_mini_ensemble",
        }
        observer_id = observer_map.get(self.zone_type,
                                       "surface_mini_ensemble")
        return [CriterionRule(
            criterion_id = self.zone_id,
            label        = self.label,
            tier         = self.tier,
            observer_id  = observer_id,
            threshold    = self.threshold,
            enabled      = True,
            mandatory    = self.mandatory,
            details      = {
                "bbox_rel": {
                    "x": self.bbox_rel.x,
                    "y": self.bbox_rel.y,
                    "w": self.bbox_rel.w,
                    "h": self.bbox_rel.h,
                },
                **self.details,
            },
        )]

    @staticmethod
    def make(
        zone_type : str,
        bbox_rel  : BoundingBox,
        tier      : TierLevel  = TierLevel.MINOR,
        label     : str        = "",
        threshold : float      = 0.80,
        mandatory : bool       = False,
        details   : dict | None = None,
    ) -> "RoiZone":
        """Factory avec ID auto-généré."""
        # Tier fixé selon le type
        from core.tier_result import TierLevel as _TL
        fixed = {
            "ocr":     _TL.MINOR,
            "caliper": _TL.MAJOR,
            "color":   _TL.MAJOR,
        }
        effective_tier = fixed.get(zone_type, tier if tier is not None else _TL.MINOR)
        zone_id        = f"{zone_type}_{uuid.uuid4().hex[:8]}"
        return RoiZone(
            zone_id   = zone_id,
            zone_type = zone_type,
            bbox_rel  = bbox_rel,
            tier      = effective_tier,
            label     = label or zone_id,
            threshold = threshold,
            mandatory = mandatory,
            details   = details or {},
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Constantes de couleur
# ─────────────────────────────────────────────────────────────────────────────

_FILL_ALPHA  = 60
_BORDER_ALPHA = 200
_SEL_ALPHA   = 180

def _zone_fill_color(zone: RoiZone) -> QColor:
    hex_map = {
        "ocr":     (0x44, 0xCC, 0x44),
        "caliper": (0x99, 0x44, 0xFF),
    }
    tier_map = {
        TierLevel.CRITICAL: (0xFF, 0x44, 0x44),
        TierLevel.MAJOR:    (0xFF, 0x88, 0x00),
        TierLevel.MINOR:    (0xFF, 0xCC, 0x00),
    }
    r, g, b = hex_map.get(zone.zone_type, tier_map.get(zone.tier, (0x88, 0x88, 0x88)))
    return QColor(r, g, b, _FILL_ALPHA)


def _zone_border_color(zone: RoiZone, selected: bool = False) -> QColor:
    hex_map = {
        "ocr":     (0x44, 0xCC, 0x44),
        "caliper": (0x99, 0x44, 0xFF),
    }
    tier_map = {
        TierLevel.CRITICAL: (0xFF, 0x44, 0x44),
        TierLevel.MAJOR:    (0xFF, 0x88, 0x00),
        TierLevel.MINOR:    (0xFF, 0xCC, 0x00),
    }
    r, g, b = hex_map.get(zone.zone_type, tier_map.get(zone.tier, (0x88, 0x88, 0x88)))
    alpha   = _SEL_ALPHA if selected else _BORDER_ALPHA
    return QColor(r, g, b, alpha)


# ─────────────────────────────────────────────────────────────────────────────
#  RoiEditorWidget
# ─────────────────────────────────────────────────────────────────────────────

class RoiEditorWidget(QWidget):
    """
    Canvas interactif pour dessiner / sélectionner les zones ROI — §12.2.

    Signals :
        zone_selected(object)  — RoiZone | None (None si désélection)
        zone_created(object)   — RoiZone (nouvelle zone créée)
        zones_changed()        — toute modification de la liste de zones
    """

    zone_selected = pyqtSignal(object)
    zone_created  = pyqtSignal(object)
    zones_changed = pyqtSignal()

    _MAX_ZONES   = 20
    _MIN_SIZE_PX = 10

    def __init__(
        self,
        parent:      QWidget | None = None,
        max_zones:   int = 20,
        min_size_px: int = 10,
        canvas_size: tuple[int,int] | None = None,
    ) -> None:
        super().__init__(parent)
        self._canvas_w = canvas_size[0] if canvas_size else None
        self._canvas_h = canvas_size[1] if canvas_size else None
        self._pixmap:        Optional[QPixmap] = None
        self._zones:         list[RoiZone]     = []
        self._selected_zone_id: str | None = None
        self._selected_idx:  Optional[int]     = None
        self._draw_mode:     bool              = True   # True=draw · False=select
        self._current_type:  str               = "roi"
        self._current_tier:  TierLevel         = TierLevel.CRITICAL
        self._draw_start:    Optional[QPoint]  = None
        self._draw_current:  Optional[QPoint]  = None
        self._editable:      bool              = True
        self._max_zones      = max_zones
        self._min_size_px    = min_size_px

        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._update_cursor()

    # ── API publique ──────────────────────────────────────────────────────────

    def set_reference_image(self, pixmap: QPixmap) -> None:
        """Définit l'image de référence du produit affichée sous les zones."""
        self._pixmap = pixmap
        self.update()

    def set_editable(self, editable: bool) -> None:
        """GR-12 : False = lecture seule (RUNNING)."""
        self._editable = editable
        self._update_cursor()
        self.update()

    def set_draw_mode(self, draw: bool) -> None:
        """True = mode dessin (crosshair) · False = sélection (open hand)."""
        self._draw_mode   = draw
        self._draw_start  = None
        self._draw_current = None
        self._update_cursor()
        self.update()

    def set_zone_type(self, zone_type: str) -> None:
        """Type à créer lors du prochain dessin : "roi"|"ocr"|"caliper"|"color"."""
        self._current_type = zone_type

    def set_default_tier(self, tier: TierLevel) -> None:
        """Tier par défaut pour les zones de type "roi"."""
        self._current_tier = tier

    def add_zone(self, zone: RoiZone) -> bool:
        """
        Ajoute une zone manuellement. Retourne False si max atteint.
        """
        if len(self._zones) >= self._max_zones:
            return False
        self._zones.append(zone)
        self._select(len(self._zones) - 1)
        self.zones_changed.emit()
        self.update()
        return True

    def update_selected_zone(self, zone: RoiZone) -> None:
        """Remplace la zone sélectionnée (depuis le panneau propriétés)."""
        if self._selected_idx is None:
            return
        self._zones[self._selected_idx] = zone
        self.zones_changed.emit()
        self.update()

    def delete_selected(self) -> None:
        """Supprime la zone sélectionnée (_selected_idx ou _selected_zone_id)."""
        if not self._editable:
            return
        # Support _selected_zone_id (API tests)
        if self._selected_zone_id is not None:
            self._zones = [z for z in self._zones
                           if z.zone_id != self._selected_zone_id]
            self._selected_zone_id = None
            self._selected_idx = None
            self.zones_changed.emit()
            self.update()
            return
        # Support _selected_idx (API interne)
        if self._selected_idx is None:
            return
        self._zones.pop(self._selected_idx)
        self._selected_idx = None
        self.zone_selected.emit(None)
        self.zones_changed.emit()
        self.update()

    def clear_all(self) -> None:
        """Supprime toutes les zones."""
        self._zones.clear()
        self._selected_idx = None
        self.zone_selected.emit(None)
        self.zones_changed.emit()
        self.update()

    def set_zones(self, zones: list[RoiZone]) -> None:
        """Charge une liste de zones (ex: depuis config.json)."""
        self._zones        = list(zones)
        self._selected_idx = None
        self.zone_selected.emit(None)
        self.update()

    @property
    def zones(self) -> list[RoiZone]:
        return list(self._zones)

    @property
    def selected_zone(self) -> Optional[RoiZone]:
        if self._selected_idx is None:
            return None
        return self._zones[self._selected_idx]

    def to_criterion_rules(self) -> list[CriterionRule]:
        """
        Convertit les zones en CriterionRule pour sauvegarde config.json — §12.2.
        """
        rules = []
        for zone in self._zones:
            rules.append(CriterionRule(
                criterion_id = zone.zone_id,
                label        = zone.label,
                tier         = zone.tier,
                observer_id  = _observer_id_for(zone),
                threshold    = zone.threshold,
                enabled      = True,
                mandatory    = zone.mandatory,
                details      = {
                    "bbox_rel": {
                        "x": zone.bbox_rel.x,
                        "y": zone.bbox_rel.y,
                        "w": zone.bbox_rel.w,
                        "h": zone.bbox_rel.h,
                    },
                    **zone.details,
                },
            ))
        return rules

    # ── API publique ─────────────────────────────────────────────────────────
    def add_zone(self,
                 zone_type: str,
                 bbox_rel: "BoundingBox",
                 tier: "TierLevel" = None,
                 label: str = "",
                 threshold: float = 0.80,
                 mandatory: bool = False) -> RoiZone:
        """
        Ajoute une zone programmatiquement.
        Lève ValueError si max_zones atteint.
        Lève ValueError si bbox trop petite (< min_size_px).
        Bloqué si not self._editable (GR-12).
        """
        if not self._editable:
            raise PermissionError("Widget non éditable (GR-12 — RUNNING)")
        if len(self._zones) >= self._max_zones:
            raise ValueError(
                f"Max zones atteint : {self._max_zones}")
        # Vérifier taille minimale en pixels
        _cw = self._canvas_w if hasattr(self, '_canvas_w') and self._canvas_w else (self.width() or 800)
        _ch = self._canvas_h if hasattr(self, '_canvas_h') and self._canvas_h else (self.height() or 600)
        w_px = int(bbox_rel.w * _cw)
        h_px = int(bbox_rel.h * _ch)
        if w_px < self._min_size_px or h_px < self._min_size_px:
            raise ValueError(
                f"Zone trop petite : {w_px}×{h_px}px "
                f"(min {self._min_size_px}px)")
        from core.tier_result import TierLevel as TL
        effective_tier = tier if tier is not None else TL.MINOR
        zone = RoiZone.make(
            zone_type = zone_type,
            bbox_rel  = bbox_rel,
            tier      = effective_tier,
            label     = label,
            threshold = threshold,
            mandatory = mandatory,
        )
        self._zones.append(zone)
        self.update()
        return zone

    def get_tier_color(self, tier: "TierLevel") -> "QColor":
        """Retourne la couleur QColor associée au Tier."""
        name = tier.value if hasattr(tier, 'value') else str(tier)
        mapping = {
            'CRITICAL' : QColor(0xFF, 0x44, 0x44, 200),
            'MAJOR'    : QColor(0xFF, 0x88, 0x00, 200),
            'MINOR'    : QColor(0xFF, 0xCC, 0x00, 200),
        }
        return mapping.get(name, QColor(128, 128, 128, 200))

    def get_zone_type_color(self, zone_type: str) -> "QColor":
        """Retourne la couleur selon le type de zone."""
        mapping = {
            'ocr'    : QColor(0x44, 0xCC, 0x44, 200),
            'caliper': QColor(0x99, 0x44, 0xFF, 200),
            'color'  : QColor(0xFF, 0x44, 0xFF, 200),
            'roi'    : QColor(0xFF, 0x44, 0x44, 200),
        }
        return mapping.get(zone_type, QColor(128, 128, 128, 200))

    def get_all_criterion_rules(self) -> list:
        """Alias de to_criterion_rules() pour compatibilité tests."""
        return self.to_criterion_rules()

    def set_editable(self, editable: bool) -> None:
        """Active ou désactive l'édition (GR-12)."""
        self._editable = editable
        if not editable:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

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
        else:
            super().keyPressEvent(event)

    # ── Rendu ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        img_rect = self._image_rect()

        # Image de référence (ou fond gris)
        if self._pixmap is not None:
            painter.drawPixmap(img_rect, self._pixmap)
        else:
            painter.fillRect(img_rect, QColor(60, 60, 60))
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(img_rect, Qt.AlignmentFlag.AlignCenter, "Aucune image de référence")

        # Zones existantes
        for i, zone in enumerate(self._zones):
            self._draw_zone(painter, zone, selected=(i == self._selected_idx), img_rect=img_rect)

        # Rectangle de dessin en cours
        if self._draw_start is not None and self._draw_current is not None:
            self._draw_preview(painter, self._draw_start, self._draw_current)

        # Overlay RUNNING
        if not self._editable:
            overlay = QColor(0, 0, 0, 100)
            painter.fillRect(self.rect(), overlay)
            painter.setPen(QColor(255, 200, 0))
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Édition BLOQUÉE\n(inspection en cours)",
            )

    def _draw_zone(
        self,
        painter:  QPainter,
        zone:     RoiZone,
        selected: bool,
        img_rect: QRect,
    ) -> None:
        rect = self._rel_to_widget_rect(zone.bbox_rel, img_rect)

        fill   = _zone_fill_color(zone)
        border = _zone_border_color(zone, selected)

        painter.fillRect(rect, fill)

        pen = QPen(border, 2 if not selected else 3, Qt.PenStyle.SolidLine)
        if selected:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect)

        # Label
        painter.setPen(border)
        painter.setFont(QFont("Arial", 8))
        label_rect = QRect(rect.x(), rect.y() - 16, rect.width(), 16)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft, zone.label)

    def _draw_preview(self, painter: QPainter, p1: QPoint, p2: QPoint) -> None:
        rect = QRect(p1, p2).normalized()
        tier_map = {
            "ocr":     QColor(0x44, 0xCC, 0x44, 80),
            "caliper": QColor(0x99, 0x44, 0xFF, 80),
            "color":   QColor(0xFF, 0x88, 0x00, 80),
        }
        tier_border = {
            TierLevel.CRITICAL: QColor(0xFF, 0x44, 0x44, 200),
            TierLevel.MAJOR:    QColor(0xFF, 0x88, 0x00, 200),
            TierLevel.MINOR:    QColor(0xFF, 0xCC, 0x00, 200),
        }
        fill   = tier_map.get(self._current_type, QColor(200, 200, 200, 60))
        border = tier_map.get(self._current_type, tier_border.get(self._current_tier, QColor(200, 200, 200)))

        painter.fillRect(rect, fill)
        painter.setPen(QPen(border, 1, Qt.PenStyle.DashLine))
        painter.drawRect(rect)

    # ── Helpers coordonnées ───────────────────────────────────────────────────

    def _image_rect(self) -> QRect:
        """Rectangle dans lequel l'image est affichée (letterboxed)."""
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

    def _widget_to_rel(self, pos: QPoint, img_rect: QRect | None = None) -> tuple[float, float]:
        r = img_rect or self._image_rect()
        if r.width() == 0 or r.height() == 0:
            return 0.0, 0.0
        x = (pos.x() - r.x()) / r.width()
        y = (pos.y() - r.y()) / r.height()
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))

    def _rel_to_widget_rect(self, bbox: BoundingBox, img_rect: QRect) -> QRect:
        x = int(img_rect.x() + bbox.x * img_rect.width())
        y = int(img_rect.y() + bbox.y * img_rect.height())
        w = max(1, int(bbox.w * img_rect.width()))
        h = max(1, int(bbox.h * img_rect.height()))
        return QRect(x, y, w, h)

    # ── Logique dessin / sélection ────────────────────────────────────────────

    def _finalize_draw(self, p1: QPoint, p2: QPoint) -> None:
        """Crée une RoiZone à partir du rectangle dessiné."""
        if len(self._zones) >= self._max_zones:
            return

        img_rect = self._image_rect()
        rect     = QRect(p1, p2).normalized()

        # Contrainte taille minimale en pixels
        if rect.width() < self._min_size_px or rect.height() < self._min_size_px:
            return

        rx1, ry1 = self._widget_to_rel(rect.topLeft(),     img_rect)
        rx2, ry2 = self._widget_to_rel(rect.bottomRight(), img_rect)
        rw, rh   = rx2 - rx1, ry2 - ry1

        if rw <= 0 or rh <= 0:
            return

        try:
            bbox = BoundingBox(x=rx1, y=ry1, w=rw, h=rh)
        except Exception:
            return

        zone = RoiZone.make(
            zone_type = self._current_type,
            bbox_rel  = bbox,
            tier      = self._current_tier,
        )
        self._zones.append(zone)
        self._select(len(self._zones) - 1)
        self.zone_created.emit(zone)
        self.zones_changed.emit()

    def _try_select(self, pos: QPoint) -> None:
        """Sélectionne la zone sous le curseur (dernière zone en cas de chevauchement)."""
        img_rect = self._image_rect()
        hit      = None
        for i, zone in enumerate(self._zones):
            r = self._rel_to_widget_rect(zone.bbox_rel, img_rect)
            if r.contains(pos):
                hit = i
        if hit is not None:
            self._select(hit)
        else:
            self._selected_idx = None
            self.zone_selected.emit(None)

    def _select(self, idx: int) -> None:
        self._selected_idx = idx
        self.zone_selected.emit(self._zones[idx])

    def _update_cursor(self) -> None:
        if not self._editable:
            self.setCursor(QCursor(Qt.CursorShape.ForbiddenCursor))
        elif self._draw_mode:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))


# ─────────────────────────────────────────────────────────────────────────────
#  Helper — observer_id mapping
# ─────────────────────────────────────────────────────────────────────────────

def _observer_id_for(zone: RoiZone) -> str:
    if zone.zone_type == "ocr":
        return "ocr_tesseract"
    if zone.zone_type == "caliper":
        return f"caliper_{zone.zone_id}"
    if zone.zone_type == "color":
        return "color_delta_e"
    # "roi" → par tier
    return {
        TierLevel.CRITICAL: "yolo_sift",
        TierLevel.MAJOR:    "color_delta_e",
        TierLevel.MINOR:    "surface_isoforest",
    }.get(zone.tier, "yolo_sift")
