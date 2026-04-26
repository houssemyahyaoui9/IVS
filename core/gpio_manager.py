"""
GpioManager + GpioBackend ABC + GpioPi5Backend — §17

Architecture v7.0 :
  GpioBackend (ABC)             : contrat minimal setup/write/read/cleanup
  GpioPi5Backend                : Raspberry Pi 5 via RPi.GPIO (BCM)
  GpioStubBackend               : simulation PC/Mac (camera/gpio_stub.py)
  GpioManager                   : abonné UIBridge.inspection_result (GR-03)

Mapping verdict (§17) :
  FinalResult.verdict == "OK"     → lampe VERTE ON / ROUGE OFF
  FinalResult.verdict == "NOK"    → lampe ROUGE ON / VERTE OFF
  FinalResult.verdict == "REVIEW" → rien (toutes lampes OFF, opérateur décide)

GR-03 : le verdict est lu depuis FinalResult (objet émis sur UIBridge),
        jamais depuis le pipeline directement.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PIN_GREEN = 17
_DEFAULT_PIN_RED   = 18


# ─────────────────────────────────────────────────────────────────────────────
#  GpioBackend — ABC
# ─────────────────────────────────────────────────────────────────────────────

class GpioBackend(ABC):
    """Contrat minimal pour tout backend GPIO (réel ou simulé)."""

    @abstractmethod
    def setup_output(self, pin: int) -> None: ...

    @abstractmethod
    def setup_input(self, pin: int) -> None: ...

    @abstractmethod
    def write(self, pin: int, high: bool) -> None: ...

    @abstractmethod
    def read(self, pin: int) -> bool: ...

    @abstractmethod
    def cleanup(self) -> None: ...


# ─────────────────────────────────────────────────────────────────────────────
#  GpioPi5Backend — Raspberry Pi 5
# ─────────────────────────────────────────────────────────────────────────────

class GpioPi5Backend(GpioBackend):
    """
    Backend RPi5 via RPi.GPIO (BCM numbering).

    Si RPi.GPIO est absent (poste de dev), le backend logue une erreur claire
    plutôt que d'en silencer l'absence — utiliser GpioStubBackend pour PC.
    """

    def __init__(self) -> None:
        try:
            import RPi.GPIO as _GPIO   # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "GpioPi5Backend nécessite RPi.GPIO — utiliser GpioStubBackend "
                "sur poste de dev (config gpio.backend = stub)."
            ) from exc

        self._GPIO = _GPIO
        # Protection : ne pas écraser un mode déjà défini par un autre module
        if _GPIO.getmode() is None:
            _GPIO.setmode(_GPIO.BCM)
            logger.info("GpioPi5Backend: mode BCM activé")
        elif _GPIO.getmode() != _GPIO.BCM:
            logger.warning(
                "GpioPi5Backend: mode existant %s (BCM attendu) — non modifié",
                _GPIO.getmode(),
            )
        _GPIO.setwarnings(False)

    def setup_output(self, pin: int) -> None:
        self._GPIO.setup(int(pin), self._GPIO.OUT, initial=self._GPIO.LOW)
        logger.info("GpioPi5Backend: setup_output pin %d", pin)

    def setup_input(self, pin: int) -> None:
        self._GPIO.setup(int(pin), self._GPIO.IN)
        logger.info("GpioPi5Backend: setup_input pin %d", pin)

    def write(self, pin: int, high: bool) -> None:
        level = self._GPIO.HIGH if high else self._GPIO.LOW
        self._GPIO.output(int(pin), level)

    def read(self, pin: int) -> bool:
        return bool(self._GPIO.input(int(pin)))

    def cleanup(self) -> None:
        self._GPIO.cleanup()
        logger.info("GpioPi5Backend: cleanup")


# ─────────────────────────────────────────────────────────────────────────────
#  GpioManager
# ─────────────────────────────────────────────────────────────────────────────

class GpioManager:
    """
    Pilote des lampes vert/rouge selon FinalResult.verdict.

    Construction :
        mgr = GpioManager(config, ui_bridge)
        mgr.start()       # branche le signal inspection_result
        ...
        mgr.stop()        # déconnecte + cleanup backend

    Config attendue (config.yaml §17) :
        gpio:
          enabled:   true | false
          pin_green: 17       # BCM
          pin_red:   18       # BCM
          backend:   stub | pi5
    """

    def __init__(
        self,
        config    : Any,
        ui_bridge : Any,
        backend   : Optional[GpioBackend] = None,
    ) -> None:
        self._bridge    = ui_bridge
        self._enabled   = bool(_cfg_get(config, "gpio.enabled", False))
        self._pin_green = int(_cfg_get(config, "gpio.pin_green", _DEFAULT_PIN_GREEN))
        self._pin_red   = int(_cfg_get(config, "gpio.pin_red",   _DEFAULT_PIN_RED))
        self._backend_kind = str(_cfg_get(config, "gpio.backend", "stub")).lower()

        self._gpio      : Optional[GpioBackend] = backend
        self._connected = False

        if self._enabled:
            if self._gpio is None:
                self._gpio = self._build_backend(self._backend_kind)
            self._setup_pins()
        else:
            logger.info("GpioManager: désactivé (gpio.enabled=false)")

    # ── Backend selection ────────────────────────────────────────────────────

    @staticmethod
    def _build_backend(kind: str) -> GpioBackend:
        if kind == "pi5":
            return GpioPi5Backend()
        if kind == "stub":
            from camera.gpio_stub import GpioStubBackend
            return GpioStubBackend()
        raise ValueError(
            f"GpioManager: gpio.backend='{kind}' invalide (stub|pi5)"
        )

    def _setup_pins(self) -> None:
        assert self._gpio is not None
        self._gpio.setup_output(self._pin_green)
        self._gpio.setup_output(self._pin_red)
        self._reset_all_lamps()

    # ── Cycle de vie / signal câblage ────────────────────────────────────────

    def start(self) -> None:
        """Branche le signal inspection_result (GR-03). Idempotent."""
        if not self._enabled or self._connected:
            return
        sig = getattr(self._bridge, "inspection_result", None)
        if sig is None:
            logger.error("GpioManager: ui_bridge sans signal 'inspection_result'")
            return
        try:
            sig.connect(self.on_result)
        except Exception as exc:
            logger.error("GpioManager: connect signal échoué — %s", exc)
            return
        self._connected = True
        logger.info(
            "GpioManager démarré (backend=%s, green=GPIO%d, red=GPIO%d)",
            self._backend_kind, self._pin_green, self._pin_red,
        )

    def stop(self) -> None:
        """Déconnecte le signal et cleanup du backend."""
        if self._connected:
            sig = getattr(self._bridge, "inspection_result", None)
            if sig is not None:
                try:
                    sig.disconnect(self.on_result)
                except (TypeError, RuntimeError):
                    pass
            self._connected = False
        if self._gpio is not None:
            try:
                self._reset_all_lamps()
                self._gpio.cleanup()
            except Exception as exc:
                logger.error("GpioManager: cleanup échoué — %s", exc)
        logger.info("GpioManager arrêté")

    # ── Slot principal ───────────────────────────────────────────────────────

    def on_result(self, final_result: Any) -> None:
        """
        Slot du signal UIBridge.inspection_result.

        GR-03 : verdict lu UNIQUEMENT depuis FinalResult.verdict.
        """
        if not self._enabled or self._gpio is None:
            return

        verdict = getattr(final_result, "verdict", None)
        if verdict not in ("OK", "NOK", "REVIEW"):
            logger.warning("GpioManager: verdict invalide '%s' — ignoré", verdict)
            return

        try:
            self._reset_all_lamps()
            if verdict == "OK":
                self._gpio.write(self._pin_green, True)
                logger.info("GPIO: GREEN ON (pin %d)", self._pin_green)
            elif verdict == "NOK":
                self._gpio.write(self._pin_red, True)
                logger.info("GPIO: RED ON (pin %d)", self._pin_red)
            # REVIEW → rien (§17)
        except Exception as exc:
            logger.error("GpioManager: erreur écriture GPIO — %s", exc)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _reset_all_lamps(self) -> None:
        if self._gpio is None:
            return
        self._gpio.write(self._pin_green, False)
        self._gpio.write(self._pin_red, False)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def backend(self) -> Optional[GpioBackend]:
        return self._gpio

    @property
    def pin_green(self) -> int:
        return self._pin_green

    @property
    def pin_red(self) -> int:
        return self._pin_red


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers config (compat ConfigManager + dict)
# ─────────────────────────────────────────────────────────────────────────────

def _cfg_get(config: Any, dotted_key: str, default: Any) -> Any:
    """
    Lecture pointée tolérante : accepte ConfigManager (.get) ou dict imbriqué.
    """
    if config is None:
        return default
    # dict natif → traversée pointée locale (évite que dict.get traite la
    # chaîne pointée comme une clé plate).
    if isinstance(config, dict):
        node: Any = config
        for part in dotted_key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node
    # ConfigManager (ou compatible) — accepte la notation pointée nativement.
    if hasattr(config, "get") and callable(config.get):
        try:
            value = config.get(dotted_key, default)
            return default if value is None else value
        except TypeError:
            return default
    return default
