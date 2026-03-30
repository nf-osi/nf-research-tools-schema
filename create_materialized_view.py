#!/usr/bin/env python3
"""
Create Materialized View for NF Research Tools

This script creates a new materialized view that includes:
- All 9 tool types (including 4 new types)
- Completeness scores
- Key metadata fields
- Reduced columns to fit under Synapse 64KB row limit

Note: This creates a NEW view, it does not update existing view syn51730943
"""

import os
import synapseclient
from synapseclient import Schema


def create_tools_materialized_view(syn: synapseclient.Synapse,
                                   scores_table_id: str,
                                   parent_id: str = 'syn26338068',
                                   view_name: str = 'NF_Research_Tools_Complete_View') -> str:
    """
    Create a new materialized view for NF research tools.

    Args:
        syn: Authenticated Synapse client
        scores_table_id: Synapse ID of the ToolCompletenessScores table
        parent_id: Parent project/folder ID (default: syn26338068)
        view_name: Name for the new materialized view

    Returns:
        Synapse ID of the created materialized view
    """
    print(f"Creating new materialized view: {view_name}")
    print(f"Parent: {parent_id}")
    print(f"Scores table: {scores_table_id}")

    # Define SQL query for the materialized view
    # Removed category columns (except cellLineCategory) to stay under 64KB limit
    defining_sql = f"""SELECT
    R.resourceId AS resourceId,
    R.rrid AS rrid,
    R.resourceName AS resourceName,
    R.synonyms AS synonyms,
    R.description AS description,
    R.resourceType AS resourceType,
    R.usageRequirements AS usageRequirements,
    R.howToAcquire as howToAcquire,
    R.dateAdded AS dateAdded,
    R.dateModified AS dateModified,

    D_I.investigatorName AS investigatorName,
    D_I.institution AS institution,
    D_I.orcid AS orcid,

    D_F.funderName AS funderName,

    AM_CL_R_DON.species AS species,
    AM_CL_R_DON.race AS race,
    AM_CL_R_DON.sex AS sex,
    AM_CL_R_DON.age AS age,

    CL.cellLineCategory AS cellLineCategory,
    CL.cellLineGeneticDisorder AS cellLineGeneticDisorder,
    CL.cellLineManifestation AS cellLineManifestation,
    CL.tissue AS tissue,

    AM.backgroundStrain AS backgroundStrain,
    AM.backgroundSubstrain AS backgroundSubstrain,
    AM.animalModelGeneticDisorder AS animalModelGeneticDisorder,
    AM.animalModelOfManifestation AS animalModelOfManifestation,
    AM.animalState AS animalState,

    GR.insertName AS insertName,
    GR.insertSpecies AS insertSpecies,
    GR.vectorType AS vectorType,
    GR.vectorBackbone AS vectorBackbone,

    AB.targetAntigen AS targetAntigen,
    AB.reactiveSpecies AS reactiveSpecies,
    AB.hostOrganism AS hostOrganism,
    AB.clonality AS clonality,
    AB.conjugate AS conjugate,

    BB.biobankName AS biobankName,
    BB.biobankURL AS biobankURL,
    BB.specimenTissueType AS specimenTissueType,
    BB.specimenPreparationMethod AS specimenPreparationMethod,
    BB.diseaseType AS diseaseType,
    BB.tumorType AS tumorType,
    BB.specimenFormat AS specimenFormat,
    BB.specimenType AS specimenType,
    BB.contact AS contact,

    CT.softwareName AS softwareName,
    CT.softwareType AS softwareType,
    CT.softwareVersion AS softwareVersion,
    CT.programmingLanguage AS programmingLanguage,
    CT.sourceRepository AS sourceRepository,
    CT.containerized AS containerized,

    ACM.modelType AS modelType,
    ACM.derivationSource AS derivationSource,
    ACM.cellTypes AS cellTypes,
    ACM.cultureSystem AS cultureSystem,
    ACM.maturationTime AS maturationTime,

    PDM.modelSystemType AS modelSystemType,
    PDM.patientDiagnosis AS patientDiagnosis,
    PDM.hostStrain AS hostStrain,
    PDM.tumorType AS pdmTumorType,
    PDM.passageNumber AS passageNumber,

    CAT.assessmentName AS assessmentName,
    CAT.assessmentType AS assessmentType,
    CAT.targetPopulation AS targetPopulation,
    CAT.validatedLanguages AS validatedLanguages,

    L_P.latestPublicationDate AS latestPublicationDate,

    S.total_score AS totalScore,
    S.availability_score AS availabilityScore,
    S.critical_info_score AS criticalInfoScore,
    S.other_info_score AS otherInfoScore,
    S.observation_score AS observationScore,
    S.dataset_score AS datasetScore

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
    syn73709226 CT ON (R.computationalToolId = CT.computationalToolId)
LEFT JOIN
    syn73709227 ACM ON (R.advancedCellularModelId = ACM.advancedCellularModelId)
LEFT JOIN
    syn73709228 PDM ON (R.patientDerivedModelId = PDM.patientDerivedModelId)
LEFT JOIN
    syn73709229 CAT ON (R.clinicalAssessmentToolId = CAT.clinicalAssessmentToolId)
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

    print("\nCreating materialized view with defining SQL...")
    print(f"SQL length: {len(defining_sql)} characters")

    # Create the materialized view
    materialized_view = Schema(
        name=view_name,
        parent=parent_id,
        definingSQL=defining_sql
    )

    # Store the materialized view
    mv_result = syn.store(materialized_view)
    mv_id = mv_result.properties['id']

    print(f"\n✓ Materialized view created successfully!")
    print(f"  Synapse ID: {mv_id}")
    print(f"  Name: {view_name}")
    print(f"  URL: https://www.synapse.org/#!Synapse:{mv_id}")

    return mv_id


def main():
    """Main execution function."""
    print("=" * 70)
    print("CREATE NF RESEARCH TOOLS MATERIALIZED VIEW")
    print("=" * 70)
    print()

    # Get scores table ID from command line or use default
    import sys
    if len(sys.argv) > 1:
        scores_table_id = sys.argv[1]
    else:
        # Prompt user for scores table ID
        print("Enter the Synapse ID of the ToolCompletenessScores table")
        print("(or press Enter to search for it automatically):")
        user_input = input().strip()

        if user_input:
            scores_table_id = user_input
        else:
            # Try to find the table automatically
            print("\nSearching for ToolCompletenessScores table...")
            syn = synapseclient.Synapse()
            auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
            if auth_token:
                syn.login(authToken=auth_token, silent=True)
            else:
                syn.login()

            parent_id = 'syn26338068'
            children = list(syn.getChildren(parent_id))
            scores_table_id = None

            for child in children:
                if child['name'] == 'ToolCompletenessScores':
                    scores_table_id = child['id']
                    print(f"  Found: {scores_table_id}")
                    break

            if not scores_table_id:
                print("Error: Could not find ToolCompletenessScores table")
                print(f"Please run tool_scoring.py first or specify the table ID manually")
                sys.exit(1)

    # Login to Synapse (if not already logged in)
    print("\nLogging in to Synapse...")
    syn = synapseclient.Synapse()
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token, silent=True)
        print("  ✓ Logged in with auth token")
    else:
        syn.login()
        print("  ✓ Logged in")

    # Create the materialized view
    print()
    mv_id = create_tools_materialized_view(
        syn=syn,
        scores_table_id=scores_table_id,
        parent_id='syn26338068',
        view_name='NF_Research_Tools_Complete_View'
    )

    print()
    print("=" * 70)
    print("SUCCESS!")
    print("=" * 70)
    print()
    print(f"New materialized view created: {mv_id}")
    print(f"View it at: https://www.synapse.org/#!Synapse:{mv_id}")
    print()
    print("This view includes:")
    print("  - All 9 tool types (including 4 new types)")
    print("  - Completeness scores (including dataset bonus points)")
    print("  - Key metadata fields")
    print("  - Optimized to fit under Synapse 64KB row limit")
    print()


if __name__ == "__main__":
    main()
