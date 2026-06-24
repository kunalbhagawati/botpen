"""In-container background daemons, started by the entrypoint via `coordinate daemons`.

- relay        - consume the daemon's WebSocket push channel and surface events to the agent.
- disk-monitor - watch /workspace against the disk budget, escalate, and auto-terminate at 100%.
- run_daemons  - run the two above, restarting them if they exit.

The agent reads surfaced events / alerts from the relay+monitor log files in its workspace.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time

import websockets

_WORKSPACE = os.environ.get("COORDINATE__WORKSPACE", "/workspace")


def _ws_url() -> str:
    host = os.environ.get("COORDINATE__HOST", "host.docker.internal")
    port = int(os.environ.get("COORDINATE__WS_PORT", "8788"))
    return f"ws://{host}:{port}"


def _emit(channel: str, event: dict) -> None:
    """Append one event as a JSON line to a per-channel log in the workspace, and echo to stdout."""
    line = json.dumps(event, ensure_ascii=False)
    print(line, flush=True)
    try:
        with open(os.path.join(_WORKSPACE, f".{channel}.jsonl"), "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


async def _relay_loop(token: str) -> None:
    url = _ws_url()
    while True:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(token)
                async for raw in ws:
                    _emit("relay", json.loads(raw))
        except Exception as e:
            _emit("relay", {"event": "relay-error", "error": str(e)})
            await asyncio.sleep(2)


def relay(token: str) -> None:
    """Run the WebSocket relay forever (reconnecting)."""
    asyncio.run(_relay_loop(token))


def _dir_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def disk_monitor(token: str, interval: float = 10.0) -> None:
    """Watch /workspace usage vs the budget; escalate, then SIGTERM the agent at 100%.

    Ladder (percent of COORDINATE__MAX_DISK_MB): <50 silent | >=50 vague | >=80 critical | >=90
    explicit + termination warning | >=100 auto-terminate. Each band fires once."""
    max_mb = int(os.environ.get("COORDINATE__MAX_DISK_MB", "512"))
    budget = max_mb * 1024 * 1024
    messages = {
        50: "Keep an eye on the space.",
        80: "You are approaching critical space.",
        90: "You are at 90%. You will be auto-terminated at 100%. Be aware.",
    }
    fired: set[int] = set()
    while True:
        used = _dir_bytes(_WORKSPACE)
        pct = int(used * 100 / budget) if budget else 0
        if pct >= 100:
            _emit("disk", {"event": "disk-limit", "pct": pct, "msg": "Auto-terminating: disk budget reached."})
            _terminate_agent()
            return
        for threshold in (90, 80, 50):
            if pct >= threshold and threshold not in fired:
                fired.add(threshold)
                _emit("disk", {"event": "disk-warning", "pct": pct, "threshold": threshold, "msg": messages[threshold]})
                break
        time.sleep(interval)


def _terminate_agent() -> None:
    """Stop the agent: SIGTERM the claude process (PID in COORDINATE__PID), else PID 1 so the
    container exits."""
    pid_env = os.environ.get("COORDINATE__PID")
    try:
        os.kill(int(pid_env) if pid_env else 1, signal.SIGTERM)
    except ProcessLookupError, ValueError, PermissionError:
        pass


def run_daemons(token: str) -> None:
    """Spawn `coordinate relay` + `coordinate disk-monitor` and restart whichever dies."""
    specs = [["relay"], ["disk-monitor"]]
    procs: dict[int, list[str]] = {}

    def _spawn(argv: list[str]) -> None:
        # Frozen (PyInstaller): sys.executable IS the `coordinate` binary, so invoke its subcommand
        # directly. In dev, sys.executable is python, so go through `-m coordinate_cli`.
        cmd = (
            [sys.executable, *argv]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "coordinate_cli", *argv]
        )
        p = subprocess.Popen(cmd, env=os.environ.copy())
        procs[p.pid] = argv

    for spec in specs:
        _spawn(spec)
    _emit("daemons", {"event": "daemons-up", "children": specs})
    while True:
        time.sleep(5)
        for pid, argv in list(procs.items()):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                del procs[pid]
                _emit("daemons", {"event": "child-restart", "child": argv})
                _spawn(argv)
