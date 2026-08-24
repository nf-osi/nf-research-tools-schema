#!/usr/bin/env python3
"""
Tests for the Resource_id file-annotation backfill added to
scripts/review_tool_annotations.py
(nf-osi/nf-research-tools-schema#154,
https://github.com/nf-osi/nf-research-tools-schema/issues/154#issuecomment-5394955094).

This backfills Resource_id directly onto files whose individualID matches a
known tool, so the existing Tool Details "Data > Files" tab (which already
renders off Resource_id) picks up more files with no frontend change.

The critical, easy-to-break invariant under test here (see
find_resource_id_annotations' docstring) is that the returned DataFrame's
pandas index must be the SAME rowId_rowVersion labels as the input -- that's
what makes upsert_resource_id_annotations' syn.store() call an UPDATE of
those specific existing file rows rather than an attempted insert (a
fileview's rows can't be inserted directly).

These tests run offline with no Synapse access.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rta = _load_module("review_tool_annotations")


def _tool(resource_id, resource_name, synonyms=""):
    return {
        "resourceId": resource_id,
        "resourceName": resource_name,
        "resourceType": "Cell Line",
        "rrid": None,
        "description": None,
        "synonyms": synonyms,
    }


def _file_occurrences(rows, index):
    """rows: list of (id, individualID, Resource_id) tuples. index: rowId_rowVersion labels."""
    return pd.DataFrame(
        [{"id": r[0], "individualID": r[1], "Resource_id": r[2]} for r in rows],
        index=index,
    )


def test_find_resource_id_annotations_appends_to_existing_list():
    tools_data = [_tool("res-1", "NCC-MPNST1-C1")]
    occurrences = _file_occurrences(
        [("syn111", "NCC-MPNST1-C1", ["some-other-resource-id"])],
        index=["111_2"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert len(updates) == 1
    assert updates.iloc[0]["id"] == "syn111"
    assert updates.iloc[0]["Resource_id"] == ["some-other-resource-id", "res-1"]


def test_find_resource_id_annotations_preserves_row_index():
    """The returned DataFrame's index must match the input's rowId_rowVersion
    labels exactly -- Synapse uses this to target the UPDATE, per
    find_resource_id_annotations' docstring."""
    tools_data = [_tool("res-2", "Known Tool")]
    occurrences = _file_occurrences(
        [("syn222", "Known Tool", None)],
        index=["222_5"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert list(updates.index) == ["222_5"]


def test_find_resource_id_annotations_handles_null_existing_value():
    tools_data = [_tool("res-3", "Fresh Tool")]
    occurrences = _file_occurrences(
        [("syn333", "Fresh Tool", None)],
        index=["333_0"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert len(updates) == 1
    assert updates.iloc[0]["Resource_id"] == ["res-3"]


def test_find_resource_id_annotations_skips_when_already_present():
    tools_data = [_tool("res-4", "Already Tagged Tool")]
    occurrences = _file_occurrences(
        [("syn444", "Already Tagged Tool", ["res-4"])],
        index=["444_1"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert updates.empty


def test_find_resource_id_annotations_skips_when_list_at_max_length():
    tools_data = [_tool("res-5", "Full List Tool")]
    full_list = [f"other-{i}" for i in range(rta.RESOURCE_ID_MAX_LIST_LENGTH)]
    occurrences = _file_occurrences(
        [("syn555", "Full List Tool", full_list)],
        index=["555_0"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert updates.empty


def test_find_resource_id_annotations_ignores_unmatched_individual_ids():
    tools_data = [_tool("res-6", "Known Tool")]
    occurrences = _file_occurrences(
        [("syn666", "Totally Unrelated Sample", None)],
        index=["666_0"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert updates.empty


def test_find_resource_id_annotations_skips_ambiguous_stripped_suffix():
    tools_data = [
        _tool("res-7a", "JH-2-002 (MPNST)"),
        _tool("res-7b", "JH-2-002 (pNF)"),
    ]
    occurrences = _file_occurrences(
        [("syn777", "JH-2-002", None)],
        index=["777_0"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert updates.empty


def test_find_resource_id_annotations_only_returns_files_needing_change():
    tools_data = [_tool("res-8", "Known Tool")]
    occurrences = _file_occurrences(
        [
            ("syn888", "Known Tool", None),  # needs update
            ("syn889", "Already Tagged", ["res-8"]),  # unmatched name anyway
            ("syn890", "Known Tool", ["res-8"]),  # already tagged, skip
        ],
        index=["888_0", "889_0", "890_0"],
    )
    updates = rta.find_resource_id_annotations(occurrences, tools_data)
    assert len(updates) == 1
    assert updates.iloc[0]["id"] == "syn888"
    assert list(updates.index) == ["888_0"]
