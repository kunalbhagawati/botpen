"""Operation layer over the data store.

``messages`` (message/thought/read ops) and ``permissions`` (cross-agent read access). Each
function opens its own short-lived SQLModel session via :mod:`botpen.core.db`. The engine and
table models live in :mod:`botpen.core`.
"""
