#!/usr/bin/env python3
"""
Compile submissions/{type}/*.json into ACCEPTED_*.csv files for Synapse upsert.

Run by upsert-tools.yml after JSON files have been moved from submissions/{type}/ to
submissions/{type}/. New rows are appended to existing ACCEPTED_*.csv files,
deduplicating by _resourceName so re-running is safe.

Usage:
    python compile_accepted_submissions.py [--accepted-dir submissions]
                                           [--csv-dir tool_coverage/outputs]
                                           [--dry-run]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# Re-use the same column definitions and field mappers as process_formspark_export.py
# so form submissions and mined tools produce identical CSV rows.

CSV_DIR_DEFAULT = Path("tool_coverage/outputs")
ACCEPTED_DIR_DEFAULT = Path("submissions")

# ---------------------------------------------------------------------------
# Column definitions (must match ACCEPTED_*.csv headers exactly)
# ---------------------------------------------------------------------------

COLUMNS = {
    "cell_lines": [
        "cellLineId", "organ", "tissue", "cellLineManifestation",
        "cellLineGeneticDisorder", "cellLineCategory", "donorId", "originYear",
        "strProfile", "resistance", "contaminatedMisidentified",
        "populationDoublingTime", "cultureMedia",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType", "_toolName",
    ],
    "antibodies": [
        "antibodyId", "targetAntigen", "hostOrganism", "clonality", "cloneId",
        "uniprotId", "reactiveSpecies", "conjugate",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType",
    ],
    "animal_models": [
        "animalModelId", "strainNomenclature", "backgroundStrain",
        "backgroundSubstrain", "animalModelGeneticDisorder",
        "animalModelOfManifestation", "transplantationType", "animalState",
        "generation", "donorId", "transplantationDonorId",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType",
    ],
    "genetic_reagents": [
        "geneticReagentId", "insertName", "vectorType", "vectorBackbone",
        "promoter", "insertSpecies", "insertEntrezId", "selectableMarker",
        "copyNumber", "gRNAshRNASequence", "bacterialResistance", "hazardous",
        "nTerminalTag", "cTerminalTag", "totalSize", "backboneSize", "insertSize",
        "growthStrain", "growthTemp", "cloningMethod", "5primer", "3primer",
        "5primeCloningSite", "3primeCloningSite", "5primeSiteDestroyed",
        "3primeSiteDestroyed",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType",
    ],
    "patient_derived_models": [
        "patientDerivedModelId", "modelSystemType", "patientDiagnosis",
        "hostStrain", "tumorType", "engraftmentSite", "passageNumber",
        "establishmentRate", "molecularCharacterization", "clinicalData",
        "humanizationMethod", "immuneSystemComponents", "validationMethods",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType", "_toolName",
    ],
    "computational_tools": [
        "computationalToolId", "softwareName", "softwareType", "softwareVersion",
        "programmingLanguage", "sourceRepository", "documentation", "licenseType",
        "containerized", "dependencies", "systemRequirements", "lastUpdate",
        "maintainer", "analyticalPlatformSupport", "rrid", "developerName",
        "developerAffiliation", "itemAcquisition",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType",
    ],
    "advanced_cellular_models": [
        "advancedCellularModelId", "modelType", "derivationSource", "cellTypes",
        "organoidType", "matrixType", "cultureSystem", "cultureMedia", "maturationTime",
        "characterizationMethods", "passageNumber", "cryopreservationProtocol",
        "qualityControlMetrics",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType", "_toolName",
    ],
    "clinical_assessment_tools": [
        "clinicalAssessmentToolId", "assessmentName", "assessmentType",
        "targetPopulation", "diseaseSpecific", "numberOfItems", "scoringMethod",
        "validatedLanguages", "psychometricProperties", "administrationTime",
        "availabilityStatus", "licensingRequirements", "digitalVersion",
        "_resourceName", "_pmid", "_doi", "_publicationTitle", "_year",
        "_context", "_confidence", "_verdict", "_usageType",
    ],
    "observations": [
        "observationId", "resourceType", "resourceName", "observationType",
        "details", "observationTypeOntologyId", "observationPhase",
        "observationTime", "observationTimeUnits", "reliabilityRating",
        "easeOfUseRating", "observationLink",
        "_pmid", "_doi", "_publicationTitle", "_year", "_source",
    ],
}

CSV_FILES = {
    "cell_lines":               "ACCEPTED_cell_lines.csv",
    "antibodies":               "ACCEPTED_antibodies.csv",
    "animal_models":            "ACCEPTED_animal_models.csv",
    "genetic_reagents":         "ACCEPTED_genetic_reagents.csv",
    "patient_derived_models":   "ACCEPTED_patient_derived_models.csv",
    "computational_tools":      "ACCEPTED_computational_tools.csv",
    "advanced_cellular_models": "ACCEPTED_advanced_cellular_models.csv",
    "clinical_assessment_tools":"ACCEPTED_clinical_assessment_tools.csv",
    "observations":             "ACCEPTED_observations.csv",
}

# ---------------------------------------------------------------------------
# Value maps
# ---------------------------------------------------------------------------

_DISEASE_MAP = {
    "Neurofibromatosis type 1": "Neurofibromatosis Type 1",
    "Neurofibromatosis type 2": "Neurofibromatosis Type 2",
    "Schwannomatosis": "Schwannomatosis",
    "No known disease": "None",
}
_INSERT_SPECIES_MAP = {
    "Human": "Homo sapiens",
    "Mouse": "Mus musculus",
    "Rat": "Rattus norvegicus",
}
_CONJUGATE_MAP = {
    "Yes": "Conjugated",
    "Non-conjugated": "Nonconjugated",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(d: dict, *keys, default=""):
    """Nested dict lookup with flat fallback."""
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


def _fmt_bool_obj(obj) -> str:
    if isinstance(obj, dict):
        return ", ".join(k for k, v in obj.items() if v is True)
    return str(obj) if obj else ""


def _fmt_list(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val if v)
    return str(val) if val else ""


def _flatten_publications(d: dict) -> dict:
    """Flatten the first (or Development) publication's fields to top level.

    Mining-pipeline JSONs store publication info in a ``_publications`` list;
    Formspark submissions use flat top-level ``_pmid`` / ``_doi`` / etc. fields.
    This normalises both formats so builder functions work unchanged.
    """
    pubs = d.get("_publications")
    if not isinstance(pubs, list) or not pubs:
        return d

    # Prefer the Development publication; fall back to first entry
    pub = next(
        (p for p in pubs if p.get("_usageType", "").lower() == "development"),
        pubs[0],
    )

    out = dict(d)
    for key in ("_pmid", "_doi", "_publicationTitle", "_year", "_context", "_usageType"):
        if pub.get(key) and not out.get(key):
            out[key] = pub[key]
    return out


def _tool_type_from_json(data: dict) -> str | None:
    """Determine tool type from JSON contents."""
    ttype = data.get("toolType", "")
    if ttype:
        return ttype.replace(" ", "_").lower()

    # Fallback: detect from distinguishing fields
    checks = [
        ("cell_line",              ["basicInfo.cellLineName", "cellLineGeneticDisorder"]),
        ("antibody",               ["basicInfo.antibodyName", "targetAntigen"]),
        ("animal_model",           ["basicInfo.animalModelName", "animalModelGeneticDisorder"]),
        ("genetic_reagent",        ["insertName", "vectorType"]),
        ("patient_derived_model",  ["basicInfo.resourceName", "basicInfo.modelSystemType"]),
        ("computational_tool",     ["basicInfo.softwareName", "softwareType"]),
        ("advanced_cellular_model",["basicInfo.resourceName", "basicInfo.modelType", "basicInfo.derivationSource"]),
        ("clinical_assessment_tool",["basicInfo.assessmentName", "basicInfo.assessmentType"]),
        ("observation",            ["resourceType", "observationType"]),
    ]
    for t, fields in checks:
        if any(_get(data, f) for f in fields):
            return t
    return None


# ---------------------------------------------------------------------------
# Per-type row builders: form JSON → ACCEPTED_*.csv row dict
# ---------------------------------------------------------------------------

def _build_cell_line(d: dict) -> dict:
    tissue = _get(d, "tissue")
    return {
        "cellLineId": "",
        "organ": _get(d, "organ"),
        "tissue": tissue,
        "cellLineManifestation": _get(d, "cellLineManifestation"),
        "cellLineGeneticDisorder": _get(d, "cellLineGeneticDisorder"),
        "cellLineCategory": _get(d, "category", "cellLineCategory"),
        "donorId": "",
        "originYear": _get(d, "originYear"),
        "strProfile": _get(d, "strProfile"),
        "resistance": _get(d, "resistance"),
        "contaminatedMisidentified": _get(d, "contaminatedMisidentified"),
        "populationDoublingTime": _get(d, "populationDoublingTime"),
        "cultureMedia": _get(d, "cultureMedia"),
        "_resourceName": _get(d, "basicInfo.cellLineName", "cellLineName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
        "_toolName": _get(d, "basicInfo.cellLineName", "cellLineName"),
    }


def _build_antibody(d: dict) -> dict:
    reactive = _get(d, "basicInfo.reactiveSpecies", "reactiveSpecies")
    conj_raw = _get(d, "conjugate")
    return {
        "antibodyId": "",
        "targetAntigen": _get(d, "targetAntigen"),
        "hostOrganism": _get(d, "basicInfo.hostOrganism", "hostOrganism"),
        "clonality": _get(d, "clonality"),
        "cloneId": _get(d, "cloneId"),
        "uniprotId": _get(d, "uniprotId"),
        "reactiveSpecies": _fmt_bool_obj(reactive),
        "conjugate": _CONJUGATE_MAP.get(conj_raw, conj_raw),
        "_resourceName": _get(d, "basicInfo.antibodyName", "antibodyName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
    }


def _build_animal_model(d: dict) -> dict:
    disease_raw = _get(d, "animalModelGeneticDisorder")
    return {
        "animalModelId": "",
        "strainNomenclature": _get(d, "strainNomenclature"),
        "backgroundStrain": _get(d, "backgroundStrain"),
        "backgroundSubstrain": _get(d, "backgroundSubstrain"),
        "animalModelGeneticDisorder": _DISEASE_MAP.get(disease_raw, disease_raw),
        "animalModelOfManifestation": _get(d, "animalModelOfManifestation"),
        "transplantationType": _get(d, "transplantationType"),
        "animalState": _get(d, "animalState"),
        "generation": _get(d, "generation"),
        "donorId": "",
        "transplantationDonorId": "",
        "_resourceName": _get(d, "basicInfo.animalModelName", "animalModelName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
    }


def _build_genetic_reagent(d: dict) -> dict:
    species_raw = _get(d, "insertSpecies")
    return {
        "geneticReagentId": "",
        "insertName": _get(d, "insertName"),
        "vectorType": _get(d, "vectorType"),
        "vectorBackbone": _get(d, "vectorBackbone"),
        "promoter": _get(d, "promoter"),
        "insertSpecies": _INSERT_SPECIES_MAP.get(species_raw, species_raw),
        "insertEntrezId": _get(d, "insertEntrezId"),
        "selectableMarker": _fmt_bool_obj(_get(d, "selectableMarker")),
        "copyNumber": _get(d, "copyNumber"),
        "gRNAshRNASequence": _get(d, "gRNAshRNASequence"),
        "bacterialResistance": _fmt_bool_obj(_get(d, "bacterialResistance")),
        "hazardous": _get(d, "hazardous"),
        "nTerminalTag": _get(d, "nTerminalTag"),
        "cTerminalTag": _get(d, "cTerminalTag"),
        "totalSize": _get(d, "totalSize"),
        "backboneSize": _get(d, "backboneSize"),
        "insertSize": _get(d, "insertSize"),
        "growthStrain": _get(d, "growthStrain"),
        "growthTemp": _get(d, "growthTemp"),
        "cloningMethod": _get(d, "cloningMethod"),
        "5primer": _get(d, "5primer"),
        "3primer": _get(d, "3primer"),
        "5primeCloningSite": _get(d, "5primeCloningSite"),
        "3primeCloningSite": _get(d, "3primeCloningSite"),
        "5primeSiteDestroyed": _get(d, "5primeSiteDestroyed"),
        "3primeSiteDestroyed": _get(d, "3primeSiteDestroyed"),
        "_resourceName": _get(d, "insertName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
    }


def _build_patient_derived_model(d: dict) -> dict:
    bi = d.get("basicInfo", d)
    return {
        "patientDerivedModelId": "",
        "modelSystemType": _get(bi, "modelSystemType"),
        "patientDiagnosis": _get(bi, "patientDiagnosis"),
        "hostStrain": _get(bi, "hostStrain"),
        "tumorType": _get(bi, "tumorType"),
        "engraftmentSite": _get(bi, "engraftmentSite"),
        "passageNumber": _get(bi, "passageNumber"),
        "establishmentRate": _get(bi, "establishmentRate"),
        "molecularCharacterization": _fmt_list(_get(bi, "molecularCharacterization")),
        "clinicalData": _get(bi, "clinicalData"),
        "humanizationMethod": _get(bi, "humanizationMethod"),
        "immuneSystemComponents": _fmt_list(_get(bi, "immuneSystemComponents")),
        "validationMethods": _fmt_list(_get(bi, "validationMethods")),
        "_resourceName": _get(bi, "resourceName") or _get(d, "_resourceName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
        "_toolName": _get(bi, "resourceName") or _get(d, "_resourceName"),
    }


def _build_computational_tool(d: dict) -> dict:
    bi = d.get("basicInfo", d)
    return {
        "computationalToolId": "",
        "softwareName": _get(bi, "softwareName"),
        "softwareType": _get(bi, "softwareType"),
        "softwareVersion": _get(bi, "softwareVersion"),
        "programmingLanguage": _fmt_list(_get(bi, "programmingLanguage")),
        "sourceRepository": _get(bi, "sourceRepository"),
        "documentation": _get(bi, "documentation"),
        "licenseType": _get(bi, "licenseType"),
        "containerized": _get(bi, "containerized"),
        "dependencies": _fmt_list(_get(bi, "dependencies")),
        "systemRequirements": _get(bi, "systemRequirements"),
        "lastUpdate": _get(bi, "lastUpdate"),
        "maintainer": _get(bi, "maintainer"),
        "analyticalPlatformSupport": _fmt_list(_get(bi, "analyticalPlatformSupport")),
        "rrid": _get(bi, "rrid"),
        "developerName": _get(bi, "developerName"),
        "developerAffiliation": _get(bi, "developerAffiliation"),
        "itemAcquisition": _get(d, "itemAcquisition"),
        "_resourceName": _get(bi, "softwareName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
    }


def _build_advanced_cellular_model(d: dict) -> dict:
    bi = d.get("basicInfo", d)
    return {
        "advancedCellularModelId": "",
        "modelType": _get(bi, "modelType"),
        "derivationSource": _get(bi, "derivationSource"),
        "cellTypes": _fmt_list(_get(bi, "cellTypes")),
        "organoidType": _get(bi, "organoidType"),
        "matrixType": _get(bi, "matrixType"),
        "cultureSystem": _get(bi, "cultureSystem"),
        "cultureMedia": _get(bi, "cultureMedia"),
        "maturationTime": _get(bi, "maturationTime"),
        "characterizationMethods": _fmt_list(_get(bi, "characterizationMethods")),
        "passageNumber": _get(bi, "passageNumber"),
        "cryopreservationProtocol": _get(bi, "cryopreservationProtocol"),
        "qualityControlMetrics": _get(bi, "qualityControlMetrics"),
        "_resourceName": _get(bi, "resourceName") or _get(d, "_resourceName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
        "_toolName": _get(bi, "resourceName") or _get(d, "_resourceName"),
    }


def _build_clinical_assessment_tool(d: dict) -> dict:
    bi = d.get("basicInfo", d)
    return {
        "clinicalAssessmentToolId": "",
        "assessmentName": _get(bi, "assessmentName"),
        "assessmentType": _get(bi, "assessmentType"),
        "targetPopulation": _get(bi, "targetPopulation"),
        "diseaseSpecific": _get(bi, "diseaseSpecific"),
        "numberOfItems": _get(bi, "numberOfItems"),
        "scoringMethod": _get(bi, "scoringMethod"),
        "validatedLanguages": _fmt_list(_get(bi, "validatedLanguages")),
        "psychometricProperties": _get(bi, "psychometricProperties"),
        "administrationTime": _get(bi, "administrationTime"),
        "availabilityStatus": _get(bi, "availabilityStatus"),
        "licensingRequirements": _get(bi, "licensingRequirements"),
        "digitalVersion": _get(bi, "digitalVersion"),
        "_resourceName": _get(bi, "assessmentName"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi", "publicationDOI"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_context": _get(d, "_context"),
        "_confidence": _get(d, "_confidence"),
        "_verdict": _get(d, "_verdict", default="include"),
        "_usageType": _get(d, "_usageType", default="novel"),
    }


def _build_observation(d: dict) -> dict:
    obs = d.get("observationsSection", {}).get("observations", [d])[0] if "observationsSection" in d else d
    pub = d.get("publication", {})
    return {
        "observationId": "",
        "resourceType": _get(obs, "resourceType"),
        "resourceName": _get(obs, "resourceName"),
        "observationType": _get(obs, "observationType"),
        "details": _get(obs, "details"),
        "observationTypeOntologyId": _get(obs, "observationTypeOntologyId"),
        "observationPhase": _get(obs, "observationPhase"),
        "observationTime": _get(obs, "observationTime"),
        "observationTimeUnits": _get(obs, "observationTimeUnits"),
        "reliabilityRating": _get(obs, "reliabilityRating"),
        "easeOfUseRating": _get(obs, "easeOfUseRating"),
        "observationLink": _get(obs, "observationLink"),
        "_pmid": _get(d, "_pmid"),
        "_doi": _get(d, "_doi") or _get(pub, "doi"),
        "_publicationTitle": _get(d, "_publicationTitle"),
        "_year": _get(d, "_year"),
        "_source": _get(d, "_source", default="formspark"),
    }


_BUILDERS = {
    "cell_line":               ("cell_lines",               _build_cell_line),
    "antibody":                ("antibodies",               _build_antibody),
    "animal_model":            ("animal_models",            _build_animal_model),
    "genetic_reagent":         ("genetic_reagents",         _build_genetic_reagent),
    "patient_derived_model":   ("patient_derived_models",   _build_patient_derived_model),
    "computational_tool":      ("computational_tools",      _build_computational_tool),
    "advanced_cellular_model": ("advanced_cellular_models", _build_advanced_cellular_model),
    "clinical_assessment_tool":("clinical_assessment_tools",_build_clinical_assessment_tool),
    "observation":             ("observations",             _build_observation),
}


# ---------------------------------------------------------------------------
# CSV append helpers
# ---------------------------------------------------------------------------

def _load_existing_names(csv_path: Path, name_col: str) -> set:
    """Load existing _resourceName values to avoid duplicates."""
    if not csv_path.exists():
        return set()
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            return {r.get(name_col, "") for r in csv.DictReader(f) if r.get(name_col)}
    except Exception:
        return set()


def _append_rows(csv_path: Path, columns: list, rows: list, dry_run: bool) -> int:
    """Append rows to CSV, adding missing columns if needed. Returns count appended."""
    if not rows:
        return 0

    # Determine column order: existing headers + any new columns
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            existing_headers = next(csv.reader(f), [])
    else:
        existing_headers = []

    new_cols = [c for c in columns if c not in existing_headers]
    final_headers = existing_headers + new_cols if existing_headers else columns

    if dry_run:
        for row in rows:
            print(f"    Would append: {row.get('_resourceName', '?')}")
        return len(rows)

    # Add new columns to existing rows if needed
    if new_cols and csv_path.exists():
        all_rows = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                for col in new_cols:
                    r[col] = ""
                all_rows.append(r)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=final_headers)
            w.writeheader()
            w.writerows(all_rows)

    # Write header if new file
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=final_headers, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for row in rows:
            w.writerow({col: row.get(col, "") for col in final_headers})

    return len(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compile_accepted(json_files: list, csv_dir: Path, dry_run: bool) -> None:
    if not json_files:
        print("No JSON files to compile.")
        return

    print(f"Compiling {len(json_files)} JSON file(s)\n")

    # Group files by tool type
    grouped: dict[str, list[dict]] = {}
    skipped = []

    for path in sorted(json_files):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  WARNING: Could not read {path.name}: {e}", file=sys.stderr)
            skipped.append(path.name)
            continue

        data = _flatten_publications(data)
        ttype = _tool_type_from_json(data)
        if ttype is None:
            print(f"  WARNING: Could not detect tool type in {path.name} — skipping")
            skipped.append(path.name)
            continue

        grouped.setdefault(ttype, []).append(data)

    # Process each type
    total_appended = 0
    csv_dir.mkdir(parents=True, exist_ok=True)

    for ttype, items in grouped.items():
        if ttype not in _BUILDERS:
            print(f"  WARNING: No builder for type '{ttype}' — skipping {len(items)} file(s)")
            continue

        csv_key, builder_fn = _BUILDERS[ttype]
        csv_path = csv_dir / CSV_FILES[csv_key]
        columns = COLUMNS[csv_key]

        # Load existing names to deduplicate
        name_col = "_resourceName" if csv_key != "observations" else "resourceName"
        existing = _load_existing_names(csv_path, name_col)

        rows = []
        dupes = []
        for item in items:
            row = builder_fn(item)
            name = row.get(name_col, "")
            if name in existing:
                dupes.append(name)
            else:
                rows.append(row)
                existing.add(name)

        if dry_run:
            print(f"  [dry-run] {ttype}: {len(rows)} new, {len(dupes)} duplicate(s)")
            _append_rows(csv_path, columns, rows, dry_run=True)
        else:
            count = _append_rows(csv_path, columns, rows, dry_run=False)
            status = f"{count} appended"
            if dupes:
                status += f", {len(dupes)} skipped (duplicate)"
            print(f"  {ttype}: {status} → {csv_path.name}")
            total_appended += count

    if not dry_run:
        print(f"\nTotal: {total_appended} new rows appended across {len(grouped)} tool type(s)")
        if skipped:
            print(f"Skipped {len(skipped)} file(s): {skipped}")


def main():
    parser = argparse.ArgumentParser(
        description="Compile submissions/{type}/*.json into ACCEPTED_*.csv files."
    )
    parser.add_argument(
        "--accepted-dir", type=Path, default=ACCEPTED_DIR_DEFAULT,
        help="Root submissions directory to scan for */*.json files, excluding observations/ "
             "(default: submissions/). Ignored when --files-list is provided.",
    )
    parser.add_argument(
        "--files-list", type=Path, default=None,
        help="Text file with one JSON path per line. When provided, only those files are "
             "compiled instead of scanning --accepted-dir. Use to process only changed files.",
    )
    parser.add_argument(
        "--csv-dir", type=Path, default=CSV_DIR_DEFAULT,
        help="Directory for ACCEPTED_*.csv output (default: tool_coverage/outputs/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without modifying files",
    )
    args = parser.parse_args()

    if args.files_list is not None:
        if not args.files_list.exists():
            print(f"files-list not found at {args.files_list} — nothing to compile")
            sys.exit(0)
        lines = args.files_list.read_text(encoding="utf-8").splitlines()
        json_files = [Path(p.strip()) for p in lines if p.strip()]
        missing = [p for p in json_files if not p.exists()]
        if missing:
            print(f"WARNING: {len(missing)} path(s) from --files-list not found on disk:",
                  file=sys.stderr)
            for p in missing:
                print(f"  {p}", file=sys.stderr)
            json_files = [p for p in json_files if p.exists()]
    else:
        if not args.accepted_dir.exists():
            print(f"No submissions directory found at {args.accepted_dir} — nothing to compile")
            sys.exit(0)
        json_files = sorted(
            p for p in args.accepted_dir.glob("*/*.json")
            if "observations" not in p.parts
        )

    compile_accepted(json_files, args.csv_dir, args.dry_run)


if __name__ == "__main__":
    main()
