# TS2I IVS v7.0 — Rule-Governed Hierarchical Inspection

Système d'inspection visuelle industriel **AI observe → Rule Engine décide**,
3 Tiers (CRITICAL · MAJOR · MINOR), 5 Observers (YOLO · SIFT · Color ·
Surface · Logo), pipeline 8 étapes Fail-Fast, déploiement Fleet (.ivs).

| Item | Valeur |
|---|---|
| Python | 3.11 ou 3.12 |
| UI | PyQt6 (Qt 6.6+) |
| Vision | OpenCV 4.13 (headless) + scikit-image |
| AI runtime | onnxruntime + scikit-learn |
| Web API | FastAPI + uvicorn (JWT auth) |
| Cibles supportées | Linux x86_64 (dev / WSL2), Raspberry Pi 5 (prod) |

---

## 1. Installation — WSL2 / Ubuntu 22.04+

### 1.1 Pré-requis système

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-dev python3-pip \
  build-essential pkg-config \
  libgl1 libglib2.0-0 libxkbcommon-x11-0 libdbus-1-3 \
  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-randr0 \
  libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
  libfontconfig1 libxrender1 \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b   # weasyprint (PDF)

# Optionnels (uncomment dans requirements.txt) :
sudo apt install -y libzbar0          # pyzbar (barcode)
sudo apt install -y tesseract-ocr     # pytesseract (OCR)
```

### 1.2 Affichage GUI sous WSL2

WSL2 exporte automatiquement Wayland/X11 vers Windows via WSLg dès Windows 11
(et Windows 10 récent). Vérifier :

```bash
echo "$DISPLAY"          # ex : :0
echo "$WAYLAND_DISPLAY"  # ex : wayland-0
```

Si vide : mettre à jour WSL → `wsl --update` (PowerShell admin).

### 1.3 Clone + venv + installation Python

```bash
git clone <repo-url> ts2i_ivs && cd ts2i_ivs
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
```

### 1.4 Vérification

```bash
python ts2i_ivs/main.py --check
```

Sortie attendue : tous les checks `OK ✅` (caméra, ONNX, PyQt6, FastAPI,
config.yaml, dossiers data/).

---

## 2. Installation — Raspberry Pi 5 (Bookworm 64-bit)

### 2.1 Préparer la Pi

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y \
  python3 python3-venv python3-dev python3-pip \
  build-essential pkg-config \
  libgl1 libglib2.0-0 libxkbcommon-x11-0 libdbus-1-3 \
  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-randr0 \
  libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
  libfontconfig1 libxrender1 \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
  libzbar0 tesseract-ocr
```

### 2.2 GPIO

```bash
# Ajouter l'utilisateur au groupe gpio (logout/login après).
sudo usermod -aG gpio $USER

# Backend lgpio (recommandé Pi5) ou RPi.GPIO :
pip install lgpio RPi.GPIO
```

Puis dans `config/config.yaml` :

```yaml
gpio:
  enabled: true
  backend: pi5            # stub | pi5
  pin_green: 17
  pin_red:   18
```

### 2.3 Clone + venv + Python

```bash
git clone <repo-url> ts2i_ivs && cd ts2i_ivs
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
```

### 2.4 Service systemd (lancement au boot)

`/etc/systemd/system/ts2i-ivs.service` :

```ini
[Unit]
Description=TS2I IVS v7.0
After=network.target

[Service]
Type=simple
User=ts2i
WorkingDirectory=/home/ts2i/ts2i_ivs
ExecStart=/home/ts2i/ts2i_ivs/.venv/bin/python ts2i_ivs/main.py --product P208
Restart=on-failure
Environment=QT_QPA_PLATFORM=wayland

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ts2i-ivs
sudo journalctl -u ts2i-ivs -f
```

---

## 3. Lancement

### 3.1 Mode GUI avec produit pré-sélectionné

```bash
python ts2i_ivs/main.py --product P208
```

### 3.2 Options CLI

| Option | Effet |
|---|---|
| `--mode gui` *(défaut)* | Lance `QApplication` + `MainWindow` + `InspectionScreen` |
| `--mode headless` | Pipeline sans interface (réservé v7.x) |
| `--product <id>` | `product_id` activé au démarrage (ex : `P208`) |
| `--check` | Vérifie env (modules + dossiers + config) puis quitte |
| `--debug` | Logs niveau DEBUG sur stderr |
| `--inspections N` | Headless : nb d'inspections (0 = infini) |
| `--snapshot-dir <path>` | Override `ui.snapshot_dir` du YAML |

### 3.3 Vérification d'environnement

```bash
python ts2i_ivs/main.py --check
```

### 3.4 Tests

```bash
pytest                     # toute la suite
pytest tests/ui            # UI seulement (offscreen Qt automatique)
pytest -k fleet            # gates Fleet (G_FLEET-A / B)
ruff check .               # lint
```

### 3.5 Web API (optionnel)

```bash
# Démarre l'API REST + WebSocket (auth JWT)
uvicorn web.web_server:app --host 0.0.0.0 --port 8765
```

Endpoints clés :

```
GET  /api/v1/status                       — état FSM + compteurs
POST /api/v1/products/import              — upload .ivs (multipart) — GR-13
GET  /api/v1/products/{id}/export         — download .ivs
WS   /ws/inspection                       — flux résultats temps réel
```

---

## 4. Structure du projet

```
ts2i_ivs/
├── main.py                              # CLI v7.0 racine (legacy)
├── ts2i_ivs/
│   └── main.py                          # CLI v7.0 — entry point officiel
│
├── ai/                                  # Observers + ML helpers (GR-04)
│   ├── alignment_engine.py              # SIFT+RANSAC alignment
│   ├── annotation_manager.py
│   ├── barcode_observer.py              # pyzbar
│   ├── calibration_engine.py            # 7-step §10
│   ├── caliper_observer.py              # Edge detection
│   ├── color_calibration.py
│   ├── color_inspector.py               # ΔE2000 D65
│   ├── color_observer.py
│   ├── dataset_manager.py
│   ├── feature_extractor.py             # FEATURE_DIM
│   ├── llm_explainer.py                 # Mistral 7B (display only — GR-04)
│   ├── model_builder.py                 # IsoForestModel + ONNX
│   ├── model_manager.py                 # Versioning + activate
│   ├── ocr_observer.py                  # tesseract
│   ├── sift_observer.py
│   ├── surface_observer.py              # Texture + IsoForest
│   ├── texture_analyzer.py
│   ├── yolo_engine.py / yolo_observer.py / yolo_trainer.py
│
├── camera/                              # Acquisition (UVC / GigE / fake)
│
├── config/
│   └── config.yaml                      # Config unique (GR-06)
│
├── core/                                # Domain (rules + state + auth)
│   ├── ai_observer.py                   # ABC AIObserver (GR-04)
│   ├── auth.py                          # bcrypt + JWT
│   ├── auto_switch_manager.py           # §35
│   ├── config_manager.py                # singleton chargé une fois (GR-06)
│   ├── exceptions.py                    # FleetImportError, etc.
│   ├── fleet_manager.py                 # Export/import .ivs (GR-13)
│   ├── gpio_manager.py                  # stub | pi5
│   ├── models.py                        # FinalResult, ProductDefinition…
│   ├── operators.py
│   ├── pipeline_controller.py           # FSM 9 états + SystemController
│   ├── product_registry.py              # barcode → product_id
│   ├── product_scanner.py               # daemon scanner (auto-switch)
│   ├── rule_engine.py                   # GR-08 — décide
│   ├── tier_manager.py / tier_result.py # 3 Tiers + verdicts
│   ├── traceability.py
│   ├── ui_bridge.py                     # bus signaux Qt (GR-03 / GR-05)
│   ├── usb_monitor.py                   # détection USB → Fleet (§Fleet.5)
│   └── watchdog_manager.py              # timeout pipeline (§18.1)
│
├── data/                                # Runtime (ignoré par git)
│   ├── llm/  production/  reports/  snapshots/  yolo/
│
├── evaluation/
│   └── model_validator.py               # GR-13 Gate ② anti-régression
│
├── learning/                            # §11 Apprentissage 3 gates
│   ├── global_gates.py                  # GateResult + GoldenSample
│   ├── memory_system.py
│   ├── tier_background_trainer.py       # GR-09 (daemon)
│   └── tier_learning_buffer.py
│
├── monitoring/                          # §18 — observabilité
│   ├── consecutive_nok_watcher.py       # alerte 5 / stop 10
│   ├── drift_monitor.py                 # KS-test
│   ├── industrial_alert_manager.py
│   ├── spc_service.py                   # Cp/Cpk
│   └── system_monitor.py                # CPU/RAM/Temp
│
├── pipeline/                            # 8 étapes §7
│   ├── execution_guard.py
│   ├── frames.py
│   ├── pipeline_runner.py               # orchestre + watchdog
│   ├── replay_manager.py
│   ├── tier_orchestrator.py             # ObserverRegistry + Fail-Fast
│   └── stages/                          # S1..S8
│
├── products/                            # Bibliothèque produit (config + calib + models)
│   └── P208/
│       ├── config.json                  # ProductDefinition + ProductRules
│       ├── calibration/                 # alignment_template.pkl, color_reference.json…
│       ├── dataset/                     # golden.npz (validation GR-13, ignoré git)
│       ├── logos/
│       └── models/
│           ├── active/                  # isoforest.onnx + yolo.onnx
│           └── versions/
│
├── reporting/                           # PDF/HTML (weasyprint)
│
├── scripts/                             # Outils CLI ad-hoc
│
├── storage/
│   ├── database.py                      # SQLite WAL
│   └── migrations/
│
├── tests/                               # pytest + pytest-qt
│   ├── pipeline/  ui/  unit/  …
│
├── ui/                                  # PyQt6 — vues
│   ├── components/                      # Widgets réutilisables
│   ├── main_window.py                   # MainWindow + 7 onglets
│   ├── screens/
│   │   ├── fleet_screen.py              # Export/import .ivs (§Fleet)
│   │   ├── gpio_dashboard_screen.py     # §17
│   │   ├── inspection_screen.py         # §35 active product bar + 3 grilles
│   │   ├── product_creation_screen.py   # Wizard
│   │   ├── product_canvas.py
│   │   ├── roi_editor_screen.py         # ROI per criterion
│   │   └── training_screen.py           # §11 retrain par Tier
│   ├── tabs/
│   │   ├── ai_monitoring_tab.py         # observers per tier
│   │   ├── analytics_tab.py             # tier_scores + SPC
│   │   ├── history_tab.py               # historique inspections
│   │   └── settings_tab.py              # 9 sections
│   └── tier_priority_widget.py
│
├── web/                                 # FastAPI
│   ├── api_router.py
│   ├── auth_middleware.py               # JWT
│   ├── web_server.py
│   └── ws_broadcaster.py
│
├── CLAUDE_v2.md                         # 13 Golden Rules — INTERDICTIONS strictes
├── IVS_FINAL_SPEC_v7_COMPLETE.md        # Spec fonctionnelle / contrats
├── IVS_FINAL_PHASES_v7_COMPLETE.md      # Phases d'implémentation
├── IVS_SESSIONS_v7_COMPLETE.md          # Sessions / handoff notes
├── requirements.txt
├── .gitignore
└── README.md (ce fichier)
```

---

## 5. Règles d'or (extraits CLAUDE.md)

| GR | Règle |
|---|---|
| **GR-03** | UI → SystemController → Pipeline ; **jamais d'accès direct** au pipeline depuis l'UI. |
| **GR-04** | Observer **observe**, jamais de verdict. Décision = `RuleEngine`. |
| **GR-06** | `config.yaml` chargé **une seule fois** (singleton `ConfigManager`). |
| **GR-09** | `BackgroundTrainer` toujours en thread daemon — jamais bloquer le pipeline. |
| **GR-12** | `SystemState.RUNNING` → toute édition (GPIO, settings, training) **désactivée**. |
| **GR-13** | Tout `.ivs` importé **doit** passer `ModelValidator.validate()` avant activation. Réseau ⊕ USB exclusifs. Master Unit = DEFERRED v8.0. |

Voir [`CLAUDE_v2.md`](CLAUDE_v2.md) pour la liste complète + anti-patterns.

---

## 6. Dépannage rapide

| Symptôme | Cause / fix |
|---|---|
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | Installer `libxcb-cursor0` et libxcb-* (cf. §1.1). |
| `ImportError: libGL.so.1` | `sudo apt install libgl1`. |
| `weasyprint` plante (Pango/Cairo) | `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b`. |
| FleetScreen lock GR-13 | Un import est déjà en cours sur l'autre canal (réseau ⊕ USB). |
| `ModelValidator` rejette l'import | `products/<id>/dataset/golden.npz` absent ou non conforme — voir `evaluation/model_validator.py`. |
| `QT_QPA_PLATFORM=offscreen` | Forcer mode offscreen pour les tests `pytest tests/ui`. |

---

*TS2I IVS v7.0 — `AI observe · Rule Engine décide · 3 Tiers · 5 Observers`*
