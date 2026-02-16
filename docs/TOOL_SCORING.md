# Tool Completeness Scoring System

## Overview

The NF Research Tools database uses a completeness scoring system to evaluate the quality and thoroughness of tool documentation. This helps researchers identify well-characterized tools and highlights areas where additional information is needed.

**Maximum Score**: 110 points

---

## Scoring Categories

### 1. Availability (30 points)

Measures how easily researchers can access the tool.

**For Biobanks:**
- biobankURL: 30 points

**For Other Tool Types:**
- Vendor/Developer info (howToAcquire): 15 points
- RRID identifier: 7.5 points
- Publication DOI: 7.5 points

### 2. Critical Information (30 points)

Type-specific essential metadata fields. Points distributed evenly across required fields.

**Animal Model** (4 fields @ 7.5 pts each):
- animalModelGeneticDisorder, backgroundStrain, animalState, description

**Cell Line** (4 fields @ 7.5 pts each):
- cellLineCategory, cellLineGeneticDisorder, cellLineManifestation, synonyms

**Antibody** (5 fields @ 6 pts each):
- targetAntigen, reactiveSpecies, hostOrganism, clonality, conjugate

**Genetic Reagent** (5 fields @ 6 pts each):
- insertName, insertSpecies, vectorType, insertEntrezId, vectorBackbone

**Biobank** (5 fields @ 6 pts each):
- specimenTissueType, diseaseType, tumorType, specimenFormat, specimenType

**Computational Tool** (4 fields @ 7.5 pts each):
- softwareName, softwareType, programmingLanguage, sourceRepository

**Advanced Cellular Model** (4 fields @ 7.5 pts each):
- modelType, derivationSource, cellTypes, cultureSystem

**Patient-Derived Model** (4 fields @ 7.5 pts each):
- modelSystemType, patientDiagnosis, hostStrain, tumorType

**Clinical Assessment Tool** (4 fields @ 7.5 pts each):
- assessmentName, assessmentType, targetPopulation, validatedLanguages

### 3. Other Information (15 points)

Type-specific supplementary fields. Points distributed evenly across fields.

**Animal Model** (3 fields @ 5 pts each):
- backgroundSubstrain, synonyms, animalModelOfManifestation

**Cell Line** (1 field):
- tissue: 15 points

**Antibody** (1 field):
- cloneId: 15 points

**Genetic Reagent** (2 fields @ 7.5 pts each):
- synonyms, promoter

**Biobank** (1 field):
- specimenPreparationMethod: 15 points

**Computational Tool** (2 fields @ 7.5 pts each):
- softwareVersion, containerized

**Advanced Cellular Model** (2 fields @ 7.5 pts each):
- maturationTime, characterizationMethods

**Patient-Derived Model** (2 fields @ 7.5 pts each):
- passageNumber, molecularCharacterization

**Clinical Assessment Tool** (2 fields @ 7.5 pts each):
- psychometricProperties, availabilityStatus

### 4. Observations (25 points max)

Scientific characterizations and experimental findings.

- **With DOI**: 7.5 points each
- **Without DOI**: 2.5 points each
- **Maximum**: 25 points (capped)

Observations with DOI citations are weighted more heavily as they represent peer-reviewed findings.

### 5. Datasets (10 bonus points)

Linked datasets from NF Portal publications.

- **First dataset**: 5 points
- **Second dataset**: 2.5 points
- **Third dataset**: 2.5 points
- **Additional datasets**: No additional points (capped at 10)

Datasets are identified through tool publications linked to NF Portal studies.

---

## Completeness Categories

Scores are grouped into categories to provide quick quality assessments:

| Category | Score Range | Description |
|----------|-------------|-------------|
| **Excellent** | 80-110 | Well-documented with observations and datasets |
| **Good** | 60-79 | Most key fields filled, some characterization |
| **Fair** | 40-59 | Basic information present, limited details |
| **Poor** | 20-39 | Minimal information, many gaps |
| **Minimal** | 0-19 | Very limited documentation |

---

## Implementation

### Scripts

**`tool_scoring.py`**: Main scoring script
- Queries all resource types from Synapse
- Calculates scores for each tool
- Stores results in ToolCompletenessScores table
- Generates summary statistics by tool type
- Updates materialized view with scores

**`create_materialized_view.py`**: Creates optimized view
- Generates new materialized view with all 9 tool types
- Includes completeness scores and key metadata
- Optimized to fit under Synapse 64KB row limit
- Does not modify existing views

### Synapse Tables

| Table | Synapse ID | Contents |
|-------|-----------|----------|
| ToolCompletenessScores | TBD | Individual tool scores with breakdown |
| ToolCompletenessSummary | TBD | Summary statistics by resource type |
| NF_Research_Tools_Complete_View | TBD | Materialized view with scores |

### Workflow

**score-tools.yml**: Automated scoring workflow
- Triggered when dataset linking PR is merged
- Runs `tool_scoring.py`
- Uploads results to Synapse
- Generates PDF report

---

## Tool Type Support

The scoring system supports all 9 resource types:

**Original (5 types)**:
- Animal Model
- Cell Line
- Antibody
- Genetic Reagent
- Biobank

**New (4 types)**:
- Computational Tool
- Advanced Cellular Model
- Patient-Derived Model
- Clinical Assessment Tool

Each type has specific critical and supplementary fields tailored to its domain.

---

## Data Sources

### Resource Data
- **syn26450069**: Base Resource table
- **syn26486808**: AnimalModelDetails
- **syn26486811**: AntibodyDetails
- **syn26486821**: BiobankDetails
- **syn26486823**: CellLineDetails
- **syn26486832**: GeneticReagentDetails
- **syn73709226**: ComputationalToolDetails
- **syn73709227**: AdvancedCellularModelDetails
- **syn73709228**: PatientDerivedModelDetails
- **syn73709229**: ClinicalAssessmentToolDetails

### Linked Data
- **syn26486836**: Observations
- **syn26486807**: Publications (Development)
- **syn26486839**: Tool Publications with Datasets
- **syn51734029**: Investigators
- **syn51734076**: Funders
- **syn51735419**: Donor Demographics

---

## Usage Examples

### Query High-Scoring Tools
```sql
SELECT resourceName, resourceType, total_score
FROM ToolCompletenessScores
WHERE total_score >= 80
ORDER BY total_score DESC;
```

### Find Tools Needing Observations
```sql
SELECT resourceName, resourceType, total_score, observation_score
FROM ToolCompletenessScores
WHERE observation_score = 0
AND total_score < 60
ORDER BY total_score DESC;
```

### Dataset Bonus Point Analysis
```sql
SELECT
  resourceType,
  AVG(dataset_score) as avg_dataset_bonus,
  COUNT(CASE WHEN dataset_score > 0 THEN 1 END) as tools_with_datasets
FROM ToolCompletenessScores
GROUP BY resourceType
ORDER BY avg_dataset_bonus DESC;
```

### Completeness by Tool Type
```sql
SELECT
  resourceType,
  completeness_category,
  COUNT(*) as tool_count
FROM ToolCompletenessScores
GROUP BY resourceType, completeness_category
ORDER BY resourceType, completeness_category;
```

---

## Future Enhancements

Potential additions to the scoring system:

- **Usage Metrics**: Citation counts, download frequency
- **Quality Indicators**: Validation status, standardized formats
- **Recency Weighting**: Time-based scoring for updates
- **Community Ratings**: User feedback integration
- **Reproducibility**: Replication studies, protocols shared

---

## Questions?

Contact: nf-osi@sagebionetworks.org
