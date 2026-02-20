#!/usr/bin/env python3
"""
Enrich existing tool records in Synapse with consensus values from file annotations.

For each tool record with blank fields, queries NF Portal file annotations by
individualID, computes consensus values (after case normalization and schema
valid-value lookup), and generates SUBMIT_*_updates.csv files.

Only fills blank fields. Never overwrites existing values.
Consensus = all non-blank annotation values collapse to the same canonical form.

Usage:
    python scripts/enrich_existing_tools.py [--dry-run] [--output-dir .]
"""

import argparse
import ast
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import synapseclient
    from synapseclient import Synapse
    import pandas as pd
except ImportError:
    print("Error: Required packages not installed. Install with: pip install synapseclient pandas")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── Synapse table/view IDs ────────────────────────────────────────────────────
ANNOTATIONS_VIEW_ID = "syn16858331"   # NF Portal full file annotations view (has individualID, tissue, sex, age, etc.)
# Note: syn52702673 is a narrower materialized view used for review_tool_annotations.py
# but it lacks tissue/sex/age columns; syn16858331 is the authoritative source.
RESOURCES_VIEW_ID = "syn26450069"     # Base Resource table: resourceName → cellLineId / animalModelId
# Note: syn51730943 is a denormalized materialized view that lacks the detail-table ID columns.
# syn26450069 is the actual Resource table with cellLineId / animalModelId FK columns.
# patientDerivedModelId is not yet linked in this table (v2.0 schema); PDX enrichment is
# best-effort and will be skipped if the column is absent.
CELL_LINE_TABLE_ID = "syn26486823"    # CellLineDetails (tissue, cellLineManifestation, cellLineGeneticDisorder, donorId)
ANIMAL_MODEL_TABLE_ID = "syn26486808" # AnimalModelDetails (animalModelGeneticDisorder, animalModelOfManifestation)
PDX_TABLE_ID = "syn73709228"          # PatientDerivedModelDetails (patientDiagnosis, tumorType)
DONOR_TABLE_ID = "syn26486829"        # Donor (sex, age, species)

# ─── Schema valid values (sourced from NF-Tools-Schemas JSON files) ────────────

TISSUE_VALUES: List[str] = [
    "Blood", "Bone Marrow", "Buccal Mucosa", "Buffy Coat", "Cerebral Cortex",
    "Dorsal Root Ganglion", "Embryonic Tissue", "Meninges", "Nerve Tissue",
    "Optic Nerve", "Plasma", "Primary Tumor", "Sciatic Nerve", "Serum",
    "Splenocyte", "Unspecified", "Urine", "Whole Brain",
]

CELL_LINE_MANIFESTATION_VALUES: List[str] = [
    "Acute Lymphocytic Leukemia", "Adult T Acute Lymphoblastic Leukemia",
    "Amelanotic Cutaneous Melanoma", "Askin Tumor", "Astrocytoma", "Atypical",
    "BRCA2 Syndrome", "BCR-ABL1 positive", "Cafe-Au-Lait Spots",
    "Canine Histiocytic Sarcoma", "Canine Lymphoma", "Canine Melanoma",
    "Canine Soft Tissue Sarcoma", "Cecum Adenocarcinoma", "Cervical Adenocarcinoma",
    "Chronic Myelogenous Leukemia", "Clinically Affected",
    "Clinically Asymptomatic (Self-reported)", "Clinically Asymptomatic But At Risk",
    "Colon Adenocarcinoma", "Colon Carcinoma", "Cutaneous Melanoma",
    "Cutaneous Neurofibroma", "Cystic Fibrosis", "General NF1 Deficiency",
    "Glioblastoma", "Hereditary Breast and Ovarian Cancer Syndrome",
    "Human Papillomavirus-Related Endocervical Adenocarcinoma",
    "Invasive Breast Carcinoma", "Lipoma", "Lung Adenocarcinoma",
    "Lung Adenosquamous Carcinoma", "Lung Carcinoid Tumor", "Lung Giant Cell Carcinoma",
    "Lung Large Cell Carcinoma", "Lung Non-Small Cell Carcinoma",
    "Lung Papillary Adenocarcinoma", "Lung Small Cell Carcinoma",
    "Lung Squamous Cell Carcinoma", "Malignant Peripheral Nerve Sheath Tumor",
    "Melanoma", "Minimally Invasive Lung Adenocarcinoma",
    "Mouse Adrenal Gland Pheochromocytoma", "Neuroblastoma", "Neurofibroma",
    "Noonan Syndrome", "Ovarian Cystadenocarcinoma", "Pancreatic Adenocarcinoma",
    "Pancreatic Adenosquamous Carcinoma", "Pancreatic Carcinoma",
    "Pancreatic Ductal Adenocarcinoma", "Pancreatic Somatostatinoma",
    "Plexiform Neurofibroma", "Pleural Malignant Mesothelioma",
    "Poorly Differentiated Thyroid Gland Carcinoma", "Rectal Adenocarcinoma",
    "Schwannoma", "Thyroid Gland Anaplastic Carcinoma",
    "Thyroid Gland Follicular Carcinoma", "Unaffected Nerve",
]

# Note: "Schwannamatosis" is the schema spelling (typo for Schwannomatosis)
CELL_LINE_GENETIC_DISORDER_VALUES: List[str] = [
    "Neurofibromatosis Type 1", "Neurofibromatosis Type 2", "Schwannamatosis", "None",
]

# Animal model schema uses different capitalization from cell line schema
ANIMAL_MODEL_GENETIC_DISORDER_VALUES: List[str] = [
    "Neurofibromatosis type 1", "Neurofibromatosis type 2",
    "No known disease", "Schwannomatosis",
]

ANIMAL_MODEL_MANIFESTATION_VALUES: List[str] = [
    "No Symptoms", "Acute Myeloid Leukemia", "Astrocytoma", "Cognition", "Growth",
    "Heart Malformation", "High Grade Glioma", "Malignant Peripheral Nerve Sheath Tumor",
    "Metabolic Function", "Neural Crest Hyperplasia", "Optic Nerve Glioma",
    "Plexiform Neurofibroma", "Spinal Development", "Other",
]

# Patient-derived model tumor types are lowercase (as defined in the JSON schema)
PDX_TUMOR_TYPE_VALUES: List[str] = [
    "cutaneous neurofibroma", "plexiform neurofibroma", "atypical neurofibroma",
    "schwannoma", "meningioma", "malignant peripheral nerve sheath tumor",
    "low grade glioma", "high grade glioma", "pheochromocytoma",
    "optic nerve glioma", "Other",
]

SEX_VALUES: List[str] = ["Male", "Female", "Unknown"]

# ─── Synonym maps (lowercase key → canonical value) ───────────────────────────

# Maps annotation `diagnosis` values → cellLineGeneticDisorder canonical form
CELL_LINE_DISORDER_SYNONYMS: Dict[str, str] = {
    "nf1": "Neurofibromatosis Type 1",
    "nf-1": "Neurofibromatosis Type 1",
    "neurofibromatosis 1": "Neurofibromatosis Type 1",
    "neurofibromatosis type 1": "Neurofibromatosis Type 1",
    "nf2": "Neurofibromatosis Type 2",
    "nf-2": "Neurofibromatosis Type 2",
    "neurofibromatosis 2": "Neurofibromatosis Type 2",
    "neurofibromatosis type 2": "Neurofibromatosis Type 2",
    "schwannomatosis": "Schwannamatosis",   # annotation spelling → schema spelling
    "schwannamatosis": "Schwannamatosis",
    "no known genetic disorder": "None",
    "none": "None",
}

# Maps annotation `diagnosis` values → animalModelGeneticDisorder canonical form
ANIMAL_MODEL_DISORDER_SYNONYMS: Dict[str, str] = {
    "nf1": "Neurofibromatosis type 1",
    "nf-1": "Neurofibromatosis type 1",
    "neurofibromatosis 1": "Neurofibromatosis type 1",
    "neurofibromatosis type 1": "Neurofibromatosis type 1",
    "nf2": "Neurofibromatosis type 2",
    "nf-2": "Neurofibromatosis type 2",
    "neurofibromatosis 2": "Neurofibromatosis type 2",
    "neurofibromatosis type 2": "Neurofibromatosis type 2",
    "schwannomatosis": "Schwannomatosis",
    "schwannamatosis": "Schwannomatosis",
    "no known disease": "No known disease",
    "no known genetic disorder": "No known disease",
}

SEX_SYNONYMS: Dict[str, str] = {
    "male": "Male",
    "m": "Male",
    "female": "Female",
    "f": "Female",
    "unknown": "Unknown",
    "u": "Unknown",
    "not reported": "Unknown",
    "not specified": "Unknown",
}


# ─── Core helpers ─────────────────────────────────────────────────────────────

def _parse_annotation_value(val) -> List[str]:
    """Return a list of plain string values from an annotation cell.

    Synapse annotation fields (e.g. tumorType, diagnosis) can be stored as
    serialized Python list strings:  "['Malignant Peripheral Nerve Sheath Tumor']"
    This function handles both forms and always returns a flat list of strings.
    """
    if val is None:
        return []
    s = str(val).strip()
    if not s:
        return []
    # Try to parse as a Python literal (list or scalar)
    if s.startswith("["):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if item is not None and str(item).strip()]
        except (ValueError, SyntaxError):
            pass
    return [s]


def _is_blank(val) -> bool:
    """Return True if a cell value should be treated as blank/missing.

    Synapse multi-value columns are returned as Python list objects.  An empty
    list [] must be treated as blank (not as a non-empty string "[]").
    """
    if val is None:
        return True
    if isinstance(val, list):
        return len(val) == 0
    s = str(val).strip()
    return not s or s.lower() in ("nan", "none", "null")


def build_canonical_lookup(
    valid_values: List[str],
    extra_synonyms: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build {lowercase_form: canonical_form} lookup.

    Direct case-folded entries take lower priority than extra_synonyms so that
    explicit synonym mappings always win when there is a collision.
    """
    lookup: Dict[str, str] = {}
    for v in valid_values:
        lookup[v.lower()] = v
    if extra_synonyms:
        lookup.update(extra_synonyms)  # may override case-folded entries
    return lookup


def compute_consensus(
    values: List,
    canonical_lookup: Optional[Dict[str, str]],
) -> Optional[str]:
    """Return canonical value if all non-blank annotation values agree; else None.

    Args:
        values: Raw annotation values (may include None / empty strings).
        canonical_lookup: {lowercase: canonical} map.  Pass None for free-text
            fields — consensus is then simply equality after strip/lowercase.

    Returns:
        Canonical string if consensus, else None.
    """
    non_blank = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not non_blank:
        return None

    if canonical_lookup is not None:
        canonical_forms: set = set()
        for v in non_blank:
            canonical = canonical_lookup.get(v.lower())
            if canonical is None:
                # Value not in schema → whole group is ineligible
                return None
            canonical_forms.add(canonical)
        return canonical_forms.pop() if len(canonical_forms) == 1 else None
    else:
        # Free-text consensus: all values must be identical (case-insensitive)
        unique_lower = set(v.lower() for v in non_blank)
        if len(unique_lower) == 1:
            return non_blank[0]   # return original-case first value
        return None


# ─── Synapse query helpers ────────────────────────────────────────────────────

def query_annotation_values(syn: Synapse) -> pd.DataFrame:
    """Query annotation values from the NF Portal full file annotations view.

    Uses modelSystemName as the primary joining key so that annotation fields
    can be matched to resource names in the tool tables.  individualID is also
    fetched for the donor-enrichment path.

    Returns a DataFrame with one row per file annotation, columns:
      modelSystemName, individualID, tissue, tumorType, diagnosis, sex, age, species
    """
    logger.info(f"Querying annotation values from {ANNOTATIONS_VIEW_ID}…")
    query = (
        "SELECT modelSystemName, individualID, tissue, tumorType, diagnosis, sex, age, species "
        f"FROM {ANNOTATIONS_VIEW_ID} "
        "WHERE modelSystemName IS NOT NULL"
    )
    try:
        results = syn.tableQuery(query)
        df = results.asDataFrame()
        logger.info(f"  Retrieved {len(df):,} annotation records with modelSystemName")
        return df
    except Exception as exc:
        logger.error(f"  Error querying annotations: {exc}")
        raise


def build_annotation_index(
    annotations_df: pd.DataFrame,
) -> Tuple[Dict[str, Dict[str, List]], Dict[str, List[str]]]:
    """Collapse annotation rows into lookup structures.

    Returns:
        msn_index:   {modelSystemName: {field: [values…]}}
                     Used for model-level enrichment (tissue, tumorType, diagnosis,
                     and also sex/age/species since donor attributes appear in files
                     annotated with the derived model system name).
        msn_to_ids:  {modelSystemName: [individualIDs…]}
                     Used to chain from model system → donor records.
    """
    logger.info("Building annotation index by modelSystemName…")
    msn_index: Dict[str, Dict[str, List]] = defaultdict(lambda: defaultdict(list))
    msn_to_ids: Dict[str, List[str]] = defaultdict(list)
    ann_fields = ["tissue", "tumorType", "diagnosis", "sex", "age", "species"]
    for _, row in annotations_df.iterrows():
        msn = row.get("modelSystemName")
        if not msn or not str(msn).strip():
            continue
        msn = str(msn).strip()
        for field in ann_fields:
            val = row.get(field)
            parsed = _parse_annotation_value(val)
            msn_index[msn][field].extend(parsed)
        ind_id = row.get("individualID")
        if ind_id and str(ind_id).strip():
            msn_to_ids[msn].append(str(ind_id).strip())
    logger.info(f"  Indexed {len(msn_index):,} unique modelSystemNames")
    return msn_index, msn_to_ids


def query_resource_name_map(
    syn: Synapse,
    resource_type: str,
    id_col: str,
) -> Dict[str, str]:
    """Return {resourceName: id_col_value} for a given resource type.

    Queries syn51730943 (the materialized resources view) which joins the base
    Resource table with each detail table.
    """
    logger.info(f"Querying resource name map for '{resource_type}' ({id_col})…")
    query = (
        f"SELECT resourceName, {id_col} "
        f"FROM {RESOURCES_VIEW_ID} "
        f"WHERE resourceType = '{resource_type}' "
        f"AND {id_col} IS NOT NULL"
    )
    try:
        results = syn.tableQuery(query)
        df = results.asDataFrame()
        df = df.dropna(subset=["resourceName", id_col])
        name_to_id = dict(zip(df["resourceName"].astype(str), df[id_col].astype(str)))
        logger.info(f"  Found {len(name_to_id):,} resources")
        return name_to_id
    except Exception as exc:
        logger.warning(f"  Error querying resource names: {exc}")
        return {}


def query_tool_records(
    syn: Synapse,
    table_id: str,
    id_col: str,
    target_fields: List[str],
    extra_fields: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Query tool table rows where at least one target field is blank.

    Args:
        table_id:      Synapse table ID.
        id_col:        Primary key column name (e.g. 'cellLineId').
        target_fields: Fields to check for blank values and later enrich.
        extra_fields:  Additional columns to retrieve (e.g. 'donorId').

    Returns DataFrame with ROW_ID, ROW_VERSION, id_col, target_fields, extra_fields.
    """
    logger.info(f"Querying {table_id} for rows with blank fields: {target_fields}…")
    null_conditions = " OR ".join(
        [f"({f} IS NULL OR {f} = '')" for f in target_fields]
    )
    select_cols = ["ROW_ID", "ROW_VERSION", id_col] + target_fields
    if extra_fields:
        select_cols += [c for c in extra_fields if c not in select_cols]
    query = f"SELECT {', '.join(select_cols)} FROM {table_id} WHERE {null_conditions}"
    try:
        results = syn.tableQuery(query)
        df = results.asDataFrame()
        logger.info(f"  Found {len(df):,} rows with at least one blank target field")
        return df
    except Exception as exc:
        logger.warning(f"  Error querying {table_id}: {exc}")
        return pd.DataFrame()


# ─── Enrichment logic ─────────────────────────────────────────────────────────

def enrich_table(
    tool_df: pd.DataFrame,
    id_col: str,
    id_to_name: Dict[str, str],
    annotation_index: Dict[str, Dict[str, List]],
    field_map: Dict[str, Tuple[str, Optional[Dict[str, str]]]],
) -> pd.DataFrame:
    """Compute proposed updates for a single tool table.

    Args:
        tool_df:           Rows from the tool table (must include id_col + target columns).
        id_col:            Primary key column.
        id_to_name:        {tool_id: individualID/resourceName} reverse lookup.
        annotation_index:  {individualID: {annotation_field: [values…]}}
        field_map:         {annotation_field: (target_col, canonical_lookup)}
                           target_col is the column name in the tool table.

    Returns:
        DataFrame of rows that have at least one proposed update, with columns:
        [id_col, proposed_target_col…, _match_key].
    """
    updates = []
    for _, row in tool_df.iterrows():
        tool_id = str(row[id_col]) if pd.notna(row[id_col]) else None
        if not tool_id:
            continue
        ind_id = id_to_name.get(tool_id)
        if not ind_id:
            continue
        ann = annotation_index.get(ind_id, {})
        if not ann:
            continue

        proposed: Dict[str, str] = {}
        for ann_field, (target_col, canonical_lookup) in field_map.items():
            # Only enrich if the current value is blank/null
            current = row.get(target_col)
            if not _is_blank(current):
                continue  # Already has a value — skip
            values = ann.get(ann_field, [])
            consensus = compute_consensus(values, canonical_lookup)
            if consensus is not None:
                proposed[target_col] = consensus

        if proposed:
            update_row = {id_col: tool_id, "_match_key": ind_id}
            update_row.update(proposed)
            updates.append(update_row)

    if updates:
        result_df = pd.DataFrame(updates)
        logger.info(f"    → {len(result_df):,} rows with proposed updates")
        return result_df
    logger.info("    → No updates found")
    return pd.DataFrame()


def enrich_donors(
    syn: Synapse,
    msn_index: Dict[str, Dict[str, List]],
    name_to_cell_line_id: Dict[str, str],
    cell_line_df: pd.DataFrame,
) -> pd.DataFrame:
    """Enrich donor records (syn26486829) via cell line → donorId chain.

    Path: modelSystemName (= resourceName) → cellLineId (resource table)
          → donorId (syn26486823) → enrich syn26486829.

    Annotation sex/age/species is read from the MSN index: files annotated with
    a given modelSystemName carry the donor's demographic attributes, so consensus
    across those files gives the donor-level values.

    For donors linked to multiple cell lines we aggregate annotation values
    across all linked model system names before computing consensus.
    """
    logger.info("Enriching donor records via cell line → donorId chain…")

    if cell_line_df.empty or "donorId" not in cell_line_df.columns:
        logger.info("  No cell line rows with donorId available; skipping donor enrichment")
        return pd.DataFrame()

    # Build donorId → [modelSystemNames] map using the resource-name reverse lookup
    cell_line_id_to_name = {v: k for k, v in name_to_cell_line_id.items()}
    donor_to_msns: Dict[str, List[str]] = defaultdict(list)

    for _, row in cell_line_df.iterrows():
        cl_id = str(row.get("cellLineId", "")).strip()
        donor_id = str(row.get("donorId", "")).strip()
        if not cl_id or not donor_id or donor_id.lower() in ("nan", "none", ""):
            continue
        msn = cell_line_id_to_name.get(cl_id)
        if msn:
            donor_to_msns[donor_id].append(msn)

    if not donor_to_msns:
        logger.info("  No donorId → modelSystemName links found; skipping donor enrichment")
        return pd.DataFrame()

    logger.info(f"  Found {len(donor_to_msns):,} unique donorIds with annotation links")

    # Query donor table for rows with blank target fields
    donor_target_fields = ["sex", "age", "species"]
    donor_df = query_tool_records(
        syn, DONOR_TABLE_ID, "donorId", donor_target_fields
    )
    if donor_df.empty:
        logger.info("  No donor rows with blank fields found")
        return pd.DataFrame()

    sex_lookup = build_canonical_lookup(SEX_VALUES, SEX_SYNONYMS)

    updates = []
    for _, row in donor_df.iterrows():
        donor_id = str(row.get("donorId", "")).strip()
        if not donor_id:
            continue
        linked_msns = donor_to_msns.get(donor_id, [])
        if not linked_msns:
            continue

        # Aggregate annotation values across all linked model system names
        agg: Dict[str, List] = defaultdict(list)
        for msn in linked_msns:
            ann = msn_index.get(msn, {})
            for field in ["sex", "age", "species"]:
                agg[field].extend(ann.get(field, []))

        proposed: Dict = {}

        current_sex = row.get("sex")
        if _is_blank(current_sex):
            consensus_sex = compute_consensus(agg["sex"], sex_lookup)
            if consensus_sex:
                proposed["sex"] = consensus_sex

        current_age = row.get("age")
        if _is_blank(current_age):
            age_vals = [str(v).strip() for v in agg["age"] if v is not None and str(v).strip()]
            numeric_ages = []
            for av in age_vals:
                try:
                    fv = float(av)
                    if not (fv != fv):  # exclude NaN (NaN != NaN is True)
                        numeric_ages.append(fv)
                except ValueError:
                    pass
            if numeric_ages and len(set(numeric_ages)) == 1:
                proposed["age"] = numeric_ages[0]

        current_species = row.get("species")
        if _is_blank(current_species):
            consensus_species = compute_consensus(agg["species"], canonical_lookup=None)
            if consensus_species:
                proposed["species"] = consensus_species

        if proposed:
            update_row = {"donorId": donor_id, "_match_key": ",".join(linked_msns[:3])}
            update_row.update(proposed)
            updates.append(update_row)

    if updates:
        result_df = pd.DataFrame(updates)
        logger.info(f"    → {len(result_df):,} donor rows with proposed updates")
        return result_df
    logger.info("    → No donor updates found")
    return pd.DataFrame()


# ─── Output generation ────────────────────────────────────────────────────────

def generate_submit_csvs(
    updates_by_table: Dict[str, pd.DataFrame],
    output_dir: Path,
) -> None:
    """Write SUBMIT_*_updates.csv files to output_dir."""
    file_map = {
        "cell_line": "SUBMIT_cell_line_updates.csv",
        "animal_model": "SUBMIT_animal_model_updates.csv",
        "patient_derived_model": "SUBMIT_patient_derived_model_updates.csv",
        "donor": "SUBMIT_donor_updates.csv",
    }
    for key, df in updates_by_table.items():
        if df is None or df.empty:
            continue
        out_path = output_dir / file_map[key]
        df.to_csv(out_path, index=False)
        logger.info(f"Wrote {len(df):,} rows to {out_path}")


def build_enrichment_summary(updates_by_table: Dict[str, pd.DataFrame]) -> Dict:
    """Build tool_field_enrichment.json summary dict."""
    summary: Dict = {"tables": {}, "total_updates": 0}
    for key, df in updates_by_table.items():
        count = 0 if (df is None or df.empty) else len(df)
        # Count proposed updates per field
        field_counts: Dict[str, int] = {}
        if df is not None and not df.empty:
            for col in df.columns:
                if col.startswith("_") or col.endswith("Id"):
                    continue
                non_null = df[col].notna().sum()
                if non_null:
                    field_counts[col] = int(non_null)
        summary["tables"][key] = {"row_count": count, "fields": field_counts}
        summary["total_updates"] += count
    return summary


def format_enrichment_markdown(summary: Dict) -> str:
    """Format enrichment summary as markdown section for PR body."""
    lines = [
        "\n---\n",
        "## Tool Field Enrichment\n\n",
        "Existing tool records with blank fields have been enriched using consensus "
        "values from NF Portal file annotations (`individualID` match).\n\n",
        f"**Total rows with proposed updates:** {summary['total_updates']}\n\n",
    ]
    for table_key, info in summary["tables"].items():
        display = table_key.replace("_", " ").title()
        lines.append(f"### {display}\n")
        lines.append(f"- Rows: **{info['row_count']}**\n")
        if info["fields"]:
            lines.append("- Fields enriched:\n")
            for field, cnt in info["fields"].items():
                lines.append(f"  - `{field}`: {cnt} values\n")
        lines.append("\n")
    lines.append(
        "See `tool_field_enrichment.json` for machine-readable detail.\n"
        "Enrichment update files (`SUBMIT_*_updates.csv`) will be processed by "
        "`clean_submission_csvs.py` in update-mode (only fills currently-blank fields).\n"
    )
    return "".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich existing Synapse tool records from NF Portal file annotations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed updates without writing files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for SUBMIT_*_updates.csv output files (default: .)",
    )
    args = parser.parse_args()

    auth_token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    syn = Synapse()
    if auth_token:
        syn.login(authToken=auth_token, silent=True)
        logger.info("Logged into Synapse (authenticated)")
    else:
        syn.login(silent=True)  # anonymous — read-only public tables only
        logger.info("Logged into Synapse (anonymous — read-only)")

    # ── 1. Pull all annotation data ─────────────────────────────────────────
    annotations_df = query_annotation_values(syn)
    msn_index, msn_to_ids = build_annotation_index(annotations_df)

    # ── 2. Get resource name → detail-table ID mappings ─────────────────────
    logger.info("\n=== Building resource name maps ===")
    name_to_cell_line_id = query_resource_name_map(syn, "Cell Line", "cellLineId")
    name_to_animal_model_id = query_resource_name_map(syn, "Animal Model", "animalModelId")
    name_to_pdx_id = query_resource_name_map(syn, "Patient-Derived Model", "patientDerivedModelId")

    # Invert for use in enrich_table (tool_id → name)
    cell_line_id_to_name = {v: k for k, v in name_to_cell_line_id.items()}
    animal_model_id_to_name = {v: k for k, v in name_to_animal_model_id.items()}
    pdx_id_to_name = {v: k for k, v in name_to_pdx_id.items()}

    # ── 3. Build canonical lookups ───────────────────────────────────────────
    tissue_lookup = build_canonical_lookup(TISSUE_VALUES)
    cl_manifestation_lookup = build_canonical_lookup(CELL_LINE_MANIFESTATION_VALUES)
    cl_disorder_lookup = build_canonical_lookup(
        CELL_LINE_GENETIC_DISORDER_VALUES, CELL_LINE_DISORDER_SYNONYMS
    )
    am_disorder_lookup = build_canonical_lookup(
        ANIMAL_MODEL_GENETIC_DISORDER_VALUES, ANIMAL_MODEL_DISORDER_SYNONYMS
    )
    am_manifestation_lookup = build_canonical_lookup(ANIMAL_MODEL_MANIFESTATION_VALUES)
    pdx_tumor_lookup = build_canonical_lookup(PDX_TUMOR_TYPE_VALUES)

    # ── 4. Enrich cell lines (syn26486823) ───────────────────────────────────
    logger.info("\n=== Enriching cell lines ===")
    cl_target_fields = ["tissue", "cellLineManifestation", "cellLineGeneticDisorder"]
    cl_df = query_tool_records(
        syn, CELL_LINE_TABLE_ID, "cellLineId", cl_target_fields,
        extra_fields=["donorId"],
    )
    cl_field_map = {
        "tissue":     ("tissue",                  tissue_lookup),
        "tumorType":  ("cellLineManifestation",   cl_manifestation_lookup),
        "diagnosis":  ("cellLineGeneticDisorder", cl_disorder_lookup),
    }
    cl_updates = enrich_table(
        cl_df, "cellLineId", cell_line_id_to_name, msn_index, cl_field_map
    )

    # ── 5. Enrich animal models (syn26486808) ────────────────────────────────
    logger.info("\n=== Enriching animal models ===")
    am_target_fields = ["animalModelGeneticDisorder", "animalModelOfManifestation"]
    am_df = query_tool_records(
        syn, ANIMAL_MODEL_TABLE_ID, "animalModelId", am_target_fields
    )
    am_field_map = {
        "diagnosis": ("animalModelGeneticDisorder",  am_disorder_lookup),
        "tumorType": ("animalModelOfManifestation",  am_manifestation_lookup),
    }
    am_updates = enrich_table(
        am_df, "animalModelId", animal_model_id_to_name, msn_index, am_field_map
    )

    # ── 6. Enrich patient-derived models (syn73709228) ───────────────────────
    logger.info("\n=== Enriching patient-derived models ===")
    pdx_target_fields = ["patientDiagnosis", "tumorType"]
    pdx_df = query_tool_records(
        syn, PDX_TABLE_ID, "patientDerivedModelId", pdx_target_fields
    )
    pdx_field_map = {
        # patientDiagnosis is free text → no canonical lookup (None)
        "diagnosis": ("patientDiagnosis", None),
        "tumorType": ("tumorType",        pdx_tumor_lookup),
    }
    pdx_updates = enrich_table(
        pdx_df, "patientDerivedModelId", pdx_id_to_name, msn_index, pdx_field_map
    )

    # ── 7. Enrich donors (syn26486829) via cell line → donorId chain ─────────
    logger.info("\n=== Enriching donors ===")
    donor_updates = enrich_donors(
        syn, msn_index, name_to_cell_line_id, cl_df
    )

    # ── 8. Summarize and output ──────────────────────────────────────────────
    updates_by_table: Dict[str, pd.DataFrame] = {
        "cell_line":            cl_updates,
        "animal_model":         am_updates,
        "patient_derived_model": pdx_updates,
        "donor":                donor_updates,
    }

    summary = build_enrichment_summary(updates_by_table)

    logger.info("\n=== Enrichment Summary ===")
    for table_key, info in summary["tables"].items():
        logger.info(f"  {table_key}: {info['row_count']} rows with proposed updates")
    logger.info(f"  Total: {summary['total_updates']} updates")

    if args.dry_run:
        print("\n--- DRY RUN: proposed updates (first 10 rows per table) ---")
        for table_key, df in updates_by_table.items():
            if df is not None and not df.empty:
                print(f"\n{table_key}:")
                print(df.head(10).to_string(index=False))
        return

    # Write files
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generate_submit_csvs(updates_by_table, args.output_dir)

    summary_path = args.output_dir / "tool_field_enrichment.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Wrote enrichment summary to {summary_path}")

    markdown_path = args.output_dir / "tool_field_enrichment.md"
    with open(markdown_path, "w") as f:
        f.write(format_enrichment_markdown(summary))
    logger.info(f"Wrote enrichment markdown to {markdown_path}")


if __name__ == "__main__":
    main()
