#!/usr/bin/env python3
"""
Vendors already in syn26486850 often have vendorIds from before the UUID5
scheme, so upserts must recognize them by name instead of inserting a
duplicate (e.g. a second "ATCC", or "Jackson Laboratory" next to
"The Jackson Laboratory"). Runs offline with no Synapse access.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "tool_coverage" / "scripts"


def _load_module(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


clean = _load_module("clean_submission_csvs")
cas = _load_module("compile_accepted_submissions")
upl = _load_module("upsert_publication_links")


def test_normalize_vendor_name():
    n = clean.normalize_vendor_name
    assert n("The Jackson Laboratory") == n("Jackson Laboratory") == "jackson laboratory"
    assert n(" ATCC ") == n("atcc")
    assert n("Thermo Fisher Scientific, Inc.") == "thermo fisher scientific inc"
    assert n("Theravance") == "theravance"  # only a leading "the " word is dropped
    assert n(float("nan")) == n(None) == ""


def test_vendor_item_rows_carry_vendor_name(tmp_path):
    with open(tmp_path / cas.CSV_FILES["cell_lines"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["_resourceName", "vendor", "catalogNumber", "catalogURL"])
        w.writeheader()
        w.writerow({"_resourceName": "MCF-7", "vendor": "ATCC", "catalogNumber": "HTB-22",
                    "catalogURL": "https://www.atcc.org/products/htb-22"})

    cas._generate_vendor_and_donor_csvs(tmp_path, dry_run=False)

    items = list(csv.DictReader(open(tmp_path / cas.CSV_FILES["vendorItem"], encoding="utf-8")))
    assert [(i["_resourceName"], i["_vendorName"]) for i in items] == [("MCF-7", "ATCC")]


class _FakeSyn:
    def __init__(self, tables):
        self.tables = tables

    def tableQuery(self, query):
        table = next(t for t in self.tables if t in query)
        frame = self.tables[table]
        return type("R", (), {"asDataFrame": lambda _self: frame})()


def test_vendor_items_use_existing_vendor_id(tmp_path, monkeypatch):
    csv_path = tmp_path / "ACCEPTED_vendorItem.csv"
    pd.DataFrame([
        {"vendorItemId": "vi-1", "vendorId": "new-uuid5-jax", "catalogNumber": "007799",
         "catalogNumberURL": "", "_resourceName": "NRG", "_vendorName": "Jackson Laboratory"},
        {"vendorItemId": "vi-2", "vendorId": "new-uuid5-acme", "catalogNumber": "A1",
         "catalogNumberURL": "", "_resourceName": "NRG", "_vendorName": "Acme Bio"},
    ]).to_csv(csv_path, index=False)
    syn = _FakeSyn({
        upl.VENDOR_ITEM_TABLE: pd.DataFrame({"vendorItemId": []}),
        clean.VENDOR_TABLE: pd.DataFrame({"vendorId": ["legacy-jax"],
                                          "vendorName": ["The Jackson Laboratory"]}),
    })

    added = []
    monkeypatch.setattr(upl, "store_with_snapshots", lambda syn, table_id, df: added.append(df))

    upl.upsert_vendor_items(syn, str(csv_path), {("nrg", "Animal Model"): "res-nrg"}, dry_run=False)

    rows = added[0].set_index("vendorItemId")["vendorId"].to_dict()
    assert rows == {"vi-1": "legacy-jax", "vi-2": "new-uuid5-acme"}
