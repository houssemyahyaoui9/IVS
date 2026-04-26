"""
core/operators/models.py — TS2I IVS v9.0
Modèle Operator + énumération des rôles (S26-v9).
GR-V9-7 : pin_hash bcrypt — jamais plain text.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperatorRole(Enum):
    """3 rôles seulement en v9. 'supervisor' supprimé."""

    ADMIN = "admin"          # tout : produits + opérateurs + paramètres
    OPERATOR = "operator"    # inspection + REVIEW validation
    VIEWER = "viewer"        # lecture seule

    @classmethod
    def from_str(cls, raw: str) -> "OperatorRole":
        """Tolère casse + valeurs legacy. 'supervisor' → ADMIN (mapping v9)."""
        s = (raw or "").strip().lower()
        if s == "supervisor":
            return cls.ADMIN
        for r in cls:
            if r.value == s:
                return r
        raise ValueError(f"OperatorRole inconnu : {raw!r}")


@dataclass(frozen=True)
class Operator:
    """
    Opérateur immuable. pin_hash = bcrypt (jamais plain text — GR-V9-7).
    """

    operator_id: str
    name: str
    role: OperatorRole
    pin_hash: str
    active: bool
    created_at: float
    last_login: float | None = None

    def __repr__(self) -> str:
        # Jamais exposer pin_hash dans les logs / repr (GR-V9-7).
        return (
            f"Operator(id={self.operator_id!r}, name={self.name!r}, "
            f"role={self.role.value}, active={self.active})"
        )
