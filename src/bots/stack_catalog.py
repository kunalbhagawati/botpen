"""Stack catalog for `scaffold new`: category -> list of installable choices (static, in code).

The default container installs NONE of these - a blank Alpine plus common OS utilities only (the
base image always adds Node for claude, the `manage` binary, acl/git/bash/curl). An agent picks
any subset per category. Versions track the Alpine repo (recent); each language's own manager
(uv / bundler / cargo / npm) handles finer version control at runtime.
"""

from __future__ import annotations

SCAFFOLD_STACK_CATALOG: dict[str, list[dict[str, object]]] = {
    # Each language installs the version and/or package manager that ships in the Alpine repo;
    # where a popular manager is not packaged (fnm / pyenv / rbenv / gvm / sdkman), we skip it and
    # let the agent install its own. Verified available on alpine:3.21.
    "language": [
        {"key": "python", "packages": ["python3"]},  # uv (version + package manager) ships in the base image
        {"key": "node", "packages": ["nodejs", "npm"]},  # npm = package manager (fnm not packaged)
        {"key": "ruby", "packages": ["ruby", "ruby-dev", "ruby-bundler"]},  # bundler = package manager
        {"key": "go", "packages": ["go"]},  # go modules built-in
        {"key": "java", "packages": ["openjdk21", "gradle"]},  # gradle = build/pkg manager (java + kotlin)
        {"key": "rust", "packages": ["rust", "cargo"]},  # cargo = package manager
    ],
    "db": [
        {"key": "postgresql", "packages": ["postgresql", "postgresql-client"]},
        {"key": "redis", "packages": ["redis"]},
        {"key": "sqlite", "packages": ["sqlite"]},
    ],
    "tools": [
        {"key": "build", "packages": ["build-base"]},
        {"key": "ffmpeg", "packages": ["ffmpeg"]},
    ],
}
