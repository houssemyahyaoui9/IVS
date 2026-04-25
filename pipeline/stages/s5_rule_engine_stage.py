"""
S5 RuleEngine Stage — §7
Entrée  : TierOrchestratorResult
Sortie  : FinalResult
GR-02   : seul RuleEngine produit le verdict final
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from core.models import FinalResult, LuminosityResult, ProductRules, SeverityLevel
from core.rule_engine import RuleEngine
from core.tier_result import TierLevel, TierOrchestratorResult, TierVerdict

logger = logging.getLogger(__name__)


class S5RuleEngineStage:
    """
    Stage 5 — RuleEngine.

    Reçoit TierOrchestratorResult, délègue à RuleEngine pour le verdict final,
    et construit FinalResult (frozen — GR-07).
    """

    def __init__(
        self,
        rule_engine:    RuleEngine,
        product_rules:  ProductRules,
        model_versions: dict[str, str],
    ) -> None:
        self._rule_engine    = rule_engine
        self._product_rules  = product_rules
        self._model_versions = model_versions

    def process(
        self,
        orch_result: TierOrchestratorResult,
        luminosity:  Optional[LuminosityResult] = None,
        pipeline_ms: float = 0.0,
    ) -> FinalResult:
        """
        Produit le FinalResult depuis TierOrchestratorResult.

        Returns:
            FinalResult frozen — jamais None (GR-11, GR-07).
        """
        # Construire le dict des verdicts disponibles
        tier_verdicts: dict[str, TierVerdict] = {
            "CRITICAL": orch_result.critical,
        }
        if orch_result.major is not None:
            tier_verdicts["MAJOR"] = orch_result.major
        if orch_result.minor is not None:
            tier_verdicts["MINOR"] = orch_result.minor

        # Verdict global via RuleEngine (GR-02)
        verdict, severity, fail_tier = self._rule_engine.evaluate_final(tier_verdicts)

        # Collecter les fail_reasons globales
        all_fail_reasons: list[str] = []
        for tv in tier_verdicts.values():
            all_fail_reasons.extend(tv.fail_reasons)
        # §18.3 : luminosité CRITICAL → flag prioritaire dans fail_reasons
        if luminosity is not None and luminosity.critical:
            all_fail_reasons.insert(0, "LUMINOSITY_CRITICAL")

        # Scores par tier
        tier_scores = {name: tv.tier_score for name, tv in tier_verdicts.items()}

        # LuminosityResult factice si non fourni
        if luminosity is None:
            luminosity = LuminosityResult(
                value=128.0, ref_mean=128.0, delta_percent=0.0,
                ok=True, warning=False, critical=False,
            )

        product_id = self._product_rules.product_id

        result = FinalResult(
            frame_id=str(uuid.uuid4()),
            product_id=product_id,
            model_versions=dict(self._model_versions),
            verdict=verdict,
            severity=severity,
            fail_tier=fail_tier,
            fail_reasons=tuple(all_fail_reasons),
            tier_verdicts=tier_verdicts,
            tier_scores=tier_scores,
            llm_explanation=None,
            pipeline_ms=round(pipeline_ms, 2),
            background_complete=not orch_result.fail_fast,
            luminosity_result=luminosity,
            timestamp=time.time(),
        )

        logger.info(
            "S5: verdict=%s severity=%s fail_tier=%s fail_reasons=%s",
            result.verdict, result.severity.value,
            result.fail_tier.value if result.fail_tier else None,
            result.fail_reasons,
        )
        return result
