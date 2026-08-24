#!/usr/bin/env python3
"""
Regression tests for wiring up PR #196's new fields end-to-end, and for fixing
the primary-key/geneticDisorder/manifestation column names that the LinkML
migration (unifying all 9 tool-type tables onto `resourceId`, and AnimalModel/
CellLine/Biobank onto shared `geneticDisorder`/`manifestation`) left stale in
compile_accepted_submissions.py and clean_submission_csvs.py.

These tests run offline with no Synapse access.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = REPO_ROOT / "tool_coverage" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cas = _load_module("compile_accepted_submissions")
ccs = _load_module("clean_submission_csvs")

# The live canonical enum values (modules/enums.yaml GeneticDisorderEnum) --
# duplicated here rather than parsed from YAML so this test fails loudly if
# either side drifts, instead of silently agreeing with itself.
_CANONICAL_GENETIC_DISORDER_VALUES = {
    "Neurofibromatosis type 1",
    "Neurofibromatosis type 2",
    "Schwannomatosis",
    "NF1 Spontaneous Mutation",
    "No known genetic disorder",
    "Other",
}


def test_genetic_disorder_map_targets_canonical_values():
    """Every _GENETIC_DISORDER_MAP target must be a real GeneticDisorderEnum value --
    otherwise submissions get quietly written with a value the schema doesn't have."""
    for target in cas._GENETIC_DISORDER_MAP.values():
        assert target in _CANONICAL_GENETIC_DISORDER_VALUES, (
            f"{target!r} is not a canonical GeneticDisorderEnum value"
        )


def test_genetic_disorder_map_covers_all_live_formspark_raw_values():
    """Formspark's raw (pre-translation) values across every form that collects
    a genetic-disorder-style field, translated through the map (or passed
    through unchanged if already canonical), must land on a canonical value."""
    raw_values_seen_on_live_forms = {
        "Neurofibromatosis Type 1", "Neurofibromatosis Type 2", "Schwannomatosis",
        "NF1 Spontaneous Mutation", "No known disease", "None", "Other",
    }
    for raw in raw_values_seen_on_live_forms:
        translated = cas._GENETIC_DISORDER_MAP.get(raw, raw)
        assert translated in _CANONICAL_GENETIC_DISORDER_VALUES, (
            f"raw Formspark value {raw!r} -> {translated!r}, not canonical"
        )


def _sample_animal_model_submission():
    return {
        "basicInfo": {"animalModelName": "NF1 KO Mouse"},
        "strainNomenclature": "B6.129-Nf1tm1",
        "backgroundStrain": "C57BL/6",
        "animalModelGeneticDisorder": "Neurofibromatosis Type 1",
        "animalModelOfManifestation": "Plexiform Neurofibroma",
        "humanizationMethod": "HSC engraftment",
        "immuneSystemComponents": "T cells, B cells",
        "species": "Mouse",
    }


def test_build_animal_model_uses_resourceid_and_canonical_genetic_disorder():
    row = cas._build_animal_model(_sample_animal_model_submission())
    assert "resourceId" in row
    assert "animalModelId" not in row
    assert "geneticDisorder" in row
    assert "animalModelGeneticDisorder" not in row
    assert row["geneticDisorder"] == "Neurofibromatosis type 1"
    assert "manifestation" in row
    assert "animalModelOfManifestation" not in row
    assert row["humanizationMethod"] == "HSC engraftment"
    assert row["immuneSystemComponents"] != ""


def test_build_cell_line_uses_resourceid_and_canonical_genetic_disorder():
    submission = {
        "basicInfo": {"cellLineName": "Test Line", "species": "Human"},
        "cellLineGeneticDisorder": "None",
        "cellLineManifestation": "Schwannoma",
        "mechanismOfActionValidation": "MEK inhibitors",
        "mtaRequired": True,
    }
    row = cas._build_cell_line(submission)
    assert "resourceId" in row
    assert "cellLineId" not in row
    assert row["geneticDisorder"] == "No known genetic disorder"
    assert "cellLineGeneticDisorder" not in row
    assert row["manifestation"] == "Schwannoma"
    assert row["mechanismOfActionValidation"] == "MEK inhibitors"
    assert row["mtaRequired"] is True


def test_build_mutation_uses_resourceid_matching_animal_model():
    submission = {
        "basicInfo": {"animalModelName": "NF1 KO Mouse"},
        "affectedGeneSymbol": "Nf1",
        "alleleType": "Knockout",
    }
    mutation_rows = cas._build_mutation(submission)
    assert mutation_rows is not None
    for row in mutation_rows:
        assert "resourceId" in row
        assert "animalModelId" not in row
        assert "cellLineId" not in row
        # Must match what the central per-type loop will assign to the
        # corresponding AnimalModel row's own resourceId.
        assert row["resourceId"] == cas._make_resource_id("NF1 KO Mouse", "animal_models")


def test_build_organoid_and_patient_derived_model_map_nf_genetic_disorder():
    submission = {
        "basicInfo": {
            "resourceName": "Test Organoid",
            "modelType": "Tumor organoid",
            "derivationSource": "Patient biopsy",
            "nfGeneticDisorder": "None",
        },
    }
    organoid_row = cas._build_organoid_protocol(submission)
    assert organoid_row["geneticDisorder"] == "No known genetic disorder"
    assert "nfGeneticDisorder" not in organoid_row

    pdm_submission = {
        "basicInfo": {
            "resourceName": "Test PDX",
            "modelSystemType": "PDX (Patient-Derived Xenograft)",
            "nfGeneticDisorder": "NF1 Spontaneous Mutation",
        },
    }
    pdm_row = cas._build_patient_derived_model(pdm_submission)
    assert pdm_row["geneticDisorder"] == "NF1 Spontaneous Mutation"
    assert "nfGeneticDisorder" not in pdm_row


def test_map_genetic_disorder_handles_list_valued_input():
    """geneticDisorder is multivalued (modules/mixins.yaml), and real
    organoid/patient-derived-model submissions return a list from
    Formspark's multi-select nfGeneticDisorder field -- a plain dict.get()
    on a list crashed with 'unhashable type: list' against live submission
    data. Each element must be mapped and re-joined instead."""
    assert cas._map_genetic_disorder(["Neurofibromatosis Type 1", "None"]) == (
        "Neurofibromatosis type 1, No known genetic disorder"
    )
    assert cas._map_genetic_disorder([]) == ""

    organoid_row = cas._build_organoid_protocol({
        "basicInfo": {
            "resourceName": "Test Organoid 2",
            "modelType": "Tumor organoid",
            "derivationSource": "Patient biopsy",
            "nfGeneticDisorder": ["Neurofibromatosis Type 1", "Schwannomatosis"],
        },
    })
    assert organoid_row["geneticDisorder"] == (
        "Neurofibromatosis type 1, Schwannomatosis"
    )


def test_build_biobank_exists_and_produces_expected_columns():
    """Biobank had no builder at all before this fix -- submissions from
    submitBiobank.json could not reach Synapse through this pipeline."""
    submission = {
        "basicInfo": {
            "biobankName": "Test Biobank",
            "biobankURL": "https://example.org/biobank",
            "diseaseType": ["Neurofibromatosis type 1"],
            "mtaRequired": True,
        },
        "requestFormURL": "https://example.org/request",
    }
    row = cas._build_biobank(submission)
    assert row["resourceId"] == ""
    assert row["biobankName"] == "Test Biobank"
    assert row["geneticDisorder"] == "Neurofibromatosis type 1"
    assert row["mtaRequired"] is True
    assert row["requestFormURL"] == "https://example.org/request"
    assert "biobank" in cas._BUILDERS
    assert "biobank" in cas._TTYPE_ID_INFO


def test_columns_dicts_have_no_stale_type_specific_id_columns():
    """Every detail-table COLUMNS entry's first column must be `resourceId` --
    none of the old `<type>Id` names, which no longer exist on Synapse."""
    stale_names = {
        "animalModelId", "cellLineId", "antibodyId", "geneticReagentId",
        "biobankId", "computationalToolId", "organoidProtocolId",
        "patientDerivedModelId", "clinicalAssessmentToolId",
    }
    detail_table_keys = [
        "cell_lines", "antibodies", "animal_models", "genetic_reagents",
        "patient_derived_models", "computational_tools", "organoid_protocols",
        "clinical_assessment_tools", "biobanks",
    ]
    for key in detail_table_keys:
        cols = set(cas.COLUMNS[key])
        overlap = cols & stale_names
        assert not overlap, f"COLUMNS[{key!r}] still references stale ID column(s): {overlap}"
        assert "resourceId" in cols, f"COLUMNS[{key!r}] missing resourceId"


def test_detail_table_pk_all_resourceid():
    """clean_submission_csvs.py's dedup-by-PK must key every tool-type table
    off resourceId -- the old per-type names no longer exist on Synapse, so a
    dedup check against them would never match and every re-run would
    silently re-insert every row as if it were new (the #213 bug, again)."""
    tool_type_tables = {
        "syn26486808", "syn26486811", "syn26486821", "syn26486823",
        "syn26486832", "syn73709226", "syn73709227", "syn73709228", "syn73709229",
    }
    for table_id in tool_type_tables:
        assert ccs._DETAIL_TABLE_PK[table_id] == "resourceId", (
            f"{table_id}: _DETAIL_TABLE_PK is {ccs._DETAIL_TABLE_PK[table_id]!r}, expected 'resourceId'"
        )


def test_strip_before_upload_no_longer_drops_live_columns():
    """Fields that now have a live Synapse column must not be silently
    stripped before upload -- that was the active-data-loss bug found in the
    #196 field audit (bbbIntegrityStatus etc. on AnimalModel, licenseDetails
    on ComputationalTool, qualityControlMetrics on OrganoidProtocol,
    validationMethods on PatientDerivedModel)."""
    must_not_be_stripped = {
        "CLEAN_animal_models.csv": {
            "bbbIntegrityStatus", "routeOfAdministration", "pkpdCapabilities",
            "mechanismOfActionValidation", "pediatricSuitability", "timelineToResults",
            "modelLimitations", "clinicalTranslationHistory", "regulatoryAcceptanceHistory",
            "mtaRequired", "ngnriRepositoryStatus", "inducedVsDevelopmental",
            "alleleType", "affectedGeneSymbol",
        },
        "CLEAN_computational_tools.csv": {"licenseDetails", "rrid"},
        "CLEAN_organoid_protocols.csv": {"qualityControlMetrics"},
        "CLEAN_patient_derived_models.csv": {"validationMethods"},
    }
    for csv_name, fields in must_not_be_stripped.items():
        stripped = set(ccs._STRIP_BEFORE_UPLOAD.get(csv_name, []))
        overlap = stripped & fields
        assert not overlap, f"{csv_name}: still stripping live-column field(s) {overlap}"


def test_build_patient_derived_model_maps_organ_and_tumor_type():
    """PatientDerivedModel.tumorType was migrated to the shared, multivalued
    Synapse column (same Column ID as Biobank.tumorType, unifying the facet
    the way geneticDisorder/manifestation already are). The submission form
    is still single-select Title Case, so it must be mapped to the canonical
    lowercase TumorTypeEnum value and wrapped in a one-item list. organ was
    a real column (shared with CellLine) that the builder never read at all."""
    submission = {
        "basicInfo": {
            "resourceName": "Test PDX 2",
            "modelSystemType": "PDX (Patient-Derived Xenograft)",
            "organ": "Skin",
            "tumorType": "Malignant Peripheral Nerve Sheath Tumor",
        },
    }
    row = cas._build_patient_derived_model(submission)
    assert row["organ"] == "Skin"
    assert row["tumorType"] == "malignant peripheral nerve sheath tumor"

    # Unmapped/no value -> empty list string, not a crash
    empty_row = cas._build_patient_derived_model({
        "basicInfo": {"resourceName": "No Tumor Type", "modelSystemType": "Humanized Mouse"},
    })
    assert empty_row["tumorType"] == ""
    assert empty_row["organ"] is None or empty_row["organ"] == ""


def test_patient_derived_models_columns_include_organ():
    assert "organ" in cas.COLUMNS["patient_derived_models"]
