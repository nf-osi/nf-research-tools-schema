#!/usr/bin/env python3
"""
One-time cleanup: delete duplicate/null rows from Donor, Vendor, and Development tables.

Requires SYNAPSE_AUTH_TOKEN env var.

Tables touched:
  syn26486807  Development links — 118 rows with null developmentId (pre-migration orphans)
  syn26486850  Vendor            — 13 duplicate Creative Biolabs rows (14 copies, keep 1)
  syn26486829  Donor             — 460 extra rows (uploaded repeatedly without dedup)
"""

import os
import sys
import pandas as pd
import synapseclient
from synapseclient import Table

COMMENT = "deleting duplicate entries"


def row_ids_from_index(df: pd.DataFrame) -> pd.DataFrame:
    """Parse ROW_ID / ROW_VERSION from a pandas index like '640_9'."""
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
    print("Logged in to Synapse\n")

    # ── Development: delete null-developmentId rows ────────────────────────
    print("=== Development (syn26486807) — deleting null-developmentId rows ===")
    df_dev = syn.tableQuery("SELECT * FROM syn26486807").asDataFrame()
    to_delete = df_dev[
        df_dev["developmentId"].isna()
        | (df_dev["developmentId"].astype(str).str.strip() == "")
    ]
    print(f"  Rows to delete: {len(to_delete)}")
    if not to_delete.empty:
        syn.delete(Table("syn26486807", row_ids_from_index(to_delete)))
        syn.create_snapshot_version("syn26486807", comment=COMMENT)
        print(f"  ✅ Deleted {len(to_delete)} rows + snapshot created")
    else:
        print("  Nothing to delete")

    # ── Vendor: keep one Creative Biolabs row, delete the rest ────────────
    print("\n=== Vendor (syn26486850) — deduplicating ===")
    df_vendor = syn.tableQuery("SELECT * FROM syn26486850").asDataFrame()
    dup_counts = df_vendor.groupby("vendorId").size()
    dup_ids = dup_counts[dup_counts > 1].index.tolist()
    to_delete_v_parts = []
    for vid in dup_ids:
        rows = df_vendor[df_vendor["vendorId"] == vid]
        to_delete_v_parts.append(rows.iloc[1:])  # keep first, delete rest
    to_delete_v = pd.concat(to_delete_v_parts) if to_delete_v_parts else pd.DataFrame()
    print(f"  Rows to delete: {len(to_delete_v)}")
    if not to_delete_v.empty:
        syn.delete(Table("syn26486850", row_ids_from_index(to_delete_v)))
        syn.create_snapshot_version("syn26486850", comment=COMMENT)
        print(f"  ✅ Deleted {len(to_delete_v)} duplicate vendor rows + snapshot created")
    else:
        print("  Nothing to delete")

    # ── Donor: keep one row per donorId (most non-null fields), delete rest
    print("\n=== Donor (syn26486829) — deduplicating ===")
    df_donor = syn.tableQuery("SELECT * FROM syn26486829").asDataFrame()
    df_donor["_non_null"] = df_donor.notna().sum(axis=1)
    keep_idx = df_donor.groupby("donorId")["_non_null"].idxmax()
    to_delete_d = df_donor[~df_donor.index.isin(keep_idx)]
    print(f"  Total rows: {len(df_donor)}, keeping: {len(keep_idx)}, deleting: {len(to_delete_d)}")
    if not to_delete_d.empty:
        syn.delete(Table("syn26486829", row_ids_from_index(to_delete_d)))
        syn.create_snapshot_version("syn26486829", comment=COMMENT)
        print(f"  ✅ Deleted {len(to_delete_d)} duplicate donor rows + snapshot created")
    else:
        print("  Nothing to delete")

    print("\n✅ Cleanup complete.")


if __name__ == "__main__":
    main()
