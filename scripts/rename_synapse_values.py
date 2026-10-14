#!/usr/bin/env python3
"""
Reusable Synapse value-rename tooling (nf-research-tools-schema#274).

Generalizes the one-time-script pattern used for #262
(scripts/fix_enum_value_styling_262.py, removed before merge per #272
review -- one-time-use scripts shouldn't be committed) into a repeatable
CLI: given a mapping of {table_id: {column: {old_value: new_value}}},
safely renames matching values in a live Synapse table.

- STRING columns are rewritten via a plain `Table(table_id, df)` +
  `syn.store()` patch.
- STRING_LIST columns are rewritten via `PartialRowset`/`PartialRow` with
  native Python list values, replacing only the matching element(s) in
  each row's list -- NOT a CSV-based Table upload, which breaks faceting
  for multi-valued columns (see #266).
- Column type (STRING vs STRING_LIST) is looked up live via
  `syn.getTableColumns()` -- the mapping itself doesn't say which, so the
  same mapping shape works for either kind of column.
- Both paths only rewrite EXACT (case-sensitive) matches to a mapping
  key. Synapse SQL string comparison is case-insensitive, so the
  candidate-row query can return rows already in a different casing than
  the mapping key (e.g. an already-correct 'Primary tumor' row when
  fixing 'Primary Tumor') -- those are left untouched.
- Every write is routed through synapse_safety.safe_store() for
  mandatory before/after snapshotting.

Deliberately does NOT support "fill in a currently-blank value" (matching
NULL as an old_value): unlike a specific wrong string, NULL/blank has no
distinguishing content, so a mapping keyed on it would match every blank
row table-wide with no way to scope it to the handful of rows you
actually mean (confirmed live against #306's investigatorId/funderId gap
while building this -- a blank-fill dry run matched 121 unrelated rows
instead of the 3 intended). Backfilling a specific row's blank value
needs a row-scoped filter (e.g. by resourceId), which is a different,
more dangerous operation than this tool's mapping shape can express
safely -- do that inline instead, the way the AnimalModel fix in #272
was applied inline rather than folded into a committed script.

Mapping input (pick one, or both -- --set entries are layered onto the
mapping file's contents):
  --mapping-file path.json    JSON: {table_id: {column: {old: new}}}
  --set TABLE:COLUMN:OLD=NEW  one rename, no file needed (repeatable)

Requires: pip install synapseclient pandas
Requires SYNAPSE_AUTH_TOKEN env var (or a cached synapseclient login).

Usage:
  # Preview only, no Synapse writes
  python scripts/rename_synapse_values.py --mapping-file fix.json --dry-run

  # Apply a mapping file
  python scripts/rename_synapse_values.py --mapping-file fix.json \\
      --comment "nf-research-tools-schema#274 test"

  # One-off inline rename, no file
  python scripts/rename_synapse_values.py \\
      --set syn26486823:tissue:Primary Tumor=Primary tumor \\
      --comment "casing fix"

Run scripts/snapshot_synapse_tables.py against the target table(s) first
if you want a rollback manifest beyond the before/after snapshots
safe_store() already takes -- see docs/STAGING_PROCEDURE.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synapse_safety import safe_store, safe_store_row_patch  # noqa: E402


def _row_id_version(index_value) -> tuple[int, int]:
    """synapseclient sets the DataFrame index to 'ROW_ID_ROW_VERSION'
    strings (e.g. '12345_0') -- same pattern used in
    tool_coverage/scripts/clean_submission_csvs.py's patch path and the
    original #262 one-time script."""
    row_id, row_version = str(index_value).split("_")
    return int(row_id), int(row_version)


def scalar_candidate_query(table_id: str, column: str, mapping: dict) -> str:
    """Build the case-insensitive candidate-row SELECT for a STRING
    column rename. Only a candidate filter -- exact-match checking
    happens client-side in apply_scalar_rename."""
    return f'SELECT "{column}" FROM {table_id} WHERE "{column}" IN ({", ".join(repr(k) for k in mapping)})'


def list_candidate_query(table_id: str, column: str, mapping: dict) -> str:
    """Build the case-insensitive candidate-row SELECT for a STRING_LIST
    column rename. Only a candidate filter -- exact-match checking
    happens client-side in apply_list_rename."""
    clauses = " OR ".join(f'"{column}" HAS (\'{k}\')' for k in mapping)
    return f'SELECT "{column}" FROM {table_id} WHERE {clauses}'


def _scalar_matches(query_result, column: str, mapping: dict) -> list[tuple[int, int, str, str]]:
    """Filter a tableQuery() result's DataFrame down to exact (case-
    sensitive) mapping matches, returning (row_id, row_version, old, new)
    tuples. Shared by the dry-run preview and the real patch build so
    both apply the same matching logic against whichever query result
    they were given."""
    df = query_result.asDataFrame()
    matches = []
    for idx, old in df[column].items():
        if old not in mapping:
            continue  # case-insensitive false positive -- different casing than any mapping key
        row_id, row_version = _row_id_version(idx)
        matches.append((row_id, row_version, old, mapping[old]))
    return matches


def apply_scalar_rename(syn, table_id: str, column: str, mapping: dict, dry_run: bool, comment: str):
    """Rename matching values in a single-valued STRING column. Safe for
    scalars -- the STRING_LIST unnesting bug in #266 only affects
    multi-valued columns (see apply_list_rename).

    The actual write goes through safe_store_row_patch(), not safe_store():
    this is a row-level patch (ROW_ID/ROW_VERSION for existing rows), and
    Synapse's row-update endpoint needs the etag of the specific
    tableQuery() RowSet being patched -- which must be read fresh *after*
    the before-snapshot, not reused from a query made before it (any
    entity modification between that read and the store invalidates it).
    See safe_store_row_patch()'s docstring for the full story -- found
    live while applying nf-research-tools-schema#306's DevelopmentRecord
    fix, 2026-08-27.
    """
    query = scalar_candidate_query(table_id, column, mapping)
    preview_matches = _scalar_matches(syn.tableQuery(query), column, mapping)

    if not preview_matches:
        print(f"  {table_id}.{column}: no matching rows")
        return
    for row_id, _row_version, old, new in preview_matches:
        print(f"    row {row_id}: {old!r} -> {new!r}")
    print(f"  {table_id}.{column}: {len(preview_matches)} row(s) to fix")
    if dry_run:
        return

    import pandas as pd
    import synapseclient

    def build_patch(syn):
        # Fresh query, run after safe_store_row_patch's before-snapshot --
        # see the docstring above for why this can't reuse preview_matches.
        result = syn.tableQuery(query)
        matches = _scalar_matches(result, column, mapping)
        if not matches:
            return None
        patch_df = pd.DataFrame([
            {"ROW_ID": row_id, "ROW_VERSION": row_version, column: new}
            for row_id, row_version, _old, new in matches
        ])
        table = synapseclient.Table(table_id, patch_df)
        table.etag = result.etag  # the RowSet's own changeset etag, not the table entity's
        return table

    safe_store_row_patch(syn, table_id, build_patch, comment=f"{comment}: {column}")


def apply_list_rename(syn, table_id: str, column: str, mapping: dict, dry_run: bool, comment: str):
    """Rename matching elements in a multi-valued STRING_LIST column via
    PartialRowset/PartialRow with native Python list values -- NOT a
    CSV-based Table upload.

    Per #266: Synapse's facet-value indexer only unnests STRING_LIST
    values correctly when they arrive via PartialRowset/PartialRow: a
    CSV-based Table upload serializes the list to a single opaque string
    on the wire, breaking faceting for every OTHER value already in that
    row's list, not just the one being fixed -- even though the DataFrame
    cell here is a genuine Python list before upload.
    """
    query = list_candidate_query(table_id, column, mapping)
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
        comment=f"{comment}: {column}",
        table_id=table_id,
    )


def apply_mapping(syn, mapping: dict, dry_run: bool, comment: str):
    """Dispatch each table/column in the mapping to the scalar or list
    rename path based on the column's live Synapse type."""
    for table_id, columns in mapping.items():
        columns_by_name = {c["name"]: c["columnType"] for c in syn.getTableColumns(table_id)}
        for column, column_mapping in columns.items():
            if column not in columns_by_name:
                raise ValueError(f"Column {column!r} not found on table {table_id}")
            column_type = columns_by_name[column]
            if column_type == "STRING_LIST":
                apply_list_rename(syn, table_id, column, column_mapping, dry_run, comment)
            elif column_type == "STRING":
                apply_scalar_rename(syn, table_id, column, column_mapping, dry_run, comment)
            else:
                raise ValueError(
                    f"{table_id}.{column}: unsupported column type {column_type!r} -- "
                    f"only STRING and STRING_LIST renames are supported"
                )


def load_mapping(args) -> dict:
    """Merge --mapping-file contents with any --set entries into a single
    {table_id: {column: {old: new}}} mapping. --set entries are layered
    on top of (i.e. can add to or override) the mapping file's contents."""
    mapping: dict = {}
    if args.mapping_file:
        mapping = json.loads(Path(args.mapping_file).read_text())

    for entry in args.set or []:
        try:
            table_id, rest = entry.split(":", 1)
            column, old_new = rest.split(":", 1)
            old, new = old_new.split("=", 1)
        except ValueError:
            raise SystemExit(
                f"--set {entry!r} is not in TABLE:COLUMN:OLD=NEW form"
            )
        mapping.setdefault(table_id, {}).setdefault(column, {})[old] = new

    if not mapping:
        raise SystemExit("No mapping given -- pass --mapping-file and/or --set.")
    return mapping


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--mapping-file",
        help='JSON file: {"table_id": {"column": {"old_value": "new_value"}}}',
    )
    parser.add_argument(
        "--set", action="append",
        help="One rename as TABLE:COLUMN:OLD=NEW (repeatable)",
    )
    parser.add_argument(
        "--comment", required=True,
        help="Snapshot/change comment, e.g. 'nf-research-tools-schema#274 test'",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print planned changes without touching Synapse",
    )
    return parser


def main():
    args = build_arg_parser().parse_args()
    mapping = load_mapping(args)

    if args.dry_run:
        print("Dry run -- resolving candidates, no writes.\n")

    import synapseclient
    syn = synapseclient.login()
    apply_mapping(syn, mapping, args.dry_run, args.comment)

    if args.dry_run:
        print("\nDry run -- no changes written.")


if __name__ == "__main__":
    main()
