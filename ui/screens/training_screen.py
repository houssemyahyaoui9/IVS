"""
TrainingScreen v7.0 — Session d'entraînement per-Tier (§11)

Dialogue modal qui :

  • Affiche l'état FSM courant (l'entraînement n'est légal qu'à certains états).
  • Pour chaque Tier (CRITICAL · MAJOR · MINOR) :
      - état du buffer (taille / trigger),
      - bouton "Déclencher retrain" (best-effort, GR-09).
  • Journal en direct des messages d'entraînement (logger handler temporaire).

GR-03 : pas d'accès direct au pipeline. Les actions tentent d'abord
        SystemController (méthodes optionnelles), puis fallback sur
        controller.tier_buffers / .tier_trainers s'ils sont exposés.
GR-09 : trigger_retrain() est non bloquant — daemon thread.
GR-12 : RUNNING → boutons retrain désactivés (entraînement interdit).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import SystemState

logger = logging.getLogger(__name__)

_REFRESH_MS = 1000

_TIER_NAMES = ("CRITICAL", "MAJOR", "MINOR")


# ─────────────────────────────────────────────────────────────────────────────
#  Handler logging → QPlainTextEdit (signal Qt-safe cross-thread)
# ─────────────────────────────────────────────────────────────────────────────

class _QtLogHandler(logging.Handler):
    """Émet les records sous forme de signal Qt — thread-safe."""

    def __init__(self, sink: "TrainingScreen") -> None:
        super().__init__(level=logging.INFO)
        self._sink = sink
        self.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            # Filtrage doux : on garde tout ce qui parle de training/learning.
            name = record.name.lower()
            if any(k in name for k in ("trainer", "learning", "global_gates")):
                self._sink.log_signal.emit(msg, record.levelno)
        except Exception:  # ne JAMAIS faire planter le logger
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Carte par Tier
# ─────────────────────────────────────────────────────────────────────────────

class _TierTrainerCard(QGroupBox):
    """État du buffer + bouton retrain pour un Tier donné."""

    retrain_requested = pyqtSignal(str)   # tier_name

    def __init__(self, tier_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(tier_name, parent)
        self._tier_name = tier_name
        self._trigger   = 50

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(6)

        self._buffer_lbl = QLabel("Buffer : —")
        self._buffer_lbl.setStyleSheet("color:#ddd;")
        layout.addWidget(self._buffer_lbl)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFormat("%p%")
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("État : prêt")
        self._status_lbl.setStyleSheet("color:#aaa;")
        layout.addWidget(self._status_lbl)

        self._retrain_btn = QPushButton(f"🧠 Déclencher retrain {tier_name}")
        self._retrain_btn.clicked.connect(
            lambda: self.retrain_requested.emit(self._tier_name),
        )
        layout.addWidget(self._retrain_btn)
        layout.addStretch(1)

    def set_trigger(self, trigger: int) -> None:
        self._trigger = max(1, int(trigger))

    def set_buffer_size(self, size: int) -> None:
        pct = min(100, int(100.0 * size / max(1, self._trigger)))
        self._progress.setValue(pct)
        self._buffer_lbl.setText(
            f"Buffer : {size} / {self._trigger} samples"
        )

    def set_status(self, text: str, color: Optional[str] = None) -> None:
        css = "color:#aaa;"
        if color:
            css = f"color:{color}; font-weight:bold;"
        self._status_lbl.setStyleSheet(css)
        self._status_lbl.setText(f"État : {text}")

    def set_locked(self, locked: bool, reason: str = "") -> None:
        self._retrain_btn.setEnabled(not locked)
        if locked and reason:
            self._retrain_btn.setToolTip(reason)
        else:
            self._retrain_btn.setToolTip("")


# ─────────────────────────────────────────────────────────────────────────────
#  TrainingScreen
# ─────────────────────────────────────────────────────────────────────────────

class TrainingScreen(QDialog):
    """
    Dialogue de gestion des sessions d'entraînement par Tier (§11).

    Construction tolérante :
        TrainingScreen(controller=system_controller, ui_bridge=ui_bridge)
    """

    log_signal = pyqtSignal(str, int)     # message, levelno

    def __init__(
        self,
        controller : Any                = None,
        ui_bridge  : Any                = None,
        parent     : Optional[QWidget]  = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._bridge     = ui_bridge

        self.setWindowTitle("Entraînement per-Tier — TS2I IVS v7.0")
        self.resize(820, 560)
        self.setSizeGripEnabled(True)

        self._build_ui()
        self.log_signal.connect(self._append_log)

        # Handler logger temporaire (vivant le temps du dialogue)
        self._log_handler = _QtLogHandler(self)
        logging.getLogger().addHandler(self._log_handler)

        # Timer de rafraîchissement état + buffers
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        if self._bridge is not None and hasattr(self._bridge, "state_changed"):
            self._bridge.state_changed.connect(self._on_state_changed)

        self._refresh()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header — état FSM + produit actif
        header = QFrame()
        header.setObjectName("TrainingHeader")
        header.setStyleSheet(
            "QFrame#TrainingHeader { background:#1a1a1a; border-radius:4px; }"
            "QLabel { color:white; font-weight:bold; padding:6px; }"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(8, 4, 8, 4)
        self._lbl_state   = QLabel("État : —")
        self._lbl_product = QLabel("Produit : —")
        h.addWidget(self._lbl_state)
        h.addStretch(1)
        h.addWidget(self._lbl_product)
        root.addWidget(header)

        # Avertissement état
        self._lock_lbl = QLabel("")
        self._lock_lbl.setStyleSheet("color:#E74C3C; font-weight:bold; padding:4px;")
        self._lock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lock_lbl.hide()
        root.addWidget(self._lock_lbl)

        # 3 cartes par Tier
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self._cards: dict[str, _TierTrainerCard] = {}
        for tier in _TIER_NAMES:
            card = _TierTrainerCard(tier, self)
            card.retrain_requested.connect(self._on_retrain_clicked)
            cards_row.addWidget(card, 1)
            self._cards[tier] = card
        root.addLayout(cards_row)

        # Journal
        log_group = QGroupBox("Journal d'entraînement", self)
        log_layout = QVBoxLayout(log_group)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(2000)
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding,
                                QSizePolicy.Policy.Expanding)
        self._log.setStyleSheet(
            "QPlainTextEdit { background:#0d0d0d; color:#ddd; "
            "font-family: 'Consolas','Monaco',monospace; font-size:12px; }"
        )
        log_layout.addWidget(self._log)
        root.addWidget(log_group, 1)

        # Boutons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        root.addWidget(btns)

    # ── Refresh état ──────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        # État FSM + produit
        state = self._safe_state()
        if state is not None:
            self._lbl_state.setText(f"État : {state.value}")
        product_id = self._safe_active_product()
        self._lbl_product.setText(f"Produit : {product_id or '—'}")

        running = (state == SystemState.RUNNING)
        if running:
            self._lock_lbl.setText(
                "🔒 Inspection en cours — entraînement temporairement désactivé (GR-12)."
            )
            self._lock_lbl.show()
        else:
            self._lock_lbl.hide()

        # Buffer states / triggers
        for tier_name, card in self._cards.items():
            trigger = self._read_trigger(tier_name) or 50
            card.set_trigger(trigger)
            size = self._read_buffer_size(tier_name)
            if size is None:
                card.set_buffer_size(0)
                card.set_status("buffer indisponible", color="#888")
            else:
                card.set_buffer_size(size)
                ratio = size / max(1, trigger)
                if ratio >= 1.0:
                    card.set_status("prêt à retrain", color="#2ECC71")
                elif ratio >= 0.5:
                    card.set_status("en cours d'accumulation", color="#F1C40F")
                else:
                    card.set_status("collecte des samples", color="#aaa")

            no_product = product_id is None
            card.set_locked(
                running or no_product,
                reason=("Inspection en cours (GR-12)" if running
                        else "Aucun produit actif"),
            )

    # ── Slots / actions ───────────────────────────────────────────────────────

    def _on_state_changed(self, _state_value: str) -> None:
        self._refresh()

    def _on_retrain_clicked(self, tier_name: str) -> None:
        product_id = self._safe_active_product()
        if not product_id:
            self._append_log(
                f"⛔ Retrain {tier_name} ignoré — aucun produit actif.",
                logging.WARNING,
            )
            return
        ok = self._invoke_retrain(tier_name, product_id)
        if ok:
            self._append_log(
                f"➡ Retrain {tier_name} déclenché (background, GR-09).",
                logging.INFO,
            )
        else:
            self._append_log(
                f"⚠ Retrain {tier_name} indisponible — vérifier la "
                "configuration TierBackgroundTrainer.",
                logging.WARNING,
            )

    # ── Accès tolérant au controller ──────────────────────────────────────────

    def _safe_state(self) -> Optional[SystemState]:
        if self._controller is None:
            return None
        try:
            return self._controller.get_state()
        except Exception:
            return None

    def _safe_active_product(self) -> Optional[str]:
        if self._controller is None:
            return None
        try:
            return self._controller.active_product_id
        except Exception:
            return None

    def _read_buffer_size(self, tier_name: str) -> Optional[int]:
        """
        Tente plusieurs chemins (best-effort) pour lire la taille du buffer :
            controller.get_buffer_size(tier_name)
            controller.tier_buffers[tier].size()
            controller._tier_buffers[tier].size()
        """
        ctrl = self._controller
        if ctrl is None:
            return None
        fn = getattr(ctrl, "get_buffer_size", None)
        if callable(fn):
            try:
                return int(fn(tier_name))
            except Exception:
                pass
        for attr in ("tier_buffers", "_tier_buffers", "learning_buffers"):
            buffers = getattr(ctrl, attr, None)
            if not buffers:
                continue
            try:
                buf = buffers.get(tier_name) if hasattr(buffers, "get") else None
                if buf is None:
                    from core.tier_result import TierLevel
                    buf = buffers.get(TierLevel(tier_name))
                if buf is None:
                    continue
                size_fn = getattr(buf, "size", None)
                if callable(size_fn):
                    return int(size_fn())
                return int(len(buf))
            except Exception:
                continue
        return None

    def _read_trigger(self, _tier_name: str) -> Optional[int]:
        ctrl = self._controller
        if ctrl is None:
            return None
        # Best effort : config sur le controller s'il l'expose
        for attr in ("config", "_config"):
            cfg = getattr(ctrl, attr, None)
            if cfg is None:
                continue
            getter = getattr(cfg, "get", None)
            if callable(getter):
                try:
                    return int(getter("learning.trigger_count", 50))
                except Exception:
                    continue
        return None

    def _invoke_retrain(self, tier_name: str, product_id: str) -> bool:
        """
        Essaie dans l'ordre :
          controller.trigger_retrain(tier_name)
          controller.tier_trainers[tier].trigger_retrain([])
        """
        ctrl = self._controller
        if ctrl is None:
            return False
        fn = getattr(ctrl, "trigger_retrain", None)
        if callable(fn):
            try:
                fn(tier_name)
                return True
            except Exception as exc:
                logger.error("TrainingScreen: trigger_retrain a échoué — %s", exc)
                return False
        for attr in ("tier_trainers", "_tier_trainers"):
            trainers = getattr(ctrl, attr, None)
            if not trainers:
                continue
            try:
                t = trainers.get(tier_name) if hasattr(trainers, "get") else None
                if t is None:
                    from core.tier_result import TierLevel
                    t = trainers.get(TierLevel(tier_name))
                if t is None:
                    continue
                trigger_fn = getattr(t, "trigger_retrain", None)
                if callable(trigger_fn):
                    trigger_fn([])
                    return True
            except Exception as exc:
                logger.error("TrainingScreen: trainer[%s] a échoué — %s",
                             tier_name, exc)
        return False

    # ── Journal ───────────────────────────────────────────────────────────────

    def _append_log(self, message: str, levelno: int) -> None:
        color = {
            logging.DEBUG:    "#7F8C8D",
            logging.INFO:     "#EAEAEA",
            logging.WARNING:  "#F1C40F",
            logging.ERROR:    "#E74C3C",
            logging.CRITICAL: "#E74C3C",
        }.get(levelno, "#EAEAEA")
        # appendHtml n'ajoute pas implicitement un newline visuel mais un nouveau bloc.
        safe_msg = (
            message.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
        )
        self._log.appendHtml(f"<span style='color:{color}'>{safe_msg}</span>")

    # ── Fermeture propre ──────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            logging.getLogger().removeHandler(self._log_handler)
        except Exception:
            pass
        self._timer.stop()
        super().closeEvent(event)

    def reject(self) -> None:
        self.close()
        super().reject()

    # ── Helpers tests ─────────────────────────────────────────────────────────

    def tier_card(self, tier_name: str) -> Optional[_TierTrainerCard]:
        return self._cards.get(tier_name)
