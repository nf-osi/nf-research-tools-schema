#!/usr/bin/env python3
"""
One-time fix: patch investigatorId for JH-2-* and WU-* cell line dev link rows
in syn26486807 that were created by the upsert pipeline with a null investigatorId.

Only touches rows that have a non-null funderId (pipeline rows); leaves
original-import rows (null funderId) untouched.

Requires SYNAPSE_AUTH_TOKEN env var.
"""
import os
import sys
import pandas as pd
import synapseclient
from synapseclient import Table

DEV_TABLE = "syn26486807"
RES_TABLE = "syn26450069"

PRATILAS_ID = "f7721852-6466-5fb7-bb09-63fe6a9c3342"   # Christine A. Pratilas (JH-2-*)
HIRBE_ID    = "8a688e78-2ff1-5a65-bc9d-8c2523162b3c"   # Angela C. Hirbe (WU-*)


def main():
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("Error: SYNAPSE_AUTH_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    syn = synapseclient.Synapse(silent=True)
    syn.login(authToken=token, silent=True)

    dev_df = syn.tableQuery(f"SELECT * FROM {DEV_TABLE}").asDataFrame()
    res_df = syn.tableQuery(
        f"SELECT resourceId, resourceName FROM {RES_TABLE} WHERE resourceType='Cell Line'"
    ).asDataFrame()
    res_map = dict(zip(res_df["resourceId"], res_df["resourceName"]))

    # Only rows with null investigatorId AND non-null funderId (pipeline rows)
    candidates = dev_df[
        dev_df["investigatorId"].isna()
        & dev_df["funderId"].notna()
        & dev_df["resourceId"].isin(res_map)
    ].copy()
    candidates["resourceName"] = candidates["resourceId"].map(res_map)

    jh2 = candidates[candidates["resourceName"].str.startswith("JH-2-", na=False)]
    wu  = candidates[candidates["resourceName"].str.startswith("WU-", na=False)]
    other = candidates[
        ~candidates["resourceName"].str.startswith("JH-2-", na=False)
        & ~candidates["resourceName"].str.startswith("WU-", na=False)
    ]

    print(f"JH-2-* rows to patch (→ Christine A. Pratilas): {len(jh2)}")
    print(f"WU-*   rows to patch (→ Angela C. Hirbe):        {len(wu)}")
    if not other.empty:
        print(f"Other cell line rows with non-null funder (skipping): {len(other)}")
        print(other[["resourceName", "funderId"]].to_string())

    to_patch = pd.concat([jh2, wu]) if not (jh2.empty and wu.empty) else pd.DataFrame()
    if to_patch.empty:
        print("Nothing to patch.")
        return

    confirm = input(f"\nPatch {len(to_patch)} rows? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    patch_rows = []
    for idx, row in to_patch.iterrows():
        parts = str(idx).split("_")
        name = row["resourceName"]
        inv_id = PRATILAS_ID if name.startswith("JH-2-") else HIRBE_ID
        patch_rows.append({
            "ROW_ID":          int(parts[0]),
            "ROW_VERSION":     int(parts[1]),
            "investigatorId":  inv_id,
        })

    syn.store(Table(DEV_TABLE, pd.DataFrame(patch_rows)))
    syn.create_snapshot_version(
        DEV_TABLE,
        comment="patch investigatorId for JH-2-* and WU-* cell line dev links",
    )
    print(f"\n✅ Patched {len(patch_rows)} rows + snapshot created")


if __name__ == "__main__":
    main()
