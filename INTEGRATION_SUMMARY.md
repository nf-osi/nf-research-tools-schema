# Integration Summary: Filtered PubMed Mining Workflow

## Overview
Successfully integrated the filtered PubMed query workflow into `fetch_fulltext_and_mine.py`. The script now automatically filters publications and queries PubMed for additional research-focused NF publications.

## Changes Made

### 1. Updated `fetch_fulltext_and_mine.py`

#### Added Query Filters
- Added `PUBMED_QUERY_FILTERS` constant with the same filters from `mine_pubmed_nf.py` lines 382-397
- Filters exclude clinical case reports, reviews, retrospective studies, and other non-research publications

#### New Functions
- **`should_exclude_publication(title, journal)`**: Applies local filtering to exclude publications based on title/journal
- **`check_pmc_availability(pmids, max_retries)`**: Checks which PMIDs have full text available in PMC
- **`load_previously_reviewed_pmids(cache_file)`**: Loads set of previously reviewed PMIDs from cache
- **`save_reviewed_pmids(pmids, cache_file)`**: Saves reviewed PMIDs to cache (append mode)
- **`query_pubmed(query, max_results, max_retries)`**: Queries PubMed API and returns matching PMIDs
- **`fetch_pubmed_metadata_batch(pmids, max_retries)`**: Fetches metadata for batches of PMIDs from PubMed

#### Updated Workflow
The main function now follows this pipeline:

1. **Load Previously Reviewed PMIDs**:
   - Reads `tool_coverage/outputs/previously_reviewed_pmids.csv`
   - Maintains running list of all reviewed publications
   - Prevents re-processing the same publications

2. **Load NF Portal Publications** (from Synapse table syn16857542)

3. **Apply Local Filters**: Exclude publications with:
   - Clinical terms in title (case, review, patient, clinical, cohort, pediatric, etc.)
   - Non-research study types (retrospective, trial, guideline, perspective, etc.)
   - Demographic-focused terms (child, woman, family, pregnancy, etc.)
   - Procedure terms (surgery, resection, MRI, tomography, etc.)
   - Excluded journals (Clinical case reports, JA clinical reports)

4. **Check PMC Full Text Availability**:
   - Queries PubMed Central API for each NF Portal publication
   - Verifies full text is available for mining
   - Excludes publications without full text access
   - **Critical step**: Ensures we can actually fetch methods/results sections

5. **Query PubMed** (optional, skip with `--skip-pubmed-query`):
   - Uses same filters as `mine_pubmed_nf.py`
   - Searches for: neurofibroma*[Abstract] + all exclusion filters
   - Requires: hasabstract, free full text, Journal Article type
   - Fetches up to 10,000 results
   - **Excludes previously reviewed PMIDs** to avoid re-processing

6. **Merge & Deduplicate**:
   - Combines NF Portal and PubMed publications
   - Removes duplicates (prefers NF Portal data)
   - Standardizes column names
   - Excludes already-linked publications
   - Excludes previously reviewed publications

7. **Mine Full Text for Tools**:
   - Fetches full text from PMC
   - Extracts Methods, Introduction, Results, Discussion sections
   - Mines for research tools
   - Continues with existing workflow

8. **Save Reviewed PMIDs**:
   - Appends newly reviewed PMIDs to cache file
   - Ensures they won't be re-processed in future runs

#### New Command-Line Options
- `--skip-pubmed-query`: Skip PubMed query, only use NF Portal publications

## Workflow Integration

### GitHub Actions (`check-tool-coverage.yml`)
No changes needed! The workflow already calls `fetch_fulltext_and_mine.py`, so it will automatically use the new integrated pipeline.

Current workflow step (lines 81-103):
```yaml
- name: Mine publications for novel tools
  env:
    SYNAPSE_AUTH_TOKEN: ${{ secrets.SYNAPSE_AUTH_TOKEN }}
  run: |
    python tool_coverage/scripts/fetch_fulltext_and_mine.py
```

This will now automatically:
1. Load previously reviewed PMIDs
2. Filter NF Portal publications (title/journal + PMC availability)
3. Query PubMed for additional research publications
4. Exclude previously reviewed publications
5. Mine all new publications for tools
6. Save newly reviewed PMIDs to cache

## Filters Applied

### Title Exclusions
Publications with these terms in the title are excluded:
- Clinical: case, clinical, patient, cohort, trial, retrospective
- Demographics: child, pediatric, adult, woman, women, family, pregnancy
- Procedures: surgery, resection, MRI, tomography
- Study types: review, guideline, perspective, overview, presentation
- Other: pain, outcomes, prevalence, prognostic, facial, hearing loss

### Journal Exclusions
- Clinical case reports
- JA clinical reports

### PubMed Requirements
- Must have abstract (hasabstract)
- Must have free full text available in PMC
- Must be Journal Article publication type
- Must mention neurofibromatosis in abstract

### Cache File: Previously Reviewed PMIDs
The script maintains a running cache of reviewed publications at:
- **Path**: `tool_coverage/outputs/previously_reviewed_pmids.csv`
- **Format**: Single column CSV with PMID values
- **Purpose**: Prevents re-processing the same publications across multiple runs
- **Behavior**:
  - Loaded at start of each run
  - New PMIDs appended after mining
  - Automatically created if doesn't exist
  - Should be committed to git to persist across workflow runs

## Usage Examples

### Standard Mining (NF Portal + PubMed)
```bash
python tool_coverage/scripts/fetch_fulltext_and_mine.py
```

### Testing with Limited Publications
```bash
python tool_coverage/scripts/fetch_fulltext_and_mine.py --max-publications 50
```

### NF Portal Only (Skip PubMed Query)
```bash
python tool_coverage/scripts/fetch_fulltext_and_mine.py --skip-pubmed-query
```

### In GitHub Actions Workflow
The workflow automatically runs with default settings (NF Portal + PubMed):
```bash
# Triggered automatically or manually via workflow_dispatch
# No configuration changes needed
```

## Expected Results

### Before Integration
- Only mined publications already in NF Portal (Synapse)
- Included clinical case reports and reviews
- Included publications without full text access
- Re-processed publications across runs
- Limited to ~2,000 publications

### After Integration
- Mines NF Portal publications (filtered for research + PMC full text)
- Queries PubMed for additional research publications (with full text)
- Excludes non-research publications
- Excludes publications without PMC full text
- **Incremental processing**: Only mines new publications each run
- Expected: 500-2,000 research-focused publications with full text
- Better signal-to-noise ratio for tool mining
- Faster subsequent runs (skips previously reviewed publications)

## Next Steps

1. **Test the workflow**:
   ```bash
   # Test locally with limited publications
   python tool_coverage/scripts/fetch_fulltext_and_mine.py --max-publications 10
   ```

2. **Run full mining** (via GitHub Actions or locally):
   ```bash
   python tool_coverage/scripts/fetch_fulltext_and_mine.py
   ```

3. **AI Validation** (existing step):
   ```bash
   python tool_coverage/scripts/run_publication_reviews.py
   ```

4. **Format Results** (existing step):
   ```bash
   python tool_coverage/scripts/format_mining_for_submission.py
   ```

## Files Modified

- ✅ `tool_coverage/scripts/fetch_fulltext_and_mine.py` - Main mining script (updated with integrated PubMed query & PMC checking)
- ✅ `.github/workflows/review-tool-annotations.yml` - Updated to be scheduled entry point (Monday 9 AM UTC)
- ✅ `.github/workflows/check-tool-coverage.yml` - Already set up, no changes needed
- ✅ `INTEGRATION_SUMMARY.md` - This documentation
- ✅ `docs/WORKFLOW_COORDINATION.md` - Updated workflow sequence documentation
- ✅ `docs/TOOL_ANNOTATION_REVIEW.md` - Updated to reflect new entry point
- ✅ `README.md` - Updated workflow sequence
- ✅ `.github/workflows/README.md` - Updated workflow documentation

## Files Created (Runtime)

- `tool_coverage/outputs/previously_reviewed_pmids.csv` - Cache of reviewed PMIDs (created automatically)

## Files Not Modified (No Changes Needed)

- `.github/workflows/check-tool-coverage.yml` - Already calls the updated script
- `tool_coverage/scripts/mine_pubmed_nf.py` - Original PubMed mining script (still functional)
- Other workflow scripts - Remain unchanged

## Benefits

1. **Automated Filtering**: No manual CSV filtering needed
2. **PMC Full Text Verification**: Only mines publications with accessible full text
3. **Incremental Processing**: Maintains cache of reviewed PMIDs to avoid re-processing
4. **Expanded Coverage**: Includes PubMed publications not in NF Portal
5. **Research-Focused**: Filters out clinical case reports and reviews
6. **Tool-Relevant**: Focuses on publications likely to describe research tools
7. **Workflow Integration**: Seamlessly integrates with existing GitHub Actions
8. **Backward Compatible**: Can still skip PubMed query if needed
9. **Faster Subsequent Runs**: Only processes new publications each time

## Verification

To verify the integration works:

```bash
# 1. Check help output
python tool_coverage/scripts/fetch_fulltext_and_mine.py --help

# 2. Test with small sample
python tool_coverage/scripts/fetch_fulltext_and_mine.py --max-publications 5

# 3. Check output files
ls -lh tool_coverage/outputs/processed_publications.csv
ls -lh tool_coverage/outputs/mining_summary_ALL_publications.csv
```

Expected output structure:
- Filtering statistics (NF Portal)
- PubMed query results
- Merge statistics
- Mining progress
- Tool counts (existing vs novel)
