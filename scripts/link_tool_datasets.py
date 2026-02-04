#!/usr/bin/env python3
"""
Script to link datasets from the NF portal to NF tools.

This script:
1. Finds publications linked to NF tools (via usage or development)
2. Extracts studyId from those publications
3. Queries Synapse for datasets associated with each study
4. Creates a CSV file to upsert dataset information to the tool publications table

Requires: synapseclient >= 4.4.0
"""

import os
import sys
from pathlib import Path
import synapseclient
import pandas as pd
from typing import List, Dict, Set

# Try to import new API (synapseclient >= 4.9.0)
try:
    from synapseclient.models import Table as TableModel
    USE_NEW_API = True
except ImportError:
    USE_NEW_API = False


def get_tool_linked_publications(syn: synapseclient.Synapse) -> pd.DataFrame:
    """
    Query publications linked to tools via usage or development.

    Returns:
        DataFrame with columns: pmid, studyId, publicationId
    """
    print("Fetching tool-linked publications...")

    # Get all tool-linked pmids from usage table
    print("  - Querying tool usage table (syn26486841)...")
    usage_query = "SELECT DISTINCT pmid FROM syn26486841"

    if USE_NEW_API:
        table = TableModel(id='syn26486841')
        usage_df = table.query(usage_query, synapse_client=syn)
    else:
        usage_df = syn.tableQuery(usage_query).asDataFrame()

    usage_pmids = set(usage_df['pmid'].dropna().unique())
    print(f"    Found {len(usage_pmids)} unique PMIDs in usage table")

    # Get all tool-linked pmids from development table
    print("  - Querying tool development table (syn26486807)...")
    dev_query = "SELECT DISTINCT pmid FROM syn26486807"

    if USE_NEW_API:
        table = TableModel(id='syn26486807')
        dev_df = table.query(dev_query, synapse_client=syn)
    else:
        dev_df = syn.tableQuery(dev_query).asDataFrame()

    dev_pmids = set(dev_df['pmid'].dropna().unique())
    print(f"    Found {len(dev_pmids)} unique PMIDs in development table")

    # Combine all tool-linked pmids
    all_tool_pmids = usage_pmids | dev_pmids
    print(f"  - Total unique tool-linked PMIDs: {len(all_tool_pmids)}")

    if not all_tool_pmids:
        print("Warning: No tool-linked PMIDs found")
        return pd.DataFrame(columns=['pmid', 'studyId', 'publicationId'])

    # Get publications from portal with those pmids
    print("  - Querying portal publications (syn16857542)...")
    portal_query = "SELECT pmid, studyId, publicationId FROM syn16857542"

    if USE_NEW_API:
        table = TableModel(id='syn16857542')
        portal_df = table.query(portal_query, synapse_client=syn)
    else:
        portal_df = syn.tableQuery(portal_query).asDataFrame()

    # Filter to only publications linked to tools and with valid studyIds
    filtered_pubs = portal_df[
        (portal_df['pmid'].isin(all_tool_pmids)) &
        (portal_df['studyId'].notna()) &
        (portal_df['studyId'] != '') &
        (portal_df['studyId'] != 'NULL')
    ].copy()

    print(f"  ✓ Found {len(filtered_pubs)} publications linked to tools with studyIds")

    return filtered_pubs


def get_datasets_for_study(syn: synapseclient.Synapse, study_id: str) -> List[str]:
    """
    Get dataset IDs for a study.

    Args:
        syn: Authenticated Synapse client
        study_id: Synapse ID of the study

    Returns:
        List of dataset Synapse IDs
    """
    try:
        children = list(syn.getChildren(study_id))
        dataset_ids = []

        for child in children:
            # Check if it's a dataset-like entity
            entity_type = child.get('type', '').lower()

            # Look for Dataset, TableEntity, or entities with 'dataset' in the type
            if ('dataset' in entity_type or
                'table' in entity_type or
                entity_type == 'org.sagebionetworks.repo.model.table.dataset'):
                dataset_ids.append(child['id'])

        return dataset_ids
    except Exception as e:
        # Handle permission errors or non-existent studies gracefully
        print(f"    Warning: Could not get children for {study_id}: {e}")
        return []


def get_study_to_datasets_mapping(syn: synapseclient.Synapse,
                                   publications: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Build a mapping of studyId to list of dataset IDs.

    Args:
        syn: Authenticated Synapse client
        publications: DataFrame with studyId column

    Returns:
        Dictionary mapping studyId to list of dataset IDs
    """
    print("\nBuilding study to datasets mapping...")

    # Get unique study IDs
    unique_studies = publications['studyId'].unique()
    print(f"  - Processing {len(unique_studies)} unique studies")

    study_to_datasets = {}
    studies_with_datasets = 0
    total_datasets = 0

    for study_id in unique_studies:
        print(f"  - Checking {study_id}...", end=' ')
        datasets = get_datasets_for_study(syn, study_id)

        if datasets:
            study_to_datasets[study_id] = datasets
            studies_with_datasets += 1
            total_datasets += len(datasets)
            print(f"✓ Found {len(datasets)} dataset(s)")
        else:
            study_to_datasets[study_id] = []
            print("No datasets found")

    print(f"\n  ✓ Summary:")
    print(f"    - Studies with datasets: {studies_with_datasets}/{len(unique_studies)}")
    print(f"    - Total datasets found: {total_datasets}")

    return study_to_datasets


def get_tool_publications(syn: synapseclient.Synapse) -> pd.DataFrame:
    """
    Get current tool publications from syn26486839.

    Returns:
        DataFrame with tool publication data
    """
    print("\nFetching current tool publications (syn26486839)...")
    query = "SELECT * FROM syn26486839"

    if USE_NEW_API:
        table = TableModel(id='syn26486839')
        tool_pubs_df = table.query(query, synapse_client=syn)
    else:
        tool_pubs_df = syn.tableQuery(query).asDataFrame()

    print(f"  ✓ Retrieved {len(tool_pubs_df)} tool publication records")

    return tool_pubs_df


def map_datasets_to_tool_publications(syn: synapseclient.Synapse) -> pd.DataFrame:
    """
    Main function to create the mapping of datasets to tool publications.

    Returns:
        DataFrame ready for CSV export with columns: publicationId, pmid, resourceId, datasets
    """
    print("=" * 70)
    print("Starting dataset linking process...")
    print("=" * 70)

    # Step 1: Get publications linked to tools with studyIds
    portal_pubs = get_tool_linked_publications(syn)

    if portal_pubs.empty:
        print("\nNo tool-linked publications with studyIds found. Exiting.")
        return pd.DataFrame(columns=['publicationId', 'pmid', 'resourceId', 'datasets'])

    # Step 2: Build study to datasets mapping
    study_to_datasets = get_study_to_datasets_mapping(syn, portal_pubs)

    # Step 3: Get current tool publications
    tool_pubs = get_tool_publications(syn)

    # Step 4: Map datasets to tool publications by pmid
    print("\nMapping datasets to tool publications...")

    # Add datasets column to portal_pubs based on studyId
    portal_pubs['datasets'] = portal_pubs['studyId'].map(
        lambda study_id: ','.join(study_to_datasets.get(study_id, []))
    )

    # Create a mapping from pmid to datasets
    pmid_to_datasets = portal_pubs.groupby('pmid')['datasets'].first().to_dict()

    # Filter tool_pubs to only those with pmids that have datasets
    tool_pubs_with_datasets = tool_pubs[tool_pubs['pmid'].isin(pmid_to_datasets.keys())].copy()

    # Map datasets to tool publications
    tool_pubs_with_datasets['datasets'] = tool_pubs_with_datasets['pmid'].map(pmid_to_datasets)

    # Only include rows where datasets is not empty
    tool_pubs_with_datasets = tool_pubs_with_datasets[
        tool_pubs_with_datasets['datasets'].notna() &
        (tool_pubs_with_datasets['datasets'] != '')
    ]

    print(f"  ✓ Mapped datasets to {len(tool_pubs_with_datasets)} tool publication records")

    # Prepare output dataframe with required columns
    # Need to determine the primary key column - check what's available
    required_cols = ['pmid', 'resourceId', 'datasets']

    # Check if we have a unique identifier column
    if 'publicationId' in tool_pubs_with_datasets.columns:
        required_cols.insert(0, 'publicationId')
    elif 'id' in tool_pubs_with_datasets.columns:
        required_cols.insert(0, 'id')
    elif 'ROW_ID' in tool_pubs_with_datasets.columns:
        required_cols.insert(0, 'ROW_ID')

    # Select only columns that exist
    available_cols = [col for col in required_cols if col in tool_pubs_with_datasets.columns]
    output_df = tool_pubs_with_datasets[available_cols].copy()

    print(f"\n  Output columns: {list(output_df.columns)}")
    print(f"  Output rows: {len(output_df)}")

    # Show sample of mappings
    if len(output_df) > 0:
        print("\n  Sample mappings:")
        for idx, row in output_df.head(3).iterrows():
            datasets_list = row['datasets'].split(',')
            print(f"    - PMID {row['pmid']}: {len(datasets_list)} dataset(s)")

    return output_df


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("LINK TOOL DATASETS SCRIPT")
    print("=" * 70 + "\n")

    # Login to Synapse
    print("Logging in to Synapse...")
    syn = synapseclient.Synapse()

    auth_token = os.environ.get('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token, silent=True)
        print("  ✓ Logged in with auth token")
    else:
        print("  Warning: No SYNAPSE_AUTH_TOKEN found, attempting anonymous access")
        # Some operations may fail without authentication

    try:
        # Map datasets to tool publications
        output_df = map_datasets_to_tool_publications(syn)

        if output_df.empty:
            print("\n" + "=" * 70)
            print("No dataset links to create. Exiting.")
            print("=" * 70)
            sys.exit(0)

        # Write to CSV
        output_file = Path("SUBMIT_tool_datasets.csv")
        output_df.to_csv(output_file, index=False)
        print(f"\n✓ CSV file created: {output_file}")
        print(f"  - Rows: {len(output_df)}")
        print(f"  - Columns: {list(output_df.columns)}")

        # Summary statistics
        total_datasets = sum(len(datasets.split(',')) for datasets in output_df['datasets'] if datasets)
        print(f"\n📊 Summary Statistics:")
        print(f"  - Total tool publications with datasets: {len(output_df)}")
        print(f"  - Total unique datasets linked: {total_datasets}")
        avg_datasets = total_datasets / len(output_df) if len(output_df) > 0 else 0
        print(f"  - Average datasets per publication: {avg_datasets:.2f}")

        print("\n" + "=" * 70)
        print("SUCCESS: Dataset linking complete!")
        print("=" * 70)

        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Error during dataset linking: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
