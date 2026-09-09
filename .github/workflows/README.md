# Automated Workflows

This repository uses automated GitHub Actions workflows to maintain and improve the NF Research Tools schema.

## 🔗 Workflow Sequence

Workflows are coordinated through **issue close triggers and PR merges**:

```
1. monthly-submission-check.yml (1st of each month, 9 AM UTC)
   ├─ Runs annotation review (new cell lines from individualID annotations)
   ├─ Creates annotation PR if new cell lines found
   └─ Creates monthly issue with label: tool-submissions
         ↓ (when issue with label tool-submissions is closed)

2. publication-mining.yml
   ├─ Mines NF Portal + PubMed publications for tools
   ├─ Filters publications (title + abstract screening with Haiku)
   ├─ Fetches minimal cache (Phase 1) and upgrades for high-confidence tools (Phase 2)
   ├─ AI validation with Sonnet (direct API, 4 parallel workers)
   ├─ Extracts observations for high-confidence tools (Phase 2)
   ├─ Formats mined tools as JSON in submissions/{type}/
   └─ Creates PR with label: tool-submissions
         ↓ (reviewer deletes rejected files from submissions/{type}/, then merges PR --
            there is no accepted/ subfolder step; whatever remains at merge time uploads)

3. upsert-tools.yml
   ├─ Compiles submissions/{type}/*.json → ACCEPTED_*.csv
   ├─ Validates CSV schemas
   ├─ Uploads to Synapse tables (animal models, antibodies, cell lines, etc.)
   └─ No PR created (uploads directly to Synapse)
         ↓ (when PR from step 2 is merged, label: tool-submissions)

         ↓ (when PR from step 2 is merged, triggers independently):

4. score-tools.yml
   ├─ Calculates tool completeness scores
   ├─ Uploads directly to Synapse
   └─ No PR created (direct upload)

4. update-observation-schema.yml  (runs in parallel with score-tools)
   ├─ Fetches latest tool data from syn51730943
   ├─ Updates SubmitObservationSchema.json enums
   └─ Creates PR if schema changes detected (label: schema-update)
```

### Key Points

- **Entry point**: `monthly-submission-check.yml` runs on the 1st of each month (9 AM UTC)
- **publication-mining**: Triggers when monthly issue with label `tool-submissions` is closed
- **upsert-tools**: Triggers on push to main with files in `submissions/*/*.json` (no `accepted/` subfolder — that step was dropped in 2026-04, see the Upsert Tools section below)
- **score-tools**: Triggers on PR merge with label `tool-submissions`
- **update-observation-schema**: Triggers after `upsert-tools` completes, OR weekly (every Monday, as a fallback — see 4a below for why)
- **Manual triggers**: All workflows support `workflow_dispatch` for testing
- **Annotation review**: Embedded in the monthly issue workflow (not a separate weekly step)

## 📋 Workflow Details

### 1. Monthly Submission Check (monthly-submission-check.yml)

**Purpose**: Coordinate monthly tool review — runs annotation review and creates a GitHub issue with Formspark checklist (ENTRY POINT)

**Trigger**:
- Schedule: 1st of each month at 9 AM UTC
- Manual: workflow_dispatch

**What it does**:
1. Runs `scripts/review_tool_annotations.py` to compare `individualID` annotations (syn52702673) against tools registry (syn51730943)
2. Converts annotation suggestions to `submissions/cell_lines/annotation_*.json`
3. Creates a PR for annotation submissions if new cell lines found
4. Creates a monthly GitHub issue with:
   - Annotation review results (and link to PR if applicable)
   - Formspark submission review checklist

**Outputs**:
- `submissions/cell_lines/annotation_*.json` (if new cell lines found)
- `tool_annotation_suggestions.json`
- `tool_annotation_suggestions.md`
- GitHub issue with label `tool-submissions`
- PR with label `annotation-submissions` (if new cell lines found)

**Documentation**: See [`docs/TOOL_ANNOTATION_REVIEW.md`](../../docs/TOOL_ANNOTATION_REVIEW.md)

---

### 2. Publication Mining (publication-mining.yml)

**Purpose**: Mine NF Portal + PubMed publications for ALL 9 tool types using multi-query strategy with AI validation

**Trigger**:
- When monthly issue with label `tool-submissions` is closed
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
2. **Merges publication lists** by PMID, preserving query_type tags
3. **Title screening with Haiku**: Pre-filters publications to research-relevant studies
4. **Abstract screening with Haiku**: Further filters for NF tool usage/development
5. **Applies timeout protection**: Caps publications to fit within 6-hour GitHub Actions limit
6. **Appends Synapse candidates**: Fetches unlinked publications from NF portal
7. **Phase 1 cache fetch**: Fetches minimal content per publication
8. **AI validation with Sonnet** (direct Anthropic API, 4 parallel workers):
   - Searches for ALL 9 tool types in every publication
9. **Phase 2 cache upgrade**: Selectively adds Results + Discussion sections for high-confidence tools
10. **Phase 2 observation extraction**: Extracts efficacy, safety, and outcome observations
11. **Post-filter**: Removes generic tools, deduplicates (ephemeral — not committed)
12. **Format as submission JSON**: Writes mined tools to `submissions/{type}/*.json`

**Outputs**:
- `submissions/{type}/*.json` — mined tools as form-compatible JSON (one file per tool)
- `tool_reviews/results/` — per-publication YAML review files
- `tool_reviews/publication_cache/` — cached publication text
- Artifacts: `tool-coverage-reports` (30-day), `tool-coverage-pre-validation` (7-day)

**PR Labels**: `tool-submissions`

**Assignee**: BelindaBGarana

**Documentation**: See [`tool_coverage/README.md`](../../tool_coverage/README.md)

---

### 4a. Update Observation Schema (update-observation-schema.yml)

**Purpose**: Keep `SubmitObservationSchema.json` in sync with tools in Synapse (resourceType/resourceName enums)

**Trigger**:
- After `upsert-tools.yml` completes on main (independent of score-tools)
- Weekly fallback: every Monday at 9 AM UTC (added for #336, see below)
- Manual: workflow_dispatch

**Why the weekly fallback exists (#336)**: the `upsert-tools.yml` trigger only fires
when a `submissions/*.json` file is pushed to main. A `resourceName` can also
change directly in a live Synapse table — a rename/curation fix applied via a
one-time script (see `scripts/README.md`) rather than a submission JSON — and
that kind of write never touches `submissions/`, so it never triggers
`upsert-tools.yml` and this workflow would never fire either. That gap let the
schema drift stale for over a month before #336 (e.g. it was still offering
`Central AI-enabled Volumetric Service for NF1` after that tool was renamed to
`CAVS-NF1` via a one-time script, and still listed a retired `Nf1tm1a(KOMP)Wtsi`
row). The weekly cron re-checks `syn51730943` regardless of what caused a
change, so drift from any source is caught within a week.

**What it does**:
1. Fetches current tool data from syn51730943
2. Updates `resourceType` and `resourceName` enum values in `SubmitObservationSchema.json`
3. Creates a PR if changes are detected (label: `schema-update`)
4. Fails the run loudly (rather than silently reporting "up to date") if the
   Synapse fetch itself errors — see the workflow file for why this matters

**No PR Created if no changes**: Only creates PR when enums differ from current schema

---

### 4b. Calculate Completeness Scores (score-tools.yml)

**Purpose**: Calculate and upload tool completeness scores

**Trigger**:
- When PR with label `tool-submissions` is merged to main
- Manual: workflow_dispatch

**What it does**:
1. Fetches all tools from syn51730943
2. Calculates completeness scores based on filled fields
3. Uploads scores directly to Synapse
4. Generates PDF report

**No PR Created**: Uploads directly to Synapse

---


## 🔧 Supporting Workflows

These workflows support the main sequence but run independently:

### 3. Upsert Tools to Synapse (upsert-tools.yml)

**Purpose**: Compile accepted JSON submissions and upload to Synapse

**Trigger**:
- When `submissions/*/*.json` files are pushed to main (i.e. when a tool-submissions PR is merged) — `submissions/*/observations/*.json` is excluded from this trigger
- Manual: workflow_dispatch with optional dry-run

**What it does**:
1. Diffs changed files — only processes JSON files that changed in the push (diff-based compile)
2. Compiles `submissions/{type}/*.json` (+ `submissions/{type}/observations/*.json`) → `ACCEPTED_*.csv` + `submission_publications.csv`, `submission_dev_links.csv`, `submission_usage_links.csv`
3. Validates CSV schemas (including `publicationId` resolution for observations)
4. Cleans tracking columns (prefixed with `_`)
5. Uploads to corresponding Synapse tables, one type-specific detail table per
   tool type (each carries its own `resourceId`/`resourceName`/etc. directly —
   there's no longer a central Resources table these feed into; the legacy
   `syn26450069` was retired in the Phase 7 LinkML migration, see
   `docs/MIGRATION.md`):
   - syn26486808 (animal models)
   - syn26486811 (antibodies)
   - syn26486823 (cell lines)
   - syn26486832 (genetic reagents)
   - syn26486839 (publications)
   - syn26486807 (development links)
   - syn26486841 (usage links — non-development publications)
   - syn26486836 (observations)
6. Regenerates coverage report

**Review flow** (no `accepted/` subfolder — dropped 2026-04, see `submissions/README.md`):
- Mined tools are written as JSON directly to `submissions/{type}/`
- Reviewer edits/deletes files in place in the PR; whatever remains in `submissions/{type}/` at merge time is what gets uploaded — no file move needed
- Merging the PR pushes the surviving `submissions/*/*.json` files to main → triggers this workflow

**No PR Created**: Uploads directly, creates summary in Actions

---

### Upsert Tool Datasets (upsert-tool-datasets.yml)

**Purpose**: Upload tool-dataset linkages to Synapse

**Trigger**:
- When SUBMIT_tool_datasets.csv is pushed to main
- Manual: workflow_dispatch

---

### Publish Schema Visualization (publish-schema-viz.yml)

**Purpose**: Generate and publish interactive schema visualization

**Trigger**:
- When schema files change
- Manual: workflow_dispatch

---

### Schematic Schema Convert (schematic-schema-convert.yml)

**Purpose**: Convert between schema formats

**Trigger**:
- When schema CSV is updated
- Manual: workflow_dispatch

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
   - Only needed for publication-mining.yml AI validation
   - Can skip validation if not configured
   - Configure in: Settings → Secrets and variables → Actions

### Repository Permissions

Ensure workflows have these permissions:
- `contents: write` - to commit changes
- `pull-requests: write` - to create PRs
- `issues: write` - for monthly-submission-check workflow

## 🧪 Manual Testing

All workflows can be manually triggered:

1. Go to **Actions** tab
2. Select the workflow you want to run
3. Click **Run workflow**
4. Select branch and provide any inputs
5. Click **Run workflow**

**Testing Order** (if running entire chain manually):
1. monthly-submission-check (entry point) — or close an issue with `tool-submissions` label
2. publication-mining triggers automatically → creates PR
3. Review PR: delete rejected JSONs from `submissions/{type}/`, merge → triggers upsert-tools
4. Merge also triggers score-tools and update-observation-schema (independently)

## 📊 Monitoring

### Check Workflow Status

1. Go to **Actions** tab
2. View recent workflow runs
3. Green checkmark = Success
4. Red X = Failed (click to view logs)

### Review PRs

Filter PRs by labels:
- `annotation-submissions` - New cell lines from annotations
- `tool-submissions` - Mined tools from publications (review in place — delete rejected files before merging, no accepted/ move)



## 🔍 Troubleshooting

### Workflow Not Triggering

**Problem**: publication-mining doesn't trigger after closing the monthly issue

**Check**:
- Verify issue has the `tool-submissions` label
- Confirm issue was closed (not just commented on)
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
- **PubMed mining**: [`tool_coverage/docs/README_PUBMED_MINING.md`](../../tool_coverage/docs/README_PUBMED_MINING.md)
- **Scripts documentation**: [`scripts/README.md`](../../scripts/README.md)
