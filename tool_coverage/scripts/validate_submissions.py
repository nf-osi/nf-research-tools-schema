#!/usr/bin/env python3
"""validate_submissions.py — General correctness checks for submissions/{type}/*.json
against their NF-Tools-Schemas/{type}/submit*.json JSON Schema.

Catches the kind of issues found by hand during review of PRs #171/#172/#183-187:
wrong field names, missing conditionally-expected fields (e.g. a vendor URL when
itemAcquisition is "Purchase from Vendor"), duplicate tool names/synonyms within a
type, dead vendor/source URLs, and submissions with no publication at all.

Checks run per submissions/{type}/*.json file:
  1. JSON Schema conformance (required fields present, enum values valid, and any
     "required" arrays inside allOf/if/then conditional blocks) via `jsonschema`.
     HARD FAILURE.
  2. Fields listed under an allOf/if/then block whose "if" condition matches this
     submission's data, even when the schema itself doesn't mark them "required"
     (e.g. cell-line's "Purchase from Vendor" branch defines vendor/catalogNumber/
     catalogURL but never requires them) — flagged as a WARNING, since the schema
     intends them to be filled in but doesn't enforce it structurally.
  3. Any property whose name contains "url" (case-insensitive), if non-empty, is a
     syntactically valid http(s) URL. With --check-urls, also does a live HEAD/GET
     request and flags non-2xx/3xx responses. WARNING (HARD FAILURE for syntax
     with --strict).
  4. Duplicate cellLineName/animalModelName/etc. (the first required basicInfo
     field) or synonym across all submissions of the same tool type. HARD FAILURE
     — this is a real dedup problem, not just a nice-to-have.
  5. At least one publication is cited (_publications, usagePublicationDOIs, or
     developmentPublicationDOI). WARNING — some legitimate entries (unpublished
     patient-derived resources, internal tools) have none.
  6. Specifically a *development* publication (developmentPublicationDOI, or a
     _publications entry with _usageType == "Development"). WARNING.

Exit code is non-zero only for HARD FAILURES (schema violations, duplicate name/
synonym within a type) unless --strict, which also fails on warnings.

Usage:
  python tool_coverage/scripts/validate_submissions.py
  python tool_coverage/scripts/validate_submissions.py --tool-type cell_line
  python tool_coverage/scripts/validate_submissions.py --check-urls
  python tool_coverage/scripts/validate_submissions.py --strict
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import jsonschema
except ImportError:
    jsonschema = None

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBMISSIONS_DIR = REPO_ROOT / "submissions"
SCHEMA_DIR = REPO_ROOT / "NF-Tools-Schemas"

# submissions/{dir} -> (NF-Tools-Schemas/{dir}, schema filename)
TYPE_MAP = {
    "animal_models": ("animal-model", "submitAnimalModel.json"),
    "antibodies": ("antibody", "submitAntibody.json"),
    "biobanks": ("biobank", "submitBiobank.json"),
    "cell_lines": ("cell-line", "submitCellLine.json"),
    "clinical_assessment_tools": ("clinical-assessment-tool", "submitClinicalAssessmentTool.json"),
    "computational_tools": ("computational-tool", "submitComputationalTool.json"),
    "genetic_reagents": ("genetic-reagent", "submitGeneticReagent.json"),
    "organoid_protocols": ("organoid-protocol", "submitOrganoidProtocol.json"),
    "patient_derived_models": ("patient-derived-model", "submitPatientDerivedModel.json"),
}

_URL_RE = re.compile(r'^https?://', re.IGNORECASE)


def _load_schema(schema_dir: str, schema_file: str) -> dict | None:
    path = SCHEMA_DIR / schema_dir / schema_file
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _name_field(schema: dict) -> str | None:
    """The canonical name field is, in every schema checked so far, the first
    entry in basicInfo's required list (animalModelName, cellLineName, ...)."""
    required = schema.get("properties", {}).get("basicInfo", {}).get("required", [])
    return required[0] if required else None


def _iter_submission_files(tool_type_filter: list[str] | None):
    for subdir, (schema_dir, schema_file) in TYPE_MAP.items():
        if tool_type_filter and subdir not in tool_type_filter:
            continue
        folder = SUBMISSIONS_DIR / subdir
        if not folder.is_dir():
            continue
        schema = _load_schema(schema_dir, schema_file)
        for path in sorted(folder.glob("*.json")):
            yield subdir, schema, path


def _check_schema_conformance(data: dict, schema: dict, path: Path, errors: list, warnings: list):
    if jsonschema is None:
        warnings.append(f"{path}: jsonschema package not installed — skipping schema conformance check")
        return
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for err in validator.iter_errors(data):
        errors.append(f"{path}: schema violation at {'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}")


def _check_conditional_fields(data: dict, schema: dict, path: Path, warnings: list):
    """Flag fields defined (but not formally required) under an allOf/if/then
    block whose condition matches this submission, e.g. vendor/catalogURL when
    itemAcquisition == 'Purchase from Vendor'."""

    def _value_matches(val, sub: dict) -> bool:
        if "const" in sub:
            return val == sub["const"]
        if "enum" in sub:
            return val in sub["enum"]
        if "contains" in sub:
            # e.g. a multi-select array field must contain a matching item
            return isinstance(val, list) and any(_value_matches(item, sub["contains"]) for item in val)
        # Unrecognized condition shape: fail closed (no match) rather than
        # silently treating every submission as matching this branch.
        return False

    def _condition_matches(cond: dict, obj: dict) -> bool:
        for key, sub in cond.get("properties", {}).items():
            if key not in obj:
                return False
            if not _value_matches(obj[key], sub):
                return False
        return True

    def _walk(node: dict, obj: dict, prefix: str):
        for block in node.get("allOf", []):
            if_cond = block.get("if")
            then = block.get("then")
            if not if_cond or not then:
                continue
            if _condition_matches(if_cond, obj):
                for field_name, field_schema in then.get("properties", {}).items():
                    value = obj.get(field_name)
                    if value in (None, "", [], {}):
                        loc = f"{prefix}{field_name}" if prefix else field_name
                        warnings.append(
                            f"{path}: '{loc}' is blank but is expected given the current "
                            f"selection in this conditional branch (schema defines it under "
                            f"an if/then block but doesn't mark it formally required)"
                        )
                # Nested basicInfo-scoped conditionals (e.g. softwareType == "Other")
                if "basicInfo" in then.get("properties", {}) and isinstance(obj.get("basicInfo"), dict):
                    _walk(then, obj, prefix)

    _walk(schema, data, "")
    basic_info_schema = schema.get("properties", {}).get("basicInfo", {})
    if isinstance(data.get("basicInfo"), dict):
        _walk(basic_info_schema, data["basicInfo"], "basicInfo.")


def _find_urls(obj, prefix=""):
    """Yield (path, value) for every non-empty string value under a key containing 'url'."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            loc = f"{prefix}.{k}" if prefix else k
            if "url" in k.lower() and isinstance(v, str) and v:
                yield loc, v
            else:
                yield from _find_urls(v, loc)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _find_urls(v, f"{prefix}[{i}]")


def _check_urls(data: dict, path: Path, do_live_check: bool, errors: list, warnings: list):
    for loc, url in _find_urls(data):
        if not _URL_RE.match(url):
            errors.append(f"{path}: '{loc}' = {url!r} doesn't look like a valid http(s) URL")
            continue
        if not do_live_check:
            continue
        try:
            req = Request(url, method="HEAD", headers={"User-Agent": "nf-research-tools-schema-validator/1.0"})
            with urlopen(req, timeout=10) as resp:
                if not (200 <= resp.status < 400):
                    warnings.append(f"{path}: '{loc}' = {url!r} returned HTTP {resp.status}")
        except HTTPError as e:
            warnings.append(f"{path}: '{loc}' = {url!r} returned HTTP {e.code}")
        except URLError as e:
            warnings.append(f"{path}: '{loc}' = {url!r} failed to resolve: {e.reason}")


def _check_publications(data: dict, path: Path, warnings: list):
    pubs = data.get("_publications") or []
    usage_dois = data.get("usagePublicationDOIs") or []
    dev_doi_raw = data.get("developmentPublicationDOI")
    # Defensive: schema says this should be a string, but malformed submissions
    # (e.g. a list) shouldn't crash this check — _check_schema_conformance
    # reports the actual type violation separately.
    dev_doi = dev_doi_raw.strip() if isinstance(dev_doi_raw, str) else bool(dev_doi_raw)

    if not pubs and not usage_dois and not dev_doi:
        warnings.append(f"{path}: no publication cited at all (_publications, usagePublicationDOIs, developmentPublicationDOI all empty)")
        return

    has_dev_pub = bool(dev_doi) or any((p.get("_usageType") or "") == "Development" for p in pubs)
    if not has_dev_pub:
        warnings.append(f"{path}: no development publication (developmentPublicationDOI empty and no _publications entry has _usageType == 'Development')")


def _collect_names(subdir: str, schema: dict, path: Path, data: dict, registry: dict, errors: list):
    name_field = _name_field(schema) if schema else None
    basic_info = data.get("basicInfo", {})
    candidates = []
    if name_field and basic_info.get(name_field):
        candidates.append(basic_info[name_field])
    synonyms = basic_info.get("synonyms", "")
    if isinstance(synonyms, str) and synonyms:
        candidates.extend(s.strip() for s in re.split(r"[;,]", synonyms) if s.strip())

    for candidate in candidates:
        key = (subdir, candidate.strip().lower())
        if key in registry and registry[key] != path:
            errors.append(
                f"{path}: name/synonym {candidate!r} collides with {registry[key]} within tool type '{subdir}'"
            )
        else:
            registry.setdefault(key, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tool-type", dest="tool_types", action="append", default=[],
                        choices=list(TYPE_MAP.keys()), help="Restrict to one submissions/ subfolder (repeatable)")
    parser.add_argument("--check-urls", action="store_true", help="Also make live HTTP requests to validate URLs resolve")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings too, not just hard failures")
    parser.add_argument(
        "--only-files", metavar="PATH", nargs="+", default=None,
        help="Still scan the whole submissions/ tree (needed for accurate duplicate-name "
             "detection), but only report/fail on findings for these specific file paths. "
             "For CI: pass the files changed in a PR, so pre-existing issues elsewhere in "
             "the tree don't block unrelated PRs.",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    name_registry: dict = {}
    total = 0
    only_files = {str(Path(f).resolve()) for f in args.only_files} if args.only_files else None

    for subdir, schema, path in _iter_submission_files(args.tool_types or None):
        total += 1
        # Always scan every file (duplicate-name detection needs the full registry
        # built regardless of --only-files), but route findings to a per-file bucket
        # so they can be dropped afterward if this file wasn't asked for.
        file_errors: list[str] = []
        file_warnings: list[str] = []
        include = only_files is None or str(path.resolve()) in only_files

        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            file_errors.append(f"{path}: invalid JSON — {e}")
            if include:
                errors.extend(file_errors)
            continue

        if schema:
            _check_schema_conformance(data, schema, path, file_errors, file_warnings)
            _check_conditional_fields(data, schema, path, file_warnings)
            _collect_names(subdir, schema, path, data, name_registry, file_errors)
        else:
            file_warnings.append(f"{path}: no schema found for type '{subdir}' — skipping schema checks")

        _check_urls(data, path, args.check_urls, file_errors, file_warnings)
        _check_publications(data, path, file_warnings)

        if include:
            errors.extend(file_errors)
            warnings.extend(file_warnings)

    print(f"Checked {total} submission file(s).\n")
    if warnings:
        print(f"--- {len(warnings)} warning(s) ---")
        for w in warnings:
            print(f"  ⚠️  {w}")
        print()
    if errors:
        print(f"--- {len(errors)} error(s) ---")
        for e in errors:
            print(f"  ❌ {e}")
        print()

    if errors:
        print("FAILED")
        return 1
    if warnings and args.strict:
        print("FAILED (--strict)")
        return 1
    print("OK" + (" (with warnings)" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
