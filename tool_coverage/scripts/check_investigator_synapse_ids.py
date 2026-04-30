#!/usr/bin/env python3
"""
Check syn26486833 (Investigator table) for rows with a developerName but no
investigatorSynapseId, then search the Synapse People Search API to find
candidate profiles.

Outputs:
  - Console table of matches / no-matches
  - tool_coverage/outputs/investigator_synapse_id_report.csv (for GH Actions artifact)
  - GitHub Actions step summary (GITHUB_STEP_SUMMARY) when running in CI

Requires SYNAPSE_AUTH_TOKEN env var.
"""
import csv
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import json
import pathlib
import synapseclient

INVESTIGATOR_TABLE = "syn26486833"
OUTPUT_CSV = pathlib.Path("tool_coverage/outputs/investigator_synapse_id_report.csv")
PEOPLE_SEARCH_API = "https://www.synapse.org/repo/v1/userGroupHeaders"


def _search_synapse_users(prefix: str, limit: int = 20) -> list[dict]:
    """Call the Synapse userGroupHeaders API and return the children list."""
    params = urllib.parse.urlencode({"prefix": prefix, "filter": "USER", "limit": limit})
    url = f"{PEOPLE_SEARCH_API}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("children", [])
    except Exception:
        return []


def _name_score(candidate: dict, first: str, last: str) -> int:
    """Score a candidate profile against the target first/last name (0–4)."""
    c_first = (candidate.get("firstName") or "").lower().strip()
    c_last  = (candidate.get("lastName")  or "").lower().strip()
    score = 0
    if last  and c_last  == last.lower():  score += 2
    if first and c_first == first.lower(): score += 1
    if first and c_first.startswith(first.lower()[0]): score += 1
    return score


def find_synapse_profiles(full_name: str) -> list[dict]:
    """
    Return candidate Synapse profiles for a full name string.
    Searches by last name first; falls back to first name if zero results.
    Each candidate dict: {ownerId, userName, firstName, lastName, score}
    """
    parts = full_name.strip().split()
    if not parts:
        return []
    last  = parts[-1]
    first = parts[0] if len(parts) > 1 else ""

    candidates = _search_synapse_users(last)
    if not candidates and first:
        candidates = _search_synapse_users(first)

    scored = []
    for c in candidates:
        score = _name_score(c, first, last)
        if score >= 2:  # require at least a last-name match
            scored.append({
                "ownerId":   c.get("ownerId", ""),
                "userName":  c.get("userName", ""),
                "firstName": c.get("firstName", ""),
                "lastName":  c.get("lastName", ""),
                "score":     score,
            })

    scored.sort(key=lambda x: -x["score"])
    return scored


def split_names(raw: str) -> list[str]:
    """Split semicolon-separated compound name fields into individual names."""
    return [n.strip() for n in raw.split(";") if n.strip()]


def main():
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not token:
        print("Error: SYNAPSE_AUTH_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    syn = synapseclient.Synapse(silent=True)
    syn.login(authToken=token, silent=True)

    print(f"Querying {INVESTIGATOR_TABLE} for rows with missing investigatorSynapseId...")
    df = syn.tableQuery(
        f"SELECT resourceId, resourceName, developerName, investigatorSynapseId "
        f"FROM {INVESTIGATOR_TABLE}"
    ).asDataFrame()

    print(f"Total rows: {len(df)}")

    missing = df[
        df["investigatorSynapseId"].isna()
        & df["developerName"].notna()
        & (df["developerName"].astype(str).str.strip() != "")
    ].copy()

    print(f"Rows with developerName but no investigatorSynapseId: {len(missing)}\n")

    # Collect unique individual names across all rows
    unique_names: dict[str, list[str]] = {}  # name → [resourceName, ...]
    for _, row in missing.iterrows():
        for name in split_names(str(row["developerName"])):
            unique_names.setdefault(name, [])
            rname = str(row.get("resourceName") or "")
            if rname not in unique_names[name]:
                unique_names[name].append(rname)

    print(f"Unique developer names to search: {len(unique_names)}\n")

    results = []
    for name, resources in sorted(unique_names.items()):
        time.sleep(0.2)  # be polite to the API
        candidates = find_synapse_profiles(name)
        results.append({
            "developerName": name,
            "resources":     "; ".join(resources),
            "found":         bool(candidates),
            "candidates":    candidates,
        })

    # ── Console output ──────────────────────────────────────────────────────
    found     = [r for r in results if r["found"]]
    not_found = [r for r in results if not r["found"]]

    print("=" * 72)
    print(f"FOUND ({len(found)})")
    print("=" * 72)
    for r in found:
        best = r["candidates"][0]
        alt  = f" (+{len(r['candidates'])-1} more)" if len(r["candidates"]) > 1 else ""
        print(f"  {r['developerName']:<35} → @{best['userName']} (ownerId={best['ownerId']}){alt}")
        if len(r["candidates"]) > 1:
            for c in r["candidates"][1:]:
                print(f"    alt: @{c['userName']} (ownerId={c['ownerId']})")

    print()
    print("=" * 72)
    print(f"NOT FOUND ({len(not_found)})")
    print("=" * 72)
    for r in not_found:
        print(f"  {r['developerName']}")

    # ── CSV artifact ─────────────────────────────────────────────────────────
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["developerName", "resources", "found",
                         "synapseOwnerId", "synapseUserName", "alternateMatches"])
        for r in results:
            if r["candidates"]:
                best = r["candidates"][0]
                alts = "; ".join(
                    f"@{c['userName']}({c['ownerId']})" for c in r["candidates"][1:]
                )
                writer.writerow([r["developerName"], r["resources"], True,
                                  best["ownerId"], best["userName"], alts])
            else:
                writer.writerow([r["developerName"], r["resources"], False, "", "", ""])

    print(f"\nReport written to {OUTPUT_CSV}")

    # ── GitHub Actions step summary ───────────────────────────────────────────
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as s:
            s.write("## Investigator Synapse ID Check\n\n")
            s.write(f"**Rows missing investigatorSynapseId:** {len(missing)}  \n")
            s.write(f"**Unique names searched:** {len(unique_names)}  \n")
            s.write(f"**Profiles found:** {len(found)} | **Not found:** {len(not_found)}\n\n")

            if found:
                s.write("### Found\n\n")
                s.write("| Developer Name | Resources | Synapse Username | ownerId | Alternates |\n")
                s.write("|---|---|---|---|---|\n")
                for r in found:
                    best = r["candidates"][0]
                    alts = ", ".join(
                        f"`@{c['userName']}`" for c in r["candidates"][1:]
                    )
                    s.write(f"| {r['developerName']} | {r['resources']} "
                            f"| `@{best['userName']}` | {best['ownerId']} | {alts} |\n")

            if not_found:
                s.write("\n### Not Found\n\n")
                s.write("| Developer Name | Resources |\n")
                s.write("|---|---|\n")
                for r in not_found:
                    s.write(f"| {r['developerName']} | {r['resources']} |\n")


if __name__ == "__main__":
    main()
