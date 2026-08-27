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
from types import SimpleNamespace

import pandas as pd
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
    def __init__(self, snapshot_version=7, delete_error=None, fresh_etag=None, get_error=None, query_df=None):
        self.snapshot_calls = []
        self.store_calls = []
        self.delete_calls = []
        self.get_calls = []
        self.query_calls = []
        self._snapshot_version = snapshot_version
        self._delete_error = delete_error
        self._fresh_etag = fresh_etag
        self._get_error = get_error
        self._query_df = query_df

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

    def get(self, entity_id, downloadFile=False):
        self.get_calls.append(entity_id)
        if self._get_error:
            raise self._get_error
        return SimpleNamespace(etag=self._fresh_etag)

    def tableQuery(self, query):
        self.query_calls.append(query)
        return SimpleNamespace(asDataFrame=lambda: self._query_df)


class _FakeTableWithTableId:
    def __init__(self, table_id):
        self.tableId = table_id


class _FakeTableWithSchema:
    def __init__(self, schema_id):
        self.schema = schema_id


class _FakeEntityWithEtag:
    """Mimics a fetched Schema/Entity object with a stale etag carried
    over from before a pre-write snapshot bumped the server-side version."""
    def __init__(self, table_id, etag):
        self.tableId = table_id
        self.etag = etag


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


def test_safe_store_refreshes_stale_etag_before_storing():
    """The pre-write snapshot bumps the entity's version/etag server-side.
    For a *fetched* entity object (carries an etag from before the
    snapshot), storing it unmodified would fail with "updated since you
    last fetched" -- safe_store must refresh .etag from the server after
    snapshotting but before the actual store."""
    syn = _FakeSyn(fresh_etag="etag-after-snapshot")
    entity = _FakeEntityWithEtag("syn999", etag="etag-before-snapshot")
    safety.safe_store(syn, entity, comment="test write")
    assert entity.etag == "etag-after-snapshot"
    assert syn.get_calls == ["syn999"]
    assert syn.store_calls == [entity]


def test_safe_store_tolerates_etag_refresh_failure():
    """If the refresh fetch itself fails, safe_store should still attempt
    the store with whatever etag the caller already had -- not crash."""
    syn = _FakeSyn(get_error=RuntimeError("network blip"))
    entity = _FakeEntityWithEtag("syn999", etag="etag-before-snapshot")
    safety.safe_store(syn, entity, comment="test write")
    assert entity.etag == "etag-before-snapshot"
    assert syn.store_calls == [entity]


def test_safe_store_skips_etag_refresh_for_objects_without_one():
    """PartialRowset and similar freshly-constructed objects carry no
    etag baggage -- no refresh call needed."""
    class _NoEtag:
        def __init__(self, table_id):
            self.tableId = table_id

    syn = _FakeSyn()
    obj = _NoEtag("syn999")
    safety.safe_store(syn, obj, comment="test write")
    assert syn.get_calls == []


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


# --- safe_delete_rows ------------------------------------------------------ #

def test_safe_delete_rows_refuses_without_confirmation():
    syn = _FakeSyn(query_df=pd.DataFrame({"a": [1, 2]}))
    with pytest.raises(safety.DeletionNotConfirmedError):
        safety.safe_delete_rows(syn, "syn123", "SELECT a FROM syn123", comment="c")
    assert syn.delete_calls == []
    assert syn.query_calls == []  # refuses before even querying
    assert syn.snapshot_calls == []


def test_safe_delete_rows_proceeds_when_confirmed():
    query_result_df = pd.DataFrame({"a": [1, 2, 3]})
    syn = _FakeSyn(query_df=query_result_df)
    n = safety.safe_delete_rows(
        syn, "syn123", "SELECT a FROM syn123 WHERE a > 0", comment="c",
        confirmed=True, reason="moving to usage",
    )
    assert n == 3
    assert syn.query_calls == ["SELECT a FROM syn123 WHERE a > 0"]
    assert len(syn.delete_calls) == 1
    assert syn.snapshot_calls == [("syn123", "c -- before"), ("syn123", "c -- after")]


# --- safe_store_row_patch ------------------------------------------------- #

def test_safe_store_row_patch_snapshots_before_read_and_store():
    """The build_patch callback must run AFTER the before-snapshot, and
    the store must happen with no snapshot in between -- that ordering is
    the whole point of this function (see its docstring)."""
    syn = _FakeSyn()
    calls = []

    def build_patch(passed_syn):
        assert passed_syn is syn
        calls.append("build_patch")
        assert syn.snapshot_calls == [("syn999", "test patch -- before")], (
            "build_patch (the fresh read) must run after the before-snapshot"
        )
        return "the-patch-object"

    result = safety.safe_store_row_patch(syn, "syn999", build_patch, comment="test patch")
    assert result == "the-patch-object"
    assert calls == ["build_patch"]
    assert syn.store_calls == ["the-patch-object"]
    assert syn.snapshot_calls == [
        ("syn999", "test patch -- before"),
        ("syn999", "test patch -- after"),
    ]


def test_safe_store_row_patch_skips_store_when_build_patch_returns_none():
    syn = _FakeSyn()
    result = safety.safe_store_row_patch(syn, "syn999", lambda s: None, comment="test patch")
    assert result is None
    assert syn.store_calls == []
    # the before-snapshot still happened (harmless) -- only the store/after-snapshot are skipped
    assert syn.snapshot_calls == [("syn999", "test patch -- before")]
