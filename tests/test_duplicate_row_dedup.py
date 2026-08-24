#!/usr/bin/env python3
"""
Regression tests for the duplicate-row bug tracked in #213 (and its sub-issues
#220-#222): resource dedup and deterministic-ID hashing compared/hashed raw,
unnormalized ``resourceName`` strings, so the *same* real-world tool
reprocessed with a slightly different capitalization or spacing (e.g. two
mining passes over the same publication) silently produced a fresh ID and a
duplicate row instead of being recognized as already present.

Covers the fix in both places it was needed:
  * tool_coverage/scripts/compile_accepted_submissions.py -- the actual root
    cause (unnormalized dedup + ID hashing at submission-compile time).
  * tool_coverage/scripts/clean_submission_csvs.py -- a defense-in-depth
    safety net at upload time, in case a duplicate slips past the fix above.

These tests run offline with no Synapse access.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = REPO_ROOT / "tool_coverage" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cas = _load_module("compile_accepted_submissions")


def test_normalize_name_folds_case_and_whitespace():
    assert cas._normalize_name("iMSC-001 (pNF)") == cas._normalize_name("IMSC-001  (pNF)")
    assert cas._normalize_name("  Foo   Bar  ") == "foo bar"
    assert cas._normalize_name("Foo Bar") == cas._normalize_name("foo bar")
    assert cas._normalize_name(None) == ""


def test_make_id_stable_across_formatting_drift():
    """Same logical name, different incidental formatting -> same ID.

    This is the direct fix for the observed bug: before, _make_id hashed the
    raw string, so "NF1-iPSC Line 3" and "nf1-ipsc line 3" produced two
    unrelated UUIDs -- indistinguishable from two different tools.
    """
    variants = ["NF1-iPSC Line 3", "nf1-ipsc line 3", "  NF1-iPSC   Line 3  "]
    ids = {cas._make_id("cell_line", v) for v in variants}
    assert len(ids) == 1, f"expected one stable ID across formatting variants, got {ids}"


def test_make_resource_id_and_donor_id_stable_across_formatting_drift():
    variants = ["Patient PDX 7", "patient pdx 7", "Patient  PDX  7"]
    resource_ids = {cas._make_resource_id(v, "patient_derived_models") for v in variants}
    donor_ids = {cas._make_donor_id(v) for v in variants}
    assert len(resource_ids) == 1
    assert len(donor_ids) == 1


def test_make_vendor_ids_stable_across_formatting_drift():
    vendor_variants = ["ATCC", "atcc", " ATCC "]
    assert len({cas._make_vendor_id(v) for v in vendor_variants}) == 1
    assert len({cas._make_vendor_item_id(v, "CRL-1234") for v in vendor_variants}) == 1


ccs = _load_module("clean_submission_csvs")


def test_clean_submission_csvs_normalize_name_matches_compile_side():
    assert ccs._normalize_name("NF1-iPSC  Line 3") == cas._normalize_name(" nf1-ipsc line 3 ")


def test_find_resourcename_duplicates_catches_formatting_drift():
    """The actual safety-net check in clean_submission_csvs.py's upsert path:
    a row whose PK is "new" (no match by _DETAIL_TABLE_PK) but whose
    resourceName matches an existing row (after normalization) must be
    flagged, not silently uploaded as a duplicate.
    """
    df_clean = pd.DataFrame({
        "cellLineId": ["brand-new-uuid-1", "brand-new-uuid-2"],
        "resourceName": ["nf1-ipsc line 3", "Totally Different Line"],
    })
    existing_names = ["NF1-iPSC  Line 3"]  # already in Synapse, different formatting

    mask = ccs._find_resourcename_duplicates(df_clean, existing_names)

    assert mask.tolist() == [True, False]


def test_load_existing_names_normalizes(tmp_path):
    csv_path = tmp_path / "ACCEPTED_cell_lines.csv"
    csv_path.write_text("_resourceName\nNF1-iPSC Line 3\n", encoding="utf-8")

    existing = cas._load_existing_names(csv_path, "_resourceName")

    # A re-processed row with different capitalization/spacing must be
    # recognized as already present -- this is the actual dedup check that
    # was missing before the fix (comparing normalized values, not raw ones).
    assert cas._normalize_name("nf1-ipsc  line 3") in existing
    assert cas._normalize_name("NF1-iPSC Line 3") in existing
