#!/usr/bin/env python3
"""
Clean SUBMIT_*.csv files by removing tracking columns (prefixed with '_').
Optionally upsert cleaned data to Synapse tables.

These columns are for manual review only and must be removed before
uploading to Synapse.
"""

import json
import pandas as pd
import os
import glob
import argparse
import synapseclient
from synapseclient import Table
from typing import List, Dict, Tuple

SYN_RESOURCES_TABLE = "syn26450069"

# Primary-key column for each detail table — used to skip rows already in Synapse.
_DETAIL_TABLE_PK = {
    "syn26486808": "animalModelId",
    "syn26486811": "antibodyId",
    "syn26486823": "cellLineId",
    "syn26486832": "geneticReagentId",
    "syn26486836": "observationId",
    "syn73709226": "computationalToolId",
    "syn73709227": "organoidProtocolId",
    "syn73709228": "patientDerivedModelId",
    "syn73709229": "clinicalAssessmentToolId",
}


def _run_url_comment() -> str:
    """Return the GitHub Actions run URL for use as a snapshot comment, or '' locally."""
    server = os.getenv("GITHUB_SERVER_URL", "").rstrip("/")
    repo   = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{run_id}" if (server and repo and run_id) else ""

# Mapping of CLEAN_*.csv files to Synapse table IDs
SYNAPSE_TABLE_MAP = {
    # Existing tool types (v1.0)
    'CLEAN_animal_models.csv': 'syn26486808',
    'CLEAN_antibodies.csv': 'syn26486811',
    'CLEAN_cell_lines.csv': 'syn26486823',
    'CLEAN_genetic_reagents.csv': 'syn26486832',

    # Biobank (v2.0)
    'CLEAN_biobanks.csv': 'syn26486821',  # BiobankDetails table

    # New tool types (v2.0) - Created 2026-02-11
    'CLEAN_computational_tools.csv': 'syn73709226',  # ComputationalToolDetails table
    'CLEAN_organoid_protocols.csv': 'syn73709227',  # OrganoidProtocolDetails table
    'CLEAN_patient_derived_models.csv': 'syn73709228',  # PatientDerivedModelDetails table
    'CLEAN_clinical_assessment_tools.csv': 'syn73709229',  # ClinicalAssessmentToolDetails table

    # Vendor / donor tables — syn26486850, syn26486843, syn26486829
    'CLEAN_vendor.csv': 'syn26486850',        # Vendor table
    'CLEAN_donor.csv': 'syn26486829',         # Donor table
    # Note: CLEAN_vendorItem.csv is NOT uploaded here — it needs resourceId resolution
    # via upsert_publication_links.py (run after resources are in Synapse)

    # Common tables
    'CLEAN_resources.csv': 'syn26450069',
    'CLEAN_publications.csv': 'syn26486839',  # Base publication table
    'CLEAN_usage.csv': 'syn26486841',  # Publications where tools were USED
    'CLEAN_development.csv': 'syn26486807',  # Publications where tools were DEVELOPED
    'CLEAN_observations.csv': 'syn26486836',  # Scientific observations about tools
    # Note: syn51735450 is a materialized view that auto-updates from usage + resources
}

# Columns that exist in ACCEPTED_*.csv for routing/tracking purposes but do NOT belong
# in the corresponding Synapse detail table.  They are either stored in a different table
# by upsert_publication_links.py or are handled elsewhere in the pipeline.
_STRIP_BEFORE_UPLOAD = {
    # developerName/Affiliation → investigator table (syn51734029) via upsert_publication_links
    # developerContactEmail → no schema home; dropped
    # itemAcquisition → resource.howToAcquire (syn26450069); handled by generate pipeline
    # Columns after transplantationDonorId not yet in syn26486808 — remove once schema updated:
    'CLEAN_animal_models.csv': [
        'developerName', 'developerAffiliation', 'developerContactEmail', 'itemAcquisition',
        'alleleType', 'affectedGeneSymbol', 'inducedVsDevelopmental', 'bbbIntegrityStatus',
        'routeOfAdministration', 'pkpdCapabilities', 'mechanismOfActionValidation',
        'pediatricSuitability', 'timelineToResults', 'modelLimitations',
        'clinicalTranslationHistory', 'regulatoryAcceptanceHistory', 'mtaRequired',
        'ngnriRepositoryStatus',
    ],
    # vendor/catalogNumber/catalogURL → vendorItem pipeline (upsert_publication_links)
    'CLEAN_antibodies.csv': [
        'vendor', 'catalogNumber', 'catalogURL',
    ],
    # rrid → resource table (syn26450069); developer fields same as animal models
    # licenseDetails not yet in syn73709226 with sufficient length — remove once schema updated:
    'CLEAN_computational_tools.csv': [
        'rrid', 'developerName', 'developerAffiliation', 'itemAcquisition',
        'licenseDetails',
    ],
    # qualityControlMetrics items up to 118 chars — increase maximumStringLength to ≥200 in syn73709227:
    # developerName/developerContactEmail used only for howToAcquire in resources table
    'CLEAN_organoid_protocols.csv': [
        'qualityControlMetrics', 'developerName', 'developerContactEmail',
    ],
    # developerName/developerContactEmail used only for howToAcquire in resources table
    'CLEAN_clinical_assessment_tools.csv': [
        'developerName', 'developerContactEmail',
    ],
    # validationMethods items are 70 chars — increase maximumStringLength to ≥100 in syn73709228:
    # itemAcquisition/developerName/developerAffiliation used only for howToAcquire in resources table
    'CLEAN_patient_derived_models.csv': [
        'validationMethods', 'itemAcquisition', 'developerName', 'developerAffiliation',
    ],
    # v2.0 type-specific FK columns not yet added to syn26450069 schema
    'CLEAN_resources.csv': [
        'computationalToolId', 'organoidProtocolId', 'patientDerivedModelId',
        'clinicalAssessmentToolId',
    ],
    # resourceType/resourceName kept in ACCEPTED for review; strip before Synapse upload.
    # observationTypeOntologyId not in syn26486836 schema.
    'CLEAN_observations.csv': ['resourceType', 'resourceName', 'observationTypeOntologyId'],
}


def get_synapse_table_id(filename):
    """Get Synapse table ID for a given cleaned CSV file."""
    basename = os.path.basename(filename)
    return SYNAPSE_TABLE_MAP.get(basename)


def _get_string_list_columns(syn: synapseclient.Synapse, table_id: str) -> List[str]:
    """Return the names of STRING_LIST columns in a Synapse table."""
    try:
        schema = syn.get(table_id)
        cols = list(syn.getColumns(schema))
        return [c.name for c in cols if getattr(c, 'columnType', '') == 'STRING_LIST']
    except Exception as e:
        print(f"      ⚠️  Could not fetch schema for {table_id}: {e}")
        return []


def _smart_split(val: str, sep: str = ',') -> List[str]:
    """Split on sep but not inside parentheses or brackets."""
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in val:
        if ch in '([':
            depth += 1
            current.append(ch)
        elif ch in ')]':
            depth -= 1
            current.append(ch)
        elif ch == sep and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    return [p for p in parts if p]


def _serialize_string_lists(df: pd.DataFrame, string_list_cols: List[str]) -> pd.DataFrame:
    """Convert STRING_LIST columns from plain comma-separated strings to JSON arrays.

    compile_accepted_submissions._fmt_list() produces comma-joined strings
    (e.g. "French, English").  Synapse requires JSON arrays (["French","English"]).
    Commas inside parentheses (e.g. "IHC (S100, CD34)") are not treated as delimiters.
    """
    if not string_list_cols:
        return df
    df = df.copy()

    def _to_json_array(val):
        if pd.isna(val) or val == '' or val == 'NULL':
            return None
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return val  # already a valid JSON array
            except (json.JSONDecodeError, ValueError):
                pass
            items = _smart_split(val)
            return json.dumps(items)
        if isinstance(val, list):
            return json.dumps([str(v) for v in val if v])
        return json.dumps([str(val)])

    for col in string_list_cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_json_array)
    return df

def validate_csv_schema(df: pd.DataFrame, file_type: str) -> Tuple[bool, List[str]]:
    """Validate CSV against expected schema requirements.

    Args:
        df: DataFrame to validate
        file_type: Type of CSV (animal_models, antibodies, cell_lines, genetic_reagents, etc.)

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Define required columns for each type (verified against live Synapse tables)
    required_columns = {
        # Existing tool types (v1.0) — syn26486808, syn26486811, syn26486823, syn26486832
        'animal_models': ['strainNomenclature'],
        'antibodies': ['targetAntigen'],
        'cell_lines': ['organ'],
        'genetic_reagents': ['insertName'],

        # New tool types (v2.0) — syn73709226-syn73709229
        'computational_tools': ['softwareName', 'softwareType'],
        'organoid_protocols': ['modelType', 'derivationSource'],
        'patient_derived_models': ['modelSystemType', 'patientDiagnosis'],
        'clinical_assessment_tools': ['assessmentName', 'assessmentType', 'targetPopulation'],

        # Vendor / donor tables
        'vendor': ['vendorId', 'vendorName'],
        'donor': ['donorId', 'species'],

        # Common tables
        'publications': ['publicationId', 'pmid'],
        'usage': ['usageId', 'publicationId', 'resourceId'],
        'development': ['publicationDevelopmentId', 'publicationId', 'resourceId'],
        'publication_links': ['resourceId'],  # Existing tool links (materialized view)
        'resources': ['resourceName', 'resourceType'],
        'observations': ['observationId', 'resourceType', 'resourceName', 'observationType', 'observationText']
    }

    # Extract type name from filename stem (exact match to avoid e.g. "vendor" matching "vendorItem")
    import re as _re
    m = _re.search(r'(?:ACCEPTED|CLEAN|SUBMIT)_(\w+)\.csv', os.path.basename(file_type))
    file_stem = m.group(1) if m else ''
    if file_stem not in required_columns:
        return True, []
    req_cols = required_columns[file_stem]

    # Check for required columns
    missing_cols = [col for col in req_cols if col not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}")

    # Check for empty required fields
    for col in req_cols:
        if col in df.columns:
            null_count = df[col].isna().sum()
            if null_count > 0:
                errors.append(f"Column '{col}' has {null_count} null/empty values")

    # Check for completely empty rows
    empty_rows = df.isna().all(axis=1).sum()
    if empty_rows > 0:
        errors.append(f"Found {empty_rows} completely empty rows")

    return len(errors) == 0, errors

def clean_csv(input_file):
    """Remove columns prefixed with '_' from CSV and save cleaned version.

    Returns:
        tuple: (output_file, df_clean) - Path to cleaned file and cleaned DataFrame
    """
    df = pd.read_csv(input_file)

    # Find columns that start with '_'
    tracking_cols = [col for col in df.columns if col.startswith('_')]

    if not tracking_cols:
        print(f"   {input_file}: No tracking columns to remove")
        # Still save even if no tracking columns
        output_file = input_file.replace('ACCEPTED_', 'CLEAN_')
        df.to_csv(output_file, index=False)
        return output_file, df

    # Remove tracking columns
    df_clean = df.drop(columns=tracking_cols)

    # Save to CLEAN_ prefixed file
    output_file = input_file.replace('ACCEPTED_', 'CLEAN_')
    df_clean.to_csv(output_file, index=False)

    print(f"   {input_file}: Removed {len(tracking_cols)} columns → {output_file}")
    print(f"      Removed: {', '.join(tracking_cols)}")

    return output_file, df_clean

def upsert_to_synapse(syn, clean_file, df_clean):
    """Upsert cleaned data to Synapse table.

    Strips routing columns (those belonging to other Synapse tables), serializes
    STRING_LIST columns to JSON arrays, then appends new rows.  Creates a snapshot
    version after each successful upload.

    Args:
        syn: Synapse client
        clean_file: Path to cleaned CSV file
        df_clean: Cleaned DataFrame to upload

    Returns:
        bool: True if successful, False otherwise
    """
    table_id = get_synapse_table_id(clean_file)

    if not table_id:
        print(f"      ⚠️  No Synapse table mapping for {os.path.basename(clean_file)}")
        return False

    if df_clean.empty:
        print(f"      ⚠️  Empty DataFrame, skipping upload")
        return False

    basename = os.path.basename(clean_file)

    # Strip columns that belong to other tables
    cols_to_strip = [c for c in _STRIP_BEFORE_UPLOAD.get(basename, []) if c in df_clean.columns]
    if cols_to_strip:
        df_clean = df_clean.drop(columns=cols_to_strip)
        print(f"      ℹ️  Stripped {cols_to_strip} (routed to other tables)")

    # Serialize STRING_LIST columns to JSON arrays
    string_list_cols = _get_string_list_columns(syn, table_id)
    present_sl = [c for c in string_list_cols if c in df_clean.columns]
    if present_sl:
        df_clean = _serialize_string_lists(df_clean, present_sl)
        print(f"      ℹ️  Serialized STRING_LIST columns: {present_sl}")

    try:
        # For the Resources table, skip rows whose (resourceName, resourceType) pair is
        # already in Synapse to prevent duplicate name+type entries.  We check by name+type
        # (not resourceId) because that is the lookup key used by upsert_publication_links.py
        # and because ID format may differ between pipeline runs.  Real metadata updates to
        # existing resources should go through generate_review_csv.py, which preserves
        # curated fields; uploading here would blank them out.
        if table_id == SYN_RESOURCES_TABLE and "resourceName" in df_clean.columns:
            existing_res = syn.tableQuery(
                f"SELECT resourceName, resourceType FROM {SYN_RESOURCES_TABLE}"
            ).asDataFrame()
            existing_keys = set(
                zip(
                    existing_res["resourceName"].str.lower().fillna(""),
                    existing_res["resourceType"].fillna(""),
                )
            ) if len(existing_res) > 0 else set()
            before = len(df_clean)
            mask = df_clean.apply(
                lambda r: (str(r["resourceName"]).lower(), str(r.get("resourceType", ""))) not in existing_keys,
                axis=1,
            )
            df_clean = df_clean[mask].copy()
            skipped = before - len(df_clean)
            if skipped:
                print(f"      ℹ️  Skipped {skipped} resource(s) already registered in Synapse")
            if df_clean.empty:
                print(f"      ✅ No new resources to upload to {table_id}")
                return True

        elif table_id in _DETAIL_TABLE_PK:
            pk_col = _DETAIL_TABLE_PK[table_id]
            if pk_col in df_clean.columns:
                try:
                    existing = syn.tableQuery(
                        f"SELECT {pk_col} FROM {table_id}"
                    ).asDataFrame()
                    existing_pks = set(existing[pk_col].dropna())
                    before = len(df_clean)
                    df_clean = df_clean[~df_clean[pk_col].isin(existing_pks)].copy()
                    skipped = before - len(df_clean)
                    if skipped:
                        print(f"      ℹ️  Skipped {skipped} row(s) already in {table_id} (by {pk_col})")
                    if df_clean.empty:
                        print(f"      ✅ No new rows to upload to {table_id}")
                        return True
                except Exception as e:
                    print(f"      ⚠️  Could not check existing {pk_col}s in {table_id}: {e} — uploading without dedup")

        table = Table(table_id, df_clean)
        table = syn.store(table)

        print(f"      ✅ Uploaded {len(df_clean)} rows to {table_id}")
        print(f"         Creating snapshot version...")
        syn.create_snapshot_version(table_id, comment=_run_url_comment() or None)
        print(f"         ✅ Snapshot version created")

        return True

    except Exception as e:
        print(f"      ❌ Error uploading to {table_id}: {str(e)}")
        return False

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Clean SUBMIT_*.csv files and optionally upsert to Synapse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Clean CSVs only (default)
  python clean_submission_csvs.py

  # Clean and upsert to Synapse
  python clean_submission_csvs.py --upsert

  # Dry run (show what would be uploaded without uploading)
  python clean_submission_csvs.py --upsert --dry-run
        """
    )
    parser.add_argument(
        '--upsert',
        action='store_true',
        help='Upload cleaned data to Synapse tables'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be uploaded without actually uploading (requires --upsert)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate CSV schema before cleaning/upserting'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("CLEANING SUBMISSION CSVs FOR SYNAPSE UPLOAD")
    print("=" * 80)
    print("\nRemoving tracking columns (prefixed with '_') from ACCEPTED_*.csv files...")
    print("These columns are for manual review only.\n")

    if args.upsert:
        if args.dry_run:
            print("🔍 DRY RUN MODE - No data will be uploaded\n")
        else:
            print("⚠️  UPSERT MODE - Data will be uploaded to Synapse!\n")

    # Find all ACCEPTED_*.csv files — check both repo root and tool_coverage/outputs/
    submit_files = glob.glob('ACCEPTED_*.csv') + glob.glob('tool_coverage/outputs/ACCEPTED_*.csv')
    submit_files = sorted(set(submit_files))

    if not submit_files:
        print("❌ No ACCEPTED_*.csv files found (checked . and tool_coverage/outputs/)!")
        return

    print(f"Found {len(submit_files)} files to clean:\n")

    # Initialize Synapse client if upserting
    syn = None
    if args.upsert and not args.dry_run:
        try:
            print("Connecting to Synapse...")
            syn = synapseclient.Synapse()
            syn.login()
            print("✅ Connected to Synapse\n")
        except Exception as e:
            print(f"❌ Failed to connect to Synapse: {str(e)}")
            print("Continuing with cleaning only...\n")
            args.upsert = False

    # Process each file
    upload_summary = []
    validation_errors = []

    for file in sorted(submit_files):
        # Validate if requested
        if args.validate:
            df_to_validate = pd.read_csv(file)
            is_valid, errors = validate_csv_schema(df_to_validate, file)
            if not is_valid:
                print(f"\n   ❌ Validation failed for {file}:")
                for error in errors:
                    print(f"      - {error}")
                validation_errors.append((file, errors))
                continue  # Skip this file
            else:
                print(f"   ✅ Validation passed for {file}")

        clean_file, df_clean = clean_csv(file)

        # Upsert if requested
        if args.upsert and not args.dry_run:
            if not get_synapse_table_id(clean_file):
                print(f"      ⏭️  {os.path.basename(clean_file)} — no Synapse table mapping (handled elsewhere)")
            else:
                success = upsert_to_synapse(syn, clean_file, df_clean)
                upload_summary.append((clean_file, len(df_clean), success))
        elif args.dry_run:
            table_id = get_synapse_table_id(clean_file)
            if table_id:
                print(f"      🔍 Would upload {len(df_clean)} rows to {table_id}")
                upload_summary.append((clean_file, len(df_clean), None))

    # Print summary
    print("\n" + "=" * 80)
    print("CLEANING COMPLETE")
    print("=" * 80)

    if validation_errors:
        print("\n⚠️  VALIDATION ERRORS:")
        for file, errors in validation_errors:
            print(f"\n   {file}:")
            for error in errors:
                print(f"      - {error}")
        print("\n❌ Some files failed validation and were skipped")
        print("   Fix the errors above before uploading to Synapse")
        return
    elif args.validate:
        print("\n✅ All files passed validation")

    print("\n✅ Clean files saved with CLEAN_* prefix")

    if args.upsert and not args.dry_run:
        print("\n📊 UPLOAD SUMMARY:")
        total_rows = 0
        success_count = 0
        for clean_file, row_count, success in upload_summary:
            total_rows += row_count
            if success:
                success_count += 1
                status = "✅"
            else:
                status = "❌"
            print(f"   {status} {os.path.basename(clean_file)}: {row_count} rows")

        print(f"\n   Total: {success_count}/{len(upload_summary)} tables uploaded successfully")
        print(f"   Total rows: {total_rows}")

    elif args.dry_run:
        print("\n📊 DRY RUN SUMMARY:")
        total_rows = sum(count for _, count, _ in upload_summary)
        print(f"   Would upload {len(upload_summary)} files")
        print(f"   Would upload {total_rows} total rows")

    else:
        print("\n⚠️  Review CLEAN_*.csv files before uploading to Synapse")
        print("⚠️  Verify all required fields are filled in")
        print("\n💡 To upload to Synapse, run: python clean_submission_csvs.py --upsert")

if __name__ == "__main__":
    main()
