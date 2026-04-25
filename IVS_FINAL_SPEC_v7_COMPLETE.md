# IVS_FINAL_SPEC_v7.md
# TS2I Industrial Vision System — Specification v7.0
# Rule-Governed Hierarchical Inspection System
#
# Versions :
#   v6.0 → Système de base + Ensemble AI
#   v6.1 → Multi-Logo + ZoomableGrid + Auto-Switch
#   v6.2 → Watchdog + NOK Watcher + Luminosité + System Monitor
#   v7.0 → Architecture Rule-Governed Hierarchical (rupture philosophique)
#
# Décisions architecturales v7.0 :
#   Q1 : 3 Tiers (CRITICAL / MAJOR / MINOR)
#   Q2 : Hybride Fail-Fast + Full-Check Background
#   Q3 : AI = Observers purs + Mini Ensemble dans MINOR
#   Q4 : Verdict Tier-based + Scores internes pour analytics
#   Q5 : Apprentissage per-Tier + 3 Gates globales
#   Q6 : 5 Models (YOLO + SIFT + Color + Texture + IsoForest)
#   Q7 : UI Tableau + Preview résumé

---

## §1 — Philosophie v7.0

### §1.1 Rupture avec v6.x

Dans v6.x, tous les modèles AI participaient au décision via un EnsembleEngine global.
Cette architecture produisait une "décision floue" difficile à expliquer et à auditer.

Dans v7.0, la philosophie est radicalement différente :

```
v6.x : AI models → Ensemble → fused_score → Decision
                    (tous décident ensemble)

v7.0 : AI Observers → Signals → Rule Engine → Verdict
        (AI observe · Rule Engine décide)
```

### §1.2 Séparation fondamentale

```
OBSERVER (qui observe) :
  Rôle    : extraire un signal précis depuis l'image
  Nature  : algorithmique ou AI model
  Output  : signal structuré avec confidence
  Décide  : JAMAIS

RULE ENGINE (qui décide) :
  Rôle    : lire les signals et appliquer les règles produit
  Nature  : logique déterministe pure
  Input   : signals des observers
  Décide  : TOUJOURS
  Apprend : JAMAIS
```

### §1.3 Hiérarchie à 3 Tiers

```
TIER CRITICAL :
  Défauts bloquants → NOK immédiat si fail
  Exemples : logo absent, produit déchiré

TIER MAJOR :
  Défauts importants → NOK retouchable si fail
  Exemples : couleur incorrecte, position décalée

TIER MINOR :
  Défauts cosmétiques → REVIEW si fail
  Exemples : anomalie texture légère
```

### §1.4 Fail-Fast Hybride

```
Scénario CRITICAL fail :
  Thread principal  → Verdict NOK immédiat → GPIO rouge ON
  Background thread → continue MAJOR + MINOR → rapport complet

Scénario MAJOR fail :
  Thread principal  → verdict NOK après MAJOR
  Background thread → continue MINOR → rapport complet

Scénario tous PASS :
  Pipeline complet  → Verdict OK → GPIO vert ON
```

---

## §2 — Golden Rules v7.0

### GR-01 — Déterminisme absolu

```
seed=42 dans TOUS les composants stochastiques.
Même frame + même modèle → même signal → même verdict.
Reproductible à 100%.
```

### GR-02 — Rule Engine est le seul décideur

```
Aucun AI Observer ne produit de verdict.
Seul RuleEngine produit TierVerdict et FinalVerdict.
INTERDIT : tout observer qui retourne "OK" ou "NOK" directement.
```

### GR-03 — UI via SystemController uniquement

```
UI → SystemController → Pipeline
INTERDIT : UI accède directement au pipeline ou à la DB.
```

### GR-04 — Séparation Observer / Rule Engine

```
AI Observers retournent uniquement des ObserverSignal.
Rule Engine lit les ObserverSignal et applique les règles.
INTERDIT : logique de décision dans un Observer.
```

### GR-05 — Thread UI séparé

```
Toutes les opérations UI dans le thread Qt principal.
INTERDIT : appel Qt depuis un thread background.
Utiliser pyqtSignal pour communication cross-thread.
```

### GR-06 — Config immuable pendant inspection

```
Config chargée une fois à l'init.
INTERDIT : relire config.yaml dans la boucle d'inspection.
```

### GR-07 — FinalResult immuable

```
FinalResult est @dataclass(frozen=True).
INTERDIT : modifier FinalResult après création.
```

### GR-08 — Rule Engine n'apprend jamais

```
RuleEngine.rules sont définies par l'utilisateur.
INTERDIT : modifier les règles du Rule Engine automatiquement.
Seuls les AI Observers s'entraînent.
```

### GR-09 — Background Trainer hors pipeline

```
BackgroundTrainer tourne dans un thread daemon séparé.
INTERDIT : entraînement dans le thread pipeline.
```

### GR-10 — Fail-Fast Background complet

```
Si CRITICAL fail → Verdict NOK émis IMMÉDIATEMENT.
Background thread lance quand même MAJOR + MINOR.
Rapport final contient TOUJOURS tous les tiers inspectés.
```

### GR-11 — No Graceful Skip

```
Chaque Observer DOIT retourner un ObserverSignal.
INTERDIT : retourner None ou lever exception silencieuse.
Si observer échoue → ObserverSignal avec confidence=0 + error_msg.
```

### GR-12 — Tier Rules définies par utilisateur

```
L'utilisateur définit lors de la création produit :
  - Quel critère est dans quel Tier
  - Le seuil de chaque critère
Rule Engine applique ces règles à la lettre.
INTERDIT : modifier les règles sans action utilisateur.
```

---

## §3 — Architecture Générale v7.0

```
┌──────────────────────────────────────────────────────────────┐
│  TS2I IVS v7.0 — Architecture                               │
│                                                              │
│  COUCHE UI (PyQt6)                                           │
│    MainWindow → InspectionScreen → ZoomableGridView         │
│    TierPriorityWidget (Tableau + Preview)                    │
│    SystemStatusBar · NOKCounterBadge · LuminosityIndicator   │
│                                                              │
│  COUCHE CONTRÔLE                                             │
│    SystemController (FSM 9 états)                           │
│    UIBridge (signals Qt)                                     │
│    WatchdogManager · ConsecutiveNOKWatcher                  │
│                                                              │
│  COUCHE PIPELINE                                             │
│    S1 Acquisition → S2 Pre-process → S3 Alignment           │
│    S4 TierOrchestrator (CRITICAL / MAJOR / MINOR)           │
│    S5 RuleEngine → S8 Output + LLM + Learning               │
│                                                              │
│  COUCHE OBSERVERS (AI)                                       │
│    YoloObserver · SiftObserver (→ CRITICAL)                 │
│    ColorObserver                (→ MAJOR)                   │
│    SurfaceObserver              (→ MINOR, Mini Ensemble)     │
│                                                              │
│  COUCHE RÈGLES                                               │
│    RuleEngine · TierManager · ProductRules                  │
│                                                              │
│  COUCHE APPRENTISSAGE                                        │
│    TierLearningBuffer (×3) · BackgroundTrainer (×3)         │
│    GlobalGates · ModelVersionManager                         │
│                                                              │
│  COUCHE DONNÉES                                              │
│    SQLite WAL · JSONL Trace · ONNX Models                   │
└──────────────────────────────────────────────────────────────┘
```

---

## §4 — FSM — 9 États (inchangé)

```
IDLE_NO_PRODUCT → IMAGE_CAPTURE → CALIBRATING → TRAINING
    ↑                                               ↓
SHUTTING_DOWN ← ERROR ← RUNNING ← IDLE_READY ←────┘
                              ↕
                           REVIEW
```

| État | Description | Transitions autorisées |
|------|-------------|----------------------|
| IDLE_NO_PRODUCT | Aucun produit actif | → IMAGE_CAPTURE |
| IMAGE_CAPTURE | Capture images référence | → CALIBRATING |
| CALIBRATING | Calibration automatique 7 étapes | → TRAINING, → ERROR |
| TRAINING | Entraînement AI per-Tier | → IDLE_READY, → ERROR |
| IDLE_READY | Prêt à inspecter | → RUNNING, → CALIBRATING |
| RUNNING | Inspection en cours | → REVIEW, → IDLE_READY, → ERROR |
| REVIEW | Attente validation opérateur | → RUNNING, → IDLE_READY |
| ERROR | Erreur système | → IDLE_READY (après reset) |
| SHUTTING_DOWN | Arrêt propre | terminal |

---

## §5 — Modèle de Données v7.0

### §5.1 ObserverSignal

```python
@dataclass(frozen=True)
class ObserverSignal:
    """
    Output unique de tout AI Observer.
    Jamais un verdict — uniquement une observation.
    """
    observer_id    : str          # "yolo_v8x" | "sift" | "color_de" | "surface"
    tier           : TierLevel    # CRITICAL | MAJOR | MINOR
    passed         : bool         # signal principal : critère respecté ?
    confidence     : float        # confiance [0.0, 1.0]
    value          : float        # valeur mesurée (conf, score, delta_e...)
    threshold      : float        # seuil configuré
    details        : dict         # données supplémentaires (bbox, delta_e, etc.)
    error_msg      : str | None   # GR-11 : jamais None silencieux
    latency_ms     : float        # temps d'exécution
```

### §5.2 TierVerdict

```python
@dataclass(frozen=True)
class TierVerdict:
    """
    Verdict d'un Tier produit par RuleEngine.
    """
    tier           : TierLevel
    passed         : bool
    fail_reasons   : tuple[str, ...]   # ex: ("LOGO_LION_ABSENT",)
    signals        : tuple[ObserverSignal, ...]
    tier_score     : float             # score interne [0.0, 1.0] pour analytics
    completed      : bool              # False si background (Fail-Fast)
    latency_ms     : float
```

### §5.3 FinalResult v7.0

```python
@dataclass(frozen=True)
class FinalResult:
    """
    Résultat complet d'une inspection v7.0.
    Immuable après création — GR-07.
    """
    # Identité
    frame_id       : str
    product_id     : str
    model_versions : dict[str, str]    # {"yolo": "v3", "color": "v2", ...}

    # Verdict principal (Tier-based)
    verdict        : str               # "OK" | "NOK" | "REVIEW"
    severity       : SeverityLevel     # dérivée du tier qui a échoué
    fail_tier      : TierLevel | None  # tier qui a causé NOK
    fail_reasons   : tuple[str, ...]   # raisons exactes

    # Verdicts par Tier
    tier_verdicts  : dict[str, TierVerdict]   # {"CRITICAL": ..., "MAJOR": ..., "MINOR": ...}

    # Scores internes (pour analytics / SPC uniquement)
    tier_scores    : dict[str, float]  # {"CRITICAL": 0.94, "MAJOR": 0.22, "MINOR": 0.91}

    # Explication LLM
    llm_explanation: LLMExplanation | None

    # Métadonnées
    pipeline_ms    : float
    background_complete : bool         # True si Full-Check background terminé
    luminosity_result   : LuminosityResult
    timestamp      : float
```

### §5.4 ProductRules

```python
@dataclass(frozen=True)
class CriterionRule:
    """
    Règle d'un critère défini par l'utilisateur.
    """
    criterion_id   : str           # "logo_presence" | "color_logo" | ...
    label          : str           # "Présence Logo Lion"
    tier           : TierLevel     # CRITICAL | MAJOR | MINOR
    observer_id    : str           # quel observer évalue ce critère
    threshold      : float         # seuil numérique
    enabled        : bool
    mandatory      : bool          # si False et tier=MINOR → REVIEW au lieu de NOK

@dataclass(frozen=True)
class ProductRules:
    """
    Ensemble des règles définies par l'utilisateur pour un produit.
    Chargé à l'init · jamais modifié pendant RUNNING (GR-12).
    """
    product_id     : str
    criteria       : tuple[CriterionRule, ...]

    @property
    def critical_criteria(self) -> tuple[CriterionRule, ...]:
        return tuple(c for c in self.criteria if c.tier == TierLevel.CRITICAL)

    @property
    def major_criteria(self) -> tuple[CriterionRule, ...]:
        return tuple(c for c in self.criteria if c.tier == TierLevel.MAJOR)

    @property
    def minor_criteria(self) -> tuple[CriterionRule, ...]:
        return tuple(c for c in self.criteria if c.tier == TierLevel.MINOR)
```

---

## §6 — Les 5 AI Observers

### §6.1 ABC — AIObserver

```python
class AIObserver(ABC):
    """
    Contrat strict pour tous les observers v7.0.
    Un observer observe — il ne décide pas.
    GR-04 : aucune logique de verdict ici.
    """

    @property
    @abstractmethod
    def observer_id(self) -> str: ...

    @property
    @abstractmethod
    def tier(self) -> TierLevel: ...

    @abstractmethod
    def observe(self,
                frame: np.ndarray,
                product_def: ProductDefinition,
                rule: CriterionRule
                ) -> ObserverSignal: ...
```

### §6.2 YoloObserver (CRITICAL)

```
Tier    : CRITICAL
Modèle  : YOLOv8x ONNX (hailo HEF si AI HAT+ présent)
Signal  : {logo_found: bool, bbox: list, conf: float}
Seuil   : rule.threshold = confidence minimale (default 0.70)

Algorithme :
  1. Préprocessing : resize 640×640 · normalisation
  2. Inférence ONNX (ou Hailo HEF)
  3. NMS : conf ≥ rule.threshold · IoU = 0.45
  4. Pour chaque LogoDefinition :
     → chercher détection dans zone attendue (±tolerance)
     → ObserverSignal.passed = détection trouvée
     → ObserverSignal.value = max confidence détection
     → ObserverSignal.details = {bbox, class_name}
  5. Si aucune détection → passed=False · confidence=0.0

Seed : seed=42 dans onnxruntime.SessionOptions
```

### §6.3 SiftObserver (CRITICAL)

```
Tier    : CRITICAL
Algo    : SIFT 5000 keypoints + BFMatcher ratio test 0.75
Signal  : {match_score: float, position_delta_mm: float}
Seuil   : rule.threshold = match_score minimum (default 0.70)

Algorithme :
  1. Extraire keypoints frame corrigée
  2. BFMatcher.knnMatch vs template calibré
  3. Lowe ratio test : ratio < 0.75
  4. RANSAC homography si ≥ 10 good matches
  5. Position delta en mm via pixel_per_mm
  6. passed = match_score ≥ threshold AND delta ≤ tolerance_mm

Note : SIFT est deterministe (seed non requis)
```

### §6.4 ColorObserver (MAJOR)

```
Tier    : MAJOR
Algo    : K-means k=5 CIE LAB · ΔE2000 · illuminant D65
Signal  : {delta_e: float, color_ok: bool}
Seuil   : rule.threshold = delta_e maximum (default 8.0)

Algorithme :
  1. Extraire crop zone logo
  2. Convertir BGR → CIE LAB
  3. K-means k=5 sur pixels LAB (seed=42)
  4. Cluster dominant → couleur mesurée
  5. ΔE2000 vs couleur référence calibrée
  6. passed = delta_e ≤ rule.threshold
  7. ObserverSignal.value = delta_e mesuré
```

### §6.5 SurfaceObserver (MINOR) — Mini Ensemble

```
Tier    : MINOR
Modèles : Texture (GLCM+LBP+FFT) + IsolationForest
Signal  : {anomaly_score: float, anomaly_detected: bool}
Seuil   : rule.threshold = anomaly_score max (default 0.30)

Architecture Mini Ensemble :
  texture_score   = TextureAnalyzer.score(frame) → [0,1]
  iso_score       = IsoForestModel.score(features) → [0,1]
  anomaly_score   = 0.55 × texture_score + 0.45 × iso_score
  passed          = anomaly_score ≤ rule.threshold

Note : c'est le SEUL endroit autorisé pour fusion de scores.
       La fusion reste INTERNE à l'observer.
       Le Rule Engine voit uniquement ObserverSignal final.

TextureAnalyzer :
  GLCM  : distances=[1,2,4] · angles=[0,45,90,135] · poids=0.40
  LBP   : P=24 · R=3 · method=uniform · poids=0.35
  FFT   : corrcoef vs spectre référence · poids=0.25

IsolationForest :
  n_estimators=1000 · bootstrap=True · seed=42
  Export ONNX via skl2onnx
```

---

## §7 — Rule Engine

### §7.1 Contract RuleEngine

```python
class RuleEngine:
    """
    Décideur unique du système v7.0.
    Lit les ObserverSignals · applique les ProductRules.
    Ne s'entraîne JAMAIS (GR-08).
    """

    def evaluate_tier(self,
                      tier: TierLevel,
                      signals: list[ObserverSignal],
                      rules: ProductRules
                      ) -> TierVerdict:
        """
        Évalue un Tier complet.
        Retourne TierVerdict avec PASS/FAIL et raisons.
        """

    def evaluate_final(self,
                       tier_verdicts: dict[str, TierVerdict]
                       ) -> tuple[str, SeverityLevel, TierLevel | None]:
        """
        Produit le verdict final depuis les 3 TierVerdicts.

        Logique :
        if CRITICAL.passed == False:
            verdict = "NOK"
            severity = SeverityLevel.REJECT
            fail_tier = CRITICAL

        elif MAJOR.passed == False:
            verdict = "NOK"
            severity = SeverityLevel.DEFECT_1
            fail_tier = MAJOR

        elif MINOR.passed == False:
            if all mandatory minor passed:
                verdict = "REVIEW"
                severity = SeverityLevel.REVIEW
            else:
                verdict = "NOK"
                severity = SeverityLevel.DEFECT_2
            fail_tier = MINOR

        elif MINOR.confidence < confidence_threshold:
            verdict = "REVIEW"
            severity = SeverityLevel.REVIEW
            fail_tier = None

        else:
            verdict = "OK"
            fail_tier = None
            severity = EXCELLENT if all scores > 0.90 else ACCEPTABLE
        """
```

### §7.2 Mapping Tier → Severity

| Tier qui échoue | Severity | Action |
|----------------|----------|--------|
| CRITICAL fail | REJECT | NOK immédiat · pas de retouche |
| MAJOR fail | DEFECT_1 | NOK · retouche possible |
| MINOR fail mandatory | DEFECT_2 | NOK · inspection manuelle |
| MINOR fail non-mandatory | REVIEW | Opérateur décide |
| MINOR incertain | REVIEW | Opérateur décide |
| Tout PASS + scores > 0.90 | EXCELLENT | OK |
| Tout PASS + scores normaux | ACCEPTABLE | OK |

### §7.3 Règles tier_evaluate

```
Pour chaque CriterionRule dans le Tier :
  1. Trouver ObserverSignal correspondant (par observer_id)
  2. Si signal.error_msg → FAIL avec reason="OBSERVER_ERROR"
  3. Si signal.confidence < 0.50 → REVIEW (incertitude AI)
  4. Si signal.passed == False ET rule.mandatory:
     → ajouter fail_reason
  5. Si signal.passed == False ET NOT rule.mandatory:
     → ajouter warn_reason (pas de fail)

TierVerdict.passed = len(fail_reasons) == 0
```

---

## §8 — TierOrchestrator (S4 v7.0)

### §8.1 Architecture Fail-Fast Hybride

```python
class TierOrchestrator:
    """
    Orchestre les 3 Tiers selon la logique Fail-Fast Hybride.
    Remplace S4DetectionOrchestrator de v6.x.
    GR-10 : Fail-Fast pour verdict + Full-Check en background.
    """

    def run(self, aligned_frame, product_def) -> TierOrchestratorResult:

        # ── CRITICAL (toujours en main thread) ───────────────
        critical_result = self._run_critical(aligned_frame, product_def)

        if not critical_result.passed:
            # Fail-Fast : verdict NOK immédiat
            # Background : continuer MAJOR + MINOR pour rapport complet
            self._launch_background(aligned_frame, product_def,
                                    skip_critical=True)
            return TierOrchestratorResult(
                critical=critical_result,
                major=None,       # pending background
                minor=None,       # pending background
                fail_fast=True
            )

        # ── MAJOR (main thread si CRITICAL passé) ────────────
        major_result = self._run_major(aligned_frame, product_def)

        if not major_result.passed:
            self._launch_background(aligned_frame, product_def,
                                    skip_critical=True, skip_major=True)
            return TierOrchestratorResult(
                critical=critical_result,
                major=major_result,
                minor=None,
                fail_fast=True
            )

        # ── MINOR (main thread si tout passé) ────────────────
        minor_result = self._run_minor(aligned_frame, product_def)

        return TierOrchestratorResult(
            critical=critical_result,
            major=major_result,
            minor=minor_result,
            fail_fast=False
        )
```

### §8.2 Background Thread

```
_launch_background() → threading.Thread(daemon=True)

Complète les Tiers manquants.
Résultats sauvegardés dans DB via callback.
Rapport PDF contient TOUJOURS tous les Tiers.
Signal UI émis quand background complet.
Si background thread dépasse 30s → timeout + log WARNING.
```

---

## §9 — Pipeline v7.0

### §9.1 Stages

| Stage | Nom | Description | Modifié v7.0 |
|-------|-----|-------------|--------------|
| S1 | Acquisition | Capture frame + validation | Non |
| S2 | PreProcess | CLAHE + LuminosityChecker | Non |
| S3 | Alignment | SIFT alignment + correction | Non |
| S4 | TierOrchestrator | 3 Tiers + Fail-Fast Hybride | ✅ OUI |
| S5 | RuleEngine | Verdict final | ✅ OUI (remplace DecisionEngine) |
| S8 | Output | LLM + Learning + GPIO + WS | Partiel |

### §9.2 Budget temporel v7.0

```
Scénario CRITICAL fail (Fail-Fast) :
  S1+S2+S3 : ~1500ms
  S4 CRITICAL : ~400ms (YOLO sur Hailo + SIFT)
  S5 RuleEngine : ~10ms
  S8 minimal : ~100ms
  TOTAL main thread : ~2010ms ← 5× plus rapide que v6.x

Scénario tout OK (Full pipeline) :
  S1+S2+S3 : ~1500ms
  S4 CRITICAL : ~400ms
  S4 MAJOR    : ~300ms (Color)
  S4 MINOR    : ~500ms (Texture + IsoForest)
  S5 RuleEngine : ~15ms
  S8 + LLM : ~2000ms
  TOTAL : ~4715ms
```

---

## §10 — Calibration v7.0 (7 étapes)

```
Étape 1 : pixel_per_mm
  → calcul depuis dimensions réelles produit

Étape 2 : brightness_reference
  → mean + std + min_ok + max_ok (pour LuminosityChecker §42)

Étape 3 : noise_reference
  → floor de bruit pour filtrage

Étape 4 : SIFT alignment template
  → 5000 keypoints · sauvegardé en .pkl

Étape 5 : Logo templates (par LogoDefinition)
  → 1 template SIFT par logo → logo_{idx}_template.pkl
  → Utilisé par SiftObserver

Étape 6 : Color reference (par LogoDefinition)
  → K-means k=5 LAB sur zone logo
  → color_reference.json avec {logo_id: {lab_clusters, ref_color}}
  → Utilisé par ColorObserver

Étape 7 : Surface texture reference
  → GLCM + LBP + FFT sur zone produit complète
  → texture_reference.npz + isolation_forest_init.onnx
  → Utilisé par SurfaceObserver
```

---

## §11 — Apprentissage Autonome v7.0

### §11.1 Architecture per-Tier

```
TierLearningBuffer × 3 :
  CRITICAL_buffer  → samples YOLO + SIFT
  MAJOR_buffer     → samples Color
  MINOR_buffer     → samples Texture + IsoForest

Déclenchement retrain :
  Si buffer ≥ trigger_count (default=50) → BackgroundTrainer

BackgroundTrainer × 3 (un par Tier) :
  Tourne en thread daemon
  Entraîne les observers du Tier concerné
  Valide via ModelValidator (anti-regression)
  Si validation OK → swap models
  Si validation FAIL → discard + log WARNING
```

### §11.2 Portes par Tier

```
CRITICAL buffer gate :
  signal.confidence ≥ 0.80 (strict car tier critique)
  signal.error_msg is None

MAJOR buffer gate :
  signal.confidence ≥ 0.70

MINOR buffer gate :
  signal.confidence ≥ 0.60
```

### §11.3 3 Gates Globales (inchangées)

```
Gate ① Stabilité :
  10 verdicts identiques consécutifs avant d'accepter un sample

Gate ② Anti-régression :
  golden_pass_rate candidat ≥ 0.95
  tier_score candidat ≥ tier_score actif

Gate ③ Drift :
  KS-test statistic < 0.15 par Tier
  Si drift détecté → pause learning ce Tier + alerte
```

### §11.4 Rollback per-Tier

```
ModelVersionManager maintient :
  active_models   : dict[str, str]    # {"yolo": "v3", "color": "v2", ...}
  previous_models : dict[str, str]    # rollback par observer

rollback_tier(tier: TierLevel) → None :
  Identifie les observers du Tier
  Pour chaque observer → swap avec version précédente
  Log INFO "Rollback Tier {tier} : {old} → {prev}"
  Durée rollback : < 1 seconde (symlinks)
```

---

## §12 — UI TierPriorityWidget

### §12.1 Intégration Wizard

```
Wizard création produit — Étape N (après Canvas logos) :
  TierPriorityWidget
  → Tableau gauche + Preview résumé droite
```

### §12.2 Tableau (gauche)

```
QTableWidget avec colonnes :
  Critère | Activé | Tier | Seuil | Mandatory

Lignes pré-remplies :
  Présence Logo 1   [✅] [CRITICAL ▼] [—]      [✅]
  Présence Logo 2   [✅] [CRITICAL ▼] [—]      [✅]
  Couleur Logo 1    [✅] [MAJOR    ▼] [ΔE ≤ 8] [✅]
  Couleur Logo 2    [✅] [MAJOR    ▼] [ΔE ≤ 8] [✅]
  Position Logo 1   [✅] [MAJOR    ▼] [±5mm]   [✅]
  Position Logo 2   [✅] [MAJOR    ▼] [±5mm]   [✅]
  Caliper largeur   [❌] [MAJOR    ▼] [±2mm]   [✅]
  Caliper hauteur   [❌] [MAJOR    ▼] [±2mm]   [✅]
  Texture surface   [✅] [MINOR    ▼] [auto]   [❌]
  OCR numéro        [❌] [MINOR    ▼] [—]      [❌]
  Barcode           [❌] [MINOR    ▼] [—]      [❌]

QComboBox Tier : CRITICAL | MAJOR | MINOR
```

### §12.3 Preview résumé (droite)

```
Mise à jour temps réel quand utilisateur modifie le tableau.

🔴 CRITICAL (2 critères) — NOK immédiat si fail
   • Présence Logo Lion
   • Présence Logo 208

🟠 MAJOR (4 critères) — NOK retouchable si fail
   • Couleur Logo Lion
   • Couleur Logo 208
   • Position Logo Lion
   • Position Logo 208

🟡 MINOR (1 critère) — REVIEW si fail
   • Texture surface

Avertissement si CRITICAL vide :
  ⚠ Aucun critère CRITICAL défini.
  Le système n'aura pas de vérification bloquante.
```

### §12.4 Règles UI TierPriorityWidget

```
- Modifier Tier pendant RUNNING est FORBIDDEN (GR-12)
- CRITICAL vide → avertissement (non bloquant)
- Seuil doit être numérique > 0 → validation inline
- Mandatory = True force le Tier à FAIL si critère échoué
- Mandatory = False → REVIEW si critère échoué dans MINOR
```

---

## §13 — Caliper v7.0

```
Tier        : MAJOR (si activé par utilisateur)
Observer    : CaliperObserver (nouveau observer dédié)
Signal      : {measured_mm: float, in_tolerance: bool, delta_mm: float}
Seuil       : rule.threshold = tolerance_mm (default ±2.0mm)

Algorithme (inchangé depuis v6.x) :
  10 lectures par mesure (configurable)
  Filtre 2-sigma sur les 10 valeurs
  Gaussien fit sub-pixel sur gradient profil
  Précision : ±0.02mm

CaliperObserver.observer_id = "caliper_{measurement_id}"
Plusieurs CaliperObserver possibles (un par mesure définie)
```

---

## §14 — OCR Observer

```
Tier        : MINOR (si activé par utilisateur)
Observer    : OcrObserver
Signal      : {text_found: str, matches_pattern: bool, confidence: float}
Seuil       : rule.threshold = confidence minimale (default 0.70)

Algorithme :
  3 angles (0°, +2°, -2°) → meilleure lecture retenue
  Pattern regex depuis CriterionRule.details["expected_pattern"]
  passed = text_found AND matches_pattern AND confidence ≥ threshold
```

---

## §15 — Barcode Observer

```
Tier        : MINOR (si activé par utilisateur)
Observer    : BarcodeObserver
Signal      : {code_found: str, matches_expected: bool, confidence: float}
Seuil       : rule.threshold = 1.0 (binaire : trouvé ou pas)

Algorithme :
  pyzbar : QR · Code128 · EAN13 · DataMatrix
  4 rotations (0°, 90°, 180°, 270°)
  passed = code_found == expected_code (depuis CriterionRule.details)
```

---

## §16 — LLM Explainer v7.0

```
Modèle  : Mistral 7B Q4_K_M · llama.cpp · local · timeout 3s
Seed    : 42 · température 0.1 · déterministe (GR-01)
Langue  : fr (configurable)

Prompt v7.0 adapté :
  "Produit {product_name}. Verdict {verdict}.
   Tier {fail_tier} a échoué : {fail_reasons}.
   Scores : CRITICAL={x} MAJOR={y} MINOR={z}.
   Explication en 3 phrases : cause probable, localisation défaut,
   recommandation opérateur."

Output JSON structuré :
  {summary, defect_detail, probable_cause, recommendation}

Display only — GR-04 : jamais utilisé dans la logique de décision.
Fallback texte automatique si timeout.
```

---

## §17 — GPIO v7.0 (implémentation future P24)

```
Logique GPIO v7.0 :

  FinalResult.verdict == "OK"  → GPIO lampe VERTE ON
  FinalResult.verdict == "NOK" → GPIO lampe ROUGE ON
  FinalResult.verdict == "REVIEW" → rien (opérateur décide)

GPIO Manager :
  Lit verdict depuis UIBridge signal (GR-03)
  Thread séparé — non-bloquant
  Relay module 5V → 24V pour lampes industrielles

Implémentation : Phase P24 après P23 (code complet)
```

---

## §18 — Monitoring v7.0

### §18.1 WatchdogManager (§40 — inchangé)

```
Timeout pipeline : 60s (configurable)
Max récupérations : 3
heartbeat() appelé depuis S8 après chaque FinalResult
```

### §18.2 ConsecutiveNOKWatcher (§41 — inchangé)

```
alert_threshold : 5 NOK consécutifs → WARNING
stop_threshold  : 10 NOK consécutifs → arrêt ligne
reset par opérateur obligatoire
```

### §18.3 LuminosityChecker (§42 — inchangé)

```
Vérifié dans S2 avant tout traitement
warning_percent  : 15%
critical_percent : 30%
```

### §18.4 SystemMonitor (§43 — inchangé)

```
CPU · RAM · Température · Disk · Uptime
Refresh 5s · thread daemon
Thermal throttling si temp > 75°C
```

---

## §19 — Nouveaux Fichiers v7.0

```
core/
  rule_engine.py           ← §7  — décideur unique
  tier_manager.py          ← §5  — ProductRules + TierLevel
  ai_observer.py           ← §6.1 — ABC AIObserver
  tier_result.py           ← §5  — ObserverSignal + TierVerdict

ai/
  yolo_observer.py         ← §6.2 — YOLO comme observer CRITICAL
  sift_observer.py         ← §6.3 — SIFT comme observer CRITICAL
  color_observer.py        ← §6.4 — Color ΔE comme observer MAJOR
  surface_observer.py      ← §6.5 — Texture+ISO Mini Ensemble MINOR
  caliper_observer.py      ← §13  — Caliper comme observer MAJOR
  ocr_observer.py          ← §14  — OCR comme observer MINOR
  barcode_observer.py      ← §15  — Barcode comme observer MINOR

pipeline/
  tier_orchestrator.py     ← §8  — coordination 3 Tiers Fail-Fast

learning/
  tier_learning_buffer.py  ← §11.1 — buffer per-Tier
  tier_background_trainer.py← §11.1 — retrain per-Tier

ui/
  tier_priority_widget.py  ← §12  — Tableau + Preview
```

### Fichiers supprimés de v6.x

```
ai/ensemble_engine.py      → supprimé (remplacé par TierOrchestrator)
ai/random_forest_model.py  → supprimé (Q6)
ai/svm_model.py            → supprimé (Q6)
core/decision_engine.py    → supprimé (remplacé par RuleEngine)
```

---

## §20 — Acceptance Gates v7.0 (29 Gates)

### Gates v7.0 (nouveaux ou modifiés)

```
G-01 : test_models_v7.py
  → ObserverSignal frozen · TierVerdict frozen · FinalResult frozen
  → FinalResult.tier_verdicts non vide
  → ProductRules validation

G-02 : test_rule_engine.py
  → CRITICAL fail → verdict NOK · severity REJECT
  → MAJOR fail → verdict NOK · severity DEFECT_1
  → MINOR fail mandatory → verdict NOK · severity DEFECT_2
  → MINOR fail non-mandatory → verdict REVIEW
  → All pass → verdict OK
  → Déterminisme : ×2 même résultat

G-03 : test_tier_orchestrator.py
  → CRITICAL fail → TierOrchestratorResult.fail_fast=True
  → Background thread lancé si Fail-Fast
  → Tout pass → fail_fast=False
  → Déterminisme garanti

G-04 : test_observers.py
  → YoloObserver retourne ObserverSignal · jamais verdict
  → SiftObserver retourne ObserverSignal · jamais verdict
  → ColorObserver retourne ObserverSignal · jamais verdict
  → SurfaceObserver retourne ObserverSignal · jamais verdict
  → Aucun observer ne retourne "OK" ou "NOK" directement

G-05 : test_tier_learning.py
  → Sample CRITICAL : confidence ≥ 0.80 gate
  → Sample MAJOR    : confidence ≥ 0.70 gate
  → Sample MINOR    : confidence ≥ 0.60 gate
  → 3 Gates globales : stabilité + anti-regression + drift
  → Rollback per-Tier < 1s

G-06 → G-29 : inchangés (voir v6.2 spec §46)
```

---

## §21 — Configuration v7.0

```yaml
# config.yaml v7.0

station_id: STATION-001
deployment_mode: DEV

camera:
  type: fake
  resolution: {width: 1920, height: 1080}
  fps: 5

pipeline:
  max_duration_ms: 10000
  background_timeout_ms: 30000   # timeout background Full-Check

tier_engine:
  critical_confidence_min: 0.80  # gate buffer CRITICAL
  major_confidence_min:    0.70  # gate buffer MAJOR
  minor_confidence_min:    0.60  # gate buffer MINOR
  review_confidence_threshold: 0.50  # en dessous → REVIEW

observers:
  yolo:
    model_path: data/yolo/yolov8x.onnx
    confidence_threshold: 0.45
    iou_threshold: 0.45
    device: cpu           # cpu | hailo
  sift:
    nfeatures: 5000
    ratio_test: 0.75
  color:
    illuminant: D65
    k_clusters: 5
  surface:
    texture_weight:     0.55
    isoforest_weight:   0.45
    isoforest_n:        1000
    seed:               42

learning:
  trigger_count:         50
  stability_window:      10
  drift_threshold:       0.15
  golden_pass_rate_min:  0.95
  operator_weight:       2.0

llm:
  enabled: true
  timeout_ms: 3000
  language: fr
  seed: 42
  temperature: 0.1

watchdog:
  enabled: true
  pipeline_timeout_s:  60
  max_recoveries:       3

nok_watcher:
  enabled: true
  alert_threshold:      5
  stop_threshold:      10

luminosity:
  enabled: true
  warning_percent:    15.0
  critical_percent:   30.0

system_monitor:
  enabled: true
  refresh_s:            5
  temp_warn:           75
  temp_crit:           85

scanner:
  enabled: false
  interval_ms:        500
  debounce_s:         3.0

ui:
  auto_zoom_on_nok: true
  zoom_nok_level:   4.0
  snapshot_dir: data/snapshots

web:
  enabled: false
  port: 8765
  auth_required: true
```

---

## §22 — Anti-Patterns v7.0

```python
# ❌ INTERDIT v7.0 — Observer qui retourne verdict
class BadObserver(AIObserver):
    def observe(self, frame, product_def, rule):
        if score > 0.70:
            return "OK"     # INTERDIT — GR-04

# ✅ CORRECT v7.0 — Observer qui retourne signal
class GoodObserver(AIObserver):
    def observe(self, frame, product_def, rule):
        return ObserverSignal(
            observer_id="yolo_v8x",
            tier=TierLevel.CRITICAL,
            passed=score >= rule.threshold,
            confidence=conf,
            value=score,
            threshold=rule.threshold,
            ...
        )

# ❌ INTERDIT v7.0 — Rule Engine qui s'entraîne
class BadRuleEngine:
    def learn(self, result):    # INTERDIT — GR-08
        self.rules.update(...)

# ❌ INTERDIT v7.0 — Mélanger observers de tiers différents
ensemble = YOLO_score * 0.5 + Color_score * 0.5  # INTERDIT

# ❌ INTERDIT v7.0 — Ensemble global
fused = weighted_average([yolo, sift, color, texture, iso])  # INTERDIT

# ✅ CORRECT v7.0 — Mini Ensemble dans MINOR uniquement
class SurfaceObserver(AIObserver):
    def observe(self, ...):
        texture_score = self._texture.score(frame)
        iso_score     = self._isoforest.score(features)
        anomaly = 0.55 * texture_score + 0.45 * iso_score  # autorisé ici
        return ObserverSignal(passed=anomaly <= rule.threshold, ...)
```

---

*TS2I IVS v7.0 — Specification Complète*
*Rule-Governed Hierarchical Inspection System*
*47 sections · 29 Gates · 5 Observers · 3 Tiers · 1 Rule Engine*
*Philosophie : AI observe · Rule Engine décide*

---

## §Fleet — Déploiement en Flotte (Fleet Deployment)

### §Fleet.1 — Principe

```
Unité SOURCE (calibrée + entraînée) :
  → export_package() → fichier .ivs

N Unités CIBLES (production) :
  → import_package(.ivs) via :
     ① HTTP API (réseau local)
     ② Clé USB (mount + copy)
  → ModelValidator (GR-13) → activation

Master Unit : DEFERRED — phase ultérieure
```

### §Fleet.2 — Structure Package .ivs

```
product_{id}_v{version}.ivs  (ZIP signé SHA256)
├── package.json              ← metadata + signature
│     {product_id, export_date, station_id,
│      ivs_version:"7.0", sha256:...}
├── config.json               ← ProductDefinition + ProductRules
├── calibration/
│   ├── alignment_template.pkl
│   ├── brightness_reference.json
│   ├── logo_{n}_template.pkl
│   ├── color_reference.json
│   └── texture_reference.npz
├── models/
│   ├── isoforest.onnx
│   └── yolo.onnx              (si disponible)
└── logos/
    └── logo_{n}.png
```

### §Fleet.3 — FleetManager Contract

```python
class FleetManager:

  export_package(product_id, output_path) → str :
    Copie calibration + models actifs + config
    Signe SHA256
    Crée .ivs (ZIP)
    Log INFO export

  import_package(ivs_file_path) → ImportResult :
    Dézippage → vérif signature SHA256
    Vérif version 7.0
    Copie vers products/
    GR-13 : ModelValidator.validate() obligatoire
    Si fail → rollback complet (supprimer produit copié)
    Si pass → produit disponible dans ProductRegistry

  import_via_usb(mount_point) → ImportResult :
    Chercher *.ivs dans mount_point
    Copier en local (tmp) avant traitement
    Appeler import_package()
    GR-13 : même validation

  Contrainte GR-13 :
    Import réseau ET USB jamais simultanés
    Validation OBLIGATOIRE avant toute activation
```

### §Fleet.4 — Import réseau

```
Endpoint : POST /api/v1/products/import
Auth     : JWT obligatoire
Body     : multipart/form-data : file (.ivs)
Response : {success, product_id, validation_report}

Import depuis unité cible :
  curl -X POST http://192.168.1.10:8765/api/v1/products/import \
       -H "Authorization: Bearer {token}" \
       -F "file=@tapis_p208.ivs"
```

### §Fleet.5 — Import USB

```
UsbMonitor (thread daemon · polling 2s) :
  Surveille /media/ (Linux) ou /Volumes/ (macOS)
  Détecte nouveau mount + fichier *.ivs
  Signal usb_ivs_found(path, mount_point)

Règle : 1 seul .ivs par clé USB
        → 2 fichiers → FleetImportError
Copie locale avant import (protection débranchement)
```

### §Fleet.6 — Master Unit (DEFERRED)

```
RÉSERVÉ — Phase ultérieure (IVS v8.0)

Ne pas implémenter dans v7.0.
Placeholder dans code avec commentaire :
  # RESERVED — Master Unit — IVS v8.0

Ce que ferait Master Unit :
  - Agrège résultats N unités terrain
  - Ré-entraîne sur données agrégées
  - Distribue nouveaux modèles via Fleet Export
  - Dashboard centralisé multi-unités

Trigger d'implémentation :
  Validation production v7.0 sur ≥ 3 unités
  + infrastructure réseau sécurisée définie
```

### §Fleet.7 — Acceptance Gates Fleet

```
G_FLEET-A : test_fleet_manager.py
  Export :
    → .ivs créé · package.json avec sha256 · calibration/ présent
  Import réseau :
    → ImportResult.validation.passed=True (modèles valides)
    → Signature invalide → FleetImportError
    → Version incompatible → FleetImportError
    → GR-13 : ModelValidator appelé AVANT activation
    → Rollback si validation fail
  Endpoints API :
    → POST /import → 200 + ImportResult
    → GET /{id}/export → download .ivs

G_FLEET-B : test_fleet_usb.py
  UsbMonitor :
    → Détecte mount avec .ivs simulé
    → Signal usb_ivs_found émis
  import_via_usb :
    → Même validation GR-13 que réseau
    → 2 fichiers .ivs → FleetImportError
    → Copie locale avant import
  Concurrent import :
    → Réseau en cours → USB bloqué (et vice-versa)

G_FLEET-C : vérification DEFERRED
  grep -r "MasterUnit" → vide (aucun code Master)
  → PASS ✅
```

### §Fleet.8 — Nouveaux fichiers Fleet

```
core/fleet_manager.py     ← export/import package .ivs
core/usb_monitor.py       ← détection USB thread daemon
ui/screens/fleet_screen.py← Fleet UI Tab
tests/unit/test_fleet_manager.py
tests/unit/test_fleet_usb.py
```

---

*TS2I IVS v7.0 — Spec Fleet Deployment*
*Export réseau + USB · Master Unit DEFERRED · GR-13*
