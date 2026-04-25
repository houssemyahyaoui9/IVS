"""
ZoomableGridView — §36
QWidget pour afficher une frame caméra avec zoom et pan.

Slot principal :
  set_frame(payload) — accepte np.ndarray BGR ou QPixmap.

Zoom : molette souris (Ctrl+wheel), Pan : drag souris.
Pas de dépendance pipeline — alimenté via signal UIBridge.frame_ready.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
    QWidget,
)

logger = logging.getLogger(__name__)

_MIN_ZOOM = 0.1
_MAX_ZOOM = 10.0
_WHEEL_FACTOR = 1.15


class ZoomableGridView(QGraphicsView):
    """
    Vue d'image avec zoom (molette) et pan (drag).

    Construction :
        view = ZoomableGridView(title="Live")
        bridge.frame_ready.connect(view.set_frame)
    """

    frame_received = pyqtSignal(int)   # nb total de frames reçues (debug/tests)

    def __init__(
        self,
        title  : str = "",
        parent : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ZoomableGridView")
        self._title = title

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None

        self._frame_count = 0

        # Apparence
        self.setRenderHints(
            QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing
        )
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 150)
        self.setStyleSheet(
            "QGraphicsView#ZoomableGridView { border: 1px solid #333; background:#000; }"
        )

    # ── API publique ──────────────────────────────────────────────────────────

    def set_frame(self, payload: Any) -> None:
        """
        Affiche une frame. Accepte :
          - np.ndarray BGR (H×W×3 uint8) ou GRAY (H×W uint8)
          - QImage
          - QPixmap
          - None (efface la vue)
        """
        if payload is None:
            self._clear_pixmap()
            return

        pix = self._to_pixmap(payload)
        if pix is None or pix.isNull():
            return

        if self._pixmap_item is None:
            self._pixmap_item = self._scene.addPixmap(pix)
            self._scene.setSceneRect(pix.rect().toRectF())
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self._pixmap_item.setPixmap(pix)
            self._scene.setSceneRect(pix.rect().toRectF())

        self._frame_count += 1
        self.frame_received.emit(self._frame_count)

    @property
    def title(self) -> str:
        return self._title

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def has_frame(self) -> bool:
        return self._pixmap_item is not None

    # ── Conversion payload → QPixmap ──────────────────────────────────────────

    @staticmethod
    def _to_pixmap(payload: Any) -> Optional[QPixmap]:
        if isinstance(payload, QPixmap):
            return payload
        if isinstance(payload, QImage):
            return QPixmap.fromImage(payload)
        if isinstance(payload, np.ndarray):
            return ZoomableGridView._ndarray_to_pixmap(payload)
        return None

    @staticmethod
    def _ndarray_to_pixmap(arr: np.ndarray) -> Optional[QPixmap]:
        if arr.size == 0:
            return None
        if arr.ndim == 2:
            h, w = arr.shape
            qimg = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
            return QPixmap.fromImage(qimg)
        if arr.ndim == 3 and arr.shape[2] in (3, 4):
            h, w, ch = arr.shape
            # OpenCV BGR → Qt RGB888 nécessite swap de canaux R↔B.
            if ch == 3:
                rgb = arr[:, :, ::-1].copy()
                qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                return QPixmap.fromImage(qimg)
            if ch == 4:
                qimg = QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
                return QPixmap.fromImage(qimg)
        logger.debug("ZoomableGridView: ndarray non supporté shape=%s", arr.shape)
        return None

    def _clear_pixmap(self) -> None:
        if self._pixmap_item is not None:
            self._scene.removeItem(self._pixmap_item)
            self._pixmap_item = None

    # ── Zoom / Pan ────────────────────────────────────────────────────────────

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier or self._pixmap_item is None:
            super().wheelEvent(event)
            return
        # Zoom centré sur la position du curseur
        delta = event.angleDelta().y()
        factor = _WHEEL_FACTOR if delta > 0 else 1.0 / _WHEEL_FACTOR
        # Clamp zoom global (échelle courante = m11)
        current = self.transform().m11()
        new = current * factor
        if new < _MIN_ZOOM:
            factor = _MIN_ZOOM / current
        elif new > _MAX_ZOOM:
            factor = _MAX_ZOOM / current
        self.scale(factor, factor)

    def fit_to_view(self) -> None:
        """Redimensionne la vue à l'image entière."""
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Au redimensionnement initial, ajuster l'image.
        if self._pixmap_item is not None and self._frame_count <= 1:
            self.fit_to_view()
