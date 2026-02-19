#!/usr/bin/env python3
"""
Regenerate FILTERED_*.csv files from enriched VALIDATED_*.csv files.

This script:
1. Reads VALIDATED_*.csv files (after metadata enrichment)
2. Calculates completeness on enriched schema fields
3. Filters to high-completeness subset (≥60% critical fields)
4. Writes to FILTERED_*.csv files

This ensures FILTERED files include tools that became complete after enrichment.
"""

import os
import sys
import pandas as pd
from pathlib import Path

# Import from format_validation_for_submission
sys.path.insert(0, str(Path(__file__).parent))
from format_validation_for_submission import (
    normalize_tool_type,
    has_minimum_critical_fields,
    MIN_COMPLETENESS_FOR_PRIORITY,
    CRITICAL_FIELDS_BY_TYPE
)


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


def regenerate_filtered_file(validated_file, tool_type, outputs_dir):
    """
    Regenerate FILTERED file from enriched VALIDATED file.

    Args:
        validated_file: Path to VALIDATED_*.csv file
        tool_type: Normalized tool type
        outputs_dir: Output directory path

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

    print("Processing enriched VALIDATED_*.csv files...")
    print("-" * 80)

    total_filtered = 0
    total_validated = 0

    for validated_file, tool_type in VALIDATED_FILE_TO_TYPE.items():
        filtered_count = regenerate_filtered_file(validated_file, tool_type, outputs_dir)
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
