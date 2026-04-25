"""
WatchdogManager — Gate G-26
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from core.models import SystemState
from core.watchdog_manager import WatchdogManager


def _ctrl(state: SystemState) -> MagicMock:
    c = MagicMock()
    c._state = state
    c.get_state.side_effect = lambda: c._state
    return c


class TestWatchdogManager:
    def test_invalid_params_raise(self) -> None:
        ctrl = _ctrl(SystemState.IDLE_READY)
        with pytest.raises(ValueError):
            WatchdogManager(ctrl, timeout_s=0)
        with pytest.raises(ValueError):
            WatchdogManager(ctrl, check_interval_s=0)
        with pytest.raises(ValueError):
            WatchdogManager(ctrl, max_recoveries=-1)

    def test_heartbeat_resets_timer(self) -> None:
        ctrl = _ctrl(SystemState.RUNNING)
        wd = WatchdogManager(ctrl, timeout_s=0.2, check_interval_s=0.05,
                             max_recoveries=3)
        time.sleep(0.1)
        wd.heartbeat("frame_42")
        # Force un check immédiat sans attendre l'intervalle
        wd._check()
        assert wd.recovery_count == 0
        assert ctrl.emergency_stop.call_count == 0

    def test_state_not_running_resets_baseline(self) -> None:
        ctrl = _ctrl(SystemState.IDLE_READY)
        wd = WatchdogManager(ctrl, timeout_s=0.05, check_interval_s=0.05,
                             max_recoveries=3)
        time.sleep(0.2)
        wd._check()
        assert wd.recovery_count == 0
        ctrl.emergency_stop.assert_not_called()

    def test_timeout_in_running_triggers_recovery(self) -> None:
        ctrl = _ctrl(SystemState.RUNNING)

        # emergency_stop fait basculer vers ERROR puis IDLE_READY
        # (simule la séquence FSM réelle).
        def _emergency():
            ctrl._state = SystemState.IDLE_READY
        ctrl.emergency_stop.side_effect = _emergency

        wd = WatchdogManager(ctrl, timeout_s=0.05, check_interval_s=10,
                             max_recoveries=3)
        time.sleep(0.1)  # provoque elapsed > timeout
        wd._check()

        assert wd.recovery_count == 1
        ctrl.emergency_stop.assert_called_once()
        ctrl.transition.assert_not_called()

    def test_max_recoveries_exceeded_transitions_error(self) -> None:
        ctrl = _ctrl(SystemState.RUNNING)

        def _emergency():
            ctrl._state = SystemState.IDLE_READY
            # Repasse en RUNNING pour le test (sinon _check reset baseline)
            ctrl._state = SystemState.RUNNING
        ctrl.emergency_stop.side_effect = _emergency

        wd = WatchdogManager(ctrl, timeout_s=0.05, check_interval_s=10,
                             max_recoveries=2)
        # 1ère et 2ème récupération autorisées
        time.sleep(0.1); wd._check()
        time.sleep(0.1); wd._check()
        assert wd.recovery_count == 2
        # 3ème déclenche transition ERROR (sans emergency_stop)
        time.sleep(0.1); wd._check()
        assert wd.recovery_count == 3
        ctrl.transition.assert_called_once()
        # Vérifier le dernier appel : SystemState.ERROR
        assert ctrl.transition.call_args[0][0] == SystemState.ERROR

    def test_start_stop_thread(self) -> None:
        ctrl = _ctrl(SystemState.IDLE_READY)
        wd = WatchdogManager(ctrl, timeout_s=1.0, check_interval_s=0.05,
                             max_recoveries=3)
        wd.start()
        assert wd.is_running
        time.sleep(0.15)
        wd.stop()
        assert not wd.is_running

    def test_idempotent_start(self) -> None:
        ctrl = _ctrl(SystemState.IDLE_READY)
        wd = WatchdogManager(ctrl, timeout_s=1.0, check_interval_s=0.5,
                             max_recoveries=3)
        wd.start()
        thread1 = wd._thread
        wd.start()  # second appel sans effet
        assert wd._thread is thread1
        wd.stop()


class TestS8Heartbeat:
    def test_s8_calls_heartbeat_with_frame_id(self) -> None:
        from pipeline.stages.s8_output import S8Output
        wd = MagicMock()
        s8 = S8Output(watchdog=wd)
        result = MagicMock()
        result.frame_id = "frame_xyz"
        result.verdict  = "OK"
        s8.process(result)
        wd.heartbeat.assert_called_once_with("frame_xyz")

    def test_s8_heartbeat_failure_does_not_propagate(self) -> None:
        from pipeline.stages.s8_output import S8Output
        wd = MagicMock()
        wd.heartbeat.side_effect = RuntimeError("boom")
        s8 = S8Output(watchdog=wd)
        result = MagicMock()
        result.frame_id = "frame_x"
        result.verdict  = "OK"
        # ne lève pas
        s8.process(result)
        wd.heartbeat.assert_called_once()
