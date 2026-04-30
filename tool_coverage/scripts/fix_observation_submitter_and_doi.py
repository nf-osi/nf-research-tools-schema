#!/usr/bin/env python3
"""
One-time patch for data uploaded by upsert-tools.yml:

  1. Publications (syn26486839):
     Normalize bare DOIs (e.g. 10.1038/...) to full URL form
     (https://www.doi.org/10.1038/...).

  2. Observations (syn26486836):
     - Set observationSubmitterName = '🤖 AI-extracted' for rows
       whose observationId matches a local submission JSON (pipeline-uploaded).
       Formspark rows not found in local JSONs are left untouched.
     - Clear observationLink when it equals the publication DOI
       (bare or URL form); keep it only for genuinely distinct external links.

Requires SYNAPSE_AUTH_TOKEN env var. Run from the repo root.
"""
import glob
import json
import os
import sys
import uuid
import pathlib
import pandas as pd
import synapseclient
from synapseclient import Table

OBS_TABLE       = "syn26486836"
PUB_TABLE       = "syn26486839"
SUBMISSIONS_DIR = pathlib.Path("submissions")
_PROJECT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://nf.synapse.org/NF-research-tools")

AI_SUBMITTER = "🤖 AI-extracted"


def _doi_url(doi: str) -> str:
    if not doi:
        return doi
    doi = doi.strip()
    if doi.startswith("http"):
        return doi
    return f"https://www.doi.org/{doi}"


def _doi_bare(doi: str) -> str:
    return (doi or "").replace("https://doi.org/", "").replace("https://www.doi.org/", "").strip()


def _make_obs_id(resource_name: str, obs_type: str, obs_text: str, pmid_or_doi: str) -> str:
    key = f"{resource_name}|{obs_type}|{(obs_text or '')[:200]}|{pmid_or_doi}"
    return str(uuid.uuid5(_PROJECT_NAMESPACE, f"observation:{key}"))


def build_local_obs_map() -> dict:
    """
    Scan submissions/*/observations/*.json.
    Returns {observationId: doi_bare} for every local (AI-extracted) observation.
    """
    obs_map = {}
    for fpath in sorted(glob.glob(str(SUBMISSIONS_DIR / "*" / "observations" / "*.json"))):
        with open(fpath) as f:
            d = json.load(f)

        pubs = d.get("_publications", [])
        first_pub = pubs[0] if pubs else {}
        raw_pmid    = (first_pub.get("_pmid") or d.get("_pmid") or "").strip()
        doi         = (first_pub.get("_doi")  or d.get("_doi")  or "").strip()
        pmid_or_doi = raw_pmid or doi

        resource_name = d.get("resourceName", "")
        obs_type      = d.get("observationType", "")
        obs_text      = d.get("details", "")

        if not resource_name or not obs_type or not pmid_or_doi:
            continue

        obs_id = _make_obs_id(resource_name, obs_type, obs_text, pmid_or_doi)
        obs_map[obs_id] = _doi_bare(doi)

    return obs_map


def patch_publications(syn, dry_run: bool) -> int:
    """Normalize bare DOIs to https://www.doi.org/ URLs. Returns patch count."""
    print(f"\n── Publications ({PUB_TABLE}) ──")
    pub_df = syn.tableQuery(
        f"SELECT publicationId, doi FROM {PUB_TABLE}"
    ).asDataFrame()
    print(f"Total publication rows: {len(pub_df)}")

    to_patch = pub_df[
        pub_df["doi"].notna()
        & ~pub_df["doi"].astype(str).str.startswith("http")
        & (pub_df["doi"].astype(str).str.strip() != "")
    ].copy()
    print(f"Bare-DOI rows to normalize: {len(to_patch)}")
    if to_patch.empty:
        print("Nothing to patch.")
        return 0

    print(to_patch[["publicationId", "doi"]].head(10).to_string())
    if len(to_patch) > 10:
        print(f"  ... and {len(to_patch) - 10} more")

    if dry_run:
        print("[dry-run] Would normalize these DOIs.")
        return len(to_patch)

    patch_rows = []
    for idx, row in to_patch.iterrows():
        parts = str(idx).split("_")
        patch_rows.append({
            "ROW_ID":      int(parts[0]),
            "ROW_VERSION": int(parts[1]),
            "doi":         _doi_url(str(row["doi"])),
        })

    syn.store(Table(PUB_TABLE, pd.DataFrame(patch_rows)))
    syn.create_snapshot_version(
        PUB_TABLE,
        comment="normalize bare DOIs to https://www.doi.org/ URL format",
    )
    print(f"✅ Patched {len(patch_rows)} publication DOIs + snapshot created")
    return len(patch_rows)


def patch_observations(syn, local_obs_map: dict, dry_run: bool) -> int:
    """
    Set observationSubmitterName and clear matching observationLink for
    pipeline-uploaded (AI-extracted) rows. Returns patch count.
    """
    print(f"\n── Observations ({OBS_TABLE}) ──")
    obs_df = syn.tableQuery(
        f"SELECT observationId, observationSubmitterName, observationLink "
        f"FROM {OBS_TABLE}"
    ).asDataFrame()
    print(f"Total observation rows: {len(obs_df)}")
    print(f"Local AI-extracted observation JSONs: {len(local_obs_map)}")

    patch_rows = []
    skipped_not_local = 0

    for idx, row in obs_df.iterrows():
        obs_id = str(row["observationId"])
        if obs_id not in local_obs_map:
            skipped_not_local += 1
            continue

        doi_bare_pub = local_obs_map[obs_id]
        current_name = str(row.get("observationSubmitterName") or "")
        current_link = str(row.get("observationLink") or "")

        new_name = AI_SUBMITTER
        # Clear link if it matches the publication DOI; otherwise keep
        new_link = current_link if (_doi_bare(current_link) != doi_bare_pub) else ""

        if current_name == new_name and current_link == new_link:
            continue  # already correct

        parts = str(idx).split("_")
        patch_rows.append({
            "ROW_ID":                    int(parts[0]),
            "ROW_VERSION":               int(parts[1]),
            "observationSubmitterName":  new_name,
            "observationLink":           new_link if new_link else None,
        })

    matched = len(obs_df) - skipped_not_local
    print(f"Rows matched to local JSONs:    {matched}")
    print(f"  Need patching:               {len(patch_rows)}")
    print(f"  Already correct:             {matched - len(patch_rows)}")
    print(f"Not from local submissions:    {skipped_not_local} (left untouched)")

    if not patch_rows:
        print("Nothing to patch.")
        return 0

    if dry_run:
        print("[dry-run] Would patch these observation rows.")
        return len(patch_rows)

    syn.store(Table(OBS_TABLE, pd.DataFrame(patch_rows)))
    syn.create_snapshot_version(
        OBS_TABLE,
        comment="set observationSubmitterName='🤖 AI-extracted', clear DOI-duplicate observationLinks",
    )
    print(f"✅ Patched {len(patch_rows)} observation rows + snapshot created")
    return len(patch_rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("Error: SYNAPSE_AUTH_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    if not SUBMISSIONS_DIR.exists():
        print(f"Error: {SUBMISSIONS_DIR} not found — run from the repo root", file=sys.stderr)
        sys.exit(1)

    local_obs_map = build_local_obs_map()
    print(f"Local observation JSONs parsed: {len(local_obs_map)}")

    syn = synapseclient.Synapse(silent=True)
    syn.login(authToken=token, silent=True)

    pub_count = patch_publications(syn, dry_run=args.dry_run)
    obs_count = patch_observations(syn, local_obs_map, dry_run=args.dry_run)

    print(f"\n{'[dry-run] ' if args.dry_run else ''}Summary: {pub_count} publication DOIs, {obs_count} observation rows")


if __name__ == "__main__":
    main()
