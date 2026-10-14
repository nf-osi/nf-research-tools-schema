#!/usr/bin/env python3
"""validate_submissions.py --check-synapse: submissions naming a tool that's
already live (by compiled name or synonym, same type) fail. Offline."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "tool_coverage" / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("validate_submissions", SCRIPTS / "validate_submissions.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

LIVE = {("Cell Line", "mcf-7"): "MCF-7", ("Animal Model", "nrg"): "NRG",
        ("Patient-Derived Model", "jh-2-002 (xenograft)"): "JH-2-002 (Xenograft)"}


def _errors(data):
    errs: list = []
    vs._check_live_duplicates(data, Path("x.json"), LIVE, errs)
    return errs


def test_live_name_fails():
    assert _errors({"toolType": "cell_line", "basicInfo": {"cellLineName": "MCF-7"}})


def test_live_synonym_fails():
    assert _errors({"toolType": "cell_line", "basicInfo": {"cellLineName": "New", "synonyms": "foo; MCF-7"}})


def test_same_name_other_type_passes():
    assert not _errors({"toolType": "cell_line", "basicInfo": {"cellLineName": "NRG"}})


def test_pdm_uses_compiled_name_with_suffix():
    assert _errors({"toolType": "patient_derived_model",
                    "basicInfo": {"resourceName": "JH-2-002", "modelType": "Xenograft"}})


def test_new_tool_passes():
    assert not _errors({"toolType": "cell_line", "basicInfo": {"cellLineName": "Brand New Line"}})
