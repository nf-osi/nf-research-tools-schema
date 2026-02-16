#!/usr/bin/env python3
"""
Process publications in safe batches to avoid timeouts.
Tracks progress and skips already-processed publications.
"""

import pandas as pd
import argparse
from pathlib import Path
import subprocess
import sys

def load_progress_file():
    """Load processed PMIDs from checkpoint file."""
    progress_file = Path('tool_coverage/outputs/.processing_progress.txt')
    if progress_file.exists():
        with open(progress_file, 'r') as f:
            processed = set(int(line.strip()) for line in f if line.strip().isdigit())
        return processed
    return set()


def save_progress(pmid):
    """Save processed PMID to checkpoint file."""
    progress_file = Path('tool_coverage/outputs/.processing_progress.txt')
    with open(progress_file, 'a') as f:
        f.write(f"{pmid}\n")


def get_publications_to_process(input_file, batch_size, skip_processed=True):
    """
    Get publications that need to be processed.

    Returns: DataFrame with next batch to process
    """
    # Load screened publications
    df = pd.read_csv(input_file)
    print(f"✓ Loaded {len(df)} screened publications")

    # Check for already-processed publications
    if skip_processed:
        # Check if we have any existing mining results
        processed_file = Path('tool_coverage/outputs/processed_publications.csv')
        if processed_file.exists():
            processed_df = pd.read_csv(processed_file)
            processed_pmids = set(processed_df['pmid'].unique())
            print(f"  - Found {len(processed_pmids)} publications already mined")
            df = df[~df['pmid'].isin(processed_pmids)]

        # Also check progress file
        progress_pmids = load_progress_file()
        if progress_pmids:
            print(f"  - Found {len(progress_pmids)} publications in progress file")
            df = df[~df['pmid'].isin(progress_pmids)]

    print(f"✓ {len(df)} publications remaining to process")

    # Return next batch
    if len(df) == 0:
        return None

    batch_df = df.head(batch_size)
    print(f"✓ Processing next batch: {len(batch_df)} publications")
    return batch_df


def process_batch(batch_file, max_pubs, use_optimized=True):
    """Run the mining script on a batch of publications."""
    script = 'fetch_publication_fulltext_optimized.py' if use_optimized else 'fetch_publication_fulltext.py'
    cmd = [
        'python', f'tool_coverage/scripts/{script}',
        '--input', str(batch_file),
        '--max-publications', str(max_pubs)
    ]

    print(f"\nRunning: {' '.join(cmd)}")
    if use_optimized:
        print("  ⚡ Using OPTIMIZED two-stage approach (60-70% faster!)")
    result = subprocess.run(cmd, capture_output=False, text=True)

    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description='Process publications in safe batches'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of publications to process per batch (default: 100)'
    )
    parser.add_argument(
        '--max-batches',
        type=int,
        default=None,
        help='Maximum number of batches to run (default: unlimited)'
    )
    parser.add_argument(
        '--input',
        default='tool_coverage/outputs/screened_publications.csv',
        help='Input file with screened publications'
    )
    parser.add_argument(
        '--skip-processed',
        action='store_true',
        default=True,
        help='Skip publications already processed (default: True)'
    )
    parser.add_argument(
        '--reset-progress',
        action='store_true',
        help='Clear progress file and start fresh'
    )
    parser.add_argument(
        '--use-optimized',
        action='store_true',
        default=True,
        help='Use optimized two-stage mining (default: True, 60-70%% faster)'
    )
    parser.add_argument(
        '--no-optimize',
        dest='use_optimized',
        action='store_false',
        help='Use original mining script (slower but fetches all sections)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Batch Publication Processing")
    print("=" * 80)

    # Reset progress if requested
    if args.reset_progress:
        progress_file = Path('tool_coverage/outputs/.processing_progress.txt')
        if progress_file.exists():
            progress_file.unlink()
            print("✓ Cleared progress file\n")

    # Check input file exists
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        print("   Run: python tool_coverage/scripts/reconstruct_from_logs.py")
        sys.exit(1)

    batch_num = 0
    total_processed = 0

    while True:
        batch_num += 1

        # Check max batches
        if args.max_batches and batch_num > args.max_batches:
            print(f"\n✓ Reached maximum batch limit ({args.max_batches})")
            break

        print(f"\n{'=' * 80}")
        print(f"Batch {batch_num}")
        print(f"{'=' * 80}\n")

        # Get next batch
        batch_df = get_publications_to_process(
            args.input,
            args.batch_size,
            skip_processed=args.skip_processed
        )

        if batch_df is None or len(batch_df) == 0:
            print("\n✅ All publications processed!")
            break

        # Save batch to temp file
        batch_file = Path('tool_coverage/outputs/.batch_temp.csv')
        batch_df.to_csv(batch_file, index=False)

        # Process batch
        success = process_batch(batch_file, len(batch_df), use_optimized=args.use_optimized)

        if success:
            # Mark PMIDs as processed
            for pmid in batch_df['pmid']:
                save_progress(pmid)
            total_processed += len(batch_df)
            print(f"\n✓ Batch {batch_num} completed successfully")
        else:
            print(f"\n❌ Batch {batch_num} failed")
            print("   Check logs for errors")
            break

    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"  Batches processed: {batch_num}")
    print(f"  Publications processed: {total_processed}")
    print("\nNext steps:")
    print("  1. Check tool_coverage/outputs/processed_publications.csv for results")
    print("  2. Run again to process more batches if needed")
    print("  3. Run: python tool_coverage/scripts/run_publication_reviews.py for validation")


if __name__ == '__main__':
    main()
