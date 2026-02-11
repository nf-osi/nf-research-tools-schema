#!/usr/bin/env python3
"""
Fetch full text and mine publications that passed title screening.
Reads screened_publications.csv and outputs processed_publications.csv with mined tools.
"""

import sys
import os

# Import functions from fetch_fulltext_and_mine.py
sys.path.insert(0, os.path.dirname(__file__))

try:
    from fetch_fulltext_and_mine import (
        fetch_pmc_fulltext,
        fetch_pubmed_abstract,
        extract_methods_section,
        extract_introduction_section,
        extract_results_section,
        extract_discussion_section,
        cache_publication_text,
        load_existing_tools_for_matching,
        mine_publication,
        sanitize_pmid_for_filename
    )
except ImportError as e:
    print(f"Error importing from fetch_fulltext_and_mine.py: {e}")
    print("Make sure fetch_fulltext_and_mine.py is in the same directory")
    sys.exit(1)

import pandas as pd
import synapseclient
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description='Fetch full text and mine for tools (screened publications only)'
    )
    parser.add_argument(
        '--input',
        default='tool_coverage/outputs/screened_publications.csv',
        help='Input file with screened publications (default: screened_publications.csv)'
    )
    parser.add_argument(
        '--output',
        default='tool_coverage/outputs/processed_publications.csv',
        help='Output file for mining results'
    )
    parser.add_argument(
        '--max-publications',
        type=int,
        default=None,
        help='Limit number of publications to process (for testing)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Fetch Full Text & Mine Publications (Step 3)")
    print("=" * 80)

    # Check input file exists
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        print("   Run screen_publication_titles.py first!")
        return

    # Login to Synapse
    print("\n1. Connecting to Synapse...")
    syn = synapseclient.Synapse()
    syn.login(silent=True)

    # Load screened publications
    print(f"\n2. Loading screened publications from {input_file}...")
    pubs_df = pd.read_csv(input_file)
    
    # Filter to research publications if is_research column exists
    if 'is_research' in pubs_df.columns:
        before_filter = len(pubs_df)
        pubs_df = pubs_df[pubs_df['is_research'] == True].copy()
        print(f"   - Loaded {len(pubs_df)} research publications ({before_filter - len(pubs_df)} clinical excluded)")
    else:
        print(f"   - Loaded {len(pubs_df)} publications")

    # Apply max limit if specified
    if args.max_publications and len(pubs_df) > args.max_publications:
        print(f"   - Limiting to first {args.max_publications} publications (--max-publications)")
        pubs_df = pubs_df.head(args.max_publications)

    # Load existing tools for pattern matching
    print("\n3. Loading existing tool patterns...")
    existing_tools = load_existing_tools_for_matching(syn)
    print(f"   - Loaded patterns for {len(existing_tools)} tool types")

    # Build tool patterns from existing tools
    tool_patterns = {}
    for tool_type, tools_dict in existing_tools.items():
        tool_patterns[tool_type] = list(tools_dict.keys())

    # Mine publications
    print(f"\n4. Fetching full text and mining {len(pubs_df)} publications...")
    print("   (This may take a while - ~0.5s per publication)")

    results = []
    summary = []
    abstract_mined = 0
    fetch_success = 0
    methods_found = 0
    intro_found = 0
    existing_tool_matches = 0
    novel_tools_found = 0
    pub_counter = 0

    # Create cache directory
    Path('tool_reviews/publication_cache').mkdir(parents=True, exist_ok=True)

    for idx, row in pubs_df.iterrows():
        pmid = row.get('pmid', '')
        if not pmid or pmid == 'nan':
            continue

        pub_counter += 1
        print(f"\n   [{pub_counter}/{len(pubs_df)}] Mining PMID {pmid}...")

        # Mine publication (includes fetching full text)
        mining_result = mine_publication(row, tool_patterns, existing_tools)

        # Cache fetched text to avoid duplicate API calls during validation
        cache_publication_text(
            pmid=mining_result['pmid'],
            abstract=mining_result.get('abstract_text', ''),
            methods=mining_result.get('methods_text', ''),
            intro=mining_result.get('intro_text', ''),
            results=mining_result.get('results_text', ''),
            discussion=mining_result.get('discussion_text', '')
        )

        # Log progress
        if mining_result['abstract_available']:
            abstract_mined += 1

        if mining_result['fulltext_available']:
            fetch_success += 1

        if mining_result['methods_found']:
            methods_found += 1

        if mining_result['introduction_found']:
            intro_found += 1

        # Count tools
        existing_count = sum(len(tools) for tools in mining_result['existing_tools'].values())
        novel_count = sum(len(tools) for tools in mining_result['novel_tools'].values())

        if existing_count > 0:
            existing_tool_matches += existing_count
            print(f"     🔗 Matched {existing_count} existing tools")

        if novel_count > 0:
            novel_tools_found += novel_count
            print(f"     🎯 Found {novel_count} novel tools")

        # Store result if any tools found
        if existing_count > 0 or novel_count > 0:
            result_row = {
                'pmid': mining_result['pmid'],
                'doi': mining_result['doi'],
                'title': mining_result['title'],
                'journal': mining_result['journal'],
                'year': mining_result['year'],
                'fundingAgency': mining_result['fundingAgency'],
                'abstract_length': mining_result['abstract_length'],
                'methods_length': mining_result['methods_length'],
                'intro_length': mining_result['intro_length'],
                'existing_tool_count': existing_count,
                'novel_tool_count': novel_count,
                'total_tool_count': existing_count + novel_count,
                'existing_tools': json.dumps(mining_result['existing_tools']),
                'novel_tools': json.dumps({k: list(v) for k, v in mining_result['novel_tools'].items()}),
                'tool_metadata': json.dumps(mining_result['tool_metadata']),
                'tool_sources': json.dumps({k: list(v) for k, v in mining_result['tool_sources'].items()}),
                'is_gff': mining_result['is_gff']
            }
            results.append(result_row)

        # Track in summary (ALL publications)
        summary.append({
            'pmid': mining_result['pmid'],
            'doi': mining_result['doi'],
            'title': mining_result['title'],
            'journal': mining_result['journal'],
            'year': mining_result['year'],
            'fundingAgency': mining_result['fundingAgency'],
            'abstract_available': mining_result['abstract_available'],
            'fulltext_available': mining_result['fulltext_available'],
            'methods_found': mining_result['methods_found'],
            'introduction_found': mining_result['introduction_found'],
            'existing_tool_count': existing_count,
            'novel_tool_count': novel_count,
            'total_tool_count': existing_count + novel_count,
            'is_gff': mining_result['is_gff']
        })

    # Save results
    print("\n" + "=" * 80)
    print("5. Mining Results:")
    print("=" * 80)
    print(f"   Total publications mined: {len(summary)}")
    print(f"   Abstracts mined: {abstract_mined}/{len(pubs_df)} ({100*abstract_mined/len(pubs_df):.1f}%)")
    print(f"   Methods sections found: {methods_found}/{len(pubs_df)} ({100*methods_found/len(pubs_df):.1f}%)")
    print(f"   Introduction sections found: {intro_found}/{len(pubs_df)} ({100*intro_found/len(pubs_df):.1f}%)")
    if fetch_success > 0:
        print(f"   Full text sections extracted: {fetch_success}/{len(pubs_df)} ({100*fetch_success/len(pubs_df):.1f}%)")

    print(f"\n   Existing tool matches: {existing_tool_matches}")
    print(f"   Novel tools found: {novel_tools_found}")
    print(f"   Publications with tools: {len(results)}/{len(pubs_df)} ({100*len(results)/len(pubs_df):.1f}%)")

    # Save to CSV
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if results:
        results_df = pd.DataFrame(results)
        results_df.to_csv(output_file, index=False)
        print(f"\n✅ Saved {len(results)} publications with tools to {output_file}")
    else:
        print(f"\n⚠️  No publications with tools found")

    # Save summary
    summary_file = output_file.parent / 'mining_summary.json'
    with open(summary_file, 'w') as f:
        json.dump({
            'total_publications': len(summary),
            'abstracts_mined': abstract_mined,
            'methods_found': methods_found,
            'intro_found': intro_found,
            'fulltext_fetched': fetch_success,
            'existing_tool_matches': existing_tool_matches,
            'novel_tools_found': novel_tools_found,
            'publications_with_tools': len(results)
        }, f, indent=2)
    print(f"📊 Saved summary to {summary_file}")


if __name__ == '__main__':
    main()
