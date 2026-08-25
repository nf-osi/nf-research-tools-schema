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
    modelSystemName should narrow the SELECT down via Synapse's "Unknown
    column" error on each field in turn, then give up cleanly (no
    getTableColumns call -- see _query_one_dataset's docstring for why)."""

    class FakeSyn:
        def getTableColumns(self, dataset_id):
            raise AssertionError("getTableColumns should never be called -- see _query_one_dataset docstring")

        def tableQuery(self, query):
            if "individualID" in query:
                raise Exception("400 Client Error: \nUnknown column individualID")
            if "modelSystemName" in query:
                raise Exception("400 Client Error: \nUnknown column modelSystemName")
            raise AssertionError(f"Unexpected query: {query}")

    result, failed = mtdl.query_dataset_match_values(FakeSyn(), ["syn11"])
    assert result.empty
    assert list(result.columns) == ["datasetId", "field", "value"]
    assert failed == []  # neither field existing is not a query failure


def test_query_one_dataset_narrows_select_on_unknown_column_error():
    """A dataset missing only modelSystemName should retry with just
    individualID rather than giving up on the whole dataset."""

    class FakeSyn:
        def tableQuery(self, query):
            if "individualID, modelSystemName" in query or "modelSystemName, individualID" in query:
                raise Exception("400 Client Error: \nUnknown column modelSystemName")
            assert query == "SELECT DISTINCT individualID FROM syn12 WHERE individualID IS NOT NULL"
            return _FakeResults(pd.DataFrame({"individualID": ["JH-2-002"]}))

    rows, error = mtdl._query_one_dataset(FakeSyn(), "syn12")
    assert rows == [{"datasetId": "syn12", "field": "individualID", "value": "JH-2-002"}]
    assert error is None


def test_query_one_dataset_reports_genuine_query_failures():
    """A dataset that fails for a reason other than a missing column (e.g.
    a stale column-size declaration blocking the whole query, confirmed
    live) should be reported as a failure, not silently treated as
    "neither field present."""

    class FakeSyn:
        def tableQuery(self, query):
            raise Exception(
                "400 Client Error: \nThe size of the column 'accessType' is too small.  "
                "The column size needs to be at least 13 characters."
            )

    rows, error = mtdl._query_one_dataset(FakeSyn(), "syn13")
    assert rows == []
    assert "accessType" in error


def test_query_dataset_match_values_collects_failed_datasets():
    class FakeSyn:
        def tableQuery(self, query):
            if "syn14" in query:
                raise Exception("400 Client Error: \nThe size of the column 'accessType' is too small.")
            return _FakeResults(pd.DataFrame({"individualID": ["JH-2-002"]}))

    result, failed = mtdl.query_dataset_match_values(FakeSyn(), ["syn14", "syn15"], max_workers=2)
    assert len(result) == 1
    assert failed == [{"datasetId": "syn14", "error": "The size of the column 'accessType' is too small."}]


def test_query_dataset_match_values_runs_multiple_datasets_concurrently():
    """The thread-pool fan-out in query_dataset_match_values must still
    collect every dataset's rows correctly, regardless of completion order."""

    class FakeSyn:
        def tableQuery(self, query):
            if "syn20" in query:
                return _FakeResults(pd.DataFrame({"individualID": ["JH-2-002", None]}))
            if "syn21" in query:
                return _FakeResults(pd.DataFrame({"modelSystemName": ["NSG"]}))
            if "syn22" in query:
                # neither field exists on syn22 -- narrows away via "Unknown column" on both
                if "individualID" in query:
                    raise Exception("400 Client Error: \nUnknown column individualID")
                raise Exception("400 Client Error: \nUnknown column modelSystemName")
            raise AssertionError(f"Unexpected query: {query}")

    result, failed = mtdl.query_dataset_match_values(FakeSyn(), ["syn20", "syn21", "syn22"], max_workers=4)
    rows = {(r.datasetId, r.field, r.value) for r in result.itertuples()}
    assert rows == {
        ("syn20", "individualID", "JH-2-002"),
        ("syn21", "modelSystemName", "NSG"),
    }
    assert failed == []


class _FakeResults:
    """Minimal stand-in for synapseclient's tableQuery() return value."""

    def __init__(self, df):
        self._df = df

    def asDataFrame(self):
        return self._df


def test_call_with_rate_limit_retry_retries_on_429(monkeypatch):
    monkeypatch.setattr(mtdl.time, "sleep", lambda seconds: None)

    class RateLimitError(Exception):
        def __init__(self):
            self.response = type("Response", (), {"status_code": 429})()

    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RateLimitError()
        return "success"

    assert mtdl._call_with_rate_limit_retry(flaky) == "success"
    assert attempts["count"] == 3


def test_call_with_rate_limit_retry_does_not_retry_other_errors(monkeypatch):
    monkeypatch.setattr(mtdl.time, "sleep", lambda seconds: None)

    attempts = {"count": 0}

    def always_fails():
        attempts["count"] += 1
        raise ValueError("not a rate limit")

    import pytest
    with pytest.raises(ValueError):
        mtdl._call_with_rate_limit_retry(always_fails)
    assert attempts["count"] == 1


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
