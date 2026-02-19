#!/usr/bin/env python3
"""
Regenerate FILTERED_*.csv files from enriched VALIDATED_*.csv files.

This script:
1. Reads VALIDATED_*.csv files (after metadata enrichment)
2. Calculates completeness on enriched schema fields
3. Filters to high-completeness subset (≥60% critical fields)
4. Enriches funderId for high-confidence development publications
5. Writes to FILTERED_*.csv files

This ensures FILTERED files include tools that became complete after enrichment.
"""

import os
import sys
import json
import re
import pandas as pd
from pathlib import Path
from typing import Dict, Optional

# Import from format_validation_for_submission
sys.path.insert(0, str(Path(__file__).parent))
from format_validation_for_submission import (
    normalize_tool_type,
    has_minimum_critical_fields,
    MIN_COMPLETENESS_FOR_PRIORITY,
    CRITICAL_FIELDS_BY_TYPE
)


# Known funders from Synapse table syn26486830
KNOWN_FUNDERS = [
    {
        'funderId': '55d4b7cf-3cd9-49ba-9f9e-e44b7f917330',
        'funderName': 'Gilbert Family Foundation',
        'aliases': ['Gilbert Family Foundation', 'GFF']
    },
    {
        'funderId': 'e57a7c37-49e9-4466-8f38-5226f3525460',
        'funderName': "Children's Tumor Foundation",
        'aliases': ["Children's Tumor Foundation", 'CTF']
    },
    {
        'funderId': '57ded652-4826-4058-bfb6-1c61ac8bd357',
        'funderName': 'Neurofibromatosis Therapeutic Acceleration Program',
        'aliases': ['Neurofibromatosis Therapeutic Acceleration Program', 'NTAP']
    },
    {
        'funderId': '0ba0958e-36c4-41f7-af13-7ea7fde0b7c9',
        'funderName': 'National Cancer Institute',
        'aliases': ['National Cancer Institute', 'NCI', 'NIH-NCI']  # NIH-NCI from fundingAgency
    },
    {
        'funderId': '3ceffe3e-3897-4ea8-9188-49d8056a07f6',
        'funderName': 'Congressionally Directed Medical Research Programs (CDMRP) Neurofibromatosis Research Program (NFRP)',
        'aliases': [
            'Congressionally Directed Medical Research Programs',
            'CDMRP',
            'Neurofibromatosis Research Program',
            'NFRP',
            'Department of Defense',
            'DoD'
        ]
    }
]

# Mapping for fundingAgency abbreviations (from syn16857542) to funderId
FUNDING_AGENCY_MAP = {
    'CTF': 'e57a7c37-49e9-4466-8f38-5226f3525460',
    'GFF': '55d4b7cf-3cd9-49ba-9f9e-e44b7f917330',
    'NIH-NCI': '0ba0958e-36c4-41f7-af13-7ea7fde0b7c9',
    'NTAP': '57ded652-4826-4058-bfb6-1c61ac8bd357',
    'CDMRP': '3ceffe3e-3897-4ea8-9188-49d8056a07f6',
    'NFRP': '3ceffe3e-3897-4ea8-9188-49d8056a07f6',
    'DoD': '3ceffe3e-3897-4ea8-9188-49d8056a07f6'
}

# Development tool types that need funderId
DEVELOPMENT_TOOL_TYPES = [
    'Computational Tool',
    'Patient-Derived Model',
    'Advanced Cellular Model',
    'Clinical Assessment Tool'
]


# Mapping of VALIDATED file names to their tool types
VALIDATED_FILE_TO_TYPE = {
    'VALIDATED_animal_models.csv': 'Animal Model',
    'VALIDATED_antibodies.csv': 'Antibody',
    'VALIDATED_cell_lines.csv': 'Cell Line',
    'VALIDATED_genetic_reagents.csv': 'Genetic Reagent',
    'VALIDATED_computational_tools.csv': 'Computational Tool',
    'VALIDATED_patient_derived_models.csv': 'Patient-Derived Model',
    'VALIDATED_advanced_cellular_models.csv': 'Advanced Cellular Model',
    'VALIDATED_clinical_assessment_tools.csv': 'Clinical Assessment Tool'
}


def load_publication_cache() -> Dict[str, Dict]:
    """
    Load publication abstracts and methods from cache for funder extraction.

    Returns:
        Dict mapping PMID -> publication data (abstract, methods, etc.)
    """
    pub_cache = {}

    # Try multiple cache locations
    cache_dirs = [
        Path('tool_coverage/outputs/publication_cache'),
        Path('tool-coverage-reports/tool_reviews/publication_cache'),
        Path('tool-coverage-reports-partial/tool_reviews/publication_cache')
    ]

    for cache_dir in cache_dirs:
        if not cache_dir.exists():
            continue

        for cache_file in cache_dir.glob('*_text.json'):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    pmid = data.get('pmid', '').replace('PMID:', '').strip()
                    if pmid:
                        pub_cache[pmid] = data
            except Exception:
                continue

    return pub_cache


def extract_funder_from_text(text: str) -> Optional[str]:
    """
    Extract funder ID from publication text by matching against known funders.

    Searches for exact matches of funder names and their common aliases.

    Args:
        text: Combined publication text (abstract, methods, etc.)

    Returns:
        funderId if match found, None otherwise
    """
    if not text:
        return None

    # Search for exact matches (case-insensitive)
    for funder in KNOWN_FUNDERS:
        for alias in funder['aliases']:
            # Use word boundaries for exact matching
            pattern = r'\b' + re.escape(alias) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                return funder['funderId']

    return None


def enrich_funder_id(row: pd.Series, pub_cache: Dict[str, Dict]) -> str:
    """
    Enrich funderId for a single development tool row.

    Priority:
    1. Keep existing funderId if already populated
    2. Map from fundingAgency abbreviations if present
    3. Map from funderName if present
    4. Extract from publication text

    Args:
        row: DataFrame row for a single tool
        pub_cache: Publication cache data

    Returns:
        funderId or empty string
    """
    # 1. Keep existing funderId if present
    existing_funder = row.get('funderId', '')
    if pd.notna(existing_funder) and existing_funder and existing_funder != '':
        return existing_funder

    # 2. Map from fundingAgency if present (e.g., 'CTF', 'GFF', 'NIH-NCI')
    funding_agency = row.get('fundingAgency', '')
    if pd.notna(funding_agency) and funding_agency:
        # Handle list format ['CTF'] or string format 'CTF'
        if isinstance(funding_agency, str):
            funding_agency = funding_agency.strip("[]'\"")
            if funding_agency in FUNDING_AGENCY_MAP:
                return FUNDING_AGENCY_MAP[funding_agency]

    # 3. Map from funderName if present (from syn51730943)
    funder_name = row.get('funderName', '')
    if pd.notna(funder_name) and funder_name:
        for funder in KNOWN_FUNDERS:
            if funder_name.lower() == funder['funderName'].lower():
                return funder['funderId']

    # 4. Extract from publication text
    pmid = str(row.get('_pmid', '')).replace('PMID:', '').strip()
    if pmid and pmid in pub_cache:
        pub_data = pub_cache[pmid]

        # Combine available text sections
        text_parts = []
        for field in ['abstract', 'methods', 'introduction', 'results', 'discussion']:
            if field in pub_data and pub_data[field]:
                text_parts.append(str(pub_data[field]))

        combined_text = ' '.join(text_parts)
        funder_id = extract_funder_from_text(combined_text)
        if funder_id:
            return funder_id

    # No funder found
    return ''


def calculate_completeness_on_enriched_data(df, tool_type):
    """
    Calculate completeness for enriched data (schema fields exist).

    Args:
        df: DataFrame with enriched schema fields
        tool_type: Normalized tool type

    Returns:
        DataFrame with added completeness columns
    """
    critical_fields = CRITICAL_FIELDS_BY_TYPE.get(tool_type, [])

    if not critical_fields:
        # No critical fields required - all tools pass
        df['_completenessPercentage'] = 100.0
        df['_filledFields'] = 0
        df['_totalFields'] = 0
        df['_meetsThreshold'] = True
        return df

    completeness_list = []
    filled_list = []
    total_list = []
    meets_threshold_list = []

    for _, row in df.iterrows():
        filled_count = 0
        for field in critical_fields:
            value = row.get(field)
            if pd.notna(value) and value != "" and value != "NULL":
                filled_count += 1

        total_count = len(critical_fields)
        completeness_pct = (filled_count / total_count * 100) if total_count > 0 else 0
        meets_threshold = (filled_count / total_count) >= MIN_COMPLETENESS_FOR_PRIORITY if total_count > 0 else True

        completeness_list.append(completeness_pct)
        filled_list.append(filled_count)
        total_list.append(total_count)
        meets_threshold_list.append(meets_threshold)

    df['_completenessPercentage'] = completeness_list
    df['_filledFields'] = filled_list
    df['_totalFields'] = total_list
    df['_meetsThreshold'] = meets_threshold_list

    return df


def regenerate_filtered_file(validated_file, tool_type, outputs_dir, pub_cache):
    """
    Regenerate FILTERED file from enriched VALIDATED file.

    Args:
        validated_file: Path to VALIDATED_*.csv file
        tool_type: Normalized tool type
        outputs_dir: Output directory path
        pub_cache: Publication cache for funder extraction

    Returns:
        Number of tools in filtered subset
    """
    validated_path = os.path.join(outputs_dir, validated_file)
    filtered_file = validated_file.replace('VALIDATED_', 'FILTERED_')
    filtered_path = os.path.join(outputs_dir, filtered_file)

    if not os.path.exists(validated_path):
        print(f"  ⚠️  {validated_file} not found - skipping")
        return 0

    # Read validated file
    df = pd.read_csv(validated_path)
    total_tools = len(df)

    if total_tools == 0:
        print(f"  📄 {validated_file}: 0 tools - skipping")
        return 0

    # Calculate completeness on enriched data
    df = calculate_completeness_on_enriched_data(df, tool_type)

    # Filter to high-completeness subset
    filtered_df = df[df['_meetsThreshold'] == True].copy()
    filtered_count = len(filtered_df)

    # Remove temporary threshold column before saving
    filtered_df = filtered_df.drop(columns=['_meetsThreshold'])

    # Enrich funderId for development publications (only high-confidence tools)
    if tool_type in DEVELOPMENT_TOOL_TYPES and 'funderId' in filtered_df.columns:
        print(f"    └─ Enriching funderId for {filtered_count} development tools...")
        funders_enriched = 0
        for idx in filtered_df.index:
            funder_id = enrich_funder_id(filtered_df.loc[idx], pub_cache)
            if funder_id:
                # Only count as enriched if funderId was previously empty
                was_empty = pd.isna(filtered_df.at[idx, 'funderId']) or filtered_df.at[idx, 'funderId'] == ''
                filtered_df.at[idx, 'funderId'] = funder_id
                if was_empty:
                    funders_enriched += 1

        if funders_enriched > 0:
            print(f"    └─ Enriched funderId for {funders_enriched}/{filtered_count} tools")

    # Save filtered file
    filtered_df.to_csv(filtered_path, index=False)

    # Report statistics
    if total_tools > 0:
        percentage = (filtered_count / total_tools) * 100
        print(f"  ✓ {validated_file}: {filtered_count}/{total_tools} tools ({percentage:.1f}%) meet threshold")
        if filtered_count < total_tools:
            incomplete = total_tools - filtered_count
            print(f"    └─ Excluded {incomplete} tools with <60% critical fields")
    else:
        print(f"  📄 {validated_file}: 0 tools")

    return filtered_count


def main():
    """Regenerate all FILTERED_*.csv files from enriched VALIDATED_*.csv files."""
    print("=" * 80)
    print("REGENERATING FILTERED_*.csv FILES FROM ENRICHED DATA")
    print("=" * 80)
    print(f"\nMinimum completeness threshold: {int(MIN_COMPLETENESS_FOR_PRIORITY * 100)}%")
    print("\nCritical fields by tool type:")
    for tool_type, fields in CRITICAL_FIELDS_BY_TYPE.items():
        if fields:
            print(f"  - {tool_type}: {', '.join(fields)}")
        else:
            print(f"  - {tool_type}: (no critical fields required)")
    print()

    outputs_dir = 'tool_coverage/outputs'
    if not os.path.exists(outputs_dir):
        print(f"❌ Error: {outputs_dir} directory not found")
        sys.exit(1)

    # Load publication cache for funder extraction (development tools only)
    print("Loading publication cache for funder extraction...")
    pub_cache = load_publication_cache()
    print(f"  ✓ Loaded cache for {len(pub_cache)} publications")
    print()

    print("Processing enriched VALIDATED_*.csv files...")
    print("-" * 80)

    total_filtered = 0
    total_validated = 0

    for validated_file, tool_type in VALIDATED_FILE_TO_TYPE.items():
        filtered_count = regenerate_filtered_file(validated_file, tool_type, outputs_dir, pub_cache)
        total_filtered += filtered_count

        # Count validated tools
        validated_path = os.path.join(outputs_dir, validated_file)
        if os.path.exists(validated_path):
            validated_df = pd.read_csv(validated_path)
            total_validated += len(validated_df)

    print("-" * 80)
    print(f"\n✅ Regeneration complete!")
    print(f"   Total validated tools: {total_validated}")
    print(f"   Total filtered tools: {total_filtered}")
    if total_validated > 0:
        print(f"   Percentage meeting threshold: {(total_filtered/total_validated)*100:.1f}%")
    print()
    print("Next steps:")
    print("  1. Review FILTERED_*.csv files for priority manual review")
    print("  2. Commit changes to trigger upsert-tools.yml workflow")
    print("  3. Upsert to Synapse after PR merge or manual trigger")


if __name__ == '__main__':
    main()
