#!/usr/bin/env python3
"""
Tool Completeness Scoring Script

This script calculates completeness scores for research tools and biobanks
in the NF-OSI database. The scoring system evaluates resources across multiple dimensions:
- Availability (30 points): Biobank URL, vendor/developer info, RRID, and DOI
- Critical Info (30 points): Type-specific essential fields
- Other Info (15 points): Type-specific additional fields
- Observations (25 points): Scientific characterizations with DOI weighting

Total Maximum Score: 100 points
"""

import synapseclient
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import os


def count_filled(x):
    """Count non-NA, non-empty values"""
    if x.size == 0 or pd.isna(x) or x == "" or x == "NULL":
        return 0
    return 1


def is_filled(value):
    """Check if a value is filled"""
    return value.size > 0 and not pd.isna(value) and value != "" and value != "NULL"


def calculate_tool_score(resource_data: pd.Series, observations_data: pd.DataFrame,
                         pub_data: pd.DataFrame) -> Dict:
    """
    Calculate completeness score for a tool

    Args:
        resource_data: Series containing resource information
        observations_data: DataFrame containing observations for this resource
        pub_data: DataFrame containing publications for this resource

    Returns:
        Dictionary with total_score, breakdown, and missing_fields
    """
    score_breakdown = {}
    missing_fields = {}
    total_score = 0
    tool_type = resource_data.get('resourceType')

    # Availability (30 points)
    availability_score = 0
    availability_missing = []

    if pd.notna(tool_type) and tool_type == "Biobank":
        # For biobanks: biobankURL (30 points)
        if is_filled(resource_data.get('biobankURL')):
            availability_score = 30
        else:
            availability_missing.append("biobankURL")
        score_breakdown['biobank_url'] = availability_score
    else:
        # For other resource types: vendor/developer (15), RRID (7.5), DOI (7.5)

        # Vendor/developer: 15 points
        vendor_developer_score = 0
        how_to_acquire = resource_data.get('howToAcquire', '')
        default_message = "We don't know of a reliable source for this tool.If you do, let us know at nf-osi@sagebionetworks.org!"
        has_acquisition_info = is_filled(how_to_acquire) and how_to_acquire != default_message

        if has_acquisition_info:
            vendor_developer_score = 15
        else:
            availability_missing.append("howToAcquire")
        score_breakdown['vendor_developer'] = vendor_developer_score
        availability_score += vendor_developer_score

        # RRID: 7.5 points
        rrid_score = 0
        if is_filled(resource_data.get('rrid')):
            rrid_score = 7.5
        else:
            availability_missing.append("rrid")
        score_breakdown['rrid'] = rrid_score
        availability_score += rrid_score

        # DOI: 7.5 points
        doi_score = 0
        if len(pub_data) > 0 and is_filled(pub_data.iloc[0].get('publicationId')):
            doi_score = 7.5
        else:
            availability_missing.append("publicationId")
        score_breakdown['doi'] = doi_score
        availability_score += doi_score

    missing_fields['availability'] = "; ".join(availability_missing)
    score_breakdown['availability'] = round(availability_score, 1)
    total_score += availability_score

    # Critical info (30 points distributed evenly)
    critical_info_score = 0
    critical_info_missing = []

    if pd.notna(tool_type):
        if tool_type == "Animal Model":
            fields = ["animalModelGeneticDisorder", "backgroundStrain", "animalState", "description"]
        elif tool_type == "Cell Line":
            fields = ["cellLineCategory", "cellLineGeneticDisorder", "cellLineManifestation", "synonyms"]
        elif tool_type == "Antibody":
            fields = ["targetAntigen", "reactiveSpecies", "hostOrganism", "clonality", "conjugate"]
        elif tool_type == "Genetic Reagent":
            fields = ["insertName", "insertSpecies", "vectorType", "insertEntrezId", "vectorBackbone"]
        elif tool_type == "Biobank":
            fields = ["specimenTissueType", "diseaseType", "tumorType", "specimenFormat", "specimenType"]
        else:
            fields = []

        # Count how many critical info fields are filled
        if len(fields) > 0:
            for field in fields:
                if not is_filled(resource_data.get(field)):
                    critical_info_missing.append(field)
            filled_count = len(fields) - len(critical_info_missing)
            critical_info_score = (filled_count / len(fields)) * 30

    missing_fields['critical_info'] = "; ".join(critical_info_missing)
    score_breakdown['critical_info'] = round(critical_info_score, 1)
    total_score += critical_info_score

    # Other info (15 points distributed evenly)
    other_info_score = 0
    other_info_missing = []

    if pd.notna(tool_type):
        if tool_type == "Animal Model":
            fields = ["backgroundSubstrain", "synonyms", "animalModelOfManifestation"]
        elif tool_type == "Cell Line":
            fields = ["tissue"]
        elif tool_type == "Antibody":
            fields = ["cloneId"]
        elif tool_type == "Genetic Reagent":
            fields = ["synonyms", "promoter"]
        elif tool_type == "Biobank":
            fields = ["specimenPreparationMethod"]
        else:
            fields = []

        # Count how many other info fields are filled
        if len(fields) > 0:
            for field in fields:
                if not is_filled(resource_data.get(field)):
                    other_info_missing.append(field)
            filled_count = len(fields) - len(other_info_missing)
            other_info_score = (filled_count / len(fields)) * 15

    missing_fields['other_info'] = "; ".join(other_info_missing)
    score_breakdown['other_info'] = round(other_info_score, 1)
    total_score += other_info_score

    # Observations (25 points max)
    # With DOI: 7.5 points each, No DOI: 2.5 points each
    observation_score = 0
    obs_with_doi = 0
    obs_without_doi = 0

    if observations_data is not None and len(observations_data) > 0:
        for _, obs in observations_data.iterrows():
            has_doi = is_filled(obs.get('doi'))

            if has_doi:
                observation_score += 7.5
                obs_with_doi += 1
            else:
                observation_score += 2.5
                obs_without_doi += 1

            # Cap at 25 points
            if observation_score >= 25:
                observation_score = 25
                break
        observation_status = f"{obs_with_doi} with DOI, {obs_without_doi} without DOI"
    else:
        observation_status = "No observations"

    missing_fields['observations'] = observation_status
    score_breakdown['observations'] = observation_score
    total_score += observation_score

    return {
        'total_score': round(total_score, 1),
        'breakdown': score_breakdown,
        'missing_fields': missing_fields
    }


def score_all_tools(syn: synapseclient.Synapse) -> pd.DataFrame:
    """
    Score all tools in the database

    Args:
        syn: Authenticated Synapse client

    Returns:
        DataFrame with scores for all resources
    """
    # Read base Resource table
    print("Reading base Resource data from Synapse...")
    resource_df = syn.tableQuery("SELECT * FROM syn26450069").asDataFrame()

    # Read type-specific tables
    print("Reading Animal Model data...")
    animal_model_df = syn.tableQuery("SELECT * FROM syn26486808").asDataFrame()

    print("Reading Antibody data...")
    antibody_df = syn.tableQuery("SELECT * FROM syn26486811").asDataFrame()

    print("Reading Biobank data...")
    biobank_df = syn.tableQuery("SELECT * FROM syn26486821").asDataFrame()

    print("Reading Cell Line data...")
    cell_line_df = syn.tableQuery("SELECT * FROM syn26486823").asDataFrame()

    print("Reading Genetic Reagent data...")
    genetic_reagent_df = syn.tableQuery("SELECT * FROM syn26486832").asDataFrame()

    # Join base resource data with type-specific data
    print("Joining resource data with type-specific tables...")

    # Left join with each type-specific table
    if 'animalModelId' in resource_df.columns:
        resource_df = resource_df.merge(
            animal_model_df[animal_model_df['animalModelId'].notna()],
            on='animalModelId', how='left', suffixes=('', '_animal')
        )

    if 'antibodyId' in resource_df.columns:
        resource_df = resource_df.merge(
            antibody_df[antibody_df['antibodyId'].notna()],
            on='antibodyId', how='left', suffixes=('', '_antibody')
        )

    if 'biobankId' in resource_df.columns:
        resource_df = resource_df.merge(
            biobank_df[biobank_df['biobankId'].notna()],
            on='biobankId', how='left', suffixes=('', '_biobank')
        )

    if 'cellLineId' in resource_df.columns:
        resource_df = resource_df.merge(
            cell_line_df[cell_line_df['cellLineId'].notna()],
            on='cellLineId', how='left', suffixes=('', '_cellline')
        )

    if 'geneticReagentId' in resource_df.columns:
        resource_df = resource_df.merge(
            genetic_reagent_df[genetic_reagent_df['geneticReagentId'].notna()],
            on='geneticReagentId', how='left', suffixes=('', '_genetic')
        )

    # Read observations data
    print("Reading Observation data from Synapse...")
    obs_df = syn.tableQuery("SELECT * FROM syn26486836").asDataFrame()

    # Read publications data
    print("Reading Publication data from Synapse...")
    pub_df = syn.tableQuery("SELECT resourceId, publicationId FROM syn26486807").asDataFrame()

    # Initialize results list
    results = []

    # Calculate scores for each resource
    print("Calculating scores...")
    for idx, resource in resource_df.iterrows():
        # Get observations for this resource
        resource_obs = obs_df[obs_df['resourceId'] == resource['resourceId']]

        # Get publications for this resource
        resource_pub = pub_df[pub_df['resourceId'] == resource['resourceId']]

        # Calculate score
        score_result = calculate_tool_score(resource, resource_obs, resource_pub)

        # Create result row
        result_row = {
            'resourceId': resource['resourceId'],
            'resourceName': resource['resourceName'],
            'resourceType': resource['resourceType'],
            'rrid': resource.get('rrid'),
            'total_score': score_result['total_score'],
            'availability_score': score_result['breakdown'].get('availability'),
            'biobank_url_score': score_result['breakdown'].get('biobank_url'),
            'vendor_developer_score': score_result['breakdown'].get('vendor_developer'),
            'rrid_score': score_result['breakdown'].get('rrid'),
            'doi_score': score_result['breakdown'].get('doi'),
            'critical_info_score': score_result['breakdown']['critical_info'],
            'other_info_score': score_result['breakdown']['other_info'],
            'observation_score': score_result['breakdown']['observations'],
            'missing_availability': score_result['missing_fields']['availability'],
            'missing_critical_info': score_result['missing_fields']['critical_info'],
            'missing_other_info': score_result['missing_fields']['other_info'],
            'observation_status': score_result['missing_fields']['observations']
        }

        results.append(result_row)

    results_df = pd.DataFrame(results)

    # Add completeness categories
    results_df['completeness_category'] = pd.cut(
        results_df['total_score'],
        bins=[-np.inf, 20, 40, 60, 80, np.inf],
        labels=['Minimal', 'Poor', 'Fair', 'Good', 'Excellent']
    )

    def categorize_score(score, max_score):
        if pd.isna(score):
            return 'No'
        elif score >= max_score:
            return 'All'
        elif score > 0:
            return 'Some'
        else:
            return 'No'

    results_df['availability_category'] = results_df['availability_score'].apply(
        lambda x: categorize_score(x, 30)
    )
    results_df['critical_info_category'] = results_df['critical_info_score'].apply(
        lambda x: categorize_score(x, 30)
    )
    results_df['other_info_category'] = results_df['other_info_score'].apply(
        lambda x: categorize_score(x, 15)
    )
    results_df['observation_category'] = results_df['observation_score'].apply(
        lambda x: categorize_score(x, 25)
    )

    return results_df


def summarize_scores(scores_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate summary statistics by tool type

    Args:
        scores_df: DataFrame with tool scores

    Returns:
        DataFrame with summary statistics by resource type
    """
    summary_stats = scores_df.groupby('resourceType').agg({
        'total_score': ['count', 'mean', 'median', 'min', 'max', 'std']
    }).reset_index()

    # Flatten column names
    summary_stats.columns = ['resourceType', 'count', 'mean_score', 'median_score',
                             'min_score', 'max_score', 'sd_score']

    # Add category counts
    category_counts = scores_df.groupby(['resourceType', 'completeness_category']).size().unstack(fill_value=0)
    for cat in ['Excellent', 'Good', 'Fair', 'Poor', 'Minimal']:
        if cat in category_counts.columns:
            summary_stats[cat.lower()] = summary_stats['resourceType'].map(category_counts[cat])
        else:
            summary_stats[cat.lower()] = 0

    summary_stats = summary_stats.sort_values('mean_score', ascending=False)

    return summary_stats


def find_existing_table(syn: synapseclient.Synapse, parent_id: str, table_name: str):
    """Find existing table by name in a project/folder"""
    try:
        children = list(syn.getChildren(parent_id))
        for child in children:
            if child['name'] == table_name and child['type'] == 'org.sagebionetworks.repo.model.table.TableEntity':
                return child['id']
        return None
    except Exception:
        return None


def store_results_to_synapse(syn: synapseclient.Synapse, all_scores: pd.DataFrame,
                             summary_by_type: pd.DataFrame):
    """
    Store results as Synapse tables

    Args:
        syn: Authenticated Synapse client
        all_scores: DataFrame with all tool scores
        summary_by_type: DataFrame with summary statistics
    """
    parent_id = "syn26338068"

    # Store completeness scores table
    print("\nStoring results as Synapse table...")
    existing_scores_table_id = find_existing_table(syn, parent_id, "ToolCompletenessScores")

    if existing_scores_table_id:
        print(f"Found existing table: {existing_scores_table_id}")
        print("Updating table with new data (this will create a new version)...")

        # Delete existing rows
        current_data = syn.tableQuery(f"SELECT * FROM {existing_scores_table_id}")
        syn.delete(current_data)

        # Store new data
        table = synapseclient.Table(existing_scores_table_id, all_scores)
        syn.store(table)
        syn.create_snapshot_version(existing_scores_table_id)

        print(f"\n✓ Completeness scores updated in Synapse table: {existing_scores_table_id}")
        print(f"  View at: https://www.synapse.org/#!Synapse:{existing_scores_table_id}")
    else:
        print("Creating new table...")

        # Define table schema
        cols = [
            synapseclient.Column(name='resourceId', columnType='STRING', maximumSize=50),
            synapseclient.Column(name='resourceName', columnType='STRING', maximumSize=255),
            synapseclient.Column(name='resourceType', columnType='STRING', maximumSize=50),
            synapseclient.Column(name='rrid', columnType='STRING', maximumSize=100),
            synapseclient.Column(name='total_score', columnType='DOUBLE'),
            synapseclient.Column(name='availability_score', columnType='DOUBLE'),
            synapseclient.Column(name='biobank_url_score', columnType='DOUBLE'),
            synapseclient.Column(name='vendor_developer_score', columnType='DOUBLE'),
            synapseclient.Column(name='rrid_score', columnType='DOUBLE'),
            synapseclient.Column(name='doi_score', columnType='DOUBLE'),
            synapseclient.Column(name='critical_info_score', columnType='DOUBLE'),
            synapseclient.Column(name='other_info_score', columnType='DOUBLE'),
            synapseclient.Column(name='observation_score', columnType='DOUBLE'),
            synapseclient.Column(name='missing_availability', columnType='STRING', maximumSize=500),
            synapseclient.Column(name='missing_critical_info', columnType='STRING', maximumSize=500),
            synapseclient.Column(name='missing_other_info', columnType='STRING', maximumSize=500),
            synapseclient.Column(name='observation_status', columnType='STRING', maximumSize=200),
            synapseclient.Column(name='completeness_category', columnType='STRING', maximumSize=50),
            synapseclient.Column(name='availability_category', columnType='STRING', maximumSize=4),
            synapseclient.Column(name='critical_info_category', columnType='STRING', maximumSize=4),
            synapseclient.Column(name='other_info_category', columnType='STRING', maximumSize=4),
            synapseclient.Column(name='observation_category', columnType='STRING', maximumSize=4)
        ]

        schema = synapseclient.Schema(name='ToolCompletenessScores', columns=cols, parent=parent_id)
        table = synapseclient.Table(schema, all_scores)
        table_result = syn.store(table)
        syn.create_snapshot_version(table_result.tableId)

        print(f"\n✓ Completeness scores stored as new Synapse table: {table_result.tableId}")
        print(f"  View at: https://www.synapse.org/#!Synapse:{table_result.tableId}")
        existing_scores_table_id = table_result.tableId

    # Store summary statistics table
    print("\nStoring summary statistics as Synapse table...")
    existing_summary_table_id = find_existing_table(syn, parent_id, "ToolCompletenessSummary")

    if existing_summary_table_id:
        print(f"Found existing summary table: {existing_summary_table_id}")
        print("Updating summary table with new data (this will create a new version)...")

        # Delete existing rows
        current_summary = syn.tableQuery(f"SELECT * FROM {existing_summary_table_id}")
        syn.delete(current_summary)

        # Store new data
        summary_table = synapseclient.Table(existing_summary_table_id, summary_by_type)
        syn.store(summary_table)
        syn.create_snapshot_version(existing_summary_table_id)

        print(f"✓ Summary statistics updated in Synapse table: {existing_summary_table_id}")
        print(f"  View at: https://www.synapse.org/#!Synapse:{existing_summary_table_id}")
    else:
        print("Creating new summary table...")

        summary_cols = [
            synapseclient.Column(name='resourceType', columnType='STRING', maximumSize=50),
            synapseclient.Column(name='count', columnType='INTEGER'),
            synapseclient.Column(name='mean_score', columnType='DOUBLE'),
            synapseclient.Column(name='median_score', columnType='DOUBLE'),
            synapseclient.Column(name='min_score', columnType='DOUBLE'),
            synapseclient.Column(name='max_score', columnType='DOUBLE'),
            synapseclient.Column(name='sd_score', columnType='DOUBLE'),
            synapseclient.Column(name='excellent', columnType='INTEGER'),
            synapseclient.Column(name='good', columnType='INTEGER'),
            synapseclient.Column(name='fair', columnType='INTEGER'),
            synapseclient.Column(name='poor', columnType='INTEGER'),
            synapseclient.Column(name='minimal', columnType='INTEGER')
        ]

        summary_schema = synapseclient.Schema(name='ToolCompletenessSummary',
                                              columns=summary_cols, parent=parent_id)
        summary_table = synapseclient.Table(summary_schema, summary_by_type)
        summary_table_result = syn.store(summary_table)
        syn.create_snapshot_version(summary_table_result.tableId)

        print(f"✓ Summary statistics stored as new Synapse table: {summary_table_result.tableId}")
        print(f"  View at: https://www.synapse.org/#!Synapse:{summary_table_result.tableId}")

    return existing_scores_table_id


def update_materialized_view(syn: synapseclient.Synapse, view_id: str, scores_table_id: str) -> bool:
    """
    Update materialized view with completeness scores

    Args:
        syn: Authenticated Synapse client
        view_id: Synapse ID of the materialized view
        scores_table_id: Synapse ID of the scores table

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"\nUpdating materialized view {view_id} with completeness scores...")
        print(f"Using scores table: {scores_table_id}")

        # Get the current materialized view
        mv = syn.get(view_id)

        # Get the current defining SQL
        current_sql = mv.properties.get('definingSQL', '')
        print(f"Current defining SQL:\n{current_sql}\n")

        # Create new SQL that includes the completeness scores
        new_sql = f"""SELECT
    R.resourceId AS resourceId,
    R.rrid AS rrid,
    R.resourceName AS resourceName,
    R.synonyms AS synonyms,
    R.description AS description,

    R.resourceType AS resourceType,

    D_I.investigatorName AS investigatorName,
    D_I.institution AS institution,
    D_I.orcid AS orcid,

    R.usageRequirements AS usageRequirements,
    R.howToAcquire as howToAcquire,

    AM_CL_R_DON.species AS species,

    CL.cellLineCategory AS cellLineCategory,
    CL.cellLineGeneticDisorder AS cellLineGeneticDisorder,
    CL.cellLineManifestation AS cellLineManifestation,
    AM.backgroundStrain AS backgroundStrain,
    AM.backgroundSubstrain AS backgroundSubstrain,
    AM.animalModelGeneticDisorder AS animalModelGeneticDisorder,
    AM.animalModelOfManifestation AS animalModelOfManifestation,
    GR.insertName AS insertName,
    GR.insertSpecies AS insertSpecies,
    GR.vectorType AS vectorType,
    AB.targetAntigen AS targetAntigen,
    AB.reactiveSpecies AS reactiveSpecies,
    AB.hostOrganism AS hostOrganism,
    BB.biobankName AS biobankName,
    BB.biobankURL AS biobankURL,
    BB.specimenTissueType AS specimenTissueType,
    BB.specimenPreparationMethod AS specimenPreparationMethod,
    BB.diseaseType AS diseaseType,
    BB.tumorType AS tumorType,
    BB.specimenFormat AS specimenFormat,
    BB.specimenType AS specimenType,
    BB.contact AS contact,
    D_F.funderName AS funderName,
    AM_CL_R_DON.race AS race,
    AM_CL_R_DON.sex AS sex,
    AM_CL_R_DON.age AS age,
    R.dateAdded AS dateAdded,
    R.dateModified AS dateModified,
    L_P.latestPublicationDate AS latestPublicationDate,
    S.completeness_category AS completenessCategory,
    S.availability_category AS availabilityCategory,
    S.critical_info_category AS criticalInfoCategory,
    S.other_info_category AS otherInfoCategory,
    S.observation_category AS observationCategory
FROM
    syn26450069 R
LEFT JOIN
    syn26486823 CL ON (R.cellLineId = CL.cellLineId)
LEFT JOIN
    syn26486808 AM ON (R.animalModelId = AM.animalModelId)
LEFT JOIN
    syn26486832 GR ON (R.geneticReagentId = GR.geneticReagentId)
LEFT JOIN
    syn26486811 AB ON (R.antibodyId = AB.antibodyId)
LEFT JOIN
    syn26486821 BB ON (R.resourceId = BB.resourceId)
LEFT JOIN
    syn51734029 D_I ON (R.resourceId = D_I.resourceId)
LEFT JOIN
    syn51734076 D_F ON (R.resourceId = D_F.resourceId)
LEFT JOIN
    syn51735419 AM_CL_R_DON ON (R.resourceId = AM_CL_R_DON.resourceId)
LEFT JOIN
    syn62139114 L_P ON (R.resourceId = L_P.resourceId)
LEFT JOIN
    {scores_table_id} S ON (R.resourceId = S.resourceId)"""

        print(f"New defining SQL:\n{new_sql}\n")

        # Update the materialized view with new SQL
        mv.properties['definingSQL'] = new_sql
        updated_mv = syn.store(mv)

        print("✓ Materialized view updated successfully!")
        print(f"  View at: https://www.synapse.org/#!Synapse:{view_id}")

        return True
    except Exception as e:
        print(f"✗ Error updating materialized view: {str(e)}")
        print("  You may need to update the materialized view manually.")
        print(f"  The scores are available in table: {scores_table_id}")
        return False


def main():
    """Main execution function"""
    # Login to Synapse
    print("Logging in to Synapse...")
    syn = synapseclient.Synapse()

    # Check for auth token in environment variable
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token)
    else:
        syn.login()

    # Run the analysis
    print("\nStarting tool completeness scoring...")
    all_scores = score_all_tools(syn)

    # Generate summary
    summary_by_type = summarize_scores(all_scores)

    # Display results
    print("\n=== Summary by Tool Type ===")
    print(summary_by_type.to_string(index=False))

    print("\n=== Top 10 Most Complete Tools ===")
    top_10 = all_scores.nlargest(10, 'total_score')[['resourceName', 'resourceType', 'rrid',
                                                      'total_score', 'completeness_category']]
    print(top_10.to_string(index=False))

    print("\n=== Tools Needing Improvement (Score < 40) ===")
    incomplete_tools = all_scores[all_scores['total_score'] < 40].nsmallest(
        20, 'total_score')[['resourceName', 'resourceType', 'total_score', 'completeness_category']]
    print(incomplete_tools.to_string(index=False))

    # Store results to Synapse
    scores_table_id = store_results_to_synapse(syn, all_scores, summary_by_type)

    # Update materialized view
    update_success = update_materialized_view(syn, "syn51730943", scores_table_id)

    if update_success:
        print("\n✓ All tasks completed successfully!")
    else:
        print("\n⚠ Materialized view update failed. Please update manually.")
        print(f"  Need to join {scores_table_id} with syn51730943 on resourceId column.")


if __name__ == "__main__":
    main()
