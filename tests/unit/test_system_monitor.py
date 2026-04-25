"""
SystemMonitor + SystemStatusBar — Gate G-29
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from monitoring.system_monitor import HostMetricsSnapshot, SystemMonitor


# ─────────────────────────────────────────────────────────────────────────────
#  Construction
# ─────────────────────────────────────────────────────────────────────────────

class TestConstruction:
    def test_invalid_refresh_rejected(self) -> None:
        with pytest.raises(ValueError):
            SystemMonitor(refresh_s=0)

    def test_default_thresholds(self) -> None:
        m = SystemMonitor()
        assert m._temp_warn == 75.0
        assert m._temp_crit == 85.0


# ─────────────────────────────────────────────────────────────────────────────
#  Severity
# ─────────────────────────────────────────────────────────────────────────────

class TestSeverity:
    def _mon(self) -> SystemMonitor:
        return SystemMonitor()

    def test_all_ok(self) -> None:
        m = self._mon()
        sev = m._compute_severity(50.0, 2.0, 8.0, 60.0, 50.0, 250.0)
        assert sev == "OK"

    def test_temp_warning_promotes_severity(self) -> None:
        m = self._mon()
        sev = m._compute_severity(20.0, 1.0, 8.0, 78.0, 10.0, 250.0)
        assert sev == "WARNING"

    def test_temp_critical_dominates(self) -> None:
        m = self._mon()
        sev = m._compute_severity(20.0, 1.0, 8.0, 90.0, 10.0, 250.0)
        assert sev == "CRITICAL"

    def test_cpu_critical(self) -> None:
        m = self._mon()
        sev = m._compute_severity(96.0, 1.0, 8.0, 50.0, 10.0, 250.0)
        assert sev == "CRITICAL"

    def test_temp_none_does_not_throw(self) -> None:
        m = self._mon()
        sev = m._compute_severity(50.0, 2.0, 8.0, None, 50.0, 250.0)
        assert sev == "OK"


# ─────────────────────────────────────────────────────────────────────────────
#  Thermal throttle
# ─────────────────────────────────────────────────────────────────────────────

class TestThermalThrottle:
    def test_above_critical_calls_reduce_fps_once(self) -> None:
        pipeline = MagicMock()
        m = SystemMonitor(pipeline=pipeline, temp_warn=75, temp_crit=85)
        snap = HostMetricsSnapshot(
            cpu_percent=10, ram_used_gb=1, ram_total_gb=8,
            temp_c=90.0, disk_used_gb=10, disk_total_gb=250,
            uptime_s=1000, severity="CRITICAL",
        )
        m._thermal_throttle(snap)
        m._thermal_throttle(snap)  # ne doit pas re-appeler (déjà throttled)
        pipeline.reduce_fps.assert_called_once_with(1)

    def test_throttle_release_below_warn(self) -> None:
        pipeline = MagicMock()
        m = SystemMonitor(pipeline=pipeline, temp_warn=75, temp_crit=85)
        hot = HostMetricsSnapshot(
            cpu_percent=10, ram_used_gb=1, ram_total_gb=8,
            temp_c=90.0, disk_used_gb=10, disk_total_gb=250,
            uptime_s=1, severity="CRITICAL",
        )
        cool = HostMetricsSnapshot(
            cpu_percent=10, ram_used_gb=1, ram_total_gb=8,
            temp_c=70.0, disk_used_gb=10, disk_total_gb=250,
            uptime_s=2, severity="OK",
        )
        m._thermal_throttle(hot)
        assert m._throttled is True
        m._thermal_throttle(cool)
        assert m._throttled is False

    def test_no_throttle_without_pipeline(self) -> None:
        m = SystemMonitor(pipeline=None, temp_crit=85)
        snap = HostMetricsSnapshot(
            cpu_percent=10, ram_used_gb=1, ram_total_gb=8,
            temp_c=99.0, disk_used_gb=10, disk_total_gb=250,
            uptime_s=1, severity="CRITICAL",
        )
        m._thermal_throttle(snap)  # ne lève pas
        assert m._throttled is False

    def test_no_throttle_without_temp_reading(self) -> None:
        pipeline = MagicMock()
        m = SystemMonitor(pipeline=pipeline)
        snap = HostMetricsSnapshot(
            cpu_percent=10, ram_used_gb=1, ram_total_gb=8,
            temp_c=None, disk_used_gb=10, disk_total_gb=250,
            uptime_s=1, severity="OK",
        )
        m._thermal_throttle(snap)
        pipeline.reduce_fps.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
#  get_snapshot + history + dispatch
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotAndDispatch:
    def test_get_snapshot_returns_snapshot(self) -> None:
        m = SystemMonitor()
        snap = m.get_snapshot()
        assert isinstance(snap, HostMetricsSnapshot)
        assert m.last_snapshot is snap

    def test_history_appended(self) -> None:
        m = SystemMonitor(history_size=3)
        for _ in range(5):
            m.get_snapshot()
        assert len(m.history()) == 3   # ring buffer

    def test_subscribe_callback_invoked_in_run(self) -> None:
        seen: list[HostMetricsSnapshot] = []
        evt = threading.Event()

        def cb(s: HostMetricsSnapshot) -> None:
            seen.append(s)
            evt.set()

        m = SystemMonitor(refresh_s=0.05)
        m.subscribe(cb)
        m.start()
        try:
            assert evt.wait(timeout=2.0)
            assert len(seen) >= 1
            assert isinstance(seen[0], HostMetricsSnapshot)
        finally:
            m.stop()
        assert not m.is_running

    def test_bridge_emit_when_provided(self) -> None:
        bridge = MagicMock()
        bridge.system_health_update = MagicMock()
        m = SystemMonitor(ui_bridge=bridge)
        snap = m.get_snapshot()
        m._dispatch(snap)
        bridge.system_health_update.emit.assert_called_once_with(snap)


# ─────────────────────────────────────────────────────────────────────────────
#  SystemStatusBar (UI)
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemStatusBar:
    @pytest.fixture(autouse=True)
    def _qt(self, qapp):
        return qapp

    def _snap(self, cpu=20.0, ram_u=2.0, ram_t=8.0, temp=58.0,
              disk_u=45.0, disk_t=250.0, uptime=4 * 3600 + 32 * 60,
              severity="OK") -> HostMetricsSnapshot:
        return HostMetricsSnapshot(
            cpu_percent=cpu, ram_used_gb=ram_u, ram_total_gb=ram_t,
            temp_c=temp, disk_used_gb=disk_u, disk_total_gb=disk_t,
            uptime_s=uptime, severity=severity,
        )

    def test_initial_state_ok(self) -> None:
        from ui.components.system_status_bar import SystemStatusBar
        bar = SystemStatusBar()
        assert bar.cpu_state == "OK"

    def test_update_ok_values(self) -> None:
        from ui.components.system_status_bar import SystemStatusBar
        bar = SystemStatusBar()
        bar.on_health_update(self._snap())
        assert bar.cpu_state == "OK"
        assert bar.ram_state == "OK"
        assert bar.temp_state == "OK"
        assert bar.disk_state == "OK"
        assert "42" not in bar._cpu.text() and "20" in bar._cpu.text()

    def test_update_temp_warning_yellow(self) -> None:
        from ui.components.system_status_bar import SystemStatusBar
        bar = SystemStatusBar()
        bar.on_health_update(self._snap(temp=78.0))
        assert bar.temp_state == "WARNING"

    def test_update_temp_critical_red(self) -> None:
        from ui.components.system_status_bar import SystemStatusBar
        bar = SystemStatusBar()
        bar.on_health_update(self._snap(temp=90.0))
        assert bar.temp_state == "CRITICAL"

    def test_update_cpu_critical(self) -> None:
        from ui.components.system_status_bar import SystemStatusBar
        bar = SystemStatusBar()
        bar.on_health_update(self._snap(cpu=97.0))
        assert bar.cpu_state == "CRITICAL"

    def test_update_temp_none_renders_dash(self) -> None:
        from ui.components.system_status_bar import SystemStatusBar
        bar = SystemStatusBar()
        bar.on_health_update(self._snap(temp=None))
        assert "—" in bar._temp.text()
        assert bar.temp_state == "OK"

    def test_uptime_formatting(self) -> None:
        from ui.components.system_status_bar import _format_uptime
        assert _format_uptime(4 * 3600 + 32 * 60) == "4h32m"
        assert _format_uptime(0) == "0h00m"
        # 1 jour 5h
        assert _format_uptime(29 * 3600 + 0) == "1d05h"
