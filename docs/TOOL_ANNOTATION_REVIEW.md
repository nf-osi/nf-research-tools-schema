# Tool Annotation Review

## Overview

The tool annotation review system analyzes `individualID` and `modelSystemName` annotations from Synapse to:
1. **Suggest new cell lines** — `individualID` values not yet in the tools database
2. **Enrich existing tool records** — fill blank fields in cell lines, animal models, patient-derived models, and donors using consensus annotation values

**Workflow**: `review-tool-annotations.yml`
**Scripts**: `scripts/review_tool_annotations.py`, `scripts/enrich_existing_tools.py`
**Trigger**: Scheduled weekly (Monday 9 AM UTC) OR manual workflow_dispatch
**Schedule Position**: Step 1 in workflow sequence (entry point)

## Purpose

- Ensures that `individualID` values used in file annotations are properly represented in the tools database as cell lines, preventing orphaned or unrecognized tool references.
- Backfills blank fields (`tissue`, `cellLineManifestation`, `cellLineGeneticDisorder`, `animalModelGeneticDisorder`, `animalModelOfManifestation`, `sex`, `age`, `species`) using consensus values derived from NF Portal file annotations matched by `modelSystemName`.

## How It Works

### 1. Data Collection

**Annotations Source for new cell line suggestions** (`syn52702673`):
- Queries all `individualID` values from file annotations
- Counts frequency of each unique value
- Filters to values with ≥2 occurrences (configurable)

**Annotations Source for field enrichment** (`syn16858331`):
- Queries `modelSystemName`, `tissue`, `tumorType`, `diagnosis`, `sex`, `age`, `species` from the full NF Portal file annotations view
- `modelSystemName` matches `resourceName` in the tools database — used as the join key

**Tools Source** (`syn51730943`):
- Fetches all tools with resourceName and synonyms
- Analyzes which columns are configured as facets
- Evaluates value diversity across all fields

### 2. IndividualID Analysis

For each individualID value, the script:

1. **Exact match with resourceName**
   - If found: Classified as "existing resource"
   - No action needed

2. **Exact match with synonyms**
   - If found: Classified as "existing synonym"
   - No action needed

3. **Fuzzy match with synonyms** (threshold: 0.85)
   - If match score ≥ 0.85: Suggest adding as synonym
   - Example: "NF90.8" fuzzy matches "NF90-8" → suggest synonym

4. **No match**
   - Suggest creating as new cell line
   - Generates SUBMIT_cell_lines.csv entry

### 3. Facet Analysis

Analyzes all columns in syn51730943:

- **Existing facets**: Documents current facets and their value diversity
- **Suggested new facets**: Columns with 5-100 unique values
- **Low diversity facets**: Flags facets with very few values (may not be useful)

### 4. Output Generation — New Cell Lines

Creates multiple files:

**JSON Output** (`tool_annotation_suggestions.json`):
```json
{
  "individual_id_suggestions": {
    "new_resources": [...],      // New cell lines to add
    "new_synonyms": [...],        // Synonyms to add
    "existing_exact": [...],      // Already in resourceName
    "existing_synonyms": [...]    // Already in synonyms
  },
  "facet_analysis": {
    "existing_facets": {...},     // Current facet info
    "suggested_new_facets": {...} // Potential new facets
  }
}
```

**Markdown Report** (`tool_annotation_suggestions.md`):
- Human-readable summary
- Categorized suggestions
- Facet recommendations
- Usage frequencies

**Submission CSVs**:
- `SUBMIT_cell_lines.csv` - New cell lines
- `SUBMIT_resources.csv` - Corresponding resource entries

### 5. Field Enrichment — Existing Tool Records

`scripts/enrich_existing_tools.py` backfills blank fields in existing tool records using consensus annotation values. A value is only proposed when **all** non-blank annotation values for a given `modelSystemName` agree on the same canonical form (case-normalized, validated against schema valid values).

**Fields enriched per table**:

| Table (Synapse ID) | Target fields | Annotation source |
|---|---|---|
| CellLineDetails (syn26486823) | `tissue`, `cellLineManifestation`, `cellLineGeneticDisorder` | `tissue`, `tumorType`, `diagnosis` |
| AnimalModelDetails (syn26486808) | `animalModelGeneticDisorder`, `animalModelOfManifestation` | `diagnosis`, `tumorType` |
| PatientDerivedModelDetails (syn73709228) | `patientDiagnosis`, `tumorType` | `diagnosis`, `tumorType` |
| Donor (syn26486829) | `sex`, `age`, `species` | `sex`, `age`, `species` (via cell line → donorId chain) |

**Rules**:
- Only fills currently-blank fields — existing values are never overwritten
- Values must match schema valid values (or a synonym map) — free-form text is rejected
- For `age`: all annotation values must be the same numeric value

**Output files**:
- `SUBMIT_cell_line_updates.csv` - Cell line rows with proposed field updates
- `SUBMIT_animal_model_updates.csv` - Animal model rows with proposed field updates
- `SUBMIT_patient_derived_model_updates.csv` - PDX rows with proposed field updates
- `SUBMIT_donor_updates.csv` - Donor rows with proposed field updates
- `tool_field_enrichment.json` - Machine-readable enrichment summary (counts by table and field)
- `tool_field_enrichment.md` - Human-readable enrichment summary

## Assumptions

### All individualIDs are Cell Lines

The system assumes all `individualID` values refer to cell lines. This is because:

1. The `individualID` annotation is primarily used for biospecimen tracking
2. Most biospecimens in NF research come from cell lines
3. Cell lines are the most common type of individual/specimen

**Manual Review Required**: Before merging the PR, verify that suggested resources are indeed cell lines and fill in the required `organ` field.

## Workflow Integration

### Position in Chain

```
1. review-tool-annotations (scheduled Mon 9AM UTC) → Analyzes annotations → Creates PR  ← ENTRY POINT
         ↓ (PR merged)
2. check-tool-coverage → Mines NF Portal + PubMed for tools
         ↓ (PR merged)
3. link-tool-datasets → Links tools to datasets
         ↓ ...
```

### PR Creation

A PR is created when either new cell lines are found **or** existing tool fields can be enriched.

**Title**: `🔍 Annotation Review (N new, M enriched)`

**Labels**:
- `automated-annotation-review`
- `cell-lines`
- `needs-manual-review`

**Assignee**: BelindaBGarana

**Files Included**:
- `SUBMIT_cell_lines.csv` *(if new cell lines found)*
- `SUBMIT_resources.csv` *(if new cell lines found)*
- `SUBMIT_cell_line_updates.csv` *(if enrichment proposed)*
- `SUBMIT_animal_model_updates.csv` *(if enrichment proposed)*
- `SUBMIT_patient_derived_model_updates.csv` *(if enrichment proposed)*
- `SUBMIT_donor_updates.csv` *(if enrichment proposed)*
- `tool_annotation_suggestions.json`
- `tool_annotation_suggestions.md`
- `tool_field_enrichment.json` *(always written)*
- `tool_field_enrichment.md` *(always written)*

### Manual Review Checklist

Before merging the PR:

- [ ] Verify suggested cell lines are legitimate (not typos or errors)
- [ ] Fill in `organ` field for each new cell line (REQUIRED)
- [ ] Check suggested synonyms make sense
- [ ] Review facet suggestions (informational only)
- [ ] Ensure no duplicate entries
- [ ] Review proposed field updates in `SUBMIT_*_updates.csv` (check `_match_key` column to confirm annotation match)
- [ ] Check `tool_field_enrichment.json` for per-field update counts

### What Happens After Merge

When the PR is merged:

1. **Immediate**: `upsert-tools.yml` triggers automatically
   - Validates CSV schemas
   - Cleans tracking columns (prefixed with `_`)
   - Inserts new rows to Synapse (new cell lines / resources):
     - syn26486823 (cell lines table)
     - syn26450069 (resources table)
   - Updates existing rows in Synapse (enrichment, update-mode — only fills blank fields):
     - syn26486823 (cell line field updates)
     - syn26486808 (animal model field updates)
     - syn73709228 (patient-derived model field updates)
     - syn26486829 (donor field updates)

2. **Next Step**: `check-tool-coverage.yml` triggers
   - Continues the workflow chain

## Configuration

### Tunable Parameters

**In Script** (`review_tool_annotations.py`):
- `MIN_FREQUENCY = 2` - Minimum occurrences to suggest a value
- `MIN_FILTER_FREQUENCY = 5` - Minimum unique values for facet suggestion
- `FUZZY_MATCH_THRESHOLD = 0.85` - Similarity threshold for synonym matching

**In Workflow** (`review-tool-annotations.yml`):
- `min_count` input - Override minimum frequency (workflow_dispatch)
- `annotation_limit` input - Limit records for testing

### Data Sources

**Annotations (new cell line suggestions)**: `syn52702673`
- Narrow annotations view (individualID, resourceType, studyId, etc.)
- Contains `individualID` field
- Public access

**Annotations (field enrichment)**: `syn16858331`
- Full NF Portal file annotations view
- Contains `modelSystemName`, `tissue`, `tumorType`, `diagnosis`, `sex`, `age`, `species`
- Join key: `modelSystemName` matches `resourceName` in the tool database
- Public access

**Tools resource table**: `syn26450069`
- Base Resource table with `cellLineId`, `animalModelId` foreign keys
- Used to map `resourceName` → detail-table primary key
- Public access

**Tools**: `syn51730943`
- Tools materialized view (denormalized)
- Contains resourceName, synonyms, all tool fields
- Used for new cell line comparison and facet analysis
- Public access

## Example Output

### New Resources Suggested

```
individualID: "NF-ipsc-1234"
Usage count: 15
Status: New cell line
Action: Create SUBMIT_cell_lines.csv entry
```

### Synonym Suggested

```
individualID: "NF-90.8"
Fuzzy matched: "NF90-8" in resource "NF90-8 Cell Line" (score: 0.92)
Usage count: 8
Action: Add "NF-90.8" to synonyms field
Note: Manual update required (not in SUBMIT_*.csv)
```

### Facet Suggestion

```
Column: "cellLineCategory"
Unique values: 12
Current status: Not a facet
Recommendation: Add as facet for filtering
Sample values: ["Cancer cell line", "Induced pluripotent stem cell", ...]
```

## Troubleshooting

### No PR Created

**Possible reasons**:
- All individualID values already exist as resources or synonyms
- No values meet minimum frequency threshold
- Workflow ran but had no new suggestions

**Check**:
- View workflow logs in Actions tab
- Check `tool_annotation_suggestions.json` artifact
- Verify syn52702673 has data

### Wrong Resource Type Suggested

**Problem**: IndividualID should not be a cell line

**Solution**:
- Close PR without merging
- Update script assumption if needed
- Or manually create correct resource type in Synapse

### Fuzzy Matching Issues

**Problem**: Too many/few synonym suggestions

**Solution**:
- Adjust `FUZZY_MATCH_THRESHOLD` in script
- Lower = more lenient (more suggestions)
- Higher = stricter (fewer suggestions)
- Recommended range: 0.80-0.90

## Technical Details

### Fuzzy Matching Algorithm

Uses Python's `difflib.SequenceMatcher`:
- Compares strings character by character
- Returns similarity ratio (0.0 to 1.0)
- Case-insensitive comparison
- Works well for typos, formatting variations

### CSV Format

**SUBMIT_cell_lines.csv** schema:
```
cellLineId,donorId,originYear,organ,strProfile,tissue,...
uuid1234,,,,[empty fields]...,
```

**Tracking columns** (prefixed with `_`, removed before upload):
```
_cellLineName,_individualID,_usage_count,_source
```

**SUBMIT_resources.csv** schema:
```
resourceId,resourceName,resourceType,synonyms,cellLineId,...
uuid5678,NF-ipsc-1234,Cell Line,,uuid1234,...
```

## Related Documentation

- **Workflow sequence**: [`.github/workflows/README.md`](../.github/workflows/README.md)
- **Workflow coordination**: [`WORKFLOW_COORDINATION.md`](WORKFLOW_COORDINATION.md)
- **Scripts**: [`../scripts/README.md`](../scripts/README.md)
- **Tool coverage**: [`../tool_coverage/README.md`](../tool_coverage/README.md)
