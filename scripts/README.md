# Scripts Documentation

This directory contains utility scripts for maintaining the NF Research Tools schema and database.

## Scripts

### review_tool_annotations.py

**Purpose:** Analyzes tool-related file annotations from Synapse to identify values that should be standardized in the tools schema.

**Features:**
- Queries Synapse materialized view (syn52702673) for file annotations
- Focuses on tool-specific fields (animalModelID, cellLineID, antibodyID, geneticReagentID, tumorType, tissue, organ, species, etc.)
- Checks values against both:
  - Tools schema valid values (`nf_research_tools.rdb.model.csv`)
  - Metadata dictionary enums (including synonyms/aliases)
- Generates suggestions only for truly novel values
- Creates JSON and Markdown output files with frequency counts

**Usage:**
```bash
# Basic usage (requires Synapse authentication)
export SYNAPSE_AUTH_TOKEN=your_token
python scripts/review_tool_annotations.py

# Dry run to preview results
python scripts/review_tool_annotations.py --dry-run

# Test with limited records
python scripts/review_tool_annotations.py --limit 1000 --dry-run

# Custom output files
python scripts/review_tool_annotations.py \
  --output my_suggestions.json \
  --markdown my_summary.md
```

**Automated Workflow:**
- Runs weekly on Mondays at 10:00 AM UTC
- Creates PRs with suggestions when new values are found
- Workflow file: `.github/workflows/review-tool-annotations.yml`

**Related Documentation:**
- [`../docs/TOOL_ANNOTATION_REVIEW.md`](../docs/TOOL_ANNOTATION_REVIEW.md) - Comprehensive guide
- [Metadata Dictionary Annotation Review](https://github.com/nf-osi/nf-metadata-dictionary/blob/main/docs/annotation-review-workflow.md) - Related workflow for non-tool fields

### update_observation_schema.py

**Purpose:** Updates the observation schema based on changes to the tools database.

**Usage:**
```bash
python scripts/update_observation_schema.py
```

### link_tool_datasets.py

**Purpose:** Links tools to associated datasets in Synapse.

**Usage:**
```bash
python scripts/link_tool_datasets.py
```

### upsert_tool_datasets.py

**Purpose:** Upserts tool dataset links to Synapse tables.

**Usage:**
```bash
python scripts/upsert_tool_datasets.py
```

## Dependencies

Most scripts require:
```bash
pip install synapseclient pandas pyyaml
```

## Authentication

Scripts that interact with Synapse require authentication:

```bash
# Set environment variable (preferred for automation)
export SYNAPSE_AUTH_TOKEN=your_token

# Or use Synapse client auto-login (local development)
synapse login
```

## See Also

- [`../tool_coverage/scripts/`](../tool_coverage/scripts/) - Scripts for mining publications and analyzing tool coverage
- [`../.github/workflows/`](../.github/workflows/) - Automated workflow definitions
- [`../docs/`](../docs/) - Comprehensive documentation

---

*For questions or issues with scripts, please open a GitHub issue.*
