"""Application configuration for botpen.

A single pydantic-settings ``Settings`` object holds every app-level constant and env var.
It lives at the repo root (Django-style); ``manage.py`` puts the repo root on ``sys.path`` so
package code can ``from config import settings``.

SQLite is a local file with no built-in users or passwords - ``MESSAGES_USER`` / ``MESSAGES_APP``
are informational tags, not credentials.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

WORKING_DIR: Path = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # Cascade: later files override earlier; process env vars override both. Missing files
    # (e.g. an absent .env.local) are skipped silently.
    model_config = SettingsConfigDict(
        env_file=(str(WORKING_DIR / ".env"), str(WORKING_DIR / ".env.local")),
        extra="ignore",
    )

    # Values come from .env (the committed source of truth) - no defaults here, so the value
    # lives in exactly one place. Relative MESSAGES_DB resolves against WORKING_DIR.
    MESSAGES_DB: str
    MESSAGES_USER: str  # informational owner tag (no auth enforced)
    MESSAGES_APP: str

    # Claude Code credential injected into scaffolded containers (secret; lives in .env.local).
    CLAUDE_CODE_OAUTH_TOKEN: str

    # Hub daemon (`serve`): the single DB writer that containers reach.
    # DAEMON_PORT = Thrift RPC; DAEMON_WS_PORT = the websockets push channel (relay).
    DAEMON_HOST: str
    DAEMON_PORT: int
    DAEMON_WS_PORT: int

    # Redact tokens from request_log. Off by default - this is a local, single-operator system.
    REQUEST_LOG_REDACT_TOKEN: bool

    # Scaffolding: base image, the ACL helper image, the shared volume, and per-agent defaults.
    SCAFFOLD_BASE_IMAGE: str
    ACL_HELPER_IMAGE: str
    SHARED_VOLUME_NAME: str
    SHARED_VOLUME_SIZE_GB: int
    SCAFFOLD_DEFAULT_MAX_DISK_MB: int
    SCAFFOLD_DEFAULT_MODEL: str  # default claude model alias for scaffolded agents (opus/sonnet/haiku/default)
    SCAFFOLD_UID_BASE: int
    SCAFFOLD_GID_BASE: int

    # Teardown monitor: minutes after an agent's container stops before the Hub reaps its
    # container / image / private volume / playground folder.
    SCAFFOLD_TEARDOWN_AFTER_MINS: int

    # noinspection PyPep8Naming
    @computed_field
    @property
    def WORKING_DIR(self) -> Path:
        return WORKING_DIR

    # noinspection PyPep8Naming
    @computed_field
    @property
    def DB_PATH(self) -> Path:
        p = Path(self.MESSAGES_DB).expanduser()
        return p if p.is_absolute() else (WORKING_DIR / p)

    # noinspection PyPep8Naming
    @computed_field
    @property
    def TMP_DIR(self) -> Path:
        """Runtime scratch (monitor cursor state); git-ignored."""
        return WORKING_DIR / ".tmp"


settings = Settings()
