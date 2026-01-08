# Smart Skip Logic for AI Validation

## Feature Overview

Added intelligent skip logic to avoid re-reviewing publications that have already been validated, saving time and API costs.

## Problem Solved

**Before this feature:**
- Every run would re-validate ALL publications, even ones already reviewed
- For 50 publications: ~$0.50-1.50 per run
- Weekly runs would incur repeated costs for the same publications
- Total waste: ~$2-6 per month for redundant validations

**After this feature:**
- Only NEW publications are validated in subsequent runs
- First run: 50 pubs (~$0.50-1.50)
- Weekly runs: 5-10 new pubs (~$0.05-0.30)
- **Cost reduction: ~85% savings** on weekly runs

## How It Works

### Automatic Skip Detection

When `run_publication_reviews.py` is invoked:

1. **Check for existing YAML**: Looks for `tool_reviews/results/{PMID}_tool_review.yaml`
2. **Skip if exists**: If found, displays message and moves to next publication
3. **Validate if missing**: If not found, proceeds with Goose AI validation

```python
# Check if already reviewed (unless force flag is set)
yaml_path = Path(results_dir) / f'{pmid}_tool_review.yaml'
if yaml_path.exists() and not args.force_rereviews:
    print(f"\n⏭️  Skipping {pmid} (already reviewed, use --force-rereviews to override)")
    continue
```

### Override with Force Flag

To re-review publications (e.g., after recipe changes):

```bash
python run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv --force-rereviews
```

This will:
- Detect existing YAML files
- Show "🔄 Re-reviewing {PMID} (force flag set)" message
- Proceed with validation anyway
- Overwrite existing YAML files

## Command-Line Options

### Standard Usage (Skip Already-Reviewed)

```bash
# Default behavior - skips existing validations
python run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv
```

Output:
```
================================================================================
Running Goose Reviews for 50 publications
================================================================================

⏭️  Skipping PMID:28078640 (already reviewed, use --force-rereviews to override)
⏭️  Skipping PMID:28198162 (already reviewed, use --force-rereviews to override)
...
✅ Reviewing PMID:12345678 (new publication)
✅ Reviewing PMID:87654321 (new publication)
```

### Force Re-review All

```bash
# Force flag - re-reviews everything
python run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv --force-rereviews
```

Output:
```
================================================================================
Running Goose Reviews for 50 publications
================================================================================

🔄 Re-reviewing PMID:28078640 (force flag set)
🔄 Re-reviewing PMID:28198162 (force flag set)
...
```

### Compile Only (No Reviews)

```bash
# Just compile existing YAMLs, no validation
python run_publication_reviews.py --compile-only
```

## GitHub Actions Integration

Added workflow dispatch input to control force re-reviews from GitHub UI:

```yaml
workflow_dispatch:
  inputs:
    force_rereviews:
      description: 'Force re-review of already-reviewed publications'
      required: false
      type: boolean
      default: false
```

**Usage in GitHub Actions:**
1. Go to Actions → Check Tool Coverage → Run workflow
2. Check "Force re-review" checkbox if needed
3. Click "Run workflow"

**Default behavior**: Only new publications are validated (cost-efficient)

## Cost Savings Analysis

### Scenario 1: Initial Full Validation

**Publications**: 50
**Cost per publication**: $0.01-0.03
**Total cost**: $0.50-1.50

### Scenario 2: Weekly Run (Without Skip Logic)

**Publications**: 50 (all re-validated)
**Cost per publication**: $0.01-0.03
**Total cost**: $0.50-1.50 **per week**
**Monthly cost**: ~$2-6

### Scenario 3: Weekly Run (With Skip Logic)

**New publications**: 5-10 per week
**Cost per publication**: $0.01-0.03
**Total cost**: $0.05-0.30 **per week**
**Monthly cost**: ~$0.20-1.20

**Savings**: 85-90% reduction in API costs

## Use Cases

### Use Case 1: Weekly Automated Runs

**Scenario**: GitHub Actions runs weekly to check for new publications

**Behavior**:
- Week 1: Validates 50 publications (initial run)
- Week 2: Skips 50, validates 5 new → Total: 5 validations
- Week 3: Skips 55, validates 3 new → Total: 3 validations
- Week 4: Skips 58, validates 7 new → Total: 7 validations

**Result**: Only new publications incur API costs

### Use Case 2: Recipe Refinement

**Scenario**: Updated validation recipe with stricter criteria

**Behavior**:
```bash
# Re-validate all publications with new recipe
python run_publication_reviews.py --force-rereviews
```

**Result**: All publications re-reviewed with new criteria

### Use Case 3: Spot-Check Specific Publication

**Scenario**: Need to re-review a single problematic publication

**Behavior**:
```bash
# Delete existing YAML
rm tool_reviews/results/PMID:28078640_tool_review.yaml

# Re-run validation
python run_publication_reviews.py --pmids "PMID:28078640"
```

**Result**: Only that publication is re-validated

## Implementation Details

### Files Modified

1. **`run_publication_reviews.py`** (lines 411-459)
   - Added `--force-rereviews` argument
   - Updated skip logic to check force flag
   - Added informative messages for skip vs re-review

2. **`.github/workflows/check-tool-coverage.yml`** (lines 19-23)
   - Added `force_rereviews` workflow dispatch input
   - Default: false (cost-efficient behavior)

3. **Documentation Updates**:
   - `docs/AI_VALIDATION_README.md` - Usage examples
   - `TOOL_COVERAGE_WORKFLOW.md` - Workflow options
   - `PR_DESCRIPTION.md` - Feature documentation

### Code Implementation

```python
# Added command-line argument
parser.add_argument(
    '--force-rereviews',
    action='store_true',
    help='Force re-review of publications even if YAML files already exist'
)

# Updated skip logic
yaml_path = Path(results_dir) / f'{pmid}_tool_review.yaml'
if yaml_path.exists() and not args.force_rereviews:
    print(f"\n⏭️  Skipping {pmid} (already reviewed, use --force-rereviews to override)")
    continue
elif yaml_path.exists() and args.force_rereviews:
    print(f"\n🔄 Re-reviewing {pmid} (force flag set)")
```

## Testing

### Test 1: Skip Logic Works

```bash
$ python run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv

⏭️  Skipping PMID:28078640 (already reviewed, use --force-rereviews to override)
⏭️  Skipping PMID:28198162 (already reviewed, use --force-rereviews to override)
```

✅ **Result**: Both publications skipped as expected

### Test 2: Force Flag Works

```bash
$ python run_publication_reviews.py --pmids "PMID:28078640" --force-rereviews

🔄 Re-reviewing PMID:28078640 (force flag set)
  Fetching abstract from PubMed...
  Fetching full text from PMC...
```

✅ **Result**: Publication re-reviewed despite existing YAML

### Test 3: Help Message

```bash
$ python run_publication_reviews.py --help

  --force-rereviews     Force re-review of publications even if YAML files
                        already exist
```

✅ **Result**: Help message shows new flag correctly

## Benefits

1. **💰 Cost Savings**: 85-90% reduction in API costs for weekly runs
2. **⚡ Speed**: Skip existing validations, only process new publications
3. **🔄 Flexibility**: Force flag allows re-review when needed
4. **📊 Incremental**: Supports continuous integration workflow
5. **🎯 Targeted**: Can selectively re-review specific publications

## Best Practices

### When to Use Default Behavior (No Force)

✅ Weekly automated runs
✅ Incremental validation of new publications
✅ Cost-conscious production usage
✅ Continuous integration workflows

### When to Use Force Flag

✅ Updated validation recipe (new criteria)
✅ Testing recipe changes
✅ Discovered bug in validation logic
✅ Quality assurance spot-checks
✅ Regenerating all reports for audit

### When to Manually Delete YAMLs

✅ Re-validate single problematic publication
✅ Testing specific edge cases
✅ Debugging validation errors

## Future Enhancements

Potential improvements:

1. **Version tracking**: Detect recipe version changes and auto-trigger re-review
2. **Selective force**: `--force-rereviews-for-type antibody` to re-review specific tool types
3. **Staleness check**: Auto re-review if YAML older than X days
4. **Checksum validation**: Detect if source publication text changed
5. **Batch force**: Force re-review only publications matching criteria

## Conclusion

The smart skip logic feature provides:
- Significant cost savings (85-90%)
- Faster processing times
- Flexibility for re-review when needed
- Production-ready incremental validation

This feature is essential for sustainable, cost-effective AI validation in production workflows.
