#!/usr/bin/env python3
"""
One-time fix: remove remaining duplicate development link rows from syn26486807
where BOTH rows have a non-null publicationId.

The first fix (fix_dev_link_duplicates.py) removed 135 null-pub duplicates.
This script handles the remaining case: (resourceId, funderId) pairs with
more than one row where all rows have a non-null publicationId.

Strategy: for each such group, keep the row with the highest ROW_VERSION
(most recently written) and delete the rest.

Also prints a diagnostic for a specific resourceId if passed as an arg:
    python fix_dev_link_duplicates_v2.py c0fdf926-7ad8-50b5-9cbb-81a09e0b6f58

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


def row_version_from_index(idx) -> int:
    return int(str(idx).split("_")[1])


def main():
    target_resource = sys.argv[1] if len(sys.argv) > 1 else None

    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("Error: SYNAPSE_AUTH_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    syn = synapseclient.Synapse(silent=True)
    syn.login(authToken=token, silent=True)

    dev_df = syn.tableQuery(
        f"SELECT developmentId, resourceId, funderId, publicationId FROM {DEV_TABLE}"
    ).asDataFrame()
    print(f"Total dev-link rows in Synapse: {len(dev_df)}")

    if target_resource:
        subset = dev_df[dev_df["resourceId"].astype(str) == target_resource]
        print(f"\nAll rows for resourceId={target_resource}:")
        print(subset[["developmentId", "resourceId", "funderId", "publicationId"]].to_string())
        print()

    # Parse ROW_VERSION from index for keep/delete logic
    dev_df["_row_version"] = [row_version_from_index(i) for i in dev_df.index]

    # Normalize (resourceId, funderId) key — treat NaN funder as empty string
    dev_df["_rid"] = dev_df["resourceId"].astype(str).str.strip()
    dev_df["_fid"] = dev_df["funderId"].fillna("").astype(str).str.strip()

    # Find groups with > 1 row where ALL rows have the SAME non-null publicationId
    to_delete_indices = []
    duplicate_groups = []
    skipped_groups = []

    for (rid, fid), grp in dev_df.groupby(["_rid", "_fid"], sort=False):
        if len(grp) <= 1:
            continue
        # Only handle groups where all rows have non-null publicationId
        # (null-pub duplicates were handled by fix_dev_link_duplicates.py)
        if grp["publicationId"].isna().any():
            continue
        # SAFETY CHECK: only delete if all rows have the same publicationId.
        # Different publicationIds → distinct publication links, not duplicates.
        unique_pubs = grp["publicationId"].dropna().unique()
        if len(unique_pubs) > 1:
            skipped_groups.append({
                "resourceId": rid,
                "funderId": fid,
                "publicationIds": list(unique_pubs),
            })
            continue
        # Keep highest ROW_VERSION; delete the rest
        keep_idx = grp["_row_version"].idxmax()
        to_drop = grp.index[grp.index != keep_idx].tolist()
        to_delete_indices.extend(to_drop)
        duplicate_groups.append({
            "resourceId": rid,
            "funderId": fid,
            "publicationId": unique_pubs[0],
            "kept_version": grp.loc[keep_idx, "_row_version"],
            "deleted_count": len(to_drop),
        })

    if skipped_groups:
        print(f"\n⚠️  Skipped {len(skipped_groups)} group(s) with DIFFERENT publicationIds (not duplicates):")
        for g in skipped_groups:
            print(f"  resourceId={g['resourceId']}  funderId={g['funderId']}")
            for p in g["publicationIds"]:
                print(f"    publicationId={p}")

    print(f"(resourceId, funderId) groups with all-non-null-pub duplicates: {len(duplicate_groups)}")
    print(f"Rows to delete: {len(to_delete_indices)}")

    if not to_delete_indices:
        print("Nothing to delete.")
        return

    print("\nGroups (all rows share the same publicationId):")
    for g in duplicate_groups:
        print(f"  resourceId={g['resourceId']}  funderId={g['funderId']}  "
              f"pub={g['publicationId']}  kept_version={g['kept_version']}  deleting={g['deleted_count']} row(s)")

    confirm = input(f"\nDelete {len(to_delete_indices)} duplicate row(s)? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    rows_to_delete = dev_df.loc[to_delete_indices]
    syn.delete(Table(DEV_TABLE, row_ids_from_index(rows_to_delete)))
    syn.create_snapshot_version(
        DEV_TABLE,
        comment="remove all-non-null-pub duplicate dev-link rows (funder appearing twice fix v2)",
    )
    print(f"\n✅ Deleted {len(to_delete_indices)} rows + snapshot created")


if __name__ == "__main__":
    main()
