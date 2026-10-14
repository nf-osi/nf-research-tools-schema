#!/usr/bin/env python3
"""
Offline integration tests for the tool-schema pipeline.

These run on every PR with NO Synapse access and NO secrets. They catch the
common ways registration or record-set creation would fail *before* the live
pipeline (register-tool-schemas.yml) ever touches Synapse:

  * committed schemas are stale (someone edited a LinkML module but did not
    regenerate) -- would register the wrong shape;
  * a generated schema is not valid draft-07 -- rejected by the registry;
  * a schema is not self-contained (dangling ``$ref`` / leftover ``$defs``) --
    the registry and Record Sets require a flat, standalone schema;
  * a tool's ``upsert_keys`` (used to build the Record Set) are not real
    properties of its schema -- record-set creation would bind bad keys;
  * ``register_tool_schemas.py --dry-run`` cannot resolve versions / find files.

What they deliberately do NOT cover: a real round-trip against Synapse (network
+ CREATE permission + persistent objects). That is the opt-in live smoke test,
kept out of PR CI. See docs/SCHEMA_PIPELINE.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "scripts" / "tool_schema_config.yaml"


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()
TOOLS = CONFIG["tools"]
OUTPUT_DIR = REPO_ROOT / CONFIG["output_dir"]
ORGANIZATION = CONFIG["organization"]

# Give each parametrized case a readable id like "CellLine".
TOOL_IDS = [t["class"] for t in TOOLS]


def schema_path(tool: dict) -> Path:
    return OUTPUT_DIR / f"{tool['class']}.json"


def load_schema(tool: dict) -> dict:
    return json.loads(schema_path(tool).read_text(encoding="utf-8"))


def iter_nodes(node):
    """Yield every dict/list node in a JSON structure (depth-first)."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from iter_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_nodes(item)


# --------------------------------------------------------------------------- #
# Config-level sanity
# --------------------------------------------------------------------------- #

def test_config_has_tools():
    assert TOOLS, "tool_schema_config.yaml lists no tools."


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_schema_file_exists(tool):
    path = schema_path(tool)
    assert path.exists(), (
        f"{path.relative_to(REPO_ROOT)} is missing. "
        f"Run: python scripts/generate_tool_schemas.py"
    )


# --------------------------------------------------------------------------- #
# Each committed schema must be registrable
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_schema_is_valid_draft07(tool):
    """The registry targets draft-07; an invalid meta-schema is rejected."""
    schema = load_schema(tool)
    assert schema.get("$schema") == CONFIG["json_schema_dialect"], (
        f"{tool['class']}: unexpected $schema dialect {schema.get('$schema')!r}"
    )
    # Raises jsonschema.SchemaError if the schema itself is malformed.
    Draft7Validator.check_schema(schema)


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_schema_is_self_contained(tool):
    """
    Synapse's registry + Record Sets require a flat, standalone schema: no
    internal ``$ref`` and no ``$defs`` block (the generator inlines both).
    """
    schema = load_schema(tool)
    assert "$defs" not in schema, f"{tool['class']}: leftover $defs block."
    dangling = [
        n["$ref"]
        for n in iter_nodes(schema)
        if isinstance(n, dict) and "$ref" in n
    ]
    assert not dangling, f"{tool['class']}: dangling $ref(s): {dangling}"


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_types_have_no_null_unions(tool):
    """Nullable unions like ['string', 'null'] must be collapsed to a scalar."""
    schema = load_schema(tool)
    offenders = [
        n["type"]
        for n in iter_nodes(schema)
        if isinstance(n, dict)
        and isinstance(n.get("type"), list)
        and "null" in n["type"]
    ]
    assert not offenders, f"{tool['class']}: uncollapsed nullable type(s): {offenders}"


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_id_matches_config(tool):
    """$id must encode organization + schema_name (register appends version)."""
    schema = load_schema(tool)
    expected_suffix = f"{ORGANIZATION}-{tool['schema_name']}"
    assert schema.get("$id", "").endswith(expected_suffix), (
        f"{tool['class']}: $id {schema.get('$id')!r} does not end with "
        f"{expected_suffix!r}"
    )


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_upsert_keys_are_properties(tool):
    """
    Record-set creation binds ``upsert_keys`` as the record identity. Every key
    must be a real property of the schema, or the Record Set is misconfigured.
    """
    schema = load_schema(tool)
    properties = set(schema.get("properties", {}))
    missing = [k for k in tool["upsert_keys"] if k not in properties]
    assert not missing, (
        f"{tool['class']}: upsert_keys not present as properties: {missing}"
    )


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_required_are_properties(tool):
    """Anything in ``required`` must be defined in ``properties``."""
    schema = load_schema(tool)
    properties = set(schema.get("properties", {}))
    missing = [k for k in schema.get("required", []) if k not in properties]
    assert not missing, (
        f"{tool['class']}: required entries missing from properties: {missing}"
    )


# --------------------------------------------------------------------------- #
# Whole-pipeline smoke checks (subprocess, still offline)
# --------------------------------------------------------------------------- #

def test_committed_schemas_up_to_date():
    """
    ``generate --check`` regenerates in-memory and diffs against the committed
    files. Fails if a LinkML change was not accompanied by a regenerate.
    """
    result = subprocess.run(
        [sys.executable, "scripts/generate_tool_schemas.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Committed schemas are stale. Run: python scripts/generate_tool_schemas.py\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_dry_run_registration_resolves():
    """
    ``register --dry-run`` resolves the version and confirms every schema file
    exists, exercising the register path without calling Synapse.
    """
    result = subprocess.run(
        [sys.executable, "scripts/register_tool_schemas.py", "--dry-run", "--patch", "0"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"register --dry-run failed:\n{result.stdout}\n{result.stderr}"
    )
    # Every configured class should have resolved with no failures.
    assert "Failed: 0" in result.stdout, (
        f"register --dry-run reported failures:\n{result.stdout}"
    )

    # Dry-run output prints schema URIs (<org>-<schema_name>-<version>), not tool classes.
    version_line = next(
        (line for line in result.stdout.splitlines() if line.strip().startswith("Version:")),
        "",
    )
    version = version_line.split()[-1] if version_line else ""
    assert version, f"Could not parse resolved version from output:\n{result.stdout}"

    for tool in TOOLS:
        expected_uri = f"{ORGANIZATION}-{tool['schema_name']}-{version}"
        assert expected_uri in result.stdout, (
            f"{expected_uri} absent from dry-run output:\n{result.stdout}"
        )
