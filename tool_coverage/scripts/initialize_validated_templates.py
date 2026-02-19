#!/usr/bin/env python3
"""
Initialize VALIDATED_*.csv template files before Sonnet reviews.

Creates empty CSV files with proper column headers (Synapse schema + tracking columns).
Sonnet reviews will populate these via format_validation_for_submission.py.
"""

import pandas as pd
from pathlib import Path

OUTPUT_DIR = Path('tool_coverage/outputs')

def create_cell_lines_template():
    """Create VALIDATED_cell_lines.csv template."""
    columns = [
        # Synapse schema columns (syn26486803)
        'cellLineId',
        'organ',
        'tissue',
        'donorId',
        'originYear',
        'strProfile',
        'cellLineManifestation',
        'resistance',
        'cellLineCategory',
        'contaminatedMisidentified',
        'cellLineGeneticDisorder',
        'populationDoublingTime',
        # Tracking columns (prefixed with _)
        '_cellLineName',  # Original tool name
        '_pmid',          # Publication PMID
        '_doi',           # Publication DOI
        '_publicationTitle',  # Publication title
        '_foundIn',       # Section found (abstract, methods, etc.)
        '_confidence',    # AI confidence score
        '_contextSnippet',  # Text snippet showing usage
        '_source',        # Source (AI validation, mining, etc.)
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_cell_lines.csv', index=False)
    print(f"✓ Created VALIDATED_cell_lines.csv ({len(columns)} columns)")


def create_animal_models_template():
    """Create VALIDATED_animal_models.csv template."""
    columns = [
        # Synapse schema columns (syn26486804)
        'animalModelId',
        'strainNomenclature',
        'backgroundStrain',
        'backgroundSubstrain',
        'animalModelOfManifestation',
        'animalModelGeneticDisorder',
        'animalState',
        # Tracking columns
        '_pmid',
        '_doi',
        '_publicationTitle',
        '_foundIn',
        '_confidence',
        '_contextSnippet',
        '_source',
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_animal_models.csv', index=False)
    print(f"✓ Created VALIDATED_animal_models.csv ({len(columns)} columns)")


def create_genetic_reagents_template():
    """Create VALIDATED_genetic_reagents.csv template."""
    columns = [
        # Synapse schema columns (syn26486805)
        'geneticReagentId',
        'insertName',
        'vectorType',
        'vectorBackbone',
        'selectableMarker',
        'insertSpecies',
        'gRNAshRNASequence',
        # Tracking columns
        '_pmid',
        '_doi',
        '_publicationTitle',
        '_foundIn',
        '_confidence',
        '_contextSnippet',
        '_source',
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_genetic_reagents.csv', index=False)
    print(f"✓ Created VALIDATED_genetic_reagents.csv ({len(columns)} columns)")


def create_antibodies_template():
    """Create VALIDATED_antibodies.csv template."""
    columns = [
        # Synapse schema columns (syn26486802)
        'antibodyId',
        'targetAntigen',
        'reactiveSpecies',
        'hostOrganism',
        'clonality',
        # Tracking columns
        '_pmid',
        '_doi',
        '_publicationTitle',
        '_foundIn',
        '_confidence',
        '_contextSnippet',
        '_source',
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_antibodies.csv', index=False)
    print(f"✓ Created VALIDATED_antibodies.csv ({len(columns)} columns)")


def create_computational_tools_template():
    """Create VALIDATED_computational_tools.csv template."""
    columns = [
        # Synapse schema columns (syn52659110)
        'computationalToolId',
        'softwareName',
        'softwareType',
        'softwareVersion',
        'programmingLanguage',
        'sourceRepository',
        'documentation',
        'licenseType',
        'containerized',
        'dependencies',
        'systemRequirements',
        'lastUpdate',
        'maintainer',
        # Tracking columns
        '_pmid',
        '_doi',
        '_publicationTitle',
        '_foundIn',
        '_confidence',
        '_contextSnippet',
        '_source',
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_computational_tools.csv', index=False)
    print(f"✓ Created VALIDATED_computational_tools.csv ({len(columns)} columns)")


def create_patient_derived_models_template():
    """Create VALIDATED_patient_derived_models.csv template."""
    columns = [
        # Synapse schema columns (syn52659111)
        'patientDerivedModelId',
        'modelSystemType',
        'patientDiagnosis',
        'hostStrain',
        'passageNumber',
        'tumorType',
        'engraftmentSite',
        'establishmentRate',
        'molecularCharacterization',
        'clinicalData',
        'humanizationMethod',
        'immuneSystemComponents',
        'validationMethods',
        # Tracking columns
        '_modelName',
        '_pmid',
        '_doi',
        '_publicationTitle',
        '_foundIn',
        '_confidence',
        '_contextSnippet',
        '_source',
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_patient_derived_models.csv', index=False)
    print(f"✓ Created VALIDATED_patient_derived_models.csv ({len(columns)} columns)")


def create_advanced_cellular_models_template():
    """Create VALIDATED_advanced_cellular_models.csv template."""
    columns = [
        # Synapse schema columns (syn52659112)
        'advancedCellularModelId',
        'modelType',
        'derivationSource',
        'cellTypes',
        'organoidType',
        'matrixType',
        'cultureSystem',
        'maturationTime',
        'characterizationMethods',
        'passageNumber',
        'cryopreservationProtocol',
        'qualityControlMetrics',
        # Tracking columns
        '_modelName',
        '_pmid',
        '_doi',
        '_publicationTitle',
        '_foundIn',
        '_confidence',
        '_contextSnippet',
        '_source',
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_advanced_cellular_models.csv', index=False)
    print(f"✓ Created VALIDATED_advanced_cellular_models.csv ({len(columns)} columns)")


def create_clinical_assessment_tools_template():
    """Create VALIDATED_clinical_assessment_tools.csv template."""
    columns = [
        # Synapse schema columns (syn52659113)
        'clinicalAssessmentToolId',
        'assessmentName',
        'assessmentType',
        'targetPopulation',
        'diseaseSpecific',
        'numberOfItems',
        'scoringMethod',
        'validatedLanguages',
        'psychometricProperties',
        'administrationTime',
        'availabilityStatus',
        'licensingRequirements',
        'digitalVersion',
        # Tracking columns
        '_pmid',
        '_doi',
        '_publicationTitle',
        '_foundIn',
        '_confidence',
        '_contextSnippet',
        '_source',
    ]
    df = pd.DataFrame(columns=columns)
    df.to_csv(OUTPUT_DIR / 'VALIDATED_clinical_assessment_tools.csv', index=False)
    print(f"✓ Created VALIDATED_clinical_assessment_tools.csv ({len(columns)} columns)")


def initialize_all_templates():
    """Initialize all VALIDATED_*.csv template files."""
    print("\n" + "="*80)
    print("INITIALIZING VALIDATED_*.csv TEMPLATES")
    print("="*80)
    print("\nCreating empty CSV files with proper column headers...\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    create_cell_lines_template()
    create_animal_models_template()
    create_genetic_reagents_template()
    create_antibodies_template()
    create_computational_tools_template()
    create_patient_derived_models_template()
    create_advanced_cellular_models_template()
    create_clinical_assessment_tools_template()

    print("\n" + "="*80)
    print("✅ ALL TEMPLATES INITIALIZED")
    print("="*80)
    print("\nThese files will be populated by format_validation_for_submission.py")
    print("after Sonnet reviews are complete.\n")


if __name__ == '__main__':
    initialize_all_templates()
