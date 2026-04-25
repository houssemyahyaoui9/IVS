"""
YoloObserver CRITICAL tier — §6.2
GR-04 : observe() retourne UNIQUEMENT ObserverSignal — jamais de verdict
GR-11 : jamais None — échec → ObserverSignal(confidence=0, error_msg=...)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from ai.yolo_engine import Detection, YoloEngine
from core.ai_observer import AIObserver
from core.models import CriterionRule, LogoDefinition, ProductDefinition
from core.tier_result import ObserverSignal, TierLevel

logger = logging.getLogger(__name__)

_DEFAULT_PPM       = 1.0
_DEFAULT_MODEL_PATH = Path("data/yolo/yolov8x.onnx")


class YoloObserver(AIObserver):
    """
    Observer YOLO pour détection de logos — §6.2.

    Pour chaque LogoDefinition du produit :
      1. Cherche la meilleure détection dans la zone attendue ± tolerance_mm
      2. Une détection "candidate" doit avoir son centre (cx,cy) dans la zone élargie
      3. Filtrage optionnel par class_name si le modèle fournit le mapping

    Agrégation multi-logo :
      confidence = min(confidence par logo)  ← worst-case
      passed     = True si tous les logos ont une détection ≥ rule.threshold
      details    = {"logos": [{logo_id, bbox, class_id, confidence}, ...]}

    GR-04 : retourne UNIQUEMENT ObserverSignal — jamais "OK", "NOK", True, False.
    GR-11 : try/except global → ObserverSignal(confidence=0, error_msg=...) si crash.
    """

    def __init__(
        self,
        engine:     Optional[YoloEngine] = None,
        model_path: Optional[Path]       = None,
        conf_thresh: float               = 0.45,
        iou_thresh:  float               = 0.45,
        class_names: Optional[list[str]] = None,
    ) -> None:
        if engine is not None:
            self._engine = engine
        else:
            path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
            self._engine = YoloEngine(
                model_path=path,
                conf_thresh=conf_thresh,
                iou_thresh=iou_thresh,
                class_names=class_names or [],
            )
        # Cache pixel_per_mm par product_id — stable pendant RUNNING (GR-12)
        self._ppm_cache: dict[str, float] = {}

    # ── ABC ───────────────────────────────────────────────────────────────────

    @property
    def observer_id(self) -> str:
        return "yolo_v8x"

    @property
    def tier(self) -> TierLevel:
        return TierLevel.CRITICAL

    # ── Point d'entrée principal ──────────────────────────────────────────────

    def observe(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
    ) -> ObserverSignal:
        """
        GR-04 : retourne UNIQUEMENT ObserverSignal — jamais de verdict.
        GR-11 : capture toutes les exceptions → ObserverSignal(confidence=0, error_msg=...).
        """
        t0 = time.perf_counter()
        try:
            return self._observe_impl(frame, product_def, rule, t0)
        except Exception as exc:
            logger.error("YoloObserver: exception non gérée — %s", exc, exc_info=True)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=False,
                confidence=0.0,
                value=0.0,
                threshold=rule.threshold,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error_msg=str(exc),
            )

    # ── Implémentation ────────────────────────────────────────────────────────

    def _observe_impl(
        self,
        frame:       np.ndarray,
        product_def: ProductDefinition,
        rule:        CriterionRule,
        t0:          float,
    ) -> ObserverSignal:
        logos = product_def.logo_definitions

        if not logos:
            logger.debug("YoloObserver: aucun logo défini pour '%s' — pass automatique",
                         product_def.product_id)
            return ObserverSignal(
                observer_id=self.observer_id,
                tier=self.tier,
                passed=True,
                confidence=1.0,
                value=1.0,
                threshold=rule.threshold,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                details={"logos": [], "note": "no logos defined"},
            )

        detections = self._engine.infer(frame)
        ppm        = self._load_ppm(product_def.product_id)

        logo_results: list[dict] = []
        for logo_def in logos:
            result = self._check_logo(detections, logo_def, ppm, rule.threshold)
            logo_results.append(result)

        scores     = [r["confidence"] for r in logo_results]
        min_score  = min(scores)
        all_passed = all(
            r["found"] and r["confidence"] >= rule.threshold
            for r in logo_results
        )

        logger.debug(
            "YoloObserver: '%s' logos=%d detections=%d min_conf=%.3f threshold=%.3f passed=%s",
            product_def.product_id, len(logos), len(detections),
            min_score, rule.threshold, all_passed,
        )

        return ObserverSignal(
            observer_id=self.observer_id,
            tier=self.tier,
            passed=all_passed,
            confidence=min_score,
            value=min_score,
            threshold=rule.threshold,
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={
                "logos":      logo_results,
                "n_detections": len(detections),
            },
        )

    # ── Vérification d'un logo ────────────────────────────────────────────────

    def _check_logo(
        self,
        detections: list[Detection],
        logo_def:   LogoDefinition,
        ppm:        float,
        threshold:  float,
    ) -> dict:
        """
        Trouve la meilleure détection dans la zone attendue pour ce logo.
        Retourne un dict de résultat (jamais None — GR-11).
        """
        zone_px = logo_def.expected_zone.to_pixel(ppm)
        tol_px  = max(1.0, logo_def.tolerance_mm * ppm)

        best: Optional[Detection] = None
        for det in detections:
            # Filtre optionnel : class_name doit correspondre si renseigné
            if logo_def.class_name and det.class_name:
                if det.class_name != logo_def.class_name:
                    continue
            if _detection_in_zone(det, zone_px, tol_px):
                if best is None or det.confidence > best.confidence:
                    best = det

        if best is None:
            return {
                "logo_id":    logo_def.logo_id,
                "found":      False,
                "confidence": 0.0,
                "bbox":       None,
                "class_id":   -1,
                "class_name": "",
            }

        return {
            "logo_id":    logo_def.logo_id,
            "found":      True,
            "confidence": round(best.confidence, 4),
            "bbox":       list(best.bbox),
            "class_id":   best.class_id,
            "class_name": best.class_name,
        }

    # ── Chargement paresseux ──────────────────────────────────────────────────

    def _load_ppm(self, product_id: str) -> float:
        """Charge pixel_per_mm depuis calibration/, mis en cache."""
        if product_id not in self._ppm_cache:
            path = (Path("products") / product_id / "calibration"
                    / "pixel_per_mm.json")
            if not path.exists():
                logger.warning("YoloObserver: pixel_per_mm absent — %s — défaut %.1f",
                               path, _DEFAULT_PPM)
                self._ppm_cache[product_id] = _DEFAULT_PPM
            else:
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    self._ppm_cache[product_id] = float(
                        data.get("pixel_per_mm", _DEFAULT_PPM)
                    )
                except Exception as exc:
                    logger.error("YoloObserver: échec lecture %s — %s", path, exc)
                    self._ppm_cache[product_id] = _DEFAULT_PPM
        return self._ppm_cache[product_id]


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detection_in_zone(
    det:    Detection,
    zone:   "BoundingBox",
    tol_px: float,
) -> bool:
    """
    Vérifie si le centre de la détection tombe dans la zone attendue ± tolérance.
    Zone et tolérance sont en pixels.
    """
    x_min = zone.x - tol_px
    y_min = zone.y - tol_px
    x_max = zone.x + zone.w + tol_px
    y_max = zone.y + zone.h + tol_px
    return x_min <= det.cx <= x_max and y_min <= det.cy <= y_max
