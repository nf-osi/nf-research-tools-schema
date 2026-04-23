#!/usr/bin/env python3
"""
Upsert publication records and development links from submission CSVs to Synapse.

Sources (produced by compile_accepted_submissions.py):
  tool_coverage/outputs/submission_publications.csv
  tool_coverage/outputs/submission_dev_links.csv

Targets:
  syn26486839  NF Tool Publications (base publication table)
  syn26486807  Tool Development links (tool ↔ development publication)

FK resolution for development links:
  publicationId : UUID5 already correct (same namespace as generate_review_csv.py)
  resourceId    : looked up from syn51730943 by (resourceName, resourceType)

Usage:
    python upsert_publication_links.py [--csv-dir tool_coverage/outputs] [--dry-run]
"""

import os
import sys
import argparse
import pandas as pd
import synapseclient
from synapseclient import Table

PUB_TABLE = "syn26486839"
DEV_TABLE = "syn26486807"
RES_TABLE = "syn51730943"

CSV_DIR_DEFAULT = "tool_coverage/outputs"

# Maps compile_accepted ttype values → Synapse resourceType strings in syn51730943
_TTYPE_TO_RTYPE = {
    "animal_model":             "Animal Model",
    "antibody":                 "Antibody",
    "cell_line":                "Cell Line",
    "genetic_reagent":          "Genetic Reagent",
    "patient_derived_model":    "Patient-Derived Model",
    "computational_tool":       "Computational Tool",
    "organoid_protocol":  "Organoid Protocol",
    "clinical_assessment_tool": "Clinical Assessment Tool",
}


def _login() -> synapseclient.Synapse:
    token = os.getenv("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("❌ SYNAPSE_AUTH_TOKEN not set")
        sys.exit(1)
    syn = synapseclient.Synapse()
    syn.login(authToken=token, silent=True)
    return syn


def upsert_publications(syn, pubs_csv: str, dry_run: bool) -> int:
    """Upsert new publications from submission_publications.csv to syn26486839."""
    df = pd.read_csv(pubs_csv)

    # Strip internal tracking columns
    pub_cols = [c for c in df.columns if not c.startswith("_")]
    df_clean = df[pub_cols].drop_duplicates(subset="pmid", keep="first").copy()
    df_clean = df_clean[df_clean["pmid"].notna() & (df_clean["pmid"] != "")]

    # Fetch PMIDs already in Synapse
    existing = syn.tableQuery(f"SELECT pmid FROM {PUB_TABLE}").asDataFrame()
    existing_pmids = (
        set(existing["pmid"].dropna().str.strip().str.upper())
        if len(existing) > 0 else set()
    )

    new_pubs = df_clean[
        ~df_clean["pmid"].str.strip().str.upper().isin(existing_pmids)
    ].copy()

    print(f"  {len(df_clean)} in CSV | {len(existing_pmids)} already in Synapse "
          f"| {len(new_pubs)} to add")

    if dry_run:
        for _, row in new_pubs.iterrows():
            title = str(row.get("publicationTitle", ""))[:70]
            print(f"    + {row.get('pmid', '')} — {title}")
        return len(new_pubs)

    if len(new_pubs) > 0:
        syn.store(Table(PUB_TABLE, new_pubs))
        syn.create_snapshot_version(PUB_TABLE)
        print(f"  ✅ Added {len(new_pubs)} publications to {PUB_TABLE}")
    else:
        print("  ✅ No new publications to add")

    return len(new_pubs)


def upsert_development_links(syn, dev_csv: str, dry_run: bool) -> int:
    """
    Upsert development links from submission_dev_links.csv to syn26486807.

    Resolves resourceId from syn51730943 using (_toolName, _toolType).
    Skips rows already present (by publicationDevelopmentId) or unresolvable.
    """
    df = pd.read_csv(dev_csv)

    # Build (name_lower, resourceType) → resourceId lookup from syn51730943
    print(f"  Fetching resource registry from {RES_TABLE}...")
    res_df = syn.tableQuery(
        f"SELECT resourceId, resourceName, resourceType FROM {RES_TABLE}"
    ).asDataFrame()
    res_map: dict = {}
    for _, row in res_df.iterrows():
        rname = (row.get("resourceName") or "").strip()
        rtype = row.get("resourceType", "")
        res_map[(rname.lower(), rtype)] = row["resourceId"]

    # Fetch existing development link IDs to avoid duplicates
    existing_dev = syn.tableQuery(
        f"SELECT publicationDevelopmentId FROM {DEV_TABLE}"
    ).asDataFrame()
    existing_ids = (
        set(existing_dev["publicationDevelopmentId"].dropna())
        if len(existing_dev) > 0 else set()
    )

    rows_to_add = []
    skipped_dup = []
    skipped_no_res = []

    for _, row in df.iterrows():
        dev_id = row.get("publicationDevelopmentId", "")
        if dev_id in existing_ids:
            skipped_dup.append(dev_id)
            continue

        tool_name = (row.get("_toolName") or "").strip()
        ttype = row.get("_toolType", "")
        rtype = _TTYPE_TO_RTYPE.get(ttype, "")
        resource_id = res_map.get((tool_name.lower(), rtype))

        if not resource_id:
            skipped_no_res.append(f"{tool_name} ({rtype or ttype})")
            continue

        rows_to_add.append({
            "publicationDevelopmentId": dev_id,
            "publicationId": row["publicationId"],
            "resourceId": resource_id,
            "funderId": row.get("funderId") or "",
            "investigatorId": row.get("investigatorId") or "",
        })

    print(f"  {len(df)} in CSV | {len(existing_ids)} already in Synapse "
          f"| {len(rows_to_add)} to add | {len(skipped_no_res)} unresolved "
          f"| {len(skipped_dup)} duplicate")

    if skipped_no_res:
        print(f"  ⚠️  Could not resolve resourceId for {len(skipped_no_res)} row(s):")
        for name in skipped_no_res[:10]:
            print(f"    - {name}")
        if len(skipped_no_res) > 10:
            print(f"    ... and {len(skipped_no_res) - 10} more")
        print("  (Tool may not yet be in syn51730943 — run upsert-tools first)")

    if dry_run:
        for r in rows_to_add:
            print(f"    + devId={r['publicationDevelopmentId'][:8]}… "
                  f"resId={r['resourceId'][:8]}… funder={r['funderId'][:8] if r['funderId'] else '—'}")
        return len(rows_to_add)

    if rows_to_add:
        df_clean = pd.DataFrame(rows_to_add)
        syn.store(Table(DEV_TABLE, df_clean))
        syn.create_snapshot_version(DEV_TABLE)
        print(f"  ✅ Added {len(rows_to_add)} development links to {DEV_TABLE}")
    else:
        print("  ✅ No new development links to add")

    return len(rows_to_add)


def main():
    parser = argparse.ArgumentParser(
        description="Upsert publication records and development links to Synapse."
    )
    parser.add_argument(
        "--csv-dir", default=CSV_DIR_DEFAULT,
        help=f"Directory with submission_publications.csv and submission_dev_links.csv "
             f"(default: {CSV_DIR_DEFAULT})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be uploaded without making changes"
    )
    parser.add_argument(
        "--skip-publications", action="store_true",
        help=f"Skip upserting to the publications table ({PUB_TABLE})"
    )
    parser.add_argument(
        "--skip-development", action="store_true",
        help=f"Skip upserting to the development links table ({DEV_TABLE})"
    )
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 70)
        print("DRY-RUN MODE — no changes will be made to Synapse")
        print("=" * 70)

    syn = _login()
    print("✅ Logged in to Synapse\n")

    pub_csv = os.path.join(args.csv_dir, "submission_publications.csv")
    dev_csv = os.path.join(args.csv_dir, "submission_dev_links.csv")

    total_added = 0

    if not args.skip_publications:
        if not os.path.exists(pub_csv):
            print(f"⚠️  {pub_csv} not found — skipping publication upsert")
        else:
            print(f"[1/2] Publications → {PUB_TABLE}")
            total_added += upsert_publications(syn, pub_csv, args.dry_run)
            print()

    if not args.skip_development:
        if not os.path.exists(dev_csv):
            print(f"⚠️  {dev_csv} not found — skipping development link upsert")
        else:
            print(f"[2/2] Development links → {DEV_TABLE}")
            total_added += upsert_development_links(syn, dev_csv, args.dry_run)
            print()

    print("=" * 70)
    mode = "DRY-RUN" if args.dry_run else "LIVE"
    verb = "would be added" if args.dry_run else "added"
    print(f"✅ Done ({mode}) — {total_added} rows {verb}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
