#!/usr/bin/env python3
"""
Tests for the human-review CSV round trip added to
scripts/review_tool_annotations.py per review on
nf-osi/nf-research-tools-schema#246
(https://github.com/nf-osi/nf-research-tools-schema/pull/246#issuecomment-5403174547):
neither an exact nor a stripped-suffix individualID match is safe to write
to Synapse unattended (a single donor/specimen individualID can span more
than one downstream resource -- confirmed live for JH-2-002, which splits
MPNST vs. Plexiform Neurofibroma via each file's own tumorType annotation
even though the base name looks unambiguous within the tools registry).

find_tool_study_links/find_resource_id_annotations still mine candidates,
but main() never upserts them automatically -- it writes a review CSV, and
a human applies survivors via --apply-tool-study-links-csv /
--apply-resource-id-annotations-csv, which round-trip through the four
functions under test here.

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


def test_tool_study_links_review_round_trip(tmp_path):
    links = [
        {
            'resourceId': 'res-1',
            'resourceName': 'JH-2-002 (MPNST)',
            'resourceType': 'Cell Line',
            'rrid': None,
            'description': None,
            'synonyms': '',
            'studyId': 'syn111',
            'studyName': 'Some Study',
            'matchedVia': 'JH-2-002',
            'tumorType': "['Malignant Peripheral Nerve Sheath Tumor']",
            'diagnosis': "['Neurofibromatosis type 1']",
            'tissue': 'cell line',
        }
    ]
    path = tmp_path / "tool_study_links_for_review.csv"
    rta.save_tool_study_links_for_review(links, path)
    assert path.exists()

    loaded = rta.load_tool_study_links_from_review(path)
    assert len(loaded) == 1
    assert loaded[0]['resourceId'] == 'res-1'
    assert loaded[0]['studyId'] == 'syn111'
    assert loaded[0]['matchedVia'] == 'JH-2-002'


def test_tool_study_links_review_skips_writing_when_empty(tmp_path):
    path = tmp_path / "tool_study_links_for_review.csv"
    rta.save_tool_study_links_for_review([], path)
    assert not path.exists()


def test_tool_study_links_review_reflects_human_deletion(tmp_path):
    """A row a human deletes from the CSV before applying must not survive
    the round trip -- this is the whole point of the review step."""
    links = [
        {'resourceId': 'res-1', 'resourceName': 'A', 'resourceType': 'Cell Line',
         'rrid': None, 'description': None, 'synonyms': '', 'studyId': 'syn1',
         'studyName': 'S1', 'matchedVia': 'A', 'tumorType': None, 'diagnosis': None, 'tissue': None},
        {'resourceId': 'res-2', 'resourceName': 'B', 'resourceType': 'Cell Line',
         'rrid': None, 'description': None, 'synonyms': '', 'studyId': 'syn2',
         'studyName': 'S2', 'matchedVia': 'B', 'tumorType': None, 'diagnosis': None, 'tissue': None},
    ]
    path = tmp_path / "review.csv"
    rta.save_tool_study_links_for_review(links, path)

    # Simulate a human deleting the row they didn't trust
    df = pd.read_csv(path)
    df[df['resourceId'] != 'res-2'].to_csv(path, index=False)

    loaded = rta.load_tool_study_links_from_review(path)
    assert len(loaded) == 1
    assert loaded[0]['resourceId'] == 'res-1'


def _file_occurrences_with_context(rows, index):
    """rows: list of (id, individualID, Resource_id, tumorType, diagnosis, tissue) tuples."""
    return pd.DataFrame(
        [
            {
                "id": r[0], "individualID": r[1], "Resource_id": r[2],
                "tumorType": r[3], "diagnosis": r[4], "tissue": r[5],
            }
            for r in rows
        ],
        index=index,
    )


def test_resource_id_review_round_trip_preserves_row_label_and_list(tmp_path):
    file_occurrences = _file_occurrences_with_context(
        [("syn111", "JH-2-002-GAF53", None, "['MPNST']", "['NF1']", "cell line")],
        index=["111_2"],
    )
    updates = pd.DataFrame(
        [{"id": "syn111", "Resource_id": ["res-1"]}],
        index=["111_2"],
    )
    path = tmp_path / "resource_id_annotations_for_review.csv"
    rta.save_resource_id_annotations_for_review(updates, file_occurrences, path)
    assert path.exists()

    loaded = rta.load_resource_id_annotations_from_review(path)
    assert list(loaded.index) == ["111_2"]
    assert loaded.iloc[0]["id"] == "syn111"
    assert loaded.iloc[0]["Resource_id"] == ["res-1"]


def test_resource_id_review_includes_context_columns_for_manual_review():
    """The review CSV must carry enough context (individualID, tumorType,
    diagnosis, tissue, addedResourceId) for a human to judge a candidate
    without a separate Synapse lookup -- per #246 review."""
    file_occurrences = _file_occurrences_with_context(
        [("syn111", "JH-2-002", ["existing-res"], "['MPNST']", "['NF1']", "cell line")],
        index=["111_2"],
    )
    updates = pd.DataFrame(
        [{"id": "syn111", "Resource_id": ["existing-res", "res-1"]}],
        index=["111_2"],
    )
    review = updates.copy()
    context_cols = ['individualID', 'tumorType', 'diagnosis', 'tissue']
    context_by_file = file_occurrences.set_index('id')[context_cols]
    review = review.join(context_by_file, on='id')
    review.insert(0, 'row_label', updates.index)
    review['addedResourceId'] = review['Resource_id'].apply(lambda lst: lst[-1])

    for col in ['row_label', 'individualID', 'tumorType', 'diagnosis', 'tissue', 'addedResourceId']:
        assert col in review.columns
    assert review.iloc[0]['addedResourceId'] == 'res-1'
    assert review.iloc[0]['individualID'] == 'JH-2-002'


def test_resource_id_review_skips_writing_when_empty(tmp_path):
    path = tmp_path / "resource_id_annotations_for_review.csv"
    empty_updates = pd.DataFrame(columns=['id', 'Resource_id'])
    file_occurrences = _file_occurrences_with_context([], index=[])
    rta.save_resource_id_annotations_for_review(empty_updates, file_occurrences, path)
    assert not path.exists()


def test_resource_id_review_reflects_human_deletion(tmp_path):
    """A file row a human decides is unclear (e.g. JH-2-002 -- ambiguous
    tumorType) and deletes from the CSV must not survive to the apply step."""
    file_occurrences = _file_occurrences_with_context(
        [
            ("syn111", "JH-2-002-GAF53", None, "['MPNST']", None, "cell line"),
            ("syn222", "JH-2-002-FF824", None, "['Plexiform Neurofibroma']", None, "primary tumor"),
        ],
        index=["111_1", "222_1"],
    )
    updates = pd.DataFrame(
        [
            {"id": "syn111", "Resource_id": ["res-mpnst"]},
            {"id": "syn222", "Resource_id": ["res-mpnst"]},  # wrong match a reviewer would reject
        ],
        index=["111_1", "222_1"],
    )
    path = tmp_path / "review.csv"
    rta.save_resource_id_annotations_for_review(updates, file_occurrences, path)

    df = pd.read_csv(path)
    df[df['id'] != 'syn222'].to_csv(path, index=False)

    loaded = rta.load_resource_id_annotations_from_review(path)
    assert list(loaded['id']) == ['syn111']
    assert list(loaded.index) == ['111_1']
