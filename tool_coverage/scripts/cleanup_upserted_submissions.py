#!/usr/bin/env python3
"""
Delete submission JSONs whose tool is now live in Synapse.

Run by upsert-tools.yml after a push-triggered upsert with no upload
failures. Synapse is the source of truth once a tool is uploaded (curators
edit it there directly), so keeping the JSON on main only lets it drift from
the live record (see nf-research-tools-schema#349). The workflow commits the
deletions through a cleanup PR for review.

A file is deleted only when its resource (name + type, as the compile step
names it) is found in the resource registry (syn51730943). Observation files
are matched on their own resourceName/resourceType. Everything else is kept
and listed in the report with a reason.

Usage:
    python tool_coverage/scripts/cleanup_upserted_submissions.py \\
        --files-list changed_json_files.txt --report cleanup_report.md [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_accepted_submissions as cas  # noqa: E402

RES_TABLE = "syn51730943"


def _str(val) -> str:
    """Coerce None/NaN (blank Synapse cells) to ''."""
    return val.strip() if isinstance(val, str) else ""


def _norm(name) -> str:
    return _str(name).lower()


def resource_key(data: dict) -> tuple[str, str] | None:
    """Return (normalized resourceName, resourceType label) for a submission."""
    ttype = cas._tool_type_from_json(data)
    if ttype == "observation":
        return _norm(data.get("resourceName")), _str(data.get("resourceType"))
    if ttype not in cas._TTYPE_ID_INFO:
        return None
    name = cas._resource_name_from_data(data, ttype)
    if not name:
        return None
    return _norm(name), cas._TTYPE_ID_INFO[ttype][0]


def plan_cleanup(paths: list[Path], live_keys: set) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Split paths into (delete, keep-with-reason)."""
    delete, keep = [], []
    for path in paths:
        if not path.exists():
            keep.append((path, "file not found"))
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            keep.append((path, f"unreadable JSON ({e})"))
            continue
        key = resource_key(data)
        if key is None or not key[0]:
            keep.append((path, "could not determine resource name/type"))
        elif key in live_keys:
            delete.append(path)
        else:
            keep.append((path, f"not found in {RES_TABLE} as {key[1]} '{key[0]}'"))
    return delete, keep


def _fetch_live_keys() -> set:
    import synapseclient

    token = os.getenv("SYNAPSE_AUTH_TOKEN")
    if not token:
        sys.exit("❌ SYNAPSE_AUTH_TOKEN not set")
    syn = synapseclient.Synapse()
    syn.login(authToken=token, silent=True)
    df = syn.tableQuery(
        f"SELECT resourceName, resourceType FROM {RES_TABLE}"
    ).asDataFrame()
    return {(_norm(n), _str(t)) for n, t in zip(df["resourceName"], df["resourceType"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--files-list", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("cleanup_report.md"))
    parser.add_argument("--dry-run", action="store_true", help="Report only; delete nothing")
    parser.add_argument("--retries", type=int, default=5,
                        help="Re-query attempts while new resources are still missing "
                             "(the registry is a materialized view and can lag the upload)")
    parser.add_argument("--retry-wait", type=int, default=60, help="Seconds between attempts")
    args = parser.parse_args()

    paths = [Path(p.strip()) for p in args.files_list.read_text(encoding="utf-8").splitlines() if p.strip()]
    if not paths:
        print("No files to clean up.")
        args.report.write_text("", encoding="utf-8")
        return

    for attempt in range(1, args.retries + 1):
        delete, keep = plan_cleanup(paths, _fetch_live_keys())
        if not keep or attempt == args.retries:
            break
        print(f"  {len(keep)} file(s) not yet resolvable — retrying in {args.retry_wait}s "
              f"(attempt {attempt}/{args.retries})")
        time.sleep(args.retry_wait)

    for path in delete:
        print(f"  🗑  {path}")
        if not args.dry_run:
            path.unlink()
    for path, reason in keep:
        print(f"  ⏸  kept {path}: {reason}")

    lines = [
        "Removes submission JSONs uploaded by "
        f"[upsert run {os.getenv('GITHUB_RUN_ID', 'local')}]"
        f"({os.getenv('GITHUB_SERVER_URL', '')}/{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}). "
        "Each one's resource was found in the Synapse resource registry, which is now the "
        "source of truth; make further edits in Synapse. Merging this PR uploads nothing "
        "(the upsert only compiles added/modified files).",
        "",
        f"### Deleted ({len(delete)})",
        *[f"- `{p}`" for p in delete],
    ]
    if keep:
        lines += ["", f"### Kept for manual follow-up ({len(keep)})",
                  *[f"- `{p}`: {reason}" for p, reason in keep]]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    gh_out = os.getenv("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"deleted_count={0 if args.dry_run else len(delete)}\n")
    print(f"\n{'[dry-run] would delete' if args.dry_run else 'Deleted'} {len(delete)}, kept {len(keep)}")


if __name__ == "__main__":
    main()
