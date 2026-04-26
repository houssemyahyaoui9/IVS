"""
SettingsTab v7.0 — 9 sections de configuration

Sections (sous-onglets QTabWidget) :
    Caméra · Pipeline · Observers · Learning · GPIO ·
    Web · Monitoring · Calibration · Comptes

GR-03 : aucun accès direct au pipeline — lecture/écriture YAML uniquement,
        et lecture d'état FSM via SystemController.
GR-06 : la config en mémoire (ConfigManager singleton) n'est jamais rechargée
        à chaud dans la boucle d'inspection ; la sauvegarde sur disque prend
        effet au prochain démarrage. Un toast le rappelle après "Sauvegarder".
GR-12 : SystemState.RUNNING → tous les widgets éditables sont désactivés
        et un bandeau rouge l'indique à l'opérateur.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import SystemState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Petit helper : bandeau de verrouillage GR-12
# ─────────────────────────────────────────────────────────────────────────────

class _LockBanner(QFrame):
    """Bandeau rouge visible quand l'inspection est RUNNING (GR-12)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsLockBanner")
        self.setStyleSheet(
            "QFrame#SettingsLockBanner { background-color:#C0392B; }"
            "QLabel { color:white; font-weight:bold; padding:6px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        lbl = QLabel("🔒 INSPECTION ACTIVE — paramètres en lecture seule (GR-12)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        self.hide()


# ─────────────────────────────────────────────────────────────────────────────
#  SettingsTab
# ─────────────────────────────────────────────────────────────────────────────

class SettingsTab(QWidget):
    """
    Onglet Paramètres — édition de config.yaml en 9 sections.

    Construction :
        SettingsTab(
            controller  = system_controller,
            ui_bridge   = ui_bridge,
            config      = ConfigManager | dict | None,
            config_path = "config/config.yaml",
        )
    """

    config_saved = pyqtSignal(dict)   # émis après sauvegarde YAML

    SECTIONS = (
        "Caméra", "Pipeline", "Observers", "Learning", "GPIO",
        "Web", "Monitoring", "Calibration", "Comptes",
    )

    def __init__(
        self,
        controller  : Any                 = None,
        ui_bridge   : Any                 = None,
        config      : Any                 = None,
        config_path : str | Path          = "config/config.yaml",
        parent      : Optional[QWidget]   = None,
    ) -> None:
        super().__init__(parent)
        self._controller  = controller
        self._bridge      = ui_bridge
        self._config      = config
        self._config_path = Path(config_path)
        self._locked      = False

        # Données YAML lues sur disque (pour préserver les clés inconnues
        # non éditées par l'UI, GR-06).
        self._yaml_data: dict[str, Any] = {}
        self._reload_yaml()

        # Widgets éditables groupés par chemin pointé "section.key"
        self._editors: dict[str, QWidget] = {}

        self._build_ui()
        self._populate_from_yaml()

        if self._bridge is not None and hasattr(self._bridge, "state_changed"):
            self._bridge.state_changed.connect(self._on_state_changed)
        if self._controller is not None:
            try:
                self._sync_lock(self._controller.get_state())
            except Exception:
                pass

    # ── Layout principal ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._lock_banner = _LockBanner(self)
        root.addWidget(self._lock_banner)

        self._sections = QTabWidget(self)
        self._sections.setTabPosition(QTabWidget.TabPosition.North)  # GR-V9-8
        root.addWidget(self._sections, 1)

        self._build_camera_section()
        self._build_pipeline_section()
        self._build_observers_section()
        self._build_learning_section()
        self._build_gpio_section()
        self._build_web_section()
        self._build_monitoring_section()
        self._build_calibration_section()
        self._build_accounts_section()

        # Barre d'actions
        actions = QHBoxLayout()
        actions.addStretch(1)
        self._reload_btn = QPushButton("⟳ Recharger YAML")
        self._reload_btn.clicked.connect(self._on_reload_clicked)
        actions.addWidget(self._reload_btn)

        self._save_btn = QPushButton("💾 Sauvegarder")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save_clicked)
        actions.addWidget(self._save_btn)
        root.addLayout(actions)

        self._hint = QLabel(
            "ℹ Les modifications enregistrées prennent effet au prochain "
            "démarrage du système (GR-06)."
        )
        self._hint.setStyleSheet("color:#888; padding:4px;")
        root.addWidget(self._hint)

    # ── Sections (chacune = QWidget + QFormLayout) ────────────────────────────

    def _new_section(self, title: str) -> QFormLayout:
        page  = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(6)
        group = QGroupBox(title, page)
        form  = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        outer.addWidget(group, 1)
        outer.addStretch(1)
        self._sections.addTab(page, title)
        return form

    def _add_str(self, form: QFormLayout, label: str, key: str,
                 placeholder: str = "") -> QLineEdit:
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        form.addRow(label, w)
        self._editors[key] = w
        return w

    def _add_int(self, form: QFormLayout, label: str, key: str,
                 lo: int = 0, hi: int = 1_000_000, step: int = 1,
                 suffix: str = "") -> QSpinBox:
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        if suffix:
            w.setSuffix(f" {suffix}")
        form.addRow(label, w)
        self._editors[key] = w
        return w

    def _add_float(self, form: QFormLayout, label: str, key: str,
                   lo: float = 0.0, hi: float = 1_000_000.0,
                   step: float = 0.01, decimals: int = 3,
                   suffix: str = "") -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
        w.setSingleStep(step)
        if suffix:
            w.setSuffix(f" {suffix}")
        form.addRow(label, w)
        self._editors[key] = w
        return w

    def _add_bool(self, form: QFormLayout, label: str, key: str) -> QCheckBox:
        w = QCheckBox()
        form.addRow(label, w)
        self._editors[key] = w
        return w

    def _add_choice(self, form: QFormLayout, label: str, key: str,
                    choices: tuple[str, ...]) -> QComboBox:
        w = QComboBox()
        w.addItems(list(choices))
        form.addRow(label, w)
        self._editors[key] = w
        return w

    # ── Section 1 — Caméra ────────────────────────────────────────────────────

    def _build_camera_section(self) -> None:
        f = self._new_section("Caméra")
        self._add_choice(f, "Type", "camera.type",
                         ("fake", "uvc", "gige"))
        self._add_int(f, "Résolution largeur (px)",
                      "camera.resolution.width",   1, 16384, 1, "px")
        self._add_int(f, "Résolution hauteur (px)",
                      "camera.resolution.height",  1, 16384, 1, "px")
        self._add_int(f, "FPS", "camera.fps", 1, 240, 1, "fps")

    # ── Section 2 — Pipeline ──────────────────────────────────────────────────

    def _build_pipeline_section(self) -> None:
        f = self._new_section("Pipeline")
        self._add_int(f, "Durée max d'un cycle",
                      "pipeline.max_duration_ms", 100, 600_000, 100, "ms")
        self._add_int(f, "Timeout background (Full-Check)",
                      "pipeline.background_timeout_ms", 100, 600_000, 100, "ms")

    # ── Section 3 — Observers ─────────────────────────────────────────────────

    def _build_observers_section(self) -> None:
        f = self._new_section("Observers")
        # Tier engine — gates de confiance
        self._add_float(f, "CRITICAL min confiance",
                        "tier_engine.critical_confidence_min",
                        0.0, 1.0, 0.01, 2)
        self._add_float(f, "MAJOR min confiance",
                        "tier_engine.major_confidence_min",
                        0.0, 1.0, 0.01, 2)
        self._add_float(f, "MINOR min confiance",
                        "tier_engine.minor_confidence_min",
                        0.0, 1.0, 0.01, 2)
        self._add_float(f, "Seuil REVIEW",
                        "tier_engine.review_confidence_threshold",
                        0.0, 1.0, 0.01, 2)

        # YOLO
        self._add_str(f, "YOLO modèle",
                      "observers.yolo.model_path", "data/yolo/yolov8x.onnx")
        self._add_float(f, "YOLO confidence",
                        "observers.yolo.confidence_threshold",
                        0.0, 1.0, 0.01, 2)
        self._add_float(f, "YOLO IoU",
                        "observers.yolo.iou_threshold",
                        0.0, 1.0, 0.01, 2)
        self._add_choice(f, "YOLO device",
                         "observers.yolo.device", ("cpu", "hailo"))

        # SIFT
        self._add_int(f, "SIFT nfeatures",
                      "observers.sift.nfeatures", 100, 100_000, 100)
        self._add_float(f, "SIFT ratio test",
                        "observers.sift.ratio_test",
                        0.0, 1.0, 0.01, 2)

        # Color
        self._add_choice(f, "Color illuminant",
                         "observers.color.illuminant",
                         ("D50", "D55", "D65", "D75"))
        self._add_int(f, "Color k-clusters",
                      "observers.color.k_clusters", 1, 64, 1)

        # Surface
        self._add_float(f, "Surface texture weight",
                        "observers.surface.texture_weight",
                        0.0, 1.0, 0.01, 2)
        self._add_float(f, "Surface IsoForest weight",
                        "observers.surface.isoforest_weight",
                        0.0, 1.0, 0.01, 2)
        self._add_int(f, "Surface IsoForest n",
                      "observers.surface.isoforest_n", 50, 100_000, 50)
        self._add_int(f, "Surface seed",
                      "observers.surface.seed", 0, 2_147_483_647, 1)

    # ── Section 4 — Learning ──────────────────────────────────────────────────

    def _build_learning_section(self) -> None:
        f = self._new_section("Learning")
        self._add_int(f, "Trigger count",
                      "learning.trigger_count", 1, 100_000, 1)
        self._add_int(f, "Stability window",
                      "learning.stability_window", 1, 1000, 1)
        self._add_float(f, "Drift threshold",
                        "learning.drift_threshold",
                        0.0, 1.0, 0.01, 2)
        self._add_float(f, "Golden pass-rate min",
                        "learning.golden_pass_rate_min",
                        0.0, 1.0, 0.01, 2)
        self._add_float(f, "Operator weight",
                        "learning.operator_weight",
                        0.1, 100.0, 0.1, 1)

    # ── Section 5 — GPIO ──────────────────────────────────────────────────────

    def _build_gpio_section(self) -> None:
        f = self._new_section("GPIO")
        self._add_bool(f, "GPIO activé", "gpio.enabled")
        self._add_choice(f, "Backend", "gpio.backend", ("stub", "pi5"))
        self._add_int(f, "Pin Lampe VERTE (BCM)",
                      "gpio.pin_green", 0, 27, 1)
        self._add_int(f, "Pin Lampe ROUGE (BCM)",
                      "gpio.pin_red",   0, 27, 1)
        # pin_start / pin_stop peuvent être null → on saisit -1 pour désactiver
        self._add_int(f, "Pin Start (-1 = désactivé)",
                      "gpio.pin_start", -1, 27, 1)
        self._add_int(f, "Pin Stop  (-1 = désactivé)",
                      "gpio.pin_stop",  -1, 27, 1)

    # ── Section 6 — Web ───────────────────────────────────────────────────────

    def _build_web_section(self) -> None:
        f = self._new_section("Web")
        self._add_bool(f, "Web activé",      "web.enabled")
        self._add_int(f, "Port",             "web.port", 1, 65535, 1)
        self._add_bool(f, "Auth requise",    "web.auth_required")

    # ── Section 7 — Monitoring ────────────────────────────────────────────────

    def _build_monitoring_section(self) -> None:
        f = self._new_section("Monitoring")
        self._add_bool(f, "SystemMonitor activé",
                       "system_monitor.enabled")
        self._add_int(f, "Refresh",
                      "system_monitor.refresh_s", 1, 600, 1, "s")
        self._add_int(f, "Temp WARNING",
                      "system_monitor.temp_warn", 0, 200, 1, "°C")
        self._add_int(f, "Temp CRITICAL",
                      "system_monitor.temp_crit", 0, 200, 1, "°C")

        self._add_bool(f, "Watchdog pipeline",
                       "watchdog.enabled")
        self._add_int(f, "Watchdog timeout",
                      "watchdog.pipeline_timeout_s", 1, 3600, 1, "s")
        self._add_int(f, "Watchdog max recoveries",
                      "watchdog.max_recoveries", 0, 100, 1)

        self._add_bool(f, "NOK watcher",
                       "nok_watcher.enabled")
        self._add_int(f, "NOK alert threshold",
                      "nok_watcher.alert_threshold", 1, 1000, 1)
        self._add_int(f, "NOK stop threshold",
                      "nok_watcher.stop_threshold",  1, 1000, 1)

    # ── Section 8 — Calibration ───────────────────────────────────────────────

    def _build_calibration_section(self) -> None:
        f = self._new_section("Calibration")
        self._add_bool(f, "Luminosité activée",
                       "luminosity.enabled")
        self._add_float(f, "Luminosité WARNING",
                        "luminosity.warning_percent",
                        0.0, 100.0, 0.5, 1, "%")
        self._add_float(f, "Luminosité CRITICAL",
                        "luminosity.critical_percent",
                        0.0, 100.0, 0.5, 1, "%")

        self._add_bool(f, "Auto-zoom NOK",
                       "ui.auto_zoom_on_nok")
        self._add_float(f, "Niveau zoom NOK",
                        "ui.zoom_nok_level",
                        1.0, 16.0, 0.5, 1)
        self._add_str(f, "Snapshot dir",
                      "ui.snapshot_dir", "data/snapshots")

        # Scanner code-barres (auto-switch §35)
        self._add_bool(f, "Scanner activé",  "scanner.enabled")
        self._add_int(f, "Scanner intervalle",
                      "scanner.interval_ms", 50, 10_000, 50, "ms")
        self._add_float(f, "Scanner debounce",
                        "scanner.debounce_s",
                        0.0, 60.0, 0.1, 2, "s")

    # ── Section 9 — Comptes ───────────────────────────────────────────────────

    def _build_accounts_section(self) -> None:
        page  = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 12, 12, 12)

        info = QLabel(
            "Gestion des opérateurs / superviseurs.\n"
            "Lecture seule depuis core.auth — l'édition se fait via "
            "le module d'administration (à venir)."
        )
        info.setStyleSheet("color:#888; padding:4px;")
        outer.addWidget(info)

        self._accounts_table = QTableWidget(0, 3, page)
        self._accounts_table.setHorizontalHeaderLabels(
            ["Identifiant", "Rôle", "Actif"]
        )
        self._accounts_table.verticalHeader().setVisible(False)
        self._accounts_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch,
        )
        self._accounts_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers,
        )
        outer.addWidget(self._accounts_table, 1)

        # Bouton refresh
        refresh = QPushButton("⟳ Rafraîchir la liste")
        refresh.clicked.connect(self._refresh_accounts)
        outer.addWidget(refresh)

        self._sections.addTab(page, "Comptes")
        self._refresh_accounts()

    def _refresh_accounts(self) -> None:
        """Tente de lister les comptes depuis core.auth ; sinon affiche un placeholder."""
        rows: list[tuple[str, str, bool]] = []
        try:
            from core import auth as auth_mod  # noqa: WPS433
            list_fn: Optional[Callable[[], Any]] = getattr(
                auth_mod, "list_accounts", None,
            )
            if callable(list_fn):
                for entry in list_fn() or []:
                    rows.append((
                        str(entry.get("username", "?")),
                        str(entry.get("role", "?")),
                        bool(entry.get("active", True)),
                    ))
        except Exception as exc:
            logger.debug("SettingsTab: lecture comptes impossible — %s", exc)

        if not rows:
            rows = [("(aucun)", "—", False)]

        self._accounts_table.setRowCount(len(rows))
        for r, (user, role, active) in enumerate(rows):
            self._accounts_table.setItem(r, 0, QTableWidgetItem(user))
            self._accounts_table.setItem(r, 1, QTableWidgetItem(role))
            self._accounts_table.setItem(
                r, 2, QTableWidgetItem("oui" if active else "non"),
            )

    # ── Lecture YAML ──────────────────────────────────────────────────────────

    def _reload_yaml(self) -> None:
        if self._config_path.exists():
            try:
                with self._config_path.open(encoding="utf-8") as fh:
                    self._yaml_data = yaml.safe_load(fh) or {}
            except Exception as exc:
                logger.error("SettingsTab: lecture YAML échouée — %s", exc)
                self._yaml_data = {}
        else:
            self._yaml_data = {}

    def _get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._yaml_data
        for part in dotted.split("."):
            if not isinstance(node, dict):
                return default
            node = node.get(part)
            if node is None:
                return default
        return node

    def _populate_from_yaml(self) -> None:
        for key, w in self._editors.items():
            value = self._get(key)
            if isinstance(w, QCheckBox):
                w.setChecked(bool(value)) if value is not None else None
            elif isinstance(w, QComboBox):
                if value is not None:
                    text = str(value)
                    idx  = w.findText(text)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                    else:
                        w.addItem(text)
                        w.setCurrentText(text)
            elif isinstance(w, QSpinBox):
                # GPIO pin_start/pin_stop : null → -1
                if value is None and key in ("gpio.pin_start", "gpio.pin_stop"):
                    w.setValue(-1)
                elif value is not None:
                    try:
                        w.setValue(int(value))
                    except (TypeError, ValueError):
                        pass
            elif isinstance(w, QDoubleSpinBox):
                if value is not None:
                    try:
                        w.setValue(float(value))
                    except (TypeError, ValueError):
                        pass
            elif isinstance(w, QLineEdit):
                w.setText("" if value is None else str(value))

    # ── Sauvegarde YAML ───────────────────────────────────────────────────────

    def _collect(self) -> dict[str, Any]:
        """Construit la dict YAML mise à jour en préservant les clés inconnues."""
        out: dict[str, Any] = dict(self._yaml_data) if self._yaml_data else {}

        for dotted, w in self._editors.items():
            value: Any
            if isinstance(w, QCheckBox):
                value = w.isChecked()
            elif isinstance(w, QComboBox):
                value = w.currentText()
            elif isinstance(w, QSpinBox):
                value = w.value()
                if dotted in ("gpio.pin_start", "gpio.pin_stop") and value < 0:
                    value = None
            elif isinstance(w, QDoubleSpinBox):
                value = float(w.value())
            elif isinstance(w, QLineEdit):
                value = w.text().strip() or None
            else:
                continue
            self._set_path(out, dotted, value)
        return out

    @staticmethod
    def _set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = data
        for part in parts[:-1]:
            sub = node.get(part)
            if not isinstance(sub, dict):
                sub = {}
                node[part] = sub
            node = sub
        node[parts[-1]] = value

    def _on_save_clicked(self) -> None:
        if self._locked:
            QMessageBox.warning(
                self, "Verrouillé",
                "Inspection en cours — impossible d'éditer la configuration (GR-12).",
            )
            return
        merged = self._collect()
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with self._config_path.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(merged, fh, sort_keys=False, allow_unicode=True)
        except Exception as exc:
            logger.error("SettingsTab: sauvegarde YAML échouée — %s", exc)
            QMessageBox.critical(self, "Erreur", f"Sauvegarde impossible :\n{exc}")
            return

        self._yaml_data = merged
        self.config_saved.emit(merged)
        logger.info("SettingsTab: configuration sauvegardée → %s", self._config_path)
        QMessageBox.information(
            self, "Sauvegarde OK",
            f"Configuration écrite dans :\n{self._config_path}\n\n"
            "Les changements prendront effet au prochain démarrage (GR-06).",
        )

    def _on_reload_clicked(self) -> None:
        self._reload_yaml()
        self._populate_from_yaml()

    # ── Verrouillage GR-12 ────────────────────────────────────────────────────

    def _on_state_changed(self, state_value: str) -> None:
        try:
            self._sync_lock(SystemState(state_value))
        except ValueError:
            pass

    def _sync_lock(self, state: SystemState) -> None:
        running = (state == SystemState.RUNNING)
        self._locked = running
        for w in list(self._editors.values()):
            w.setEnabled(not running)
        self._save_btn.setEnabled(not running)
        self._reload_btn.setEnabled(not running)
        self._lock_banner.setVisible(running)

    # ── API publique ──────────────────────────────────────────────────────────

    @property
    def is_locked(self) -> bool:
        return self._locked

    def section_titles(self) -> tuple[str, ...]:
        return tuple(self._sections.tabText(i) for i in range(self._sections.count()))
