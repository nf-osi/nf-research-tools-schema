# Tool Annotation Review Workflow

## Overview

The tool annotation review workflow automatically analyzes tool-related file annotations from Synapse to identify free-text values that should be standardized in the NF Research Tools schema. This workflow complements the metadata dictionary annotation review by focusing specifically on fields relevant to research tools (animal models, cell lines, antibodies, genetic reagents).

**Workflow:** `.github/workflows/review-tool-annotations.yml`
**Script:** `scripts/review_tool_annotations.py`
**Schedule:** Runs weekly on Mondays at 10:00 AM UTC (1 hour after metadata dictionary sync)

## Why Separate from Metadata Dictionary?

Tool-related annotations are reviewed in this repository rather than in nf-metadata-dictionary for several reasons:

1. **Efficiency**: Tool annotations are already being synced from Synapse tables in this repository
2. **Organization**: Tool schema updates are managed alongside tool database maintenance
3. **No Duplication**: Avoids reviewing the same fields in two different repositories
4. **Clear Separation**: Metadata dictionary focuses on file/dataset annotations, this repo focuses on research tool metadata

## Tool-Related Fields Reviewed

The workflow analyzes the following annotation fields:

### Tool Identifiers
- `animalModelID` - Links to animal model resources
- `cellLineID` - Links to cell line resources
- `antibodyID` - Links to antibody resources
- `geneticReagentID` - Links to genetic reagent resources

### Specimen/Biobank Fields
- `tumorType` - Type of tumor in specimens
- `tissue` - Tissue type
- `organ` - Organ of origin
- `species` - Species of the specimen/tool

### Manifestation Fields
- `cellLineManifestation` - Clinical manifestations modeled by cell lines
- `animalModelOfManifestation` - Symptoms/phenotypes in animal models
- `animalModelManifestation` - Alternative manifestation field

### Disease Fields
- `cellLineGeneticDisorder` - Genetic disorders in cell lines
- `animalModelGeneticDisorder` - Genetic disorders in animal models
- `animalModelDisease` - Disease associations

### Other Tool-Specific Fields
- `cellLineCategory` - Classification of cell lines
- `backgroundStrain` - Genetic background of animal models
- `backgroundSubstrain` - Specific substrain information
- `sex` - Sex of donor/model (in tool context)
- `race` - Ethnicity of donor (in tool context)

## How It Works

### 1. Data Sources

The script loads and checks values against multiple sources:

**Tools Schema** (`nf_research_tools.rdb.model.csv`):
- Contains valid values defined in the tools database schema
- 41 fields with controlled vocabularies

**Metadata Dictionary** (from sibling repository):
- Contains enum definitions with synonyms/aliases
- 109 enums loaded for cross-checking
- Prevents suggesting values that are already defined as aliases

### 2. Analysis Process

```python
# For each annotation value:
1. Check if value is in tools schema valid values ✓
2. Check if value is in metadata dictionary enums (including aliases) ✓
3. If found in neither → Add to suggestions
4. Track frequency of each unique value
5. Filter by minimum frequency threshold (≥2)
```

### 3. Synonym Detection

The script performs **two-stage checking** to avoid suggesting synonyms:

```python
# Example: species = "Mouse"
1. Check tools schema: "Mouse" in species valid values? → No
2. Check metadata dictionary: "Mouse" is alias of "Mus musculus"? → Check enums
3. If found as synonym → Don't suggest
4. If not found anywhere → Suggest as new value
```

This prevents suggesting values like "Human" when "Homo sapiens" is already defined with "Human" as an alias.

## Script Usage

### Prerequisites

```bash
# Install dependencies
pip install synapseclient pandas pyyaml

# Set Synapse authentication
export SYNAPSE_AUTH_TOKEN=your_token
```

### Basic Usage

```bash
# Run full analysis (requires Synapse auth)
cd /path/to/nf-research-tools-schema
python scripts/review_tool_annotations.py

# Dry run - preview without creating files
python scripts/review_tool_annotations.py --dry-run

# Test with limited records
python scripts/review_tool_annotations.py --limit 1000 --dry-run

# Custom output files
python scripts/review_tool_annotations.py \
  --output suggestions.json \
  --markdown summary.md
```

### Output Files

**tool_annotation_suggestions.json** - Structured data:
```json
{
  "suggestions": {
    "species": {
      "Novel Species Name": 5,
      "Another Species": 3
    },
    "tumorType": {
      "Novel Tumor Type": 12
    }
  },
  "filters": {
    "cellLineCategory": 8,
    "species": 15
  },
  "materialized_view": "syn52702673",
  "tool_fields_reviewed": ["animalModelID", "cellLineID", ...]
}
```

**tool_annotation_suggestions.md** - Human-readable summary:
```markdown
# Tool Annotation Review - Schema Updates from Synapse Annotations

## Suggested Value Additions

### Field: `species`
- `Novel Species Name` (used 5 times)
- `Another Species` (used 3 times)

### Field: `tumorType`
- `Novel Tumor Type` (used 12 times)

## Suggested Search Filters
- `cellLineCategory` (8 unique values)
- `species` (15 unique values)
```

## Automated Workflow

### Schedule

The workflow runs automatically:
- **Every Monday at 10:00 AM UTC**
- 1 hour after the metadata dictionary annotation review
- Can be manually triggered via GitHub Actions

### Manual Triggering

**Via GitHub CLI:**
```bash
# Run full workflow
gh workflow run review-tool-annotations.yml

# Test with limited records
gh workflow run review-tool-annotations.yml \
  -f annotation_limit=1000
```

**Via GitHub UI:**
1. Go to Actions tab
2. Select "Weekly Tool Annotation Review"
3. Click "Run workflow"
4. Optional: Set `annotation_limit` for testing

### Workflow Steps

1. **Checkout repository** - Get latest code
2. **Set up Python** - Install Python 3.10
3. **Install dependencies** - synapseclient, pandas, pyyaml
4. **Review annotations** - Run analysis script
5. **Create PR** - If suggestions found, create pull request with:
   - `tool_annotation_suggestions.json`
   - `tool_annotation_suggestions.md`
   - Branch: `tool-annotation-review-YYYYMMDD`
   - Labels: `automated`, `annotation-review`

### Pull Request Format

**Title:** Tool Annotation Review - 2026-02-05 10:00:00 UTC

**Body:**
- Summary of findings
- Number of fields with suggestions
- List of tool-related fields reviewed
- Links to suggestion files
- Reminder about minimum frequency threshold
- Context about integration with tools sync

## Reviewing Suggestions

### When a PR is Created

1. **Review the suggestions:**
   - Check `tool_annotation_suggestions.md` for summary
   - Review `tool_annotation_suggestions.json` for detailed counts

2. **Evaluate each suggestion:**
   - Is this a legitimate new value or a typo?
   - Should it be added to the tools schema?
   - Should it be added to metadata dictionary (with synonym)?
   - Does it need standardization (e.g., "Mouse" → "Mus musculus")?

3. **Take action:**

   **Option A: Add to tools schema** (for tool-specific values)
   ```csv
   # Edit nf_research_tools.rdb.model.csv
   Attribute,Description,Valid Values,...
   species,Species of model,"Mouse, Rat, ..., Novel Species Name"
   ```

   **Option B: Add to metadata dictionary** (for general values)
   ```yaml
   # In nf-metadata-dictionary/modules/Sample/BodyPart.yaml
   SpeciesEnum:
     permissible_values:
       Novel Species Name:
         description: A newly supported species
   ```

   **Option C: Add as alias** (for synonyms)
   ```yaml
   # In metadata dictionary
   SpeciesEnum:
     permissible_values:
       Mus musculus:
         aliases:
           - Mouse
           - mouse
   ```

4. **Merge or close PR:**
   - Merge if you've made schema updates in separate commits
   - Close with comment explaining decision
   - Document rationale for future reference

### Handling False Positives

Common cases:

**Typos/Variations:**
- "Mus musculus" vs "mus musculus" (case differences)
- "NF1" vs "NF-1" (punctuation)

**Solution:** Add as aliases in metadata dictionary

**Data Quality Issues:**
- Inconsistent naming conventions
- Deprecated terms
- Legacy identifiers

**Solution:** Coordinate with data contributors to fix at source

## Configuration

### Script Configuration

Edit `scripts/review_tool_annotations.py`:

```python
# Synapse materialized view
MATERIALIZED_VIEW_ID = "syn52702673"

# Tool-related fields to review
TOOL_RELATED_FIELDS = {
    'animalModelID',
    'cellLineID',
    # ... full list
}

# Minimum frequency for suggestions
MIN_FREQUENCY = 2

# Minimum diversity for filter suggestions
MIN_FILTER_FREQUENCY = 5
```

### Workflow Configuration

Edit `.github/workflows/review-tool-annotations.yml`:

```yaml
# Schedule (runs Monday 10:00 AM UTC)
on:
  schedule:
    - cron: '0 10 * * 1'

# Required secret
env:
  SYNAPSE_AUTH_TOKEN: ${{ secrets.SYNAPSE_AUTH_TOKEN }}
```

## Integration with Other Workflows

### Related Workflows

| Workflow | Repository | Purpose | Schedule |
|----------|-----------|---------|----------|
| **Tool Annotation Review** | nf-research-tools-schema | Review tool annotations | Mon 10:00 AM UTC |
| **Metadata Annotation Review** | nf-metadata-dictionary | Review file annotations | Mon 9:00 AM UTC |
| **Model System Sync** | nf-metadata-dictionary | Sync model systems | Mon 9:00 AM UTC |
| **Tool Coverage Mining** | nf-research-tools-schema | Mine publications for tools | On-demand |

### Workflow Coordination

```
Monday 9:00 AM UTC
├─ nf-metadata-dictionary: Model System Sync + Annotation Review
│  └─ Reviews non-tool annotation fields
│  └─ Updates metadata dictionary enums
│
Monday 10:00 AM UTC (1 hour later)
└─ nf-research-tools-schema: Tool Annotation Review
   └─ Reviews tool-specific annotation fields
   └─ Generates suggestions for tools schema
```

**Why 1-hour offset?**
- Ensures metadata dictionary completes first
- Allows tool review to benefit from any metadata updates
- Spreads workflow load
- Reduces chance of concurrent Synapse API limits

## Troubleshooting

### Issue: Script fails with authentication error

**Solution:**
```bash
# Check token is set
echo $SYNAPSE_AUTH_TOKEN

# Verify token is valid
synapse login -p $SYNAPSE_AUTH_TOKEN
```

### Issue: No suggestions generated

**Possible causes:**
1. All tool annotations match schema (good!)
2. Frequency threshold too high
3. Metadata dictionary sibling path incorrect

**Debug:**
```bash
# Run with verbose output
python scripts/review_tool_annotations.py --dry-run --limit 1000

# Check what was loaded
python -c "
import sys
sys.path.insert(0, 'scripts')
import review_tool_annotations as rta
schema = rta.load_tools_schema_values()
print(f'Loaded {len(schema)} fields')
print(f'Fields: {list(schema.keys())}')
"
```

### Issue: Metadata dictionary not found

**Error:** `Metadata dictionary not found at /path/to/nf-metadata-dictionary`

**Solution:**
```bash
# Ensure repositories are sibling directories
ls -la ..
# Should show both:
# - nf-metadata-dictionary/
# - nf-research-tools-schema/

# Or adjust path in script
METADATA_DICT_PATH = Path(__file__).parent.parent.parent / "nf-metadata-dictionary" / "modules"
```

### Issue: Too many suggestions

**Solutions:**
1. Increase `MIN_FREQUENCY` threshold (default: 2)
2. Add common variations as aliases in metadata dictionary
3. Improve data quality at source

## Best Practices

### 1. Regular Review
- Review PRs promptly when generated
- Don't let suggestions accumulate
- Provide feedback to data contributors

### 2. Documentation
- Document rationale for accepting/rejecting suggestions
- Add source URLs when adding new values
- Keep this guide updated with new patterns

### 3. Coordination
- Coordinate with metadata dictionary team
- Share insights about common issues
- Align on naming conventions

### 4. Quality Control
- Verify new terms against authoritative sources
- Maintain consistency with metadata dictionary
- Add ontology mappings where applicable

## Testing

### Unit Tests

See `TEST_RESULTS.md` for comprehensive test results.

**Test coverage:**
- ✅ Schema loading functions
- ✅ Synonym detection logic
- ✅ Tool field identification
- ✅ Frequency thresholding
- ✅ Output file generation

### Manual Testing

```bash
# Test with small dataset
python scripts/review_tool_annotations.py --limit 100 --dry-run

# Test specific fields
# (Edit TOOL_RELATED_FIELDS to focus on specific fields)

# Test with different frequencies
# (Edit MIN_FREQUENCY in script)
```

## Future Enhancements

Potential improvements:

1. **Automated Schema Updates**: Directly update CSV schema file
2. **ML-based Matching**: Use similarity matching for synonyms
3. **Ontology Integration**: Auto-map to biomedical ontologies
4. **Data Quality Reports**: Identify inconsistencies at source
5. **Interactive Dashboard**: Web UI for reviewing suggestions

## Reference

### Files
- `scripts/review_tool_annotations.py` - Main analysis script
- `.github/workflows/review-tool-annotations.yml` - Automated workflow
- `nf_research_tools.rdb.model.csv` - Tools schema with valid values
- `../nf-metadata-dictionary/modules/` - Metadata dictionary enums

### Documentation
- `ANNOTATION_REVIEW_SEPARATION.md` - Implementation details
- [Metadata Dictionary Annotation Review](https://github.com/nf-osi/nf-metadata-dictionary/blob/main/docs/annotation-review-workflow.md)
- `TEST_RESULTS.md` - Test results and validation

### External Resources
- [Synapse Materialized View](https://www.synapse.org/#!Synapse:syn52702673)
- [NF Research Tools Database](https://www.synapse.org/#!Synapse:syn26486839)

---

*Last Updated: 2026-02-05*
*Related Issue: Efficiency improvement for annotation review workflow*
