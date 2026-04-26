"""
storage/db_connection.py — TS2I IVS v9.0
Mini connecteur SQLite + applicateur de migrations idempotent (S26-v9).
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

_LOG = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/ts2i_ivs.db")
DEFAULT_MIGRATIONS_DIR = Path("storage/migrations")


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Retourne une connexion SQLite avec foreign_keys + WAL activés."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    """Retourne la version actuelle du schéma (0 si table absente)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    row = conn.execute(
        "SELECT MAX(version) AS v FROM schema_version"
    ).fetchone()
    return int(row["v"] or 0)


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: str | Path = DEFAULT_MIGRATIONS_DIR,
) -> int:
    """
    Applique toutes les migrations *.sql dans l'ordre alphabétique.
    Idempotent : ne rejoue pas une migration déjà appliquée.

    Retourne la nouvelle version (highest applied).
    """
    mdir = Path(migrations_dir)
    if not mdir.exists():
        raise FileNotFoundError(f"Migrations dir absent : {mdir}")

    files = sorted(mdir.glob("*.sql"))
    if not files:
        return _current_version(conn)

    current = _current_version(conn)
    for f in files:
        # Convention : 001_xxx.sql, 002_xxx.sql -> version = int prefix
        try:
            version = int(f.name.split("_", 1)[0])
        except ValueError:
            _LOG.warning("Migration ignorée (préfixe non numérique) : %s", f.name)
            continue
        if version <= current:
            continue
        sql = f.read_text(encoding="utf-8")
        _LOG.info("Applying migration %s (v%d)", f.name, version)
        conn.executescript(sql)
        current = version

    return current
