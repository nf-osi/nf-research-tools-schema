"""
Delete duplicate rows from new tool type detail tables in Synapse.

Duplicates were created by multiple force=true runs of upsert-tools.yml
each appending the same rows. Keeps the first-inserted row per primary key
(lowest rowId) and deletes all later duplicates. Also deletes null-PK orphan
rows inserted before the FK column existed in the target table.

Tables targeted:
  syn26486808  AnimalModelDetails
  syn26486811  AntibodyDetails
  syn26486823  CellLineDetails
  syn73709226  ComputationalToolDetails
  syn73709227  OrganoidProtocolDetails
  syn73709228  PatientDerivedModelDetails
  syn73709229  ClinicalAssessmentToolDetails

After deletion, creates a snapshot for each modified table with the
comment 'deleting duplicates in new tool submissions'.
"""
import os
import sys

import pandas as pd
import synapseclient
from synapseclient import Synapse
from synapseclient.models import Table as SynapseTable

TABLES = {
    "syn26486808": "animalModelId",
    "syn26486811": "antibodyId",
    "syn26486823": "cellLineId",
    "syn73709226": "computationalToolId",
    "syn73709227": "organoidProtocolId",
    "syn73709228": "patientDerivedModelId",
    "syn73709229": "clinicalAssessmentToolId",
}

SNAPSHOT_COMMENT = "deleting duplicates in new tool submissions"


def delete_duplicates(syn: Synapse, table_id: str, pk_col: str, dry_run: bool = False) -> int:
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Processing {table_id} (pk={pk_col})")

    # CSV download is fast; index is '{rowId}_{versionNumber}'.
    results = syn.tableQuery(f"SELECT * FROM {table_id}")
    df = results.asDataFrame()

    if df.empty:
        print(f"  ✅ Empty table, nothing to do")
        return 0

    if pk_col not in df.columns:
        print(f"  ⚠️  Column {pk_col} not found — skipping")
        return 0

    # Parse ROW_ID and ROW_VERSION out of the '{rowId}_{versionNumber}' index.
    df["ROW_ID"] = df.index.map(lambda x: int(str(x).split("_")[0]))
    df["ROW_VERSION"] = df.index.map(lambda x: int(str(x).split("_")[1]))
    df_sorted = df.sort_values("ROW_ID")

    # All null-PK rows are orphans — delete them all.
    null_pk = df_sorted[df_sorted[pk_col].isna()].copy()
    # For valid PKs, keep the earliest (lowest rowId) and delete later duplicates.
    valid_pk = df_sorted[df_sorted[pk_col].notna()]
    dup_valid = valid_pk[valid_pk.duplicated(subset=[pk_col], keep="first")].copy()

    n_null = len(null_pk)
    n_dup = len(dup_valid)
    n = n_null + n_dup
    total = len(df)
    print(
        f"  Total rows: {total} | To delete: {n} "
        f"({n_null} null-PK orphans + {n_dup} duplicates)"
    )

    if n == 0:
        print(f"  ✅ No duplicates or orphans")
        return 0

    for _, row in pd.concat([null_pk, dup_valid]).iterrows():
        print(f"    Delete rowId={int(row['ROW_ID'])} ({pk_col}={row[pk_col]})")

    if dry_run:
        print(f"  [dry-run] Would delete {n} rows")
        return n

    to_delete_df = pd.concat([null_pk, dup_valid])[["ROW_ID", "ROW_VERSION"]].copy()
    SynapseTable(id=table_id).delete_rows(df=to_delete_df)
    print(f"  ✅ Deleted {n} rows")

    try:
        syn.create_snapshot_version(table_id, comment=SNAPSHOT_COMMENT)
        print(f"  ✅ Snapshot created: '{SNAPSHOT_COMMENT}'")
    except Exception as e:
        print(f"  ⚠️  Snapshot failed: {e}")

    return n


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

    print(
        f"\n{'[DRY-RUN] ' if dry_run else ''}Done. "
        f"Total rows {'would be ' if dry_run else ''}deleted: {total_deleted}"
    )


if __name__ == "__main__":
    main()
