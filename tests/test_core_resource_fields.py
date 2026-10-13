#!/usr/bin/env python3
"""
Since the LinkML migration every detail table carries resourceName/
resourceType/description/synonyms/rrid/howToAcquire itself. #183 uploaded
MCF-7 with all of these blank because compile only wrote them to tracking
columns. Offline; no Synapse access.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "tool_coverage" / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("compile_accepted_submissions", SCRIPTS / "compile_accepted_submissions.py")
cas = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cas
spec.loader.exec_module(cas)

TOOL_KEYS = ["cell_lines", "antibodies", "animal_models", "genetic_reagents", "patient_derived_models",
             "computational_tools", "organoid_protocols", "clinical_assessment_tools", "biobanks"]


@pytest.mark.parametrize("key", TOOL_KEYS)
def test_every_tool_type_writes_core_columns(key):
    for col in cas._CORE_RESOURCE_COLUMNS + ["howToAcquire"]:
        assert col in cas.COLUMNS[key], f"{key} missing {col}"


def test_cell_line_from_vendor_compiles_complete_row(tmp_path):
    sub = tmp_path / "cell_lines" / "X.json"
    sub.parent.mkdir(parents=True)
    sub.write_text(json.dumps({
        "toolType": "cell_line",
        "basicInfo": {"cellLineName": "MCF-7", "synonyms": "MCF7; MCF 7", "species": "Human",
                      "description": "Breast cancer line, ER+", "rrid": "rrid:CVCL_0031"},
        "cellLineCategory": "Cancer cell line",
        "itemAcquisition": "Purchase from Vendor", "vendor": "ATCC", "catalogNumber": "HTB-22",
    }))
    out = tmp_path / "out"
    cas.compile_accepted([sub], out, dry_run=False)
    row = next(csv.DictReader(open(out / cas.CSV_FILES["cell_lines"], encoding="utf-8")))
    assert row["resourceName"] == "MCF-7"
    assert row["resourceType"] == "Cell Line"
    assert row["description"] == "Breast cancer line, ER+"
    assert json.loads(row["synonyms"]) == ["MCF7", "MCF 7"]
    assert row["rrid"] == "rrid:CVCL_0031"
    assert row["howToAcquire"] == cas._VENDOR_HOW_TO_ACQUIRE
    assert row["availability"] == "Vendor"


def test_pdm_name_keeps_model_type_suffix():
    row = {"_resourceName": "JH-2-002 (PDX)"}
    cas._apply_core_resource_fields(row, {"basicInfo": {"synonyms": "a, b"}}, "patient_derived_model")
    assert row["resourceName"] == "JH-2-002 (PDX)"
    assert row["resourceType"] == "Patient-Derived Model"
    assert json.loads(row["synonyms"]) == ["a", "b"]
