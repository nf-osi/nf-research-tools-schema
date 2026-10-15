#!/usr/bin/env python3
"""
Regression test: mined patient-derived-model and organoid-protocol submissions
must keep their tool name through compile.

format_mining_as_submissions.py used to write the name to basicInfo.modelName,
but the submit*.json schemas (and compile_accepted_submissions.py) use
basicInfo.resourceName -- so mined PDMs compiled as " (PDX)" and organoids
with a blank _resourceName.

Runs offline: rows use a non-Development _usageType, so the formatter never
calls PubMed for the corresponding author.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "NF-Tools-Schemas"


def _load_module(name: str):
    path = REPO_ROOT / "tool_coverage" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fmt = _load_module("format_mining_as_submissions")
cas = _load_module("compile_accepted_submissions")

_PUB = {
    "_pmid": "12345678",
    "_doi": "10.1000/example",
    "_publicationTitle": "Example NF paper",
    "_year": "2024",
    "_usageType": "Experimental Usage",
    "_context": "",
    "_confidence": "0.9",
}


def _write_csv(path: Path, row: dict) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _mine_and_compile(tmp_path: Path) -> tuple[Path, Path]:
    mined_dir = tmp_path / "mined"
    sub_dir = tmp_path / "submissions"
    out_dir = tmp_path / "outputs"
    mined_dir.mkdir()
    _write_csv(mined_dir / "ACCEPTED_patient_derived_models.csv", {
        **_PUB, "_toolName": "JH-2-002 PDX", "modelType": "PDX",
        "patientDiagnosis": "MPNST",
    })
    _write_csv(mined_dir / "ACCEPTED_organoid_protocols.csv", {
        **_PUB, "_toolName": "cNF organoid protocol", "modelType": "Organoid",
        "derivationSource": "Patient tumor",
    })
    fmt.format_csv_to_submissions(mined_dir, sub_dir, dry_run=False)
    json_files = sorted(sub_dir.glob("*/*.json"))
    cas.compile_accepted(json_files, out_dir, dry_run=False)
    return sub_dir, out_dir


def test_formatter_writes_schema_name_field(tmp_path):
    """The formatter must write the field the submit*.json schema requires."""
    sub_dir, _ = _mine_and_compile(tmp_path)
    for subdir, schema_path in [
        ("patient_derived_models", "patient-derived-model/submitPatientDerivedModel.json"),
        ("organoid_protocols", "organoid-protocol/submitOrganoidProtocol.json"),
    ]:
        schema = json.loads((SCHEMA_DIR / schema_path).read_text())
        assert "resourceName" in schema["properties"]["basicInfo"]["required"]
        (path,) = sorted((sub_dir / subdir).glob("*.json"))
        bi = json.loads(path.read_text())["basicInfo"]
        assert bi.get("resourceName"), f"{path.name}: basicInfo.resourceName is blank"
        assert "modelName" not in bi


def test_mined_pdm_and_organoid_compile_with_names(tmp_path):
    _, out_dir = _mine_and_compile(tmp_path)

    (pdm,) = _read_csv(out_dir / cas.CSV_FILES["patient_derived_models"])
    assert pdm["_resourceName"] == "JH-2-002 PDX (PDX)"
    assert pdm["_toolName"] == "JH-2-002 PDX (PDX)"

    (org,) = _read_csv(out_dir / cas.CSV_FILES["organoid_protocols"])
    assert org["_resourceName"] == "cNF organoid protocol"
    assert org["_toolName"] == "cNF organoid protocol"


def test_resource_name_from_mined_json(tmp_path):
    """_resource_name_from_data feeds the publication/developer link rows."""
    sub_dir, _ = _mine_and_compile(tmp_path)
    (pdm_path,) = sorted((sub_dir / "patient_derived_models").glob("*.json"))
    (org_path,) = sorted((sub_dir / "organoid_protocols").glob("*.json"))
    pdm = json.loads(pdm_path.read_text())
    org = json.loads(org_path.read_text())
    assert cas._resource_name_from_data(pdm, "patient_derived_model") == "JH-2-002 PDX (PDX)"
    assert cas._resource_name_from_data(org, "organoid_protocol") == "cNF organoid protocol"


pfe = _load_module("process_formspark_export")


def test_formspark_pdm_and_organoid_detection_and_names():
    """Formspark exports follow the submit*.json schemas: basicInfo.resourceName,
    and both forms carry basicInfo.modelType -- so detection must key on each
    form's own required field, not modelType (which sent organoids to PDM)."""
    pdm = {"basicInfo": {"resourceName": "JH-2-002", "modelType": "PDX",
                         "patientDiagnosis": "MPNST", "species": "Human"}}
    org = {"basicInfo": {"resourceName": "cNF organoids", "modelType": "Organoid",
                         "derivationSource": "Patient tumor"}}
    assert pfe._detect_tool_type(pdm) == "patient_derived_model"
    assert pfe._detect_tool_type(org) == "organoid_protocol"
    assert pfe._resource_name(pdm, "patient_derived_model") == "JH-2-002"
    assert pfe._resource_name(org, "organoid_protocol") == "cNF organoids"
