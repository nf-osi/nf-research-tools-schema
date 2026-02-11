#!/usr/bin/env python3
"""
Create 4 new tool type tables in Synapse for v2.0 schema expansion.

Tables created:
- ComputationalToolDetails
- AdvancedCellularModelDetails
- PatientDerivedModelDetails
- ClinicalAssessmentToolDetails

All tables are created under parent project syn26338068.
"""

import os
import synapseclient
from synapseclient import Schema, Table
# Use old Column API (still works, just deprecated)
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
from synapseclient import Column

def create_computational_tool_table(syn, parent_id):
    """Create ComputationalToolDetails table."""
    print("\n1. Creating ComputationalToolDetails table...")

    columns = [
        Column(name='computationalToolId', columnType='STRING', maximumSize=50),
        Column(name='softwareName', columnType='STRING', maximumSize=200),
        Column(name='softwareType', columnType='STRING', maximumSize=100),
        Column(name='softwareVersion', columnType='STRING', maximumSize=50),
        Column(name='programmingLanguage', columnType='STRING_LIST', maximumSize=30, maximumListLength=10),
        Column(name='sourceRepository', columnType='STRING', maximumSize=300),
        Column(name='documentation', columnType='STRING', maximumSize=300),
        Column(name='licenseType', columnType='STRING', maximumSize=50),
        Column(name='containerized', columnType='STRING', maximumSize=20),
        Column(name='dependencies', columnType='STRING_LIST', maximumSize=50, maximumListLength=20),
        Column(name='systemRequirements', columnType='STRING', maximumSize=300),
        Column(name='lastUpdate', columnType='STRING', maximumSize=50),
        Column(name='maintainer', columnType='STRING', maximumSize=150),
    ]

    schema = Schema(
        name='ComputationalToolDetails',
        columns=columns,
        parent=parent_id
    )

    table = syn.store(schema)
    print(f"   ✅ Created: {table.id}")
    return table.id


def create_advanced_cellular_model_table(syn, parent_id):
    """Create AdvancedCellularModelDetails table."""
    print("\n2. Creating AdvancedCellularModelDetails table...")

    columns = [
        Column(name='advancedCellularModelId', columnType='STRING', maximumSize=50),
        Column(name='modelType', columnType='STRING', maximumSize=50),
        Column(name='derivationSource', columnType='STRING', maximumSize=100),
        Column(name='cellTypes', columnType='STRING_LIST', maximumSize=50, maximumListLength=10),
        Column(name='organoidType', columnType='STRING', maximumSize=50),
        Column(name='matrixType', columnType='STRING', maximumSize=100),
        Column(name='cultureSystem', columnType='STRING', maximumSize=100),
        Column(name='maturationTime', columnType='STRING', maximumSize=50),
        Column(name='characterizationMethods', columnType='STRING_LIST', maximumSize=50, maximumListLength=10),
        Column(name='passageNumber', columnType='STRING', maximumSize=20),
        Column(name='cryopreservationProtocol', columnType='STRING', maximumSize=300),
        Column(name='qualityControlMetrics', columnType='STRING_LIST', maximumSize=50, maximumListLength=10),
    ]

    schema = Schema(
        name='AdvancedCellularModelDetails',
        columns=columns,
        parent=parent_id
    )

    table = syn.store(schema)
    print(f"   ✅ Created: {table.id}")
    return table.id


def create_patient_derived_model_table(syn, parent_id):
    """Create PatientDerivedModelDetails table."""
    print("\n3. Creating PatientDerivedModelDetails table...")

    columns = [
        Column(name='patientDerivedModelId', columnType='STRING', maximumSize=50),
        Column(name='modelSystemType', columnType='STRING', maximumSize=100),
        Column(name='patientDiagnosis', columnType='STRING', maximumSize=200),
        Column(name='hostStrain', columnType='STRING', maximumSize=50),
        Column(name='passageNumber', columnType='STRING', maximumSize=20),
        Column(name='tumorType', columnType='STRING', maximumSize=100),
        Column(name='engraftmentSite', columnType='STRING', maximumSize=100),
        Column(name='establishmentRate', columnType='STRING', maximumSize=50),
        Column(name='molecularCharacterization', columnType='STRING_LIST', maximumSize=50, maximumListLength=10),
        Column(name='clinicalData', columnType='STRING', maximumSize=500),
        Column(name='humanizationMethod', columnType='STRING', maximumSize=150),
        Column(name='immuneSystemComponents', columnType='STRING_LIST', maximumSize=50, maximumListLength=10),
        Column(name='validationMethods', columnType='STRING_LIST', maximumSize=50, maximumListLength=10),
    ]

    schema = Schema(
        name='PatientDerivedModelDetails',
        columns=columns,
        parent=parent_id
    )

    table = syn.store(schema)
    print(f"   ✅ Created: {table.id}")
    return table.id


def create_clinical_assessment_tool_table(syn, parent_id):
    """Create ClinicalAssessmentToolDetails table."""
    print("\n4. Creating ClinicalAssessmentToolDetails table...")

    columns = [
        Column(name='clinicalAssessmentToolId', columnType='STRING', maximumSize=50),
        Column(name='assessmentName', columnType='STRING', maximumSize=200),
        Column(name='assessmentType', columnType='STRING', maximumSize=100),
        Column(name='targetPopulation', columnType='STRING', maximumSize=50),
        Column(name='diseaseSpecific', columnType='STRING', maximumSize=50),
        Column(name='numberOfItems', columnType='STRING', maximumSize=20),
        Column(name='scoringMethod', columnType='STRING', maximumSize=300),
        Column(name='validatedLanguages', columnType='STRING_LIST', maximumSize=30, maximumListLength=20),
        Column(name='psychometricProperties', columnType='STRING', maximumSize=300),
        Column(name='administrationTime', columnType='STRING', maximumSize=50),
        Column(name='availabilityStatus', columnType='STRING', maximumSize=50),
        Column(name='licensingRequirements', columnType='STRING', maximumSize=300),
        Column(name='digitalVersion', columnType='STRING', maximumSize=20),
    ]

    schema = Schema(
        name='ClinicalAssessmentToolDetails',
        columns=columns,
        parent=parent_id
    )

    table = syn.store(schema)
    print(f"   ✅ Created: {table.id}")
    return table.id


def main():
    """Main function to create all 4 new tool type tables."""
    print("=" * 80)
    print("Creating New Tool Type Tables in Synapse")
    print("=" * 80)

    # Check for auth token
    auth_token = os.environ.get('SYNAPSE_AUTH_TOKEN') or os.environ.get('NF_SERVICE_TOKEN')
    if not auth_token:
        print("\n❌ Error: No Synapse auth token found!")
        print("   Set SYNAPSE_AUTH_TOKEN or NF_SERVICE_TOKEN environment variable")
        print("   Example: export SYNAPSE_AUTH_TOKEN='your_token_here'")
        return 1

    # Login to Synapse
    print("\nConnecting to Synapse...")
    syn = synapseclient.Synapse()
    syn.login(authToken=auth_token)
    print("✅ Connected to Synapse")

    # Parent project for all tool tables
    parent_id = 'syn26338068'
    print(f"\nParent project: {parent_id}")

    # Create tables
    table_ids = {}

    try:
        table_ids['computational_tools'] = create_computational_tool_table(syn, parent_id)
        table_ids['advanced_cellular_models'] = create_advanced_cellular_model_table(syn, parent_id)
        table_ids['patient_derived_models'] = create_patient_derived_model_table(syn, parent_id)
        table_ids['clinical_assessment_tools'] = create_clinical_assessment_tool_table(syn, parent_id)

        # Summary
        print("\n" + "=" * 80)
        print("SUCCESS - All Tables Created!")
        print("=" * 80)
        print("\nTable IDs:")
        print(f"  ComputationalToolDetails:        {table_ids['computational_tools']}")
        print(f"  AdvancedCellularModelDetails:    {table_ids['advanced_cellular_models']}")
        print(f"  PatientDerivedModelDetails:      {table_ids['patient_derived_models']}")
        print(f"  ClinicalAssessmentToolDetails:   {table_ids['clinical_assessment_tools']}")

        # Generate update for clean_submission_csvs.py
        print("\n" + "=" * 80)
        print("Next Step: Update clean_submission_csvs.py")
        print("=" * 80)
        print("\nReplace the TBD placeholders with actual table IDs:")
        print("\nSYNAPSE_TABLE_MAP = {")
        print("    # ... existing mappings ...")
        print(f"    'CLEAN_computational_tools.csv': '{table_ids['computational_tools']}',")
        print(f"    'CLEAN_advanced_cellular_models.csv': '{table_ids['advanced_cellular_models']}',")
        print(f"    'CLEAN_patient_derived_models.csv': '{table_ids['patient_derived_models']}',")
        print(f"    'CLEAN_clinical_assessment_tools.csv': '{table_ids['clinical_assessment_tools']}',")
        print("}")

        print("\n✅ Tables are ready for data upload!")
        print("   You can now run the workflow to mine and upload tools.")

        return 0

    except Exception as e:
        print(f"\n❌ Error creating tables: {e}")
        print("\nPartially created tables (if any):")
        for name, table_id in table_ids.items():
            print(f"  {name}: {table_id}")
        return 1


if __name__ == '__main__':
    exit(main())
