#!/usr/bin/env python3
"""
Register the generated tool JSON Schemas with the Synapse schema registry.

Version scheme (mirrors nf-metadata-dictionary):
    <MAJOR>.<MINOR>  taken from the ``version:`` field of the source LinkML
                     schema (modules/nf_research_tools.yaml)
    <PATCH>          supplied via --patch (CI passes ${{ github.run_number }})
So a run produces e.g. ``2.0.57``. An explicit --version overrides all of this.

Each schema is registered under ``organization`` / ``schema_name`` from
scripts/tool_schema_config.yaml using the synapseclient JSONSchema model (same
call as CURATOR_store_json_schema.py). The server derives ``$id`` from
organization + name + version, so the ``$id`` in the file body is dropped
before storing.

Auth: set SYNAPSE_AUTH_TOKEN, or have a ~/.synapseConfig.

Usage:
    python scripts/register_tool_schemas.py --patch 57
    python scripts/register_tool_schemas.py --version 2.1.0 --only CellLine
    python scripts/register_tool_schemas.py --patch 57 --rebind   # also rebind
    python scripts/register_tool_schemas.py --patch 0 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import yaml
from synapseclient import Synapse
from synapseclient.models import JSONSchema

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "scripts" / "tool_schema_config.yaml"
RECORD_SETS_PATH = REPO_ROOT / "scripts" / "record_sets.json"


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def schema_base_version(source_schema: Path) -> tuple[int, int]:
    """Read MAJOR.MINOR from the LinkML schema's version field."""
    with source_schema.open() as f:
        data = yaml.safe_load(f)
    version = str(data.get("version", "0.0.0"))
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return major, minor


def resolve_version(config: dict, args) -> str:
    if args.version:
        return args.version
    major, minor = schema_base_version(REPO_ROOT / config["source_schema"])
    return f"{major}.{minor}.{args.patch}"


def login() -> Synapse:
    syn = Synapse()
    token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if token:
        syn.login(authToken=token)
    else:
        syn.login()
    return syn


async def register_one(syn: Synapse, org: str, name: str, body: dict, version: str):
    # $id is derived server-side from organization + name + version.
    body = dict(body)
    body.pop("$id", None)
    schema = JSONSchema(organization_name=org, name=name)
    await schema.store_async(schema_body=body, version=version, synapse_client=syn)
    return f"{org}-{name}-{version}"


def rebind(syn: Synapse, record_set_id: str, schema_uri: str) -> None:
    from synapseclient.models import RecordSet

    record_set = RecordSet(id=record_set_id).get(synapse_client=syn)
    record_set.bind_schema(
        json_schema_uri=schema_uri,
        enable_derived_annotations=False,
        synapse_client=syn,
    )


def load_record_sets() -> dict:
    if RECORD_SETS_PATH.exists():
        return json.loads(RECORD_SETS_PATH.read_text(encoding="utf-8"))
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", type=int, default=0,
                        help="PATCH number (CI passes github.run_number).")
    parser.add_argument("--version", help="Explicit full version (overrides --patch).")
    parser.add_argument("--only", nargs="+", metavar="CLASS",
                        help="Only register these tool classes.")
    parser.add_argument("--rebind", action="store_true",
                        help="After registering, rebind the new version to the "
                             "record set listed in scripts/record_sets.json.")
    parser.add_argument("--log-file", help="Write a markdown registration log here.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve versions and validate files; do not call Synapse.")
    args = parser.parse_args()

    config = load_config()
    output_dir = REPO_ROOT / config["output_dir"]
    organization = config["organization"]
    version = resolve_version(config, args)

    tools = config["tools"]
    if args.only:
        wanted = set(args.only)
        tools = [t for t in tools if t["class"] in wanted]
        missing = wanted - {t["class"] for t in tools}
        if missing:
            parser.error(f"Unknown tool class(es): {', '.join(sorted(missing))}")
    record_sets = load_record_sets()

    print(f"Organization: {organization}")
    print(f"Version:      {version}")
    print(f"Schemas:      {len(tools)}\n")

    log_lines = [
        "# Tool schema registration log",
        "",
        f"- Organization: `{organization}`",
        f"- Version: `{version}`",
        "",
        "| Tool | Schema URI | Status |",
        "| --- | --- | --- |",
    ]

    syn = None if args.dry_run else login()
    successful, failed = [], {}

    for tool in tools:
        cls = tool["class"]
        name = tool["schema_name"]
        path = output_dir / f"{cls}.json"
        if not path.exists():
            failed[cls] = f"missing {path.name} (run generate_tool_schemas.py)"
            print(f"  FAILED {cls}: {failed[cls]}")
            log_lines.append(f"| {cls} | `{organization}-{name}` | missing file |")
            continue

        body = json.loads(path.read_text(encoding="utf-8"))
        uri = f"{organization}-{name}-{version}"

        if args.dry_run:
            print(f"  [dry-run] would register {uri}")
            log_lines.append(f"| {cls} | `{uri}` | dry-run |")
            successful.append(cls)
            continue

        try:
            asyncio.run(register_one(syn, organization, name, body, version))
            print(f"  registered {uri}")
            status = "registered"
            if args.rebind and cls in record_sets:
                rs_id = record_sets[cls]["record_set_id"]
                rebind(syn, rs_id, uri)
                print(f"    rebound {rs_id} -> {uri}")
                status = f"registered + rebound {rs_id}"
            successful.append(cls)
            log_lines.append(f"| {cls} | `{uri}` | {status} |")
        except Exception as error:
            msg = str(error)
            failed[cls] = msg
            print(f"  FAILED {cls}: {msg}")
            log_lines.append(f"| {cls} | `{uri}` | FAILED: {msg} |")

    print(f"\nSuccessful: {len(successful)}  Failed: {len(failed)}")

    if args.log_file:
        Path(args.log_file).write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        print(f"Log written to {args.log_file}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
