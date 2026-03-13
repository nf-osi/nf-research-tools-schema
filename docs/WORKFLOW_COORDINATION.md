# Workflow Coordination

## Overview

The automated workflows in this repository run in a coordinated sequence. The monthly issue serves as the human-in-the-loop gate that coordinates annotation review, Formspark submission review, and publication mining.

- ✅ Human review gates between steps
- ✅ Annotation review embedded in monthly workflow (no separate weekly run)
- ✅ Unified `submissions/{type}/` → `submissions/{type}/accepted/` review flow for all tool sources
- ✅ Clear audit trail of changes

## Workflow Sequence

```mermaid
graph TD
    A[monthly-submission-check<br/>1st of month, 9 AM UTC] -->|Runs annotation review| B{New cell lines?}
    B -->|Yes| C[Create annotation PR<br/>submissions/cell_lines/annotation_*.json]
    B -->|No| D[Create monthly issue<br/>label: tool-submissions]
    C --> D
    D -->|Reviewer closes issue| E[publication-mining]
    E -->|Creates PR| F[PR Review & Merge<br/>move submissions/{type}/ → submissions/{type}/accepted/]
    F -->|push triggers| G[upsert-tools]
    F -->|merge triggers| H[score-tools]
    G -->|Uploads to Synapse| H
    H -->|workflow_run| I[update-observation-schema]
    I -->|Creates PR if changes| J[Final Review]
```

## Detailed Flow

### 1. Monthly Submission Check (Entry Point)
**Workflow**: `monthly-submission-check.yml`
**Trigger**: Schedule (1st of month, 9 AM UTC)
**Creates**: Annotation PR (if new cell lines) + monthly issue

1. Runs `scripts/review_tool_annotations.py`
2. Converts new cell line suggestions → `submissions/cell_lines/annotation_*.json`
3. Creates annotation PR (label: `annotation-submissions`) if new cells found
4. Creates monthly issue (label: `tool-submissions`) with:
   - Annotation review results and link to annotation PR
   - Formspark submission review checklist

**Manual Action Required**:
- Review the annotation PR: confirm cell line names are real NF-relevant cell lines
- Check Formspark dashboard for new form submissions; process with `process_formspark_export.py`
- Move accepted files: `git mv submissions/{type}/*.json submissions/{type}/accepted/`
- Close the monthly issue when done (triggers next step)

**Next Step**: Closing the monthly issue → triggers `publication-mining`

---

### 2. Publication Mining
**Workflow**: `publication-mining.yml`
**Trigger**: Monthly issue closed with label `tool-submissions`
**Creates PR**: Yes (label: `tool-submissions`)

Mines NF Portal and PubMed publications for novel tools:
- Filters for research-focused publications (excludes clinical case reports, reviews)
- Checks PMC full text availability
- Maintains cache of reviewed publications for incremental processing
- Validates findings with AI (optional)
- Formats mined tools as JSON in `submissions/{type}/`
- Extracts observations into `submissions/{type}/observations/`

**Next Step**: Reviewer moves accepted files to `submissions/{type}/accepted/`, then merges PR → triggers `upsert-tools` (via push) and `score-tools` (via PR merge)

---

### 3. Upsert Tools to Synapse
**Workflow**: `upsert-tools.yml`
**Trigger**: Push to main with files in `submissions/*/accepted/`
**Creates PR**: No (uploads directly to Synapse)

Compiles accepted JSON submissions and uploads to Synapse tables.

---

### 4. Calculate Completeness Scores
**Workflow**: `score-tools.yml`
**Trigger**: PR merge with label `tool-submissions`
**Creates PR**: No (uploads directly to Synapse)

Calculates tool completeness scores and uploads to Synapse tables.

**Next Step**: When workflow completes → triggers `update-observation-schema`

---

### 5. Update Observation Schema
**Workflow**: `update-observation-schema.yml`
**Trigger**: `workflow_run` (after `score-tools` completes)
**Creates PR**: Only if schema changes detected

Updates observation schema with latest tool data from Synapse.

**End of Chain**: Final step in the sequence

## Technical Implementation

### Issue Close Trigger (publication-mining)

`publication-mining.yml` uses this pattern:

```yaml
on:
  issues:
    types: [closed]
  workflow_dispatch:

jobs:
  mine-publications:
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'issues' &&
       contains(github.event.issue.labels.*.name, 'tool-submissions'))
```

### PR Merge Triggers (score-tools)

Later workflows use this pattern:

```yaml
on:
  pull_request:
    types: [closed]
    branches:
      - main
  workflow_dispatch:

jobs:
  workflow-name:
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'pull_request' &&
       github.event.pull_request.merged == true &&
       contains(github.event.pull_request.labels.*.name, 'expected-label'))
```

### Label-Based Coordination

| Workflow | Checks for Label | Creates issue/PR with Label |
|----------|-----------------|----------------------|
| monthly-submission-check | N/A (entry point - scheduled) | `tool-submissions` (issue), `annotation-submissions` (PR if new cells) |
| publication-mining | `tool-submissions` (issue closed) | `tool-submissions` |
| upsert-tools | N/A (path trigger: `submissions/*/accepted/`) | N/A (no PR) |
| score-tools | `tool-submissions` | N/A (no PR) |
| update-observation-schema | N/A (workflow_run) | `schema-update` |

### submissions/{type}/ → submissions/{type}/accepted/ Review Flow

All tool sources (mining, form submissions, annotation review) produce JSON files in `submissions/{type}/`:

```
submissions/
  cell_lines/
    annotation_NF90-8.json        ← from annotation review
    form_abc123_NF90-8.json       ← from Formspark export
    pmid12345678_NF90-8.json      ← from publication mining
    accepted/                     ← reviewer moves files here
      annotation_NF90-8.json
    observations/                 ← per-tool observations (read-only, from mining)
  animal_models/
    accepted/
    observations/
  ...
```

When `submissions/*/accepted/**/*.json` is pushed to main, `upsert-tools.yml` triggers:
1. Compiles `submissions/{type}/accepted/**/*.json` → `ACCEPTED_*.csv`
2. Validates CSV schemas
3. Uploads to Synapse tables

## Manual Trigger Guide

All workflows support manual triggers via `workflow_dispatch`:

### To Run Entire Chain Manually:

1. **Trigger**: `monthly-submission-check`
   - Go to Actions → Monthly Tool Submission Check → Run workflow
   - Wait for completion

2. **Review annotation PR** (if created)
   - Confirm cell line names are real NF-relevant cell lines
   - Move valid files to `submissions/cell_lines/accepted/` or delete if not a cell line

3. **Review Formspark submissions**
   - Export from dashboard → run `process_formspark_export.py`
   - Move accepted files to `submissions/{type}/accepted/`

4. **Close the monthly issue**
   - Triggers `publication-mining` automatically

5. **Automatic**: `publication-mining` runs
   - Mines NF Portal and PubMed publications
   - Creates PR with mined tools in `submissions/{type}/`

6. **Review & merge PR**
   - Move accepted tools from `submissions/{type}/` → `submissions/{type}/accepted/`
   - Merging triggers `upsert-tools` (path-based) and `score-tools` (label-based)

7. Continue through remaining workflows

### To Test Single Workflow:

1. Go to Actions tab
2. Select workflow to test
3. Click "Run workflow"
4. Provide inputs if needed
5. Run on your branch

## Monitoring the Chain

### Check Progress

1. **Actions Tab**: See all running/completed workflows
2. **Issues**: Filter by `tool-submissions` label for monthly issues
3. **Pull Requests**: Filter by labels to see chain PRs

### Troubleshooting Breaks

If a workflow doesn't trigger:

1. **publication-mining**: Check that the issue has `tool-submissions` label and was closed
2. **score-tools**: Check PR was merged (not just closed) and has `tool-submissions` label
3. **Check workflow permissions** in Settings
4. **Review Actions logs** for errors
5. **Verify secrets** are configured correctly

## Best Practices

### For Reviewers

1. **Annotation review**: Verify cell line names are real, NF-relevant (not sample IDs or typos)
2. **Formspark submissions**: Check for new submissions before closing the monthly issue
3. **Mining PR**: Inspect `submissions/{type}/` JSON files — move valid tools to `submissions/{type}/accepted/`, delete rejects
4. **Look for anomalies** in suggested values
5. **Read workflow logs** if something looks wrong

### For Maintainers

1. **Monitor Actions tab** regularly
2. **Set up notifications** for failed workflows
3. **Close monthly issues promptly** to keep chain moving
4. **Check labels** are correct on issues and PRs
5. **Update secrets** before they expire

### For Developers

1. **Test changes** with manual triggers first
2. **Don't modify labels** used for coordination
3. **Keep conditionals** in sync with labels
4. **Document changes** in workflow files
5. **Update this documentation** when changing flows

## Related Documentation

- **Workflow details**: [`.github/workflows/README.md`](../.github/workflows/README.md)
- **Tool annotation review**: [`TOOL_ANNOTATION_REVIEW.md`](TOOL_ANNOTATION_REVIEW.md)
- **Tool coverage**: [`../tool_coverage/README.md`](../tool_coverage/README.md)
- **Scripts**: [`../scripts/README.md`](../scripts/README.md)
