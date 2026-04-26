# IVS_SESSIONS_v9_FINAL.md
# TS2I IVS v9.0 — Sessions additionnelles et correctifs
# À exécuter APRÈS complétion totale de IVS_SESSIONS_v7_COMPLETE.md
#
# PRÉREQUIS STRICT : S00-A → S_FLEET-B (v7) toutes complétées + pytest vert
#
# Ordre d'exécution OBLIGATOIRE :
#   S25-v9 → S26-v9 → S28-v9 → S29-v9 → S30-v9
#   → S20-v9 → S21-v9 → S27-v9 → S31 → S32

---

## Bugs identifiés post-v7+v8 (10 bugs confirmés)

```
BUG-01 : Texte noir sur fond noir → ThemeManager non appelé dans main.py
BUG-02 : QTabWidget en position West → doit être North (GR-V9-8)
BUG-03 : InspectionScreen figée → 3 grids QLabel fixes (anti-pattern)
BUG-04 : Wizard produit sans saisie image logo
BUG-05 : Page Produits absente (ProductsScreen non accessible)
BUG-06 : Page Opérateurs absente (OperatorsScreen non intégrée)
BUG-07 : TelemetryPanel créé (v8) mais non intégré dans InspectionScreen
BUG-08 : FlexibleGridView créé (v8) mais non substitué aux 3 grids
BUG-09 : ShortcutManager créé (v8) mais raccourcis non configurables
BUG-10 : LogoDefinition.reference_image jamais renseigné dans wizard
```

## Règles v9.0 (en plus des GR-01→GR-13 v7)

```
GR-V9-1  DEUX ÉCRANS    : Navigation ≠ Inspection (F11/Esc, QStackedWidget)
GR-V9-2  THEME AU BOOT  : ThemeManager.apply() AVANT QMainWindow.show()
GR-V9-3  PANELS ORDER   : Ordre sections telemetry → config/ui_prefs.yaml
GR-V9-4  SHORTCUTS CFG  : Tous raccourcis configurables via ShortcutManager
GR-V9-5  LOGO IMAGE     : LogoDefinition.reference_image JAMAIS None
GR-V9-6  PRODUCT CRUD   : delete/edit FORBIDDEN si RUNNING + produit actif
GR-V9-7  OPERATOR PIN   : bcrypt rounds=12 · jamais plain text · jamais loggué
GR-V9-8  TABS NORTH     : QTabWidget.setTabPosition(North) partout
```

---

# ════════════════════════════════════════════════════════════════
# S25-v9 — THEME SYSTEM CORRIGÉ (BUG-01 + BUG-02)
# EXÉCUTER EN PREMIER — prérequis de toutes les sessions suivantes
# ════════════════════════════════════════════════════════════════

## S25-v9 : Thèmes Light/Dark + Application correcte au démarrage

```
📋 Objectif  : 2 thèmes industriels + correction application au boot
⏱  Durée     : 2 jours
🔄 Action    : RÉÉCRIRE ui/theme/ complet + CORRIGER main.py
🐛 Bugs fixés: BUG-01 (texte noir sur noir), BUG-02 (tabs West)
📄 Règles    : GR-V9-2, GR-V9-8
```

### 🤖 Prompt S25-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md intégralement avant de commencer.

CONTEXTE :
  v8 a créé ui/theme/theme_manager.py avec un seul thème "cognex".
  BUG-01 : main.py n'appelle PAS theme.apply() avant window.show()
           → texte noir sur fond noir (application illisible).
  BUG-02 : Certains QTabWidget utilisent setTabPosition(West).

MISSION — Modifier/créer UNIQUEMENT dans ui/theme/ et main.py.
          NE TOUCHER NI au core/ NI au pipeline/ NI à l'ai/.

════════════════════════════════════════════════════
FICHIER 1 : ui/theme/colors.py  (RÉÉCRIRE COMPLET)
════════════════════════════════════════════════════

from dataclasses import dataclass

@dataclass(frozen=True)
class ThemePalette:
    """
    Palette complète d'un thème UI.
    Tous les champs sont des strings CSS (#RRGGBB ou rgba(...)).
    """
    name: str

    # ── Fonds ──
    bg_primary:    str   # fond principal fenêtre/panels
    bg_secondary:  str   # fond sidebars, headers
    bg_tertiary:   str   # fond toolbars, alternate rows
    bg_grid:       str   # fond zones caméra (toujours sombre pour vision)
    bg_input:      str   # fond QLineEdit, QComboBox
    bg_hover:      str   # élément survolé
    bg_selected:   str   # élément sélectionné

    # ── Textes ──
    text_primary:   str  # texte principal (DOIT contraster avec bg_primary)
    text_secondary: str  # texte secondaire
    text_muted:     str  # labels discrets
    text_disabled:  str  # texte désactivé
    text_on_accent: str  # texte sur fond accent (toujours #ffffff ou #000000)

    # ── États inspection ──
    ok_color:      str   # vert → verdict OK
    nok_color:     str   # rouge → verdict NOK
    review_color:  str   # orange → verdict REVIEW
    warning_color: str   # avertissement système

    # ── Accent ──
    accent:        str   # couleur principale navigation/focus
    accent_hover:  str   # accent au survol

    # ── Bordures ──
    border_light:  str
    border_default:str
    border_strong: str

    # ── Tiers (badges) ──
    tier_critical_bg:  str
    tier_critical_fg:  str
    tier_critical_brd: str
    tier_major_bg:     str
    tier_major_fg:     str
    tier_major_brd:    str
    tier_minor_bg:     str
    tier_minor_fg:     str
    tier_minor_brd:    str

    # ── ResultBand fonds ──
    ok_band_bg:     str
    ok_band_brd:    str
    nok_band_bg:    str
    nok_band_brd:   str
    review_band_bg: str
    review_band_brd:str

════════════════════════════════════════════════════
FICHIER 2 : ui/theme/presets/light.py  (CRÉER)
════════════════════════════════════════════════════

from ui.theme.colors import ThemePalette

LIGHT_PALETTE = ThemePalette(
    name            = "light",
    bg_primary      = "#ffffff",
    bg_secondary    = "#f6f6f6",
    bg_tertiary     = "#eeeeee",
    bg_grid         = "#1a1a1a",     # zone caméra toujours sombre
    bg_input        = "#ffffff",
    bg_hover        = "#e8e8e8",
    bg_selected     = "#ddeeff",
    text_primary    = "#111111",     # ← CRITIQUE : jamais noir sur fond blanc
    text_secondary  = "#444444",
    text_muted      = "#888888",
    text_disabled   = "#bbbbbb",
    text_on_accent  = "#ffffff",
    ok_color        = "#16a34a",
    nok_color       = "#dc2626",
    review_color    = "#d97706",
    warning_color   = "#ea580c",
    accent          = "#1d4ed8",
    accent_hover    = "#1e40af",
    border_light    = "#eeeeee",
    border_default  = "#d0d0d0",
    border_strong   = "#a0a0a0",
    tier_critical_bg   = "#fef2f2",
    tier_critical_fg   = "#b91c1c",
    tier_critical_brd  = "#fca5a5",
    tier_major_bg      = "#fff7ed",
    tier_major_fg      = "#c2410c",
    tier_major_brd     = "#fed7aa",
    tier_minor_bg      = "#eff6ff",
    tier_minor_fg      = "#1d4ed8",
    tier_minor_brd     = "#93c5fd",
    ok_band_bg      = "#f0fdf4",
    ok_band_brd     = "#86efac",
    nok_band_bg     = "#fef2f2",
    nok_band_brd    = "#fca5a5",
    review_band_bg  = "#fffbeb",
    review_band_brd = "#fcd34d",
)

════════════════════════════════════════════════════
FICHIER 3 : ui/theme/presets/dark.py  (CRÉER)
════════════════════════════════════════════════════

from ui.theme.colors import ThemePalette

DARK_PALETTE = ThemePalette(
    name            = "dark",
    bg_primary      = "#0d1117",
    bg_secondary    = "#161b22",
    bg_tertiary     = "#21262d",
    bg_grid         = "#010409",
    bg_input        = "#161b22",
    bg_hover        = "#1f2937",
    bg_selected     = "#1e3a5f",
    text_primary    = "#e6edf3",
    text_secondary  = "#c9d1d9",
    text_muted      = "#8b949e",
    text_disabled   = "#484f58",
    text_on_accent  = "#000000",
    ok_color        = "#4ade80",
    nok_color       = "#f87171",
    review_color    = "#fbbf24",
    warning_color   = "#fb923c",
    accent          = "#06b6d4",
    accent_hover    = "#0891b2",
    border_light    = "#21262d",
    border_default  = "#30363d",
    border_strong   = "#484f58",
    tier_critical_bg   = "#1c0a0a",
    tier_critical_fg   = "#fca5a5",
    tier_critical_brd  = "#7f1d1d",
    tier_major_bg      = "#1c1000",
    tier_major_fg      = "#fcd34d",
    tier_major_brd     = "#78350f",
    tier_minor_bg      = "#041020",
    tier_minor_fg      = "#93c5fd",
    tier_minor_brd     = "#1e3a5f",
    ok_band_bg      = "#031a0f",
    ok_band_brd     = "#166534",
    nok_band_bg     = "#1a0505",
    nok_band_brd    = "#7f1d1d",
    review_band_bg  = "#1a1100",
    review_band_brd = "#92400e",
)

════════════════════════════════════════════════════
FICHIER 4 : ui/theme/styles.py  (RÉÉCRIRE)
════════════════════════════════════════════════════

def generate_qss(palette) -> str:
    """
    Génère le QSS complet pour toute l'application.
    Utilise les couleurs de la palette.
    Longueur minimale : 4000 caractères.

    Widgets couverts OBLIGATOIREMENT (ordre) :
      QMainWindow, QWidget, QFrame
      QPushButton, QPushButton:hover, QPushButton:pressed,
        QPushButton:disabled
      QLineEdit, QLineEdit:focus, QLineEdit:disabled
      QTextEdit, QPlainTextEdit
      QComboBox, QComboBox::drop-down, QComboBox QAbstractItemView
      QSpinBox, QDoubleSpinBox
      QTableWidget, QHeaderView::section
      QTableWidget::item, QTableWidget::item:selected
      QTabWidget::pane
      QTabBar::tab, QTabBar::tab:selected, QTabBar::tab:hover
        QTabBar::tab:disabled
      QScrollBar:vertical, QScrollBar::handle:vertical,
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical
      QScrollBar:horizontal, QScrollBar::handle:horizontal
      QGroupBox, QGroupBox::title
      QLabel
      QSplitter::handle
      QMenuBar, QMenuBar::item, QMenuBar::item:selected
      QMenu, QMenu::item, QMenu::item:selected, QMenu::separator
      QStatusBar
      QDialog
      QMessageBox
      QProgressBar, QProgressBar::chunk
      QCheckBox, QCheckBox::indicator, QCheckBox::indicator:checked
      QRadioButton
      QToolTip
      QListWidget, QListWidget::item, QListWidget::item:selected

    RÈGLE TABS (GR-V9-8) :
      Ne PAS forcer la position dans QSS.
      La position North est définie dans le code Python.
      Le QSS doit seulement styler l'apparence des tabs.

    RÈGLE bg_grid :
      Les widgets avec objectName="GridCell" ou "ZoomableGridView"
      doivent avoir background-color: {p.bg_grid}.

    Construire avec f-string :
      p = palette
      return f\"\"\"
      QMainWindow, QWidget {{
          background-color: {p.bg_primary};
          color: {p.text_primary};
          font-family: 'Segoe UI', Tahoma, sans-serif;
          font-size: 13px;
      }}
      ... (tous les widgets)
      \"\"\"
    """
    p = palette
    # Implémenter generate_qss() complète ici.
    # Elle doit couvrir TOUS les widgets listés.
    # Retourner une string QSS de minimum 4000 chars.
    raise NotImplementedError(
        "Implémenter generate_qss() avec tous les widgets")

════════════════════════════════════════════════════
FICHIER 5 : ui/theme/theme_manager.py  (RÉÉCRIRE)
════════════════════════════════════════════════════

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal
from ui.theme.colors import ThemePalette
from ui.theme.presets.light import LIGHT_PALETTE
from ui.theme.presets.dark  import DARK_PALETTE
from ui.theme.styles        import generate_qss
import logging

logger = logging.getLogger(__name__)

class ThemeManager(QObject):
    """
    Singleton. Applique le thème global à l'application entière.

    GR-V9-2 : apply() DOIT être appelé AVANT QMainWindow.show().
    GR-V8-5 : Commutable à chaud sans redémarrage.

    Usage obligatoire dans main.py :
      app = QApplication(sys.argv)
      config = Config.load(...)
      ThemeManager.instance().apply(config.get("ui.theme","light"))
      window = MainWindow(config)
      window.show()
    """
    themeChanged = pyqtSignal(str)

    _instance: "ThemeManager | None" = None

    THEMES: dict[str, ThemePalette] = {
        "light": LIGHT_PALETTE,
        "dark":  DARK_PALETTE,
    }

    def __init__(self):
        super().__init__()
        self._current: str = "light"

    @classmethod
    def instance(cls) -> "ThemeManager":
        """Retourne l'instance singleton (crée si nécessaire)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def apply(self, theme_name: str) -> None:
        """
        Applique le thème à l'application entière.
        Appelle QApplication.instance().setStyleSheet(qss).

        Si theme_name inconnu → fallback "light" + log warning.
        Si QApplication n'existe pas → RuntimeError.

        Émet themeChanged après application réussie.
        """
        app = QApplication.instance()
        if app is None:
            raise RuntimeError(
                "ThemeManager.apply() appelé sans QApplication. "
                "Créer QApplication AVANT d'appeler apply().")

        palette = self.THEMES.get(theme_name)
        if palette is None:
            logger.warning(
                f"Thème inconnu '{theme_name}'. "
                "Utilisation du thème 'light' par défaut.")
            palette = LIGHT_PALETTE
            theme_name = "light"

        qss = generate_qss(palette)
        app.setStyleSheet(qss)
        self._current = theme_name
        self.themeChanged.emit(theme_name)
        logger.info(f"Thème appliqué : {theme_name}")

    def current_theme(self) -> str:
        return self._current

    def current_palette(self) -> ThemePalette:
        return self.THEMES.get(self._current, LIGHT_PALETTE)

    def available_themes(self) -> list[str]:
        return list(self.THEMES.keys())

════════════════════════════════════════════════════
FICHIER 6 : main.py  (CORRIGER — ordre strict obligatoire)
════════════════════════════════════════════════════

Localiser main.py et modifier la fonction main() pour respecter
STRICTEMENT cet ordre :

def main() -> None:
    # ── ÉTAPE 1 : QApplication EN PREMIER (toujours) ──
    app = QApplication(sys.argv)

    # ── ÉTAPE 2 : Configuration ──
    config = Config.load(Path("config/config.yaml"))

    # ── ÉTAPE 3 : ThemeManager.apply() AVANT TOUT WIDGET ──
    #             GR-V9-2 : INTERDIT de créer un widget avant cette ligne
    theme = ThemeManager.instance()
    theme_name = config.get("ui.theme", "light")
    theme.apply(theme_name)

    # ── ÉTAPE 4 : Création des widgets (après le thème) ──
    main_window = MainWindow(config)
    main_window.show()

    sys.exit(app.exec())

⚠ INTERDIT d'inverser les étapes 3 et 4.
⚠ INTERDIT de créer un QWidget ou QDialog AVANT theme.apply().
⚠ INTERDIT de créer une QApplication sans appeler theme.apply()
  juste après le chargement de la config.

════════════════════════════════════════════════════
CORRECTION BUG-02 : QTabWidget tabs North (GR-V9-8)
════════════════════════════════════════════════════

Chercher TOUS les fichiers Python dans ui/ :
  grep -rn "setTabPosition" ts2i_ivs/ui/ --include="*.py"

Pour chaque occurrence de West, East, ou South :
  Remplacer par : QTabWidget.TabPosition.North

Fichiers probablement concernés :
  ui/tabs/settings_tab.py
  ui/main_window.py
  ui/screens/product_creation_screen.py
  (vérifier tous les autres)

════════════════════════════════════════════════════
AJOUTER dans config/config.yaml (si absent)
════════════════════════════════════════════════════

ui:
  theme: "light"          # "light" | "dark"
  auto_zoom_on_nok: true
  zoom_nok_level: 4.0
```

### ✅ Gate S25-v9

```bash
# Test 1 : QSS valide pour les 2 thèmes
python3 -c "
from ui.theme.presets.light import LIGHT_PALETTE
from ui.theme.presets.dark  import DARK_PALETTE
from ui.theme.styles        import generate_qss

REQUIRED_WIDGETS = [
    'QPushButton', 'QLabel', 'QTableWidget', 'QTabWidget',
    'QLineEdit', 'QScrollBar', 'QComboBox', 'QGroupBox',
    'QProgressBar', 'QCheckBox', 'QMenuBar', 'QDialog',
    'QListWidget', 'QSplitter',
]

for P in [LIGHT_PALETTE, DARK_PALETTE]:
    qss = generate_qss(P)
    assert len(qss) >= 4000, \
        f'{P.name}: QSS trop court ({len(qss)} chars, min 4000)'
    for w in REQUIRED_WIDGETS:
        assert w in qss, f'Widget {w} ABSENT du QSS {P.name}'
    # Vérifier couleurs de base
    assert P.bg_primary in qss,   f'{P.name}: bg_primary absent du QSS'
    assert P.text_primary in qss, f'{P.name}: text_primary absent du QSS'
    print(f'OK {P.name}: {len(qss)} chars, tous widgets présents')
"

# Test 2 : ThemeManager singleton
python3 -c "
from ui.theme.theme_manager import ThemeManager
t1 = ThemeManager.instance()
t2 = ThemeManager.instance()
assert t1 is t2, 'FAIL: ThemeManager doit être singleton'
print('OK: ThemeManager singleton')
assert 'light' in t1.available_themes()
assert 'dark'  in t1.available_themes()
print('OK: 2 thèmes disponibles')
"

# Test 3 : Aucun setStyleSheet en dehors de ThemeManager
grep -rn "setStyleSheet" ts2i_ivs/ui/ --include="*.py" \
  | grep -v "theme_manager.py" \
  | grep -v "^.*#" \
  | grep -v "test_"
# → DOIT être vide. Chaque ligne affichée = BUG.

# Test 4 : Tabs North uniquement
grep -rn "TabPosition.West\|TabPosition.East\|TabPosition.South" \
  ts2i_ivs/ui/ --include="*.py"
# → DOIT être vide.

# Test 5 : Ordre correct dans main.py
python3 -c "
content = open('ts2i_ivs/main.py').read()
# Vérifier que theme.apply() précède MainWindow(
assert 'theme.apply(' in content, 'theme.apply() absent de main.py'
assert 'MainWindow(' in content, 'MainWindow( absent de main.py'
idx_theme  = content.index('theme.apply(')
idx_window = content.index('MainWindow(')
assert idx_theme < idx_window, \
    f'ORDRE INCORRECT: theme.apply() à {idx_theme} > MainWindow( à {idx_window}'
print('OK: theme.apply() précède MainWindow()')
"

pytest tests/ui/test_theme_manager.py -v
```

---

# ════════════════════════════════════════════════════════════════
# S26-v9 — OPERATORS CRUD CORE (COMPLÉTION BUG-06)
# ════════════════════════════════════════════════════════════════

## S26-v9 : Gestion opérateurs — models, manager, permissions, repository

```
📋 Objectif  : Système opérateurs complet côté core + storage
⏱  Durée     : 2 jours
🔄 Action    : CRÉER core/operators/ + RÉÉCRIRE storage/operator_repository.py
🐛 Bugs fixés: BUG-06 (opérateurs core non fonctionnel)
📄 Règles    : GR-V9-7 (bcrypt, jamais plain text)
📦 Dépend    : S25-v9 complété
📦 Ajouter   : bcrypt>=4.1 dans requirements.txt + pip install bcrypt
```

### 🤖 Prompt S26-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md GR-03, GR-V9-7 intégralement.

CONTEXTE :
  TABLE operators existe dans 001_initial.sql (S00-A) :
    id TEXT PRIMARY KEY, name TEXT, role TEXT,
    pin_hash TEXT, active INTEGER DEFAULT 1,
    last_login REAL, created_at REAL
  TABLE operator_stats :
    operator_id TEXT, product_id TEXT,
    total INTEGER, ok_count INTEGER, nok_count INTEGER

  OperatorManager v8 : PIN stocké plain text dans certains cas → BUG.
  GR-V9-7 : PIN TOUJOURS hashé bcrypt rounds=12, jamais loggué.

MISSION — Créer/réécrire ces fichiers :

════════════════════════════════════════════════════
FICHIER 1 : core/operators/models.py  (CRÉER)
════════════════════════════════════════════════════

from enum import Enum
from dataclasses import dataclass

class OperatorRole(Enum):
    ADMIN    = "admin"     # accès total
    OPERATOR = "operator"  # inspection + review
    VIEWER   = "viewer"    # lecture seule

@dataclass(frozen=True)
class Operator:
    """
    Données opérateur. pin_hash = hash bcrypt, JAMAIS le PIN brut.
    GR-V9-7 : Ne jamais exposer le PIN brut dans ce dataclass.
    """
    operator_id : str         # format "OP-001"
    name        : str
    role        : OperatorRole
    pin_hash    : str         # bcrypt hash — pas le PIN !
    active      : bool
    created_at  : float       # timestamp Unix
    last_login  : float | None

@dataclass(frozen=True)
class OperatorStats:
    operator_id    : str
    product_id     : str | None  # None = toutes productions
    total          : int
    ok_count       : int
    nok_count      : int
    taux_ok        : float       # 0.0 si total == 0
    last_inspection: float | None

@dataclass(frozen=True)
class OperatorSummary:
    """Version légère pour affichage liste (évite N+1 queries)."""
    operator_id       : str
    name              : str
    role              : OperatorRole
    active            : bool
    last_login        : float | None
    total_inspections : int
    taux_ok           : float

════════════════════════════════════════════════════
FICHIER 2 : core/operators/permissions.py  (CRÉER)
════════════════════════════════════════════════════

from core.operators.models import OperatorRole
from functools import wraps
import logging

logger = logging.getLogger(__name__)

PERMISSIONS: dict[OperatorRole, frozenset[str]] = {
    OperatorRole.ADMIN: frozenset({
        "product.create", "product.edit", "product.delete",
        "product.duplicate", "product.activate",
        "product.export", "product.import",
        "product.view",
        "operator.create", "operator.edit",
        "operator.delete", "operator.view",
        "inspection.start", "inspection.stop",
        "review.validate",
        "settings.view", "settings.edit",
        "gpio.view", "gpio.config",
        "fleet.export", "fleet.import",
        "reports.view", "reports.export",
    }),
    OperatorRole.OPERATOR: frozenset({
        "product.view",
        "inspection.start", "inspection.stop",
        "review.validate",
        "reports.view",
    }),
    OperatorRole.VIEWER: frozenset({
        "product.view",
        "reports.view",
    }),
}

def has_permission(operator: "Operator",
                   permission: str) -> bool:
    """Vérifie si un opérateur possède une permission."""
    return permission in PERMISSIONS.get(
        operator.role, frozenset())

def requires_permission(permission: str):
    """
    Décorateur pour méthodes de SystemController.
    self doit avoir self._current_operator: Operator | None.

    Lève PermissionError si :
      - Aucun opérateur connecté
      - Permission refusée pour le rôle

    Usage :
      @requires_permission("product.edit")
      def edit_product(self, product_id): ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            op = getattr(self, "_current_operator", None)
            if op is None:
                raise PermissionError(
                    f"Permission '{permission}' refusée : "
                    "aucun opérateur connecté.")
            if not has_permission(op, permission):
                raise PermissionError(
                    f"Opérateur '{op.name}' "
                    f"(rôle={op.role.value}) "
                    f"n'a pas la permission '{permission}'.")
            logger.info(
                f"Permission '{permission}' accordée "
                f"à {op.name} ({op.role.value})")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator

════════════════════════════════════════════════════
FICHIER 3 : storage/operator_repository.py  (RÉÉCRIRE)
════════════════════════════════════════════════════

import bcrypt
import sqlite3
import time
from pathlib import Path
from core.operators.models import (
    Operator, OperatorRole, OperatorStats, OperatorSummary)
import logging

logger = logging.getLogger(__name__)

class OperatorRepository:
    """
    Accès DB opérateurs.
    GR-V9-7 : PIN JAMAIS stocké/loggué en clair.
               bcrypt rounds=12 obligatoire.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _next_operator_id(self, conn: sqlite3.Connection) -> str:
        """Génère le prochain ID format OP-001, OP-002, ..."""
        count = conn.execute(
            "SELECT COUNT(*) FROM operators").fetchone()[0]
        return f"OP-{count + 1:03d}"

    def create(self, name: str, role: OperatorRole,
               pin: str) -> "Operator":
        """
        Crée un opérateur en DB.

        Validation (lève ValueError si invalide) :
          - name : non vide après strip()
          - pin  : 4 à 6 chiffres uniquement (isdigit() + len)

        Hashage :
          pin_hash = bcrypt.hashpw(
              pin.encode('utf-8'),
              bcrypt.gensalt(rounds=12)
          ).decode('utf-8')

        ⚠ GR-V9-7 : Ne JAMAIS logguer le pin brut.
           logger.info doit mentionner le nom, PAS le pin.
        """
        name = name.strip()
        if not name:
            raise ValueError("Nom opérateur vide.")
        if not pin.isdigit() or not (4 <= len(pin) <= 6):
            raise ValueError(
                "PIN invalide : doit contenir 4 à 6 chiffres.")

        # Hash bcrypt — jamais stocker le brut
        pin_hash = bcrypt.hashpw(
            pin.encode("utf-8"),
            bcrypt.gensalt(rounds=12)
        ).decode("utf-8")

        with self._get_conn() as conn:
            operator_id = self._next_operator_id(conn)
            now = time.time()
            conn.execute(
                """INSERT INTO operators
                   (id, name, role, pin_hash, active, created_at)
                   VALUES (?, ?, ?, ?, 1, ?)""",
                (operator_id, name, role.value, pin_hash, now))

        # ⚠ Log sans le pin
        logger.info(
            f"Opérateur créé : {operator_id} ({name}, "
            f"{role.value})")
        return self.get(operator_id)

    def authenticate(self, operator_id: str,
                     pin: str) -> "Operator | None":
        """
        Vérifie le PIN par bcrypt.checkpw().
        Retourne Operator si correct + actif, None sinon.
        Met à jour last_login si succès.

        ⚠ GR-V9-7 : Ne JAMAIS logguer le pin brut.
           Logger seulement "auth OK" ou "auth FAIL" + operator_id.
           Ne pas logguer "PIN correct: 1234" ou similaire.
        """
        op = self.get(operator_id)
        if op is None or not op.active:
            return None

        try:
            match = bcrypt.checkpw(
                pin.encode("utf-8"),
                op.pin_hash.encode("utf-8"))
        except Exception:
            return None

        if match:
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE operators SET last_login=? WHERE id=?",
                    (time.time(), operator_id))
            logger.info(f"Auth OK : {operator_id}")
            return self.get(operator_id)

        logger.warning(f"Auth FAIL : {operator_id}")
        return None

    def update(self, operator_id: str,
               name: str | None = None,
               role: OperatorRole | None = None,
               active: bool | None = None) -> "Operator":
        """
        Mise à jour partielle (champs non-None seulement).
        Ne modifie PAS le pin_hash (utiliser change_pin()).
        """
        with self._get_conn() as conn:
            if name is not None:
                conn.execute(
                    "UPDATE operators SET name=? WHERE id=?",
                    (name, operator_id))
            if role is not None:
                conn.execute(
                    "UPDATE operators SET role=? WHERE id=?",
                    (role.value, operator_id))
            if active is not None:
                conn.execute(
                    "UPDATE operators SET active=? WHERE id=?",
                    (1 if active else 0, operator_id))
        return self.get(operator_id)

    def change_pin(self, operator_id: str,
                   new_pin: str) -> None:
        """
        Change le PIN. Valide et hash avant persistance.
        ⚠ GR-V9-7 : Ne jamais logguer new_pin.
        """
        if not new_pin.isdigit() or not (4 <= len(new_pin) <= 6):
            raise ValueError(
                "Nouveau PIN invalide : 4 à 6 chiffres requis.")
        new_hash = bcrypt.hashpw(
            new_pin.encode("utf-8"),
            bcrypt.gensalt(rounds=12)
        ).decode("utf-8")
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE operators SET pin_hash=? WHERE id=?",
                (new_hash, operator_id))
        # ⚠ log sans le pin
        logger.info(f"PIN modifié : {operator_id}")

    def delete(self, operator_id: str) -> None:
        """
        Supprime l'opérateur de la table operators.
        Conserve operator_stats (audit trail).
        """
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM operators WHERE id=?",
                (operator_id,))
        logger.info(f"Opérateur supprimé : {operator_id}")

    def get(self, operator_id: str) -> "Operator | None":
        """Retourne Operator depuis DB ou None si absent."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM operators WHERE id=?",
                (operator_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_operator(row)

    def list_all(self) -> list["Operator"]:
        """Tous les opérateurs, triés par name ASC."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM operators ORDER BY name ASC"
            ).fetchall()
        return [self._row_to_operator(r) for r in rows]

    def get_summaries(self) -> list["OperatorSummary"]:
        """
        Liste légère avec stats agrégées depuis operator_stats.
        Un seul SELECT avec LEFT JOIN (pas de N+1 queries).
        """
        sql = """
        SELECT
            o.id, o.name, o.role, o.active, o.last_login,
            COALESCE(SUM(s.total), 0)    AS total,
            COALESCE(SUM(s.ok_count), 0) AS ok_total
        FROM operators o
        LEFT JOIN operator_stats s ON s.operator_id = o.id
        GROUP BY o.id
        ORDER BY o.name ASC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql).fetchall()
        result = []
        for r in rows:
            total = r["total"] or 0
            ok    = r["ok_total"] or 0
            taux  = (ok / total * 100) if total > 0 else 0.0
            result.append(OperatorSummary(
                operator_id       = r["id"],
                name              = r["name"],
                role              = OperatorRole(r["role"]),
                active            = bool(r["active"]),
                last_login        = r["last_login"],
                total_inspections = total,
                taux_ok           = taux,
            ))
        return result

    def update_stats(self, operator_id: str,
                     product_id: str,
                     verdict: str) -> None:
        """
        Appelé depuis SystemController après chaque inspection.
        UPSERT dans operator_stats.
        verdict : "OK" | "NOK" | "REVIEW"
        """
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO operator_stats
                   (operator_id, product_id, total, ok_count, nok_count)
                   VALUES (?, ?, 1,
                     CASE WHEN ? = 'OK'  THEN 1 ELSE 0 END,
                     CASE WHEN ? = 'NOK' THEN 1 ELSE 0 END)
                   ON CONFLICT(operator_id, product_id) DO UPDATE SET
                     total     = total + 1,
                     ok_count  = ok_count  +
                       CASE WHEN ? = 'OK'  THEN 1 ELSE 0 END,
                     nok_count = nok_count +
                       CASE WHEN ? = 'NOK' THEN 1 ELSE 0 END
                """,
                (operator_id, product_id,
                 verdict, verdict, verdict, verdict))

    def _row_to_operator(self, row) -> "Operator":
        return Operator(
            operator_id = row["id"],
            name        = row["name"],
            role        = OperatorRole(row["role"]),
            pin_hash    = row["pin_hash"],
            active      = bool(row["active"]),
            created_at  = row["created_at"] or 0.0,
            last_login  = row["last_login"],
        )

════════════════════════════════════════════════════
FICHIER 4 : core/operators/operator_manager.py  (RÉÉCRIRE)
════════════════════════════════════════════════════

from core.operators.models import (
    Operator, OperatorRole, OperatorSummary)
from storage.operator_repository import OperatorRepository
import logging

logger = logging.getLogger(__name__)

class OperatorError(Exception):
    """Erreur métier opérateur (règles, contraintes)."""
    pass

class OperatorManager:
    """
    Couche métier opérateurs.
    Applique les règles métier AVANT de déléguer au Repository.
    GR-V9-7 : Ne manipule jamais le PIN brut directement.
    """

    def __init__(self, repository: OperatorRepository):
        self._repo = repository
        self._current_operator: Operator | None = None

    # ── Gestion session courante ──

    def set_current(self, operator: Operator) -> None:
        self._current_operator = operator
        logger.info(
            f"Opérateur connecté : {operator.name} "
            f"({operator.role.value})")

    def get_current(self) -> Operator | None:
        return self._current_operator

    def logout(self) -> None:
        if self._current_operator:
            logger.info(
                f"Déconnexion : {self._current_operator.name}")
        self._current_operator = None

    # ── CRUD ──

    def create(self, name: str, role: OperatorRole,
               pin: str) -> Operator:
        """Délègue au repository (validation et hash dans repo)."""
        return self._repo.create(name, role, pin)

    def authenticate(self, operator_id: str,
                     pin: str) -> Operator | None:
        """Retourne Operator si succès, None si échec."""
        return self._repo.authenticate(operator_id, pin)

    def update(self, operator_id: str, **kwargs) -> Operator:
        """
        Règle métier :
          INTERDIT de désactiver l'opérateur actuellement connecté.
        """
        if kwargs.get("active") is False:
            cur = self._current_operator
            if cur and cur.operator_id == operator_id:
                raise OperatorError(
                    "Impossible de désactiver "
                    "l'opérateur actuellement connecté.")
        return self._repo.update(operator_id, **kwargs)

    def delete(self, operator_id: str) -> None:
        """
        Règles métier :
          1. INTERDIT de supprimer l'opérateur connecté.
          2. INTERDIT de supprimer le dernier ADMIN actif.
        """
        cur = self._current_operator
        if cur and cur.operator_id == operator_id:
            raise OperatorError(
                "Impossible de supprimer "
                "l'opérateur actuellement connecté.")

        target = self._repo.get(operator_id)
        if target and target.role == OperatorRole.ADMIN:
            admins = [
                op for op in self._repo.list_all()
                if op.role == OperatorRole.ADMIN
                and op.active
                and op.operator_id != operator_id
            ]
            if not admins:
                raise OperatorError(
                    "Impossible de supprimer le dernier "
                    "administrateur actif. "
                    "Créer un autre admin avant.")

        self._repo.delete(operator_id)

    def change_pin(self, operator_id: str,
                   new_pin: str) -> None:
        """Délègue au repository (validation + hash dans repo)."""
        self._repo.change_pin(operator_id, new_pin)

    def list_all(self) -> list[Operator]:
        return self._repo.list_all()

    def get(self, operator_id: str) -> Operator | None:
        return self._repo.get(operator_id)

    def get_summaries(self) -> list[OperatorSummary]:
        return self._repo.get_summaries()

    def update_stats(self, operator_id: str,
                     product_id: str,
                     verdict: str) -> None:
        self._repo.update_stats(operator_id, product_id, verdict)

════════════════════════════════════════════════════
MIGRATION DB : storage/migrations/002_operators_v9.sql
════════════════════════════════════════════════════

-- Ajout colonnes manquantes (idempotent)
-- SQLite : ALTER TABLE ADD COLUMN ignore si colonne existe déjà
-- (utiliser try/except dans le code Python pour SQLite < 3.35)

-- Colonne last_login si absente
ALTER TABLE operators ADD COLUMN last_login REAL;
-- Colonne created_at si absente
ALTER TABLE operators ADD COLUMN created_at REAL;

-- Table operator_stats avec contrainte UNIQUE si absente
CREATE TABLE IF NOT EXISTS operator_stats (
    operator_id TEXT NOT NULL,
    product_id  TEXT NOT NULL,
    total       INTEGER DEFAULT 0,
    ok_count    INTEGER DEFAULT 0,
    nok_count   INTEGER DEFAULT 0,
    PRIMARY KEY (operator_id, product_id)
);

════════════════════════════════════════════════════
requirements.txt  (AJOUTER si absent)
════════════════════════════════════════════════════

bcrypt>=4.1

Installer :
  pip install bcrypt
```

### ✅ Gate S26-v9

```bash
pip install bcrypt

pytest tests/unit/test_operator_manager.py -v

# Contenu minimum des tests :
# - create("Ahmed", ADMIN, "1234") → Operator retourné
# - operator.pin_hash != "1234"  (pas de plain text)
# - operator.pin_hash.startswith("$2b$")  (format bcrypt)
# - create("Ali", OPERATOR, "12") → ValueError (PIN court)
# - create("Ali", OPERATOR, "ABCD") → ValueError (pas chiffres)
# - authenticate(op.id, "1234") → Operator (PIN correct)
# - authenticate(op.id, "9999") → None (PIN incorrect)
# - authenticate(op.id, "") → None
# - delete(dernier ADMIN) → OperatorError
# - delete(opérateur connecté) → OperatorError
# - update(op.id, active=False) si connecté → OperatorError
# - change_pin(op.id, "5678") → authenticate("5678") succès

# Vérifier bcrypt dans la DB
python3 -c "
import sqlite3
conn = sqlite3.connect('ts2i_ivs/data/ivs.db')
rows = conn.execute(
    'SELECT id, pin_hash FROM operators LIMIT 5').fetchall()
for op_id, pin_hash in rows:
    assert pin_hash.startswith('\$2b\$'), \
        f'{op_id}: pin_hash non-bcrypt = {pin_hash[:10]}...'
    print(f'OK {op_id}: bcrypt hash confirmé')
"

# Vérifier aucun PIN en clair dans les logs
grep -rn "pin\b" ts2i_ivs/core/ ts2i_ivs/storage/ \
  --include="*.py" \
  | grep -v "pin_hash\|bcrypt\|encode\|# " \
  | grep -i "log\|print\|info\|warn\|error\|debug"
# → DOIT être vide (GR-V9-7)
```

---

# ════════════════════════════════════════════════════════════════
# S28-v9 — TELEMETRY PANEL DRAGGABLE (RÉÉCRITURE BUG-07)
# ════════════════════════════════════════════════════════════════

## S28-v9 : Panel gauche — 4 sections réorganisables par drag

```
📋 Objectif  : TelemetryPanel avec drag & drop + section Image Qualité
⏱  Durée     : 2 jours
🔄 Action    : RÉÉCRIRE ui/components/telemetry_panel.py (créer telemetry_section.py)
🐛 Bugs fixés: BUG-07 (TelemetryPanel v8 créé mais non intégré)
📄 Règles    : GR-V9-3 (ordre persisté), GR-V8-2 (thème global)
📦 Dépend    : S25-v9 complété
```

### 🤖 Prompt S28-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md GR-03, GR-05, GR-V8-2, GR-V9-3.

MISSION — Créer/réécrire ces 2 fichiers :
  ui/components/telemetry_section.py  (CRÉER)
  ui/components/telemetry_panel.py    (RÉÉCRIRE)

════════════════════════════════════════════════════
FICHIER 1 : ui/components/telemetry_section.py
════════════════════════════════════════════════════

class TelemetrySection(QFrame):
    """
    Section individuelle draggable du TelemetryPanel.

    section_id valeurs autorisées (UNIQUEMENT ces 4) :
      "session"    → 📊 Session : stats inspection
      "pipeline"   → ⚡ Pipeline : latences observers + FPS
      "image_qual" → 📷 Image Qualité : brightness/contrast/sharpness
      "observers"  → 🔬 Observers : état de chaque observer

    Structure interne (QVBoxLayout) :
      ├─ _header (QWidget, height=28px, cursor=OpenHand)
      │    QHBoxLayout :
      │      QLabel "⠿" (font-size 14px, drag handle)
      │      QLabel titre (SECTION_LABELS[section_id])
      └─ _body (QWidget)
           _body_layout (QVBoxLayout) ← contenu variable

    DRAG : initié par mousePressEvent SUR le _header uniquement.
    QDrag + QMimeData avec text = self._section_id.
    Pixmap drag = self.grab() semi-transparent.
    Hotspot = centre horizontal, haut vertical.

    MÉTHODES de mise à jour du contenu :

    update_session(total, ok, nok, review, taux_ok) :
      Affiche dans _body :
        "Total   : {total}"
        "OK      : {ok}"       couleur ok_color
        "NOK     : {nok}"      couleur nok_color
        "REVIEW  : {review}"   couleur review_color
        "Taux OK : {taux:.1f}%" vert si ≥95%, orange si ≥80%, rouge sinon
      ⚠ Applicable UNIQUEMENT si section_id == "session"
         → logger.debug si appelé sur autre section_id

    update_pipeline(avg_ms, fps, latencies) :
      latencies = dict[str, float] ex: {"SIFT": 38.0, "YOLO": 61.0}
      Affiche :
        "Avg    : {avg_ms:.0f}ms" vert<300ms, orange<500ms, rouge sinon
        "FPS    : {fps:.1f}"
        Pour chaque (obs, ms) dans latencies :
          "  {obs:<10}: {ms:.0f}ms"
      ⚠ Applicable UNIQUEMENT si section_id == "pipeline"

    update_image_quality(brightness, contrast, sharpness,
                         exposure, gain,
                         ref_b, ref_b_std,
                         ref_c, ref_c_std,
                         ref_s, ref_s_std) :
      Pour brightness, contrast, sharpness :
        delta = valeur - ref
        in_range = abs(delta) <= std
        Afficher : label | "{valeur:.0f}" | delta coloré
        Couleur delta : vert si in_range, orange sinon
      Pour exposure et gain : QLabel texte simple
      ⚠ Applicable UNIQUEMENT si section_id == "image_qual"

    update_observers(observer_results: list[dict]) :
      observer_results = liste de dicts :
        {
          "observer_id" : str,
          "label"       : str,    # ex: "Yolo V8X"
          "tier"        : str,    # "CRITICAL"|"MAJOR"|"MINOR"
          "passed"      : bool|None,
          "value"       : float|str|None,
          "enabled"     : bool,
          "error_msg"   : str|None,
        }
      Pour chaque observer, afficher une ligne :
        ● (dot coloré) | label | [tier badge] | valeur
        dot : vert si passed=True, rouge si False,
              gris si None ou enabled=False
        valeur : str(value) si not None, "⏳" si None, "—" si disabled
        Si error_msg : tooltip "⚠" sur le dot
      ⚠ Applicable UNIQUEMENT si section_id == "observers"
    """

    SECTION_LABELS: dict[str, str] = {
        "session"    : "📊 Session",
        "pipeline"   : "⚡ Pipeline",
        "image_qual" : "📷 Image Qualité",
        "observers"  : "🔬 Observers",
    }

    def __init__(self, section_id: str, parent=None): ...

    @property
    def section_id(self) -> str: ...

    def mousePressEvent(self, event) -> None:
        """
        Initie le drag UNIQUEMENT si clic sur _header.
        Utiliser self._header.geometry().contains(event.pos()).
        Si clic ailleurs → propager à super().mousePressEvent().
        """

    def _start_drag(self) -> None:
        """
        QDrag avec :
          mime.setText(self._section_id)
          drag.setPixmap(self.grab())
          drag.exec(Qt.DropAction.MoveAction)
        """

════════════════════════════════════════════════════
FICHIER 2 : ui/components/telemetry_panel.py
════════════════════════════════════════════════════

PREFS_FILE = Path("config/ui_prefs.yaml")

class TelemetryPanel(QWidget):
    """
    Container des 4 TelemetrySection, réorganisables par drag.
    Largeur fixe : 200px.
    Persistance ordre dans config/ui_prefs.yaml (GR-V9-3).

    Structure interne :
      QVBoxLayout
        └─ QScrollArea (widgetResizable=True, no horizontal scrollbar)
             └─ QWidget container
                  └─ QVBoxLayout sections_layout
                       ├─ TelemetrySection("session")
                       ├─ TelemetrySection("pipeline")
                       ├─ TelemetrySection("image_qual")
                       ├─ TelemetrySection("observers")
                       └─ stretch (addStretch à la fin)

    DRAG & DROP sur le panel lui-même :
      setAcceptDrops(True)
      dragEnterEvent : accepter si mimeData().hasText()
                       et text dans SECTION_LABELS
      dropEvent :
        1. source_id = mimeData().text()
        2. Trouver section cible sous le curseur drop
        3. Si source != cible → réordonner dans layout
        4. _save_order() (GR-V9-3)

    CHARGEMENT ordre :
      _load_order() → lit ui_prefs.yaml["telemetry_order"]
      Si absent/invalide → DEFAULT_ORDER
      Valider que tous les section_ids sont dans SECTION_LABELS

    SAUVEGARDE ordre :
      _save_order() → écrit ui_prefs.yaml["telemetry_order"]
      Préserve les autres clés du fichier (yaml.safe_load + update + dump)

    API publique de mise à jour :
      update_from_result(result: FinalResult) :
        → _sections["session"].update_session(...)
        → _sections["observers"].update_observers(...)
        GR-03 : appelé via signal UIBridge uniquement
        GR-05 : thread UI uniquement

      update_pipeline(latencies, avg_ms, fps) :
        → _sections["pipeline"].update_pipeline(...)

      update_image_quality(frame: np.ndarray, metadata: dict) :
        Calcule depuis frame numpy :
          gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) si BGR
          brightness = float(gray.mean())
          contrast   = float(gray.std())
          sharpness  = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        Récupère références depuis metadata (clés "ref_brightness" etc.)
        → _sections["image_qual"].update_image_quality(...)
    """

    DEFAULT_ORDER: list[str] = [
        "session", "pipeline", "image_qual", "observers"
    ]
```

### ✅ Gate S28-v9

```bash
pytest tests/ui/test_telemetry_panel.py -v

# Tests minimum :
# - TelemetryPanel créé → 4 sections, ordre DEFAULT_ORDER
# - section_id invalide ("inconnu") → AssertionError dans TelemetrySection
# - update_session(145,142,3,0,97.9) → labels visibles dans section
# - update_pipeline(142,28,{"SIFT":38,"YOLO":61}) → lignes affichées
# - update_image_quality(frame_noir) → brightness≈0, sharpness≈0
# - update_observers([{passed:True,...},{passed:False,...}])
#   → dots verts/rouges selon passed
# - Drag "observers" sur "session" → ordre changé
# - _save_order() → ui_prefs.yaml["telemetry_order"] mis à jour
# - Rechargement TelemetryPanel → ordre restauré depuis yaml
```

---

# ════════════════════════════════════════════════════════════════
# S29-v9 — FLEXIBLE GRID VIEW (RÉÉCRITURE BUG-03 + BUG-08)
# ════════════════════════════════════════════════════════════════

## S29-v9 : 1/2/3/4 grids configurables + right-click + sources

```
📋 Objectif  : Remplacer 3 QLabel fixes par FlexibleGridView propre
⏱  Durée     : 3 jours
🔄 Action    : CRÉER grid_cell.py + source_renderer.py, RÉÉCRIRE flexible_grid_view.py
🐛 Bugs fixés: BUG-03 (grids QLabel fixes), BUG-08 (FlexibleGridView non utilisé)
📄 Règles    : GR-V8-6 (layout persisté), anti-pattern QLabel
📦 Dépend    : S22-A (ZoomableGridView existant), S25-v9
```

### 🤖 Prompt S29-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md GR-03, GR-05, GR-V8-6, et l'anti-pattern QLabel.
Vérifier que ZoomableGridView (S22-A) est bien implémentée.

MISSION — Créer/réécrire ces 3 fichiers :

════════════════════════════════════════════════════
FICHIER 1 : ui/components/grid_cell.py  (CRÉER)
════════════════════════════════════════════════════

# Sources disponibles (8 au total)
GRID_SOURCES: dict[str, str] = {
    "live_raw"     : "📷 Live Raw",
    "aligned"      : "📐 Aligned (SIFT)",
    "logo_zoom"    : "🔍 Logo Zoom auto",
    "differential" : "🔬 Differential",
    "reference"    : "📋 Référence produit",
    "roi_overlay"  : "🎯 ROI Overlay",
    "heatmap"      : "🌡 Heatmap anomalies",
    "caliper"      : "📏 Caliper mesures",
}

ZOOM_LEVELS: list[float] = [0.5, 1.0, 2.0, 4.0, 6.0]

class GridCell(QWidget):
    """
    Une cellule du FlexibleGridView.
    Contient un header compact et un ZoomableGridView.
    ⚠ INTERDIT d'utiliser QLabel pour afficher les frames.

    Structure (QVBoxLayout) :
      ├─ _header (QWidget, height=24px, objectName="GridCellHeader")
      │    QHBoxLayout :
      │      _source_label (QLabel, nom de la source actuelle)
      │      spacer
      │      _tools_label  (QLabel "🔍  ⛶  📸", cursor=PointingHand)
      └─ _grid_view (ZoomableGridView, stretch=1)

    PROPRIÉTÉS :
      cell_id : str (lecture seule)
      current_source : str (lecture seule)

    MÉTHODES PUBLIQUES :
      set_source(source_id: str) :
        Valider source_id dans GRID_SOURCES (AssertionError sinon)
        Mettre à jour _source et _source_label.setText()
        Émettre sourceChanged(cell_id, source_id)

      update_frame(rendered_pixmap: QPixmap) :
        Appelle _grid_view.set_pixmap(rendered_pixmap)
        GR-05 : thread UI uniquement

      set_nok_highlight(active: bool) :
        setProperty("nok_highlight", active)
        style().unpolish(self) ; style().polish(self)

    CONTEXT MENU (contextMenuEvent) :
      Sous-menu "📺 Source" :
        Une QAction par source (8 sources)
        checkable=True, checked si c'est la source courante
        triggered → self.set_source(source_id)

      Sous-menu "🔍 Zoom" :
        Une QAction par niveau dans ZOOM_LEVELS (×0.5, ×1.0, ×2.0, ×4.0, ×6.0)
        triggered → self._grid_view.set_zoom(z)
        Séparateur + "🔄 Reset zoom" → self._grid_view.reset_zoom()

      Séparateur

      "⛶ Plein écran" → self._on_fullscreen()
      "📸 Capture PNG" → self._on_capture()
      "📋 Copier image" → QApplication.clipboard().setPixmap(...)

      Séparateur
      "🔄 Reset position" → self._grid_view.reset_pan()

    _on_capture() :
      Si pas de pixmap courant → return
      Chemin : data/snapshots/{YYYY-MM-DD}/snapshot_{timestamp}_{source}.png
      Créer le dossier si absent (parents=True, exist_ok=True)
      Sauvegarder avec QPixmap.save()
      Notification utilisateur : non bloquante (QTimer.singleShot ou simple log)
    """
    sourceChanged = pyqtSignal(str, str)   # cell_id, new_source_id

════════════════════════════════════════════════════
FICHIER 2 : ui/components/source_renderer.py  (CRÉER)
════════════════════════════════════════════════════

class SourceRenderer:
    """
    Convertit frame numpy + metadata → QPixmap selon la source.
    Toutes les méthodes sont @staticmethod (pas d'état).

    MÉTHODE PRINCIPALE : render(source_id, frame, metadata) → QPixmap

    Dispatch selon source_id :

    "live_raw" :
      → _to_pixmap(frame) directement

    "aligned" :
      → metadata.get("aligned_frame") → _to_pixmap(af)
      → Si absent : _to_pixmap(frame)

    "logo_zoom" :
      → metadata.get("logo_zoom_frame") → _to_pixmap(lzf)
      → Si absent : metadata.get("logo_bbox") → crop du frame × bbox
      → Si absent : _unavailable(frame)

    "differential" :
      → ref = metadata.get("reference_frame")
      → Si ref absent : _unavailable(frame)
      → diff = cv2.absdiff(frame, ref)
      → diff_u8 = cv2.convertScaleAbs(diff, alpha=3)
      → gray = cv2.cvtColor(diff_u8, cv2.COLOR_BGR2GRAY)
      → colored = cv2.applyColorMap(gray, cv2.COLORMAP_HOT)
      → _to_pixmap(colored)

    "reference" :
      → metadata.get("reference_frame") → _to_pixmap
      → Si absent : _unavailable(frame)

    "roi_overlay" :
      → _render_roi(frame, metadata)
      → metadata["roi_zones"] = [
           {"bbox":(x,y,w,h), "tier":"CRITICAL"|"MAJOR"|"MINOR",
            "label":str, "passed":bool|None}
         ]
      → Dessiner contours colorés sur copie frame
         CRITICAL=#ef4444 BGR=(68,84,239)
         MAJOR   =#f59e0b BGR=(11,158,245)
         MINOR   =#3b82f6 BGR=(246,158,59)
      → cv2.rectangle + cv2.putText(label)

    "heatmap" :
      → hm = metadata.get("anomaly_heatmap")  # float32 [0..1]
      → Si absent : _unavailable(frame)
      → hm_u8 = (clip(hm,0,1)*255).astype(uint8)
      → hm_color = cv2.applyColorMap(hm_u8, cv2.COLORMAP_JET)
      → blended = cv2.addWeighted(frame,0.4, hm_color,0.6, 0)
      → _to_pixmap(blended)

    "caliper" :
      → _render_caliper(frame, metadata)
      → metadata["caliper_lines"] = [
           {"p1":(x1,y1), "p2":(x2,y2),
            "value_mm":float, "passed":bool}
         ]
      → Dessiner lignes + valeur mm au milieu
         couleur : vert (50,200,50) si passed, rouge (50,50,220) sinon

    source_id inconnu :
      → _unavailable(frame)

    _unavailable(frame) :
      → frame grisé à 30% + texte "Source indisponible"

    _to_pixmap(frame: np.ndarray) → QPixmap :
      Si frame.shape == 2 (grayscale) : QImage.Format_Grayscale8
      Si frame.shape == 3 (BGR) : convertir en RGB → QImage.Format_RGB888
      Retourner QPixmap.fromImage(q_img.copy())
    """

════════════════════════════════════════════════════
FICHIER 3 : ui/components/flexible_grid_view.py  (RÉÉCRIRE)
════════════════════════════════════════════════════

GRID_PRESETS: dict[str, dict] = {
    "Standard"     : {"count": 2, "sources": ["live_raw", "roi_overlay"]},
    "Défaut Focus" : {"count": 3, "sources": ["live_raw", "logo_zoom", "heatmap"]},
    "Analyse Full" : {"count": 4, "sources": ["live_raw","aligned","reference","differential"]},
    "Monitoring"   : {"count": 1, "sources": ["live_raw"]},
}

PREFS_FILE = Path("config/ui_prefs.yaml")

class FlexibleGridView(QWidget):
    """
    Zone centrale avec N grids (1 ≤ N ≤ 4).
    Utilise QSplitter pour proportions libres.
    Persistance layout dans ui_prefs.yaml (GR-V8-6).

    ⚠ JAMAIS utiliser QLabel pour afficher des frames.
      Utiliser GridCell → ZoomableGridView.

    LAYOUTS :
      N=1 : une seule GridCell plein espace (pas de splitter)
      N=2 : QSplitter horizontal, 2 GridCells [50%, 50%]
      N=3 : QSplitter horizontal, 3 GridCells [33%, 33%, 33%]
      N=4 : QSplitter vertical
               ├─ QSplitter horizontal (Grid0, Grid1)
               └─ QSplitter horizontal (Grid2, Grid3)

    MÉTHODES PUBLIQUES :

    set_grid_count(n: int) :
      ASSERT 1 ≤ n ≤ 4 (AssertionError explicite si hors range)
      Message AssertionError : "Nombre de grids invalide : {n}. Valeurs acceptées : 1, 2, 3, 4 (max RPi5)."
      Conserve les sources des cells existantes si possible
      Reconstruit le layout
      _save_prefs()
      Émet gridCountChanged(n)

    apply_preset(preset_name: str) :
      Cherche dans GRID_PRESETS
      Si absent : log warning, return (pas d'exception)
      Reconstruit layout avec count + sources du preset
      _save_prefs()

    load_from_prefs() :
      Lit ui_prefs.yaml["grid_count"] et ["grid_sources"]
      Si absent/invalide → garder état courant
      Reconstruit le layout

    _save_prefs() :
      Écrit dans ui_prefs.yaml :
        "grid_count" : int
        "grid_sources" : list[str]
        "splitter_sizes" : dict {"sp_0": [int,...], "sp_1": [int,...], ...}
      Préserve les autres clés du fichier

    _restore_splitter_sizes() :
      Lit "splitter_sizes" depuis yaml
      Applique setSizes() sur chaque splitter correspondant

    update_frame(frame: np.ndarray, metadata: dict) :
      Pour CHAQUE GridCell dans self._cells :
        pixmap = SourceRenderer.render(cell.current_source, frame, metadata)
        cell.update_frame(pixmap)
      GR-05 : thread UI uniquement
      GR-03 : appelé via signal UIBridge uniquement

    on_result(result: FinalResult) :
      Si result.verdict == "NOK" :
        Pour chaque cell avec source == "logo_zoom" :
          cell.set_nok_highlight(True)
          cell._grid_view.set_zoom(4.0)
      Si result.verdict == "OK" :
        Toutes les cells :
          cell.set_nok_highlight(False)
          cell._grid_view.reset_zoom()
    """
    gridCountChanged = pyqtSignal(int)
```

### ✅ Gate S29-v9

```bash
pytest tests/ui/test_flexible_grid_v9.py -v

# - set_grid_count(1) → 1 GridCell visible
# - set_grid_count(2) → 2 GridCells + QSplitter horizontal
# - set_grid_count(4) → 4 GridCells + 2 QSplitter horizontaux
# - set_grid_count(0) → AssertionError (message correct)
# - set_grid_count(5) → AssertionError (message correct)
# - apply_preset("Analyse Full") → 4 grids, 4 sources correctes
# - apply_preset("inconnu") → log warning, aucune exception
# - Right-click GridCell → menu avec 8 sources
# - Changement source "heatmap" → _source_label mis à jour
# - update_frame(frame_blanc, {}) → pixmap dans chaque cell
# - on_result(NOK) → cell logo_zoom : highlight + zoom 4.0
# - on_result(OK) → toutes cells : pas highlight + zoom reset
# - _save_prefs() → ui_prefs.yaml contient grid_count + sources
# - load_from_prefs() → état restauré

# Anti-pattern QLabel pour frames
python3 -c "
import subprocess
r = subprocess.run(
    ['grep', '-n', 'QLabel', 'ts2i_ivs/ui/components/flexible_grid_view.py'],
    capture_output=True, text=True)
assert not r.stdout, f'Anti-pattern QLabel: {r.stdout}'
print('OK: aucun QLabel dans FlexibleGridView')
"

# SourceRenderer : toutes les 8 sources retournent un QPixmap non nul
python3 -c "
import numpy as np
from ui.components.source_renderer import SourceRenderer, GRID_SOURCES
frame = np.zeros((480,640,3), dtype=np.uint8)
for src in GRID_SOURCES:
    px = SourceRenderer.render(src, frame, {})
    assert not px.isNull(), f'{src}: pixmap null'
    print(f'OK {src}: {px.width()}x{px.height()}')
"
```

---

# ════════════════════════════════════════════════════════════════
# S30-v9 — SHORTCUT MANAGER CONFIGURABLE (RÉÉCRITURE BUG-09)
# ════════════════════════════════════════════════════════════════

## S30-v9 : Raccourcis configurables + persistance

```
📋 Objectif  : Tous les raccourcis modifiables sans redémarrage
⏱  Durée     : 1.5 jours
🔄 Action    : RÉÉCRIRE ui/shortcut_manager.py
🐛 Bugs fixés: BUG-09 (raccourcis non configurables)
📄 Règles    : GR-V9-4 (tous configurables)
📦 Dépend    : S25-v9
```

### 🤖 Prompt S30-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md GR-03, GR-05, GR-V9-4.

MISSION — Réécrire ui/shortcut_manager.py

════════════════════════════════════════════════════
FICHIER : ui/shortcut_manager.py  (RÉÉCRIRE)
════════════════════════════════════════════════════

PREFS_FILE = Path("config/ui_prefs.yaml")

# Touches système BLOQUÉES (non réassignables)
BLOCKED_KEYS: frozenset[str] = frozenset({
    "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z",
    "Ctrl+A", "Ctrl+S", "Alt+F4", "Ctrl+W",
    "Ctrl+Q", "Meta+Q",
})

@dataclass
class ShortcutDef:
    shortcut_id  : str    # ex: "start"
    label        : str    # ex: "Démarrer inspection"
    category     : str    # "Inspection"|"Navigation"|"Grids"|"Capture"
    default_key  : str    # ex: "F5"
    current_key  : str    # peut différer de default_key
    callback_name: str    # méthode à appeler dans MainWindow
    _qshortcut : QShortcut | None = field(
        default=None, repr=False, compare=False)

# 13 raccourcis DEFAULT_SHORTCUTS :
DEFAULT_SHORTCUTS = [
    # Inspection (4)
    ShortcutDef("start",    "Démarrer inspection",
                "Inspection","F5","F5","trigger_start"),
    ShortcutDef("stop",     "Arrêter inspection",
                "Inspection","F6","F6","trigger_stop"),
    ShortcutDef("val_ok",   "REVIEW → Valider OK",
                "Inspection","F7","F7","trigger_review_ok"),
    ShortcutDef("val_nok",  "REVIEW → Rejeter NOK",
                "Inspection","F8","F8","trigger_review_nok"),
    # Navigation (4)
    ShortcutDef("insp_mode","Mode Inspection plein écran",
                "Navigation","F11","F11","enter_inspection_mode"),
    ShortcutDef("exit_insp","Quitter mode Inspection",
                "Navigation","Escape","Escape","exit_inspection_mode"),
    ShortcutDef("help",     "Aide / liste raccourcis",
                "Navigation","F1","F1","show_help"),
    ShortcutDef("login",    "Changer d'opérateur",
                "Navigation","Ctrl+L","Ctrl+L","show_login"),
    # Grids (4)
    ShortcutDef("grid_1",   "1 Grid",
                "Grids","Ctrl+1","Ctrl+1","set_grid_1"),
    ShortcutDef("grid_2",   "2 Grids",
                "Grids","Ctrl+2","Ctrl+2","set_grid_2"),
    ShortcutDef("grid_3",   "3 Grids",
                "Grids","Ctrl+3","Ctrl+3","set_grid_3"),
    ShortcutDef("grid_4",   "4 Grids",
                "Grids","Ctrl+4","Ctrl+4","set_grid_4"),
    # Capture (1)
    ShortcutDef("capture",  "Capturer grid actif en PNG",
                "Capture","F9","F9","trigger_capture"),
]

class ShortcutManager(QObject):
    """
    Gère TOUS les raccourcis de l'application.
    GR-V9-4 : Tous configurables + persistés dans ui_prefs.yaml.

    INITIALISATION :
      __init__() :
        Copie DEFAULT_SHORTCUTS dans self._shortcuts dict[str, ShortcutDef]
        self._parent_widget = None
        self._callback_target = None
        _load_from_prefs()  ← applique customisations sauvegardées

    install_all(parent: QWidget, callback_target: object) :
      Stocke parent et callback_target.
      Pour chaque ShortcutDef dans self._shortcuts.values() :
        _install_one(sdef)

    _install_one(sdef: ShortcutDef) :
      Si sdef._qshortcut not None :
        sdef._qshortcut.setEnabled(False)
        sdef._qshortcut.deleteLater()
        sdef._qshortcut = None
      Si self._parent_widget is None → return
      qs = QShortcut(QKeySequence(sdef.current_key), parent_widget)
      callback = getattr(callback_target, sdef.callback_name, None)
      Si callback is None → log warning (méthode absente du target)
      Sinon → qs.activated.connect(callback)
      sdef._qshortcut = qs

    reassign(shortcut_id: str, new_key: str) → bool :
      Si shortcut_id absent de self._shortcuts → log error, return False
      Si new_key dans BLOCKED_KEYS → log warning, return False
      Si new_key déjà utilisée par autre shortcut → log warning, return False
      Sinon :
        sdef.current_key = new_key
        _install_one(sdef)
        _save_to_prefs()
        log info
        return True

    reset_to_defaults() :
      Pour chaque sdef :
        sdef.current_key = sdef.default_key
        _install_one(sdef)
      _save_to_prefs()

    get_all() → list[ShortcutDef] :
      Retourne list(self._shortcuts.values())

    get_by_category() → dict[str, list[ShortcutDef]] :
      Grouper par category

    get_help_text() → str :
      Texte formaté par catégorie :
        \n═══ {Catégorie} ═══
        {current_key:<12} {label}
        ...

    _save_to_prefs() :
      Lit yaml existant, ajoute/met à jour clé "shortcuts",
      réécrit le fichier yaml complet.
      "shortcuts" = dict {shortcut_id: current_key, ...}

    _load_from_prefs() :
      Lit "shortcuts" depuis yaml.
      Pour chaque (sid, key) sauvegardé :
        Si sid absent de self._shortcuts → ignorer
        Si key dans BLOCKED_KEYS → utiliser default_key
        Si key conflit avec autre already-assigned → utiliser default_key
        Sinon → sdef.current_key = key
      Gérer exceptions silencieusement (corrompus → défauts)
    """
```

### ✅ Gate S30-v9

```bash
pytest tests/ui/test_shortcut_manager.py -v

# - ShortcutManager() → 13 raccourcis chargés
# - get_by_category() → 4 catégories : Inspection/Navigation/Grids/Capture
# - reassign("start", "F9") → True, "start".current_key == "F9"
# - reassign("start", "Ctrl+C") → False (BLOCKED_KEYS)
# - reassign("start", "F6") → False (conflit avec "stop")
# - reassign("inconnu", "F9") → False
# - reset_to_defaults() → "start".current_key == "F5"
# - get_help_text() → contient "Inspection", "Navigation", "Grids"
# - _save_to_prefs() → ui_prefs.yaml["shortcuts"]["start"] == current_key
# - _load_from_prefs() après save → même current_key rechargé
# - BLOCKED_KEYS contient exactement les 10 touches listées
```

---

# ════════════════════════════════════════════════════════════════
# S20-v9 — INSPECTION SCREEN RÉÉCRITE (BUG-03 + BUG-07 + BUG-08)
# ════════════════════════════════════════════════════════════════

## S20-v9 : InspectionScreen v9 — FlexibleGrid + TelemetryPanel intégrés

```
📋 Objectif  : Réécrire InspectionScreen pour intégrer les composants v9
⏱  Durée     : 3 jours
🔄 Action    : RÉÉCRIRE ui/screens/inspection_screen.py
🐛 Bugs fixés: BUG-03 (grids QLabel), BUG-07 (telemetry), BUG-08 (flex grid)
📄 Règles    : GR-03, GR-05, GR-V9-1 (2 écrans)
📦 Dépend    : S25-v9, S28-v9, S29-v9, S30-v9 TOUS complétés
```

### 🤖 Prompt S20-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md intégralement.
Vérifier que TelemetryPanel, FlexibleGridView, ShortcutManager
sont déjà implémentés (S28/S29/S30-v9).

ANTI-PATTERNS INTERDITS dans ce fichier :
  ❌ QLabel pour afficher des frames caméra
  ❌ setStyleSheet() inline (thème via ThemeManager uniquement)
  ❌ Appel direct à pipeline/db (GR-03 → UIBridge uniquement)
  ❌ Création de thread (GR-05 → déjà géré ailleurs)
  ❌ 3 grids fixes avec sources hardcodées

MISSION — Réécrire ui/screens/inspection_screen.py

════════════════════════════════════════════════════
CLASSE : InspectionScreen(QWidget)
════════════════════════════════════════════════════

CONSTRUCTEUR :
  def __init__(self,
               system_controller,
               ui_bridge,
               shortcut_manager,
               compact_mode: bool = False,
               parent=None):
    super().__init__(parent)
    self._ctrl     = system_controller
    self._bridge   = ui_bridge
    self._shortcuts= shortcut_manager
    self._compact  = compact_mode
    self._trigger_timer = QTimer(self)
    self._trigger_timer.timeout.connect(self._on_timer_trigger)
    self._build_ui()
    self._connect_signals()

LAYOUT (compact_mode=False) — ControlBar PRÉSENTE :
  QVBoxLayout :
    ├─ _control_bar (QWidget, height=46px, objectName="ControlBar")
    └─ _body_splitter (QSplitter horizontal, handleWidth=1)
         ├─ _telemetry (TelemetryPanel, 200px fixe)
         └─ right_widget (QWidget)
              QVBoxLayout :
                ├─ _tier_row (QWidget, contient 3 TierVerdictBadge)
                ├─ _grid_view (FlexibleGridView, stretch=1)
                └─ _result_band (ResultBand)

LAYOUT (compact_mode=True) — SANS ControlBar :
  QVBoxLayout :
    └─ _body_splitter (identique, sans _control_bar au-dessus)

_build_control_bar() → QWidget :
  Contenu de gauche à droite :
    [▶ Démarrer  F5]  (objectName="BtnStart")
    [■ Arrêter  F6]   (objectName="BtnStop", enabled=False)
    │─────│
    QComboBox _mode_combo : ["⏱ Intervalle", "▶ Manuel"]
    QComboBox _interval_combo : ["1 s", "5 s", "10 s", "20 s", "Personnalisé…"]
      visible UNIQUEMENT si mode = Intervalle
      défaut : index 1 (5s)
    │─────│
    QComboBox _grid_combo : ["⊞ 1 Grid","⊞ 2 Grids","⊞ 3 Grids","⊞ 4 Grids"]
      défaut : index 1 (2 grids)
    QComboBox _preset_combo : list(GRID_PRESETS.keys())
    ──stretch──
    QLabel _product_label : "" (droite, objectName="ActiveProductLabel")

_build_tier_row() → QWidget :
  QHBoxLayout :
    TierVerdictBadge("CRITICAL")  (self._badge_critical)
    TierVerdictBadge("MAJOR")     (self._badge_major)
    TierVerdictBadge("MINOR")     (self._badge_minor)
    stretch

_connect_signals() :
  self._bridge.inspection_result.connect(self._on_result)
  self._bridge.frame_captured.connect(self._on_frame)
  self._bridge.system_state_changed.connect(self._on_state_changed)
  self._bridge.pipeline_metrics.connect(self._on_pipeline_metrics)
  Si compact_mode=False :
    self._btn_start.clicked.connect(self._on_start_clicked)
    self._btn_stop.clicked.connect(self._on_stop_clicked)
    self._mode_combo.currentIndexChanged.connect(self._on_trigger_mode_changed)
    self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
    self._grid_combo.currentIndexChanged.connect(self._on_grid_count_changed)
    self._preset_combo.currentTextChanged.connect(self._grid_view.apply_preset)

SLOTS (@pyqtSlot) :

_on_result(result: FinalResult) :
  self._result_band.update(result)
  self._badge_critical.update_from_result(result, "CRITICAL")
  self._badge_major.update_from_result(result, "MAJOR")
  self._badge_minor.update_from_result(result, "MINOR")
  self._telemetry.update_from_result(result)
  self._grid_view.on_result(result)

_on_frame(frame: np.ndarray, metadata: dict) :
  self._telemetry.update_image_quality(frame, metadata)
  self._grid_view.update_frame(frame, metadata)

_on_state_changed(state: SystemState) :
  running = (state == SystemState.RUNNING)
  Si compact_mode=False :
    self._btn_start.setEnabled(not running)
    self._btn_stop.setEnabled(running)
    self._mode_combo.setEnabled(not running)
    self._interval_combo.setEnabled(not running)

_on_pipeline_metrics(metrics: dict) :
  metrics format : {"avg_ms":142.0, "fps":28.0,
                    "SIFT":38.0, "YOLO":61.0, ...}
  self._telemetry.update_pipeline(
      {k:v for k,v in metrics.items() if k not in ("avg_ms","fps")},
      metrics.get("avg_ms",0.0),
      metrics.get("fps",0.0))

_on_start_clicked() :
  self._ctrl.start_inspection()  # GR-03

_on_stop_clicked() :
  self._ctrl.stop_inspection()

_on_trigger_mode_changed(index: int) :
  is_interval = (index == 0)
  self._interval_combo.setVisible(is_interval)
  Si is_interval :
    self._trigger_timer.start(self._get_interval_ms())
  Sinon :
    self._trigger_timer.stop()

_on_interval_changed(index: int) :
  Si self._trigger_timer.isActive() :
    self._trigger_timer.start(self._get_interval_ms())

_get_interval_ms() → int :
  mapping = {0:1000, 1:5000, 2:10000, 3:20000}
  Retourner mapping.get(self._interval_combo.currentIndex(), 5000)

_on_grid_count_changed(index: int) :
  self._grid_view.set_grid_count(index + 1)

_on_timer_trigger() :
  self._ctrl.trigger_once()

API publique :
  set_active_product(name, version) :
    self._product_label.setText(f"🪞 {name}  v{version}")
  get_telemetry_panel() → TelemetryPanel
  get_grid_view() → FlexibleGridView
```

### ✅ Gate S20-v9

```bash
pytest tests/ui/test_inspection_screen_v9.py -v

# - InspectionScreen(ctrl, bridge, shortcuts) instanciable
# - compact_mode=False → _control_bar présent dans layout
# - compact_mode=True → pas de _control_bar
# - _on_result(FinalResult OK) → result_band + badges mis à jour
# - _on_frame(frame, {}) → grid_view.update_frame() appelé
# - _on_state_changed(RUNNING) → btn_start disabled, btn_stop enabled
# - _on_state_changed(IDLE) → btn_start enabled, btn_stop disabled
# - mode_combo index=0 (Intervalle) → timer démarré
# - mode_combo index=1 (Manuel) → timer arrêté
# - interval_combo index=0 → interval 1000ms
# - grid_combo index=3 → grid_view.set_grid_count(4) appelé
# - set_active_product("P208","3.1") → product_label mis à jour

# Anti-patterns
python3 -c "
import subprocess
# Aucun QLabel pour frames
r = subprocess.run(
    ['grep','-n','QLabel','ts2i_ivs/ui/screens/inspection_screen.py'],
    capture_output=True, text=True)
frame_labels = [l for l in r.stdout.splitlines()
                if any(kw in l.lower()
                       for kw in ['frame','grid','camera','live'])]
assert not frame_labels, f'Anti-pattern QLabel: {frame_labels}'
print('OK: aucun QLabel pour frames')

# Aucun setStyleSheet inline
r2 = subprocess.run(
    ['grep','-n','setStyleSheet',
     'ts2i_ivs/ui/screens/inspection_screen.py'],
    capture_output=True, text=True)
assert not r2.stdout, f'setStyleSheet inline: {r2.stdout}'
print('OK: aucun setStyleSheet inline')
"
```

---

# ════════════════════════════════════════════════════════════════
# S21-v9 — WIZARD PRODUIT RÉÉCRIT (BUG-04 + BUG-10)
# ════════════════════════════════════════════════════════════════

## S21-v9 : Wizard 9 étapes avec image logo obligatoire

```
📋 Objectif  : Wizard complet incluant saisie image logo à chaque logo
⏱  Durée     : 4 jours
🔄 Action    : CRÉER logo_form_widget.py + product_definition_wizard.py
🐛 Bugs fixés: BUG-04 (wizard sans image), BUG-10 (reference_image absent)
📄 Règles    : GR-V9-5 (logo image obligatoire), GR-12 (FORBIDDEN RUNNING)
📦 Dépend    : S22-B (ProductCanvas existant), S25-v9
```

### 🤖 Prompt S21-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md GR-12, GR-V9-5.
Vérifier ProductCanvas (S22-B) + LogoDefinition dans core/models.py.

MISSION — Créer :

════════════════════════════════════════════════════
FICHIER 1 : ui/components/logo_form_widget.py  (CRÉER)
════════════════════════════════════════════════════

class LogoFormWidget(QGroupBox):
    """
    Formulaire pour un logo unique dans le wizard.
    GR-V9-5 : image de référence OBLIGATOIRE.

    CHAMPS :
      Nom       : QLineEdit, placeholder "Ex: Logo Lion", min 1 char
      Image réf : QPushButton "📁 Charger image…" + QLabel preview 80×80px
                  ⚠ Image OBLIGATOIRE — label "⚠ Image obligatoire (GR-V9-5)"
                    visible par défaut, caché après chargement réussi
      Largeur   : QDoubleSpinBox [10.0..1000.0] step=1.0 défaut=120.0 suffix=" mm"
      Hauteur   : QDoubleSpinBox [10.0..1000.0] step=1.0 défaut=80.0 suffix=" mm"
      Couleur   : QPushButton [████] + QLabel "#RRGGBB"
                  QColorDialog on click
      Tolérance ΔE : QDoubleSpinBox [0.0..50.0] step=0.5 défaut=8.0
      Tolérance pos: QDoubleSpinBox [0.0..50.0] step=0.5 défaut=5.0 suffix=" mm"
      Obligatoire  : QCheckBox, coché par défaut
      [🗑 Supprimer] : QPushButton objectName="BtnDanger"

    SIGNALS :
      logoChanged(int)  → index du logo modifié
      logoDeleted(int)  → index du logo supprimé

    _on_load_image() :
      QFileDialog.getOpenFileName filtres : "Images (*.png *.jpg *.jpeg *.bmp *.tiff)"
      Si fichier choisi :
        1. Charger en QPixmap
        2. Si QPixmap.isNull() → QMessageBox.warning + return
        3. Copier vers self._tmp_dir / f"logo_{self._index}.png"
           (QPixmap.save(str(dest), "PNG"))
        4. self._image_path = str(dest)
        5. Preview : scaled(80,80, KeepAspectRatio, SmoothTransformation)
        6. self._img_required_label.hide()
        7. Émettre logoChanged(self._index)

    validate() → list[str] :
      Retourne liste d'erreurs. Vide = valide.
      Contrôles :
        Si self._image_path is None :
          "Logo #{index+1} : image de référence obligatoire (GR-V9-5)"
        Si self._name_input.text().strip() == "" :
          "Logo #{index+1} : nom obligatoire"

    to_logo_definition() → LogoDefinition :
      ⚠ Appeler validate() AVANT. Ne pas appeler si validate() non vide.
      Retourner LogoDefinition(frozen) avec :
        logo_id          = f"logo_{self._index}"
        logo_index       = self._index
        label            = self._name_input.text().strip()
        reference_image  = self._image_path    ← GR-V9-5, jamais None ici
        width_mm         = self._width_spin.value()
        height_mm        = self._height_spin.value()
        position_relative= (0.5, 0.5)           ← mis à jour par Canvas
        tolerance_mm     = self._pos_tol_spin.value()
        color_hex        = self._color_hex
        color_tolerance_de = self._de_spin.value()
        mandatory        = self._mandatory_check.isChecked()

    load_from_definition(logo_def: LogoDefinition) :
      Pré-remplir tous les champs depuis un LogoDefinition existant.
      Si logo_def.reference_image existe et le fichier est présent :
        Afficher preview + cacher _img_required_label

════════════════════════════════════════════════════
FICHIER 2 : ui/screens/product_definition_wizard.py  (CRÉER)
════════════════════════════════════════════════════

TMP_LOGOS_DIR = Path("data/tmp_logos")

class ProductDefinitionWizard(QWizard):
    """
    Wizard 9 pages pour créer ou éditer un produit.
    productSaved(ProductDefinition) émis à l'accept().

    PAGES (index 0 à 8) :
      0 : Métadonnées (nom, ID, version, barcode, station)
      1 : Dimensions (width_mm, height_mm)
      2 : Images référence (GOOD ≥1, BAD optionnel)
      3 : Définition logos (LogoFormWidget × N)  ← NOUVEAU
      4 : Canvas positionnement (ProductCanvas)
      5 : Critères Tier (TierPriorityWidget — v7 inchangé)
      6 : Zones ROI (RoiEditorWidget — v7 inchangé)
      7 : Calibration (CalibrationEngine UI — v7 inchangé)
      8 : Entraînement AI (v7 inchangé)

    ATTRIBUTS CLÉS :
      self._logo_widgets : list[LogoFormWidget]
      self._tmp_dir : Path (uuid unique par wizard)
      self._canvas : ProductCanvas (page 4)

    __init__(system_controller, product_id=None, parent=None) :
      product_id non None → mode édition (pré-chargement données)
      ⚠ GR-12 : Si SystemState == RUNNING → bloquer l'ouverture
        (vérifier dans __init__ avant d'afficher)

    PAGE 3 _build_page_3_logos() :
      QPushButton "+ Ajouter un logo" (connecté à _add_logo_form)
      QScrollArea → QWidget container → QVBoxLayout + stretch
      _add_logo_form() appelé 1 fois dans __init__ (logo par défaut)

    _add_logo_form() :
      Si len(_logo_widgets) >= 10 → QMessageBox.warning "Max 10 logos" + return
      Créer LogoFormWidget(index, self._tmp_dir)
      Connecter logoDeleted → _remove_logo_form
      Insérer dans layout avant stretch

    _remove_logo_form(index) :
      Si len(_logo_widgets) <= 1 → QMessageBox.warning "Min 1 logo" + return
      Supprimer widget
      Réindexer (_index et titre) les widgets restants

    validateCurrentPage() → bool :
      page 0 :
        Si _input_name.text().strip() vide → warning + return False
        Si _input_id.text().strip() vide → warning + return False
      page 3 :
        Si pas de logos → warning + return False
        Collecter toutes les erreurs de tous les validate()
        Si erreurs → QMessageBox.warning avec liste + return False
        Si OK → appeler self._canvas.load_logo_definitions(
                   [w.to_logo_definition() for w in self._logo_widgets])
      Autres pages → return True

    accept() :
      1. Collecter données de toutes les pages
      2. Construire logo_defs = [w.to_logo_definition() ...]
      3. Pour chaque logo_def :
           Copier image de _tmp_dir vers products/{id}/logos/logo_{idx}.png
           Mettre à jour reference_image dans LogoDefinition
      4. Construire ProductDefinition complet
      5. Sauvegarder products/{id}/config.json
      6. Émettre productSaved(product_def)
      7. Nettoyer _tmp_dir (shutil.rmtree)
      8. super().accept()
    """
    productSaved = pyqtSignal(object)   # ProductDefinition
```

### ✅ Gate S21-v9

```bash
pytest tests/ui/test_product_wizard_v9.py -v

# - LogoFormWidget sans image → validate() → ["...obligatoire (GR-V9-5)"]
# - LogoFormWidget après load image → validate() → []
# - to_logo_definition().reference_image → str non vide, fichier existant
# - Wizard page 3 : logo sans image → validateCurrentPage() False
# - Wizard page 3 : logo avec image → validateCurrentPage() True
# - _add_logo_form() × 10 → OK
# - _add_logo_form() × 11 → warning + rien ajouté
# - _remove_logo_form(0) si seul logo → warning + rien supprimé
# - accept() → ProductDefinition.logo_definitions[0].reference_image non None
# - accept() → fichier copié dans products/{id}/logos/logo_0.png
# - accept() → productSaved émis

python3 -c "
# Vérifier GR-V9-5 : reference_image jamais None dans to_logo_definition
from ui.components.logo_form_widget import LogoFormWidget
from pathlib import Path
import tempfile

# Simuler un LogoFormWidget avec image
tmp = Path(tempfile.mkdtemp())
w = LogoFormWidget(0, tmp)
w._name_input.setText('Lion')
# Sans image → validate() doit retourner une erreur
errors = w.validate()
assert any('GR-V9-5' in e for e in errors), \
    f'validate() devrait retourner erreur GR-V9-5, got: {errors}'
print('OK: validate() retourne erreur GR-V9-5 si pas image')
"
```

---

# ════════════════════════════════════════════════════════════════
# S27-v9 — OPERATORS UI (COMPLÉTION BUG-06)
# ════════════════════════════════════════════════════════════════

## S27-v9 : LoginDialog + OperatorsScreen + OperatorCard + OperatorFormDialog

```
📋 Objectif  : Interface opérateurs complète (login + CRUD complet)
⏱  Durée     : 2 jours
🔄 Action    : CRÉER les 4 fichiers UI opérateurs
🐛 Bugs fixés: BUG-06 (interface opérateurs absente)
📄 Règles    : GR-V9-7 (PIN jamais affiché/loggué)
📦 Dépend    : S26-v9 (OperatorManager fonctionnel)
```

### 🤖 Prompt S27-v9

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md GR-03, GR-05, GR-V9-7.
OperatorManager (S26-v9) est déjà implémenté et fonctionnel.

MISSION — Créer ces 4 fichiers :

════════════════════════════════════════════════════
FICHIER 1 : ui/screens/login_dialog.py
════════════════════════════════════════════════════

class LoginDialog(QDialog):
    """
    Dialog connexion PIN opérateur.
    Affiché au démarrage et via Ctrl+L (ShortcutManager).
    Modal = True.

    SÉCURITÉ :
      MAX_ATTEMPTS = 3
      LOCKOUT_SECONDS = 30
      Après 3 échecs → bouton disabled, champ disabled, timer 30s
      ⚠ GR-V9-7 : Ne JAMAIS logguer le PIN brut
         Même pas "PIN incorrect: 1234" ou similaire

    LAYOUT :
      QVBoxLayout :
        QLabel "Sélectionner un opérateur :"
        QListWidget _op_list (height=160px, un item par opérateur actif)
          Format item : "{icon_role} {nom} — {rôle capitalisé}"
          Icônes : ADMIN=🔴, OPERATOR=🟡, VIEWER=🟢
          data(UserRole) = operator_id (str)
          Triés par nom ASC
        QLabel "PIN :"
        QLineEdit _pin_input
          echoMode = Password
          maxLength = 6
          returnPressed → _on_login()
        QLabel _error_label (rouge, caché par défaut)
        QHBoxLayout :
          stretch
          QPushButton "Annuler" → reject()
          QPushButton "Connexion" (default=True) → _on_login()

    SIGNAL : loginSuccess = pyqtSignal(object)   # Operator

    _on_login() :
      Si self._locked → return
      Si pas de sélection dans _op_list → _show_error("Sélectionner un opérateur.") + return
      op_id = item.data(UserRole)
      pin = self._pin_input.text()
      op = self._manager.authenticate(op_id, pin)
      Si op is None :
        self._attempts += 1
        remaining = MAX_ATTEMPTS - self._attempts
        Si remaining <= 0 → _lockout()
        Sinon → _show_error(f"PIN incorrect. {remaining} tentative(s) restante(s).")
      Sinon :
        self._attempts = 0
        self.loginSuccess.emit(op)
        self.accept()
      Dans tous les cas : self._pin_input.clear() + setFocus()

    _lockout() :
      self._locked = True
      self._btn_login.setEnabled(False)
      self._pin_input.setEnabled(False)
      _show_error(f"Trop de tentatives. Attendre {LOCKOUT_SECONDS}s.")
      QTimer.singleShot(LOCKOUT_SECONDS * 1000, self._unlock)

    _unlock() :
      self._locked = False ; self._attempts = 0
      self._btn_login.setEnabled(True)
      self._pin_input.setEnabled(True)
      self._error_label.hide()

════════════════════════════════════════════════════
FICHIER 2 : ui/screens/operators_screen.py
════════════════════════════════════════════════════

class OperatorsScreen(QWidget):
    """
    Page gestion opérateurs (Tab "👥 Opérateurs").
    Visible uniquement si ADMIN (MainWindow vérifie permissions).

    LAYOUT :
      QVBoxLayout :
        QHBoxLayout header :
          QPushButton "+ Nouvel Opérateur" (objectName="BtnPrimary")
          stretch
          QLineEdit _search_input ("🔍 Rechercher…", maxWidth=220)
        QScrollArea :
          QWidget _container
            QVBoxLayout _list_layout : OperatorCard × N + stretch

    refresh() :
      Vider _list_layout (sauf stretch)
      Charger _manager.get_summaries()
      Trier : actifs en premier, puis par nom ASC
      Créer OperatorCard pour chaque summary
      Connecter signaux : editRequested → _on_edit,
        deleteRequested → _on_delete,
        toggleActiveRequested → _on_toggle_active,
        resetPinRequested → _on_reset_pin
      Insérer dans layout avant stretch

    _on_search(text) :
      Filtrer cartes par text dans nom (insensible casse)
      card.setVisible(matches)

    _on_delete(operator_id) :
      QMessageBox.question "Confirmer suppression"
        Mentionner "statistiques conservées (audit trail)"
        Boutons : Yes | No, défaut = No
      Si Yes → _manager.delete() → refresh()
      Attraper OperatorError → QMessageBox.critical(str(e))

    _on_toggle_active(operator_id, active) :
      _manager.update(operator_id, active=active) → refresh()
      Attraper OperatorError → QMessageBox.critical(str(e))

    _on_reset_pin(operator_id) :
      QInputDialog.getText mode Password "Nouveau PIN (4 à 6 chiffres)"
      Si ok et new_pin :
        _manager.change_pin(operator_id, new_pin)
        QMessageBox.information "PIN modifié."
        Attraper ValueError → QMessageBox.warning(str(e))
      ⚠ GR-V9-7 : Ne pas logguer new_pin

════════════════════════════════════════════════════
FICHIER 3 : ui/components/operator_card.py
════════════════════════════════════════════════════

class OperatorCard(QFrame):
    """
    Carte affichage opérateur dans OperatorsScreen.

    SIGNALS :
      editRequested(str)               → operator_id
      deleteRequested(str)             → operator_id
      toggleActiveRequested(str, bool) → operator_id, new_active
      resetPinRequested(str)           → operator_id

    LAYOUT (QVBoxLayout, contentsMargins=14,12,14,12) :
      Ligne 1 : "👤 {nom}"  | stretch | "{icône_rôle} {RÔLE}" | "● Actif"/"○ Inactif"
      Ligne 2 : "ID: {id}  |  Inspections: {total}  |  Taux OK: {taux:.1f}%"
      Ligne 3 : "Dernière connexion : {il y a X min/h/jour}"
                Si last_login None → "jamais connecté"
      Ligne 4 : [✏ Modifier] [🔑 Reset PIN] [● Activer/○ Désactiver] [🗑 Supprimer]

    ICÔNES rôle : ADMIN=🔴, OPERATOR=🟡, VIEWER=🟢

    Bouton Toggle :
      Si summary.active → "○ Désactiver"
      Sinon → "● Activer"

    Propriété : operator_name → self._summary.name (pour filtrage)
    """
    editRequested         = pyqtSignal(str)
    deleteRequested       = pyqtSignal(str)
    toggleActiveRequested = pyqtSignal(str, bool)
    resetPinRequested     = pyqtSignal(str)

════════════════════════════════════════════════════
FICHIER 4 : ui/screens/operator_form_dialog.py
════════════════════════════════════════════════════

class OperatorFormDialog(QDialog):
    """
    Dialog création/édition opérateur.

    Mode création (operator_id=None) :
      Tous les champs vides. PIN obligatoire.

    Mode édition (operator_id donné) :
      Champs pré-remplis. PIN optionnel (vide = inchangé).

    LAYOUT :
      Nom      : QLineEdit, placeholder "Prénom Nom"
      Rôle     : QComboBox (Admin, Operator, Viewer)
      PIN      : QGroupBox "PIN" (ou "PIN (laisser vide = inchangé)")
                   QLineEdit _pin_input (Password, maxLength=6)
                   QLineEdit _pin_confirm (Password, maxLength=6)
      Actif    : QCheckBox "Compte actif" (coché par défaut)
      Boutons  : [Annuler] [💾 Enregistrer]

    _on_save() validation :
      nom vide → warning "Nom obligatoire"
      En création : pin vide → warning "PIN obligatoire"
      En création/si pin renseigné :
        pin != pin_confirm → warning "PIN ne correspondent pas" + clear + return
        not pin.isdigit() or not (4<=len(pin)<=6) → warning "PIN 4 à 6 chiffres"

    _on_save() sauvegarde :
      Mode création :
        op = _manager.create(name, role, pin)
        Si not active : _manager.update(op.operator_id, active=False)
      Mode édition :
        op = _manager.update(operator_id, name=name, role=role, active=active)
        Si pin non vide : _manager.change_pin(operator_id, pin)
      Émettre operatorSaved(op)
      self.accept()
      Attraper OperatorError → QMessageBox.critical(str(e))

    SIGNAL : operatorSaved = pyqtSignal(object)   # Operator
    """
```

### ✅ Gate S27-v9

```bash
pytest tests/ui/test_operators_ui.py -v

# - LoginDialog : opérateurs actifs affichés, inactifs cachés
# - LoginDialog : PIN correct → loginSuccess émis
# - LoginDialog : PIN incorrect 3× → locked, bouton disabled
# - LoginDialog : après 30s → unlocked
# - OperatorsScreen.refresh() → cartes créées
# - Recherche → filtre par setVisible
# - Delete confirm → delete() appelé + refresh()
# - Delete dernier ADMIN → OperatorError → message affiché (pas de crash)
# - OperatorFormDialog création : PIN vide → bloqué
# - OperatorFormDialog création : PIN != confirm → bloqué
# - OperatorFormDialog création valide → create() appelé
# - OperatorFormDialog édition PIN vide → change_pin() NON appelé
# - OperatorFormDialog édition PIN renseigné → change_pin() appelé
```

---

# ════════════════════════════════════════════════════════════════
# S31 — MAINWINDOW v9 (NOUVELLE SESSION)
# ════════════════════════════════════════════════════════════════

## S31 : MainWindow v9 — 2 écrans (Navigation + Inspection F11/Esc)

```
📋 Objectif  : Assembler tous les composants v9 dans MainWindow
⏱  Durée     : 3 jours
🆕 Statut    : NOUVELLE SESSION
📄 Règles    : GR-V9-1 (2 écrans), GR-V9-8 (tabs North), GR-03
📦 Dépend    : TOUTES sessions précédentes (S20-v9 → S30-v9)
```

### 🤖 Prompt S31

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md intégralement.
Toutes les sessions S20-v9 → S30-v9 sont implémentées.

MISSION — Réécrire ui/main_window.py

GR-V9-1 : QStackedWidget central avec 2 widgets :
  Index 0 → NavigationWidget (tabs + content variable)
  Index 1 → InspectionWidget (InspectionScreen plein écran)

GR-V9-8 : NavigationBar avec tabs NORTH (QTabBar horizontal).

ARCHITECTURE COMPLÈTE :

QMainWindow
  ├─ centralWidget : QStackedWidget self._main_stack
  │    ├─ [0] NavigationWidget
  │    │    QVBoxLayout :
  │    │      NavigationBar (tabs horizontaux)
  │    │      QWidget body
  │    │        QVBoxLayout :
  │    │          QStackedWidget self._content_stack
  │    │            [0] InspectionScreen (compact_mode=False)
  │    │            [1] ProductsScreen
  │    │            [2] OperatorsScreen
  │    │            [3] ReportsScreen (placeholder si absent)
  │    │            [4] GPIODashboardScreen
  │    │            [5] FleetScreen
  │    │            [6] SettingsWidget
  │    └─ [1] InspectionWidget (plein écran)
  │         QVBoxLayout :
  │           InspectionTopbar (compact)
  │           InspectionScreen (compact_mode=True, MÊME instance que [0])
  └─ statusBar() : MainStatusBar

⚠ MÊME InspectionScreen réutilisée dans les 2 stacks.
  enter_inspection_mode() : déplacer l'instance vers _main_stack[1]
  exit_inspection_mode()  : déplacer l'instance vers _content_stack[0]

MÉTHODES PUBLIQUES (appelées par ShortcutManager) :
  trigger_start(), trigger_stop()
  trigger_review_ok(), trigger_review_nok()
  enter_inspection_mode(), exit_inspection_mode()
  set_grid_1(), set_grid_2(), set_grid_3(), set_grid_4()
  show_help(), show_login(), trigger_capture()

_on_tab_activated(tab_name: str) :
  PERMISSIONS :
    "operators" → requires "operator.view"
    "settings"  → requires "settings.view"
  Si permission refusée → QMessageBox.warning + return
  TAB_INDEX = {"inspection":0, "products":1, "operators":2,
               "reports":3, "gpio":4, "fleet":5, "settings":6}
  self._content_stack.setCurrentIndex(TAB_INDEX[tab_name])

_on_login_success(operator) :
  self._op_manager.set_current(operator)
  self._status_bar.set_operator(operator)
  self._nav_bar.refresh_for_role(operator.role)

════ NavigationBar(QWidget) ════

Tabs horizontaux (QTabBar, position North — GR-V9-8) :
  [🔍 Inspection] [📦 Produits] [👥 Opérateurs]
  [📊 Rapports] [📡 GPIO] [🚀 Fleet] [⚙ Paramètres]

Signal : tabActivated(str)   # tab_name

refresh_for_role(role) :
  ADMIN   → tous tabs visibles
  OPERATOR → cacher "operators" et "settings"
  VIEWER  → cacher "operators", "settings", "gpio"

════ MainStatusBar(QStatusBar) ════

Contenu permanent :
  "👤 {nom} [{RÔLE}]  |  CPU {cpu}%  |  RAM {ram:.1f}GB  |  
   TEMP {temp:.0f}°C  |  FPS {fps:.0f}  |  UP {uptime}  |  v9.0.0"

set_operator(operator) : mettre à jour partie gauche
update_system(metrics: dict) :
  metrics = {"cpu_percent":62.0, "ram_gb":3.2,
             "cpu_temp_c":58.0, "fps":28.0,
             "uptime_str":"4h12m", "disk_free_gb":45.0}
  Couleurs : vert/orange/rouge selon seuils §43

════ SettingsWidget(QWidget) ════

QTabWidget (tabPosition=North — GR-V9-8) avec 5 tabs :
  "🎨 Apparence" :
    Label "Thème :"
    QComboBox ["☀ Light", "🌙 Dark"]
    currentChanged → ThemeManager.instance().apply(theme_name)

  "⌨ Raccourcis" :
    QTableWidget colonnes : Catégorie | Action | Touche | [Changer]
    Peuplé depuis ShortcutManager.get_by_category()
    Bouton [Changer] → KeyCaptureDialog → ShortcutManager.reassign()
    Bouton [🔄 Défauts] → ShortcutManager.reset_to_defaults()

  "⚙ Inspection" :
    Intervalle défaut, mode déclenchement défaut
    Connexion vers config.yaml

  "📷 Caméra" :
    Paramètres caméra (config existante)

  "🤖 AI / Modèles" :
    Versions modèles + bouton réentraînement
```

### ✅ Gate S31

```bash
pytest tests/ui/test_main_window_v9.py -v

# - MainWindow instanciable sans erreur
# - QStackedWidget avec 2 widgets
# - F11 → _main_stack.currentIndex() == 1
# - Escape → _main_stack.currentIndex() == 0
# - Tab "Opérateurs" sans opérateur connecté → accès refusé
# - Login ADMIN → tab "Opérateurs" accessible
# - ShortcutManager.install_all() appelé → 13 raccourcis
# - _on_login_success(op) → status_bar affiche nom
# - SettingsWidget.tabs.tabPosition() == North (GR-V9-8)
# - NavigationBar tabs horizontaux (pas verticaux)
# - Aucun setStyleSheet inline dans main_window.py

python3 ts2i_ivs/main.py --check
# → ✅ ALL SYSTEMS GO
```

---

# ════════════════════════════════════════════════════════════════
# S32 — PRODUCTS MANAGEMENT SCREEN (NOUVELLE SESSION)
# ════════════════════════════════════════════════════════════════

## S32 : Page Produits — CRUD + ProductManager

```
📋 Objectif  : Gestion produits complète (liste, ajout, edit, delete, duplicate)
⏱  Durée     : 2 jours
🆕 Statut    : NOUVELLE SESSION
📄 Règles    : GR-V9-6 (FORBIDDEN si RUNNING + actif)
📦 Dépend    : S21-v9 (Wizard), S26-v9 (permissions), S31
```

### 🤖 Prompt S32

```
Tu es ingénieur senior Python industriel — TS2I IVS v9.0.
Lire CLAUDE.md GR-03, GR-12, GR-V9-6.

MISSION — Créer :
  ui/screens/products_screen.py
  ui/components/product_card.py
  core/product_manager.py

════════════════════════════════════════════════════
ProductsScreen(QWidget)
════════════════════════════════════════════════════

LAYOUT :
  QVBoxLayout :
    QHBoxLayout header :
      QPushButton "+ Nouveau Produit" (objectName="BtnPrimary")
      stretch
      QLineEdit _search ("🔍 Rechercher…", maxWidth=220)
    QScrollArea → QWidget → QVBoxLayout + ProductCard × N

_on_add() :
  Ouvrir ProductDefinitionWizard(self._controller)
  Connecter productSaved → _on_product_saved

_on_edit(product_id) :
  ⚠ GR-V9-6 : Si _controller.is_running() ET
               product_id == _controller.active_product_id :
    QMessageBox.warning "Impossible de modifier pendant inspection."
    return
  Ouvrir ProductDefinitionWizard(self._controller, product_id=product_id)

_on_delete(product_id) :
  ⚠ GR-V9-6 : même vérification que _on_edit
  QMessageBox.question "Supprimer {nom} ?"
    "Les inspections historiques seront conservées."
    Boutons : Yes | No, défaut = No
  Si Yes → _product_manager.delete(product_id) → refresh()

_on_duplicate(product_id) :
  new_name = f"Copie de {original_name}"
  new_id = _product_manager.duplicate(product_id, new_name)
  refresh()

_on_activate(product_id) :
  self._controller.set_active_product(product_id)
  refresh()   # mettre à jour les cartes (actif/inactif)

_on_search(text) :
  Filtrer cartes par text dans nom/ID (setVisible)

════════════════════════════════════════════════════
ProductCard(QFrame)
════════════════════════════════════════════════════

SIGNALS :
  editRequested(str), deleteRequested(str),
  duplicateRequested(str), exportRequested(str),
  activateRequested(str)

LAYOUT QVBoxLayout (contentsMargins=14,12,14,12) :
  Ligne 1 : "🪞 {nom} v{version}" | stretch | "● Actif"/"○ Inactif"
  Ligne 2 : "ID: {id}  |  {Xmm}×{Ymm}mm  |  {N} logo(s)"
  Ligne 3 : "Inspections: {total}  |  OK: {ok:.1f}%  |  NOK: {nok}"
  Ligne 4 : "Modèles : {versions}" (si disponible)
  Ligne 5 : "Dernière inspection : {texte relatif}"
  Ligne 6 : [✏ Modifier] [📋 Dupliquer] [📤 Export] [🗑 Supprimer]
             [● Activer] ou ["✓ Actif" disabled] si déjà actif

Produit actif → setProperty("active", True) pour QSS (bordure accent)

════════════════════════════════════════════════════
ProductManager CRUD
════════════════════════════════════════════════════

class ProductManager:

  list_all() → list[ProductSummary] :
    Charger depuis DB + lire products/*/config.json
    Joindre avec stats depuis TABLE inspections

  get(product_id) → ProductDefinition :
    Lire products/{product_id}/config.json

  delete(product_id) → None :
    ⚠ GR-V9-6 : Vérifier SystemState != RUNNING
                ou product_id != active_product_id
    Supprimer products/{product_id}/ (shutil.rmtree)
    ⚠ NE PAS supprimer les inspections DB liées (audit trail)

  duplicate(source_id, new_name=None) → str :
    new_id = f"{source_id}_copy_{int(time.time())}"
    shutil.copytree(products/{source_id}, products/{new_id})
    Lire config.json → modifier name + product_id → réécrire
    Retourner new_id

  get_stats(product_id) → dict :
    SELECT COUNT(*), SUM(verdict='OK'), SUM(verdict='NOK')
    FROM inspections WHERE product_id=?
    Retourner {total, ok, nok, taux_ok, last_date}
```

### ✅ Gate S32

```bash
pytest tests/ui/test_products_screen.py -v

# - ProductsScreen : cartes créées depuis ProductManager.list_all()
# - "+ Nouveau" → ProductDefinitionWizard ouvert
# - Recherche "P208" → filtre par setVisible
# - "Modifier" + RUNNING + actif → warning GR-V9-6
# - "Supprimer" confirm → delete() → carte disparaît
# - Inspections DB conservées après delete()
# - "Dupliquer" → nouveau produit "Copie de..." dans liste
# - "Activer" → carte marquée "● Actif"
# - ProductManager.delete() : dossier products/{id} supprimé
# - ProductManager.duplicate() : dossier copié, new_id retourné
```

---

# ════════════════════════════════════════════════════════════════
# VALIDATION FINALE v9.0
# ════════════════════════════════════════════════════════════════

```bash
# ═══════════════════════════════════════════
# 1. TESTS AUTOMATIQUES
# ═══════════════════════════════════════════
pytest tests/ -v --tb=short

# ═══════════════════════════════════════════
# 2. VÉRIFICATIONS ANTI-PATTERNS
# ═══════════════════════════════════════════

echo "=== BUG-01 : Aucun setStyleSheet inline ==="
grep -rn "setStyleSheet" ts2i_ivs/ui/ --include="*.py" \
  | grep -v "theme_manager.py" | grep -v "^.*#" | grep -v "test_"
# → DOIT être vide

echo "=== BUG-02 : Aucun TabPosition West/East/South ==="
grep -rn "TabPosition.West\|TabPosition.East\|TabPosition.South" \
  ts2i_ivs/ui/ --include="*.py"
# → DOIT être vide

echo "=== BUG-03 : Aucun QLabel pour frames ==="
grep -rn "QLabel" ts2i_ivs/ui/screens/inspection_screen.py \
  | grep -i "frame\|camera\|grid\|live\|raw"
# → DOIT être vide

echo "=== GR-V9-7 : Aucun PIN en clair dans logs ==="
grep -rn "logger\|print" ts2i_ivs/core/ ts2i_ivs/storage/ \
  --include="*.py" | grep -i "pin" | grep -v "pin_hash\|# "
# → DOIT être vide

echo "=== GR-V9-5 : reference_image dans config.json ==="
python3 -c "
import json
from pathlib import Path
count = 0
for cfg in Path('products').glob('*/config.json'):
    data = json.load(open(cfg))
    for logo in data.get('logo_definitions', []):
        assert logo.get('reference_image'), \
            f'reference_image manquant dans {cfg}'
        count += 1
print(f'OK: {count} logo(s) avec reference_image')
"

echo "=== GR-V9-8 : Tabs North dans SettingsWidget ==="
python3 -c "
from PyQt6.QtWidgets import QApplication, QTabWidget
import sys
app = QApplication.instance() or QApplication(sys.argv)
# Import et vérification SettingsWidget
from ui.main_window import SettingsWidget
from unittest.mock import MagicMock
sw = SettingsWidget(MagicMock(), MagicMock(), MagicMock())
tabs = sw.findChild(QTabWidget)
assert tabs is not None
assert tabs.tabPosition() == QTabWidget.TabPosition.North
print('OK: SettingsWidget tabs position North')
"

# ═══════════════════════════════════════════
# 3. LANCEMENT APPLICATION
# ═══════════════════════════════════════════
python3 ts2i_ivs/main.py --check
# → ✅ ALL SYSTEMS GO

# Vérifications visuelles à effectuer manuellement :
# ☑ Thème light : fond blanc, texte noir (BUG-01 résolu)
# ☑ Tabs horizontaux dans NavBar (BUG-02 résolu)
# ☑ TelemetryPanel visible + sections draggables (BUG-07 résolu)
# ☑ FlexibleGridView 2 grids par défaut (BUG-08 résolu)
# ☑ F11 → mode inspection plein écran (GR-V9-1)
# ☑ Esc → retour navigation (GR-V9-1)
# ☑ F5 démarrage inspection (si produit actif)
# ☑ Right-click grid → menu 8 sources
# ☑ Drag section TelemetryPanel → réorganisation
# ☑ Ctrl+L → LoginDialog
# ☑ Tab Paramètres → sous-onglets en North (GR-V9-8)
# ☑ Tab Produits → cartes + bouton "+ Nouveau Produit"
# ☑ Tab Opérateurs → accessible uniquement si ADMIN

# ═══════════════════════════════════════════
# 4. RÉCAPITULATIF FINAL
# ═══════════════════════════════════════════

echo "=== Résumé sessions v9.0 ==="
echo "S25-v9  CORRECTION  2j   BUG-01, BUG-02"
echo "S26-v9  COMPLÉTION  2j   BUG-06 (core)"
echo "S28-v9  RÉÉCRITURE  2j   BUG-07"
echo "S29-v9  RÉÉCRITURE  3j   BUG-03, BUG-08"
echo "S30-v9  RÉÉCRITURE  1.5j BUG-09"
echo "S20-v9  RÉÉCRITURE  3j   BUG-03, BUG-07, BUG-08"
echo "S21-v9  RÉÉCRITURE  4j   BUG-04, BUG-10"
echo "S27-v9  COMPLÉTION  2j   BUG-06 (UI)"
echo "S31     NOUVELLE    3j   BUG-05, BUG-06 (assemblage)"
echo "S32     NOUVELLE    2j   BUG-05 (Products CRUD)"
echo "──────────────────────────────"
echo "Total : 10 sessions  ~24.5 jours  10 bugs corrigés"
```

---

## Récapitulatif fichiers créés/modifiés en v9.0

```
RÉÉCRITURES (remplacement v7/v8) :
  ui/theme/colors.py
  ui/theme/presets/light.py            ← NOUVEAU
  ui/theme/presets/dark.py             ← NOUVEAU
  ui/theme/styles.py
  ui/theme/theme_manager.py
  main.py                              ← correction ordre boot
  ui/screens/inspection_screen.py
  ui/components/flexible_grid_view.py
  ui/shortcut_manager.py

CRÉATIONS (nouveaux fichiers) :
  core/operators/__init__.py
  core/operators/models.py
  core/operators/permissions.py
  core/operators/operator_manager.py
  storage/operator_repository.py
  storage/migrations/002_operators_v9.sql
  ui/components/telemetry_section.py
  ui/components/telemetry_panel.py
  ui/components/grid_cell.py
  ui/components/source_renderer.py
  ui/components/logo_form_widget.py
  ui/components/operator_card.py
  ui/screens/product_definition_wizard.py
  ui/screens/login_dialog.py
  ui/screens/operators_screen.py
  ui/screens/operator_form_dialog.py
  ui/screens/products_screen.py
  ui/components/product_card.py
  core/product_manager.py
  ui/main_window.py                    ← réécriture complète

SUPPRIMÉS (ne pas recréer) :
  ui/theme/presets/cognex.py
  ui/theme/presets/keyence.py
  ui/theme/presets/halcon.py
  ui/screens/product_creation_screen.py → remplacé par product_definition_wizard.py
```

---

*TS2I IVS v9.0 — Sessions additionnelles*
*Prérequis : IVS_SESSIONS_v7_COMPLETE.md intégralement complété*
*Ordre : S25-v9 → S26-v9 → S28-v9 → S29-v9 → S30-v9 → S20-v9 → S21-v9 → S27-v9 → S31 → S32*
*10 sessions · 10 bugs corrigés · ~24.5 jours*
