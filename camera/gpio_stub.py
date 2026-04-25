"""
GpioStubBackend — §17 (simulation PC/Mac sans GPIO réel).

Implémente le contrat GpioBackend de core.gpio_manager pour permettre de
développer / tester GpioManager sur poste de dev (sans RPi5).

Comportement :
  - Tous les appels write/read sont consignés (log INFO) et mémorisés
    dans un dict[int, bool] interne.
  - Aucune action matérielle.

Thread-safe (verrou interne).
"""
from __future__ import annotations

import logging
import threading
from typing import Set

from core.gpio_manager import GpioBackend

logger = logging.getLogger(__name__)


class GpioStubBackend(GpioBackend):
    """Backend de simulation — utilisable sur n'importe quelle plateforme."""

    def __init__(self) -> None:
        self._lock          = threading.RLock()
        self._state         : dict[int, bool] = {}
        self._outputs       : Set[int] = set()
        self._inputs        : Set[int] = set()
        self._cleaned_up    = False
        logger.info("GpioStubBackend: backend simulation actif (aucun GPIO réel)")

    # ── Setup ────────────────────────────────────────────────────────────────

    def setup_output(self, pin: int) -> None:
        with self._lock:
            self._outputs.add(int(pin))
            self._state.setdefault(int(pin), False)
        logger.info("GPIO stub: setup_output pin %d", pin)

    def setup_input(self, pin: int) -> None:
        with self._lock:
            self._inputs.add(int(pin))
            self._state.setdefault(int(pin), False)
        logger.info("GPIO stub: setup_input pin %d", pin)

    # ── I/O ──────────────────────────────────────────────────────────────────

    def write(self, pin: int, high: bool) -> None:
        pin = int(pin)
        level = bool(high)
        with self._lock:
            if pin not in self._outputs:
                logger.warning(
                    "GPIO stub: write pin %d sans setup_output préalable", pin,
                )
                self._outputs.add(pin)
            self._state[pin] = level
        logger.info(
            "GPIO stub: pin %d → %s", pin, "HIGH" if level else "LOW",
        )

    def read(self, pin: int) -> bool:
        pin = int(pin)
        with self._lock:
            return bool(self._state.get(pin, False))

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        with self._lock:
            self._state.clear()
            self._outputs.clear()
            self._inputs.clear()
            self._cleaned_up = True
        logger.info("GPIO stub: cleanup")

    # ── Lecture (tests) ──────────────────────────────────────────────────────

    @property
    def state(self) -> dict[int, bool]:
        with self._lock:
            return dict(self._state)

    @property
    def outputs(self) -> Set[int]:
        with self._lock:
            return set(self._outputs)

    @property
    def is_cleaned_up(self) -> bool:
        with self._lock:
            return self._cleaned_up
