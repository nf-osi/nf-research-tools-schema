# Tool Coverage Monitoring Workflow

## Overview

This repository includes an automated workflow to monitor tool coverage in the NF research tools database and suggest novel tools to add from publications. The workflow runs weekly and creates GitHub issues with findings.

## Components

### 1. Scripts

#### `analyze_missing_tools.py`
Analyzes current tool coverage against GFF-funded publications:
- Queries publications table (syn16857542) for GFF-funded publications
- Checks which publications have linked tools in the database (syn51730943)
- Calculates coverage percentage against 80% target
- Generates PDF report with visualizations

**Outputs:**
- `GFF_Tool_Coverage_Report.pdf` - Visual coverage analysis
- `gff_publications_MISSING_tools.csv` - Publications without tools

#### `fetch_fulltext_and_mine.py`
Mines full text from PubMed Central for novel tools:
- Fetches full text XML from PMC using PMIDs
- Extracts Methods sections using pattern matching
- Uses existing tools as training data (1,142+ tools)
- Applies fuzzy matching (88% threshold) to find tool mentions
- Extracts cell line names via regex patterns (no name field in database)
- **Distinguishes development vs usage** using keyword context analysis
- **Filters generic commercial tools** (e.g., C57BL/6, nude mice) unless NF-specific
- Focuses on Methods sections to avoid false positives

**Outputs:**
- `novel_tools_FULLTEXT_mining.csv` - All findings with development flags
- `priority_publications_FULLTEXT.csv` - Top 30 by tool count
- `GFF_publications_with_tools_FULLTEXT.csv` - GFF-specific findings
- `mining_summary_ALL_publications.csv` - All publications processed

#### `extract_tool_metadata.py`
Extracts rich metadata from Methods section context:
- **Antibodies:** clonality (monoclonal/polyclonal), host organism, vendor, catalog number, reactive species
- **Cell Lines:** category (cancer/normal), organ, tissue
- **Animal Models:** background strain/substrain, manifestations, allele types
- **Genetic Reagents:** vector type, bacterial resistance, backbone

Uses pattern matching within 200-character windows around tool mentions.

#### `format_mining_for_submission.py`
Transforms mining results into submission-ready CSVs:
- Formats tool mentions to match Synapse table schemas
- Generates unique UUIDs for new entries
- **Pre-fills fields using extracted metadata**
- Creates publication-tool linking entries
- Adds metadata for tracking (source, confidence, context)
- **Generates NEW ROWS only** - files are meant to be appended after verification

**Outputs (Core Tables):**
- `SUBMIT_resources.csv` - For syn26450069 (main table with resourceName)

**Outputs (Detail Tables):**
- `SUBMIT_animal_models.csv` - For syn26486808
- `SUBMIT_antibodies.csv` - For syn26486811
- `SUBMIT_cell_lines.csv` - For syn26486823
- `SUBMIT_genetic_reagents.csv` - For syn26486832

**Outputs (Relationship Tables):**
- `SUBMIT_publication_links.csv` - For syn51735450
- `SUBMIT_development.csv` - For syn26486807 (publications where tools were developed)

**Pre-filled Fields:**
- Antibodies: clonality, host, vendor, catalog #, reactive species
- Cell lines: category, organ, tissue
- Animal models: strain, substrain, manifestations, allele type
- Genetic reagents: vector type, resistance, backbone

#### `generate_coverage_summary.py`
Generates markdown summary for GitHub issue:
- Summarizes current coverage status
- Lists novel tools discovered
- Highlights GFF publications with potential tools
- Provides action items and links to artifacts

**Output:**
- `issue_body.md` - Markdown content for GitHub issue

### 2. GitHub Actions Workflow

**File:** `.github/workflows/check-tool-coverage.yml`

**Schedule:** Weekly on Mondays at 9 AM UTC

**Manual Trigger:** Available via workflow dispatch

**Steps:**
1. Checkout repository
2. Set up Python 3.11 with pip cache
3. Install dependencies from requirements.txt
4. Run coverage analysis
5. Mine publications for novel tools
6. Generate summary report
7. Upload all reports as artifacts (90-day retention)
8. Create or update GitHub issue with findings

## Configuration

### Required Secrets

The workflow requires the following GitHub secrets to be configured:

1. **`SYNAPSE_AUTH_TOKEN`**
   - Personal access token for Synapse API
   - Used to query publications and tools databases
   - Generate at: https://www.synapse.org/#!PersonalAccessTokens:

2. **`NF_SERVICE_GIT_TOKEN`**
   - GitHub token with `issues: write` permission
   - Used to create/update GitHub issues
   - Can use a personal access token or GitHub App token

### Dependencies

All dependencies are listed in `requirements.txt`:
- synapseclient >= 4.4.0
- pandas >= 2.0.0
- numpy >= 1.24.0
- matplotlib >= 3.7.0
- seaborn >= 0.12.0
- requests >= 2.31.0

## Running Locally

### Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Set Synapse auth token
export SYNAPSE_AUTH_TOKEN="your_token_here"
```

### Run Coverage Analysis
```bash
python analyze_missing_tools.py
```

### Run Full Text Mining
```bash
python fetch_fulltext_and_mine.py
```

### Generate Summary
```bash
python generate_coverage_summary.py > issue_body.md
```

## Understanding the Results

### Coverage Metrics

- **Target:** 80% of GFF-funded publications should have linked tools
- **Current Status:** Displayed in weekly reports
- **Needed:** Number of additional publications required to reach target

### Tool Mining Results

The mining process identifies potential tools in four categories:
- **Cell Lines** (🧫) - Cell culture resources
- **Antibodies** (🔬) - Immunological reagents
- **Animal Models** (🐭) - Transgenic/knockout models
- **Genetic Reagents** (🧬) - Plasmids, vectors, constructs

Each tool is tagged with:
- **Development Status** - Whether the tool was developed in this publication or just used
- **Context Metadata** - Extracted characteristics (species, strain, clonality, etc.)

### Priority Publications

Publications are ranked by:
1. Tool count (number of potential tools mentioned)
2. Methods section length (longer = more detail)
3. GFF funding status (prioritized)

## Workflow Outputs

### GitHub Issue

A weekly issue is created with:
- Current coverage status
- Novel tools discovered
- Top priority publications to review
- Links to downloadable artifacts
- Summary of submission-ready CSVs

### Downloadable Artifacts

All reports are available as workflow artifacts:
- **Analysis Reports:**
  - PDF reports with visualizations
  - CSV files for manual review
  - Full logs from analysis and mining

- **Submission Files:**
  - `SUBMIT_*.csv` - Formatted for direct table submission
  - Each CSV matches the schema of its target Synapse table
  - Includes UUIDs, publication links, and metadata

## Next Steps After Report

### 1. Download and Review Artifacts

Access the workflow artifacts from the GitHub Actions run:
- Download `SUBMIT_*.csv` files for your tool type
- Review `priority_publications_FULLTEXT.csv` for context
- Check PDF reports for coverage visualizations

### 2. Validate Tool Mentions

For each tool in the submission CSVs:
- ✅ **Verify in Full Text:** Check the publication's Methods section
- ✅ **Confirm Usage:** Ensure the tool was actually used (not just cited)
- ✅ **Check for Duplicates:** Search existing database entries
- ✅ **Remove False Positives:** Delete entries that aren't real tools

### 3. Complete Required Fields

Many fields are **automatically pre-filled** from metadata extraction, but may need review:

**Automatically Pre-filled:**
- **Antibodies:** clonality, host organism, reactive species, vendor, catalog number
- **Cell Lines:** category, organ, tissue
- **Animal Models:** background strain/substrain, manifestations, allele types
- **Genetic Reagents:** vector type, backbone, bacterial resistance

**Still Need Manual Completion:**
- Fields left empty if not detected in context
- Vendor information if not recognized
- Specific allele nomenclature
- Population doubling times
- RRID identifiers

**Review Pre-filled Fields:**
- Verify accuracy of auto-extracted values
- Check for pattern matching false positives
- Confirm species and organism assignments

### 4. Submit to Synapse Tables

**IMPORTANT:** All `SUBMIT_*.csv` files contain NEW ROWS only - these should be **appended** to existing tables, not used as replacements.

Upload validated entries to the appropriate tables:

**Core Tables:**
- `SUBMIT_resources.csv` → syn26450069 (Resource table with resourceName)

**Detail Tables:**
- `SUBMIT_animal_models.csv` → syn26486808
- `SUBMIT_antibodies.csv` → syn26486811
- `SUBMIT_cell_lines.csv` → syn26486823
- `SUBMIT_genetic_reagents.csv` → syn26486832

**Relationship Tables:**
- `SUBMIT_publication_links.csv` → syn51735450
- `SUBMIT_development.csv` → syn26486807 (Development publications)

### 5. Track Progress

Monitor coverage percentage in the next weekly report to see improvement toward the 80% target.

## Limitations

### Full Text Availability
- Only publications in PubMed Central (PMC) can be fully analyzed
- Closed-access articles may only show in coverage analysis
- Typically ~30-50% of publications have PMC full text

### False Positives
- Fuzzy matching may identify gene/protein names that aren't reagents
- Manual verification always required before adding to database
- Focus on Methods sections reduces but doesn't eliminate false positives

**Improvements to Reduce False Positives:**
- Generic animal strains (C57BL/6, nude mice) filtered unless NF-specific genetic modifications present
- Development context detection prevents listing tools that were only purchased/used
- Cell line extraction uses regex patterns validated against cell line naming conventions
- Commercial tool filtering removes standard lab reagents without NF context

### Rate Limits
- NCBI E-utilities: 3 requests/second (10 with API key)
- Workflow limited to prevent excessive runtime
- Full mining may take 1-2 hours for large publication sets

## Troubleshooting

### Workflow Fails on Synapse Login
- Verify `SYNAPSE_AUTH_TOKEN` secret is set correctly
- Check token hasn't expired at https://www.synapse.org/#!PersonalAccessTokens:

### No Full Text Retrieved
- Many publications aren't in PMC (paywall)
- Check PMID is correct in publications table
- Some publishers restrict text mining

### Mining Finds No Tools
- Methods sections may use different terminology
- Tool names may not match existing database entries
- Consider manual review of publication

## Contributing

To improve the mining accuracy:
1. Add more tool names to database (increases training data)
2. Adjust fuzzy matching threshold in `fetch_fulltext_and_mine.py`
3. Add domain-specific patterns for tool types
4. Improve Methods section extraction patterns

## Support

For issues or questions:
- Open a GitHub issue with label `tool-coverage`
- Tag maintainers in weekly report comments
- Check workflow logs in Actions tab
