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
3. upsert-tools → Uploads accepted tools to Synapse
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
- [ ] Fill in known fields (tissue, disease, species, etc.) directly in the JSON
- [ ] If not a real cell line or a duplicate, **delete the file** (no `accepted/` subdirectory move needed post-LinkML-migration -- see below)
- [ ] Check suggested synonyms in `tool_annotation_suggestions.md` (informational; update manually if needed)
- [ ] Ensure no duplicate entries

### What Happens After Merge

**Post-LinkML-migration correction**: there is no `submissions/accepted/` subdirectory step anymore. Everything remaining in `submissions/cell_lines/` (with `_source: annotation_review`) at merge time is uploaded automatically -- editing a file in place or deleting it is the whole review action, no `git mv` required.

When the annotation PR is merged:

1. **Immediate**: `upsert-tools.yml` triggers automatically
   - Compiles `submissions/cell_lines/*.json` remaining at merge
   - Cleans tracking columns (prefixed with `_`)
   - Uploads to `syn26486823` (`CellLineDetails`) -- still the current, live per-resourceType detail table post-migration, **not** retired; it feeds into the tools materialized view `syn51730943` alongside the other resourceType detail tables

**Correction to an earlier draft of this doc**: only the old flat `Resource` table (`syn26450069`) was retired by the LinkML migration (fields absorbed into the per-resourceType detail tables -- see `docs/MIGRATION.md` for the full before/after). `syn26486823` was never retired and is still the correct upload target above.

### What Happens If No New Cell Lines Found

- No annotation PR is created
- Monthly issue still created with annotation results section:
  > ✅ No new cell lines found in `individualID` annotations this month — nothing to do.

## Tool<->Study Links and Resource_id Backfill (#132, #154, #246)

The same script also mines two additional automations -- tool<->study links
and a Resource_id file-annotation backfill -- both additive-only, so
nothing existing is ever modified or removed. **Neither is written to
Synapse automatically.** Both require a human to review a generated CSV
first.

### Why these require manual review

An individualID match against a known tool's `resourceName`/synonym (exact,
or a stripped-disambiguation-suffix fallback -- e.g. `JH-2-002` matching
`JH-2-002 (MPNST)` when that stripped base name isn't shared by more than
one resourceId in the tools registry) looks like a high-confidence,
mechanical signal, but it isn't a safe one to write unattended: a single
donor/specimen individualID can legitimately span more than one downstream
resource, and the tools registry alone can't always tell you that.

Confirmed live on [#246 review](https://github.com/nf-osi/nf-research-tools-schema/pull/246#issuecomment-5403174547):
`JH-2-002` currently has three resourceIds sharing that stripped base name
(two Cell Lines -- MPNST and Plexiform Neurofibroma -- and one
Patient-Derived Model), so today it's correctly excluded as ambiguous. But
files tagged `individualID=JH-2-002` split cleanly between MPNST and
Plexiform Neurofibroma via each file's **own** `tumorType` annotation --
if only one of those siblings were registered (e.g. before the other was
added, or if it's never registered at all -- an unregistered raw donor
specimen, say), the match would have looked "unambiguous within the
registry" while still being wrong for roughly half the files. Registry
uniqueness isn't the same as biological uniqueness, so nothing gets written
without a human confirming each row. See `_build_resource_match_lookups`'s
docstring in `review_tool_annotations.py` for the exact matching tiers this
applies to.

### The review-then-apply flow

1. A normal run (`python scripts/review_tool_annotations.py`, e.g. via the
   monthly workflow) mines candidates and writes them to
   `tool_study_links_for_review.csv` and
   `resource_id_annotations_for_review.csv` -- nothing is upserted. Each row
   includes the matched tool info plus review context pulled straight from
   Synapse (`tumorType`, `diagnosis`, `tissue`, and for the Resource_id CSV,
   `individualID` and the specific `addedResourceId`), so a reviewer can
   judge a candidate without a separate Synapse lookup.
2. A human reviews each CSV and **deletes any row that isn't clearly
   correct** -- when in doubt, delete the row rather than keep it.
3. Re-run the script against the (possibly trimmed) CSV to actually write
   the survivors:
   ```bash
   python scripts/review_tool_annotations.py --apply-tool-study-links-csv tool_study_links_for_review.csv
   python scripts/review_tool_annotations.py --apply-resource-id-annotations-csv resource_id_annotations_for_review.csv
   ```
   These are the *only* code paths that call `upsert_tool_study_links` /
   `upsert_resource_id_annotations`.

### Tool<->study links

Once applied, writes `(resourceId, studyId)` pairs to `syn26461958` for
every matched individualID/study co-occurrence not already recorded there.
Candidate count reported in the monthly issue under "Tool<->Study Links".

### Resource_id file-annotation backfill

The Tool Details "Data > Files" tab in synapse-web-monorepo renders off a
`Resource_id` annotation set directly on files -- historically only ever
set manually (779 of ~82k individualID-tagged files as of 2026-08). Once
applied, this backfill appends the matched resourceId to that file's
`Resource_id` list wherever a match is found and the value isn't already
present, so the existing tab picks up more files with **no frontend change
needed**.

### Every write is snapshotted

`snapshot_table()` is called immediately before and immediately after each
of these writes (and the tool<->study link write above), independent of
Synapse's trash can, per standing policy.

## Cross-Project Table Dependencies (#249)

Not everything this script reads from or writes to lives in this repo's
own Synapse project. Two different projects are involved:

| Table | Project | Role |
|---|---|---|
| `syn51730943` | **Neurofibromatosis Research Tools Central** (`syn26338068`) -- this repo's project | Tools materialized view: resourceName, synonyms, all tool fields |
| `syn52702673` ("Portal - MV Files") | **NF Data Portal (backend)** (`syn26451327`) | MaterializedView joining file annotations -- **read-only**, has no writable row-to-entity mapping of its own |
| `syn16858331` ("Portal - Files") | **NF Data Portal (backend)** (`syn26451327`) | The real, writable EntityView `syn52702673` is built from. `individualID` and `Resource_id` both live here; **all writes must target this table, not the MV** |
| `syn26461958` ("Study - Resource") | **NF Data Portal (backend)** (`syn26451327`) | Tool<->study junction table |

The practical implication: three of the four tables this script's
tool<->study/Resource_id mining depends on are owned by the NF Data Portal
project, not this repo's own NFRTC project. Anyone maintaining this script
who only has NFRTC-project permissions may not be able to write to
`syn16858331` or `syn26461958` without separately requesting NF Data Portal
access.

## Configuration

### Tunable Parameters

**In Script** (`review_tool_annotations.py`):
- `MIN_FREQUENCY = 2` - Minimum occurrences to suggest a value
- `MIN_FILTER_FREQUENCY = 5` - Minimum unique values for facet suggestion
- `FUZZY_MATCH_THRESHOLD = 0.85` - Similarity threshold for synonym matching

### Data Sources

**Annotations (read)**: `syn52702673`
- File annotations MaterializedView, joined for convenience
- Contains individualID, studyId/studyName, Resource_id
- Public access
- See "Cross-Project Table Dependencies" above -- this is read-only; annotation writes target `syn16858331` instead

**Annotations (write target for Resource_id backfill)**: `syn16858331`
- The writable EntityView `syn52702673` is built from
- Public read, requires NF Data Portal project write access

**Tools**: `syn51730943`
- Tools materialized view
- Contains resourceName, synonyms, all tool fields
- Public access

**Tool<->Study Links**: `syn26461958`
- Junction table, additive-only writes
- Requires NF Data Portal project write access

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
