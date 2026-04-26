"""
tests/unit/test_operator_permissions.py — TS2I IVS v9.0
Gate G-S26-v9 : permissions par rôle + @requires_permission.
"""
from __future__ import annotations

import time

import pytest

from core.operators import (
    Operator,
    OperatorRole,
    PERMISSIONS,
    has_permission,
    requires_permission,
)


# ─────────────────────────────────────────────────────────────────────────────
#  PERMISSIONS dict
# ─────────────────────────────────────────────────────────────────────────────

class TestPermissionsDict:
    def test_admin_has_all_actions(self):
        admin_perms = PERMISSIONS[OperatorRole.ADMIN]
        for p in [
            "product.create", "product.edit", "product.delete",
            "operator.create", "operator.edit", "operator.delete",
            "inspection.start", "inspection.stop",
            "review.validate", "settings.edit", "gpio.config",
            "fleet.export", "fleet.import",
        ]:
            assert p in admin_perms, f"ADMIN devrait avoir {p}"

    def test_operator_has_inspection_review_only(self):
        op_perms = PERMISSIONS[OperatorRole.OPERATOR]
        assert op_perms == {
            "inspection.start",
            "inspection.stop",
            "review.validate",
        }

    def test_viewer_has_no_permission(self):
        assert PERMISSIONS[OperatorRole.VIEWER] == set()

    def test_three_roles_only(self):
        assert set(PERMISSIONS.keys()) == {
            OperatorRole.ADMIN,
            OperatorRole.OPERATOR,
            OperatorRole.VIEWER,
        }

    def test_has_permission_helper(self):
        assert has_permission(OperatorRole.ADMIN, "product.create")
        assert not has_permission(OperatorRole.OPERATOR, "product.create")
        assert not has_permission(OperatorRole.VIEWER, "inspection.start")


# ─────────────────────────────────────────────────────────────────────────────
#  Décorateur @requires_permission
# ─────────────────────────────────────────────────────────────────────────────

def _make_op(role: OperatorRole) -> Operator:
    return Operator(
        operator_id=f"id_{role.value}",
        name=f"User_{role.value}",
        role=role,
        pin_hash="$2b$xx_fake",
        active=True,
        created_at=time.time(),
    )


class _FakeController:
    """Sujet de test pour le décorateur."""

    def __init__(self, current=None):
        self._current_operator = current

    @requires_permission("product.create")
    def create_product(self, name: str) -> str:
        return f"created:{name}"

    @requires_permission("inspection.start")
    def start_inspection(self) -> bool:
        return True


class TestRequiresPermission:
    def test_not_connected_raises(self):
        ctrl = _FakeController(current=None)
        with pytest.raises(PermissionError, match="Non connecté"):
            ctrl.create_product("widget")

    def test_admin_passes_product_create(self):
        ctrl = _FakeController(current=_make_op(OperatorRole.ADMIN))
        assert ctrl.create_product("widget") == "created:widget"

    def test_operator_blocked_on_product_create(self):
        ctrl = _FakeController(current=_make_op(OperatorRole.OPERATOR))
        with pytest.raises(PermissionError, match="refusée"):
            ctrl.create_product("widget")

    def test_viewer_blocked_on_inspection_start(self):
        ctrl = _FakeController(current=_make_op(OperatorRole.VIEWER))
        with pytest.raises(PermissionError, match="refusée"):
            ctrl.start_inspection()

    def test_operator_passes_inspection_start(self):
        ctrl = _FakeController(current=_make_op(OperatorRole.OPERATOR))
        assert ctrl.start_inspection() is True

    def test_admin_passes_inspection_start(self):
        ctrl = _FakeController(current=_make_op(OperatorRole.ADMIN))
        assert ctrl.start_inspection() is True

    def test_error_message_contains_role_name(self):
        ctrl = _FakeController(current=_make_op(OperatorRole.OPERATOR))
        with pytest.raises(PermissionError) as exc:
            ctrl.create_product("widget")
        assert "operator" in str(exc.value)
        assert "product.create" in str(exc.value)
