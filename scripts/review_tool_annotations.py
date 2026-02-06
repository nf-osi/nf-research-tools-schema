#!/usr/bin/env python3
"""
Review Synapse file annotations for tool-related fields and suggest additions to tools schema.

This script:
1. Queries Synapse materialized view syn52702673 for file annotations
2. Loads the current tools schema from nf_research_tools.rdb.model.csv
3. Identifies tool-related annotation fields with free-text values
4. Generates suggestions for new values to add to the tools schema
5. Outputs suggestions in a format suitable for PR creation

Tool-related fields reviewed:
- Tool identifiers: animalModelID, cellLineID, antibodyID, geneticReagentID
- Specimen fields: tumorType, tissue, organ, species
- Manifestation fields: cellLineManifestation, animalModelOfManifestation
- Disease fields: cellLineGeneticDisorder, animalModelGeneticDisorder
- Donor fields: sex, age, race

Usage:
    python review_tool_annotations.py [--output OUTPUT_FILE] [--dry-run] [--limit LIMIT]
"""

import argparse
import csv
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    import synapseclient
    from synapseclient import Synapse
    import pandas as pd
    import yaml
except ImportError:
    print("Error: Required packages not installed. Install with: pip install synapseclient pandas pyyaml")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
MATERIALIZED_VIEW_ID = "syn52702673"
TOOLS_SCHEMA_CSV = Path(__file__).parent.parent / "nf_research_tools.rdb.model.csv"

# Tool-related fields to review from file annotations
TOOL_RELATED_FIELDS = {
    # Tool identifiers
    'animalModelID',
    'cellLineID',
    'antibodyID',
    'geneticReagentID',

    # Specimen/biobank fields
    'tumorType',
    'tissue',
    'organ',
    'species',

    # Manifestation fields
    'cellLineManifestation',
    'animalModelOfManifestation',
    'animalModelManifestation',

    # Disease fields
    'cellLineGeneticDisorder',
    'animalModelGeneticDisorder',
    'animalModelDisease',

    # Donor fields
    'sex',
    'race',

    # Cell line specific
    'cellLineCategory',

    # Other tool-related
    'backgroundStrain',
    'backgroundSubstrain',
}

# Minimum frequency threshold for suggesting new values
MIN_FREQUENCY = 2

# Minimum frequency for suggesting search filters
MIN_FILTER_FREQUENCY = 5


def load_tools_schema_values() -> Dict[str, Set[str]]:
    """
    Load valid values for tool-related fields from the tools schema CSV.

    Returns:
        Dictionary mapping field names to their valid values
    """
    schema_values = {}

    logger.info(f"Loading tools schema from {TOOLS_SCHEMA_CSV}...")

    try:
        with open(TOOLS_SCHEMA_CSV, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                attribute = row.get('Attribute', '')
                valid_values_str = row.get('Valid Values', '')

                # Skip if no valid values defined
                if not valid_values_str or valid_values_str.strip() == '':
                    continue

                # Parse comma-separated valid values
                valid_values = set()
                for value in valid_values_str.split(','):
                    value = value.strip()
                    if value:
                        valid_values.add(value)

                if valid_values:
                    schema_values[attribute] = valid_values

        logger.info(f"Loaded {len(schema_values)} fields with valid values from tools schema")

    except Exception as e:
        logger.error(f"Error loading tools schema: {e}")
        raise

    return schema_values


def load_metadata_dict_enums() -> Dict[str, Dict[str, Set[str]]]:
    """
    Load enum permissible values and aliases from the metadata dictionary schema.
    This is important for checking if annotation values are synonyms/aliases.

    Returns:
        Dictionary mapping enum names to their permissible values and aliases
    """
    enums = {}

    # Path to metadata dictionary (assuming it's a sibling directory)
    metadata_dict_path = Path(__file__).parent.parent.parent / "nf-metadata-dictionary" / "modules"

    if not metadata_dict_path.exists():
        logger.warning(f"Metadata dictionary not found at {metadata_dict_path}, skipping synonym checking")
        return {}

    logger.info(f"Loading metadata dictionary enums for synonym checking from {metadata_dict_path}...")

    try:
        # Load from all module YAML files
        for yaml_file in metadata_dict_path.rglob("*.yaml"):
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)

                if not data or 'enums' not in data:
                    continue

                for enum_name, enum_data in data['enums'].items():
                    if 'permissible_values' not in enum_data:
                        continue

                    values = set()
                    aliases = set()

                    for value, value_data in enum_data['permissible_values'].items():
                        values.add(value)

                        # Also collect aliases
                        if value_data and isinstance(value_data, dict) and 'aliases' in value_data:
                            if isinstance(value_data['aliases'], list):
                                aliases.update(value_data['aliases'])
                            elif isinstance(value_data['aliases'], str):
                                aliases.add(value_data['aliases'])

                    enums[enum_name] = {
                        'values': values,
                        'aliases': aliases,
                        'all': values | aliases
                    }

            except Exception as e:
                logger.debug(f"Error loading {yaml_file}: {e}")

        logger.info(f"Loaded {len(enums)} enums with aliases from metadata dictionary")

    except Exception as e:
        logger.warning(f"Error loading metadata dictionary enums: {e}")

    return enums


def load_metadata_dict_slot_mappings() -> Dict[str, List[str]]:
    """
    Load mapping of slot names to their enum types from metadata dictionary.

    Returns:
        Dictionary mapping slot names to list of enum names
    """
    slot_enum_map = {}

    metadata_dict_path = Path(__file__).parent.parent.parent / "nf-metadata-dictionary" / "modules"
    props_file = metadata_dict_path / "props.yaml"

    if not props_file.exists():
        logger.warning(f"props.yaml not found at {props_file}")
        return {}

    try:
        with open(props_file, 'r') as f:
            data = yaml.safe_load(f)

        if data and 'slots' in data:
            for slot_name, slot_data in data['slots'].items():
                if not slot_data:
                    continue

                enum_types = []

                # Check for direct range
                if 'range' in slot_data and slot_data['range'].endswith('Enum'):
                    enum_types.append(slot_data['range'])

                # Check for any_of ranges
                if 'any_of' in slot_data and isinstance(slot_data['any_of'], list):
                    for constraint in slot_data['any_of']:
                        if 'range' in constraint and constraint['range'].endswith('Enum'):
                            enum_types.append(constraint['range'])

                if enum_types:
                    slot_enum_map[slot_name] = enum_types

        logger.info(f"Loaded {len(slot_enum_map)} slot mappings from metadata dictionary")

    except Exception as e:
        logger.warning(f"Error loading slot mappings: {e}")

    return slot_enum_map


def query_synapse_annotations(syn: Synapse, limit: int = None) -> List[Dict]:
    """
    Query Synapse materialized view for file annotations.

    Args:
        syn: Synapse client
        limit: Optional limit on number of rows to retrieve

    Returns:
        List of annotation records
    """
    logger.info(f"Querying Synapse view {MATERIALIZED_VIEW_ID}...")

    query = f"SELECT * FROM {MATERIALIZED_VIEW_ID}"
    if limit:
        query += f" LIMIT {limit}"

    try:
        results = syn.tableQuery(query)
        df = results.asDataFrame()

        logger.info(f"Retrieved {len(df)} records with {len(df.columns)} columns")

        # Convert to list of dicts
        records = df.to_dict('records')
        return records

    except Exception as e:
        logger.error(f"Error querying Synapse: {e}")
        raise


def analyze_tool_annotations(
    records: List[Dict],
    schema_values: Dict[str, Set[str]],
    metadata_enums: Dict[str, Dict[str, Set[str]]] = None,
    slot_enum_map: Dict[str, List[str]] = None
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
    """
    Analyze tool-related annotations to find free-text values not in schema.

    Args:
        records: List of annotation records from Synapse
        schema_values: Valid values from tools schema
        metadata_enums: Enum definitions from metadata dictionary (includes aliases)
        slot_enum_map: Mapping of slot names to enum types from metadata dictionary

    Returns:
        Tuple of (suggestions_by_field, filter_suggestions)
    """
    suggestions = defaultdict(lambda: defaultdict(int))
    filter_candidates = defaultdict(set)

    if not records:
        logger.warning("No records to analyze")
        return {}, {}

    if metadata_enums is None:
        metadata_enums = {}
    if slot_enum_map is None:
        slot_enum_map = {}

    # Get all column names
    columns = list(records[0].keys())

    # Filter to only tool-related fields that exist in the data
    tool_fields_in_data = [f for f in columns if f in TOOL_RELATED_FIELDS]
    logger.info(f"Found {len(tool_fields_in_data)} tool-related fields in annotations: {tool_fields_in_data}")

    for record in records:
        for field in tool_fields_in_data:
            value = record.get(field)

            # Skip null/empty values
            if value is None or value == '':
                continue

            # Convert to string and clean
            value_str = str(value).strip()
            if not value_str:
                continue

            # Track for potential filters
            filter_candidates[field].add(value_str)

            # Check if value is already valid
            value_is_valid = False

            # 1. Check against tools schema valid values
            if field in schema_values and value_str in schema_values[field]:
                value_is_valid = True

            # 2. Check against metadata dictionary enums (including synonyms/aliases)
            if not value_is_valid and field in slot_enum_map:
                enum_names = slot_enum_map[field]
                for enum_name in enum_names:
                    if enum_name in metadata_enums:
                        # Check against both values and aliases
                        if value_str in metadata_enums[enum_name]['all']:
                            value_is_valid = True
                            logger.debug(f"Value '{value_str}' for field '{field}' found as synonym in enum '{enum_name}'")
                            break

            # If value is not valid anywhere, add as suggestion
            if not value_is_valid:
                suggestions[field][value_str] += 1

    # Filter suggestions by minimum frequency
    filtered_suggestions = {}
    for field, values in suggestions.items():
        filtered_values = {v: c for v, c in values.items() if c >= MIN_FREQUENCY}
        if filtered_values:
            filtered_suggestions[field] = filtered_values

    # Identify filter candidates (fields with diverse values)
    filter_suggestions = {}
    for field, values in filter_candidates.items():
        unique_count = len(values)
        if unique_count >= MIN_FILTER_FREQUENCY:
            filter_suggestions[field] = unique_count

    logger.info(f"Found {len(filtered_suggestions)} tool fields with suggested additions")
    logger.info(f"Found {len(filter_suggestions)} tool fields as potential filters")

    return filtered_suggestions, filter_suggestions


def format_suggestions_as_markdown(
    suggestions: Dict[str, Dict[str, int]],
    filters: Dict[str, int]
) -> str:
    """
    Format suggestions as markdown for PR description.

    Args:
        suggestions: Field suggestions with counts
        filters: Filter candidates with unique value counts

    Returns:
        Markdown formatted string
    """
    md = ["# Tool Annotation Review - Schema Updates from Synapse Annotations\n"]
    md.append("This PR contains automatic updates to the NF Research Tools schema based on ")
    md.append(f"analysis of tool-related file annotations in Synapse view {MATERIALIZED_VIEW_ID}.\n\n")
    md.append("**Note:** This review checks both tools schema values and metadata dictionary enums ")
    md.append("(including synonyms/aliases) to avoid suggesting values that are already defined.\n")

    if suggestions:
        md.append("\n## Suggested Value Additions\n")
        md.append("The following values appear in tool-related annotations but are not currently ")
        md.append("in the tools schema. Values shown with frequency counts.\n")

        for field in sorted(suggestions.keys()):
            values = suggestions[field]
            md.append(f"\n### Field: `{field}`\n")

            # Sort by frequency (descending)
            sorted_values = sorted(values.items(), key=lambda x: x[1], reverse=True)

            for value, count in sorted_values[:20]:  # Limit to top 20
                md.append(f"- `{value}` (used {count} times)\n")

            if len(sorted_values) > 20:
                md.append(f"\n*...and {len(sorted_values) - 20} more*\n")
    else:
        md.append("\n## No New Values Suggested\n")
        md.append("All tool annotation values match existing schema definitions.\n")

    if filters:
        md.append("\n## Suggested Search Filters\n")
        md.append("The following tool-related fields have diverse values and could be useful as ")
        md.append("search filters:\n")

        # Sort by unique value count (descending)
        sorted_filters = sorted(filters.items(), key=lambda x: x[1], reverse=True)

        for field, count in sorted_filters:
            md.append(f"- `{field}` ({count} unique values)\n")

    md.append("\n---\n")
    md.append("*Generated by automated tool annotation review workflow*\n")

    return ''.join(md)


def save_suggestions_to_file(
    suggestions: Dict[str, Dict[str, int]],
    filters: Dict[str, int],
    output_file: Path
) -> None:
    """
    Save suggestions to JSON file for potential automated processing.

    Args:
        suggestions: Field suggestions with counts
        filters: Filter candidates
        output_file: Path to output file
    """
    data = {
        'suggestions': suggestions,
        'filters': filters,
        'materialized_view': MATERIALIZED_VIEW_ID,
        'tool_fields_reviewed': list(TOOL_RELATED_FIELDS)
    }

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved suggestions to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Review tool-related Synapse annotations and suggest schema additions'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('tool_annotation_suggestions.json'),
        help='Output file for suggestions (JSON format)'
    )
    parser.add_argument(
        '--markdown',
        type=Path,
        default=Path('tool_annotation_suggestions.md'),
        help='Output file for markdown summary'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print suggestions without modifying files'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of records to query (for testing)'
    )

    args = parser.parse_args()

    # Check for Synapse authentication
    auth_token = os.environ.get('SYNAPSE_AUTH_TOKEN')
    if not auth_token:
        logger.error("SYNAPSE_AUTH_TOKEN environment variable not set")
        sys.exit(1)

    try:
        # Initialize Synapse client
        syn = Synapse()
        syn.login(authToken=auth_token)
        logger.info("Logged into Synapse")

        # Load tools schema
        logger.info("Loading tools schema values...")
        schema_values = load_tools_schema_values()

        # Load metadata dictionary enums for synonym checking
        logger.info("Loading metadata dictionary enums for synonym checking...")
        metadata_enums = load_metadata_dict_enums()
        slot_enum_map = load_metadata_dict_slot_mappings()

        # Query annotations
        records = query_synapse_annotations(syn, limit=args.limit)

        # Analyze tool-related annotations
        logger.info("Analyzing tool-related annotations...")
        suggestions, filters = analyze_tool_annotations(
            records,
            schema_values,
            metadata_enums,
            slot_enum_map
        )

        # Format as markdown
        markdown = format_suggestions_as_markdown(suggestions, filters)

        if args.dry_run:
            logger.info("Dry run - printing results:")
            print("\n" + "="*80)
            print(markdown)
            print("="*80)
        else:
            # Save files
            save_suggestions_to_file(suggestions, filters, args.output)

            with open(args.markdown, 'w') as f:
                f.write(markdown)
            logger.info(f"Saved markdown to {args.markdown}")

        # Summary
        total_suggestions = sum(len(v) for v in suggestions.values())
        logger.info(f"\nSummary:")
        logger.info(f"  - {len(suggestions)} tool fields with suggested additions")
        logger.info(f"  - {total_suggestions} total value suggestions")
        logger.info(f"  - {len(filters)} potential search filters")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
