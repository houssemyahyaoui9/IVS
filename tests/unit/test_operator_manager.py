"""
tests/unit/test_operator_manager.py — TS2I IVS v9.0
Gate G-S26-v9 : OperatorManager + bcrypt + migration idempotente.
"""
from __future__ import annotations

import time
from pathlib import Path

import bcrypt
import pytest

from core.operators import (
    Operator,
    OperatorManager,
    OperatorRole,
)
from storage.db_connection import (
    DEFAULT_MIGRATIONS_DIR,
    apply_migrations,
    get_connection,
)

MIGRATIONS = Path(__file__).resolve().parents[2] / "storage" / "migrations"


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "ivs_test.db"


@pytest.fixture
def mgr(db_path) -> OperatorManager:
    m = OperatorManager(db_path=db_path, migrations_dir=MIGRATIONS,
                        seed_default_admin=True)
    yield m
    m.close()


@pytest.fixture
def empty_mgr(db_path) -> OperatorManager:
    m = OperatorManager(db_path=db_path, migrations_dir=MIGRATIONS,
                        seed_default_admin=False)
    yield m
    m.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Migration & default admin
# ─────────────────────────────────────────────────────────────────────────────

class TestBootstrap:
    def test_default_admin_created_on_empty_db(self, mgr):
        ops = mgr.list_all()
        assert len(ops) == 1
        admin = ops[0]
        assert admin.operator_id == "admin"
        assert admin.role == OperatorRole.ADMIN
        assert admin.active is True

    def test_default_admin_pin_is_hashed_not_plain(self, mgr):
        admin = mgr.get("admin")
        assert admin.pin_hash != "0000"
        assert admin.pin_hash.startswith("$2")  # bcrypt prefix

    def test_default_admin_authenticates_with_0000(self, mgr):
        op = mgr.authenticate("admin", "0000")
        assert op is not None
        assert op.operator_id == "admin"

    def test_no_double_seed(self, db_path):
        m1 = OperatorManager(db_path=db_path, migrations_dir=MIGRATIONS)
        n1 = len(m1.list_all())
        m1.close()
        m2 = OperatorManager(db_path=db_path, migrations_dir=MIGRATIONS)
        n2 = len(m2.list_all())
        m2.close()
        assert n1 == 1 and n2 == 1

    def test_migration_idempotent(self, db_path):
        conn = get_connection(db_path)
        v1 = apply_migrations(conn, MIGRATIONS)
        v2 = apply_migrations(conn, MIGRATIONS)
        v3 = apply_migrations(conn, MIGRATIONS)
        assert v1 == v2 == v3 >= 2
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  CRUD + bcrypt
# ─────────────────────────────────────────────────────────────────────────────

class TestCRUD:
    def test_create_pin_is_hashed(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        assert op.pin_hash != "1234"
        assert op.pin_hash.startswith("$2")
        assert isinstance(op, Operator)

    def test_create_each_call_uses_distinct_salt(self, mgr):
        a = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        b = mgr.create("Bob",   OperatorRole.OPERATOR, "1234")
        assert a.pin_hash != b.pin_hash

    def test_db_never_contains_plain_pin(self, mgr):
        mgr.create("Alice", OperatorRole.OPERATOR, "secret_pin_xyz")
        rows = mgr._conn.execute("SELECT pin_hash FROM operators").fetchall()
        for r in rows:
            assert "secret_pin_xyz" not in r["pin_hash"]
            assert "1234" not in r["pin_hash"]
            assert r["pin_hash"].startswith("$2")

    def test_authenticate_correct_pin(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        result = mgr.authenticate(op.operator_id, "1234")
        assert result is not None
        assert result.operator_id == op.operator_id

    def test_authenticate_wrong_pin_returns_none(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        assert mgr.authenticate(op.operator_id, "wrong") is None

    def test_authenticate_unknown_returns_none(self, mgr):
        assert mgr.authenticate("does_not_exist", "1234") is None

    def test_authenticate_inactive_returns_none(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        mgr.update(op.operator_id, active=False)
        assert mgr.authenticate(op.operator_id, "1234") is None

    def test_authenticate_updates_last_login(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        assert op.last_login is None
        before = time.time()
        result = mgr.authenticate(op.operator_id, "1234")
        assert result.last_login is not None
        assert result.last_login >= before - 0.5

    def test_change_pin_invalidates_old(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        mgr.change_pin(op.operator_id, "5678")
        assert mgr.authenticate(op.operator_id, "1234") is None
        assert mgr.authenticate(op.operator_id, "5678") is not None

    def test_change_pin_unknown_raises(self, mgr):
        with pytest.raises(KeyError):
            mgr.change_pin("nope", "1111")

    def test_update_name_role_active(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        u = mgr.update(op.operator_id, name="Alice2", role=OperatorRole.ADMIN,
                       active=False)
        assert u.name == "Alice2"
        assert u.role == OperatorRole.ADMIN
        assert u.active is False

    def test_update_unknown_raises(self, mgr):
        with pytest.raises(KeyError):
            mgr.update("nope", name="x")

    def test_delete_disconnected_ok(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        mgr.delete(op.operator_id)
        assert mgr.get(op.operator_id) is None

    def test_delete_connected_raises(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        mgr.authenticate(op.operator_id, "1234")  # → connecté
        with pytest.raises(PermissionError):
            mgr.delete(op.operator_id)

    def test_delete_unknown_raises(self, mgr):
        with pytest.raises(KeyError):
            mgr.delete("nope")

    def test_logout_allows_delete(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        mgr.authenticate(op.operator_id, "1234")
        mgr.logout(op.operator_id)
        mgr.delete(op.operator_id)  # ne lève plus
        assert mgr.get(op.operator_id) is None

    def test_create_duplicate_name_raises(self, mgr):
        mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        with pytest.raises(ValueError):
            mgr.create("Alice", OperatorRole.OPERATOR, "5678")

    def test_create_empty_pin_raises(self, mgr):
        with pytest.raises(ValueError):
            mgr.create("Alice", OperatorRole.OPERATOR, "")

    def test_create_empty_name_raises(self, mgr):
        with pytest.raises(ValueError):
            mgr.create("", OperatorRole.OPERATOR, "1234")

    def test_get_unknown_returns_none(self, mgr):
        assert mgr.get("nope") is None

    def test_list_all_returns_sorted(self, empty_mgr):
        empty_mgr.create("Charlie", OperatorRole.OPERATOR, "1")
        empty_mgr.create("Alice",   OperatorRole.OPERATOR, "2")
        empty_mgr.create("Bob",     OperatorRole.OPERATOR, "3")
        names = [o.name for o in empty_mgr.list_all()]
        assert names == ["Alice", "Bob", "Charlie"]


# ─────────────────────────────────────────────────────────────────────────────
#  Stats
# ─────────────────────────────────────────────────────────────────────────────

class TestStats:
    def test_get_stats_empty(self, mgr):
        stats = mgr.get_stats("admin")
        assert stats["total"] == 0
        assert stats["ok_count"] == 0
        assert stats["nok_count"] == 0
        assert stats["taux_ok"] == 0.0

    def test_get_stats_unknown_raises(self, mgr):
        with pytest.raises(KeyError):
            mgr.get_stats("nope")


# ─────────────────────────────────────────────────────────────────────────────
#  GR-V9-7 — bcrypt format
# ─────────────────────────────────────────────────────────────────────────────

class TestBcryptCompliance:
    def test_pin_hash_is_valid_bcrypt(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        assert bcrypt.checkpw(b"1234", op.pin_hash.encode())
        assert not bcrypt.checkpw(b"wrong", op.pin_hash.encode())

    def test_repr_does_not_expose_pin_hash(self, mgr):
        op = mgr.create("Alice", OperatorRole.OPERATOR, "1234")
        assert "$2" not in repr(op)
        assert op.pin_hash not in repr(op)


# ─────────────────────────────────────────────────────────────────────────────
#  Migration legacy supervisor → admin
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacyMigration:
    def test_supervisor_role_migrated_to_admin(self, tmp_path):
        """Simule une DB v7 avec un supervisor + applique migration v9."""
        db = tmp_path / "legacy.db"
        # 1) Apply only 001 manually (recréer schéma v7 avec supervisor)
        conn = get_connection(db)
        conn.executescript("""
            CREATE TABLE schema_version(version INTEGER PRIMARY KEY,
                                        applied_at TEXT);
            CREATE TABLE operators(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'operator',
                pin_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO schema_version(version) VALUES(1);
            INSERT INTO operators(name, role, pin_hash)
                VALUES('LegacySup', 'supervisor', 'fake_hash');
            INSERT INTO operators(name, role, pin_hash)
                VALUES('LegacyOp',  'operator',   'fake_hash');
        """)
        conn.close()
        # 2) Apply v9 migration (002)
        conn = get_connection(db)
        v = apply_migrations(conn, MIGRATIONS)
        assert v >= 2
        rows = conn.execute(
            "SELECT name, role FROM operators ORDER BY name"
        ).fetchall()
        roles = {r["name"]: r["role"] for r in rows}
        assert roles["LegacySup"] == "admin"   # migré
        assert roles["LegacyOp"]  == "operator"
        conn.close()
