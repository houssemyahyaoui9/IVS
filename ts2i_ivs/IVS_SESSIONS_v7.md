# IVS_SESSIONS_v7.md
# TS2I IVS v7.0 — Sessions de Développement
# Chaque session = 1 Prompt Claude Code + 1 Gate
# Architecture : Rule-Governed Hierarchical Inspection

---

## Workflow Claude Code

```bash
# Chaque session :
source .venv/bin/activate
claude

/session          → voir où on en est
# Copier Prompt S0X-Y ci-dessous
# Coller dans Claude Code
/gate             → vérifier après complétion
make test         → vérification complète
git commit -m "S0X-Y: description [§N] ✅"
```

---

# ════════════════════════════════════════════════════════
# PHASE 00 — Bootstrap
# ════════════════════════════════════════════════════════

## S00-A : Structure projet + config

```
📋 الهدف  : Initialiser projet v7.0 — structure + config
⏱ المدة  : 1 jour
📄 الـ Spec: §21
```

### 🤖 Prompt S00-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §21 (config.yaml) et §19 (fichiers).

MISSION : Créer la structure complète du projet IVS v7.0.

Structure dossiers à créer :
ts2i_ivs/
├── core/           (rule_engine, tier_manager, ai_observer, models, etc.)
├── pipeline/stages/
├── ai/             (yolo_observer, sift_observer, color_observer, surface_observer, etc.)
├── monitoring/
├── learning/
├── camera/
├── web/
├── reporting/report_templates/
├── ui/screens/ ui/components/ ui/tabs/
├── storage/migrations/
├── config/
├── products/example/
├── data/production/{OK,NOK,REVIEW}/ data/snapshots/ data/llm/ data/yolo/
├── tests/unit/ tests/pipeline/ tests/ai/ tests/web/ tests/ui/ tests/fixtures/
├── scripts/
└── logs/

Créer config/config.yaml complet selon §21.
Créer storage/migrations/001_initial.sql avec schéma v7.0 :
  TABLE products : product_id, name, version, width_mm, height_mm,
                   product_barcode, created_at, station_id
  TABLE inspections : id, product_id, frame_id, verdict, severity,
                      fail_tier, fail_reasons, tier_scores (JSON),
                      tier_verdicts (JSON), llm_summary, model_versions,
                      background_complete, operator, timestamp
  TABLE operators : id, name, role, pin_hash, active
  TABLE operator_stats : operator_id, product_id, total, ok_count, nok_count
  TABLE schema_version : version, applied_at

Créer main.py avec --check :
  Vérifier Python 3.11, OpenCV, ONNX Runtime, scikit-learn,
  PyQt6, FastAPI, config.yaml, dossiers data/
  Afficher "✅ ALL SYSTEMS GO" si tout OK

Créer requirements.txt v7.0 :
  opencv-python>=4.9
  numpy>=1.26
  scikit-learn>=1.4
  scikit-image>=0.22
  scipy>=1.12
  onnxruntime>=1.17
  skl2onnx>=1.16
  ultralytics>=8.1
  PyQt6>=6.6
  fastapi>=0.109
  uvicorn>=0.27
  psutil>=5.9
  pytesseract>=0.3
  pyzbar>=0.1
  colormath>=3.0
  weasyprint>=60.0
  python-jose>=3.3
  passlib>=1.7
  httpx>=0.26
  pytest>=8.0
  black>=24.0
  ruff>=0.2
```

### ✅ Gate S00-A
```bash
python ts2i_ivs/main.py --check
# ✅ ALL SYSTEMS GO
ls ts2i_ivs/core/ ts2i_ivs/ai/ ts2i_ivs/pipeline/
# tous les dossiers présents
```

---

# ════════════════════════════════════════════════════════
# PHASE 01 — Modèles de données v7.0
# ════════════════════════════════════════════════════════

## S01-A : ObserverSignal + TierVerdict + FinalResult

```
📋 الهدف  : Dataclasses frozen v7.0 — cœur du système
⏱ المدة  : 1.5 jours
📄 الـ Spec: §5
```

### 🤖 Prompt S01-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §5 (Modèle de Données) complet.
Lire CLAUDE.md §GR-01 à GR-12.

MISSION : core/tier_result.py + core/models.py + core/exceptions.py

PARTIE 1 : core/tier_result.py

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class TierLevel(Enum):
    CRITICAL = "CRITICAL"
    MAJOR    = "MAJOR"
    MINOR    = "MINOR"

@dataclass(frozen=True)
class ObserverSignal:
    observer_id   : str
    tier          : TierLevel
    passed        : bool
    confidence    : float
    value         : float
    threshold     : float
    details       : dict       # utiliser field(default_factory=dict)
    error_msg     : Optional[str]
    latency_ms    : float

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence {self.confidence} hors [0,1]")
        if not (0.0 <= self.value):
            raise ValueError(f"value {self.value} < 0")

@dataclass(frozen=True)
class TierVerdict:
    tier          : TierLevel
    passed        : bool
    fail_reasons  : tuple[str, ...]
    signals       : tuple[ObserverSignal, ...]
    tier_score    : float
    completed     : bool
    latency_ms    : float

    def __post_init__(self):
        if not (0.0 <= self.tier_score <= 1.0):
            raise ValueError(f"tier_score {self.tier_score} hors [0,1]")

@dataclass(frozen=True)
class TierOrchestratorResult:
    critical      : TierVerdict
    major         : Optional[TierVerdict]
    minor         : Optional[TierVerdict]
    fail_fast     : bool

PARTIE 2 : core/models.py

Créer TOUS les dataclasses selon §5 :
- SeverityLevel enum (EXCELLENT/ACCEPTABLE/REVIEW/DEFECT_1/DEFECT_2/REJECT)
- SystemState enum (9 états §4)
- SwitchResult enum
- LearningDecision enum
- PhysicalDimensions frozen
- CameraResolution frozen
- BoundingBox frozen (avec propriétés cx, cy, to_pixel())
- LuminosityResult frozen
- LLMExplanation frozen
- CriterionRule frozen (criterion_id, label, tier, observer_id, threshold, enabled, mandatory)
- ProductRules frozen (product_id, criteria, propriétés critical_criteria/major_criteria/minor_criteria)
- LogoDefinition frozen (§37 hérité v6.1)
- ProductDefinition frozen v7.0 (avec logo_definitions, product_barcode)
- FinalResult frozen v7.0 :
    frame_id, product_id, model_versions,
    verdict, severity, fail_tier, fail_reasons,
    tier_verdicts (dict[str, TierVerdict]),
    tier_scores (dict[str, float]),
    llm_explanation, pipeline_ms, background_complete,
    luminosity_result, timestamp

PARTIE 3 : core/exceptions.py

class ConfigValidationError(ValueError): pass
class ObserverError(RuntimeError): pass
class RuleEngineError(RuntimeError): pass
class TierOrchestratorError(RuntimeError): pass
class PipelineTimeoutError(RuntimeError): pass
class CameraError(RuntimeError): pass

Tout doit être @dataclass(frozen=True).
Validation __post_init__ pour chaque dataclass.
seed=42 pour tout élément stochastique (GR-01).
```

### ✅ Gate S01-A
```bash
pytest tests/unit/test_models_v7.py -v    # G-01
# ObserverSignal frozen : modification lève FrozenInstanceError
# TierVerdict frozen
# FinalResult frozen
# FinalResult.tier_verdicts dict valide
# ProductRules.critical_criteria filtre correct
# SeverityLevel : 6 niveaux
# ConfigValidationError levée si dimensions négatives
```

---

# ════════════════════════════════════════════════════════
# PHASE 02 — Caméra
# ════════════════════════════════════════════════════════

## S02-A : CameraManager + FakeCamera

```
📋 الهدف  : Acquisition frames + FakeCamera DEV
⏱ المدة  : 1 jour
📄 الـ Spec: §21 camera.type
```

### 🤖 Prompt S02-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §21 (camera config).

MISSION : camera/camera_manager.py + camera/fake_camera.py

CameraBackend (ABC) :
  grab_frame() → RawFrame   (frame_id, image np.ndarray, timestamp)
  start() → None
  stop()  → None
  is_connected() → bool

FakeCamera (CameraBackend) :
  Génère frames synthétiques DÉTERMINISTES (seed=42)
  frame.image : 1920×1080×3 uint8
    - fond gris 200
    - rectangle produit (tapis)
    - zones logo (bleu + rouge)
    - bruit gaussien seed=42
  frame_id = f"FAKE_{n:06d}"

  INTERDIT en deployment_mode=PRODUCTION :
    if config.deployment_mode == "PRODUCTION":
        raise ConfigValidationError(
            "FakeCamera FORBIDDEN in PRODUCTION mode"
        )

CameraManager :
  Charge le bon backend selon config.camera.type
  fake → FakeCamera
  uvc  → UvcCamera (stub)
  gige → GigECamera (stub)
  rtsp → RtspCamera (stub)

core/config_manager.py :
  Charge config.yaml au démarrage (une seule fois — GR-06)
  Expose get(key, default) avec notation pointée
  ex : config.get("camera.type", "fake")
  INTERDIT de recharger dans la boucle d'inspection
```

### ✅ Gate S02-A
```bash
pytest tests/unit/test_camera_manager.py -v    # G-02
# FakeCamera : frames synthétiques identiques (seed=42) ×2
# FakeCamera : lève ConfigValidationError si PRODUCTION
# CameraManager : pluggable (swap backend)
# RawFrame : frame_id séquentiel
```

---

# ════════════════════════════════════════════════════════
# PHASE 03 — Pipeline Stubs
# ════════════════════════════════════════════════════════

## S03-A : FSM + SystemController + Pipeline chain

```
📋 الهدف  : FSM 9 états + pipeline S1→S8 stubs + UIBridge
⏱ المدة  : 2 jours
📄 الـ Spec: §4, §9
```

### 🤖 Prompt S03-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §4 (FSM) et §9 (Pipeline).

MISSION : core/pipeline_controller.py + pipeline/ + core/ui_bridge.py

SystemController :
  Gère la FSM 9 états :
    IDLE_NO_PRODUCT → IMAGE_CAPTURE → CALIBRATING → TRAINING
    → IDLE_READY → RUNNING → REVIEW → ERROR → SHUTTING_DOWN

  transition(new_state) → None :
    Vérifie la transition est légale (tableau §4)
    Lève SystemStateError si illégale
    Émet signal via UIBridge

  start_inspection() · stop_inspection() · emergency_stop()
  activate_product(product_id) · get_state() → SystemState

UIBridge (QObject) :
  Tous les signals Qt pour communication Pipeline → UI
  Respecte GR-03 (UI via SystemController uniquement)
  Signals :
    state_changed = pyqtSignal(str)
    inspection_result = pyqtSignal(object)    # FinalResult
    tier_verdict_ready = pyqtSignal(str, object)  # tier, TierVerdict
    background_complete = pyqtSignal(object)  # FinalResult complet
    system_snapshot = pyqtSignal(object)      # SystemSnapshot
    nok_counter_update = pyqtSignal(int)
    luminosity_update = pyqtSignal(object)    # LuminosityResult
    watchdog_triggered = pyqtSignal()
    auto_switch_started = pyqtSignal(str)     # product_name

Pipeline stubs (chain S1→S8) :
  Chaque stage : process(input) → output
  ExecutionGuard : aucun stage ne retourne None (GR-11)
    Si stage échoue → retourner ErrorResult (jamais None)

  S1 : Acquisition    → RawFrame
  S2 : PreProcess     → ProcessedFrame (CLAHE + LuminosityCheck)
  S3 : Alignment      → AlignedFrame
  S4 : TierOrchestrator → TierOrchestratorResult
  S5 : RuleEngineStage → FinalResult (tier_verdicts + verdict)
  S8 : Output          → (LLM + Learning + GPIO + WebSocket + DB)
```

### ✅ Gate S03-A
```bash
pytest tests/pipeline/test_pipeline_stubs_v7.py -v    # G-03
# FSM : toutes transitions légales fonctionnent
# FSM : transitions illégales lèvent erreur
# Pipeline S1→S8 : chain sans None
# ExecutionGuard : aucun None retourné
# UIBridge : signals émis aux bons moments
```

---

# ════════════════════════════════════════════════════════
# PHASE 04 — Calibration
# ════════════════════════════════════════════════════════

## S04-A : CalibrationEngine 7 étapes

```
📋 الهدف  : Calibration complète selon §10
⏱ المدة  : 2 jours
📄 الـ Spec: §10
```

### 🤖 Prompt S04-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §10 (Calibration) complet.

MISSION : ai/calibration_engine.py + pipeline/stages/luminosity_checker.py

CalibrationEngine :
  calibrate(reference_images, product_def) → CalibrationResult

  Étape 1 : pixel_per_mm
    pixel_per_mm = image.width / product_def.physical_dimensions.width_mm
    Vérifier cohérence avec height

  Étape 2 : brightness_reference
    gray = cv2.cvtColor(ref_image, cv2.COLOR_BGR2GRAY)
    mean_b = float(np.mean(gray))
    std_b  = float(np.std(gray))
    min_ok = mean_b * (1 - warning_percent/100)
    max_ok = mean_b * (1 + warning_percent/100)
    Sauvegarder dans brightness_reference.json

  Étape 3 : noise_reference
    noise_floor = float(np.percentile(gray, 5))
    Sauvegarder

  Étape 4 : SIFT alignment template
    sift = cv2.SIFT_create(nfeatures=5000)
    kp, des = sift.detectAndCompute(gray, None)
    Sauvegarder en alignment_template.pkl (keypoints + descriptors)
    Si < 1000 keypoints → CalibrationError

  Étape 5 : Logo templates (par LogoDefinition)
    Pour chaque logo_def dans product_def.logo_definitions :
      Extraire crop zone logo
      kp, des = sift.detectAndCompute(crop, None)
      Sauvegarder logo_{idx}_template.pkl

  Étape 6 : Color reference
    Pour chaque logo_def :
      Extraire crop zone logo
      lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
      kmeans = KMeans(n_clusters=5, random_state=42)
      kmeans.fit(lab.reshape(-1, 3))
      dominant = kmeans.cluster_centers_[np.bincount(kmeans.labels_).argmax()]
      Sauvegarder color_reference.json : {logo_id: {lab_mean, ref_hex}}

  Étape 7 : Texture reference
    GLCM properties sur zone produit complète
    LBP histogram
    FFT magnitude normalisée
    Sauvegarder texture_reference.npz
    IsoForest initial (fit sur frames GOOD) → isolation_forest_init.onnx

LuminosityChecker :
  check(raw_frame, product_def) → LuminosityResult
  Comparer mean_brightness vs brightness_reference
  warning si écart > 15% · critical si > 30%
  Intégré dans S2
```

### ✅ Gate S04-A
```bash
pytest tests/ai/test_calibration_engine_v7.py -v    # G-04
# 7 étapes sans erreur
# pixel_per_mm = 1920 / 800 = 2.40
# SIFT template ≥ 1000 keypoints
# logo_0_template.pkl créé
# color_reference.json : {logo_id: {lab_mean, ref_hex}}
# texture_reference.npz créé
# LuminosityChecker : frame sombre → WARNING
```

---

# ════════════════════════════════════════════════════════
# PHASE 05 — Dataset & Features
# ════════════════════════════════════════════════════════

## S05-A : FeatureExtractor + DatasetManager

```
📋 الهدف  : Features HOG+Color + Dataset versioning
⏱ المدة  : 1.5 jours
📄 الـ Spec: §11
```

### 🤖 Prompt S05-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §11 (Apprentissage).

MISSION : ai/feature_extractor.py + ai/dataset_manager.py

FeatureExtractor :
  extract(frame: np.ndarray) → np.ndarray (256-dim, float32)

  HOG 128-dim :
    fd = hog(gray, orientations=8,
             pixels_per_cell=(16,16),
             cells_per_block=(1,1),
             feature_vector=True)

  Color histogram HSV 128-dim :
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist_h = np.histogram(hsv[:,:,0], bins=64, range=(0,180))[0]
    hist_s = np.histogram(hsv[:,:,1], bins=32, range=(0,256))[0]
    hist_v = np.histogram(hsv[:,:,2], bins=32, range=(0,256))[0]
    color_feat = np.concatenate([hist_h, hist_s, hist_v])

  features = np.concatenate([hog_feat / (np.linalg.norm(hog_feat) + 1e-6),
                               color_feat / (color_feat.sum() + 1e-6)])
  → 256-dim float32 · normalisé

DatasetManager :
  Séparés par product_id + Tier :
    products/{id}/dataset/GOOD/
    products/{id}/dataset/BAD/
    products/{id}/dataset/UNKNOWN/
  add_sample(frame, label, tier, product_id) → None
  get_features(label, tier, product_id) → np.ndarray
  Version incrémentale + backup avant retrain
```

### ✅ Gate S05-A
```bash
pytest tests/ai/test_feature_extractor.py -v
pytest tests/ai/test_dataset_manager.py -v    # G-05
# features : 256-dim float32
# features déterministes seed=42 ×2
# dataset séparé par Tier
```

---

# ════════════════════════════════════════════════════════
# PHASE 06 — SiftObserver
# ════════════════════════════════════════════════════════

## S06-A : SIFT Alignment + SiftObserver

```
📋 الهدف  : Premier AI Observer v7.0 (CRITICAL tier)
⏱ المدة  : 2 jours
📄 الـ Spec: §6.1, §6.3
```

### 🤖 Prompt S06-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §6.1 (ABC) et §6.3 (SiftObserver).
Lire CLAUDE.md GR-04 (séparation Observer/RuleEngine).

MISSION : ai/sift_observer.py + ai/alignment_engine.py

AIObserver (ABC dans core/ai_observer.py) :
  @property observer_id → str
  @property tier → TierLevel
  observe(frame, product_def, rule) → ObserverSignal
  JAMAIS de verdict dans observe() — GR-04

AlignmentEngine (ai/alignment_engine.py) :
  sift = cv2.SIFT_create(nfeatures=5000)
  matcher = cv2.BFMatcher(cv2.NORM_L2)

  align(frame, template) → AlignedFrame :
    kp1, des1 = sift.detectAndCompute(gray_frame, None)
    kp2, des2 = template.keypoints, template.descriptors
    matches = matcher.knnMatch(des1, des2, k=2)
    good = [m for m,n in matches if m.distance < 0.75 * n.distance]
    Si len(good) < 10 → AlignmentError
    H, _ = cv2.findHomography(pts_src, pts_dst, cv2.RANSAC, 5.0)
    aligned = cv2.warpPerspective(frame, H, (w, h))
    → AlignedFrame avec homography matrix

SiftObserver (ai/sift_observer.py) :
  observer_id = "sift"
  tier = TierLevel.CRITICAL

  observe(frame, product_def, rule) → ObserverSignal :
    Pour chaque logo_def dans product_def.logo_definitions :
      Charger logo_{idx}_template.pkl
      kp1, des1 = sift.detectAndCompute(crop, None)
      Matcher vs template
      match_score = len(good_matches) / max(len(template_kp), 1)
      match_score = min(1.0, match_score)

      Calculer position_delta_mm :
        detected_center = centroid des good_matches dans frame
        expected_center = logo_def.position_relative × (w, h)
        delta_px = distance euclidienne
        delta_mm = delta_px / pixel_per_mm

      passed = match_score >= rule.threshold AND delta_mm <= logo_def.tolerance_mm

    → ObserverSignal(
        observer_id="sift",
        tier=TierLevel.CRITICAL,
        passed=passed,
        confidence=match_score,
        value=match_score,
        threshold=rule.threshold,
        details={"position_delta_mm": delta_mm, "good_matches": len(good)},
        error_msg=None,
        latency_ms=elapsed
      )

    INTERDIT de retourner "OK" ou "NOK" ou un verdict quelconque.
    SEUL ObserverSignal est autorisé.

Intégrer AlignmentEngine dans S3 (s3_alignment.py).
```

### ✅ Gate S06-A
```bash
pytest tests/ai/test_sift_observer.py -v    # G-06
# SiftObserver.observe() → ObserverSignal (pas "OK"/"NOK")
# ObserverSignal.tier == TierLevel.CRITICAL
# passed correct selon threshold
# confidence dans [0, 1]
# Déterminisme ×2 identique
# AlignmentEngine : ≥ 10 good matches sur frame test
```

---

# ════════════════════════════════════════════════════════
# PHASE 07 — Model Builder
# ════════════════════════════════════════════════════════

## S07-A : IsolationForest + ModelVersionManager

```
📋 الهدف  : Init IsoForest + versioning per-Tier
⏱ المدة  : 1.5 jours
📄 الـ Spec: §6.5, §11.4
```

### 🤖 Prompt S07-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §6.5 et §11.4.

MISSION : ai/model_builder.py + ai/model_manager.py + evaluation/model_validator.py

IsolationForestBuilder :
  build(features: np.ndarray, product_id: str) → IsoForestModel :
    iso = IsolationForest(
        n_estimators=1000,
        contamination="auto",
        bootstrap=True,
        random_state=42
    )
    iso.fit(features)
    # Export ONNX
    initial_type = [("float_input", FloatTensorType([None, 256]))]
    onnx_model = convert_sklearn(iso, initial_types=initial_type, target_opset=12)
    # Sauvegarder dans products/{id}/models/iso_forest_{tier}.onnx

ModelVersionManager :
  Structure :
    products/{id}/models/
      active/    → symlinks vers versions actives
      versions/  → v1/, v2/, v3/, ...

  activate_version(observer_id, version_path) → None :
    os.symlink(version_path, active/{observer_id})

  rollback_tier(tier: TierLevel, product_id) → None :
    Identifie observers du tier
    Pour chaque observer : swap active → previous
    Log INFO "Rollback {tier} : {v_current} → {v_prev}"
    Durée < 1s (symlinks)

ModelValidator :
  validate(new_model, golden_dataset, current_model) → bool :
    new_pass_rate = evaluate(new_model, golden_dataset)
    cur_pass_rate = evaluate(current_model, golden_dataset)
    return (new_pass_rate >= 0.95) and (new_pass_rate >= cur_pass_rate)
```

### ✅ Gate S07-A
```bash
pytest tests/ai/test_model_builder_v7.py -v    # G-07
# IsoForest : n=1000 · seed=42 · ONNX exporté correctement
# ModelVersionManager : rollback < 1s (symlinks)
# rollback_tier MAJOR → CRITICAL intact
# ModelValidator : golden_pass < 0.95 → rejet modèle
```

---

# ════════════════════════════════════════════════════════
# PHASE 08 — YoloObserver
# ════════════════════════════════════════════════════════

## S08-A : YOLOv8x comme Observer CRITICAL

```
📋 الهدف  : YOLO observer pur — jamais de verdict
⏱ المدة  : 2 jours
📄 الـ Spec: §6.2
```

### 🤖 Prompt S08-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §6.2 (YoloObserver) complet.
Lire CLAUDE.md GR-04 (séparation stricte Observer/RuleEngine).

MISSION : ai/yolo_engine.py + ai/yolo_observer.py + ai/yolo_trainer.py

YoloEngine (ai/yolo_engine.py) :
  Inférence ONNX onnxruntime :
    session = onnxruntime.InferenceSession(
        model_path,
        sess_options=session_options  # seed=42 dans options
    )
  Préprocess : resize 640×640 · normalisation /255.0 · CHW
  NMS : cv2.dnn.NMSBoxes(conf=0.45, iou=0.45)
  Output : list[Detection(bbox, class_id, confidence)]

YoloObserver (ai/yolo_observer.py) :
  observer_id = "yolo_v8x"
  tier = TierLevel.CRITICAL

  observe(frame, product_def, rule) → ObserverSignal :
    detections = self._engine.infer(frame)

    # Chercher logo dans zone attendue
    best_detection = None
    for det in detections :
      if detection_in_expected_zone(det, logo_def, tolerance_mm) :
        best_detection = max(best_detection, det, key=lambda d: d.confidence)

    passed = (best_detection is not None and
              best_detection.confidence >= rule.threshold)

    → ObserverSignal(
        observer_id = "yolo_v8x",
        tier        = TierLevel.CRITICAL,
        passed      = passed,
        confidence  = best_detection.confidence if best_detection else 0.0,
        value       = best_detection.confidence if best_detection else 0.0,
        threshold   = rule.threshold,
        details     = {"bbox": best_detection.bbox if best_detection else None,
                       "class_id": best_detection.class_id if best_detection else -1},
        error_msg   = None,
        latency_ms  = elapsed
      )

    INTERDIT : retourner "OK" / "NOK" / tout verdict — GR-04

YoloTrainer (ai/yolo_trainer.py) :
  train(dataset_path, product_id, epochs=30) → str :
    model = YOLO("yolov8x.pt")
    results = model.train(
        data=data_yaml,
        epochs=30,
        batch=4,
        device="cpu",
        seed=42,
        project=f"products/{product_id}/models",
        name="yolo_train"
    )
    # Export ONNX
    model.export(format="onnx", opset=12)
    return onnx_path
```

### ✅ Gate S08-A
```bash
pytest tests/ai/test_yolo_observer.py -v    # G-08
# YoloObserver.observe() → ObserverSignal uniquement
# observer_id == "yolo_v8x"
# tier == TierLevel.CRITICAL
# confidence dans [0, 1]
# Déterminisme ×2
# INTERDIT vérifié : aucune méthode retourne "OK"/"NOK"
```

---

# ════════════════════════════════════════════════════════
# PHASE 09 — ColorObserver
# ════════════════════════════════════════════════════════

## S09-A : ΔE2000 comme Observer MAJOR

```
📋 الهدف  : Couleur broderie — observer pur MAJOR tier
⏱ المدة  : 1.5 jours
📄 الـ Spec: §6.4
```

### 🤖 Prompt S09-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §6.4 (ColorObserver) complet.

MISSION : ai/color_observer.py + ai/color_inspector.py

ColorInspector (ai/color_inspector.py) :
  delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) → float :
    Implémentation ΔE2000 complète (CIEDE2000)
    Utiliser la formule standard avec kL=kC=kH=1

  dominant_color_lab(crop: np.ndarray, k: int = 5) → np.ndarray :
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(lab.reshape(-1, 3))
    dominant_idx = np.bincount(kmeans.labels_).argmax()
    return kmeans.cluster_centers_[dominant_idx]

ColorObserver (ai/color_observer.py) :
  observer_id = "color_de2000"
  tier = TierLevel.MAJOR

  observe(frame, product_def, rule) → ObserverSignal :
    # Extraire crop zone logo depuis BBox normalisée
    h, w = frame.shape[:2]
    x1 = int(logo_def.position_relative[0] * w - logo_def.width_mm * ppm / 2)
    ... (clamp [0, w/h])
    crop = frame[y1:y2, x1:x2]

    # Couleur mesurée
    measured_lab = self._inspector.dominant_color_lab(crop, k=5)

    # Référence calibrée
    ref_lab = color_reference[logo_def.logo_id]["lab_mean"]

    # ΔE2000
    delta_e = self._inspector.delta_e_2000(measured_lab, ref_lab)

    passed = delta_e <= rule.threshold   # threshold = delta_e max

    → ObserverSignal(
        observer_id = "color_de2000",
        tier        = TierLevel.MAJOR,
        passed      = passed,
        confidence  = max(0.0, 1.0 - delta_e / 30.0),
        value       = delta_e,
        threshold   = rule.threshold,
        details     = {"delta_e": delta_e,
                       "measured_lab": measured_lab.tolist(),
                       "ref_lab": ref_lab},
        error_msg   = None,
        latency_ms  = elapsed
      )

    JAMAIS verdict retourné — GR-04
```

### ✅ Gate S09-A
```bash
pytest tests/ai/test_color_observer.py -v    # G-09
# ColorObserver.observe() → ObserverSignal
# tier == TierLevel.MAJOR
# delta_e calculé correctement (frame bleu #0028A0)
# passed = delta_e ≤ threshold
# Déterminisme K-means seed=42 ×2
```

---

# ════════════════════════════════════════════════════════
# PHASE 10 — SurfaceObserver
# ════════════════════════════════════════════════════════

## S10-A : Mini Ensemble Texture+IsoForest MINOR

```
📋 الهدف  : Seul Mini Ensemble autorisé — observer MINOR
⏱ المدة  : 2 jours
📄 الـ Spec: §6.5
```

### 🤖 Prompt S10-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §6.5 (SurfaceObserver) complet.
Lire CLAUDE.md anti-patterns (Ensemble global INTERDIT).

MISSION : ai/texture_analyzer.py + ai/surface_observer.py

TextureAnalyzer (ai/texture_analyzer.py) :
  analyze(frame: np.ndarray,
          reference: TextureReference) → float :
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # GLCM — poids 0.40
    glcm = graycomatrix(gray, distances=[1,2,4],
                        angles=[0, np.pi/4, np.pi/2, 3*np.pi/4],
                        symmetric=True, normed=True)
    props = {p: graycoprops(glcm, p).mean()
             for p in ['contrast','dissimilarity','homogeneity','energy','correlation']}
    glcm_score = cosine_similarity(
        list(props.values()), reference.glcm_props
    )

    # LBP — poids 0.35
    lbp = local_binary_pattern(gray, P=24, R=3, method='uniform')
    hist, _ = np.histogram(lbp.ravel(), bins=26, range=(0, 26), density=True)
    lbp_score = 1.0 - chi2_distance(hist, reference.lbp_hist)

    # FFT — poids 0.25
    fft = np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(gray))))
    fft_norm = fft / (fft.max() + 1e-6)
    fft_score = float(np.corrcoef(
        fft_norm.ravel(), reference.fft_spectrum.ravel()
    )[0, 1])

    return 0.40 * glcm_score + 0.35 * lbp_score + 0.25 * fft_score

SurfaceObserver (ai/surface_observer.py) :
  observer_id = "surface_mini_ensemble"
  tier = TierLevel.MINOR

  NOTE : Mini Ensemble INTERNE UNIQUEMENT
  Le Rule Engine voit un seul ObserverSignal (pas deux scores séparés)

  observe(frame, product_def, rule) → ObserverSignal :
    # Score texture
    texture_score = self._texture.analyze(frame, reference)
    texture_anomaly = 1.0 - texture_score   # 0=normal, 1=anomalie

    # Score IsoForest
    features = self._extractor.extract(frame)
    iso_score = self._iso_session.run(...)   # ONNX inference
    iso_anomaly = float(np.clip(-iso_score / 3.0, 0.0, 1.0))

    # Mini Ensemble INTERNE (seul endroit autorisé)
    anomaly_score = 0.55 * texture_anomaly + 0.45 * iso_anomaly
    passed = anomaly_score <= rule.threshold

    → ObserverSignal(
        observer_id = "surface_mini_ensemble",
        tier        = TierLevel.MINOR,
        passed      = passed,
        confidence  = 1.0 - anomaly_score,
        value       = anomaly_score,
        threshold   = rule.threshold,
        details     = {"texture_anomaly": texture_anomaly,
                       "iso_anomaly": iso_anomaly,
                       "anomaly_score": anomaly_score},
        error_msg   = None,
        latency_ms  = elapsed
      )
```

### ✅ Gate S10-A
```bash
pytest tests/ai/test_surface_observer.py -v    # G-10
# SurfaceObserver → ObserverSignal (pas deux scores séparés)
# observer_id == "surface_mini_ensemble"
# tier == TierLevel.MINOR
# anomaly_score = 0.55*texture + 0.45*iso (vérifier dans details)
# Déterminisme seed=42 ×2
# AUCUN Ensemble global ailleurs dans le code (grep check)
```

---

# ════════════════════════════════════════════════════════
# PHASE 11 — CaliperObserver
# ════════════════════════════════════════════════════════

## S11-A : Mesures ±0.02mm Observer MAJOR

```
📋 الهدف  : Caliper précis comme Observer MAJOR
⏱ المدة  : 1.5 jours
📄 الـ Spec: §13
```

### 🤖 Prompt S11-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §13 (CaliperObserver).

MISSION : ai/caliper_observer.py

CaliperObserver (ai/caliper_observer.py) :
  observer_id = f"caliper_{measurement_id}"
  tier = TierLevel.MAJOR

  observe(frame, product_def, rule) → ObserverSignal :
    readings = []
    for _ in range(10) :
      # Extraire profil perpendiculaire à la ligne de mesure
      profile = extract_edge_profile(frame, measurement_def)
      # Gradient Sobel
      gradient = np.gradient(profile.astype(float))
      # Fit Gaussien sub-pixel pour localiser bord
      from scipy.optimize import curve_fit
      popt, _ = curve_fit(gaussian, x, gradient, p0=[...])
      edge_px = popt[1]   # position sub-pixel
      readings.append(edge_px)

    # Filtre 2-sigma
    mean_r = np.mean(readings)
    std_r  = np.std(readings)
    filtered = [r for r in readings if abs(r - mean_r) <= 2 * std_r]

    measured_px = np.mean(filtered)
    measured_mm = measured_px / product_def.pixel_per_mm
    expected_mm = rule.threshold   # ici threshold = dimension attendue
    delta_mm    = abs(measured_mm - expected_mm)
    tolerance   = measurement_def.tolerance_mm
    in_tolerance = delta_mm <= tolerance

    → ObserverSignal(
        observer_id = self.observer_id,
        tier        = TierLevel.MAJOR,
        passed      = in_tolerance,
        confidence  = max(0.0, 1.0 - delta_mm / (tolerance * 3)),
        value       = measured_mm,
        threshold   = expected_mm,
        details     = {"delta_mm": delta_mm,
                       "tolerance_mm": tolerance,
                       "readings_count": len(filtered)},
        error_msg   = None,
        latency_ms  = elapsed
      )
```

### ✅ Gate S11-A
```bash
pytest tests/ai/test_caliper_observer.py -v    # G-11
# 10 lectures · filtre 2-sigma
# Précision ±0.02mm sur image synthétique
# in_tolerance correct
# Déterminisme ×2
```

---

# ════════════════════════════════════════════════════════
# PHASE 12 — RuleEngine
# ════════════════════════════════════════════════════════

## S12-A : Décideur unique v7.0

```
📋 الهدف  : RuleEngine — seul décideur du système
⏱ المدة  : 2 jours
📄 الـ Spec: §7
```

### 🤖 Prompt S12-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §7 (RuleEngine) complet.
Lire CLAUDE.md GR-02 (Rule Engine = seul décideur) et GR-08 (jamais apprend).

MISSION : core/rule_engine.py + core/tier_manager.py

TierManager (core/tier_manager.py) :
  Charge ProductRules depuis products/{id}/config.json
  Méthodes : get_rules(product_id) · validate_rules(rules)
  Validation : CRITICAL vide → avertissement (non bloquant)

RuleEngine (core/rule_engine.py) :

  evaluate_tier(tier, signals, rules) → TierVerdict :
    criteria = rules.criteria_for_tier(tier)
    fail_reasons = []
    tier_scores = []

    for criterion in criteria :
      signal = find_signal(signals, criterion.observer_id)

      if signal is None :
        fail_reasons.append(f"{criterion.criterion_id}_SIGNAL_MISSING")
        tier_scores.append(0.0)
        continue

      if signal.error_msg :
        fail_reasons.append(f"{criterion.criterion_id}_OBSERVER_ERROR")
        tier_scores.append(0.0)
        continue

      if signal.confidence < 0.50 :
        # AI incertaine → REVIEW (géré en evaluate_final)
        tier_scores.append(signal.confidence)
        continue

      if not signal.passed and criterion.mandatory :
        fail_reasons.append(
            f"{criterion.criterion_id.upper()}_FAIL"
        )

      tier_scores.append(signal.confidence if signal.passed else signal.value / signal.threshold)

    tier_score = float(np.mean(tier_scores)) if tier_scores else 0.0
    passed = len(fail_reasons) == 0

    return TierVerdict(
        tier        = tier,
        passed      = passed,
        fail_reasons= tuple(fail_reasons),
        signals     = tuple(signals),
        tier_score  = round(tier_score, 3),
        completed   = True,
        latency_ms  = elapsed
    )

  evaluate_final(tier_verdicts) → tuple[str, SeverityLevel, TierLevel|None] :
    critical = tier_verdicts.get("CRITICAL")
    major    = tier_verdicts.get("MAJOR")
    minor    = tier_verdicts.get("MINOR")

    # Règles prioritaires (ordre strict)
    if critical and not critical.passed :
        return "NOK", SeverityLevel.REJECT, TierLevel.CRITICAL

    if major and not major.passed :
        return "NOK", SeverityLevel.DEFECT_1, TierLevel.MAJOR

    if minor and not minor.passed :
        # Vérifier si critères mandatory
        has_mandatory_fail = any(
            "MANDATORY" in r or not r.endswith("_OPTIONAL")
            for r in (minor.fail_reasons or [])
        )
        if has_mandatory_fail :
            return "NOK", SeverityLevel.DEFECT_2, TierLevel.MINOR
        else :
            return "REVIEW", SeverityLevel.REVIEW, TierLevel.MINOR

    # Vérifier incertitude AI (confidence basse)
    all_scores = [tv.tier_score for tv in tier_verdicts.values() if tv]
    if any(s < 0.50 for s in all_scores) :
        return "REVIEW", SeverityLevel.REVIEW, None

    # OK
    overall_score = np.mean(all_scores) if all_scores else 1.0
    severity = SeverityLevel.EXCELLENT if overall_score >= 0.90 else SeverityLevel.ACCEPTABLE
    return "OK", severity, None

  AUCUNE méthode learn(), train(), update_rules() — GR-08
```

### ✅ Gate S12-A
```bash
pytest tests/unit/test_rule_engine.py -v    # G-12
# CRITICAL fail → ("NOK", REJECT, CRITICAL)
# MAJOR fail    → ("NOK", DEFECT_1, MAJOR)
# MINOR fail mandatory → ("NOK", DEFECT_2, MINOR)
# MINOR fail non-mandatory → ("REVIEW", REVIEW, MINOR)
# All pass + scores > 0.90 → ("OK", EXCELLENT, None)
# All pass + scores normaux → ("OK", ACCEPTABLE, None)
# Déterminisme ×2 identique
# Vérifier : aucune méthode learn/train dans RuleEngine
```

---

# ════════════════════════════════════════════════════════
# PHASE 13 — TierOrchestrator
# ════════════════════════════════════════════════════════

## S13-A : Fail-Fast Hybride

```
📋 الهدف  : Orchestration 3 Tiers + Fail-Fast + Background
⏱ المدة  : 2 jours
📄 الـ Spec: §8
```

### 🤖 Prompt S13-A

```
Tu es ingénieur senior Python industriel — TS2I IVS v7.0.
Lire IVS_FINAL_SPEC_v7.md §8 (TierOrchestrator) complet.
Lire CLAUDE.md GR-10 (Fail-Fast + Full-Check background).

MISSION : pipeline/tier_orchestrator.py

TierOrchestrator :

  def run(self, aligned_frame, product_def,
          product_rules) → TierOrchestratorResult :

    t0 = time.monotonic()

    # ── CRITICAL (toujours main thread) ──────────────────
    critical_signals = self._run_tier_observers(
        TierLevel.CRITICAL, aligned_frame, product_def, product_rules
    )
    critical_verdict = self._rule_engine.evaluate_tier(
        TierLevel.CRITICAL, critical_signals, product_rules
    )

    if not critical_verdict.passed :
      # Fail-Fast : lancer background pour MAJOR + MINOR
      bg_future = self._executor.submit(
          self._background_complete,
          aligned_frame, product_def, product_rules,
          skip_critical=True
      )
      self._pending_backgrounds[aligned_frame.frame_id] = bg_future
      logger.info(
          f"Fail-Fast CRITICAL: {critical_verdict.fail_reasons} "
          f"→ background lancé pour rapport complet"
      )
      return TierOrchestratorResult(
          critical=critical_verdict,
          major=None,
          minor=None,
          fail_fast=True
      )

    # ── MAJOR ─────────────────────────────────────────────
    major_signals = self._run_tier_observers(
        TierLevel.MAJOR, aligned_frame, product_def, product_rules
    )
    major_verdict = self._rule_engine.evaluate_tier(
        TierLevel.MAJOR, major_signals, product_rules
    )

    if not major_verdict.passed :
      bg_future = self._executor.submit(
          self._background_complete,
          aligned_frame, product_def, product_rules,
          skip_critical=True, skip_major=True
      )
      self._pending_backgrounds[aligned_frame.frame_id] = bg_future
      return TierOrchestratorResult(
          critical=critical_verdict,
          major=major_verdict,
          minor=None,
          fail_fast=True
      )

    # ── MINOR ─────────────────────────────────────────────
    minor_signals = self._run_tier_observers(
        TierLevel.MINOR, aligned_frame, product_def, product_rules
    )
    minor_verdict = self._rule_engine.evaluate_tier(
        TierLevel.MINOR, minor_signals, product_rules
    )

    return TierOrchestratorResult(
        critical=critical_verdict,
        major=major_verdict,
        minor=minor_verdict,
        fail_fast=False
    )

  def _background_complete(self, frame, product_def, rules,
                            skip_critical=False, skip_major=False) :
    """Complète les tiers manquants pour le rapport."""
    results = {}
    if not skip_critical :
      signals = self._run_tier_observers(TierLevel.CRITICAL, ...)
      results["CRITICAL"] = self._rule_engine.evaluate_tier(...)
    if not skip_major :
      signals = self._run_tier_observers(TierLevel.MAJOR, ...)
      results["MAJOR"] = self._rule_engine.evaluate_tier(...)
    # MINOR toujours complété en background
    signals = self._run_tier_observers(TierLevel.MINOR, ...)
    results["MINOR"] = self._rule_engine.evaluate_tier(...)
    # Callback → DB save + UIBridge.background_complete
    self._on_background_complete(frame.frame_id, results)

  def _run_tier_observers(self, tier, frame,
                           product_def, rules) → list[ObserverSignal] :
    """Lance tous les observers du Tier en parallèle."""
    observers = self._observer_registry.get_for_tier(tier, product_def)
    criteria  = rules.criteria_for_tier(tier)
    with ThreadPoolExecutor(max_workers=4) as pool :
      futures = {
          pool.submit(obs.observe, frame.image, product_def, crit): obs
          for obs, crit in zip(observers, criteria)
          if crit.enabled
      }
    signals = []
    for future, obs in futures.items() :
      try :
        signals.append(future.result(timeout=5.0))
      except Exception as e :
        signals.append(ObserverSignal(
            observer_id=obs.observer_id, tier=tier,
            passed=False, confidence=0.0, value=0.0,
            threshold=0.0, details={},
            error_msg=str(e), latency_ms=5000.0
        ))   # GR-11 : jamais None
    return signals
```

### ✅ Gate S13-A
```bash
pytest tests/pipeline/test_tier_orchestrator.py -v    # G-13
# CRITICAL fail → fail_fast=True · background thread lancé
# Background complète MAJOR+MINOR
# Rapport final : 3 TierVerdicts présents
# Tout pass → fail_fast=False · minor non None
# GR-11 : aucun signal None retourné
# Déterminisme ×2
```

---

# ════════════════════════════════════════════════════════
# PHASES 14-24 — Résumé Prompts
# ════════════════════════════════════════════════════════

## S14-A : OCR + Barcode Observers

```
Lire §14 et §15.
Créer OcrObserver (tier=MINOR) + BarcodeObserver (tier=MINOR).
Chacun retourne ObserverSignal — jamais verdict.
OCR : 3 angles · pattern regex.
Barcode : pyzbar · 4 rotations.
Gate : → ObserverSignal · tier=MINOR · déterminisme.
```

## S15-A : LLM Explainer v7.0

```
Lire §16.
Prompt adapté Tiers : "Tier {fail_tier} a échoué : {fail_reasons}"
Output JSON : summary + cause + recommendation.
Seed=42 · temperature=0.1 · timeout=3s · fallback.
Gate : JSON structuré · fallback si timeout · display only.
```

## S16-A : Apprentissage per-Tier

```
Lire §11.
TierLearningBuffer × 3 (CRITICAL/MAJOR/MINOR).
Gates par tier (confidence 0.80/0.70/0.60).
3 Gates globales : stabilité + anti-regression + drift KS.
BackgroundTrainer per-Tier.
Rollback per-Tier.
Gate : buffer gate CRITICAL strict · rollback MAJOR seul.
```

## S17-A : ROI Editor

```
Lire §12.2.
Zones ROI/OCR/Caliper/Color drag-and-drop.
Coordonnées relatives [0,1].
FORBIDDEN pendant RUNNING.
```

## S18-A : Web API v7.0

```
15 endpoints FastAPI.
/api/v1/tier_verdicts → nouveau endpoint v7.0.
WebSocket émet tier_verdicts dans message.
JWT auth.
```

## S19-A : SPC + PDF v7.0

```
Cp/Cpk calculés sur tier_scores (3 scores par inspection).
PDF inclut distribution par Tier (CRITICAL/MAJOR/MINOR fails).
Graphiques par Tier.
```

## S20-A : Interface Principale v7.0

```
Lire §12 UI.
ResultBand affiche fail_tier + fail_reasons (PAS fused_score).
TierVerdictBadge : CRITICAL ✅/❌ · MAJOR ✅/❌ · MINOR ✅/❌.
ZoomableGridView §36 inchangé.
SystemStatusBar + NOKCounterBadge.
```

## S21-A : Wizard + TierPriorityWidget

```
Lire §12.2 et §12.3.
Tableau gauche : critères + ComboBox Tier + seuil.
Preview droite : résumé par Tier temps réel.
Validation : CRITICAL vide → avertissement.
Export → ProductRules → config.json.
FORBIDDEN si RUNNING.
```

## S22-A à S22-E : Multi-Logo + Canvas + Auto-Switch

```
Identique v6.1 (§35, §36, §37).
Gates G-22 → G-25.
```

## S23-A à S23-D : Robustesse Industrielle

```
Identique v6.2 (§40, §41, §42, §43).
Gates G-26 → G-29.
```

## S24-A : GPIO basique

```
OK → GPIO lampe VERTE ON.
NOK → GPIO lampe ROUGE ON.
REVIEW → rien.
Lecture verdict depuis UIBridge (GR-03).
gpio_stub.py pour PC.
```

## S24-B : GPIO Dashboard

```
Affichage tous pins RPi5.
Config : pin → fonction.
Test manuel ON/OFF.
Monitoring 100ms.
FORBIDDEN pendant RUNNING.
```

---

## Résumé Sessions v7.0

| Session | Phase | Durée | Gate |
|---------|-------|-------|------|
| S00-A | P00 Bootstrap | 1j | G-00 |
| S01-A | P01 Modèles | 1.5j | G-01 |
| S02-A | P02 Caméra | 1j | G-02 |
| S03-A | P03 Pipeline | 2j | G-03 |
| S04-A | P04 Calibration | 2j | G-04 |
| S05-A | P05 Dataset | 1.5j | G-05 |
| S06-A | P06 SiftObserver | 2j | G-06 |
| S07-A | P07 ModelBuilder | 1.5j | G-07 |
| S08-A | P08 YoloObserver | 2j | G-08 |
| S09-A | P09 ColorObserver | 1.5j | G-09 |
| S10-A | P10 SurfaceObserver | 2j | G-10 |
| S11-A | P11 CaliperObserver | 1.5j | G-11 |
| S12-A | P12 RuleEngine | 2j | G-12 |
| S13-A | P13 TierOrchestrator | 2j | G-13 |
| S14-A | P14 OCR+Barcode | 1.5j | G-14 |
| S15-A | P15 LLM v7.0 | 1j | G-15 |
| S16-A | P16 Learning | 3j | G-16 |
| S17-A | P17 ROI Editor | 1.5j | G-17 |
| S18-A | P18 Web API | 2j | G-18 |
| S19-A | P19 SPC+PDF | 2j | G-19 |
| S20-A | P20 Interface | 3j | G-20 |
| S21-A | P21 Wizard+Tier | 3j | G-21 |
| S22-A→E | P22 Multi-Logo | 9j | G-22→25 |
| S23-A→D | P23 Robustesse | 6j | G-26→29 |
| S24-A→B | P24 GPIO | 4j | — |

**Total : 45 sessions · 29 Gates · ~56 jours**

---

*TS2I IVS v7.0 — Sessions Complètes*
*AI observe · Rule Engine décide · 3 Tiers · 5 Observers*
