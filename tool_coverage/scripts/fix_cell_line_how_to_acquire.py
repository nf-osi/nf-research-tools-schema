#!/usr/bin/env python3
"""
One-time fix: set howToAcquire = "Contact Developer" for cell lines in
syn26450069 that currently have a null value.

These are the JH-2-* and WU-* lines added by the upsert pipeline before
the _compute_how_to_acquire cell_line branch existed.

Requires SYNAPSE_AUTH_TOKEN env var.
"""
import os
import sys
import pandas as pd
import synapseclient
from synapseclient import Table

RESOURCE_TABLE = "syn26450069"
HOW_TO_ACQUIRE = "Contact Developer"


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

    res_df = syn.tableQuery(
        f"SELECT * FROM {RESOURCE_TABLE} WHERE resourceType='Cell Line'"
    ).asDataFrame()

    to_update = res_df[res_df["howToAcquire"].isna()].copy()
    print(f"Cell lines with null howToAcquire: {len(to_update)}")
    if to_update.empty:
        print("Nothing to update.")
        return

    print(to_update[["resourceName", "howToAcquire"]].to_string())

    confirm = input(f"\nSet howToAcquire='{HOW_TO_ACQUIRE}' for {len(to_update)} rows? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    to_update["howToAcquire"] = HOW_TO_ACQUIRE
    syn.store(Table(RESOURCE_TABLE, to_update))
    print(f"\n✅ Updated {len(to_update)} rows")


if __name__ == "__main__":
    main()
