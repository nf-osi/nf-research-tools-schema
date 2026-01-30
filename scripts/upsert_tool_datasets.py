#!/usr/bin/env python3
"""
Script to clean and upsert tool dataset links to Synapse.

This script:
1. Reads SUBMIT_tool_datasets.csv
2. Validates the data
3. Adds or updates the 'datasets' column in syn26486839
4. Upserts the data to Synapse
5. Creates a snapshot version
"""

import os
import sys
from pathlib import Path
import synapseclient
import pandas as pd
from typing import List


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

        # Add column to schema
        table.addColumn(new_column)
        syn.store(table)

        print("  ✓ Column 'datasets' added successfully")
        return True

    except Exception as e:
        print(f"  ✗ Error ensuring column exists: {e}")
        raise


def upsert_datasets_column(syn: synapseclient.Synapse, table_id: str, data_df: pd.DataFrame):
    """
    Upsert the datasets column to the Synapse table.

    This updates existing rows with the new datasets column values.

    Args:
        syn: Authenticated Synapse client
        table_id: Synapse ID of the target table
        data_df: DataFrame with data to upsert
    """
    print(f"\nUpserting data to {table_id}...")

    # Ensure the datasets column exists
    ensure_datasets_column_exists(syn, table_id)

    # Get current table data to find ROW_IDs
    print("  - Fetching current table data...")
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


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("UPSERT TOOL DATASETS SCRIPT")
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
        upsert_datasets_column(syn, table_id, clean_df)

        print("\n" + "=" * 70)
        print("SUCCESS: Tool datasets upserted to Synapse!")
        print("=" * 70)

        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Error during upsert: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
