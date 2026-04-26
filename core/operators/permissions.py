"""
core/operators/permissions.py — TS2I IVS v9.0
Permissions par rôle + décorateur @requires_permission (S26-v9).
"""
from __future__ import annotations

from functools import wraps
from typing import Callable

from core.operators.models import OperatorRole

# ─────────────────────────────────────────────────────────────────────────────
#  Permissions par rôle
# ─────────────────────────────────────────────────────────────────────────────

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
    OperatorRole.VIEWER: set(),  # lecture seule — aucune action
}


# ─────────────────────────────────────────────────────────────────────────────
#  Décorateur @requires_permission
# ─────────────────────────────────────────────────────────────────────────────


def requires_permission(permission: str) -> Callable:
    """
    Décorateur pour méthodes qui exigent une permission.

    L'objet décoré doit exposer un attribut `_current_operator`
    (instance Operator) ou None si non connecté.

    Lève PermissionError si :
    - aucun opérateur connecté
    - rôle de l'opérateur ne possède pas la permission
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            op = getattr(self, "_current_operator", None)
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


def has_permission(role: OperatorRole, permission: str) -> bool:
    """Helper pour query — utile en UI pour griser des boutons."""
    return permission in PERMISSIONS.get(role, set())
