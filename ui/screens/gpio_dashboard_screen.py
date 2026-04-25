"""
GpioDashboardScreen — §17

Dashboard d'inspection / configuration des GPIO BCM 2-27 du Raspberry Pi 5.

  • Affiche TOUS les pins BCM disponibles (2-27) en deux tables (OUTPUTS / INPUTS).
  • Assigne fonction par pin via QComboBox :
      OUTPUT : "Libre" | "Lampe VERTE" | "Lampe ROUGE"
      INPUT  : "Libre" | "Start inspection" | "Stop inspection"
  • Monitoring temps réel des états (QTimer 100 ms) — ● HIGH (cyan) / ○ LOW (gris).
  • Test manuel : boutons ON/OFF par pin assigné OUTPUT.
  • Sauvegarde config → config/config.yaml section `gpio` (sans toucher au reste).
  • Monitoring INPUT Start/Stop : QTimer 50 ms — front montant déclenche
    SystemController.start_inspection() / stop_inspection() (GR-03).

Contraintes :
  GR-03 : aucune écriture pipeline directe — tout passe par SystemController.
  GR-12 : SystemState.RUNNING → toute interaction utilisateur désactivée.
  REVIEW (inspection en attente) → confirmation avant modification.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.gpio_manager import GpioManager
from core.models import SystemState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Constantes
# ─────────────────────────────────────────────────────────────────────────────

BCM_PINS: tuple[int, ...] = tuple(range(2, 28))   # GPIO 2-27 — RPi5

OUTPUT_FUNCTIONS = ("Libre", "Lampe VERTE", "Lampe ROUGE")
INPUT_FUNCTIONS  = ("Libre", "Start inspection", "Stop inspection")

_OUT_TO_KEY = {
    "Lampe VERTE": "pin_green",
    "Lampe ROUGE": "pin_red",
}
_IN_TO_KEY = {
    "Start inspection": "pin_start",
    "Stop inspection":  "pin_stop",
}

_REFRESH_MONITOR_MS = 100
_REFRESH_INPUTS_MS  = 50

_COLOR_HIGH = "#00CED1"   # cyan
_COLOR_LOW  = "#888888"   # gris


# ─────────────────────────────────────────────────────────────────────────────
#  Bandeau verrouillage GR-12
# ─────────────────────────────────────────────────────────────────────────────

class _LockBanner(QFrame):
    """Bandeau visible uniquement quand l'inspection est RUNNING (GR-12)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("GpioLockBanner")
        self.setStyleSheet(
            "QFrame#GpioLockBanner { background-color: #C0392B; }"
            "QLabel { color: white; font-weight: bold; padding: 6px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        self._label = QLabel(
            "🔒 INSPECTION ACTIVE — modifications GPIO désactivées (GR-12)"
        )
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)
        self.hide()


# ─────────────────────────────────────────────────────────────────────────────
#  GpioDashboardScreen
# ─────────────────────────────────────────────────────────────────────────────

class GpioDashboardScreen(QWidget):
    """
    Dashboard GPIO complet — §17.

    Construction :
        screen = GpioDashboardScreen(
            controller   = system_controller,
            ui_bridge    = ui_bridge,
            gpio_manager = gpio_manager,
            config_path  = "config/config.yaml",
        )
    """

    config_saved = pyqtSignal(dict)   # émis après sauvegarde YAML

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(
        self,
        controller   : Any,
        ui_bridge    : Any,
        gpio_manager : GpioManager,
        config_path  : str | Path = "config/config.yaml",
        parent       : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller   = controller
        self._bridge       = ui_bridge
        self._gpio         = gpio_manager
        self._config_path  = Path(config_path)

        # État interne (pin → fonction)
        self._output_funcs : Dict[int, str] = {pin: "Libre" for pin in BCM_PINS}
        self._input_funcs  : Dict[int, str] = {pin: "Libre" for pin in BCM_PINS}
        self._last_input_state : Dict[int, bool] = {}

        # Indique qu'une mise à jour widget → état est en cours (anti-rebond signal)
        self._programmatic_update = False
        self._locked = False

        self._build_ui()
        self._load_initial_assignments()

        # Timers
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(_REFRESH_MONITOR_MS)
        self._monitor_timer.timeout.connect(self._refresh_states)

        self._inputs_timer = QTimer(self)
        self._inputs_timer.setInterval(_REFRESH_INPUTS_MS)
        self._inputs_timer.timeout.connect(self._poll_input_triggers)

        # Connexion signaux
        if hasattr(self._bridge, "state_changed"):
            self._bridge.state_changed.connect(self._on_state_changed)

        self._sync_lock_state(controller.get_state())
        self._monitor_timer.start()
        self._inputs_timer.start()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Header
        root.addWidget(self._build_header())

        # Lock banner (caché par défaut)
        self._lock_banner = _LockBanner(self)
        root.addWidget(self._lock_banner)

        # Tables OUTPUTS / INPUTS côte à côte
        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(10)
        self._out_table, self._out_state_items = self._build_table(
            title="OUTPUTS", functions=OUTPUT_FUNCTIONS, is_output=True,
        )
        self._in_table, self._in_state_items = self._build_table(
            title="INPUTS", functions=INPUT_FUNCTIONS, is_output=False,
        )
        tables_layout.addWidget(self._out_table)
        tables_layout.addWidget(self._in_table)
        root.addLayout(tables_layout, 1)

        # Test manuel
        root.addWidget(self._build_manual_test_box())

        # Config save
        root.addWidget(self._build_config_box())

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("GpioHeader")
        header.setStyleSheet(
            "QFrame#GpioHeader { background-color: #2C3E50; padding: 6px; }"
            "QLabel { color: white; font-weight: bold; }"
        )
        h = QHBoxLayout(header)
        title = QLabel(
            f"GPIO Dashboard — Raspberry Pi 5 ({len(BCM_PINS)} pins disponibles)"
        )
        backend_kind = getattr(self._gpio, "_backend_kind", "stub")
        bk_label = QLabel(f"Backend: {backend_kind} ●")
        refresh_label = QLabel(
            f"● Refresh {_REFRESH_MONITOR_MS}ms"
        )
        h.addWidget(title, 1)
        h.addWidget(bk_label)
        h.addSpacing(20)
        h.addWidget(refresh_label)
        return header

    def _build_table(
        self,
        title     : str,
        functions : tuple[str, ...],
        is_output : bool,
    ) -> tuple[QGroupBox, Dict[int, QLabel]]:
        """Construit une table (Pin | Fonction | État) pour outputs ou inputs."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 14, 6, 6)

        table = QTableWidget(len(BCM_PINS), 3, group)
        table.setHorizontalHeaderLabels(["Pin", "Fonction", "État"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch,
        )
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        state_items: Dict[int, QLabel] = {}
        for row, pin in enumerate(BCM_PINS):
            # Col 0 : pin BCM
            pin_item = QTableWidgetItem(str(pin))
            pin_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 0, pin_item)

            # Col 1 : combo fonction
            combo = QComboBox()
            combo.addItems(functions)
            combo.setProperty("pin", pin)
            combo.setProperty("is_output", is_output)
            combo.currentTextChanged.connect(
                lambda txt, p=pin, out=is_output: self._on_function_changed(p, out, txt)
            )
            table.setCellWidget(row, 1, combo)

            # Col 2 : état (label)
            state_lbl = QLabel("○")
            state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            state_lbl.setStyleSheet(f"color: {_COLOR_LOW}; font-size: 18px;")
            state_items[pin] = state_lbl

            state_widget = QWidget()
            sw_layout = QHBoxLayout(state_widget)
            sw_layout.setContentsMargins(0, 0, 0, 0)
            sw_layout.addWidget(state_lbl)
            table.setCellWidget(row, 2, state_widget)

        table.resizeColumnToContents(0)
        table.resizeColumnToContents(2)
        layout.addWidget(table)

        # Mémoriser les combos pour reset / reload
        if is_output:
            self._out_table_widget = table
        else:
            self._in_table_widget = table
        return group, state_items

    def _build_manual_test_box(self) -> QWidget:
        box = QGroupBox("TEST MANUEL")
        layout = QHBoxLayout(box)
        self._manual_buttons: Dict[int, tuple[QPushButton, QPushButton]] = {}

        # Boutons générés à la volée selon l'assignation OUTPUT
        self._manual_container = QWidget()
        self._manual_layout    = QHBoxLayout(self._manual_container)
        self._manual_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._manual_container)
        layout.addStretch(1)
        return box

    def _build_config_box(self) -> QWidget:
        box = QGroupBox("CONFIG")
        layout = QHBoxLayout(box)

        layout.addWidget(QLabel("Lampe VERTE : Pin"))
        self._cfg_green_combo = QComboBox()
        self._cfg_green_combo.addItems([str(p) for p in BCM_PINS])
        layout.addWidget(self._cfg_green_combo)

        layout.addSpacing(20)
        layout.addWidget(QLabel("Lampe ROUGE : Pin"))
        self._cfg_red_combo = QComboBox()
        self._cfg_red_combo.addItems([str(p) for p in BCM_PINS])
        layout.addWidget(self._cfg_red_combo)

        layout.addStretch(1)
        self._save_btn = QPushButton("💾 Sauvegarder config GPIO")
        self._save_btn.clicked.connect(self._on_save_clicked)
        layout.addWidget(self._save_btn)

        # Synchronisation combos CONFIG ↔ table OUTPUTS
        self._cfg_green_combo.currentTextChanged.connect(
            lambda txt: self._on_config_pin_changed("Lampe VERTE", txt)
        )
        self._cfg_red_combo.currentTextChanged.connect(
            lambda txt: self._on_config_pin_changed("Lampe ROUGE", txt)
        )
        return box

    def _on_config_pin_changed(self, function: str, pin_text: str) -> None:
        """Quand l'utilisateur change le pin d'une lampe via la combo CONFIG."""
        if self._programmatic_update:
            return
        try:
            pin = int(pin_text)
        except ValueError:
            return
        # Reverse-look up actual current pin and clear it before assigning
        for p, f in list(self._output_funcs.items()):
            if f == function and p != pin:
                self._output_funcs[p] = "Libre"
                self._programmatic_update = True
                self._set_combo_text(self._out_table_widget, p, "Libre")
                self._programmatic_update = False
        # Déléguer à _on_function_changed pour cohérence (gère aussi setup_output)
        self._programmatic_update = True
        self._set_combo_text(self._out_table_widget, pin, function)
        self._programmatic_update = False
        # Notifier (sans déclencher de boucle infinie : on appelle directement la
        # logique métier sans repasser par les combos)
        self._output_funcs[pin] = function
        backend = getattr(self._gpio, "backend", None)
        if backend is not None:
            try:
                backend.setup_output(pin)
            except Exception as exc:
                logger.error("GpioDashboard: setup_output pin %d a échoué — %s",
                             pin, exc)
        self._rebuild_manual_buttons()

    # ── Initialisation depuis le manager ──────────────────────────────────────

    def _load_initial_assignments(self) -> None:
        """Lit les pins déjà assignés dans GpioManager pour pré-remplir l'UI."""
        self._programmatic_update = True
        try:
            green = getattr(self._gpio, "pin_green", 17)
            red   = getattr(self._gpio, "pin_red", 18)

            if green in self._output_funcs:
                self._output_funcs[green] = "Lampe VERTE"
            if red in self._output_funcs:
                self._output_funcs[red] = "Lampe ROUGE"

            for pin in BCM_PINS:
                func = self._output_funcs[pin]
                self._set_combo_text(self._out_table_widget, pin, func)
                self._set_combo_text(self._in_table_widget,  pin,
                                     self._input_funcs[pin])

            self._cfg_green_combo.setCurrentText(str(green))
            self._cfg_red_combo.setCurrentText(str(red))
        finally:
            self._programmatic_update = False

        self._rebuild_manual_buttons()

    def _set_combo_text(self, table: QTableWidget, pin: int, text: str) -> None:
        for row in range(table.rowCount()):
            cell = table.cellWidget(row, 1)
            if isinstance(cell, QComboBox) and cell.property("pin") == pin:
                cell.setCurrentText(text)
                return

    # ── Slot fonction combo ───────────────────────────────────────────────────

    def _on_function_changed(self, pin: int, is_output: bool, text: str) -> None:
        if self._programmatic_update:
            return

        # Confirmation si REVIEW (inspection en attente)
        state = self._controller.get_state()
        if state == SystemState.REVIEW:
            if not self._confirm("Modifier l'assignation GPIO maintenant ?"):
                # Restaurer l'ancien
                old = (self._output_funcs if is_output
                       else self._input_funcs)[pin]
                self._programmatic_update = True
                table = self._out_table_widget if is_output else self._in_table_widget
                self._set_combo_text(table, pin, old)
                self._programmatic_update = False
                return

        # Empêcher double assignation pin OUTPUT ↔ INPUT
        if text != "Libre":
            other_funcs = self._input_funcs if is_output else self._output_funcs
            if other_funcs.get(pin, "Libre") != "Libre":
                other_funcs[pin] = "Libre"
                other_table = self._in_table_widget if is_output else self._out_table_widget
                self._programmatic_update = True
                self._set_combo_text(other_table, pin, "Libre")
                self._programmatic_update = False

        # Une fonction OUTPUT (Lampe VERTE/ROUGE) ne peut être assignée qu'à un seul pin
        if is_output and text in _OUT_TO_KEY:
            for other_pin, f in list(self._output_funcs.items()):
                if other_pin != pin and f == text:
                    self._output_funcs[other_pin] = "Libre"
                    self._programmatic_update = True
                    self._set_combo_text(
                        self._out_table_widget, other_pin, "Libre",
                    )
                    self._programmatic_update = False
        if (not is_output) and text in _IN_TO_KEY:
            for other_pin, f in list(self._input_funcs.items()):
                if other_pin != pin and f == text:
                    self._input_funcs[other_pin] = "Libre"
                    self._programmatic_update = True
                    self._set_combo_text(
                        self._in_table_widget, other_pin, "Libre",
                    )
                    self._programmatic_update = False

        # Mémoriser
        if is_output:
            self._output_funcs[pin] = text
            # Sync combo CONFIG (sans réémettre)
            if text == "Lampe VERTE":
                self._programmatic_update = True
                self._cfg_green_combo.setCurrentText(str(pin))
                self._programmatic_update = False
            elif text == "Lampe ROUGE":
                self._programmatic_update = True
                self._cfg_red_combo.setCurrentText(str(pin))
                self._programmatic_update = False
        else:
            self._input_funcs[pin] = text

        # Setup pin physique côté backend si nécessaire
        backend = getattr(self._gpio, "backend", None)
        if backend is not None:
            try:
                if text != "Libre":
                    if is_output:
                        backend.setup_output(pin)
                    else:
                        backend.setup_input(pin)
            except Exception as exc:
                logger.error("GpioDashboard: setup pin %d a échoué — %s", pin, exc)

        self._rebuild_manual_buttons()

    # ── Test manuel ───────────────────────────────────────────────────────────

    def _rebuild_manual_buttons(self) -> None:
        # Vider
        while self._manual_layout.count() > 0:
            item = self._manual_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._manual_buttons.clear()

        # Reconstruire pour chaque OUTPUT non-libre
        for pin, func in sorted(self._output_funcs.items()):
            if func == "Libre":
                continue
            label = QLabel(f"Pin {pin} ({func}) :")
            on_btn  = QPushButton("ON")
            off_btn = QPushButton("OFF")
            on_btn.clicked.connect(lambda _=False, p=pin: self._manual_write(p, True))
            off_btn.clicked.connect(lambda _=False, p=pin: self._manual_write(p, False))
            self._manual_layout.addWidget(label)
            self._manual_layout.addWidget(on_btn)
            self._manual_layout.addWidget(off_btn)
            self._manual_layout.addSpacing(15)
            self._manual_buttons[pin] = (on_btn, off_btn)

        self._sync_lock_state(self._controller.get_state())

    def _manual_write(self, pin: int, high: bool) -> None:
        backend = getattr(self._gpio, "backend", None)
        if backend is None:
            return
        try:
            backend.write(pin, high)
            logger.info("GpioDashboard: test manuel pin %d → %s",
                        pin, "HIGH" if high else "LOW")
        except Exception as exc:
            logger.error("GpioDashboard: write pin %d a échoué — %s", pin, exc)

    # ── Monitoring 100 ms ─────────────────────────────────────────────────────

    def _refresh_states(self) -> None:
        backend = getattr(self._gpio, "backend", None)
        if backend is None:
            return
        for pin in BCM_PINS:
            try:
                level = bool(backend.read(pin))
            except Exception:
                continue
            self._apply_state_indicator(self._out_state_items[pin], level)
            self._apply_state_indicator(self._in_state_items[pin],  level)

    @staticmethod
    def _apply_state_indicator(label: QLabel, high: bool) -> None:
        if high:
            label.setText("●")
            label.setStyleSheet(f"color: {_COLOR_HIGH}; font-size: 18px;")
        else:
            label.setText("○")
            label.setStyleSheet(f"color: {_COLOR_LOW}; font-size: 18px;")

    # ── Polling INPUTS Start/Stop (50 ms) — front montant ────────────────────

    def _poll_input_triggers(self) -> None:
        backend = getattr(self._gpio, "backend", None)
        if backend is None:
            return
        for pin, func in self._input_funcs.items():
            if func == "Libre":
                continue
            try:
                level = bool(backend.read(pin))
            except Exception:
                continue
            prev = self._last_input_state.get(pin, False)
            self._last_input_state[pin] = level
            if level and not prev:
                self._on_input_rising_edge(func, pin)

    def _on_input_rising_edge(self, func: str, pin: int) -> None:
        """GR-03 : pas d'appel direct au pipeline — passe par SystemController."""
        try:
            if func == "Start inspection":
                logger.info("GpioDashboard: pin %d HIGH → start_inspection", pin)
                self._controller.start_inspection()
            elif func == "Stop inspection":
                logger.info("GpioDashboard: pin %d HIGH → stop_inspection", pin)
                self._controller.stop_inspection()
        except Exception as exc:
            logger.error("GpioDashboard: action %s sur pin %d échouée — %s",
                         func, pin, exc)

    # ── Verrouillage GR-12 ────────────────────────────────────────────────────

    def _on_state_changed(self, state_value: str) -> None:
        try:
            state = SystemState(state_value)
        except ValueError:
            return
        self._sync_lock_state(state)

    def _sync_lock_state(self, state: SystemState) -> None:
        running = (state == SystemState.RUNNING)
        self._locked = running
        # Verrouille TOUS les widgets interactifs (GR-12)
        for w in (
            self._out_table_widget, self._in_table_widget,
            self._cfg_green_combo, self._cfg_red_combo, self._save_btn,
            self._manual_container,
        ):
            w.setEnabled(not running)
        self._lock_banner.setVisible(running)

    # ── Sauvegarde config.yaml ────────────────────────────────────────────────

    def _on_save_clicked(self) -> None:
        gpio_section = self._collect_gpio_section()
        try:
            saved = self._save_to_yaml(gpio_section)
        except Exception as exc:
            logger.error("GpioDashboard: sauvegarde a échoué — %s", exc)
            QMessageBox.critical(self, "Erreur", f"Sauvegarde impossible :\n{exc}")
            return
        logger.info("GpioDashboard: config GPIO sauvegardée → %s", self._config_path)
        self.config_saved.emit(saved)
        QMessageBox.information(
            self, "Sauvegarde OK",
            f"Configuration GPIO écrite dans :\n{self._config_path}",
        )

    def _collect_gpio_section(self) -> Dict[str, Any]:
        """Construit le dict gpio à fusionner dans config.yaml."""
        section: Dict[str, Any] = {
            "enabled": True,
            "backend": getattr(self._gpio, "_backend_kind", "stub"),
            "pin_green": int(self._cfg_green_combo.currentText()),
            "pin_red":   int(self._cfg_red_combo.currentText()),
            "pin_start": None,
            "pin_stop":  None,
        }
        for pin, func in self._input_funcs.items():
            key = _IN_TO_KEY.get(func)
            if key is not None:
                section[key] = pin
        # Aligner OUTPUT (lampes) avec l'assignation tableau si elle diffère du combo config
        for pin, func in self._output_funcs.items():
            key = _OUT_TO_KEY.get(func)
            if key is not None:
                section[key] = pin
        return section

    def _save_to_yaml(self, gpio_section: Dict[str, Any]) -> Dict[str, Any]:
        """Lit YAML actuel, fusionne section gpio, réécrit. Préserve le reste."""
        data: Dict[str, Any] = {}
        if self._config_path.exists():
            with self._config_path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        data["gpio"] = gpio_section
        with self._config_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        return gpio_section

    # ── Nettoyage ─────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        self._monitor_timer.stop()
        self._inputs_timer.stop()
        super().closeEvent(event)

    # ── Lecture (tests) ───────────────────────────────────────────────────────

    @property
    def output_assignments(self) -> Dict[int, str]:
        return dict(self._output_funcs)

    @property
    def input_assignments(self) -> Dict[int, str]:
        return dict(self._input_funcs)

    @property
    def is_locked(self) -> bool:
        return self._locked

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _confirm(self, message: str) -> bool:
        ret = QMessageBox.question(
            self, "Confirmation", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return ret == QMessageBox.StandardButton.Yes
