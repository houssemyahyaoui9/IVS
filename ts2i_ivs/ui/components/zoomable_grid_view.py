"""
ZoomableGridView — vue grille avec zoom snap / pan / snapshot async — §36.

Anti-pattern (CLAUDE.md) : interdiction d'utiliser QLabel pour les grilles.
GR-05 : opérations Qt dans le thread principal · I/O snapshot dans QThread.
"""
from __future__ import annotations

import os
import time
from bisect import bisect_left, bisect_right
from typing import Any, Optional

import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QAction, QImage, QKeySequence, QPainter, QPixmap, QShortcut, QWheelEvent,
)
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QMenu, QSizePolicy,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Snapshot worker (I/O hors thread UI — GR-05)
# ─────────────────────────────────────────────────────────────────────────────

class _SnapshotWorker(QThread):
    """Sauvegarde un QPixmap dans un fichier PNG sans bloquer le thread UI."""

    finished_with_path = pyqtSignal(str, bool)   # (path, success)

    def __init__(self, pixmap: QPixmap, path: str, parent=None) -> None:
        super().__init__(parent)
        self._pixmap = pixmap
        self._path   = path

    def run(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            ok = self._pixmap.save(self._path, "PNG")
        except Exception:
            ok = False
        self.finished_with_path.emit(self._path, bool(ok))


# ─────────────────────────────────────────────────────────────────────────────
#  ZoomableGridView
# ─────────────────────────────────────────────────────────────────────────────

class ZoomableGridView(QGraphicsView):
    """
    Vue zoomable + pannable d'une image (Live, Critical, Corrigé, …).

    Interactions §36 :
      - Molette                → zoom snap dans _ZOOM_LEVELS, centré sur souris
      - Clic gauche + drag     → pan (ScrollHandDrag)
      - Double-clic            → ouvre une FullscreenGridWindow
      - Clic droit             → menu contextuel (presets + snapshot + centrer)
      - set_result(...)        → auto-zoom ×4 si verdict NOK

    Signals :
      fullscreen_requested(QPixmap, str, dict, dict)
        — pixmap courant, label, tier_verdicts, llm_dict (peuvent être {} / None)
      snapshot_saved(str)
        — chemin PNG enregistré (émis depuis le worker)
    """

    _ZOOM_LEVELS = [0.5, 1.0, 1.5, 2.0, 4.0, 8.0]
    _ZOOM_NOK    = 4.0

    fullscreen_requested = pyqtSignal(object, str, object, object)
    snapshot_saved       = pyqtSignal(str)

    def __init__(
        self,
        label       : str           = "",
        snapshot_dir: Optional[str] = None,
        parent      = None,
    ) -> None:
        super().__init__(parent)
        self._label        = label
        self._snapshot_dir = snapshot_dir or os.path.join("data", "snapshots")
        self._zoom         = 1.0
        self._scene        = QGraphicsScene(self)
        self._pixmap_item  : Optional[QGraphicsPixmapItem] = None
        self._verdict      : Optional[str] = None
        self._tier_verdicts: dict          = {}
        self._llm_dict     : dict          = {}
        self._workers      : list[_SnapshotWorker] = []

        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.Antialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            "QGraphicsView { background:#0a0a0a; border:1px solid #333; }"
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.center_default)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._take_snapshot)

    # ─────────────────────────────────────────────────────────────────────────
    #  API publique
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def label(self) -> str:
        return self._label

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def pixmap(self) -> Optional[QPixmap]:
        return self._pixmap_item.pixmap() if self._pixmap_item is not None else None

    @property
    def verdict(self) -> Optional[str]:
        return self._verdict

    @property
    def tier_verdicts(self) -> dict:
        return dict(self._tier_verdicts)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Affiche `pixmap` (1 seul item à la fois) et recentre."""
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(pixmap.rect().toRectF())
        self.center_default()

    def set_image_array(self, array: np.ndarray) -> None:
        """numpy uint8 (H, W) ou (H, W, 3=BGR / 4=RGBA) → QPixmap."""
        if array is None or array.size == 0:
            return
        if array.ndim == 2:
            h, w = array.shape
            qimg = QImage(array.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
        else:
            h, w, c = array.shape
            fmt = QImage.Format.Format_BGR888 if c == 3 else QImage.Format.Format_RGBA8888
            qimg = QImage(array.tobytes(), w, h, w * c, fmt)
        self.set_pixmap(QPixmap.fromImage(qimg.copy()))

    def set_verdict(self, verdict: Optional[str]) -> None:
        """Auto-zoom ×4 si verdict bascule en NOK (§36)."""
        previous = self._verdict
        self._verdict = verdict
        if verdict == "NOK" and previous != "NOK":
            self.set_zoom(self._ZOOM_NOK)

    def set_result(
        self,
        pixmap         : Optional[QPixmap],
        tier_verdicts  : Optional[dict] = None,
        verdict        : Optional[str]  = None,
        llm_explanation: Optional[Any]  = None,
    ) -> None:
        """
        API combinée — §36 :
          - Met à jour pixmap si fourni
          - Stocke tier_verdicts + llm pour FullscreenGridWindow
          - Auto-zoom ×4 si verdict == 'NOK'
        """
        if pixmap is not None and not pixmap.isNull():
            self.set_pixmap(pixmap)

        self._tier_verdicts = dict(tier_verdicts or {})
        self._llm_dict      = _llm_to_dict(llm_explanation)
        self.set_verdict(verdict)

    def center_default(self) -> None:
        """Réinitialise zoom à ×1.0 et recadre sur l'image."""
        self.resetTransform()
        self._zoom = 1.0

    def reset_zoom(self) -> None:   # alias rétro-compat
        self.center_default()

    def set_zoom(self, factor: float) -> None:
        target = max(self._ZOOM_LEVELS[0], min(self._ZOOM_LEVELS[-1], float(factor)))
        if target == self._zoom or self._zoom == 0:
            return
        scale = target / self._zoom
        self.scale(scale, scale)
        self._zoom = target

    def save_snapshot(self) -> Optional[str]:
        """API publique — démarre un worker async. Retourne le path planifié."""
        return self._take_snapshot()

    # ─────────────────────────────────────────────────────────────────────────
    #  Événements
    # ─────────────────────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        self._step_zoom(up=delta > 0)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._pixmap_item is not None:
            self.fullscreen_requested.emit(
                self._pixmap_item.pixmap(),
                self._label,
                dict(self._tier_verdicts),
                dict(self._llm_dict),
            )
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        # Presets de zoom
        for level in self._ZOOM_LEVELS:
            mark = " ✓" if abs(self._zoom - level) < 1e-3 else ""
            act = QAction(f"Zoom ×{level:g}{mark}", self)
            act.triggered.connect(lambda _=False, lv=level: self.set_zoom(lv))
            menu.addAction(act)

        menu.addSeparator()

        act_center = QAction("Centrer (défaut · Ctrl+0)", self)
        act_center.triggered.connect(self.center_default)
        menu.addAction(act_center)

        act_snap = QAction("Snapshot PNG (Ctrl+S)", self)
        act_snap.triggered.connect(self._take_snapshot)
        menu.addAction(act_snap)

        act_full = QAction("Plein écran (double-clic)", self)
        act_full.triggered.connect(self._emit_fullscreen)
        menu.addAction(act_full)

        menu.exec(event.globalPos())

    # ─────────────────────────────────────────────────────────────────────────
    #  Snapshot async — data/snapshots/{YYYY-MM-DD}/snapshot_{ts}.png
    # ─────────────────────────────────────────────────────────────────────────

    def _take_snapshot(self) -> Optional[str]:
        if self._pixmap_item is None:
            return None
        date_dir  = time.strftime("%Y-%m-%d")
        ts        = time.strftime("%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        safe_lbl  = "".join(c if c.isalnum() else "_" for c in (self._label or "grid"))
        fname     = f"snapshot_{safe_lbl}_{ts}.png"
        full_dir  = os.path.join(self._snapshot_dir, date_dir)
        full_path = os.path.join(full_dir, fname)

        worker = _SnapshotWorker(self._pixmap_item.pixmap(), full_path, parent=self)
        self._workers.append(worker)
        worker.finished_with_path.connect(self._on_snapshot_done)
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        worker.start()
        return full_path

    def _on_snapshot_done(self, path: str, ok: bool) -> None:
        if ok:
            self.snapshot_saved.emit(path)

    def _cleanup_worker(self, worker: _SnapshotWorker) -> None:
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers internes
    # ─────────────────────────────────────────────────────────────────────────

    def _step_zoom(self, up: bool) -> None:
        levels = self._ZOOM_LEVELS
        # Index immédiatement supérieur / inférieur, en snap
        if up:
            idx = bisect_right(levels, self._zoom + 1e-6)
            target = levels[min(idx, len(levels) - 1)]
            if target <= self._zoom:
                target = levels[-1]
        else:
            idx = bisect_left(levels, self._zoom - 1e-6) - 1
            target = levels[max(idx, 0)]
            if target >= self._zoom:
                target = levels[0]
        self.set_zoom(target)

    def _emit_fullscreen(self) -> None:
        if self._pixmap_item is None:
            return
        self.fullscreen_requested.emit(
            self._pixmap_item.pixmap(),
            self._label,
            dict(self._tier_verdicts),
            dict(self._llm_dict),
        )


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
