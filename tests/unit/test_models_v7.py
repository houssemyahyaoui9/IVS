"""
Gate G-01 — Models v7.0
§5 : ObserverSignal · TierVerdict · FinalResult · ProductRules
"""
import time
import pytest

from core.tier_result import TierLevel, ObserverSignal, TierVerdict, TierOrchestratorResult
from core.models import (
    SeverityLevel, SystemState, SwitchResult, LearningDecision,
    PhysicalDimensions, CameraResolution, BoundingBox,
    LuminosityResult, LLMExplanation,
    CriterionRule, ProductRules,
    LogoDefinition, ProductDefinition,
    FinalResult,
)
from core.exceptions import ConfigValidationError


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_signal(
    observer_id: str = "yolo_v8x",
    tier: TierLevel = TierLevel.CRITICAL,
    passed: bool = True,
    confidence: float = 0.92,
    value: float = 0.92,
    threshold: float = 0.70,
    latency_ms: float = 12.0,
) -> ObserverSignal:
    return ObserverSignal(
        observer_id=observer_id,
        tier=tier,
        passed=passed,
        confidence=confidence,
        value=value,
        threshold=threshold,
        latency_ms=latency_ms,
    )


def _make_tier_verdict(
    tier: TierLevel = TierLevel.CRITICAL,
    passed: bool = True,
) -> TierVerdict:
    return TierVerdict(
        tier=tier,
        passed=passed,
        fail_reasons=() if passed else ("LOGO_ABSENT",),
        signals=(_make_signal(tier=tier),),
        tier_score=0.92 if passed else 0.10,
        completed=True,
        latency_ms=15.0,
    )


def _make_luminosity() -> LuminosityResult:
    return LuminosityResult(
        value=128.0, ref_mean=130.0,
        delta_percent=1.5,
        ok=True, warning=False, critical=False,
    )


def _make_final_result(verdict: str = "OK") -> FinalResult:
    critical_tv = _make_tier_verdict(TierLevel.CRITICAL, passed=(verdict != "NOK"))
    major_tv    = _make_tier_verdict(TierLevel.MAJOR,    passed=True)
    minor_tv    = _make_tier_verdict(TierLevel.MINOR,    passed=True)
    return FinalResult(
        frame_id="frame_001",
        product_id="prod_001",
        model_versions={"yolo": "v1", "sift": "v1"},
        verdict=verdict,
        severity=SeverityLevel.ACCEPTABLE if verdict == "OK" else SeverityLevel.REJECT,
        fail_tier=None if verdict == "OK" else TierLevel.CRITICAL,
        fail_reasons=() if verdict == "OK" else ("LOGO_ABSENT",),
        tier_verdicts={
            "CRITICAL": critical_tv,
            "MAJOR":    major_tv,
            "MINOR":    minor_tv,
        },
        tier_scores={"CRITICAL": 0.92, "MAJOR": 0.88, "MINOR": 0.95},
        llm_explanation=None,
        pipeline_ms=45.0,
        background_complete=True,
        luminosity_result=_make_luminosity(),
        timestamp=time.time(),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-A  ObserverSignal frozen
# ─────────────────────────────────────────────────────────────────────────────

class TestObserverSignal:
    def test_frozen_raises_on_assign(self):
        sig = _make_signal()
        with pytest.raises(Exception):  # FrozenInstanceError
            sig.passed = False  # type: ignore[misc]

    def test_confidence_out_of_range(self):
        with pytest.raises(ValueError):
            _make_signal(confidence=1.5)

    def test_confidence_negative(self):
        with pytest.raises(ValueError):
            _make_signal(confidence=-0.1)

    def test_value_negative(self):
        with pytest.raises(ValueError):
            _make_signal(value=-1.0)

    def test_latency_negative(self):
        with pytest.raises(ValueError):
            _make_signal(latency_ms=-0.001)

    def test_empty_observer_id(self):
        with pytest.raises(ValueError):
            _make_signal(observer_id="")

    def test_details_default_empty(self):
        sig = _make_signal()
        assert sig.details == {}

    def test_error_msg_default_none(self):
        sig = _make_signal()
        assert sig.error_msg is None

    def test_valid_signal_with_details(self):
        sig = ObserverSignal(
            observer_id="sift",
            tier=TierLevel.CRITICAL,
            passed=True,
            confidence=0.85,
            value=0.85,
            threshold=0.70,
            latency_ms=8.0,
            details={"match_count": 42, "position_delta_mm": 0.5},
        )
        assert sig.details["match_count"] == 42

    def test_tier_level_assignment(self):
        for tier in TierLevel:
            sig = _make_signal(tier=tier)
            assert sig.tier == tier


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-B  TierVerdict frozen
# ─────────────────────────────────────────────────────────────────────────────

class TestTierVerdict:
    def test_frozen_raises_on_assign(self):
        tv = _make_tier_verdict()
        with pytest.raises(Exception):
            tv.passed = False  # type: ignore[misc]

    def test_tier_score_out_of_range_high(self):
        with pytest.raises(ValueError):
            TierVerdict(
                tier=TierLevel.CRITICAL,
                passed=True,
                fail_reasons=(),
                signals=(_make_signal(),),
                tier_score=1.01,
                completed=True,
                latency_ms=10.0,
            )

    def test_tier_score_out_of_range_low(self):
        with pytest.raises(ValueError):
            TierVerdict(
                tier=TierLevel.CRITICAL,
                passed=False,
                fail_reasons=("ERR",),
                signals=(_make_signal(),),
                tier_score=-0.01,
                completed=True,
                latency_ms=10.0,
            )

    def test_latency_negative(self):
        with pytest.raises(ValueError):
            TierVerdict(
                tier=TierLevel.MAJOR,
                passed=True,
                fail_reasons=(),
                signals=(),
                tier_score=0.80,
                completed=True,
                latency_ms=-1.0,
            )

    def test_fail_reasons_tuple(self):
        tv = _make_tier_verdict(passed=False)
        assert isinstance(tv.fail_reasons, tuple)
        assert len(tv.fail_reasons) >= 1

    def test_completed_false_fail_fast(self):
        tv = TierVerdict(
            tier=TierLevel.MAJOR,
            passed=False,
            fail_reasons=(),
            signals=(),
            tier_score=0.0,
            completed=False,   # background non terminé
            latency_ms=0.0,
        )
        assert tv.completed is False


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-C  TierOrchestratorResult
# ─────────────────────────────────────────────────────────────────────────────

class TestTierOrchestratorResult:
    def test_fail_fast_no_major_minor(self):
        """CRITICAL fail → fail_fast=True, major/minor None."""
        tor = TierOrchestratorResult(
            critical=_make_tier_verdict(passed=False),
            major=None,
            minor=None,
            fail_fast=True,
        )
        assert tor.fail_fast is True
        assert tor.major is None

    def test_no_fail_fast_requires_major_minor(self):
        with pytest.raises(ValueError):
            TierOrchestratorResult(
                critical=_make_tier_verdict(passed=True),
                major=None,
                minor=None,
                fail_fast=False,
            )

    def test_all_pass_full_result(self):
        tor = TierOrchestratorResult(
            critical=_make_tier_verdict(TierLevel.CRITICAL, passed=True),
            major=_make_tier_verdict(TierLevel.MAJOR, passed=True),
            minor=_make_tier_verdict(TierLevel.MINOR, passed=True),
            fail_fast=False,
        )
        assert tor.fail_fast is False
        assert tor.critical.passed is True


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-D  FinalResult frozen + tier_verdicts valide
# ─────────────────────────────────────────────────────────────────────────────

class TestFinalResult:
    def test_frozen_raises_on_assign(self):
        fr = _make_final_result()
        with pytest.raises(Exception):
            fr.verdict = "NOK"  # type: ignore[misc]

    def test_tier_verdicts_non_empty(self):
        fr = _make_final_result()
        assert len(fr.tier_verdicts) > 0

    def test_tier_verdicts_contains_critical(self):
        fr = _make_final_result()
        assert "CRITICAL" in fr.tier_verdicts

    def test_tier_verdicts_values_are_tier_verdict(self):
        fr = _make_final_result()
        for key, tv in fr.tier_verdicts.items():
            assert isinstance(tv, TierVerdict), f"tier_verdicts['{key}'] n'est pas TierVerdict"

    def test_tier_verdicts_empty_raises(self):
        with pytest.raises(ValueError):
            FinalResult(
                frame_id="f", product_id="p",
                model_versions={},
                verdict="OK",
                severity=SeverityLevel.ACCEPTABLE,
                fail_tier=None, fail_reasons=(),
                tier_verdicts={},      # ← vide → doit lever ValueError
                tier_scores={},
                llm_explanation=None,
                pipeline_ms=10.0,
                background_complete=True,
                luminosity_result=_make_luminosity(),
                timestamp=time.time(),
            )

    def test_tier_verdicts_missing_critical_raises(self):
        with pytest.raises(ValueError):
            FinalResult(
                frame_id="f", product_id="p",
                model_versions={},
                verdict="OK",
                severity=SeverityLevel.ACCEPTABLE,
                fail_tier=None, fail_reasons=(),
                tier_verdicts={"MAJOR": _make_tier_verdict(TierLevel.MAJOR)},
                tier_scores={"MAJOR": 0.80},
                llm_explanation=None,
                pipeline_ms=10.0,
                background_complete=True,
                luminosity_result=_make_luminosity(),
                timestamp=time.time(),
            )

    def test_invalid_verdict_raises(self):
        with pytest.raises(ValueError):
            FinalResult(
                frame_id="f", product_id="p",
                model_versions={},
                verdict="MAYBE",  # ← invalide
                severity=SeverityLevel.ACCEPTABLE,
                fail_tier=None, fail_reasons=(),
                tier_verdicts={"CRITICAL": _make_tier_verdict()},
                tier_scores={"CRITICAL": 0.90},
                llm_explanation=None,
                pipeline_ms=10.0,
                background_complete=True,
                luminosity_result=_make_luminosity(),
                timestamp=time.time(),
            )

    def test_negative_pipeline_ms_raises(self):
        with pytest.raises(ValueError):
            FinalResult(
                frame_id="f", product_id="p",
                model_versions={},
                verdict="OK",
                severity=SeverityLevel.ACCEPTABLE,
                fail_tier=None, fail_reasons=(),
                tier_verdicts={"CRITICAL": _make_tier_verdict()},
                tier_scores={"CRITICAL": 0.90},
                llm_explanation=None,
                pipeline_ms=-1.0,  # ← négatif
                background_complete=True,
                luminosity_result=_make_luminosity(),
                timestamp=time.time(),
            )

    def test_ok_result(self):
        fr = _make_final_result("OK")
        assert fr.verdict == "OK"
        assert fr.fail_tier is None
        assert len(fr.fail_reasons) == 0

    def test_nok_result(self):
        fr = _make_final_result("NOK")
        assert fr.verdict == "NOK"
        assert fr.severity == SeverityLevel.REJECT
        assert fr.fail_tier == TierLevel.CRITICAL

    def test_review_verdict(self):
        tv = _make_tier_verdict()
        fr = FinalResult(
            frame_id="f", product_id="p",
            model_versions={},
            verdict="REVIEW",
            severity=SeverityLevel.REVIEW,
            fail_tier=None, fail_reasons=("SURFACE_BORDERLINE",),
            tier_verdicts={"CRITICAL": tv},
            tier_scores={"CRITICAL": 0.80},
            llm_explanation=None,
            pipeline_ms=55.0,
            background_complete=False,
            luminosity_result=_make_luminosity(),
            timestamp=time.time(),
        )
        assert fr.verdict == "REVIEW"


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-E  ProductRules.critical_criteria filtre correct
# ─────────────────────────────────────────────────────────────────────────────

class TestProductRules:
    def _make_rules(self) -> ProductRules:
        return ProductRules(
            product_id="prod_001",
            criteria=(
                CriterionRule("logo_lion",    "Logo Lion",    TierLevel.CRITICAL, "yolo",    0.70, True,  True),
                CriterionRule("logo_pos",     "Position Logo",TierLevel.CRITICAL, "sift",    0.70, True,  True),
                CriterionRule("color_logo",   "Couleur Logo", TierLevel.MAJOR,    "color",   8.0,  True,  True),
                CriterionRule("surface_ok",   "Surface OK",   TierLevel.MINOR,    "surface", 0.30, True,  True),
                CriterionRule("ocr_lot",      "Numéro Lot",   TierLevel.MINOR,    "ocr",     0.80, True,  False),
            ),
        )

    def test_critical_criteria_count(self):
        rules = self._make_rules()
        assert len(rules.critical_criteria) == 2

    def test_critical_criteria_all_critical(self):
        rules = self._make_rules()
        for c in rules.critical_criteria:
            assert c.tier == TierLevel.CRITICAL

    def test_major_criteria_count(self):
        rules = self._make_rules()
        assert len(rules.major_criteria) == 1
        assert rules.major_criteria[0].criterion_id == "color_logo"

    def test_minor_criteria_count(self):
        rules = self._make_rules()
        assert len(rules.minor_criteria) == 2

    def test_minor_non_mandatory(self):
        rules = self._make_rules()
        non_mandatory = [c for c in rules.minor_criteria if not c.mandatory]
        assert len(non_mandatory) == 1
        assert non_mandatory[0].criterion_id == "ocr_lot"

    def test_product_rules_frozen(self):
        rules = self._make_rules()
        with pytest.raises(Exception):
            rules.product_id = "other"  # type: ignore[misc]

    def test_empty_product_id_raises(self):
        with pytest.raises(ConfigValidationError):
            ProductRules(product_id="", criteria=())

    def test_criterion_negative_threshold_raises(self):
        with pytest.raises(ConfigValidationError):
            CriterionRule("c", "label", TierLevel.CRITICAL, "obs", -1.0, True, True)

    def test_criterion_empty_id_raises(self):
        with pytest.raises(ConfigValidationError):
            CriterionRule("", "label", TierLevel.CRITICAL, "obs", 0.70, True, True)


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-F  SeverityLevel : 6 niveaux
# ─────────────────────────────────────────────────────────────────────────────

class TestSeverityLevel:
    def test_six_levels(self):
        levels = list(SeverityLevel)
        assert len(levels) == 6

    def test_level_names(self):
        names = {s.value for s in SeverityLevel}
        assert names == {"EXCELLENT", "ACCEPTABLE", "REVIEW", "DEFECT_2", "DEFECT_1", "REJECT"}

    def test_tier_mapping(self):
        """Mapping CLAUDE.md : CRITICAL→REJECT · MAJOR→DEFECT_1 · MINOR mandatory→DEFECT_2"""
        assert SeverityLevel.REJECT.value   == "REJECT"
        assert SeverityLevel.DEFECT_1.value == "DEFECT_1"
        assert SeverityLevel.DEFECT_2.value == "DEFECT_2"
        assert SeverityLevel.REVIEW.value   == "REVIEW"


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-G  SystemState : 9 états §4
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemState:
    def test_nine_states(self):
        assert len(list(SystemState)) == 9

    def test_state_names(self):
        names = {s.value for s in SystemState}
        expected = {
            "IDLE_NO_PRODUCT", "IMAGE_CAPTURE", "CALIBRATING",
            "TRAINING", "IDLE_READY", "RUNNING",
            "REVIEW", "ERROR", "SHUTTING_DOWN",
        }
        assert names == expected


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-H  ConfigValidationError levée si dimensions négatives
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigValidationError:
    def test_physical_dimensions_negative_width(self):
        with pytest.raises(ConfigValidationError):
            PhysicalDimensions(width_mm=-1.0, height_mm=100.0)

    def test_physical_dimensions_negative_height(self):
        with pytest.raises(ConfigValidationError):
            PhysicalDimensions(width_mm=100.0, height_mm=-5.0)

    def test_physical_dimensions_zero_width(self):
        with pytest.raises(ConfigValidationError):
            PhysicalDimensions(width_mm=0.0, height_mm=100.0)

    def test_physical_dimensions_valid(self):
        pd = PhysicalDimensions(width_mm=150.0, height_mm=80.0)
        assert pd.width_mm == 150.0

    def test_camera_resolution_invalid(self):
        with pytest.raises(ConfigValidationError):
            CameraResolution(width=0, height=1080)

    def test_product_definition_negative_width(self):
        with pytest.raises(ConfigValidationError):
            ProductDefinition(
                product_id="p", name="Test", version="1.0",
                width_mm=-10.0, height_mm=80.0,
                logo_definitions=(),
            )

    def test_product_definition_negative_height(self):
        with pytest.raises(ConfigValidationError):
            ProductDefinition(
                product_id="p", name="Test", version="1.0",
                width_mm=150.0, height_mm=0.0,
                logo_definitions=(),
            )

    def test_product_definition_empty_id(self):
        with pytest.raises(ConfigValidationError):
            ProductDefinition(
                product_id="", name="Test", version="1.0",
                width_mm=150.0, height_mm=80.0,
                logo_definitions=(),
            )

    def test_config_validation_error_is_value_error(self):
        """ConfigValidationError hérite de ValueError."""
        with pytest.raises(ValueError):
            PhysicalDimensions(width_mm=-1.0, height_mm=100.0)


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-I  BoundingBox : cx, cy, to_pixel
# ─────────────────────────────────────────────────────────────────────────────

class TestBoundingBox:
    def test_cx_cy(self):
        bb = BoundingBox(x=10.0, y=20.0, w=50.0, h=40.0)
        assert bb.cx == pytest.approx(35.0)
        assert bb.cy == pytest.approx(40.0)

    def test_to_pixel(self):
        bb = BoundingBox(x=10.0, y=5.0, w=50.0, h=30.0)
        ppm = 2.0  # 2 pixels par mm
        px = bb.to_pixel(ppm)
        assert px.x == pytest.approx(20.0)
        assert px.y == pytest.approx(10.0)
        assert px.w == pytest.approx(100.0)
        assert px.h == pytest.approx(60.0)

    def test_frozen(self):
        bb = BoundingBox(x=0.0, y=0.0, w=10.0, h=10.0)
        with pytest.raises(Exception):
            bb.w = 20.0  # type: ignore[misc]

    def test_zero_w_raises(self):
        with pytest.raises(ConfigValidationError):
            BoundingBox(x=0.0, y=0.0, w=0.0, h=10.0)

    def test_negative_h_raises(self):
        with pytest.raises(ConfigValidationError):
            BoundingBox(x=0.0, y=0.0, w=10.0, h=-1.0)


# ─────────────────────────────────────────────────────────────────────────────
#  G-01-J  LLMExplanation frozen
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMExplanation:
    def test_frozen(self):
        llm = LLMExplanation(
            summary="Défaut surface détecté",
            defect_detail="Rayure 2cm zone logo",
            probable_cause="Mauvaise manipulation",
            recommendation="Vérifier poste emballage",
            latency_ms=250.0,
        )
        with pytest.raises(Exception):
            llm.summary = "other"  # type: ignore[misc]

    def test_negative_latency_raises(self):
        with pytest.raises(ValueError):
            LLMExplanation(
                summary="s", defect_detail="d",
                probable_cause="c", recommendation="r",
                latency_ms=-1.0,
            )
