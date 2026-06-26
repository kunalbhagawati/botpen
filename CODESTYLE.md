# Code Style

Source-code rules for the `botpen` package. Workflow, schema/migration discipline, and "where
things go" live in [CONTRIBUTING.md](CONTRIBUTING.md); this file is about how the Python itself
is written. Enforced by ruff (`E`/`F`/`UP`, line length 120) - run
`uv run ruff check src config.py botpen migrations` before committing.

## Imports

- **At the top of the file** (PEP 8). No inline/local imports mid-function.
- Exception: a genuine circular-import break, or a deliberate side-effect import (e.g.
  `register_models()` in `core/db.py` wraps `from . import models`). Keep those rare and named.

## Functions over classes

Functions carry **behavior**; classes carry **state**. Default to plain functions for verbs - the
whole service layer is functions, each taking `(s, …)` and returning plain data. Don't wrap
behavior in a class just to group it.

Reach for a class when there is **state to hold**, in either of two shapes:

- **A struct that holds + presents state** - prefer a `@dataclass` over an ad-hoc dict. Derived or
  formatted views of that state belong *on the struct* as `@property` (or a descriptor), so the
  shape and its presentation travel together.
- **An object that owns live, mutable state** for its lifetime - the `Hub` (`commands/serve.py`) is
  the canonical example; it holds the open WebSocket connections.

| Use a… | When |
|---|---|
| function | the unit is a verb - a read / write / transform with no owned state (every `services/` op) |
| `@dataclass` / struct | you hold a bag of related fields; expose derived/formatted views via `@property` or descriptors |
| class with methods | an instance owns live, mutable state for its lifetime (the `Hub` + its connection list) |

## Complexity & nesting

- Small units, one responsibility, low cyclomatic complexity. Split before a function gets hard to
  hold in your head.
- **Nested functions: max depth 1.** A function may define an inner function; that inner function
  may **not** define another. The Hub's `async def work(sc)` closures are the canonical depth-1
  case - each RPC method defines exactly one inner `work`, never deeper.

## Type hints

| Use | Not |
|---|---|
| `X \| None` | `Optional[X]` |
| `list[T]`, `dict[K, V]` | `List[T]`, `Dict[K, V]` |
| `X \| Y` | `Union[X, Y]` |

`from __future__ import annotations` at the top of every module. (`UP` rules enforce this;
they auto-fix on `ruff check --fix`.)

**Annotate signatures, not locals.** Put types on parameters and return values; leave obvious
locals bare. A local annotation that just restates its right-hand side is noise.

```python
# Good - signature typed, locals bare
def read_since_last(s, scaffold_id: str) -> list[dict]:
    msgs = [_msg_to_dict(m) for m in rows]
    ...

# Noise - the annotation adds nothing
def read_since_last(s, scaffold_id: str) -> list[dict]:
    msgs: list[dict] = [_msg_to_dict(m) for m in rows]
```

**Generics (PEP 695).** This repo targets Python 3.14 - if you need a generic, use the inline form
(`def first[T](xs: list[T]) -> T:`, `class Box[T]:`), never `TypeVar` / `Generic`. Use sparingly;
most code here needs no generics at all.

**`Any` and type-checker escapes.** `Any` is allowed where a precise type fights the system - add a
one-line comment saying why. There is no type-checker gate in this repo (ruff + complexipy are the
gates); if you do suppress an editor/type-checker complaint, keep it to the single offending line
with the rule named - never a blanket file-level ignore.

**Multiple exception types — `except A, B:`.** Python 3.14 ([PEP 758](https://peps.python.org/pep-0758/))
allows the parenthesis-free form `except ValueError, TypeError:` to catch several types. This is the
house style here and is used throughout (`commands/serve.py`, `services/utils.py`, `commands/utils.py`).

> [!WARNING]
> This is **not** the Python-2 `except Exc, name:` bind syntax and **not** a bug. Both types are
> caught; nothing is bound to a name. Do not "fix" it by adding parentheses.

## Exceptions

Let exceptions bubble to a boundary that actually handles them. Do not catch just to log and
re-raise.

- **The RPC boundary is `Hub._run`** (`commands/serve.py`). It wraps every Thrift method, records
  the call to `request_log` on **both** success and error, and re-raises. Service and core code
  must therefore **not** pre-log or re-wrap their own exceptions on the way out - `_run` already
  captures them. Just let them propagate.
- **The CLI boundary is Click** - an unhandled exception in a command surfaces to the operator.
- **Catch only to handle**, i.e. when you will:
  - produce a side effect on failure (`_apply_or_fail` marks the permission row failed, then continues);
  - swallow a genuinely expected condition (`except OSError: pass` on a best-effort log write);
  - translate to a more meaningful error: `raise NewError(...) from e`.

```python
# BAD - catch-log-reraise: redundant, and _run already logs it
async def work(sc):
    try:
        return await asyncio.to_thread(messages_service.read_since_last, sc["scaffold_id"])
    except Exception as e:
        print(f"error: {e}")   # noise; risks swallowing the error if `raise` is ever dropped
        raise

# GOOD - let it bubble to _run
async def work(sc):
    return await asyncio.to_thread(messages_service.read_since_last, sc["scaffold_id"])
```

## Datetimes

Always [`arrow`](https://arrow.readthedocs.io) - never `datetime`, `time`, or `dateutil`
directly. UTC timestamps come from `botpen.services.utils.utc_now`
(`arrow.utcnow().format("YYYY-MM-DDTHH:mm:ss[Z]")`). Timestamps are stored as ISO-8601 TEXT.

## Database access

- **SQLModel only.** No raw SQL strings, no `sqlite3` connections, no `string.Template` queries.
- Get a session from `core.db` via the session decorators - **`@with_session`** for reads,
  **`@atomic`** for writes (`@atomic` is `@with_session` + a commit on success). Do not call
  `session()` / `commit()` by hand in a service.

  ```python
  # GOOD - decorator supplies the session; @atomic commits on success
  @atomic
  def write_message(s, session_id, body, ...):
      s.add(Message(...))
      s.flush()           # need the autogenerated id before returning
      return m.id, ts

  # BAD - manual session lifecycle in a service
  def write_message(session_id, body, ...):
      with core_db.session() as s:
          ...
          s.commit()
  ```

- **JSON columns** (`msg`, `extra`, `to`, `paths`) are TEXT; `json.dumps`/`json.loads` in the
  service layer, so stored shape and CLI output stay stable.
- **SQLite-specific code** (the connect-event pragmas, the WAL `_setup`) stays isolated in
  `core/db.py`. Do not sprinkle `PRAGMA`s or dialect assumptions elsewhere - the backend may
  change.

## CLI commands

- Commands parse args and format output only - no data logic, no DB access. Call into
  `services/`.
- Human-facing output uses the shared `console` from `commands/console.py`
  (rich tables / notices); machine output is `click.echo(json.dumps(...))`.
- Input coercion/rendering helpers live in `commands/utils.py`.

## Hub RPC methods

Every Thrift method on the `Hub` (`commands/serve.py`) follows one shape - match it:

```python
async def write(self, token, body, recipients) -> str:
    async def work(sc):                      # depth-1 closure; sc = authenticated scaffold row
        sid = sc["scaffold_id"]
        mid, ts = await asyncio.to_thread(   # every blocking / DB call hops to a thread
            messages_service.write_message, sid, _decode(body), ...
        )
        return {"id": mid, "created_at": ts}

    return await self._run("write", token, {"body": body}, work)
```

- **The logic lives in an inner `async def work(sc)`** - a depth-1 closure (see
  [Complexity & nesting](#complexity--nesting)). `sc` is the scaffold row `_run` already
  authenticated from the token.
- **Return `await self._run("<method>", token, <payload>, work)`.** `_run` resolves the token to a
  scaffold, runs `work`, records the call to `request_log` (success **and** error), and
  `json.dumps`-es the result. Don't authenticate, log, or JSON-encode by hand - and don't catch to
  log; `_run` is the [exception boundary](#exceptions).
- **Never block the event loop.** The services are sync and the Hub is the single async DB writer,
  so every service / DB call goes through `await asyncio.to_thread(fn, …)`.
- The handler name must match `hub.thrift` exactly (thriftpy2 resolves by name). The contribution
  workflow for adding one is in [CONTRIBUTING.md](CONTRIBUTING.md#adding-a-hub-rpc-method).

## Output & diagnostics

There is no stdlib `logging` here - the system emits **structured JSON events**, not free-text
logs. Stay on the established sinks:

| Side | Audience | Sink | How |
|---|---|---|---|
| Host CLI | human | rich `console` | `console.print(...)` from `commands/console.py` |
| Host CLI / Hub | machine | stdout JSON | `click.echo(json.dumps(event))` |
| Container daemons | agent | per-channel `.{channel}.jsonl` + stdout | `_emit(channel, event)` in `coordinate_cli/daemons.py` |

> [!NOTE]
> **No bare `print()` in the host package (`src/botpen/`)** - it is either `console` (human) or
> `click.echo` (machine). `print()` is reserved for the container-side `_emit` helper, which
> deliberately writes one JSON line to stdout and the workspace log.

## Config

Read config via `from config import settings`; never re-read env vars or recompute paths
inline. Add new settings to `config.py` (see [CONTRIBUTING.md § Config](CONTRIBUTING.md#config)).
