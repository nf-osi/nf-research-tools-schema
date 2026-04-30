#!/usr/bin/env python3
"""
One-time fix: remove duplicate development link rows from syn26486807.

After the pipeline added non-null publicationId rows for existing resources,
some (resourceId, funderId) pairs now have two rows:
  - an original-import row with null publicationId
  - a pipeline-added row with the correct publicationId

The portal renders the funder once per dev-link row, so duplicate rows cause
the same funder to appear twice. This script deletes the null-publicationId
row in each such pair, keeping the one with the correct publicationId.

Only deletes rows where ALL of these are true:
  - publicationId IS NULL
  - another row with the same (resourceId, funderId) and non-null publicationId exists

Requires SYNAPSE_AUTH_TOKEN env var. Run from the repo root.
"""
import os
import sys
import pandas as pd
import synapseclient
from synapseclient import Table

DEV_TABLE = "syn26486807"


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

    dev_df = syn.tableQuery(
        f"SELECT resourceId, funderId, publicationId FROM {DEV_TABLE}"
    ).asDataFrame()
    print(f"Total dev-link rows in Synapse: {len(dev_df)}")

    # (resourceId, funderId) pairs that have at least one non-null publicationId
    filled = set()
    for _, row in dev_df.iterrows():
        rid = str(row.get("resourceId") or "")
        fid = str(row.get("funderId") or "")
        pub = str(row.get("publicationId") or "")
        if rid and pub:
            filled.add((rid, fid))

    # Null-pub rows whose pair is already covered by a non-null row → duplicates
    to_delete = dev_df[
        dev_df["publicationId"].isna()
        & dev_df.apply(
            lambda r: (str(r.get("resourceId") or ""), str(r.get("funderId") or "")) in filled,
            axis=1,
        )
    ]

    print(f"Null-pub duplicate rows to delete: {len(to_delete)}")
    if to_delete.empty:
        print("Nothing to delete.")
        return

    print(to_delete[["resourceId", "funderId"]].to_string())

    confirm = input(f"\nDelete {len(to_delete)} null-publicationId duplicate row(s)? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    syn.delete(Table(DEV_TABLE, row_ids_from_index(to_delete)))
    syn.create_snapshot_version(
        DEV_TABLE,
        comment="remove null-pub duplicate dev-link rows (funder appearing twice fix)",
    )
    print(f"\n✅ Deleted {len(to_delete)} rows + snapshot created")


if __name__ == "__main__":
    main()
