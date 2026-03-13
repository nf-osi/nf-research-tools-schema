# Tool Annotation Review

## Overview

The tool annotation review system analyzes `individualID` annotations from Synapse and suggests new cell lines to add to the tools database.

**Workflow**: `monthly-submission-check.yml` (embedded step)
**Script**: `scripts/review_tool_annotations.py`
**Trigger**: Runs as part of monthly check (1st of each month, 9 AM UTC) OR manual workflow_dispatch
**Schedule Position**: Part of Step 1 in workflow sequence (monthly entry point)

## Purpose

Ensures that `individualID` values used in file annotations are properly represented in the tools database as cell lines, preventing orphaned or unrecognized tool references.

## How It Works

### 1. Data Collection

**Annotations Source** (`syn52702673`):
- Queries all `individualID` values from file annotations
- Counts frequency of each unique value
- Filters to values with ≥2 occurrences (configurable)

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
   - Generates `submissions/cell_lines/annotation_*.json` entry

### 3. Facet Analysis

Analyzes all columns in syn51730943:

- **Existing facets**: Documents current facets and their value diversity
- **Suggested new facets**: Columns with 5-100 unique values
- **Low diversity facets**: Flags facets with very few values (may not be useful)

### 4. Output Generation

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

**Submission JSON files** (`submissions/cell_lines/annotation_*.json`):
- One file per suggested new cell line
- Form-compatible JSON with `_source: annotation_review`
- Pre-filled: cell line name, source context
- Needs manual review before moving to `submissions/accepted/`

## Assumptions

### All individualIDs are Cell Lines

The system assumes all `individualID` values refer to cell lines. This is because:

1. The `individualID` annotation is primarily used for biospecimen tracking
2. Most biospecimens in NF research come from cell lines
3. Cell lines are the most common type of individual/specimen

**Manual Review Required**: Before merging the PR, verify that suggested resources are indeed cell lines (not sample IDs or typos).

## Workflow Integration

### Position in Chain

```
1. monthly-submission-check (1st of month, 9 AM UTC)
   ├─ Runs annotation review
   ├─ Creates submissions/cell_lines/annotation_*.json for new cell lines
   ├─ Creates annotation PR if new cell lines found
   └─ Creates monthly issue (label: tool-submissions)
         ↓ (issue closed by reviewer)
2. publication-mining → Mines NF Portal + PubMed for tools
         ↓ (PR merged)
3. link-tool-datasets → Links tools to datasets
         ↓ ...
```

### PR Creation

When new cell lines are found, `monthly-submission-check.yml` creates a PR with:

**Title**: `Annotation Review: N new cell line suggestion(s)`

**Branch**: `annotation-submissions-{run_number}`

**Labels**:
- `annotation-submissions`
- `needs-manual-review`

**Assignee**: BelindaBGarana

**Files Included**:
- `submissions/cell_lines/annotation_*.json` — one per suggested cell line
- `tool_annotation_suggestions.json`
- `tool_annotation_suggestions.md`

### Manual Review Checklist

Before merging the annotation PR:

- [ ] Verify suggested cell lines are legitimate NF-relevant cell lines (not typos, sample IDs, or errors)
- [ ] For each valid cell line: move to `submissions/accepted/`:
  ```bash
  git mv submissions/cell_lines/annotation_<name>.json submissions/accepted/cell_lines/
  ```
- [ ] Fill in known fields (tissue, disease, species, etc.) in the JSON
- [ ] Delete files that are not real cell lines
- [ ] Check suggested synonyms in `tool_annotation_suggestions.md` (informational; update manually if needed)
- [ ] Ensure no duplicate entries

### What Happens After Merge

When the annotation PR (or any PR touching `submissions/accepted/`) is merged:

1. **Immediate**: `upsert-tools.yml` triggers automatically
   - Compiles `submissions/accepted/**/*.json` → appends new rows to `ACCEPTED_cell_lines.csv`
   - Validates CSV schemas
   - Cleans tracking columns (prefixed with `_`)
   - Uploads to Synapse:
     - syn26486823 (cell lines table)
     - syn26450069 (resources table)

### What Happens If No New Cell Lines Found

- No annotation PR is created
- Monthly issue still created with annotation results section:
  > ✅ No new cell lines found in `individualID` annotations this month — nothing to do.

## Configuration

### Tunable Parameters

**In Script** (`review_tool_annotations.py`):
- `MIN_FREQUENCY = 2` - Minimum occurrences to suggest a value
- `MIN_FILTER_FREQUENCY = 5` - Minimum unique values for facet suggestion
- `FUZZY_MATCH_THRESHOLD = 0.85` - Similarity threshold for synonym matching

### Data Sources

**Annotations**: `syn52702673`
- File annotations view
- Contains individualID field
- Public access

**Tools**: `syn51730943`
- Tools materialized view
- Contains resourceName, synonyms, all tool fields
- Public access

## Example Output

### New Resources Suggested

```
individualID: "NF-ipsc-1234"
Usage count: 15
Status: New cell line
Action: Write submissions/cell_lines/annotation_NF-ipsc-1234.json
```

### Synonym Suggested

```
individualID: "NF-90.8"
Fuzzy matched: "NF90-8" in resource "NF90-8 Cell Line" (score: 0.92)
Usage count: 8
Action: Add "NF-90.8" to synonyms field (manual update required)
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
- Delete the `submissions/cell_lines/annotation_*.json` file for that entry
- Or manually create the correct resource type in Synapse

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

### Submission JSON Format

Each `submissions/cell_lines/annotation_*.json` file:
```json
{
  "toolType": "cell_line",
  "_source": "annotation_review",
  "_context": "Found as individualID annotation in N Synapse dataset(s)",
  "_confidence": "",
  "_verdict": "include",
  "_usageType": "novel",
  "_pmid": "",
  "_doi": "",
  "_publicationTitle": "",
  "_year": "",
  "userInfo": {},
  "basicInfo": {
    "cellLineName": "NF-ipsc-1234",
    "description": "",
    "synonyms": "",
    "species": "",
    "sex": "",
    "age": null,
    "race": ""
  },
  "category": "",
  "cellLineGeneticDisorder": "",
  ...
}
```

**Tracking columns** (prefixed with `_`, removed before Synapse upload):
- `_source`, `_context`, `_confidence`, `_verdict`, `_usageType`, `_pmid`, etc.

## Related Documentation

- **Workflow sequence**: [`.github/workflows/README.md`](../.github/workflows/README.md)
- **Workflow coordination**: [`WORKFLOW_COORDINATION.md`](WORKFLOW_COORDINATION.md)
- **Scripts**: [`../scripts/README.md`](../scripts/README.md)
- **Tool coverage**: [`../tool_coverage/README.md`](../tool_coverage/README.md)
