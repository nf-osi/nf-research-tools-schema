#!/usr/bin/env python3
"""
Generate PMID-level review summary table.

Creates a comprehensive table where each row is a PMID with:
- Publication metadata
- Tool counts (mined, accepted, rejected, missed)
- New tools discovered by Sonnet
- Existing tools in Synapse
- Key observations
- Critical metadata fields extracted

This table is for review purposes, NOT for Synapse upload.
"""

import pandas as pd
import json
from pathlib import Path
import sys

REVIEW_OUTPUT_DIR = Path('tool_reviews')
VALIDATION_SUMMARY = REVIEW_OUTPUT_DIR / 'validation_summary.json'
MISSED_TOOLS = REVIEW_OUTPUT_DIR / 'potentially_missed_tools.csv'
OBSERVATIONS = REVIEW_OUTPUT_DIR / 'observations.csv'
OUTPUT_FILE = Path('tool_coverage/outputs/PMID_REVIEW_SUMMARY.csv')


def load_validation_summary():
    """Load validation summary JSON."""
    if not VALIDATION_SUMMARY.exists():
        print(f"⚠️  {VALIDATION_SUMMARY} not found")
        return []

    with open(VALIDATION_SUMMARY, 'r') as f:
        return json.load(f)


def load_missed_tools():
    """Load potentially missed tools CSV."""
    if not MISSED_TOOLS.exists():
        print(f"⚠️  {MISSED_TOOLS} not found")
        return pd.DataFrame()

    return pd.read_csv(MISSED_TOOLS)


def load_observations():
    """Load observations CSV."""
    if not OBSERVATIONS.exists():
        print(f"⚠️  {OBSERVATIONS} not found")
        return pd.DataFrame()

    return pd.read_csv(OBSERVATIONS)


def generate_review_summary():
    """Generate PMID-level review summary table."""
    print("\n" + "="*80)
    print("GENERATING PMID-LEVEL REVIEW SUMMARY TABLE")
    print("="*80)
    print()

    # Load data
    print("Loading validation data...")
    validation_data = load_validation_summary()
    missed_tools_df = load_missed_tools()
    observations_df = load_observations()

    if not validation_data:
        print("❌ No validation data found - cannot generate review summary")
        return

    print(f"  ✓ Loaded {len(validation_data)} publications from validation summary")
    print(f"  ✓ Loaded {len(missed_tools_df)} missed tools")
    print(f"  ✓ Loaded {len(observations_df)} observations")
    print()

    # Build summary table
    summary_rows = []

    for pub in validation_data:
        pmid = pub.get('pmid', '').replace('PMID:', '').strip()

        # Publication metadata
        row = {
            'pmid': pmid,
            'publicationTitle': pub.get('publicationTitle', ''),
            'doi': pub.get('doi', ''),
            'year': pub.get('year', ''),
            'journal': pub.get('journal', ''),
            'publicationType': pub.get('publicationType', ''),
            'queryType': pub.get('queryType', ''),
        }

        # Tool counts
        accepted_tools = pub.get('acceptedTools', [])
        rejected_tools = pub.get('rejectedTools', [])
        uncertain_tools = pub.get('uncertainTools', [])

        row['totalMinedTools'] = len(accepted_tools) + len(rejected_tools) + len(uncertain_tools)
        row['acceptedTools'] = len(accepted_tools)
        row['rejectedTools'] = len(rejected_tools)
        row['uncertainTools'] = len(uncertain_tools)

        # Missed tools for this PMID
        pmid_missed = missed_tools_df[missed_tools_df['pmid'] == pmid] if not missed_tools_df.empty else pd.DataFrame()
        row['missedTools'] = len(pmid_missed)

        # Tool type breakdown (accepted tools only)
        tool_types = {}
        for tool in accepted_tools:
            ttype = tool.get('toolType', 'unknown')
            tool_types[ttype] = tool_types.get(ttype, 0) + 1

        row['cellLines'] = tool_types.get('cell_line', 0)
        row['animalModels'] = tool_types.get('animal_model', 0)
        row['geneticReagents'] = tool_types.get('genetic_reagent', 0)
        row['antibodies'] = tool_types.get('antibody', 0)
        row['computationalTools'] = tool_types.get('computational_tool', 0)
        row['patientDerivedModels'] = tool_types.get('patient_derived_model', 0)
        row['advancedCellularModels'] = tool_types.get('advanced_cellular_model', 0)
        row['clinicalAssessmentTools'] = tool_types.get('clinical_assessment_tool', 0)

        # New tools discovered by Sonnet (from missed tools)
        if not pmid_missed.empty:
            new_tools_list = pmid_missed['toolName'].tolist()
            row['newToolsDiscovered'] = '; '.join(str(t) for t in new_tools_list[:5])  # First 5
            if len(new_tools_list) > 5:
                row['newToolsDiscovered'] += f' ... ({len(new_tools_list)-5} more)'
        else:
            row['newToolsDiscovered'] = ''

        # Accepted tool names (first 5)
        if accepted_tools:
            accepted_names = [t.get('toolName', '') for t in accepted_tools[:5]]
            row['acceptedToolNames'] = '; '.join(accepted_names)
            if len(accepted_tools) > 5:
                row['acceptedToolNames'] += f' ... ({len(accepted_tools)-5} more)'
        else:
            row['acceptedToolNames'] = ''

        # Observations count for this PMID
        pmid_obs = observations_df[observations_df['pmid'] == pmid] if not observations_df.empty else pd.DataFrame()
        row['observationsExtracted'] = len(pmid_obs)

        # Observation types (top 3)
        if not pmid_obs.empty and 'observationType' in pmid_obs.columns:
            obs_types = pmid_obs['observationType'].value_counts().head(3)
            obs_summary = [f"{otype}({count})" for otype, count in obs_types.items()]
            row['topObservationTypes'] = '; '.join(obs_summary)
        else:
            row['topObservationTypes'] = ''

        # Critical metadata extracted (sample from first accepted tool)
        critical_metadata = []
        if accepted_tools:
            first_tool = accepted_tools[0]
            metadata = first_tool.get('metadata', {})

            # Check for common critical fields
            for field in ['organ', 'tissue', 'backgroundStrain', 'vectorType',
                         'targetAntigen', 'softwareType', 'modelSystemType',
                         'assessmentType', 'tumorType']:
                if field in metadata and metadata[field]:
                    value = metadata[field]
                    # Truncate if too long
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:47] + '...'
                    critical_metadata.append(f"{field}={value}")

        row['sampleMetadata'] = '; '.join(critical_metadata[:3])  # First 3 fields

        # Review status
        has_methods = pub.get('hasMethodsSection', 'Unknown')
        likely_tools = pub.get('likelyContainsTools', 'Unknown')
        row['hasMethodsSection'] = has_methods
        row['likelyContainsTools'] = likely_tools

        # Major issues
        major_issues = pub.get('majorIssuesFound', '')
        row['majorIssues'] = major_issues[:100] if major_issues else ''  # First 100 chars

        # Context snippet (from first accepted tool)
        if accepted_tools:
            context = accepted_tools[0].get('contextSnippet', '')
            row['sampleContext'] = context[:150] if context else ''  # First 150 chars
        else:
            row['sampleContext'] = ''

        summary_rows.append(row)

    # Create DataFrame
    summary_df = pd.DataFrame(summary_rows)

    # Reorder columns for readability
    column_order = [
        'pmid', 'publicationTitle', 'year', 'journal', 'publicationType', 'queryType',
        'totalMinedTools', 'acceptedTools', 'rejectedTools', 'uncertainTools', 'missedTools',
        'cellLines', 'animalModels', 'geneticReagents', 'antibodies',
        'computationalTools', 'patientDerivedModels', 'advancedCellularModels', 'clinicalAssessmentTools',
        'acceptedToolNames', 'newToolsDiscovered',
        'observationsExtracted', 'topObservationTypes',
        'sampleMetadata', 'sampleContext',
        'hasMethodsSection', 'likelyContainsTools', 'majorIssues', 'doi'
    ]

    summary_df = summary_df[column_order]

    # Sort by number of accepted tools (descending)
    summary_df = summary_df.sort_values('acceptedTools', ascending=False)

    # Save to CSV
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(OUTPUT_FILE, index=False)

    print("="*80)
    print("✅ REVIEW SUMMARY TABLE GENERATED")
    print("="*80)
    print(f"\nOutput: {OUTPUT_FILE}")
    print(f"Total publications: {len(summary_df)}")
    print(f"Total accepted tools: {summary_df['acceptedTools'].sum()}")
    print(f"Total rejected tools: {summary_df['rejectedTools'].sum()}")
    print(f"Total missed tools found: {summary_df['missedTools'].sum()}")
    print(f"Total observations extracted: {summary_df['observationsExtracted'].sum()}")
    print()

    # Print top 10 publications by tool count
    print("Top 10 publications by accepted tools:")
    print("-" * 80)
    top_10 = summary_df.head(10)
    for idx, row in top_10.iterrows():
        print(f"  {row['pmid']:12} | {row['acceptedTools']:2} tools | {row['publicationTitle'][:60]}")
    print()


if __name__ == '__main__':
    generate_review_summary()
