# Workflow Recovery Guide

## What Happened

The GitHub Actions workflow [run #21899738477](https://github.com/nf-osi/nf-research-tools-schema/actions/runs/21899738477) timed out after **6 hours** while processing 1,128 publications.

**Completed Steps:**
- ✅ Prepared publication list (1,878 bench + 381 clinical = 2,205 unique)
- ✅ Screened titles with Haiku (1,128 research publications identified)

**Timed Out:**
- ❌ Fetch full text and mine for tools (processing 1,128 publications took >6 hours)

## What Was Salvaged

We successfully reconstructed the screening results from the workflow logs:

1. **`tool_coverage/outputs/screened_publications.csv`** - 1,128 research publications ready for mining
2. **`tool_coverage/outputs/title_screening_cache.csv`** - Screening cache (can reuse to avoid re-screening)

These files contain:
- PMID, DOI, title, journal, year
- Screening reasoning (why each was marked as research)
- Ready to be fed into the mining step

## How to Continue

### Option 1: Run Locally in Batches (Recommended)

Process publications in safe batches to avoid timeouts:

```bash
# Process first 100 publications
python tool_coverage/scripts/batch_process_publications.py \
    --batch-size 100 \
    --max-batches 1

# Process next 100 (automatically skips already-processed)
python tool_coverage/scripts/batch_process_publications.py \
    --batch-size 100 \
    --max-batches 1

# Continue until all done...
```

**Benefits:**
- Processes in manageable chunks
- Tracks progress (resumes if interrupted)
- Skips already-processed publications
- No 6-hour timeout limit

### Option 2: Re-run Workflow with Smaller Batch

Trigger the workflow again with the `max_publications` parameter:

```bash
gh workflow run check-tool-coverage.yml \
    -f max_publications=100 \
    -f ai_validation=true
```

**Run multiple times** with different batch sizes:
- First run: 100 publications
- Second run: 200 publications
- etc.

### Option 3: Optimize the Mining Script

The mining script is slow because it fetches full text for every publication. Consider:

1. **Use publication cache** - Check `tool_reviews/publication_cache/` for already-fetched publications
2. **Parallel processing** - The script currently processes serially; could parallelize
3. **Skip unavailable full text** - Many publications don't have full text available (use abstract only)

## Files Created for Recovery

| File | Purpose | Location |
|------|---------|----------|
| `screened_publications.csv` | 1,128 research publications ready for mining | `tool_coverage/outputs/` |
| `title_screening_cache.csv` | Screening cache (reusable) | `tool_coverage/outputs/` |
| `reconstruct_from_logs.py` | Script that generated above files | `tool_coverage/scripts/` |
| `batch_process_publications.py` | Batch processing helper script | `tool_coverage/scripts/` |
| `.processing_progress.txt` | Checkpoint file (tracks processed PMIDs) | `tool_coverage/outputs/` |

## Estimation

Based on the timeout:
- **1,128 publications** took **>6 hours** (timed out)
- Estimated: **~20-30 seconds per publication** minimum
- **Recommendation:** Process in batches of **50-100** publications (15-50 minutes each)

## Next Steps

1. ✅ **Salvaged screening results** (`screened_publications.csv` created)
2. 🔄 **Start batch processing:**
   ```bash
   python tool_coverage/scripts/batch_process_publications.py --batch-size 50 --max-batches 1
   ```
3. ⏳ **Monitor progress** - Check `tool_coverage/outputs/processed_publications.csv`
4. 🔁 **Repeat** - Run batch processing multiple times until all 1,128 are processed
5. ✅ **Validation** - Once mining completes, run AI validation step

## Avoiding Future Timeouts

1. **Use batch processing** - Don't try to process 1,000+ publications in one run
2. **Set realistic batch sizes** - 50-100 publications per run (30-60 minutes)
3. **Check cache first** - Reuse cached full text when available
4. **Consider parallelization** - Process multiple publications concurrently

## Questions?

- To reset progress and start fresh: `--reset-progress`
- To process specific publications: Edit `screened_publications.csv` before running
- To check what's been processed: `cat tool_coverage/outputs/.processing_progress.txt`
