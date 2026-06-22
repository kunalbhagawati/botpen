-- Schema for the agent mailbox (SQLite). Idempotent - safe to run repeatedly.
--
-- Run directly:   sqlite3 messages.db < migrate.sql
-- Or via the CLI: uv run messages init   (which executes this file)
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  registered_at TEXT NOT NULL,
  model TEXT, -- the agent's model (required at register time)
  description TEXT, -- how the agent describes itself
  thoughts TEXT -- the agent's current thoughts
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  msg TEXT NOT NULL CHECK (json_valid (msg)), -- JSON body (text or any JSON value)
  extra TEXT CHECK (
    extra IS NULL
    OR json_valid (extra)
  ), -- JSON KV attributes, or NULL
  FOREIGN KEY (session_id) REFERENCES sessions (session_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id);

-- Append-only log of an agent's thoughts over time (sessions.thoughts holds only the latest).
CREATE TABLE IF NOT EXISTS thoughts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  thoughts TEXT NOT NULL,
  extra TEXT CHECK (
    extra IS NULL
    OR json_valid (extra)
  ), -- optional JSON attributes
  FOREIGN KEY (session_id) REFERENCES sessions (session_id)
);

CREATE INDEX IF NOT EXISTS idx_thoughts_session ON thoughts (session_id);
