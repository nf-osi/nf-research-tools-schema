# Development Guide

Working with the LinkML schema in `modules/`.

## Prerequisites

```bash
pip install linkml
```

## Schema validation

Check that the schema itself is well-formed:

```bash
# Merge all modules and validate structure
gen-yaml modules/nf_research_tools.yaml > /dev/null

# Lint for best-practice warnings (camelCase names will warn — that's expected)
linkml-lint modules/nf_research_tools.yaml
```

## Generating artifacts

```bash
# Merged YAML (single-file distribution)
gen-yaml modules/nf_research_tools.yaml -o nf_research_tools.merged.yaml

# JSON Schema (for form validation, external tools)
gen-json-schema modules/nf_research_tools.yaml -o nf_research_tools.schema.json

# Python dataclasses
gen-python modules/nf_research_tools.yaml -o nf_research_tools.py

# Pydantic models
gen-pydantic modules/nf_research_tools.yaml -o nf_research_tools_pydantic.py

# Mermaid ER diagram
gen-erdiagram modules/nf_research_tools.yaml -o er_diagram.md

# Documentation site (markdown per class/slot/enum)
gen-doc modules/nf_research_tools.yaml -d docs/schema \
  --include-top-level-diagram --diagram-type mermaid_class_diagram
```

## Validation: Referential integrity

Synapse tables don't enforce foreign keys. LinkML's `gen-sqltables` generates
SQL DDL with real FK constraints from the schema. The script
[`scripts/check_referential_integrity.py`](../scripts/check_referential_integrity.py)
uses this to download Synapse data into a local SQLite database where the
engine enforces referential integrity on insert; any orphaned FK reference
raises `IntegrityError`. Class-to-table mappings are read from
`synapse_table_id` annotations on the schema.

```bash
# Generate DDL + load Synapse data into SQLite with FK enforcement
python scripts/check_referential_integrity.py --mode sqlite

# Quick alternative: query Synapse directly for orphaned references
python scripts/check_referential_integrity.py --mode synapse

# Check enum values in Synapse match schema permissible values
python scripts/check_referential_integrity.py --check-enums

# Both FK and enum checks
python scripts/check_referential_integrity.py --mode sqlite --check-enums
```

## Validation: Instance data

### CLI — validate a single file

```bash
# Validate a JSON submission against a specific tool type
linkml-validate -s modules/nf_research_tools.yaml \
  -C AnimalModel \
  submissions/animal_model/pending/tool_123.json

# Include detailed error context
linkml-validate -s modules/nf_research_tools.yaml \
  -C Antibody \
  -D \
  submissions/antibody/pending/tool_456.json

# Stop on first error (useful in CI)
linkml-validate -s modules/nf_research_tools.yaml \
  -C CellLine \
  --exit-on-first-failure \
  submissions/cell_line/pending/tool_789.json
```

### Python — validate programmatically

```python
from linkml.validator import validate
import json

with open("submissions/animal_model/pending/tool_123.json") as f:
    data = json.load(f)

report = validate(data, "modules/nf_research_tools.yaml", "AnimalModel")

for result in report.results:
    print(f"  {result.severity}: {result.message}")

if not report.results:
    print("Valid!")
```

### Batch validation

```python
from linkml.validator import Validator
from linkml.validator.plugins import JsonschemaValidationPlugin
from pathlib import Path
import json

validator = Validator(
    schema="modules/nf_research_tools.yaml",
    validation_plugins=[JsonschemaValidationPlugin(closed=True)],
)

CLASS_MAP = {
    "animal_model": "AnimalModel",
    "cell_line": "CellLine",
    "antibody": "Antibody",
    "genetic_reagent": "GeneticReagent",
    "biobank": "Biobank",
    "computational_tool": "ComputationalTool",
    "organoid_protocol": "OrganoidProtocol",
    "patient_derived_model": "PatientDerivedModel",
    "clinical_assessment_tool": "ClinicalAssessmentTool",
}

for subdir, cls_name in CLASS_MAP.items():
    for f in Path(f"submissions/{subdir}").rglob("*.json"):
        data = json.loads(f.read_text())
        report = validator.validate(data, cls_name)
        if report.results:
            print(f"FAIL {f}:")
            for r in report.results:
                print(f"  {r.severity}: {r.message}")
```

## Common tasks

### Adding a field to an existing tool type

1. Edit the relevant module in `modules/` (e.g., `animal_model.yaml`)
2. Add the attribute under the class's `attributes:` block
3. If the field uses an enum, add it to `enums.yaml` (shared) or the module file (type-specific)
4. Run `gen-yaml` to validate
5. The corresponding Synapse table column must be added separately

### Adding a new enum value

1. Find the enum in its module file (check `enums.yaml` for shared enums)
2. Add the value under `permissible_values:`
3. Run `gen-yaml` to validate

### Adding a new tool type

1. Create `modules/new_type.yaml` following the pattern of existing types
2. Add `is_a: Tool` and any relevant mixins
3. Add `- new_type` to imports in `modules/nf_research_tools.yaml`
4. Create the Synapse table and add the `synapse_table_id` annotation
5. Update submission forms, upsert workflows, etc.

### Using mixins

To share a cross-cutting concern with a new tool type, add the mixin to its
`mixins:` list. Available mixins:

| Mixin | Slots added | Used by |
|-------|-------------|---------|
| `HasDonor` | `donor` | AnimalModel, CellLine |
| `HasTransplantationDonor` | `transplantationDonor`, `transplantationType` | AnimalModel |
| `HasMutations` | `mutations` | AnimalModel, CellLine |
| `HasGeneticDisorder` | `geneticDisorder`, `manifestation` | AnimalModel, CellLine, Biobank |
| `HasTumorType` | `tumorType` | Biobank, PatientDerivedModel |
| `HasPassageNumber` | `passageNumber` | OrganoidProtocol, PatientDerivedModel |
