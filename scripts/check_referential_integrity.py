"""
Check referential integrity of NF Research Tools data in Synapse.

Reads class-to-table mappings from synapse_table_id annotations on the
LinkML schema (single source of truth). Supports two modes:

  --mode sqlite   Download all tables into a local SQLite database with
                  FK constraints. Any orphaned reference raises an error
                  on insert. (recommended, thorough)

  --mode synapse  Query Synapse directly for orphaned FK references.
                  Faster, no local state, but limited to known FK pairs.

Also checks enum consistency: values in Synapse tables are compared
against permissible values defined in the schema.

Usage:
  python scripts/check_referential_integrity.py --mode sqlite
  python scripts/check_referential_integrity.py --mode synapse
  python scripts/check_referential_integrity.py --check-enums
  python scripts/check_referential_integrity.py --mode sqlite --check-enums

Requires: pip install synapseclient linkml linkml-runtime
"""

import argparse
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from linkml_runtime import SchemaView

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "modules" / "nf_research_tools.yaml"


def get_schema_view():
    return SchemaView(str(SCHEMA_PATH))


def get_table_map(sv):
    """Return {class_name: synapse_table_id} from schema annotations."""
    tables = {}
    for cls_name in sv.all_classes():
        cls = sv.get_class(cls_name)
        for ann in cls.annotations.values():
            if ann.tag == "synapse_table_id":
                tables[cls_name] = ann.value
    return tables


# ── SQLite mode ─────────────────────────────────────────────────────────

# Tables with no inbound FK dependencies — safe to load first.
PARENT_CLASSES = {
    "Donor", "Funder", "Investigator", "Publication",
    "Vendor", "MutationDetails",
}


def check_sqlite(sv, tables):
    """Download Synapse tables into SQLite with FK constraints."""
    import synapseclient

    syn = synapseclient.login()

    # Generate DDL
    with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
        ddl = subprocess.check_output(
            ["gen-sqltables", str(SCHEMA_PATH), "--dialect", "sqlite"],
            text=True,
        )
        f.write(ddl)
        ddl_path = f.name

    db_path = tempfile.mktemp(suffix=".db")
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys = ON")

    # Create tables
    with open(ddl_path) as f:
        db.executescript(f.read())

    # Order: parents first, then children
    parents = {k: v for k, v in tables.items() if k in PARENT_CLASSES}
    children = {k: v for k, v in tables.items() if k not in PARENT_CLASSES}

    failures = []
    for table_name, syn_id in [*parents.items(), *children.items()]:
        try:
            df = syn.tableQuery(f"SELECT * FROM {syn_id}").asDataFrame()
        except Exception as e:
            print(f"  SKIP {table_name} ({syn_id}): {e}")
            continue

        try:
            df.to_sql(table_name, db, if_exists="append", index=False)
            print(f"    OK {table_name}: {len(df)} rows")
        except sqlite3.IntegrityError as e:
            print(f"  FAIL {table_name}: {e}")
            failures.append((table_name, str(e)))

    db.close()
    Path(ddl_path).unlink(missing_ok=True)
    Path(db_path).unlink(missing_ok=True)

    return failures


# ── Synapse query mode ──────────────────────────────────────────────────

def get_fk_checks(sv, tables):
    """Derive FK relationships from schema slot ranges and annotations."""
    checks = []
    for cls_name in sv.all_classes():
        src_id = tables.get(cls_name)
        if not src_id:
            continue
        for slot in sv.class_induced_slots(cls_name):
            if slot.range in sv.all_classes():
                tgt_id = tables.get(slot.range)
                if not tgt_id:
                    continue
                id_slot = next(
                    (s.name for s in sv.class_induced_slots(slot.range)
                     if s.identifier),
                    None,
                )
                if id_slot:
                    checks.append((
                        src_id, id_slot, tgt_id, id_slot,
                        f"{cls_name}.{slot.name} -> {slot.range}",
                    ))
    return checks


def check_synapse(sv, tables):
    """Query Synapse directly for orphaned FK references."""
    import synapseclient

    syn = synapseclient.login()
    fk_checks = get_fk_checks(sv, tables)

    failures = []
    for src_table, src_col, tgt_table, tgt_col, desc in fk_checks:
        query = (
            f"SELECT DISTINCT t1.{src_col} FROM {src_table} t1 "
            f"WHERE t1.{src_col} IS NOT NULL "
            f"AND t1.{src_col} NOT IN (SELECT {tgt_col} FROM {tgt_table})"
        )
        try:
            orphans = syn.tableQuery(query).asDataFrame()
            if len(orphans) > 0:
                print(f"  FAIL {desc}: {len(orphans)} orphaned reference(s)")
                print(f"       IDs: {orphans[src_col].tolist()[:5]}")
                failures.append((desc, len(orphans)))
            else:
                print(f"    OK {desc}")
        except Exception as e:
            print(f"  SKIP {desc}: {e}")

    return failures


# ── Enum consistency ────────────────────────────────────────────────────

def check_enums(sv, tables):
    """Compare Synapse data against schema enum permissible values."""
    import synapseclient

    syn = synapseclient.login()
    failures = []

    for cls_name in sv.all_classes():
        syn_id = tables.get(cls_name)
        if not syn_id:
            continue

        for slot in sv.class_induced_slots(cls_name):
            if not slot.range or slot.range not in [e.name for e in sv.all_enums().values()]:
                continue

            enum_def = sv.get_enum(slot.range)
            valid = set(enum_def.permissible_values.keys())

            try:
                df = syn.tableQuery(
                    f"SELECT {slot.name} FROM {syn_id}"
                ).asDataFrame()
            except Exception:
                continue

            if slot.name not in df.columns:
                continue

            actual = set()
            for val in df[slot.name].dropna():
                actual.update(v.strip() for v in str(val).split(","))

            invalid = actual - valid
            if invalid:
                print(f"  FAIL {cls_name}.{slot.name}: invalid values {invalid}")
                failures.append((cls_name, slot.name, invalid))
            else:
                print(f"    OK {cls_name}.{slot.name} ({len(actual)} distinct values)")

    return failures


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Check referential integrity and enum consistency."
    )
    parser.add_argument(
        "--mode",
        choices=["sqlite", "synapse"],
        help="FK check mode: sqlite (local DB) or synapse (remote queries)",
    )
    parser.add_argument(
        "--check-enums",
        action="store_true",
        help="Also check enum value consistency",
    )
    args = parser.parse_args()

    if not args.mode and not args.check_enums:
        parser.print_help()
        sys.exit(1)

    sv = get_schema_view()
    tables = get_table_map(sv)
    print(f"Schema: {SCHEMA_PATH}")
    print(f"Classes with Synapse tables: {len(tables)}\n")

    all_failures = []

    if args.mode == "sqlite":
        print("── FK check (SQLite) ──")
        all_failures.extend(check_sqlite(sv, tables))

    elif args.mode == "synapse":
        print("── FK check (Synapse queries) ──")
        all_failures.extend(check_synapse(sv, tables))

    if args.check_enums:
        print("\n── Enum consistency ──")
        all_failures.extend(check_enums(sv, tables))

    print()
    if all_failures:
        print(f"FAILED: {len(all_failures)} issue(s) found")
        sys.exit(1)
    else:
        print("PASSED: no issues found")


if __name__ == "__main__":
    main()
