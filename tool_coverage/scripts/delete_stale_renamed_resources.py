"""
Delete stale resource rows created before resource renames.

Two rename events introduced orphaned rows:
  1. Cell lines JH-2-002 / JH-2-009 / JH-2-031 renamed to
     "JH-2-002 (pNF)" / "JH-2-002 (MPNST)" etc.  Old plain-named rows remain.
  2. PDMs renamed from "JH-2-002 (PDX (Patient-Derived Xenograft))" to
     "JH-2-002 (PDX)" (and all other JH-2 / MN-2 / xenograft PDX entries).

Tables cleaned:
  syn26450069  Resources (main registry)
  syn26486823  CellLineDetails  (rows whose cellLineId is the old plain-name UUID)
  syn73709228  PatientDerivedModelDetails (rows whose patientDerivedModelId is old)
"""
import os
import sys

import pandas as pd
import synapseclient
from synapseclient import Synapse
from synapseclient.models import Table as SynapseTable

RES_TABLE   = "syn26450069"
CL_TABLE    = "syn26486823"
PDM_TABLE   = "syn73709228"

# Cell line plain names that were renamed to include a suffix
_STALE_CL_NAMES = {"JH-2-002", "JH-2-009", "JH-2-031"}

SNAPSHOT_COMMENT = "delete stale rows from pre-rename resource entries"


def _row_ids(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ROW_ID"]      = df.index.map(lambda x: int(str(x).split("_")[0]))
    df["ROW_VERSION"] = df.index.map(lambda x: int(str(x).split("_")[1]))
    return df


def delete_from_table(
    syn: Synapse,
    table_id: str,
    mask: pd.Series,
    df: pd.DataFrame,
    label: str,
    dry_run: bool,
) -> int:
    to_del = _row_ids(df[mask])
    n = len(to_del)
    if n == 0:
        print(f"  ✅ {label}: nothing to delete")
        return 0
    for _, row in to_del.iterrows():
        print(f"    delete rowId={int(row['ROW_ID'])}")
    if dry_run:
        print(f"  [dry-run] Would delete {n} rows from {label} ({table_id})")
        return n
    SynapseTable(id=table_id).delete_rows(df=to_del[["ROW_ID", "ROW_VERSION"]])
    print(f"  ✅ Deleted {n} rows from {label} ({table_id})")
    try:
        syn.create_snapshot_version(table_id, comment=SNAPSHOT_COMMENT)
        print(f"  ✅ Snapshot created")
    except Exception as e:
        print(f"  ⚠️  Snapshot failed: {e}")
    return n


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    syn = Synapse()
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if token:
        syn.login(authToken=token)
    else:
        syn.login()

    # ------------------------------------------------------------------ #
    # 1. Resources table — find stale rows                                 #
    # ------------------------------------------------------------------ #
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Scanning {RES_TABLE} (Resources)")
    res_df = _row_ids(
        syn.tableQuery(f"SELECT * FROM {RES_TABLE}").asDataFrame()
    )

    # Stale PDM: resourceType == 'Patient-Derived Model' AND name contains old verbose label
    stale_pdm_mask = (
        (res_df.get("resourceType", "") == "Patient-Derived Model") &
        res_df.get("resourceName", res_df.get("name", pd.Series(dtype=str))).str.contains(
            r"PDX \(Patient-Derived Xenograft\)", regex=True, na=False
        )
    )
    stale_pdm_ids = set(
        res_df.loc[stale_pdm_mask, "resourceId"].dropna()
    ) if "resourceId" in res_df.columns else set()
    print(f"  Stale PDM resource rows: {stale_pdm_mask.sum()}")
    if not stale_pdm_mask.sum() and "resourceName" not in res_df.columns:
        # Fallback — column may be named differently; print columns for debugging
        print(f"  Columns available: {list(res_df.columns)}")

    # Stale cell lines: resourceType == 'Cell Line' AND plain name (no suffix)
    cl_name_col = next(
        (c for c in ("resourceName", "name") if c in res_df.columns), None
    )
    if cl_name_col:
        stale_cl_mask = (
            (res_df.get("resourceType", "") == "Cell Line") &
            res_df[cl_name_col].isin(_STALE_CL_NAMES)
        )
    else:
        stale_cl_mask = pd.Series(False, index=res_df.index)
    stale_cl_ids = set(
        res_df.loc[stale_cl_mask, "resourceId"].dropna()
    ) if "resourceId" in res_df.columns else set()
    print(f"  Stale cell-line resource rows: {stale_cl_mask.sum()}")

    total = 0
    total += delete_from_table(
        syn, RES_TABLE, stale_pdm_mask, res_df, "stale PDM resources", dry_run
    )
    total += delete_from_table(
        syn, RES_TABLE, stale_cl_mask, res_df, "stale CL resources", dry_run
    )

    # ------------------------------------------------------------------ #
    # 2. CellLineDetails — rows whose cellLineId is a stale resource       #
    # ------------------------------------------------------------------ #
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Scanning {CL_TABLE} (CellLineDetails)")
    cl_df = _row_ids(syn.tableQuery(f"SELECT * FROM {CL_TABLE}").asDataFrame())
    if "cellLineId" in cl_df.columns and stale_cl_ids:
        stale_cl_detail_mask = cl_df["cellLineId"].isin(stale_cl_ids)
        total += delete_from_table(
            syn, CL_TABLE, stale_cl_detail_mask, cl_df,
            "stale CL details", dry_run
        )
    else:
        print("  ✅ No matching stale cell-line detail rows")

    # ------------------------------------------------------------------ #
    # 3. PatientDerivedModelDetails — rows with stale PDM IDs             #
    # ------------------------------------------------------------------ #
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Scanning {PDM_TABLE} (PDMDetails)")
    pdm_df = _row_ids(syn.tableQuery(f"SELECT * FROM {PDM_TABLE}").asDataFrame())
    if "patientDerivedModelId" in pdm_df.columns and stale_pdm_ids:
        stale_pdm_detail_mask = pdm_df["patientDerivedModelId"].isin(stale_pdm_ids)
        total += delete_from_table(
            syn, PDM_TABLE, stale_pdm_detail_mask, pdm_df,
            "stale PDM details", dry_run
        )
    else:
        print("  ✅ No matching stale PDM detail rows (or stale IDs not found)")

    print(
        f"\n{'[DRY-RUN] ' if dry_run else ''}Done. "
        f"Total rows {'would be ' if dry_run else ''}deleted: {total}"
    )


if __name__ == "__main__":
    main()
