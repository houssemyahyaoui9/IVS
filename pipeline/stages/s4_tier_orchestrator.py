"""
S4 TierOrchestrator Stage — §8
Entrée  : AlignedFrame
Sortie  : TierOrchestratorResult
Délègue à pipeline.tier_orchestrator.TierOrchestrator
"""
from __future__ import annotations

import logging

from core.models import ProductDefinition, ProductRules
from core.tier_result import TierOrchestratorResult
from pipeline.frames import AlignedFrame
from pipeline.tier_orchestrator import TierOrchestrator

logger = logging.getLogger(__name__)


class S4TierOrchestratorStage:
    """
    Stage 4 — TierOrchestrator.

    Wrapper de stage autour de TierOrchestrator.
    Reçoit AlignedFrame et retourne TierOrchestratorResult.
    La logique Fail-Fast Hybride est dans TierOrchestrator (§8).
    """

    def __init__(
        self,
        orchestrator:  TierOrchestrator,
        product_def:   ProductDefinition,
        product_rules: ProductRules,
    ) -> None:
        self._orchestrator  = orchestrator
        self._product_def   = product_def
        self._product_rules = product_rules

    def process(self, frame: AlignedFrame) -> TierOrchestratorResult:
        """
        Exécute les 3 Tiers via TierOrchestrator.

        Returns:
            TierOrchestratorResult — jamais None (GR-11).
        """
        logger.debug("S4: lancement orchestration 3-Tiers frame_id=%s", frame.frame_id)
        result = self._orchestrator.run(frame, self._product_def, self._product_rules)
        logger.debug("S4: fail_fast=%s", result.fail_fast)
        return result
