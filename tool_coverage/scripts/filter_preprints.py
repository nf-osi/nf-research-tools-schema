#!/usr/bin/env python3
"""
Filter out preprints from publication lists.

Excludes publications from:
- bioRxiv
- medRxiv
- arXiv
- Other preprint servers
"""

import pandas as pd
import argparse
from pathlib import Path


def is_preprint(journal: str, doi: str = None) -> bool:
    """
    Check if publication is a preprint.

    Args:
        journal: Journal name
        doi: DOI (optional, for additional checking)

    Returns:
        True if preprint, False otherwise
    """
    if pd.isna(journal):
        journal = ""
    else:
        journal = str(journal).lower()

    # Preprint server patterns
    preprint_patterns = [
        'biorxiv',
        'medrxiv',
        'arxiv',
        'preprint',
        'ssrn',
        'researchsquare',
        'research square',
        'authorea',
        'preprints.org',
        'chemrxiv',
        'psyarxiv',
        'socarxiv'
    ]

    # Check journal name
    for pattern in preprint_patterns:
        if pattern in journal:
            return True

    # Check DOI if available
    if doi and not pd.isna(doi):
        doi_str = str(doi).lower()
        doi_preprint_patterns = [
            '10.1101',  # bioRxiv, medRxiv
            '10.48550',  # arXiv
            '10.2139',  # SSRN
        ]
        for pattern in doi_preprint_patterns:
            if pattern in doi_str:
                return True

    return False


def filter_preprints(input_file: Path, output_file: Path) -> dict:
    """
    Filter preprints from publication list.

    Args:
        input_file: Input CSV file
        output_file: Output CSV file (preprints removed)

    Returns:
        Dict with statistics
    """
    # Read publications
    df = pd.read_csv(input_file)

    original_count = len(df)

    # Apply filter
    df['is_preprint'] = df.apply(
        lambda row: is_preprint(row.get('journal'), row.get('doi')),
        axis=1
    )

    preprint_count = df['is_preprint'].sum()

    # Remove preprints
    df_filtered = df[~df['is_preprint']].copy()
    df_filtered = df_filtered.drop(columns=['is_preprint'])

    # Save filtered list
    df_filtered.to_csv(output_file, index=False)

    # Save preprints for reference
    if preprint_count > 0:
        preprints_file = output_file.parent / f"{output_file.stem}_preprints.csv"
        df[df['is_preprint']].to_csv(preprints_file, index=False)
        print(f"   Saved {preprint_count} preprints to {preprints_file}")

    return {
        'original_count': original_count,
        'preprint_count': preprint_count,
        'filtered_count': len(df_filtered),
        'removal_rate': preprint_count / original_count * 100 if original_count > 0 else 0
    }


def main():
    parser = argparse.ArgumentParser(
        description='Filter preprints from publication lists'
    )
    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help='Input CSV file with publications'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output CSV file (preprints removed)'
    )

    args = parser.parse_args()

    print("Filtering preprints...")
    result = filter_preprints(args.input, args.output)

    print(f"\n✓ Filtering complete:")
    print(f"  Original: {result['original_count']} publications")
    print(f"  Preprints: {result['preprint_count']} ({result['removal_rate']:.1f}%)")
    print(f"  Filtered: {result['filtered_count']} publications")
    print(f"  Saved to: {args.output}")


if __name__ == '__main__':
    main()
