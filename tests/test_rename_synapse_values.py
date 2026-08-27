#!/usr/bin/env python3
"""
Tests for scripts/rename_synapse_values.py -- the reusable Synapse
value-rename tooling from nf-research-tools-schema#274.

These tests run offline with no Synapse access -- the Synapse client is
replaced with fakes, matching the pattern in tests/test_synapse_safety.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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


rsv = _load_module("rename_synapse_values")


class _FakeQueryResult:
    def __init__(self, df: pd.DataFrame, etag: str = "rowset-etag"):
        self._df = df
        self.etag = etag

    def asDataFrame(self):
        return self._df


class _FakeSyn:
    """Fakes just enough of synapseclient.Synapse for rename_synapse_values
    to run against: getTableColumns, tableQuery, and (via safe_store /
    safe_store_row_patch) create_snapshot_version/store."""

    def __init__(self, columns: list[dict], query_df: pd.DataFrame, query_etag: str = "rowset-etag"):
        self._columns = columns
        self._query_df = query_df
        self._query_etag = query_etag
        self.queries = []
        self.snapshot_calls = []
        self.store_calls = []

    def getTableColumns(self, table_id):
        return self._columns

    def tableQuery(self, query):
        self.queries.append(query)
        return _FakeQueryResult(self._query_df, etag=self._query_etag)

    def create_snapshot_version(self, table_id, comment=None):
        self.snapshot_calls.append((table_id, comment))
        return 1

    def store(self, obj):
        self.store_calls.append(obj)
        return obj


# --- load_mapping --------------------------------------------------------- #

def test_load_mapping_from_file(tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"syn1": {"col": {"old": "new"}}}')
    args = _Args(mapping_file=str(f), set=None)
    assert rsv.load_mapping(args) == {"syn1": {"col": {"old": "new"}}}


def test_load_mapping_from_set_only():
    args = _Args(mapping_file=None, set=["syn1:tissue:Primary Tumor=Primary tumor"])
    assert rsv.load_mapping(args) == {"syn1": {"tissue": {"Primary Tumor": "Primary tumor"}}}


def test_load_mapping_from_set_layers_onto_file(tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"syn1": {"col": {"old": "new"}}}')
    args = _Args(mapping_file=str(f), set=["syn1:col2:a=b", "syn2:col3:c=d"])
    mapping = rsv.load_mapping(args)
    assert mapping == {
        "syn1": {"col": {"old": "new"}, "col2": {"a": "b"}},
        "syn2": {"col3": {"c": "d"}},
    }


def test_load_mapping_set_handles_equals_in_value():
    # DOI-style values contain '://' but not '=' -- confirm the split only
    # breaks on the first '=' so values are passed through unmangled.
    args = _Args(mapping_file=None, set=["syn1:doi:https://old=https://new"])
    mapping = rsv.load_mapping(args)
    assert mapping == {"syn1": {"doi": {"https://old": "https://new"}}}


def test_load_mapping_rejects_malformed_set():
    args = _Args(mapping_file=None, set=["not-well-formed"])
    with pytest.raises(SystemExit):
        rsv.load_mapping(args)


def test_load_mapping_rejects_empty():
    args = _Args(mapping_file=None, set=None)
    with pytest.raises(SystemExit):
        rsv.load_mapping(args)


class _Args:
    def __init__(self, mapping_file, set):
        self.mapping_file = mapping_file
        self.set = set


# --- query builders -------------------------------------------------------- #

def test_scalar_candidate_query_literal_only():
    q = rsv.scalar_candidate_query("syn1", "tissue", {"Primary Tumor": "Primary tumor"})
    assert q == "SELECT \"tissue\" FROM syn1 WHERE \"tissue\" IN ('Primary Tumor')"


def test_scalar_candidate_query_multiple_keys():
    q = rsv.scalar_candidate_query("syn1", "tissue", {"old1": "new1", "old2": "new2"})
    assert q == "SELECT \"tissue\" FROM syn1 WHERE \"tissue\" IN ('old1', 'old2')"


def test_list_candidate_query():
    q = rsv.list_candidate_query("syn1", "manifestation", {"a": "b"})
    assert q == "SELECT \"manifestation\" FROM syn1 WHERE \"manifestation\" HAS ('a')"


# --- apply_scalar_rename --------------------------------------------------- #

def test_apply_scalar_rename_skips_case_insensitive_false_positive():
    # Synapse SQL's IN (...) is case-insensitive, so a candidate row already
    # correctly cased ('Primary tumor') can come back alongside the real
    # match -- only the exact-case match should be rewritten.
    df = pd.DataFrame({"tissue": ["Primary Tumor", "Primary tumor"]}, index=["1_0", "2_0"])
    syn = _FakeSyn(columns=[], query_df=df)
    rsv.apply_scalar_rename(syn, "syn1", "tissue", {"Primary Tumor": "Primary tumor"}, dry_run=False, comment="c")
    assert len(syn.store_calls) == 1
    stored_df = syn.store_calls[0].asDataFrame()
    assert list(stored_df.index) == ["1_0"]
    assert list(stored_df["tissue"]) == ["Primary tumor"]


def test_apply_scalar_rename_uses_fresh_rowset_etag_not_entity_etag():
    # The row-update endpoint needs the *query RowSet's* changeset etag,
    # not the table entity's etag -- see safe_store_row_patch()'s docstring.
    df = pd.DataFrame({"tissue": ["Primary Tumor"]}, index=["1_0"])
    syn = _FakeSyn(columns=[], query_df=df, query_etag="fresh-rowset-etag")
    rsv.apply_scalar_rename(syn, "syn1", "tissue", {"Primary Tumor": "Primary tumor"}, dry_run=False, comment="c")
    assert syn.store_calls[0].etag == "fresh-rowset-etag"


def test_apply_scalar_rename_queries_again_after_before_snapshot():
    # Must re-query (for a fresh RowSet etag) strictly after the
    # before-snapshot, never reusing the dry-run-style preview read.
    df = pd.DataFrame({"tissue": ["Primary Tumor"]}, index=["1_0"])
    syn = _FakeSyn(columns=[], query_df=df)
    seen_query_count_before_store = []
    real_store = syn.store

    def spying_store(obj):
        seen_query_count_before_store.append(len(syn.queries))
        return real_store(obj)

    syn.store = spying_store
    rsv.apply_scalar_rename(syn, "syn1", "tissue", {"Primary Tumor": "Primary tumor"}, dry_run=False, comment="c")
    assert len(syn.queries) == 2  # preview read, then the fresh post-snapshot read
    assert seen_query_count_before_store == [2]


def test_apply_scalar_rename_dry_run_makes_no_writes():
    df = pd.DataFrame({"tissue": ["Primary Tumor"]}, index=["1_0"])
    syn = _FakeSyn(columns=[], query_df=df)
    rsv.apply_scalar_rename(syn, "syn1", "tissue", {"Primary Tumor": "Primary tumor"}, dry_run=True, comment="c")
    assert syn.store_calls == []
    assert syn.snapshot_calls == []


def test_apply_scalar_rename_no_matches_makes_no_writes():
    df = pd.DataFrame({"tissue": []}, dtype=object)
    syn = _FakeSyn(columns=[], query_df=df)
    rsv.apply_scalar_rename(syn, "syn1", "tissue", {"Primary Tumor": "Primary tumor"}, dry_run=False, comment="c")
    assert syn.store_calls == []
    assert syn.snapshot_calls == []  # nothing to patch -- never even reaches safe_store_row_patch


def test_apply_scalar_rename_snapshots_before_and_after():
    df = pd.DataFrame({"tissue": ["Primary Tumor"]}, index=["1_0"])
    syn = _FakeSyn(columns=[], query_df=df)
    rsv.apply_scalar_rename(syn, "syn1", "tissue", {"Primary Tumor": "Primary tumor"}, dry_run=False, comment="c")
    assert syn.snapshot_calls == [("syn1", "c: tissue -- before"), ("syn1", "c: tissue -- after")]


# --- apply_list_rename ------------------------------------------------------ #

def test_apply_list_rename_replaces_only_matching_element():
    df = pd.DataFrame(
        {"manifestation": [["cervical adenocarcinoma", "other value"]]}, index=["1_0"]
    )
    syn = _FakeSyn(
        columns=[{"id": "999", "name": "manifestation", "columnType": "STRING_LIST"}],
        query_df=df,
    )
    rsv.apply_list_rename(
        syn, "syn1", "manifestation",
        {"cervical adenocarcinoma": "Cervical Adenocarcinoma"},
        dry_run=False, comment="c",
    )
    assert len(syn.store_calls) == 1
    stored = syn.store_calls[0]
    row = stored.rows[0]
    assert row.rowId == 1
    assert row.values == [{"key": "999", "value": ["Cervical Adenocarcinoma", "other value"]}]


def test_apply_list_rename_skips_rows_already_correct():
    df = pd.DataFrame({"manifestation": [["Cervical Adenocarcinoma"]]}, index=["1_0"])
    syn = _FakeSyn(
        columns=[{"id": "999", "name": "manifestation", "columnType": "STRING_LIST"}],
        query_df=df,
    )
    rsv.apply_list_rename(
        syn, "syn1", "manifestation",
        {"cervical adenocarcinoma": "Cervical Adenocarcinoma"},
        dry_run=False, comment="c",
    )
    assert syn.store_calls == []


def test_apply_list_rename_dry_run_makes_no_writes():
    df = pd.DataFrame({"manifestation": [["cervical adenocarcinoma"]]}, index=["1_0"])
    syn = _FakeSyn(
        columns=[{"id": "999", "name": "manifestation", "columnType": "STRING_LIST"}],
        query_df=df,
    )
    rsv.apply_list_rename(
        syn, "syn1", "manifestation",
        {"cervical adenocarcinoma": "Cervical Adenocarcinoma"},
        dry_run=True, comment="c",
    )
    assert syn.store_calls == []


# --- apply_mapping dispatch -------------------------------------------------- #

def test_apply_mapping_dispatches_to_scalar_for_string_column():
    df = pd.DataFrame({"tissue": ["Primary Tumor"]}, index=["1_0"])
    syn = _FakeSyn(columns=[{"id": "1", "name": "tissue", "columnType": "STRING"}], query_df=df)
    rsv.apply_mapping(syn, {"syn1": {"tissue": {"Primary Tumor": "Primary tumor"}}}, dry_run=False, comment="c")
    assert len(syn.store_calls) == 1


def test_apply_mapping_rejects_unsupported_column_type():
    syn = _FakeSyn(columns=[{"id": "1", "name": "count", "columnType": "INTEGER"}], query_df=pd.DataFrame())
    with pytest.raises(ValueError, match="unsupported column type"):
        rsv.apply_mapping(syn, {"syn1": {"count": {"1": "2"}}}, dry_run=False, comment="c")


def test_apply_mapping_rejects_unknown_column():
    syn = _FakeSyn(columns=[{"id": "1", "name": "tissue", "columnType": "STRING"}], query_df=pd.DataFrame())
    with pytest.raises(ValueError, match="not found"):
        rsv.apply_mapping(syn, {"syn1": {"nope": {"a": "b"}}}, dry_run=False, comment="c")
