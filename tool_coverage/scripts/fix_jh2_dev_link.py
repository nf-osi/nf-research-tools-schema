#!/usr/bin/env python3
"""
One-time fix: delete the broken JH-2-002 (MPNST) dev link row that
references publicationId f57a8bad-... which does not exist in syn26486839.
The pipeline will recreate it correctly on the next run using the actual
Synapse publicationId for PMID:32561749.

Requires SYNAPSE_AUTH_TOKEN env var.
"""
import os, sys
import pandas as pd
import synapseclient
from synapseclient import Table

def main():
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("Error: SYNAPSE_AUTH_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    syn = synapseclient.Synapse(silent=True)
    syn.login(authToken=token, silent=True)

    DEV_TABLE = "syn26486807"
    BROKEN_PUB_ID = "f57a8bad-d8f2-5bad-b71f-e65c941783a3"
    JH2_RES_ID = "d53f3a73-f8b3-5fe5-9467-3a2e1ef690d3"

    df = syn.tableQuery(f"SELECT * FROM {DEV_TABLE}").asDataFrame()
    to_delete = df[
        (df["publicationId"] == BROKEN_PUB_ID) &
        (df["resourceId"] == JH2_RES_ID)
    ]
    print(f"Rows to delete: {len(to_delete)}")
    if to_delete.empty:
        print("Nothing to delete — already clean.")
        return

    print(to_delete[["developmentId","publicationId","resourceId","funderId"]].to_string())

    del_df = pd.DataFrame([
        {"ROW_ID": int(str(idx).split("_")[0]), "ROW_VERSION": int(str(idx).split("_")[1])}
        for idx in to_delete.index
    ])
    syn.delete(Table(DEV_TABLE, del_df))
    syn.create_snapshot_version(DEV_TABLE, comment="delete broken JH-2-002 dev link (publicationId not in syn26486839)")
    print(f"✅ Deleted {len(to_delete)} row(s) + snapshot created")

if __name__ == "__main__":
    main()
