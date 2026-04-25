# CLAUDE.md — TS2I IVS v7.0
# Golden Rules · Anti-Patterns · Workflow
# Lu automatiquement par Claude Code à chaque session

---

## Philosophie v7.0

```
AI Observers → ObserverSignal  (qui observe)
Rule Engine  → Verdict         (qui décide)

JAMAIS mélanger les deux rôles.
```

---

## Golden Rules GR-01 → GR-12

```
GR-01 DÉTERMINISME     seed=42 partout · même frame = même verdict
GR-02 RULE ENGINE SEUL seul RuleEngine produit verdict · jamais un observer
GR-03 UI VIA CTRL      UI → SystemController → Pipeline (jamais direct)
GR-04 OBSERVER PUR     observe() retourne ObserverSignal UNIQUEMENT
GR-05 THREAD UI        opérations Qt dans thread principal · pyqtSignal cross-thread
GR-06 CONFIG IMMUABLE  config chargée 1 fois · jamais reluire en boucle
GR-07 RESULT IMMUTABLE FinalResult frozen · jamais modifié après création
GR-08 RULE NO LEARN    RuleEngine n'a PAS de méthode learn/train/update
GR-09 BG TRAINER       BackgroundTrainer dans thread daemon · pas dans pipeline
GR-10 FAIL-FAST HYBRID CRITICAL fail → verdict NOK immédiat + background Full-Check
GR-11 NO SKIP          Observer échoue → ObserverSignal(confidence=0, error_msg=...)
GR-12 RULES USER       ProductRules définies par utilisateur · modif FORBIDDEN RUNNING
```

---

## Anti-Patterns INTERDITS

### ❌ Observer qui retourne un verdict

```python
# INTERDIT — GR-04
class BadObserver(AIObserver):
    def observe(self, frame, product_def, rule):
        if score > 0.70:
            return "OK"                  # ← INTERDIT
        return {"verdict": "NOK"}       # ← INTERDIT
        return True                      # ← INTERDIT

# ✅ CORRECT — GR-04
class GoodObserver(AIObserver):
    def observe(self, frame, product_def, rule):
        return ObserverSignal(
            observer_id="my_observer",
            tier=TierLevel.CRITICAL,
            passed=score >= rule.threshold,  # bool uniquement
            confidence=conf,
            value=score,
            threshold=rule.threshold,
            details={"score": score},
            error_msg=None,
            latency_ms=elapsed
        )
```

### ❌ Ensemble global (INTERDIT en v7.0)

```python
# INTERDIT — philosophie v7.0
fused = 0.30*yolo + 0.30*texture + 0.20*color + 0.12*rf + 0.08*svm

# INTERDIT — ensemble cross-tier
ensemble_score = weighted_average([critical_score, major_score, minor_score])

# ✅ SEUL Mini Ensemble autorisé : dans SurfaceObserver uniquement
class SurfaceObserver(AIObserver):
    def observe(self, ...):
        anomaly = 0.55 * texture_anomaly + 0.45 * iso_anomaly  # ← autorisé ici uniquement
        return ObserverSignal(value=anomaly, ...)
```

### ❌ Rule Engine qui apprend

```python
# INTERDIT — GR-08
class BadRuleEngine:
    def learn(self, result): ...        # ← INTERDIT
    def update_thresholds(self): ...    # ← INTERDIT
    def train(self, samples): ...       # ← INTERDIT

# ✅ Rule Engine immuable
class GoodRuleEngine:
    def evaluate_tier(self, tier, signals, rules) -> TierVerdict: ...
    def evaluate_final(self, tier_verdicts) -> tuple: ...
    # Aucune autre méthode publique
```

### ❌ FakeCamera en PRODUCTION

```python
# INTERDIT — GR-01
if config.deployment_mode == "PRODUCTION":
    raise ConfigValidationError("FakeCamera FORBIDDEN in PRODUCTION")
```

### ❌ None retourné par un observer

```python
# INTERDIT — GR-11
def observe(self, ...):
    try:
        return compute_signal(frame)
    except Exception:
        return None    # ← INTERDIT

# ✅ CORRECT — GR-11
def observe(self, ...):
    try:
        return compute_signal(frame)
    except Exception as e:
        return ObserverSignal(
            ..., confidence=0.0, passed=False,
            error_msg=str(e)     # jamais None silencieux
        )
```

### ❌ UI accède directement au pipeline

```python
# INTERDIT — GR-03
class BadUI(QWidget):
    def on_click(self):
        self._pipeline.run(frame)    # ← INTERDIT
        self._db.query(...)          # ← INTERDIT

# ✅ CORRECT — GR-03
class GoodUI(QWidget):
    def on_click(self):
        self._system_controller.start_inspection()  # ← via controller
```

### ❌ Modifier ProductRules pendant RUNNING

```python
# INTERDIT — GR-12
if state == SystemState.RUNNING:
    product_rules.update_threshold(...)  # ← INTERDIT
```

### ❌ QLabel pour les grilles

```python
# INTERDIT — v7.0 (hérité v6.1)
self._grid3 = QLabel()              # ← INTERDIT
# ✅ CORRECT
self._grid3 = ZoomableGridView("Corrigé")
```

---

## Structure Observers v7.0

```
CRITICAL Tier :
  YoloObserver       → logo_found, bbox, conf
  SiftObserver       → match_score, position_delta_mm

MAJOR Tier :
  ColorObserver      → delta_e, color_ok
  CaliperObserver    → measured_mm, in_tolerance, delta_mm (si activé)

MINOR Tier :
  SurfaceObserver    → anomaly_score (Mini Ensemble interne)
  OcrObserver        → text_found, matches_pattern (si activé)
  BarcodeObserver    → code_found, matches_expected (si activé)
```

---

## Mapping Tier → Severity

```
CRITICAL fail → SeverityLevel.REJECT
MAJOR fail    → SeverityLevel.DEFECT_1
MINOR fail mandatory → SeverityLevel.DEFECT_2
MINOR fail non-mandatory → SeverityLevel.REVIEW (opérateur décide)
All pass + scores > 0.90 → SeverityLevel.EXCELLENT
All pass → SeverityLevel.ACCEPTABLE
```

---

## Mapping Tier → GPIO

```
FinalResult.verdict == "OK"     → GPIO lampe VERTE ON
FinalResult.verdict == "NOK"    → GPIO lampe ROUGE ON
FinalResult.verdict == "REVIEW" → rien (opérateur décide)
```

---

## Nouveaux fichiers v7.0

```python
# À créer (pas dans v6.x)
core/rule_engine.py           # décideur unique
core/tier_manager.py          # ProductRules + TierLevel
core/ai_observer.py           # ABC AIObserver
core/tier_result.py           # ObserverSignal + TierVerdict
ai/yolo_observer.py           # YOLO observer CRITICAL
ai/sift_observer.py           # SIFT observer CRITICAL
ai/color_observer.py          # Color ΔE observer MAJOR
ai/surface_observer.py        # Texture+ISO Mini Ensemble MINOR
ai/caliper_observer.py        # Caliper observer MAJOR
ai/ocr_observer.py            # OCR observer MINOR
ai/barcode_observer.py        # Barcode observer MINOR
pipeline/tier_orchestrator.py # Fail-Fast Hybride
learning/tier_learning_buffer.py  # buffer per-Tier
learning/tier_background_trainer.py  # retrain per-Tier
learning/global_gates.py      # 3 gates globales
ui/tier_priority_widget.py    # Tableau + Preview
```

---

## Fichiers supprimés vs v6.x

```python
# SUPPRIMÉS — ne pas recréer
ai/ensemble_engine.py          # remplacé par TierOrchestrator
ai/random_forest_model.py      # Q6 : supprimé
ai/svm_model.py                # Q6 : supprimé
core/decision_engine.py        # remplacé par RuleEngine
```

---

## Workflow Session

```
1. source .venv/bin/activate && claude
2. /session          → voir où on en est
3. Copier Prompt S0X-A depuis IVS_SESSIONS_v7.md
4. Coller dans Claude Code
5. Attendre complétion complète
6. /gate OU make test
7. git commit -m "S0X-A: description [§N] ✅"
8. Passer à la session suivante
```

---

## Slash Commands

```
/gate        → exécuter gate session courante
/spec §N     → consulter spec et appliquer
/check       → vérifier conformité fichier courant
/session     → démarrer session proprement
/determinism → générer test déterminisme
```

---

## Config clés v7.0

```yaml
deployment_mode: DEV        # → PRODUCTION avant usine
camera.type: fake           # → uvc / gige en production
tier_engine.critical_confidence_min: 0.80
tier_engine.major_confidence_min:    0.70
tier_engine.minor_confidence_min:    0.60
observers.yolo.device: cpu  # → hailo si AI HAT+ installé
observers.surface.texture_weight: 0.55
observers.surface.isoforest_weight: 0.45
observers.surface.isoforest_n: 1000
observers.surface.seed: 42
```

---

## Vérification rapide conformité v7.0

```bash
# Vérifier aucun Ensemble global
grep -r "EnsembleEngine\|fused_score\|weighted_average" ts2i_ivs/ \
  --include="*.py" | grep -v "SurfaceObserver\|test_\|#"
# → Doit être vide (seul SurfaceObserver autorisé)

# Vérifier aucun verdict dans un observer
grep -r "return.*OK\|return.*NOK" ts2i_ivs/ai/ --include="*.py"
# → Doit être vide

# Vérifier Rule Engine sans learn
grep -r "def learn\|def train\|def update" ts2i_ivs/core/rule_engine.py
# → Doit être vide
```

---

*TS2I IVS v7.0 — CLAUDE.md*
*12 Golden Rules · Anti-Patterns · Architecture Rule-Governed*
*AI observe · Rule Engine décide · 3 Tiers · 5 Observers*
