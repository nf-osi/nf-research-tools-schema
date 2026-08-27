# Scripts

This directory contains scripts for workflow automation and data management.

## Script Overview

### Tool Annotation Review

**`review_tool_annotations.py`**
- Analyzes individualID annotations from Synapse syn52702673
- Compares against tools in syn51730943
- Suggests new cell lines and synonyms using fuzzy matching
- Analyzes facet configuration for search improvements
- Outputs JSON suggestions and markdown reports
- Also mines two further automations -- additive-only, but requiring manual
  CSV review before either is applied (nf-research-tools-schema#132, #154,
  #246): tool<->study links to syn26461958, and a Resource_id
  file-annotation backfill on syn16858331. See `--apply-tool-study-links-csv`
  / `--apply-resource-id-annotations-csv` and the "Tool<->Study Links and
  Resource_id Backfill" and "Cross-Project Table Dependencies" sections of
  [`docs/TOOL_ANNOTATION_REVIEW.md`](../docs/TOOL_ANNOTATION_REVIEW.md)

**Used by**: `review-tool-annotations.yml` workflow

**Documentation**: See [`docs/TOOL_ANNOTATION_REVIEW.md`](../docs/TOOL_ANNOTATION_REVIEW.md)

---

### Dataset Linking

**`mine_tool_dataset_links.py`**
- Populates `syn16859448` (Tool_Dataset), the tool<->dataset junction table
  the frontend's Tool Details "Data" tab reads to list linked datasets
  (nf-research-tools-schema#252)
- For each Dataset entity in the Portal Dataset Collection (`syn50913342`),
  queries that dataset's own item table for `individualID` (Cell Line) and
  `modelSystemName` (Animal Model) values, matching against known tools
  using the same disambiguation-aware lookup as
  `review_tool_annotations.py`'s tool<->study link mining
- Additive-only, but **not auto-upserted** -- same review-then-apply policy
  as `review_tool_annotations.py` (see `--apply-tool-dataset-links-csv`)
- The mining/dry-run path doesn't need `SYNAPSE_AUTH_TOKEN` -- all of its
  source tables (tools view, dataset collection, each Dataset entity) are
  public. Only `--apply-tool-dataset-links-csv` (the write step) requires it.
- Per-dataset queries run concurrently (`--workers`, default 8) via a thread
  pool -- confirmed live, this is ~7x faster than sequential (~87s vs. ~590s
  across the full collection) with no throttling, as long as it does NOT
  call `getTableColumns` first (that endpoint has its own much stricter
  server-side rate limit -- see the module docstring for the full story)
- `--dataset-id` (repeatable) limits mining to specific dataset(s) instead
  of the full collection -- e.g. to review newly-added datasets without
  re-scanning ones already reviewed

**`upsert_tool_datasets.py`**
- Legacy script from the pre-submission-based, PMID-keyed tool-publications
  pipeline (writes a `datasets` column onto `syn26486839` and a separate
  `NFToolDatasets` table); expects a hand-produced `SUBMIT_tool_datasets.csv`
  and is unrelated to `syn16859448`/`mine_tool_dataset_links.py` above

---

### Schema Management

**`update_observation_schema.py`**
- Syncs SubmitObservationSchema.json with Synapse data
- Updates resourceType and resourceName enums
- Creates conditional enums based on resource type

**Used by**: `update-observation-schema.yml` workflow

---

### Staging a live table/MV change

**`snapshot_synapse_tables.py`**
- Creates versioned snapshots of a set of Synapse tables/views and writes a
  JSON rollback manifest (entity id, name, `versionNumber`, `etag`,
  `columnIds`, and `definingSQL` where present) plus a markdown summary
  table for pasting into a tracking issue
- Table selection: `--table-id` (repeatable, explicit ids), `--from-schema`
  (every `synapse_table_id`-annotated class in the LinkML schema), or
  `--class-name` (repeatable, specific schema classes only) — reuses
  `check_referential_integrity.py`'s schema-driven table map as the single
  source of truth rather than hardcoding a duplicate id list
- `--dry-run` resolves and prints the table list with no Synapse access
- Step 1 of the staging procedure documented in
  [`docs/STAGING_PROCEDURE.md`](../docs/STAGING_PROCEDURE.md) (formalizes
  the ad hoc snapshot-then-record-fallback-plan work done in #261)

**Used by**: the staging procedure in `docs/STAGING_PROCEDURE.md`, manually
invoked before any live change to the tools search MV chain

---

## Tool Coverage Scripts

More complex mining and validation scripts are in `tool_coverage/scripts/`:

- `fetch_fulltext_and_mine.py` - PubMed mining
- `run_publication_reviews.py` - AI validation
- `format_mining_for_submission.py` - Format mining results
- `clean_submission_csvs.py` - Validate and upload to Synapse
- And more...

See [`tool_coverage/README.md`](../tool_coverage/README.md) for details.

## Usage Examples

### Review Tool Annotations
```bash
# Full run
python scripts/review_tool_annotations.py

# With limit (testing)
python scripts/review_tool_annotations.py --limit 1000

# Dry run (no files saved)
python scripts/review_tool_annotations.py --dry-run
```

### Mine Tool<->Dataset Links
```bash
# Mine candidates, write tool_dataset_links_for_review.csv
python scripts/mine_tool_dataset_links.py

# With limit (testing)
python scripts/mine_tool_dataset_links.py --limit 1000

# After reviewing the CSV, upsert survivors to syn16859448
python scripts/mine_tool_dataset_links.py --apply-tool-dataset-links-csv tool_dataset_links_for_review.csv

# Review specific (e.g. newly-added) datasets only, skipping the full collection scan
python scripts/mine_tool_dataset_links.py --dataset-id syn123 --dataset-id syn456
```

### Update Observation Schema
```bash
python scripts/update_observation_schema.py
```

### Snapshot Tables Before a Staged Change
```bash
# See what would be snapshotted, no Synapse access
python scripts/snapshot_synapse_tables.py --from-schema --comment "x" --dry-run

# Snapshot every schema-mapped detail table
python scripts/snapshot_synapse_tables.py --from-schema \
    --comment "pre-migration snapshot for #262"

# Snapshot specific classes, or arbitrary non-schema-mapped entities (e.g. MVs)
python scripts/snapshot_synapse_tables.py --class-name CellLine --class-name AnimalModel \
    --comment "pre-migration snapshot for #262"
python scripts/snapshot_synapse_tables.py --table-id syn77019684 --table-id syn51730943 \
    --comment "pre-migration snapshot for #262"
```

## Requirements

Most scripts require:
- `synapseclient` - Synapse API client
- `pandas` - Data manipulation
- Environment variable: `SYNAPSE_AUTH_TOKEN`

Install with:
```bash
pip install synapseclient pandas
```

## Related Documentation

- **Workflows**: [`.github/workflows/README.md`](../.github/workflows/README.md)
- **Workflow coordination**: [`docs/WORKFLOW_COORDINATION.md`](../docs/WORKFLOW_COORDINATION.md)
- **Tool coverage**: [`tool_coverage/README.md`](../tool_coverage/README.md)
