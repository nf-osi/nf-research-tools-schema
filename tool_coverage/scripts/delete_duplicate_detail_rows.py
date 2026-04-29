"""
Delete duplicate rows from new tool type detail tables in Synapse.

Duplicates were created by multiple force=true runs of upsert-tools.yml
each appending the same rows. Keeps the first-inserted row per primary key
(lowest ROW_ID) and deletes all later duplicates.

Tables targeted (all rows were added by the upsert pipeline):
  syn73709226  ComputationalToolDetails
  syn73709227  OrganoidProtocolDetails
  syn73709228  PatientDerivedModelDetails
  syn73709229  ClinicalAssessmentToolDetails

After deletion, creates a snapshot for each modified table with the
comment 'deleting duplicates in new tool submissions'.
"""
import json
import os
import sys

import pandas as pd
import synapseclient
from synapseclient import Synapse

TABLES = {
    "syn26486808": "animalModelId",
    "syn26486811": "antibodyId",
    "syn73709226": "computationalToolId",
    "syn73709227": "organoidProtocolId",
    "syn73709228": "patientDerivedModelId",
    "syn73709229": "clinicalAssessmentToolId",
}

SNAPSHOT_COMMENT = "deleting duplicates in new tool submissions"


def delete_duplicates(syn: Synapse, table_id: str, pk_col: str, dry_run: bool = False) -> int:
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Processing {table_id} (pk={pk_col})")

    result = syn.tableQuery(f"SELECT * FROM {table_id}")
    # Read the raw CSV to get ROW_ID and ROW_VERSION
    df = pd.read_csv(result.filepath)

    if pk_col not in df.columns:
        print(f"  ⚠️  Column {pk_col} not found — skipping")
        return 0

    if "ROW_ID" not in df.columns or "ROW_VERSION" not in df.columns:
        print(f"  ⚠️  ROW_ID/ROW_VERSION not in result — skipping")
        return 0

    total = len(df)
    df_sorted = df.sort_values("ROW_ID")

    # Rows with null PK are orphans (FK column was stripped in early uploads) — delete all.
    null_pk = df_sorted[df_sorted[pk_col].isna()]
    # For valid PKs, keep the first-inserted row (lowest ROW_ID) and delete later duplicates.
    valid_pk = df_sorted[df_sorted[pk_col].notna()]
    dup_valid = valid_pk[valid_pk.duplicated(subset=[pk_col], keep="first")]

    to_delete = pd.concat([null_pk, dup_valid])
    n_dupes = len(to_delete)
    print(f"  Total rows: {total} | To delete: {n_dupes} ({len(null_pk)} null-PK orphans + {len(dup_valid)} duplicates)")

    if n_dupes == 0:
        print(f"  ✅ No duplicates")
        return 0

    for _, row in to_delete.iterrows():
        print(f"    Delete ROW_ID={int(row['ROW_ID'])} ({pk_col}={row[pk_col]})")

    if dry_run:
        print(f"  [dry-run] Would delete {n_dupes} rows")
        return n_dupes

    # Build RowReferenceSet and POST to Synapse deleteRows endpoint
    row_refs = {
        "tableId": table_id,
        "rows": [
            {"rowId": int(r["ROW_ID"]), "versionNumber": int(r["ROW_VERSION"])}
            for _, r in to_delete.iterrows()
        ],
    }
    syn.restPOST(f"/entity/{table_id}/table/deleteRows", body=json.dumps(row_refs))
    print(f"  ✅ Deleted {n_dupes} duplicate rows")

    try:
        syn.create_snapshot_version(table_id, comment=SNAPSHOT_COMMENT)
        print(f"  ✅ Snapshot created: '{SNAPSHOT_COMMENT}'")
    except Exception as e:
        print(f"  ⚠️  Snapshot failed: {e}")

    return n_dupes


def main():
    dry_run = "--dry-run" in sys.argv

    syn = Synapse()
    auth_token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if auth_token:
        syn.login(authToken=auth_token)
    else:
        syn.login()

    total_deleted = 0
    for table_id, pk_col in TABLES.items():
        total_deleted += delete_duplicates(syn, table_id, pk_col, dry_run=dry_run)

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Done. Total rows {'would be ' if dry_run else ''}deleted: {total_deleted}")


if __name__ == "__main__":
    main()
