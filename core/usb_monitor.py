"""
UsbMonitor — détection automatique des clés USB porteuses d'un fichier .ivs

Spec : IVS_FINAL_SPEC_v7_COMPLETE.md §Fleet.5 — Import USB.
Plateformes : Linux (/media/<user>/, /media/, /run/media/<user>/) et
              macOS (/Volumes/). Sur Windows, le polling reste passif —
              passer un mount root explicite via `extra_roots=`.

Thread daemon · polling 2s. À chaque tick :
  • énumère les sous-répertoires de chaque mount root,
  • détecte les nouveaux montages depuis le dernier tick,
  • cherche un (et un seul) *.ivs à la racine du nouveau montage,
  • émet `usb_ivs_found(ivs_path: str, mount_point: str)` Qt-safe.

GR-03 : aucun import direct n'est déclenché ici — l'UI/FleetScreen reçoit
        le signal et appelle `FleetManager.import_via_usb()` après accord
        opérateur (préserve le mutex réseau ⊕ USB de FleetManager).
"""
from __future__ import annotations

import logging
import os
import platform
import sys
import threading
from pathlib import Path
from typing import Iterable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


_DEFAULT_POLL_S    = 2.0
_GLOB_PATTERN      = "*.ivs"


# ─────────────────────────────────────────────────────────────────────────────
#  Mount roots par défaut selon plateforme
# ─────────────────────────────────────────────────────────────────────────────

def _default_mount_roots() -> tuple[Path, ...]:
    """Retourne la liste des racines de montage à surveiller selon l'OS."""
    system = platform.system()
    if system == "Darwin":
        return (Path("/Volumes"),)
    if system == "Linux":
        roots: list[Path] = [Path("/media"), Path("/run/media")]
        # /media/<user>/ — chemin Ubuntu auto-mount
        user = os.environ.get("USER") or os.environ.get("LOGNAME")
        if user:
            roots.append(Path("/media") / user)
            roots.append(Path("/run/media") / user)
        # Dédoublonne en préservant l'ordre.
        seen: set[Path] = set()
        unique: list[Path] = []
        for r in roots:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return tuple(unique)
    # Windows / autres — l'UI doit fournir extra_roots= si besoin.
    return ()


# ─────────────────────────────────────────────────────────────────────────────
#  UsbMonitor
# ─────────────────────────────────────────────────────────────────────────────

class UsbMonitor(QObject):
    """
    Détecteur USB → signal Qt `usb_ivs_found(ivs_path, mount_point)`.

    Construction :
        mon = UsbMonitor()                       # roots auto selon OS
        mon = UsbMonitor(extra_roots=["/mnt"])   # ajoute des racines custom
        mon.usb_ivs_found.connect(on_found)
        mon.start()
        ...
        mon.stop()

    Le polling est un thread daemon (s'arrête avec le process). `stop()`
    attend la fin du tick courant.
    """

    # (ivs_path, mount_point) — toujours des str pour les slots Qt.
    usb_ivs_found = pyqtSignal(str, str)

    # Émis quand un mount disparaît (utile pour le bandeau "clé retirée").
    usb_unmounted = pyqtSignal(str)

    # Émis quand un nouveau mount est vu (avec ou sans .ivs).
    usb_mounted = pyqtSignal(str)

    def __init__(
        self,
        extra_roots : Optional[Iterable[str | Path]] = None,
        poll_s      : float                          = _DEFAULT_POLL_S,
        parent      : Optional[QObject]              = None,
    ) -> None:
        super().__init__(parent)
        if poll_s <= 0:
            raise ValueError(f"poll_s doit être > 0, reçu {poll_s}")

        roots = list(_default_mount_roots())
        if extra_roots:
            for r in extra_roots:
                p = Path(r)
                if p not in roots:
                    roots.append(p)
        self._roots: tuple[Path, ...] = tuple(roots)
        self._poll_s = float(poll_s)

        # État interne — accédé depuis le thread daemon uniquement.
        self._known_mounts : set[str] = set()
        # Chemins .ivs déjà annoncés pour éviter les ré-émissions au tick suivant.
        self._announced    : set[str] = set()

        self._stop_event   = threading.Event()
        self._thread       : Optional[threading.Thread] = None

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le thread daemon. No-op si déjà démarré."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="UsbMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "UsbMonitor: démarré — roots=%s, poll=%.1fs",
            [str(r) for r in self._roots], self._poll_s,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Demande l'arrêt et attend la fin du tick courant."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        logger.info("UsbMonitor: arrêté")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def mount_roots(self) -> tuple[Path, ...]:
        return self._roots

    # ── Boucle de polling ─────────────────────────────────────────────────────

    def _run(self) -> None:
        # Première itération sans émission : on enregistre les mounts déjà
        # présents au démarrage pour ne signaler que les NOUVEAUX.
        self._known_mounts = self._enumerate_current_mounts()
        for mount in self._known_mounts:
            for ivs in self._scan_ivs(Path(mount)):
                self._announced.add(str(ivs))

        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                # Aucune exception ne doit tuer le thread daemon (GR-11).
                logger.error(
                    "UsbMonitor: exception dans tick — %s", exc, exc_info=True,
                )
            # wait() retourne True si stop demandé → interrompt sleep.
            if self._stop_event.wait(self._poll_s):
                break

    def _tick(self) -> None:
        current = self._enumerate_current_mounts()

        # Mounts disparus
        for gone in self._known_mounts - current:
            self.usb_unmounted.emit(gone)
            # Purge les chemins .ivs annoncés depuis ce mount.
            self._announced = {
                p for p in self._announced if not p.startswith(gone)
            }

        # Nouveaux mounts
        new_mounts = current - self._known_mounts
        for mount_str in new_mounts:
            self.usb_mounted.emit(mount_str)
            ivs_files = self._scan_ivs(Path(mount_str))
            # Spec §Fleet.5 : 1 .ivs max par clé. Si plusieurs, on n'émet rien
            # (FleetManager.import_via_usb lèvera FleetImportError si l'opérateur
            # tente l'import) — on signale néanmoins le mount.
            if len(ivs_files) == 1:
                ivs = str(ivs_files[0])
                if ivs not in self._announced:
                    self._announced.add(ivs)
                    logger.info(
                        "UsbMonitor: .ivs détecté → %s (mount=%s)",
                        ivs, mount_str,
                    )
                    self.usb_ivs_found.emit(ivs, mount_str)
            elif len(ivs_files) > 1:
                logger.warning(
                    "UsbMonitor: %d .ivs sur %s — l'opérateur devra n'en "
                    "garder qu'un (§Fleet.5)",
                    len(ivs_files), mount_str,
                )

        self._known_mounts = current

    # ── Énumération ───────────────────────────────────────────────────────────

    def _enumerate_current_mounts(self) -> set[str]:
        """Liste les sous-répertoires (= mount points USB) de chaque root."""
        mounts: set[str] = set()
        for root in self._roots:
            try:
                if not root.is_dir():
                    continue
                for entry in root.iterdir():
                    try:
                        if entry.is_dir():
                            mounts.add(str(entry))
                    except OSError:
                        # Un mount peut disparaître entre iterdir et is_dir.
                        continue
            except OSError as exc:
                logger.debug(
                    "UsbMonitor: lecture %s impossible — %s", root, exc,
                )
        return mounts

    @staticmethod
    def _scan_ivs(mount: Path) -> list[Path]:
        """Liste les *.ivs à la racine du mount (non récursif — §Fleet.5)."""
        try:
            return sorted(mount.glob(_GLOB_PATTERN))
        except OSError as exc:
            logger.debug(
                "UsbMonitor: glob %s impossible — %s", mount, exc,
            )
            return []

    # ── Helpers tests ─────────────────────────────────────────────────────────

    def force_scan(self) -> None:
        """Déclenche un tick immédiat — utilisé par les tests sans sleep."""
        self._tick()

    def reset_announced(self) -> None:
        """Vide la mémoire des .ivs déjà annoncés (utile pour tests)."""
        self._announced.clear()
