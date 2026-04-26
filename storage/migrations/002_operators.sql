-- TS2I IVS v9.0 — Migration 002 : Operators v9 schema
-- Idempotente : appliquée uniquement si schema_version < 2.
-- Changements vs v7 (001_initial) :
--   * Ajout colonnes : operator_id TEXT UNIQUE, created_at REAL, last_login REAL
--   * Refonte CHECK role : 'admin' | 'operator' | 'viewer' (suppression 'supervisor')
--   * Migration legacy : 'supervisor' → 'admin'
-- Stratégie : drop+recreate car SQLite ne supporte pas ALTER CHECK.

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- ─────────────────────────────────────────────
--  Backup table existante (si présente)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operators (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL UNIQUE,
    role     TEXT    NOT NULL DEFAULT 'operator',
    pin_hash TEXT    NOT NULL,
    active   INTEGER NOT NULL DEFAULT 1
);

-- ─────────────────────────────────────────────
--  Nouvelle table v9 (3 rôles, cols étendues)
-- ─────────────────────────────────────────────
CREATE TABLE operators_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL UNIQUE,
    role        TEXT    NOT NULL DEFAULT 'operator'
                        CHECK(role IN ('admin','operator','viewer')),
    pin_hash    TEXT    NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    created_at  REAL    NOT NULL DEFAULT (strftime('%s','now')),
    last_login  REAL
);

-- ─────────────────────────────────────────────
--  Copie données legacy (supervisor → admin)
-- ─────────────────────────────────────────────
INSERT INTO operators_new (id, operator_id, name, role, pin_hash, active, created_at, last_login)
SELECT
    id,
    'op_' || id                AS operator_id,
    name,
    CASE role
        WHEN 'supervisor' THEN 'admin'
        WHEN 'admin'      THEN 'admin'
        WHEN 'operator'   THEN 'operator'
        WHEN 'viewer'     THEN 'viewer'
        ELSE 'operator'
    END                        AS role,
    pin_hash,
    active,
    strftime('%s','now')       AS created_at,
    NULL                       AS last_login
FROM operators;

DROP TABLE operators;
ALTER TABLE operators_new RENAME TO operators;

-- Index utiles
CREATE INDEX IF NOT EXISTS idx_operators_operator_id ON operators(operator_id);
CREATE INDEX IF NOT EXISTS idx_operators_active      ON operators(active);

-- ─────────────────────────────────────────────
--  Schema version bump
-- ─────────────────────────────────────────────
INSERT OR IGNORE INTO schema_version (version) VALUES (2);

COMMIT;

PRAGMA foreign_keys = ON;
