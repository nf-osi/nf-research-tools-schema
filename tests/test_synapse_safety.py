#!/usr/bin/env python3
"""
Tests for scripts/synapse_safety.py -- the shared before/after-snapshot and
no-delete-without-explicit-confirmation wrappers enforcing standing policy
(established 2026-08 after an automated MV rebuild accidentally trashed
live production entities).

These tests run offline with no Synapse access -- the Synapse client is
replaced with fakes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


safety = _load_module("synapse_safety")


class _FakeSyn:
    def __init__(self, snapshot_version=7, delete_error=None):
        self.snapshot_calls = []
        self.store_calls = []
        self.delete_calls = []
        self._snapshot_version = snapshot_version
        self._delete_error = delete_error

    def create_snapshot_version(self, table_id, comment=None):
        self.snapshot_calls.append((table_id, comment))
        return self._snapshot_version

    def store(self, obj):
        self.store_calls.append(obj)
        return obj

    def delete(self, entity_id):
        if self._delete_error:
            raise self._delete_error
        self.delete_calls.append(entity_id)


class _FakeTableWithTableId:
    def __init__(self, table_id):
        self.tableId = table_id


class _FakeTableWithSchema:
    def __init__(self, schema_id):
        self.schema = schema_id


# --- snapshot_table ---------------------------------------------------- #

def test_snapshot_table_returns_version_on_success():
    syn = _FakeSyn(snapshot_version=42)
    version = safety.snapshot_table(syn, "syn123", "a comment")
    assert version == 42
    assert syn.snapshot_calls == [("syn123", "a comment")]


def test_snapshot_table_swallows_exception_and_returns_none():
    class _FailingSyn:
        def create_snapshot_version(self, table_id, comment=None):
            raise RuntimeError("boom")

    version = safety.snapshot_table(_FailingSyn(), "syn123", "a comment")
    assert version is None


def test_snapshot_table_handles_dict_style_response():
    class _DictReturningSyn:
        def create_snapshot_version(self, table_id, comment=None):
            return {"snapshotVersionNumber": 9}

    version = safety.snapshot_table(_DictReturningSyn(), "syn123", "a comment")
    assert version == 9


# --- safe_store ---------------------------------------------------------- #

def test_safe_store_snapshots_before_and_after():
    syn = _FakeSyn()
    table = _FakeTableWithTableId("syn999")
    result = safety.safe_store(syn, table, comment="test write")
    assert result is table
    assert syn.store_calls == [table]
    assert syn.snapshot_calls == [
        ("syn999", "test write -- before"),
        ("syn999", "test write -- after"),
    ]


def test_safe_store_infers_table_id_from_schema_attr():
    syn = _FakeSyn()
    table = _FakeTableWithSchema("syn888")
    safety.safe_store(syn, table, comment="test write")
    assert syn.snapshot_calls[0][0] == "syn888"


def test_safe_store_accepts_explicit_table_id_override():
    syn = _FakeSyn()
    table = _FakeTableWithTableId("syn999")
    safety.safe_store(syn, table, comment="test write", table_id="syn777")
    assert syn.snapshot_calls[0][0] == "syn777"


def test_safe_store_raises_when_table_id_cannot_be_resolved():
    syn = _FakeSyn()
    with pytest.raises(ValueError):
        safety.safe_store(syn, object(), comment="test write")


# --- safe_delete ---------------------------------------------------------- #

def test_safe_delete_refuses_without_confirmation():
    syn = _FakeSyn()
    with pytest.raises(safety.DeletionNotConfirmedError):
        safety.safe_delete(syn, "syn123")
    assert syn.delete_calls == []


def test_safe_delete_refuses_with_confirmed_false_explicitly():
    syn = _FakeSyn()
    with pytest.raises(safety.DeletionNotConfirmedError):
        safety.safe_delete(syn, "syn123", confirmed=False)
    assert syn.delete_calls == []


def test_safe_delete_proceeds_when_confirmed():
    syn = _FakeSyn()
    safety.safe_delete(syn, "syn123", confirmed=True, reason="orphaned duplicate")
    assert syn.delete_calls == ["syn123"]
