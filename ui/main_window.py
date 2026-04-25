"""
MainWindow — TS2I IVS v7.0
QMainWindow avec navigation à onglets + menu Fichier + toolbar.

Onglets (gauche → droite) :
  Inspection · Historique · Analytics · AI Monitoring · GPIO Dashboard · Paramètres

Menu Fichier :
  Nouveau produit (Wizard)  ·  ROI Editor  ·  Formation  ·  Quitter

Toolbar : bouton "+ Produit" toujours visible.

Les stubs (ui/screens/product_creation_screen.py, training_screen.py,
ui/tabs/*.py) ne sont PAS écrasés ; la MainWindow génère un placeholder
"Module en cours de développement" tant qu'un module est vide.

GR-03 : aucune action déclenchée ici n'accède au pipeline directement —
        tout passe par SystemController.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Placeholder pour modules non encore implémentés
# ─────────────────────────────────────────────────────────────────────────────

class _PlaceholderTab(QWidget):
    """Onglet de courtoisie pour un module encore vide (stub)."""

    def __init__(self, title: str, hint: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel(f"🛈  {title}")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet("font-size: 22px; color: #888;")

        hint_lbl = QLabel(hint or "Module en cours de développement.")
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_lbl.setStyleSheet("color: #666; font-size: 14px;")

        layout.addStretch(1)
        layout.addWidget(title_lbl)
        layout.addWidget(hint_lbl)
        layout.addStretch(1)


# ─────────────────────────────────────────────────────────────────────────────
#  MainWindow
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    Fenêtre principale TS2I IVS v7.0.

    Construction :
        win = MainWindow(
            controller   = system_controller,   # core.pipeline_controller.SystemController
            ui_bridge    = ui_bridge,
            gpio_manager = gpio_manager,        # optionnel — onglet GPIO si fourni
            config       = config,              # ConfigManager ou dict (ROI editor)
            config_path  = "config/config.yaml",
        )
        win.show()
    """

    TAB_TITLES = (
        "Inspection",
        "Historique",
        "Analytics",
        "AI Monitoring",
        "GPIO Dashboard",
        "Fleet",
        "Paramètres",
    )

    def __init__(
        self,
        controller    : Any,
        ui_bridge     : Any,
        gpio_manager  : Optional[Any] = None,
        config        : Any           = None,
        config_path    : str           = "config/config.yaml",
        fleet_manager  : Optional[Any] = None,
        usb_monitor    : Optional[Any] = None,
        system_monitor : Optional[Any] = None,
        parent         : Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller     = controller
        self._bridge         = ui_bridge
        self._gpio_manager   = gpio_manager
        self._config         = config
        self._config_path    = config_path
        self._fleet_manager  = fleet_manager
        self._usb_monitor    = usb_monitor
        self._system_monitor = system_monitor

        self.setWindowTitle("TS2I IVS v7.0 — Rule-Governed Hierarchical Inspection")
        self.resize(1440, 900)
        # QSS global : fond sombre + onglets explicitement clairs et lisibles.
        self.setStyleSheet(
            "QMainWindow { background:#0d0d0d; }"
            "QTabWidget::pane { border-top: 2px solid #444; background:#1a1a1a; }"
            "QTabBar { background:#1a1a1a; }"
            "QTabBar::tab { background:#222; color:#ddd; padding: 8px 18px; "
            "  margin-right:2px; font-weight:bold; "
            "  border-top-left-radius:4px; border-top-right-radius:4px; }"
            "QTabBar::tab:selected { background:#0078d7; color:white; }"
            "QTabBar::tab:hover:!selected { background:#333; color:#fff; }"
            "QStatusBar { color: #ddd; }"
            "QStatusBar QLabel { color: #ddd; }"
        )

        # Layout central : QTabWidget — North + tab bar visible (pas de documentMode
        # qui rend les onglets transparents sur fond sombre).
        self._tabs = QTabWidget(self)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(False)
        self._tabs.setMovable(False)
        self._tabs.setUsesScrollButtons(False)
        tab_bar = self._tabs.tabBar()
        tab_bar.setExpanding(False)
        tab_bar.setDrawBase(True)
        self.setCentralWidget(self._tabs)

        self._tab_indices: dict[str, int] = {}
        self._build_tabs()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()

        # Wire l'état FSM dans la barre de statut
        if self._bridge is not None and hasattr(self._bridge, "state_changed"):
            self._bridge.state_changed.connect(self._on_state_changed)
        if self._controller is not None:
            try:
                self._on_state_changed(self._controller.get_state().value)
            except Exception:
                pass

    # ── Onglets ───────────────────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        self._tab_indices["Inspection"]    = self._tabs.addTab(
            self._make_inspection_tab(),   "Inspection",
        )
        self._tab_indices["Historique"]    = self._tabs.addTab(
            self._make_history_tab(),       "Historique",
        )
        self._tab_indices["Analytics"]     = self._tabs.addTab(
            self._make_analytics_tab(),     "Analytics",
        )
        self._tab_indices["AI Monitoring"] = self._tabs.addTab(
            self._make_ai_monitoring_tab(), "AI Monitoring",
        )
        self._tab_indices["GPIO Dashboard"] = self._tabs.addTab(
            self._make_gpio_tab(),          "GPIO Dashboard",
        )
        self._tab_indices["Fleet"]         = self._tabs.addTab(
            self._make_fleet_tab(),         "Fleet",
        )
        self._tab_indices["Paramètres"]    = self._tabs.addTab(
            self._make_settings_tab(),      "Paramètres",
        )

    def _make_inspection_tab(self) -> QWidget:
        """Retourne InspectionScreen si dispo + ses dépendances présentes, sinon placeholder."""
        try:
            from ui.screens.inspection_screen import InspectionScreen
        except Exception as exc:
            logger.warning("InspectionScreen indisponible : %s", exc)
            return _PlaceholderTab("Inspection",
                                   "InspectionScreen indisponible — vérifier les imports.")
        if self._controller is None or self._bridge is None:
            return _PlaceholderTab(
                "Inspection",
                "Controller ou UIBridge absent — démarrage en mode aperçu.",
            )
        try:
            return InspectionScreen(
                controller=self._controller,
                ui_bridge=self._bridge,
                parent=self,
            )
        except Exception as exc:
            logger.error("InspectionScreen build échoué : %s", exc, exc_info=True)
            return _PlaceholderTab("Inspection", f"Erreur : {exc}")

    def _make_gpio_tab(self) -> QWidget:
        """GpioDashboardScreen si gpio_manager fourni, sinon placeholder explicatif."""
        if self._gpio_manager is None:
            return _PlaceholderTab(
                "GPIO Dashboard",
                "Aucun GpioManager fourni — passer gpio_manager=… au constructeur.",
            )
        try:
            from ui.screens.gpio_dashboard_screen import GpioDashboardScreen
        except Exception as exc:
            logger.warning("GpioDashboardScreen indisponible : %s", exc)
            return _PlaceholderTab("GPIO Dashboard", f"Import échoué : {exc}")
        try:
            return GpioDashboardScreen(
                controller=self._controller,
                ui_bridge=self._bridge,
                gpio_manager=self._gpio_manager,
                config_path=self._config_path,
                parent=self,
            )
        except Exception as exc:
            logger.error("GpioDashboard build échoué : %s", exc, exc_info=True)
            return _PlaceholderTab("GPIO Dashboard", f"Erreur : {exc}")

    def _make_history_tab(self) -> QWidget:
        try:
            from ui.tabs.history_tab import HistoryTab
        except Exception as exc:
            logger.warning("HistoryTab indisponible : %s", exc)
            return _PlaceholderTab("Historique", f"Import échoué : {exc}")
        try:
            return HistoryTab(
                controller=self._controller,
                ui_bridge=self._bridge,
                parent=self,
            )
        except Exception as exc:
            logger.error("HistoryTab build échoué : %s", exc, exc_info=True)
            return _PlaceholderTab("Historique", f"Erreur : {exc}")

    def _make_analytics_tab(self) -> QWidget:
        try:
            from ui.tabs.analytics_tab import AnalyticsTab
        except Exception as exc:
            logger.warning("AnalyticsTab indisponible : %s", exc)
            return _PlaceholderTab("Analytics", f"Import échoué : {exc}")
        try:
            return AnalyticsTab(
                controller=self._controller,
                ui_bridge=self._bridge,
                config=self._config,
                parent=self,
            )
        except Exception as exc:
            logger.error("AnalyticsTab build échoué : %s", exc, exc_info=True)
            return _PlaceholderTab("Analytics", f"Erreur : {exc}")

    def _make_ai_monitoring_tab(self) -> QWidget:
        try:
            from ui.tabs.ai_monitoring_tab import AIMonitoringTab
        except Exception as exc:
            logger.warning("AIMonitoringTab indisponible : %s", exc)
            return _PlaceholderTab("AI Monitoring", f"Import échoué : {exc}")
        # Tente de récupérer un ObserverRegistry exposé par le controller.
        registry = None
        for attr in ("observer_registry", "_observer_registry"):
            registry = getattr(self._controller, attr, None) if self._controller else None
            if registry is not None:
                break
        try:
            return AIMonitoringTab(
                controller=self._controller,
                ui_bridge=self._bridge,
                observer_registry=registry,
                parent=self,
            )
        except Exception as exc:
            logger.error("AIMonitoringTab build échoué : %s", exc, exc_info=True)
            return _PlaceholderTab("AI Monitoring", f"Erreur : {exc}")

    def _make_fleet_tab(self) -> QWidget:
        """FleetScreen — export/import .ivs (§Fleet). Lazy build des dépendances."""
        try:
            from ui.screens.fleet_screen import FleetScreen
        except Exception as exc:
            logger.warning("FleetScreen indisponible : %s", exc)
            return _PlaceholderTab("Fleet", f"Import échoué : {exc}")

        fleet = self._fleet_manager or self._build_default_fleet_manager()
        if fleet is None:
            return _PlaceholderTab(
                "Fleet",
                "FleetManager indisponible — passer fleet_manager=… au constructeur "
                "ou vérifier la présence de evaluation.model_validator.",
            )

        usb = self._usb_monitor or self._build_default_usb_monitor()
        registry = (
            getattr(self._controller, "product_registry", None)
            if self._controller is not None else None
        )
        try:
            return FleetScreen(
                fleet_manager    = fleet,
                product_registry = registry,
                usb_monitor      = usb,
                controller       = self._controller,
                ui_bridge        = self._bridge,
                parent           = self,
            )
        except Exception as exc:
            logger.error("FleetScreen build échoué : %s", exc, exc_info=True)
            return _PlaceholderTab("Fleet", f"Erreur : {exc}")

    def _build_default_fleet_manager(self) -> Optional[Any]:
        """Crée un FleetManager par défaut si possible (best-effort)."""
        try:
            from core.fleet_manager import FleetManager
        except Exception as exc:
            logger.warning("FleetManager import échoué : %s", exc)
            return None
        try:
            from evaluation.model_validator import ModelValidator
            validator: Any = ModelValidator()
        except Exception as exc:
            logger.warning(
                "ModelValidator indisponible — FleetManager sans validateur "
                "(GR-13 refusera tout import) : %s", exc,
            )
            validator = None

        registry = (
            getattr(self._controller, "product_registry", None)
            if self._controller is not None else None
        )
        products_dir = (
            getattr(registry, "_dir", None)
            or getattr(self._controller, "_products_dir", None)
            or "products"
        )
        try:
            fleet = FleetManager(
                products_dir    = products_dir,
                config          = self._config,
                model_validator = validator,
                registry        = registry,
            )
            self._fleet_manager = fleet
            return fleet
        except Exception as exc:
            logger.error("FleetManager build échoué : %s", exc, exc_info=True)
            return None

    def _build_default_usb_monitor(self) -> Optional[Any]:
        """Crée et démarre un UsbMonitor par défaut (best-effort)."""
        try:
            from core.usb_monitor import UsbMonitor
        except Exception as exc:
            logger.warning("UsbMonitor import échoué : %s", exc)
            return None
        try:
            mon = UsbMonitor()
            mon.start()
            self._usb_monitor = mon
            return mon
        except Exception as exc:
            logger.error("UsbMonitor build échoué : %s", exc, exc_info=True)
            return None

    def _make_settings_tab(self) -> QWidget:
        try:
            from ui.tabs.settings_tab import SettingsTab
        except Exception as exc:
            logger.warning("SettingsTab indisponible : %s", exc)
            return _PlaceholderTab("Paramètres", f"Import échoué : {exc}")
        try:
            return SettingsTab(
                controller=self._controller,
                ui_bridge=self._bridge,
                config=self._config,
                config_path=self._config_path,
                parent=self,
            )
        except Exception as exc:
            logger.error("SettingsTab build échoué : %s", exc, exc_info=True)
            return _PlaceholderTab("Paramètres", f"Erreur : {exc}")

    # ── Menu Fichier ──────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Fichier")

        self._act_new_product = QAction("➕ &Nouveau produit…", self)
        self._act_new_product.setShortcut(QKeySequence("Ctrl+N"))
        self._act_new_product.triggered.connect(self._open_product_wizard)
        file_menu.addAction(self._act_new_product)

        self._act_roi = QAction("🎯 &ROI Editor…", self)
        self._act_roi.setShortcut(QKeySequence("Ctrl+R"))
        self._act_roi.triggered.connect(self._open_roi_editor)
        file_menu.addAction(self._act_roi)

        self._act_training = QAction("🧠 &Formation…", self)
        self._act_training.setShortcut(QKeySequence("Ctrl+T"))
        self._act_training.triggered.connect(self._open_training)
        file_menu.addAction(self._act_training)

        file_menu.addSeparator()

        act_quit = QAction("&Quitter", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Menu Affichage : raccourcis vers chaque onglet
        view_menu = bar.addMenu("&Affichage")
        for i, title in enumerate(self.TAB_TITLES):
            act = QAction(title, self)
            act.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            act.triggered.connect(lambda _=False, t=title: self.show_tab(t))
            view_menu.addAction(act)

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Actions principales", self)
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize())
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # Bouton "+ Produit" toujours visible
        self._tb_new_product = QAction("➕ Produit", self)
        self._tb_new_product.setStatusTip("Créer un nouveau produit (wizard)")
        self._tb_new_product.triggered.connect(self._open_product_wizard)
        tb.addAction(self._tb_new_product)

        tb.addSeparator()
        self._tb_roi = QAction("🎯 ROI", self)
        self._tb_roi.setStatusTip("Éditeur de zones ROI du produit actif")
        self._tb_roi.triggered.connect(self._open_roi_editor)
        tb.addAction(self._tb_roi)

        self._tb_training = QAction("🧠 Formation", self)
        self._tb_training.setStatusTip("Lancer une session d'entraînement")
        self._tb_training.triggered.connect(self._open_training)
        tb.addAction(self._tb_training)

        # Spacer + indicateur produit actif
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self._tb_product_label = QLabel("Produit : —")
        self._tb_product_label.setStyleSheet(
            "color: white; padding: 0 12px; font-weight: bold;"
        )
        tb.addWidget(self._tb_product_label)
        if self._bridge is not None and hasattr(self._bridge, "product_switched"):
            self._bridge.product_switched.connect(self._on_product_switched)
        if self._controller is not None and self._controller.active_product_id:
            self._on_product_switched(self._controller.active_product_id)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self._sb_state = QLabel("État : —")
        bar.addPermanentWidget(self._sb_state)

        # SystemStatusBar — CPU/RAM/Temp/Disk/Uptime alimenté via UIBridge.system_health_update
        try:
            from ui.components.system_status_bar import SystemStatusBar
            self._sb_health = SystemStatusBar(monitor=self._system_monitor, parent=self)
            bar.addPermanentWidget(self._sb_health)
            if self._bridge is not None and hasattr(self._bridge, "system_health_update"):
                self._bridge.system_health_update.connect(
                    self._sb_health.on_health_update,
                )
        except Exception as exc:
            logger.warning("SystemStatusBar indisponible : %s", exc)
            self._sb_health = None

        bar.showMessage("Prêt", 2000)

    # ── Actions menu / toolbar ────────────────────────────────────────────────

    def _open_product_wizard(self) -> None:
        screen = self._try_instantiate(
            "ui.screens.product_creation_screen", "ProductCreationScreen",
            controller=self._controller, ui_bridge=self._bridge,
            config=self._config, parent=self,
        )
        if screen is None:
            self._show_module_pending(
                "Wizard de création produit",
                "Le module ProductCreationScreen n'est pas encore implémenté.",
            )
            return
        self._exec_or_show(screen)

    def _open_roi_editor(self) -> None:
        product_id = (
            self._controller.active_product_id
            if self._controller is not None else None
        )
        if not product_id:
            QMessageBox.information(
                self, "ROI Editor",
                "Aucun produit actif. Activez un produit avant d'éditer ses ROI.",
            )
            return
        try:
            from ui.screens.roi_editor_screen import RoiEditorScreen
        except Exception as exc:
            self._show_module_pending("ROI Editor", f"Import échoué : {exc}")
            return
        try:
            dlg = RoiEditorScreen(
                product_id      = product_id,
                system_state_fn = (self._controller.get_state
                                   if self._controller is not None else None),
                on_save         = self._on_roi_saved,
                config          = self._config,
                parent          = self,
            )
        except Exception as exc:
            logger.error("ROI Editor : construction échouée — %s", exc, exc_info=True)
            QMessageBox.warning(self, "ROI Editor", f"Erreur : {exc}")
            return
        dlg.exec()

    def _open_training(self) -> None:
        screen = self._try_instantiate(
            "ui.screens.training_screen", "TrainingScreen",
            controller=self._controller, ui_bridge=self._bridge, parent=self,
        )
        if screen is None:
            self._show_module_pending(
                "Formation per-Tier",
                "Le module TrainingScreen n'est pas encore implémenté.",
            )
            return
        self._exec_or_show(screen)

    def _on_roi_saved(self, criteria) -> None:
        logger.info("MainWindow: %d critères ROI sauvegardés (relais GR-03)",
                    len(criteria) if criteria else 0)
        # GR-03 : la persistance disque appartient au controller / TierManager.
        # Ici on émet juste un message statut à l'utilisateur.
        self.statusBar().showMessage(
            f"{len(criteria) if criteria else 0} critères ROI sauvegardés.", 4000,
        )

    # ── Slots signaux ─────────────────────────────────────────────────────────

    def _on_state_changed(self, state_value: str) -> None:
        self._sb_state.setText(f"État : {state_value}")

    def _on_product_switched(self, product_id: str) -> None:
        self._tb_product_label.setText(f"Produit : {product_id}")

    # ── Navigation publique ───────────────────────────────────────────────────

    def show_tab(self, title: str) -> None:
        idx = self._tab_indices.get(title)
        if idx is not None:
            self._tabs.setCurrentIndex(idx)

    @property
    def current_tab_title(self) -> str:
        return self._tabs.tabText(self._tabs.currentIndex())

    @property
    def tab_titles(self) -> tuple[str, ...]:
        return tuple(self._tabs.tabText(i) for i in range(self._tabs.count()))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _try_instantiate(
        self, module_name: str, class_name: str, **kwargs,
    ) -> Optional[QWidget]:
        """Importe et instancie une classe si elle existe ; sinon None."""
        try:
            mod = __import__(module_name, fromlist=[class_name])
            cls = getattr(mod, class_name, None)
        except Exception as exc:
            logger.debug("import %s.%s : %s", module_name, class_name, exc)
            return None
        if cls is None or not inspect.isclass(cls):
            return None
        # Filtre kwargs à ceux acceptés par le constructeur (résiste aux
        # signatures variables des stubs).
        try:
            sig = inspect.signature(cls.__init__)
            accepted = {k for k in sig.parameters.keys() if k != "self"}
            kwargs   = {k: v for k, v in kwargs.items() if k in accepted}
            return cls(**kwargs)
        except Exception as exc:
            logger.warning("Instanciation %s échouée : %s", class_name, exc)
            return None

    def _exec_or_show(self, widget: QWidget) -> None:
        """Si QDialog → exec() (modal) ; sinon affichage flottant."""
        from PyQt6.QtWidgets import QDialog
        if isinstance(widget, QDialog):
            widget.exec()
        else:
            widget.setWindowFlag(Qt.WindowType.Window)
            widget.show()

    def _show_module_pending(self, title: str, body: str) -> None:
        QMessageBox.information(self, title, body)

    # ── Fermeture propre ──────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._usb_monitor is not None:
            try:
                self._usb_monitor.stop()
            except Exception as exc:
                logger.debug("UsbMonitor.stop ignoré : %s", exc)
        if self._controller is not None:
            try:
                self._controller.shutdown()
            except Exception as exc:
                logger.debug("shutdown ignoré : %s", exc)
        super().closeEvent(event)
