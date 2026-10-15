#!/usr/bin/env python3
"""build_processed_publications.py decides which papers go to the paid Sonnet
review. It used to glob every committed publication_cache file, so each mining
run re-reviewed (and re-mined) papers from earlier runs."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tool_coverage" / "scripts"))

import build_processed_publications as bpp  # noqa: E402


def _write_cache(cache_dir: Path, pmid: str, **extra):
    data = {"pmid": f"PMID:{pmid}", "title": f"Paper {pmid}",
            "abstract": "abs", "methods": "meth", "cache_level": "minimal",
            "has_fulltext": True, **extra}
    (cache_dir / f"{pmid}_text.json").write_text(json.dumps(data))


def _setup(tmp_path: Path, screened, cached, reviewed=()):
    cache_dir = tmp_path / "publication_cache"
    results_dir = tmp_path / "results"
    cache_dir.mkdir()
    results_dir.mkdir()
    for pmid in cached:
        _write_cache(cache_dir, pmid)
    for pmid in reviewed:
        (results_dir / f"{pmid}_tool_review.yaml").write_text("toolValidations: []\n")
    # Observation YAMLs must not count as "reviewed".
    (results_dir / "999_observations.yaml").write_text("observations: []\n")
    screened_file = tmp_path / "screened_publications.csv"
    with open(screened_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pmid", "title", "source"])
        for pmid in screened:
            w.writerow([pmid, "t", "pubmed"])
    return screened_file, cache_dir, results_dir


def _run(tmp_path, screened_file, cache_dir, results_dir, *flags):
    out = tmp_path / "processed_publications.csv"
    assert bpp.main([
        "--screened-file", str(screened_file),
        "--cache-dir", str(cache_dir),
        "--results-dir", str(results_dir),
        "--output", str(out), *flags,
    ]) == 0
    with open(out, newline="") as f:
        return list(csv.DictReader(f))


def test_only_screened_pmids_with_cache_are_selected(tmp_path):
    # 3 and 4 are cached from earlier runs but not screened this run.
    screened_file, cache_dir, results_dir = _setup(
        tmp_path, screened=["PMID:1", "PMID:2", "PMID:5"], cached=["1", "2", "3", "4"])
    rows = _run(tmp_path, screened_file, cache_dir, results_dir)
    assert [r["pmid"] for r in rows] == ["PMID:1", "PMID:2"]  # 5 has no cache
    assert rows[0]["title"] == "Paper 1"
    assert rows[0]["methods"] == "meth"
    assert list(rows[0].keys()) == bpp.FIELDNAMES


def test_already_reviewed_pmids_are_skipped(tmp_path):
    screened_file, cache_dir, results_dir = _setup(
        tmp_path, screened=["PMID:1", "PMID:2", "PMID:999"],
        cached=["1", "2", "999"], reviewed=["1"])
    rows = _run(tmp_path, screened_file, cache_dir, results_dir)
    assert [r["pmid"] for r in rows] == ["PMID:2", "PMID:999"]


def test_force_rereviews_keeps_reviewed_pmids(tmp_path):
    screened_file, cache_dir, results_dir = _setup(
        tmp_path, screened=["PMID:1", "PMID:2"], cached=["1", "2"], reviewed=["1"])
    rows = _run(tmp_path, screened_file, cache_dir, results_dir, "--force-rereviews")
    assert [r["pmid"] for r in rows] == ["PMID:1", "PMID:2"]


def test_pmid_formats_and_duplicates_normalize(tmp_path):
    # Synapse-candidate rows can arrive as bare or float-ish PMIDs.
    screened_file, cache_dir, results_dir = _setup(
        tmp_path, screened=["PMID:1", "1", "2.0", ""], cached=["1", "2"])
    rows = _run(tmp_path, screened_file, cache_dir, results_dir)
    assert [r["pmid"] for r in rows] == ["PMID:1", "PMID:2"]


def test_missing_results_dir_means_nothing_reviewed(tmp_path):
    screened_file, cache_dir, _ = _setup(tmp_path, screened=["PMID:1"], cached=["1"])
    rows = _run(tmp_path, screened_file, cache_dir, tmp_path / "nope")
    assert [r["pmid"] for r in rows] == ["PMID:1"]


def test_empty_selection_still_writes_header(tmp_path):
    screened_file, cache_dir, results_dir = _setup(
        tmp_path, screened=["PMID:1"], cached=["1"], reviewed=["1"])
    rows = _run(tmp_path, screened_file, cache_dir, results_dir)
    assert rows == []


def _mining_steps():
    wf = yaml.safe_load((REPO_ROOT / ".github/workflows/publication-mining.yml").read_text())
    return {s.get("name"): s for s in wf["jobs"]["mine-publications"]["steps"]}


def test_workflow_uses_script_and_persists_review_yamls():
    steps = _mining_steps()
    prep = steps["Prepare publications list from cache"]["run"]
    assert "build_processed_publications.py" in prep
    assert "glob('*_text.json')" not in prep
    assert "--force-rereviews" in prep

    assert "--include-reviewed" in steps["Prepare publication list (bench + clinical queries)"]["run"]

    review_paths = steps["List tool review YAMLs to commit"]["run"]
    assert "tool_reviews/results/*_tool_review.yaml" in review_paths
    add_paths = steps["Create Pull Request (mining results)"]["with"]["add-paths"]
    assert "steps.review_paths.outputs.paths" in add_paths
    # Observation YAMLs would be re-emitted as submissions every run.
    assert "observations" not in add_paths
