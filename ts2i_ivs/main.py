"""
main — TS2I IVS v7.0
CLI entry point — Rule-Governed Hierarchical Inspection System.

Modes :
  --check                Vérifie l'environnement et quitte (CI / install)
  --mode gui (défaut)    Lance QApplication + MainWindow + InspectionScreen
  --mode headless        Démarre la pipeline sans interface (futur)
  --debug                Logging DEBUG
  --inspections N        (réservé : nombre d'inspections en mode headless)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  sys.path bootstrap : la version canonique des modules vit à la racine du
#  projet (ui/main_window.py = celle avec 7 onglets). Le dossier ts2i_ivs/
#  contient un miroir partiel hérité — on le contourne ici.
#
#  Important : Python ajoute automatiquement la directory du script (ts2i_ivs/)
#  en sys.path[0]. Sans cette purge, `import core` / `import ui` chargeraient
#  les stubs internes au lieu des modules canoniques racine. On retire donc
#  l'entrée et on force la racine projet en tête.
# ─────────────────────────────────────────────────────────────────────────────

_THIS_DIR     = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent

# 1) Retire le miroir interne du chemin (ts2i_ivs/ contient des stubs vides
#    qui supplantent monitoring/, ui/, core/ de la racine).
sys.path[:] = [p for p in sys.path if Path(p).resolve() != _THIS_DIR]

# 2) Force la racine projet en sys.path[0] — même si déjà présente via
#    PYTHONPATH=. (pour garantir l'ordre de résolution).
if str(_PROJECT_ROOT) in sys.path:
    sys.path.remove(str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TS2I IVS v7.0")
    p.add_argument("--mode", choices=["gui", "headless"], default="gui",
                   help="Mode d'exécution (défaut: gui)")
    p.add_argument("--check", action="store_true",
                   help="Vérifier l'environnement et quitter")
    p.add_argument("--debug", action="store_true",
                   help="Active les logs DEBUG")
    p.add_argument("--inspections", type=int, default=0,
                   help="Headless : nombre d'inspections à exécuter (0 = boucle infinie)")
    p.add_argument("--product", type=str, default="—",
                   help="product_id à activer au démarrage (gui)")
    p.add_argument("--snapshot-dir", type=str, default=None,
                   help="Dossier de snapshots PNG (défaut: data/snapshots)")
    return p.parse_args(argv)


# ─────────────────────────────────────────────────────────────────────────────
#  System check (--check)
# ─────────────────────────────────────────────────────────────────────────────

def _check_import(module: str) -> tuple[bool, str]:
    try:
        __import__(module)
        return True, ""
    except Exception as e:
        return False, str(e)


def check_systems() -> int:
    """Affiche les checks runtime (modules + dossiers + config). Retourne exit code."""
    print("TS2I IVS v7.0 — System Check")
    print("═══════════════════════════════")

    # Recherche du fichier config (root projet ou ts2i_ivs/)
    config_candidates = [
        os.path.join("config", "config.yaml"),
        os.path.join("ts2i_ivs", "config", "config.yaml"),
    ]
    config_path = next((p for p in config_candidates if os.path.exists(p)), None)

    checks: list[tuple[str, bool, str]] = []

    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python ≥ 3.11", py_ok, sys.version.split()[0]))

    runtime_modules = [
        ("OpenCV",       "cv2"),
        ("NumPy",        "numpy"),
        ("scikit-learn", "sklearn"),
        ("scikit-image", "skimage"),
        ("SciPy",        "scipy"),
        ("ONNX Runtime", "onnxruntime"),
        ("PyQt6",        "PyQt6"),
        ("FastAPI",      "fastapi"),
        ("psutil",       "psutil"),
        ("Jinja2",       "jinja2"),
        ("matplotlib",   "matplotlib"),
    ]
    for label, mod in runtime_modules:
        ok, err = _check_import(mod)
        detail = "" if ok else f"({err})"
        checks.append((label, ok, detail))

    # Optionnels (warning, pas critique pour --check)
    optional_modules = [
        ("uvicorn (web)",        "uvicorn"),
        ("python-multipart",     "multipart"),
        ("WeasyPrint (PDF)",     "weasyprint"),
        ("python-jose (JWT)",    "jose"),
    ]
    optional_results: list[tuple[str, bool, str]] = []
    for label, mod in optional_modules:
        ok, err = _check_import(mod)
        optional_results.append((label, ok, "" if ok else "(optionnel)"))

    # Dossiers / fichiers requis
    fs_checks = [
        ("Config file", config_path is not None,
         config_path or "config/config.yaml introuvable"),
        ("data/production/OK",     os.path.isdir("data/production/OK"),     ""),
        ("data/production/NOK",    os.path.isdir("data/production/NOK"),    ""),
        ("data/production/REVIEW", os.path.isdir("data/production/REVIEW"), ""),
        ("data/snapshots",         os.path.isdir("data/snapshots"),         ""),
        ("data/yolo",              os.path.isdir("data/yolo"),              ""),
        ("data/llm",               os.path.isdir("data/llm"),               ""),
        ("data/reports",           os.path.isdir("data/reports"),           ""),
    ]

    # ── Affichage requis (compte pour le verdict) ──
    all_ok = True
    for label, ok, detail in checks + fs_checks:
        mark = "✅" if ok else "❌"
        line = f"  {mark} {label}"
        if detail:
            line += f"  {detail}"
        print(line)
        if not ok:
            all_ok = False

    # ── Affichage optionnels (n'impacte pas le verdict) ──
    print("───── Optionnels ─────")
    for label, ok, detail in optional_results:
        mark = "✅" if ok else "⚠️"
        print(f"  {mark} {label}  {detail}".rstrip())

    print("═══════════════════════════════")
    if all_ok:
        print("✅ ALL SYSTEMS GO")
    else:
        print("❌ Some checks failed")
    return 0 if all_ok else 1


# ─────────────────────────────────────────────────────────────────────────────
#  GUI mode
# ─────────────────────────────────────────────────────────────────────────────

def run_gui(args: argparse.Namespace) -> int:
    """Lance QApplication → UIBridge → SystemController → SystemMonitor → MainWindow."""
    from PyQt6.QtWidgets import QApplication

    # Modules canoniques (racine projet — pas le miroir ts2i_ivs/)
    from core.ui_bridge import UIBridge
    from ui.main_window import MainWindow

    try:
        from core.pipeline_controller import SystemController
    except Exception as e:
        logging.warning("SystemController indisponible (%s) — mode preview", e)
        SystemController = None  # type: ignore[assignment]

    try:
        from monitoring.system_monitor import SystemMonitor
    except Exception as e:
        logging.warning("SystemMonitor indisponible (%s) — status bar inactive", e)
        SystemMonitor = None  # type: ignore[assignment]

    app = QApplication.instance() or QApplication(sys.argv)

    bridge = UIBridge()
    controller = SystemController(bridge) if SystemController is not None else None

    # SystemMonitor : thread daemon CPU/RAM/Temp/Disk → UIBridge.system_health_update
    monitor = None
    if SystemMonitor is not None:
        try:
            monitor = SystemMonitor(ui_bridge=bridge)
            monitor.start()
            logging.info("SystemMonitor démarré (refresh 5s)")
        except Exception as e:
            logging.warning("SystemMonitor.start() échoué : %s", e)
            monitor = None

    # Bootstrap produit CLI (--product P208) : active + amène la FSM à IDLE_READY
    # AVANT que l'UI s'affiche (sinon le bouton Démarrer reste désactivé).
    if controller is not None and _is_real_product(args.product):
        _bootstrap_product(controller, args.product)

    window = MainWindow(
        controller     = controller,
        ui_bridge      = bridge,
        config         = None,
        config_path    = "config/config.yaml",
        system_monitor = monitor,
    )
    window.show()

    logging.info("MainWindow affichée — entrée dans la boucle Qt")
    rc = app.exec()
    if monitor is not None:
        try:
            monitor.stop()
        except Exception:
            pass
    return rc


# ─────────────────────────────────────────────────────────────────────────────
#  Bootstrap produit CLI
# ─────────────────────────────────────────────────────────────────────────────

def _is_real_product(value: str | None) -> bool:
    """args.product peut valoir '—' (placeholder argparse) ou ''/None."""
    if value is None:
        return False
    v = value.strip()
    return bool(v) and v != "—"


def _bootstrap_product(controller, product_id: str) -> bool:
    """
    Active `product_id` et fast-forward la FSM jusqu'à IDLE_READY si tous les
    artefacts de calibration sont présents.

    FSM walk : IDLE_NO_PRODUCT → IMAGE_CAPTURE → CALIBRATING → TRAINING → IDLE_READY

    Retourne True si IDLE_READY atteint, False sinon (état partiel loggé).
    """
    from pathlib import Path
    from core.models import SystemState

    product_dir = Path("products") / product_id
    config_path = product_dir / "config.json"

    if not config_path.exists():
        logging.error(
            "Bootstrap produit '%s' impossible : %s introuvable",
            product_id, config_path,
        )
        return False

    try:
        controller.activate_product(product_id)   # IDLE_NO_PRODUCT → IMAGE_CAPTURE
        logging.info("Produit '%s' activé (config: %s)", product_id, config_path)
    except Exception as exc:
        logging.error("activate_product('%s') a échoué : %s", product_id, exc)
        return False

    calib_dir = product_dir / "calibration"
    required = ("pixel_per_mm.json", "brightness_reference.json")
    missing  = [f for f in required if not (calib_dir / f).exists()]
    if missing:
        logging.warning(
            "Produit '%s' : calibration incomplète (%s) — FSM en %s, "
            "wizard de calibration requis pour atteindre IDLE_READY",
            product_id, ", ".join(missing), controller.get_state().value,
        )
        return False

    # Fast-forward : artefacts présents → on saute calibration + training
    try:
        controller.transition(SystemState.CALIBRATING)
        controller.transition(SystemState.TRAINING)
        controller.transition(SystemState.IDLE_READY)
    except Exception as exc:
        logging.error(
            "Bootstrap '%s' : transition FSM a échoué (état=%s) : %s",
            product_id, controller.get_state().value, exc,
        )
        return False

    logging.info(
        "Produit '%s' bootstrap OK → IDLE_READY (bouton Démarrer prêt)",
        product_id,
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
#  Headless mode (placeholder réservé pour S22+)
# ─────────────────────────────────────────────────────────────────────────────

def run_headless(args: argparse.Namespace) -> int:
    print("TS2I IVS v7.0 — Mode headless")
    print(f"Inspections demandées : {args.inspections or '∞'}")
    print("(Implémentation pipeline headless réservée — sessions futures)")
    return 0


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.debug)

    if args.check:
        return check_systems()

    if args.mode == "headless":
        return run_headless(args)

    return run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
