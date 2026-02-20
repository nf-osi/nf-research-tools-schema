#!/usr/bin/env python3
"""
Clean SUBMIT_*.csv files by removing tracking columns (prefixed with '_').
Optionally upsert cleaned data to Synapse tables.

These columns are for manual review only and must be removed before
uploading to Synapse.
"""

import pandas as pd
import os
import glob
import argparse
import synapseclient
from synapseclient import Table
from typing import List, Dict, Tuple

# Mapping of CLEAN_*.csv files to Synapse table IDs
SYNAPSE_TABLE_MAP = {
    # Existing tool types (v1.0)
    'CLEAN_animal_models.csv': 'syn26486808',
    'CLEAN_antibodies.csv': 'syn26486811',
    'CLEAN_cell_lines.csv': 'syn26486823',
    'CLEAN_genetic_reagents.csv': 'syn26486832',

    # New tool types (v2.0) - Created 2026-02-11
    'CLEAN_computational_tools.csv': 'syn73709226',  # ComputationalToolDetails table
    'CLEAN_advanced_cellular_models.csv': 'syn73709227',  # AdvancedCellularModelDetails table
    'CLEAN_patient_derived_models.csv': 'syn73709228',  # PatientDerivedModelDetails table
    'CLEAN_clinical_assessment_tools.csv': 'syn73709229',  # ClinicalAssessmentToolDetails table

    # Common tables
    'CLEAN_resources.csv': 'syn26450069',
    'CLEAN_publications.csv': 'syn26486839',  # Base publication table
    'CLEAN_usage.csv': 'syn26486841',  # Publications where tools were USED
    'CLEAN_development.csv': 'syn26486807',  # Publications where tools were DEVELOPED
    'CLEAN_observations.csv': 'syn26486836',  # Scientific observations about tools
    # Note: syn51735450 is a materialized view that auto-updates from usage + resources

    # Enrichment updates (update-mode: fill blank fields in existing rows)
    'CLEAN_cell_line_updates.csv': 'syn26486823',
    'CLEAN_animal_model_updates.csv': 'syn26486808',
    'CLEAN_patient_derived_model_updates.csv': 'syn73709228',
    'CLEAN_donor_updates.csv': 'syn26486829',
}

# Files that should be processed in update-mode (fill blank fields only,
# never append new rows, never overwrite existing values).
UPDATE_MODE_FILES = {
    'CLEAN_cell_line_updates.csv',
    'CLEAN_animal_model_updates.csv',
    'CLEAN_patient_derived_model_updates.csv',
    'CLEAN_donor_updates.csv',
}

# Primary key column for each update-mode file (used to match rows)
UPDATE_MODE_MATCH_COL = {
    'CLEAN_cell_line_updates.csv': 'cellLineId',
    'CLEAN_animal_model_updates.csv': 'animalModelId',
    'CLEAN_patient_derived_model_updates.csv': 'patientDerivedModelId',
    'CLEAN_donor_updates.csv': 'donorId',
}

def get_synapse_table_id(filename):
    """Get Synapse table ID for a given cleaned CSV file."""
    basename = os.path.basename(filename)
    return SYNAPSE_TABLE_MAP.get(basename)

def validate_csv_schema(df: pd.DataFrame, file_type: str) -> Tuple[bool, List[str]]:
    """Validate CSV against expected schema requirements.

    Args:
        df: DataFrame to validate
        file_type: Type of CSV (animal_models, antibodies, cell_lines, genetic_reagents, etc.)

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Define required columns for each type
    required_columns = {
        # Existing tool types (v1.0)
        'animal_models': ['name', 'species'],
        'antibodies': ['targetAntigen'],
        'cell_lines': ['organ'],
        'genetic_reagents': ['insertName'],

        # New tool types (v2.0)
        'computational_tools': ['softwareName', 'softwareType'],
        'advanced_cellular_models': ['modelType', 'derivationSource'],
        'patient_derived_models': ['modelSystemType', 'patientDiagnosis'],
        'clinical_assessment_tools': ['assessmentName', 'assessmentType', 'targetPopulation'],

        # Common tables
        'publications': ['publicationId', 'pmid'],
        'usage': ['usageId', 'publicationId', 'resourceId'],
        'development': ['publicationDevelopmentId', 'publicationId', 'resourceId'],
        'publication_links': ['resourceId'],  # Existing tool links (materialized view)
        'resources': ['resourceName', 'resourceType'],
        'observations': ['resourceId', 'resourceType', 'resourceName', 'observationType', 'details']
    }

    # Extract file type from filename
    for key in required_columns.keys():
        if key in file_type:
            req_cols = required_columns[key]
            break
    else:
        # Unknown type, skip validation
        return True, []

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
        output_file = input_file.replace('SUBMIT_', 'CLEAN_')
        df.to_csv(output_file, index=False)
        return output_file, df

    # Remove tracking columns
    df_clean = df.drop(columns=tracking_cols)

    # Save to CLEAN_ prefixed file
    output_file = input_file.replace('SUBMIT_', 'CLEAN_')
    df_clean.to_csv(output_file, index=False)

    print(f"   {input_file}: Removed {len(tracking_cols)} columns → {output_file}")
    print(f"      Removed: {', '.join(tracking_cols)}")

    return output_file, df_clean

def update_existing_rows(syn, table_id: str, df_updates: pd.DataFrame, match_col: str) -> bool:
    """Update blank fields in existing Synapse table rows.

    Safe, idempotent update that only fills currently-blank/null fields.
    Never overwrites a field that already has a value.

    Workflow:
    1. Query the full current table (all rows and columns) to get ROW_ID, ROW_VERSION.
    2. Merge with df_updates on match_col.
    3. For each update field: set value only when the current cell is blank/null.
    4. Store only the rows that were actually changed (with ROW_ID + ROW_VERSION,
       which triggers an in-place Synapse update rather than an append).

    Args:
        syn:        Authenticated Synapse client.
        table_id:   Synapse table ID (e.g. 'syn26486823').
        df_updates: DataFrame with proposed new values.  Must contain match_col.
                    Tracking columns (starting with '_') have already been removed.
        match_col:  Column name used to join df_updates with the live table
                    (e.g. 'cellLineId').

    Returns:
        True if at least one row was successfully updated, False otherwise.
    """
    if df_updates.empty:
        print(f"      ⚠️  Empty update DataFrame, skipping {table_id}")
        return False

    if match_col not in df_updates.columns:
        print(f"      ⚠️  match_col '{match_col}' not in update DataFrame; skipping {table_id}")
        return False

    # Columns in df_updates that carry actual values to write (exclude match col)
    update_cols = [c for c in df_updates.columns if c != match_col]
    if not update_cols:
        print(f"      ⚠️  No update columns found (beyond match_col); skipping {table_id}")
        return False

    try:
        # ── Step 1: Read current table state ─────────────────────────────────
        print(f"      Reading current state of {table_id}…")
        results = syn.tableQuery(f"SELECT * FROM {table_id}")
        current_df = results.asDataFrame()

        if current_df.empty:
            print(f"      ⚠️  Table {table_id} is empty; skipping update")
            return False

        if match_col not in current_df.columns:
            print(f"      ⚠️  match_col '{match_col}' not found in {table_id}; skipping")
            return False

        # Ensure match key is string for reliable joins
        current_df[match_col] = current_df[match_col].astype(str)
        df_updates[match_col] = df_updates[match_col].astype(str)

        # ── Step 2: Merge proposed updates with current table ─────────────────
        merged = current_df.merge(
            df_updates[[match_col] + update_cols].rename(
                columns={c: f"__new_{c}" for c in update_cols}
            ),
            on=match_col,
            how='inner',
        )

        if merged.empty:
            print(f"      ⚠️  No matching rows found in {table_id} for proposed updates")
            return False

        # ── Step 3: Apply updates — only fill blank/null cells ────────────────
        changed_indices = set()
        for col in update_cols:
            if col not in current_df.columns:
                print(f"         Skipping unknown column '{col}' (not in table)")
                continue
            new_col = f"__new_{col}"
            # Identify rows where current value is blank AND new value is not blank
            current_blank = merged[col].isna() | (merged[col].astype(str).str.strip() == '')
            new_not_blank = merged[new_col].notna() & (merged[new_col].astype(str).str.strip() != '')
            to_fill = current_blank & new_not_blank
            if to_fill.any():
                merged.loc[to_fill, col] = merged.loc[to_fill, new_col]
                changed_indices.update(merged.index[to_fill].tolist())
                print(f"         '{col}': {to_fill.sum()} cells to fill")

        # Drop the temporary __new_* columns
        new_cols_to_drop = [f"__new_{c}" for c in update_cols]
        merged = merged.drop(columns=[c for c in new_cols_to_drop if c in merged.columns])

        if not changed_indices:
            print(f"      ℹ️  All target fields already populated in {table_id}; no changes needed")
            return True

        # ── Step 4: Store only modified rows back to Synapse ─────────────────
        rows_to_store = merged.loc[list(changed_indices)]
        print(f"      Storing {len(rows_to_store)} modified rows to {table_id}…")
        table = Table(table_id, rows_to_store)
        syn.store(table)

        print(f"      ✅ Updated {len(rows_to_store)} rows in {table_id}")
        print(f"         Creating snapshot version…")
        syn.create_snapshot_version(table_id)
        print(f"         ✅ Snapshot version created")
        return True

    except Exception as exc:
        print(f"      ❌ Error updating {table_id}: {exc}")
        return False


def upsert_to_synapse(syn, clean_file, df_clean):
    """Dispatch to the correct upload handler for a cleaned CSV file.

    • Update-mode files (CLEAN_*_updates.csv): call update_existing_rows() to
      fill only currently-blank fields in existing rows.
    • All other files: append new rows to the Synapse table.

    After uploading, creates a snapshot version of the table to track this update.

    Args:
        syn: Synapse client
        clean_file: Path to cleaned CSV file
        df_clean: Cleaned DataFrame to upload

    Returns:
        bool: True if successful, False otherwise
    """
    # Get Synapse table ID for this file
    table_id = get_synapse_table_id(clean_file)

    if not table_id:
        print(f"      ⚠️  No Synapse table mapping for {os.path.basename(clean_file)}")
        return False

    if df_clean.empty:
        print(f"      ⚠️  Empty DataFrame, skipping upload")
        return False

    basename = os.path.basename(clean_file)

    # ── Update-mode: fill blank fields in existing rows ───────────────────────
    if basename in UPDATE_MODE_FILES:
        match_col = UPDATE_MODE_MATCH_COL.get(basename)
        if not match_col:
            print(f"      ⚠️  No match column configured for {basename}; skipping")
            return False
        print(f"      🔄 Update-mode: filling blank fields in {table_id} (match on '{match_col}')")
        return update_existing_rows(syn, table_id, df_clean, match_col)

    # ── Standard mode: append new rows ───────────────────────────────────────
    try:
        # Store the DataFrame to Synapse table
        # This appends new rows to the existing table
        table = Table(table_id, df_clean)
        table = syn.store(table)

        # Create a snapshot version to track this update
        print(f"      ✅ Uploaded {len(df_clean)} rows to {table_id}")
        print(f"         Creating snapshot version...")
        syn.create_snapshot_version(table_id)
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
    print("\nRemoving tracking columns (prefixed with '_') from SUBMIT_*.csv files...")
    print("These columns are for manual review only.\n")

    if args.upsert:
        if args.dry_run:
            print("🔍 DRY RUN MODE - No data will be uploaded\n")
        else:
            print("⚠️  UPSERT MODE - Data will be uploaded to Synapse!\n")

    # Find all SUBMIT_*.csv files
    submit_files = glob.glob('SUBMIT_*.csv')

    if not submit_files:
        print("❌ No SUBMIT_*.csv files found!")
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
            success = upsert_to_synapse(syn, clean_file, df_clean)
            upload_summary.append((clean_file, len(df_clean), success))
        elif args.dry_run:
            table_id = get_synapse_table_id(clean_file)
            if table_id:
                basename = os.path.basename(clean_file)
                if basename in UPDATE_MODE_FILES:
                    match_col = UPDATE_MODE_MATCH_COL.get(basename, '?')
                    print(f"      🔍 Would update {len(df_clean)} rows in {table_id} (update-mode, match on '{match_col}')")
                else:
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
