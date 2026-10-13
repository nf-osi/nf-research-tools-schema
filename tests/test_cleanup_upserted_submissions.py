#!/usr/bin/env python3
"""
Tests for cleanup_upserted_submissions.py: a submission JSON is deleted only
when its resource (named the same way the compile step names it) is live in
the resource registry. Runs offline with no Synapse access.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "tool_coverage" / "scripts"


def _load_module(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cleanup = _load_module("cleanup_upserted_submissions")


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_resource_key_matches_compile_naming():
    cell_line = {"toolType": "cell_line", "basicInfo": {"cellLineName": " MCF-7 "}}
    pdm = {"toolType": "patient_derived_model",
           "basicInfo": {"resourceName": "NewModel", "modelType": "Xenograft"}}
    obs = {"resourceName": "MCF-7", "resourceType": "Cell Line", "observationType": "Growth"}
    assert cleanup.resource_key(cell_line) == ("mcf-7", "Cell Line")
    assert cleanup.resource_key(pdm) == ("newmodel (xenograft)", "Patient-Derived Model")
    assert cleanup.resource_key(obs) == ("mcf-7", "Cell Line")


def test_plan_cleanup_deletes_only_live_resources(tmp_path):
    live = _write(tmp_path / "cell_lines" / "Live.json",
                  {"toolType": "cell_line", "basicInfo": {"cellLineName": "LiveLine"}})
    missing = _write(tmp_path / "cell_lines" / "Missing.json",
                     {"toolType": "cell_line", "basicInfo": {"cellLineName": "NotUploaded"}})
    wrong_type = _write(tmp_path / "antibodies" / "Wrong.json",
                        {"toolType": "antibody", "basicInfo": {"antibodyName": "LiveLine"}})
    nameless = _write(tmp_path / "cell_lines" / "Nameless.json", {"toolType": "cell_line"})
    gone = tmp_path / "cell_lines" / "Gone.json"

    delete, keep = cleanup.plan_cleanup(
        [live, missing, wrong_type, nameless, gone],
        live_keys={("liveline", "Cell Line")},
    )

    assert delete == [live]
    assert [p for p, _ in keep] == [missing, wrong_type, nameless, gone]
