"""
UIBridge — bus de signaux Qt Pipeline → UI
GR-03 : UI via SystemController uniquement — jamais accès direct au pipeline
GR-05 : signaux émis depuis n'importe quel thread, traités dans le thread Qt principal
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class UIBridge(QObject):
    """
    Bus de signaux Qt unidirectionnel Pipeline → UI.

    Tous les composants pipeline émettent via UIBridge.
    Aucun composant UI n'appelle le pipeline directement (GR-03).
    Les connexions Qt sont automatiquement queued si cross-thread (GR-05).
    """

    # ── État système ───────────────────────────────────────────────────────────

    state_changed = pyqtSignal(str)
    """SystemState.value émis à chaque transition FSM."""

    system_snapshot = pyqtSignal(object)
    """SystemSnapshot émis périodiquement (dashboard, barre de statut)."""

    # ── Résultats d'inspection ─────────────────────────────────────────────────

    inspection_result = pyqtSignal(object)
    """FinalResult émis dès que le verdict principal est disponible (Fail-Fast ou complet)."""

    tier_verdict_ready = pyqtSignal(str, object)
    """(tier_name: str, TierVerdict) émis après chaque Tier complété dans S4."""

    background_complete = pyqtSignal(object)
    """FinalResult complet (tous Tiers) émis quand le background thread termine."""

    # ── Compteurs et monitoring ────────────────────────────────────────────────

    nok_counter_update = pyqtSignal(int)
    """Nombre total de NOK de la session, émis après chaque résultat NOK."""

    nok_alert = pyqtSignal(int)
    """NOK consécutifs >= alert_threshold (5) — bandeau orange WARNING."""

    nok_stop = pyqtSignal(int)
    """NOK consécutifs >= stop_threshold (10) — arrêt ligne, reset opérateur requis."""

    nok_reset = pyqtSignal(str)
    """Reset opérateur effectué — operator_id émis (traçabilité UI)."""

    luminosity_update = pyqtSignal(object)
    """LuminosityResult émis par S2 avant chaque inspection (indicateur UI)."""

    frame_ready = pyqtSignal(object)
    """Frame brute (np.ndarray BGR ou QPixmap) émise après S1_Acquisition."""

    system_health_update = pyqtSignal(object)
    """HostMetricsSnapshot émis périodiquement par SystemMonitor (§18.4)."""

    # ── Événements système ─────────────────────────────────────────────────────

    watchdog_triggered = pyqtSignal()
    """Émis quand le watchdog détecte un timeout pipeline (§18.1)."""

    auto_switch_started = pyqtSignal(str)
    """product_name émis au début d'un changement de produit automatique."""

    product_switched = pyqtSignal(str)
    """product_id émis après chaque activate_product (initial ou auto-switch)."""
