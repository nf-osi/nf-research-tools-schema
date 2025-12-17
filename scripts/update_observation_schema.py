#!/usr/bin/env python3
"""
Script to update SubmitObservationSchema.json with latest data from Synapse.
This script queries syn51730943 for unique resourceType and resourceName values
and updates the schema with conditional enums.
"""

import json
import sys
import os
from pathlib import Path
import synapseclient
import pandas as pd


def get_synapse_data(syn_id: str):
    """Fetch resourceType and resourceName mappings from Synapse."""
    syn = synapseclient.Synapse()

    # Login only if SYNAPSE_AUTH_TOKEN is provided
    # Not required for public tables like syn51730943
    auth_token = os.environ.get('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token, silent=True)
    # If no auth token, synapseclient can still access public resources without login

    # Get unique resourceType values
    query_result = syn.tableQuery(f'SELECT DISTINCT resourceType FROM {syn_id}')
    df_types = query_result.asDataFrame()
    resource_types = sorted([str(v) for v in df_types['resourceType'].dropna().unique()])

    # Get mapping of resourceType to resourceName
    query_result = syn.tableQuery(f'SELECT resourceType, resourceName FROM {syn_id}')
    df = query_result.asDataFrame()
    df = df.dropna()

    mapping = {}
    for resource_type in resource_types:
        names = sorted(df[df['resourceType'] == resource_type]['resourceName'].unique().tolist())
        mapping[resource_type] = names

    return resource_types, mapping


def update_schema(schema_path: Path, resource_types: list, mapping: dict) -> bool:
    """
    Update the schema file with new data.
    Returns True if changes were made, False otherwise.
    """
    # Read current schema
    with open(schema_path, 'r') as f:
        schema = json.load(f)

    items_schema = schema['properties']['observationsSection']['properties']['observations']['items']

    # Check if there are changes
    current_types = items_schema['properties']['resourceType'].get('enum', [])

    # Compare resource types
    if set(current_types) != set(resource_types):
        print(f"Resource types changed: {set(resource_types) - set(current_types)} added, "
              f"{set(current_types) - set(resource_types)} removed")
        changes_made = True
    else:
        # Check if resourceName mappings changed
        changes_made = False
        if 'allOf' in items_schema:
            for condition in items_schema['allOf']:
                resource_type = condition['if']['properties']['resourceType']['const']
                current_names = set(condition['then']['properties']['resourceName']['enum'])
                new_names = set(mapping.get(resource_type, []))

                if current_names != new_names:
                    added = new_names - current_names
                    removed = current_names - new_names
                    if added or removed:
                        print(f"Changes in '{resource_type}':")
                        if added:
                            print(f"  Added: {list(added)[:5]}{'...' if len(added) > 5 else ''} ({len(added)} total)")
                        if removed:
                            print(f"  Removed: {list(removed)[:5]}{'...' if len(removed) > 5 else ''} ({len(removed)} total)")
                        changes_made = True
        else:
            # First time adding conditional logic
            changes_made = True

    if not changes_made:
        print("No changes detected in Synapse data.")
        return False

    print("Updating schema with new data...")

    # Update resourceType enum
    items_schema['properties']['resourceType']['enum'] = resource_types

    # Update resourceName to be conditional
    items_schema['properties']['resourceName'] = {
        "type": "string",
        "title": "Name of the Resource"
    }

    # Build conditional logic using allOf
    conditional_schemas = []
    for resource_type in resource_types:
        condition = {
            "if": {
                "properties": {
                    "resourceType": {
                        "const": resource_type
                    }
                }
            },
            "then": {
                "properties": {
                    "resourceName": {
                        "enum": mapping[resource_type]
                    }
                }
            }
        }
        conditional_schemas.append(condition)

    items_schema['allOf'] = conditional_schemas

    # Write back to file
    with open(schema_path, 'w') as f:
        json.dump(schema, f, indent=2)

    print(f"✓ Schema updated successfully!")
    print(f"  - {len(resource_types)} resource types")
    total_resources = sum(len(mapping[rt]) for rt in resource_types)
    print(f"  - {total_resources} total resources across all types")

    return True


def main():
    """Main entry point."""
    syn_id = 'syn51730943'

    # Determine schema path
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    schema_path = repo_root / 'NF-Tools-Schemas' / 'observations' / 'SubmitObservationSchema.json'

    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}")
        sys.exit(1)

    print(f"Fetching data from Synapse {syn_id}...")
    try:
        resource_types, mapping = get_synapse_data(syn_id)
    except Exception as e:
        print(f"Error fetching data from Synapse: {e}")
        sys.exit(1)

    print(f"✓ Retrieved data from Synapse:")
    for rt in resource_types:
        print(f"  - {rt}: {len(mapping[rt])} resources")

    print(f"\nChecking schema at {schema_path}...")
    try:
        changes_made = update_schema(schema_path, resource_types, mapping)
    except Exception as e:
        print(f"Error updating schema: {e}")
        sys.exit(1)

    # Exit with status code to indicate if changes were made
    sys.exit(0 if changes_made else 2)


if __name__ == '__main__':
    main()
