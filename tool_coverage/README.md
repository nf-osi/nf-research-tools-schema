# Tool Coverage Monitoring Workflow

## Overview

This repository includes an automated workflow to monitor tool coverage in the NF research tools database and suggest novel tools to add from publications. The workflow runs weekly and creates GitHub issues with findings.

## Components

### 1. Scripts

#### `tool_coverage/scripts/analyze_missing_tools.py`
Analyzes current tool coverage against GFF-funded publications:
- Queries publications table (syn16857542) for GFF-funded publications
- Checks which publications have linked tools in the database (syn51730943)
- Calculates coverage percentage against 80% target
- Generates PDF report with visualizations

**Outputs:**
- `GFF_Tool_Coverage_Report.pdf` - Visual coverage analysis
- `gff_publications_MISSING_tools.csv` - Publications without tools

#### `tool_coverage/scripts/fetch_fulltext_and_mine.py`
Mines abstracts and full text for tools, with AI validation enabled by default:
- **Mines ALL publications via abstracts** (fetched from PubMed API using PMID) - no PMC requirement
- **Enhances with full text when available:** Fetches PMC XML and extracts Methods + Introduction sections
- **Matches against existing tools** using fuzzy matching (88% threshold) before creating new entries
- **AI validates mined tools** (default: enabled) using Goose agent to filter false positives
- Uses existing tools as training data (1,142+ tools) for pattern matching
- Extracts cell line names via regex patterns (no name field in database)
- **Distinguishes development vs usage** using keyword context analysis (100-300 char windows)
- **Filters generic commercial tools** (e.g., C57BL/6, nude mice) unless NF-specific
- **Tracks source sections** (abstract, methods, introduction) for each tool found
- **Deduplicates** tools found in multiple sections, preferring Methods metadata

**Tool Matching & Validation Process:**
1. Mine abstract (always available)
2. Mine Methods + Introduction sections (when PMC full text available)
3. Merge results with deduplication
4. Match tool names against existing database tools (fuzzy, 88%)
5. **If match found:** Link to existing tool (reuse resourceId)
6. **If no match:** Create new tool entry (generate UUID)
7. **AI validation (default):** Goose agent analyzes each tool in context
8. **Filter false positives:** Remove disease/gene names, non-lab publications

**Command-line options:**
```bash
# With AI validation (default)
python tool_coverage/scripts/fetch_fulltext_and_mine.py

# Without AI validation (faster, may have false positives)
python tool_coverage/scripts/fetch_fulltext_and_mine.py --no-validate

# Limit publications for testing
python tool_coverage/scripts/fetch_fulltext_and_mine.py --max-publications 50
```

**Outputs (without AI validation):**
- `novel_tools_FULLTEXT_mining.csv` - All findings with existing/novel categorization
- `SUBMIT_*.csv` - Submission-ready CSVs (may contain false positives)

**Outputs (with AI validation - default):**
- `novel_tools_FULLTEXT_mining.csv` - All findings
- `SUBMIT_*.csv` - Unvalidated submissions
- `VALIDATED_*.csv` - Validated submissions (false positives removed) ⭐ USE THESE
- `tool_reviews/validation_report.xlsx` - AI validation summary
- `tool_reviews/results/{PMID}_tool_review.yaml` - Per-publication validation details

#### `tool_coverage/scripts/extract_tool_metadata.py`
Extracts rich metadata from Methods section context:
- **Antibodies:** clonality (monoclonal/polyclonal), host organism, vendor, catalog number, reactive species
- **Cell Lines:** category (cancer/normal), organ, tissue
- **Animal Models:** background strain/substrain, manifestations, allele types
- **Genetic Reagents:** vector type, bacterial resistance, backbone

Uses pattern matching within 200-character windows around tool mentions.

#### `tool_coverage/scripts/format_mining_for_submission.py`
Transforms mining results into submission-ready CSVs:
- **Separates existing tool links from novel tool entries**
- Formats novel tool mentions to match Synapse table schemas
- Generates unique UUIDs for new entries
- **Pre-fills fields using extracted metadata**
- Creates publication-tool linking entries
- Adds metadata for tracking (source, confidence, context)
- **Generates NEW ROWS only** - files are meant to be appended after verification

**Outputs (Core Tables):**
- `SUBMIT_resources.csv` - For syn26450069 (main table with resourceName)

**Outputs (Detail Tables) - Novel tools only:**
- `SUBMIT_animal_models.csv` - For syn26486808
- `SUBMIT_antibodies.csv` - For syn26486811
- `SUBMIT_cell_lines.csv` - For syn26486823
- `SUBMIT_genetic_reagents.csv` - For syn26486832

**Outputs (Relationship Tables):**
- `SUBMIT_publication_links_EXISTING.csv` - Links to existing tools (uses existing resourceIds)
- `SUBMIT_publication_links_NEW.csv` - Links for newly discovered tools
- `SUBMIT_development.csv` - For syn26486807 (publications where tools were developed)

**Pre-filled Fields:**
- Antibodies: clonality, host, vendor, catalog #, reactive species
- Cell lines: category, organ, tissue
- Animal models: strain, substrain, manifestations, allele type
- Genetic reagents: vector type, resistance, backbone

#### `tool_coverage/scripts/generate_coverage_summary.py`
Generates markdown summary for GitHub issue:
- Summarizes current coverage status
- Lists novel tools discovered
- Highlights GFF publications with potential tools
- Provides action items and links to artifacts

**Output:**
- `issue_body.md` - Markdown content for GitHub issue

#### `tool_coverage/scripts/run_publication_reviews.py`
AI-powered validation of mined tools using Goose agent (optional):
- **Validates mined tools** to filter out false positives (gene/disease names misidentified as tools)
- **Analyzes publication type** (lab research vs clinical studies vs questionnaires)
- **Checks tool keywords** (antibody, plasmid, cell line, etc.) near mentions
- **Generates validation reports** with detailed reasoning for accept/reject decisions
- **Creates VALIDATED_*.csv** files with rejected tools removed

⚠️ **Requires Anthropic API key** - See [tool_coverage/docs/AI_VALIDATION_README.md](tool_coverage/docs/AI_VALIDATION_README.md) for setup

**Usage:**
```bash
# Validate specific publications
python tool_coverage/scripts/run_publication_reviews.py --pmids "PMID:28078640"

# Validate all mined publications (skips already-reviewed to save API costs)
python tool_coverage/scripts/run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv

# Force re-review of already-reviewed publications
python tool_coverage/scripts/run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv --force-rereviews

# Integrated with mining (default behavior)
python tool_coverage/scripts/fetch_fulltext_and_mine.py
```

⭐ **Smart Optimizations**:
- **Text Caching**: Fetched text cached during mining, reused in validation (50% fewer API calls)
- **Skip Logic**: Publications with existing validation YAMLs automatically skipped (85-90% cost savings)
- **Combined**: 80-85% reduction in API calls and costs for ongoing operations
- Use `--force-rereviews` to override skip logic when needed

**Example false positive caught:**
- Publication: "Development of pediatric quality of life inventory for NF1"
- Mined: "NF1 antibody", "NF1 genetic reagent"
- AI verdict: **Reject** - "Questionnaire development study, not lab research. NF1 refers to disease throughout."

#### `tool_coverage/scripts/clean_submission_csvs.py`
Prepares SUBMIT_*.csv files for Synapse upload (manual use only):
- **Removes tracking columns** (prefixed with '_') used for manual review
- **Saves cleaned versions** as CLEAN_*.csv files
- **Optionally uploads** cleaned data to Synapse tables via --upsert flag
- **Dry-run mode** (--dry-run) previews uploads without making changes
- Maps CSV files to appropriate Synapse table IDs automatically

⚠️ **Not part of automated workflow** - intended for manual use after reviewing mined tools

**Usage:**
```bash
# Clean only (default)
python tool_coverage/scripts/clean_submission_csvs.py

# Preview upload (no changes)
python tool_coverage/scripts/clean_submission_csvs.py --upsert --dry-run

# Clean and upload to Synapse
python tool_coverage/scripts/clean_submission_csvs.py --upsert
```

### 2. GitHub Actions Workflow

**File:** `.github/workflows/check-tool-coverage.yml`

**Schedule:** Weekly on Mondays at 9 AM UTC

**Manual Trigger:** Available via workflow dispatch with options:
- **AI Validation** (default: enabled) - Run Goose AI validation on mined tools
- **Max Publications** (default: all) - Limit number of publications to mine
- **Force Re-reviews** (default: disabled) - Force re-review of already-reviewed publications

**Steps:**
1. Checkout repository
2. Set up Python 3.11 with pip cache
3. Install dependencies from requirements.txt
4. Check for ANTHROPIC_API_KEY (skips validation if missing)
5. Install Goose CLI (if AI validation enabled and API key present)
6. Configure Goose with Anthropic API
7. Run coverage analysis
8. Mine publications for novel tools (with AI validation by default)
9. Format mining results into submission CSVs
10. Generate summary report
11. Upload all reports as artifacts including validation results (90-day retention)
12. **Create Pull Request** with result files for review

### 3. Synapse Upsert Workflow

**File:** `.github/workflows/upsert-tools.yml`

**Triggers:**
- Automatically when PR is merged to `main` branch with `VALIDATED_*.csv` or `SUBMIT_*.csv` files
- Manual trigger via workflow dispatch

**Steps:**
1. Checkout repository
2. Set up Python 3.11 with pip cache
3. Install dependencies from requirements.txt
4. Check for validated or submit CSV files
5. Clean submission files (remove tracking columns)
6. **Dry-run preview** of Synapse uploads (safety check)
7. **Upload cleaned data** to Synapse tables
8. Create upload summary with table links
9. Upload cleaned CSVs as artifacts (30-day retention)

**Safety Features:**
- Prefers `VALIDATED_*.csv` files (AI-validated, false positives removed)
- Falls back to `SUBMIT_*.csv` if validated files not present
- Runs dry-run before actual upload
- Skips if no CSV files found

**Synapse Tables Updated:**
- Animal Models: syn26486808
- Antibodies: syn26486811
- Cell Lines: syn26486823
- Genetic Reagents: syn26486832
- Resources (links): syn51730943

## Configuration

### Required Secrets

The workflow requires the following GitHub secrets to be configured:

1. **`SYNAPSE_AUTH_TOKEN`**
   - Personal access token for Synapse API
   - Used to query publications and tools databases
   - Generate at: https://www.synapse.org/#!PersonalAccessTokens:

2. **`ANTHROPIC_API_KEY`** ⭐ NEW
   - API key for Claude AI (used by Goose for tool validation)
   - Required for AI validation (enabled by default)
   - Generate at: https://console.anthropic.com/settings/keys
   - Cost: ~$0.01-0.03 per publication validated

3. **`NF_SERVICE_GIT_TOKEN`**
   - GitHub token with `contents: write` and `pull_requests: write` permissions
   - Used to create Pull Requests with mining results
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
python tool_coverage/scripts/analyze_missing_tools.py
```

### Run Full Text Mining

**With AI validation (recommended):**
```bash
# Requires Goose CLI and Anthropic API key
python tool_coverage/scripts/fetch_fulltext_and_mine.py

# Or test with limited publications
python tool_coverage/scripts/fetch_fulltext_and_mine.py --max-publications 10
```

**Setup for AI validation:**
```bash
# Install Goose CLI
go install github.com/block/goose@latest

# Configure with Anthropic API key
goose configure
# (Enter API key from https://console.anthropic.com/settings/keys)
```

**Without AI validation (faster, but may have false positives):**
```bash
python tool_coverage/scripts/fetch_fulltext_and_mine.py --no-validate
```

### Generate Summary
```bash
python tool_coverage/scripts/generate_coverage_summary.py > issue_body.md
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

### Pull Request

A weekly PR is created with:
- **Title:** `🔍 Tool Coverage Update - [run number]`
- **Labels:** `automated-mining`, `tool-coverage`
- **Description includes:**
  - Current coverage status
  - Novel tools discovered
  - Top priority publications to review
  - Summary of submission-ready CSVs
- **Files included:**
  - `VALIDATED_*.csv` or `SUBMIT_*.csv` - Submission files
  - `GFF_Tool_Coverage_Report.pdf` - Coverage analysis
  - `novel_tools_FULLTEXT_mining.csv` - All mining results
  - `priority_publications_FULLTEXT.csv` - Top publications
  - Other supporting files

**Workflow after PR creation:**
1. Review the mining results and validation reports
2. Verify tool mentions in publication full text
3. Remove any false positives
4. Complete missing metadata fields
5. **Merge PR** → Automatically triggers Synapse upsert workflow

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

## Next Steps After PR Creation

### 1. Review the Pull Request

Navigate to the created PR and review the changes:
- Check the PR description for coverage summary
- Download artifacts from the workflow run if needed
- Review `VALIDATED_*.csv` or `SUBMIT_*.csv` files in the PR
- Check `priority_publications_FULLTEXT.csv` for context
- Review PDF coverage reports

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

### 4. Merge the Pull Request

Once you've validated the results and completed any necessary edits:

**Merge the PR** → This automatically triggers the Synapse upsert workflow

**What happens automatically:**
1. The upsert workflow detects the CSV files
2. Cleans submission files (removes tracking columns)
3. Runs a dry-run preview of uploads
4. Uploads data to Synapse tables:
   - **Resources:** syn26450069
   - **Animal Models:** syn26486808
   - **Antibodies:** syn26486811
   - **Cell Lines:** syn26486823
   - **Genetic Reagents:** syn26486832
   - **Publication Links:** syn51735450
   - **Development:** syn26486807
5. Creates upload summary in GitHub Actions

**IMPORTANT:** The CSV files contain NEW ROWS only - they are **appended** to existing Synapse tables, not used as replacements.

### 5. Verify Upload Success

After merging:
- Check the `upsert-tools` workflow run in GitHub Actions
- Review the upload summary for any errors
- Verify row counts increased in Synapse tables

### 6. Track Progress

Monitor coverage percentage in the next weekly PR to see improvement toward the 80% target.

## Limitations

### Abstract and Full Text Availability
- **Abstracts:** Fetched from PubMed API - available for nearly all publications (>95%)
- **Full Text:** Only publications in PubMed Central (PMC) provide complete Methods and Introduction sections
- Closed-access articles can still be mined via abstracts but with less detail
- Typically ~30-50% of publications have PMC full text available for enhanced mining

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

## Output Files

Scripts currently write output files to the **repository root** (for GitHub Actions workflow compatibility). Generated files are gitignored and include:
- `novel_tools_FULLTEXT_mining.csv` - Mining results
- `SUBMIT_*.csv` - Unvalidated submission files
- `VALIDATED_*.csv` - AI-validated submission files (production-ready)
- `GFF_Tool_Coverage_Report.pdf` - Coverage analysis report
- `tool_reviews/` - AI validation results and cache

The `results/` folder in this directory is available for organizing outputs locally if desired.

