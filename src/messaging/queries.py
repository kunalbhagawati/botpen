"""SQL statements for the mailbox, each a string.Template. (Schema DDL lives in migrate.sql.)

Each query is a ``string.Template``; call ``.substitute(...)`` to render the SQL. Value
placeholders use SQLite's ``?`` parameters (passed at execute time); ``$name`` slots, if
any, are filled by ``.substitute``.
"""

from string import Template

REGISTER_SESSION = Template("""
INSERT INTO sessions (session_id, registered_at, model, description, thoughts)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(session_id) DO UPDATE SET
    model       = COALESCE(excluded.model,       sessions.model),
    description = COALESCE(excluded.description, sessions.description),
    thoughts    = COALESCE(excluded.thoughts,    sessions.thoughts)
""")

ENSURE_SESSION = Template("INSERT OR IGNORE INTO sessions (session_id, registered_at) VALUES (?, ?)")

INSERT_MESSAGE = Template("INSERT INTO messages (session_id, ts, msg, extra) VALUES (?, ?, ?, ?)")

INSERT_THOUGHT = Template("INSERT INTO thoughts (session_id, ts, thoughts, extra) VALUES (?, ?, ?, ?)")

LAST_MESSAGE_ID = Template("SELECT MAX(id) AS last FROM messages WHERE session_id = ?")

READ_ALL = Template("SELECT id, session_id, ts, msg, extra FROM messages ORDER BY id")

READ_SINCE = Template("SELECT id, session_id, ts, msg, extra FROM messages WHERE id > ? ORDER BY id")

# Like READ_SINCE but cursor-driven for the monitor (any author; self filtered in Python).
READ_AFTER = Template("SELECT id, session_id, ts, msg, extra FROM messages WHERE id > ? ORDER BY id")

ASK_PERMISSION = Template("""
INSERT INTO permissions (asker, granter, status, ask_why, paths, created_at, updated_at)
VALUES (?, ?, 'requested', ?, NULL, ?, ?)
ON CONFLICT(asker, granter) DO UPDATE SET
    ask_why    = excluded.ask_why,
    status     = CASE WHEN permissions.status = 'granted' THEN 'granted' ELSE 'requested' END,
    updated_at = excluded.updated_at
""")

GRANT_PERMISSION = Template("""
INSERT INTO permissions (asker, granter, status, grant_why, paths, created_at, updated_at)
VALUES (?, ?, 'granted', ?, ?, ?, ?)
ON CONFLICT(asker, granter) DO UPDATE SET
    status         = 'granted',
    grant_why      = excluded.grant_why,
    paths          = excluded.paths,
    revoked_at     = NULL,
    revoked_reason = NULL,
    updated_at     = excluded.updated_at
""")

DENY_PERMISSION = Template("""
UPDATE permissions
   SET status = 'denied', grant_why = ?, updated_at = ?
 WHERE granter = ? AND asker = ?
""")

REVOKE_PERMISSION = Template("""
UPDATE permissions
   SET status = 'revoked', revoked_at = ?, revoked_reason = ?, updated_at = ?
 WHERE granter = ? AND asker = ?
""")

_PERM_COLS = (
    "id, asker, granter, status, ask_why, grant_why, paths,"
    " revoked_at, revoked_reason, created_at, updated_at"
)

LIST_PERMISSIONS = Template(
    f"SELECT {_PERM_COLS} FROM permissions WHERE asker = ? OR granter = ? ORDER BY id"
)

# Rows involving a session (as asker or granter) changed since a timestamp cursor — the
# monitor relays these so both sides hear requests and decisions in near-real-time.
PERMISSIONS_CHANGED = Template(
    f"SELECT {_PERM_COLS} FROM permissions"
    " WHERE (asker = ? OR granter = ?) AND updated_at > ? ORDER BY updated_at, id"
)

CHECK_PERMISSION = Template(
    "SELECT paths FROM permissions WHERE asker = ? AND granter = ? AND status = 'granted'"
)

DROP_TABLES = Template(
    "DROP TABLE IF EXISTS permissions;"
    " DROP TABLE IF EXISTS thoughts;"
    " DROP TABLE IF EXISTS messages;"
    " DROP TABLE IF EXISTS sessions;"
)

LIST_TABLES = Template("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
