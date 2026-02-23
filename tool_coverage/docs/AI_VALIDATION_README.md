# AI-Powered Tool Validation with Claude Sonnet

## Overview

**AI validation runs as a separate step** in the tool mining workflow. This system uses the Claude Sonnet API directly (via the `anthropic` Python library) to automatically filter false positives like gene/disease names being misidentified as research tools, and to detect tools the mining step may have missed.

## Problem It Solves

**Example False Positive:**
- Publication: "Development of the pediatric quality of life inventory neurofibromatosis type 1 module"
- Mining system found: "NF1 antibody", "NF1 genetic reagent"
- Reality: This is a questionnaire development study, not lab research. All "NF1" mentions refer to the disease, not tools.

**AI validation provides:**
- **False Positive Filtering:** Catches disease/gene names misidentified as tools
- **Publication Type Analysis:** Distinguishes clinical studies from lab research
- **Keyword Checking:** Verifies tool-specific keywords near mentions
- **Missed Tool Detection:** Actively searches for tools mining didn't catch
- **Pattern Suggestions:** Recommends improvements to mining patterns
- **Observation Extraction:** Mines scientific observations from Results/Discussion sections (Phase 2)

## Architecture

```
Step 1: Mining
fetch_minimal_fulltext.py
    ↓ (fetches title + abstract + methods + metadata)
tool_reviews/publication_cache/{PMID}_text.json (Phase 1 cache)

Step 2: AI Validation (Phase 1)
run_publication_reviews.py
    ↓ (reads from Phase 1 cache, calls Claude Sonnet API directly)
    ↓ (skips already-reviewed publications)
Claude Sonnet API (system prompt from recipes/publication_tool_review.yaml)
    ↓ (generates per-publication validation)
{PMID}_tool_review.yaml
    ↓ (compiles all results)
VALIDATED_*.csv (filtered submission files)
potentially_missed_tools.csv (tools AI found)
suggested_patterns.csv (pattern recommendations)

Step 3: Selective Cache Upgrade (Phase 2)
upgrade_cache_for_observations.py
    ↓ (upgrades cache for high-confidence tools, confidence ≥0.8)
tool_reviews/publication_cache/{PMID}_text.json (Phase 2 cache, adds results + discussion)

Step 4: Observation Extraction (Phase 2)
run_publication_reviews.py --extract-observations
    ↓ (reads Phase 2 cache, calls Claude Sonnet API directly)
Claude Sonnet API (system prompt from recipes/publication_observation_extraction.yaml)
    ↓ (generates per-publication observations)
{PMID}_observations.yaml

Step 5: Automated Pattern Improvement
apply_pattern_suggestions.py
    ↓ (reads suggested patterns with confidence scores)
    ↓ (auto-adds patterns with >0.9 confidence)
    ↓ (generates report for 0.7-0.9 confidence)
tool_coverage/config/mining_patterns.json (updated)
PATTERN_IMPROVEMENTS.md (manual review report)
    ↓ (feedback loop: next mining run uses improved patterns)
```

**Key Optimizations**:
- 📦 **Text Caching**: Fetched text cached during Phase 1, reused in validation (50% fewer API calls)
- ⏭️ **Smart Skip**: Only validates new publications, skips already-reviewed (85-90% cost savings)
- 💰 **Combined**: 80-85% reduction in API calls and costs for ongoing operations
- 🔍 **Missed Tool Detection**: AI actively searches for tools mining didn't catch
- 📈 **Pattern Learning**: Suggests improvements based on missed tools

## Components

### 1. Recipe YAMLs (`tool_coverage/scripts/recipes/`)

Two YAML files define the AI agent's instructions, system prompt, and output format. They are loaded by Python and passed directly to the Anthropic API — not run by any external tool.

- **`publication_tool_review.yaml`** — Phase 1: tool validation
- **`publication_observation_extraction.yaml`** — Phase 2: observation extraction

**Key features of `publication_tool_review.yaml`:**
- Uses Claude Sonnet (temperature 0.0 for consistency)
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

potentiallyMissedTools:
  - toolName: "Anti-Neurofibromin antibody (clone D7R7D)"
    toolType: "antibody"
    foundIn: "methods"
    contextSnippet: "...stained with Anti-Neurofibromin antibody (clone D7R7D, Cell Signaling)..."
    whyMissed: "Specific clone name not in pattern database"
    confidence: 0.92
    shouldBeAdded: Yes

suggestedPatterns:
  - patternType: "vendor_indicator"
    pattern: "Cell Signaling #\\d+"
    toolType: "antibody"
    examples: ["Cell Signaling #9876"]
    reasoning: "Commonly used vendor catalog format for antibodies"

summary:
  potentiallyMissedCount: 1
  newPatternsCount: 1
```

### 2. Orchestrator (`run_publication_reviews.py`)

Python script that manages the validation workflow using direct Anthropic API calls:
- Loads Phase 1 cache files (`{PMID}_text.json`) for publication text
- **Automatically fetches candidate publications from Synapse**:
  - NF portal publications (syn16857542) not yet in tools table (syn26486839)
  - Tools publications (syn26486839) not linked to usage (syn26486841) or development (syn26486807)
- Calls Claude Sonnet API directly (4 parallel workers in production)
- Parses validation YAMLs
- Filters VALIDATED_*.csv files to remove rejected tools
- Extracts potentially missed tools and pattern suggestions
- Generates validation reports

**Usage:**
```bash
# Validate mined + candidate publications (includes Synapse candidates automatically)
python tool_coverage/scripts/run_publication_reviews.py --mining-file processed_publications.csv

# Validate specific publications
python tool_coverage/scripts/run_publication_reviews.py --pmids "PMID:28078640,PMID:29415745"

# Validate publications listed in a file (one PMID per line)
python tool_coverage/scripts/run_publication_reviews.py --pmids-file phase2_upgraded_pmids.txt

# Force re-review of already-reviewed publications
python tool_coverage/scripts/run_publication_reviews.py --mining-file processed_publications.csv --force-rereviews

# Phase 2: extract observations for high-confidence tools
python tool_coverage/scripts/run_publication_reviews.py --mining-file processed_publications.csv --extract-observations

# Compile results from existing YAMLs only (no API calls)
python tool_coverage/scripts/run_publication_reviews.py --compile-only

# Alias for --compile-only (legacy flag)
python tool_coverage/scripts/run_publication_reviews.py --skip-goose
```

**Candidate Publication Sources** (fetched automatically):
1. **NF Portal → Tools Table Gap**: Publications in NF portal (syn16857542) not yet in tools publications table (syn26486839)
2. **Unlinked Tools Publications**: Publications in tools table (syn26486839) without any tool links in usage (syn26486841) or development (syn26486807)

These publications are reviewed to discover potential new tools or confirm they don't contain relevant tools. No Synapse authentication required (tables are open access).

**Outputs:**
- `VALIDATED_*.csv` - Filtered submission files (rejected tools removed)
- `tool_reviews/validation_report.xlsx` - Summary report (includes observation counts)
- `tool_reviews/validation_summary.json` - Machine-readable results
- `tool_reviews/potentially_missed_tools.csv` - Tools AI found that mining missed
- `tool_reviews/suggested_patterns.csv` - Pattern recommendations
- `tool_reviews/results/{PMID}_tool_review.yaml` - Per-publication validation details
- `tool_reviews/results/{PMID}_observations.yaml` - Per-publication observations (Phase 2)

**Smart Optimizations:**

**Publication Text Caching:**
- Phase 1 cache (`{PMID}_text.json`) contains title, abstract, methods, and metadata
- Phase 2 cache additionally includes results and discussion sections
- Validation reads from cache instead of re-fetching from PubMed/PMC APIs
- **Eliminates duplicate API calls**: 50% reduction (100 vs 200 for 50 publications)
- Cache persists across runs, enabling fast re-validation
- Backwards compatible: falls back to API if cache missing

**Review Skip Logic:**
- Publications with existing `{PMID}_tool_review.yaml` files are **automatically skipped**
- Use `--force-rereviews` flag to override and re-review all publications
- Allows incremental validation of new publications without re-processing old ones
- **85-90% cost savings** on subsequent runs

**Combined Impact:**
- Week 1: 100 API calls + 50 AI reviews = $0.50-1.50
- Week 2: 10 API calls + 5 AI reviews = $0.05-0.15 (skip 45)
- **Monthly savings**: 80-85% reduction in costs

### 3. Pattern Improvement Script (`apply_pattern_suggestions.py`)

Automatically applies high-confidence pattern suggestions from AI validation, creating a feedback loop that continuously improves mining accuracy.

**Features:**
- **Auto-add high confidence patterns** (>0.9): Directly updates `mining_patterns.json`
- **Generate manual review report** (0.7-0.9): Creates `PATTERN_IMPROVEMENTS.md` for human review
- **Ignore low confidence** (<0.7): Filters out unreliable suggestions
- **Audit trail**: Tracks all AI-added patterns with reasoning and confidence scores

**Pattern Categories:**
```json
{
  "antibodies": {
    "vendor_indicators": ["Abcam ab\\d+", "Cell Signaling #\\d+"],
    "context_phrases": ["antibody.*purchased from"]
  },
  "cell_lines": {
    "naming_conventions": ["[A-Z]{2,4}[0-9]{2,3}"],
    "context_phrases": ["cells were cultured"]
  },
  "animal_models": {
    "strain_nomenclature": ["C57BL/6", "Nf1\\+/-"],
    "context_phrases": ["knockout mice"]
  },
  "genetic_reagents": {
    "vector_indicators": ["pCMV-", "AAV-"],
    "context_phrases": ["transfected with"]
  }
}
```

**Usage:**
```bash
# Apply pattern improvements
python tool_coverage/scripts/apply_pattern_suggestions.py

# Preview without modifying files
python tool_coverage/scripts/apply_pattern_suggestions.py --dry-run
```

**Audit Trail:**

All AI-added patterns are tracked in `mining_patterns.json`:
```json
{
  "ai_suggested_patterns": {
    "comment": "Patterns automatically added by AI validation with confidence >0.9",
    "additions": [
      {
        "category": "antibodies",
        "section": "vendor_indicators",
        "pattern": "ThermoFisher \\\\d+",
        "reasoning": "Common vendor catalog number format",
        "confidence": 0.92,
        "added_date": "2026-01-28"
      }
    ]
  }
}
```

**Integration:**

Pattern improvement runs automatically after AI validation in GitHub Actions workflow, creating a continuous improvement cycle:
1. Mining extracts tools using current patterns
2. AI validation identifies missed tools and suggests new patterns
3. High-confidence patterns auto-added, medium-confidence exported to report
4. Updated patterns committed to PR
5. Next mining run benefits from improved patterns

### 4. Observation Extraction

AI validation also extracts **scientific observations** about tools from Results and Discussion sections of publications (Phase 2).

**What Are Observations?**

Observations are scientific characterizations of research tools stored in syn26486836:
- Phenotypic data (body weight, coat color, growth rate)
- Behavioral observations (motor activity, social behavior)
- Disease characteristics (tumor growth, disease susceptibility)
- Usage notes (best practices, issues, cross-reactivity)

**Observation Types (20 categories from schema):**

| Category | Types |
|----------|-------|
| **Phenotypic** | Body Length, Body Weight, Coat Color, Organ Development |
| **Growth/Metabolic** | Growth Rate, Lifespan, Feed Intake, Feeding Behavior |
| **Behavioral** | Motor Activity, Swimming Behavior, Social Behavior, Reproductive Behavior, Reflex Development |
| **Disease** | Disease Susceptibility, Tumor Growth |
| **Practical** | Usage Instructions, Issue, Depositor Comment, General Comment or Review, Other |

**Extraction Process:**

1. **Phase 2 cache upgrade**: `upgrade_cache_for_observations.py` selectively fetches Results + Discussion for high-confidence publications (confidence ≥0.8)
2. **AI reads Results/Discussion sections** from upgraded cache
3. **Identifies scientific findings** about validated tools
4. **Categorizes by observation type** (20 types from schema)
5. **Links to tool** via resourceName
6. **Includes quantitative data** when available
7. **Outputs to `*_observations.yaml`** alongside tool review YAMLs

**Example Output (`{PMID}_observations.yaml`):**

```yaml
observations:
  - resourceName: "Nf1+/-"
    resourceType: "Animal Model"
    observationType: "Body Weight"
    details: "Nf1+/- mice showed 15% reduced body weight at 8 weeks (p<0.01)"
    foundIn: "results"
    contextSnippet: "...relevant excerpt..."
    confidence: 0.95
    doi: "10.1234/journal.2023.001"
```

**Impact on Tool Completeness:**

Observations contribute **25 points** (25%) to tool completeness scoring:
- Observations with DOI: 7.5 points each (up to 4)
- Observations without DOI: 2.5 points each (up to 10)
- Maximum: 25 points from observations

## Setup Requirements

### 1. Configure Anthropic API Key

The validation script uses the Anthropic Python SDK directly:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

Get API key from: https://console.anthropic.com/settings/keys

### 2. Install Python Dependencies

Already included in `requirements.txt`:
```
anthropic>=0.39.0
synapseclient>=4.4.0
pandas>=2.0.0
pyyaml>=6.0
```

## Workflow

### Step 1: Run Phase 1 Cache Fetch

```bash
python tool_coverage/scripts/fetch_minimal_fulltext.py \
  --pmids-file tool_coverage/outputs/screened_publications.csv \
  --output-dir tool_reviews/publication_cache
```

### Step 2: Run AI Validation

```bash
# With 4 parallel workers (recommended for large sets)
export ANTHROPIC_API_KEY="your-key"
python tool_coverage/scripts/run_publication_reviews.py \
  --mining-file tool_coverage/outputs/processed_publications.csv \
  --parallel-workers 4
```

**Generates:**
- `tool_reviews/results/{PMID}_tool_review.yaml` - Per-publication reviews
- `tool_reviews/validation_summary.json` - JSON summary
- `tool_reviews/validation_report.xlsx` - Excel report
- `VALIDATED_*.csv` - Validated submission files (false positives removed) ⭐ **USE THESE**

### Step 3: Run Phase 2 (Observation Extraction)

```bash
# First upgrade the cache for high-confidence tools
python tool_coverage/scripts/upgrade_cache_for_observations.py \
  --reviews-dir tool_reviews/results \
  --cache-dir tool_reviews/publication_cache

# Then extract observations
python tool_coverage/scripts/run_publication_reviews.py \
  --mining-file tool_coverage/outputs/processed_publications.csv \
  --pmids-file tool_coverage/outputs/phase2_upgraded_pmids.txt \
  --extract-observations \
  --parallel-workers 4
```

**Generates:**
- `tool_reviews/results/{PMID}_observations.yaml` - Per-publication observations

### Step 4: Review Results

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

### Step 5: Manual Review (if needed)

For tools with `verdict: "Uncertain"` or `recommendation: "Manual Review Required"`:

1. Read the YAML file: `tool_reviews/results/{PMID}_tool_review.yaml`
2. Review the `reasoning` and `contextSnippet` fields
3. Manually accept or reject in the CSV

## Output Files

### Validation YAMLs
**Location:** `tool_reviews/results/{PMID}_tool_review.yaml`

Contains detailed validation for each tool with reasoning and recommendations.

### Observation YAMLs
**Location:** `tool_reviews/results/{PMID}_observations.yaml`

Contains scientific observations extracted from Results/Discussion sections (Phase 2 only).

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

**Speed (Initial Run):**
- ~20-60 seconds per publication (direct API call)
- With 4 parallel workers: ~5-20 seconds effective per publication
- For 50 publications: ~5-15 minutes (vs 25-50 minutes with serial processing)

**Speed (Subsequent Runs with Optimizations):**
- Text caching: No API fetch latency (~5 seconds saved per pub)
- Skip logic: Only processes new publications
- For 5 new publications: ~1-5 minutes

**Cost Analysis:**

*Initial Run (50 publications):*
- Phase 1 cache fetch: ~50 API calls
- AI validations: 50
- Total cost: ~$0.50-1.50

*Subsequent Weekly Runs (5 new publications):*
- Phase 1 cache fetch: ~5 API calls
- AI validations: 5 (with skip logic)
- Total cost: ~$0.05-0.15

**Monthly Savings**: 80-85% reduction vs without optimizations

## Customization

### Adjust Validation Strictness

Edit `tool_coverage/scripts/recipes/publication_tool_review.yaml`:

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
export ANTHROPIC_API_KEY="your-key"
```

### Validation too strict/lenient

**Adjust in recipe:**
- Modify `confidence` thresholds
- Change `verdict` criteria
- Update tool keyword lists

### No YAML files generated

**Possible causes:**
1. ANTHROPIC_API_KEY not set
2. Recipe file path incorrect
3. Cache file malformed or missing

**Debug:**
```bash
# Check API key is set
echo $ANTHROPIC_API_KEY

# Check cache file exists for PMID
ls tool_reviews/publication_cache/PMID_28078640_text.json

# Run with a single PMID for targeted debugging
python tool_coverage/scripts/run_publication_reviews.py --pmids "PMID:28078640"
```

## GitHub Actions Integration

**AI validation is integrated into the workflow and enabled by default.**

The workflow includes manual trigger options:
- **AI Validation** (default: enabled) - Toggle AI validation on/off via `ai_validation` input
- **Max Publications** (default: all) - Limit publications via `max_publications` input
- **Force Re-reviews** (default: disabled) - Force re-review via `force_rereviews` input
- **Max Reviews** (default: auto) - Cap Sonnet reviews via `max_reviews` input

**Required GitHub secret:**
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude access (https://console.anthropic.com/settings/keys)

**Workflow automatically:**
1. Checks for `ANTHROPIC_API_KEY` (skips AI validation if missing)
2. Runs Phase 1 validation with 4 parallel workers
3. Runs Phase 2 cache upgrade and observation extraction for high-confidence tools
4. Uploads validation artifacts: `VALIDATED_*.csv`, validation reports, review YAMLs

**To disable AI validation manually:**
- Go to Actions → Check Tool Coverage → Run workflow
- Set `ai_validation` to `false`
- Click "Run workflow"

## Best Practices

1. **Always review uncertain tools manually** - These need human judgment
2. **Check validation report first** - Identifies systemic issues
3. **Spot-check accepted tools** - Verify AI isn't being too lenient
4. **Keep recipes updated** - Add patterns as you find new false positive types
5. **Monitor API costs** - Set budget alerts in Anthropic console
6. **Version control YAMLs** - Git track validation results for audit trail

## Future Enhancements

Potential improvements:
- [ ] Confidence threshold tuning based on validation accuracy
- [ ] Custom MCP tools for fetching publication text (avoid API delays)
- [ ] Integration with PubMed metadata for journal quality signals
- [x] Automated pattern learning from missed tools (IMPLEMENTED - see Pattern Improvement Script)
- [ ] Batch validation mode for large publication sets
- [ ] Learning from manual corrections to further refine patterns

## Support

For issues:
1. Check `tool_reviews/results/{PMID}_tool_review.yaml` for detailed reasoning
2. Check `ANTHROPIC_API_KEY` is set and valid
3. Validate Phase 1 cache files exist in `tool_reviews/publication_cache/`
4. Check Anthropic API usage/limits at https://console.anthropic.com/

## References

- Anthropic API docs: https://docs.anthropic.com/
- Project issue: https://github.com/nf-osi/nf-research-tools-schema/issues/97
