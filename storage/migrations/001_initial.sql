-- TS2I IVS v7.0 — Initial Schema
-- Rule-Governed Hierarchical Inspection System
-- Migration: 001_initial

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
--  Products
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    product_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    version         TEXT NOT NULL DEFAULT '1.0',
    width_mm        REAL NOT NULL DEFAULT 0.0,
    height_mm       REAL NOT NULL DEFAULT 0.0,
    product_barcode TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    station_id      TEXT NOT NULL DEFAULT 'STATION-001'
);

-- ─────────────────────────────────────────────
--  Inspections
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inspections (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          TEXT    NOT NULL REFERENCES products(product_id),
    frame_id            TEXT,
    verdict             TEXT    NOT NULL CHECK(verdict IN ('OK','NOK','REVIEW')),
    severity            TEXT    NOT NULL,
    fail_tier           TEXT,
    fail_reasons        TEXT,           -- JSON array
    tier_scores         TEXT,           -- JSON object {"CRITICAL":…,"MAJOR":…,"MINOR":…}
    tier_verdicts       TEXT,           -- JSON object {"CRITICAL":"OK",…}
    llm_summary         TEXT,
    model_versions      TEXT,           -- JSON object
    background_complete INTEGER NOT NULL DEFAULT 0 CHECK(background_complete IN (0,1)),
    operator            TEXT,
    timestamp           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_inspections_product   ON inspections(product_id);
CREATE INDEX IF NOT EXISTS idx_inspections_timestamp ON inspections(timestamp);
CREATE INDEX IF NOT EXISTS idx_inspections_verdict   ON inspections(verdict);

-- ─────────────────────────────────────────────
--  Operators
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operators (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL UNIQUE,
    role     TEXT    NOT NULL DEFAULT 'operator'
                     CHECK(role IN ('operator','supervisor','admin')),
    pin_hash TEXT    NOT NULL,
    active   INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);

-- ─────────────────────────────────────────────
--  Operator stats (per product)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operator_stats (
    operator_id INTEGER NOT NULL REFERENCES operators(id),
    product_id  TEXT    NOT NULL REFERENCES products(product_id),
    total       INTEGER NOT NULL DEFAULT 0,
    ok_count    INTEGER NOT NULL DEFAULT 0,
    nok_count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (operator_id, product_id)
);

-- ─────────────────────────────────────────────
--  Schema version
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO schema_version (version) VALUES (1);
