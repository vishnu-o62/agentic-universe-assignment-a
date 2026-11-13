
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    external_ref TEXT,
    batch_id TEXT NOT NULL,
    phone_hash TEXT NOT NULL,
    fields_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workflow_id, phone_hash)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    call_id TEXT,
    occurred_at TEXT,
    phone_hash TEXT,
    phone_encrypted TEXT,
    lead_id INTEGER,
    payload_json TEXT,
    received_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS ingested_drops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drop_key TEXT NOT NULL UNIQUE,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    warning TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_ingestion_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drop_key TEXT NOT NULL UNIQUE,
    malformed_json INTEGER NOT NULL DEFAULT 0,
    missing_event_id INTEGER NOT NULL DEFAULT 0,
    duplicate_event_id INTEGER NOT NULL DEFAULT 0,
    unknown_disposition INTEGER NOT NULL DEFAULT 0,
    inserted_events INTEGER NOT NULL DEFAULT 0,
    orphan_events INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_batch
ON leads(batch_id);

CREATE INDEX IF NOT EXISTS idx_events_lead
ON events(lead_id);

CREATE INDEX IF NOT EXISTS idx_events_call
ON events(call_id);

CREATE INDEX IF NOT EXISTS idx_events_phone
ON events(phone_hash);

CREATE INDEX IF NOT EXISTS idx_rejections_batch
ON rejections(batch_id);

CREATE INDEX IF NOT EXISTS idx_warnings_batch
ON warnings(batch_id);

CREATE INDEX IF NOT EXISTS idx_event_stats_drop
ON event_ingestion_stats(drop_key);
"""
