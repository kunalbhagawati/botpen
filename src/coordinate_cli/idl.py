"""Load the Thrift IDL (``hub.thrift``) that defines the daemon contract.

In a PyInstaller one-file build the IDL is bundled next to the binary (`--add-data`), reachable
via ``sys._MEIPASS``. In dev it lives at ``src/resources/hub.thrift`` beside this package.
"""

from __future__ import annotations

import os
import sys

import thriftpy2

_module = None


def _idl_path() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return os.path.join(sys._MEIPASS, "hub.thrift")  # pyrefly: ignore [missing-attribute]
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, os.pardir, "resources", "hub.thrift")


def hub():
    """The loaded Thrift module (cached). Exposes `Hub` (service) and `GrantNode` (struct)."""
    global _module
    if _module is None:
        _module = thriftpy2.load(_idl_path(), module_name="hub_thrift")
    return _module
