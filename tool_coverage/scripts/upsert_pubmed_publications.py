#!/usr/bin/env python3
"""
Upsert PubMed publications to Synapse table syn26486839.

This script can be run standalone for testing or as part of the GitHub Actions workflow.

Requires: synapseclient >= 4.4.0
"""

import os
import sys
import argparse
import pandas as pd
import synapseclient
from synapseclient import Table

# Try to import new API (synapseclient >= 4.9.0)
try:
    from synapseclient.models import Table as TableModel
    USE_NEW_API = True
except ImportError:
    USE_NEW_API = False


def main():
    parser = argparse.ArgumentParser(
        description='Upsert PubMed publications to Synapse'
    )
    parser.add_argument(
        '--csv-path',
        type=str,
        default='tool_coverage/outputs/pubmed_nf_publications.csv',
        help='Path to CSV file with publications'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode - validate without upserting'
    )
    parser.add_argument(
        '--table-id',
        type=str,
        default='syn26486839',
        help='Synapse table ID (default: syn26486839)'
    )

    args = parser.parse_args()

    csv_file = args.csv_path
    dry_run = args.dry_run
    table_id = args.table_id

    if dry_run:
        print("=" * 80)
        print("🔍 DRY-RUN MODE - No changes will be made to Synapse")
        print("=" * 80)
        print()

    # Check if input file exists
    if not os.path.exists(csv_file):
        print(f"❌ File not found: {csv_file}")
        sys.exit(1)

    print(f"📁 Using CSV file: {csv_file}")

    # Login to Synapse
    syn = synapseclient.Synapse()
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if not auth_token:
        print("❌ SYNAPSE_AUTH_TOKEN not found")
        print("   Please set environment variable or run: export SYNAPSE_AUTH_TOKEN=<your_token>")
        sys.exit(1)

    syn.login(authToken=auth_token)
    print("✅ Logged into Synapse")

    # Read publications
    df = pd.read_csv(csv_file)
    print(f"📚 Read {len(df)} publications from CSV")

    # Get existing publications to avoid duplicates
    print(f"🔍 Checking for existing publications in {table_id}...")

    if USE_NEW_API:
        # Use new API (synapseclient >= 4.9.0)
        table = TableModel(id=table_id)
        existing_df = table.query(f"SELECT pmid FROM {table_id}", synapse_client=syn)
    else:
        # Use old API (synapseclient < 4.9.0)
        query = f"SELECT pmid FROM {table_id}"
        existing = syn.tableQuery(query)
        existing_df = existing.asDataFrame()

    if len(existing_df) > 0:
        existing_pmids = set(existing_df['pmid'].str.upper().tolist())
    else:
        existing_pmids = set()

    print(f"   Found {len(existing_pmids)} existing publications")

    # Filter out duplicates
    df['pmid_upper'] = df['pmid'].str.upper()
    new_pubs = df[~df['pmid_upper'].isin(existing_pmids)].copy()
    new_pubs = new_pubs.drop('pmid_upper', axis=1)

    if len(new_pubs) == 0:
        print("✅ No new publications to add (all already exist)")
        print(f"\n📊 Summary:")
        print(f"   Publications checked: {len(df)}")
        print(f"   New publications: 0")
        return 0

    print(f"📝 Found {len(new_pubs)} new publications to add to {table_id}")

    # Get table schema to validate columns
    print("🔍 Checking table schema...")

    if USE_NEW_API:
        # Use new API (synapseclient >= 4.9.0)
        table_model = TableModel(id=table_id)
        table_model = table_model.get(synapse_client=syn)

        # Extract column names - columns is a dict with column names as keys
        if isinstance(table_model.columns, dict):
            schema_col_names = set(table_model.columns.keys())
        elif isinstance(table_model.columns, list):
            schema_col_names = {col.name for col in table_model.columns}
        else:
            schema_col_names = set()
    else:
        # Use old API (synapseclient < 4.9.0)
        table_entity = syn.get(table_id)
        table_cols = syn.getTableColumns(table_entity)
        schema_col_names = {col.name for col in table_cols}

    print(f"   Table has {len(schema_col_names)} columns")

    # Prepare data for Synapse table
    # Expected columns in CSV match syn26486839 schema
    expected_cols = ['publicationId', 'doi', 'pmid', 'abstract', 'journal',
                     'publicationDate', 'citation', 'publicationDateUnix',
                     'authors', 'publicationTitle']

    # Only include columns that exist in both dataframe and table schema
    valid_cols = [col for col in expected_cols if col in new_pubs.columns and col in schema_col_names]

    print(f"   Using columns: {', '.join(valid_cols)}")
    table_df = new_pubs[valid_cols].copy()

    if dry_run:
        # Dry-run mode - show what would be done
        print("\n" + "=" * 80)
        print(f"DRY-RUN: The following would be uploaded to {table_id}:")
        print("=" * 80)
        print(f"\nFirst 5 rows preview:")
        print(table_df.head().to_string())
        print(f"\n📊 Summary:")
        print(f"   Total rows to upload: {len(table_df)}")
        print(f"   Columns: {', '.join(table_df.columns.tolist())}")
        print("\n✅ Dry-run validation complete - no changes made to Synapse")
    else:
        # Actual upsert
        print(f"\n⬆️  Uploading to Synapse table {table_id}...")
        table = syn.store(Table(table_id, table_df))
        print(f"✅ Successfully added {len(new_pubs)} publications to {table_id}")

        # Create snapshot version for tracking
        print("   Creating snapshot version...")
        syn.create_snapshot_version(table_id)
        print("   ✅ Snapshot version created")

    # Log the PMIDs
    print("\n📋 Publications (PMIDs):")
    for pmid in table_df['pmid'].tolist()[:10]:  # Show first 10
        print(f"   - {pmid}")
    if len(table_df) > 10:
        print(f"   ... and {len(table_df) - 10} more")

    print("\n" + "=" * 80)
    print("✅ Complete!")
    print("=" * 80)
    print(f"\n📊 Final Summary:")
    print(f"   Publications checked: {len(df)}")
    print(f"   New publications added: {len(new_pubs)}")
    print(f"   Mode: {'DRY-RUN (no changes)' if dry_run else 'LIVE (uploaded to Synapse)'}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
