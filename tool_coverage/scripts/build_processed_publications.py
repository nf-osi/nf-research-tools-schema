#!/usr/bin/env python3
"""
Build processed_publications.csv (the Sonnet review input) for one mining run.

Rows come from this run's screened_publications.csv, filled in from each
PMID's tool_reviews/publication_cache/{pmid}_text.json. Two kinds of PMID are
left out:

  * Cached papers that weren't screened in this run. The cache is committed to
    the repo, so globbing it would re-send every paper ever mined.
  * Papers that already have tool_reviews/results/{pmid}_tool_review.yaml
    (persisted by the mining PR). run_publication_reviews.py would skip the
    Sonnet call for these but still compile the old YAML into submissions,
    re-mining tools that are already live. --force-rereviews keeps them.

Usage:
    python build_processed_publications.py \\
        --screened-file tool_coverage/outputs/screened_publications.csv \\
        --cache-dir tool_reviews/publication_cache \\
        --results-dir tool_reviews/results \\
        --output tool_coverage/outputs/processed_publications.csv \\
        [--force-rereviews]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

FIELDNAMES = [
    'pmid', 'title', 'abstract', 'methods', 'authors', 'journal',
    'publicationDate', 'doi', 'cache_level', 'has_fulltext',
]


def bare_pmid(pmid) -> str:
    """'PMID:123', '123', '123.0' -> '123'."""
    s = str(pmid).strip().replace('PMID:', '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


def load_screened_pmids(screened_file: Path) -> list:
    """Unique bare PMIDs from screened_publications.csv, in file order."""
    seen = []
    with open(screened_file, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            pmid = bare_pmid(row.get('pmid') or '')
            if pmid and pmid.lower() != 'nan' and pmid not in seen:
                seen.append(pmid)
    return seen


def load_reviewed_pmids(results_dir: Path) -> set:
    if not results_dir.exists():
        return set()
    return {p.name[:-len('_tool_review.yaml')]
            for p in results_dir.glob('*_tool_review.yaml')}


def build_rows(screened_pmids, cache_dir: Path, reviewed_pmids=frozenset(),
               force_rereviews=False):
    """Return (rows, stats) for the screened PMIDs that should go to review."""
    rows = []
    stats = {'screened': len(screened_pmids), 'no_cache': 0,
             'already_reviewed': 0, 'selected': 0}
    for pmid in screened_pmids:
        if pmid in reviewed_pmids and not force_rereviews:
            stats['already_reviewed'] += 1
            continue
        cache_file = cache_dir / f'{pmid}_text.json'
        if not cache_file.exists():
            stats['no_cache'] += 1
            continue
        with open(cache_file, encoding='utf-8') as f:
            cache = json.load(f)
        rows.append({
            'pmid': f'PMID:{pmid}',
            'title': cache.get('title', ''),
            'abstract': cache.get('abstract', ''),
            'methods': cache.get('methods', ''),
            'authors': cache.get('authors', ''),
            'journal': cache.get('journal', ''),
            'publicationDate': cache.get('publicationDate', ''),
            'doi': cache.get('doi', ''),
            'cache_level': cache.get('cache_level', ''),
            'has_fulltext': cache.get('has_fulltext', False),
        })
    stats['selected'] = len(rows)
    return rows, stats


def write_rows(rows, output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--screened-file',
                        default='tool_coverage/outputs/screened_publications.csv')
    parser.add_argument('--cache-dir', default='tool_reviews/publication_cache')
    parser.add_argument('--results-dir', default='tool_reviews/results')
    parser.add_argument('--output',
                        default='tool_coverage/outputs/processed_publications.csv')
    parser.add_argument('--force-rereviews', action='store_true',
                        help='Keep PMIDs that already have a tool review YAML')
    args = parser.parse_args(argv)

    screened = load_screened_pmids(Path(args.screened_file))
    reviewed = load_reviewed_pmids(Path(args.results_dir))
    rows, stats = build_rows(screened, Path(args.cache_dir), reviewed,
                             args.force_rereviews)
    write_rows(rows, Path(args.output))

    print(f"Screened this run:            {stats['screened']}")
    print(f"Already reviewed (skipped):   {stats['already_reviewed']}"
          + (' (kept: --force-rereviews)' if args.force_rereviews else ''))
    print(f"No cache file (skipped):      {stats['no_cache']}")
    print(f"Created {args.output} with {stats['selected']} publications")
    return 0


if __name__ == '__main__':
    sys.exit(main())
