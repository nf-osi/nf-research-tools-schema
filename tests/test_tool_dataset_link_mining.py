#!/usr/bin/env python3
"""
Tests for scripts/mine_tool_dataset_links.py (nf-osi/nf-research-tools-schema#252).

These tests run offline with no Synapse access -- Synapse-querying functions
(query_datasets, query_dataset_match_values, query_existing_tool_dataset_links)
are exercised only for their pure logic via the functions below that take
already-fetched DataFrames/lists as input.
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


mtdl = _load_module("mine_tool_dataset_links")


def _tool(resource_id, resource_name, resource_type, synonyms=""):
    return {
        "resourceId": resource_id,
        "resourceName": resource_name,
        "resourceType": resource_type,
        "synonyms": synonyms,
    }


def _dataset_row(dataset_id, **overrides):
    row = {
        "id": dataset_id,
        "title": "Some Dataset",
        "description": "A dataset",
        "studyId": "syn999",
        "dataType": ["gene expression"],
        "diseaseFocus": "Neurofibromatosis type 1",
    }
    row.update(overrides)
    return row


def test_find_tool_dataset_links_matches_individual_id_to_cell_line():
    tools_data = [_tool("res-1", "JH-2-002", "Cell Line")]
    datasets = pd.DataFrame([_dataset_row("syn1")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn1", "field": "individualID", "value": "JH-2-002"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert len(links) == 1
    assert links[0]["resourceId"] == "res-1"
    assert links[0]["id"] == "syn1"
    assert links[0]["matchedField"] == "individualID"
    assert links[0]["title"] == "Some Dataset"


def test_find_tool_dataset_links_matches_model_system_name_to_animal_model():
    tools_data = [_tool("res-2", "NSG", "Animal Model")]
    datasets = pd.DataFrame([_dataset_row("syn2")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn2", "field": "modelSystemName", "value": "NSG"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert len(links) == 1
    assert links[0]["resourceId"] == "res-2"
    assert links[0]["matchedField"] == "modelSystemName"


def test_find_tool_dataset_links_does_not_cross_match_field_to_wrong_resource_type():
    """individualID must only match Cell Line tools and modelSystemName must
    only match Animal Model tools -- a same-named tool of the "wrong" type
    for that field must not match."""
    tools_data = [_tool("res-3", "NSG", "Cell Line")]  # NSG registered as a Cell Line, not Animal Model
    datasets = pd.DataFrame([_dataset_row("syn3")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn3", "field": "modelSystemName", "value": "NSG"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert links == []


def test_find_tool_dataset_links_matches_via_synonym():
    tools_data = [_tool("res-4", "NCC-MPNST1-C1", "Cell Line", synonyms="ipn02.3, ipnNF95.11c")]
    datasets = pd.DataFrame([_dataset_row("syn4")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn4", "field": "individualID", "value": "ipn02.3"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert len(links) == 1
    assert links[0]["resourceId"] == "res-4"


def test_find_tool_dataset_links_matches_stripped_disambiguation_suffix():
    tools_data = [_tool("res-5", "JH-2-031 (MPNST)", "Cell Line")]
    datasets = pd.DataFrame([_dataset_row("syn5")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn5", "field": "individualID", "value": "JH-2-031"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert len(links) == 1
    assert links[0]["resourceId"] == "res-5"


def test_find_tool_dataset_links_skips_ambiguous_stripped_suffix():
    tools_data = [
        _tool("res-6a", "JH-2-002 (MPNST)", "Cell Line"),
        _tool("res-6b", "JH-2-002 (pNF)", "Cell Line"),
    ]
    datasets = pd.DataFrame([_dataset_row("syn6")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn6", "field": "individualID", "value": "JH-2-002"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert links == []


def test_find_tool_dataset_links_skips_already_existing():
    tools_data = [_tool("res-7", "NF1-Cell-A", "Cell Line")]
    datasets = pd.DataFrame([_dataset_row("syn7")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn7", "field": "individualID", "value": "NF1-Cell-A"}]
    )
    links = mtdl.find_tool_dataset_links(
        match_values, datasets, tools_data, existing_links={("res-7", "syn7")}
    )
    assert links == []


def test_find_tool_dataset_links_dedupes_multiple_occurrences_of_same_pair():
    tools_data = [_tool("res-8", "Repeated Tool", "Cell Line")]
    datasets = pd.DataFrame([_dataset_row("syn8")])
    match_values = pd.DataFrame(
        [
            {"datasetId": "syn8", "field": "individualID", "value": "Repeated Tool"},
            {"datasetId": "syn8", "field": "individualID", "value": "Repeated Tool"},
        ]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert len(links) == 1


def test_find_tool_dataset_links_ignores_unmatched_values():
    tools_data = [_tool("res-9", "Known Tool", "Cell Line")]
    datasets = pd.DataFrame([_dataset_row("syn9")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn9", "field": "individualID", "value": "Totally Unrelated Sample"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert links == []


def test_find_tool_dataset_links_ignores_unknown_field():
    """A (dataset, field, value) row for a field other than individualID/
    modelSystemName should be ignored rather than raising."""
    tools_data = [_tool("res-10", "Known Tool", "Cell Line")]
    datasets = pd.DataFrame([_dataset_row("syn10")])
    match_values = pd.DataFrame(
        [{"datasetId": "syn10", "field": "specimenID", "value": "Known Tool"}]
    )
    links = mtdl.find_tool_dataset_links(match_values, datasets, tools_data, existing_links=set())
    assert links == []


def test_query_dataset_match_values_skips_datasets_without_match_columns():
    """A dataset whose own item table has neither individualID nor
    modelSystemName should be skipped without an extra query."""

    class FakeSyn:
        def getTableColumns(self, dataset_id):
            return [{"name": "assay"}, {"name": "fileFormat"}]

        def tableQuery(self, query):
            raise AssertionError("tableQuery should not be called when no match columns exist")

    result = mtdl.query_dataset_match_values(FakeSyn(), ["syn11"])
    assert result.empty
    assert list(result.columns) == ["datasetId", "field", "value"]


def test_save_and_load_tool_dataset_links_round_trip(tmp_path):
    links = [
        {
            "resourceId": "res-11",
            "resourceName": "Known Tool",
            "resourceType": "Cell Line",
            "id": "syn12",
            "title": "Some Dataset",
            "description": "A dataset",
            "studyId": "syn999",
            "dataType": ["gene expression", "clinical"],
            "diseaseFocus": "Neurofibromatosis type 1",
            "matchedField": "individualID",
            "matchedVia": "Known Tool",
        }
    ]
    path = tmp_path / "tool_dataset_links_for_review.csv"
    mtdl.save_tool_dataset_links_for_review(links, path)

    loaded = mtdl.load_tool_dataset_links_from_review(path)
    assert len(loaded) == 1
    assert loaded[0]["resourceId"] == "res-11"
    assert loaded[0]["dataType"] == ["gene expression", "clinical"]
