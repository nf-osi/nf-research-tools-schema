#!/usr/bin/env python3
"""
One-time fix: delete dev link rows in syn26486807 whose publicationId is
non-null but does not exist in syn26486839 (ghost IDs written by the old
pipeline before the PMID-lookup fix was in place).

Rows with a null publicationId are left untouched — those are original-import
rows that intentionally track funder/investigator without a known publication.

After deletion, re-trigger the upsert-tools workflow to recreate the rows
with correct publicationIds resolved from PMID via syn26486839.

Requires SYNAPSE_AUTH_TOKEN env var.
"""
import os
import sys
import pandas as pd
import synapseclient
from synapseclient import Table

DEV_TABLE = "syn26486807"
PUB_TABLE = "syn26486839"


def row_ids_from_index(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for idx in df.index:
        parts = str(idx).split("_")
        rows.append({"ROW_ID": int(parts[0]), "ROW_VERSION": int(parts[1])})
    return pd.DataFrame(rows)


def main():
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("Error: SYNAPSE_AUTH_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    syn = synapseclient.Synapse(silent=True)
    syn.login(authToken=token, silent=True)

    dev_df = syn.tableQuery(f"SELECT * FROM {DEV_TABLE}").asDataFrame()
    pub_df = syn.tableQuery(
        f"SELECT publicationId FROM {PUB_TABLE}"
    ).asDataFrame()

    valid_pub_ids = set(pub_df["publicationId"].dropna())

    # Only target rows with a non-null publicationId that doesn't exist in
    # syn26486839. Null-publicationId rows are intentional original-import rows.
    to_delete = dev_df[
        dev_df["publicationId"].notna()
        & ~dev_df["publicationId"].isin(valid_pub_ids)
    ]

    print(f"Total dev links:              {len(dev_df)}")
    print(f"Rows with ghost publicationId: {len(to_delete)}")

    if to_delete.empty:
        print("Nothing to delete — already clean.")
        return

    res_df = syn.tableQuery(
        "SELECT resourceId, resourceName FROM syn26450069"
    ).asDataFrame()
    named = to_delete.merge(res_df, on="resourceId", how="left")
    print("\nRows to delete:")
    print(
        named[["resourceName", "publicationId", "funderId", "investigatorId"]]
        .to_string()
    )

    confirm = input(f"\nDelete {len(to_delete)} rows? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    syn.delete(Table(DEV_TABLE, row_ids_from_index(to_delete)))
    syn.create_snapshot_version(
        DEV_TABLE,
        comment="delete dev links with ghost publicationId — will be recreated by upsert pipeline with correct IDs",
    )
    print(f"\n✅ Deleted {len(to_delete)} rows + snapshot created")
    print("Re-trigger upsert-tools workflow to recreate rows with correct publicationIds.")


if __name__ == "__main__":
    main()
