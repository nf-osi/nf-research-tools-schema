#!/usr/bin/env python3
"""
Regression tests for nf-research-tools-schema#349: a push to main that adds
one submission JSON must only produce publication / link / resource rows for
that file, and legacy (pre-#262) patient-derived-model submissions must
compile to the resource names already live in Synapse.

These tests run offline with no Synapse access.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
# Real pre-#262 patient-derived-model submissions, kept as fixtures because
# uploaded submission JSONs are deleted from submissions/ (#352).
PDM_DIR = REPO_ROOT / "tests" / "fixtures" / "legacy_pdm"


def _load_module(name: str):
    path = REPO_ROOT / "tool_coverage" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compile_mod = _load_module("compile_accepted_submissions")


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_submission(path: Path, name: str, pmid: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "_publications": [{
            "_pmid": pmid,
            "_doi": f"10.0000/{pmid}",
            "_publicationTitle": f"Paper {pmid}",
            "_year": "2025",
            "_usageType": "Development",
        }],
        "toolType": "cell_line",
        "resourceType": "Cell Line",
        "basicInfo": {"cellLineName": name, "species": "Human"},
        "cellLineCategory": "Cancer cell line",
    }), encoding="utf-8")
    return path


def test_files_list_scopes_links_and_resources(tmp_path, monkeypatch):
    """Only the compiled file's publications/links/resources are emitted, even
    when cwd has a full submissions/ dir (the old code globbed it)."""
    sub_dir = tmp_path / "submissions"
    changed = _write_submission(sub_dir / "cell_lines" / "Changed.json", "ChangedLine", "111")
    _write_submission(sub_dir / "cell_lines" / "Untouched.json", "UntouchedLine", "222")
    out = tmp_path / "out"
    monkeypatch.chdir(tmp_path)

    compile_mod.compile_accepted([changed], out, dry_run=False)

    pubs = _read_csv(out / "submission_publications.csv")
    devs = _read_csv(out / "submission_dev_links.csv")
    resources = _read_csv(out / "ACCEPTED_resources.csv")
    assert {p["pmid"] for p in pubs} == {"111"}
    assert {d["_toolName"] for d in devs} == {"ChangedLine"}
    assert {r["resourceName"] for r in resources} == {"ChangedLine"}


def test_accepted_dir_mode_still_scans_everything(tmp_path, monkeypatch):
    """--accepted-dir (workflow_dispatch force=true) passes every file."""
    sub_dir = tmp_path / "submissions"
    a = _write_submission(sub_dir / "cell_lines" / "A.json", "LineA", "111")
    b = _write_submission(sub_dir / "cell_lines" / "B.json", "LineB", "222")
    out = tmp_path / "out"
    monkeypatch.chdir(tmp_path)

    compile_mod.compile_accepted([a, b], out, dry_run=False)

    assert {p["pmid"] for p in _read_csv(out / "submission_publications.csv")} == {"111", "222"}


@pytest.mark.parametrize("filename, expected_name, expected_model_type", [
    ("JH-2-002.json", "JH-2-002 (PDX)", "Xenograft"),
    ("NF1_MPNST_PDX4.json", "NF1 MPNST PDX4 (PDX)", "Xenograft"),
    ("NF0001_cNF_organoid.json", "NF0001 (Patient-Derived Organoid)", "Organoid"),
])
def test_legacy_pdm_names_match_live_synapse_labels(filename, expected_name, expected_model_type):
    """Pre-#262 JSONs (modelSystemType/tumorType) must reproduce the labels
    they were uploaded with, and still fill modelType/manifestation."""
    data = json.loads((PDM_DIR / filename).read_text(encoding="utf-8"))
    assert "modelType" not in data["basicInfo"], "fixture is no longer a legacy submission"

    row = compile_mod._build_patient_derived_model(data)
    assert row["_resourceName"] == expected_name
    assert compile_mod._resource_name_from_data(data, "patient_derived_model") == expected_name
    assert row["modelType"] == expected_model_type
    assert row["manifestation"], "tumorType should backfill manifestation"


def test_all_pdm_link_names_match_detail_names():
    """Link rows and detail rows must agree on every PDM's name, otherwise
    links resolve to a resourceId that was never uploaded."""
    for path in sorted(PDM_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        detail_name = compile_mod._build_patient_derived_model(data)["_resourceName"]
        link_name = compile_mod._resource_name_from_data(data, "patient_derived_model")
        assert detail_name == link_name, path.name
        assert detail_name.endswith(")"), f"{path.name}: missing model-type suffix"


def test_current_form_pdm_naming_unchanged():
    data = {"basicInfo": {"resourceName": "NewModel", "modelType": "Xenograft",
                          "manifestation": "Schwannoma"}}
    row = compile_mod._build_patient_derived_model(data)
    assert row["_resourceName"] == "NewModel (Xenograft)"
    assert row["modelType"] == "Xenograft"
