#!/usr/bin/env python3
"""
Timeout protection for GitHub Actions workflows.

Prevents workflow timeout by capping the number of publications processed
to fit within the 6-hour GitHub Actions limit with safety margin.
"""

import argparse
import json
import sys
import pandas as pd
from pathlib import Path


def calculate_safe_limit(total_publications: int,
                        time_per_publication: float,
                        max_parallel: int = 1,
                        safety_margin_minutes: int = 30) -> dict:
    """
    Calculate how many publications can safely be processed within timeout.

    Args:
        total_publications: Total number of publications to process
        time_per_publication: Estimated seconds per publication
        max_parallel: Number of parallel jobs (reduces total time)
        safety_margin_minutes: Safety margin before timeout

    Returns:
        Dict with results
    """
    # GitHub Actions timeout: 6 hours = 360 minutes
    GITHUB_TIMEOUT_MINUTES = 360

    # Available processing time (with safety margin)
    available_minutes = GITHUB_TIMEOUT_MINUTES - safety_margin_minutes

    # Account for setup/teardown overhead (~10 minutes)
    SETUP_OVERHEAD_MINUTES = 10
    processing_minutes = available_minutes - SETUP_OVERHEAD_MINUTES

    # Calculate publications that fit
    processing_seconds = processing_minutes * 60

    # Adjust for parallelization (if applicable)
    effective_time_per_pub = time_per_publication / max_parallel

    # Max publications that fit
    max_publications = int(processing_seconds / effective_time_per_pub)

    # Determine if capping is needed
    capped = total_publications > max_publications

    if capped:
        # Need to cap
        publications_to_process = max_publications
        publications_deferred = total_publications - max_publications
    else:
        # All fit
        publications_to_process = total_publications
        publications_deferred = 0

    return {
        'total_publications': total_publications,
        'publications_to_process': publications_to_process,
        'publications_deferred': publications_deferred,
        'capped': capped,
        'available_time_minutes': processing_minutes,
        'estimated_time_minutes': (publications_to_process * time_per_publication / max_parallel) / 60,
        'safety_margin_minutes': safety_margin_minutes
    }


def apply_timeout_protection(publications_file: Path,
                            output_file: Path,
                            deferred_file: Path,
                            time_per_publication: float = 3.6,
                            max_parallel: int = 1) -> dict:
    """
    Apply timeout protection by capping publication list.

    Args:
        publications_file: Input CSV file with publications
        output_file: Output CSV file with capped list
        deferred_file: Output text file with deferred PMIDs
        time_per_publication: Estimated seconds per publication
        max_parallel: Number of parallel jobs

    Returns:
        Dict with results
    """
    # Read publications CSV
    df = pd.read_csv(publications_file)
    total = len(df)

    # Calculate safe limit
    result = calculate_safe_limit(
        total_publications=total,
        time_per_publication=time_per_publication,
        max_parallel=max_parallel
    )

    # Split publications
    if result['capped']:
        df_to_process = df.head(result['publications_to_process'])
        df_deferred = df.tail(result['publications_deferred'])

        # Write capped CSV
        df_to_process.to_csv(output_file, index=False)

        # Write deferred PMIDs (text file with one PMID per line)
        with open(deferred_file, 'w') as f:
            for pmid in df_deferred['pmid']:
                f.write(f"{pmid}\n")

        print(f"⚠️  Capped to {len(df_to_process)} publications (deferred {len(df_deferred)})", file=sys.stderr)
        print(f"   Estimated time: {result['estimated_time_minutes']:.1f} minutes", file=sys.stderr)
        print(f"   Available time: {result['available_time_minutes']:.1f} minutes", file=sys.stderr)
        print(f"   Safety margin: {result['safety_margin_minutes']} minutes", file=sys.stderr)
    else:
        # All fit - copy input to output
        df.to_csv(output_file, index=False)

        # Empty deferred file
        with open(deferred_file, 'w') as f:
            f.write('')

        print(f"✓ All {total} publications fit within timeout", file=sys.stderr)
        print(f"   Estimated time: {result['estimated_time_minutes']:.1f} minutes", file=sys.stderr)
        print(f"   Available time: {result['available_time_minutes']:.1f} minutes", file=sys.stderr)

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Apply timeout protection to prevent GitHub Actions timeout'
    )
    parser.add_argument(
        '--publications-file',
        required=True,
        type=Path,
        help='Input file with list of publications (one per line)'
    )
    parser.add_argument(
        '--output-file',
        required=True,
        type=Path,
        help='Output file with capped list'
    )
    parser.add_argument(
        '--deferred-file',
        required=True,
        type=Path,
        help='Output file with deferred publications for next run'
    )
    parser.add_argument(
        '--time-per-publication',
        type=float,
        default=3.6,
        help='Estimated seconds per publication (default: 3.6 from 50 pubs in 3 min test)'
    )
    parser.add_argument(
        '--max-parallel',
        type=int,
        default=1,
        help='Number of parallel jobs (default: 1)'
    )

    args = parser.parse_args()

    # Apply timeout protection
    result = apply_timeout_protection(
        publications_file=args.publications_file,
        output_file=args.output_file,
        deferred_file=args.deferred_file,
        time_per_publication=args.time_per_publication,
        max_parallel=args.max_parallel
    )

    # Output JSON result
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
