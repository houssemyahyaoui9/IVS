"""
LuminosityChecker + LuminosityIndicator + S5 propagation — Gate G-28
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from camera.camera_manager import RawFrame
from core.models import LuminosityResult
from pipeline.stages.luminosity_checker import LuminosityChecker


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _frame_with_mean(mean: int) -> RawFrame:
    img = np.full((100, 100, 3), mean, dtype=np.uint8)
    return RawFrame(frame_id="f1", image=img, timestamp=0.0)


def _checker_with_ref(ref_mean: float, *, warn_pct: float = 15.0,
                      crit_pct: float = 30.0, tmp_path: Path = None) -> LuminosityChecker:
    c = LuminosityChecker(warn_percent=warn_pct, critical_percent=crit_pct)
    if tmp_path is not None:
        d = tmp_path / "calibration"
        d.mkdir(parents=True, exist_ok=True)
        (d / "brightness_reference.json").write_text(json.dumps({
            "mean": ref_mean,
            "warn_percent": warn_pct,
            "critical_percent": crit_pct,
        }))
        c.load_reference(d)
    else:
        c._ref_mean = ref_mean  # noqa: SLF001
    return c


# ─────────────────────────────────────────────────────────────────────────────
#  LuminosityResult.severity (§18.3)
# ─────────────────────────────────────────────────────────────────────────────

class TestLuminosityResultSeverity:
    def test_ok_severity(self) -> None:
        r = LuminosityResult(value=130, ref_mean=128, delta_percent=1.5,
                             ok=True, warning=False, critical=False)
        assert r.severity == "OK"

    def test_warning_severity(self) -> None:
        r = LuminosityResult(value=150, ref_mean=128, delta_percent=17.0,
                             ok=False, warning=True, critical=False)
        assert r.severity == "WARNING"

    def test_critical_severity(self) -> None:
        r = LuminosityResult(value=200, ref_mean=128, delta_percent=56.0,
                             ok=False, warning=False, critical=True)
        assert r.severity == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
#  LuminosityChecker.check
# ─────────────────────────────────────────────────────────────────────────────

class TestLuminosityChecker:
    def test_check_ok_within_warn(self) -> None:
        c = _checker_with_ref(128.0)
        # 140 vs 128 → 9.4% < 15%
        r = c.check(_frame_with_mean(140))
        assert r.ok is True
        assert r.warning is False
        assert r.critical is False
        assert r.severity == "OK"

    def test_check_warning_band(self) -> None:
        c = _checker_with_ref(100.0)
        # 120 vs 100 → 20% (entre 15 et 30)
        r = c.check(_frame_with_mean(120))
        assert r.warning is True
        assert r.critical is False
        assert r.severity == "WARNING"

    def test_check_critical(self) -> None:
        c = _checker_with_ref(100.0)
        # 200 vs 100 → 100% > 30%
        r = c.check(_frame_with_mean(200))
        assert r.critical is True
        assert r.severity == "CRITICAL"

    def test_check_zero_ref_no_div_zero(self) -> None:
        c = _checker_with_ref(0.0)
        r = c.check(_frame_with_mean(50))
        # +1e-6 protège la division — résultat non NaN/Inf
        assert np.isfinite(r.delta_percent)
        assert r.delta_percent > 0

    def test_check_accepts_optional_product_def(self) -> None:
        c = _checker_with_ref(128.0)
        # product_def=None autorisé (signature §18.3)
        r = c.check(_frame_with_mean(140), product_def=None)
        assert isinstance(r, LuminosityResult)

    def test_load_reference_from_calibration(self, tmp_path: Path) -> None:
        c = _checker_with_ref(75.0, tmp_path=tmp_path)
        assert c.is_loaded
        assert c.ref_mean == 75.0


# ─────────────────────────────────────────────────────────────────────────────
#  S5 — propagation LUMINOSITY_CRITICAL dans fail_reasons
# ─────────────────────────────────────────────────────────────────────────────

class TestS5LuminosityCritical:
    def _build_s5(self):
        from core.rule_engine import RuleEngine
        from core.models import ProductRules, CriterionRule
        from core.tier_result import TierLevel
        from pipeline.stages.s5_rule_engine_stage import S5RuleEngineStage

        rule = CriterionRule(
            criterion_id="c1", label="dummy", tier=TierLevel.CRITICAL,
            observer_id="yolo_v8x", threshold=0.7, enabled=True, mandatory=True,
        )
        rules = ProductRules(product_id="p1", criteria=(rule,))
        engine = RuleEngine()
        return S5RuleEngineStage(engine, rules, model_versions={"yolo": "v1"}), rules

    def _ok_orch_result(self):
        from core.tier_result import (
            TierLevel, TierVerdict, TierOrchestratorResult,
        )
        critical = TierVerdict(
            tier=TierLevel.CRITICAL, passed=True, tier_score=0.95,
            fail_reasons=(), signals=(), completed=True, latency_ms=5.0,
        )
        # fail_fast=True : seul CRITICAL est présent → satisfait __post_init__
        return TierOrchestratorResult(
            critical=critical, major=None, minor=None, fail_fast=True,
        )

    def test_critical_luminosity_added_to_fail_reasons(self) -> None:
        s5, _ = self._build_s5()
        lum = LuminosityResult(
            value=200, ref_mean=128, delta_percent=56.0,
            ok=False, warning=False, critical=True,
        )
        result = s5.process(self._ok_orch_result(), luminosity=lum,
                            pipeline_ms=12.0)
        assert "LUMINOSITY_CRITICAL" in result.fail_reasons
        assert result.fail_reasons[0] == "LUMINOSITY_CRITICAL"

    def test_warning_luminosity_not_added(self) -> None:
        s5, _ = self._build_s5()
        lum = LuminosityResult(
            value=150, ref_mean=128, delta_percent=17.0,
            ok=False, warning=True, critical=False,
        )
        result = s5.process(self._ok_orch_result(), luminosity=lum,
                            pipeline_ms=12.0)
        assert "LUMINOSITY_CRITICAL" not in result.fail_reasons

    def test_ok_luminosity_not_added(self) -> None:
        s5, _ = self._build_s5()
        lum = LuminosityResult(
            value=130, ref_mean=128, delta_percent=1.5,
            ok=True, warning=False, critical=False,
        )
        result = s5.process(self._ok_orch_result(), luminosity=lum,
                            pipeline_ms=12.0)
        assert "LUMINOSITY_CRITICAL" not in result.fail_reasons


# ─────────────────────────────────────────────────────────────────────────────
#  LuminosityIndicator (UI)
# ─────────────────────────────────────────────────────────────────────────────

class TestLuminosityIndicator:
    @pytest.fixture(autouse=True)
    def _qt(self, qapp):
        return qapp

    def test_initial_state(self) -> None:
        from ui.components.luminosity_indicator import LuminosityIndicator
        ind = LuminosityIndicator()
        assert ind.severity == "OK"
        assert ind.severity_color == "green"
        assert "—" in ind.text

    def test_update_ok_green(self) -> None:
        from ui.components.luminosity_indicator import LuminosityIndicator
        ind = LuminosityIndicator()
        ind.on_luminosity_update(LuminosityResult(
            value=187, ref_mean=180, delta_percent=3.9,
            ok=True, warning=False, critical=False,
        ))
        assert ind.severity == "OK"
        assert ind.severity_color == "green"
        assert ind.text == "☀ 187"

    def test_update_warning_yellow(self) -> None:
        from ui.components.luminosity_indicator import LuminosityIndicator
        ind = LuminosityIndicator()
        ind.on_luminosity_update(LuminosityResult(
            value=150, ref_mean=128, delta_percent=17.0,
            ok=False, warning=True, critical=False,
        ))
        assert ind.severity == "WARNING"
        assert ind.severity_color == "yellow"

    def test_update_critical_red(self) -> None:
        from ui.components.luminosity_indicator import LuminosityIndicator
        ind = LuminosityIndicator()
        ind.on_luminosity_update(LuminosityResult(
            value=210, ref_mean=128, delta_percent=64.0,
            ok=False, warning=False, critical=True,
        ))
        assert ind.severity == "CRITICAL"
        assert ind.severity_color == "red"

    def test_tooltip_contains_numeric_values(self) -> None:
        from ui.components.luminosity_indicator import LuminosityIndicator
        ind = LuminosityIndicator()
        ind.on_luminosity_update(LuminosityResult(
            value=187.4, ref_mean=180.0, delta_percent=4.1,
            ok=True, warning=False, critical=False,
        ))
        tip = ind.toolTip()
        assert "187" in tip
        assert "180" in tip
        assert "4.1" in tip
