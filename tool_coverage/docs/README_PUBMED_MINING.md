# PubMed Mining for NF Publications

Automated workflow to mine PubMed for neurofibromatosis-related research articles.

## Overview

This workflow implements **Step 1** from [Issue #97](https://github.com/nf-osi/nf-research-tools-schema/issues/97):
> Add NF-related publications from PubMed to NF tools publication table (syn26486839)

## Workflows

### 1. `mine-pubmed-nf.yml` - Mine Publications

**What It Does:**

1. **Searches PubMed** for neurofibromatosis-related articles:
   - neurofibromatosis, NF1, NF2, schwannomatosis
   - Research articles only (excludes reviews)
   - **Free full text available** (PMC articles)

2. **Checks for duplicates** against existing publications in syn26486839

3. **Extracts Metadata**:
   - PMID, DOI
   - Title, journal, year
   - PMC ID (for full text access)
   - Publication types

4. **Creates PR** with results in `tool_coverage/outputs/pubmed_nf_publications.csv`

**Schedule:**
- **Weekly**: Sundays at 9 AM UTC (runs before Monday's tool coverage workflow)
- **Manual**: Can be triggered via GitHub Actions UI

### 2. `upsert-pubmed-publications.yml` - Add to Synapse

**What It Does:**

1. Triggers automatically when PR from mining workflow is **merged**
2. **Checks for duplicates** to avoid re-adding existing publications
3. **Upserts** new publications to Synapse table syn26486839
4. **Comments on PR** with results and next steps

**Note:** Publications are added without usage/development classification. This requires manual review.

### Parameters (Manual Trigger)

- `max_results`: Maximum publications to retrieve (default: 1000)
- `years`: Year range filter (e.g., `2020:2024`)

## Script: `mine_pubmed_nf.py`

### Usage

```bash
# Basic usage
python tool_coverage/scripts/mine_pubmed_nf.py

# Limit results
python tool_coverage/scripts/mine_pubmed_nf.py --max-results 500

# Filter by year range
python tool_coverage/scripts/mine_pubmed_nf.py --years 2020:2024

# Custom output location
python tool_coverage/scripts/mine_pubmed_nf.py --output custom_output.csv
```

### Search Criteria

The script searches for:
- **Keywords**: neurofibromatosis, NF1, NF2, schwannomatosis (in title/abstract)
- **Has abstract**: Yes
- **Free full text**: Available (PMC)
- **Excludes**: Reviews, systematic reviews

### Output Format

CSV file with columns:
- `pmid`: PubMed ID (format: PMID:12345678)
- `doi`: Digital Object Identifier
- `title`: Article title
- `journal`: Journal name
- `year`: Publication year
- `pmc_id`: PMC ID for full text access
- `publication_types`: Article types (separated by |)

## Complete Workflow

1. **Mining** (Automated - Weekly)
   - `mine-pubmed-nf.yml` runs on Sundays
   - Mines PubMed for new NF publications with free full text
   - Checks for duplicates against syn26486839
   - Creates PR with results

2. **Review** (Manual)
   - Review PR to verify publications are relevant
   - Check that duplicates were properly filtered
   - Merge PR if approved

3. **Upsert** (Automated - On PR Merge)
   - `upsert-pubmed-publications.yml` triggers automatically
   - Adds new publications to syn26486839
   - Double-checks for duplicates before adding
   - Comments on PR with success/failure status

4. **Classification** (Manual - Future)
   - Classify publications in syn26486839 as:
     - Tool usage (link in syn26486841)
     - Tool development (link in syn26486807)
   - Can be done manually or via future automation

5. **Tool Mining** (Automated - Weekly)
   - Tool coverage workflow (#92) runs on Mondays
   - Mines these publications for research tools
   - Creates PR with discovered tools

## Dependencies

- `requests`: HTTP requests to PubMed API
- `pandas`: Data processing and CSV output
- `xml.etree.ElementTree`: Parse PubMed XML responses

## API Rate Limits

The script respects NCBI E-utilities guidelines:
- Maximum 3 requests/second (implemented via 0.5s delays)
- Batches requests (200 PMIDs per fetch)
- Includes email and tool identification

## Troubleshooting

**No results found:**
- Check search terms match expected publications
- Verify year range if specified
- Ensure PubMed API is accessible

**Timeout errors:**
- Large result sets may take time
- Use `--max-results` to limit query size
- Check network connectivity

## Related Workflows

1. **This workflow** - Mine PubMed for NF publications (#97 Step 1)
2. **check-tool-coverage.yml** - Mine existing publications for tools (#92)
3. **upsert-tools.yml** - Upload discovered tools to Synapse

## References

- [Issue #97](https://github.com/nf-osi/nf-research-tools-schema/issues/97)
- [NF Research Tools Database](https://www.synapse.org/Synapse:syn26486839)
- [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
