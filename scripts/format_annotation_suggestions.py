#!/usr/bin/env python3
"""
Format annotation review suggestions into SUBMIT_*.csv files for Synapse upload.

This script:
1. Reads the JSON output from review_tool_annotations.py
2. Creates SUBMIT_resources.csv for new resources
3. Creates SUBMIT_cell_lines.csv for cell line details
4. Assumes all new individualID values are cell lines (as per user specification)

Note: Synonym additions require manual review since they need to UPDATE existing
      rows rather than append new ones. These are documented in the markdown report.
"""

import argparse
import json
import pandas as pd
import uuid
from pathlib import Path
from typing import Dict, List


def generate_uuid():
    """Generate a UUID for new entries."""
    return str(uuid.uuid4())


def format_cell_lines_from_suggestions(suggestions: Dict) -> pd.DataFrame:
    """
    Format new resource suggestions as cell lines.

    Args:
        suggestions: Dictionary with 'new_resources' key containing individualID suggestions

    Returns:
        DataFrame with cell line records matching syn26486823 schema
    """
    cell_line_rows = []

    new_resources = suggestions.get('new_resources', [])

    for item in new_resources:
        value = item['value']
        count = item['count']

        # Create cell line entry (matching syn26486823 schema)
        cell_line_rows.append({
            # EXACT Synapse column order (syn26486823)
            'cellLineId': generate_uuid(),
            'donorId': '',
            'originYear': '',
            'organ': '',  # Required but unknown from individualID alone
            'strProfile': '',
            'tissue': '',
            'cellLineManifestation': '',
            'resistance': '',
            'cellLineCategory': '',
            'contaminatedMisidentified': '',
            'cellLineGeneticDisorder': '',
            'populationDoublingTime': '',
            # Tracking columns (prefixed with _ = not in Synapse)
            '_cellLineName': value,
            '_individualID': value,
            '_usage_count': count,
            '_source': 'annotation_review',
            '_needs_manual_review': 'YES - organ and other fields need to be filled in'
        })

    return pd.DataFrame(cell_line_rows)


def format_resources_from_cell_lines(cell_lines_df: pd.DataFrame) -> pd.DataFrame:
    """
    Format Resource table entries (syn26450069) from cell lines.

    Args:
        cell_lines_df: DataFrame with cell line records

    Returns:
        DataFrame with Resource table entries
    """
    resource_rows = []

    for _, row in cell_lines_df.iterrows():
        cell_line_id = row['cellLineId']
        cell_line_name = row.get('_cellLineName', '')

        if not cell_line_name:
            continue

        # Create Resource table entry
        resource_rows.append({
            'resourceId': generate_uuid(),
            'resourceName': cell_line_name,
            'resourceType': 'Cell Line',
            'synonyms': '',  # Can be filled in manually during review
            'rrid': '',
            'description': '',
            'aiSummary': '',
            'usageRequirements': '',
            'howToAcquire': '',
            # Foreign keys to detail tables
            'animalModelId': '',
            'antibodyId': '',
            'cellLineId': cell_line_id,
            'geneticReagentId': '',
            'biobankId': '',
            # Tracking columns
            '_individualID': row.get('_individualID', ''),
            '_usage_count': row.get('_usage_count', ''),
            '_source': 'annotation_review'
        })

    return pd.DataFrame(resource_rows)


def create_synonym_update_report(suggestions: Dict, output_file: Path) -> None:
    """
    Create a report documenting synonyms that need manual addition.

    Since the upsert workflow only appends rows, synonym updates need manual intervention.

    Args:
        suggestions: Dictionary with 'new_synonyms' key
        output_file: Path to output markdown file
    """
    new_synonyms = suggestions.get('new_synonyms', [])

    if not new_synonyms:
        return

    lines = [
        "# Synonym Updates Requiring Manual Review\n\n",
        "The following individualID values should be added as synonyms to existing resources. ",
        "These require manual updates to the Synapse tables since the automated workflow ",
        "only appends new rows.\n\n",
        "## Suggested Synonym Additions\n\n"
    ]

    for item in new_synonyms:
        value = item['value']
        resource = item['resource']
        matched_synonym = item['matched_synonym']
        match_score = item['match_score']
        count = item['count']

        lines.append(f"### `{value}` → `{resource}`\n\n")
        lines.append(f"- **Fuzzy matched**: `{matched_synonym}` (score: {match_score:.2f})\n")
        lines.append(f"- **Usage count**: {count}\n")
        lines.append(f"- **Action**: Add `{value}` to the `synonyms` field of resource `{resource}`\n\n")

    with open(output_file, 'w') as f:
        f.writelines(lines)

    print(f"✅ Created synonym update report: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Format annotation review suggestions into SUBMIT_*.csv files'
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=Path('tool_annotation_suggestions.json'),
        help='Input JSON file from review_tool_annotations.py'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('.'),
        help='Output directory for SUBMIT_*.csv files'
    )
    parser.add_argument(
        '--min-count',
        type=int,
        default=2,
        help='Minimum usage count to include a suggestion'
    )

    args = parser.parse_args()

    # Load suggestions
    if not args.input.exists():
        print(f"❌ Input file not found: {args.input}")
        print("   Run review_tool_annotations.py first to generate suggestions")
        return 1

    with open(args.input, 'r') as f:
        data = json.load(f)

    suggestions = data.get('individual_id_suggestions', {})

    # Filter by minimum count
    new_resources = [
        item for item in suggestions.get('new_resources', [])
        if item['count'] >= args.min_count
    ]

    if not new_resources:
        print(f"ℹ️  No new resources with count >= {args.min_count}")
        print("   Adjust --min-count or wait for more data")
        return 0

    print(f"📊 Processing {len(new_resources)} new resource suggestions...")

    # Create cell lines DataFrame
    suggestions_filtered = {'new_resources': new_resources}
    cell_lines_df = format_cell_lines_from_suggestions(suggestions_filtered)

    # Create resources DataFrame
    resources_df = format_resources_from_cell_lines(cell_lines_df)

    # Save SUBMIT files
    cell_lines_file = args.output_dir / 'SUBMIT_cell_lines.csv'
    resources_file = args.output_dir / 'SUBMIT_resources.csv'

    cell_lines_df.to_csv(cell_lines_file, index=False)
    resources_df.to_csv(resources_file, index=False)

    print(f"✅ Created {cell_lines_file} ({len(cell_lines_df)} rows)")
    print(f"✅ Created {resources_file} ({len(resources_df)} rows)")

    # Create synonym update report
    synonym_report = args.output_dir / 'MANUAL_SYNONYM_UPDATES.md'
    create_synonym_update_report(suggestions, synonym_report)

    # Summary
    print(f"\n📋 Summary:")
    print(f"   - New cell lines: {len(cell_lines_df)}")
    print(f"   - New resources: {len(resources_df)}")
    print(f"   - Synonyms needing manual update: {len(suggestions.get('new_synonyms', []))}")
    print(f"\n⚠️  Important: All cell lines need manual review to fill in required 'organ' field")

    return 0


if __name__ == '__main__':
    exit(main())
