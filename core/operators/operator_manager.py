"""
core/operators/operator_manager.py — TS2I IVS v9.0
CRUD opérateurs + bcrypt + permissions (S26-v9).

GR-V9-7 : PIN bcrypt — jamais stocké plain text, jamais loggué.
GR-V8-4 : Operators stockés en DB SQLite + bcrypt pour PIN.
"""
from __future__ import annotations

import logging
import secrets
import sqlite3
import time
from pathlib import Path

import bcrypt

from core.operators.models import Operator, OperatorRole
from storage.db_connection import (
    DEFAULT_DB_PATH,
    DEFAULT_MIGRATIONS_DIR,
    apply_migrations,
    get_connection,
)

_LOG = logging.getLogger(__name__)

DEFAULT_ADMIN_OPERATOR_ID = "admin"
DEFAULT_ADMIN_NAME = "Administrator"
DEFAULT_ADMIN_PIN = "0000"  # à changer au premier login (cf. WARNING)


class OperatorManager:
    """
    CRUD opérateurs. GR-V9-7 : PIN jamais stocké plain text.

    Au premier démarrage (DB vide), crée un compte admin par défaut :
        operator_id = "admin", PIN = "0000"
    Un WARNING est loggué (jamais le PIN).
    """

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        migrations_dir: str | Path = DEFAULT_MIGRATIONS_DIR,
        seed_default_admin: bool = True,
    ) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection = get_connection(self._db_path)
        apply_migrations(self._conn, migrations_dir)
        self._connected_ids: set[str] = set()
        if seed_default_admin and self._is_empty():
            self._seed_default_admin()

    # ── DB helpers ────────────────────────────────────────────────────────

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _is_empty(self) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM operators"
        ).fetchone()
        return int(row["n"]) == 0

    def _seed_default_admin(self) -> None:
        self.create(
            name=DEFAULT_ADMIN_NAME,
            role=OperatorRole.ADMIN,
            pin=DEFAULT_ADMIN_PIN,
            operator_id=DEFAULT_ADMIN_OPERATOR_ID,
        )
        _LOG.warning(
            "Default admin created (operator_id=%s) — change PIN immediately",
            DEFAULT_ADMIN_OPERATOR_ID,
        )

    @staticmethod
    def _row_to_operator(row: sqlite3.Row) -> Operator:
        return Operator(
            operator_id=row["operator_id"],
            name=row["name"],
            role=OperatorRole.from_str(row["role"]),
            pin_hash=row["pin_hash"],
            active=bool(row["active"]),
            created_at=float(row["created_at"]),
            last_login=(float(row["last_login"])
                        if row["last_login"] is not None else None),
        )

    # ── bcrypt helpers ────────────────────────────────────────────────────

    @staticmethod
    def _hash_pin(pin: str) -> str:
        """GR-V9-7 : bcrypt hash, jamais retourner le plain text."""
        if not isinstance(pin, str) or pin == "":
            raise ValueError("PIN obligatoire (non vide)")
        return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def _check_pin(pin: str, stored_hash: str) -> bool:
        try:
            return bcrypt.checkpw(pin.encode("utf-8"), stored_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        role: OperatorRole,
        pin: str,
        operator_id: str | None = None,
    ) -> Operator:
        """
        Crée un nouvel opérateur.
        GR-V9-7 : pin → bcrypt.hashpw, jamais loggué.
        """
        if not name or not name.strip():
            raise ValueError("name obligatoire")
        if not isinstance(role, OperatorRole):
            raise TypeError("role doit être OperatorRole")
        op_id = operator_id or self._generate_operator_id()
        now = time.time()
        pin_hash = self._hash_pin(pin)
        try:
            self._conn.execute(
                "INSERT INTO operators "
                "(operator_id, name, role, pin_hash, active, created_at, last_login) "
                "VALUES (?, ?, ?, ?, 1, ?, NULL)",
                (op_id, name.strip(), role.value, pin_hash, now),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Opérateur déjà existant : {e}") from e
        # Jamais logguer le PIN (GR-V9-7) — uniquement l'identifiant.
        _LOG.info("Operator created: id=%s name=%s role=%s",
                  op_id, name, role.value)
        return self.get(op_id)  # type: ignore[return-value]

    @staticmethod
    def _generate_operator_id() -> str:
        return f"op_{secrets.token_hex(4)}"

    def get(self, operator_id: str) -> Operator | None:
        row = self._conn.execute(
            "SELECT * FROM operators WHERE operator_id = ?",
            (operator_id,),
        ).fetchone()
        return self._row_to_operator(row) if row else None

    def list_all(self) -> list[Operator]:
        rows = self._conn.execute(
            "SELECT * FROM operators ORDER BY name"
        ).fetchall()
        return [self._row_to_operator(r) for r in rows]

    def authenticate(self, operator_id: str, pin: str) -> Operator | None:
        """
        Vérifie bcrypt.checkpw. Met à jour last_login si succès.
        Retourne None si PIN incorrect, opérateur inconnu, ou inactif.
        Le PIN n'apparaît JAMAIS dans les logs (GR-V9-7).
        """
        op = self.get(operator_id)
        if op is None:
            _LOG.info("Auth failed: unknown operator_id=%s", operator_id)
            return None
        if not op.active:
            _LOG.info("Auth failed: inactive operator_id=%s", operator_id)
            return None
        if not self._check_pin(pin, op.pin_hash):
            _LOG.info("Auth failed: wrong PIN operator_id=%s", operator_id)
            return None
        # Succès — MAJ last_login
        now = time.time()
        self._conn.execute(
            "UPDATE operators SET last_login = ? WHERE operator_id = ?",
            (now, operator_id),
        )
        self._connected_ids.add(operator_id)
        _LOG.info("Auth OK: operator_id=%s", operator_id)
        return self.get(operator_id)

    def logout(self, operator_id: str) -> None:
        self._connected_ids.discard(operator_id)

    def is_connected(self, operator_id: str) -> bool:
        return operator_id in self._connected_ids

    def update(
        self,
        operator_id: str,
        name: str | None = None,
        role: OperatorRole | None = None,
        active: bool | None = None,
    ) -> Operator:
        """Mise à jour — PAS de changement PIN ici (méthode séparée)."""
        op = self.get(operator_id)
        if op is None:
            raise KeyError(f"Opérateur inconnu : {operator_id}")
        new_name = name.strip() if name else op.name
        new_role = role.value if isinstance(role, OperatorRole) else op.role.value
        new_active = 1 if (active if active is not None else op.active) else 0
        self._conn.execute(
            "UPDATE operators SET name=?, role=?, active=? WHERE operator_id=?",
            (new_name, new_role, new_active, operator_id),
        )
        return self.get(operator_id)  # type: ignore[return-value]

    def change_pin(self, operator_id: str, new_pin: str) -> None:
        """Nouveau hash bcrypt. Jamais logguer le PIN (GR-V9-7)."""
        if self.get(operator_id) is None:
            raise KeyError(f"Opérateur inconnu : {operator_id}")
        new_hash = self._hash_pin(new_pin)
        self._conn.execute(
            "UPDATE operators SET pin_hash=? WHERE operator_id=?",
            (new_hash, operator_id),
        )
        _LOG.info("PIN changed for operator_id=%s", operator_id)

    def delete(self, operator_id: str) -> None:
        """Interdit si opérateur actuellement connecté."""
        if operator_id in self._connected_ids:
            raise PermissionError(
                f"Suppression interdite : opérateur {operator_id} connecté"
            )
        if self.get(operator_id) is None:
            raise KeyError(f"Opérateur inconnu : {operator_id}")
        self._conn.execute(
            "DELETE FROM operators WHERE operator_id = ?",
            (operator_id,),
        )
        _LOG.info("Operator deleted: operator_id=%s", operator_id)

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self, operator_id: str) -> dict:
        """
        Retourne stats agrégées depuis operator_stats.
        Si tables / data absentes → totaux à 0.
        """
        op = self.get(operator_id)
        if op is None:
            raise KeyError(f"Opérateur inconnu : {operator_id}")
        # operator_stats référence operators(id) (legacy v7).
        # On récupère l'id INTEGER associé à operator_id TEXT.
        row = self._conn.execute(
            "SELECT id FROM operators WHERE operator_id = ?", (operator_id,)
        ).fetchone()
        op_int_id = row["id"]
        agg = self._conn.execute(
            "SELECT "
            "COALESCE(SUM(total),0)     AS total, "
            "COALESCE(SUM(ok_count),0)  AS ok_count, "
            "COALESCE(SUM(nok_count),0) AS nok_count "
            "FROM operator_stats WHERE operator_id = ?",
            (op_int_id,),
        ).fetchone()
        total = int(agg["total"])
        ok_count = int(agg["ok_count"])
        nok_count = int(agg["nok_count"])
        taux_ok = (ok_count / total) if total > 0 else 0.0
        return {
            "total": total,
            "ok_count": ok_count,
            "nok_count": nok_count,
            "taux_ok": taux_ok,
            "last_inspection": None,  # populé par S19/SPC plus tard
        }
