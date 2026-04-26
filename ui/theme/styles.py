"""
ui/theme/styles.py — TS2I IVS v9.0
Génère le QSS global à partir d'une ThemePalette.
GR-V9-8 : tabs en position North uniquement.
GR-V8-2 : QSS centralisé — aucun setStyleSheet inline ailleurs.
"""
from __future__ import annotations

from ui.theme.colors import ThemePalette


def generate_qss(p: ThemePalette) -> str:
    """
    Retourne un QSS couvrant tous les widgets industriels :
    QPushButton, QLabel, QTableWidget, QTabWidget, QLineEdit,
    QScrollBar, QComboBox, QFrame, QMenu, QToolBar, QStatusBar,
    QHeaderView, QCheckBox, QRadioButton, QGroupBox, QProgressBar,
    QSpinBox, QToolTip, QSplitter, QDialog, QMainWindow.

    Longueur cible : ≥ 3000 caractères (Gate G-S25-v9).
    """
    return f"""
/* ═══════════════════════════════════════════════════════════════════
 * TS2I IVS v9.0 — Theme {p.name}
 * Auto-généré depuis ui/theme/styles.py — NE PAS éditer manuellement.
 * GR-V9-8 : tabs NORTH uniquement.
 * ═══════════════════════════════════════════════════════════════════ */

/* ── Base ───────────────────────────────────────────────────────── */
QWidget {{
    background-color: {p.bg_primary};
    color: {p.text_primary};
    font-family: "Segoe UI", "Roboto", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    selection-background-color: {p.accent_primary};
    selection-color: {p.bg_primary};
}}

QMainWindow {{
    background-color: {p.bg_primary};
}}

QDialog {{
    background-color: {p.bg_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
}}

QFrame {{
    background-color: {p.bg_secondary};
    border: 1px solid {p.border_subtle};
    border-radius: 4px;
}}

QFrame[flat="true"] {{
    border: none;
    background: transparent;
}}

/* ── Labels ─────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {p.text_primary};
    border: none;
    padding: 2px;
}}

QLabel[role="muted"] {{
    color: {p.text_muted};
}}

QLabel[role="success"] {{
    color: {p.success};
    font-weight: 600;
}}

QLabel[role="danger"] {{
    color: {p.danger};
    font-weight: 600;
}}

QLabel[role="review"] {{
    color: {p.review};
    font-weight: 600;
}}

QLabel[role="warning"] {{
    color: {p.warning};
    font-weight: 600;
}}

QLabel[role="title"] {{
    color: {p.text_primary};
    font-size: 16px;
    font-weight: 700;
    padding: 6px 0;
}}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    border-radius: 4px;
    padding: 6px 14px;
    min-height: 24px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {p.accent_secondary};
    color: {p.bg_primary};
    border-color: {p.accent_primary};
}}

QPushButton:pressed {{
    background-color: {p.accent_primary};
    color: {p.bg_primary};
    border-color: {p.accent_primary};
}}

QPushButton:disabled {{
    background-color: {p.bg_secondary};
    color: {p.text_disabled};
    border-color: {p.border_subtle};
}}

QPushButton[role="primary"] {{
    background-color: {p.accent_primary};
    color: {p.bg_primary};
    border-color: {p.accent_primary};
    font-weight: 600;
}}

QPushButton[role="danger"] {{
    background-color: {p.danger};
    color: {p.bg_primary};
    border-color: {p.danger};
}}

QPushButton[role="success"] {{
    background-color: {p.success};
    color: {p.bg_primary};
    border-color: {p.success};
}}

/* ── LineEdit / TextEdit ────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {p.bg_primary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {p.accent_primary};
    selection-color: {p.bg_primary};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {p.accent_primary};
}}

QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    background-color: {p.bg_secondary};
    color: {p.text_disabled};
    border-color: {p.border_subtle};
}}

QLineEdit[role="error"] {{
    border: 1px solid {p.danger};
}}

/* ── ComboBox ───────────────────────────────────────────────────── */
QComboBox {{
    background-color: {p.bg_primary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}}

QComboBox:hover {{
    border-color: {p.accent_primary};
}}

QComboBox:disabled {{
    background-color: {p.bg_secondary};
    color: {p.text_disabled};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid {p.border_default};
}}

QComboBox QAbstractItemView {{
    background-color: {p.bg_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    selection-background-color: {p.accent_primary};
    selection-color: {p.bg_primary};
    outline: 0;
}}

/* ── SpinBox ────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background-color: {p.bg_primary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {p.accent_primary};
}}

/* ── Tabs (GR-V9-8 : NORTH uniquement) ─────────────────────────── */
QTabWidget::pane {{
    background-color: {p.bg_secondary};
    border: 1px solid {p.border_default};
    border-top: none;
    top: -1px;
}}

QTabWidget::tab-bar {{
    alignment: left;
}}

QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
}}

QTabBar::tab {{
    background-color: {p.bg_tertiary};
    color: {p.text_secondary};
    border: 1px solid {p.border_default};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 14px;
    margin-right: 2px;
    min-width: 80px;
}}

QTabBar::tab:selected {{
    background-color: {p.bg_secondary};
    color: {p.text_primary};
    border-color: {p.accent_primary};
    font-weight: 600;
}}

QTabBar::tab:hover:!selected {{
    background-color: {p.bg_secondary};
    color: {p.text_primary};
}}

/* ── Tables ─────────────────────────────────────────────────────── */
QTableWidget, QTableView {{
    background-color: {p.bg_primary};
    color: {p.text_primary};
    gridline-color: {p.border_subtle};
    border: 1px solid {p.border_default};
    selection-background-color: {p.accent_primary};
    selection-color: {p.bg_primary};
    alternate-background-color: {p.bg_secondary};
}}

QTableWidget::item, QTableView::item {{
    padding: 4px 8px;
    border: none;
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {p.accent_primary};
    color: {p.bg_primary};
}}

QHeaderView {{
    background-color: {p.bg_tertiary};
    border: none;
}}

QHeaderView::section {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    padding: 6px 10px;
    border: none;
    border-right: 1px solid {p.border_default};
    border-bottom: 1px solid {p.border_default};
    font-weight: 600;
}}

QHeaderView::section:hover {{
    background-color: {p.bg_secondary};
}}

/* ── ScrollBars ─────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {p.bg_secondary};
    width: 12px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {p.border_strong};
    min-height: 24px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p.accent_primary};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    background: none;
    border: none;
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: {p.bg_secondary};
    height: 12px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    min-width: 24px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {p.accent_primary};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    background: none;
    border: none;
    width: 0;
}}

/* ── Menus / Toolbar / StatusBar ────────────────────────────────── */
QMenuBar {{
    background-color: {p.bg_secondary};
    color: {p.text_primary};
    border-bottom: 1px solid {p.border_default};
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
}}

QMenuBar::item:selected {{
    background-color: {p.accent_primary};
    color: {p.bg_primary};
}}

QMenu {{
    background-color: {p.bg_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    padding: 4px 0;
}}

QMenu::item {{
    padding: 6px 24px;
}}

QMenu::item:selected {{
    background-color: {p.accent_primary};
    color: {p.bg_primary};
}}

QMenu::separator {{
    height: 1px;
    background: {p.border_subtle};
    margin: 4px 8px;
}}

QToolBar {{
    background-color: {p.bg_secondary};
    border: none;
    spacing: 4px;
    padding: 4px;
}}

QToolBar::separator {{
    background: {p.border_default};
    width: 1px;
    margin: 4px 6px;
}}

QStatusBar {{
    background-color: {p.bg_secondary};
    color: {p.text_secondary};
    border-top: 1px solid {p.border_default};
}}

QStatusBar::item {{
    border: none;
}}

/* ── CheckBox / RadioButton ─────────────────────────────────────── */
QCheckBox, QRadioButton {{
    background: transparent;
    color: {p.text_primary};
    spacing: 6px;
}}

QCheckBox:disabled, QRadioButton:disabled {{
    color: {p.text_disabled};
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {p.border_strong};
    background: {p.bg_primary};
}}

QCheckBox::indicator {{
    border-radius: 3px;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {p.accent_primary};
    border-color: {p.accent_primary};
}}

/* ── GroupBox ───────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {p.bg_secondary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    border-radius: 4px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background: transparent;
    color: {p.accent_primary};
}}

/* ── ProgressBar ────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    border-radius: 4px;
    text-align: center;
    height: 18px;
}}

QProgressBar::chunk {{
    background-color: {p.accent_primary};
    border-radius: 3px;
}}

/* ── ToolTip ────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {p.bg_tertiary};
    color: {p.text_primary};
    border: 1px solid {p.border_default};
    padding: 4px 8px;
}}

/* ── Splitter ───────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {p.border_default};
}}

QSplitter::handle:horizontal {{
    width: 3px;
}}

QSplitter::handle:vertical {{
    height: 3px;
}}

QSplitter::handle:hover {{
    background: {p.accent_primary};
}}

/* ── Slider ─────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {p.bg_tertiary};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {p.accent_primary};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
"""
