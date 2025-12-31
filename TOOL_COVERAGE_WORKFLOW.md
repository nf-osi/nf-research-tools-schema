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
- Uses existing tools as training data (1,142 tools)
- Applies fuzzy matching (88% threshold) to find tool mentions
- Focuses on Methods sections to avoid false positives

**Outputs:**
- `novel_tools_FULLTEXT_mining.csv` - All findings
- `priority_publications_FULLTEXT.csv` - Top 30 by tool count
- `GFF_publications_with_tools_FULLTEXT.csv` - GFF-specific findings

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

### Downloadable Artifacts

All reports are available as workflow artifacts:
- PDF reports with visualizations
- CSV files for manual review
- Full logs from analysis and mining

## Next Steps After Report

1. **Download Artifacts:** Access reports from workflow run
2. **Review Priority Publications:** Check top publications for valid tool mentions
3. **Verify in Full Text:** Confirm tools are actually used in Methods
4. **Submit to Database:** Add validated tools via submission forms
5. **Track Progress:** Monitor coverage percentage in next report

## Limitations

### Full Text Availability
- Only publications in PubMed Central (PMC) can be fully analyzed
- Closed-access articles may only show in coverage analysis
- Typically ~30-50% of publications have PMC full text

### False Positives
- Fuzzy matching may identify gene/protein names that aren't reagents
- Manual verification always required before adding to database
- Focus on Methods sections reduces but doesn't eliminate false positives

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
