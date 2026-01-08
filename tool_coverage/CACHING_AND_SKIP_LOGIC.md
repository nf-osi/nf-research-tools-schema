# Caching and Skip Logic Implementation

## Overview

Two optimization features prevent duplicate work:
1. **Publication Text Caching**: Avoids duplicate API calls to PubMed/PMC
2. **Review Skip Logic**: Avoids re-reviewing already-validated publications

## 1. Publication Text Caching ✨ NEW

### Problem Solved

Previously, we fetched text twice:
- **Mining phase**: Fetch abstract + full text from APIs → mine for tools
- **Validation phase**: Fetch abstract + full text from APIs again → validate tools

**Result**: 100 duplicate API calls for 50 publications, ~4-8 extra minutes

### Solution: Cache During Mining

#### Step 1: Cache Creation (fetch_fulltext_and_mine.py)

When mining each publication:
```python
# After fetching and mining
mining_result = mine_publication(row, tool_patterns, existing_tools)

# Cache the fetched text (NEW)
cache_publication_text(
    pmid=mining_result['pmid'],
    abstract=mining_result.get('abstract_text', ''),
    methods=mining_result.get('methods_text', ''),
    intro=mining_result.get('intro_text', '')
)
```

Creates cache file:
```
tool_reviews/publication_cache/PMID:28078640_text.json
```

#### Cache File Format

```json
{
  "pmid": "PMID:28078640",
  "abstract": "Background: Neurofibromatosis type 1 (NF1)...",
  "methods": "We conducted interviews with 93 individuals...",
  "introduction": "Neurofibromatosis type 1 is an autosomal dominant...",
  "fetched_at": "2026-01-08T15:30:00",
  "abstract_length": 1245,
  "methods_length": 3456,
  "introduction_length": 2345
}
```

#### Step 2: Cache Usage (run_publication_reviews.py)

When validating:
```python
def prepare_goose_input(pub_row, inputs_dir):
    pmid = pub_row['pmid']

    # Try cache first (NEW)
    cached = load_cached_text(pmid)

    if cached:
        print(f"  ✅ Using cached text (skipping API calls)")
        abstract_text = cached['abstract']
        methods_text = cached['methods']
        intro_text = cached['introduction']
    else:
        # Fall back to API (backwards compatibility)
        print(f"  Fetching abstract from PubMed...")
        abstract_text = fetch_pubmed_abstract(pmid)
        ...
```

### Benefits

**Before** (no caching):
```
Mining: 50 pubs × 2 API calls = 100 API calls (~5 min)
Validation: 50 pubs × 2 API calls = 100 API calls (~5 min)
Total: 200 API calls (~10 min)
```

**After** (with caching):
```
Mining: 50 pubs × 2 API calls = 100 API calls (~5 min) [creates cache]
Validation: 50 pubs × 0 API calls = 0 API calls (~0 sec) [uses cache]
Total: 100 API calls (~5 min)
```

**Savings**: 50% fewer API calls, 50% faster, lower rate limit risk

### Cache Management

**Location**: `tool_reviews/publication_cache/`

**Lifetime**: Cache persists until manually deleted

**Invalidation**: Delete specific cache file to force re-fetch
```bash
rm tool_reviews/publication_cache/PMID:28078640_text.json
```

**Clear all cache**:
```bash
rm -rf tool_reviews/publication_cache/
```

**Git Ignored**: Cache directory in `.gitignore` (not committed)

### Testing

```bash
# Run mining (creates cache)
python tool_coverage/fetch_fulltext_and_mine.py

# Check cache was created
ls tool_reviews/publication_cache/
# Should see: PMID:28078640_text.json, PMID:28198162_text.json, ...

# Run validation (uses cache)
python tool_coverage/run_publication_reviews.py --skip-goose

# Should see: "✅ Using cached text (skipping API calls)"
```

---

## 2. Review Skip Logic

### Problem Solved

Without skip logic, every validation run would:
- Re-review ALL publications (even already-validated ones)
- Cost: 50 pubs × $0.01-0.03 = $0.50-1.50 **per run**
- Time: ~25-50 minutes **per run**

**For weekly runs**: ~$2-6 per month, mostly redundant

### Solution: Check for Existing Validation Files

#### How It Works

When `run_publication_reviews.py` runs:

```python
for idx, row in mining_df.iterrows():
    pmid = row['pmid']

    # Check if already reviewed (unless force flag is set)
    yaml_path = Path(results_dir) / f'{pmid}_tool_review.yaml'

    if yaml_path.exists() and not args.force_rereviews:
        print(f"\n⏭️  Skipping {pmid} (already reviewed, use --force-rereviews to override)")
        continue
    elif yaml_path.exists() and args.force_rereviews:
        print(f"\n🔄 Re-reviewing {pmid} (force flag set)")

    # Only reaches here if not reviewed or force flag set
    run_goose_review(pmid, ...)
```

#### Detection Mechanism

**Checks**: `tool_reviews/results/{PMID}_tool_review.yaml`

**If exists**: Skip (already validated)

**If missing**: Run validation (new publication)

### Usage Modes

#### Default: Skip Already-Reviewed

```bash
# Only validates new publications
python tool_coverage/run_publication_reviews.py --mining-file novel_tools_FULLTEXT_mining.csv
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

#### Force Re-review All

```bash
# Re-validates ALL publications (override skip logic)
python tool_coverage/run_publication_reviews.py --force-rereviews
```

Output:
```
🔄 Re-reviewing PMID:28078640 (force flag set)
🔄 Re-reviewing PMID:28198162 (force flag set)
...
```

#### Review Specific Publications

```bash
# Force re-review specific publications
python tool_coverage/run_publication_reviews.py --pmids "PMID:28078640,PMID:29415745" --force-rereviews
```

### When to Use Each Mode

#### Default (Skip Already-Reviewed)
✅ Weekly automated runs
✅ Incremental validation of new publications
✅ Cost-conscious production usage
✅ Normal workflow

#### Force Re-review
✅ Updated Goose recipe (new validation criteria)
✅ Bug fix in validation logic
✅ Quality assurance spot-checks
✅ Testing recipe changes

### Cost Savings Analysis

#### Scenario: Weekly Automated Runs

**Week 1** (initial):
- Publications: 50
- Already reviewed: 0
- To review: 50
- API cost: ~$0.50-1.50

**Week 2** (with skip logic):
- Publications: 55 (5 new)
- Already reviewed: 50 (skipped)
- To review: 5
- API cost: ~$0.05-0.15

**Week 3** (with skip logic):
- Publications: 58 (3 new)
- Already reviewed: 55 (skipped)
- To review: 3
- API cost: ~$0.03-0.09

**Monthly savings**: 85-90% cost reduction

#### Scenario: Without Skip Logic

**Every week**:
- Publications: 50+ (growing)
- Already reviewed: 0 (all re-reviewed)
- To review: 50+
- API cost: ~$0.50-1.50 **per week**

**Monthly cost**: ~$2-6 (wasteful)

### Manual Review Invalidation

To re-review a specific publication:

**Option 1: Delete YAML file**
```bash
rm tool_reviews/results/PMID:28078640_tool_review.yaml
python tool_coverage/run_publication_reviews.py --pmids "PMID:28078640"
```

**Option 2: Use force flag**
```bash
python tool_coverage/run_publication_reviews.py --pmids "PMID:28078640" --force-rereviews
```

### GitHub Actions Integration

Workflow dispatch inputs control skip behavior:

```yaml
workflow_dispatch:
  inputs:
    force_rereviews:
      description: 'Force re-review of already-reviewed publications'
      type: boolean
      default: false  # Skip by default (cost-efficient)
```

**Usage**:
1. Go to Actions → Check Tool Coverage → Run workflow
2. **Default**: Leave "Force re-review" unchecked (skips reviewed)
3. **Override**: Check "Force re-review" box (re-validates all)

---

## Combined Benefits

### Both Features Together

**Mining phase**:
- Fetches text from APIs → caches for reuse
- Mines tools from text
- Generates mining CSV

**First validation run**:
- Reads text from cache (no API calls)
- Validates with Goose AI
- Generates YAML validation files
- Filters submission CSVs

**Subsequent validation runs**:
- Checks for existing YAML files → skips reviewed
- For new publications: reads text from cache → validates
- No duplicate API calls, no duplicate validations

### Performance Impact

**50 publications, weekly validation**:

**Without optimizations**:
```
Week 1: 200 API calls (fetch × 2) + 50 AI reviews = $0.50-1.50
Week 2: 200 API calls (fetch × 2) + 50 AI reviews = $0.50-1.50
Week 3: 200 API calls (fetch × 2) + 50 AI reviews = $0.50-1.50
Monthly: 600 API calls + 150 AI reviews = $1.50-4.50
```

**With optimizations**:
```
Week 1: 100 API calls (fetch once, cache) + 50 AI reviews = $0.50-1.50
Week 2: 10 API calls (5 new pubs) + 5 AI reviews = $0.05-0.15
Week 3: 6 API calls (3 new pubs) + 3 AI reviews = $0.03-0.09
Monthly: 116 API calls + 58 AI reviews = $0.58-1.74
```

**Savings**: 80-85% reduction in API calls and AI costs

---

## File Structure

```
nf-research-tools-schema/
├── tool_reviews/
│   ├── publication_cache/           ← Text cache (gitignored)
│   │   ├── PMID:28078640_text.json
│   │   ├── PMID:28198162_text.json
│   │   └── ...
│   ├── inputs/                      ← Goose input files (gitignored)
│   │   ├── PMID:28078640_input.json
│   │   └── ...
│   ├── results/                     ← Validation YAMLs (gitignored)
│   │   ├── PMID:28078640_tool_review.yaml
│   │   ├── PMID:28198162_tool_review.yaml
│   │   └── ...
│   ├── validation_summary.json
│   └── validation_report.xlsx
└── ...
```

**Gitignored directories**:
- `tool_reviews/publication_cache/` (cache files)
- `tool_reviews/inputs/` (Goose input JSONs)
- `tool_reviews/results/*.yaml` (validation results)

**Not gitignored**:
- `validation_summary.json` (aggregate results)
- `validation_report.xlsx` (Excel report)

---

## Debugging

### Check if caching is working

```bash
# Run mining
python tool_coverage/fetch_fulltext_and_mine.py

# Check cache files created
ls -lh tool_reviews/publication_cache/

# Run validation
python tool_coverage/run_publication_reviews.py --skip-goose

# Should see: "✅ Using cached text (skipping API calls)"
```

### Check if skip logic is working

```bash
# Run validation
python tool_coverage/run_publication_reviews.py

# Should see: "⏭️  Skipping PMID:... (already reviewed)"

# Check review files exist
ls tool_reviews/results/*.yaml
```

### Force fresh validation

```bash
# Clear cache and reviews
rm -rf tool_reviews/publication_cache/
rm -rf tool_reviews/results/*.yaml

# Re-run mining (creates fresh cache)
python tool_coverage/fetch_fulltext_and_mine.py

# Re-run validation (reviews all)
python tool_coverage/run_publication_reviews.py
```

---

## Best Practices

### 1. Let Cache Accumulate

✅ **Do**: Let cache build up over time
❌ **Don't**: Clear cache frequently

Cache persists across runs, saving time and API calls.

### 2. Use Skip Logic by Default

✅ **Do**: Run without `--force-rereviews` for normal workflow
❌ **Don't**: Force re-review unless specifically needed

Skip logic saves 85-90% of API costs on subsequent runs.

### 3. Only Force When Needed

**Force re-review when**:
- Updated Goose recipe
- Bug fix in validation
- Testing changes
- Quality assurance

**Don't force when**:
- Normal weekly runs
- Adding new publications
- Incremental validation

### 4. Monitor Cache Size

Cache grows with number of publications:
- ~50 KB per publication (JSON)
- 1000 publications = ~50 MB
- Not a problem unless thousands of publications

### 5. Audit Trail

Review YAML files serve as audit trail:
- Keep them committed (or backed up)
- Show validation decisions
- Allow reproducibility

---

## Future Enhancements

### Cache Expiration

Add timestamp checking:
```python
def is_cache_stale(cached, max_age_days=30):
    """Check if cache is older than max_age_days."""
    fetched_at = datetime.fromisoformat(cached['fetched_at'])
    age = datetime.now() - fetched_at
    return age.days > max_age_days
```

### Cache Statistics

Track cache hit rate:
```python
cache_hits = 0
cache_misses = 0

# In prepare_goose_input()
if cached:
    cache_hits += 1
else:
    cache_misses += 1

hit_rate = cache_hits / (cache_hits + cache_misses)
print(f"Cache hit rate: {hit_rate:.1%}")
```

### Selective Skip

Skip by confidence:
```python
# Re-review if previous validation had low confidence
if yaml_exists and previous_confidence < 0.7:
    revalidate = True
```

---

## Summary

| Feature | What It Does | Savings |
|---------|-------------|---------|
| **Text Caching** | Saves fetched text to avoid duplicate API calls | 50% fewer API calls |
| **Review Skip Logic** | Avoids re-reviewing already-validated publications | 85-90% fewer AI validations |
| **Combined** | Both optimizations together | 80-85% total cost reduction |

**Result**: Fast, cost-efficient, production-ready workflow ✅
