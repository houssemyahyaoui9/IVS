# IVS_SESSIONS_v9_COMPLETE.md
# TS2I IVS v9.0 — Sessions de Développement Complètes
# Version consolidée : v7.0 + v8.0 corrigé + v9.0 nouveau
#
# Historique :
#   v7.0 : Architecture Rule-Governed Hierarchical (35 sessions)
#   v8.0 : UI Overhaul partiel — 6 sessions (S25→S30) — NON INTÉGRÉ
#   v9.0 : Consolidation complète + corrections + 5 nouvelles sessions
#
# Statut sessions :
#   S00→S19          : INCHANGÉES (voir IVS_SESSIONS_v7_COMPLETE.md)
#   S20, S21         : RÉÉCRITES (interface + wizard produit)
#   S22→S24          : INCHANGÉES (voir IVS_SESSIONS_v7_COMPLETE.md)
#   S25→S30          : CORRIGÉES ET COMPLÉTÉES
#   S31, S32, S33    : NOUVELLES
#   S_FLEET-A, B     : INCHANGÉES (voir IVS_SESSIONS_v7_COMPLETE.md)

---

## Vue d'ensemble v9.0

```
Sessions inchangées v7 : S00-A → S19-A, S22-A→S24-B, S_FLEET-A→B
Sessions réécrites     : S20-A (InspectionScreen), S21-A (Wizard Produit)
Sessions corrigées     : S25→S30 (Theme, Operators, Telemetry, Grid, Shortcuts)
Sessions nouvelles     : S31 (MainWindow v9), S32 (Products Page), S33 (Operators Page)

Total v9.0 : 41 sessions core + 3 nouvelles = 44 sessions
```

---

## Règles v9.0 — Toutes les règles actives

```
══ RÈGLES CORE v7.0 (inchangées) ══════════════════════════════
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
GR-13 FLEET-IMPORT     Validation ModelValidator obligatoire avant activation

══ RÈGLES UI v8.0 (corrigées) ══════════════════════════════════
GR-V8-1 ZÉRO modification du core/, pipeline/, observers/, rule_engine/
GR-V8-2 Tous les écrans héritent du thème global (pas de styles inline)
GR-V8-3 Toutes les actions UI passent par SystemController (GR-03)
GR-V8-4 Operators stockés en DB SQLite + bcrypt pour PIN (jamais plain text)
GR-V8-5 Themes commutables à chaud sans redémarrage
GR-V8-6 Layouts grids sauvegardés dans config/ui_prefs.yaml (global)
GR-V8-7 Aucune session v8/v9 ne casse les sessions v7 (pytest tests/ vert)

══ RÈGLES NOUVELLES v9.0 ═══════════════════════════════════════
GR-V9-1 DEUX ÉCRANS    Navigation principale ≠ Inspection (F11/Esc)
GR-V9-2 THEME AU BOOT  ThemeManager.apply() AVANT QMainWindow.show()
GR-V9-3 PANELS ORDER   Ordre panels telemetry sauvegardé dans ui_prefs.yaml
GR-V9-4 SHORTCUTS CFG  Tous les raccourcis configurables via ShortcutManager
GR-V9-5 LOGO IMAGE     Chaque LogoDefinition DOIT avoir reference_image non-None
GR-V9-6 PRODUCT CRUD   Suppression produit FORBIDDEN si état = RUNNING
GR-V9-7 OPERATOR BCRYPT PIN hashé bcrypt · jamais stocké plain text · jamais loggué
GR-V9-8 TABS NORTH     QTabWidget.setTabPosition(North) dans tous les écrans
```

---

# ════════════════════════════════════════════════════════════════
# SESSIONS S00 → S19  (INCHANGÉES)
# ════════════════════════════════════════════════════════════════

```
Ces sessions sont identiques à IVS_SESSIONS_v7_COMPLETE.md.
Copier les prompts S00-A → S19-A sans modification.

Résumé :
  S00-A  Structure projet + config + DB schema + main.py --check
  S01-A  ObserverSignal + TierVerdict + FinalResult (dataclasses frozen)
  S02-A  CameraManager + FakeCamera
  S03-A  FSM 9 états + SystemController + Pipeline chain
  S04-A  CalibrationEngine 7 étapes
  S05-A  FeatureExtractor + DatasetManager
  S06-A  SIFT Alignment + SiftObserver
  S07-A  IsolationForest + ModelVersionManager
  S08-A  YOLOv8x Observer CRITICAL
  S09-A  ΔE2000 ColorObserver MAJOR
  S10-A  SurfaceObserver Mini Ensemble MINOR
  S11-A  CaliperObserver ±0.02mm MAJOR
  S12-A  RuleEngine décideur unique v7.0
  S13-A  TierOrchestrator Fail-Fast Hybride
  S14-A  OcrObserver + BarcodeObserver
  S15-A  LLM Explainer v7.0
  S16-A  TierLearningBuffer + BackgroundTrainer + 3 Gates
  S17-A  ROI Editor
  S18-A  FastAPI 15 endpoints + WebSocket
  S19-A  SPC par Tier + Rapports PDF

⚠ NOTE S00-A : Ajouter au schéma SQL initial :
  ALTER TABLE products ADD COLUMN category TEXT DEFAULT 'carpet_logo';
  ALTER TABLE operators ADD COLUMN pin_hash TEXT;
  ALTER TABLE operators ADD COLUMN last_login REAL;
```

---

# ════════════════════════════════════════════════════════════════
# S20-v9 — InspectionScreen RÉÉCRITE
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : InspectionScreen v9 — FlexibleGrid + TelemetryPanel draggable
⏱  Durée    : 3 jours
🔄 Statut   : REMPLACEMENT de S20-A v7 (layout fixe 3 grids → layout flexible)
📄 Dépend   : S28 (TelemetryPanel), S29 (FlexibleGridView) — faire S28+S29 AVANT
```

## Spec S20-v9

### Architecture

```
ui/screens/inspection_screen.py   ← RÉÉCRIRE COMPLÈTEMENT

InspectionScreen — layout v9 :
  ┌─ ControlBar ───────────────────────────────────────────────┐
  │ [▶ Start F5] [■ Stop F6] | ⏱[5s ▼] | ⊞[2 Grids] [Std ▼]│
  │                                    Produit: Tapis P208 v3.1│
  ├─ body ─────────────────────────────────────────────────────┤
  │ TelemetryPanel   │  FlexibleGridView                        │
  │ (draggable       │  ┌──────────────────────────────────┐   │
  │  sections)       │  │ tier-row badges                  │   │
  │                  │  ├──────────────┬───────────────────┤   │
  │ 📊 Session       │  │  Grid 1      │  Grid 2           │   │
  │ ⚡ Pipeline      │  │  [src ▼] ⛶📸│  [src ▼] ⛶📸     │   │
  │ 📷 Image Qualité │  ├──────────────┴───────────────────┤   │
  │ 🔬 Observers     │  │  ResultBand                       │   │
  │                  │  └──────────────────────────────────┘   │
  ├─ StatusBar ────────────────────────────────────────────────┤
  │ 👤 Ahmed  CPU 62%  RAM 3.2GB  TEMP 58°C  FPS 28  UP 4h   │
  └────────────────────────────────────────────────────────────┘
```

### InspectionScreen(QWidget)

```python
class InspectionScreen(QWidget):
    """
    Écran d'inspection principal v9.
    Toujours visible — pas un dialog.
    S'intègre dans MainWindow comme widget central.
    """

    def __init__(self, system_controller: SystemController,
                 ui_bridge: UIBridge,
                 theme_manager: ThemeManager,
                 shortcut_manager: ShortcutManager): ...

    # ── Layout ──
    def _build_layout(self) -> None:
        """
        QHBoxLayout :
          - TelemetryPanel (w=200px, border-right)
          - QVBoxLayout :
              - ControlBar (QWidget)
              - tier_row (QWidget — 3 TierVerdictBadges)
              - FlexibleGridView (stretch=1)
              - ResultBand
        """

    # ── ControlBar ──
    def _build_control_bar(self) -> QWidget:
        """
        Contient :
          btn_start, btn_stop (via ShortcutManager)
          mode_combo : Intervalle [1s, 5s, 10s, 20s, Personnalisé]
          grid_combo : [1, 2, 3, 4] grids
          preset_combo : [Standard, Défaut Focus, Analyse Full, Monitoring]
          label_product : nom produit actif (droite)
        """

    # ── Signals UIBridge → UI ──
    def _on_result(self, result: FinalResult) -> None:
        """Appeler depuis UIBridge signal — GR-05"""
        self._result_band.update(result)
        self._tier_badges.update(result.tier_verdicts)
        self._telemetry.update_session(result)
        self._grid_view.on_result(result)
        self._observers_panel.update(result)

    def _on_frame(self, frame: np.ndarray,
                  metadata: dict) -> None:
        """Frame brute → grids + image quality"""
        self._telemetry.update_image_quality(frame, metadata)
        self._grid_view.update_frame(frame, metadata)

    def _on_system_state(self, state: SystemState) -> None:
        """FSM state change → ControlBar enable/disable"""
        running = (state == SystemState.RUNNING)
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        self._mode_combo.setEnabled(not running)
```

### Mode Déclenchement

```python
class TriggerMode(Enum):
    INTERVALLE = "intervalle"
    MANUEL     = "manuel"

class IntervalleValues:
    PRESETS = [1000, 5000, 10000, 20000]  # ms
    # "Personnalisé" → QInputDialog pour valeur libre

# Dans SystemController :
def set_trigger_mode(self, mode: TriggerMode,
                     interval_ms: int = 5000) -> None:
    """GR-03 — appelé depuis ControlBar"""
    self._trigger_mode = mode
    self._interval_ms  = interval_ms
    if mode == TriggerMode.INTERVALLE:
        self._timer.start(interval_ms)
    else:
        self._timer.stop()

def trigger_once(self) -> None:
    """Mode MANUEL — bouton Start ou F5"""
    if self._state == SystemState.RUNNING:
        self._pipeline.run_once()
```

### Gate G-S20-v9

```bash
pytest tests/ui/test_inspection_screen_v9.py -v

# - ControlBar : btn_start/stop connectés via SystemController (GR-03)
# - Mode Intervalle : timer démarre/s'arrête selon mode
# - FlexibleGridView intégrée (pas 3 QLabel fixes)
# - TelemetryPanel intégré (draggable)
# - ResultBand mis à jour via UIBridge signal
# - TierVerdictBadges : 3 badges corrects
# - FSM RUNNING → btn_start disabled, btn_stop enabled
# - FSM IDLE → btn_start enabled, btn_stop disabled
# - theme appliqué (pas de noir sur noir) — GR-V9-2
python3 -c "
from ui.screens.inspection_screen import InspectionScreen
# Vérifier : pas de QLabel pour les grids
import subprocess, sys
result = subprocess.run(['grep', '-n', 'QLabel', 'ui/screens/inspection_screen.py'],
                        capture_output=True, text=True)
assert not result.stdout, f'Anti-pattern QLabel détecté : {result.stdout}'
print('✅ Aucun QLabel dans InspectionScreen')
"
```

---

# ════════════════════════════════════════════════════════════════
# S21-v9 — Product Definition Wizard RÉÉCRIT (9 étapes)
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : Wizard complet avec saisie logo image + specs tapis
⏱  Durée    : 4 jours
🔄 Statut   : REMPLACEMENT de S21-A v7 (ajout étapes 0 et logo-form)
📄 Dépend   : S20-v9, S22-B (ProductCanvas)
```

## Spec S21-v9

### Architecture

```
ui/screens/product_definition_wizard.py   ← NOUVEAU (remplace product_creation_screen.py)
ui/components/logo_form_widget.py         ← NOUVEAU
ui/components/tapis_form_widget.py        ← NOUVEAU
ui/components/logo_image_picker.py        ← NOUVEAU
```

### Wizard — 9 étapes

```
Étape 0 : Métadonnées Tapis
  Nom produit    : [QLineEdit]
  ID produit     : [QLineEdit — auto-généré, modifiable]
  Version        : [QLineEdit — "1.0"]
  Barcode/QR     : [QLineEdit — optionnel]
  Station ID     : [QLineEdit — "S01"]

Étape 1 : Dimensions Tapis
  ┌─────────────────────────────────────────┐
  │  Largeur   : [  800  ] mm               │
  │  Hauteur   : [ 1000  ] mm               │
  │  ─────────────────────────────────────  │
  │  Preview automatique du canvas vide     │
  │  (tapis dessiné à l'échelle)            │
  └─────────────────────────────────────────┘

Étape 2 : Images référence Tapis
  📁 Image GOOD × ≥1  (obligatoire)
  📁 Image BAD        (optionnel — pour training)
  Preview : miniatures avec [✕] pour supprimer

Étape 3 : Définition des Logos  ← NOUVEAU
  [+ Ajouter Logo]

  ┌─ Logo #1 ──────────────────────────────┐
  │  Nom        : [Logo Lion              ] │
  │  Image réf  : [📁 Charger...] ← OBLIGATOIRE │
  │               [preview 80×80px]         │
  │  Largeur    : [  120  ] mm              │
  │  Hauteur    : [   80  ] mm              │
  │  Couleur    : [████] #FFD700            │
  │  Tolérance ΔE : [ 8.0 ]                │
  │  Tolérance pos: [ ±5  ] mm             │
  │  Obligatoire  : [☑]                    │
  │  [🗑 Supprimer]                         │
  └────────────────────────────────────────┘
  [+ Ajouter Logo]

  Règles :
    Min 1 logo obligatoire
    Max 10 logos (GR existant S22-B)
    Image obligatoire (GR-V9-5)
    Image copiée dans products/{id}/logos/logo_{idx}.png

Étape 4 : Canvas Positionnement  (= S22-B existant, adapté)
  Tapis pré-dessiné depuis étape 1 (dimensions automatiques)
  Logos disponibles depuis étape 3 dans liste gauche
  Drag & drop sur canvas pour positionner
  → Met à jour LogoDefinition.position_relative

Étape 5 : TierPriorityWidget  (= S21-A v7 existant)
  Critères pré-remplis depuis logos définis en étape 3

Étape 6 : ROI Zones  (= S17-A existant)

Étape 7 : Calibration  (= S04-A existant)

Étape 8 : Entraînement AI  (= S16-A existant)
```

### LogoFormWidget

```python
class LogoFormWidget(QGroupBox):
    """
    Formulaire pour un seul logo.
    Utilisé dans étape 3 du wizard.
    Émis logoChanged(logo_index, LogoDefinition) à chaque modification.
    """
    logoChanged = pyqtSignal(int, object)
    logoDeleted = pyqtSignal(int)

    def __init__(self, logo_index: int,
                 parent: QWidget = None): ...

    def set_image(self, path: str) -> None:
        """Copie image → products/tmp/logos/logo_{idx}.png"""
        # Vérifier format : PNG/JPG/BMP
        # Redimensionner en preview 80×80
        # GR-V9-5 : obligatoire avant de passer à l'étape suivante

    def to_logo_definition(self) -> LogoDefinition:
        """Convertit le formulaire en LogoDefinition frozen."""
        return LogoDefinition(
            logo_id=f"logo_{self._index}",
            logo_index=self._index,
            label=self._name_input.text(),
            reference_image=self._image_path,  # GR-V9-5
            width_mm=self._width_input.value(),
            height_mm=self._height_input.value(),
            position_relative=(0.5, 0.5),  # mis à jour par Canvas étape 4
            tolerance_mm=self._pos_tol_input.value(),
            color_hex=self._color_hex,
            color_tolerance_de=self._de_input.value(),
            mandatory=self._mandatory_check.isChecked()
        )

    def validate(self) -> list[str]:
        """Retourne liste d'erreurs. Vide = valide."""
        errors = []
        if not self._image_path:
            errors.append(f"Logo #{self._index} : image obligatoire (GR-V9-5)")
        if not self._name_input.text().strip():
            errors.append(f"Logo #{self._index} : nom obligatoire")
        if self._width_input.value() < 10:
            errors.append(f"Logo #{self._index} : largeur min 10mm")
        return errors
```

### Validation inter-étapes

```python
# ProductDefinitionWizard.validateCurrentPage()
def validateCurrentPage(self) -> bool:
    page = self.currentId()

    if page == 3:  # Logos
        errors = []
        for widget in self._logo_widgets:
            errors.extend(widget.validate())
        if errors:
            QMessageBox.warning(self, "Validation",
                                "\n".join(errors))
            return False
        if not self._logo_widgets:
            QMessageBox.warning(self, "Validation",
                                "Au moins 1 logo obligatoire.")
            return False
    return True
```

### Gate G-S21-v9

```bash
pytest tests/ui/test_product_wizard_v9.py -v

# - Étape 3 : logo sans image → validation bloquante (GR-V9-5)
# - Étape 3 : image PNG chargée → preview affiché → copiée products/tmp/
# - to_logo_definition() : reference_image non-None
# - Étape 4 : canvas affiche tapis aux dimensions de l'étape 1
# - Étape 4 : logo drag → position_relative mis à jour
# - ProductDefinition sauvegardée → config.json avec logo.reference_image
# - Logo image copiée dans products/{id}/logos/logo_0.png
```

---

# ════════════════════════════════════════════════════════════════
# SESSIONS S22 → S24  (INCHANGÉES)
# ════════════════════════════════════════════════════════════════

```
Ces sessions sont identiques à IVS_SESSIONS_v7_COMPLETE.md.

  S22-A  ZoomableGridView + FullscreenGridWindow
  S22-B  ProductCanvas + LogoDefinition multi-logo
         ⚠ NOTE : ProductCanvas reçoit maintenant les logos
           déjà définis depuis étape 3 du wizard S21-v9
           (ne crée plus les logos depuis zéro)
  S22-C  LogoInspectionEngine multi-logo
  S22-D  Auto-Switch QR/Barcode
  S22-E  E2E Tapis Voiture + Gates 22-25
  S23-A  WatchdogManager
  S23-B  ConsecutiveNOKWatcher
  S23-C  LuminosityChecker
  S23-D  SystemMonitor CPU/RAM/Température
  S24-A  GPIO basique OK/NOK
  S24-B  GPIO Dashboard
```

---

# ════════════════════════════════════════════════════════════════
# S25-v9 — Theme System CORRIGÉ (Light + Dark)
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : 2 thèmes industriels + application correcte au boot
⏱  Durée    : 2 jours
🔄 Statut   : CORRECTION de S25 v8 (ThemeManager non appliqué + un seul thème dark)
🐛 Bug fixé : Noir sur noir — ThemeManager non appelé dans main.py
```

## Spec S25-v9

### Architecture

```
ui/theme/
├── __init__.py
├── theme_manager.py        ← Singleton — CORRIGÉ
├── colors.py               ← palettes
├── styles.py               ← générateur QSS
└── presets/
    ├── light.py            ← Blanc / Texte noir (NOUVEAU)
    └── dark.py             ← Fond #0d1117 / Cyan (REMPLACE cognex/keyence/halcon)
```

### Thème Light

```python
@dataclass(frozen=True)
class LightPalette(ThemePalette):
    name             = "light"

    bg_primary       = "#ffffff"
    bg_secondary     = "#f6f6f6"
    bg_tertiary      = "#f0f0f0"
    bg_grid          = "#fafafa"

    text_primary     = "#111111"
    text_secondary   = "#444444"
    text_muted       = "#888888"
    text_disabled    = "#bbbbbb"

    success          = "#16a34a"
    warning          = "#ea580c"
    danger           = "#dc2626"
    review           = "#7c3aed"
    info             = "#1d4ed8"

    accent_primary   = "#1d4ed8"
    accent_secondary = "#2563eb"

    border_subtle    = "#e8e8e8"
    border_default   = "#d0d0d0"
    border_strong    = "#b0b0b0"

    shadow           = "rgba(0,0,0,0.1)"
    glow             = "none"
```

### Thème Dark

```python
@dataclass(frozen=True)
class DarkPalette(ThemePalette):
    name             = "dark"

    bg_primary       = "#0d1117"
    bg_secondary     = "#161b22"
    bg_tertiary      = "#21262d"
    bg_grid          = "#010409"

    text_primary     = "#e6edf3"
    text_secondary   = "#c9d1d9"
    text_muted       = "#8b949e"
    text_disabled    = "#484f58"

    success          = "#4ade80"
    warning          = "#fb923c"
    danger           = "#f87171"
    review           = "#c084fc"
    info             = "#06b6d4"

    accent_primary   = "#06b6d4"
    accent_secondary = "#0891b2"

    border_subtle    = "#21262d"
    border_default   = "#30363d"
    border_strong    = "#484f58"

    shadow           = "rgba(0,0,0,0.4)"
    glow             = "0 0 8px rgba(6,182,212,0.3)"
```

### ThemeManager CORRIGÉ

```python
class ThemeManager(QObject):
    THEMES = {"light": LightPalette, "dark": DarkPalette}
    themeChanged = pyqtSignal(str)

    _instance: "ThemeManager | None" = None

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def apply(self, theme_name: str) -> None:
        """
        GR-V9-2 : Appeler AVANT QMainWindow.show()
        GR-V8-5 : Commutable à chaud sans redémarrage
        """
        palette = self.THEMES.get(theme_name, LightPalette)()
        qss = generate_qss(palette)
        QApplication.instance().setStyleSheet(qss)
        self._current = theme_name
        self.themeChanged.emit(theme_name)

    def current_theme(self) -> str:
        return self._current

    def available_themes(self) -> list[str]:
        return list(self.THEMES.keys())
```

### main.py CORRIGÉ (ordre obligatoire)

```python
def main() -> None:
    app = QApplication(sys.argv)

    # ── STEP 1 : Config ──
    config = Config.load("config/config.yaml")

    # ── STEP 2 : Theme AVANT tout widget (GR-V9-2) ──
    theme = ThemeManager.instance()
    theme.apply(config.get("ui.theme", "light"))  # défaut : light

    # ── STEP 3 : MainWindow ──
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())
```

### QSS minimum — onglets NORD obligatoire (GR-V9-8)

```css
/* GR-V9-8 : tabs NORTH uniquement */
QTabWidget::tab-bar { alignment: left; }
QTabBar { /* position North — jamais West/East/South */ }
```

### Gate G-S25-v9

```bash
# Test 1 : QSS non vide, couvre tous les widgets
python3 -c "
from ui.theme.presets.light import LightPalette
from ui.theme.presets.dark  import DarkPalette
from ui.theme.styles import generate_qss
for P in [LightPalette, DarkPalette]:
    qss = generate_qss(P())
    assert len(qss) > 3000, f'{P.name} QSS trop court : {len(qss)}'
    for w in ['QPushButton','QLabel','QTableWidget','QTabWidget',
              'QLineEdit','QScrollBar','QComboBox']:
        assert w in qss, f'{w} manquant dans {P.name}'
    print(f'✅ {P.name} QSS valide ({len(qss)} chars)')
"

# Test 2 : ThemeManager appliqué avant show()
grep -n "theme.apply\|ThemeManager" main.py
# → theme.apply() DOIT apparaître AVANT window.show()

# Test 3 : Aucun setStyleSheet inline dans les écrans
grep -rn "setStyleSheet" ui/ --include="*.py" | grep -v "theme_manager\|test_\|#"
# → DOIT être vide (tout centralisé dans ThemeManager)

# Test 4 : Tabs en position North
grep -rn "setTabPosition" ui/ --include="*.py"
# → DOIT afficher North ou rien (jamais West/East/South)
```

---

# ════════════════════════════════════════════════════════════════
# S26-v9 — Operators CRUD COMPLÉTÉ
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : Système opérateurs complet (core + DB + API)
⏱  Durée    : 2 jours
🔄 Statut   : COMPLÉTION de S26 v8
```

## Spec S26-v9

### Modèle

```python
from enum import Enum
from dataclasses import dataclass

class OperatorRole(Enum):
    ADMIN    = "admin"     # tout : produits + opérateurs + paramètres
    OPERATOR = "operator"  # inspection + REVIEW validation
    VIEWER   = "viewer"    # lecture seule

@dataclass(frozen=True)
class Operator:
    operator_id  : str
    name         : str
    role         : OperatorRole
    pin_hash     : str          # bcrypt — jamais plain text (GR-V9-7)
    active       : bool
    created_at   : float
    last_login   : float | None
```

### OperatorManager

```python
# core/operators/operator_manager.py

class OperatorManager:
    """
    CRUD opérateurs. GR-V9-7 : PIN jamais stocké plain text.
    """

    def create(self, name: str, role: OperatorRole,
               pin: str) -> Operator:
        """
        pin → bcrypt.hashpw(pin.encode(), bcrypt.gensalt())
        Jamais logguer le pin (GR-V9-7)
        """

    def authenticate(self, operator_id: str,
                     pin: str) -> Operator | None:
        """
        Vérifie bcrypt.checkpw(pin.encode(), stored_hash)
        Retourne None si PIN incorrect
        Met à jour last_login si succès
        """

    def update(self, operator_id: str,
               name: str | None = None,
               role: OperatorRole | None = None,
               active: bool | None = None) -> Operator:
        """Mise à jour — PAS de changement PIN ici (méthode séparée)"""

    def change_pin(self, operator_id: str,
                   new_pin: str) -> None:
        """Nouveau hash bcrypt — GR-V9-7"""

    def delete(self, operator_id: str) -> None:
        """Interdit si opérateur actuellement connecté"""

    def list_all(self) -> list[Operator]: ...
    def get(self, operator_id: str) -> Operator | None: ...

    def get_stats(self, operator_id: str) -> dict:
        """
        Retourne depuis TABLE operator_stats :
        total, ok_count, nok_count, taux_ok, last_inspection
        """
```

### Permissions

```python
# core/operators/permissions.py

PERMISSIONS: dict[OperatorRole, set[str]] = {
    OperatorRole.ADMIN: {
        "product.create", "product.edit", "product.delete",
        "operator.create", "operator.edit", "operator.delete",
        "inspection.start", "inspection.stop",
        "review.validate",
        "settings.edit", "gpio.config",
        "fleet.export", "fleet.import",
    },
    OperatorRole.OPERATOR: {
        "inspection.start", "inspection.stop",
        "review.validate",
    },
    OperatorRole.VIEWER: {
        # lecture seule — aucune action
    },
}

def requires_permission(permission: str):
    """Décorateur pour méthodes SystemController."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            op = self._current_operator
            if op is None:
                raise PermissionError("Non connecté")
            if permission not in PERMISSIONS[op.role]:
                raise PermissionError(
                    f"Rôle {op.role.value} : permission "
                    f"'{permission}' refusée"
                )
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
```

### Gate G-S26-v9

```bash
pytest tests/unit/test_operator_manager.py -v

# - create() → PIN hashé (jamais plain text dans DB)
# - authenticate() correct PIN → Operator retourné
# - authenticate() mauvais PIN → None
# - Permissions ADMIN : toutes accordées
# - Permissions OPERATOR : inspection + review seulement
# - Permissions VIEWER : toutes refusées
# - @requires_permission décorateur bloque OPERATOR sur product.create
# - delete() opérateur connecté → PermissionError
```

---

# ════════════════════════════════════════════════════════════════
# S27-v9 — Operators UI COMPLÉTÉ (Login + Page Dédiée)
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : LoginDialog + Page Opérateurs complète (CRUD)
⏱  Durée    : 2 jours
🔄 Statut   : COMPLÉTION de S27 v8
📄 Dépend   : S26-v9, S31 (MainWindow)
```

## Spec S27-v9

### Architecture

```
ui/screens/login_dialog.py        ← Login PIN entry
ui/screens/operators_screen.py    ← Page dédiée (NON dans SettingsTab)
ui/components/operator_card.py    ← Carte d'un opérateur
ui/components/operator_form.py    ← Formulaire ajout/édition
```

### LoginDialog

```python
class LoginDialog(QDialog):
    """
    Dialog de connexion PIN.
    Affiché au démarrage et sur Ctrl+L.
    """
    loginSuccess = pyqtSignal(object)   # Operator

    layout :
      Label : "Sélectionner opérateur"
      QListWidget : liste opérateurs actifs (nom + rôle)
      Label : "Entrer PIN"
      QLineEdit : echoMode=Password, maxLength=6
      [Connexion]  [Annuler]
      Label erreur : "PIN incorrect" (rouge, caché par défaut)

    def _on_login(self) -> None:
        selected = self._list.currentItem()
        pin = self._pin_input.text()
        op = self._manager.authenticate(selected.data(Qt.UserRole), pin)
        if op:
            self.loginSuccess.emit(op)
            self.accept()
        else:
            self._error_label.show()
            self._pin_input.clear()
            self._pin_input.setFocus()
```

### OperatorsScreen

```python
class OperatorsScreen(QWidget):
    """
    Page complète gestion opérateurs.
    Accessible via Tab "👥 Opérateurs" dans MainWindow.
    Visible uniquement si role == ADMIN (GR-V9-7).
    """
    layout :
      ┌─ Header ──────────────────────────────────────────────┐
      │ [+ Nouvel Opérateur]              [🔍 Rechercher...]  │
      ├─ Liste (QScrollArea) ─────────────────────────────────┤
      │  OperatorCard × N                                     │
      └───────────────────────────────────────────────────────┘

    def _load_operators(self) -> None:
        """Charge depuis OperatorManager.list_all()"""

    def _on_add(self) -> None:
        """Ouvre OperatorFormDialog en mode création"""

    def _on_edit(self, op_id: str) -> None:
        """Ouvre OperatorFormDialog en mode édition"""

    def _on_delete(self, op_id: str) -> None:
        """Confirmation → OperatorManager.delete()"""
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Supprimer l'opérateur {name} ?\n"
            "Cette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._manager.delete(op_id)
            self._load_operators()

    def _on_toggle_active(self, op_id: str,
                          active: bool) -> None:
        """Active/désactive un opérateur"""
        self._manager.update(op_id, active=active)
```

### OperatorCard

```python
class OperatorCard(QFrame):
    """
    Carte d'affichage d'un opérateur dans la liste.
    Affiche : nom, rôle, stats, dernière connexion, boutons.
    """
    layout :
      ┌────────────────────────────────────────────────┐
      │ 👤 Ahmed Ben Ali           [🔴 ADMIN] [●Actif] │
      │ ID: OP-001                                     │
      │ Inspections: 1247 · OK: 96.2% · NOK: 3.8%    │
      │ Dernière connexion: aujourd'hui 08:42          │
      │ [✏ Modifier] [🔑 Reset PIN] [○ Désactiver]    │
      └────────────────────────────────────────────────┘

    Couleurs rôle :
      ADMIN    → accent_primary (#1d4ed8 light / #06b6d4 dark)
      OPERATOR → warning (#ea580c)
      VIEWER   → text_muted
```

### Gate G-S27-v9

```bash
pytest tests/ui/test_operators_screen.py -v

# - LoginDialog : PIN correct → loginSuccess émis
# - LoginDialog : PIN incorrect → erreur affichée, champ vidé
# - OperatorsScreen : visible si ADMIN, caché si OPERATOR
# - OperatorCard : stats affichées depuis operator_stats
# - Add : OperatorFormDialog → create() appelé → refresh liste
# - Delete : confirmation → delete() appelé → carte disparaît
# - Toggle active : update(active=False) → card mise à jour
# - PIN reset : change_pin() appelé (jamais plain text affiché)
```

---

# ════════════════════════════════════════════════════════════════
# S28-v9 — TelemetryPanel Draggable RÉÉCRIT
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : Panel gauche avec 4 sections réorganisables par drag
⏱  Durée    : 2 jours
🔄 Statut   : REMPLACEMENT de S28 v8
📄 Dépend   : S25-v9 (thème)
```

## Spec S28-v9

### Architecture

```
ui/components/telemetry_panel.py     ← NOUVEAU (remplace S28 v8)
ui/components/telemetry_section.py   ← Section draggable individuelle
```

### TelemetrySection (draggable)

```python
class TelemetrySection(QFrame):
    """
    Section draggable du TelemetryPanel.
    Header avec icône ⠿ de drag.
    Contenu variable selon type.
    """
    moved = pyqtSignal(str, int)   # section_id, new_position

    SECTIONS = {
        "session"   : ("📊", "Session",       SessionSectionContent),
        "pipeline"  : ("⚡", "Pipeline",      PipelineSectionContent),
        "image_qual": ("📷", "Image Qualité", ImageQualitySectionContent),
        "observers" : ("🔬", "Observers",     ObserversSectionContent),
    }

    def __init__(self, section_id: str, ui_bridge: UIBridge): ...

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self._section_id)
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)
```

### TelemetryPanel

```python
class TelemetryPanel(QWidget):
    """
    Container des sections draggables.
    Sauvegarde l'ordre dans ui_prefs.yaml (GR-V9-3).
    """

    DEFAULT_ORDER = ["session", "pipeline", "image_qual", "observers"]

    def __init__(self, ui_bridge: UIBridge,
                 config: Config): ...

    def _load_order(self) -> list[str]:
        """Charge ordre depuis config/ui_prefs.yaml"""
        prefs = self._config.get("ui.telemetry_order",
                                  self.DEFAULT_ORDER)
        return prefs

    def _save_order(self) -> None:
        """Sauvegarde ordre dans config/ui_prefs.yaml (GR-V9-3)"""
        order = [s.section_id for s in self._sections]
        self._config.set("ui.telemetry_order", order)

    def dragEnterEvent(self, event) -> None:
        event.accept()

    def dropEvent(self, event) -> None:
        source_id = event.mimeData().text()
        drop_pos  = event.position().toPoint()
        target    = self._find_section_at(drop_pos)
        if target and target.section_id != source_id:
            self._reorder(source_id, target.section_id)
            self._save_order()

    # ── Updates ──
    def update_session(self, result: FinalResult) -> None:
        self._sections["session"].update(result)

    def update_pipeline(self, latencies: dict) -> None:
        self._sections["pipeline"].update(latencies)

    def update_image_quality(self, frame: np.ndarray,
                              metadata: dict) -> None:
        self._sections["image_qual"].update(frame, metadata)

    def update_observers(self, result: FinalResult) -> None:
        self._sections["observers"].update(result)
```

### ObserversSectionContent

```python
class ObserversSectionContent(QWidget):
    """
    Affiche chaque observer avec :
      ● (couleur selon résultat) | Nom | Tier badge | Valeur
    Mis à jour via FinalResult.tier_verdicts
    """
    # Observers affichés :
    # YOLO Logo    [CRIT]  0.94 ✅
    # SIFT Align   [CRIT]  ±1.3mm ✅
    # Color ΔE     [MAJ]   2.1 ✅
    # Caliper      [MAJ]   803mm ❌
    # Surface      [MIN]   0.87 ✅
    # OCR          [MIN]   — (disabled, gris)

    def update(self, result: FinalResult) -> None:
        for signal in result.all_signals():
            row = self._rows[signal.observer_id]
            row.set_result(signal.passed, signal.value,
                           signal.error_msg)
```

### ImageQualitySectionContent

```python
class ImageQualitySectionContent(QWidget):
    """
    Luminosité, Contraste, Netteté, Exposition, Gain.
    Chaque métrique affichée avec :
      - valeur actuelle
      - référence calibration ± tolérance
      - delta coloré (vert/orange)
      - barre jauge
    Calculé depuis frame numpy dans S2 (PreProcess).
    Mis à jour via UIBridge signal toutes les frames.
    """

    METRICS = [
        ("Luminosité",  "brightness",  0, 255),
        ("Contraste",   "contrast",    0, 128),
        ("Netteté",     "sharpness",   0, 500),
        ("Exposition",  "exposure",    None, None),  # texte
        ("Gain",        "gain",        None, None),  # texte
    ]

    def update(self, frame: np.ndarray,
               metadata: dict) -> None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) \
               if len(frame.shape) == 3 else frame

        brightness = float(gray.mean())
        contrast   = float(gray.std())
        sharpness  = float(cv2.Laplacian(gray,
                           cv2.CV_64F).var())

        self._update_metric("brightness", brightness)
        self._update_metric("contrast",   contrast)
        self._update_metric("sharpness",  sharpness)
        self._lbl_exposure.setText(
            metadata.get("exposure", "—"))
        self._lbl_gain.setText(
            f"{metadata.get('gain', 1.0):.1f}×")
```

### Gate G-S28-v9

```bash
pytest tests/ui/test_telemetry_panel.py -v

# - 4 sections présentes dans le bon ordre (DEFAULT_ORDER)
# - Drag section "observers" → au-dessus "session" → ordre mis à jour
# - Ordre sauvegardé dans ui_prefs.yaml
# - Rechargement → ordre persisté
# - update_image_quality() : brightness/contrast/sharpness calculés
# - ObserversSection : signal NOK → row rouge
# - ObserversSection : observer disabled → row gris "—"
```

---

# ════════════════════════════════════════════════════════════════
# S29-v9 — FlexibleGridView RÉÉCRIT (1/2/3/4 grids)
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : Grille flexible avec sources configurables + right-click menu
⏱  Durée    : 3 jours
🔄 Statut   : REMPLACEMENT de S29 v8 (max 4 grids, pas 6)
📄 Dépend   : S22-A (ZoomableGridView), S25-v9 (thème)
```

## Spec S29-v9

### Sources disponibles

```python
class GridSource(Enum):
    LIVE_RAW      = ("live_raw",      "📷 Live Raw")
    ALIGNED       = ("aligned",       "📐 Aligned")
    LOGO_ZOOM     = ("logo_zoom",     "🔍 Logo Zoom")
    DIFFERENTIAL  = ("differential",  "🔬 Differential")
    REFERENCE     = ("reference",     "📋 Reference")
    ROI_OVERLAY   = ("roi_overlay",   "🎯 ROI Overlay")
    HEATMAP       = ("heatmap",       "🌡 Heatmap")
    CALIPER       = ("caliper",       "📏 Caliper")
```

### Layouts disponibles

```python
LAYOUTS: dict[str, dict] = {
    "1":        {"count": 1, "cols": 1, "rows": 1},
    "2_50_50":  {"count": 2, "cols": 2, "rows": 1, "ratios": [1,1]},
    "2_70_30":  {"count": 2, "cols": 2, "rows": 1, "ratios": [7,3]},
    "2_30_70":  {"count": 2, "cols": 2, "rows": 1, "ratios": [3,7]},
    "3_eq":     {"count": 3, "cols": 3, "rows": 1},
    "3_50_25":  {"count": 3, "cols": None, "rows": None,
                 "split": "70_30_split"},  # 1 grand + 2 petits
    "4_2x2":    {"count": 4, "cols": 2, "rows": 2},
    "4_main":   {"count": 4, "split": "main_plus_3"},
}

PRESETS: dict[str, dict] = {
    "Standard":     {"layout": "2_50_50",
                     "sources": ["live_raw", "roi_overlay"]},
    "Défaut Focus": {"layout": "3_50_25",
                     "sources": ["live_raw", "logo_zoom", "heatmap"]},
    "Analyse Full": {"layout": "4_2x2",
                     "sources": ["live_raw","aligned","reference","differential"]},
    "Monitoring":   {"layout": "1",
                     "sources": ["live_raw"]},
}
```

### GridCell — Right-Click Menu

```python
class GridCell(QWidget):
    """
    Une cellule du grid.
    Header : [source name] + [🔍 ⛶ 📸] tools
    Body   : ZoomableGridView
    """

    ZOOM_LEVELS = [0.5, 1.0, 2.0, 4.0, 6.0]

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        # Sources
        src_menu = menu.addMenu("📺 Source")
        for src in GridSource:
            act = src_menu.addAction(src.value[1])
            act.setCheckable(True)
            act.setChecked(src.value[0] == self._source)
            act.triggered.connect(
                lambda _, s=src.value[0]: self.set_source(s))

        menu.addSeparator()

        # Zoom
        zoom_menu = menu.addMenu("🔍 Zoom")
        for z in self.ZOOM_LEVELS:
            act = zoom_menu.addAction(f"×{z}")
            act.triggered.connect(lambda _, z=z: self._view.set_zoom(z))
        zoom_menu.addSeparator()
        zoom_menu.addAction("🔄 Reset", self._view.reset_zoom)

        menu.addSeparator()
        menu.addAction("⛶ Plein écran", self._fullscreen)
        menu.addAction("📸 Capture PNG", self._capture)
        menu.addAction("📋 Copier",      self._copy_clipboard)
        menu.addSeparator()
        menu.addAction("🔄 Reset position", self._view.reset_pan)

        menu.exec(event.globalPos())
```

### FlexibleGridView

```python
class FlexibleGridView(QWidget):
    """
    Container des GridCells.
    Utilise QSplitter pour proportions libres.
    Sauvegarde splitter sizes dans ui_prefs.yaml (GR-V8-6).
    """

    def set_grid_count(self, n: int) -> None:
        """n ∈ {1, 2, 3, 4}. Recrée les splitters."""
        assert 1 <= n <= 4, "Max 4 grids (RPi5 performance)"

    def apply_preset(self, preset_name: str) -> None:
        """Charge layout + sources depuis PRESETS dict."""

    def apply_layout(self, layout_name: str) -> None:
        """Applique layout sans changer les sources."""

    def save_layout(self) -> None:
        """Sauvegarde splitter sizes dans ui_prefs.yaml."""

    def load_layout(self) -> None:
        """Restaure depuis ui_prefs.yaml."""

    def on_result(self, result: FinalResult) -> None:
        """
        NOK → auto-zoom ×4 sur la cell "logo_zoom" si présente.
        OK  → reset zoom sur toutes les cells.
        """

    def update_frame(self, frame: np.ndarray,
                     metadata: dict) -> None:
        """Distribue la frame à chaque GridCell selon sa source."""
```

### SourceRenderer

```python
class SourceRenderer:
    """Convertit frame + metadata → QPixmap selon source."""

    @staticmethod
    def render(source: str, frame: np.ndarray,
               metadata: dict) -> QPixmap:
        match source:
            case "live_raw":
                return array_to_pixmap(frame)
            case "aligned":
                return array_to_pixmap(
                    metadata.get("aligned_frame", frame))
            case "logo_zoom":
                return SourceRenderer._render_logo_zoom(
                    frame, metadata)
            case "differential":
                ref = metadata.get("reference_frame")
                if ref is None:
                    return array_to_pixmap(frame)
                diff = cv2.absdiff(frame, ref)
                diff_colored = cv2.applyColorMap(
                    diff, cv2.COLORMAP_HOT)
                return array_to_pixmap(diff_colored)
            case "reference":
                return array_to_pixmap(
                    metadata.get("reference_frame", frame))
            case "roi_overlay":
                return SourceRenderer._render_roi(
                    frame, metadata)
            case "heatmap":
                scores = metadata.get("anomaly_scores")
                if scores is None:
                    return array_to_pixmap(frame)
                hm = cv2.applyColorMap(
                    (scores * 255).astype(np.uint8),
                    cv2.COLORMAP_JET)
                return array_to_pixmap(
                    cv2.addWeighted(frame, 0.5, hm, 0.5, 0))
            case "caliper":
                return SourceRenderer._render_caliper(
                    frame, metadata)
```

### Gate G-S29-v9

```bash
pytest tests/ui/test_flexible_grid_v9.py -v

# - set_grid_count(5) → AssertionError (max 4)
# - set_grid_count(1) → 1 GridCell, full width
# - set_grid_count(4) → 4 GridCells 2x2
# - apply_preset("Analyse Full") → 4 grids, sources correctes
# - Right-click → menu Source affiché, 8 sources listées
# - Source change "roi_overlay" → SourceRenderer appelé
# - auto-zoom NOK : cell logo_zoom → zoom=4.0
# - Splitter drag → sizes sauvegardées ui_prefs.yaml
# - Rechargement → sizes restaurées
# - Capture PNG → fichier dans data/snapshots/
```

---

# ════════════════════════════════════════════════════════════════
# S30-v9 — ShortcutManager Configurable RÉÉCRIT
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : Raccourcis clavier configurables par l'utilisateur
⏱  Durée    : 1.5 jours
🔄 Statut   : REMPLACEMENT de S30 v8 (raccourcis fixes → configurables)
```

## Spec S30-v9

### ShortcutManager

```python
# ui/shortcut_manager.py

@dataclass
class ShortcutDef:
    shortcut_id  : str
    label        : str
    default_key  : str          # "F5" | "Ctrl+1" | "Escape"
    current_key  : str          # peut différer du défaut
    callback_name: str          # méthode dans MainWindow
    category     : str          # "Inspection" | "Navigation" | "Grids"

class ShortcutManager(QObject):
    """
    Centralise TOUS les raccourcis.
    GR-V9-4 : tous configurables via SettingsTab → Raccourcis.
    Sauvegardés dans config/ui_prefs.yaml.
    """

    DEFAULTS: list[ShortcutDef] = [
        # Inspection
        ShortcutDef("start",    "Démarrer inspection",    "F5",  "F5",  "_start",    "Inspection"),
        ShortcutDef("stop",     "Arrêter inspection",     "F6",  "F6",  "_stop",     "Inspection"),
        ShortcutDef("val_ok",   "REVIEW → Valider OK",    "F7",  "F7",  "_val_ok",   "Inspection"),
        ShortcutDef("val_nok",  "REVIEW → Rejeter NOK",   "F8",  "F8",  "_val_nok",  "Inspection"),
        # Navigation
        ShortcutDef("insp_mode","Mode Inspection",        "F11", "F11", "_insp_mode","Navigation"),
        ShortcutDef("exit_insp","Quitter inspection",     "Escape","Escape","_exit_insp","Navigation"),
        ShortcutDef("help",     "Aide / raccourcis",      "F1",  "F1",  "_help",     "Navigation"),
        ShortcutDef("login",    "Changer opérateur",      "Ctrl+L","Ctrl+L","_login","Navigation"),
        # Grids
        ShortcutDef("grid_1",   "1 Grid",                 "Ctrl+1","Ctrl+1","_grid_1","Grids"),
        ShortcutDef("grid_2",   "2 Grids",                "Ctrl+2","Ctrl+2","_grid_2","Grids"),
        ShortcutDef("grid_3",   "3 Grids",                "Ctrl+3","Ctrl+3","_grid_3","Grids"),
        ShortcutDef("grid_4",   "4 Grids",                "Ctrl+4","Ctrl+4","_grid_4","Grids"),
        # Capture
        ShortcutDef("capture",  "Capture grid actif",     "PrintScreen","PrintScreen","_capture","Capture"),
    ]

    def install_all(self, parent: QWidget) -> None:
        """Installe tous les QShortcut sur parent."""
        for sdef in self._shortcuts.values():
            qs = QShortcut(QKeySequence(sdef.current_key), parent)
            qs.activated.connect(
                lambda s=sdef: self._dispatch(s.callback_name))
            self._qshortcuts[sdef.shortcut_id] = qs

    def reassign(self, shortcut_id: str,
                 new_key: str) -> bool:
        """
        Vérifie conflit, réassigne, sauvegarde.
        Retourne False si touche déjà utilisée.
        Bloque : Ctrl+C, Ctrl+V, Ctrl+X, Alt+F4 (touches système).
        """
        BLOCKED = {"Ctrl+C","Ctrl+V","Ctrl+X","Ctrl+Z","Alt+F4"}
        if new_key in BLOCKED:
            return False
        for s in self._shortcuts.values():
            if s.shortcut_id != shortcut_id and \
               s.current_key == new_key:
                return False  # conflit
        self._shortcuts[shortcut_id].current_key = new_key
        self._reinstall(shortcut_id)
        self._save()
        return True

    def reset_to_defaults(self) -> None:
        """Réinitialise tous les raccourcis."""

    def get_help_text(self) -> str:
        """Retourne texte formaté pour HelpDialog (F1)."""
```

### Interface de configuration (dans SettingsTab → Raccourcis)

```python
class ShortcutsSettingsWidget(QWidget):
    """
    Tableau éditable des raccourcis.
    Colonnes : Catégorie | Action | Touche actuelle | [Changer]
    """

    def _on_change_clicked(self, shortcut_id: str) -> None:
        """
        Affiche QMessageBox : "Appuyez sur la nouvelle touche..."
        Capture le prochain keyPressEvent
        Appelle ShortcutManager.reassign()
        """
        dialog = KeyCaptureDialog(self)
        if dialog.exec() == QDialog.Accepted:
            new_key = dialog.captured_key
            ok = self._manager.reassign(shortcut_id, new_key)
            if not ok:
                QMessageBox.warning(self, "Conflit",
                    f"La touche {new_key} est déjà assignée "
                    "ou est une touche système.")
            else:
                self._refresh_table()
```

### Intervalle — valeurs fixes

```python
class IntervalleWidget(QWidget):
    """
    Sélecteur d'intervalle : boutons fixes + Personnalisé.
    Intégré dans ControlBar ET SettingsTab → Inspection.
    """
    PRESETS_MS = [1000, 5000, 10000, 20000]
    PRESETS_LBL = ["1s", "5s", "10s", "20s"]

    # Bouton "Personnalisé" → QInputDialog spinbox
    # Min : 100ms, Max : 60000ms (1 min)
    # Sauvegardé dans config.yaml → inspection.interval_ms
```

### Gate G-S30-v9

```bash
pytest tests/ui/test_shortcut_manager.py -v

# - Tous les défauts installés
# - F5 → SystemController.start() appelé
# - Ctrl+1 → FlexibleGridView.set_grid_count(1)
# - reassign("start", "F9") → OK, F9 déclenche start
# - reassign("start", "Ctrl+C") → False (touche système)
# - reassign("start", "F6") → False (conflit avec stop)
# - reset_to_defaults() → F5 restauré
# - Sauvegarde yaml → rechargement → raccourcis persistés
# - get_help_text() → toutes les catégories présentes
```

---

# ════════════════════════════════════════════════════════════════
# S31 — MainWindow v9 NOUVEAU
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : MainWindow v9 — architecture 2 écrans (Navigation + Inspection)
⏱  Durée    : 2 jours
🆕 Statut   : NOUVELLE SESSION
📄 Dépend   : S20-v9, S25-v9, S26-v9, S27-v9, S28-v9, S29-v9, S30-v9
              S32 (ProductsScreen), S33 (OperatorsScreen)
```

## Spec S31

### Architecture 2 écrans

```
MainWindow
├── Écran 1 — Navigation principale (QStackedWidget index=0)
│   ├── Navbar (Tabs : Produits, Opérateurs, Rapports, GPIO, Fleet, Paramètres)
│   │   + bouton Inspection [F11] à droite
│   ├── ControlBar (Start/Stop/Mode/Grids/Preset/Produit actif)
│   ├── Body (QSplitter horizontal)
│   │   ├── TelemetryPanel (draggable)
│   │   └── QStackedWidget (contenu selon tab active)
│   │       ├── ProductsScreen      (S32)
│   │       ├── OperatorsScreen     (S33)
│   │       ├── ReportsScreen       (S19-A)
│   │       ├── GPIODashboardScreen (S24-B)
│   │       ├── FleetScreen         (S_FLEET-A)
│   │       └── SettingsTab         (S25-v9, S30-v9)
│   └── StatusBar (👤 Opérateur + CPU/RAM/TEMP/FPS/UP)
│
└── Écran 2 — Inspection plein écran (QStackedWidget index=1)
    ├── InspectionTopbar (Produit + État + NOK + Controls)
    ├── Body (TelemetryPanel + FlexibleGridView)
    └── StatusBar compact (👤 + CPU/TEMP/FPS + "Esc")
```

### MainWindow

```python
class MainWindow(QMainWindow):

    def __init__(self, config: Config): ...

    def _build_ui(self) -> None:
        """
        QStackedWidget central avec 2 pages :
          index 0 : NavigationWidget
          index 1 : InspectionWidget
        """

    def _enter_inspection_mode(self) -> None:
        """
        GR-V9-1 : Basculer vers écran 2 (inspection).
        Shortcut : F11 (configurable via ShortcutManager).
        Sauvegarde état Navbar avant switch.
        """
        self._stack.setCurrentIndex(1)

    def _exit_inspection_mode(self) -> None:
        """
        Retour vers écran 1.
        Shortcut : Escape (configurable).
        Restaure état Navbar.
        """
        self._stack.setCurrentIndex(0)

    def _on_tab_changed(self, tab_name: str) -> None:
        """
        Bascule le contenu central selon l'onglet.
        Vérifie permissions :
          OperatorsScreen → ADMIN seulement
          SettingsTab     → ADMIN seulement
        """
        perm_map = {
            "operators": "operator.edit",
            "settings":  "settings.edit",
        }
        if tab_name in perm_map:
            try:
                self._system_controller.check_permission(
                    perm_map[tab_name])
            except PermissionError:
                QMessageBox.warning(self, "Accès refusé",
                    "Votre rôle ne permet pas d'accéder "
                    "à cette section.")
                return

        self._content_stack.setCurrentWidget(
            self._screens[tab_name])

    def _on_login_success(self, operator: Operator) -> None:
        """
        Met à jour StatusBar avec nom + rôle opérateur.
        Notifie SystemController du changement d'opérateur.
        Rafraîchit permissions (hide/show certains tabs).
        """
        self._system_controller.set_operator(operator)
        self._statusbar.set_operator(operator)
        self._refresh_tab_visibility(operator.role)

    def _refresh_tab_visibility(self,
                                  role: OperatorRole) -> None:
        """
        ADMIN   → tous les onglets visibles
        OPERATOR → Opérateurs + Paramètres cachés
        VIEWER   → Opérateurs + Paramètres + GPIO cachés
        """
```

### NavigationBar

```python
class NavigationBar(QTabBar):
    """
    Tabs horizontaux NORD (GR-V9-8) :
    [📦 Produits] [👥 Opérateurs] [📊 Rapports]
    [📡 GPIO] [🚀 Fleet] [⚙ Paramètres]
                              [🔍 Inspection F11]→ droite
    """
    tabActivated = pyqtSignal(str)   # tab_name

    # setTabPosition(QTabWidget.TabPosition.North) — GR-V9-8
```

### StatusBar

```python
class MainStatusBar(QStatusBar):
    """
    Affichage permanent en bas :
    👤 Ahmed Ben Ali [OPERATOR] | CPU 62% | RAM 3.2GB |
    TEMP 58°C | DISK 45GB | FPS 28 | UP 4h 12m | v9.0.0
    """
    def set_operator(self, op: Operator) -> None: ...
    def update_system(self, metrics: dict) -> None: ...
```

### Gate G-S31

```bash
pytest tests/ui/test_main_window_v9.py -v

# - F11 → écran Inspection (QStackedWidget index=1)
# - Escape → retour Navigation (index=0)
# - Tab "Opérateurs" avec OPERATOR → accès refusé + message
# - Tab "Opérateurs" avec ADMIN → OperatorsScreen affiché
# - Login → StatusBar mis à jour avec nom + rôle
# - Refresh tabs : OPERATOR → tabs Opérateurs + Paramètres absents
# - theme appliqué correctement (GR-V9-2)
# - Tabs en position North (GR-V9-8)
# - StatusBar : CPU/RAM/TEMP mis à jour toutes les 5s

python3 main.py --check
# → ✅ ALL SYSTEMS GO
```

---

# ════════════════════════════════════════════════════════════════
# S32 — Products Management Screen NOUVEAU
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : Page gestion produits — CRUD complet
⏱  Durée    : 2 jours
🆕 Statut   : NOUVELLE SESSION
📄 Dépend   : S21-v9 (Wizard), S26-v9 (permissions)
```

## Spec S32

### Architecture

```
ui/screens/products_screen.py     ← NOUVEAU
ui/components/product_card.py     ← NOUVEAU
core/product_manager.py           ← NOUVEAU (CRUD produits)
```

### ProductsScreen

```python
class ProductsScreen(QWidget):
    """
    Page principale gestion produits.
    Accessible via Tab "📦 Produits".
    """
    layout :
      ┌─ Header ─────────────────────────────────────────────┐
      │ [+ Nouveau Produit]  [🔍 Rechercher...]  [Filtrer ▼] │
      ├─ Liste (QScrollArea + QVBoxLayout) ──────────────────┤
      │  ProductCard × N (triés par: actif en premier)       │
      └──────────────────────────────────────────────────────┘

    def _on_add(self) -> None:
        """Ouvre ProductDefinitionWizard (S21-v9)"""
        wizard = ProductDefinitionWizard(self._controller)
        wizard.productCreated.connect(self._on_product_created)
        wizard.exec()

    def _on_edit(self, product_id: str) -> None:
        """
        Ouvre Wizard en mode édition (chargé avec données existantes).
        INTERDIT si produit actif + RUNNING (GR-V9-6).
        """
        if self._controller.is_running() and \
           product_id == self._controller.active_product_id:
            QMessageBox.warning(self, "Interdit",
                "Impossible de modifier le produit actif "
                "pendant une inspection.")
            return
        wizard = ProductDefinitionWizard(
            self._controller, product_id=product_id)
        wizard.exec()

    def _on_delete(self, product_id: str) -> None:
        """
        Confirmation → ProductManager.delete().
        GR-V9-6 : INTERDIT si RUNNING + produit actif.
        Supprime : config.json + models + logos + calibration.
        """

    def _on_duplicate(self, product_id: str) -> None:
        """
        Copie produit avec nouvel ID + nom "Copie de X".
        Copie : config, modèles, logos, calibration.
        NE copie PAS : historique inspections.
        """

    def _on_activate(self, product_id: str) -> None:
        """
        Rend ce produit actif pour la prochaine inspection.
        SystemController.set_active_product(product_id).
        Un seul produit actif à la fois.
        """

    def _on_export(self, product_id: str) -> None:
        """Délègue à FleetManager.export_package() (S_FLEET-A)"""
```

### ProductCard

```python
class ProductCard(QFrame):
    """
    Carte d'affichage d'un produit.
    """
    editRequested      = pyqtSignal(str)
    deleteRequested    = pyqtSignal(str)
    duplicateRequested = pyqtSignal(str)
    activateRequested  = pyqtSignal(str)
    exportRequested    = pyqtSignal(str)

    layout :
      ┌──────────────────────────────────────────────────────┐
      │  🪞 Tapis P208 — Lion              [● Actif]        │
      │  ID: TAPIS-208  |  v3.1  |  800×1000mm  |  2 logos  │
      │  Inspections: 1,847  |  OK: 97.9%  |  NOK: 2.1%    │
      │  Modèles: YOLO v3 · Color v2 · Surface v1           │
      │  Dernière inspection: il y a 3 min                  │
      │  [✏ Modifier] [📋 Dupliquer] [📤 Export] [🗑 Suppr] │
      └──────────────────────────────────────────────────────┘

    # Produit actif → bordure accent_primary
    # Produit inactif → opacité 0.7
```

### ProductManager (CRUD)

```python
class ProductManager:
    """
    CRUD produits. Tout passe par SystemController (GR-03).
    """

    def list_all(self) -> list[ProductSummary]: ...

    def get(self, product_id: str) -> ProductDefinition: ...

    def delete(self, product_id: str) -> None:
        """
        Supprime :
          products/{id}/  (config + models + logos + calibration)
          DB : inspections liées CONSERVÉES (audit trail)
        GR-V9-6 : INTERDIT si RUNNING et produit actif.
        """

    def duplicate(self, source_id: str,
                  new_name: str) -> str:
        """Retourne le nouvel product_id."""

    def get_stats(self, product_id: str) -> dict:
        """Retourne depuis DB : total, ok, nok, taux, last_date"""
```

### Gate G-S32

```bash
pytest tests/ui/test_products_screen.py -v

# - ProductsScreen : liste chargée depuis DB
# - Bouton "+ Nouveau" → Wizard ouvert
# - Carte produit : stats affichées (total/ok/nok)
# - "Modifier" + RUNNING + actif → message d'erreur
# - "Supprimer" → confirmation → produit retiré de la liste
# - "Dupliquer" → nouveau produit "Copie de..." dans liste
# - "Activer" → carte marquée "● Actif", ancienne démarquée
# - ProductManager.delete() : fichiers supprimés
# - ProductManager.delete() : inspections DB conservées (audit)
```

---

# ════════════════════════════════════════════════════════════════
# S33 — Operators Management Screen NOUVEAU
# ════════════════════════════════════════════════════════════════

```
📋 Objectif : Page gestion opérateurs — CRUD complet avec stats
⏱  Durée    : 2 jours
🆕 Statut   : NOUVELLE SESSION
📄 Dépend   : S26-v9, S27-v9, S31
```

## Spec S33

### Architecture

```
ui/screens/operators_screen.py est défini en S27-v9.
Cette session complète avec :
  ui/components/operator_stats_widget.py  ← graphiques stats
  ui/screens/operator_form_dialog.py      ← dialog ajout/édition
```

### OperatorFormDialog

```python
class OperatorFormDialog(QDialog):
    """
    Dialog création/édition opérateur.
    Mode création : tous les champs vides.
    Mode édition  : champs pré-remplis (PIN masqué).
    """
    operatorSaved = pyqtSignal(object)   # Operator

    layout :
      ┌─────────────────────────────────────────────────┐
      │  Nom complet   : [_______________________]      │
      │  ID            : [OP-___] (auto / modifiable)   │
      │  Rôle          : [ADMIN ▼][OPERATOR ▼][VIEWER ▼]│
      │  ─────────────────────────────────────────────  │
      │  PIN (4-6 chiffres) : [____]                    │
      │  Confirmer PIN      : [____]                    │
      │  (mode édition : laisser vide = garder l'actuel)│
      │  ─────────────────────────────────────────────  │
      │  Actif         : [☑]                            │
      │  ─────────────────────────────────────────────  │
      │  [💾 Enregistrer]              [✖ Annuler]      │
      └─────────────────────────────────────────────────┘

    Validation :
      Nom non vide
      PIN = 4 à 6 chiffres uniquement
      PIN = confirmation PIN
      En création : PIN obligatoire
      En édition  : PIN optionnel (vide = inchangé)
```

### OperatorStatsWidget

```python
class OperatorStatsWidget(QWidget):
    """
    Affiche les statistiques d'un opérateur.
    Visible dans la carte et dans le dialog détail.
    """
    layout :
      Inspections: 1,247  OK: 96.2%  NOK: 3.8%
      Produit le + inspecté: Tapis P208
      Dernière session: aujourd'hui 08:42 → 12:15 (3h33)
      Taux moyen sur 30j : [barre verte 96.2%]
```

### Règles sécurité opérateurs

```python
# Règles métier appliquées dans OperatorManager :

# 1. Impossible de supprimer le dernier ADMIN
def delete(self, operator_id: str) -> None:
    op = self.get(operator_id)
    if op.role == OperatorRole.ADMIN:
        admins = [o for o in self.list_all()
                  if o.role == OperatorRole.ADMIN and o.active]
        if len(admins) <= 1:
            raise OperatorError(
                "Impossible de supprimer le dernier administrateur.")
    super().delete(operator_id)

# 2. Impossible de désactiver l'opérateur connecté
def update(self, operator_id: str, active: bool = None, ...) -> Operator:
    if active == False and \
       operator_id == self._current_operator_id:
        raise OperatorError(
            "Impossible de désactiver l'opérateur actuellement connecté.")
```

### Gate G-S33

```bash
pytest tests/ui/test_operator_form.py -v

# - Formulaire : PIN < 4 chiffres → validation bloquante
# - Formulaire : PIN ≠ confirmation → validation bloquante
# - Formulaire : champs vides → validation bloquante
# - Création : create() appelé → opérateur dans liste
# - Édition PIN vide : pin_hash inchangé
# - Édition PIN renseigné : change_pin() appelé
# - Delete dernier ADMIN → OperatorError + message
# - Désactiver opérateur connecté → OperatorError + message
# - Stats : total/ok/nok/taux affichés depuis operator_stats DB
```

---

# ════════════════════════════════════════════════════════════════
# SESSIONS FLEET (INCHANGÉES)
# ════════════════════════════════════════════════════════════════

```
Ces sessions sont identiques à IVS_SESSIONS_v7_COMPLETE.md.

  S_FLEET-A  Export Package + Import Réseau
  S_FLEET-B  Import via USB (auto-detect + validate)
  S_FLEET-C  RÉSERVÉ — Master Unit (non implémenté)
```

---

# ════════════════════════════════════════════════════════════════
# Plan d'exécution v9.0
# ════════════════════════════════════════════════════════════════

```
PHASE 1 — Core (inchangé v7)
  S00-A → S19-A  (exécuter dans ordre)

PHASE 2 — Écrans réécrit (AVANT les nouveaux)
  S22-A → S24-B  (inchangé v7)

PHASE 3 — UI Fondation v9
  S25-v9  (Theme FIRST — GR-V9-2)
      ↓
  S26-v9  (Operators core)
      ↓
  S28-v9  (TelemetryPanel)
      ↓
  S29-v9  (FlexibleGridView)
      ↓
  S30-v9  (ShortcutManager)

PHASE 4 — Écrans principaux
  S20-v9  (InspectionScreen — utilise S28+S29+S30)
      ↓
  S21-v9  (Wizard Produit — utilise S22-B)
      ↓
  S27-v9  (Operators UI — utilise S26)
      ↓
  S31     (MainWindow v9 — utilise TOUT)

PHASE 5 — Pages CRUD
  S32     (Products Screen)
      ↓
  S33     (Operators Screen)

PHASE 6 — Fleet (inchangé v7)
  S_FLEET-A → S_FLEET-B
```

---

# ════════════════════════════════════════════════════════════════
# Validation finale v9.0
# ════════════════════════════════════════════════════════════════

```bash
# ── Après chaque session ──
pytest tests/ -x
/gate

# ── Après toutes les sessions ──
pytest tests/ -v --cov=ui --cov=core

# ── Vérifications v9 spécifiques ──

# GR-V9-1 : 2 écrans séparés
grep -n "QStackedWidget" ui/main_window.py
# → doit avoir 2 pages (index 0 et 1)

# GR-V9-2 : Theme avant show()
python3 -c "
import ast, sys
tree = ast.parse(open('main.py').read())
# Vérifier que theme.apply() précède window.show()
"

# GR-V9-5 : Pas de logo sans image
python3 -c "
from core.models import LogoDefinition
# Vérifier que reference_image est vérifiée dans to_logo_definition()
import subprocess
r = subprocess.run(['grep', '-n', 'reference_image', 'ui/components/logo_form_widget.py'],
                   capture_output=True, text=True)
assert 'None' not in r.stdout or 'GR-V9-5' in r.stdout
print('✅ GR-V9-5 respecté')
"

# GR-V9-7 : Aucun PIN plain text en log
grep -rn "pin\|PIN" ts2i_ivs/ --include="*.py" | \
  grep -v "pin_hash\|bcrypt\|#\|test_" | \
  grep "log\|print\|str(pin)"
# → Doit être vide

# GR-V9-8 : Tabs en North
grep -rn "setTabPosition" ui/ --include="*.py"
# → Aucun West/East/South

# Anti-pattern QLabel pour grids
grep -rn "QLabel" ui/screens/inspection_screen.py
# → Doit être vide

# Lancer l'application
python3 main.py --check
# → ✅ ALL SYSTEMS GO

python3 main.py
# → Vérification visuelle : thème appliqué, tabs horizontaux,
#   2 écrans (Nav + Inspection F11), panels draggables
```

---

## Récapitulatif des fichiers nouveaux v9.0

```
NOUVEAUX :
  core/operators/operator_manager.py
  core/operators/permissions.py
  core/product_manager.py
  ui/main_window.py                         (RÉÉCRITURE)
  ui/screens/inspection_screen.py           (RÉÉCRITURE)
  ui/screens/product_definition_wizard.py   (RÉÉCRITURE)
  ui/screens/products_screen.py
  ui/screens/operators_screen.py
  ui/screens/login_dialog.py
  ui/screens/operator_form_dialog.py
  ui/components/telemetry_panel.py
  ui/components/telemetry_section.py
  ui/components/logo_form_widget.py
  ui/components/tapis_form_widget.py
  ui/components/logo_image_picker.py
  ui/components/product_card.py
  ui/components/operator_card.py
  ui/components/operator_stats_widget.py
  ui/components/flexible_grid_view.py       (RÉÉCRITURE)
  ui/components/grid_cell.py
  ui/components/source_renderer.py
  ui/shortcut_manager.py                    (RÉÉCRITURE)
  ui/theme/presets/light.py
  ui/theme/presets/dark.py
  config/ui_prefs.yaml                      (généré au runtime)

SUPPRIMÉS / REMPLACÉS :
  ui/screens/product_creation_screen.py     → product_definition_wizard.py
  ui/theme/presets/cognex.py                → light.py + dark.py
  ui/theme/presets/keyence.py               → light.py + dark.py
  ui/theme/presets/halcon.py                → light.py + dark.py
```

---

*TS2I IVS v9.0 — Sessions de Développement Complètes*
*44 sessions · Rule-Governed · 2 Thèmes · Architecture 2 écrans*
*Tous les bugs v8 corrigés · CRUD Products + Operators · Grid flexible*
