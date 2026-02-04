# Dataset Linking Workflows

## Overview

We have a two-stage automated workflow which runs weekly:

1. **Discovery & Proposal** (`link-tool-datasets.yml`): Identifies Synapse projects (studyId) associated with NF tools and creates a PR with suggested tool-dataset relationships
2. **Database Update** (`upsert-tool-datasets.yml`): When the PR is merged, automatically updates the database with the approved relationships

## Workflow Process

### Stage 1: Link Tool Datasets Workflow

**File:** `.github/workflows/link-tool-datasets.yml`
**Script:** `scripts/link_tool_datasets.py` (325 lines)

This workflow runs on a weekly schedule and:
1. Queries Synapse to find projects (studyId) associated with NF research tools
2. Identifies datasets within those projects
3. Generates suggested tool-dataset relationships
4. **Creates a PR** if any new relationships are found

The PR contains the proposed dataset linkages for manual review and approval.

### Stage 2: Upsert Tool Datasets Workflow

**File:** `.github/workflows/upsert-tool-datasets.yml`
**Script:** `scripts/upsert_tool_datasets.py` (628 lines)

This workflow is triggered when a PR from Stage 1 is **merged** and:
1. Processes the approved dataset-tool relationships
2. Upserts (inserts or updates) the data into the database
3. Ensures data consistency and integrity
4. Updates dataset metadata from Synapse

## Monitoring

### View Weekly Discovery PRs
```bash
# View PRs created by the link-tool-datasets workflow
gh pr list --author=github-actions --label=dataset-linking
```

### Check Workflow Status
```bash
# View recent discovery workflow runs
gh run list --workflow=link-tool-datasets.yml

# View recent upsert workflow runs (triggered by PR merges)
gh run list --workflow=upsert-tool-datasets.yml
```