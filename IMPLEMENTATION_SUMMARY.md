# Tool Annotation Review Implementation Summary

## Overview
This implementation separates tool-related annotation field review from the nf-metadata-dictionary repository into nf-research-tools-schema for better efficiency and workflow coordination.

## What Was Implemented

### 1. Tool Annotation Review Script
**File**: `scripts/review_tool_annotations.py`

- Reviews tool-related annotation fields from Synapse materialized view (syn52702673)
- Implements two-stage synonym detection:
  - First checks against nf-research-tools-schema values
  - Then checks metadata dictionary enums including aliases
- Prevents suggesting values that are already defined as synonyms
- Generates suggestions only for new, unrecognized values

**Tool-related fields reviewed** (19 fields):
- Tool identifiers: `animalModelID`, `cellLineID`, `antibodyID`, `geneticReagentID`
- Specimen fields: `tumorType`, `tissue`, `organ`, `species`, `sex`, `race`
- Manifestation fields: `cellLineManifestation`, `animalModelOfManifestation`
- Disease fields: `cellLineGeneticDisorder`, `animalModelGeneticDisorder`
- Other: `cellLineCategory`, `backgroundStrain`, `backgroundSubstrain`, `animalModelNFGene`, `antibodyUsageType`

### 2. Automated Workflow
**File**: `.github/workflows/review-tool-annotations.yml`

- Runs weekly via workflow_run trigger (after tool coverage check completes)
- Has fallback schedule: Monday 10 AM UTC
- Creates pull requests when new values are found
- Assignee: BelindaBGarana

### 3. Workflow Coordination with workflow_run Triggers

Implemented dependency chain using GitHub Actions `workflow_run` triggers:

```
check-tool-coverage (Monday 9 AM UTC - entry point)
   ↓ workflow_run trigger (on completion)
review-tool-annotations (+ fallback schedule Monday 10 AM)
   ↓ workflow_run trigger (on completion)
link-tool-datasets
   ↓ workflow_run trigger (on completion)
score-tools
   ↓ workflow_run trigger (on completion)
update-observation-schema
```

**Benefits**:
- Explicit dependency management
- No race conditions or overlapping workflows
- Workflows only run when prerequisites complete
- All workflows retain `workflow_dispatch` for manual triggering
- Clear execution order visible in workflow configuration

### 4. Metadata Dictionary Updates
**Repository**: nf-metadata-dictionary

- Modified `utils/review_annotations.py` to exclude 19 tool-related fields
- Tool fields are now reviewed in nf-research-tools-schema instead
- Prevents duplicate suggestions across repositories

### 5. Documentation
- `docs/TOOL_ANNOTATION_REVIEW.md`: Comprehensive guide to the review process
- `docs/WORKFLOW_COORDINATION.md`: Workflow dependency chain documentation
- `scripts/README.md`: Script usage and purpose
- Updated repository README with workflow information

## Testing Results

✅ All tests passed:
- Tool annotation script loads 41 fields from tools schema
- Loads 109 enums from metadata dictionary (for synonym checking)
- Properly excludes tool fields from metadata dictionary review
- Two-stage checking prevents suggesting existing aliases

## Synapse Resources
- **Materialized View**: [syn52702673](https://www.synapse.org/Synapse:syn52702673)
- **Tools Schema**: nf_research_tools.rdb.model.csv

## Related Issues
- Addresses workflow coordination per nf-research-tools-schema#97
- Implements annotation review separation per nf-metadata-dictionary discussion

## Configuration
- **Minimum frequency**: 2 occurrences required for value to be suggested
- **Review scope**: Tool-related fields only
- **Output format**: JSON (machine-readable) + Markdown (human-readable)
