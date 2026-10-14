#!/usr/bin/env python3
"""
Every upsert write snapshots the table first (once per table per run) and
after, so curator edits made directly in Synapse since the last snapshot are
never lost on rollback. Runs offline with a fake Synapse client.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "tool_coverage" / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("clean_submission_csvs", SCRIPTS / "clean_submission_csvs.py")
clean = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = clean
spec.loader.exec_module(clean)


class _FakeSyn:
    def __init__(self, fail_snapshot=False):
        self.calls = []
        self.fail_snapshot = fail_snapshot

    def create_snapshot_version(self, table_id, comment=None):
        if self.fail_snapshot:
            raise RuntimeError("no snapshot")
        self.calls.append(("snapshot", table_id, comment.split(" ")[0]))

    def store(self, table):
        self.calls.append(("store", table.tableId, None))
        return table


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(clean, "_PRE_SNAPSHOTTED", set())


def test_snapshot_before_first_write_and_after_each():
    syn = _FakeSyn()
    df = pd.DataFrame({"a": [1]})
    clean.store_with_snapshots(syn, "syn1", df)
    clean.store_with_snapshots(syn, "syn1", df)
    clean.store_with_snapshots(syn, "syn2", df)
    assert syn.calls == [
        ("snapshot", "syn1", "before"), ("store", "syn1", None), ("snapshot", "syn1", "after"),
        ("store", "syn1", None), ("snapshot", "syn1", "after"),
        ("snapshot", "syn2", "before"), ("store", "syn2", None), ("snapshot", "syn2", "after"),
    ]


def test_no_write_without_pre_snapshot():
    syn = _FakeSyn(fail_snapshot=True)
    with pytest.raises(RuntimeError):
        clean.store_with_snapshots(syn, "syn1", pd.DataFrame({"a": [1]}))
    assert syn.calls == []
