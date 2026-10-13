#!/usr/bin/env python3
"""tool_scoring.join_detail_tables: each tool gets only its own type's detail
row, keyed on resourceId (post-LinkML), with the detail table winning on
shared columns. Offline; no Synapse access."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "tool_scoring", Path(__file__).resolve().parent.parent / "tool_scoring.py")
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)


def test_join_keeps_types_apart_and_prefers_detail():
    base = pd.DataFrame([
        {"resourceId": "p1", "resourceType": "Patient-Derived Model", "description": "base"},
        {"resourceId": "o1", "resourceType": "Organoid Protocol", "description": "base"},
        {"resourceId": "x1", "resourceType": None, "description": "orphan"},
    ])
    pdm = pd.DataFrame([{"resourceId": "p1", "modelType": "Xenograft", "description": "detail"}])
    org = pd.DataFrame([{"resourceId": "o1", "modelType": "Organoid"}])

    out = ts.join_detail_tables(base, {"Patient-Derived Model": pdm, "Organoid Protocol": org})
    by_id = out.set_index("resourceId")

    assert len(out) == 3
    assert by_id.loc["p1", "modelType"] == "Xenograft"
    assert by_id.loc["o1", "modelType"] == "Organoid"  # not the PDM's value
    assert by_id.loc["p1", "description"] == "detail"
    assert by_id.loc["o1", "description"] == "base"


def test_renamed_fields_are_scored():
    row = pd.Series({"resourceType": "Cell Line", "cellLineCategory": "Cancer cell line",
                     "geneticDisorder": "No known genetic disorder",
                     "manifestation": "Breast Carcinoma", "synonyms": "MCF7"})
    result = ts.calculate_tool_score(row, pd.DataFrame(), pd.DataFrame())
    assert result["missing_fields"]["critical_info"] == ""
