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

The LinkML schema defines relationships between entities (e.g., an AnimalModel
references a Donor, a DevelopmentRecord references an Investigator). Synapse
tables don't enforce foreign keys, so referential integrity must be checked
separately.

### Option A: Load into SQLite (recommended)

LinkML can generate SQL DDL with real foreign key constraints. Load Synapse
data into a local SQLite database and let the db engine enforce integrity for free:

```bash
# 1. Generate DDL from the schema
gen-sqltables modules/nf_research_tools.yaml --dialect sqlite > ddl.sql

# 2. Create the database
sqlite3 nf_tools.db < ddl.sql
```

Then export Synapse tables as CSV and load them:

```python
"""
Download Synapse tables and load into SQLite for FK validation.

Requires: pip install synapseclient
"""
import synapseclient
import sqlite3
import pandas as pd

syn = synapseclient.login()
db = sqlite3.connect("nf_tools.db")
db.execute("PRAGMA foreign_keys = ON")

# Map LinkML class names to their Synapse table IDs
TABLES = {
    "AnimalModel":            "syn26486808",
    "CellLine":               "syn26486823",
    "Antibody":               "syn26486811",
    "GeneticReagent":         "syn26486832",
    "Biobank":                "syn26486821",
    "ComputationalTool":      "syn73709226",
    "OrganoidProtocol":       "syn73709227",
    "PatientDerivedModel":    "syn73709228",
    "ClinicalAssessmentTool": "syn73709229",
    "Donor":                  "syn26486829",
    "MutationDetails":        "syn26486835",
    "Publication":            "syn26486839",
    "Investigator":           "syn26486833",
    "Funder":                 "syn26486830",
    "Vendor":                 "syn26486850",
    "VendorItem":             "syn26486843",
    "Observation":            "syn26486836",
    "DevelopmentRecord":      "syn26486807",
}

# Load parent tables first, then children (order matters for FK checks)
load_order = [
    "Donor", "Funder", "Investigator", "Publication", "Vendor",
    "MutationDetails",
    "AnimalModel", "CellLine", "Antibody", "GeneticReagent",
    "Biobank", "ComputationalTool", "OrganoidProtocol",
    "PatientDerivedModel", "ClinicalAssessmentTool",
    "VendorItem", "Observation", "DevelopmentRecord",
]

for table_name in load_order:
    syn_id = TABLES[table_name]
    df = syn.tableQuery(f"SELECT * FROM {syn_id}").asDataFrame()
    try:
        df.to_sql(table_name, db, if_exists="append", index=False)
        print(f"  OK {table_name} ({len(df)} rows)")
    except sqlite3.IntegrityError as e:
        print(f"FAIL {table_name}: {e}")

db.close()
```

Any FK violation will raise `sqlite3.IntegrityError` on insert, pinpointing
the exact orphaned reference.

### Option B: Query Synapse directly

For a quick spot-check without a local database:

```python
import synapseclient
syn = synapseclient.login()

FK_CHECKS = [
    # (source_table, source_column, target_table, target_column, description)
    ("syn26486808", "donorId",         "syn26486829", "donorId",         "AnimalModel → Donor"),
    ("syn26486823", "donorId",         "syn26486829", "donorId",         "CellLine → Donor"),
    ("syn26486807", "investigatorId",  "syn26486833", "investigatorId",  "Development → Investigator"),
    ("syn26486807", "publicationId",   "syn26486839", "publicationId",   "Development → Publication"),
    ("syn26486807", "funderId",        "syn26486830", "funderId",        "Development → Funder"),
    ("syn26486843", "vendorId",        "syn26486850", "vendorId",        "VendorItem → Vendor"),
    ("syn26486836", "publicationId",   "syn26486839", "publicationId",   "Observation → Publication"),
]

for src_table, src_col, tgt_table, tgt_col, desc in FK_CHECKS:
    query = f"""
        SELECT DISTINCT t1.{src_col}
        FROM {src_table} t1
        WHERE t1.{src_col} IS NOT NULL
          AND t1.{src_col} NOT IN (SELECT {tgt_col} FROM {tgt_table})
    """
    try:
        orphans = syn.tableQuery(query).asDataFrame()
        if len(orphans) > 0:
            print(f"FAIL {desc}: {len(orphans)} orphaned reference(s)")
            print(f"     Missing IDs: {orphans[src_col].tolist()[:5]}")
        else:
            print(f"  OK {desc}")
    except Exception as e:
        print(f"SKIP {desc}: {e}")
```

### Checking enum consistency

Verify that values in Synapse tables match the schema's permissible values:

```python
from linkml_runtime import SchemaView

sv = SchemaView("modules/nf_research_tools.yaml")

# Get all permissible values for an enum
enum_def = sv.get_enum("GeneticDisorderEnum")
valid = set(enum_def.permissible_values.keys())
print(f"GeneticDisorderEnum: {valid}")

# Compare against actual Synapse data
import synapseclient
syn = synapseclient.login()

df = syn.tableQuery("SELECT geneticDisorder FROM syn26486808").asDataFrame()
actual = set()
for val in df["geneticDisorder"].dropna():
    # Handle multivalued (comma-separated in Synapse)
    actual.update(v.strip() for v in val.split(","))

invalid = actual - valid
if invalid:
    print(f"Invalid values in AnimalModel.geneticDisorder: {invalid}")
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
