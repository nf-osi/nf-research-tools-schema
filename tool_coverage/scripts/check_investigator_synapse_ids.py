#!/usr/bin/env python3
"""
Scan submission JSONs for developerName values, search the Synapse People
Search API for each unique name, and report which ones have no matching
Synapse profile.

No authentication required — reads local files and calls a public API.

Outputs:
  - Console table of matches / no-matches
  - tool_coverage/outputs/investigator_synapse_id_report.csv
  - GitHub Actions step summary (GITHUB_STEP_SUMMARY) when running in CI
  - Exit code 1 if any names have no Synapse profile found (for CI gating)
"""
import csv
import glob
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request

SUBMISSIONS_DIR   = pathlib.Path("submissions")
OUTPUT_CSV        = pathlib.Path("tool_coverage/outputs/investigator_synapse_id_report.csv")
PEOPLE_SEARCH_API = "https://www.synapse.org/repo/v1/userGroupHeaders"


# ---------------------------------------------------------------------------
# Synapse People Search
# ---------------------------------------------------------------------------

def _search_synapse_users(prefix: str, limit: int = 20) -> list[dict]:
    params = urllib.parse.urlencode({"prefix": prefix, "filter": "USER", "limit": limit})
    url = f"{PEOPLE_SEARCH_API}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("children", [])
    except Exception:
        return []


def _name_score(candidate: dict, first: str, last: str) -> int:
    c_first = (candidate.get("firstName") or "").lower().strip()
    c_last  = (candidate.get("lastName")  or "").lower().strip()
    score = 0
    if last  and c_last  == last.lower():  score += 2
    if first and c_first == first.lower(): score += 1
    if first and c_first.startswith(first.lower()[0]): score += 1
    return score


def find_synapse_profiles(full_name: str) -> list[dict]:
    """Search by last name (fallback: first name). Returns scored candidates."""
    parts = full_name.strip().split()
    if not parts:
        return []
    last  = parts[-1]
    first = parts[0] if len(parts) > 1 else ""

    candidates = _search_synapse_users(last)
    if not candidates and first:
        candidates = _search_synapse_users(first)

    scored = [
        {
            "ownerId":   c.get("ownerId", ""),
            "userName":  c.get("userName", ""),
            "firstName": c.get("firstName", ""),
            "lastName":  c.get("lastName", ""),
            "score":     _name_score(c, first, last),
        }
        for c in candidates
        if _name_score(c, first, last) >= 2
    ]
    scored.sort(key=lambda x: -x["score"])
    return scored


# ---------------------------------------------------------------------------
# Submission scanning
# ---------------------------------------------------------------------------

def split_names(raw: str) -> list[str]:
    return [n.strip() for n in raw.split(";") if n.strip()]


def collect_developer_names() -> dict[str, list[str]]:
    """
    Scan all submission JSONs for developerName fields.
    Returns {name: [resourceName, ...]} for each unique individual name.
    """
    name_to_resources: dict[str, list[str]] = {}
    pattern = str(SUBMISSIONS_DIR / "**" / "*.json")
    for fpath in sorted(glob.glob(pattern, recursive=True)):
        # Skip observation JSONs — they don't have developerName
        if "observations" in fpath:
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue

        raw = (d.get("developerName") or "").strip()
        if not raw:
            continue
        resource = (d.get("resourceName") or pathlib.Path(fpath).stem).strip()
        for name in split_names(raw):
            name_to_resources.setdefault(name, [])
            if resource not in name_to_resources[name]:
                name_to_resources[name].append(resource)

    return name_to_resources


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def write_csv(results: list[dict]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
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


def write_step_summary(results: list[dict], summary_path: str) -> None:
    found     = [r for r in results if r["found"]]
    not_found = [r for r in results if not r["found"]]
    with open(summary_path, "a", encoding="utf-8") as s:
        s.write("## Investigator Synapse ID Check\n\n")
        s.write(f"**Names searched:** {len(results)}  \n")
        s.write(f"**Profiles found:** {len(found)} | **Not found:** {len(not_found)}\n\n")

        if found:
            s.write("### ✅ Synapse profiles found\n\n")
            s.write("| Developer Name | Resources | Username | ownerId | Alternates |\n")
            s.write("|---|---|---|---|---|\n")
            for r in found:
                best = r["candidates"][0]
                alts = ", ".join(f"`@{c['userName']}`" for c in r["candidates"][1:])
                s.write(f"| {r['developerName']} | {r['resources']} "
                        f"| `@{best['userName']}` | {best['ownerId']} | {alts} |\n")

        if not_found:
            s.write("\n### ❌ No Synapse profile found\n\n")
            s.write("| Developer Name | Resources |\n")
            s.write("|---|---|\n")
            for r in not_found:
                s.write(f"| {r['developerName']} | {r['resources']} |\n")


def write_issue_body(results: list[dict]) -> str:
    """Return markdown body for the GitHub issue."""
    not_found = [r for r in results if not r["found"]]
    found     = [r for r in results if r["found"]]
    lines = [
        "Investigators in submission JSONs with `developerName` set but no matching "
        "Synapse profile found via People Search. "
        "Update `investigatorSynapseId` in syn26486833 once the correct profile is confirmed.\n",
    ]
    lines.append("## No Synapse profile found\n")
    lines.append("| Developer Name | Resources |")
    lines.append("|---|---|")
    for r in not_found:
        lines.append(f"| {r['developerName']} | {r['resources']} |")

    if found:
        lines.append("\n## Candidates found (verify before updating)\n")
        lines.append("| Developer Name | Resources | Username | ownerId | Alternates |")
        lines.append("|---|---|---|---|---|")
        for r in found:
            best = r["candidates"][0]
            alts = ", ".join(f"@{c['userName']}({c['ownerId']})" for c in r["candidates"][1:])
            lines.append(
                f"| {r['developerName']} | {r['resources']} "
                f"| @{best['userName']} | {best['ownerId']} | {alts} |"
            )

    lines.append(
        "\n---\n_Auto-generated by [check-investigator-synapse-ids]"
        "(.github/workflows/check-investigator-synapse-ids.yml)_"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not SUBMISSIONS_DIR.exists():
        print(f"Error: {SUBMISSIONS_DIR} not found — run from repo root", file=sys.stderr)
        return 1

    name_to_resources = collect_developer_names()
    print(f"Unique developer names found in submission JSONs: {len(name_to_resources)}")

    results = []
    for name, resources in sorted(name_to_resources.items()):
        time.sleep(0.15)
        candidates = find_synapse_profiles(name)
        results.append({
            "developerName": name,
            "resources":     "; ".join(resources),
            "found":         bool(candidates),
            "candidates":    candidates,
        })

    found     = [r for r in results if r["found"]]
    not_found = [r for r in results if not r["found"]]

    # Console output
    print(f"\n{'─'*72}")
    print(f"FOUND ({len(found)})")
    print(f"{'─'*72}")
    for r in found:
        best = r["candidates"][0]
        alt  = f" (+{len(r['candidates'])-1} more)" if len(r["candidates"]) > 1 else ""
        print(f"  {r['developerName']:<35} → @{best['userName']} ({best['ownerId']}){alt}")

    print(f"\n{'─'*72}")
    print(f"NOT FOUND ({len(not_found)})")
    print(f"{'─'*72}")
    for r in not_found:
        print(f"  {r['developerName']:<35}   resources: {r['resources']}")

    write_csv(results)
    print(f"\nReport written to {OUTPUT_CSV}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        write_step_summary(results, summary_path)

    # Write issue body to a file so the workflow can use it with `gh issue create`
    issue_body_path = pathlib.Path("investigator_issue_body.md")
    if not_found:
        issue_body_path.write_text(write_issue_body(results), encoding="utf-8")
        print(f"Issue body written to {issue_body_path}")

    return 1 if not_found else 0


if __name__ == "__main__":
    sys.exit(main())
