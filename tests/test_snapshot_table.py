#!/usr/bin/env python3
"""
Tests for snapshot_table, the before/after snapshot helper added to
scripts/review_tool_annotations.py per standing policy: every automated
table/view write is bracketed by a snapshot on both sides.

These tests run offline with no Synapse access -- syn.create_snapshot_version
is replaced with a fake.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rta = _load_module("review_tool_annotations")


class _FakeSynSuccess:
    def __init__(self):
        self.calls = []

    def create_snapshot_version(self, table_id, comment=None):
        self.calls.append((table_id, comment))
        return 7


class _FakeSynFailure:
    def create_snapshot_version(self, table_id, comment=None):
        raise RuntimeError("simulated Synapse error")


def test_snapshot_table_returns_version_on_success():
    syn = _FakeSynSuccess()
    version = rta.snapshot_table(syn, "syn123", "test comment")
    assert version == 7
    assert syn.calls == [("syn123", "test comment")]


def test_snapshot_table_swallows_exception_and_returns_none():
    """A snapshot failure must be logged, not raised -- it should never
    block (or be blocked by) the write it's bracketing."""
    syn = _FakeSynFailure()
    version = rta.snapshot_table(syn, "syn123", "test comment")
    assert version is None
