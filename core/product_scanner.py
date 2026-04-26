"""
ProductScanner — auto-switch barcode §35
Thread daemon · intervalle 500ms · BarcodeDecoder pluggable
Anti-rebond 3s · signal product_detected(product_id) via callbacks.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional, Protocol

import numpy as np

from core.product_registry import ProductRegistry

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  BarcodeDecoder — protocole + implémentation par défaut (pyzbar)
# ─────────────────────────────────────────────────────────────────────────────

class BarcodeDecoder(Protocol):
    """Décodage barcode/QR sur frame BGR/grayscale → str ou None."""

    def decode(self, frame: np.ndarray) -> Optional[str]: ...


class PyzbarDecoder:
    """
    Décodeur par défaut basé sur pyzbar (1D + QR).
    Imports optionnels — absents → décodage neutralisé sans planter.
    """

    def __init__(self) -> None:
        try:
            from pyzbar import pyzbar as _pyzbar
            import cv2 as _cv2
            self._pyzbar = _pyzbar
            self._cv2    = _cv2
        except ImportError:
            self._pyzbar = None
            self._cv2    = None
            logger.warning(
                "PyzbarDecoder: pyzbar/cv2 absents — scanner inactif "
                "(pip install pyzbar opencv-python)"
            )

    def decode(self, frame: np.ndarray) -> Optional[str]:
        if self._pyzbar is None or self._cv2 is None or frame is None:
            return None
        gray = (
            self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)
            if frame.ndim == 3 else frame
        )
        codes = self._pyzbar.decode(gray)
        if not codes:
            return None
        return codes[0].data.decode("utf-8", errors="replace").strip() or None


# ─────────────────────────────────────────────────────────────────────────────
#  ProductScanner
# ─────────────────────────────────────────────────────────────────────────────

ProductDetectedCallback = Callable[[str], None]


class ProductScanner:
    """
    Scanner barcode en thread daemon — §35.

    À chaque tick (interval_ms, défaut 500) :
      1. Récupère une frame via `frame_source()`.
      2. Décode via `decoder.decode(frame)`.
      3. Résout barcode → product_id via `registry.lookup()`.
      4. Anti-rebond : un même product_id n'est pas réémis dans
         la fenêtre `debounce_s` (défaut 3.0s).
      5. Émet `product_detected(product_id)` vers tous les callbacks
         abonnés via `subscribe()`.

    Thread-safe. Les callbacks sont invoqués dans le thread du scanner —
    si Qt est concerné, brancher via QueuedConnection (GR-05).
    """

    def __init__(
        self,
        frame_source : Callable[[], Optional[np.ndarray]],
        registry     : ProductRegistry,
        decoder      : Optional[BarcodeDecoder] = None,
        interval_ms  : int   = 500,
        debounce_s   : float = 3.0,
    ) -> None:
        if interval_ms <= 0:
            raise ValueError(f"interval_ms={interval_ms} doit être > 0")
        if debounce_s < 0:
            raise ValueError(f"debounce_s={debounce_s} doit être >= 0")

        self._frame_source = frame_source
        self._registry     = registry
        self._decoder      = decoder if decoder is not None else PyzbarDecoder()
        self._interval_s   = interval_ms / 1000.0
        self._debounce_s   = debounce_s

        self._callbacks : list[ProductDetectedCallback] = []
        self._cb_lock   = threading.RLock()

        self._stop_evt = threading.Event()
        self._thread   : Optional[threading.Thread] = None

        self._last_emit : dict[str, float] = {}   # product_id → monotonic ts

    # ── Souscription aux détections ───────────────────────────────────────────

    def subscribe(self, callback: ProductDetectedCallback) -> None:
        with self._cb_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unsubscribe(self, callback: ProductDetectedCallback) -> None:
        with self._cb_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, name="ProductScanner", daemon=True,
        )
        self._thread.start()
        logger.info(
            "ProductScanner démarré (interval=%dms, debounce=%.1fs)",
            int(self._interval_s * 1000), self._debounce_s,
        )

    def stop(self, timeout_s: float = 2.0) -> None:
        self._stop_evt.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_s)
        self._thread = None
        logger.info("ProductScanner arrêté")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Boucle de scan ────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.monotonic()
            try:
                self._scan_once()
            except Exception as exc:
                logger.error(
                    "ProductScanner: erreur scan — %s", exc, exc_info=True,
                )
            elapsed = time.monotonic() - t0
            wait = max(0.0, self._interval_s - elapsed)
            if self._stop_evt.wait(wait):
                break

    def _scan_once(self) -> None:
        frame = self._frame_source()
        if frame is None:
            return
        code = self._decoder.decode(frame)
        if not code:
            return
        product_id = self._registry.lookup(code)
        if product_id is None:
            logger.debug("ProductScanner: barcode '%s' non indexé", code)
            return
        if not self._consume_debounce(product_id):
            return
        self._emit(product_id)

    def _consume_debounce(self, product_id: str) -> bool:
        now  = time.monotonic()
        last = self._last_emit.get(product_id)
        if last is not None and (now - last) < self._debounce_s:
            return False
        self._last_emit[product_id] = now
        return True

    def _emit(self, product_id: str) -> None:
        with self._cb_lock:
            callbacks = list(self._callbacks)
        logger.info("ProductScanner: product_detected('%s')", product_id)
        for cb in callbacks:
            try:
                cb(product_id)
            except Exception as exc:
                logger.error(
                    "ProductScanner: callback %r a levé %s",
                    cb, exc, exc_info=True,
                )
