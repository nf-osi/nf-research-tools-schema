#!/usr/bin/env python3
"""
Screen publication abstracts using Claude Haiku to identify NF tool usage or development.
This follows title screening and provides more targeted filtering before full-text mining.
"""

import pandas as pd
import os
import argparse
from pathlib import Path
import anthropic
import time
import json
import requests
import xml.etree.ElementTree as ET
from typing import Set, List, Dict
import synapseclient


def load_screening_knowledge() -> Dict:
    """Load domain knowledge for AI screening."""
    config_file = Path(__file__).parent.parent / 'config' / 'ai_screening_knowledge.json'
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {}


def load_existing_cache() -> Set[str]:
    """Load PMIDs that already have cached abstract screening results."""
    cache_file = Path('tool_coverage/outputs/abstract_screening_cache.csv')
    if not cache_file.exists():
        return set()

    try:
        df = pd.read_csv(cache_file)
        return set(df['pmid'].astype(str).tolist())
    except Exception as e:
        print(f"⚠️  Could not load abstract screening cache: {e}")
        return set()


def batch_fetch_abstracts_from_pubmed(pmids: List[str], batch_size: int = 200) -> Dict[str, str]:
    """
    Fetch abstracts for multiple PMIDs in batched PubMed XML API calls.
    Up to 200 PMIDs per request — ~60x faster than one-at-a-time Entrez fetching.

    Args:
        pmids: List of numeric PMID strings (no 'PMID:' prefix)
        batch_size: PMIDs per request (max 200 for PubMed efetch)

    Returns:
        Dict mapping PMID -> abstract text
    """
    results = {}
    total_batches = (len(pmids) + batch_size - 1) // batch_size

    for batch_num, batch_start in enumerate(range(0, len(pmids), batch_size), 1):
        batch = pmids[batch_start:batch_start + batch_size]
        print(f"     Fetching batch {batch_num}/{total_batches} ({len(batch)} PMIDs)...")

        try:
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            params = {
                'db': 'pubmed',
                'id': ','.join(batch),
                'retmode': 'xml',
                'email': 'neurofibromatosis.tools@sagebionetworks.org',
                'tool': 'nf-research-tools-miner'
            }
            response = requests.get(url, params=params, timeout=30)
            if response.status_code != 200:
                print(f"     ⚠️  PubMed API error: {response.status_code}")
                continue

            root = ET.fromstring(response.content)
            for article in root.findall('.//PubmedArticle'):
                pmid_elem = article.find('.//PMID')
                if pmid_elem is None or not pmid_elem.text:
                    continue
                pmid = pmid_elem.text

                abstract_texts = article.findall('.//AbstractText')
                abstract_parts = []
                for text_elem in abstract_texts:
                    label = text_elem.get('Label', '')
                    text = text_elem.text if text_elem.text else ''
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
                if abstract_parts:
                    results[pmid] = ' '.join(abstract_parts)

        except Exception as e:
            print(f"     ⚠️  Batch fetch error: {e}")

        # Rate limiting: 3 req/sec without API key
        if batch_start + batch_size < len(pmids):
            time.sleep(0.34)

    return results


def ensure_abstracts_available(publications_df: pd.DataFrame, syn: synapseclient.Synapse = None) -> pd.DataFrame:
    """
    Ensure all publications have abstracts available.
    Uses batched PubMed XML API (200 PMIDs/request) instead of one-at-a-time fetching.

    Args:
        publications_df: DataFrame with publication info
        syn: Synapse client (unused, kept for API compatibility)

    Returns:
        DataFrame with 'abstract' column populated
    """
    print("\n📄 Ensuring abstracts are available...")

    if 'abstract' not in publications_df.columns:
        publications_df['abstract'] = ''

    missing_mask = publications_df['abstract'].isna() | (publications_df['abstract'] == '')
    num_missing = missing_mask.sum()

    if num_missing == 0:
        print(f"   ✅ All {len(publications_df)} publications already have abstracts")
        return publications_df

    print(f"   📥 Need to fetch {num_missing} abstracts from PubMed (batch mode)...")

    # Extract clean PMIDs for the missing rows
    missing_pmids = [
        str(row['pmid']).replace('PMID:', '').strip()
        for _, row in publications_df[missing_mask].iterrows()
    ]

    # Batch fetch all at once
    fetched = batch_fetch_abstracts_from_pubmed(missing_pmids)

    # Write back into DataFrame
    fetched_count = 0
    for idx, row in publications_df[missing_mask].iterrows():
        clean_pmid = str(row['pmid']).replace('PMID:', '').strip()
        abstract = fetched.get(clean_pmid, '')
        if abstract:
            publications_df.at[idx, 'abstract'] = abstract
            fetched_count += 1

    has_abstract = ~(publications_df['abstract'].isna() | (publications_df['abstract'] == ''))
    print(f"\n   ✅ {has_abstract.sum()} publications have abstracts ({fetched_count} newly fetched)")
    print(f"   ⚠️  {(~has_abstract).sum()} publications missing abstracts (will be excluded)")

    return publications_df


def screen_abstracts_batch_with_haiku(abstracts_batch: List[Dict], client: anthropic.Anthropic,
                                       knowledge: Dict = None) -> List[Dict]:
    """
    Screen multiple publication abstracts in one API call using Claude Haiku.

    Args:
        abstracts_batch: List of dicts with 'pmid', 'title', and 'abstract' keys
        client: Anthropic API client
        knowledge: Domain knowledge dictionary for screening

    Returns:
        List of dicts with screening results: {'pmid': str, 'has_nf_tools': bool, 'reasoning': str}
    """
    if knowledge is None:
        knowledge = load_screening_knowledge()

    # Build numbered list of abstracts
    abstracts_list = []
    for i, item in enumerate(abstracts_batch, 1):
        abstracts_list.append(f"{i}. [{item['pmid']}] {item['title']}\n   Abstract: {item['abstract'][:500]}...")  # Truncate for token limit

    abstracts_text = "\n\n".join(abstracts_list)

    # Build examples from knowledge base
    comp_tools = knowledge.get('computational_tools', {})
    known_tools = []
    for category, tools in comp_tools.get('known_established_tools', {}).items():
        known_tools.extend(tools[:3])  # Take first 3 from each category
    known_tools_str = ", ".join(known_tools[:15])  # Limit to 15 examples

    excluded_terms = []
    for category, terms in comp_tools.get('excluded_false_positives', {}).items():
        if category == 'programming_languages':
            excluded_terms.extend(terms[:5])
    excluded_str = ", ".join(excluded_terms)

    animal_models = knowledge.get('animal_models', {})
    nf_models_str = ", ".join(animal_models.get('nf_specific_models', {}).get('Nf1_models', [])[:3])

    prompt = f"""You are screening publication abstracts to identify neurofibromatosis (NF) research that USES or DEVELOPS research tools.

Screen each of the following {len(abstracts_batch)} publication abstracts for evidence of NF tool usage or development:

{abstracts_text}

Research tools include these 9 categories:
1. **Antibodies** - antibodies used for detection, immunostaining, Western blot
2. **Cell lines** - NF-specific lines (ST88-14, sNF96.2, ipNF95.11) or generic lines used for NF research
3. **Animal models** - NF-specific genetic models ({nf_models_str}, etc.)
4. **Genetic reagents** - plasmids, CRISPR constructs, shRNA, viral vectors
5. **Biobanks** - tissue repositories, specimen collections
6. **Computational tools** - software, pipelines, algorithms (e.g., {known_tools_str})
7. **Organoids/3D models** - organoids, spheroids, 3D cultures, assembloids
8. **Patient-derived xenografts (PDX)** - PDX models, patient tissue grafts
9. **Clinical assessment tools** - questionnaires (SF-36, PROMIS, PedsQL), outcome measures

**IMPORTANT DISTINCTIONS:**

**Computational Tools - Novel vs Established:**
- **NOVEL tools** (INCLUDE): Tool name in title + "novel"/"new"/"developed" (e.g., "NovelToolName: a new analysis pipeline")
- **ESTABLISHED tools** (INCLUDE): Using known tools for analysis (ImageJ, GraphPad Prism, STAR, Seurat, etc.)
- **DO NOT include as tools**: Programming languages ({excluded_str}), IDEs (RStudio, Jupyter), or generic terms ("analysis", "software", "pipeline" without specific names)

**Animal Models - NF-specific vs Generic:**
- **INCLUDE**: NF-specific models (Nf1+/-, Nf2-/-, heterozygous Nf1 knockout, etc.)
- **EXCLUDE**: Generic strains alone (C57BL/6, nude mice, BALB/c) UNLESS combined with NF mutation

**INCLUDE if abstract mentions:**
- Using ANY of the above tool types for NF research
- Developing novel tools (check title for tool name + "novel"/"new"/"developed")
- NF-specific animal models or cell lines
- Specific computational tools by name (not just "software" or "R")
- Patient assessments using standardized instruments

**EXCLUDE if abstract:**
- Pure review/meta-analysis/commentary
- Generic animal strains without NF mutations
- Programming languages mentioned without specific tool names
- Generic terms without specific tools ("we used software", "statistical analysis")
- Purely observational without research tools

Respond in this exact format for each abstract:
#1: INCLUDE|EXCLUDE - Brief reason (one phrase)
#2: INCLUDE|EXCLUDE - Brief reason
... etc

Example:
#1: INCLUDE - Uses MPNST cell lines
#2: EXCLUDE - Clinical observational study
#3: INCLUDE - Mouse model development"""

    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=8000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Parse response line by line
        results = []
        for i, item in enumerate(abstracts_batch, 1):
            # Look for line matching this number
            pattern = f"#{i}:"
            matching_lines = [line for line in response_text.split('\n') if line.strip().startswith(pattern)]

            if matching_lines:
                line = matching_lines[0].split(':', 1)[1].strip()  # Remove "#X:" prefix

                # Parse verdict and reasoning
                has_nf_tools = line.upper().startswith('INCLUDE')

                # Extract reasoning (after dash)
                if ' - ' in line:
                    reasoning = line.split(' - ', 1)[1].strip()
                else:
                    reasoning = line.split(maxsplit=1)[1] if len(line.split()) > 1 else "No reason provided"

                results.append({
                    'pmid': item['pmid'],
                    'title': item['title'],
                    'abstract': item['abstract'],
                    'has_nf_tools': has_nf_tools,
                    'reasoning': reasoning
                })
            else:
                # Couldn't find this abstract in response
                results.append({
                    'pmid': item['pmid'],
                    'title': item['title'],
                    'abstract': item['abstract'],
                    'has_nf_tools': True,  # Default to including
                    'reasoning': 'Parse error - defaulted to include'
                })

        return results

    except Exception as e:
        print(f"  ⚠️  Error screening batch: {e}")
        # Return all as having tools (default to including on error)
        return [{
            'pmid': item['pmid'],
            'title': item['title'],
            'abstract': item['abstract'],
            'has_nf_tools': True,
            'reasoning': f"Error: {str(e)}"
        } for item in abstracts_batch]


def screen_abstracts(publications_df: pd.DataFrame, max_pubs: int = None, batch_size: int = 50) -> pd.DataFrame:
    """
    Screen publication abstracts using Claude Haiku (batch processing).

    Args:
        publications_df: DataFrame with 'pmid', 'title', and 'abstract' columns
        max_pubs: Maximum number to screen (for testing)
        batch_size: Number of abstracts to screen per API call (default: 50, abstracts are longer than titles)

    Returns:
        DataFrame with screening results
    """
    # Check for API key
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found - cannot perform AI screening")
        print("   Returning all publications unscreened")
        publications_df['has_nf_tools'] = True
        publications_df['abstract_screening_reasoning'] = 'No API key - unscreened'
        return publications_df

    client = anthropic.Anthropic(api_key=api_key)

    # Load domain knowledge for screening
    print("📚 Loading domain knowledge for screening...")
    knowledge = load_screening_knowledge()
    if knowledge:
        comp_tools = knowledge.get('computational_tools', {})
        known_count = sum(len(tools) for tools in comp_tools.get('known_established_tools', {}).values())
        excluded_count = sum(len(terms) for terms in comp_tools.get('excluded_false_positives', {}).values())
        print(f"   - {known_count} known computational tools")
        print(f"   - {excluded_count} excluded terms (false positives)")
    else:
        print("   ⚠️  No domain knowledge loaded - using basic screening")

    # Load existing cache
    cached_pmids = load_existing_cache()
    print(f"📋 Found {len(cached_pmids)} previously screened abstracts in cache")

    # Identify publications needing screening
    to_screen = publications_df[~publications_df['pmid'].astype(str).isin(cached_pmids)].copy()

    if max_pubs and len(to_screen) > max_pubs:
        print(f"⚙️  Limiting to {max_pubs} publications for screening")
        to_screen = to_screen.head(max_pubs)

    # Filter out rows without abstracts
    to_screen = to_screen[to_screen['abstract'].notna() & (to_screen['abstract'] != '')].copy()

    num_batches = (len(to_screen) + batch_size - 1) // batch_size
    print(f"\n🤖 Screening {len(to_screen)} publication abstracts with Claude Haiku...")
    print(f"   Using batch processing: {num_batches} batches of ~{batch_size} abstracts")
    print(f"   Estimated cost: ${num_batches * 0.002:.3f} (abstracts use more tokens than titles)")

    all_results = []

    # Process in batches
    for batch_idx in range(0, len(to_screen), batch_size):
        batch = to_screen.iloc[batch_idx:batch_idx + batch_size]
        batch_num = (batch_idx // batch_size) + 1

        print(f"\n  📦 Batch {batch_num}/{num_batches} ({len(batch)} abstracts)...")

        # Prepare batch
        abstracts_batch = [
            {
                'pmid': row['pmid'],
                'title': row.get('title', row.get('publicationTitle', '')),
                'abstract': row.get('abstract', '')
            }
            for _, row in batch.iterrows()
        ]

        # Screen batch
        batch_results = screen_abstracts_batch_with_haiku(abstracts_batch, client, knowledge)

        # Display results
        for result in batch_results:
            verdict = "✅ INCLUDE" if result['has_nf_tools'] else "❌ EXCLUDE"
            print(f"     {result['pmid']}: {verdict} - {result['reasoning']}")

        all_results.extend(batch_results)

        # Rate limiting: Haiku tier 1 = 50 requests/min
        # Be conservative with 5 seconds between batches
        if batch_num < num_batches:
            time.sleep(5)

    # Save to cache (append mode)
    if all_results:
        results_df = pd.DataFrame(all_results)
        cache_file = Path('tool_coverage/outputs/abstract_screening_cache.csv')
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
        report_file = Path('tool_coverage/outputs/abstract_screening_detailed_report.csv')
        full_report_df = results_df[['pmid', 'title', 'has_nf_tools', 'reasoning']].copy()
        full_report_df['verdict'] = full_report_df['has_nf_tools'].apply(lambda x: 'INCLUDE' if x else 'EXCLUDE')
        full_report_df = full_report_df[['pmid', 'title', 'verdict', 'reasoning']]
        full_report_df.to_csv(report_file, index=False)
        print(f"📋 Saved detailed report to {report_file}")

    # Merge with original DataFrame
    if all_results:
        screening_df = pd.DataFrame(all_results)
        publications_df = publications_df.merge(
            screening_df[['pmid', 'has_nf_tools', 'reasoning']],
            on='pmid',
            how='left'
        )
        # Rename for consistency
        if 'reasoning' in publications_df.columns:
            publications_df.rename(columns={'reasoning': 'abstract_screening_reasoning'}, inplace=True)

    # Load from cache for previously screened
    if len(cached_pmids) > 0:
        cache_df = pd.read_csv('tool_coverage/outputs/abstract_screening_cache.csv')
        publications_df = publications_df.merge(
            cache_df[['pmid', 'has_nf_tools', 'abstract_screening_reasoning']],
            on='pmid',
            how='left',
            suffixes=('', '_cached')
        )
        # Use cached values where available
        publications_df['has_nf_tools'] = publications_df['has_nf_tools_cached'].fillna(publications_df['has_nf_tools'])
        publications_df['abstract_screening_reasoning'] = publications_df['abstract_screening_reasoning_cached'].fillna(publications_df['abstract_screening_reasoning'])
        publications_df.drop(columns=['has_nf_tools_cached', 'abstract_screening_reasoning_cached'], inplace=True, errors='ignore')

    return publications_df


def main():
    parser = argparse.ArgumentParser(
        description='Screen publication abstracts to identify NF tool usage or development'
    )
    parser.add_argument(
        '--max-publications',
        type=int,
        default=None,
        help='Maximum number of publications to screen (for testing)'
    )
    parser.add_argument(
        '--output',
        default='tool_coverage/outputs/abstract_screened_publications.csv',
        help='Output file for screened publications'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of abstracts per API call (default: 50, abstracts are longer)'
    )
    parser.add_argument(
        '--input',
        default='tool_coverage/outputs/screened_publications.csv',
        help='Input file with title-screened publications'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Publication Abstract Screening with Claude Haiku")
    print("=" * 80)

    # Load publications from title screening
    print("\n1. Loading title-screened publications...")
    input_file = Path(args.input)

    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        print("   Run screen_publication_titles.py first!")
        return

    pubs_df = pd.read_csv(input_file)

    # Standardize title column
    if 'publicationTitle' in pubs_df.columns and 'title' not in pubs_df.columns:
        pubs_df['title'] = pubs_df['publicationTitle']

    print(f"   Loaded {len(pubs_df)} publications from {input_file}")

    # Login to Synapse (for potential abstract fetching from Synapse table)
    print("\n2. Connecting to Synapse...")
    syn = synapseclient.Synapse()
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token, silent=True)
        print("   ✅ Connected to Synapse")
    else:
        print("   ⚠️  No SYNAPSE_AUTH_TOKEN - will only use PubMed for abstracts")
        syn = None

    # Ensure abstracts are available
    print("\n3. Ensuring abstracts are available...")
    pubs_df = ensure_abstracts_available(pubs_df, syn)

    # Screen abstracts
    print("\n4. Screening publication abstracts...")
    screened_df = screen_abstracts(pubs_df, max_pubs=args.max_publications, batch_size=args.batch_size)

    # Filter to publications with NF tools
    if 'has_nf_tools' in screened_df.columns:
        tool_pubs = screened_df[screened_df['has_nf_tools'] == True].copy()
        excluded_pubs = screened_df[screened_df['has_nf_tools'] == False].copy()

        print("\n" + "=" * 80)
        print("Abstract Screening Results:")
        print("=" * 80)
        print(f"   ✅ Publications with NF tools: {len(tool_pubs)}")
        print(f"   ❌ Publications without NF tools (excluded): {len(excluded_pubs)}")
        print(f"   📊 Total screened: {len(screened_df)}")
        print(f"   💰 Estimated cost: ${len(screened_df) * 0.0002:.4f}")

        # Save filtered list
        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        tool_pubs.to_csv(output_file, index=False)
        print(f"\n✅ Saved {len(tool_pubs)} publications with NF tools to {output_file}")
    else:
        print("\n⚠️  No screening performed (API key missing)")
        screened_df.to_csv(args.output, index=False)


if __name__ == '__main__':
    main()
