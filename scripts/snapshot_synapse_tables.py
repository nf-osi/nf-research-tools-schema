#!/usr/bin/env python3
"""
Create versioned Synapse snapshots (and a JSON rollback manifest) for a set
of tables/views before a staged schema change.

Formalizes the ad hoc snapshot-then-record-a-fallback-plan procedure used
manually in nf-research-tools-schema#261 (see docs/STAGING_PROCEDURE.md for
the full staging workflow this is step 1 of).

A plain `create_snapshot_version()` is sufficient to roll back a *Table*
(pin a FROM clause to that version). It is NOT sufficient to roll back a
MaterializedView's `definingSQL` -- Synapse re-derives `columnIds` from
`definingSQL` on every store, so restoring an MV means re-storing its exact
prior `definingSQL` text, not reverting to a snapshot version. This script
therefore captures each entity's full current state (etag, versionNumber,
columnIds, and definingSQL when present) into the manifest alongside its
new snapshot version number, so any entity type can be restored from it.

Table selection (pick one):
  --table-id syn123 (repeatable)      explicit entity ids
  --from-schema                       every synapse_table_id-annotated
                                       class in modules/nf_research_tools.yaml
  --class-name CellLine (repeatable)  specific schema classes only

Requires: pip install synapseclient linkml-runtime
Requires SYNAPSE_AUTH_TOKEN env var (or a cached synapseclient login).

Usage:
  # See what would be snapshotted, no Synapse access
  python scripts/snapshot_synapse_tables.py --from-schema --comment "x" --dry-run

  # Snapshot every schema-mapped table
  python scripts/snapshot_synapse_tables.py --from-schema \\
      --comment "pre-migration snapshot for #262"

  # Snapshot specific classes only
  python scripts/snapshot_synapse_tables.py \\
      --class-name CellLine --class-name AnimalModel \\
      --comment "pre-migration snapshot for #262"

  # Snapshot arbitrary entity ids (e.g. the union-chain MVs from #261, which
  # aren't schema-mapped classes)
  python scripts/snapshot_synapse_tables.py \\
      --table-id syn77019684 --table-id syn51730943 \\
      --comment "pre-migration snapshot for #262"
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synapse_safety import snapshot_table  # noqa: E402
from check_referential_integrity import get_schema_view, get_table_map  # noqa: E402


def resolve_table_ids(args) -> list[str]:
    """Return the ordered, deduplicated list of entity ids to snapshot,
    per the selection flags in args. Raises SystemExit on bad input."""
    ids = list(dict.fromkeys(args.table_id or []))

    if args.from_schema or args.class_name:
        table_map = get_table_map(get_schema_view())
        if args.class_name:
            missing = sorted(set(args.class_name) - set(table_map))
            if missing:
                raise SystemExit(
                    f"Unknown class name(s) not in schema: {missing} "
                    f"(known classes with a synapse_table_id: {sorted(table_map)})"
                )
            selected = {c: table_map[c] for c in args.class_name}
        else:
            selected = table_map
        for syn_id in selected.values():
            if syn_id not in ids:
                ids.append(syn_id)

    if not ids:
        raise SystemExit(
            "No tables selected -- pass --table-id, --class-name, and/or --from-schema."
        )
    return ids


def capture_entity_state(syn, entity_id: str) -> dict:
    """Read current entity state needed to restore it later: name, type,
    versionNumber, etag, columnIds, and definingSQL (present on
    MaterializedViews/Views only)."""
    entity = syn.get(entity_id, downloadFile=False)
    state = {
        "id": entity_id,
        "name": entity.get("name"),
        "concreteType": entity.get("concreteType"),
        "versionNumber": entity.get("versionNumber"),
        "etag": entity.get("etag"),
        "columnIds": entity.get("columnIds"),
    }
    defining_sql = entity.get("definingSQL")
    if defining_sql:
        state["definingSQL"] = defining_sql
    return state


def snapshot_all(syn, table_ids: list[str], comment: str) -> dict:
    """Snapshot each entity, returning the full rollback manifest dict."""
    manifest = {
        "comment": comment,
        "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "entities": [],
    }
    for table_id in table_ids:
        state = capture_entity_state(syn, table_id)
        state["snapshotVersion"] = snapshot_table(syn, table_id, comment)
        manifest["entities"].append(state)
    return manifest


def format_summary_table(manifest: dict) -> str:
    """Markdown table (name, syn id, version) suitable for pasting into a
    GitHub issue comment, matching the format used in #261."""
    lines = ["| Table | syn | version |", "|---|---|---|"]
    for e in manifest["entities"]:
        lines.append(f"| {e['name'] or e['id']} | {e['id']} | {e['snapshotVersion']} |")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--table-id", action="append",
        help="Explicit Synapse table/view id to snapshot (repeatable)",
    )
    parser.add_argument(
        "--class-name", action="append",
        help="Snapshot only this schema class's table (repeatable)",
    )
    parser.add_argument(
        "--from-schema", action="store_true",
        help="Snapshot every synapse_table_id-annotated class in the LinkML schema",
    )
    parser.add_argument(
        "--comment", required=True,
        help="Snapshot comment, e.g. 'pre-migration snapshot for #262'",
    )
    parser.add_argument(
        "--output", default=None,
        help="Rollback manifest JSON path (default: rollback_record_<today>.json in cwd)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Resolve and print the table list without touching Synapse",
    )
    return parser


def main():
    args = build_arg_parser().parse_args()
    table_ids = resolve_table_ids(args)

    if args.dry_run:
        print(f"Would snapshot {len(table_ids)} table(s):")
        for t in table_ids:
            print(f"  {t}")
        return

    import synapseclient  # deferred so --dry-run needs no Synapse login

    syn = synapseclient.login()
    manifest = snapshot_all(syn, table_ids, args.comment)

    output_path = Path(args.output) if args.output else Path(
        f"rollback_record_{datetime.date.today().isoformat()}.json"
    )
    output_path.write_text(json.dumps(manifest, indent=2))

    print(f"Snapshotted {len(table_ids)} table(s). Rollback manifest: {output_path}\n")
    print(format_summary_table(manifest))


if __name__ == "__main__":
    main()
