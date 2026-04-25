# IVS_FINAL_PHASES_v7.md
# TS2I IVS v7.0 — Plan de Développement Complet
# 24 Phases · 29 Gates · Architecture Rule-Governed Hierarchical

---

## Vue d'ensemble

```
P00  : Bootstrap & Configuration
P01  : Modèles de données v7.0
P02  : Caméra & Acquisition
P03  : Pipeline stubs v7.0
P04  : Calibration 7 étapes
P05  : Dataset & Features
P06  : SiftObserver + Alignment
P07  : Observers Training Init
P08  : YoloObserver
P09  : ColorObserver
P10  : SurfaceObserver (Mini Ensemble)
P11  : CaliperObserver
P12  : RuleEngine + TierManager
P13  : TierOrchestrator (Fail-Fast Hybride)
P14  : OCR + Barcode Observers
P15  : LLM Explainer v7.0
P16  : Apprentissage per-Tier
P17  : ROI Editor
P18  : Web API + WebSocket
P19  : SPC + PDF Reports
P20  : Interface principale (3 Grilles + ZoomableGrid)
P21  : Wizard Produit + TierPriorityWidget
P22  : Multi-Logo + ProductCanvas + Auto-Switch
P23  : Robustesse (Watchdog + NOK + Luminosité + CPU)
P24  : GPIO (OK=vert · NOK=rouge) + GPIO Dashboard
```

---

# ════════════════════════════════════════════════════════
# PHASE 00 — Bootstrap & Configuration
# ════════════════════════════════════════════════════════

**Objectif :** Initialiser le projet, créer la structure, vérifier l'environnement
**Durée :** 1 jour

## Tasks P00

1. Créer structure dossiers complète selon §19
2. Initialiser `config/config.yaml` selon §21
3. `storage/migrations/001_initial.sql` — schéma DB v7.0
4. `requirements.txt` v7.0 (skl2onnx, onnxruntime, ultralytics, etc.)
5. `install.sh` — auto-install RPi5/Ubuntu
6. `main.py --check` — vérification système

## Gate P00 ✅
```bash
python main.py --check
# ✅ Python 3.11
# ✅ OpenCV
# ✅ ONNX Runtime
# ✅ scikit-learn
# ✅ PyQt6
# ✅ Config file
# ✅ ALL SYSTEMS GO
```

---

# ════════════════════════════════════════════════════════
# PHASE 01 — Modèles de données v7.0
# ════════════════════════════════════════════════════════

**Objectif :** Créer tous les dataclasses frozen v7.0
**Durée :** 1.5 jours
**Spec :** §2 (GR), §5

## Tasks P01

1. `core/tier_result.py`
   - `TierLevel` enum (CRITICAL / MAJOR / MINOR)
   - `ObserverSignal` frozen dataclass
   - `TierVerdict` frozen dataclass
   - `TierOrchestratorResult` frozen dataclass

2. `core/models.py` v7.0
   - `SeverityLevel` enum (6 niveaux)
   - `SystemState` enum (9 états)
   - `LuminosityResult` frozen
   - `LLMExplanation` frozen
   - `FinalResult` v7.0 frozen (avec tier_verdicts, tier_scores)
   - `ProductDefinition` v7.0 (avec logo_definitions)
   - `LogoDefinition` frozen
   - `CriterionRule` frozen
   - `ProductRules` frozen

3. `core/exceptions.py`
   - `ConfigValidationError`
   - `ObserverError`
   - `RuleEngineError`
   - `TierOrchestratorError`

4. Validation `__post_init__` pour chaque dataclass

## Gate P01 ✅
```bash
pytest tests/unit/test_models_v7.py -v    # G-01
# ObserverSignal frozen
# TierVerdict frozen
# FinalResult frozen
# FinalResult.tier_verdicts non vide
# ProductRules.critical_criteria correct
# SeverityLevel mapping correct
# ConfigValidationError levée si invalide
```

---

# ════════════════════════════════════════════════════════
# PHASE 02 — Caméra & Acquisition
# ════════════════════════════════════════════════════════

**Objectif :** CameraManager pluggable + FakeCamera DEV
**Durée :** 1 jour
**Spec :** §21 (camera.type)

## Tasks P02

1. `camera/camera_manager.py` — ABC CameraBackend
2. `camera/fake_camera.py` — FakeCamera (images synthétiques seed=42)
   - FORBIDDEN en deployment_mode=PRODUCTION
3. `camera/uvc_camera.py` — stub UVC/V4L2
4. `core/config_manager.py` — chargement config.yaml

## Gate P02 ✅
```bash
pytest tests/unit/test_camera_manager.py -v    # G-02
# FakeCamera → frames synthétiques déterministes
# FakeCamera bloquée si PRODUCTION
# CameraManager pluggable (backend swappable)
```

---

# ════════════════════════════════════════════════════════
# PHASE 03 — Pipeline Stubs v7.0
# ════════════════════════════════════════════════════════

**Objectif :** Structure pipeline + FSM 9 états + SystemController
**Durée :** 2 jours
**Spec :** §4, §9

## Tasks P03

1. `core/pipeline_controller.py` — SystemController + FSM
2. `pipeline/pipeline_runner.py` — boucle principale
3. `pipeline/stages/s1_acquisition.py` — stub
4. `pipeline/stages/s2_preprocessor.py` — stub
5. `pipeline/stages/s3_alignment.py` — stub
6. `pipeline/stages/s4_tier_orchestrator.py` — stub
7. `pipeline/stages/s5_rule_engine_stage.py` — stub
8. `pipeline/stages/s8_output.py` — stub
9. `core/ui_bridge.py` — signals PyQt6
10. `pipeline/execution_guard.py` — GR-11 no graceful skip

## Gate P03 ✅
```bash
pytest tests/pipeline/test_pipeline_stubs_v7.py -v    # G-03
# FSM : 9 états · transitions légales
# Pipeline stubs : chain S1→S8
# ExecutionGuard : aucun stage ne retourne None
# UIBridge : signals émis
```

---

# ════════════════════════════════════════════════════════
# PHASE 04 — Calibration 7 Étapes
# ════════════════════════════════════════════════════════

**Objectif :** CalibrationEngine complet selon §10
**Durée :** 2 jours
**Spec :** §10

## Tasks P04

1. `ai/calibration_engine.py` — 7 étapes complètes
2. Étape 1 : pixel_per_mm depuis dimensions réelles
3. Étape 2 : brightness_reference (mean, std, min_ok, max_ok)
4. Étape 3 : noise_reference
5. Étape 4 : SIFT alignment template.pkl
6. Étape 5 : logo templates (un par LogoDefinition)
7. Étape 6 : color_reference.json par logo
8. Étape 7 : texture_reference.npz + IsoForest init
9. `ai/color_calibration.py` — K-means k=5 LAB
10. `pipeline/stages/luminosity_checker.py` — §42

## Gate P04 ✅
```bash
pytest tests/ai/test_calibration_engine_v7.py -v    # G-04
# 7 étapes complètes sans erreur
# pixel_per_mm calculé correctement
# brightness_reference : min_ok/max_ok cohérents
# SIFT template : ≥ 1000 keypoints
# logo_0_template.pkl créé
# color_reference.json valide
# texture_reference.npz créé
```

---

# ════════════════════════════════════════════════════════
# PHASE 05 — Dataset & Feature Extractor
# ════════════════════════════════════════════════════════

**Objectif :** DatasetManager + FeatureExtractor HOG+Color
**Durée :** 1.5 jours
**Spec :** §11

## Tasks P05

1. `ai/feature_extractor.py` — HOG 8 orientations + Color HSV 256-dim
2. `ai/dataset_manager.py` — versioning GOOD/BAD/UNKNOWN
3. `ai/annotation_manager.py` — YOLO annotations + pseudo-labels

## Gate P05 ✅
```bash
pytest tests/ai/test_feature_extractor.py -v
pytest tests/ai/test_dataset_manager.py -v    # G-05
# features : 256-dim · déterministe seed=42
# dataset versioning correct
# GOOD/BAD séparés
```

---

# ════════════════════════════════════════════════════════
# PHASE 06 — SiftObserver + AlignmentEngine
# ════════════════════════════════════════════════════════

**Objectif :** SIFT alignment + SiftObserver comme premier AI Observer
**Durée :** 2 jours
**Spec :** §6.3, §9

## Tasks P06

1. `ai/alignment_engine.py` — SIFT 5000 kp + BFMatcher + RANSAC
2. `ai/sift_observer.py` — SiftObserver(AIObserver) CRITICAL
   - observe() → ObserverSignal (jamais verdict — GR-04)
   - match_score · position_delta_mm
3. `pipeline/stages/s3_alignment.py` — stage complet
4. Brancher sur FakeCamera frames

## Gate P06 ✅
```bash
pytest tests/ai/test_sift_observer.py -v    # G-06
# SiftObserver.observe() → ObserverSignal
# ObserverSignal.passed correct selon threshold
# JAMAIS "OK" ou "NOK" retourné directement
# Déterminisme ×2
# Alignement : RANSAC inliers ≥ 10
```

---

# ════════════════════════════════════════════════════════
# PHASE 07 — Model Builder Init
# ════════════════════════════════════════════════════════

**Objectif :** IsolationForest init + ModelVersionManager
**Durée :** 1.5 jours
**Spec :** §6.5, §11.4

## Tasks P07

1. `ai/model_builder.py` — IsoForest n=1000 seed=42 + ONNX export
2. `ai/model_manager.py` — versioning + rollback per-Tier (symlinks)
3. `evaluation/model_validator.py` — golden_pass_rate ≥ 0.95

## Gate P07 ✅
```bash
pytest tests/ai/test_model_builder_v7.py -v    # G-07
# IsoForest : n=1000 · seed=42 · ONNX exporté
# ModelVersionManager : rollback < 1s
# ModelValidator : golden_pass ≥ 0.95
```

---

# ════════════════════════════════════════════════════════
# PHASE 08 — YoloObserver
# ════════════════════════════════════════════════════════

**Objectif :** YOLOv8x comme AI Observer CRITICAL
**Durée :** 2 jours
**Spec :** §6.2

## Tasks P08

1. `ai/yolo_engine.py` — inférence ONNX + NMS + Hailo stub
2. `ai/yolo_observer.py` — YoloObserver(AIObserver) CRITICAL
   - observe() → ObserverSignal {logo_found, bbox, conf}
   - JAMAIS verdict
3. `ai/yolo_trainer.py` — fine-tuning 30 epochs seed=42

## Gate P08 ✅
```bash
pytest tests/ai/test_yolo_observer.py -v    # G-08
# YoloObserver.observe() → ObserverSignal
# logo_found correct sur frame test
# confidence dans [0,1]
# Déterminisme : ×2 même résultat
# JAMAIS verdict retourné
```

---

# ════════════════════════════════════════════════════════
# PHASE 09 — ColorObserver
# ════════════════════════════════════════════════════════

**Objectif :** Color ΔE2000 comme AI Observer MAJOR
**Durée :** 1.5 jours
**Spec :** §6.4

## Tasks P09

1. `ai/color_observer.py` — ColorObserver(AIObserver) MAJOR
   - K-means k=5 CIE LAB seed=42
   - ΔE2000 vs référence calibrée
   - observe() → ObserverSignal {delta_e, color_ok}
2. `ai/color_inspector.py` — logique colorimétrie (ΔE2000)

## Gate P09 ✅
```bash
pytest tests/ai/test_color_observer.py -v    # G-09
# ColorObserver.observe() → ObserverSignal
# delta_e calculé correctement
# passed = delta_e ≤ threshold
# Déterminisme K-means seed=42 ×2
# JAMAIS verdict retourné
```

---

# ════════════════════════════════════════════════════════
# PHASE 10 — SurfaceObserver (Mini Ensemble MINOR)
# ════════════════════════════════════════════════════════

**Objectif :** Texture + IsoForest → Mini Ensemble → signal unique MINOR
**Durée :** 2 jours
**Spec :** §6.5

## Tasks P10

1. `ai/texture_analyzer.py` — GLCM+LBP+FFT
   - GLCM : distances=[1,2,4] angles=[0,45,90,135] poids=0.40
   - LBP  : P=24 R=3 uniform poids=0.35
   - FFT  : corrcoef vs ref poids=0.25
2. `ai/surface_observer.py` — SurfaceObserver(AIObserver) MINOR
   - Mini Ensemble interne : 0.55×texture + 0.45×isoforest
   - observe() → ObserverSignal {anomaly_score, anomaly_detected}
   - Seul endroit autorisé pour fusion interne

## Gate P10 ✅
```bash
pytest tests/ai/test_surface_observer.py    # G-10
# SurfaceObserver.observe() → ObserverSignal
# anomaly_score = weighted(texture + iso)
# passed = anomaly_score ≤ threshold
# AUCUN ensemble global (vérification stricte)
# Déterminisme seed=42 ×2
```

---

# ════════════════════════════════════════════════════════
# PHASE 11 — CaliperObserver
# ════════════════════════════════════════════════════════

**Objectif :** Caliper 10 lectures ±0.02mm comme Observer MAJOR
**Durée :** 1.5 jours
**Spec :** §13

## Tasks P11

1. `ai/caliper_observer.py` — CaliperObserver(AIObserver) MAJOR
   - 10 lectures · filtre 2-sigma · Gaussien fit sub-pixel
   - observe() → ObserverSignal {measured_mm, in_tolerance, delta_mm}
2. Plusieurs instances possibles (une par mesure produit)

## Gate P11 ✅
```bash
pytest tests/ai/test_caliper_observer.py -v    # G-11
# 10 lectures · filtre 2-sigma
# Précision ±0.02mm sur image test
# passed = in_tolerance correct
# Déterminisme ×2
```

---

# ════════════════════════════════════════════════════════
# PHASE 12 — RuleEngine + TierManager
# ════════════════════════════════════════════════════════

**Objectif :** Le décideur unique du système v7.0
**Durée :** 2 jours
**Spec :** §7, §5.4

## Tasks P12

1. `core/tier_manager.py`
   - `TierLevel` enum
   - `ProductRules` management
   - Chargement depuis config.json produit

2. `core/rule_engine.py`
   - `evaluate_tier(tier, signals, rules)` → TierVerdict
   - `evaluate_final(tier_verdicts)` → (verdict, severity, fail_tier)
   - Mapping Tier → Severity (§7.2)
   - Ne s'entraîne JAMAIS (GR-08)

3. `pipeline/stages/s5_rule_engine_stage.py` — stage complet

## Gate P12 ✅
```bash
pytest tests/unit/test_rule_engine.py -v    # G-12 (G-02 redésigné)
# CRITICAL fail → NOK · REJECT
# MAJOR fail → NOK · DEFECT_1
# MINOR fail mandatory → NOK · DEFECT_2
# MINOR fail non-mandatory → REVIEW
# All pass → OK
# Déterminisme ×2 identique
# RuleEngine n'a aucune méthode learn() ou train()
```

---

# ════════════════════════════════════════════════════════
# PHASE 13 — TierOrchestrator Fail-Fast Hybride
# ════════════════════════════════════════════════════════

**Objectif :** Orchestration 3 Tiers avec Fail-Fast + Background
**Durée :** 2 jours
**Spec :** §8

## Tasks P13

1. `pipeline/tier_orchestrator.py`
   - `_run_critical()` → TierVerdict
   - `_run_major()` → TierVerdict
   - `_run_minor()` → TierVerdict
   - `_launch_background()` → threading.Thread daemon
   - Fail-Fast si CRITICAL ou MAJOR fail
   - Background complete callback → DB save

2. `pipeline/stages/s4_tier_orchestrator.py` — intégration pipeline

## Gate P13 ✅
```bash
pytest tests/pipeline/test_tier_orchestrator.py -v    # G-13 (G-03 redésigné)
# CRITICAL fail → fail_fast=True · background lancé
# Background complète MAJOR+MINOR
# Rapport contient toujours les 3 tiers
# Tout pass → fail_fast=False
# Déterminisme ×2
```

---

# ════════════════════════════════════════════════════════
# PHASE 14 — OCR + Barcode Observers
# ════════════════════════════════════════════════════════

**Objectif :** OCR et Barcode comme Observers MINOR
**Durée :** 1.5 jours
**Spec :** §14, §15

## Tasks P14

1. `ai/ocr_observer.py` — OcrObserver(AIObserver) MINOR
   - 3 angles · meilleure lecture retenue
   - pattern regex depuis CriterionRule.details
2. `ai/barcode_observer.py` — BarcodeObserver(AIObserver) MINOR
   - pyzbar + pylibdmtx · 4 rotations

## Gate P14 ✅
```bash
pytest tests/ai/test_ocr_observer.py -v
pytest tests/ai/test_barcode_observer.py -v    # G-14
# OcrObserver → ObserverSignal · jamais verdict
# BarcodeObserver → ObserverSignal · jamais verdict
```

---

# ════════════════════════════════════════════════════════
# PHASE 15 — LLM Explainer v7.0
# ════════════════════════════════════════════════════════

**Objectif :** LLM avec prompt adapté aux Tiers v7.0
**Durée :** 1 jour
**Spec :** §16

## Tasks P15

1. `ai/llm_explainer.py` — prompt v7.0 adapté Tiers
   - "Tier {fail_tier} a échoué : {fail_reasons}"
   - Output JSON : summary + cause + recommendation
   - timeout=3s · fallback texte · seed=42

## Gate P15 ✅
```bash
pytest tests/ai/test_llm_explainer.py -v    # G-15
# Output structuré JSON
# Fallback si timeout
# seed=42 → déterminisme
# Display only (GR-04)
```

---

# ════════════════════════════════════════════════════════
# PHASE 16 — Apprentissage per-Tier
# ════════════════════════════════════════════════════════

**Objectif :** TierLearningBuffer × 3 + BackgroundTrainer × 3 + Gates globales
**Durée :** 3 jours
**Spec :** §11

## Tasks P16

1. `learning/tier_learning_buffer.py`
   - 3 buffers indépendants (CRITICAL / MAJOR / MINOR)
   - Gates par Tier (confidence minimale)
   - Gate stabilité 10 frames

2. `learning/tier_background_trainer.py`
   - Thread daemon par Tier
   - Retrain observers du Tier concerné
   - Validation via ModelValidator

3. `learning/global_gates.py`
   - Gate ① Stabilité
   - Gate ② Anti-régression golden_pass ≥ 0.95
   - Gate ③ Drift KS-test < 0.15

4. Rollback per-Tier dans ModelVersionManager

## Gate P16 ✅
```bash
pytest tests/ai/test_tier_learning.py -v    # G-16
# Buffer CRITICAL : gate confidence ≥ 0.80
# Buffer MAJOR    : gate confidence ≥ 0.70
# Buffer MINOR    : gate confidence ≥ 0.60
# Gate anti-régression bloque si dégradation
# Rollback MAJOR uniquement → CRITICAL intact
# Déterminisme seed=42
```

---

# ════════════════════════════════════════════════════════
# PHASE 17 — ROI Editor
# ════════════════════════════════════════════════════════

**Objectif :** Éditeur visuel zones d'inspection
**Durée :** 1.5 jours
**Spec :** §12.2

## Tasks P17

1. `ui/screens/roi_editor_screen.py`
2. `ui/components/roi_editor_widget.py`
   - Zones ROI / OCR / Caliper / Color
   - Drag-and-drop zones
   - Propriétés par zone

## Gate P17 ✅
```bash
pytest tests/ui/test_roi_editor.py -v    # G-17
# Zones créées et sauvegardées
# Coordonnées relatives [0,1] correctes
```

---

# ════════════════════════════════════════════════════════
# PHASE 18 — Web API + WebSocket
# ════════════════════════════════════════════════════════

**Objectif :** FastAPI 15 endpoints + WebSocket broadcast
**Durée :** 2 jours

## Tasks P18

1. `web/web_server.py` — FastAPI + Uvicorn
2. `web/api_router.py` — 15 endpoints v7.0
   - `/api/v1/status` · `/api/v1/inspection/start`
   - `/api/v1/results/last` · `/api/v1/tier_verdicts`
   - `/api/v1/reports/generate` · etc.
3. `web/ws_broadcaster.py` — WebSocket fire-and-forget
4. `web/auth_middleware.py` — JWT auth

## Gate P18 ✅
```bash
pytest tests/web/test_api_v7.py -v    # G-18
# 15 endpoints répondent correctement
# WebSocket émet verdict + tier_verdicts
# JWT auth fonctionne
```

---

# ════════════════════════════════════════════════════════
# PHASE 19 — SPC + PDF Reports
# ════════════════════════════════════════════════════════

**Objectif :** Statistiques Cp/Cpk + rapports PDF
**Durée :** 2 jours

## Tasks P19

1. `monitoring/spc_service.py` — X-bar/R/p/Cp/Cpk par Tier
2. `monitoring/drift_monitor.py` — KS-test par Tier
3. `reporting/pdf_reporter.py` — WeasyPrint + template HTML
   - Tier scores dans rapport
   - Distribution par Tier (CRITICAL/MAJOR/MINOR fails)

## Gate P19 ✅
```bash
pytest tests/unit/test_spc_v7.py -v    # G-19
python scripts/test_pdf_report.py
# Cp/Cpk calculés sur tier_scores
# PDF généré avec sections par Tier
```

---

# ════════════════════════════════════════════════════════
# PHASE 20 — Interface Principale
# ════════════════════════════════════════════════════════

**Objectif :** Écran inspection avec 3 grilles + overlays Tier-based
**Durée :** 3 jours
**Spec :** §12

## Tasks P20

1. `ui/main_window.py` — QMainWindow + tabs
2. `ui/screens/inspection_screen.py`
   - Grid 1 : Live
   - Grid 2 : CRITICAL tier (Logo zoom)
   - Grid 3 : Corrigé + overlays Tier colorés
3. `ui/components/zoomable_grid_view.py` — §36
4. `ui/components/fullscreen_grid_window.py` — §36.3
5. `ui/components/result_band.py` — verdict Tier-based
   - Affiche : verdict + fail_tier + fail_reasons
   - PAS de fused_score global (v7.0)
6. `ui/components/tier_verdict_badge.py`
   - CRITICAL ✅/❌ · MAJOR ✅/❌ · MINOR ✅/❌
7. `ui/components/severity_badge.py` — 6 niveaux
8. `ui/components/nok_counter_badge.py` — §41
9. `ui/components/luminosity_indicator.py` — §42
10. `ui/components/system_status_bar.py` — §43

## Gate P20 ✅
```bash
pytest tests/ui/test_inspection_screen_v7.py -v    # G-20
# ResultBand affiche fail_tier (pas fused_score)
# TierVerdictBadge correct pour chaque Tier
# ZoomableGridView auto-zoom sur défaut NOK
```

---

# ════════════════════════════════════════════════════════
# PHASE 21 — Wizard Produit + TierPriorityWidget
# ════════════════════════════════════════════════════════

**Objectif :** Wizard création produit avec définition des Tiers
**Durée :** 3 jours
**Spec :** §12

## Tasks P21

1. `ui/screens/product_creation_screen.py`
   - Étape 1 : Métadonnées
   - Étape 2 : Images référence
   - Étape 3 : Dimensions
   - Étape 4 : Canvas Logos (§37)
   - Étape 5 : TierPriorityWidget ← NOUVEAU v7.0
   - Étape 6 : Zones (ROI)
   - Étape 7 : Calibration
   - Étape 8 : Entraînement

2. `ui/tier_priority_widget.py` — §12
   - Tableau gauche : critères + Tier ComboBox + seuil
   - Preview droite : résumé par Tier (mis à jour temps réel)
   - Validation : CRITICAL vide → avertissement
   - FORBIDDEN pendant RUNNING (GR-12)

3. Export ProductRules → config.json produit

## Gate P21 ✅
```bash
pytest tests/ui/test_tier_priority_widget.py -v    # G-21
# Tableau modifiable
# Preview mis à jour temps réel
# ProductRules exporté correctement
# CRITICAL vide → avertissement affiché
# FORBIDDEN si RUNNING
```

---

# ════════════════════════════════════════════════════════
# PHASE 22 — Multi-Logo + ProductCanvas + Auto-Switch
# ════════════════════════════════════════════════════════

**Objectif :** Canvas tapis + multi-logos + auto-switch QR
**Durée :** 9 jours
**Spec :** §35, §36, §37 (hérités v6.1)

## P22-A : ZoomableGridView (1.5j) → Gate G-23
## P22-B : ProductCanvas + LogoDefinition (3j) → Gate G-25
## P22-C : LogoInspectionEngine multi-logo (2j) → Gate G-24
## P22-D : Auto-Switch QR/Barcode (2j) → Gate G-22
## P22-E : E2E tapis voiture (0.5j) → 25 gates

---

# ════════════════════════════════════════════════════════
# PHASE 23 — Robustesse Industrielle
# ════════════════════════════════════════════════════════

**Objectif :** Watchdog + NOK Watcher + Luminosité + SystemMonitor
**Durée :** 6 jours
**Spec :** §40, §41, §42, §43

## P23-A : WatchdogManager (1j) → Gate G-26
## P23-B : ConsecutiveNOKWatcher (1j) → Gate G-27
## P23-C : LuminosityChecker (1j) → Gate G-28
## P23-D : SystemMonitor CPU/RAM/Temp (2j) → Gate G-29
## P23-E : Integration + tests (1j) → 29/29 PASS

---

# ════════════════════════════════════════════════════════
# PHASE 24 — GPIO
# ════════════════════════════════════════════════════════

**Objectif :** GPIO OK=vert · NOK=rouge + Dashboard complet
**Durée :** 4 jours
**Spec :** §17

## P24-A : GPIO basique (2j)

1. `core/gpio_manager.py`
   - OK  → GPIO lampe VERTE ON
   - NOK → GPIO lampe ROUGE ON
   - REVIEW → rien
   - `gpio_stub.py` pour PC (simulation)
2. Lecture verdict depuis UIBridge (GR-03)

## P24-B : GPIO Dashboard (2j)

1. `ui/screens/gpio_dashboard_screen.py`
   - Affichage tous les pins RPi5 (INPUT/OUTPUT)
   - Config : quel pin pour quelle fonction
   - Test manuel : ON/OFF par pin
   - Monitoring temps réel (100ms)
   - Sauvegarde config GPIO dans config.yaml
   - FORBIDDEN de changer pendant RUNNING

---

## Résumé Calendrier

| Phase | Contenu | Durée | Gates |
|-------|---------|-------|-------|
| P00 | Bootstrap | 1j | G-00 |
| P01 | Modèles v7.0 | 1.5j | G-01 |
| P02 | Caméra | 1j | G-02 |
| P03 | Pipeline stubs | 2j | G-03 |
| P04 | Calibration | 2j | G-04 |
| P05 | Dataset | 1.5j | G-05 |
| P06 | SiftObserver | 2j | G-06 |
| P07 | Model Builder | 1.5j | G-07 |
| P08 | YoloObserver | 2j | G-08 |
| P09 | ColorObserver | 1.5j | G-09 |
| P10 | SurfaceObserver | 2j | G-10 |
| P11 | CaliperObserver | 1.5j | G-11 |
| P12 | RuleEngine | 2j | G-12 |
| P13 | TierOrchestrator | 2j | G-13 |
| P14 | OCR + Barcode | 1.5j | G-14 |
| P15 | LLM v7.0 | 1j | G-15 |
| P16 | Learning per-Tier | 3j | G-16 |
| P17 | ROI Editor | 1.5j | G-17 |
| P18 | Web API | 2j | G-18 |
| P19 | SPC + PDF | 2j | G-19 |
| P20 | Interface | 3j | G-20 |
| P21 | Wizard + TierWidget | 3j | G-21 |
| P22 | Multi-Logo + QR | 9j | G-22→25 |
| P23 | Robustesse | 6j | G-26→29 |
| P24 | GPIO | 4j | — |
| **Total** | | **~56 jours** | **29 Gates** |

---

*TS2I IVS v7.0 — Plan de Développement*
*24 Phases · 29 Gates · Rule-Governed Hierarchical Inspection*

---

# ════════════════════════════════════════════════════════
# PHASE FLEET — Déploiement en Flotte
# ════════════════════════════════════════════════════════

**Objectif :** Export/Import packages .ivs — réseau et USB
**Durée :** 3.5 jours
**Spec :** §Fleet
**Dépendance :** P24 complète (GPIO) + Web API opérationnelle

---

## PH_FLEET-A : FleetManager + Export/Import réseau (2j)

**Spec :** §Fleet.3, §Fleet.4

### Tasks

1. `core/fleet_manager.py`
   - `export_package(product_id, output_path)` → .ivs
   - `import_package(ivs_file_path)` → ImportResult
   - Signature SHA256 · vérification intégrité
   - GR-13 : ModelValidator avant activation
   - Rollback si validation fail

2. Endpoints API (déjà stubbed dans P18) :
   - `POST /api/v1/products/import`
   - `GET /api/v1/products/{id}/export`

3. `ui/screens/fleet_screen.py`
   - Section Export : QComboBox produit + [📦 Exporter]
   - Section Import réseau : FileDialog .ivs + POST
   - Barre progression + résultat validation

### Gate PH_FLEET-A ✅
```bash
pytest tests/unit/test_fleet_manager.py -v    # G_FLEET-A
# Export → .ivs créé + sha256 valide
# Import → validation GR-13 → activation
# Signature invalide → FleetImportError + rollback
```

---

## PH_FLEET-B : Import USB auto-detect (1.5j)

**Spec :** §Fleet.5

### Tasks

1. `core/usb_monitor.py`
   - Thread daemon polling 2s
   - Surveille /media/ (Linux) · /Volumes/ (macOS)
   - Signal `usb_ivs_found(path, mount_point)`

2. `FleetManager.import_via_usb(mount_point)`
   - Copie locale avant import
   - Appelle import_package → GR-13

3. UI Fleet Screen — Section USB :
   - Statut auto-detect (QTimer 2s)
   - Si .ivs détecté → [📥 Importer maintenant]
   - Preview package : product_id + export_date

### Gate PH_FLEET-B ✅
```bash
pytest tests/unit/test_fleet_usb.py -v    # G_FLEET-B
# UsbMonitor détecte mount simulé
# import_via_usb → GR-13 respecté
# 2 fichiers .ivs → FleetImportError
```

---

## PH_FLEET-C : Master Unit — DEFERRED

**Spec :** §Fleet.6 (RÉSERVÉ)

```
Status : DEFERRED — Non implémenté dans v7.0

Trigger : validation production ≥ 3 unités + infra réseau

Gate :
  grep -r "MasterUnit" ts2i_ivs/ → vide ✅
```

---

## Résumé Phase Fleet

| Sous-phase | Contenu | Durée | Gate |
|-----------|---------|-------|------|
| PH_FLEET-A | FleetManager + Export/Import réseau | 2j | G_FLEET-A |
| PH_FLEET-B | Import USB auto-detect | 1.5j | G_FLEET-B |
| PH_FLEET-C | Master Unit — DEFERRED | — | DEFERRED |
| **Total** | | **3.5j** | **2 Gates** |

---

## Plan de développement complet v7.0 + Fleet

| Phase | Contenu | Durée | Gates |
|-------|---------|-------|-------|
| P00→P13 | Core + Observers + RuleEngine + TierOrchestrator | 21j | G-00→13 |
| P14→P16 | OCR+LLM+Learning | 5.5j | G-14→16 |
| P17→P19 | ROI+API+SPC | 5.5j | G-17→19 |
| P20→P21 | Interface | 6j | G-20→21 |
| P22 | Multi-Logo+AutoSwitch | 9j | G-22→25 |
| P23 | Robustesse | 6j | G-26→29 |
| P24 | GPIO | 4j | — |
| PH_FLEET | Fleet Deploy | 3.5j | G_FL-A,B |
| **Total** | | **~60.5j** | **31 Gates** |

---

*TS2I IVS v7.0 — Plan de Développement Complet*
*24 Phases + PH_FLEET · 31 Gates · ~60 jours*
*Master Unit : DEFERRED — IVS v8.0*
