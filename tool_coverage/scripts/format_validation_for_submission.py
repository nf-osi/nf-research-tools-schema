#!/usr/bin/env python3
"""
Format Sonnet validation results into VALIDATED_*.csv files for Synapse submission.

This is the CONSOLIDATED formatting script that processes ALL validated tools:
1. Accepted mined tools (from validation_summary.json - tools that passed Sonnet review)
2. Missed tools (from potentially_missed_tools.csv - tools Sonnet found that mining missed)
3. Observations (from observations.csv)

The output VALIDATED_*.csv files contain ALL tools that passed AI validation,
combining both mining results (filtered for false positives) and newly discovered tools.
"""

import pandas as pd
import uuid
import sys
import os
import json
from pathlib import Path

def generate_uuid():
    """Generate a UUID for new entries."""
    return str(uuid.uuid4())


def load_accepted_tools(validation_summary_file):
    """
    Load accepted tools from validation_summary.json.

    These are tools that were mined and then validated by Sonnet as real tools
    (false positives removed).

    Returns:
        DataFrame with columns: toolName, toolType, pmid, confidence, contextSnippet, etc.
    """
    if not os.path.exists(validation_summary_file):
        print(f"⚠️  {validation_summary_file} not found - skipping accepted mined tools")
        return pd.DataFrame()

    with open(validation_summary_file, 'r') as f:
        validation_data = json.load(f)

    accepted_tools = []

    for pub in validation_data:
        pmid = pub.get('pmid', '')

        # Extract accepted tools from this publication
        for tool in pub.get('acceptedTools', []):
            accepted_tools.append({
                'toolName': tool.get('toolName'),
                'toolType': tool.get('toolType'),
                'foundIn': tool.get('foundIn', 'methods'),
                'contextSnippet': tool.get('usageContext', ''),
                'confidence': tool.get('confidence', 0.9),
                'pmid': pmid,
                'reasoning': tool.get('reasoning', ''),
                'whyMissed': '',  # Not applicable - this was mined successfully
                'shouldBeAdded': True,  # Already validated as accepted
                'source': 'mined_and_validated'
            })

    return pd.DataFrame(accepted_tools)


def format_validated_tools(tools_df):
    """
    Format validated tools by type.

    Args:
        tools_df: DataFrame from potentially_missed_tools.csv filtered for shouldBeAdded=True

    Returns:
        Dictionary mapping tool type to formatted DataFrames
    """
    tool_dfs = {}

    # Group by tool type
    for tool_type in tools_df['toolType'].unique():
        if pd.isna(tool_type) or tool_type == 'toolType':
            continue

        type_tools = tools_df[tools_df['toolType'] == tool_type].copy()

        if tool_type == 'computational_tool':
            formatted = format_computational_tools(type_tools)
            tool_dfs['Computational Tool'] = formatted

        elif tool_type == 'animal_model':
            formatted = format_animal_models(type_tools)
            tool_dfs['Animal Model'] = formatted

        elif tool_type == 'antibody':
            formatted = format_antibodies(type_tools)
            tool_dfs['Antibody'] = formatted

        elif tool_type == 'cell_line':
            formatted = format_cell_lines(type_tools)
            tool_dfs['Cell Line'] = formatted

        elif tool_type == 'genetic_reagent':
            formatted = format_genetic_reagents(type_tools)
            tool_dfs['Genetic Reagent'] = formatted

        elif tool_type == 'clinical_assessment_tool':
            formatted = format_clinical_assessment_tools(type_tools)
            tool_dfs['Clinical Assessment Tool'] = formatted

        elif tool_type == 'advanced_cellular_model':
            formatted = format_advanced_cellular_models(type_tools)
            tool_dfs['Advanced Cellular Model'] = formatted

        elif tool_type == 'patient_derived_model':
            formatted = format_patient_derived_models(type_tools)
            tool_dfs['Patient-Derived Model'] = formatted

    return tool_dfs


def format_computational_tools(tools_df):
    """Format computational tools for Synapse ComputationalToolDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'computationalToolId': tool_id,
            'toolName': tool['toolName'],
            'toolType': '',  # Needs manual curation
            'softwareRepositoryURL': '',
            'softwareApplicationURL': '',
            'programmingLanguage': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_animal_models(tools_df):
    """Format animal models for Synapse AnimalModelDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'animalModelId': tool_id,
            'strainNomenclature': tool['toolName'],
            'backgroundStrain': '',  # Needs manual curation
            'nf1Genotype': '',
            'nf2Genotype': '',
            'otherGeneticAlteration': '',
            'transplantation': '',
            'tumorType': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_antibodies(tools_df):
    """Format antibodies for Synapse AntibodyDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'antibodyId': tool_id,
            'targetAntigen': tool['toolName'],
            'hostOrganism': '',  # Needs manual curation
            'clonality': '',
            'vendor': '',
            'catalogNumber': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_cell_lines(tools_df):
    """Format cell lines for Synapse CellLineDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'cellLineId': tool_id,
            'lineName': tool['toolName'],
            'atccID': '',  # Needs manual curation
            'organism': '',
            'organ': '',
            'tissue': '',
            'cellType': '',
            'nf1Genotype': '',
            'nf2Genotype': '',
            'disease': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_cellLineName': tool['toolName'],  # For Resource table linking
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_genetic_reagents(tools_df):
    """Format genetic reagents for Synapse GeneticReagentDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'geneticReagentId': tool_id,
            'insertName': tool['toolName'],
            'promoter': '',  # Needs manual curation
            'insert': '',
            'vectorBackbone': '',
            'selectionMarker': '',
            'insertType': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_clinical_assessment_tools(tools_df):
    """Format clinical assessment tools for Synapse ClinicalAssessmentToolDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'clinicalAssessmentToolId': tool_id,
            'toolName': tool['toolName'],
            'assessmentType': '',  # Needs manual curation
            'targetCondition': '',
            'ageRange': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_advanced_cellular_models(tools_df):
    """Format advanced cellular models for Synapse AdvancedCellularModelDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'advancedCellularModelId': tool_id,
            'modelName': tool['toolName'],
            'modelType': '',  # Needs manual curation (organoid, spheroid, etc.)
            'derivedFrom': '',
            'nf1Genotype': '',
            'nf2Genotype': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_patient_derived_models(tools_df):
    """Format patient-derived models for Synapse PatientDerivedModelDetails table."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'patientDerivedModelId': tool_id,
            'modelName': tool['toolName'],
            'modelType': '',  # Needs manual curation (PDX, PDO, etc.)
            'tumorType': '',
            'patientAge': '',
            'patientSex': '',
            'nf1Genotype': '',
            'nf2Genotype': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_observations(obs_df):
    """Format observations for Synapse Observations table."""
    rows = []

    for _, obs in obs_df.iterrows():
        rows.append({
            'observationId': generate_uuid(),
            'resourceName': obs.get('resourceName', ''),
            'resourceType': obs.get('resourceType', ''),
            'observationType': obs.get('observationType', ''),
            'details': obs.get('details', ''),
            'referencePublication': obs.get('doi', ''),
            # Tracking fields
            '_pmid': obs.get('pmid', ''),
            '_foundIn': obs.get('foundIn', ''),
            '_confidence': obs.get('confidence', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print("FORMATTING AI VALIDATION RESULTS FOR SYNAPSE SUBMISSION")
    print("=" * 80)
    print("\nThis script combines ALL validated tools:")
    print("  1. Accepted mined tools (passed Sonnet validation)")
    print("  2. Missed tools (found by Sonnet, not by mining)")
    print()

    # Create outputs directory
    os.makedirs('tool_coverage/outputs', exist_ok=True)

    # Load accepted mined tools from validation summary
    print("1. Loading accepted mined tools from validation_summary.json...")
    validation_summary_file = 'tool_reviews/validation_summary.json'
    accepted_df = load_accepted_tools(validation_summary_file)
    print(f"   ✓ {len(accepted_df)} tools mined and validated by Sonnet")

    # Load potentially missed tools
    print("\n2. Loading missed tools from potentially_missed_tools.csv...")
    tools_file = 'tool_reviews/potentially_missed_tools.csv'
    if not os.path.exists(tools_file):
        print(f"   ⚠️  {tools_file} not found - skipping missed tools")
        missed_df = pd.DataFrame()
    else:
        tools_df = pd.read_csv(tools_file)
        print(f"   - {len(tools_df)} potential tools identified by Sonnet")

        # Filter for validated tools (shouldBeAdded=True or 'True')
        missed_df = tools_df[
            (tools_df['shouldBeAdded'] == True) |
            (tools_df['shouldBeAdded'] == 'True')
        ].copy()
        missed_df['source'] = 'found_by_sonnet'
        print(f"   ✓ {len(missed_df)} missed tools validated as real (shouldBeAdded=True)")

    # Combine accepted and missed tools
    if not accepted_df.empty and not missed_df.empty:
        # Ensure both have the same columns
        all_columns = set(accepted_df.columns) | set(missed_df.columns)
        for col in all_columns:
            if col not in accepted_df.columns:
                accepted_df[col] = ''
            if col not in missed_df.columns:
                missed_df[col] = ''

        validated_df = pd.concat([accepted_df, missed_df], ignore_index=True)
    elif not accepted_df.empty:
        validated_df = accepted_df
    elif not missed_df.empty:
        validated_df = missed_df
    else:
        print("\n⚠️  No validated tools found from either source. Nothing to format.")
        sys.exit(0)

    print(f"\n3. Combined total: {len(validated_df)} validated tools")

    # Format tools by type
    print("\n4. Formatting VALIDATED tool submissions by type...")
    tool_dfs = format_validated_tools(validated_df)

    # Save each tool type
    type_file_map = {
        'Computational Tool': 'computational_tools',
        'Animal Model': 'animal_models',
        'Antibody': 'antibodies',
        'Cell Line': 'cell_lines',
        'Genetic Reagent': 'genetic_reagents',
        'Clinical Assessment Tool': 'clinical_assessment_tools',
        'Advanced Cellular Model': 'advanced_cellular_models',
        'Patient-Derived Model': 'patient_derived_models'
    }

    for tool_type, file_suffix in type_file_map.items():
        if tool_type in tool_dfs and not tool_dfs[tool_type].empty:
            df = tool_dfs[tool_type]
            output_file = f'tool_coverage/outputs/VALIDATED_{file_suffix}.csv'
            df.to_csv(output_file, index=False)
            print(f"   ✓ {len(df)} {tool_type}s → {output_file}")
        else:
            print(f"   - {tool_type}s... (none validated)")

    # Load and format observations
    print("\n5. Formatting observations...")
    obs_file = 'tool_reviews/observations.csv'
    if os.path.exists(obs_file):
        obs_df = pd.read_csv(obs_file)
        print(f"   - {len(obs_df)} observations found")

        if not obs_df.empty:
            formatted_obs = format_observations(obs_df)
            output_file = 'tool_coverage/outputs/VALIDATED_observations.csv'
            formatted_obs.to_csv(output_file, index=False)
            print(f"   ✓ {len(formatted_obs)} observations → {output_file}")
        else:
            print("   - No observations to format")
            formatted_obs = pd.DataFrame()
    else:
        print(f"   ⚠️  {obs_file} not found")
        formatted_obs = pd.DataFrame()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_tools = sum(len(df) for df in tool_dfs.values())

    print(f"\nValidated tools by source:")
    print(f"   - Mined and validated: {len(accepted_df)}")
    print(f"   - Found by Sonnet: {len(missed_df)}")
    print(f"   - Total: {total_tools}")

    print(f"\nValidated tools by type:")
    for tool_type in sorted(tool_dfs.keys()):
        if not tool_dfs[tool_type].empty:
            print(f"   - {tool_type}: {len(tool_dfs[tool_type])}")

    if not formatted_obs.empty:
        print(f"\nObservations: {len(formatted_obs)}")

    print("\n📋 VALIDATED Files Created:")
    for tool_type, file_suffix in type_file_map.items():
        if tool_type in tool_dfs and not tool_dfs[tool_type].empty:
            print(f"   - VALIDATED_{file_suffix}.csv ({len(tool_dfs[tool_type])} entries)")
    if not formatted_obs.empty:
        print(f"   - VALIDATED_observations.csv ({len(formatted_obs)} entries)")

    print("\n✅ Validation formatting complete!")
    print("   These VALIDATED_*.csv files are AI-reviewed with false positives removed.")
    print("   They can be uploaded via the upsert-tools.yml workflow.")


if __name__ == '__main__':
    main()
