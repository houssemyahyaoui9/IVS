"""
YOLOv8x ONNX inference — §6.2
Préprocess : resize 640×640 · /255.0 · CHW
NMS        : cv2.dnn.NMSBoxes conf=0.45 iou=0.45
GR-01      : ExecutionMode séquentiel → inférence déterministe
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)

_INPUT_SIZE   = 640
_CONF_DEFAULT = 0.45
_IOU_DEFAULT  = 0.45


# ─────────────────────────────────────────────────────────────────────────────
#  Detection — sortie de l'inférence YOLO
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Detection:
    """
    Une détection YOLO dans le repère de l'image originale.

    bbox       : (x, y, w, h) en pixels — coin haut-gauche + dimensions
    class_id   : indice de classe YOLO (0-based)
    confidence : score de confiance [0.0, 1.0]
    class_name : nom de classe (facultatif, rempli si class_names fourni à YoloEngine)
    """
    bbox:       tuple[int, int, int, int]
    class_id:   int
    confidence: float
    class_name: str = ""

    @property
    def cx(self) -> float:
        return self.bbox[0] + self.bbox[2] / 2.0

    @property
    def cy(self) -> float:
        return self.bbox[1] + self.bbox[3] / 2.0


# ─────────────────────────────────────────────────────────────────────────────
#  YoloEngine
# ─────────────────────────────────────────────────────────────────────────────

class YoloEngine:
    """
    Moteur d'inférence YOLOv8 ONNX — §6.2.

    Pipeline :
      1. Préprocess : resize 640×640, /255.0, HWC→CHW, ajout batch dim
      2. Inférence  : onnxruntime.InferenceSession (mode séquentiel — GR-01)
      3. Postprocess : filtrage par confidence, NMS, rescale vers image originale

    Format de sortie ONNX YOLOv8 attendu :
      (1, 4 + num_classes, num_anchors) — ex. (1, 84, 8400) pour COCO-80.
      Colonnes 0-3 : cx, cy, w, h normalisés sur 640×640.
      Colonnes 4+  : scores par classe (pas d'objectness séparé en v8).

    GR-01 : ExecutionMode.ORT_SEQUENTIAL → résultats reproductibles.
    """

    def __init__(
        self,
        model_path:   str | Path,
        conf_thresh:  float      = _CONF_DEFAULT,
        iou_thresh:   float      = _IOU_DEFAULT,
        class_names:  list[str]  = None,
    ) -> None:
        self._conf_thresh  = conf_thresh
        self._iou_thresh   = iou_thresh
        self._class_names  = class_names or []
        self._session: Optional[ort.InferenceSession] = None
        self._input_name:  str = ""
        self._output_name: str = ""
        self._model_path   = Path(model_path)
        self._load_session()

    # ── Inférence ─────────────────────────────────────────────────────────────

    def infer(self, frame: np.ndarray) -> list[Detection]:
        """
        Détecte les objets dans frame.

        Args:
            frame : image BGR uint8, toute résolution.

        Returns:
            list[Detection] triée par confiance décroissante.
            Liste vide si aucune détection ou modèle non chargé.
        """
        if self._session is None:
            logger.warning("YoloEngine: session non initialisée — infer() ignoré")
            return []

        orig_h, orig_w = frame.shape[:2]
        blob = _preprocess(frame)

        try:
            raw = self._session.run(
                [self._output_name],
                {self._input_name: blob},
            )[0]
        except Exception as exc:
            logger.error("YoloEngine: inférence échouée — %s", exc)
            return []

        return _postprocess(
            raw,
            orig_w=orig_w,
            orig_h=orig_h,
            conf_thresh=self._conf_thresh,
            iou_thresh=self._iou_thresh,
            class_names=self._class_names,
        )

    # ── Chargement ────────────────────────────────────────────────────────────

    def _load_session(self) -> None:
        if not self._model_path.exists():
            logger.warning("YoloEngine: modèle absent — %s", self._model_path)
            return

        opts = ort.SessionOptions()
        # GR-01 : mode séquentiel → déterministe entre appels
        opts.execution_mode              = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level    = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.inter_op_num_threads        = 1
        opts.intra_op_num_threads        = 0   # auto
        opts.log_severity_level          = 3   # ERROR seulement

        try:
            self._session = ort.InferenceSession(
                str(self._model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._input_name  = self._session.get_inputs()[0].name
            self._output_name = self._session.get_outputs()[0].name
            logger.info(
                "YoloEngine: session chargée — %s (input=%s)",
                self._model_path.name, self._input_name,
            )
        except Exception as exc:
            logger.error("YoloEngine: impossible de charger %s — %s",
                         self._model_path, exc)

    def __repr__(self) -> str:
        loaded = self._session is not None
        return f"YoloEngine(model={self._model_path.name!r}, loaded={loaded})"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers préprocessing / postprocessing
# ─────────────────────────────────────────────────────────────────────────────

def _preprocess(frame: np.ndarray) -> np.ndarray:
    """
    BGR uint8 → (1, 3, 640, 640) float32 normalisé [0, 1].
    Simple resize sans letterbox (§6.2 spec).
    """
    resized = cv2.resize(frame, (_INPUT_SIZE, _INPUT_SIZE),
                         interpolation=cv2.INTER_LINEAR)
    blob    = resized.astype(np.float32) / 255.0
    blob    = blob.transpose(2, 0, 1)         # HWC → CHW
    blob    = blob[np.newaxis, ...]            # → (1, 3, 640, 640)
    return blob


def _postprocess(
    raw:         np.ndarray,
    orig_w:      int,
    orig_h:      int,
    conf_thresh: float,
    iou_thresh:  float,
    class_names: list[str],
) -> list[Detection]:
    """
    YOLOv8 ONNX output → list[Detection] en coordonnées image originale.

    raw shape attendu : (1, 4+nc, num_anchors) ou (4+nc, num_anchors).
    """
    # Normalise shape → (num_anchors, 4+nc)
    out = raw[0] if raw.ndim == 3 else raw
    if out.shape[0] < out.shape[1]:
        out = out.T   # (num_anchors, 4+nc)

    if out.shape[1] < 5:
        logger.warning("YoloEngine: sortie ONNX inattendue shape=%s", raw.shape)
        return []

    boxes_cxcywh = out[:, :4]    # cx, cy, w, h en espace 640×640
    class_scores = out[:, 4:]    # (num_anchors, nc)

    confidences = class_scores.max(axis=1)
    class_ids   = class_scores.argmax(axis=1)

    # Filtre par seuil de confiance
    mask        = confidences >= conf_thresh
    if not mask.any():
        return []

    boxes_cxcywh = boxes_cxcywh[mask]
    confidences  = confidences[mask]
    class_ids    = class_ids[mask]

    # Conversion cx,cy,w,h → x,y,w,h + rescale vers image originale
    scale_x = orig_w / _INPUT_SIZE
    scale_y = orig_h / _INPUT_SIZE

    bboxes_xywh: list[list[int]] = []
    for (cx, cy, bw, bh) in boxes_cxcywh:
        x = int((cx - bw / 2) * scale_x)
        y = int((cy - bh / 2) * scale_y)
        w = int(bw * scale_x)
        h = int(bh * scale_y)
        # Clamp to image bounds
        x = max(0, min(x, orig_w - 1))
        y = max(0, min(y, orig_h - 1))
        w = max(1, min(w, orig_w - x))
        h = max(1, min(h, orig_h - y))
        bboxes_xywh.append([x, y, w, h])

    # NMS
    nms_indices = cv2.dnn.NMSBoxes(
        bboxes_xywh,
        confidences.tolist(),
        conf_thresh,
        iou_thresh,
    )

    if len(nms_indices) == 0:
        return []

    # cv2.dnn.NMSBoxes returns shape (N,) or (N,1) depending on OpenCV version
    flat = np.array(nms_indices).flatten()

    detections: list[Detection] = []
    for idx in flat:
        i      = int(idx)
        cid    = int(class_ids[i])
        cname  = class_names[cid] if cid < len(class_names) else str(cid)
        x, y, w, h = bboxes_xywh[i]
        detections.append(Detection(
            bbox=(x, y, w, h),
            class_id=cid,
            confidence=float(confidences[i]),
            class_name=cname,
        ))

    # Trier par confiance décroissante
    detections.sort(key=lambda d: d.confidence, reverse=True)
    return detections
