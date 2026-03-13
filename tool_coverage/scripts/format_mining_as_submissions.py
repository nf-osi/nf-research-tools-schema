#!/usr/bin/env python3
"""
Convert ACCEPTED_*.csv rows and *_observations.yaml files to per-tool JSON files in submissions/.

Run after generate_review_csv.py produces the ACCEPTED_*.csv files and after
run_publication_reviews.py --extract-observations produces *_observations.yaml files.
Output JSON matches the form submission schema so the same compile step
handles both mined tools and Formspark form submissions.

Usage:
    python format_mining_as_submissions.py [--output-dir submissions]
                                           [--csv-dir tool_coverage/outputs]
                                           [--observations-yaml-dir tool_reviews/results]
                                           [--cache-dir tool_reviews/publication_cache]
                                           [--dry-run]
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

try:
    import yaml as _yaml
    def _load_yaml(path):
        return _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
except ImportError:
    import json as _json_yaml
    def _load_yaml(path):
        raise ImportError("PyYAML is required for observation YAML support — pip install pyyaml")

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

# Observation type mapping: mining types → form enum values
_OBS_TYPE_MAP = {
    "Behavioral": "Behavior",
    "Biomarker":  "Molecular",
    "Efficacy":   "Other",
    "Mechanistic":"Cellular",
    "Safety":     "Other",
    "Other":      "Other",
}

# Resource type mapping: CSV snake_case → form enum values
_RESOURCE_TYPE_MAP = {
    "animal_model":             "Animal Model",
    "antibody":                 "Antibody",
    "cell_line":                "Cell Line",
    "genetic_reagent":          "Genetic Reagent",
    "computational_tool":       "Computational Tool",
    "advanced_cellular_model":  "Advanced Cellular Model",
    "patient_derived_model":    "Patient-Derived Model",
    "clinical_assessment_tool": "Clinical Assessment Tool",
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


# ---------------------------------------------------------------------------
# Observation converter: reads *_observations.yaml directly (no CSV intermediate)
# ---------------------------------------------------------------------------

def _load_pub_cache(cache_dir: Path) -> dict:
    """Return {pmid_key: {doi, title}} from publication_cache/*_text.json files."""
    meta = {}
    for cache_file in cache_dir.glob("*_text.json"):
        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            pmid_val = data.get("pmid", "")
            meta[pmid_val] = {"doi": data.get("doi", ""), "title": data.get("title", "")}
        except Exception:
            pass
    return meta


def format_observations_from_yaml(
    yaml_dir: Path, cache_dir: Path, output_dir: Path, dry_run: bool
) -> int:
    """Read *_observations.yaml files and write one JSON per observation to submissions/observations/."""
    obs_files = sorted(yaml_dir.glob("*_observations.yaml"))
    if not obs_files:
        print(f"  observations: no *_observations.yaml files found in {yaml_dir} — skipping")
        return 0

    pub_meta = _load_pub_cache(cache_dir)

    out_subdir = output_dir / "observations"
    if not dry_run:
        out_subdir.mkdir(parents=True, exist_ok=True)

    count = 0
    for obs_file in obs_files:
        m = re.match(r"^(\d+)_observations\.yaml$", obs_file.name)
        if not m:
            continue
        pmid_num = m.group(1)
        pmid_key = f"PMID:{pmid_num}"

        meta  = pub_meta.get(pmid_key, {})
        doi   = meta.get("doi", "")
        title = meta.get("title", "")

        try:
            content = _load_yaml(obs_file)
        except Exception as e:
            print(f"  ⚠️  Could not parse {obs_file.name}: {e}")
            continue

        observations = content.get("observations") or []
        for i, obs in enumerate(observations):
            if not isinstance(obs, dict):
                continue

            resource_name = obs.get("resourceName", "")
            obs_type_raw  = obs.get("observationType", "Other")
            rtype_raw     = obs.get("resourceType", "")

            data = {
                "_source": "mining",
                "_publications": [{
                    "_pmid": pmid_key,
                    "_doi": doi,
                    "_publicationTitle": title,
                }],
                "_confidence": str(obs.get("confidence", "")),
                "_foundIn": obs.get("foundIn", ""),
                "_contextSnippet": obs.get("contextSnippet", ""),
                "resourceType": _RESOURCE_TYPE_MAP.get(rtype_raw, rtype_raw),
                "resourceName": resource_name,
                "observationType": _OBS_TYPE_MAP.get(obs_type_raw, "Other"),
                "details": obs.get("details", ""),
                "referencePublication": doi or pmid_key,
            }

            filename = f"{_sanitize(resource_name)}_{pmid_num}_{i:04d}.json"
            out_path = out_subdir / filename

            if dry_run:
                print(f"  [dry-run] Would write {out_path.relative_to(output_dir.parent)}")
            else:
                with open(out_path, "w", encoding="utf-8") as fout:
                    json.dump(data, fout, indent=2, ensure_ascii=False)
            count += 1

    print(f"  observations: {count} JSON files → submissions/observations/")
    return count


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
        description="Convert ACCEPTED_*.csv and *_observations.yaml files to JSON in submissions/."
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
        "--observations-yaml-dir", type=Path,
        default=Path("tool_reviews/results"),
        help="Directory containing *_observations.yaml files (default: tool_reviews/results)",
    )
    parser.add_argument(
        "--cache-dir", type=Path,
        default=Path("tool_reviews/publication_cache"),
        help="Directory containing *_text.json publication cache files (default: tool_reviews/publication_cache)",
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

    if args.observations_yaml_dir.exists():
        print(f"\nReading observations from {args.observations_yaml_dir}/")
        format_observations_from_yaml(
            args.observations_yaml_dir, args.cache_dir, args.output_dir, args.dry_run
        )
    else:
        print(f"No observations YAML dir found at {args.observations_yaml_dir} — skipping observations")


if __name__ == "__main__":
    main()
