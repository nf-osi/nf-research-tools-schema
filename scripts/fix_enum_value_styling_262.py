#!/usr/bin/env python3
"""
One-time data cleanup for nf-research-tools-schema#262 comment
(https://github.com/nf-osi/nf-research-tools-schema/issues/262#issuecomment-5425517940):

  1. CellLine/Biobank tissue: capitalize only the first letter of the first
     word (e.g. "Primary Tumor" -> "Primary tumor")
  2. CellLine.manifestation: fix casing drift against CellLineManifestationEnum
     ("cervical adenocarcinoma" -> "Cervical Adenocarcinoma")
  3. Antibody.targetAntigen: "Human neurofibromin 1" -> "NF1",
     "NF1 (Internal)" -> "NF1 (internal)"
  4. CellLine/GeneticReagent usageRequirements: "Unknown" -> "unknown", to
     match UsageRequirementEnum's existing (and only) casing of this value
     -- found while completing the enum-consistency pass this comment also
     asked for; not a new value, a duplicate-by-casing of one already there.

Run `python scripts/snapshot_synapse_tables.py` against these tables
before running this (see docs/STAGING_PROCEDURE.md step 1) -- this script
does not snapshot on its own since it's a one-time fix, not a repeatable
staging operation.

Requires: pip install synapseclient
Requires SYNAPSE_AUTH_TOKEN env var (or a cached synapseclient login).

Usage:
  python scripts/fix_enum_value_styling_262.py --dry-run
  python scripts/fix_enum_value_styling_262.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synapse_safety import safe_store  # noqa: E402

CELL_LINE = "syn26486823"
BIOBANK = "syn26486821"
ANTIBODY = "syn26486811"
GENETIC_REAGENT = "syn26486832"

# Single-valued STRING columns: {table_id: {column: {old_value: new_value}}}
SCALAR_FIXES = {
    CELL_LINE: {
        "tissue": {
            "Primary Tumor": "Primary tumor",
            "Dorsal Root Ganglion": "Dorsal root ganglion",
            "Recurrent Tumor": "Recurrent tumor",
        },
    },
    ANTIBODY: {
        "targetAntigen": {
            "Human neurofibromin 1": "NF1",
            "NF1 (Internal)": "NF1 (internal)",
        },
    },
}

# Multivalued STRING_LIST columns: {table_id: {column: {old_value: new_value}}}
# -- replaces just the matching element within each row's list, preserving
# any other elements and their order.
LIST_FIXES = {
    CELL_LINE: {
        "manifestation": {
            "cervical adenocarcinoma": "Cervical Adenocarcinoma",
        },
        "usageRequirements": {
            "Unknown": "unknown",
        },
    },
    BIOBANK: {
        "tissue": {
            "Cerebrospinal Fluid": "Cerebrospinal fluid",
        },
    },
    GENETIC_REAGENT: {
        "usageRequirements": {
            "Unknown": "unknown",
        },
    },
}


def _row_id_version(index_value) -> tuple[int, int]:
    """synapseclient sets the DataFrame index to 'ROW_ID_ROW_VERSION'
    strings (e.g. '12345_0') -- same pattern used in
    tool_coverage/scripts/clean_submission_csvs.py's patch path."""
    row_id, row_version = str(index_value).split("_")
    return int(row_id), int(row_version)


def apply_scalar_fixes(syn, table_id: str, column: str, mapping: dict, dry_run: bool):
    """Fix single-valued STRING columns via a plain CSV-based Table
    update. Safe for scalars -- the STRING_LIST unnesting bug in #266
    only affects multi-valued columns (see apply_list_fixes).

    Synapse SQL string comparison is case-insensitive, so the WHERE ...
    IN (...) below is only a candidate filter -- it can return rows whose
    value differs only in case from a mapping key (e.g. an already-correct
    'Primary tumor' row when fixing 'Primary Tumor'). Only rows with an
    exact (case-sensitive) match to a mapping key are actually changed.
    """
    query = f'SELECT "{column}" FROM {table_id} WHERE "{column}" IN ({", ".join(repr(k) for k in mapping)})'
    df = syn.tableQuery(query).asDataFrame()

    patch_rows = []
    for idx, old in df[column].items():
        if old not in mapping:
            continue
        row_id, row_version = _row_id_version(idx)
        print(f"    row {row_id}: {old!r} -> {mapping[old]!r}")
        patch_rows.append({"ROW_ID": row_id, "ROW_VERSION": row_version, column: mapping[old]})

    if not patch_rows:
        print(f"  {table_id}.{column}: no matching rows")
        return
    print(f"  {table_id}.{column}: {len(patch_rows)} row(s) to fix")
    if dry_run:
        return

    import pandas as pd
    import synapseclient
    safe_store(
        syn,
        synapseclient.Table(table_id, pd.DataFrame(patch_rows)),
        comment=f"#262 styling fix: {column}",
        table_id=table_id,
    )


def apply_list_fixes(syn, table_id: str, column: str, mapping: dict, dry_run: bool):
    """Fix multi-valued STRING_LIST columns via PartialRowset/PartialRow
    with native Python list values -- NOT a CSV-based Table upload.

    Per #266: Synapse's facet-value indexer only unnests STRING_LIST
    values correctly when they arrive via PartialRowset/PartialRow: a
    CSV-based Table upload serializes the list to a single opaque string
    on the wire, breaking faceting for every OTHER value already in that
    row's list, not just the one being fixed -- even though the DataFrame
    cell here is a genuine Python list before upload.

    Like apply_scalar_fixes, the WHERE HAS(...) clause is only a
    case-insensitive candidate filter -- only list elements with an exact
    (case-sensitive) match to a mapping key are replaced.
    """
    like_clauses = " OR ".join(f'"{column}" HAS (\'{k}\')' for k in mapping)
    query = f'SELECT "{column}" FROM {table_id} WHERE {like_clauses}'
    df = syn.tableQuery(query).asDataFrame()

    import synapseclient
    from synapseclient.table import PartialRow

    # PartialRow's "key" must be the column's numeric id, not its name --
    # an unqualified name is rejected by the API ("not a valid column ID").
    column_id = next(c["id"] for c in syn.getTableColumns(table_id) if c["name"] == column)

    partial_rows = []
    for idx, cell in df[column].items():
        values = list(cell) if isinstance(cell, (list, tuple)) else []
        new_values = [mapping.get(v, v) for v in values]
        if new_values == values:
            continue
        row_id, _ = _row_id_version(idx)
        print(f"    row {row_id}: {values} -> {new_values}")
        partial_rows.append(PartialRow({column_id: new_values}, row_id))

    if not partial_rows:
        print(f"  {table_id}.{column}: no matching rows (or matched rows already correct)")
        return
    print(f"  {table_id}.{column}: {len(partial_rows)} row(s) to fix")
    if dry_run:
        return
    safe_store(
        syn,
        synapseclient.PartialRowset(table_id, partial_rows),
        comment=f"#262 styling fix: {column}",
        table_id=table_id,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing to Synapse")
    args = parser.parse_args()

    import synapseclient
    syn = synapseclient.login()

    print("── Scalar (STRING) fixes ──")
    for table_id, columns in SCALAR_FIXES.items():
        for column, mapping in columns.items():
            apply_scalar_fixes(syn, table_id, column, mapping, args.dry_run)

    print("\n── List (STRING_LIST) fixes ──")
    for table_id, columns in LIST_FIXES.items():
        for column, mapping in columns.items():
            apply_list_fixes(syn, table_id, column, mapping, args.dry_run)

    if args.dry_run:
        print("\nDry run -- no changes written.")


if __name__ == "__main__":
    main()
