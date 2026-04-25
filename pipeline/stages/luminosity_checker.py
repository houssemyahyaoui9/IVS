"""
LuminosityChecker — contrôle de luminosité — §42
Chargé depuis brightness_reference.json (calibration §10 étape 2)
Intégré dans S2 avant tout traitement AI
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from typing import Optional

import cv2
import numpy as np

from camera.camera_manager import RawFrame
from core.models import LuminosityResult, ProductDefinition

logger = logging.getLogger(__name__)

# Seuils par défaut (écrasés par brightness_reference.json)
_DEFAULT_WARN_PCT     = 15.0
_DEFAULT_CRITICAL_PCT = 30.0
_DEFAULT_REF_MEAN     = 128.0


class LuminosityChecker:
    """
    Contrôle de luminosité basé sur la référence de calibration.

    Utilisation :
        checker = LuminosityChecker()
        checker.load_reference(calib_dir)          # après calibration
        lum = checker.check(raw_frame)             # dans S2
    """

    def __init__(
        self,
        warn_percent:     float = _DEFAULT_WARN_PCT,
        critical_percent: float = _DEFAULT_CRITICAL_PCT,
    ) -> None:
        self._warn_pct     = warn_percent
        self._critical_pct = critical_percent
        self._ref_mean     = _DEFAULT_REF_MEAN
        self._ref_std      = 0.0
        self._min_ok       = _DEFAULT_REF_MEAN * (1.0 - warn_percent / 100.0)
        self._max_ok       = _DEFAULT_REF_MEAN * (1.0 + warn_percent / 100.0)
        self._loaded       = False

    # ── Chargement référence ──────────────────────────────────────────────────

    def load_reference(self, calib_dir: Path) -> None:
        """
        Charge brightness_reference.json produit à l'étape 2 de calibration.
        GR-06 : appelé une seule fois avant la boucle d'inspection.
        """
        path = calib_dir / "brightness_reference.json"
        if not path.exists():
            logger.warning("LuminosityChecker: %s introuvable — valeurs par défaut", path)
            return

        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        self._ref_mean     = float(data.get("mean",             _DEFAULT_REF_MEAN))
        self._ref_std      = float(data.get("std",              0.0))
        self._min_ok       = float(data.get("min_ok",  self._ref_mean * 0.85))
        self._max_ok       = float(data.get("max_ok",  self._ref_mean * 1.15))
        self._warn_pct     = float(data.get("warn_percent",     _DEFAULT_WARN_PCT))
        self._critical_pct = float(data.get("critical_percent", _DEFAULT_CRITICAL_PCT))
        self._loaded       = True
        logger.info("LuminosityChecker: référence chargée mean=%.1f warn=%.0f%% critical=%.0f%%",
                    self._ref_mean, self._warn_pct, self._critical_pct)

    # ── Vérification ─────────────────────────────────────────────────────────

    def check(
        self,
        raw_frame   : RawFrame,
        product_def : Optional[ProductDefinition] = None,  # noqa: ARG002 — réservé v7.x
    ) -> LuminosityResult:
        """
        Évalue la luminosité d'une frame brute.

        Calcul (§18.3) :
          gray    = cv2.cvtColor(BGR2GRAY)
          mean_b  = float(np.mean(gray))
          dev_pct = |mean_b - ref_mean| / (ref_mean + 1e-6) × 100
          warning  = warn_percent < dev_pct ≤ critical_percent  (15-30 %)
          critical = dev_pct > critical_percent (30 %)

        `product_def` est accepté pour évolution future (référence par produit) ;
        actuellement ignoré — la référence courante vient de `load_reference()`.

        Returns:
            LuminosityResult — jamais None (GR-11).
        """
        gray      = cv2.cvtColor(raw_frame.image, cv2.COLOR_BGR2GRAY)
        value     = float(np.mean(gray))
        ref       = self._ref_mean
        delta_pct = abs(value - ref) / (ref + 1e-6) * 100.0

        ok       = delta_pct <= self._warn_pct
        warning  = self._warn_pct < delta_pct <= self._critical_pct
        critical = delta_pct > self._critical_pct

        result = LuminosityResult(
            value=round(value, 2),
            ref_mean=round(ref, 2),
            delta_percent=round(delta_pct, 2),
            ok=ok,
            warning=warning,
            critical=critical,
        )

        if critical:
            logger.warning("LuminosityChecker: CRITICAL delta=%.1f%% (seuil=%.0f%%)",
                           delta_pct, self._critical_pct)
        elif warning:
            logger.debug("LuminosityChecker: WARNING delta=%.1f%%", delta_pct)

        return result

    # ── Accesseurs ────────────────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def ref_mean(self) -> float:
        return self._ref_mean
