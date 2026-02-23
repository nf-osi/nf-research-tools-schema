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
   ├─ Filters publications (title + abstract screening with Haiku)
   ├─ Fetches minimal cache (Phase 1) and upgrades for high-confidence tools (Phase 2)
   ├─ AI validation with Sonnet (direct API, 4 parallel workers)
   ├─ Extracts observations for high-confidence tools (Phase 2)
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

**Purpose**: Mine NF Portal + PubMed publications for ALL 9 tool types using multi-query strategy with AI validation

**Trigger**:
- When PR from `review-tool-annotations` is merged (label: `automated-annotation-review`)
- Manual: workflow_dispatch

**Manual Inputs** (workflow_dispatch only):
| Input | Description | Default |
|-------|-------------|---------|
| `ai_validation` | Run AI validation on mined tools using Sonnet | `true` |
| `max_publications` | Maximum number of publications to mine | all |
| `force_rereviews` | Force re-review of already-reviewed publications | `false` |
| `skip_title_screening` | Skip title screening (use existing `screened_publications.csv` from artifact) | `false` |
| `skip_abstract_screening` | Skip abstract screening (use existing `abstract_screened_publications.csv` from artifact) | `false` |
| `max_reviews` | Max Sonnet reviews per run | auto-calculated from timeout budget |

**What it does**:
1. **Runs TWO PubMed queries** to capture all tool types:
   - **Bench science query**: Lab tools, computational tools, organoids, PDX models
   - **Clinical assessment query**: Questionnaires, scales, patient-reported outcomes
2. **Merges publication lists** by PMID, preserving query_type tags:
   - Publications in both queries tagged: `query_type: "bench,clinical"`
   - Used as hint for AI validation (but all 9 types always scanned)
3. **Title screening with Haiku**: Pre-filters publications to research-relevant studies
4. **Abstract screening with Haiku**: Further filters for NF tool usage/development
5. **Applies timeout protection**: Caps publications to fit within 6-hour GitHub Actions limit; defers excess to next run
6. **Appends Synapse candidates**: Fetches unlinked publications from NF portal + unlinked-tools Synapse tables and adds them to the screened list
7. **Phase 1 cache fetch**: Fetches minimal content per publication (title + abstract + methods + metadata); 48% smaller and 30% faster than full text
8. **AI validation with Sonnet** (direct Anthropic API, 4 parallel workers):
   - Searches for ALL 9 tool types in every publication:
     - **Lab tools:** Cell lines, antibodies, animal models, genetic reagents, biobanks
     - **Computational:** Software, pipelines (R, Python, ImageJ, STAR, Seurat, scanpy, 50+ tools)
     - **Advanced models:** Organoids, assembloids, 3D cultures, spheroids
     - **Patient-derived:** PDX, xenografts, humanized mice
     - **Clinical:** SF-36, PROMIS, PedsQL, VAS, questionnaires, outcome measures
   - Uses query_type as a hint for expected tool categories
   - Independently classifies publication type
   - Handles publications with multiple tool types
9. **Phase 2 cache upgrade**: Selectively adds Results + Discussion sections for high-confidence validated tools (confidence ≥ 0.8)
10. **Phase 2 observation extraction**: Extracts efficacy, safety, and outcome observations from upgraded publications; writes `*_observations.yaml` alongside tool review YAMLs
11. **Post-filter and consolidate**: Removes generic tools, deduplicates synonyms, and writes `VALIDATED_*.csv` files
12. **Applies pattern improvements**: Updates `mining_patterns.json` based on AI-suggested improvements
13. **Analyzes tool coverage** and generates summary report

**Multi-Query Strategy**: Runs BOTH queries every time to discover all tool types
- No separate runs needed - comprehensive coverage in single workflow execution
- Expected monthly discovery: 69-83 tools (vs 18 with old single-query system)

**Outputs**:
- `tool_coverage/outputs/processed_publications.csv`
- `tool_coverage/outputs/screened_publications.csv` (title + abstract filtered)
- `tool_coverage/outputs/abstract_screened_publications.csv`
- `tool_reviews/publication_cache/` — Phase 1 (minimal) and Phase 2 (upgraded) caches
- `tool_reviews/results/` — per-publication YAML review files
- `tool_reviews/results/*_observations.yaml` — Phase 2 observation YAMLs
- `tool_coverage/outputs/VALIDATED_*.csv` — post-filtered tool records
- `tool_coverage/config/mining_patterns.json` — updated mining patterns
- `pr_body.md` — coverage summary report
- Artifacts: `tool-coverage-reports` (30-day retention), `tool-coverage-pre-validation` (7-day), `deferred-publications-<run_id>` (90-day, only if publications were capped)

**PR Labels**: `automated-mining`, `tool-coverage`

**Assignee**: BelindaBGarana

**Documentation**: See [`tool_coverage/README.md`](../../tool_coverage/README.md)

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

**Purpose**: Automatically upload validated tool data to Synapse

**Trigger**:
- When SUBMIT_*.csv or VALIDATED_*.csv files are pushed to main
- Manual: workflow_dispatch with optional dry-run

**What it does**:
1. Detects VALIDATED_*.csv (AI-validated) or SUBMIT_*.csv files
2. Validates CSV schemas
3. Cleans tracking columns (prefixed with `_`)
4. Uploads to corresponding Synapse tables:
   - syn26486808 (animal models)
   - syn26486811 (antibodies)
   - syn26486823 (cell lines)
   - syn26486832 (genetic reagents)
   - syn26450069 (resources)
5. Regenerates coverage report

**No PR Created**: Uploads directly, creates summary in Actions

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
