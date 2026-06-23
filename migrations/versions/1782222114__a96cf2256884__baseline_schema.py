"""baseline schema

Revision ID: a96cf2256884
Revises:
Create Date: 2026-06-23 19:11:54.498413

Hand-written as raw SQL (``op.execute``) on purpose - SQLModel autogenerate churns SQLite's TEXT
reflection. Canonical agent identity is ``scaffold_id``; ``sessions`` are incarnations linked to
a scaffold; messages / thoughts / permission_log / request_log all key on ``scaffold_id``.
"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a96cf2256884"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE scaffolds (
            scaffold_id VARCHAR NOT NULL PRIMARY KEY,
            scaffold_slug VARCHAR NOT NULL,
            created_at VARCHAR NOT NULL,
            secret_key VARCHAR NOT NULL,
            uid INTEGER NOT NULL,
            gid INTEGER NOT NULL,
            max_disk_mb INTEGER NOT NULL,
            stack VARCHAR,
            image_tag VARCHAR,
            container_name VARCHAR,
            status VARCHAR NOT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_scaffolds_secret_key ON scaffolds (secret_key)")

    op.execute(
        """
        CREATE TABLE sessions (
            session_id VARCHAR NOT NULL PRIMARY KEY,
            scaffold_id VARCHAR REFERENCES scaffolds (scaffold_id),
            registered_at VARCHAR NOT NULL,
            model VARCHAR,
            description VARCHAR,
            agent_personality VARCHAR,
            chosen_stack VARCHAR,
            thoughts_readers VARCHAR,
            stopped_at VARCHAR,
            stopped_reason VARCHAR,
            stopped_reason_notes VARCHAR,
            stopped_sig VARCHAR
        )
        """
    )
    op.execute("CREATE INDEX ix_sessions_scaffold_id ON sessions (scaffold_id)")

    op.execute(
        """
        CREATE TABLE messages (
            id INTEGER NOT NULL PRIMARY KEY,
            scaffold_id VARCHAR NOT NULL REFERENCES scaffolds (scaffold_id),
            session_id VARCHAR NOT NULL REFERENCES sessions (session_id),
            created_at VARCHAR NOT NULL,
            msg VARCHAR NOT NULL,
            extra VARCHAR,
            "to" VARCHAR
        )
        """
    )
    op.execute("CREATE INDEX ix_messages_scaffold_id ON messages (scaffold_id)")
    op.execute("CREATE INDEX ix_messages_session_id ON messages (session_id)")

    op.execute(
        """
        CREATE TABLE thoughts (
            id INTEGER NOT NULL PRIMARY KEY,
            scaffold_id VARCHAR NOT NULL REFERENCES scaffolds (scaffold_id),
            session_id VARCHAR NOT NULL REFERENCES sessions (session_id),
            created_at VARCHAR NOT NULL,
            thoughts VARCHAR NOT NULL,
            extra VARCHAR
        )
        """
    )
    op.execute("CREATE INDEX ix_thoughts_scaffold_id ON thoughts (scaffold_id)")
    op.execute("CREATE INDEX ix_thoughts_session_id ON thoughts (session_id)")

    op.execute(
        """
        CREATE TABLE permission_log (
            id INTEGER NOT NULL PRIMARY KEY,
            permission_type VARCHAR NOT NULL,
            owner_scaffold_id VARCHAR NOT NULL REFERENCES scaffolds (scaffold_id),
            peer_scaffold_id VARCHAR NOT NULL REFERENCES scaffolds (scaffold_id),
            "grant" VARCHAR,
            peer_permission_request_reason VARCHAR,
            owner_permission_decision_reason VARCHAR,
            status VARCHAR NOT NULL,
            error VARCHAR,
            created_at VARCHAR NOT NULL,
            updated_at VARCHAR NOT NULL,
            applied_at VARCHAR
        )
        """
    )
    op.execute("CREATE INDEX ix_permission_log_owner_scaffold_id ON permission_log (owner_scaffold_id)")
    op.execute("CREATE INDEX ix_permission_log_peer_scaffold_id ON permission_log (peer_scaffold_id)")

    op.execute(
        """
        CREATE TABLE request_log (
            id INTEGER NOT NULL PRIMARY KEY,
            created_at VARCHAR NOT NULL,
            method VARCHAR NOT NULL,
            scaffold_id VARCHAR,
            request VARCHAR,
            status VARCHAR NOT NULL,
            error VARCHAR,
            duration_ms INTEGER
        )
        """
    )
    op.execute("CREATE INDEX ix_request_log_scaffold_id ON request_log (scaffold_id)")


def downgrade() -> None:
    op.execute("DROP TABLE request_log")
    op.execute("DROP TABLE permission_log")
    op.execute("DROP TABLE thoughts")
    op.execute("DROP TABLE messages")
    op.execute("DROP TABLE sessions")
    op.execute("DROP TABLE scaffolds")
