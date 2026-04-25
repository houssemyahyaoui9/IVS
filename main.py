"""
main — TS2I IVS v7.0
CLI entry point — Rule-Governed Hierarchical Inspection System
"""
import argparse
import sys
import os


def parse_args():
    p = argparse.ArgumentParser(description="TS2I IVS v7.0")
    p.add_argument("--mode", choices=["gui", "headless"], default="gui")
    p.add_argument("--check", action="store_true", help="Run system checks and exit")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--inspections", type=int, default=0)
    return p.parse_args()


def check_systems() -> int:
    print("TS2I IVS v7.0 — System Check")
    print("═══════════════════════════════")

    checks = [
        ("Python 3.11+",   lambda: sys.version_info >= (3, 11)),
        ("OpenCV",         lambda: __import__("cv2") and True),
        ("ONNX Runtime",   lambda: __import__("onnxruntime") and True),
        ("scikit-learn",   lambda: __import__("sklearn") and True),
        ("PyQt6",          lambda: __import__("PyQt6") and True),
        ("FastAPI",        lambda: __import__("fastapi") and True),
        ("Config file",    lambda: os.path.exists("config/config.yaml")),
        ("data/production/OK",     lambda: os.path.isdir("data/production/OK")),
        ("data/production/NOK",    lambda: os.path.isdir("data/production/NOK")),
        ("data/production/REVIEW", lambda: os.path.isdir("data/production/REVIEW")),
        ("data/snapshots", lambda: os.path.isdir("data/snapshots")),
        ("data/yolo",      lambda: os.path.isdir("data/yolo")),
        ("data/llm",       lambda: os.path.isdir("data/llm")),
    ]

    all_ok = True
    for name, fn in checks:
        try:
            ok = fn()
            print(f"  {'✅' if ok else '❌'} {name}")
            if not ok:
                all_ok = False
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            all_ok = False

    print("═══════════════════════════════")
    if all_ok:
        print("✅ ALL SYSTEMS GO")
    else:
        print("❌ Some checks failed")
    return 0 if all_ok else 1


def main():
    args = parse_args()

    if args.check:
        sys.exit(check_systems())

    print("TS2I IVS v7.0 — Rule-Governed Hierarchical Inspection")
    print("Run Sessions S00-A → S24-B to implement")


if __name__ == "__main__":
    main()
