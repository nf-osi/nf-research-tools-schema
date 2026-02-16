# Tool Coverage Monitoring Workflow

## Overview

This repository includes an automated workflow to monitor tool coverage in the NF research tools database and suggest novel tools to add from publications. The workflow supports **9 resource types** across different publication categories using tool-type-specific mining strategies.

## Supported Tool Types

**Established Types (v1.0) - Lab Research:**
- 🔬 **Antibodies** - Immunological reagents
- 🧫 **Cell Lines** - Immortalized cell cultures
- 🐭 **Animal Models** - Genetically modified organisms
- 🧬 **Genetic Reagents** - Plasmids, constructs, CRISPR
- 🏦 **Biobanks** - Biological sample collections

**New Types (v2.0) - Expanded Coverage:**
- 💻 **Computational Tools** - Software, pipelines, analysis tools (50+ known tools)
- 🧪 **Advanced Cellular Models** - Organoids, assembloids, 3D cultures
- 🐁 **Patient-Derived Models** - PDX, xenografts, humanized systems
- 📋 **Clinical Assessment Tools** - Questionnaires, scales, PROMs (SF-36, PROMIS, PedsQL)

## Multi-Query Mining Strategy

The system uses **tool-type-specific PubMed queries** to maximize discovery across different publication types. **Both bench and clinical queries run in EVERY workflow execution** to ensure comprehensive coverage of all 9 tool types.

### How It Works

1. **Workflow runs TWO queries in parallel:**
   - Bench science query (lab tools, computational, organoids, PDX)
   - Clinical assessment query (questionnaires, scales, outcome measures)

2. **Publications are merged by PMID:**
   - Each publication gets `query_type` tag: "bench", "clinical", or "bench,clinical"
   - Publications found by both queries have both tags merged

3. **ALL publications are mined for ALL 9 tool types:**
   - query_type serves as hint for AI validation
   - But every publication is scanned for all tool categories
   - Publications can contain multiple tool types

4. **Result: Complete coverage in single workflow run**
   - No separate runs needed
   - Expected: 69-83 tools/month (vs 18 with old system)

### Query Details

**1. Bench Science Query**
- **Targets:** Computational tools, PDX models, organoids, antibodies, cell lines, genetic reagents
- **Excludes:** Pure clinical case reports, clinical trials without lab methods
- **Papers:** ~1000/month from NF Portal + PubMed
- **Use case:** Laboratory research publications with Methods sections

**2. Clinical Assessment Query**
- **Targets:** Clinical assessment tools (SF-36, PROMIS, PedsQL, VAS, outcome measures)
- **Includes:** Quality of life, questionnaires, patient-reported outcomes
- **Publication types:** Clinical Trial, Observational Study, Clinical Research
- **Papers:** ~150/month from NF Portal + PubMed
- **Use case:** Clinical studies, patient outcome research
- **Note:** Clinical tools accepted even WITHOUT traditional Methods sections

**3. Organoid Focused Query (Optional, not in automated workflow)**
- **Targets:** Advanced cellular models (organoids, assembloids, 3D cultures)
- **Includes:** Organoid-specific terminology, 3D culture systems
- **Use case:** Manual/ad-hoc targeted search if bench query proves insufficient

### Query Selection

```bash
# Default: Bench science query (computational, PDX, organoids, lab tools)
python prepare_publication_list.py

# Clinical assessment query (questionnaires, QoL measures)
python prepare_publication_list.py --query-type clinical

# Organoid focused query (3D cellular models)
python prepare_publication_list.py --query-type organoid

# Test mode (sample)
python prepare_publication_list.py --query-type clinical --test-sample 50
```

**📚 See [`MULTI_QUERY_IMPLEMENTATION.md`](MULTI_QUERY_IMPLEMENTATION.md) for complete architecture and deployment details.**

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

#### `tool_coverage/scripts/screen_publication_titles.py`
Pre-screens publication titles using Claude 3.5 Haiku to identify research publications:
- **Purpose:** Filter out clinical case reports, reviews, and non-research publications
- **Model:** Claude 3.5 Haiku (batch processing, ~100 titles per API call)
- **Cost:** ~$0.001 per batch of 100 titles
- **Caching:** Results cached to avoid re-screening

**Screening Criteria:**
- **INCLUDE:** Lab research, computational analysis, model systems, clinical tools, experimental methods
- **EXCLUDE:** Pure case reports, surgical procedures, epidemiology without tools, reviews/editorials

**Usage:**
```bash
python tool_coverage/scripts/screen_publication_titles.py
python tool_coverage/scripts/screen_publication_titles.py --max-publications 100
```

**Outputs:**
- `screened_publications.csv` - Research publications passing screening
- `title_screening_cache.csv` - Cached screening results
- `title_screening_detailed_report.csv` - Full report with verdicts

#### `tool_coverage/scripts/screen_publication_abstracts.py`
Screens publication abstracts using Claude 3.5 Haiku for NF tool usage or development:
- **Purpose:** Second-stage filtering after title screening to identify publications with NF tools
- **Model:** Claude 3.5 Haiku (batch processing, ~50 abstracts per API call)
- **Cost:** ~$0.002 per batch of 50 abstracts (abstracts longer than titles)
- **Abstract availability:** Ensures abstracts are available before screening
  - First checks Synapse table for abstracts
  - Falls back to PubMed API if not available
  - Excludes publications without abstracts

**Screening for 9 Tool Categories:**
1. Antibodies - immunological reagents
2. Cell lines - established cultures
3. Animal models - transgenic/knockout organisms
4. Genetic reagents - plasmids, CRISPR constructs
5. Biobanks - tissue repositories
6. Computational tools - software, pipelines
7. Organoids/3D models - advanced cellular systems
8. Patient-derived xenografts (PDX) - patient tissue models
9. Clinical assessment tools - questionnaires, scales (SF-36, PROMIS, PedsQL)

**Screening Criteria:**
- **INCLUDE:** Using/developing any of the 9 tool types, experimental methods with tools
- **EXCLUDE:** Purely observational studies, reviews/meta-analyses, clinical cases without research tools

**Usage:**
```bash
python tool_coverage/scripts/screen_publication_abstracts.py
python tool_coverage/scripts/screen_publication_abstracts.py --max-publications 100
python tool_coverage/scripts/screen_publication_abstracts.py --batch-size 50
```

**Outputs:**
- `abstract_screened_publications.csv` - Publications with NF tools
- `abstract_screening_cache.csv` - Cached screening results
- `abstract_screening_detailed_report.csv` - Full report with verdicts

**Domain Knowledge Integration:**

The script loads `config/ai_screening_knowledge.json` containing domain knowledge from tool mining logic:

- **175 known computational tools** across 8 categories (statistics/graphing, image analysis, sequencing, etc.)
  - Examples: GraphPad Prism, ImageJ, STAR, DESeq2, Seurat, FlowJo, Cytoscape
  - Distinguishes established tools from novel tool development

- **113 excluded false positives**
  - Programming languages (R, Python, Java, C++) - not tools themselves
  - IDEs/environments (RStudio, Jupyter, PyCharm) - not research tools
  - Generic terms ("software", "tool", "pipeline" without specific names)

- **NF-specific animal models and aliases**
  - Include: Nf1+/-, Nf1-/-, Nf2+/-, Nf2-/- and variants (heterozygous Nf1, Nf1 knockout, etc.)
  - Exclude: Generic strains (C57BL/6, BALB/c, nude mice) unless combined with NF mutation

- **Novel tool indicators**
  - Tool name in publication title + development language ("novel", "new", "introduces")
  - Context patterns ("we developed", "we created", "we designed")

**Screening Improvements:**

| Scenario | Before | After |
|----------|--------|-------|
| Programming language | "Analysis using R" → INCLUDE ❌ | → EXCLUDE ✅ |
| Novel vs established | "ImageJ analysis" → novel ❌ | → established tool ✅ |
| Novel tool in title | "TumorTracker: novel plugin" → maybe | → novel tool ✅ |
| Generic strain | "C57BL/6 mice" → INCLUDE ❌ | → EXCLUDE ✅ |
| NF-specific model | "C57BL/6 Nf1+/- mice" → maybe | → INCLUDE ✅ |

**Benefits:**
- 🎯 **Better targeting:** Filters publications before expensive full-text extraction
- 💰 **Cost efficient:** Cheap Haiku screening saves Sonnet tokens later
- ⚡ **Faster workflow:** Skip publications without tool evidence
- 📊 **Higher precision:** Two-stage filtering (title → abstract) improves accuracy
- 🧠 **Smarter screening:** Uses domain knowledge to reduce false positives

#### `tool_coverage/scripts/mine_publications_improved.py`
Extracts publication sections for AI review (tool mining disabled by default):

**Section Extraction Mode (Default)**
- **Primary purpose:** Extract all publication sections for later Sonnet review
- **Tool mining disabled** by default (can be re-enabled with `--enable-tool-mining`)
- **Focus on quality:** Haiku pre-filters publications, Sonnet reviews full text

**Section Extraction Pipeline:**
1. **Fetch abstracts** (from Synapse table or PubMed API)
2. **Fetch full text** from PubMed Central (PMC) when available
3. **Extract all sections:**
   - Abstract
   - Introduction
   - Methods
   - Results
   - Discussion
4. **Cache extracted text** for Sonnet review (publication_cache/)
5. **Track section lengths** in output CSV

**Optional: Tool Mining Mode** (use `--enable-tool-mining` flag)
- Performs pattern-based tool mining from abstract + methods sections
- Uses exact matching (case-insensitive) with synonyms
- Distinguishes development vs usage contexts
- Filters generic commercial tools unless NF-specific
- Matches against existing database tools (1,700+ synonyms)

**Command-line options:**
```bash
# Extract sections only (default, recommended)
python tool_coverage/scripts/mine_publications_improved.py

# Extract sections with tool mining enabled
python tool_coverage/scripts/mine_publications_improved.py --enable-tool-mining

# Limit publications for testing
python tool_coverage/scripts/mine_publications_improved.py --max-publications 10
```

**Outputs:**
- `processed_publications_improved.csv` - Section lengths and optional tool mining results
  - Columns: pmid, title, abstract_length, intro_length, methods_length, results_length, discussion_length
  - Optional (if mining enabled): existing_tools, novel_tools, tool_metadata, tool_sources
- `tool_reviews/publication_cache/{PMID}_text.json` - Cached text with all 5 sections

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
- **Matches observations to resources** via syn51730943 lookup
- Adds metadata for tracking (source, confidence, context)
- **Generates NEW ROWS only** - files are meant to be appended after verification

**Outputs (Core Tables):**
- `SUBMIT_resources.csv` - For syn26450069 (main table with resourceName)

**Outputs (Detail Tables) - Novel tools only:**
- `SUBMIT_animal_models.csv` - For syn26486808
- `SUBMIT_antibodies.csv` - For syn26486811
- `SUBMIT_cell_lines.csv` - For syn26486823
- `SUBMIT_genetic_reagents.csv` - For syn26486832

**Outputs (Publication Tables):**
- `SUBMIT_publications.csv` - For syn26486839 (base publication information)
- `SUBMIT_usage.csv` - For syn26486841 (publications where tools were USED)
- `SUBMIT_development.csv` - For syn26486807 (publications where tools were DEVELOPED)

**Outputs (Observation Tables):**
- `SUBMIT_observations.csv` - For syn26486836 (scientific observations about tools)
- `SUBMIT_observations_UNMATCHED.csv` - Observations needing manual resource matching

**Pre-filled Fields:**
- Antibodies: clonality, host, vendor, catalog #, reactive species
- Cell lines: category, organ, tissue
- Animal models: strain, substrain, manifestations, allele type
- Genetic reagents: vector type, resistance, backbone

#### `tool_coverage/scripts/generate_coverage_summary.py`
Generates markdown summary for GitHub Pull Request:
- Summarizes current coverage status
- Lists novel tools discovered
- Highlights GFF publications with potential tools
- Explains review workflow and automatic upload on merge

**Output:**
- `pr_body.md` - Markdown content for GitHub Pull Request

#### `tool_coverage/scripts/run_publication_reviews.py`
AI-powered validation of mined tools using Goose agent:
- **Validates mined tools** to filter out false positives (gene/disease names misidentified as tools)
- **Analyzes publication type** (lab research vs clinical studies vs bioinformatics vs questionnaires)
- **Uses query_type as hint** but independently assesses ALL 9 tool types in every publication
- **Handles multi-type publications** (e.g., clinical study using computational tools for analysis)
- **Checks tool keywords** (antibody, plasmid, cell line, software, questionnaire, etc.) near mentions
- **Detects potentially missed tools** that mining didn't catch
- **Suggests new patterns** to improve future mining accuracy
- **Generates validation reports** with detailed reasoning for accept/reject decisions
- **Creates VALIDATED_*.csv** files with rejected tools removed (9 files, one per tool type)

**How query_type is used:**
- Publications tagged with `query_type: "bench"` → Likely contains lab tools
- Publications tagged with `query_type: "clinical"` → Likely contains clinical assessment tools
- Publications tagged with `query_type: "bench,clinical"` → May contain both categories
- **BUT:** AI always scans for ALL 9 tool types regardless of query_type (just a hint for prioritization)

⚠️ **Requires Anthropic API key** - See [tool_coverage/docs/AI_VALIDATION_README.md](tool_coverage/docs/AI_VALIDATION_README.md) for setup

**Usage:**
```bash
# Validate specific publications
python tool_coverage/scripts/run_publication_reviews.py --pmids "PMID:28078640"

# Validate all mined publications (skips already-reviewed to save API costs)
python tool_coverage/scripts/run_publication_reviews.py --mining-file processed_publications.csv

# Force re-review of already-reviewed publications
python tool_coverage/scripts/run_publication_reviews.py --mining-file processed_publications.csv --force-rereviews
```

**Smart Optimizations**:
- **Text Caching**: Fetched text cached during mining, reused in validation (50% fewer API calls)
- **Skip Logic**: Publications with existing validation YAMLs automatically skipped (85-90% cost savings)
- **Combined**: 80-85% reduction in API calls and costs for ongoing operations
- Use `--force-rereviews` to override skip logic when needed

**Outputs:**
- `VALIDATED_*.csv` - Validated submissions (false positives removed, recommended)
- `tool_reviews/validation_report.xlsx` - AI validation summary
- `tool_reviews/validation_summary.json` - Machine-readable validation results
- `tool_reviews/potentially_missed_tools.csv` - Tools AI found that mining missed
- `tool_reviews/suggested_patterns.csv` - Recommended patterns to improve mining
- `tool_reviews/results/{PMID}_tool_review.yaml` - Per-publication validation details

**Example false positive caught:**
- Publication: "Development of pediatric quality of life inventory for NF1"
- Mined: "NF1 antibody", "NF1 genetic reagent"
- AI verdict: **Reject** - "Questionnaire development study, not lab research. NF1 refers to disease throughout."

#### `tool_coverage/scripts/clean_submission_csvs.py`
Prepares SUBMIT_*.csv files for Synapse upload:
- **Validates CSV schema** against required columns and non-null constraints
- **Removes tracking columns** (prefixed with '_') used for manual review
- **Saves cleaned versions** as CLEAN_*.csv files
- **Optionally uploads** cleaned data to Synapse tables via --upsert flag
- **Dry-run mode** (--dry-run) previews uploads without making changes
- Maps CSV files to appropriate Synapse table IDs automatically

⚠️ **Validation runs automatically in workflow** - also available for local testing

**Usage:**
```bash
# Validate only
python tool_coverage/scripts/clean_submission_csvs.py --validate

# Clean only (with validation)
python tool_coverage/scripts/clean_submission_csvs.py

# Preview upload (validate + dry-run, no actual upload)
python tool_coverage/scripts/clean_submission_csvs.py --upsert --dry-run

# Validate, clean, and upload to Synapse
python tool_coverage/scripts/clean_submission_csvs.py --upsert
```

### 2. GitHub Actions Workflow

**File:** `.github/workflows/check-tool-coverage.yml`

**Trigger:**
- When PR from review-tool-annotations is merged (label: `automated-annotation-review`)
- Manual trigger via workflow_dispatch

**Manual Trigger Options:**
- **AI Validation** (default: enabled) - Run Goose AI validation on mined tools
- **Max Publications** (default: all) - Limit number of publications to mine
- **Force Re-reviews** (default: disabled) - Force re-review of already-reviewed publications

**Steps:**
1. Checkout repository
2. Set up Python 3.11 with pip cache
3. Install dependencies from requirements.txt
4. Check for ANTHROPIC_API_KEY (skips AI validation if missing)
5. Install Goose CLI (if AI validation enabled and API key present)
6. **Prepare publication lists:**
   - Run bench science query → `publication_list_bench.csv`
   - Run clinical assessment query → `publication_list_clinical.csv`
   - Merge by PMID, preserving query_type tags → `publication_list.csv`
7. **Screen titles with Haiku:** Filter to research publications (includes clinical studies)
8. **Screen abstracts with Haiku:** Filter for NF tool usage/development
   - Ensures abstracts available (from Synapse or fetches from PubMed)
   - Screens for 9 tool categories using Claude 3.5 Haiku
   - Batch processing: ~50 abstracts per API call (~$0.002/batch)
9. **Apply timeout protection:** Cap publications to fit within 6-hour GitHub Actions limit
10. **Extract publication sections:** Fetch full text and extract all sections
   - Abstract, Introduction, Methods, Results, Discussion
   - Caches all sections for Sonnet review
   - Tool mining disabled by default (focus on section extraction)
11. **Run AI validation with Sonnet:**
   - Reviews extracted sections for tools and observations
   - Uses query_type as hint
   - Validates all 9 tool types
   - Handles multi-type publications
12. **Format mining results:** Create 9 SUBMIT_*.csv files (one per tool type)
13. **Clean and validate:** Remove tracking columns, validate schema
14. Run coverage analysis
15. Generate summary report
16. Upload all reports as artifacts including validation results (90-day retention)
17. **Create Pull Request** with result files for review

### 3. Synapse Upsert Workflow

**File:** `.github/workflows/upsert-tools.yml`

**Triggers:**
- Automatically when PR is merged to `main` branch with `VALIDATED_*.csv` or `SUBMIT_*.csv` files
- Manual trigger via workflow dispatch (with optional `dry_run` mode)

**Steps:**
1. Checkout repository
2. Set up Python 3.11 with pip cache
3. Install dependencies from requirements.txt
4. Check for validated or submit CSV files
5. **Validate CSV schema** against required columns and constraints
6. Clean submission files (remove tracking columns)
7. **Dry-run preview** of Synapse uploads (safety check)
8. **Upload cleaned data** to Synapse tables (skipped if `dry_run=true`)
9. **Regenerate coverage report** (shows updated metrics after upload)
10. Create upload summary with table links
11. Upload cleaned CSVs and updated PDF as artifacts (30-day retention)

**Safety Features:**
- **Schema validation** checks required fields before upload
- **Dry-run mode** available via workflow_dispatch input (validate without uploading)
- Prefers `VALIDATED_*.csv` files (AI-validated, false positives removed)
- Falls back to `SUBMIT_*.csv` if validated files not present
- Runs dry-run preview before actual upload
- Skips if no CSV files found or validation fails

**Synapse Tables Updated:**

**Established Tool Types (v1.0):**
- Animal Models: syn26486808
- Antibodies: syn26486811
- Cell Lines: syn26486823
- Genetic Reagents: syn26486832

**New Tool Types (v2.0):**
- Computational Tools: syn73709226
- Advanced Cellular Models: syn73709227
- Patient-Derived Models: syn73709228
- Clinical Assessment Tools: syn73709229

**Common Tables:**
- Resources: syn26450069
- Publications: syn26486839
- Usage: syn26486841 (where tools were USED)
- Development: syn26486807 (where tools were DEVELOPED)
- Observations: syn26486836 (scientific observations about tools)

## Recent Improvements

### Abstract Screening & Section Extraction

**Two-stage Haiku screening:**
1. **Title screening** - Filters research vs clinical publications
2. **Abstract screening** - Filters for NF tool usage/development

**Benefits:**
- 🎯 **Better precision:** Two stages of filtering before full-text extraction
- 💰 **Cost efficient:** Cheap Haiku screening (~$0.002/batch) saves expensive Sonnet tokens
- ⚡ **Faster workflow:** Skip publications without tool evidence
- 📊 **Higher quality:** Sonnet reviews only relevant publications

**Workflow changes:**
- **Before:** Title screening → Full-text mining → Sonnet review
- **After:** Title screening → Abstract screening → Section extraction → Sonnet review

**Section extraction mode:**
- **Tool mining disabled by default** - focus on extracting all sections for AI review
- Extracts: Abstract, Introduction, Methods, Results, Discussion
- Sonnet reviews full text instead of relying on pattern matching
- Can re-enable tool mining with `--enable-tool-mining` flag

### Exact Matching & Synonym Support

**Changed from fuzzy to exact matching:**
- **Before:** Fuzzy matching with ~88% similarity threshold
- **After:** Exact matching (case-insensitive) with word boundaries
- **Why:** Reduces false positives, more precise tool identification

**Synonym support added:**
- Loads **1,700+ synonyms** from syn51730943 'synonyms' column
- Synonyms parsed from comma-separated format (e.g., "syn1, syn2, syn3")
- Matches both resourceName AND all synonyms
- **Example:** Cell lines have 1,200+ synonyms for improved matching

**Distribution of synonyms by tool type:**
| Tool Type | Resources | Synonyms |
|-----------|-----------|----------|
| Cell Lines | 638 | 1,200 |
| Antibodies | 261 | 261 |
| Animal Models | 123 | 137 |
| Genetic Reagents | 122 | 123 |

### Publication Filtering Workflow

The workflow uses a two-stage Haiku screening process to filter publications efficiently:

**Stage 1: Title Screening**
- Filters research vs clinical publications
- Excludes reviews, case reports, editorials
- Cost: ~$0.001 per batch of 100 titles

**Stage 2: Abstract Screening**
- Filters for NF tool usage or development
- Ensures abstracts available (fetches from PubMed if needed)
- Screens for all 9 tool categories
- Cost: ~$0.002 per batch of 50 abstracts

**Benefits:**
- Better precision through two stages of filtering
- Reduces full-text extraction workload
- Cost-efficient Haiku screening saves Sonnet tokens
- Faster workflow by skipping publications without tool evidence

**Complete Workflow:**
```
Title Screening → Abstract Screening → Section Extraction → Sonnet Review
  (Haiku)            (Haiku)            (PMC fetch)         (Sonnet)
```

## Configuration

### Required Secrets

The workflow requires the following GitHub secrets to be configured:

1. **`SYNAPSE_AUTH_TOKEN`**
   - Personal access token for Synapse API
   - Used to query publications and tools databases
   - Generate at: https://www.synapse.org/#!PersonalAccessTokens:

2. **`ANTHROPIC_API_KEY`**
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
- anthropic >= 0.39.0 (for AI screening and validation)
- pyyaml >= 6.0
- biopython >= 1.83 (for PubMed abstract fetching)
- rapidfuzz >= 3.0.0 (for fuzzy matching when tool mining enabled)

### Configuration Files

#### `config/ai_screening_knowledge.json`
Domain knowledge for AI screening prompts (Haiku and Sonnet). Contains:

**Computational Tools:**
- Known established tools (175): GraphPad Prism, ImageJ, STAR, DESeq2, Seurat, FlowJo, etc.
- Excluded false positives (113): Programming languages (R, Python), IDEs (RStudio, Jupyter), generic terms
- Novel tool indicators: Title patterns, development language

**Animal Models:**
- NF-specific models: Nf1+/-, Nf1-/-, Nf2+/-, Nf2-/- with aliases
- Generic strains to exclude: C57BL/6, BALB/c, nude mice (unless with NF mutation)

**Cell Lines:**
- NF-specific lines: ST88-14, sNF96.2, ipNF95.11
- Generic line context rules

**Usage:**
- Automatically loaded by `screen_publication_abstracts.py`
- Can be extended with new tools, exclusions, or aliases
- Update when false positive patterns are identified

**Updating the knowledge base:**
```json
{
  "computational_tools": {
    "known_established_tools": {
      "new_category": ["Tool1", "Tool2"]
    },
    "excluded_false_positives": {
      "new_exclusions": ["Term1", "Term2"]
    }
  }
}
```

#### `config/known_computational_tools.json`
Original computational tools configuration (used by tool mining when enabled).

#### `config/animal_model_aliases.json`
Animal model nomenclature aliases for pattern matching.

#### `config/mining_patterns.json`
Text patterns for tool detection when tool mining is enabled.

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

### Run Publication Screening and Section Extraction

**Step 1: Screen publication titles** (requires ANTHROPIC_API_KEY)
```bash
# Filter to research publications
python tool_coverage/scripts/screen_publication_titles.py

# Or test with limited publications
python tool_coverage/scripts/screen_publication_titles.py --max-publications 10
```

**Step 2: Screen publication abstracts** (requires ANTHROPIC_API_KEY)
```bash
# Filter for NF tool usage/development
python tool_coverage/scripts/screen_publication_abstracts.py

# Or test with limited publications
python tool_coverage/scripts/screen_publication_abstracts.py --max-publications 10
```

**Step 3: Extract publication sections**
```bash
# Extract all sections (abstract, intro, methods, results, discussion)
python tool_coverage/scripts/mine_publications_improved.py

# Or test with limited publications
python tool_coverage/scripts/mine_publications_improved.py --max-publications 10

# Optional: Enable tool mining (pattern-based)
python tool_coverage/scripts/mine_publications_improved.py --enable-tool-mining --max-publications 10
```

### Run AI Validation (Optional but Recommended)

**Setup for AI validation:**
```bash
# Install Goose CLI
go install github.com/block/goose@latest

# Configure with Anthropic API key
goose configure
# (Enter API key from https://console.anthropic.com/settings/keys)
```

**Run validation + observation extraction:**
```bash
# Validates mined tools AND extracts scientific observations
# Uses cached text (all 5 sections) from mining step - no additional API calls
python tool_coverage/scripts/run_publication_reviews.py --mining-file processed_publications.csv
```

**AI validation performs:**
- Tool validation (accept/reject false positives)
- Potentially missed tool detection
- Mining pattern suggestions
- **Scientific observation extraction** (from Results/Discussion sections)

**Outputs:**
- `VALIDATED_*.csv` - Filtered tool lists (false positives removed)
- `observations.csv` - Scientific observations about tools
- `potentially_missed_tools.csv` - Tools that mining may have missed
- `suggested_patterns.csv` - Patterns to improve future mining
- `validation_report.xlsx` - Summary with observation counts

### Generate Summary
```bash
python tool_coverage/scripts/generate_coverage_summary.py > pr_body.md
```

## Understanding the Results

### Coverage Metrics

- **Target:** 80% of GFF-funded publications should have linked tools
- **Current Status:** Displayed in weekly reports
- **Needed:** Number of additional publications required to reach target

### Tool Mining Results

The mining process identifies potential tools in **nine categories**:

**Lab Research Tools:**
- **Cell Lines** (🧫) - Cell culture resources
- **Antibodies** (🔬) - Immunological reagents
- **Animal Models** (🐭) - Transgenic/knockout models
- **Genetic Reagents** (🧬) - Plasmids, vectors, constructs
- **Biobanks** (🏦) - Sample collections

**Computational & Model Systems:**
- **Computational Tools** (💻) - Software (ImageJ, R, Python, STAR, Cell Ranger, etc.)
- **Advanced Cellular Models** (🧪) - Organoids, assembloids, 3D cultures
- **Patient-Derived Models** (🐁) - PDX, xenografts, humanized mice

**Clinical Tools:**
- **Clinical Assessment Tools** (📋) - Questionnaires, scales, PROMs (SF-36, PROMIS, PedsQL, VAS)

Each tool is tagged with:
- **Development Status** - Whether the tool was developed in this publication or just used
- **Context Metadata** - Extracted characteristics (species, strain, clonality, version, etc.)
- **Query Source** - Which query type discovered the tool (bench/clinical/organoid)

### Observation Mining

The AI validation also extracts **scientific observations** about tools from Results and Discussion sections:

**Observation Types Extracted (20 categories):**
- **Phenotypic:** Body Length, Body Weight, Coat Color, Organ Development
- **Growth/Metabolic:** Growth Rate, Lifespan, Feed Intake, Feeding Behavior
- **Behavioral:** Motor Activity, Swimming Behavior, Social Behavior, Reproductive Behavior
- **Disease:** Disease Susceptibility, Tumor Growth
- **Practical:** Usage Instructions, Issue, Depositor Comment, General Comment or Review, Other

**Example Observations:**
- "Nf1+/- mice showed 15% reduced body weight at 8 weeks (p<0.01)" → Body Weight
- "Optic gliomas developed in 30% of animals by 12 months" → Tumor Growth
- "Antibody shows cross-reactivity with NF2, use 1:1000 dilution" → Usage Instructions

**Observation Processing:**
1. AI extracts observations from Results/Discussion sections
2. Links observations to validated tools (via resourceName)
3. `format_mining_for_submission.py` matches observations to resourceIds via syn51730943
4. Creates `SUBMIT_observations.csv` (matched) and `SUBMIT_observations_UNMATCHED.csv` (unmatched)
5. `clean_submission_csvs.py` validates schema (same as all other entities):
   - Required fields: resourceId, resourceType, resourceName, observationType, details
   - No null values in required fields
   - No empty rows
6. Creates `CLEAN_observations.csv` ready for Synapse upload

**Consistent with all SUBMIT files** - observations validated the same way as tools, publications, and links.

**Impact on Tool Completeness:**
- Observations contribute **25 points** (25%) to tool completeness score
- Observations with DOI: 7.5 points each (up to 4)
- Observations without DOI: 2.5 points each (up to 10)

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
  - `processed_publications.csv` - All mining results
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
   - **Publications:** syn26486839
   - **Usage:** syn26486841 (tools that were USED)
   - **Development:** syn26486807 (tools that were DEVELOPED)
5. Creates snapshot versions for all updated tables (audit trail)
6. **Regenerates coverage report PDF** with updated metrics
7. Creates upload summary in GitHub Actions

**IMPORTANT:** The CSV files contain NEW ROWS only - they are **appended** to existing Synapse tables, not used as replacements.

### 5. Verify Upload Success

After merging:
- Check the `upsert-tools` workflow run in GitHub Actions
- Review the upload summary for any errors
- Verify row counts increased in Synapse tables
- Download the updated `GFF_Tool_Coverage_Report.pdf` from workflow artifacts to see new coverage metrics

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

Scripts currently write output files to the **repository root** (for GitHub Actions workflow compatibility).

**Tracked files (persistent state):**
- `processed_publications.csv` - Cache of all processed publications
- `SUBMIT_*.csv` - Unvalidated submission files
- `VALIDATED_*.csv` - AI-validated submission files (production-ready)
- Analysis CSVs (priority publications, GFF pubs, missing tools)
- `tool_reviews/validation_report.xlsx` - AI validation summary
- `tool_reviews/potentially_missed_tools.csv` - Tools AI found that mining missed
- `tool_reviews/suggested_patterns.csv` - Recommended patterns to improve mining

**Ignored files (temporary/regenerated):**
- `CLEAN_*.csv` - Cleaned files (regenerated from SUBMIT/VALIDATED)
- `*.log` - Workflow execution logs
- `pr_body.md` - Generated PR description
- `tool_reviews/publication_cache/` - API call caching
- `tool_reviews/inputs/` - Temporary input files
- PDF reports - Regenerated and available as artifacts

The `results/` folder in this directory is available for organizing outputs locally if desired.

