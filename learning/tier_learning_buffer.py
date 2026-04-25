"""
TierLearningBuffer × 3 — §11.1
Buffer d'apprentissage par Tier avec 3 gates.
Thread-safe. GR-08 : RuleEngine jamais impliqué.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from core.models import FinalResult
from core.tier_result import TierLevel, TierVerdict

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  LearningEntry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LearningEntry:
    """
    Un sample d'apprentissage extrait d'un FinalResult — §11.1.
    Poids ×2 si validé manuellement par un opérateur.
    """
    frame_id       : str
    product_id     : str
    tier           : TierLevel
    verdict        : str
    tier_verdict   : TierVerdict
    tier_score     : float
    operator_label : Optional[str]   # None → verdict auto
    weight         : float           # 1.0 auto · 2.0 opérateur
    timestamp      : float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
#  TierLearningBuffer
# ─────────────────────────────────────────────────────────────────────────────

class TierLearningBuffer:
    """
    Buffer d'apprentissage indépendant par Tier — §11.1.

    3 gates avant acceptation d'un sample (ordre strict) :
      Gate ① confiance     : tier_score >= seuil Tier (CRITICAL 0.80 / MAJOR 0.70 / MINOR 0.60)
      Gate ② stabilité     : verdicts identiques sur la fenêtre (stability_window)
      Gate ③ absence erreur: aucun signal en erreur dans le tier_verdict

    Déclenche retrain quand len(buffer) >= trigger_count.
    Thread-safe via threading.Lock.
    GR-08 : aucune interaction avec RuleEngine.
    """

    # Seuils de confiance par Tier — §11.2
    _CONFIDENCE_GATES: dict[TierLevel, float] = {
        TierLevel.CRITICAL: 0.80,
        TierLevel.MAJOR:    0.70,
        TierLevel.MINOR:    0.60,
    }

    def __init__(
        self,
        tier:             TierLevel,
        product_id:       str,
        trigger_count:    int = 50,
        stability_window: int = 10,
    ) -> None:
        self._tier             = tier
        self._product_id       = product_id
        self._trigger_count    = trigger_count
        self._stability_window = stability_window
        self._buffer:          list[LearningEntry] = []
        self._verdict_history: deque[str]          = deque(maxlen=stability_window)
        self._lock             = threading.Lock()
        self._min_confidence   = self._CONFIDENCE_GATES[tier]

    # ── API publique ──────────────────────────────────────────────────────────

    def add_result(
        self,
        final_result:   FinalResult,
        operator_label: Optional[str] = None,
    ) -> bool:
        """
        Ajoute un résultat au buffer si les 3 gates passent.

        Returns:
            True si le sample a été accepté, False si rejeté par une gate.
        """
        with self._lock:
            tier_verdict = final_result.tier_verdicts.get(self._tier.value)
            if tier_verdict is None:
                return False

            tier_score = final_result.tier_scores.get(self._tier.value, 0.0)

            # Gate ① — confiance minimale par Tier
            if tier_score < self._min_confidence:
                logger.debug(
                    "Buffer %s: rejeté gate① confiance=%.2f < %.2f",
                    self._tier.value, tier_score, self._min_confidence,
                )
                return False

            # Gate ② — stabilité des verdicts (stability_window consécutifs identiques)
            self._verdict_history.append(final_result.verdict)
            if len(self._verdict_history) == self._stability_window:
                if len(set(self._verdict_history)) > 1:
                    logger.debug(
                        "Buffer %s: rejeté gate② stabilité (verdicts: %s)",
                        self._tier.value, list(self._verdict_history),
                    )
                    return False

            # Gate ③ — aucun signal en erreur
            if tier_verdict.signals:
                for sig in tier_verdict.signals:
                    if sig.error_msg:
                        logger.debug(
                            "Buffer %s: rejeté gate③ signal '%s' en erreur — %s",
                            self._tier.value, sig.observer_id, sig.error_msg,
                        )
                        return False

            # Poids opérateur : validation manuelle compte double
            weight = 2.0 if operator_label else 1.0

            entry = LearningEntry(
                frame_id       = final_result.frame_id,
                product_id     = final_result.product_id,
                tier           = self._tier,
                verdict        = final_result.verdict,
                tier_verdict   = tier_verdict,
                tier_score     = tier_score,
                operator_label = operator_label,
                weight         = weight,
            )
            self._buffer.append(entry)
            logger.debug(
                "Buffer %s: accepté (%d/%d) weight=%.1f",
                self._tier.value, len(self._buffer), self._trigger_count, weight,
            )
            return True

    def should_trigger(self) -> bool:
        """True si le buffer a atteint trigger_count samples."""
        with self._lock:
            return len(self._buffer) >= self._trigger_count

    def consume(self) -> list[LearningEntry]:
        """Vide le buffer et retourne tous les samples pour retrain."""
        with self._lock:
            entries        = list(self._buffer)
            self._buffer.clear()
            logger.info(
                "Buffer %s: consommé — %d samples envoyés au trainer",
                self._tier.value, len(entries),
            )
            return entries

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._buffer)
