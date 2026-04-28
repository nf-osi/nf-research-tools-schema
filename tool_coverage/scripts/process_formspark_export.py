#!/usr/bin/env python3
"""
Process a Formspark JSON export and write per-tool JSON files to submissions/.

Usage:
    python process_formspark_export.py <formspark_export.json> [--dry-run]
                                       [--submissions-dir submissions]

Each submission becomes a JSON file in submissions/{tool_type}/{id}_{name}.json
using the same format as mined tools. Reviewer moves accepted files to submissions/accepted/
before merging the PR. Merging triggers upsert-tools.yml which compiles
submissions/accepted/**/*.json → ACCEPTED_*.csv → Synapse.

Submitter contact info (userInfo) and vendor/acquisition details are printed
but stripped from the output JSON so they are never committed to the repo.
Descriptions and synonyms must be manually added to ACCEPTED_resources.csv.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SUBMISSIONS_DIR_DEFAULT = Path("submissions")

_TYPE_SUBDIRS = {
    "cell_line":               "cell_lines",
    "antibody":                "antibodies",
    "animal_model":            "animal_models",
    "genetic_reagent":         "genetic_reagents",
    "patient_derived_model":   "patient_derived_models",
    "computational_tool":      "computational_tools",
    "organoid_protocol": "organoid_protocols",
    "clinical_assessment_tool":"clinical_assessment_tools",
    "observation":             "observations",
}

# Fields to strip from the output JSON (private / not stored in registry)
_STRIP_KEYS = {"userInfo", "firstandlastName", "email", "institution", "isDeveloper",
               "developerName", "developerAffiliation"}

# Fields to print separately (need manual handling) but not store
_PRINT_ONLY_KEYS = {"vendor", "catalogNumber", "catalogURL", "additionalDetails"}


def _get(d: dict, *keys, default=""):
    for key in keys:
        if "." in key:
            parts = key.split(".", 1)
            parent = d.get(parts[0])
            if isinstance(parent, dict):
                val = parent.get(parts[1], "")
                if val not in ("", None):
                    return val
        val = d.get(key, "")
        if val not in ("", None):
            return val
    return default


def _detect_tool_type(s: dict) -> str | None:
    checks = [
        ("cell_line",              ["basicInfo.cellLineName", "cellLineName", "cellLineGeneticDisorder"]),
        ("antibody",               ["basicInfo.antibodyName", "antibodyName", "targetAntigen"]),
        ("animal_model",           ["basicInfo.animalModelName", "animalModelName", "animalModelDisease"]),
        ("genetic_reagent",        ["insertName", "vectorType", "vectorBackbone"]),
        ("patient_derived_model",  ["basicInfo.modelName", "modelName", "basicInfo.modelSystemType"]),
        ("computational_tool",     ["basicInfo.softwareName", "softwareName", "softwareType"]),
        ("organoid_protocol",["basicInfo.modelType", "modelType", "derivationSource"]),
        ("clinical_assessment_tool",["basicInfo.assessmentName", "assessmentName", "assessmentType"]),
        ("observation",            ["observationsSection", "resourceType", "observationType"]),
    ]
    for ttype, fields in checks:
        if any(_get(s, f) for f in fields):
            return ttype
    return None


def _resource_name(s: dict, ttype: str) -> str:
    name_fields = {
        "cell_line":               ["basicInfo.cellLineName", "cellLineName"],
        "antibody":                ["basicInfo.antibodyName", "antibodyName"],
        "animal_model":            ["basicInfo.animalModelName", "animalModelName"],
        "genetic_reagent":         ["insertName"],
        "patient_derived_model":   ["basicInfo.modelName", "modelName"],
        "computational_tool":      ["basicInfo.softwareName", "softwareName"],
        "organoid_protocol": ["basicInfo.modelName", "modelName"],
        "clinical_assessment_tool":["basicInfo.assessmentName", "assessmentName"],
        "observation":             ["observationsSection.observations.0.resourceName", "resourceName"],
    }
    for field in name_fields.get(ttype, []):
        val = _get(s, field)
        if val:
            return val
    return "unnamed"


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", str(name))[:80].strip("_") or "unnamed"


def _strip_private(data: dict) -> dict:
    """Recursively remove private fields from submission data."""
    if not isinstance(data, dict):
        return data
    return {
        k: _strip_private(v)
        for k, v in data.items()
        if k not in _STRIP_KEYS
    }


def _extract_vendor_info(s: dict) -> dict | None:
    acquisition = _get(s, "itemAcquisition")
    if acquisition == "Purchase from Vendor":
        return {k: _get(s, k) for k in ("vendor", "catalogNumber", "catalogURL") if _get(s, k)}
    if acquisition == "Other":
        return {"additionalDetails": _get(s, "additionalDetails")}
    return None


def process_export(export_path: Path, submissions_dir: Path, dry_run: bool) -> None:
    with open(export_path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        submissions = data.get("submissions", data.get("data", [data]))
    else:
        submissions = data

    print(f"\nLoaded {len(submissions)} submission(s) from {export_path.name}\n")
    print("=" * 60)

    written = []
    skipped = []

    for i, submission in enumerate(submissions, 1):
        sid = submission.get("id", submission.get("_id", f"sub{i:03d}"))

        # Print submitter info (never written to file)
        ui = submission.get("userInfo", {})
        name = ui.get("firstandlastName", "")
        email = ui.get("email", "")
        institution = ui.get("institution", "")
        is_dev = ui.get("isDeveloper", "")
        print(f"\nSubmission {i}  (id: {sid})")
        if name or email:
            print(f"  Submitter: {name} <{email}> — {institution}")
            print(f"  Is developer: {is_dev}")

        ttype = _detect_tool_type(submission)
        if ttype is None:
            print("  ⚠️  Could not detect tool type — skipping")
            skipped.append(sid)
            continue

        resource_name = _resource_name(submission, ttype)
        subdir = _TYPE_SUBDIRS[ttype]

        # Print fields needing manual handling
        description = _get(submission, "basicInfo.description", "description")
        synonyms = _get(submission, "basicInfo.synonyms", "synonyms")
        if description:
            print(f"  Description (→ ACCEPTED_resources.csv manually): {description}")
        if synonyms:
            print(f"  Synonyms (→ ACCEPTED_resources.csv manually): {synonyms}")

        vendor = _extract_vendor_info(submission)
        if vendor:
            print(f"  Acquisition info (→ ACCEPTED_vendor*.csv manually):")
            for k, v in vendor.items():
                if v:
                    print(f"    {k}: {v}")

        # Build output JSON: strip private fields, add metadata
        out_data = _strip_private(submission)
        out_data["toolType"] = ttype
        out_data["_source"] = "formspark"
        out_data.setdefault("_verdict", "include")
        out_data.setdefault("_usageType", "novel")

        # Remove vendor/acquisition keys from output (manual step)
        for k in _PRINT_ONLY_KEYS:
            out_data.pop(k, None)

        filename = f"form_{_sanitize(sid)}_{_sanitize(resource_name)}.json"
        out_path = submissions_dir / subdir / filename

        print(f"  Tool type: {ttype.replace('_', ' ').title()}")
        print(f"  Tool name: {resource_name}")

        if dry_run:
            print(f"  [dry-run] Would write {out_path}")
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2, ensure_ascii=False)
            print(f"  ✅ Written to {out_path.relative_to(submissions_dir.parent)}")

        written.append({"id": sid, "type": ttype, "name": resource_name, "file": str(out_path)})

    print("\n" + "=" * 60)
    print(f"\nSummary: {len(written)} written, {len(skipped)} skipped\n")

    if written:
        print("Next steps:")
        print("  1. Review JSON files in submissions/")
        print("  2. Move accepted files:  git mv submissions/{type}/file.json submissions/accepted/{type}/")
        print("  3. Delete rejected files")
        print("  4. Create a PR — merging triggers upsert-tools.yml")
        print("  5. Manually update ACCEPTED_resources.csv with descriptions/synonyms")
        print("  6. Manually update ACCEPTED_vendor*.csv with vendor info")


def main():
    parser = argparse.ArgumentParser(
        description="Convert a Formspark JSON export to per-tool JSON files in submissions/."
    )
    parser.add_argument("export_file", type=Path, help="Path to Formspark JSON export")
    parser.add_argument(
        "--submissions-dir", type=Path, default=SUBMISSIONS_DIR_DEFAULT,
        help="Output directory for JSON files (default: submissions/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without creating files",
    )
    args = parser.parse_args()

    if not args.export_file.exists():
        print(f"Error: {args.export_file} not found", file=sys.stderr)
        sys.exit(1)

    process_export(args.export_file, args.submissions_dir, args.dry_run)


if __name__ == "__main__":
    main()
