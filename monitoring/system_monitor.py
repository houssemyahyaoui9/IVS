"""
SystemMonitor — §18.4 / §43
Thread daemon · refresh 5s · psutil + vcgencmd (RPi) avec fallback sysfs.

  get_snapshot() → HostMetricsSnapshot (CPU, RAM, Temp, Disk, Uptime + severity).
  _check_alerts() : log WARNING/ERROR selon seuils config (§43).
  _thermal_throttle() : si temp > temp_crit → pipeline.reduce_fps(1).

Émet vers UIBridge.system_health_update si bridge fourni (GR-03).
Aucune décision pipeline — l'unique action côté pipeline est `reduce_fps(1)`
appelé sur l'objet pipeline injecté (interface : `reduce_fps(int) -> None`).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_GB = 1024 ** 3
_TEMP_SYSFS_PATH = "/sys/class/thermal/thermal_zone0/temp"
_VCGENCMD_TIMEOUT_S = 0.5


# ─────────────────────────────────────────────────────────────────────────────
#  HostMetricsSnapshot — frozen dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HostMetricsSnapshot:
    """
    Photo instantanée des métriques système — §18.4.

    `severity` = pire des 4 (CPU/RAM/TEMP/DISK) → "OK" | "WARNING" | "CRITICAL".
    `temp_c` peut valoir None (capteur indisponible).
    """
    cpu_percent     : float
    ram_used_gb     : float
    ram_total_gb    : float
    temp_c          : Optional[float]
    disk_used_gb    : float
    disk_total_gb   : float
    uptime_s        : float
    severity        : str         = "OK"
    timestamp       : float       = field(default_factory=time.time)


HealthCallback = Callable[[HostMetricsSnapshot], None]


# ─────────────────────────────────────────────────────────────────────────────
#  SystemMonitor
# ─────────────────────────────────────────────────────────────────────────────

class SystemMonitor:
    """
    Monitoring CPU/RAM/Temp/Disk/Uptime en thread daemon.

    Construction :
        mon = SystemMonitor(ui_bridge=bridge, pipeline=runner)
        mon.start()
        ...
        mon.stop()

    Lecture synchrone hors thread :
        snap = mon.get_snapshot()
    """

    def __init__(
        self,
        ui_bridge      : Optional[Any]      = None,
        pipeline       : Optional[Any]      = None,   # doit exposer reduce_fps(int)
        refresh_s      : float = 5.0,
        cpu_warn       : float = 80.0,
        cpu_crit       : float = 95.0,
        ram_warn       : float = 85.0,
        ram_crit       : float = 95.0,
        temp_warn      : float = 75.0,
        temp_crit      : float = 85.0,
        disk_warn      : float = 85.0,
        disk_crit      : float = 95.0,
        history_size   : int   = 720,    # 1h à 5s
        disk_path      : str   = "/",
    ) -> None:
        if refresh_s <= 0:
            raise ValueError(f"refresh_s={refresh_s} doit être > 0")

        self._bridge   = ui_bridge
        self._pipeline = pipeline

        self._refresh_s = refresh_s
        self._cpu_warn, self._cpu_crit   = cpu_warn,  cpu_crit
        self._ram_warn, self._ram_crit   = ram_warn,  ram_crit
        self._temp_warn, self._temp_crit = temp_warn, temp_crit
        self._disk_warn, self._disk_crit = disk_warn, disk_crit
        self._disk_path = disk_path

        self._stop_evt = threading.Event()
        self._thread   : Optional[threading.Thread] = None

        self._lock      = threading.RLock()
        self._last_snap : Optional[HostMetricsSnapshot] = None
        self._history   : deque[HostMetricsSnapshot]    = deque(maxlen=history_size)

        self._callbacks : list[HealthCallback] = []
        self._cb_lock   = threading.RLock()
        self._throttled = False

        # psutil chargé paresseusement (peut être absent en CI)
        try:
            import psutil
            self._psutil = psutil
            # Premier appel non bloquant pour amorcer cpu_percent
            psutil.cpu_percent(interval=None)
        except ImportError:
            self._psutil = None
            logger.warning("SystemMonitor: psutil absent — métriques limitées")

    # ── Souscription ──────────────────────────────────────────────────────────

    def subscribe(self, callback: HealthCallback) -> None:
        with self._cb_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unsubscribe(self, callback: HealthCallback) -> None:
        with self._cb_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, name="SystemMonitor", daemon=True,
        )
        self._thread.start()
        logger.info(
            "SystemMonitor démarré (refresh=%.1fs, temp_warn=%.0f, temp_crit=%.0f)",
            self._refresh_s, self._temp_warn, self._temp_crit,
        )

    def stop(self, timeout_s: float = 2.0) -> None:
        self._stop_evt.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_s)
        self._thread = None
        logger.info("SystemMonitor arrêté")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── API publique ──────────────────────────────────────────────────────────

    def get_snapshot(self) -> HostMetricsSnapshot:
        """Capture synchrone des métriques courantes (utilisable hors thread)."""
        snap = self._sample()
        with self._lock:
            self._last_snap = snap
            self._history.append(snap)
        return snap

    @property
    def last_snapshot(self) -> Optional[HostMetricsSnapshot]:
        with self._lock:
            return self._last_snap

    def history(self, limit: Optional[int] = None) -> tuple[HostMetricsSnapshot, ...]:
        """Retourne les snapshots historiques (du plus ancien au plus récent)."""
        with self._lock:
            data = list(self._history)
        if limit is not None:
            data = data[-limit:]
        return tuple(data)

    # ── Boucle ────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                snap = self.get_snapshot()
                self._check_alerts(snap)
                self._thermal_throttle(snap)
                self._dispatch(snap)
            except Exception as exc:
                logger.error("SystemMonitor: erreur tick — %s", exc, exc_info=True)
            if self._stop_evt.wait(self._refresh_s):
                break

    # ── Capture ──────────────────────────────────────────────────────────────

    def _sample(self) -> HostMetricsSnapshot:
        cpu        = self._read_cpu()
        ram_u, ram_t = self._read_ram()
        temp       = self._read_temp()
        disk_u, disk_t = self._read_disk()
        uptime     = self._read_uptime()
        severity   = self._compute_severity(cpu, ram_u, ram_t, temp, disk_u, disk_t)
        return HostMetricsSnapshot(
            cpu_percent   = cpu,
            ram_used_gb   = ram_u,
            ram_total_gb  = ram_t,
            temp_c        = temp,
            disk_used_gb  = disk_u,
            disk_total_gb = disk_t,
            uptime_s      = uptime,
            severity      = severity,
        )

    def _read_cpu(self) -> float:
        if self._psutil is None:
            return 0.0
        try:
            return float(self._psutil.cpu_percent(interval=None))
        except Exception as exc:
            logger.debug("SystemMonitor: cpu_percent erreur — %s", exc)
            return 0.0

    def _read_ram(self) -> tuple[float, float]:
        if self._psutil is None:
            return 0.0, 0.0
        try:
            vm = self._psutil.virtual_memory()
            return round(vm.used / _GB, 2), round(vm.total / _GB, 2)
        except Exception as exc:
            logger.debug("SystemMonitor: virtual_memory erreur — %s", exc)
            return 0.0, 0.0

    def _read_disk(self) -> tuple[float, float]:
        try:
            usage = shutil.disk_usage(self._disk_path)
            return round(usage.used / _GB, 1), round(usage.total / _GB, 1)
        except Exception as exc:
            logger.debug("SystemMonitor: disk_usage erreur — %s", exc)
            return 0.0, 0.0

    def _read_uptime(self) -> float:
        if self._psutil is not None:
            try:
                return time.time() - self._psutil.boot_time()
            except Exception:
                pass
        # Fallback Linux /proc/uptime
        try:
            with open("/proc/uptime", encoding="utf-8") as fh:
                return float(fh.read().split()[0])
        except Exception:
            return 0.0

    # ── Lecture température (vcgencmd → sysfs) ───────────────────────────────

    def _read_temp(self) -> Optional[float]:
        # 1) Tentative vcgencmd (Raspberry Pi OS)
        vc = shutil.which("vcgencmd")
        if vc is not None:
            try:
                out = subprocess.check_output(
                    [vc, "measure_temp"],
                    timeout=_VCGENCMD_TIMEOUT_S,
                    stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace").strip()
                # Format : "temp=58.3'C"
                if "=" in out and "'" in out:
                    return float(out.split("=", 1)[1].split("'", 1)[0])
            except (subprocess.SubprocessError, ValueError) as exc:
                logger.debug("SystemMonitor: vcgencmd erreur — %s", exc)

        # 2) Fallback sysfs (Linux générique)
        if os.path.exists(_TEMP_SYSFS_PATH):
            try:
                with open(_TEMP_SYSFS_PATH, encoding="utf-8") as fh:
                    return round(int(fh.read().strip()) / 1000.0, 1)
            except (OSError, ValueError) as exc:
                logger.debug("SystemMonitor: sysfs temp erreur — %s", exc)

        return None

    # ── Alertes / sévérité ───────────────────────────────────────────────────

    def _classify(
        self, value: float, warn: float, crit: float,
    ) -> str:
        if value >= crit:
            return "CRITICAL"
        if value >= warn:
            return "WARNING"
        return "OK"

    def _compute_severity(
        self,
        cpu: float, ram_u: float, ram_t: float,
        temp: Optional[float],
        disk_u: float, disk_t: float,
    ) -> str:
        worst = "OK"
        levels = {"OK": 0, "WARNING": 1, "CRITICAL": 2}

        def _bump(s: str) -> None:
            nonlocal worst
            if levels[s] > levels[worst]:
                worst = s

        _bump(self._classify(cpu, self._cpu_warn, self._cpu_crit))
        if ram_t > 0:
            _bump(self._classify(ram_u / ram_t * 100.0,
                                 self._ram_warn, self._ram_crit))
        if disk_t > 0:
            _bump(self._classify(disk_u / disk_t * 100.0,
                                 self._disk_warn, self._disk_crit))
        if temp is not None:
            _bump(self._classify(temp, self._temp_warn, self._temp_crit))
        return worst

    def _check_alerts(self, snap: HostMetricsSnapshot) -> None:
        if snap.cpu_percent >= self._cpu_crit:
            logger.error("SystemMonitor: CPU CRITICAL %.0f%%", snap.cpu_percent)
        elif snap.cpu_percent >= self._cpu_warn:
            logger.warning("SystemMonitor: CPU WARNING %.0f%%", snap.cpu_percent)

        if snap.ram_total_gb > 0:
            ram_pct = snap.ram_used_gb / snap.ram_total_gb * 100.0
            if ram_pct >= self._ram_crit:
                logger.error("SystemMonitor: RAM CRITICAL %.0f%%", ram_pct)
            elif ram_pct >= self._ram_warn:
                logger.warning("SystemMonitor: RAM WARNING %.0f%%", ram_pct)

        if snap.temp_c is not None:
            if snap.temp_c >= self._temp_crit:
                logger.error("SystemMonitor: TEMP CRITICAL %.1f°C", snap.temp_c)
            elif snap.temp_c >= self._temp_warn:
                logger.warning("SystemMonitor: TEMP WARNING %.1f°C", snap.temp_c)

        if snap.disk_total_gb > 0:
            disk_pct = snap.disk_used_gb / snap.disk_total_gb * 100.0
            if disk_pct >= self._disk_crit:
                logger.error("SystemMonitor: DISK CRITICAL %.0f%%", disk_pct)
            elif disk_pct >= self._disk_warn:
                logger.warning("SystemMonitor: DISK WARNING %.0f%%", disk_pct)

    # ── Thermal throttle ─────────────────────────────────────────────────────

    def _thermal_throttle(self, snap: HostMetricsSnapshot) -> None:
        if snap.temp_c is None or self._pipeline is None:
            return
        if snap.temp_c > self._temp_crit and not self._throttled:
            try:
                self._pipeline.reduce_fps(1)
                self._throttled = True
                logger.error(
                    "SystemMonitor: thermal throttle ACTIVÉ (temp=%.1f°C > %.0f) — "
                    "pipeline.reduce_fps(1)",
                    snap.temp_c, self._temp_crit,
                )
            except Exception as exc:
                logger.error("SystemMonitor: reduce_fps a échoué — %s", exc)
        elif self._throttled and snap.temp_c <= self._temp_warn:
            # Hystérésis : ne lève le throttle qu'en repassant sous le seuil warn
            self._throttled = False
            logger.info(
                "SystemMonitor: thermal throttle LEVÉ (temp=%.1f°C < %.0f)",
                snap.temp_c, self._temp_warn,
            )

    # ── Dispatch ─────────────────────────────────────────────────────────────

    def _dispatch(self, snap: HostMetricsSnapshot) -> None:
        # UIBridge (signal Qt cross-thread — GR-05)
        if self._bridge is not None:
            sig = getattr(self._bridge, "system_health_update", None)
            if sig is not None:
                try:
                    sig.emit(snap)
                except Exception as exc:
                    logger.debug("SystemMonitor: emit bridge — %s", exc)

        # Callbacks libres (tests, hooks)
        with self._cb_lock:
            cbs = list(self._callbacks)
        for cb in cbs:
            try:
                cb(snap)
            except Exception as exc:
                logger.error("SystemMonitor: callback %r — %s", cb, exc)
