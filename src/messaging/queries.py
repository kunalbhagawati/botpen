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

LAST_MESSAGE_ID = Template("SELECT MAX(id) AS last FROM messages WHERE session_id = ?")

READ_ALL = Template("SELECT id, session_id, ts, msg, extra FROM messages ORDER BY id")

READ_SINCE = Template("SELECT id, session_id, ts, msg, extra FROM messages WHERE id > ? ORDER BY id")

DROP_TABLES = Template("DROP TABLE IF EXISTS messages; DROP TABLE IF EXISTS sessions;")

LIST_TABLES = Template("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
