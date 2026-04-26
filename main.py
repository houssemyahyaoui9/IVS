"""
main — TS2I IVS v7.0 (entry point racine)
Délègue à core/pipeline_controller + ui/main_window
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path

# Force racine projet dans sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def parse_args():
    p = argparse.ArgumentParser(description="TS2I IVS v7.0")
    p.add_argument("--mode", choices=["gui", "headless"], default="gui")
    p.add_argument("--check", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--product", type=str, default="")
    return p.parse_args()


def check_systems() -> int:
    print("TS2I IVS v7.0 — System Check")
    print("═══════════════════════════════")
    checks = [
        ("Python 3.11+",           lambda: sys.version_info >= (3, 11)),
        ("OpenCV",                 lambda: __import__("cv2") and True),
        ("NumPy",                  lambda: __import__("numpy") and True),
        ("ONNX Runtime",           lambda: __import__("onnxruntime") and True),
        ("scikit-learn",           lambda: __import__("sklearn") and True),
        ("PyQt6",                  lambda: __import__("PyQt6") and True),
        ("FastAPI",                lambda: __import__("fastapi") and True),
        ("psutil",                 lambda: __import__("psutil") and True),
        ("PyYAML",                 lambda: __import__("yaml") and True),
        ("Config file",            lambda: os.path.exists("config/config.yaml")),
        ("data/production/OK",     lambda: os.path.isdir("data/production/OK")),
        ("data/production/NOK",    lambda: os.path.isdir("data/production/NOK")),
        ("data/production/REVIEW", lambda: os.path.isdir("data/production/REVIEW")),
        ("data/snapshots",         lambda: os.path.isdir("data/snapshots")),
        ("data/yolo",              lambda: os.path.isdir("data/yolo")),
        ("data/llm",               lambda: os.path.isdir("data/llm")),
    ]
    all_ok = True
    for name, fn in checks:
        try:
            ok = fn()
        except Exception as e:
            ok = False
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok:
            all_ok = False
    print("═══════════════════════════════")
    print("✅ ALL SYSTEMS GO" if all_ok else "❌ Some checks failed")
    return 0 if all_ok else 1


def run_gui(args) -> int:
    from PyQt6.QtWidgets import QApplication
    from core.ui_bridge import UIBridge
    from ui.main_window import MainWindow

    # ── STEP 1 : Config ──
    cfg_for_theme = None
    controller = None
    try:
        from core.pipeline_controller import SystemController
        from core.config_manager import ConfigManager
        cfg_for_theme = ConfigManager("config/config.yaml").load()
        bridge = UIBridge()
        controller = SystemController(bridge)
    except Exception as e:
        logging.warning("SystemController indisponible : %s", e)
        bridge = UIBridge()

    monitor = None
    try:
        from monitoring.system_monitor import SystemMonitor
        monitor = SystemMonitor(ui_bridge=bridge)
        monitor.start()
    except Exception as e:
        logging.warning("SystemMonitor indisponible : %s", e)

    app = QApplication.instance() or QApplication(sys.argv)

    # ── STEP 2 : Theme AVANT toute fenêtre (GR-V9-2) ──
    try:
        from ui.theme.theme_manager import ThemeManager
        theme_name = "light"
        if cfg_for_theme is not None:
            theme_name = cfg_for_theme.get("ui.theme", "light") or "light"
        ThemeManager.instance().apply(theme_name)
    except Exception as e:
        logging.warning("ThemeManager non appliqué : %s", e)

    # ── STEP 3 : MainWindow ──
    window = MainWindow(
        controller=controller,
        ui_bridge=bridge,
        config=None,
        config_path="config/config.yaml",
        system_monitor=monitor,
    )
    window.show()
    rc = app.exec()
    if monitor:
        try:
            monitor.stop()
        except Exception:
            pass
    return rc


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.check:
        sys.exit(check_systems())
    if args.mode == "headless":
        print("Mode headless — à implémenter")
        sys.exit(0)
    sys.exit(run_gui(args))


if __name__ == "__main__":
    main()
