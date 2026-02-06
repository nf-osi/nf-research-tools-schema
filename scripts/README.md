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

**Used by**: `review-tool-annotations.yml` workflow

**Documentation**: See [`docs/TOOL_ANNOTATION_REVIEW.md`](../docs/TOOL_ANNOTATION_REVIEW.md)

---

### Dataset Linking

**`link_tool_datasets.py`**
- Links datasets to tools via publication relationships
- Queries NF Portal for publication-tool relationships
- Creates SUBMIT_tool_datasets.csv for Synapse upload

**Used by**: `link-tool-datasets.yml` workflow

**`upsert_tool_datasets.py`**
- Uploads tool-dataset linkages to Synapse
- Handles data validation and error checking

---

### Schema Management

**`update_observation_schema.py`**
- Syncs SubmitObservationSchema.json with Synapse data
- Updates resourceType and resourceName enums
- Creates conditional enums based on resource type

**Used by**: `update-observation-schema.yml` workflow

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

### Link Tool Datasets
```bash
python scripts/link_tool_datasets.py
```

### Update Observation Schema
```bash
python scripts/update_observation_schema.py
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
