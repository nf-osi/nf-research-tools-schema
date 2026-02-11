# PubMed Query Strategy for Tool Type Mining

## Problem Statement

Different tool types appear in different publication types:
- **Computational Tools** → Methods-heavy bench science papers
- **Patient-Derived Models (PDX)** → Animal model/preclinical studies
- **Advanced Cellular Models (Organoids)** → Developmental/3D culture papers
- **Clinical Assessment Tools** → Clinical trials, patient outcome studies

The original PubMed query **explicitly excludes clinical studies**, which prevents discovery of clinical assessment tools.

## Current Query Analysis

### Existing Query (Bench Science)
```python
PUBMED_QUERY_FILTERS = [
    '(neurofibroma*[Abstract]',
    'NOT outcomes[Title] NOT patient*[Title]',  # ❌ Excludes clinical
    'NOT clinic*[Title] NOT cohort*[Title]',    # ❌ Excludes clinical
    'NOT "quality of life"[Title]',             # ❌ Excludes QoL studies
    'NOT trial[Title]',                         # ❌ Excludes trials
    # ...
]
```

**Effect:** Highly effective for bench science, completely misses clinical papers.

### Real-World Results (50 Papers)
- Computational Tools: 65 found ✅
- PDX Models: 12 found ✅
- Clinical Tools: **1 found** ⚠️ (should be ~10-15)
- Organoids: 0 found ❓

**Conclusion:** Query works as designed (bench science only), but incompatible with clinical tool extraction.

---

## Recommended Solution: Multi-Query Strategy

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PubMed Query Dispatcher                   │
└─────────────────────────────────────────────────────────────┘
                              |
                ┌─────────────┼─────────────┐
                |             |             |
                v             v             v
      ┌─────────────┐  ┌───────────┐  ┌──────────┐
      │   Bench     │  │ Clinical  │  │ Organoid │
      │  Science    │  │Assessment │  │ Focused  │
      │   Query     │  │   Query   │  │  Query   │
      └─────────────┘  └───────────┘  └──────────┘
            |               |              |
            v               v              v
      Computational,     Clinical       Advanced
      PDX Models        Assessment      Cellular
                         Tools           Models
                            |
                            v
                  ┌──────────────────┐
                  │ Merge & Dedupe   │
                  └──────────────────┘
                            |
                            v
                  ┌──────────────────┐
                  │ Mine & Extract   │
                  └──────────────────┘
```

### Query Definitions

See `tool_coverage/config/pubmed_queries.json` for full query specifications.

#### 1. Bench Science Query (Existing)
**Target:** Computational Tools, PDX Models, Organoids
**Frequency:** Monthly
**Priority:** High
**Papers/Month:** ~500-1000
**Exclusions:** Clinical, outcomes, QoL, trials

#### 2. Clinical Assessment Query (NEW)
**Target:** Clinical Assessment Tools
**Frequency:** Quarterly
**Priority:** Medium
**Papers/Quarter:** ~100-200
**Inclusions:** QoL, questionnaires, PROs, assessments
**Publication Types:** Clinical Trial, Observational Study

#### 3. Organoid Focused Query (Optional)
**Target:** Advanced Cellular Models
**Frequency:** As needed (if bench query insufficient)
**Priority:** Low
**Papers:** ~20-50
**Inclusions:** organoid, spheroid, 3D culture

---

## Implementation Plan

### Phase 1: Add Clinical Query (Immediate)

**Files to Modify:**
1. `prepare_publication_list.py`
   - Add `--query-type` parameter (bench|clinical|organoid)
   - Implement query selection logic
   - Load queries from `pubmed_queries.json`

2. `fetch_fulltext_and_mine.py`
   - Accept query type metadata
   - Tag publications with source query
   - Adjust extraction focus based on query type

**Example Usage:**
```bash
# Monthly bench science run
python prepare_publication_list.py --query-type bench \
    --output bench_pmids.txt

python fetch_fulltext_and_mine.py \
    --pmids bench_pmids.txt \
    --query-type bench

# Quarterly clinical run
python prepare_publication_list.py --query-type clinical \
    --output clinical_pmids.txt

python fetch_fulltext_and_mine.py \
    --pmids clinical_pmids.txt \
    --query-type clinical
```

### Phase 2: Merge Results

**New Script:** `merge_mining_results.py`

```python
def merge_mining_results(bench_results, clinical_results):
    """
    Merge results from multiple query types.

    - Deduplicate by PMID (keep all tool types from both queries)
    - Aggregate tool counts by publication
    - Preserve source query metadata
    """
    merged = {}

    for pmid, tools in bench_results.items():
        merged[pmid] = {
            'tools': tools,
            'sources': ['bench']
        }

    for pmid, tools in clinical_results.items():
        if pmid in merged:
            # Same paper in both queries - merge tools
            merged[pmid]['tools'].extend(tools)
            merged[pmid]['sources'].append('clinical')
        else:
            merged[pmid] = {
                'tools': tools,
                'sources': ['clinical']
            }

    return merged
```

### Phase 3: Monitoring & Validation

**Metrics to Track:**
- Tool extraction rate by query type
- False positive rate by query type
- Papers per query
- Cost per query (API calls, processing time)

**Expected Baseline:**
- Bench query: 10-20% papers have computational/PDX tools
- Clinical query: 30-50% papers have clinical tools
- Organoid query: 50-70% papers have organoid models

**Alerts:**
- Clinical query <10% extraction → Query too broad
- Bench query <5% extraction → Query too narrow
- High duplicate rate (>30%) → Queries overlap too much

---

## Migration Strategy

### Immediate (Week 1-2)
- [x] ✅ Create `pubmed_queries.json` configuration
- [ ] Update `prepare_publication_list.py` to support query types
- [ ] Test clinical query on small sample (100 PMIDs)
- [ ] Validate clinical tool extraction rate

### Short-Term (Week 3-4)
- [ ] Run clinical query on full corpus (last 5 years)
- [ ] Mine clinical papers for assessment tools
- [ ] Compare results to bench science corpus
- [ ] Document query effectiveness

### Long-Term (Month 2-3)
- [ ] Implement automated query scheduling
- [ ] Set up monitoring dashboards
- [ ] Establish baseline metrics
- [ ] Optimize query filters based on results

---

## Cost Analysis

### Current (Bench Science Only)
- **Papers/Month:** ~1000
- **API Calls:** ~3000 (PubMed + FullText)
- **Processing Time:** ~4 hours
- **Tool Extraction Rate:** 10-15%

### Proposed (Multi-Query)
- **Bench Papers/Month:** ~1000 (unchanged)
- **Clinical Papers/Quarter:** ~150 (new)
- **Organoid Papers/Year:** ~20 (optional)
- **Total Increase:** ~15% more papers annually
- **Expected Clinical Tool Extraction:** 40-50%

**ROI:**
- **Cost:** +15% papers/year
- **Benefit:** +300% clinical tool coverage (1 → 15+ tools/quarter)
- **Recommendation:** High value, low cost

---

## Alternative Approaches Considered

### ❌ Option 1: Remove All Exclusions
**Approach:** Broaden bench query to include clinical papers

**Pros:** Single query, simple workflow

**Cons:**
- 3-5x more papers to process
- Higher cost, lower signal-to-noise
- Many papers won't have relevant tools
- Harder to optimize for either category

**Decision:** Rejected - inefficient

### ❌ Option 2: Manual Curation Lists
**Approach:** Manually curate lists of papers with clinical tools

**Pros:** Perfect precision

**Cons:**
- Not scalable
- Labor intensive
- Misses new publications
- Defeats automation purpose

**Decision:** Rejected - defeats automation

### ✅ Option 3: Tool-Specific Queries (Chosen)
**Approach:** Separate queries optimized for each tool category

**Pros:**
- High precision per category
- Cost-efficient (targeted searches)
- Easy to optimize independently
- Scalable and automated

**Cons:**
- More complex workflow
- Potential duplicates (manageable)

**Decision:** Accepted - best balance

---

## Open Questions

1. **Organoid query needed?**
   - Test bench query first
   - Only add organoid query if extraction rate stays at 0%
   - Decision point: After 3 months of bench query data

2. **Query update frequency?**
   - Bench: Monthly (confirmed)
   - Clinical: Quarterly or biannually?
   - Decision point: After first clinical run

3. **Deduplication strategy?**
   - Keep all tools from all queries (recommended)
   - OR prioritize one query's extraction over another?
   - Decision point: After merge implementation

4. **Historical backfill?**
   - Run clinical query on all historical papers?
   - OR only capture new publications going forward?
   - Decision point: Based on tool catalog gaps

---

## References

- Original query: `tool_coverage/scripts/prepare_publication_list.py`
- Query config: `tool_coverage/config/pubmed_queries.json`
- Test results: `tool_coverage/outputs/REAL_WORLD_EXTRACTION_REPORT.md`
- Issue tracking: GitHub #66 (Clinical Assessment Tools)

---

**Author:** NF Research Tools Team
**Last Updated:** 2026-02-10
**Status:** Proposed - Awaiting Implementation
