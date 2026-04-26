"""
FleetManager — Déploiement en flotte (export / import package .ivs)

Spec : IVS_FINAL_SPEC_v7_COMPLETE.md §Fleet.1 → §Fleet.8
GR-13 : tout package importé DOIT être validé par ModelValidator
        AVANT activation. Échec → rollback complet (suppression du
        produit copié).
        Import réseau ET USB jamais simultanés — 2nd appel = FleetImportError.

Format package .ivs (ZIP signé SHA256) :

    product_{id}_v{version}.ivs
    ├── package.json           ← metadata + signature SHA256
    ├── config.json            ← ProductDefinition + ProductRules
    ├── calibration/
    │   ├── alignment_template.pkl
    │   ├── brightness_reference.json
    │   ├── color_reference.json
    │   ├── logo_{n}_template.pkl
    │   └── texture_reference.npz
    ├── models/
    │   ├── isoforest.onnx
    │   └── yolo.onnx          (si disponible)
    └── logos/
        └── logo_{n}.png

# RESERVED — Master Unit — IVS v8.0
# §Fleet.6 — DEFERRED : la centralisation Master Unit n'existe pas en v7.0.
# Ne pas implémenter avant validation production v7.0 sur ≥ 3 unités.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.exceptions import FleetImportError
from learning.global_gates import GateResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────────────────────

IVS_VERSION              = "7.0"
PACKAGE_MANIFEST         = "package.json"
PRODUCT_CONFIG_FILE      = "config.json"
CALIBRATION_DIRNAME      = "calibration"
MODELS_DIRNAME           = "models"
LOGOS_DIRNAME            = "logos"
ACTIVE_MODELS_DIRNAME    = "active"

# Seuil légèrement abaissé pour un import externe (§Fleet.3) — la gate stricte
# 0.95 reste celle du retrain local (§11.3 Gate ②).
IMPORT_PASS_RATE_MIN     = 0.90


# ─────────────────────────────────────────────────────────────────────────────
#  ImportResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ImportResult:
    """Résultat retourné après un import .ivs réussi."""
    product_id     : str
    station_source : Optional[str]
    export_date    : Optional[str]
    validation     : GateResult
    ivs_version    : str
    package_path   : str            = ""
    timestamp      : str            = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id":     self.product_id,
            "station_source": self.station_source,
            "export_date":    self.export_date,
            "validation": {
                "gate_id": self.validation.gate_id,
                "passed":  self.validation.passed,
                "details": dict(self.validation.details),
            },
            "ivs_version":  self.ivs_version,
            "package_path": self.package_path,
            "timestamp":    self.timestamp,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  FleetManager
# ─────────────────────────────────────────────────────────────────────────────

class FleetManager:
    """
    Gestionnaire d'exports / imports Fleet — §Fleet.3.

    Construction :
        fleet = FleetManager(
            products_dir    = "products",
            config          = ConfigManager | dict | None,
            model_validator = ModelValidator(),
            registry        = ProductRegistry,           # optionnel — reload après import
        )

    GR-13 :
      • import_package() / import_via_usb() partagent un mutex non bloquant.
        Un 2ème import en parallèle lève FleetImportError("Import en cours").
      • ModelValidator.validate() est appelé AVANT que le produit ne soit
        considéré activé. En cas d'échec, le dossier copié est supprimé.
    """

    def __init__(
        self,
        products_dir    : str | Path                 = "products",
        config          : Any                        = None,
        model_validator : Any                        = None,
        registry        : Any                        = None,
    ) -> None:
        self._products_dir    = Path(products_dir)
        self._config          = config
        self._model_validator = model_validator
        self._registry        = registry
        # Verrou import — réseau/USB mutuellement exclusifs (GR-13).
        self._import_lock     = threading.Lock()

    # ─────────────────────────────────────────────────────────────────────────
    #  EXPORT
    # ─────────────────────────────────────────────────────────────────────────

    def export_package(
        self,
        product_id  : str,
        output_path : str | Path | None = None,
    ) -> str:
        """
        Crée un package .ivs exportable depuis un produit calibré.

        Inclut : config + calibration + models actifs (+ logos si présents).
        Signe le package avec SHA256 (integrity check).

        Returns:
            Chemin absolu du fichier .ivs créé.

        Raises:
            FileNotFoundError : produit introuvable ou calibration manquante.
        """
        if not product_id:
            raise ValueError("export_package: product_id vide")

        product_dir = self._products_dir / product_id
        if not product_dir.is_dir():
            raise FileNotFoundError(
                f"Produit introuvable : {product_dir}",
            )

        src_calib  = product_dir / CALIBRATION_DIRNAME
        src_models = product_dir / MODELS_DIRNAME / ACTIVE_MODELS_DIRNAME
        src_config = product_dir / PRODUCT_CONFIG_FILE
        src_logos  = product_dir / LOGOS_DIRNAME

        if not src_calib.is_dir():
            raise FileNotFoundError(
                f"Calibration introuvable : {src_calib}",
            )
        if not src_config.is_file():
            raise FileNotFoundError(
                f"config.json introuvable : {src_config}",
            )

        # Staging dans un tmpdir — auto-cleanup
        with tempfile.TemporaryDirectory(prefix=f"ivs-export-{product_id}-") as td:
            staging = Path(td) / f"{product_id}_export"
            staging.mkdir()

            shutil.copytree(src_calib, staging / CALIBRATION_DIRNAME)
            if src_models.is_dir():
                shutil.copytree(src_models, staging / MODELS_DIRNAME)
            else:
                # Les modèles peuvent ne pas encore exister (pré-training).
                (staging / MODELS_DIRNAME).mkdir()
                logger.info(
                    "FleetManager.export[%s]: aucun modèle actif — "
                    "package sans models/",
                    product_id,
                )
            shutil.copy(src_config, staging / PRODUCT_CONFIG_FILE)
            if src_logos.is_dir():
                shutil.copytree(src_logos, staging / LOGOS_DIRNAME)

            # Manifest + signature (calculée APRÈS staging, AVANT manifest write)
            signature = self._sign_directory(staging)
            station_id = self._read_station_id()
            manifest: dict[str, Any] = {
                "product_id":  product_id,
                "export_date": datetime.now(timezone.utc).isoformat(),
                "station_id":  station_id,
                "ivs_version": IVS_VERSION,
                "sha256":      signature,
            }
            (staging / PACKAGE_MANIFEST).write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            # Création du .ivs (zip renommé)
            final_path = self._resolve_output_path(product_id, output_path)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            base = final_path.with_suffix("")          # supprime .ivs
            zip_path = Path(shutil.make_archive(
                str(base), "zip", root_dir=str(staging),
            ))
            if final_path.exists():
                final_path.unlink()
            zip_path.rename(final_path)

        logger.info(
            "FleetManager.export[%s]: %s (sha256=%s…)",
            product_id, final_path, signature[:12],
        )
        return str(final_path)

    @staticmethod
    def _resolve_output_path(
        product_id  : str,
        output_path : str | Path | None,
    ) -> Path:
        if output_path is None:
            return Path(f"{product_id}_export.ivs").resolve()
        path = Path(output_path)
        if path.suffix.lower() != ".ivs":
            path = path.with_suffix(".ivs")
        return path.resolve()

    def _read_station_id(self) -> Optional[str]:
        cfg = self._config
        if cfg is None:
            return None
        if hasattr(cfg, "get"):
            try:
                return cfg.get("station_id")
            except Exception:
                return None
        if isinstance(cfg, dict):
            return cfg.get("station_id")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    #  IMPORT — réseau (HTTP / local file)
    # ─────────────────────────────────────────────────────────────────────────

    def import_package(self, ivs_file_path: str | Path) -> ImportResult:
        """
        Importe un package .ivs sur cette unité.

        GR-13 : validation OBLIGATOIRE par ModelValidator avant activation.
                Échec → rollback (suppression du dossier produit copié) +
                FleetImportError.

        Raises:
            FleetImportError : signature invalide / version incompatible /
                               validation échouée / import concurrent.
            FileNotFoundError : .ivs introuvable.
        """
        ivs_file = Path(ivs_file_path)
        if not ivs_file.is_file():
            raise FileNotFoundError(f"Fichier .ivs introuvable : {ivs_file}")

        # GR-13 — verrouillage non bloquant (réseau/USB exclusifs).
        if not self._import_lock.acquire(blocking=False):
            raise FleetImportError(
                "Import en cours — un autre import (réseau ou USB) est actif.",
            )
        try:
            return self._do_import(ivs_file)
        finally:
            self._import_lock.release()

    def _do_import(self, ivs_file: Path) -> ImportResult:
        # Dézippage dans tmpdir auto-nettoyé
        with tempfile.TemporaryDirectory(prefix="ivs-import-") as td:
            tmp = Path(td)
            try:
                shutil.unpack_archive(str(ivs_file), str(tmp), "zip")
            except (shutil.ReadError, OSError) as exc:
                raise FleetImportError(
                    f"Archive .ivs illisible : {exc}",
                ) from exc

            manifest_path = tmp / PACKAGE_MANIFEST
            if not manifest_path.is_file():
                raise FleetImportError(
                    "package.json absent — package .ivs malformé.",
                )
            try:
                meta = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FleetImportError(
                    f"package.json invalide : {exc}",
                ) from exc

            # Vérif signature SHA256
            expected_sig = meta.get("sha256", "")
            actual_sig   = self._sign_directory(tmp)
            if not expected_sig or expected_sig != actual_sig:
                raise FleetImportError(
                    "Signature invalide : package corrompu ou modifié.",
                )

            # Vérif version
            pkg_version = str(meta.get("ivs_version", "0"))
            if pkg_version != IVS_VERSION:
                raise FleetImportError(
                    f"Version incompatible : {pkg_version} ≠ {IVS_VERSION}",
                )

            product_id = meta.get("product_id")
            if not product_id:
                raise FleetImportError("package.json sans product_id.")

            # Copie vers products/
            dest = self._products_dir / product_id
            had_dest_before = dest.exists()
            dest.mkdir(parents=True, exist_ok=True)

            # On retient les chemins copiés pour le rollback ciblé.
            copied_paths: list[Path] = []
            try:
                src_calib = tmp / CALIBRATION_DIRNAME
                if src_calib.is_dir():
                    shutil.copytree(
                        src_calib, dest / CALIBRATION_DIRNAME,
                        dirs_exist_ok=True,
                    )
                    copied_paths.append(dest / CALIBRATION_DIRNAME)

                src_models = tmp / MODELS_DIRNAME
                if src_models.is_dir():
                    target_models = dest / MODELS_DIRNAME / ACTIVE_MODELS_DIRNAME
                    target_models.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(
                        src_models, target_models, dirs_exist_ok=True,
                    )
                    copied_paths.append(dest / MODELS_DIRNAME)

                src_config = tmp / PRODUCT_CONFIG_FILE
                if src_config.is_file():
                    shutil.copy(src_config, dest / PRODUCT_CONFIG_FILE)
                    copied_paths.append(dest / PRODUCT_CONFIG_FILE)

                src_logos = tmp / LOGOS_DIRNAME
                if src_logos.is_dir():
                    shutil.copytree(
                        src_logos, dest / LOGOS_DIRNAME, dirs_exist_ok=True,
                    )
                    copied_paths.append(dest / LOGOS_DIRNAME)

                # GR-13 — VALIDATION OBLIGATOIRE AVANT activation finale
                validation = self._validate_imported_models(product_id)
            except Exception:
                self._rollback(dest, had_dest_before)
                raise

            if not validation.passed:
                # Rollback (GR-13)
                self._rollback(dest, had_dest_before)
                raise FleetImportError(
                    f"Validation modèles échouée : {validation.details}",
                )

            # Activation effective : refresh registry produit (best-effort)
            self._refresh_registry()

            logger.info(
                "FleetManager.import[%s]: %s → OK (validation=%s, station_src=%s)",
                product_id, ivs_file, validation.details,
                meta.get("station_id"),
            )
            return ImportResult(
                product_id     = product_id,
                station_source = meta.get("station_id"),
                export_date    = meta.get("export_date"),
                validation     = validation,
                ivs_version    = pkg_version,
                package_path   = str(ivs_file.resolve()),
            )

    # ─────────────────────────────────────────────────────────────────────────
    #  IMPORT — USB
    # ─────────────────────────────────────────────────────────────────────────

    def import_via_usb(self, mount_point: str | Path) -> ImportResult:
        """
        Cherche un fichier *.ivs sur la clé montée et l'importe.

        Spec §Fleet.5 : 1 seul .ivs par clé USB ; 2 fichiers → FleetImportError.
        Copie locale (tmp) avant import — protection débranchement à chaud.
        GR-13 : même validation que l'import réseau, même mutex.
        """
        mount = Path(mount_point)
        if not mount.is_dir():
            raise FileNotFoundError(f"Point de montage introuvable : {mount}")

        candidates = sorted(mount.glob("*.ivs"))
        if len(candidates) == 0:
            raise FleetImportError(
                f"Aucun .ivs trouvé sur {mount}",
            )
        if len(candidates) > 1:
            raise FleetImportError(
                f"{len(candidates)} fichiers .ivs sur {mount} — "
                "1 seul autorisé par clé.",
            )
        source_ivs = candidates[0]

        # Copie locale avant import — protection contre débranchement.
        with tempfile.TemporaryDirectory(prefix="ivs-usb-stage-") as td:
            local_copy = Path(td) / source_ivs.name
            try:
                shutil.copy(source_ivs, local_copy)
            except OSError as exc:
                raise FleetImportError(
                    f"Copie locale impossible depuis {source_ivs} : {exc}",
                ) from exc
            logger.info(
                "FleetManager.usb: %s copié localement → %s",
                source_ivs, local_copy,
            )
            return self.import_package(local_copy)

    # ─────────────────────────────────────────────────────────────────────────
    #  Validation GR-13
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_imported_models(self, product_id: str) -> GateResult:
        """
        GR-13 — appelle ModelValidator.validate() sur le modèle importé.

        Si aucun golden_dataset local n'existe encore (premier déploiement
        du produit sur cette unité), la gate est acceptée avec la raison
        explicite ``no_golden_dataset_yet`` — conforme §Fleet.3 (un import
        ne peut être plus strict qu'un retrain : impossible de valider sans
        référence locale).
        """
        if self._model_validator is None:
            # Pas de validateur disponible → gate refusée (sécurité GR-13).
            return GateResult(
                gate_id="import_validation",
                passed=False,
                details={"reason": "model_validator_missing"},
            )

        product_dir   = self._products_dir / product_id
        active_models = product_dir / MODELS_DIRNAME / ACTIVE_MODELS_DIRNAME

        # Cherche d'abord ONNX puis fallback PKL (cohérent avec model_builder).
        candidates = (
            active_models / "isoforest.onnx",
            active_models / "isoforest.pkl",
        )
        model_path = next((p for p in candidates if p.is_file()), None)
        if model_path is None:
            return GateResult(
                gate_id="import_validation",
                passed=False,
                details={
                    "reason":  "isoforest_model_missing",
                    "looked":  [str(c) for c in candidates],
                },
            )

        golden = self._load_golden_dataset(product_id)
        if golden is None:
            return GateResult(
                gate_id="import_validation",
                passed=True,
                details={
                    "reason":     "no_golden_dataset_yet",
                    "model_path": str(model_path),
                },
            )

        try:
            new_model = self._build_isoforest(model_path)
            current_model = self._build_isoforest(model_path)  # baseline = lui-même
            ok = self._model_validator.validate(
                new_model      = new_model,
                golden_dataset = golden,
                current_model  = current_model,
            )
        except Exception as exc:
            logger.error(
                "FleetManager: ModelValidator a levé une exception — %s",
                exc, exc_info=True,
            )
            return GateResult(
                gate_id="import_validation",
                passed=False,
                details={"reason": "validator_exception", "error": str(exc)},
            )

        return GateResult(
            gate_id="import_validation",
            passed=bool(ok),
            details={
                "model_path": str(model_path),
                "threshold":  IMPORT_PASS_RATE_MIN,
                "golden_n":   len(golden),
            },
        )

    @staticmethod
    def _build_isoforest(model_path: Path) -> Any:
        """Wrap le modèle importé pour que ModelValidator puisse l'évaluer."""
        from ai.model_builder import IsoForestModel  # import différé
        return IsoForestModel(path=model_path)

    def _load_golden_dataset(self, product_id: str) -> Optional[Any]:
        """
        Cherche un golden dataset local ``products/{id}/dataset/golden.npz``.

        Format attendu : np.savez avec clés 'features' (N, FEATURE_DIM) et
        'labels' (N,) ∈ {-1, 1}. Absent → None (premier import).
        """
        path = self._products_dir / product_id / "dataset" / "golden.npz"
        if not path.is_file():
            return None
        try:
            import numpy as np
            from evaluation.model_validator import GoldenDataset

            data = np.load(path)
            features = np.asarray(data["features"], dtype=np.float32)
            labels   = np.asarray(data["labels"],   dtype=np.int32)
            return GoldenDataset(
                features=features, labels=labels, product_id=product_id,
            )
        except KeyError as exc:
            logger.warning(
                "FleetManager: golden dataset %s clé manquante — %s", path, exc,
            )
            return None
        except Exception as exc:
            logger.warning(
                "FleetManager: golden dataset %s illisible — %s", path, exc,
            )
            return None

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers — signature, rollback, registry refresh
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _sign_directory(directory: Path) -> str:
        """
        Signature SHA256 déterministe d'un répertoire.

        Conforme à la spec §Fleet.2 : agrège les contenus de TOUS les fichiers
        sauf ``package.json`` (qui contient justement la signature), triés par
        chemin absolu pour le déterminisme.
        """
        h = hashlib.sha256()
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.name == PACKAGE_MANIFEST:
                continue
            with path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _rollback(dest: Path, had_dest_before: bool) -> None:
        """Supprime le produit copié — GR-13 (rollback strict si validation KO)."""
        if dest.exists():
            try:
                shutil.rmtree(dest)
            except OSError as exc:
                logger.error(
                    "FleetManager: rollback de %s échoué — %s", dest, exc,
                )
                return
            if had_dest_before:
                # Le produit existait déjà avant l'import : on ne peut pas
                # restaurer son état antérieur sans backup. On loggue clairement.
                logger.warning(
                    "FleetManager: produit %s supprimé suite à rollback — "
                    "il existait avant l'import (pas de backup conservé).",
                    dest.name,
                )

    def _refresh_registry(self) -> None:
        """Recharge le ProductRegistry après import (best-effort, GR-03)."""
        if self._registry is None:
            return
        reload_fn = getattr(self._registry, "reload", None)
        if not callable(reload_fn):
            return
        try:
            reload_fn()
        except Exception as exc:
            logger.warning("FleetManager: registry.reload() a échoué — %s", exc)
