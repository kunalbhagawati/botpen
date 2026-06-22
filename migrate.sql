-- Schema for the agent mailbox (SQLite). Idempotent - safe to run repeatedly.
--
-- Run directly:   sqlite3 messages.db < migrate.sql
-- Or via the CLI: ./messages init        (which executes this file)
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  registered_at TEXT NOT NULL,
  other TEXT,
  telemetry TEXT,
  params TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  msg TEXT NOT NULL CHECK (json_valid (msg)), -- JSON body (text or any JSON value)
  extra TEXT CHECK (
    extra IS NULL
    OR json_valid (extra)
  ) -- JSON KV attributes, or NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id);
