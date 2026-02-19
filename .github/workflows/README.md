# Automated Workflows

This repository uses automated GitHub Actions workflows to maintain and improve the NF Research Tools schema.

## 🔗 Workflow Sequence (Issue #97)

Workflows are coordinated through **PR merge triggers** - each workflow creates a PR, and when merged, triggers the next workflow in the sequence:

```
1. review-tool-annotations.yml (Monday 9 AM UTC)
   ├─ Analyzes individualID annotations vs tools
   ├─ Suggests new cell lines and synonyms
   └─ Creates PR with label: automated-annotation-review
         ↓ (when PR merged)

2. check-tool-coverage.yml
   ├─ Mines NF Portal + PubMed publications for tools
   ├─ Filters for research-focused publications
   ├─ Checks PMC full text availability
   ├─ Incremental processing (caches reviewed PMIDs)
   ├─ AI validation with Goose (optional)
   └─ Creates PR with label: automated-mining
         ↓ (when PR merged)

3. link-tool-datasets.yml
   ├─ Links datasets to tool publications
   └─ Creates PR with label: dataset-linking
         ↓ (when PR merged)

4. score-tools.yml
   ├─ Calculates tool completeness scores
   ├─ Uploads directly to Synapse
   └─ No PR created (direct upload)
         ↓ (workflow_run trigger)

5. update-observation-schema.yml
   ├─ Updates observation schema from Synapse
   └─ Creates PR only if changes detected
```

### Key Points

- **Entry point**: `review-tool-annotations.yml` runs on schedule (Monday 9 AM UTC)
- **All other workflows**: Trigger on PR merge from previous step
- **Manual triggers**: All workflows support `workflow_dispatch` for testing
- **No schedules**: Only the entry point has a schedule; others are PR-driven

## 📋 Workflow Details

### 1. Review Tool Annotations (review-tool-annotations.yml)

**Purpose**: Analyze individualID annotations and suggest new tools (ENTRY POINT)

**Trigger**:
- Schedule: Monday 9 AM UTC
- Manual: workflow_dispatch

**What it does**:
1. Queries `individualID` from syn52702673 (annotations)
2. Compares against tools in syn51730943
3. Suggests new cell lines (assumes all individualIDs are cell lines)
4. Uses fuzzy matching (0.85 threshold) to suggest synonyms
5. Analyzes facet configuration
6. Creates SUBMIT_*.csv files ready for Synapse upload

**Outputs**:
- `SUBMIT_cell_lines.csv`
- `SUBMIT_resources.csv`
- `tool_annotation_suggestions.json`
- `tool_annotation_suggestions.md`

**PR Labels**: `automated-annotation-review`, `cell-lines`, `needs-manual-review`

**Assignee**: BelindaBGarana

**Manual Review Required**: Fill in `organ` field for cell lines before merging

**Documentation**: See [`docs/TOOL_ANNOTATION_REVIEW.md`](../../docs/TOOL_ANNOTATION_REVIEW.md)

---

### 2. Check Tool Coverage (check-tool-coverage.yml)

**Purpose**: Mine NF Portal + PubMed publications for ALL 9 tool types using multi-query strategy with AI validation, quality filtering, and completeness scoring

**Trigger**:
- When PR from `review-tool-annotations` is merged
- Manual: workflow_dispatch

**What it does**:
1. **Runs TWO PubMed queries in parallel** to capture all tool types:
   - **Bench science query**: Lab tools, computational tools, organoids, PDX models
   - **Clinical assessment query**: Questionnaires, scales, patient-reported outcomes
2. **Merges publication lists** by PMID, preserving query_type tags
3. **Title screening with Haiku**: Pre-filters publications (INCLUDES clinical studies)
4. **Abstract screening with Haiku**: Validates NF tool usage/development
5. **Full text mining**: Fetches and mines Methods, Introduction, Results, Discussion
6. **AI validation with Sonnet** (via Goose):
   - Reviews full publication text
   - Validates tools and extracts metadata
   - Assigns confidence scores (0.0-1.0)
   - Detects potentially missed tools
   - Extracts observations with metadata
7. **Quality filtering** (NEW):
   - **Confidence threshold**: Tools/observations with confidence ≥ 0.7
   - **NF-specific filtering**: Removes generic tools (R, ImageJ, GraphPad, etc.)
   - **Critical fields requirement**: Tools must have ≥50% of critical metadata fields
   - **Completeness scoring**: Calculates metadata completeness (0-30 points)
8. **Metadata enrichment**:
   - Pattern-based extraction from context snippets
   - Fills organ, tissue, manifestation, species, etc.
   - 39 metadata fields across 8 tool types
9. **Dual output generation**:
   - **VALIDATED_*.csv**: All tools passing confidence + NF filters (comprehensive)
   - **FILTERED_*.csv**: High-completeness subset (≥60% critical fields, priority review)
10. **PMID review summary**: Comprehensive table for manual review tracking

**Quality Metrics Tracked**:
- Confidence scores (0.7-1.0 scale)
- Metadata completeness (0-30 points)
- Critical fields coverage (%)
- Missing critical fields (explicit list)

**Multi-Query Strategy**: Runs BOTH queries every time to discover all tool types
- No separate runs needed - comprehensive coverage in single workflow execution
- Expected monthly discovery: 69-83 tools (vs 18 with old single-query system)

**Outputs**:
- `VALIDATED_*.csv` (8 files) - All validated tools
- `FILTERED_*.csv` (8 files) - High-completeness priority subset
- `VALIDATED_resources.csv` - Unique resources
- `VALIDATED_publications.csv` - Publication metadata
- `VALIDATED_usage.csv` - Publication-resource links
- `VALIDATED_development.csv` - NEW tools not in Synapse
- `VALIDATED_observations.csv` - Scientific observations
- `PMID_REVIEW_SUMMARY.csv` - Review tracking table
- `tool_reviews/validation_summary.json` - Full validation results
- `tool_reviews/potentially_missed_tools.csv` - Tools found by Sonnet
- `tool_reviews/observations.csv` - Extracted observations

**PR Labels**: `automated-mining`, `tool-coverage`

**Assignee**: BelindaBGarana

**Documentation**:
- Main: [`tool_coverage/README.md`](../../tool_coverage/README.md)
- AI Validation: [`tool_coverage/docs/AI_VALIDATION_README.md`](../../tool_coverage/docs/AI_VALIDATION_README.md)

---

### 3. Link Tool Datasets (link-tool-datasets.yml)

**Purpose**: Link datasets to tools via publication relationships

**Trigger**:
- When PR from `check-tool-coverage` is merged
- Manual: workflow_dispatch

**What it does**:
1. Queries NF Portal publications linked to tools
2. Finds datasets associated with those publications
3. Creates tool-dataset linkage CSV
4. Generates PR if new linkages found

**Outputs**: `SUBMIT_tool_datasets.csv`

**PR Labels**: `automated`, `dataset-linking`

**Assignee**: BelindaBGarana

**Documentation**: See [`tool_coverage/docs/Dataset-tool_linking_README.md`](../../tool_coverage/docs/Dataset-tool_linking_README.md)

---

### 4. Calculate Completeness Scores (score-tools.yml)

**Purpose**: Calculate and upload tool completeness scores

**Trigger**:
- When PR from `link-tool-datasets` is merged
- Manual: workflow_dispatch

**What it does**:
1. Fetches all tools from syn51730943
2. Calculates completeness scores based on filled fields
3. Uploads scores directly to Synapse
4. Generates PDF report

**Outputs**:
- Synapse tables: ToolCompletenessScores, ToolCompletenessSummary
- PDF report (artifact)

**No PR Created**: Uploads directly to Synapse

---

### 5. Update Observation Schema (update-observation-schema.yml)

**Purpose**: Keep observation schema in sync with Synapse data

**Trigger**:
- When `score-tools` workflow completes (workflow_run)
- Manual: workflow_dispatch

**What it does**:
1. Queries syn51730943 for unique resourceType and resourceName values
2. Compares with current SubmitObservationSchema.json
3. If changes detected, updates schema and creates PR
4. If no changes, workflow completes without PR

**Outputs**: Updated `SubmitObservationSchema.json` (if changes)

**PR Labels**: `automated`, `schema-update`

**Assignee**: BelindaBGarana

---

## 🔧 Supporting Workflows

These workflows support the main sequence but run independently:

### Upsert Tools to Synapse (upsert-tools.yml)

**Purpose**: Automatically upload high-quality tool data to Synapse

**Trigger**:
- When FILTERED_*.csv files are pushed to main (after PR merge)
- Manual: workflow_dispatch with optional dry-run

**What it does**:
1. **Detects FILTERED_*.csv files**:
   - High-completeness subset with ≥60% critical fields filled
   - Confidence ≥0.7 (AI validation)
   - NF-specific filtering applied (generic tools removed)
2. **Validates CSV schemas** against Synapse table requirements
3. **Cleans tracking columns** (prefixed with `_`):
   - Removes: _pmid, _doi, _publicationTitle, _confidence, _contextSnippet, _completenessScore, _criticalFieldsScore, _missingCriticalFields, _hasMinimumFields
   - These are for review only, not uploaded to Synapse
4. **Uploads to corresponding Synapse tables**:
   - syn73709226 (computational tools)
   - syn26486808 (animal models)
   - syn26486811 (antibodies)
   - syn26486823 (cell lines)
   - syn26486832 (genetic reagents)
   - syn52659111 (patient-derived models)
   - syn52659112 (advanced cellular models)
   - syn52659113 (clinical assessment tools)
   - syn26450069 (resources - main table)
5. **Regenerates coverage report**

**Important Notes**:
- **ONLY processes FILTERED_*.csv files** (high-quality subset)
- To upload all validated tools (VALIDATED_*.csv), manually trigger workflow or commit files to main
- SUBMIT_*.csv files (legacy format) are no longer automatically processed

**Quality Assurance**:
- Confidence threshold: ≥0.7
- NF-specific filtering: Generic tools removed (R, ImageJ, GraphPad, etc.)
- Completeness requirement: ≥60% critical metadata fields filled
- Manual review: Always review PR before merging to trigger upsert

**No PR Created**: Uploads directly after PR merge, creates summary in Actions

---



### Upsert Tool Datasets (upsert-tool-datasets.yml)

**Purpose**: Upload tool-dataset linkages to Synapse

**Trigger**:
- When SUBMIT_tool_datasets.csv is pushed to main
- Manual: workflow_dispatch

**What it does**:
1. Validates dataset linkage CSV
2. Uploads to appropriate Synapse table
3. Links datasets to tools via publications

---

### Publish Schema Visualization (publish-schema-viz.yml)

**Purpose**: Generate and publish interactive schema visualization

**Trigger**:
- When schema files change
- Manual: workflow_dispatch

**What it does**:
1. Generates visual representation of schema
2. Creates interactive documentation
3. Publishes to GitHub Pages or artifact

**Output**: Interactive schema browser

---

### Schematic Schema Convert (schematic-schema-convert.yml)

**Purpose**: Convert between schema formats

**Trigger**:
- When schema CSV is updated
- Manual: workflow_dispatch

**What it does**:
1. Converts nf_research_tools.rdb.model.csv to JSON-LD
2. Validates schema format
3. Commits converted schema

**Note**: Keeps CSV and JSON-LD schemas in sync

---

## 📊 Quality Filtering System

The tool mining workflow implements a comprehensive quality filtering system to ensure high-quality data in Synapse.

### Confidence Threshold (≥0.7)

All tools and observations must meet a minimum confidence threshold:
- **Confidence score**: 0.0-1.0 scale assigned by Sonnet AI during validation
- **Threshold**: 0.7 (tools below this are filtered out)
- **Applied to**: Tools AND observations
- **Rationale**: Ensures AI predictions are high-certainty

### NF-Specific Filtering

Removes generic lab tools not specific to neurofibromatosis research:

**Generic Tools Filtered Out** (~150+ tools):
- Programming languages: R, Python, MATLAB
- Generic software: ImageJ, GraphPad Prism, SPSS, Excel
- Statistical packages: ggplot2, pandas, DESeq2
- Generic databases: PubMed, NCBI, Gene Ontology
- Generic imaging: MRI, CT scan (without NF context)
- Generic cell lines: HEK293, U87 (without NF modifications)
- Assay kits: CellTiter-Glo, BCA Protein Assay
- Drug classes: "MEK inhibitor" (without specific name)

**NF-Specific Tools Kept**:
- NF-modified cell lines: "NF1-deficient U87", "NF2-null HEI-193"
- NF-specific models: "Nf1+/-", "Dhh-Cre;Nf1flox/flox"
- NF-relevant antibodies: Targeting neurofibromin, merlin, BRAF, MEK, ERK
- Named NF resources: "RENOVO-NF1", "PedsQL NF1 Module"

### Critical Metadata Fields

Each tool type has critical fields that must be filled for completeness:

| Tool Type | Critical Fields |
|-----------|----------------|
| **Antibody** | targetAntigen, reactiveSpecies, hostOrganism, clonality |
| **Cell Line** | cellLineCategory, cellLineGeneticDisorder, cellLineManifestation |
| **Animal Model** | animalModelGeneticDisorder, backgroundStrain, animalState |
| **Genetic Reagent** | insertName, insertSpecies, vectorType |
| **Patient-Derived Model** | modelSystemType, tumorType |
| **Advanced Cellular Model** | modelType, derivationSource |
| **Clinical Assessment Tool** | assessmentType, targetPopulation |
| **Computational Tool** | No required fields (name and type sufficient) |

**Minimum Requirement**: Tools must have ≥50% of critical fields filled (or ≥1 field minimum)

### Completeness Scoring

**Scoring System** (based on `tool_scoring.py`):
- **Critical fields**: 0-30 points (distributed evenly across required fields)
- **Calculation**: `(filled_fields / total_critical_fields) × 30`
- **Example**: Antibody with 3/4 critical fields = 22.5 points

**Tracking Columns** (added to all output files):
- `_completenessScore`: Overall metadata completeness (0-30 points)
- `_criticalFieldsScore`: Critical fields score (same as completeness)
- `_missingCriticalFields`: Semicolon-separated list of missing fields
- `_hasMinimumFields`: Boolean indicating if minimum requirements met

### Dual Output System

**VALIDATED_*.csv Files** (Comprehensive):
- **Purpose**: All tools that passed validation
- **Criteria**: Confidence ≥0.7 + NF-specific + Sonnet validated
- **Use case**: Comprehensive review, may need manual curation
- **Quality**: Variable completeness (0-30 points)

**FILTERED_*.csv Files** (Priority):
- **Purpose**: High-completeness subset for immediate upsert
- **Criteria**: All VALIDATED criteria + ≥60% critical fields filled
- **Use case**: Priority manual review, ready for Synapse upsert
- **Quality**: High completeness (≥18/30 points for critical fields)

**Example Results** (typical distribution):
- VALIDATED files: ~2,000 tools (all passing confidence threshold)
- FILTERED files: ~1,900 tools (95%+ of validated tools)
- Cell lines tend to have lower FILTERED percentage (~94%) due to sparse metadata

### Quality Metrics Reported

Each workflow run reports:
```
📊 Quality Metrics:
   - Confidence threshold: 0.7 (0.0-1.0 scale)
   - Tools filtered for low confidence: X
   - Average completeness score: X.X/30 points
   - Tools with minimum critical fields: X/X
   - High-completeness tools (priority): X/X (XX.X%)
```

### Workflow Integration

Quality filtering happens at specific steps in the workflow:

```
1. Screen publications (Haiku) → Title + abstract filtering
2. Extract sections → Full text mining
3. Initialize VALIDATED templates → Create empty CSVs
4. Run Sonnet reviews → Validate tools + assign confidence scores
5. Apply pattern improvements → Suggest new mining patterns
6. ✨ Apply confidence threshold → Filter tools below 0.7
7. ✨ Calculate completeness → Score metadata (0-30 points)
8. ✨ Generate FILTERED subset → Select high-completeness tools
9. Format results → Create VALIDATED_*.csv files
10. ✨ Save FILTERED_*.csv → Priority review subset
11. Enrichment → Fill remaining metadata gaps
12. Generate review summary → PMID-level tracking table
```

### Review Workflow Recommendations

**For Priority Review** (Start here):
1. Review `FILTERED_*.csv` files first
2. These have ≥60% critical fields filled
3. Spot-check for accuracy
4. Ready for Synapse upsert after brief review

**For Comprehensive Review**:
1. Review `VALIDATED_*.csv` files
2. May have sparse metadata (will be enriched)
3. More manual curation needed
4. Consider running enrichment first

**For Quality Monitoring**:
1. Check `PMID_REVIEW_SUMMARY.csv`
2. Track tools per publication
3. Identify high-value publications
4. Monitor observation extraction

## 🛠️ Setup Requirements

### Required Secrets

1. **NF_SERVICE_GIT_TOKEN** (required for all workflows that create PRs)
   - GitHub Personal Access Token with `repo` scope
   - Used to create pull requests
   - Configure in: Settings → Secrets and variables → Actions

2. **SYNAPSE_AUTH_TOKEN** (required for Synapse operations)
   - Synapse Personal Access Token
   - Scopes: `view`, `download`, `modify`
   - Configure in: Settings → Secrets and variables → Actions

3. **ANTHROPIC_API_KEY** (optional, for AI validation)
   - Only needed for check-tool-coverage.yml AI validation
   - Can skip validation if not configured
   - Configure in: Settings → Secrets and variables → Actions

### Repository Permissions

Ensure workflows have these permissions:
- `contents: write` - to commit changes
- `pull-requests: write` - to create PRs
- `issues: write` - for check-tool-coverage workflow

## 🧪 Manual Testing

All workflows can be manually triggered:

1. Go to **Actions** tab
2. Select the workflow you want to run
3. Click **Run workflow**
4. Select branch and provide any inputs
5. Click **Run workflow**

**Testing Order** (if running entire chain manually):
1. review-tool-annotations (entry point)
2. Review & merge PR → triggers check-tool-coverage
3. Review & merge PR → triggers link-tool-datasets
4. Review & merge PR → triggers score-tools
5. Automatically runs → update-observation-schema

## 📊 Monitoring

### Check Workflow Status

1. Go to **Actions** tab
2. View recent workflow runs
3. Green checkmark = Success
4. Red X = Failed (click to view logs)

### Review PRs

Filter PRs by labels:
- `pubmed-mining` - PubMed mining results
- `automated-annotation-review` - New cell lines from annotations
- `automated-mining` - Novel tools from publications
- `dataset-linking` - Dataset-tool linkages
- `schema-update` - Observation schema updates

## 🔍 Troubleshooting

### Workflow Not Triggering

**Problem**: Next workflow doesn't trigger after merging PR

**Check**:
- Verify PR has the correct label (e.g., `automated-annotation-review`)
- Confirm PR was merged (not just closed)
- Check Actions tab for any failed runs
- Verify workflow permissions are correct

### Authentication Errors

**Problem**: Synapse or GitHub authentication failed

**Solution**:
- Verify secrets are configured correctly
- Check tokens haven't expired
- Regenerate tokens if needed
- Ensure tokens have required scopes

### No PR Created

**Problem**: Workflow ran but didn't create PR

**Check**:
- Verify NF_SERVICE_GIT_TOKEN is set correctly
- Check workflow logs for errors
- Confirm there were actually changes to commit
- Verify repository allows automated PRs

## 📁 Related Documentation

- **Workflow coordination**: [`docs/WORKFLOW_COORDINATION.md`](../../docs/WORKFLOW_COORDINATION.md)
- **Tool annotation review**: [`docs/TOOL_ANNOTATION_REVIEW.md`](../../docs/TOOL_ANNOTATION_REVIEW.md)
- **Tool coverage mining**: [`tool_coverage/README.md`](../../tool_coverage/README.md)
- **AI validation**: [`tool_coverage/docs/AI_VALIDATION_README.md`](../../tool_coverage/docs/AI_VALIDATION_README.md)
- **Dataset linking**: [`tool_coverage/docs/Dataset-tool_linking_README.md`](../../tool_coverage/docs/Dataset-tool_linking_README.md)
- **PubMed mining**: [`tool_coverage/docs/README_PUBMED_MINING.md`](../../tool_coverage/docs/README_PUBMED_MINING.md)
- **Scripts documentation**: [`scripts/README.md`](../../scripts/README.md)
