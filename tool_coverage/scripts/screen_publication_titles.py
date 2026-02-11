#!/usr/bin/env python3
"""
Pre-screen publication titles using Claude Haiku to identify basic/translational research.
Filters out clinical research to save processing costs on irrelevant publications.
"""

import pandas as pd
import os
import argparse
from pathlib import Path
import anthropic
import time
from typing import Set, List, Dict


def load_existing_cache() -> Set[str]:
    """Load PMIDs that already have cached screening results."""
    cache_file = Path('tool_coverage/outputs/title_screening_cache.csv')
    if not cache_file.exists():
        return set()

    try:
        df = pd.read_csv(cache_file)
        return set(df['pmid'].astype(str).tolist())
    except Exception as e:
        print(f"⚠️  Could not load screening cache: {e}")
        return set()


def screen_titles_batch_with_haiku(titles_batch: List[Dict], client: anthropic.Anthropic) -> List[Dict]:
    """
    Screen multiple publication titles in one API call using Claude Haiku.

    Args:
        titles_batch: List of dicts with 'pmid' and 'title' keys
        client: Anthropic API client

    Returns:
        List of dicts with screening results: {'pmid': str, 'is_research': bool, 'reasoning': str}
    """
    # Build numbered list of titles
    titles_list = []
    for i, item in enumerate(titles_batch, 1):
        titles_list.append(f"{i}. [{item['pmid']}] {item['title']}")

    titles_text = "\n".join(titles_list)

    prompt = f"""You are screening publication titles to identify basic science or translational neurofibromatosis research that might describe research tools (cell lines, antibodies, animal models, genetic reagents).

Screen each of the following {len(titles_batch)} publication titles:

{titles_text}

For each title, determine if it describes BASIC SCIENCE or TRANSLATIONAL RESEARCH (INCLUDE) or CLINICAL/PATIENT CARE (EXCLUDE).

**INCLUDE (Basic/Translational research):**
- Laboratory experiments with cell lines, animal models
- Development or use of research tools/reagents
- Molecular biology, genetics, drug discovery
- In vitro or in vivo studies
- Mechanism of disease studies

**EXCLUDE (Clinical research):**
- Case reports, patient outcomes
- Surgical procedures, treatment results
- Clinical trials focused only on patient care
- Diagnostic imaging studies
- Epidemiology, population studies
- Quality of life, patient experience

Respond in this exact format for each title:
#1: INCLUDE|EXCLUDE - Brief reason (one phrase)
#2: INCLUDE|EXCLUDE - Brief reason
... etc

Example:
#1: INCLUDE - Cell line development
#2: EXCLUDE - Clinical case report
#3: INCLUDE - CRISPR screening method"""

    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=8000,  # Haiku max - enough for ~200 titles
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Parse response line by line
        results = []
        for i, item in enumerate(titles_batch, 1):
            # Look for line matching this number
            pattern = f"#{i}:"
            matching_lines = [line for line in response_text.split('\n') if line.strip().startswith(pattern)]

            if matching_lines:
                line = matching_lines[0].split(':', 1)[1].strip()  # Remove "#X:" prefix

                # Parse verdict and reasoning
                is_research = line.upper().startswith('INCLUDE')

                # Extract reasoning (after dash)
                if ' - ' in line:
                    reasoning = line.split(' - ', 1)[1].strip()
                else:
                    reasoning = line.split(maxsplit=1)[1] if len(line.split()) > 1 else "No reason provided"

                results.append({
                    'pmid': item['pmid'],
                    'title': item['title'],
                    'is_research': is_research,
                    'reasoning': reasoning
                })
            else:
                # Couldn't find this title in response
                results.append({
                    'pmid': item['pmid'],
                    'title': item['title'],
                    'is_research': True,  # Default to including
                    'reasoning': 'Parse error - defaulted to include'
                })

        return results

    except Exception as e:
        print(f"  ⚠️  Error screening batch: {e}")
        # Return all as research (default to including on error)
        return [{
            'pmid': item['pmid'],
            'title': item['title'],
            'is_research': True,
            'reasoning': f"Error: {str(e)}"
        } for item in titles_batch]


def screen_publications(publications_df: pd.DataFrame, max_pubs: int = None, batch_size: int = 100) -> pd.DataFrame:
    """
    Screen publication titles using Claude Haiku (batch processing).

    Args:
        publications_df: DataFrame with 'pmid' and 'title' columns
        max_pubs: Maximum number to screen (for testing)
        batch_size: Number of titles to screen per API call (default: 100, max: ~150)

    Returns:
        DataFrame with screening results
    """
    # Check for API key
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found - cannot perform AI screening")
        print("   Returning all publications unscreened")
        publications_df['is_research'] = True
        publications_df['screening_reasoning'] = 'No API key - unscreened'
        return publications_df

    client = anthropic.Anthropic(api_key=api_key)

    # Load existing cache
    cached_pmids = load_existing_cache()
    print(f"📋 Found {len(cached_pmids)} previously screened publications in cache")

    # Identify publications needing screening
    to_screen = publications_df[~publications_df['pmid'].astype(str).isin(cached_pmids)].copy()

    if max_pubs and len(to_screen) > max_pubs:
        print(f"⚙️  Limiting to {max_pubs} publications for screening")
        to_screen = to_screen.head(max_pubs)

    # Filter out rows without titles
    to_screen = to_screen[to_screen['title'].notna() & (to_screen['title'] != 'nan')].copy()

    num_batches = (len(to_screen) + batch_size - 1) // batch_size
    print(f"\n🤖 Screening {len(to_screen)} publication titles with Claude Haiku...")
    print(f"   Using batch processing: {num_batches} batches of ~{batch_size} titles")
    print(f"   Estimated cost: ${num_batches * 0.001:.3f} (vs ${len(to_screen) * 0.0001:.3f} individual)")

    all_results = []

    # Process in batches
    for batch_idx in range(0, len(to_screen), batch_size):
        batch = to_screen.iloc[batch_idx:batch_idx + batch_size]
        batch_num = (batch_idx // batch_size) + 1

        print(f"\n  📦 Batch {batch_num}/{num_batches} ({len(batch)} titles)...")

        # Prepare batch
        titles_batch = [
            {'pmid': row['pmid'], 'title': row.get('title', row.get('publicationTitle', ''))}
            for _, row in batch.iterrows()
        ]

        # Screen batch
        batch_results = screen_titles_batch_with_haiku(titles_batch, client)

        # Display results
        for result in batch_results:
            verdict = "✅ INCLUDE" if result['is_research'] else "❌ EXCLUDE"
            print(f"     {result['pmid']}: {verdict} - {result['reasoning']}")

        all_results.extend(batch_results)

        # Rate limiting: Haiku tier 1 = 50 requests/min, but batches use more tokens
        # Be conservative with 5 seconds between batches
        if batch_num < num_batches:
            time.sleep(5)

    # Save to cache (append mode)
    if all_results:
        results_df = pd.DataFrame(all_results)
        cache_file = Path('tool_coverage/outputs/title_screening_cache.csv')
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Append to existing cache
        if cache_file.exists():
            existing_df = pd.read_csv(cache_file)
            combined_df = pd.concat([existing_df, results_df], ignore_index=True)
            combined_df.drop_duplicates(subset=['pmid'], keep='last', inplace=True)
            combined_df.to_csv(cache_file, index=False)
        else:
            results_df.to_csv(cache_file, index=False)

        print(f"\n💾 Saved screening results to {cache_file}")

        # Also save full detailed report (includes excluded publications for review)
        report_file = Path('tool_coverage/outputs/title_screening_detailed_report.csv')
        full_report_df = results_df[['pmid', 'title', 'is_research', 'reasoning']].copy()
        full_report_df['verdict'] = full_report_df['is_research'].apply(lambda x: 'INCLUDE' if x else 'EXCLUDE')
        full_report_df = full_report_df[['pmid', 'title', 'verdict', 'reasoning']]
        full_report_df.to_csv(report_file, index=False)
        print(f"📋 Saved detailed report to {report_file}")

    # Merge with original DataFrame
    if all_results:
        screening_df = pd.DataFrame(all_results)
        publications_df = publications_df.merge(
            screening_df[['pmid', 'is_research', 'reasoning']],
            on='pmid',
            how='left'
        )
        # Rename for consistency
        if 'reasoning' in publications_df.columns:
            publications_df.rename(columns={'reasoning': 'screening_reasoning'}, inplace=True)

    # Load from cache for previously screened
    if len(cached_pmids) > 0:
        cache_df = pd.read_csv('tool_coverage/outputs/title_screening_cache.csv')
        publications_df = publications_df.merge(
            cache_df[['pmid', 'is_research', 'screening_reasoning']],
            on='pmid',
            how='left',
            suffixes=('', '_cached')
        )
        # Use cached values where available
        publications_df['is_research'] = publications_df['is_research_cached'].fillna(publications_df['is_research'])
        publications_df['screening_reasoning'] = publications_df['screening_reasoning_cached'].fillna(publications_df['screening_reasoning'])
        publications_df.drop(columns=['is_research_cached', 'screening_reasoning_cached'], inplace=True, errors='ignore')

    return publications_df


def main():
    parser = argparse.ArgumentParser(
        description='Pre-screen publication titles to identify basic/translational research'
    )
    parser.add_argument(
        '--max-publications',
        type=int,
        default=None,
        help='Maximum number of publications to screen (for testing)'
    )
    parser.add_argument(
        '--output',
        default='tool_coverage/outputs/screened_publications.csv',
        help='Output file for screened publications'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of titles per API call (default: 100, max: ~150 for Haiku 8K limit)'
    )
    parser.add_argument(
        '--input',
        default='tool_coverage/outputs/publication_list.csv',
        help='Input file with publication list (from prepare_publication_list.py)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Publication Title Screening with Claude Haiku")
    print("=" * 80)

    # Load publications from prepared list
    print("\n1. Loading publication list...")
    input_file = Path(args.input)

    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        print("   Run prepare_publication_list.py first!")
        return

    pubs_df = pd.read_csv(input_file)

    # Standardize title column
    if 'publicationTitle' in pubs_df.columns and 'title' not in pubs_df.columns:
        pubs_df['title'] = pubs_df['publicationTitle']

    print(f"   Loaded {len(pubs_df)} publications from {input_file}")

    # Screen publications
    print("\n3. Screening publication titles...")
    screened_df = screen_publications(pubs_df, max_pubs=args.max_publications, batch_size=args.batch_size)

    # Filter to research publications
    if 'is_research' in screened_df.columns:
        research_pubs = screened_df[screened_df['is_research'] == True].copy()
        excluded_pubs = screened_df[screened_df['is_research'] == False].copy()

        print("\n" + "=" * 80)
        print("Screening Results:")
        print("=" * 80)
        print(f"   ✅ Research publications: {len(research_pubs)}")
        print(f"   ❌ Clinical publications (excluded): {len(excluded_pubs)}")
        print(f"   📊 Total screened: {len(screened_df)}")
        print(f"   💰 Estimated cost: ${len(screened_df) * 0.0001:.4f}")

        # Save filtered list
        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        research_pubs.to_csv(output_file, index=False)
        print(f"\n✅ Saved {len(research_pubs)} research publications to {output_file}")
    else:
        print("\n⚠️  No screening performed (API key missing)")
        screened_df.to_csv(args.output, index=False)


if __name__ == '__main__':
    main()
