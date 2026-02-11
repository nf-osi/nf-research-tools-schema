# Next Steps: Implementation Phases 6-10

This document provides detailed instructions for completing the remaining implementation phases.

---

## Phase 6: Mining Script Updates (2-3 days)

### File 1: `tool_coverage/scripts/fetch_fulltext_and_mine.py`

Add these extraction functions after the existing extraction functions:

```python
def extract_computational_tools(text, patterns):
    """Extract computational tools (software, pipelines) from text."""
    tools = []

    # Software indicators
    for pattern in patterns['computational_tools']['software_indicators']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            context = extract_context(text, match, 150)
            # Check if context contains tool-specific keywords
            if any(phrase in context.lower() for phrase in patterns['computational_tools']['context_phrases']):
                tools.append({
                    'name': match,
                    'type': 'Computational Tool',
                    'context': context,
                    'confidence': calculate_confidence(text, match),
                    'pattern': pattern
                })

    # Repository URLs
    for pattern in patterns['computational_tools']['repository_indicators']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Extract tool name from URL
            tool_name = extract_tool_name_from_url(match)
            tools.append({
                'name': tool_name,
                'type': 'Computational Tool',
                'repository': match,
                'confidence': 0.9
            })

    return deduplicate_tools(tools)


def extract_advanced_cellular_models(text, patterns):
    """Extract advanced cellular models (organoids, assembloids) from text."""
    models = []

    # Organoid/assembloid indicators
    all_indicators = (
        patterns['advanced_cellular_models']['organoid_indicators'] +
        patterns['advanced_cellular_models']['assembloid_indicators']
    )

    for pattern in all_indicators:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            context = extract_context(text, match, 150)
            # Check for context phrases
            if any(phrase in context.lower() for phrase in patterns['advanced_cellular_models']['context_phrases']):
                models.append({
                    'name': match,
                    'type': 'Advanced Cellular Model',
                    'context': context,
                    'confidence': calculate_confidence(text, match)
                })

    return deduplicate_tools(models)


def extract_patient_derived_models(text, patterns):
    """Extract patient-derived models (PDX, humanized systems) from text."""
    models = []

    # PDX indicators
    for pattern in patterns['patient_derived_models']['pdx_indicators']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            context = extract_context(text, match, 150)
            # Check for engraftment context
            if any(phrase in context.lower() for phrase in patterns['patient_derived_models']['context_phrases']):
                models.append({
                    'name': match,
                    'type': 'Patient-Derived Model',
                    'context': context,
                    'confidence': calculate_confidence(text, match)
                })

    # Humanized mouse indicators
    for pattern in patterns['patient_derived_models']['humanized_indicators']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            context = extract_context(text, match, 150)
            models.append({
                'name': match,
                'type': 'Patient-Derived Model',
                'subtype': 'Humanized Mouse',
                'context': context,
                'confidence': calculate_confidence(text, match)
            })

    return deduplicate_tools(models)


def extract_clinical_assessment_tools(text, patterns):
    """Extract clinical assessment tools (questionnaires, scales) from text."""
    tools = []

    # Validated instruments
    for instrument in patterns['clinical_assessment_tools']['validated_instruments']:
        if instrument.lower() in text.lower():
            context = extract_context(text, instrument, 150)
            # Check for administration context
            if any(phrase in context.lower() for phrase in patterns['clinical_assessment_tools']['context_phrases']):
                tools.append({
                    'name': instrument,
                    'type': 'Clinical Assessment Tool',
                    'context': context,
                    'confidence': 0.95  # High confidence for validated instruments
                })

    # Generic questionnaire indicators
    for pattern in patterns['clinical_assessment_tools']['questionnaire_indicators']:
        matches = re.findall(f"{pattern}[\\w\\s-]+", text, re.IGNORECASE)
        for match in matches:
            context = extract_context(text, match, 150)
            if any(phrase in context.lower() for phrase in patterns['clinical_assessment_tools']['context_phrases']):
                tools.append({
                    'name': match.strip(),
                    'type': 'Clinical Assessment Tool',
                    'context': context,
                    'confidence': 0.7
                })

    return deduplicate_tools(tools)


# Update main extraction function
def extract_all_tools(text, patterns):
    """Extract all tool types from text."""
    all_tools = []

    # Existing extractions
    all_tools.extend(extract_antibodies(text, patterns))
    all_tools.extend(extract_cell_lines(text, patterns))
    all_tools.extend(extract_animal_models(text, patterns))
    all_tools.extend(extract_genetic_reagents(text, patterns))

    # New extractions
    all_tools.extend(extract_computational_tools(text, patterns))
    all_tools.extend(extract_advanced_cellular_models(text, patterns))
    all_tools.extend(extract_patient_derived_models(text, patterns))
    all_tools.extend(extract_clinical_assessment_tools(text, patterns))

    return all_tools
```

### File 2: `tool_coverage/scripts/format_mining_for_submission.py`

Add these formatting functions:

```python
def format_computational_tools(df):
    """Format computational tool entries for submission."""
    results = []
    for idx, row in df.iterrows():
        tool = {
            'resourceId': str(uuid.uuid4()),
            'resourceType': 'Computational Tool',
            'resourceName': row['tool_name'],
            'softwareName': row['tool_name'],
            'softwareType': extract_software_type(row),
            'softwareVersion': extract_version(row.get('context', '')),
            'programmingLanguage': extract_languages(row.get('context', '')),
            'sourceRepository': extract_repository(row.get('context', '')),
            'howToAcquire': row.get('repository', 'Contact authors'),
            'dateAdded': datetime.now().isoformat(),
            'dateModified': datetime.now().isoformat()
        }
        results.append(tool)
    return pd.DataFrame(results)


def format_advanced_cellular_models(df):
    """Format advanced cellular model entries for submission."""
    results = []
    for idx, row in df.iterrows():
        model = {
            'resourceId': str(uuid.uuid4()),
            'resourceType': 'Advanced Cellular Model',
            'resourceName': row['tool_name'],
            'modelType': classify_model_type(row['tool_name']),
            'derivationSource': extract_derivation_source(row.get('context', '')),
            'cellTypes': extract_cell_types(row.get('context', '')),
            'howToAcquire': 'Contact authors',
            'dateAdded': datetime.now().isoformat(),
            'dateModified': datetime.now().isoformat()
        }
        results.append(model)
    return pd.DataFrame(results)


def format_patient_derived_models(df):
    """Format patient-derived model entries for submission."""
    results = []
    for idx, row in df.iterrows():
        model = {
            'resourceId': str(uuid.uuid4()),
            'resourceType': 'Patient-Derived Model',
            'resourceName': row['tool_name'],
            'modelSystemType': row.get('subtype', 'PDX (Patient-Derived Xenograft)'),
            'patientDiagnosis': extract_diagnosis(row.get('context', '')),
            'hostStrain': extract_host_strain(row.get('context', '')),
            'howToAcquire': 'Contact authors',
            'dateAdded': datetime.now().isoformat(),
            'dateModified': datetime.now().isoformat()
        }
        results.append(model)
    return pd.DataFrame(results)


def format_clinical_assessment_tools(df):
    """Format clinical assessment tool entries for submission."""
    results = []
    for idx, row in df.iterrows():
        tool = {
            'resourceId': str(uuid.uuid4()),
            'resourceType': 'Clinical Assessment Tool',
            'resourceName': row['tool_name'],
            'assessmentName': row['tool_name'],
            'assessmentType': classify_assessment_type(row['tool_name']),
            'targetPopulation': extract_target_population(row.get('context', '')),
            'howToAcquire': 'Published instrument',
            'dateAdded': datetime.now().isoformat(),
            'dateModified': datetime.now().isoformat()
        }
        results.append(tool)
    return pd.DataFrame(results)


# Update main formatting function
def format_for_submission(mined_tools_df):
    """Format all mined tools for submission."""
    formatted_dfs = []

    for tool_type in mined_tools_df['type'].unique():
        subset = mined_tools_df[mined_tools_df['type'] == tool_type]

        if tool_type == 'Computational Tool':
            formatted_dfs.append(format_computational_tools(subset))
        elif tool_type == 'Advanced Cellular Model':
            formatted_dfs.append(format_advanced_cellular_models(subset))
        elif tool_type == 'Patient-Derived Model':
            formatted_dfs.append(format_patient_derived_models(subset))
        elif tool_type == 'Clinical Assessment Tool':
            formatted_dfs.append(format_clinical_assessment_tools(subset))
        # ... existing types ...

    return pd.concat(formatted_dfs, ignore_index=True)
```

### Testing
```bash
# Test extraction on sample papers
python tool_coverage/scripts/fetch_fulltext_and_mine.py \
    --pmids "PMID:12345678,PMID:23456789" \
    --output test_mining_output.json

# Verify output contains new tool types
jq '.tools[] | select(.type | contains("Computational"))' test_mining_output.json
```

---

## Phase 7: JSON-LD Schema Regeneration (1-2 days)

### Option A: Using Schematic Tool (Recommended - 1 hour)

```bash
# Install schematic if not already installed
pip install schematicpy

# Convert CSV to JSON-LD
schematic schema convert \
    --schema nf_research_tools.rdb.model.csv \
    --output nf-research-tools.jsonld
```

### Option B: Manual Update (1-2 days)

If schematic tool is not available, manually update `nf-research-tools.jsonld`:

1. **Add resourceType values** (lines 42-58):
```json
{
  "@id": "nf:ComputationalTool",
  "@type": "rdfs:Class",
  "rdfs:comment": "Computational Tool resource type",
  "rdfs:label": "Computational Tool",
  "rdfs:subClassOf": { "@id": "nf:ResourceType" }
}
```

2. **Add Details component classes** (~1,200 lines after line 899):
Follow the pattern of `GeneticReagentDetails` (lines 684-760)

3. **Add observationTypeOntologyId property** (after line 4503):
```json
{
  "@id": "nf:observationTypeOntologyId",
  "@type": "rdf:Property",
  "rdfs:comment": "Mammalian Phenotype Ontology (MP) term identifier",
  "rdfs:label": "observationTypeOntologyId",
  "schema:domainIncludes": { "@id": "nf:Observation" },
  "schema:rangeIncludes": { "@id": "schema:Text" }
}
```

4. **Add ObservationType value classes** (after line 5205):
```json
{
  "@id": "nf:Behavior",
  "@type": "rdfs:Class",
  "rdfs:comment": "Behavioral phenotypes observation type",
  "rdfs:label": "Behavior",
  "rdfs:subClassOf": { "@id": "nf:ObservationType" }
}
```

### Validation
```bash
# Validate JSON-LD syntax
python -c "import json; json.load(open('nf-research-tools.jsonld'))"

# Validate with schematic
schematic schema validate --schema nf-research-tools.jsonld
```

---

## Phase 8: Synapse Database Deployment (1 day)

### Prerequisites
- Synapse account with write permissions to `syn26338068`
- Python synapseclient installed
- Environment variable `NF_SERVICE_TOKEN` set

### Deployment Script

Create `deploy_new_tables.py`:

```python
import synapseclient
import os
from schematic_db.schema.schema import Schema, SchemaConfig
from schematic_db.rdb.synapse_database import SynapseDatabase
from schematic_db.rdb_builder.rdb_builder import RDBBuilder

# Login to Synapse
syn = synapseclient.Synapse()
syn.login(authToken=os.environ['NF_SERVICE_TOKEN'])

# Load schema
schema_url = "https://raw.githubusercontent.com/nf-osi/nf-research-tools-schema/main/nf-research-tools.jsonld"
schema_config = SchemaConfig(schema_url=schema_url)
schema = Schema(schema_config, database_config_from_build_db_py)

# Create database
database = SynapseDatabase(
    project_id='syn51710208',
    auth_token=os.environ['NF_SERVICE_TOKEN']
)

# Build new tables
rdb_builder = RDBBuilder(rdb=database, schema=schema)

# Create only new tables
new_tables = [
    'ComputationalToolDetails',
    'AdvancedCellularModelDetails',
    'PatientDerivedModelDetails',
    'ClinicalAssessmentToolDetails'
]

for table_name in new_tables:
    print(f"Creating table: {table_name}")
    rdb_builder.build_table(table_name)

# Add observationTypeOntologyId column to Observation table
print("Adding observationTypeOntologyId column to Observation table")
obs_table = syn.get('syn26486836')
new_column = {
    'name': 'observationTypeOntologyId',
    'columnType': 'STRING',
    'maximumSize': 20
}
syn.store(synapseclient.Column(**new_column, parent=obs_table))

print("Deployment complete!")
```

### Run Deployment
```bash
python deploy_new_tables.py
```

### Verification
```python
# Verify tables exist
import synapseclient
syn = synapseclient.Synapse()
syn.login()

tables = [
    'ComputationalToolDetails',
    'AdvancedCellularModelDetails',
    'PatientDerivedModelDetails',
    'ClinicalAssessmentToolDetails'
]

for table_name in tables:
    results = syn.tableQuery(f"SELECT * FROM {table_name} LIMIT 1")
    print(f"{table_name}: {len(results.asDataFrame())} rows")
```

---

## Phase 9: Testing & Validation (3-5 days)

### Unit Tests

Create `tests/test_new_tool_types.py`:

```python
import pytest
from tool_coverage.scripts.fetch_fulltext_and_mine import (
    extract_computational_tools,
    extract_advanced_cellular_models,
    extract_patient_derived_models,
    extract_clinical_assessment_tools
)

# Load patterns
with open('tool_coverage/config/mining_patterns.json') as f:
    patterns = json.load(f)['patterns']


class TestComputationalTools:
    def test_github_url_extraction(self):
        text = "Code available at https://github.com/user/tool-name"
        tools = extract_computational_tools(text, patterns)
        assert len(tools) > 0
        assert tools[0]['type'] == 'Computational Tool'

    def test_version_extraction(self):
        text = "analyzed using Software v2.1.3"
        tools = extract_computational_tools(text, patterns)
        assert len(tools) > 0
        assert 'v2.1.3' in tools[0]['name']


class TestAdvancedCellularModels:
    def test_organoid_extraction(self):
        text = "cerebral organoids were generated from iPSCs"
        models = extract_advanced_cellular_models(text, patterns)
        assert len(models) > 0
        assert 'organoid' in models[0]['name'].lower()

    def test_assembloid_extraction(self):
        text = "assembloids formed by fusing organoid regions"
        models = extract_advanced_cellular_models(text, patterns)
        assert len(models) > 0


class TestPatientDerivedModels:
    def test_pdx_extraction(self):
        text = "PDX models were established from patient tumors"
        models = extract_patient_derived_models(text, patterns)
        assert len(models) > 0
        assert models[0]['type'] == 'Patient-Derived Model'

    def test_nsg_mouse_extraction(self):
        text = "tumors were engrafted in NSG mice"
        models = extract_patient_derived_models(text, patterns)
        assert len(models) > 0


class TestClinicalAssessmentTools:
    def test_validated_instrument_extraction(self):
        text = "quality of life assessed using SF-36 questionnaire"
        tools = extract_clinical_assessment_tools(text, patterns)
        assert len(tools) > 0
        assert 'SF-36' in tools[0]['name']

    def test_generic_questionnaire_extraction(self):
        text = "participants completed a pain assessment scale"
        tools = extract_clinical_assessment_tools(text, patterns)
        assert len(tools) > 0
```

Run tests:
```bash
pytest tests/test_new_tool_types.py -v
```

### Integration Tests

Test full pipeline on known publications:

```python
# Create test_publications.json with known tool mentions
test_pubs = {
    "PMID:12345678": {
        "expected_tools": {
            "Computational Tool": ["ImageJ", "Python v3.8"],
            "Advanced Cellular Model": ["cerebral organoids"],
            "Patient-Derived Model": ["PDX-NF1-001"],
            "Clinical Assessment Tool": ["SF-36"]
        }
    }
}

# Run mining and validate
for pmid, expected in test_pubs.items():
    results = mine_publication(pmid)
    for tool_type, tools in expected["expected_tools"].items():
        found = [t for t in results if t['type'] == tool_type]
        assert len(found) >= len(tools), f"Missing {tool_type} tools in {pmid}"
```

---

## Phase 10: Documentation (2-3 days)

### User Guide Updates

Create `docs/NEW_TOOL_TYPES.md`:

```markdown
# New Tool Types Guide

## Computational Tools
Submit software, pipelines, and analysis tools used in NF research.

**Required Fields:**
- Software Name
- Software Type
- How to Acquire

**Optional Fields:**
- Version, Programming Language, Repository URL, License, etc.

**Example:** ImageJ analysis plugin for neurofibroma quantification

## Advanced Cellular Models
Submit organoids, assembloids, and 3D cell cultures.

**Required Fields:**
- Model Type (Organoid/Assembloid/etc.)
- Derivation Source (iPSC/ESC/Primary Tissue)
- Cell Types

**Example:** NF1-deficient cerebral organoids from patient iPSCs

## Patient-Derived Models
Submit PDX models and humanized mouse systems.

**Required Fields:**
- Model System Type (PDX/Humanized Mouse/etc.)
- Patient Diagnosis

**Example:** MPNST PDX model in NSG mice

## Clinical Assessment Tools
Submit questionnaires, scales, and patient-reported outcome measures.

**Required Fields:**
- Assessment Name
- Assessment Type
- Target Population

**Example:** NF-specific quality of life questionnaire (INQoL)
```

### API Documentation

Update API docs with new endpoints and examples:

```markdown
## New Tool Type Endpoints

### Submit Computational Tool
POST /api/v1/computational-tools
Content-Type: application/json

{
  "softwareName": "NF-Analyzer",
  "softwareType": "Analysis Software",
  "programmingLanguage": ["Python", "R"],
  "sourceRepository": "https://github.com/user/nf-analyzer",
  "howToAcquire": "Open source on GitHub"
}

### Submit Advanced Cellular Model
POST /api/v1/advanced-cellular-models
...

### Submit Patient-Derived Model
POST /api/v1/patient-derived-models
...

### Submit Clinical Assessment Tool
POST /api/v1/clinical-assessment-tools
...
```

---

## Quick Commands Reference

### Development
```bash
# Run mining on test set
python tool_coverage/scripts/fetch_fulltext_and_mine.py --test

# Format mining output
python tool_coverage/scripts/format_mining_for_submission.py input.json

# Regenerate JSON-LD
schematic schema convert --schema nf_research_tools.rdb.model.csv

# Build database
python build_db/build_db.py
```

### Testing
```bash
# Run unit tests
pytest tests/ -v

# Run integration tests
pytest tests/integration/ -v

# Test specific tool type
pytest tests/ -k "computational_tools"

# Check test coverage
pytest --cov=tool_coverage tests/
```

### Deployment
```bash
# Deploy to staging
python deploy_new_tables.py --env staging

# Deploy to production
python deploy_new_tables.py --env production

# Rollback if needed
python rollback_deployment.py --tables "ComputationalToolDetails,..."
```

---

## Troubleshooting

### Common Issues

**Issue:** Pattern matching too broad (high false positives)
**Solution:** Refine patterns by adding more specific context_phrases

**Issue:** Tools not being extracted
**Solution:** Check if patterns exist in mining_patterns.json, verify regex syntax

**Issue:** Database foreign key constraint errors
**Solution:** Ensure parent resource exists before inserting details

**Issue:** MP ontology ID validation failing
**Solution:** Verify format is `MP:XXXXXXX` (7 digits), check observation_ontology_mappings.json

---

## Timeline Estimate

- Phase 6 (Mining Scripts): 2-3 days
- Phase 7 (JSON-LD): 1-2 days (or 1 hour with schematic)
- Phase 8 (Synapse Deployment): 1 day
- Phase 9 (Testing): 3-5 days
- Phase 10 (Documentation): 2-3 days

**Total: 9-14 days** (full-time work)
**With schematic tool: 8-13 days**

---

## Success Criteria

✅ All unit tests passing (90%+ coverage)
✅ Integration tests passing on test publications
✅ Synapse tables created and accessible
✅ Submission forms working in Data Curator
✅ Mining pipeline extracts new tool types
✅ AI validation includes new types
✅ Documentation complete and reviewed
✅ No regressions in existing functionality

---

**Last Updated:** 2026-02-10
**Next Phase:** Phase 6 - Mining Script Updates
