#!/usr/bin/env python3
"""
Tests for lookup_rrids.py: blank rrids in submission JSONs are filled from
(monkeypatched) registry lookups, written where compile_accepted_submissions.py
reads them, and registry failures never fail the run. Runs offline.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "tool_coverage" / "scripts"


def _load_module(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lookup = _load_module("lookup_rrids")
compile_mod = _load_module("compile_accepted_submissions")
_real_lookup_mmrrc = lookup._lookup_mmrrc


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test may reach the network: every registry call is recorded and
    answered from REGISTRY; _get itself raises."""
    calls = []
    registry = {}

    def fake(source):
        def _f(name, *a):
            calls.append((source, name))
            return registry.get((source, name), "")
        return _f

    monkeypatch.setattr(lookup, "_lookup_cellosaurus", fake("cellosaurus"))
    monkeypatch.setattr(lookup, "_lookup_addgene", fake("addgene"))
    monkeypatch.setattr(lookup, "_lookup_imsr", fake("imsr"))
    monkeypatch.setattr(lookup, "_lookup_mmrrc", fake("mmrrc"))
    monkeypatch.setattr(lookup, "_lookup_scicrunch_antibody", fake("scicrunch"))
    monkeypatch.setattr(lookup, "_get", lambda *a, **k: pytest.fail("network call"))
    monkeypatch.setattr(lookup.time, "sleep", lambda s: None)
    return calls, registry


def _write(tmp_path: Path, subdir: str, name: str, data: dict) -> Path:
    p = tmp_path / "submissions" / subdir / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))
    return p


def _cell_line(name, rrid="", context=""):
    return {
        "_source": "mining",
        "_publications": [{"_pmid": "PMID:1", "_context": context}],
        "toolType": "cell_line",
        "basicInfo": {"cellLineName": name, "rrid": rrid} if rrid else {"cellLineName": name},
    }


def test_fills_blank_rrid_into_basic_info(tmp_path, offline):
    calls, registry = offline
    registry[("cellosaurus", "MCF7")] = "rrid:CVCL_0031"
    p = _write(tmp_path, "cell_lines", "MCF7", _cell_line("MCF7"))

    results = lookup.run_lookup([p])

    assert json.loads(p.read_text())["basicInfo"]["rrid"] == "rrid:CVCL_0031"
    assert results[0]["status"] == "filled"
    assert results[0]["source"] == "Cellosaurus"
    assert calls == [("cellosaurus", "MCF7")]


def test_compile_carries_filled_rrid_to_detail_row(tmp_path, offline):
    _, registry = offline
    registry[("cellosaurus", "MCF7")] = "rrid:CVCL_0031"
    p = _write(tmp_path, "cell_lines", "MCF7", _cell_line("MCF7"))
    lookup.run_lookup([p])

    item = json.loads(p.read_text())
    row = compile_mod._build_cell_line(compile_mod._flatten_publications(item))
    compile_mod._apply_core_resource_fields(row, item, "cell_line")
    assert row["rrid"] == "rrid:CVCL_0031"


def test_existing_rrid_is_not_requeried(tmp_path, offline):
    calls, _ = offline
    p = _write(tmp_path, "cell_lines", "MCF7", _cell_line("MCF7", rrid="rrid:CVCL_9999"))
    before = p.read_text()

    results = lookup.run_lookup([p])

    assert calls == []
    assert p.read_text() == before
    assert results[0]["status"] == "already_set"


def test_force_requeries(tmp_path, offline):
    calls, registry = offline
    registry[("cellosaurus", "MCF7")] = "rrid:CVCL_0031"
    p = _write(tmp_path, "cell_lines", "MCF7", _cell_line("MCF7", rrid="rrid:CVCL_9999"))

    lookup.run_lookup([p], force=True)

    assert json.loads(p.read_text())["basicInfo"]["rrid"] == "rrid:CVCL_0031"


def test_not_found_leaves_file_untouched(tmp_path, offline):
    p = _write(tmp_path, "cell_lines", "X", _cell_line("Unknown line"))
    before = p.read_text()
    results = lookup.run_lookup([p])
    assert p.read_text() == before
    assert results[0]["status"] == "not_found"


def test_dry_run_writes_nothing(tmp_path, offline):
    _, registry = offline
    registry[("cellosaurus", "MCF7")] = "rrid:CVCL_0031"
    p = _write(tmp_path, "cell_lines", "MCF7", _cell_line("MCF7"))
    before = p.read_text()
    results = lookup.run_lookup([p], dry_run=True)
    assert p.read_text() == before
    assert results[0]["rrid"] == "rrid:CVCL_0031"


def test_genetic_reagent_without_basic_info_gets_top_level_rrid(tmp_path, offline):
    _, registry = offline
    registry[("addgene", "pLKO.1-NF1")] = "rrid:Addgene_12345"
    p = _write(tmp_path, "genetic_reagents", "pLKO", {
        "toolType": "genetic_reagent", "insertName": "pLKO.1-NF1",
    })
    lookup.run_lookup([p])
    data = json.loads(p.read_text())
    assert data["rrid"] == "rrid:Addgene_12345"
    assert "basicInfo" not in data


def test_animal_model_falls_back_to_mmrrc(tmp_path, offline):
    calls, registry = offline
    registry[("mmrrc", "Nf1 KO mouse")] = "rrid:MMRRC_000001-UNC"
    p = _write(tmp_path, "animal_models", "Nf1", {
        "toolType": "animal_model", "basicInfo": {"animalModelName": "Nf1 KO mouse"},
    })
    results = lookup.run_lookup([p])
    assert calls == [("imsr", "Nf1 KO mouse"), ("mmrrc", "Nf1 KO mouse")]
    assert results[0]["source"] == "MMRRC"
    assert json.loads(p.read_text())["basicInfo"]["rrid"] == "rrid:MMRRC_000001-UNC"


def test_imsr_hit_skips_mmrrc(tmp_path, offline):
    calls, registry = offline
    registry[("imsr", "C57BL/6J")] = "rrid:IMSR_JAX:000664"
    p = _write(tmp_path, "animal_models", "B6", {
        "toolType": "animal_model", "basicInfo": {"animalModelName": "C57BL/6J"},
    })
    lookup.run_lookup([p])
    assert calls == [("imsr", "C57BL/6J")]


def test_antibody_skipped_without_api_key(tmp_path, offline):
    calls, registry = offline
    registry[("scicrunch", "anti-NF1")] = "rrid:AB_1"
    p = _write(tmp_path, "antibodies", "nf1", {
        "toolType": "antibody", "basicInfo": {"antibodyName": "anti-NF1"},
    })
    assert lookup.run_lookup([p])[0]["status"] == "not_found"
    assert calls == []
    lookup.run_lookup([p], api_key="k")
    assert json.loads(p.read_text())["basicInfo"]["rrid"] == "rrid:AB_1"


def test_types_without_registry_make_no_calls(tmp_path, offline):
    calls, _ = offline
    p = _write(tmp_path, "computational_tools", "x", {
        "toolType": "computational_tool", "basicInfo": {"softwareName": "NF-tool"},
    })
    assert lookup.run_lookup([p])[0]["status"] == "not_found"
    assert calls == []


def test_mined_pdm_uses_model_name(tmp_path, offline):
    calls, registry = offline
    registry[("cellosaurus", "JH-2-002")] = "rrid:CVCL_A123"
    p = _write(tmp_path, "patient_derived_models", "jh", {
        "toolType": "patient_derived_model",
        "basicInfo": {"modelName": "JH-2-002", "modelType": ""},
    })
    lookup.run_lookup([p])
    assert calls == [("cellosaurus", "JH-2-002")]
    assert json.loads(p.read_text())["basicInfo"]["rrid"] == "rrid:CVCL_A123"


def test_context_rrid_must_fit_tool_type(tmp_path, offline):
    calls, _ = offline
    ctx = "Cells were stained with anti-NF1 (RRID:AB_2150700) and ST88-14 (RRID:CVCL_8916)."
    p = _write(tmp_path, "cell_lines", "st88", _cell_line("ST88-14", context=ctx))
    results = lookup.run_lookup([p])
    assert calls == []  # no registry call: the context already had a cell-line RRID
    assert results[0]["source"] == "context"
    assert json.loads(p.read_text())["basicInfo"]["rrid"] == "rrid:CVCL_8916"


def test_registry_exception_is_non_fatal(tmp_path, offline, monkeypatch):
    _, registry = offline
    registry[("cellosaurus", "B")] = "rrid:CVCL_0002"

    def boom(name):
        if name == "A":
            raise TimeoutError("cellosaurus timed out")
        return registry.get(("cellosaurus", name), "")

    monkeypatch.setattr(lookup, "_lookup_cellosaurus", boom)
    a = _write(tmp_path, "cell_lines", "A", _cell_line("A"))
    b = _write(tmp_path, "cell_lines", "B", _cell_line("B"))
    results = lookup.run_lookup([a, b])
    assert [r["status"] for r in results] == ["error", "filled"]


def test_observations_and_unreadable_files(tmp_path, offline):
    obs = _write(tmp_path, "cell_lines/observations", "o", {"resourceType": "Cell Line"})
    bad = tmp_path / "submissions" / "cell_lines" / "bad.json"
    bad.write_text("{not json")
    results = lookup.run_lookup([obs, bad])
    assert [r["status"] for r in results] == ["error"]


def test_main_files_list_and_summary_md(tmp_path, offline):
    _, registry = offline
    registry[("cellosaurus", "MCF7")] = "rrid:CVCL_0031"
    p = _write(tmp_path, "cell_lines", "MCF7", _cell_line("MCF7"))
    q = _write(tmp_path, "cell_lines", "X", _cell_line("Unknown"))
    lst = tmp_path / "files.txt"
    lst.write_text(f"{p}\n{q}\n\n")
    md = tmp_path / "rrids.md"

    assert lookup.main(["--files-list", str(lst), "--summary-md", str(md)]) == 0

    text = md.read_text()
    assert "`rrid:CVCL_0031`" in text and "MCF7" in text and "Unknown" not in text


def test_summary_md_when_nothing_filled():
    assert "No RRIDs" in lookup.summary_markdown([])


def test_mmrrc_catalog_disk_cache(tmp_path, monkeypatch):
    """The MMRRC catalog is fetched once and then served from --mmrrc-cache."""
    cache = tmp_path / "mmrrc.json"
    pages = {1: [{"strain_name": "B6.Nf1 KO", "rrid": "RRID:MMRRC_000001-UNC"}], 2: []}
    fetched = []

    def fake_get(url, **k):
        n = int(url.rsplit("/", 1)[1])
        fetched.append(n)
        return pages.get(n, [])

    monkeypatch.setattr(lookup, "_get", fake_get)
    monkeypatch.setattr(lookup, "_MMRRC_CACHE_FILE", cache)
    monkeypatch.setattr(lookup, "_MMRRC_CATALOG_CACHE", None)
    assert _real_lookup_mmrrc("b6.nf1  ko") == "rrid:MMRRC_000001-UNC"
    assert fetched == [1, 2] and cache.exists()

    # New "run": in-memory cache cleared, catalog read back from disk.
    monkeypatch.setattr(lookup, "_MMRRC_CATALOG_CACHE", None)
    fetched.clear()
    assert _real_lookup_mmrrc("B6.Nf1 KO") == "rrid:MMRRC_000001-UNC"
    assert fetched == []


def test_mmrrc_outage_is_not_cached(tmp_path, monkeypatch):
    cache = tmp_path / "mmrrc.json"
    monkeypatch.setattr(lookup, "_get", lambda url, **k: None)
    monkeypatch.setattr(lookup, "_MMRRC_CACHE_FILE", cache)
    monkeypatch.setattr(lookup, "_MMRRC_CATALOG_CACHE", None)
    assert _real_lookup_mmrrc("anything") == ""
    assert not cache.exists()
