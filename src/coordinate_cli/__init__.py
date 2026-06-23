"""The `coordinate` binary: the agent-side client, the container's only handshake to the host.

A standalone CLI (PyInstaller one-file) that the in-container agent uses instead of
`uv run manage.py`. It speaks Thrift RPC to the host mailbox daemon and consumes the WebSocket
push channel. Deliberately import-light - no `bots`/`sqlmodel`/`config`, no DB access, no repo
source. Everything it knows is the shipped `mailbox.thrift` contract and the host URL + token.
"""
