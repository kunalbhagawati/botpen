"""The Hub daemon - the single writer of the DB and the endpoint agents connect to.

Runs INSIDE the Hub container as `hub serve`. Two channels in one asyncio loop:
- **Thrift RPC** (thriftpy2): the agent surface (register / messaging / about / permissions /
  stack / thoughts), authenticated by the per-agent token, scoped to the caller's scaffold_id.
- **WebSocket push** (websockets): the relay - the daemon pushes `incoming` / `permission` /
  `thought` events to connected agents. Messages route by scaffold_id; thoughts by session_id.

Every RPC is recorded in `request_log`. DB work runs in a worker thread so the loop never blocks.
ACL / reap maintenance on `/shared` is done in-process via :mod:`botpen.hub.shared` (the daemon is
already inside the Hub with the volume mounted).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import click
import thriftpy2
import websockets
from thriftpy2.rpc import make_aio_server

from config import settings

from ..commands.lib.utils import _decode, thrift_grant_to_dict
from ..core.db import ensure_db
from ..services import messages as messages_service
from ..services import permissions as permissions_service
from ..services import request_log as request_log_service
from ..services import sessions as sessions_service
from ..services.scaffolding import scaffold as scaffold_service
from ..services.utils import normalize_session
from ..stack_schema import SCAFFOLD_STACK_EXAMPLE, SCAFFOLD_STACK_SCHEMA
from . import shared as shared_ops

_IDL_PATH = settings.WORKING_DIR / "src" / "resources" / "hub.thrift"


class Hub:
    """Thrift handler + WebSocket hub. One instance owns the live push connections."""

    def __init__(self) -> None:
        # each conn: {"scaffold": str, "session": str | None, "ws": websocket}
        self._conns: list[dict] = []

    # --- auth + logging wrapper -------------------------------------------------

    async def _run(self, method: str, token: str, payload: dict, work: Callable[[dict], Awaitable[Any]]) -> str:
        start = time.monotonic()
        scaffold_id: str | None = None
        try:
            sc = await asyncio.to_thread(scaffold_service.get_by_secret_key, token)
            if sc is None:
                raise PermissionError("invalid token")
            scaffold_id = sc["scaffold_id"]
            result = await work(sc)
        except Exception as e:
            await asyncio.to_thread(
                request_log_service.record,
                method,
                scaffold_id,
                payload,
                "error",
                str(e),
                int((time.monotonic() - start) * 1000),
            )
            raise
        await asyncio.to_thread(
            request_log_service.record,
            method,
            scaffold_id,
            payload,
            "ok",
            None,
            int((time.monotonic() - start) * 1000),
        )
        return json.dumps(result)

    async def _active_or_raise(self, scaffold_id: str) -> str:
        session = await asyncio.to_thread(sessions_service.active_session_id, scaffold_id)
        if session is None:
            raise PermissionError("register first")
        return session

    # --- push -------------------------------------------------------------------

    async def _send(self, conns: list[dict], event: dict) -> None:
        data = json.dumps(event, ensure_ascii=False)
        dead = []
        for c in conns:
            try:
                await c["ws"].send(data)
            except Exception:
                dead.append(c)
        for c in dead:
            if c in self._conns:
                self._conns.remove(c)

    async def _push_scaffold(self, scaffold_id: str, event: dict) -> None:
        await self._send([c for c in self._conns if c["scaffold"] == scaffold_id], event)

    async def _push_session(self, session_id: str, event: dict) -> None:
        sid = normalize_session(session_id)
        await self._send([c for c in self._conns if c["session"] == sid], event)

    # --- Thrift methods (names match hub.thrift) --------------------------------

    async def ready(self, token) -> str:
        async def work(sc):
            await asyncio.to_thread(scaffold_service.set_status, sc["scaffold_id"], "running")
            return {"ok": True, "scaffold": sc["scaffold_id"]}

        return await self._run("ready", token, {}, work)

    async def register_session(self, token, session_id, model, description, personality) -> str:
        async def work(sc):
            await asyncio.to_thread(
                sessions_service.register,
                session_id,
                sc["scaffold_id"],
                model or None,
                description or None,
                personality or None,
            )
            return {"scaffold": sc["scaffold_id"], "session": normalize_session(session_id)}

        return await self._run("register_session", token, {"session_id": session_id, "model": model}, work)

    async def write(self, token, body, extra, recipients) -> str:
        async def work(sc):
            sid = sc["scaffold_id"]
            session = await self._active_or_raise(sid)
            body_val, extra_val = _decode(body), _decode(extra)
            to = [normalize_session(r) for r in recipients] if recipients else None
            mid, ts = await asyncio.to_thread(messages_service.write_message, sid, session, body_val, extra_val, to)
            event = {
                "event": "incoming",
                "id": mid,
                "scaffold": sid,
                "session": session,
                "created_at": ts,
                "body": body_val,
                "extra": extra_val,
                "to": to,
            }
            targets = to if to else [c["scaffold"] for c in self._conns if c["scaffold"] != sid]
            for t in set(targets):
                await self._push_scaffold(t, event)
            return {"id": mid, "created_at": ts}

        return await self._run("write", token, {"body": body, "to": list(recipients or [])}, work)

    async def think(self, token, thoughts, extra) -> str:
        async def work(sc):
            sid = sc["scaffold_id"]
            session = await self._active_or_raise(sid)
            extra_val = _decode(extra)
            tid, ts = await asyncio.to_thread(messages_service.write_thought, sid, session, thoughts, extra_val)
            readers = await asyncio.to_thread(sessions_service.get_thoughts_readers, sid)
            event = {
                "event": "thought",
                "id": tid,
                "scaffold": sid,
                "session": session,
                "created_at": ts,
                "thoughts": thoughts,
                "extra": extra_val,
            }
            for r in readers:
                await self._push_session(r, event)
            return {"id": tid, "created_at": ts}

        return await self._run("think", token, {"thoughts": thoughts}, work)

    async def read(self, token) -> str:
        async def work(sc):
            return await asyncio.to_thread(messages_service.read_since_last, sc["scaffold_id"])

        return await self._run("read", token, {}, work)

    async def about(self, token, target_scaffold_id, fields) -> str:
        async def work(sc):
            scaf = await asyncio.to_thread(scaffold_service.get_by_id, target_scaffold_id)
            profile = await asyncio.to_thread(sessions_service.get_profile, target_scaffold_id)
            if scaf is None and profile is None:
                return None
            out = {
                "scaffold": target_scaffold_id,
                "slug": scaf["slug"] if scaf else None,
                "description": (profile or {}).get("description"),
            }
            allowed = set(fields or [])
            if "personality" in allowed:
                out["personality"] = (profile or {}).get("personality")
            if "model" in allowed:
                out["model"] = (profile or {}).get("model")
            return out

        return await self._run("about", token, {"target": target_scaffold_id, "fields": list(fields or [])}, work)

    async def perm_ask(self, token, peer_scaffold_id, reason) -> str:
        async def work(sc):
            row = await asyncio.to_thread(
                permissions_service.log_ask, sc["scaffold_id"], peer_scaffold_id, reason or None
            )
            await self._push_scaffold(peer_scaffold_id, {"event": "permission", **row})
            return row

        return await self._run("perm_ask", token, {"peer": peer_scaffold_id, "reason": reason}, work)

    async def _apply_or_fail(self, row, owner_workspace, peer_scaffold_id, tree, fn) -> dict:
        """Apply (or revoke) the ACL on /shared/<owner_workspace>; close the log row accordingly."""
        peer = await asyncio.to_thread(scaffold_service.get_by_id, peer_scaffold_id)
        try:
            if peer is None:
                raise ValueError(f"unknown peer scaffold {peer_scaffold_id}")
            await asyncio.to_thread(fn, owner_workspace, peer["uid"], tree)
            await asyncio.to_thread(permissions_service.mark_applied, row["id"])
            row["status"] = "revoked" if row["permission_type"] == "revoke" else "applied"
        except Exception as e:
            await asyncio.to_thread(permissions_service.mark_failed, row["id"], str(e))
            row["status"], row["error"] = "failed", str(e)
        await self._push_scaffold(peer_scaffold_id, {"event": "permission", **row})
        return row

    async def perm_grant(self, token, peer_scaffold_id, grant, reason) -> str:
        async def work(sc):
            tree = thrift_grant_to_dict(grant)
            row = await asyncio.to_thread(
                permissions_service.log_grant, sc["scaffold_id"], peer_scaffold_id, tree, reason or None
            )
            owner_ws = shared_ops.workspace_dir(sc["slug"], sc["scaffold_id"])
            return await self._apply_or_fail(row, owner_ws, peer_scaffold_id, tree, shared_ops.apply_acl)

        return await self._run(
            "perm_grant", token, {"peer": peer_scaffold_id, "grant": thrift_grant_to_dict(grant)}, work
        )

    async def perm_revoke(self, token, peer_scaffold_id, grant, reason) -> str:
        async def work(sc):
            tree = thrift_grant_to_dict(grant)
            row = await asyncio.to_thread(
                permissions_service.log_revoke, sc["scaffold_id"], peer_scaffold_id, tree, reason or None
            )
            owner_ws = shared_ops.workspace_dir(sc["slug"], sc["scaffold_id"])
            return await self._apply_or_fail(row, owner_ws, peer_scaffold_id, tree, shared_ops.revoke_acl)

        return await self._run(
            "perm_revoke", token, {"peer": peer_scaffold_id, "grant": thrift_grant_to_dict(grant)}, work
        )

    async def perm_list(self, token) -> str:
        async def work(sc):
            return await asyncio.to_thread(permissions_service.list_log, sc["scaffold_id"])

        return await self._run("perm_list", token, {}, work)

    async def stack_schema(self, token) -> str:
        async def work(sc):
            return {"schema": SCAFFOLD_STACK_SCHEMA, "example": SCAFFOLD_STACK_EXAMPLE}

        return await self._run("stack_schema", token, {}, work)

    async def stack_get(self, token) -> str:
        async def work(sc):
            return await asyncio.to_thread(sessions_service.get_chosen_stack, sc["scaffold_id"])

        return await self._run("stack_get", token, {}, work)

    async def stack_set(self, token, stack_json) -> str:
        async def work(sc):
            try:
                parsed = json.loads(stack_json) if stack_json else None
            except ValueError, TypeError:
                parsed = stack_json  # no validation - record whatever they sent, even raw text
            await asyncio.to_thread(sessions_service.set_chosen_stack, sc["scaffold_id"], parsed)
            return {"ok": True}

        return await self._run("stack_set", token, {"stack": stack_json}, work)

    async def thoughts_ask(self, token, owner_session_id, why) -> str:
        async def work(sc):
            asker = await self._active_or_raise(sc["scaffold_id"])
            event = {
                "event": "thoughts-request",
                "from_session": asker,
                "from_scaffold": sc["scaffold_id"],
                "why": why or None,
            }
            await self._push_session(owner_session_id, event)
            return {"ok": True, "asked": normalize_session(owner_session_id)}

        return await self._run("thoughts_ask", token, {"owner_session": owner_session_id}, work)

    async def thoughts_grant(self, token, peer_session_id) -> str:
        async def work(sc):
            await asyncio.to_thread(sessions_service.grant_thoughts, sc["scaffold_id"], peer_session_id)
            return {"ok": True, "granted": normalize_session(peer_session_id)}

        return await self._run("thoughts_grant", token, {"peer_session": peer_session_id}, work)

    async def thoughts_revoke(self, token, peer_session_id) -> str:
        async def work(sc):
            await asyncio.to_thread(sessions_service.revoke_thoughts, sc["scaffold_id"], peer_session_id)
            return {"ok": True, "revoked": normalize_session(peer_session_id)}

        return await self._run("thoughts_revoke", token, {"peer_session": peer_session_id}, work)

    async def thoughts_read(self, token, owner_session_id) -> str:
        async def work(sc):
            caller = await self._active_or_raise(sc["scaffold_id"])
            return await asyncio.to_thread(messages_service.read_thoughts, owner_session_id, caller)

        return await self._run("thoughts_read", token, {"owner_session": owner_session_id}, work)

    # --- WebSocket relay --------------------------------------------------------

    async def ws_handler(self, websocket) -> None:
        """First message must be the agent's token; then the socket stays open for pushes only."""
        try:
            token = await websocket.recv()
            sc = await asyncio.to_thread(scaffold_service.get_by_secret_key, token)
            if sc is None:
                await websocket.close(code=4001, reason="invalid token")
                return
            scaffold_id = sc["scaffold_id"]
            session = await asyncio.to_thread(sessions_service.active_session_id, scaffold_id)
            conn = {"scaffold": scaffold_id, "session": session, "ws": websocket}
            self._conns.append(conn)
            try:
                await websocket.send(json.dumps({"event": "relay-up", "scaffold": scaffold_id, "session": session}))
                await websocket.wait_closed()
            finally:
                if conn in self._conns:
                    self._conns.remove(conn)
        except Exception:
            return


def run_serve() -> None:
    """Run the Hub daemon (Thrift RPC + WebSocket push). Foreground, Ctrl-C to stop."""
    ensure_db()  # self-heal the schema if it was wiped (e.g. db teardown)
    hub = Hub()
    idl = thriftpy2.load(str(_IDL_PATH), module_name="hub_thrift")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Thrift binds via run_until_complete internally (needs the loop idle), so bind it first; the
    # WebSocket server is then bound eagerly below (also before run_forever).
    thrift_server = make_aio_server(idl.Hub, hub, settings.DAEMON_HOST, settings.DAEMON_PORT, loop=loop)
    thrift_server.init_server()

    ws_holder: dict = {}

    async def _start_ws() -> None:
        ws_holder["server"] = await websockets.serve(hub.ws_handler, settings.DAEMON_HOST, settings.DAEMON_WS_PORT)

    async def _reaper() -> None:
        """Teardown monitor: every minute, reap the container/image/volume/playground of any agent
        whose container has been stopped longer than SCAFFOLD_TEARDOWN_AFTER_MINS."""
        playgrounds = settings.WORKING_DIR / "playgrounds"
        while True:
            await asyncio.sleep(60)
            try:
                reaped = await asyncio.to_thread(
                    shared_ops.reap_stopped, settings.SCAFFOLD_TEARDOWN_AFTER_MINS, playgrounds
                )
                if reaped:
                    click.echo(json.dumps({"event": "reaped", "slugs": reaped}))
            except Exception as e:
                click.echo(json.dumps({"event": "reaper-error", "error": str(e)}))

    # Bind the WebSocket server eagerly (not as a fire-and-forget task) so a bind failure - e.g.
    # the WS port already in use by another Hub - raises here and aborts serve, instead of being a
    # swallowed task exception that leaves the daemon half-running on Thrift only.
    loop.run_until_complete(_start_ws())
    loop.create_task(_reaper())

    click.echo(
        json.dumps(
            {
                "event": "serving",
                "thrift": f"{settings.DAEMON_HOST}:{settings.DAEMON_PORT}",
                "ws": f"{settings.DAEMON_HOST}:{settings.DAEMON_WS_PORT}",
            }
        )
    )
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ws_server = ws_holder.get("server")
        if ws_server is not None:
            ws_server.close()
            loop.run_until_complete(ws_server.wait_closed())
        loop.run_until_complete(thrift_server.close())
        loop.close()
