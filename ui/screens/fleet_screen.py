"""
FleetScreen — onglet UI Fleet (export / import .ivs)

Spec : IVS_FINAL_SPEC_v7_COMPLETE.md §Fleet.4 / §Fleet.5
GR-03 : aucun appel pipeline direct — toute opération passe par
        FleetManager (instance injectée) et ProductRegistry.
GR-13 : import réseau ⊕ USB jamais simultanés. Le flag local `_busy`
        désactive le bouton concurrent côté UI ; FleetManager.import_*()
        applique de toute façon le mutex côté core.

Trois sections :
    ① Exporter — combo produit, bouton "Exporter .ivs", barre progression.
    ② Importer — boutons "Import réseau" et "Import USB" (FileDialog).
    ③ Clé USB — auto-détection via UsbMonitor, preview du package détecté,
                bouton "Importer maintenant".

L'écran reste fonctionnel même sans UsbMonitor (passer usb_monitor=None) :
la section "Clé USB" affiche alors un état "indisponible".
"""
from __future__ import annotations

import json
import logging
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Workers (QThread) — évitent de figer l'UI pendant export/import
# ─────────────────────────────────────────────────────────────────────────────

class _ExportWorker(QThread):
    """Exécute FleetManager.export_package en arrière-plan."""

    finished_ok = pyqtSignal(str)         # path
    failed      = pyqtSignal(str)         # message d'erreur

    def __init__(
        self,
        fleet_manager : Any,
        product_id    : str,
        output_path   : str,
        parent        : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._fleet       = fleet_manager
        self._product_id  = product_id
        self._output_path = output_path

    def run(self) -> None:
        try:
            path = self._fleet.export_package(
                product_id=self._product_id,
                output_path=self._output_path,
            )
        except Exception as exc:
            logger.error(
                "FleetScreen.export[%s] échoué — %s",
                self._product_id, exc, exc_info=True,
            )
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(str(path))


class _ImportWorker(QThread):
    """Exécute FleetManager.import_package ou import_via_usb en arrière-plan."""

    finished_ok = pyqtSignal(object)      # ImportResult
    failed      = pyqtSignal(str)

    def __init__(
        self,
        fleet_manager : Any,
        target        : str,
        mode          : str,              # "file" | "usb"
        parent        : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._fleet  = fleet_manager
        self._target = target
        self._mode   = mode

    def run(self) -> None:
        try:
            if self._mode == "usb":
                result = self._fleet.import_via_usb(self._target)
            else:
                result = self._fleet.import_package(self._target)
        except Exception as exc:
            logger.error(
                "FleetScreen.import[%s] %s échoué — %s",
                self._mode, self._target, exc, exc_info=True,
            )
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(result)


# ─────────────────────────────────────────────────────────────────────────────
#  FleetScreen
# ─────────────────────────────────────────────────────────────────────────────

class FleetScreen(QWidget):
    """
    Écran Fleet — export et import de packages .ivs.

    Construction :
        FleetScreen(
            fleet_manager    = FleetManager(...),
            product_registry = controller.product_registry,
            usb_monitor      = UsbMonitor(...),     # ou None
        )
    """

    # Signal externe pratique (ex. notifier MainWindow → status bar).
    import_finished = pyqtSignal(object)          # ImportResult

    def __init__(
        self,
        fleet_manager    : Any,
        product_registry : Any                = None,
        usb_monitor      : Any                = None,
        controller       : Any                = None,
        ui_bridge        : Any                = None,
        parent           : Optional[QWidget]  = None,
    ) -> None:
        super().__init__(parent)
        self._fleet      = fleet_manager
        self._registry   = product_registry
        self._usb        = usb_monitor
        self._controller = controller
        self._bridge     = ui_bridge

        # GR-13 : flag local "busy" — bloque le bouton concurrent côté UI.
        self._busy: Optional[str] = None    # None | "network" | "usb" | "export"

        # Détection USB courante (mise à jour par UsbMonitor)
        self._detected_ivs   : Optional[Path] = None
        self._detected_mount : Optional[str]  = None

        # Workers actifs
        self._export_worker : Optional[_ExportWorker] = None
        self._import_worker : Optional[_ImportWorker] = None

        self._build_ui()
        self._connect_usb_monitor()
        self._refresh_products()
        self._refresh_usb_section()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        # GR-13 banner (caché par défaut)
        self._lock_banner = self._build_lock_banner()
        root.addWidget(self._lock_banner)

        root.addWidget(self._build_export_section())
        root.addWidget(self._build_import_section())
        root.addWidget(self._build_usb_section(), 1)

        # Notification log
        self._notif = QLabel("")
        self._notif.setWordWrap(True)
        self._notif.setStyleSheet(
            "padding:6px; border-radius:4px; "
            "background:#1a1a1a; color:#ddd; font-family: monospace;"
        )
        self._notif.setMinimumHeight(40)
        root.addWidget(self._notif)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("FleetHeader")
        header.setStyleSheet(
            "QFrame#FleetHeader { background:#2C3E50; border-radius:4px; }"
            "QLabel { color:white; font-weight:bold; padding:6px; }"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(8, 4, 8, 4)
        title = QLabel("Fleet — Déploiement multi-unités (.ivs)")
        h.addWidget(title)
        h.addStretch(1)
        self._station_lbl = QLabel("Station : —")
        h.addWidget(self._station_lbl)

        # Affiche station_id depuis config (si disponible via FleetManager)
        try:
            cfg = getattr(self._fleet, "_config", None)
            if cfg is not None:
                getter = cfg.get if hasattr(cfg, "get") else None
                if callable(getter):
                    sid = getter("station_id")
                    if sid:
                        self._station_lbl.setText(f"Station : {sid}")
        except Exception:
            pass
        return header

    def _build_lock_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("FleetLockBanner")
        banner.setStyleSheet(
            "QFrame#FleetLockBanner { background:#C0392B; border-radius:4px; }"
            "QLabel { color:white; font-weight:bold; padding:6px; }"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(10, 4, 10, 4)
        self._lock_lbl = QLabel("🔒 Import en cours — attendre la fin.")
        self._lock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._lock_lbl)
        banner.hide()
        return banner

    # ── Section Export ────────────────────────────────────────────────────────

    def _build_export_section(self) -> QWidget:
        box = QGroupBox("① Exporter un produit")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Produit :"))
        self._product_combo = QComboBox()
        self._product_combo.setMinimumWidth(220)
        row.addWidget(self._product_combo)

        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setToolTip("Rafraîchir la liste des produits")
        self._refresh_btn.clicked.connect(self._refresh_products)
        row.addWidget(self._refresh_btn)

        row.addStretch(1)
        self._export_btn = QPushButton("📦 Exporter .ivs…")
        self._export_btn.setDefault(True)
        self._export_btn.clicked.connect(self._on_export_clicked)
        row.addWidget(self._export_btn)
        layout.addLayout(row)

        self._export_progress = QProgressBar()
        self._export_progress.setRange(0, 0)        # busy mode
        self._export_progress.hide()
        layout.addWidget(self._export_progress)

        return box

    # ── Section Import (réseau / fichier) ─────────────────────────────────────

    def _build_import_section(self) -> QWidget:
        box = QGroupBox("② Importer un package")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(8, 14, 8, 8)

        self._network_btn = QPushButton("🌐 Import réseau / fichier .ivs…")
        self._network_btn.setToolTip(
            "Sélectionner un fichier .ivs téléchargé depuis une autre unité.",
        )
        self._network_btn.clicked.connect(self._on_network_import_clicked)
        layout.addWidget(self._network_btn)

        self._usb_btn = QPushButton("💾 Import USB…")
        self._usb_btn.setToolTip(
            "Importer depuis un point de montage USB (auto-détection ou manuel).",
        )
        self._usb_btn.clicked.connect(self._on_usb_manual_import_clicked)
        layout.addWidget(self._usb_btn)

        layout.addStretch(1)
        self._import_progress = QProgressBar()
        self._import_progress.setRange(0, 0)
        self._import_progress.hide()
        self._import_progress.setMaximumWidth(220)
        layout.addWidget(self._import_progress)

        return box

    # ── Section Clé USB ──────────────────────────────────────────────────────

    def _build_usb_section(self) -> QWidget:
        box = QGroupBox("③ Clé USB — détection automatique")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(6)

        self._usb_status = QLabel("Statut : initialisation…")
        self._usb_status.setStyleSheet("color:#aaa;")
        layout.addWidget(self._usb_status)

        # Preview package détecté
        self._preview_form = QFormLayout()
        self._preview_form.setHorizontalSpacing(16)
        self._preview_pid    = QLabel("—")
        self._preview_date   = QLabel("—")
        self._preview_source = QLabel("—")
        self._preview_ver    = QLabel("—")
        self._preview_sig    = QLabel("—")
        for lbl in (self._preview_pid, self._preview_date,
                    self._preview_source, self._preview_ver, self._preview_sig):
            lbl.setStyleSheet("color:#ddd; font-family: monospace;")
        self._preview_form.addRow("product_id :",     self._preview_pid)
        self._preview_form.addRow("export_date :",    self._preview_date)
        self._preview_form.addRow("station_source :", self._preview_source)
        self._preview_form.addRow("ivs_version :",    self._preview_ver)
        self._preview_form.addRow("sha256 :",         self._preview_sig)
        layout.addLayout(self._preview_form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._usb_import_btn = QPushButton("📥 Importer maintenant")
        self._usb_import_btn.clicked.connect(self._on_usb_auto_import_clicked)
        self._usb_import_btn.setEnabled(False)
        actions.addWidget(self._usb_import_btn)
        layout.addLayout(actions)

        return box

    # ── ProductRegistry ──────────────────────────────────────────────────────

    def _refresh_products(self) -> None:
        self._product_combo.clear()
        ids: tuple[str, ...] = ()
        if self._registry is not None:
            try:
                self._registry.reload()
            except Exception as exc:
                logger.warning(
                    "FleetScreen: registry.reload() échoué — %s", exc,
                )
            try:
                ids = tuple(self._registry.product_ids)
            except Exception:
                ids = ()
        if not ids:
            # Fallback : scan direct du dossier products/
            products_dir = getattr(self._fleet, "_products_dir", None)
            if products_dir:
                try:
                    ids = tuple(sorted(
                        p.name for p in Path(products_dir).iterdir()
                        if p.is_dir() and (p / "config.json").is_file()
                    ))
                except OSError:
                    ids = ()
        self._product_combo.addItems(list(ids))
        self._product_combo.setEnabled(bool(ids) and self._busy is None)
        self._export_btn.setEnabled(bool(ids) and self._busy is None)

    # ── UsbMonitor ───────────────────────────────────────────────────────────

    def _connect_usb_monitor(self) -> None:
        if self._usb is None:
            self._usb_status.setText(
                "Statut : indisponible (UsbMonitor non fourni)."
            )
            return
        try:
            self._usb.usb_ivs_found.connect(self._on_usb_ivs_found)
            self._usb.usb_unmounted.connect(self._on_usb_unmounted)
            self._usb.usb_mounted.connect(self._on_usb_mounted)
        except Exception as exc:
            logger.warning(
                "FleetScreen: connexion UsbMonitor échouée — %s", exc,
            )

    def _on_usb_ivs_found(self, ivs_path: str, mount_point: str) -> None:
        self._detected_ivs   = Path(ivs_path)
        self._detected_mount = mount_point
        self._refresh_usb_section()
        self._notify(
            f"Clé détectée : {Path(ivs_path).name} (mount={mount_point})",
            level="info",
        )

    def _on_usb_mounted(self, mount_point: str) -> None:
        # Affiche au moins le mount, même sans .ivs.
        if self._detected_ivs is None:
            self._usb_status.setText(
                f"Statut : clé détectée → {mount_point} "
                "(aucun .ivs à la racine)."
            )

    def _on_usb_unmounted(self, mount_point: str) -> None:
        if self._detected_mount == mount_point:
            self._detected_ivs   = None
            self._detected_mount = None
            self._refresh_usb_section()
            self._notify(f"Clé retirée : {mount_point}", level="info")

    def _refresh_usb_section(self) -> None:
        if self._usb is None:
            self._usb_status.setText(
                "Statut : indisponible (UsbMonitor non fourni)."
            )
            self._usb_import_btn.setEnabled(False)
            self._reset_preview()
            return

        if self._detected_ivs is None:
            self._usb_status.setText(
                "Statut : aucune clé .ivs détectée — "
                f"surveille {len(self._usb.mount_roots)} racine(s)."
            )
            self._usb_import_btn.setEnabled(False)
            self._reset_preview()
            return

        # Pré-remplit le preview en lisant package.json depuis le ZIP.
        self._usb_status.setText(
            f"Statut : prêt → {self._detected_ivs.name} "
            f"(mount={self._detected_mount})"
        )
        self._fill_preview_from_ivs(self._detected_ivs)
        self._usb_import_btn.setEnabled(self._busy is None)

    def _fill_preview_from_ivs(self, ivs_path: Path) -> None:
        meta = self._read_manifest(ivs_path)
        if meta is None:
            self._reset_preview(error="package.json illisible")
            return
        sig = str(meta.get("sha256", "")) or "—"
        if len(sig) > 18:
            sig = sig[:14] + "…"
        self._preview_pid.setText(str(meta.get("product_id",  "—")))
        self._preview_date.setText(str(meta.get("export_date", "—")))
        self._preview_source.setText(str(meta.get("station_id", "—")))
        self._preview_ver.setText(str(meta.get("ivs_version",  "—")))
        self._preview_sig.setText(sig)

    def _reset_preview(self, error: str = "") -> None:
        for lbl in (self._preview_pid, self._preview_date,
                    self._preview_source, self._preview_ver, self._preview_sig):
            lbl.setText("—" if not error else f"⚠ {error}")

    @staticmethod
    def _read_manifest(ivs_path: Path) -> Optional[dict[str, Any]]:
        try:
            with zipfile.ZipFile(ivs_path) as zf:
                with zf.open("package.json") as fh:
                    return json.loads(fh.read().decode("utf-8"))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "FleetScreen: manifest %s illisible — %s", ivs_path, exc,
            )
            return None

    # ── Actions Export ────────────────────────────────────────────────────────

    def _on_export_clicked(self) -> None:
        if self._busy is not None:
            return
        product_id = self._product_combo.currentText().strip()
        if not product_id:
            QMessageBox.information(
                self, "Export",
                "Aucun produit sélectionné.",
            )
            return
        default_name = f"{product_id}_export_{int(time.time())}.ivs"
        target_str, _ = QFileDialog.getSaveFileName(
            self, "Exporter le package .ivs",
            default_name, "Packages IVS (*.ivs)",
        )
        if not target_str:
            return
        if not target_str.lower().endswith(".ivs"):
            target_str += ".ivs"

        self._set_busy("export", "Export en cours…")
        self._export_progress.show()

        worker = _ExportWorker(
            fleet_manager=self._fleet,
            product_id=product_id,
            output_path=target_str,
            parent=self,
        )
        worker.finished_ok.connect(self._on_export_ok)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(worker.deleteLater)
        self._export_worker = worker
        worker.start()

    def _on_export_ok(self, path: str) -> None:
        self._export_progress.hide()
        self._set_busy(None)
        self._notify(f"✅ Export OK → {path}", level="info")
        QMessageBox.information(
            self, "Export OK", f"Package créé :\n{path}",
        )

    def _on_export_failed(self, message: str) -> None:
        self._export_progress.hide()
        self._set_busy(None)
        self._notify(f"❌ Export échoué : {message}", level="error")
        QMessageBox.critical(self, "Export échoué", message)

    # ── Actions Import — réseau / fichier ─────────────────────────────────────

    def _on_network_import_clicked(self) -> None:
        if self._busy == "usb":
            self._block_concurrent_alert()
            return
        if self._busy is not None:
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Importer un package .ivs", "",
            "Packages IVS (*.ivs);;Tous les fichiers (*)",
        )
        if not path_str:
            return
        self._launch_import(path_str, mode="file", busy_tag="network")

    # ── Actions Import — USB (auto / manuel) ──────────────────────────────────

    def _on_usb_auto_import_clicked(self) -> None:
        if self._busy == "network":
            self._block_concurrent_alert()
            return
        if self._busy is not None:
            return
        if self._detected_ivs is None or self._detected_mount is None:
            QMessageBox.information(
                self, "Import USB",
                "Aucune clé USB avec .ivs détectée.",
            )
            return
        self._launch_import(
            self._detected_mount, mode="usb", busy_tag="usb",
        )

    def _on_usb_manual_import_clicked(self) -> None:
        if self._busy == "network":
            self._block_concurrent_alert()
            return
        if self._busy is not None:
            return
        # Si une clé a été auto-détectée, propose-la directement.
        if self._detected_mount is not None:
            mount = self._detected_mount
        else:
            mount = QFileDialog.getExistingDirectory(
                self, "Choisir le point de montage USB",
                "/media" if Path("/media").is_dir() else "",
            )
            if not mount:
                return
        self._launch_import(mount, mode="usb", busy_tag="usb")

    # ── Lance un worker d'import ──────────────────────────────────────────────

    def _launch_import(self, target: str, mode: str, busy_tag: str) -> None:
        self._set_busy(
            busy_tag,
            f"Import {busy_tag} en cours — l'autre canal est temporairement bloqué.",
        )
        self._import_progress.show()

        worker = _ImportWorker(
            fleet_manager=self._fleet,
            target=target,
            mode=mode,
            parent=self,
        )
        worker.finished_ok.connect(self._on_import_ok)
        worker.failed.connect(self._on_import_failed)
        worker.finished.connect(worker.deleteLater)
        self._import_worker = worker
        worker.start()

    def _on_import_ok(self, result: Any) -> None:
        self._import_progress.hide()
        self._set_busy(None)
        details = self._format_result(result)
        self._notify(f"✅ Import OK\n{details}", level="info")
        QMessageBox.information(
            self, "Import OK",
            f"Produit '{getattr(result, 'product_id', '?')}' importé.\n\n{details}",
        )
        self._refresh_products()
        self.import_finished.emit(result)

    def _on_import_failed(self, message: str) -> None:
        self._import_progress.hide()
        self._set_busy(None)
        self._notify(f"❌ Import échoué : {message}", level="error")
        QMessageBox.critical(self, "Import échoué", message)

    @staticmethod
    def _format_result(result: Any) -> str:
        validation = getattr(result, "validation", None)
        gate_id    = getattr(validation, "gate_id", "—")
        passed     = getattr(validation, "passed",  False)
        details    = getattr(validation, "details", {}) or {}
        return (
            f"product_id    : {getattr(result, 'product_id', '?')}\n"
            f"station_source: {getattr(result, 'station_source', '—')}\n"
            f"export_date   : {getattr(result, 'export_date', '—')}\n"
            f"validation    : {gate_id} → {'PASS' if passed else 'FAIL'}\n"
            f"details       : {details}"
        )

    # ── GR-13 : verrouillage UI réseau ⊕ USB ──────────────────────────────────

    def _set_busy(self, tag: Optional[str], banner_text: str = "") -> None:
        self._busy = tag
        running = tag is not None
        # Désactive les boutons concernés
        self._network_btn.setEnabled(not running)
        self._usb_btn.setEnabled(not running)
        self._usb_import_btn.setEnabled(
            not running and self._detected_ivs is not None,
        )
        self._export_btn.setEnabled(
            not running and self._product_combo.count() > 0,
        )
        self._product_combo.setEnabled(
            not running and self._product_combo.count() > 0,
        )
        self._refresh_btn.setEnabled(not running)
        if running and banner_text:
            self._lock_lbl.setText(f"🔒 {banner_text}")
            self._lock_banner.show()
        else:
            self._lock_banner.hide()

    def _block_concurrent_alert(self) -> None:
        QMessageBox.warning(
            self, "Import en cours",
            "Un import est déjà en cours sur l'autre canal "
            "(GR-13 : réseau ⊕ USB). Attendre la fin avant de réessayer.",
        )

    # ── Notifications ─────────────────────────────────────────────────────────

    def _notify(self, message: str, level: str = "info") -> None:
        color = {"info": "#2ECC71", "warn": "#F1C40F", "error": "#E74C3C"}.get(
            level, "#DDDDDD",
        )
        self._notif.setText(message)
        self._notif.setStyleSheet(
            f"padding:6px; border-radius:4px; background:#1a1a1a; "
            f"color:{color}; font-family: monospace;"
        )

    # ── Fermeture propre ──────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        for w in (self._export_worker, self._import_worker):
            if w is not None and w.isRunning():
                # Les workers sont des QThread non interruptibles ici ;
                # on attend leur sortie naturelle (ils ne touchent qu'à
                # FleetManager qui termine ses propres opérations).
                w.wait(2000)
        super().closeEvent(event)

    # ── API tests ─────────────────────────────────────────────────────────────

    @property
    def is_busy(self) -> bool:
        return self._busy is not None

    @property
    def busy_tag(self) -> Optional[str]:
        return self._busy

    @property
    def detected_ivs(self) -> Optional[Path]:
        return self._detected_ivs
