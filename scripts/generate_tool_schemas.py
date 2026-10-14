#!/usr/bin/env python3
"""
Generate a flat, self-contained draft-07 JSON Schema for each NF research tool
type from the LinkML modules.

For every tool listed in ``scripts/tool_schema_config.yaml`` this runs
``gen-json-schema -t <Class>`` and post-processes the LinkML output into the
shape Synapse's schema registry and Record Sets expect (see docs/SCHEMA_PIPELINE.md):
  * ``$schema`` rewritten to draft-07
  * ``$id`` set to the registered Synapse URI (no version; the register step
    appends the version)
  * enum ``$ref``s inlined as ``{"type": "string", "enum": [...]}`` so the
    schema is fully self-contained (no ``$defs`` / internal ``$ref``)
  * ``["string", "null"]`` type unions collapsed to the base scalar type

Output is written to the configured ``output_dir`` (one ``<Class>.json`` per
tool). These files are committed so schema changes are reviewable in PRs.

Usage:
    python scripts/generate_tool_schemas.py
    python scripts/generate_tool_schemas.py --only CellLine AnimalModel
    python scripts/generate_tool_schemas.py --check   # fail if output is stale
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

import yaml

REGISTERED_URI_PREFIX = (
    "https://repo-prod.prod.sagebase.org/repo/v1/schema/type/registered"
)

# Repo root is the parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "scripts" / "tool_schema_config.yaml"


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def run_gen_json_schema(source_schema: Path, class_name: str) -> dict:
    """Run LinkML gen-json-schema for one class and return the parsed JSON."""
    result = subprocess.run(
        ["gen-json-schema", str(source_schema), "-t", class_name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gen-json-schema failed for {class_name}:\n{result.stderr}"
        )
    return json.loads(result.stdout)


def collapse_nullable_type(type_value):
    """['string', 'null'] -> 'string'; leave anything ambiguous untouched."""
    if isinstance(type_value, list):
        non_null = [t for t in type_value if t != "null"]
        if len(non_null) == 1:
            return non_null[0]
    return type_value


def inline_node(node, defs, _stack=None):
    """
    Recursively resolve ``#/$defs/*`` references and collapse nullable unions.

    Enum refs become ``{"type": "string", "enum": [...]}`` carrying the
    referencing property's own keywords (e.g. its description). Object refs, if
    any ever appear, are inlined by deep copy with a cycle guard.
    """
    _stack = _stack or ()

    if isinstance(node, list):
        return [inline_node(item, defs, _stack) for item in node]

    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        def_name = ref.split("/")[-1]
        if def_name in _stack:
            # Recursive definition: stop unfolding, keep a permissive object.
            return {"type": "object"}
        target = defs.get(def_name, {})
        siblings = {k: v for k, v in node.items() if k != "$ref"}

        if "enum" in target:
            resolved = {
                "type": target.get("type", "string"),
                "enum": list(target["enum"]),
            }
            # The property's own keywords (description, etc.) win.
            resolved.update(siblings)
            if "type" in resolved:
                resolved["type"] = collapse_nullable_type(resolved["type"])
            return resolved

        # Non-enum ($ref to a class) — inline the whole definition.
        resolved = copy.deepcopy(target)
        resolved = inline_node(resolved, defs, _stack + (def_name,))
        if isinstance(resolved, dict):
            resolved.update(inline_node(siblings, defs, _stack))
        return resolved

    # Plain object: recurse into every value, collapse a nullable "type".
    out = {}
    for key, value in node.items():
        if key == "type":
            out[key] = collapse_nullable_type(value)
        else:
            out[key] = inline_node(value, defs, _stack)
    return out


def build_schema(raw: dict, tool: dict, dialect: str, organization: str) -> dict:
    """Assemble the final flat draft-07 schema for one tool."""
    defs = raw.get("$defs", {})
    schema_uri = f"{REGISTERED_URI_PREFIX}/{organization}-{tool['schema_name']}"

    properties = inline_node(raw.get("properties", {}), defs)

    schema = {
        "$schema": dialect,
        "$id": schema_uri,
        "title": tool["title"],
        "description": raw.get("description", ""),
        "type": "object",
        "properties": properties,
        "required": raw.get("required", []),
        # Synapse's schema registry expects an empty-schema value here (matches
        # the working wes.json); `false` is rejected on registration.
        "additionalProperties": {},
    }
    if not schema["description"]:
        del schema["description"]
    return schema


def generate(only=None, check=False) -> int:
    config = load_config()
    source_schema = REPO_ROOT / config["source_schema"]
    output_dir = REPO_ROOT / config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    dialect = config["json_schema_dialect"]
    organization = config["organization"]

    tools = config["tools"]
    if only:
        wanted = set(only)
        tools = [t for t in tools if t["class"] in wanted]
        missing = wanted - {t["class"] for t in tools}
        if missing:
            print(f"ERROR: unknown tool class(es): {', '.join(sorted(missing))}")
            return 2

    stale = []
    for tool in tools:
        cls = tool["class"]
        raw = run_gen_json_schema(source_schema, cls)
        schema = build_schema(raw, tool, dialect, organization)
        text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"

        out_path = output_dir / f"{cls}.json"
        if check:
            existing = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
            if existing != text:
                stale.append(cls)
                print(f"STALE: {out_path.relative_to(REPO_ROOT)}")
            else:
                print(f"ok:    {out_path.relative_to(REPO_ROOT)}")
        else:
            out_path.write_text(text, encoding="utf-8")
            print(
                f"wrote {out_path.relative_to(REPO_ROOT)} "
                f"({len(schema['properties'])} properties)"
            )

    if check and stale:
        print(
            f"\n{len(stale)} schema(s) out of date. "
            f"Run: python scripts/generate_tool_schemas.py"
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="CLASS",
        help="Only (re)generate these tool classes (e.g. CellLine AnimalModel).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero if committed output is stale.",
    )
    args = parser.parse_args()
    return generate(only=args.only, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
