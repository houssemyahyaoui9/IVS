"""
YOLOv8x fine-tuning seed=42 — §6.2 / §11
Requires : pip install ultralytics
Export ONNX opset=12 après entraînement.
GR-01 : seed=42 garanti.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_EPOCHS     = 30
_DEFAULT_BATCH      = 4
_DEFAULT_DEVICE     = "cpu"
_BASE_MODEL         = "yolov8x.pt"
_SEED               = 42    # GR-01
_ONNX_OPSET         = 12


class YoloTrainer:
    """
    Fine-tune YOLOv8x sur un dataset produit puis exporte en ONNX.

    train(dataset_path, product_id, epochs=30) → str (chemin .onnx)

    Attend un dataset au format Ultralytics YOLO :
        dataset_path/
            data.yaml            ← obligatoire
            images/train/...
            images/val/...
            labels/train/...
            labels/val/...

    Sortie :
        products/{product_id}/models/yolo_train/weights/best.onnx
        (copié vers products/{product_id}/models/yolov8x_trained.onnx)

    Requires : pip install ultralytics
    GR-01 : seed=42 dans model.train()
    """

    def __init__(self, device: str = _DEFAULT_DEVICE) -> None:
        self._device = device

    def train(
        self,
        dataset_path: str | Path,
        product_id:   str,
        epochs:       int = _DEFAULT_EPOCHS,
        batch:        int = _DEFAULT_BATCH,
    ) -> str:
        """
        Entraîne YOLOv8x et exporte le modèle en ONNX.

        Args:
            dataset_path : répertoire contenant data.yaml + images/ + labels/
            product_id   : identifiant produit (destination models/)
            epochs       : nombre d'époques (défaut 30)
            batch        : taille de batch (défaut 4 pour CPU)

        Returns:
            Chemin absolu vers le fichier .onnx exporté.

        Raises:
            ImportError       : si ultralytics n'est pas installé
            FileNotFoundError : si data.yaml est absent
            RuntimeError      : si l'entraînement échoue
        """
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "ultralytics non installé — exécutez : pip install ultralytics"
            ) from exc

        dataset_path = Path(dataset_path)
        data_yaml    = dataset_path / "data.yaml"

        if not data_yaml.exists():
            raise FileNotFoundError(
                f"YoloTrainer: data.yaml introuvable dans {dataset_path}\n"
                "Format attendu : images/train · images/val · labels/train · labels/val"
            )

        project_dir = Path("products") / product_id / "models"
        project_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "YoloTrainer: démarrage entraînement — product='%s' epochs=%d "
            "batch=%d device=%s seed=%d",
            product_id, epochs, batch, self._device, _SEED,
        )

        model   = YOLO(_BASE_MODEL)
        results = model.train(
            data=str(data_yaml),
            epochs=epochs,
            batch=batch,
            device=self._device,
            seed=_SEED,             # GR-01
            project=str(project_dir),
            name="yolo_train",
            exist_ok=True,          # écrase un run précédent du même nom
            verbose=False,
        )

        # Poids best.pt → exporter en ONNX opset=12
        best_pt = project_dir / "yolo_train" / "weights" / "best.pt"
        if not best_pt.exists():
            raise RuntimeError(
                f"YoloTrainer: best.pt introuvable après entraînement — {best_pt}"
            )

        logger.info("YoloTrainer: export ONNX opset=%d depuis %s", _ONNX_OPSET, best_pt)
        export_model = YOLO(str(best_pt))
        export_model.export(format="onnx", opset=_ONNX_OPSET, dynamic=False)

        # best.onnx est créé au même endroit que best.pt
        best_onnx = best_pt.with_suffix(".onnx")
        if not best_onnx.exists():
            raise RuntimeError(
                f"YoloTrainer: export ONNX échoué — {best_onnx} introuvable"
            )

        # Copier vers destination canonique du produit
        dest = project_dir / "yolov8x_trained.onnx"
        shutil.copy2(best_onnx, dest)

        logger.info(
            "YoloTrainer: entraînement terminé — modèle ONNX → %s", dest,
        )
        return str(dest)

    # ── Utilitaire : génération data.yaml ────────────────────────────────────

    @staticmethod
    def write_data_yaml(
        dataset_path: str | Path,
        class_names:  list[str],
    ) -> Path:
        """
        Génère un data.yaml compatible Ultralytics pour un dataset produit.

        Args:
            dataset_path : répertoire racine du dataset
            class_names  : liste des noms de classes (ex. ["ce_mark", "brand_logo"])

        Returns:
            Path vers le data.yaml créé.
        """
        import yaml

        dataset_path = Path(dataset_path).resolve()
        nc           = len(class_names)

        data = {
            "path":  str(dataset_path),
            "train": "images/train",
            "val":   "images/val",
            "nc":    nc,
            "names": class_names,
        }

        out = dataset_path / "data.yaml"
        with open(out, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, allow_unicode=True, default_flow_style=False)

        logger.info(
            "YoloTrainer.write_data_yaml: %s — %d classes : %s",
            out, nc, class_names,
        )
        return out
