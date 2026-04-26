# IVS_SESSIONS_v8.md
# TS2I IVS v8.0 — UI Overhaul & Industrial-Grade Experience
# Extension v7.0 → v8.0 (UI uniquement — core inchangé)

---

## Vue d'ensemble v8.0

```
v7.0 statut : 35 sessions complètes (S00 → S_FLEET-B)
v8.0 ajoute : 6 nouvelles sessions UI/UX

Aucune modification du core, pipeline, observers, rule engine.
Tout est strictement additif et corrige les manques visuels.
```

---

## Sessions v8.0

```
S25 — Theme System (3 thèmes : Cognex / Keyence / Halcon)
S26 — Operators CRUD (core + DB + API)
S27 — Operators UI (Login + Settings management)
S28 — Right Telemetry Panel (4 sections live)
S29 — Flexible Grid Layout (1/2/3/4/6 grids + 4 presets + custom)
S30 — Fullscreen Mode + Global Shortcuts
```

---

## Règles strictes v8.0

```
GR-V8-1 : ZÉRO modification du core/, pipeline/, observers/, rule_engine/
GR-V8-2 : Tous les nouveaux écrans héritent du thème global (pas de styles inline)
GR-V8-3 : Toutes les actions UI passent par SystemController (GR-03)
GR-V8-4 : Operators stockés en DB SQLite + bcrypt pour PIN (jamais plain text)
GR-V8-5 : Themes sélectionnables à chaud sans redémarrage
GR-V8-6 : Layouts sauvegardés par opérateur dans config/user_prefs.yaml
GR-V8-7 : Aucune session v8 ne casse une session v7 (pytest tests/ doit rester vert)
```

---

# ════════════════════════════════════════════════════════
# S25 — Theme System (3 thèmes industriels)
# ════════════════════════════════════════════════════════

```
📋 Objectif : Système de thèmes pluggable avec 3 thèmes professionnels
⏱  Durée    : 2 jours
🎯 Priorité : HAUTE (résout problème "noir sur noir")
```

## Spec S25

### Architecture

```
ui/theme/
├── __init__.py
├── theme_manager.py      ← gestionnaire central
├── colors.py             ← palettes par thème
├── styles.py             ← générateur QSS depuis palette
└── presets/
    ├── cognex.py         ← thème Cognex-like (sombre + cyan)
    ├── keyence.py        ← thème Keyence-like (sombre + bleu doux)
    └── halcon.py         ← thème Halcon-like (technique gris)
```

### ThemeManager (singleton)

```python
class ThemeManager:
    """
    Gestionnaire de thème central.
    Singleton chargé au démarrage. Émet themeChanged(name) à chaque switch.
    """
    THEMES = {"cognex": CognexPalette,
              "keyence": KeyencePalette,
              "halcon": HalconPalette}

    def apply(self, theme_name: str) -> None:
        """Applique le thème à l'application QApplication.instance()."""

    def current_theme(self) -> str:
        """Retourne le nom du thème actuellement appliqué."""

    def available_themes(self) -> list[str]:
        """Liste des thèmes disponibles."""

    # Signal Qt
    themeChanged = pyqtSignal(str)
```

### Palette structure

```python
@dataclass(frozen=True)
class ThemePalette:
    name: str

    # Backgrounds
    bg_primary:    str   # fenêtre principale
    bg_secondary:  str   # panels, sidebars
    bg_tertiary:   str   # inputs, cells
    bg_grid:       str   # fond grilles caméra

    # Text
    text_primary:    str
    text_secondary:  str
    text_muted:      str
    text_disabled:   str

    # Semantic
    success:  str   # verdict OK
    warning:  str   # MAJOR
    danger:   str   # CRITICAL
    review:   str   # REVIEW
    info:     str

    # Accents
    accent_primary:    str
    accent_secondary:  str

    # Borders
    border_subtle:  str
    border_default: str
    border_strong:  str

    # Effects
    shadow:    str
    glow:      str   # pour highlights industriels
```

### Cognex-style palette

```
name           = "cognex"
bg_primary     = "#0A0E1A"   # presque noir
bg_secondary   = "#0F1729"
bg_tertiary    = "#1A2332"
bg_grid        = "#020617"

text_primary   = "#F8FAFC"
text_secondary = "#94A3B8"
text_muted     = "#64748B"

success        = "#10B981"   # vert électrique
warning        = "#F59E0B"
danger         = "#EF4444"
review         = "#A855F7"

accent_primary   = "#06B6D4"   # cyan Cognex signature
accent_secondary = "#0EA5E9"

border_subtle  = "#1E293B"
border_default = "#334155"
border_strong  = "#475569"

shadow = "rgba(0,0,0,0.5)"
glow   = "0 0 8px rgba(6,182,212,0.4)"   # cyan glow
```

### Keyence-style palette

```
name           = "keyence"
bg_primary     = "#1A1F2E"
bg_secondary   = "#252A3A"
bg_tertiary    = "#2F3548"

text_primary   = "#FFFFFF"
text_secondary = "#B0B8C5"

success        = "#22C55E"
warning        = "#FBBF24"
danger         = "#F43F5E"
review         = "#C084FC"

accent_primary   = "#3B82F6"   # bleu Keyence
accent_secondary = "#60A5FA"

border_default = "#404858"
glow           = "0 0 6px rgba(59,130,246,0.3)"
```

### Halcon-style palette

```
name           = "halcon"
bg_primary     = "#1C1C1C"   # gris technique
bg_secondary   = "#262626"
bg_tertiary    = "#333333"

text_primary   = "#E5E5E5"
text_secondary = "#A3A3A3"

success        = "#16A34A"
warning        = "#CA8A04"
danger         = "#DC2626"
review         = "#9333EA"

accent_primary   = "#737373"   # neutre
accent_secondary = "#A3A3A3"

border_default = "#525252"
glow           = "none"   # pas de glow, style technique
```

### QSS coverage minimum

```
Le QSS généré doit couvrir AU MINIMUM :
  QMainWindow, QWidget
  QPushButton (default + hover + pressed + disabled)
  QPushButton#BtnStart, #BtnStop, #BtnDanger, #BtnPrimary, #BtnSecondary
  QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox
  QGroupBox, QFrame
  QLabel#TitleLabel, #SubtitleLabel, #MutedLabel
  QTableWidget (header, rows, alternate, selected)
  QTabWidget (tabs HORIZONTAL — North uniquement)
  QMenuBar, QMenu, QMenuItem
  QStatusBar
  QToolBar
  QSplitter (handle visible et stylé)
  QScrollBar
  QDialog
  QMessageBox
  QHeaderView
```

### Intégration

```
1. main.py au démarrage :
   from ui.theme import ThemeManager
   theme = ThemeManager.instance()
   theme.apply(config.get("ui.theme", "cognex"))

2. SettingsTab — nouvelle section "Apparence" :
   QComboBox : Cognex / Keyence / Halcon
   Aperçu live : un mini panneau qui montre le thème
   Sauvegarde dans config.yaml → ui.theme

3. Tous les écrans existants ne touchent à RIEN :
   Le thème global s'applique automatiquement.
   Suppression progressive des setStyleSheet inline conflictuels.
```

### Fichiers modifiés (minimal)

```
✏️ main.py                    : 5 lignes (apply theme au boot)
✏️ ui/tabs/settings_tab.py    : ajout section "Apparence" (~40 lignes)
✏️ ui/tabs/settings_tab.py    : setTabPosition(West) → setTabPosition(North)

📁 NOUVEAUX fichiers :
   ui/theme/__init__.py
   ui/theme/theme_manager.py
   ui/theme/colors.py
   ui/theme/styles.py
   ui/theme/presets/cognex.py
   ui/theme/presets/keyence.py
   ui/theme/presets/halcon.py
```

## Gate G-S25

```bash
# Test 1 : import + apply
python3 -c "
from ui.theme import ThemeManager
tm = ThemeManager.instance()
tm.available_themes()  # ['cognex', 'keyence', 'halcon']
"

# Test 2 : QSS généré non vide
python3 -c "
from ui.theme.presets.cognex import CognexPalette
from ui.theme.styles import generate_qss
qss = generate_qss(CognexPalette())
assert len(qss) > 2000, 'QSS trop court'
assert 'QPushButton' in qss
assert 'QTableWidget' in qss
assert 'QTabWidget' in qss
print('✅ QSS valide')
"

# Test 3 : settings tab horizontal
python3 -c "
from PyQt6.QtWidgets import QApplication, QTabWidget
import sys
app = QApplication(sys.argv)
from ui.tabs.settings_tab import SettingsTab
t = SettingsTab()
inner = t.findChild(QTabWidget)
assert inner.tabPosition() == QTabWidget.TabPosition.North, 'Tabs doivent être horizontaux'
print('✅ Tabs horizontaux')
"

# Test 4 : aucun test cassé
pytest tests/ -x --ignore=tests/ai/test_yolo_observer.py
```

---

# ════════════════════════════════════════════════════════
# S26 — Operators CRUD (core + DB)
# ════════════════════════════════════════════════════════

```
📋 Objectif : Système d'opérateurs complet (core + DB + API)
⏱  Durée    : 2 jours
🎯 Priorité : HAUTE (Spec exige TABLE operators)
```

## Spec S26

### Modèle de données

```python
# core/operators.py (remplace les 3 lignes actuelles)

class OperatorRole(Enum):
    OPERATOR    = "operator"      # exécution + validation REVIEW
    SUPERVISOR  = "supervisor"    # + reset NOK, accès SPC
    ADMIN       = "admin"         # + création produits, settings, opérateurs

@dataclass(frozen=True)
class Operator:
    operator_id: str          # UUID4
    username:    str          # login
    full_name:   str
    role:        OperatorRole
    pin_hash:    str          # bcrypt — JAMAIS plain
    active:      bool
    created_at:  datetime
    last_login:  Optional[datetime]
```

### OperatorService (CRUD)

```python
class OperatorService:
    """
    Service CRUD opérateurs. Backed by SQLite.
    GR-V8-4 : pin toujours hashé bcrypt.
    """

    def __init__(self, db_path: str): ...

    # CRUD
    def create(self, username: str, full_name: str,
               role: OperatorRole, pin: str) -> Operator: ...

    def get(self, operator_id: str) -> Optional[Operator]: ...

    def get_by_username(self, username: str) -> Optional[Operator]: ...

    def list(self, active_only: bool = False) -> list[Operator]: ...

    def update(self, operator_id: str, **fields) -> Operator: ...

    def deactivate(self, operator_id: str) -> None: ...

    def delete(self, operator_id: str) -> None: ...   # HARD delete (rare)

    # Auth
    def verify_pin(self, username: str, pin: str) -> Optional[Operator]: ...
    """Retourne Operator si PIN correct + active, sinon None."""

    def change_pin(self, operator_id: str, old_pin: str, new_pin: str) -> bool: ...

    # Stats
    def record_login(self, operator_id: str) -> None: ...
    def record_inspection(self, operator_id: str, product_id: str,
                          verdict: str) -> None: ...
    def get_stats(self, operator_id: str) -> OperatorStats: ...
```

### OperatorStats

```python
@dataclass(frozen=True)
class OperatorStats:
    operator_id:  str
    total:        int
    ok_count:     int
    nok_count:    int
    review_count: int
    last_30d:     int
    products:     list[str]   # produits inspectés
```

### Schéma DB

```sql
-- storage/migrations/002_operators.sql

CREATE TABLE IF NOT EXISTS operators (
    operator_id  TEXT PRIMARY KEY,
    username     TEXT UNIQUE NOT NULL,
    full_name    TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('operator','supervisor','admin')),
    pin_hash     TEXT NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login   TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS operator_stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id  TEXT NOT NULL,
    product_id   TEXT NOT NULL,
    verdict      TEXT NOT NULL,
    timestamp    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES operators(operator_id)
);

CREATE INDEX idx_op_stats_operator ON operator_stats(operator_id);
CREATE INDEX idx_op_stats_timestamp ON operator_stats(timestamp);
```

### Migration auto

```
Au démarrage, vérifier :
  SELECT name FROM sqlite_master WHERE name='operators';

Si absent :
  Exécuter migrations/002_operators.sql
  Créer compte admin par défaut :
    username  = "admin"
    full_name = "Administrator"
    role      = ADMIN
    pin       = "0000" (à changer obligatoirement au 1er login)
    active    = True
  Logger WARNING : "Compte admin par défaut créé, PIN=0000, à changer."
```

### API endpoints (web/api_router.py)

```
POST   /api/v1/auth/login            {username, pin} → {token, operator}
POST   /api/v1/auth/logout
GET    /api/v1/operators             [Operator]
GET    /api/v1/operators/{id}        Operator
POST   /api/v1/operators             {username, full_name, role, pin}
PUT    /api/v1/operators/{id}        {full_name, role, active}
POST   /api/v1/operators/{id}/pin    {old_pin, new_pin}
DELETE /api/v1/operators/{id}        deactivate
GET    /api/v1/operators/{id}/stats  OperatorStats
```

### Dépendance

```
ajouter à requirements_pi.txt :
  bcrypt==4.2.0
```

## Gate G-S26

```bash
pytest tests/unit/test_operators.py -v

# Tests obligatoires :
# - create() : opérateur créé, pin hashé bcrypt
# - verify_pin() : PIN correct → Operator, PIN faux → None
# - verify_pin() avec inactif → None
# - change_pin() : ancien correct → succès, ancien faux → False
# - list(active_only=True) : filtre inactifs
# - admin par défaut créé au premier démarrage
# - record_inspection + get_stats : compteurs corrects
# - migration 002 idempotente (peut être lancée plusieurs fois)
```

---

# ════════════════════════════════════════════════════════
# S27 — Operators UI (Login + Settings)
# ════════════════════════════════════════════════════════

```
📋 Objectif : Interface complète gestion opérateurs
⏱  Durée    : 2 jours
🎯 Priorité : HAUTE
```

## Spec S27

### LoginDialog

```python
# ui/dialogs/login_dialog.py

class LoginDialog(QDialog):
    """
    Dialog de connexion modal au démarrage.
    Bloque l'accès à MainWindow tant qu'aucun opérateur valide.
    """
    def __init__(self, operator_service): ...

    # Layout :
    #   Logo TS2I + nom système
    #   QLineEdit username
    #   QLineEdit pin (echoMode = Password)
    #   QPushButton "Se connecter"
    #   QLabel erreur en rouge
    #   Footer : "v8.0 — Industrial Vision"

    # Comportement :
    #   3 tentatives échouées → blocage 30s
    #   PIN par défaut "0000" pour admin → forcer changement
    #   Émet : loggedIn(operator: Operator)
```

### OperatorsManagementScreen (Settings → Comptes)

```python
# Remplace la section "Comptes" placeholder de SettingsTab

Layout :
  ┌─ Toolbar ────────────────────────────────────────────────┐
  │ [➕ Nouveau] [✏️ Modifier] [🔑 Reset PIN] [⏸ Désactiver] │
  ├─ Filtres ────────────────────────────────────────────────┤
  │ Recherche: [___________]  Rôle: [Tous ▼]  ☑ Actifs only  │
  ├─ Table ──────────────────────────────────────────────────┤
  │ Username │ Nom complet │ Rôle │ Actif │ Dernier login    │
  │ ─────────┼─────────────┼──────┼───────┼─────────────     │
  │ admin    │ Admin       │ ADMIN│  ✅   │ 26/04 10:32      │
  │ op_jean  │ Jean Dupont │ OPER.│  ✅   │ 26/04 09:15      │
  │ ...                                                       │
  ├─ Stats opérateur sélectionné ──────────────────────────  │
  │ Total : 1247  ·  OK : 95%  ·  NOK : 4%  ·  REVIEW : 1%  │
  │ Produits : P208, H, 2008                                 │
  └──────────────────────────────────────────────────────────┘

Permissions :
  - operator   : voit la table, mais boutons CRUD désactivés
  - supervisor : peut reset PIN
  - admin      : tous droits
```

### CreateOperatorDialog

```
Champs :
  Username    [QLineEdit]    requis, unique
  Nom complet [QLineEdit]    requis
  Rôle        [QComboBox]    Operator / Supervisor / Admin
  PIN         [QLineEdit]    4-8 chiffres
  PIN confirm [QLineEdit]    doit matcher

Boutons :
  [Annuler] [Créer]
```

### Permissions globales

```
RoleGuard.check(action: str, operator: Operator) -> bool

Actions définies :
  "create_product"      → admin
  "edit_product"        → admin, supervisor
  "edit_settings"       → admin
  "edit_thresholds"     → admin, supervisor
  "manage_operators"    → admin
  "reset_nok_counter"   → supervisor, admin
  "validate_review"     → operator, supervisor, admin
  "start_inspection"    → operator, supervisor, admin
  "view_spc"            → supervisor, admin
  "export_fleet"        → admin
```

## Gate G-S27

```bash
pytest tests/ui/test_login_dialog.py -v
pytest tests/ui/test_operators_management.py -v

# - Login OK avec pin correct → loggedIn signal émis
# - Login KO 3 fois → bouton désactivé 30s
# - admin créé par défaut → forcer change PIN à 0000
# - operator role → boutons CRUD désactivés
# - admin role → tous boutons actifs
# - RoleGuard.check correct pour chaque combinaison
```

---

# ════════════════════════════════════════════════════════
# S28 — Right Telemetry Panel
# ════════════════════════════════════════════════════════

```
📋 Objectif : Panneau droit avec télémétrie live + corrections
⏱  Durée    : 2 jours
🎯 Priorité : HAUTE
```

## Spec S28

### Architecture

```
ui/components/telemetry_panel.py
ui/components/telemetry_section.py

InspectionScreen layout :
  ┌──────────────────────────────┬──────────────┐
  │                              │              │
  │       Grids configurables    │  Telemetry   │
  │       (S29)                  │  Panel       │
  │                              │  (S28)       │
  │                              │              │
  └──────────────────────────────┴──────────────┘
                                  width: 280px (collapsible)
```

### TelemetryPanel

```python
class TelemetryPanel(QFrame):
    """
    Panneau droit fixe (280px) ou collapsable.
    GR-03 : alimenté UNIQUEMENT par signaux UIBridge.
    """

    def __init__(self, ui_bridge: UIBridge): ...

    # 4 sections empilées
    self._section_telemetry  = LiveTelemetrySection()
    self._section_inspection = InspectionResultSection()
    self._section_stats      = SessionStatsSection()
    self._section_corrections = CorrectionsSection()

    # Bouton toggle pour cacher/montrer
    self._btn_collapse = QPushButton("▶")
```

### Section 1 — Live Telemetry

```
📊 LIVE TELEMETRY
━━━━━━━━━━━━━━━━━━━━━

  💡 Luminosité    187 / 240
     ████████████████░░░░  good

  🎚 Contraste     0.72
     ██████████████░░░░░░  good

  🔇 Bruit         4.2%
     ███░░░░░░░░░░░░░░░░░  low

  🔪 Netteté       0.89
     █████████████████░░░  excellent

  📐 FPS caméra    28.3 / 30
```

Source : signaux UIBridge.frame_telemetry (à créer)
émis par S2_Preprocessor à chaque frame

### Section 2 — Inspection Result

```
🎯 INSPECTION
━━━━━━━━━━━━━━━━━━━━━

  Verdict   : ✅ OK
  Tier      : —
  Severity  : ACCEPTABLE
  Latence   : 142 ms

  Tier scores :
    🔴 CRITICAL : 0.94
    🟠 MAJOR    : 0.88
    🟡 MINOR    : 0.91
```

Source : UIBridge.inspection_result

### Section 3 — Session Stats

```
📈 SESSION STATS
━━━━━━━━━━━━━━━━━━━━━

  Total       1,247
  OK          1,189   95.3% ▓▓▓▓▓▓▓▓▓
  NOK            52    4.2% ▓
  REVIEW          6    0.5% ░

  Cadence  :  18.2 / min
  Uptime   :  2h 34m
  [⟳ Reset]
```

Reset uniquement par supervisor/admin (S27 RoleGuard)

### Section 4 — Corrections

```
⚙️ CORRECTIONS APPLIQUÉES
━━━━━━━━━━━━━━━━━━━━━

  Frame courante :
    🔄 Rotation     : +2.3°
    ↔️  Décalage X   : -4.2 mm
    ↕️  Décalage Y   : +1.1 mm
    💡 Lum. corrigée : +12
    🎨 Balance blanc : auto

  Pipeline :
    ✓ S1 acquisition  (4 ms)
    ✓ S2 préprocesseur (18 ms)
    ✓ S3 alignment   (35 ms)
    ✓ S4 tier orch.  (78 ms)
    ✓ S5 rule engine (3 ms)
    ✓ S8 output      (4 ms)
```

Source : UIBridge.frame_metadata (nouveau signal)
émis par S3_Alignment + S4_TierOrchestrator

### Nouveaux signaux UIBridge

```python
# core/ui_bridge.py — additions

frame_telemetry   = pyqtSignal(dict)   # {luminosity, contrast, noise, sharpness, fps}
frame_metadata    = pyqtSignal(dict)   # {rotation_deg, dx_mm, dy_mm, stage_latencies}
session_stats     = pyqtSignal(dict)   # {total, ok, nok, review, rate_per_min}
session_reset_requested = pyqtSignal(str)  # operator_id
```

## Gate G-S28

```bash
pytest tests/ui/test_telemetry_panel.py -v

# - 4 sections présentes et empilées
# - Mise à jour via signaux UIBridge (pas d'accès direct au pipeline)
# - Reset stats : RoleGuard appelé
# - Collapse/expand fonctionne
# - Width 280px par défaut
```

---

# ════════════════════════════════════════════════════════
# S29 — Flexible Grid Layout
# ════════════════════════════════════════════════════════

```
📋 Objectif : Layout grids flexible avec right-click menu complet
⏱  Durée    : 3 jours
🎯 Priorité : HAUTE (cœur de la demande)
```

## Spec S29

### Architecture

```
ui/components/
├── flexible_grid_view.py     ← QWidget multi-grid configurable
├── grid_cell.py              ← une cellule (image + toolbar + context menu)
└── source_renderer.py        ← rendu selon source choisie
```

### Grid count configurable

```
Settings → Inspection → "Nombre de grilles" :
  1 grid   → plein écran
  2 grids  → 50/50 horizontal (par défaut)
  3 grids  → 50/25/25
  4 grids  → 2×2
  6 grids  → 3×2

Sauvegarde : config.yaml → ui.inspection.grid_count
```

### Layout presets

```
4 presets accessibles via toolbar Inspection :
  [▤] 50/50      (2 grids horizontal)
  [▥] 50/25/25   (3 grids — 1 grand + 2 petits)
  [▦] 33/33/33   (3 grids égaux)
  [▧] 70/30      (2 grids — 1 grand + 1 sidebar)
  [▨] 2×2        (4 grids)

Mode custom (par défaut) : QSplitter draggable par l'opérateur
Sauvegarde des tailles : config/user_prefs.yaml
```

### GridCell — chaque cellule

```python
class GridCell(QWidget):
    """
    Une cellule du grid layout.
    Contient :
      - Header (source name + dropdown)
      - Body (ZoomableGridView)
      - Hover toolbar (zoom, capture, fullscreen)
      - Right-click menu complet
    """

    SOURCES = [
        ("live_raw",      "📷 Live raw camera"),
        ("logo_zoom",     "🔍 Logo zoom"),
        ("aligned",       "📐 Aligned (post-S3)"),
        ("differential",  "🔬 Differential"),
        ("reference",     "📋 Reference image"),
        ("roi_overlay",   "🎯 ROI overlay"),
        ("heatmap",       "🌡 Heatmap anomaly"),
        ("caliper",       "📏 Caliper measurements"),
    ]

    def __init__(self, cell_id: str, ui_bridge: UIBridge): ...

    def set_source(self, source: str) -> None: ...

    def get_source(self) -> str: ...

    # Right-click menu
    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        # Sous-menu Source
        src_menu = menu.addMenu("📺 Source")
        for src_id, src_label in self.SOURCES:
            act = src_menu.addAction(src_label)
            act.setCheckable(True)
            act.setChecked(src_id == self._current_source)
            act.triggered.connect(lambda checked, s=src_id: self.set_source(s))

        menu.addSeparator()
        menu.addAction("🔍+ Zoom in",         self._zoom_in)
        menu.addAction("🔍- Zoom out",        self._zoom_out)
        menu.addAction("🔄 Reset zoom",       self._reset_zoom)
        menu.addSeparator()
        menu.addAction("⛶ Plein écran",      self._fullscreen)
        menu.addAction("📸 Capture (PNG)",    self._capture)
        menu.addAction("📋 Copier",           self._copy_clipboard)

        menu.exec(event.globalPos())
```

### Hover toolbar (overlay)

```
Apparaît en survol, top-right de chaque cellule :
  [📸] [🔍] [⛶]
  capture  zoom  fullscreen
```

### FlexibleGridView (container)

```python
class FlexibleGridView(QWidget):
    """
    Container racine pour les N grids.
    Restructure dynamiquement selon grid_count + preset.
    """

    def __init__(self, ui_bridge: UIBridge, config): ...

    def set_grid_count(self, n: int) -> None:
        """1, 2, 3, 4 ou 6"""

    def apply_preset(self, preset: str) -> None:
        """50_50 | 50_25_25 | 33_33_33 | 70_30 | 2x2 | custom"""

    def save_layout(self, operator_id: str) -> None:
        """Sauvegarde tailles splitters dans user_prefs.yaml"""

    def load_layout(self, operator_id: str) -> None:
        """Restaure layout sauvegardé"""

    def cells(self) -> list[GridCell]:
        """Liste des cellules actuelles"""
```

### SourceRenderer

```python
class SourceRenderer:
    """
    Convertit une frame brute + métadonnées en QPixmap selon la source choisie.
    """

    @staticmethod
    def render(source: str, frame: np.ndarray,
               metadata: dict) -> QPixmap: ...

    # Implementations par source :
    # - live_raw         : frame as-is
    # - logo_zoom        : crop autour du logo + upscale
    # - aligned          : metadata['aligned_frame']
    # - differential     : abs(frame - reference) avec colormap
    # - reference        : metadata['reference_frame']
    # - roi_overlay      : frame + rectangles colorés par tier
    # - heatmap          : colormap sur scores d'anomalie
    # - caliper          : frame + lignes/textes de mesure
```

## Gate G-S29

```bash
pytest tests/ui/test_flexible_grid.py -v

# - Grid count 1, 2, 3, 4, 6 → layout correct
# - Preset apply : tailles correctes
# - Right-click menu : 8 sources affichées
# - Source switch : SourceRenderer appelé avec bon paramètre
# - Save/load layout : persistance fonctionne
# - Capture PNG : fichier créé dans data/snapshots/
```

---

# ════════════════════════════════════════════════════════
# S30 — Fullscreen Mode + Global Shortcuts
# ════════════════════════════════════════════════════════

```
📋 Objectif : Mode plein écran inspection + raccourcis globaux
⏱  Durée    : 1.5 jour
🎯 Priorité : MOYENNE
```

## Spec S30

### Fullscreen Inspection Mode

```
Trigger : F11 ou bouton ⛶ dans toolbar

Comportement :
  - Cache : MenuBar, ToolBar, TabBar, StatusBar
  - Affiche uniquement :
      • TopBar produit (compact)
      • ControlBar (Start/Stop)
      • FlexibleGridView (cœur)
      • TelemetryPanel (collapsible)
      • Bandeau résultat verdict (bottom)
  - Esc : retour au mode normal
  - Indicateur visuel discret en haut-droite : "FULLSCREEN [Esc]"
```

### ShortcutManager

```python
# ui/shortcut_manager.py

class ShortcutManager(QObject):
    """
    Centralise tous les raccourcis clavier de l'application.
    Évite la duplication et simplifie la documentation.
    """

    SHORTCUTS = {
        # Navigation
        "F1":         ("Aide / raccourcis",       "_show_help"),
        "F11":        ("Plein écran",             "_toggle_fullscreen"),
        "Esc":        ("Sortir plein écran",      "_exit_fullscreen"),

        # Inspection
        "F5":         ("Démarrer inspection",     "_start_inspection"),
        "F6":         ("Arrêter inspection",      "_stop_inspection"),
        "F7":         ("Validation REVIEW OK",    "_validate_ok"),
        "F8":         ("Validation REVIEW NOK",   "_validate_nok"),
        "F9":         ("Reset compteur NOK",      "_reset_nok"),

        # Layouts
        "Ctrl+1":     ("Layout 1 grid",           "_layout_1"),
        "Ctrl+2":     ("Layout 2 grids 50/50",    "_layout_2_5050"),
        "Ctrl+3":     ("Layout 3 grids 33/33/33", "_layout_3_eq"),
        "Ctrl+Shift+3": ("Layout 3 grids 50/25/25", "_layout_3_50_25_25"),
        "Ctrl+4":     ("Layout 4 grids 2x2",      "_layout_4"),
        "Ctrl+6":     ("Layout 6 grids 3x2",      "_layout_6"),

        # Outils
        "Ctrl+N":     ("Nouveau produit",         "_new_product"),
        "Ctrl+R":     ("ROI Editor",              "_roi_editor"),
        "Ctrl+P":     ("Paramètres",              "_settings"),
        "Ctrl+L":     ("Login / changer compte",  "_login"),
        "Ctrl+Q":     ("Quitter",                 "_quit"),

        # Capture
        "PrintScreen": ("Capture grid actif",     "_capture_active"),
        "Ctrl+Shift+S": ("Capture toute UI",      "_capture_all"),
    }

    def __init__(self, main_window): ...
    def install_all(self) -> None: ...
    def get_help_text(self) -> str: ...   # pour F1
```

### Help Dialog (F1)

```
Affiche tous les raccourcis groupés par catégorie :

╔════════════════════════════════════════════╗
║  Raccourcis clavier — TS2I IVS v8.0       ║
╠════════════════════════════════════════════╣
║                                            ║
║  📐 NAVIGATION                             ║
║    F1        Aide                          ║
║    F11       Plein écran                   ║
║    Esc       Sortir                        ║
║                                            ║
║  🎯 INSPECTION                             ║
║    F5        Démarrer                      ║
║    F6        Arrêter                       ║
║    F7        REVIEW → OK                   ║
║    F8        REVIEW → NOK                  ║
║                                            ║
║  📺 LAYOUTS                                ║
║    Ctrl+1    1 grid                        ║
║    Ctrl+2    2 grids                       ║
║    ...                                     ║
╚════════════════════════════════════════════╝
```

## Gate G-S30

```bash
pytest tests/ui/test_shortcuts.py -v
pytest tests/ui/test_fullscreen.py -v

# - Tous les raccourcis installés
# - F11 → fullscreen, Esc → exit
# - F5 → SystemController.start_inspection()
# - Ctrl+1...6 → grid count change
# - F1 → help dialog avec tous les raccourcis
```

---

# ════════════════════════════════════════════════════════
# Plan d'exécution v8.0
# ════════════════════════════════════════════════════════

```
Ordre de session OBLIGATOIRE (dépendances) :

1️⃣  S25 (Theme)
        ↓
2️⃣  S26 (Operators core)
        ↓
3️⃣  S27 (Operators UI)  ←── nécessite S25 + S26
        ↓
4️⃣  S28 (Right Panel)   ←── nécessite S25
        ↓
5️⃣  S29 (Flex Grids)    ←── nécessite S25 + S28
        ↓
6️⃣  S30 (Fullscreen)    ←── nécessite S29
```

## Durée totale estimée

```
S25 — 2 jours
S26 — 2 jours
S27 — 2 jours
S28 — 2 jours
S29 — 3 jours
S30 — 1.5 jours
────────────
Total : ~12.5 jours
```

## Validation finale

```bash
# Après chaque session
pytest tests/ -x

# Après les 6 sessions
pytest tests/ -v --cov=ui --cov=core/operators
python3 main.py --check
python3 main.py   # test visuel complet
```

---

*TS2I IVS v8.0 — UI Overhaul Specification*
*6 sessions · Industrial-grade visual identity*
*Theme · Operators · Telemetry · Flexible Grids · Fullscreen*
