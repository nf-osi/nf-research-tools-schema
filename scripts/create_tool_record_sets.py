#!/usr/bin/env python3
"""
Bootstrap: create one Synapse Record Set per tool type in the tools project.

This is a ONE-TIME setup (run manually via the create-tool-record-sets
workflow), NOT part of the per-merge pipeline. Record Sets are persistent
Synapse objects; once created, the register-tool-schemas pipeline re-binds new
schema versions to them via `register_tool_schemas.py --rebind`.

What it does:
  1. Finds or creates a shared folder (config `record_set_folder_name`) under
     the tools project (config `project_id`, syn26338068).
  2. For each tool type, creates a record-based metadata task + Record Set and
     binds the registered schema (same call as CURATOR_create_record_task.py).
  3. Records each new Record Set id in scripts/record_sets.json so the pipeline
     can rebind later.

Already-created tool types are skipped unless --replace is given.

Auth: set SYNAPSE_AUTH_TOKEN, or have a ~/.synapseConfig.
Requires a synapseclient with curator extensions (install from the develop
branch, as the create-tool-record-sets workflow does).

Usage:
    python scripts/create_tool_record_sets.py --version 2.0.57
    python scripts/create_tool_record_sets.py --version 2.0.57 --only CellLine
    python scripts/create_tool_record_sets.py --version 2.0.57 --replace
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml
from synapseclient import Synapse
from synapseclient.models import Folder
try:
    from synapseclient.extensions.curator import create_record_based_metadata_task
except ImportError as e:
    raise ImportError(
        "create_tool_record_sets.py requires synapseclient curator extensions (synapseclient.extensions.curator). Install a synapseclient build that includes these extensions."
    ) from e

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "scripts" / "tool_schema_config.yaml"
RECORD_SETS_PATH = REPO_ROOT / "scripts" / "record_sets.json"


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def login() -> Synapse:
    syn = Synapse()
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if token:
        syn.login(authToken=token)
    else:
        syn.login()
    return syn


def find_or_create_folder(syn: Synapse, name: str, parent_id: str) -> str:
    """Return the id of the child folder `name` under parent_id, creating it if absent."""
    for child in syn.getChildren(parent_id, includeTypes=["folder"]):
        if child["name"] == name:
            print(f"Using existing folder '{name}': {child['id']}")
            return child["id"]
    folder = Folder(name=name, parent_id=parent_id).store(synapse_client=syn)
    print(f"Created folder '{name}': {folder.id}")
    return folder.id


def load_record_sets() -> dict:
    if RECORD_SETS_PATH.exists():
        return json.loads(RECORD_SETS_PATH.read_text(encoding="utf-8"))
    return {}


def save_record_sets(data: dict) -> None:
    RECORD_SETS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version",
                        help="Registered schema version to bind (e.g. 2.0.57). "
                             "If omitted, binds the schema name without a version "
                             "(Synapse resolves the latest).")
    parser.add_argument("--only", nargs="+", metavar="CLASS",
                        help="Only create record sets for these tool classes.")
    parser.add_argument("--replace", action="store_true",
                        help="Recreate record sets already listed in record_sets.json.")
    args = parser.parse_args()

    config = load_config()
    organization = config["organization"]
    project_id = config["project_id"]
    folder_name = config["record_set_folder_name"]

    tools = config["tools"]
    if args.only:
        wanted = set(args.only)
        tools = [t for t in tools if t["class"] in wanted]
        missing = wanted - {t["class"] for t in tools}
        if missing:
            parser.error(f"Unknown tool class(es): {', '.join(sorted(missing))}")
    syn = login()
    folder_id = find_or_create_folder(syn, folder_name, project_id)
    record_sets = load_record_sets()

    created, skipped, failed = [], [], {}

    for tool in tools:
        cls = tool["class"]
        name = tool["schema_name"]

        if cls in record_sets and not args.replace:
            print(f"SKIP {cls}: record set already exists "
                  f"({record_sets[cls]['record_set_id']}). Use --replace to recreate.")
            skipped.append(cls)
            continue

        schema_uri = f"{organization}-{name}"
        if args.version:
            schema_uri = f"{schema_uri}-{args.version}"

        try:
            record_set, curation_task, _ = create_record_based_metadata_task(
                synapse_client=syn,
                folder_id=folder_id,
                record_set_name=f"{tool['title']} Records",
                record_set_description=f"Record set for NF research tools of type {cls}.",
                curation_task_name=cls,
                upsert_keys=tool["upsert_keys"],
                instructions=f"Add or curate {tool['title']} records.",
                schema_uri=schema_uri,
                bind_schema_to_record_set=True,
                authorization_mode="SOURCE_BENEFACTOR",
            )
            record_sets[cls] = {
                "record_set_id": record_set.id,
                "curation_task_id": getattr(curation_task, "task_id", None),
                "folder_id": folder_id,
                "schema": schema_uri,
            }
            print(f"Created record set for {cls}: {record_set.id}")
            created.append(cls)
        except Exception as error:
            failed[cls] = str(error)
            print(f"FAILED {cls}: {error}")

    save_record_sets(record_sets)
    print(f"\nCreated: {len(created)}  Skipped: {len(skipped)}  Failed: {len(failed)}")
    print(f"Record set map written to {RECORD_SETS_PATH.relative_to(REPO_ROOT)}")
    print("Commit scripts/record_sets.json so the pipeline can rebind new versions.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
