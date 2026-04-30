#!/usr/bin/env python3
"""
Upsert publication records, development links, vendor items, and investigators
from submission CSVs to Synapse.

Sources (produced by compile_accepted_submissions.py):
  tool_coverage/outputs/submission_publications.csv
  tool_coverage/outputs/submission_dev_links.csv
  tool_coverage/outputs/ACCEPTED_vendorItem.csv
  tool_coverage/outputs/ACCEPTED_animal_models.csv    (developerName/Affiliation)
  tool_coverage/outputs/ACCEPTED_computational_tools.csv (developerName/Affiliation)

Targets:
  syn26486839  NF Tool Publications
  syn26486807  Tool Development links (tool ↔ development publication)
  syn26486843  VendorItem (vendor ↔ resource catalog links)
  syn51734029  Investigator (developer name/affiliation per resource)

FK resolution:
  publicationId : UUID5 already correct (same namespace as generate_review_csv.py)
  resourceId    : looked up from syn51730943 by (resourceName, resourceType)

Usage:
    python upsert_publication_links.py [--csv-dir tool_coverage/outputs] [--dry-run]
"""

import os
import sys
import uuid
import argparse
import pandas as pd
import synapseclient
from synapseclient import Table

PUB_TABLE          = "syn26486839"
DEV_TABLE          = "syn26486807"
RES_TABLE          = "syn51730943"
VENDOR_ITEM_TABLE  = "syn26486843"
INVESTIGATOR_TABLE = "syn26486833"

CSV_DIR_DEFAULT = "tool_coverage/outputs"


def _run_url_comment() -> str:
    """Return the GitHub Actions run URL for use as a snapshot comment, or '' locally."""
    server = os.getenv("GITHUB_SERVER_URL", "").rstrip("/")
    repo   = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{run_id}" if (server and repo and run_id) else ""


def _snapshot(syn, table_id: str) -> None:
    """Create a snapshot version, ignoring errors on materialized views."""
    try:
        syn.create_snapshot_version(table_id, comment=_run_url_comment() or None)
    except Exception as e:
        print(f"  ⚠️  Snapshot skipped for {table_id}: {e}")

# Shared UUID namespace — must match compile_accepted_submissions.py
_PROJECT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://nf.synapse.org/NF-research-tools"
)

# Maps compile_accepted ttype values → Synapse resourceType strings in syn51730943
_TTYPE_TO_RTYPE = {
    "animal_model":             "Animal Model",
    "antibody":                 "Antibody",
    "cell_line":                "Cell Line",
    "genetic_reagent":          "Genetic Reagent",
    "patient_derived_model":    "Patient-Derived Model",
    "computational_tool":       "Computational Tool",
    "organoid_protocol":        "Organoid Protocol",
    "clinical_assessment_tool": "Clinical Assessment Tool",
}

# ACCEPTED_*.csv files that carry developerName/developerAffiliation fields,
# mapped to the Synapse resourceType used for resourceId lookup.
_DEVELOPER_CSV_RTYPES = {
    "ACCEPTED_animal_models.csv":            "Animal Model",
    "ACCEPTED_cell_lines.csv":               "Cell Line",
    "ACCEPTED_computational_tools.csv":      "Computational Tool",
    "ACCEPTED_patient_derived_models.csv":   "Patient-Derived Model",
    "ACCEPTED_organoid_protocols.csv":       "Organoid Protocol",
    "ACCEPTED_clinical_assessment_tools.csv":"Clinical Assessment Tool",
}


def _str(val) -> str:
    """Return string, coercing None/NaN to empty string."""
    return "" if val is None or (isinstance(val, float) and pd.isna(val)) else str(val)


def _login() -> synapseclient.Synapse:
    token = os.getenv("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("❌ SYNAPSE_AUTH_TOKEN not set")
        sys.exit(1)
    syn = synapseclient.Synapse()
    syn.login(authToken=token, silent=True)
    return syn


def _build_res_map(syn, csv_dir: str | None = None) -> dict:
    """Return (name_lower, resourceType) → resourceId.

    Combines syn51730943 (existing Synapse resources) with the local
    ACCEPTED_resources.csv (newly compiled resources not yet in Synapse).
    Local entries supplement but do not override Synapse entries.
    """
    res_df = syn.tableQuery(
        f"SELECT resourceId, resourceName, resourceType FROM {RES_TABLE}"
    ).asDataFrame()
    res_map: dict = {}
    for _, row in res_df.iterrows():
        rname = (row.get("resourceName") or "").strip()
        rtype = row.get("resourceType", "")
        res_map[(rname.lower(), rtype)] = row["resourceId"]

    # Supplement with locally compiled resources (not yet in Synapse)
    if csv_dir:
        local_csv = os.path.join(csv_dir, "ACCEPTED_resources.csv")
        if os.path.exists(local_csv):
            local_df = pd.read_csv(local_csv)
            added = 0
            for _, row in local_df.iterrows():
                rname = (row.get("resourceName") or "").strip()
                rtype = row.get("resourceType", "")
                rid = (row.get("resourceId") or "").strip()
                if rname and rtype and rid:
                    key = (rname.lower(), rtype)
                    if key not in res_map:
                        res_map[key] = rid
                        added += 1
            if added:
                print(f"  + {added} local-only resource(s) added from ACCEPTED_resources.csv")

    return res_map


def upsert_publications(syn, pubs_csv: str, dry_run: bool) -> int:
    """Upsert new publications from submission_publications.csv to syn26486839."""
    df = pd.read_csv(pubs_csv)

    # Strip internal tracking columns; year is a real column now (added to syn26486839)
    pub_cols = [c for c in df.columns if not c.startswith("_")]
    df_clean = df[pub_cols].drop_duplicates(subset="pmid", keep="first").copy()
    df_clean = df_clean[df_clean["pmid"].notna() & (df_clean["pmid"] != "")]

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
        _snapshot(syn, PUB_TABLE)
        print(f"  ✅ Added {len(new_pubs)} publications to {PUB_TABLE}")
    else:
        print("  ✅ No new publications to add")

    return len(new_pubs)


def upsert_development_links(syn, dev_csv: str, res_map: dict, dry_run: bool) -> int:
    """
    Upsert development links from submission_dev_links.csv to syn26486807.

    Resolves resourceId from res_map using (_toolName, _toolType).
    Resolves publicationId from syn26486839 by PMID — the local UUID5 from
    _make_pub_id may differ from the Synapse-assigned ID for pre-existing pubs.
    Skips rows already present (by developmentId) or unresolvable.
    """
    df = pd.read_csv(dev_csv)

    existing_dev = syn.tableQuery(
        f"SELECT developmentId FROM {DEV_TABLE}"
    ).asDataFrame()
    existing_ids = (
        set(existing_dev["developmentId"].dropna())
        if len(existing_dev) > 0 else set()
    )

    # Build PMID → actual Synapse publicationId lookup to fix UUID mismatches
    pub_df = syn.tableQuery(
        f"SELECT publicationId, pmid, doi FROM {PUB_TABLE}"
    ).asDataFrame()
    pmid_to_pub_id = {
        _str(r["pmid"]): _str(r["publicationId"])
        for _, r in pub_df.iterrows() if _str(r["pmid"])
    }
    doi_to_pub_id = {
        _str(r["doi"]): _str(r["publicationId"])
        for _, r in pub_df.iterrows() if _str(r["doi"])
    }

    rows_to_add = []
    skipped_dup = []
    skipped_no_res = []

    for _, row in df.iterrows():
        dev_id = row.get("developmentId", "")
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

        # Prefer actual Synapse publicationId over the locally-generated UUID5
        csv_pmid = _str(row.get("_pmid"))
        csv_pub_id = _str(row.get("publicationId"))
        pub_id = pmid_to_pub_id.get(csv_pmid) or doi_to_pub_id.get(csv_pub_id) or csv_pub_id

        rows_to_add.append({
            "developmentId": dev_id,
            "publicationId": pub_id,
            "resourceId": resource_id,
            "funderId": _str(row.get("funderId")),
            "investigatorId": _str(row.get("investigatorId")),
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
            dev_id = r['developmentId']
            print(f"    + devId={dev_id[:8]}… resId={r['resourceId'][:8]}… "
                  f"funder={r['funderId'][:8] if r['funderId'] else '—'}")
        return len(rows_to_add)

    if rows_to_add:
        syn.store(Table(DEV_TABLE, pd.DataFrame(rows_to_add)))
        _snapshot(syn, DEV_TABLE)
        print(f"  ✅ Added {len(rows_to_add)} development links to {DEV_TABLE}")
    else:
        print("  ✅ No new development links to add")

    return len(rows_to_add)


def upsert_investigators(syn, csv_dir: str, res_map: dict, dry_run: bool) -> int:
    """
    Upsert investigator records to syn26486833 from developer fields in tool CSVs.

    developerName and developerAffiliation are stripped from the detail-table upload
    in clean_submission_csvs.py and routed here instead.  Investigator is a person-level
    entity; the investigator↔resource link lives in the dev-links table (syn26486807).
    Also patches any existing dev-link rows that still have a blank investigatorId.

    Handles:
    - Semicolon-joined multi-investigator fields ("Alice; Bob") → split into separate rows
    - Within-batch name dedup: prefers entry with institution over blank for same name
    - Cross-Synapse name dedup: if a name already exists in syn26486833 under any UUID,
      reuses that UUID rather than inserting a duplicate (covers affiliation-string drift)
    """
    # name_lower → {"inv_id", "investigatorName", "institution", ...}
    # Keyed by name so within-batch dedup is natural: prefer entry with institution.
    by_name: dict = {}
    inv_id_for_resource: dict = {}   # resourceId → investigatorId (primary investigator)

    for csv_name, rtype in _DEVELOPER_CSV_RTYPES.items():
        csv_path = os.path.join(csv_dir, csv_name)
        if not os.path.exists(csv_path):
            continue
        df = pd.read_csv(csv_path)
        if "developerName" not in df.columns:
            continue

        for _, row in df.iterrows():
            raw_name = _str(row.get("developerName"))
            if not raw_name:
                continue
            raw_affil = _str(row.get("developerAffiliation"))
            tool_name = _str(row.get("_resourceName")) or _str(row.get("_toolName"))
            resource_id = res_map.get((tool_name.lower(), rtype))
            if not resource_id:
                continue  # skip if resource not yet in Synapse

            # Split on ";" to handle multiple investigators listed in one field
            names = [n.strip() for n in raw_name.split(";") if n.strip()]
            affils = [a.strip() for a in raw_affil.split(";") if a.strip()]
            affils += [""] * (len(names) - len(affils))  # pad if fewer affiliations

            primary_inv_id = None
            for i, (name, affil) in enumerate(zip(names, affils)):
                key = name.lower()
                existing = by_name.get(key)
                if existing is None or (not existing["institution"] and affil):
                    # New name, or upgrading a blank-institution entry with a real one
                    inv_id = str(uuid.uuid5(
                        _PROJECT_NAMESPACE,
                        f"investigator:{name}:{affil}",
                    ))
                    by_name[key] = {
                        "investigatorId":        inv_id,
                        "investigatorName":      name,
                        "institution":           affil,
                        "orcid":                 "",
                        "investigatorSynapseId": "",
                    }
                if i == 0:
                    primary_inv_id = by_name[key]["investigatorId"]

            if primary_inv_id and resource_id:
                inv_id_for_resource[resource_id] = primary_inv_id

    if not by_name:
        print("  No investigator records found in CSVs")
        return 0

    # Fetch existing investigators by both UUID and name for cross-Synapse dedup
    existing_inv = syn.tableQuery(
        f"SELECT investigatorId, investigatorName FROM {INVESTIGATOR_TABLE}"
    ).asDataFrame()
    existing_ids: set = (
        set(existing_inv["investigatorId"].dropna())
        if len(existing_inv) > 0 else set()
    )
    # name_lower → existing investigatorId (handles affiliation-string drift)
    existing_by_name: dict = {}
    for _, er in existing_inv.iterrows():
        ename = _str(er.get("investigatorName")).lower()
        if ename:
            existing_by_name[ename] = _str(er["investigatorId"])

    # Remap inv_id_for_resource: if a name already exists in Synapse under a different
    # UUID, point resources to the existing UUID so dev-link patches are correct.
    for resource_id, inv_id in list(inv_id_for_resource.items()):
        row = next((r for r in by_name.values() if r["investigatorId"] == inv_id), None)
        if row:
            synapse_id = existing_by_name.get(row["investigatorName"].lower())
            if synapse_id and synapse_id != inv_id:
                inv_id_for_resource[resource_id] = synapse_id

    # New rows: not matched by UUID and not matched by name
    new_rows = [
        r for r in by_name.values()
        if r["investigatorId"] not in existing_ids
        and r["investigatorName"].lower() not in existing_by_name
    ]
    skipped_name = sum(
        1 for r in by_name.values()
        if r["investigatorId"] not in existing_ids
        and r["investigatorName"].lower() in existing_by_name
    )

    print(f"  {len(by_name)} in CSVs | {len(existing_ids)} already in Synapse "
          f"| {len(new_rows)} to add | {skipped_name} matched by name (skipped)")

    if dry_run:
        for r in new_rows:
            print(f"    + {r['investigatorName']} ({r['institution'] or '—'})")
        _patch_dev_link_investigator_ids(syn, inv_id_for_resource, dry_run=True)
        return len(new_rows)

    if new_rows:
        syn.store(Table(INVESTIGATOR_TABLE, pd.DataFrame(new_rows)))
        _snapshot(syn, INVESTIGATOR_TABLE)
        print(f"  ✅ Added {len(new_rows)} investigators to {INVESTIGATOR_TABLE}")
    else:
        print("  ✅ No new investigators to add")

    _patch_dev_link_investigator_ids(syn, inv_id_for_resource, dry_run=False)

    return len(new_rows)


def _patch_dev_link_investigator_ids(
    syn, inv_id_for_resource: dict, dry_run: bool
) -> None:
    """Update dev-link rows in syn26486807 that have a blank investigatorId."""
    if not inv_id_for_resource:
        return

    existing_dev = syn.tableQuery(
        f"SELECT resourceId, investigatorId FROM {DEV_TABLE}"
    ).asDataFrame()
    if existing_dev.empty:
        return

    patch_rows = []
    for idx, drow in existing_dev.iterrows():
        if _str(drow.get("investigatorId")):
            continue  # already set
        resource_id = _str(drow.get("resourceId"))
        inv_id = inv_id_for_resource.get(resource_id)
        if not inv_id:
            continue
        parts = str(idx).split("_")
        patch_rows.append({
            "ROW_ID":        int(parts[0]),
            "ROW_VERSION":   int(parts[1]),
            "investigatorId": inv_id,
        })

    if not patch_rows:
        print("  ℹ️  No dev-link rows need investigatorId patched")
        return

    if dry_run:
        print(f"  [dry-run] Would patch investigatorId for {len(patch_rows)} dev-link row(s)")
        return

    syn.store(Table(DEV_TABLE, pd.DataFrame(patch_rows)))
    print(f"  ✅ Patched investigatorId for {len(patch_rows)} dev-link row(s) in {DEV_TABLE}")


def upsert_vendor_items(syn, vendor_item_csv: str, res_map: dict, dry_run: bool) -> int:
    """
    Upsert vendor item records from ACCEPTED_vendorItem.csv to syn26486843.

    Resolves resourceId from res_map by (_resourceName, "Antibody").
    Skips rows already present (by vendorItemId) or where resourceId cannot be resolved.
    """
    df = pd.read_csv(vendor_item_csv)
    if df.empty:
        print("  No vendor item rows to process")
        return 0

    existing_vi = syn.tableQuery(
        f"SELECT vendorItemId FROM {VENDOR_ITEM_TABLE}"
    ).asDataFrame()
    existing_ids = (
        set(existing_vi["vendorItemId"].dropna())
        if len(existing_vi) > 0 else set()
    )

    rows_to_add = []
    skipped_dup = []
    skipped_no_res = []

    for _, row in df.iterrows():
        vi_id = row.get("vendorItemId", "")
        if vi_id in existing_ids:
            skipped_dup.append(vi_id)
            continue

        resource_name = (row.get("_resourceName") or "").strip()
        if not resource_name:
            print(f"  ⚠️  Skipping vendorItem row with blank _resourceName (vendorItemId={vi_id!r})")
            continue

        resource_id = res_map.get((resource_name.lower(), "Antibody")) or \
                      next((v for k, v in res_map.items() if k[0] == resource_name.lower()), None)

        if not resource_id:
            skipped_no_res.append(resource_name)
            continue

        rows_to_add.append({
            "vendorItemId":    vi_id,
            "vendorId":        row.get("vendorId", ""),
            "resourceId":      resource_id,
            "catalogNumber":   row.get("catalogNumber", ""),
            "catalogNumberURL": row.get("catalogNumberURL", ""),
        })

    print(f"  {len(df)} in CSV | {len(existing_ids)} already in Synapse "
          f"| {len(rows_to_add)} to add | {len(skipped_no_res)} unresolved "
          f"| {len(skipped_dup)} duplicate")

    if skipped_no_res:
        print(f"  ⚠️  Could not resolve resourceId for {len(skipped_no_res)} row(s):")
        for name in skipped_no_res[:10]:
            print(f"    - {name}")
        print("  (Resource may not yet be in syn51730943 — run upsert-tools first)")

    if dry_run:
        for r in rows_to_add:
            print(f"    + {r['vendorItemId'][:8]}… catalog={r['catalogNumber']} "
                  f"vendor={r['vendorId'][:8]}…")
        return len(rows_to_add)

    if rows_to_add:
        syn.store(Table(VENDOR_ITEM_TABLE, pd.DataFrame(rows_to_add)))
        _snapshot(syn, VENDOR_ITEM_TABLE)
        print(f"  ✅ Added {len(rows_to_add)} vendor items to {VENDOR_ITEM_TABLE}")
    else:
        print("  ✅ No new vendor items to add")

    return len(rows_to_add)


def main():
    parser = argparse.ArgumentParser(
        description="Upsert publications, development links, vendor items, and investigators to Synapse."
    )
    parser.add_argument(
        "--csv-dir", default=CSV_DIR_DEFAULT,
        help=f"Directory containing submission CSVs (default: {CSV_DIR_DEFAULT})"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be uploaded without making changes")
    parser.add_argument("--skip-publications", action="store_true",
                        help=f"Skip {PUB_TABLE}")
    parser.add_argument("--skip-development", action="store_true",
                        help=f"Skip {DEV_TABLE}")
    parser.add_argument("--skip-vendor-items", action="store_true",
                        help=f"Skip {VENDOR_ITEM_TABLE}")
    parser.add_argument("--skip-investigators", action="store_true",
                        help=f"Skip {INVESTIGATOR_TABLE}")
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 70)
        print("DRY-RUN MODE — no changes will be made to Synapse")
        print("=" * 70)

    syn = _login()
    print("✅ Logged in to Synapse\n")

    pub_csv = os.path.join(args.csv_dir, "submission_publications.csv")
    dev_csv = os.path.join(args.csv_dir, "submission_dev_links.csv")
    vi_csv  = os.path.join(args.csv_dir, "ACCEPTED_vendorItem.csv")

    # Build shared resource map once — reused by dev links, vendor items, investigators
    print(f"Fetching resource registry from {RES_TABLE}...")
    res_map = _build_res_map(syn, csv_dir=args.csv_dir)
    print(f"  {len(res_map)} resources loaded\n")

    total_added = 0
    step = 1
    total_steps = sum([
        not args.skip_publications,
        not args.skip_development,
        not args.skip_vendor_items,
        not args.skip_investigators,
    ])

    if not args.skip_publications:
        if not os.path.exists(pub_csv):
            print(f"⚠️  {pub_csv} not found — skipping publication upsert")
        else:
            print(f"[{step}/{total_steps}] Publications → {PUB_TABLE}")
            total_added += upsert_publications(syn, pub_csv, args.dry_run)
            print()
        step += 1

    if not args.skip_development:
        if not os.path.exists(dev_csv):
            print(f"⚠️  {dev_csv} not found — skipping development link upsert")
        else:
            print(f"[{step}/{total_steps}] Development links → {DEV_TABLE}")
            total_added += upsert_development_links(syn, dev_csv, res_map, args.dry_run)
            print()
        step += 1

    if not args.skip_vendor_items:
        if not os.path.exists(vi_csv):
            print(f"⚠️  {vi_csv} not found — skipping vendor item upsert")
        else:
            print(f"[{step}/{total_steps}] Vendor items → {VENDOR_ITEM_TABLE}")
            total_added += upsert_vendor_items(syn, vi_csv, res_map, args.dry_run)
            print()
        step += 1

    if not args.skip_investigators:
        print(f"[{step}/{total_steps}] Investigators → {INVESTIGATOR_TABLE}")
        total_added += upsert_investigators(syn, args.csv_dir, res_map, args.dry_run)
        print()

    print("=" * 70)
    mode = "DRY-RUN" if args.dry_run else "LIVE"
    verb = "would be added" if args.dry_run else "added"
    print(f"✅ Done ({mode}) — {total_added} rows {verb}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
