#!/usr/bin/env python3
"""
Tests for the tool<->study association mining added to
scripts/review_tool_annotations.py (nf-osi/nf-research-tools-schema#132, #154).

The script's own docstring/design note explains why exact-match individualID
associations are upserted directly rather than routed through the PR-review
flow used for new-resource suggestions: an exact match against a known
resourceName/synonym is a high-confidence, mechanical signal that doesn't
need human curation judgment the way a brand-new resource suggestion does.

These tests run offline with no Synapse access.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rta = _load_module("review_tool_annotations")


def _tool(resource_id, resource_name, synonyms=""):
    return {
        "resourceId": resource_id,
        "resourceName": resource_name,
        "resourceType": "Cell Line",
        "rrid": None,
        "description": None,
        "synonyms": synonyms,
    }


def test_find_tool_study_links_matches_exact_resource_name():
    tools_data = [_tool("res-1", "NCC-MPNST1-C1")]
    occurrences = pd.DataFrame(
        {
            "individualID": ["NCC-MPNST1-C1"],
            "studyId": ["syn12345"],
            "studyName": ["Some Study"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert len(links) == 1
    assert links[0]["resourceId"] == "res-1"
    assert links[0]["studyId"] == "syn12345"
    assert links[0]["matchedVia"] == "NCC-MPNST1-C1"


def test_find_tool_study_links_matches_via_synonym():
    tools_data = [_tool("res-2", "NCC-MPNST1-C1", synonyms="ipn02.3, ipnNF95.11c")]
    occurrences = pd.DataFrame(
        {
            "individualID": ["ipn02.3"],
            "studyId": ["syn999"],
            "studyName": ["Another Study"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert len(links) == 1
    assert links[0]["resourceId"] == "res-2"


def test_find_tool_study_links_skips_already_existing():
    tools_data = [_tool("res-3", "NF1-Cell-A")]
    occurrences = pd.DataFrame(
        {
            "individualID": ["NF1-Cell-A"],
            "studyId": ["syn111"],
            "studyName": ["Study X"],
        }
    )
    links = rta.find_tool_study_links(
        occurrences, tools_data, existing_links={("res-3", "syn111")}
    )
    assert links == []


def test_find_tool_study_links_ignores_unmatched_individual_ids():
    tools_data = [_tool("res-4", "Known Tool")]
    occurrences = pd.DataFrame(
        {
            "individualID": ["Totally Unrelated Sample"],
            "studyId": ["syn222"],
            "studyName": ["Study Y"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert links == []


def test_find_tool_study_links_dedupes_multiple_occurrences_of_same_pair():
    tools_data = [_tool("res-5", "Repeated Tool")]
    occurrences = pd.DataFrame(
        {
            "individualID": ["Repeated Tool", "Repeated Tool", "Repeated Tool"],
            "studyId": ["syn333", "syn333", "syn333"],
            "studyName": ["Study Z", "Study Z", "Study Z"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert len(links) == 1


def test_find_tool_study_links_matches_stripped_disambiguation_suffix():
    """An individualID of 'JH-2-031' should match resourceName
    'JH-2-031 (MPNST)' when no other resourceId shares that base name."""
    tools_data = [_tool("res-7", "JH-2-031 (MPNST)")]
    occurrences = pd.DataFrame(
        {
            "individualID": ["JH-2-031"],
            "studyId": ["syn555"],
            "studyName": ["Study V"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert len(links) == 1
    assert links[0]["resourceId"] == "res-7"


def test_find_tool_study_links_skips_ambiguous_stripped_suffix():
    """Two resourceIds sharing the same base name (e.g. MPNST vs pNF
    sublines of the same specimen) must NOT be auto-linked via the bare
    specimen ID -- it's genuinely ambiguous which one a file belongs to."""
    tools_data = [
        _tool("res-8a", "JH-2-002 (MPNST)"),
        _tool("res-8b", "JH-2-002 (pNF)"),
    ]
    occurrences = pd.DataFrame(
        {
            "individualID": ["JH-2-002"],
            "studyId": ["syn666"],
            "studyName": ["Study U"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert links == []


def test_find_tool_study_links_skips_ambiguous_exact_resource_name():
    """Two distinct resourceIds can legitimately share the exact same
    resourceName (e.g. two vendor SKUs of the same catalog product,
    confirmed live on nf-osi/nf-research-tools-schema#246 -- 25+ such
    collisions exist in production data). An individualID matching that
    name must NOT be silently auto-linked to whichever tool happened to be
    seen last while building the lookup."""
    tools_data = [
        _tool("res-9a", "CPTC-NF1-1"),
        _tool("res-9b", "CPTC-NF1-1"),
    ]
    occurrences = pd.DataFrame(
        {
            "individualID": ["CPTC-NF1-1"],
            "studyId": ["syn777"],
            "studyName": ["Study T"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert links == []


def test_find_tool_study_links_skips_ambiguous_exact_synonym():
    """Same as the exact-resourceName case, but for a synonym shared across
    distinct resourceIds (e.g. a common accession number like NM_001042492
    listed as a synonym for more than one tool, confirmed live on #246)."""
    tools_data = [
        _tool("res-10a", "Tool A", synonyms="NM_001042492"),
        _tool("res-10b", "Tool B", synonyms="NM_001042492"),
    ]
    occurrences = pd.DataFrame(
        {
            "individualID": ["NM_001042492"],
            "studyId": ["syn888"],
            "studyName": ["Study S"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert links == []


def test_find_tool_study_links_requires_both_resource_id_and_name():
    """A tool record missing resourceId or resourceName must not crash the
    lookup construction or be matchable -- mirrors real ACCEPTED data where
    some rows are incomplete."""
    tools_data = [
        {"resourceId": None, "resourceName": "No ID Tool", "synonyms": ""},
        {"resourceId": "res-6", "resourceName": None, "synonyms": ""},
    ]
    occurrences = pd.DataFrame(
        {
            "individualID": ["No ID Tool"],
            "studyId": ["syn444"],
            "studyName": ["Study W"],
        }
    )
    links = rta.find_tool_study_links(occurrences, tools_data, existing_links=set())
    assert links == []
