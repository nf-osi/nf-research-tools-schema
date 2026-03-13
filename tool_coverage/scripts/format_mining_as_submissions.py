#!/usr/bin/env python3
"""
Convert ACCEPTED_*.csv rows to per-tool JSON files in submissions/.

Run after generate_review_csv.py produces the ACCEPTED_*.csv files.
Output JSON matches the form submission schema so the same compile step
handles both mined tools and Formspark form submissions.

Usage:
    python format_mining_as_submissions.py [--output-dir submissions]
                                           [--csv-dir tool_coverage/outputs]
                                           [--dry-run]
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Reverse value maps (Synapse → form enum values)
# ---------------------------------------------------------------------------

_DISEASE_REVERSE = {
    "Neurofibromatosis Type 1": "Neurofibromatosis type 1",
    "Neurofibromatosis Type 2": "Neurofibromatosis type 2",
    "Schwannomatosis": "Schwannomatosis",
    "None": "No known disease",
}

_CONJUGATE_REVERSE = {
    "Conjugated": "Yes",
    "Nonconjugated": "Non-conjugated",
}

_INSERT_SPECIES_REVERSE = {
    "Homo sapiens": "Human",
    "Mus musculus": "Mouse",
    "Rattus norvegicus": "Rat",
}

# Map tool type → (csv_filename, subdir, converter_fn name)
_TYPE_CONFIG = {
    "cell_lines":              ("ACCEPTED_cell_lines.csv",              "cell_lines"),
    "animal_models":           ("ACCEPTED_animal_models.csv",           "animal_models"),
    "antibodies":              ("ACCEPTED_antibodies.csv",              "antibodies"),
    "genetic_reagents":        ("ACCEPTED_genetic_reagents.csv",        "genetic_reagents"),
    "patient_derived_models":  ("ACCEPTED_patient_derived_models.csv",  "patient_derived_models"),
    "computational_tools":     ("ACCEPTED_computational_tools.csv",     "computational_tools"),
    "advanced_cellular_models":("ACCEPTED_advanced_cellular_models.csv","advanced_cellular_models"),
    "clinical_assessment_tools":("ACCEPTED_clinical_assessment_tools.csv","clinical_assessment_tools"),
}


def _sanitize(name: str) -> str:
    """Make a string safe for use as a filename."""
    return re.sub(r"[^\w\-]", "_", name)[:80].strip("_") or "unnamed"


def _meta(row: dict) -> dict:
    """Build _publications array from pipe-separated CSV fields, plus top-level metadata."""
    pmids = [p.strip() for p in row.get("_pmid", "").split(" | ") if p.strip()]
    dois  = [d.strip() for d in row.get("_doi", "").split(" | ") if d.strip()]
    titles= [t.strip() for t in row.get("_publicationTitle", "").split(" | ") if t.strip()]
    years = [y.strip() for y in row.get("_year", "").split(" | ") if y.strip()]
    usage_type = row.get("_usageType", "")
    context    = row.get("_context", "")

    publications = []
    for i, pmid in enumerate(pmids):
        publications.append({
            "_pmid": pmid,
            "_doi": dois[i] if i < len(dois) else "",
            "_publicationTitle": titles[i] if i < len(titles) else "",
            "_year": years[i] if i < len(years) else "",
            "_usageType": usage_type,  # same for all entries (CSV limitation)
            "_context": context if i == 0 else "",
        })

    if not publications and row.get("_pmid", "").strip():
        publications.append({
            "_pmid": row.get("_pmid", ""),
            "_doi": row.get("_doi", ""),
            "_publicationTitle": row.get("_publicationTitle", ""),
            "_year": row.get("_year", ""),
            "_usageType": usage_type,
            "_context": context,
        })

    return {
        "_source": "mining",
        "_publications": publications,
        "_confidence": row.get("_confidence", ""),
        "_verdict": row.get("_verdict", "include"),
    }


def _first_doi(row: dict) -> str:
    """Return first DOI from pipe-separated list (development publication)."""
    dois = [d.strip() for d in row.get("_doi", "").split(" | ") if d.strip()]
    return dois[0] if dois else ""


def _usage_dois(row: dict) -> str:
    """Return remaining DOIs as comma-separated string (usage publications)."""
    dois = [d.strip() for d in row.get("_doi", "").split(" | ") if d.strip()]
    return ", ".join(dois[1:]) if len(dois) > 1 else ""


def _parse_list_field(val: str) -> dict:
    """Convert 'Human, Mouse' → {Human: True, Mouse: True}."""
    if not val:
        return {}
    return {s.strip(): True for s in val.split(",") if s.strip()}


# ---------------------------------------------------------------------------
# Per-type converters: CSV row dict → form-compatible JSON dict
# ---------------------------------------------------------------------------

def _cell_line(row: dict) -> dict:
    return {
        **_meta(row),
        "toolType": "cell_line",
        "userInfo": {},
        "basicInfo": {
            "cellLineName": row.get("_toolName") or row.get("_resourceName", ""),
            "description": "",
            "synonyms": "",
            "species": "",
            "sex": "",
            "age": None,
            "race": "",
        },
        "category": row.get("cellLineCategory", ""),
        "cellLineGeneticDisorder": row.get("cellLineGeneticDisorder", ""),
        "cellLineManifestation": row.get("cellLineManifestation", ""),
        "tissue": row.get("tissue", ""),
        "populationDoublingTime": row.get("populationDoublingTime", "") or None,
        "cultureMedia": row.get("cultureMedia", ""),
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
        "itemAcquisition": "",
    }


def _animal_model(row: dict) -> dict:
    disease_raw = row.get("animalModelGeneticDisorder", "")
    return {
        **_meta(row),
        "toolType": "animal_model",
        "userInfo": {},
        "basicInfo": {
            "animalModelName": row.get("_resourceName", ""),
            "description": "",
            "synonyms": "",
            "species": "",
        },
        "strainNomenclature": row.get("strainNomenclature", ""),
        "backgroundStrain": row.get("backgroundStrain", ""),
        "backgroundSubstrain": row.get("backgroundSubstrain", ""),
        "animalModelDisease": _DISEASE_REVERSE.get(disease_raw, disease_raw),
        "animalModelManifestation": row.get("animalModelOfManifestation", ""),
        "transplantationType": row.get("transplantationType", ""),
        "animalState": row.get("animalState", ""),
        "generation": row.get("generation", ""),
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
        "itemAcquisition": "",
    }


def _antibody(row: dict) -> dict:
    return {
        **_meta(row),
        "toolType": "antibody",
        "userInfo": {},
        "basicInfo": {
            "antibodyName": row.get("_resourceName", ""),
            "description": "",
            "synonyms": "",
            "hostOrganism": row.get("hostOrganism", ""),
            "reactiveSpecies": _parse_list_field(row.get("reactiveSpecies", "")),
        },
        "targetAntigen": row.get("targetAntigen", ""),
        "clonality": row.get("clonality", ""),
        "cloneId": row.get("cloneId", ""),
        "uniprotId": row.get("uniprotId", ""),
        "conjugated": _CONJUGATE_REVERSE.get(row.get("conjugate", ""), ""),
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
        "itemAcquisition": "",
    }


def _genetic_reagent(row: dict) -> dict:
    species_raw = row.get("insertSpecies", "")
    return {
        **_meta(row),
        "toolType": "genetic_reagent",
        "userInfo": {},
        "insertName": row.get("insertName") or row.get("_resourceName", ""),
        "insertEntrezId": row.get("insertEntrezId", ""),
        "gRNAshRNASequence": row.get("gRNAshRNASequence", ""),
        "insertSize": row.get("insertSize", ""),
        "insertSpecies": _INSERT_SPECIES_REVERSE.get(species_raw, species_raw),
        "nTerminalTag": row.get("nTerminalTag", ""),
        "cTerminalTag": row.get("cTerminalTag", ""),
        "cloningMethod": row.get("cloningMethod", ""),
        "5primeCloningSite": row.get("5primeCloningSite", ""),
        "5primeSiteDestroyed": row.get("5primeSiteDestroyed", ""),
        "3primeCloningSite": row.get("3primeCloningSite", ""),
        "3primeSiteDestroyed": row.get("3primeSiteDestroyed", ""),
        "promoter": row.get("promoter", ""),
        "5primer": row.get("5primer", ""),
        "3primer": row.get("3primer", ""),
        "vectorBackbone": row.get("vectorBackbone", ""),
        "vectorType": row.get("vectorType", ""),
        "backboneSize": row.get("backboneSize", ""),
        "totalSize": row.get("totalSize", ""),
        "bacterialResistance": _parse_list_field(row.get("bacterialResistance", "")),
        "selectableMarker": _parse_list_field(row.get("selectableMarker", "")),
        "copyNumber": row.get("copyNumber", ""),
        "growthTemp": row.get("growthTemp", ""),
        "growthStrain": row.get("growthStrain", ""),
        "hazardous": row.get("hazardous", ""),
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
        "itemAcquisition": "",
    }


def _patient_derived_model(row: dict) -> dict:
    mol_raw = row.get("molecularCharacterization", "")
    mol_list = [s.strip() for s in mol_raw.split(",") if s.strip()] if mol_raw else []
    return {
        **_meta(row),
        "toolType": "patient_derived_model",
        "userInfo": {},
        "basicInfo": {
            "modelName": row.get("_toolName") or row.get("_resourceName", ""),
            "description": "",
            "synonyms": "",
            "modelSystemType": row.get("modelSystemType", ""),
            "patientDiagnosis": row.get("patientDiagnosis", ""),
            "hostStrain": row.get("hostStrain", ""),
            "passageNumber": row.get("passageNumber", ""),
            "tumorType": row.get("tumorType", ""),
            "engraftmentSite": row.get("engraftmentSite", ""),
            "establishmentRate": row.get("establishmentRate", ""),
            "molecularCharacterization": mol_list,
            "clinicalData": row.get("clinicalData", ""),
            "humanizationMethod": row.get("humanizationMethod", ""),
            "immuneSystemComponents": [],
            "validationMethods": [],
            "howToAcquire": "",
        },
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
    }


def _computational_tool(row: dict) -> dict:
    return {
        **_meta(row),
        "toolType": "computational_tool",
        "userInfo": {},
        "basicInfo": {
            "softwareName": row.get("_resourceName", ""),
            "description": "",
            "synonyms": "",
            "softwareType": row.get("softwareType", ""),
            "softwareVersion": row.get("softwareVersion", ""),
            "programmingLanguage": row.get("programmingLanguage", ""),
            "sourceRepository": row.get("sourceRepository", ""),
            "documentation": row.get("documentation", ""),
            "licenseType": row.get("licenseType", ""),
            "containerized": row.get("containerized", ""),
            "dependencies": row.get("dependencies", ""),
            "systemRequirements": row.get("systemRequirements", ""),
            "lastUpdate": row.get("lastUpdate", ""),
            "maintainer": row.get("maintainer", ""),
        },
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
    }


def _advanced_cellular_model(row: dict) -> dict:
    char_raw = row.get("characterizationMethods", "")
    cell_raw = row.get("cellTypes", "")
    return {
        **_meta(row),
        "toolType": "advanced_cellular_model",
        "userInfo": {},
        "basicInfo": {
            "modelName": row.get("_toolName") or row.get("_resourceName", ""),
            "description": "",
            "synonyms": "",
            "modelType": row.get("modelType", ""),
            "derivationSource": row.get("derivationSource", ""),
            "cellTypes": [s.strip() for s in cell_raw.split(",") if s.strip()],
            "organoidType": row.get("organoidType", ""),
            "matrixType": row.get("matrixType", ""),
            "cultureSystem": row.get("cultureSystem", ""),
            "maturationTime": row.get("maturationTime", ""),
            "characterizationMethods": [s.strip() for s in char_raw.split(",") if s.strip()],
            "passageNumber": row.get("passageNumber", ""),
            "cryopreservationProtocol": row.get("cryopreservationProtocol", ""),
            "qualityControlMetrics": row.get("qualityControlMetrics", ""),
        },
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
    }


def _clinical_assessment_tool(row: dict) -> dict:
    lang_raw = row.get("validatedLanguages", "")
    return {
        **_meta(row),
        "toolType": "clinical_assessment_tool",
        "userInfo": {},
        "basicInfo": {
            "assessmentName": row.get("_resourceName", ""),
            "description": "",
            "synonyms": "",
            "assessmentType": row.get("assessmentType", ""),
            "targetPopulation": row.get("targetPopulation", ""),
            "diseaseSpecific": row.get("diseaseSpecific", ""),
            "numberOfItems": row.get("numberOfItems", ""),
            "scoringMethod": row.get("scoringMethod", ""),
            "validatedLanguages": [s.strip() for s in lang_raw.split(",") if s.strip()],
            "psychometricProperties": row.get("psychometricProperties", ""),
            "administrationTime": row.get("administrationTime", ""),
            "availabilityStatus": row.get("availabilityStatus", ""),
            "licensingRequirements": row.get("licensingRequirements", ""),
            "digitalVersion": row.get("digitalVersion", ""),
        },
        "developmentPublicationDOI": _first_doi(row),
        "usagePublicationDOIs": _usage_dois(row),
    }


_CONVERTERS = {
    "cell_lines":               _cell_line,
    "animal_models":            _animal_model,
    "antibodies":               _antibody,
    "genetic_reagents":         _genetic_reagent,
    "patient_derived_models":   _patient_derived_model,
    "computational_tools":      _computational_tool,
    "advanced_cellular_models": _advanced_cellular_model,
    "clinical_assessment_tools":_clinical_assessment_tool,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _resource_name(row: dict, ttype: str) -> str:
    """Get canonical resource name for a row."""
    for field in ("_toolName", "_resourceName", "insertName", "softwareName", "assessmentName"):
        val = row.get(field, "")
        if val:
            return val
    return "unnamed"


def format_csv_to_submissions(csv_dir: Path, output_dir: Path, dry_run: bool) -> None:
    total_written = 0

    for ttype, (csv_name, subdir) in _TYPE_CONFIG.items():
        csv_path = csv_dir / csv_name
        if not csv_path.exists():
            continue

        converter = _CONVERTERS[ttype]
        out_subdir = output_dir / subdir
        if not dry_run:
            out_subdir.mkdir(parents=True, exist_ok=True)

        # Deduplicate rows by resource name — keep first occurrence per unique name
        seen = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = _resource_name(row, ttype)
                if name and name not in seen:
                    seen[name] = row

        count = 0
        for name, row in seen.items():
            filename = f"{_sanitize(name)}.json"
            out_path = out_subdir / filename

            if dry_run:
                print(f"  [dry-run] Would write {out_path.relative_to(output_dir.parent)}")
                count += 1
                continue

            data = converter(row)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            count += 1

        print(f"  {ttype}: {count} JSON files → submissions/{subdir}/")
        total_written += count

    print(f"\nTotal: {total_written} submission JSON files written to {output_dir}/")


def main():
    parser = argparse.ArgumentParser(
        description="Convert ACCEPTED_*.csv to per-tool JSON files in submissions/."
    )
    parser.add_argument(
        "--csv-dir", type=Path,
        default=Path("tool_coverage/outputs"),
        help="Directory containing ACCEPTED_*.csv files (default: tool_coverage/outputs)",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("submissions"),
        help="Root output directory for JSON files (default: submissions/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without creating files",
    )
    args = parser.parse_args()

    if not args.csv_dir.exists():
        print(f"Error: CSV directory {args.csv_dir} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Reading ACCEPTED_*.csv from {args.csv_dir}/")
    print(f"Writing JSON to {args.output_dir}/\n")
    format_csv_to_submissions(args.csv_dir, args.output_dir, args.dry_run)


if __name__ == "__main__":
    main()
