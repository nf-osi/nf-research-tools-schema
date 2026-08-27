#!/usr/bin/env python3
"""
Tests for scripts/snapshot_synapse_tables.py -- the reusable snapshot +
rollback-manifest tool for the staging procedure formalized in
nf-research-tools-schema#265 (docs/STAGING_PROCEDURE.md).

Offline: table selection and manifest-building tests use a fake Synapse
client. Only resolve_table_ids' --from-schema/--class-name paths touch the
real (local, no-network) LinkML schema file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


snap = _load_module("snapshot_synapse_tables")


class _FakeEntity(dict):
    """synapseclient entities are dict-like with .get(); this is enough
    for capture_entity_state()."""


class _FakeSyn:
    def __init__(self, entities: dict, snapshot_versions: dict):
        self._entities = entities
        self._snapshot_versions = snapshot_versions
        self.snapshot_calls = []

    def get(self, entity_id, downloadFile=False):
        return self._entities[entity_id]

    def create_snapshot_version(self, table_id, comment=None):
        self.snapshot_calls.append((table_id, comment))
        return self._snapshot_versions[table_id]


def _args(**overrides):
    base = dict(table_id=None, class_name=None, from_schema=False)
    base.update(overrides)
    return SimpleNamespace(**base)


# --- resolve_table_ids ---------------------------------------------------- #

def test_resolve_table_ids_explicit():
    ids = snap.resolve_table_ids(_args(table_id=["syn1", "syn2"]))
    assert ids == ["syn1", "syn2"]


def test_resolve_table_ids_dedupes_explicit():
    ids = snap.resolve_table_ids(_args(table_id=["syn1", "syn1", "syn2"]))
    assert ids == ["syn1", "syn2"]


def test_resolve_table_ids_from_schema_returns_all_schema_tables():
    ids = snap.resolve_table_ids(_args(from_schema=True))
    assert "syn26486823" in ids  # CellLine
    assert len(ids) >= 9


def test_resolve_table_ids_class_name_filters_to_selected_classes():
    ids = snap.resolve_table_ids(_args(class_name=["CellLine", "AnimalModel"]))
    assert set(ids) == {"syn26486823", "syn26486808"}


def test_resolve_table_ids_unknown_class_name_raises():
    with pytest.raises(SystemExit, match="NotAClass"):
        snap.resolve_table_ids(_args(class_name=["NotAClass"]))


def test_resolve_table_ids_no_selection_raises():
    with pytest.raises(SystemExit, match="No tables selected"):
        snap.resolve_table_ids(_args())


def test_resolve_table_ids_merges_explicit_and_schema_without_duplicating():
    ids = snap.resolve_table_ids(_args(table_id=["syn26486823"], class_name=["CellLine"]))
    assert ids.count("syn26486823") == 1


# --- capture_entity_state -------------------------------------------------- #

def test_capture_entity_state_table_has_no_defining_sql():
    entity = _FakeEntity(
        name="CellLineDetails", concreteType="org.sagebionetworks.repo.model.table.TableEntity",
        versionNumber=30, etag="abc", columnIds=["1", "2"],
    )
    syn = _FakeSyn({"syn1": entity}, {})
    state = snap.capture_entity_state(syn, "syn1")
    assert state["id"] == "syn1"
    assert state["versionNumber"] == 30
    assert "definingSQL" not in state


def test_capture_entity_state_mv_captures_defining_sql():
    entity = _FakeEntity(
        name="FinalMV", concreteType="org.sagebionetworks.repo.model.table.MaterializedView",
        versionNumber=5, etag="xyz", columnIds=["9"],
        definingSQL="SELECT * FROM syn1",
    )
    syn = _FakeSyn({"syn2": entity}, {})
    state = snap.capture_entity_state(syn, "syn2")
    assert state["definingSQL"] == "SELECT * FROM syn1"


# --- snapshot_all / format_summary_table ----------------------------------- #

def test_snapshot_all_snapshots_every_table_and_records_version():
    entities = {
        "syn1": _FakeEntity(name="A", concreteType="t", versionNumber=1, etag="e1", columnIds=[]),
        "syn2": _FakeEntity(name="B", concreteType="t", versionNumber=2, etag="e2", columnIds=[]),
    }
    syn = _FakeSyn(entities, {"syn1": 11, "syn2": 22})
    manifest = snap.snapshot_all(syn, ["syn1", "syn2"], "test comment")

    assert syn.snapshot_calls == [("syn1", "test comment"), ("syn2", "test comment")]
    assert [e["snapshotVersion"] for e in manifest["entities"]] == [11, 22]
    assert manifest["comment"] == "test comment"
    assert "capturedAt" in manifest


def test_format_summary_table_renders_markdown_with_name_syn_and_version():
    manifest = {
        "entities": [
            {"id": "syn1", "name": "CellLineDetails", "snapshotVersion": 30},
            {"id": "syn2", "name": None, "snapshotVersion": 7},
        ]
    }
    table = snap.format_summary_table(manifest)
    assert "| CellLineDetails | syn1 | 30 |" in table
    assert "| syn2 | syn2 | 7 |" in table  # falls back to id when name is None
