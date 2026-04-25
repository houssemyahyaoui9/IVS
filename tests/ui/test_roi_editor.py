"""
tests/ui/test_roi_editor.py
Gate G-17 — ROI Editor
TS2I IVS v7.0

Checks:
  - RoiZone créée avec bbox_rel dans [0,1]
  - to_criterion_rules() → list[CriterionRule] valide
  - Zone min size : zone 5×5px → rejetée
  - Max zones : 21 zones → exception
  - FORBIDDEN si RUNNING → widget non éditable (GR-12)
  - Couleurs correctes par Tier
  - Tier fixé selon type : ocr→MINOR, caliper/color→MAJOR (make() factory)
  - Déterminisme : même zone = même CriterionRule
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor

# ── imports projet ──────────────────────────────────────────────────────────
from ts2i_ivs.ui.components.roi_editor_widget import RoiEditorWidget, RoiZone
from ts2i_ivs.core.models import SystemState, BoundingBox, CriterionRule
from ts2i_ivs.core.tier_result import TierLevel


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def widget(qtbot):
    """RoiEditorWidget vide, 800×600, éditable."""
    w = RoiEditorWidget(canvas_size=(800, 600))
    w.set_editable(True)
    qtbot.addWidget(w)
    w.show()
    return w


def _make_zone(zone_type: str = "roi", tier: TierLevel = TierLevel.CRITICAL,
               x=0.1, y=0.1, w=0.2, h=0.2,
               threshold: float = 0.80, mandatory: bool = True) -> RoiZone:
    """Helper : crée une RoiZone via la factory make()."""
    bbox = BoundingBox(x=x, y=y, w=w, h=h)
    return RoiZone.make(
        zone_type=zone_type,
        bbox_rel=bbox,
        tier=tier,
        label=f"zone_{zone_type}",
        threshold=threshold,
        mandatory=mandatory,
    )


# ═══════════════════════════════════════════════════════════════════════════
# G-17-01  BoundingBox normalisée [0, 1]
# ═══════════════════════════════════════════════════════════════════════════

class TestRoiZoneCreation:

    def test_bbox_rel_within_unit_range(self):
        zone = _make_zone(x=0.05, y=0.10, w=0.30, h=0.25)
        assert 0.0 <= zone.bbox_rel.x <= 1.0
        assert 0.0 <= zone.bbox_rel.y <= 1.0
        assert 0.0 < zone.bbox_rel.w <= 1.0
        assert 0.0 < zone.bbox_rel.h <= 1.0

    def test_bbox_rel_x_plus_w_le_1(self):
        zone = _make_zone(x=0.7, y=0.1, w=0.3, h=0.2)
        assert zone.bbox_rel.x + zone.bbox_rel.w <= 1.0

    def test_bbox_rel_y_plus_h_le_1(self):
        zone = _make_zone(x=0.1, y=0.7, w=0.2, h=0.3)
        assert zone.bbox_rel.y + zone.bbox_rel.h <= 1.0

    def test_zone_id_non_empty(self):
        zone = _make_zone()
        assert zone.zone_id and len(zone.zone_id) > 0

    def test_zone_frozen_immutable(self):
        zone = _make_zone()
        with pytest.raises((AttributeError, TypeError)):
            zone.label = "hack"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# G-17-02  Factory make() — Tier forcé selon type
# ═══════════════════════════════════════════════════════════════════════════

class TestMakeFactory:

    def test_ocr_zone_forced_minor(self):
        zone = _make_zone(zone_type="ocr", tier=TierLevel.CRITICAL)
        assert zone.tier == TierLevel.MINOR

    def test_caliper_zone_forced_major(self):
        zone = _make_zone(zone_type="caliper", tier=TierLevel.CRITICAL)
        assert zone.tier == TierLevel.MAJOR

    def test_color_zone_forced_major(self):
        zone = _make_zone(zone_type="color", tier=TierLevel.MINOR)
        assert zone.tier == TierLevel.MAJOR

    def test_roi_zone_respects_user_tier_critical(self):
        zone = _make_zone(zone_type="roi", tier=TierLevel.CRITICAL)
        assert zone.tier == TierLevel.CRITICAL

    def test_roi_zone_respects_user_tier_minor(self):
        zone = _make_zone(zone_type="roi", tier=TierLevel.MINOR)
        assert zone.tier == TierLevel.MINOR


# ═══════════════════════════════════════════════════════════════════════════
# G-17-03  to_criterion_rules() → list[CriterionRule] valide
# ═══════════════════════════════════════════════════════════════════════════

class TestToCriterionRules:

    def test_returns_list(self):
        zone = _make_zone()
        rules = zone.to_criterion_rules()
        assert isinstance(rules, list)

    def test_returns_criterion_rule_instances(self):
        zone = _make_zone()
        rules = zone.to_criterion_rules()
        assert len(rules) >= 1
        for r in rules:
            assert isinstance(r, CriterionRule)

    def test_criterion_rule_tier_matches_zone(self):
        zone = _make_zone(zone_type="roi", tier=TierLevel.CRITICAL)
        rules = zone.to_criterion_rules()
        assert all(r.tier == TierLevel.CRITICAL for r in rules)

    def test_criterion_rule_threshold_preserved(self):
        zone = _make_zone(threshold=0.75)
        rules = zone.to_criterion_rules()
        assert all(r.threshold == 0.75 for r in rules)

    def test_criterion_rule_mandatory_preserved(self):
        zone = _make_zone(mandatory=False)
        rules = zone.to_criterion_rules()
        assert all(r.mandatory is False for r in rules)

    def test_criterion_rule_enabled_true(self):
        zone = _make_zone()
        rules = zone.to_criterion_rules()
        assert all(r.enabled is True for r in rules)

    def test_criterion_id_non_empty(self):
        zone = _make_zone()
        rules = zone.to_criterion_rules()
        for r in rules:
            assert r.criterion_id and len(r.criterion_id) > 0

    def test_determinism_same_zone_same_rules(self):
        """GR-01 : même zone → mêmes règles à chaque appel."""
        zone = _make_zone(x=0.1, y=0.2, w=0.3, h=0.15)
        rules_a = zone.to_criterion_rules()
        rules_b = zone.to_criterion_rules()
        assert [(r.criterion_id, r.tier, r.threshold) for r in rules_a] == \
               [(r.criterion_id, r.tier, r.threshold) for r in rules_b]


# ═══════════════════════════════════════════════════════════════════════════
# G-17-04  Zone minimum size — rejet 5×5px
# ═══════════════════════════════════════════════════════════════════════════

class TestMinimumZoneSize:

    def test_zone_5px_rejected(self, widget):
        """Canvas 800×600 : 5px → bbox_rel ≈ 0.00625×0.00833 → trop petit."""
        canvas_w, canvas_h = 800, 600
        min_px = 10  # seuil spec §12.2

        x_rel = 5 / canvas_w
        y_rel = 5 / canvas_h
        w_rel = 5 / canvas_w
        h_rel = 5 / canvas_h

        bbox = BoundingBox(x=x_rel, y=y_rel, w=w_rel, h=h_rel)

        with pytest.raises((ValueError, RuntimeError)):
            widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.CRITICAL)

    def test_zone_10px_accepted(self, widget):
        """10×10px doit être acceptée (limite basse exacte)."""
        canvas_w, canvas_h = 800, 600
        bbox = BoundingBox(x=0.1, y=0.1,
                           w=10 / canvas_w,
                           h=10 / canvas_h)
        # Ne doit PAS lever d'exception
        widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.CRITICAL)

    def test_zone_normal_size_accepted(self, widget):
        bbox = BoundingBox(x=0.1, y=0.1, w=0.2, h=0.2)
        widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.MAJOR)
        assert len(widget.zones) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# G-17-05  Max zones — 21 → exception
# ═══════════════════════════════════════════════════════════════════════════

class TestMaxZones:

    def test_21_zones_raises(self, widget):
        """Max 20 zones (§12.2) — la 21ème doit lever une exception."""
        for i in range(20):
            x = (i % 5) * 0.18 + 0.01
            y = (i // 5) * 0.22 + 0.01
            bbox = BoundingBox(x=x, y=y, w=0.15, h=0.18)
            widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.MINOR)

        assert len(widget.zones) == 20

        bbox_extra = BoundingBox(x=0.50, y=0.50, w=0.10, h=0.10)
        with pytest.raises((ValueError, RuntimeError)):
            widget.add_zone(zone_type="roi", bbox_rel=bbox_extra, tier=TierLevel.MINOR)

    def test_20_zones_accepted(self, widget):
        for i in range(20):
            x = (i % 5) * 0.18 + 0.01
            y = (i // 5) * 0.22 + 0.01
            bbox = BoundingBox(x=x, y=y, w=0.15, h=0.18)
            widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.MINOR)
        assert len(widget.zones) == 20


# ═══════════════════════════════════════════════════════════════════════════
# G-17-06  GR-12 — FORBIDDEN si RUNNING
# ═══════════════════════════════════════════════════════════════════════════

class TestGR12RunningLock:

    def test_set_editable_false_blocks_add(self, widget):
        """set_editable(False) → add_zone doit être bloqué."""
        widget.set_editable(False)
        bbox = BoundingBox(x=0.1, y=0.1, w=0.2, h=0.2)
        with pytest.raises((RuntimeError, PermissionError)):
            widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.CRITICAL)

    def test_set_editable_false_cursor_forbidden(self, widget, qtbot):
        """Curseur doit être Forbidden quand non éditable."""
        widget.set_editable(False)
        assert widget.cursor().shape() == Qt.CursorShape.ForbiddenCursor

    def test_set_editable_true_restores_normal(self, widget, qtbot):
        """set_editable(True) → curseur normal restauré."""
        widget.set_editable(False)
        widget.set_editable(True)
        assert widget.cursor().shape() != Qt.CursorShape.ForbiddenCursor

    def test_set_editable_false_blocks_delete(self, widget, qtbot):
        """Delete key doit être ignoré si non éditable."""
        bbox = BoundingBox(x=0.1, y=0.1, w=0.2, h=0.2)
        widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.CRITICAL)
        count_before = len(widget.zones)

        widget.set_editable(False)
        # Sélectionner la zone et tenter delete
        if widget.zones:
            widget._selected_zone_id = widget.zones[0].zone_id
        qtbot.keyClick(widget, Qt.Key.Key_Delete)

        assert len(widget.zones) == count_before  # aucune suppression


# ═══════════════════════════════════════════════════════════════════════════
# G-17-07  Couleurs overlay par Tier
# ═══════════════════════════════════════════════════════════════════════════

class TestOverlayColors:

    EXPECTED_COLORS = {
        TierLevel.CRITICAL : "#FF4444",
        TierLevel.MAJOR    : "#FF8800",
        TierLevel.MINOR    : "#FFCC00",
    }
    OCR_COLOR     = "#44CC44"
    CALIPER_COLOR = "#9944FF"

    def test_critical_color(self, widget):
        color = widget.get_tier_color(TierLevel.CRITICAL)
        assert QColor(color).name().upper() == self.EXPECTED_COLORS[TierLevel.CRITICAL].upper()

    def test_major_color(self, widget):
        color = widget.get_tier_color(TierLevel.MAJOR)
        assert QColor(color).name().upper() == self.EXPECTED_COLORS[TierLevel.MAJOR].upper()

    def test_minor_color(self, widget):
        color = widget.get_tier_color(TierLevel.MINOR)
        assert QColor(color).name().upper() == self.EXPECTED_COLORS[TierLevel.MINOR].upper()

    def test_ocr_zone_color(self, widget):
        color = widget.get_zone_type_color("ocr")
        assert QColor(color).name().upper() == self.OCR_COLOR.upper()

    def test_caliper_zone_color(self, widget):
        color = widget.get_zone_type_color("caliper")
        assert QColor(color).name().upper() == self.CALIPER_COLOR.upper()


# ═══════════════════════════════════════════════════════════════════════════
# G-17-08  Sélection et suppression (Delete key)
# ═══════════════════════════════════════════════════════════════════════════

class TestZoneSelectDelete:

    def test_delete_selected_zone(self, widget, qtbot):
        bbox = BoundingBox(x=0.1, y=0.1, w=0.2, h=0.2)
        widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.CRITICAL)
        assert len(widget.zones) == 1

        widget._selected_zone_id = widget.zones[0].zone_id
        qtbot.keyClick(widget, Qt.Key.Key_Delete)

        assert len(widget.zones) == 0

    def test_delete_without_selection_does_nothing(self, widget, qtbot):
        bbox = BoundingBox(x=0.1, y=0.1, w=0.2, h=0.2)
        widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.CRITICAL)
        widget._selected_zone_id = None

        qtbot.keyClick(widget, Qt.Key.Key_Delete)
        assert len(widget.zones) == 1


# ═══════════════════════════════════════════════════════════════════════════
# G-17-09  Widget zones() → collecte to_criterion_rules globale
# ═══════════════════════════════════════════════════════════════════════════

class TestWidgetRulesCollection:

    def test_widget_collects_all_rules(self, widget):
        """widget.get_all_criterion_rules() agrège toutes les zones."""
        for i in range(3):
            bbox = BoundingBox(x=0.05 + i * 0.25, y=0.1, w=0.20, h=0.20)
            widget.add_zone(zone_type="roi", bbox_rel=bbox, tier=TierLevel.MAJOR)

        rules = widget.get_all_criterion_rules()
        assert isinstance(rules, list)
        assert len(rules) >= 3
        assert all(isinstance(r, CriterionRule) for r in rules)

    def test_empty_widget_returns_empty_list(self, widget):
        rules = widget.get_all_criterion_rules()
        assert rules == []