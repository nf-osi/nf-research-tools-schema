#!/usr/bin/env python3
"""
One-time fix: resolve null publicationId for observation rows in syn26486836
that were created from submissions in the local submissions/ directory.

Reads submissions/*/observations/*.json to:
  1. Reconstruct each observationId (same formula as compile_accepted_submissions.py)
  2. Extract the PMID/DOI and look up the correct Synapse publicationId from syn26486839

Only patches rows whose observationId matches a local submission JSON.
Rows from other sources (e.g. formspark) are left untouched.

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


def _make_obs_id(resource_name: str, obs_type: str, obs_text: str, pmid_or_doi: str) -> str:
    key = f"{resource_name}|{obs_type}|{(obs_text or '')[:200]}|{pmid_or_doi}"
    return str(uuid.uuid5(_PROJECT_NAMESPACE, f"observation:{key}"))


def build_local_obs_map() -> dict:
    """
    Scan submissions/*/observations/*.json and return
    {observationId: (numeric_pmid, doi)} for every local observation.
    """
    obs_map = {}
    for fpath in sorted(glob.glob(str(SUBMISSIONS_DIR / "*" / "observations" / "*.json"))):
        with open(fpath) as f:
            d = json.load(f)

        pubs = d.get("_publications", [])
        first_pub = pubs[0] if pubs else {}
        raw_pmid    = (first_pub.get("_pmid") or d.get("_pmid") or "").strip()
        doi         = (first_pub.get("_doi")  or d.get("_doi")  or "").strip()
        pmid_or_doi = raw_pmid or doi   # used verbatim in the observationId key

        resource_name = d.get("resourceName", "")
        obs_type      = d.get("observationType", "")
        obs_text      = d.get("details", "")

        if not resource_name or not obs_type or not pmid_or_doi:
            continue

        obs_id      = _make_obs_id(resource_name, obs_type, obs_text, pmid_or_doi)
        # Strip "PMID:" prefix for the Synapse pmid column lookup
        numeric_pmid = raw_pmid.replace("PMID:", "").strip() if raw_pmid else ""
        obs_map[obs_id] = (numeric_pmid, doi)

    return obs_map


def main():
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

    pub_df = syn.tableQuery(f"SELECT publicationId, pmid, doi FROM {PUB_TABLE}").asDataFrame()
    pmid_to_pub_id = dict(zip(pub_df["pmid"].astype(str).str.strip(), pub_df["publicationId"]))
    doi_to_pub_id  = dict(zip(pub_df["doi"].astype(str).str.strip(),  pub_df["publicationId"]))

    obs_df = syn.tableQuery(
        f"SELECT observationId FROM {OBS_TABLE} WHERE publicationId IS NULL"
    ).asDataFrame()
    print(f"Null-publicationId observations in Synapse: {len(obs_df)}")
    if obs_df.empty:
        print("Nothing to fix.")
        return

    patch_rows = []
    unresolved = []
    skipped    = 0

    for idx, row in obs_df.iterrows():
        obs_id = str(row["observationId"])
        if obs_id not in local_obs_map:
            skipped += 1
            continue

        pmid, doi = local_obs_map[obs_id]
        pub_id = pmid_to_pub_id.get(pmid) or doi_to_pub_id.get(doi)
        parts  = str(idx).split("_")
        if pub_id:
            patch_rows.append({
                "ROW_ID":        int(parts[0]),
                "ROW_VERSION":   int(parts[1]),
                "publicationId": pub_id,
            })
        else:
            unresolved.append((obs_id, pmid, doi))

    print(f"\nMatched to local submissions: {len(patch_rows) + len(unresolved)}")
    print(f"  Resolved publicationId:   {len(patch_rows)}")
    print(f"  No pub match in Synapse:  {len(unresolved)}")
    print(f"Not from local submissions: {skipped} (left untouched)")

    if unresolved:
        print("\nUnresolved (pmid/doi not found in syn26486839):")
        for obs_id, pmid, doi in unresolved:
            print(f"  observationId={obs_id}  pmid={pmid!r}  doi={doi!r}")

    if not patch_rows:
        print("Nothing to patch.")
        return

    confirm = input(f"\nPatch {len(patch_rows)} rows? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    syn.store(Table(OBS_TABLE, pd.DataFrame(patch_rows)))
    syn.create_snapshot_version(
        OBS_TABLE,
        comment="patch publicationId for local-submission observations",
    )
    print(f"\n✅ Patched {len(patch_rows)} rows + snapshot created")


if __name__ == "__main__":
    main()
