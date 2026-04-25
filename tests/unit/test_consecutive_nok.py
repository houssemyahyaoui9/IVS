"""
ConsecutiveNOKWatcher — Gate G-27
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from monitoring.consecutive_nok_watcher import ConsecutiveNOKWatcher


# ─────────────────────────────────────────────────────────────────────────────
#  Construction
# ─────────────────────────────────────────────────────────────────────────────

class TestConstruction:
    def test_invalid_alert_threshold(self) -> None:
        with pytest.raises(ValueError):
            ConsecutiveNOKWatcher(alert_threshold=0)

    def test_invalid_stop_threshold(self) -> None:
        with pytest.raises(ValueError):
            ConsecutiveNOKWatcher(stop_threshold=0)

    def test_stop_lt_alert_rejected(self) -> None:
        with pytest.raises(ValueError):
            ConsecutiveNOKWatcher(alert_threshold=10, stop_threshold=5)

    def test_default_thresholds(self) -> None:
        w = ConsecutiveNOKWatcher()
        assert w.alert_threshold == 5
        assert w.stop_threshold == 10
        assert w.counter == 0
        assert w.is_stopped is False


# ─────────────────────────────────────────────────────────────────────────────
#  Comptage et reset
# ─────────────────────────────────────────────────────────────────────────────

class TestCounter:
    def test_nok_increments_counter(self) -> None:
        w = ConsecutiveNOKWatcher()
        for _ in range(3):
            w.on_result("NOK")
        assert w.counter == 3

    def test_ok_resets_counter(self) -> None:
        w = ConsecutiveNOKWatcher()
        w.on_result("NOK")
        w.on_result("NOK")
        w.on_result("OK")
        assert w.counter == 0

    def test_review_resets_counter(self) -> None:
        w = ConsecutiveNOKWatcher()
        w.on_result("NOK")
        w.on_result("NOK")
        w.on_result("REVIEW")
        assert w.counter == 0

    def test_lowercase_verdict_handled(self) -> None:
        w = ConsecutiveNOKWatcher()
        w.on_result("nok")
        w.on_result("nok")
        assert w.counter == 2


# ─────────────────────────────────────────────────────────────────────────────
#  Alert / Stop callbacks
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertStop:
    def test_alert_at_threshold(self) -> None:
        on_alert = MagicMock()
        on_stop  = MagicMock()
        w = ConsecutiveNOKWatcher(
            alert_threshold=5, stop_threshold=10,
            on_alert=on_alert, on_stop=on_stop,
        )
        for _ in range(4):
            w.on_result("NOK")
        on_alert.assert_not_called()
        w.on_result("NOK")  # 5e
        on_alert.assert_called_once_with(5)
        on_stop.assert_not_called()

    def test_alert_re_emitted_each_nok_until_stop(self) -> None:
        on_alert = MagicMock()
        w = ConsecutiveNOKWatcher(
            alert_threshold=3, stop_threshold=10, on_alert=on_alert,
        )
        for _ in range(6):
            w.on_result("NOK")
        # Alerts émises pour count=3,4,5,6 (4 fois)
        assert on_alert.call_count == 4
        assert on_alert.call_args_list[0][0][0] == 3
        assert on_alert.call_args_list[-1][0][0] == 6

    def test_stop_at_threshold_triggers_stop_inspection(self) -> None:
        ctrl     = MagicMock()
        on_stop  = MagicMock()
        on_alert = MagicMock()
        w = ConsecutiveNOKWatcher(
            alert_threshold=5, stop_threshold=10,
            controller=ctrl, on_alert=on_alert, on_stop=on_stop,
        )
        for _ in range(10):
            w.on_result("NOK")
        on_stop.assert_called_once_with(10)
        ctrl.stop_inspection.assert_called_once()
        # Alertes pour count=5..9 = 5 fois (pas pour 10 qui déclenche stop)
        assert on_alert.call_count == 5
        assert w.is_stopped is True

    def test_stopped_state_blocks_further_events(self) -> None:
        ctrl    = MagicMock()
        on_stop = MagicMock()
        w = ConsecutiveNOKWatcher(
            alert_threshold=2, stop_threshold=3,
            controller=ctrl, on_stop=on_stop,
        )
        for _ in range(3):
            w.on_result("NOK")
        assert on_stop.call_count == 1
        for v in ("NOK", "OK", "NOK", "NOK"):
            w.on_result(v)
        assert on_stop.call_count == 1
        ctrl.stop_inspection.assert_called_once()
        assert w.counter == 3

    def test_callback_exception_does_not_break_watcher(self) -> None:
        on_alert = MagicMock(side_effect=RuntimeError("ui crash"))
        w = ConsecutiveNOKWatcher(alert_threshold=2, on_alert=on_alert)
        w.on_result("NOK")
        w.on_result("NOK")
        assert w.counter == 2


# ─────────────────────────────────────────────────────────────────────────────
#  Reset opérateur
# ─────────────────────────────────────────────────────────────────────────────

class TestResetCounter:
    def test_reset_requires_operator(self) -> None:
        w = ConsecutiveNOKWatcher()
        with pytest.raises(ValueError):
            w.reset_counter("")
        with pytest.raises(ValueError):
            w.reset_counter("   ")

    def test_reset_clears_counter_and_stopped(self) -> None:
        w = ConsecutiveNOKWatcher(alert_threshold=2, stop_threshold=3)
        for _ in range(3):
            w.on_result("NOK")
        assert w.is_stopped is True
        w.reset_counter("op_42")
        assert w.counter == 0
        assert w.is_stopped is False

    def test_after_reset_resumes_counting(self) -> None:
        ctrl    = MagicMock()
        on_stop = MagicMock()
        w = ConsecutiveNOKWatcher(
            alert_threshold=2, stop_threshold=3,
            controller=ctrl, on_stop=on_stop,
        )
        for _ in range(3):
            w.on_result("NOK")
        w.reset_counter("op_99")
        for _ in range(3):
            w.on_result("NOK")
        assert on_stop.call_count == 2
        assert ctrl.stop_inspection.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
#  NOKCounterBadge (UI) — couleur uniquement (banner = QDialog non testable
#  hors session Qt interactive)
# ─────────────────────────────────────────────────────────────────────────────

class TestNOKCounterBadgeColors:
    @pytest.fixture(autouse=True)
    def _qt_app(self, qapp):  # qapp fixture fournie par pytest-qt
        return qapp

    def test_grey_under_3(self) -> None:
        from ui.components.nok_counter_badge import NOKCounterBadge
        b = NOKCounterBadge()
        for n in (0, 1, 2):
            b.update_count(n)
            assert b.color_state == "grey", f"count={n}"

    def test_orange_3_to_4(self) -> None:
        from ui.components.nok_counter_badge import NOKCounterBadge
        b = NOKCounterBadge()
        for n in (3, 4):
            b.update_count(n)
            assert b.color_state == "orange", f"count={n}"

    def test_red_at_5_or_more(self) -> None:
        from ui.components.nok_counter_badge import NOKCounterBadge
        b = NOKCounterBadge()
        for n in (5, 7, 10, 25):
            b.update_count(n)
            assert b.color_state == "red", f"count={n}"

    def test_label_text_updated(self) -> None:
        from ui.components.nok_counter_badge import NOKCounterBadge
        b = NOKCounterBadge()
        b.update_count(7)
        assert "7" in b._label.text()
