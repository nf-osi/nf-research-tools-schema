#!/usr/bin/env python3
"""
Script to clean and upsert tool dataset links to Synapse.

This script:
1. Reads SUBMIT_tool_datasets.csv
2. Validates the data
3. Adds or updates the 'datasets' column in syn26486839
4. Upserts the data to Synapse
5. Creates a snapshot version
6. Creates/updates a Dataset table with dataset information from syn50913342

Requires: synapseclient >= 4.4.0
"""

import os
import sys
from pathlib import Path
import synapseclient
import pandas as pd
from typing import List

# Try to import new API (synapseclient >= 4.9.0)
try:
    from synapseclient.models import Table as TableModel
    USE_NEW_API = True
except ImportError:
    USE_NEW_API = False


def clean_csv(input_file: Path, output_file: Path) -> pd.DataFrame:
    """
    Clean the submission CSV by removing tracking columns.

    Args:
        input_file: Path to SUBMIT_*.csv
        output_file: Path to write CLEAN_*.csv

    Returns:
        Cleaned DataFrame
    """
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)

    print(f"  - Original shape: {df.shape}")
    print(f"  - Columns: {list(df.columns)}")

    # Remove any tracking columns that start with underscore or contain metadata
    tracking_cols = [col for col in df.columns if col.startswith('_') or col.startswith('ROW_')]

    if tracking_cols:
        print(f"  - Removing tracking columns: {tracking_cols}")
        df = df.drop(columns=tracking_cols)

    # Write cleaned CSV
    df.to_csv(output_file, index=False)
    print(f"  ✓ Cleaned CSV written to: {output_file}")
    print(f"  - Final shape: {df.shape}")

    return df


def validate_schema(df: pd.DataFrame) -> bool:
    """
    Validate that the DataFrame has the required columns.

    Args:
        df: DataFrame to validate

    Returns:
        True if valid, raises exception otherwise
    """
    print("\nValidating schema...")

    required_cols = ['datasets']  # At minimum we need the datasets column
    # Also need at least one identifier column
    identifier_cols = ['publicationId', 'id', 'ROW_ID', 'pmid', 'resourceId']

    has_datasets = 'datasets' in df.columns
    has_identifier = any(col in df.columns for col in identifier_cols)

    if not has_datasets:
        raise ValueError("Missing required column: 'datasets'")

    if not has_identifier:
        raise ValueError(f"Missing identifier column. Need at least one of: {identifier_cols}")

    # Check for empty dataframe
    if df.empty:
        raise ValueError("DataFrame is empty")

    print("  ✓ Schema validation passed")
    print(f"  - Rows: {len(df)}")
    print(f"  - Has datasets column: {has_datasets}")
    print(f"  - Identifier columns present: {[col for col in identifier_cols if col in df.columns]}")

    return True


def ensure_datasets_column_exists(syn: synapseclient.Synapse, table_id: str) -> bool:
    """
    Check if 'datasets' column exists in the table, and add it if not.

    Args:
        syn: Authenticated Synapse client
        table_id: Synapse ID of the table

    Returns:
        True if column exists or was added successfully
    """
    print(f"\nChecking if 'datasets' column exists in {table_id}...")

    try:
        # Get table schema
        if USE_NEW_API:
            table_model = TableModel(id=table_id)
            table_model = table_model.get(synapse_client=syn)

            if isinstance(table_model.columns, dict):
                column_names = list(table_model.columns.keys())
            elif isinstance(table_model.columns, list):
                column_names = [col.name for col in table_model.columns]
            else:
                column_names = []
        else:
            table = syn.get(table_id)
            column_names = [col['name'] for col in table.columns_to_store]

        if 'datasets' in column_names:
            print("  ✓ Column 'datasets' already exists")
            return True

        # Column doesn't exist, add it
        print("  - Column 'datasets' not found, adding it...")

        new_column = synapseclient.Column(
            name='datasets',
            columnType='STRING',
            maximumSize=1000,  # Allow for multiple comma-separated IDs
            defaultValue=''
        )

        # Add column to schema (use old API for both cases since new API column addition is complex)
        if USE_NEW_API:
            # Get table using old API for column addition
            table = syn.get(table_id)

        table.addColumn(new_column)
        syn.store(table)

        print("  ✓ Column 'datasets' added successfully")
        return True

    except Exception as e:
        print(f"  ✗ Error ensuring column exists: {e}")
        raise


def upsert_datasets_column(syn: synapseclient.Synapse, table_id: str, data_df: pd.DataFrame, dry_run: bool = False):
    """
    Upsert the datasets column to the Synapse table.

    This updates existing rows with the new datasets column values.

    Args:
        syn: Authenticated Synapse client
        table_id: Synapse ID of the target table
        data_df: DataFrame with data to upsert
        dry_run: If True, validate but don't actually upsert
    """
    print(f"\nUpserting data to {table_id}...")
    if dry_run:
        print("  (DRY-RUN MODE - validation only)")

    # Ensure the datasets column exists
    ensure_datasets_column_exists(syn, table_id)

    # Get current table data to find ROW_IDs
    print("  - Fetching current table data...")

    if USE_NEW_API:
        table = TableModel(id=table_id)
        current_data = table.query(f"SELECT * FROM {table_id}", synapse_client=syn)
    else:
        current_data = syn.tableQuery(f"SELECT * FROM {table_id}").asDataFrame()

    print(f"    Retrieved {len(current_data)} rows from table")

    # Determine which column to use for matching
    # Priority: publicationId > pmid + resourceId > pmid
    if 'publicationId' in data_df.columns and 'publicationId' in current_data.columns:
        match_col = 'publicationId'
    elif 'pmid' in data_df.columns and 'pmid' in current_data.columns:
        match_col = 'pmid'
    else:
        raise ValueError("Cannot find matching column between submission and table data")

    print(f"  - Matching rows by column: {match_col}")

    # Build update dataframe with ROW_ID and datasets
    update_rows = []

    for idx, row in data_df.iterrows():
        match_value = row[match_col]

        # Find matching row(s) in current data
        if match_col == 'pmid' and 'resourceId' in data_df.columns and 'resourceId' in current_data.columns:
            # Match by both pmid and resourceId for better accuracy
            matches = current_data[
                (current_data['pmid'] == match_value) &
                (current_data['resourceId'] == row['resourceId'])
            ]
        else:
            # Match by single column
            matches = current_data[current_data[match_col] == match_value]

        if len(matches) == 0:
            print(f"    Warning: No match found for {match_col}={match_value}")
            continue

        # Update each matching row
        for _, match_row in matches.iterrows():
            update_rows.append({
                'ROW_ID': match_row['ROW_ID'],
                'ROW_VERSION': match_row['ROW_VERSION'],
                'datasets': row['datasets']
            })

    if not update_rows:
        print("  ✗ No rows to update")
        return

    print(f"  - Prepared {len(update_rows)} rows for update")

    # Create update dataframe
    update_df = pd.DataFrame(update_rows)

    if dry_run:
        print("\n  📊 DRY-RUN SUMMARY:")
        print(f"    - Would update {len(update_rows)} rows in {table_id}")
        print(f"    - Preview of first 3 updates:")
        for idx, row in update_df.head(3).iterrows():
            print(f"      ROW_ID {row['ROW_ID']}: datasets={row['datasets'][:50]}...")
        print("\n  ✓ Dry-run validation complete - no changes made")
    else:
        # Store updates to Synapse
        print("  - Uploading updates to Synapse...")
        table = synapseclient.Table(table_id, update_df)
        syn.store(table)

        print("  ✓ Data upserted successfully")

        # Create snapshot version
        print("  - Creating snapshot version...")
        syn.create_snapshot_version(table_id)
        print("  ✓ Snapshot version created")

        print(f"\n✓ Upsert complete!")
        print(f"  - Updated {len(update_rows)} rows in {table_id}")
        print(f"  - View at: https://www.synapse.org/#!Synapse:{table_id}")


def get_all_dataset_ids(syn: synapseclient.Synapse, table_id: str) -> set:
    """
    Get all unique dataset IDs from the datasets column in the table.

    Args:
        syn: Authenticated Synapse client
        table_id: Synapse ID of the tool publications table

    Returns:
        Set of unique dataset IDs
    """
    print(f"\nExtracting dataset IDs from {table_id}...")

    # Query the datasets column
    query = f"SELECT datasets FROM {table_id}"

    if USE_NEW_API:
        table = TableModel(id=table_id)
        result = table.query(query, synapse_client=syn)
    else:
        result = syn.tableQuery(query).asDataFrame()

    # Parse comma-separated dataset IDs
    all_dataset_ids = set()

    for datasets_str in result['datasets'].dropna():
        if datasets_str and datasets_str != '':
            # Split by comma and strip whitespace
            dataset_ids = [d.strip() for d in str(datasets_str).split(',') if d.strip()]
            all_dataset_ids.update(dataset_ids)

    print(f"  ✓ Found {len(all_dataset_ids)} unique dataset IDs")

    return all_dataset_ids


def get_dataset_info(syn: synapseclient.Synapse, dataset_collection_id: str,
                     dataset_ids: set) -> pd.DataFrame:
    """
    Get dataset information from the NF portal dataset collection.

    Args:
        syn: Authenticated Synapse client
        dataset_collection_id: Synapse ID of the dataset collection (syn50913342)
        dataset_ids: Set of dataset IDs to filter for

    Returns:
        DataFrame with dataset information
    """
    print(f"\nFetching dataset information from {dataset_collection_id}...")

    # Query all datasets from the collection
    query = f"SELECT * FROM {dataset_collection_id}"

    if USE_NEW_API:
        table = TableModel(id=dataset_collection_id)
        all_datasets = table.query(query, synapse_client=syn)
    else:
        all_datasets = syn.tableQuery(query).asDataFrame()

    print(f"  - Retrieved {len(all_datasets)} total datasets from collection")

    # Filter to only datasets referenced in tool publications
    # Check what the ID column is called in the dataset collection
    id_columns = ['id', 'datasetId', 'synId', 'synapseId']
    id_col = None

    for col in id_columns:
        if col in all_datasets.columns:
            id_col = col
            break

    if id_col is None:
        print(f"  Warning: Could not find ID column in dataset collection")
        print(f"  Available columns: {list(all_datasets.columns)}")
        # Use the first column that looks like a Synapse ID
        for col in all_datasets.columns:
            if all_datasets[col].astype(str).str.contains('syn', case=False).any():
                id_col = col
                print(f"  Using column '{id_col}' as ID column")
                break

    if id_col is None:
        raise ValueError("Cannot identify ID column in dataset collection")

    # Filter datasets
    filtered_datasets = all_datasets[all_datasets[id_col].isin(dataset_ids)].copy()

    print(f"  ✓ Filtered to {len(filtered_datasets)} datasets referenced in tool publications")

    return filtered_datasets


def find_existing_table(syn: synapseclient.Synapse, parent_id: str, table_name: str):
    """Find existing table by name in a project/folder"""
    try:
        children = list(syn.getChildren(parent_id))
        for child in children:
            if child['name'] == table_name and child['type'] == 'org.sagebionetworks.repo.model.table.TableEntity':
                return child['id']
        return None
    except Exception:
        return None


def create_or_update_dataset_table(syn: synapseclient.Synapse, parent_id: str,
                                    dataset_df: pd.DataFrame, dry_run: bool = False) -> str:
    """
    Create or update the Dataset table in Synapse.

    Args:
        syn: Authenticated Synapse client
        parent_id: Parent Synapse ID for the table (syn26338068)
        dataset_df: DataFrame with dataset information
        dry_run: If True, validate but don't actually create/update

    Returns:
        Synapse ID of the created or updated table (or None in dry-run)
    """
    print(f"\nCreating/updating Dataset table under {parent_id}...")
    if dry_run:
        print("  (DRY-RUN MODE - validation only)")

    table_name = "NFToolDatasets"

    # Check if table already exists
    existing_table_id = find_existing_table(syn, parent_id, table_name)

    if existing_table_id:
        print(f"  - Found existing table: {existing_table_id}")
        print("  - Upserting data to table...")

        # Get current table data
        if USE_NEW_API:
            table = TableModel(id=existing_table_id)
            current_data = table.query(f"SELECT * FROM {existing_table_id}", synapse_client=syn)
        else:
            current_data = syn.tableQuery(f"SELECT * FROM {existing_table_id}").asDataFrame()

        print(f"    Current rows: {len(current_data)}")

        # Determine the ID column for matching
        id_columns = ['id', 'datasetId', 'synId', 'synapseId']
        id_col = None
        for col in id_columns:
            if col in dataset_df.columns:
                id_col = col
                break

        if id_col is None:
            # Fallback: find first column with 'syn' IDs
            for col in dataset_df.columns:
                if dataset_df[col].astype(str).str.contains('syn', case=False).any():
                    id_col = col
                    break

        if id_col is None:
            raise ValueError("Cannot identify ID column for upserting")

        print(f"    Matching by column: {id_col}")

        # Split into updates and inserts
        existing_ids = set(current_data[id_col].values) if id_col in current_data.columns else set()
        new_ids = set(dataset_df[id_col].values)

        ids_to_update = existing_ids & new_ids  # Intersection
        ids_to_insert = new_ids - existing_ids  # New IDs

        rows_updated = 0
        rows_inserted = 0

        # Update existing rows
        if ids_to_update:
            print(f"    Updating {len(ids_to_update)} existing rows...")
            update_rows = []

            for dataset_id in ids_to_update:
                # Get new data for this ID
                new_row = dataset_df[dataset_df[id_col] == dataset_id].iloc[0].to_dict()

                # Get ROW_ID and ROW_VERSION from current data
                current_row = current_data[current_data[id_col] == dataset_id].iloc[0]

                # Build update row with ROW_ID, ROW_VERSION, and all new data
                update_row = {
                    'ROW_ID': current_row['ROW_ID'],
                    'ROW_VERSION': current_row['ROW_VERSION']
                }
                update_row.update(new_row)

                update_rows.append(update_row)

            if update_rows and not dry_run:
                update_df = pd.DataFrame(update_rows)
                table = synapseclient.Table(existing_table_id, update_df)
                syn.store(table)
                rows_updated = len(update_rows)
                print(f"    ✓ Updated {rows_updated} rows")
            elif update_rows:
                rows_updated = len(update_rows)
                print(f"    Would update {rows_updated} rows (dry-run)")

        # Insert new rows
        if ids_to_insert:
            print(f"    Inserting {len(ids_to_insert)} new rows...")
            insert_df = dataset_df[dataset_df[id_col].isin(ids_to_insert)].copy()

            if not dry_run:
                table = synapseclient.Table(existing_table_id, insert_df)
                syn.store(table)
                rows_inserted = len(insert_df)
                print(f"    ✓ Inserted {rows_inserted} rows")
            else:
                rows_inserted = len(insert_df)
                print(f"    Would insert {rows_inserted} rows (dry-run)")

        # Handle deletions (datasets no longer referenced)
        ids_to_delete = existing_ids - new_ids
        if ids_to_delete:
            print(f"    Note: {len(ids_to_delete)} datasets are no longer referenced")
            print(f"    (Not deleting them - they remain in the table)")

        # Create snapshot version
        if not dry_run:
            syn.create_snapshot_version(existing_table_id)

        if dry_run:
            print(f"\n  ✓ Dry-run complete for dataset table: {existing_table_id}")
        else:
            print(f"  ✓ Dataset table upserted: {existing_table_id}")
            print(f"    Total rows now: {len(current_data) - len(ids_to_delete) + rows_inserted}")
            print(f"    View at: https://www.synapse.org/#!Synapse:{existing_table_id}")

        return existing_table_id

    else:
        print("  - Creating new Dataset table...")

        # Create schema from DataFrame
        # Let Synapse infer column types from the data
        cols = []
        for col_name in dataset_df.columns:
            # Determine column type
            dtype = dataset_df[col_name].dtype

            if dtype == 'int64':
                col = synapseclient.Column(name=col_name, columnType='INTEGER')
            elif dtype == 'float64':
                col = synapseclient.Column(name=col_name, columnType='DOUBLE')
            elif dtype == 'bool':
                col = synapseclient.Column(name=col_name, columnType='BOOLEAN')
            else:
                # Default to STRING with reasonable max size
                col = synapseclient.Column(name=col_name, columnType='STRING', maximumSize=500)

            cols.append(col)

        if dry_run:
            print(f"\n  ✓ Dry-run: Would create new table '{table_name}' with {len(dataset_df)} rows")
            print(f"    Columns: {', '.join(dataset_df.columns)}")
            return None
        else:
            # Create schema
            schema = synapseclient.Schema(name=table_name, columns=cols, parent=parent_id)

            # Store table
            table = synapseclient.Table(schema, dataset_df)
            table_result = syn.store(table)
            syn.create_snapshot_version(table_result.tableId)

            print(f"  ✓ Dataset table created: {table_result.tableId}")
            print(f"    View at: https://www.synapse.org/#!Synapse:{table_result.tableId}")

            return table_result.tableId


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Upsert tool datasets to Synapse')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode - validate without upserting')
    args = parser.parse_args()

    dry_run = args.dry_run

    print("\n" + "=" * 70)
    print("UPSERT TOOL DATASETS SCRIPT")
    if dry_run:
        print("🔍 DRY-RUN MODE - No changes will be made to Synapse")
    print("=" * 70 + "\n")

    # Define file paths
    input_file = Path("SUBMIT_tool_datasets.csv")
    output_file = Path("CLEAN_tool_datasets.csv")

    # Check input file exists
    if not input_file.exists():
        print(f"✗ Error: Input file not found: {input_file}")
        sys.exit(1)

    # Login to Synapse
    print("Logging in to Synapse...")
    syn = synapseclient.Synapse()

    auth_token = os.environ.get('SYNAPSE_AUTH_TOKEN')
    if not auth_token:
        print("✗ Error: SYNAPSE_AUTH_TOKEN environment variable not set")
        sys.exit(1)

    syn.login(authToken=auth_token, silent=True)
    print("  ✓ Logged in successfully")

    try:
        # Clean CSV
        clean_df = clean_csv(input_file, output_file)

        # Validate schema
        validate_schema(clean_df)

        # Upsert to Synapse
        table_id = "syn26486839"  # Tool publications table
        upsert_datasets_column(syn, table_id, clean_df, dry_run=dry_run)

        # Create/update Dataset table
        print("\n" + "=" * 70)
        print("Creating Dataset table from NF portal dataset collection...")
        if dry_run:
            print("(DRY-RUN MODE)")
        print("=" * 70)

        # Get all dataset IDs from the tool publications table
        all_dataset_ids = get_all_dataset_ids(syn, table_id)

        if all_dataset_ids:
            # Get dataset information from the collection
            dataset_collection_id = "syn50913342"
            dataset_info = get_dataset_info(syn, dataset_collection_id, all_dataset_ids)

            if not dataset_info.empty:
                # Create or update the Dataset table
                parent_id = "syn26338068"
                dataset_table_id = create_or_update_dataset_table(syn, parent_id, dataset_info, dry_run=dry_run)
            else:
                print("  ⚠ No matching datasets found in collection")
        else:
            print("  ⚠ No dataset IDs found in tool publications table")

        print("\n" + "=" * 70)
        if dry_run:
            print("SUCCESS: Dry-run validation complete - no changes made!")
        else:
            print("SUCCESS: Tool datasets upserted and Dataset table updated!")
        print("=" * 70)

        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Error during upsert: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
