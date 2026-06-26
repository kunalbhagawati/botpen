"""The `coordinate` binary: the agent-side client, the container's only handshake to the host.

A standalone CLI (PyInstaller one-file) that the in-container agent uses - the agent never has the
host `botpen` CLI. It speaks Thrift RPC to the Hub and consumes the WebSocket push channel.
Deliberately import-light - no `botpen`/`sqlmodel`/`config`, no DB access, no repo source.
Everything it knows is the shipped `hub.thrift` contract and the Hub host + token.
"""
