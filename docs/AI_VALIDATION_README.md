# AI-Powered Tool Validation with Goose (Enabled by Default)

## Overview

**AI validation is now enabled by default** in the tool mining workflow. This system uses Goose AI agent to automatically filter false positives like gene/disease names being misidentified as research tools, dramatically improving precision.

## Problem It Solves

**Example False Positive:**
- Publication: "Development of the pediatric quality of life inventory neurofibromatosis type 1 module"
- Mining system found: "NF1 antibody", "NF1 genetic reagent"
- Reality: This is a questionnaire development study, not lab research. All "NF1" mentions refer to the disease, not tools.

**AI validation catches these issues by:**
- Analyzing publication type (clinical study vs lab research)
- Checking for tool-specific keywords near mentions (antibody, plasmid, cell line, etc.)
- Distinguishing disease/gene references from actual research tools
- Verifying Methods sections exist indicating experimental work

## Architecture

```
fetch_fulltext_and_mine.py
    ↓ (mines tools)
novel_tools_FULLTEXT_mining.csv
    ↓ (AI_VALIDATE_TOOLS=true)
run_publication_reviews.py
    ↓ (invokes)
Goose AI Agent (recipes/publication_tool_review.yaml)
    ↓ (generates)
{PMID}_tool_review.yaml (per publication)
    ↓ (compiles)
VALIDATED_*.csv (filtered submission files)
```

## Components

### 1. Goose Recipe (`recipes/publication_tool_review.yaml`)

Defines the AI agent's task, instructions, and output format.

**Key features:**
- Uses Claude Sonnet 4 (temperature 0.0 for consistency)
- Analyzes publication type, Methods sections, tool keywords
- Generates structured YAML with Accept/Reject/Uncertain verdicts
- Provides detailed reasoning for every decision

**Output structure:**
```yaml
publicationMetadata:
  pmid: "PMID:28078640"
  publicationType: "Questionnaire/Survey Development"
  likelyContainsTools: No

toolValidations:
  - toolName: "NF1"
    toolType: "antibody"
    verdict: "Reject"
    confidence: 0.95
    reasoning: |
      This publication is questionnaire development, not lab research.
      NF1 refers to disease name throughout, never mentioned with tool keywords.
    recommendation: "Remove"
```

### 2. Orchestrator (`run_publication_reviews.py`)

Python script that manages the validation workflow:
- Loads mining results CSV
- Fetches abstracts and full text for each publication
- Prepares input JSON files for Goose
- Invokes Goose AI agent for each publication
- Parses validation YAMLs
- Filters SUBMIT_*.csv files to remove rejected tools
- Generates validation reports

**Usage:**
```bash
# Validate specific publications
python run_publication_reviews.py --pmids "PMID:28078640,PMID:29415745"

# Validate all mined publications (skips already-reviewed)
python run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv

# Force re-review of already-reviewed publications
python run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv --force-rereviews

# Compile results from existing YAMLs (skip goose reviews)
python run_publication_reviews.py --compile-only

# Skip goose, just filter CSVs from existing YAMLs
python run_publication_reviews.py --skip-goose
```

**Smart Skip Logic:**
- By default, publications with existing `{PMID}_tool_review.yaml` files are **automatically skipped** to save time and API costs
- Use `--force-rereviews` flag to override and re-review all publications
- This allows incremental validation of new publications without re-processing old ones

### 3. Integration with Mining Workflow

AI validation is integrated into `fetch_fulltext_and_mine.py` via environment variable:

```bash
# Run mining WITH AI validation
AI_VALIDATE_TOOLS=true python fetch_fulltext_and_mine.py

# Run mining WITHOUT AI validation (default)
python fetch_fulltext_and_mine.py
```

When enabled, validation runs automatically after mining completes.

## Setup Requirements

### 1. Install Goose CLI

```bash
# Install via block/goose (requires Go 1.20+)
go install github.com/block/goose@latest

# Or via Homebrew (macOS)
brew install block/tap/goose
```

Verify installation:
```bash
goose --version
```

### 2. Configure Anthropic API Key

Goose requires an Anthropic API key to use Claude models:

```bash
# Configure interactively
goose configure

# Or set environment variable
export ANTHROPIC_API_KEY="your-api-key-here"
```

Get API key from: https://console.anthropic.com/settings/keys

### 3. Install Python Dependencies

Already included in `requirements.txt`:
```
synapseclient>=4.4.0
pandas>=2.0.0
pyyaml>=6.0
```

## Workflow

### Step 1: Run Mining (AI Validation Enabled by Default)

```bash
# With AI validation (default)
python fetch_fulltext_and_mine.py

# Without AI validation (faster, but may have false positives)
python fetch_fulltext_and_mine.py --no-validate

# Standalone validation (if you already have mining results)
python run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv
```

**Generates:**
- `novel_tools_FULLTEXT_mining.csv` - All mined tools
- `tool_reviews/results/{PMID}_tool_review.yaml` - Per-publication reviews (if validation enabled)
- `tool_reviews/validation_summary.json` - JSON summary (if validation enabled)
- `tool_reviews/validation_report.xlsx` - Excel report (if validation enabled)
- `SUBMIT_*.csv` - Unvalidated submission files
- `VALIDATED_*.csv` - Validated submission files (false positives removed) ⭐ **USE THESE**

### Step 2: Review Results

**Check validation report:**
```bash
open tool_reviews/validation_report.xlsx
```

Columns:
- `totalMined`: Tools found by mining
- `accepted`: Tools validated as genuine
- `rejected`: False positives removed
- `uncertain`: Need manual review
- `publicationType`: Lab Research, Clinical Study, etc.
- `majorIssues`: Problems found
- `recommendations`: Next steps

**Check validated CSVs:**
```bash
ls VALIDATED_*.csv
```

Use these instead of `SUBMIT_*.csv` for Synapse upload.

### Step 3: Manual Review (if needed)

For tools with `verdict: "Uncertain"` or `recommendation: "Manual Review Required"`:

1. Read the YAML file: `tool_reviews/results/{PMID}_tool_review.yaml`
2. Review the `reasoning` and `contextSnippet` fields
3. Manually accept or reject in the CSV

## Output Files

### Validation YAMLs
**Location:** `tool_reviews/results/{PMID}_tool_review.yaml`

Contains detailed validation for each tool with reasoning and recommendations.

### Validation Report
**Location:** `tool_reviews/validation_report.xlsx`

Summary spreadsheet showing:
- Publication type analysis
- Tools accepted/rejected/uncertain
- Major issues identified
- Recommendations

### Validated CSVs
**Location:** `VALIDATED_*.csv`

Filtered versions of `SUBMIT_*.csv` with rejected tools removed:
- `VALIDATED_SUBMIT_antibodies.csv`
- `VALIDATED_SUBMIT_cell_lines.csv`
- `VALIDATED_SUBMIT_animal_models.csv`
- `VALIDATED_SUBMIT_genetic_reagents.csv`
- `VALIDATED_SUBMIT_resources.csv`

### Input Files (for debugging)
**Location:** `tool_reviews/inputs/{PMID}_input.json`

JSON files containing publication text and mined tools fed to Goose.

## Expected Results

Based on the false positive example (PMID:28078640):

**Before AI Validation:**
- 2 publications with tools
- 4 tools found (2 antibodies, 2 genetic reagents)
- All are false positives (NF1/NF2 disease references)

**After AI Validation:**
- 2 publications analyzed
- 0 tools accepted
- 4 tools rejected
- Reason: "Questionnaire development study, not lab research. NF1 refers to disease throughout."

**Impact:**
- **Precision improvement:** 0% → Can't calculate (0 true positives in sample)
- **False positive reduction:** 100% (4/4 false positives caught)
- **Manual review savings:** 100% (no manual review needed for obvious rejections)

## Performance

**Speed:**
- ~30-60 seconds per publication (depending on text length)
- Processes publications serially (for API rate limits)
- For 50 publications: ~25-50 minutes

**Cost (Anthropic API):**
- Claude Sonnet 4: ~$0.01-0.03 per publication
- 50 publications: ~$0.50-$1.50
- Much cheaper than manual curator time

## Customization

### Adjust Validation Strictness

Edit `recipes/publication_tool_review.yaml`:

```yaml
# Make more strict (fewer false positives, more manual review)
- confidence: 0.9  # Increase from 0.0-1.0

# Make more lenient (more false positives, less manual review)
- confidence: 0.5  # Decrease threshold
```

### Add Custom Publication Types

Add to the `publicationType` enum in recipe:

```yaml
publicationType: "Lab Research" | "Clinical Study" | "Review Article" | "Questionnaire/Survey Development" | "Epidemiological Study" | "Your Custom Type"
```

### Modify Tool Keyword List

Edit the "ACCEPT ONLY IF" section in recipe to add/remove keywords:

```yaml
- Clear tool-specific context (e.g., "NF1 antibody", "NF1-deficient cell line", "NF1 knockout mice", "NF1 shRNA vector")
```

## Troubleshooting

### Error: "ANTHROPIC_API_KEY not found"

**Solution:**
```bash
goose configure
# Or
export ANTHROPIC_API_KEY="your-key"
```

### Error: "goose command not found"

**Solution:**
```bash
# Install goose
go install github.com/block/goose@latest

# Add to PATH
export PATH=$PATH:$(go env GOPATH)/bin
```

### Goose hangs or times out

**Solution:**
- Check internet connection
- Verify API key is valid
- Check Anthropic API status: https://status.anthropic.com/
- Increase timeout in `run_publication_reviews.py` (line 164): `timeout=1200  # 20 minutes`

### No YAML files generated

**Possible causes:**
1. Goose error (check stderr output)
2. Recipe file path incorrect
3. Input JSON malformed

**Debug:**
```bash
# Test recipe directly
cd tool_reviews/results
goose run --recipe ../../recipes/publication_tool_review.yaml \
  --params pmid=PMID:28078640 \
  --params inputFile=/full/path/to/input.json
```

### Validation too strict/lenient

**Adjust in recipe:**
- Modify `confidence` thresholds
- Change `verdict` criteria
- Update tool keyword lists

## GitHub Actions Integration

**AI validation is now integrated into the workflow and enabled by default.**

The workflow includes manual trigger options:
- **AI Validation** (default: enabled) - Toggle AI validation on/off
- **Max Publications** (default: all) - Limit publications for testing

**Required GitHub secret:**
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude access (https://console.anthropic.com/settings/keys)

**Workflow automatically:**
1. Installs Goose CLI (if validation enabled)
2. Configures with `ANTHROPIC_API_KEY`
3. Runs mining with `--no-validate` flag only if disabled
4. Uploads validation artifacts: `VALIDATED_*.csv`, validation reports, review YAMLs

**To disable AI validation manually:**
- Go to Actions → Check Tool Coverage → Run workflow
- Uncheck "Run AI validation"
- Click "Run workflow"

## Best Practices

1. **Always review uncertain tools manually** - These need human judgment
2. **Check validation report first** - Identifies systemic issues
3. **Spot-check accepted tools** - Verify AI isn't being too lenient
4. **Keep recipe updated** - Add patterns as you find new false positive types
5. **Monitor API costs** - Set budget alerts in Anthropic console
6. **Version control YAMLs** - Git track validation results for audit trail

## Future Enhancements

Potential improvements:
- [ ] Parallel processing (with rate limit management)
- [ ] Confidence threshold tuning based on validation accuracy
- [ ] Custom MCP tools for fetching publication text (avoid API delays)
- [ ] Integration with PubMed metadata for journal quality signals
- [ ] Learning from manual corrections to improve recipe
- [ ] Batch validation mode for large publication sets

## Support

For issues:
1. Check `tool_reviews/results/{PMID}_tool_review.yaml` for detailed reasoning
2. Review Goose logs for errors
3. Validate input JSON files are correctly formatted
4. Check Anthropic API usage/limits

## References

- Goose documentation: https://block.github.io/goose/
- Anthropic API docs: https://docs.anthropic.com/
- MCP protocol: https://modelcontextprotocol.io/
- Project reviews (inspiration): `/Users/bgarana/Documents/GitHub/dcc-site/docs/PROJECT_REVIEWS_README.md`
