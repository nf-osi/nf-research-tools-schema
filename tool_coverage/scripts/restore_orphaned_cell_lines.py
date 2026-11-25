#!/usr/bin/env python3
"""
One-time restore of HS-PSS and HS-Sch-2 into CellLineDetails (syn26486823).

Why: both cell lines were in the legacy Resource table (syn26450069), but
their `cellLineId`s never matched a row in CellLineDetails (checked every
snapshot back to 2023). The 2026-08-24 LinkML migration rebuilt Tools
Central from the detail tables, so these two orphaned Resource rows were
left out of syn51730943. They are the only 2 of the 1,218 legacy Resource
rows missing from it. The weekly model-system sync in nf-metadata-dictionary
then dropped them as terms (nf-osi/nf-metadata-dictionary#1075), even though
14 files in syn22392179 use them as modelSystemName.

What this does: inserts one CellLineDetails row per tool, **reusing the
legacy resourceId** rather than minting a new UUID5. The link tables still
reference those IDs (1 Development, 2 Usage, 3 Observation and 2 RIKEN
VendorItem rows), so reusing them reconnects those links. A fresh ID would
leave them orphaned and create a duplicate.

Core fields (name, synonyms, RRID, description, usageRequirements,
howToAcquire, dateAdded) are copied from the legacy Resource row. Detail
fields are deliberately minimal: cellLineCategory and availability only.
manifestation/geneticDisorder are left blank because the lines' MPNST
identity is disputed (see their Observation rows: HS-PSS may be an
inflammatory myofibroblastic sarcoma, HS-Sch-2 a desmoplastic melanoma).

Safety:
  - Dry run by default; pass --apply to write.
  - Aborts if either resourceId is already used in any of the 9 detail
    tables, or either name already exists in CellLineDetails, so a re-run
    is a no-op rather than a duplicate.
  - The write goes through synapse_safety.safe_store (snapshot before and
    after).

Usage:
    python tool_coverage/scripts/restore_orphaned_cell_lines.py          # dry run
    python tool_coverage/scripts/restore_orphaned_cell_lines.py --apply  # write
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import synapseclient
from synapseclient import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from synapse_safety import safe_store  # noqa: E402

LEGACY_RESOURCE_TABLE = "syn26450069"
CELL_LINE_TABLE = "syn26486823"
DETAIL_TABLES = {
    "AnimalModelDetails": "syn26486808",
    "AntibodyDetails": "syn26486811",
    "BiobankDetails": "syn26486821",
    "CellLineDetails": "syn26486823",
    "GeneticReagentDetails": "syn26486832",
    "ComputationalToolDetails": "syn73709226",
    "OrganoidProtocolDetails": "syn73709227",
    "PatientDerivedModelDetails": "syn73709228",
    "ClinicalAssessmentToolDetails": "syn73709229",
}

# resourceId -> detail-only fields (core fields come from the legacy row)
RESTORE = {
    "bd49d4e2-575e-4e89-8317-cff02db4882c": {  # HS-PSS
        "resourceName": "HS-PSS",
        "cellLineCategory": "Cancer cell line",
        "availability": "Vendor",  # RIKEN BRC RCB2362 (existing VendorItem row)
    },
    "19bba596-fc3d-479b-9675-afa369b44dee": {  # HS-Sch-2
        "resourceName": "HS-Sch-2",
        "cellLineCategory": "Cancer cell line",
        "availability": "Vendor",  # RIKEN BRC RCB2230 (existing VendorItem row)
    },
}

CORE_FIELDS = [
    "resourceId", "resourceName", "resourceType", "synonyms", "rrid",
    "description", "usageRequirements", "howToAcquire", "dateAdded",
]
STRING_LIST_FIELDS = {"synonyms", "usageRequirements"}


def _id_list() -> str:
    return ", ".join(f"'{rid}'" for rid in RESTORE)


def _as_list(val) -> list:
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return []
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
        except ValueError:
            pass
        return [val]
    return [str(val)]


def check_not_already_present(syn) -> None:
    for label, table_id in DETAIL_TABLES.items():
        df = syn.tableQuery(
            f"SELECT resourceId, resourceName FROM {table_id} WHERE resourceId IN ({_id_list()})"
        ).asDataFrame()
        if len(df):
            sys.exit(f"❌ resourceId already used in {label} ({table_id}):\n{df.to_string()}\nNothing written.")
    names = ", ".join(f"'{v['resourceName']}'" for v in RESTORE.values())
    df = syn.tableQuery(
        f"SELECT resourceId, resourceName FROM {CELL_LINE_TABLE} WHERE resourceName IN ({names})"
    ).asDataFrame()
    if len(df):
        sys.exit(f"❌ Name already in CellLineDetails:\n{df.to_string()}\nNothing written.")
    print("✅ Neither resourceId is used in any of the 9 detail tables, and neither name is in CellLineDetails")


def build_rows(syn) -> pd.DataFrame:
    legacy = syn.tableQuery(
        f"SELECT {', '.join(CORE_FIELDS)} FROM {LEGACY_RESOURCE_TABLE} WHERE resourceId IN ({_id_list()})"
    ).asDataFrame()
    if len(legacy) != len(RESTORE):
        sys.exit(f"❌ Expected {len(RESTORE)} legacy rows, found {len(legacy)}. Nothing written.")

    now_ms = int(time.time() * 1000)
    rows = []
    for _, src in legacy.iterrows():
        extra = RESTORE[src["resourceId"]]
        if src["resourceName"] != extra["resourceName"]:
            sys.exit(f"❌ Legacy name {src['resourceName']!r} != expected {extra['resourceName']!r}. Nothing written.")
        row = {f: src[f] for f in CORE_FIELDS}
        for f in STRING_LIST_FIELDS:
            row[f] = json.dumps(_as_list(row[f]))
        row["dateAdded"] = int(row["dateAdded"]) if pd.notna(row["dateAdded"]) else now_ms
        row["dateModified"] = now_ms
        row.update({k: v for k, v in extra.items() if k != "resourceName"})
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Write to Synapse (default: dry run)")
    args = ap.parse_args()

    syn = synapseclient.Synapse(silent=True)
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    syn.login(authToken=token, silent=True) if token else syn.login(silent=True)

    check_not_already_present(syn)
    df = build_rows(syn)
    with pd.option_context("display.width", 200, "display.max_colwidth", 90):
        print(df.T.to_string())

    if not args.apply:
        print(f"\n[dry run] Would insert {len(df)} rows into CellLineDetails ({CELL_LINE_TABLE}). Re-run with --apply.")
        return

    safe_store(
        syn,
        Table(CELL_LINE_TABLE, df),
        comment="Restore HS-PSS and HS-Sch-2 (orphaned in LinkML migration) with legacy resourceIds",
        table_id=CELL_LINE_TABLE,
    )
    print(f"✅ Inserted {len(df)} rows into CellLineDetails ({CELL_LINE_TABLE})")


if __name__ == "__main__":
    main()
