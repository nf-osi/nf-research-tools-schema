#!/usr/bin/env python3
"""
Prepare list of publications for screening by fetching titles from Synapse and PubMed.
Fast operation - only gets metadata, not full text.

Supports multiple query types for different tool categories:
- bench: Computational tools, PDX models, organoids (default)
- clinical: Clinical assessment tools (QoL, questionnaires)
- organoid: Advanced cellular models (3D cultures)
"""

import synapseclient
import pandas as pd
import requests
import time
import os
import json
import argparse
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import List, Set, Dict, Tuple

# PubMed API configuration
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EMAIL = "your.email@example.com"
TOOL_NAME = "nf-research-tools-miner"

# Legacy query filters (bench science) - kept for backward compatibility
PUBMED_QUERY_FILTERS = [
    '(neurofibroma*[Abstract] NOT case*[Title/Journal] NOT review[Title] NOT pain[Title] NOT tomography[Title]',
    'NOT outcomes[Title] NOT individiual*[Title] NOT patient*[Title] NOT population[Title]',
    'NOT clinic*[Title] NOT cohort*[Title] NOT child*[Title] NOT current[Title] NOT MRI*[Title]',
    'NOT guideline*[Title] NOT perspective*[Title] NOT retrospective[Title] NOT after[Title]',
    'NOT "quality of life"[Title] NOT pediatric*[Title] NOT adult*[Title] NOT resection[Title]',
    'NOT parent*[Title] NOT prognostic[Title] NOT surg*[Title] NOT facial[Title] NOT giant[Title]',
    'NOT prevalence[Title] NOT experience[Title] NOT famil*[Title] NOT presentation[Title]',
    'NOT trial[Title] NOT "novel mutation"[Title] NOT presenting[Title] NOT overview[Title]',
    'NOT pregnancy[Title] NOT lady[Title] NOT female[Title] NOT woman[Title] NOT women[Title]',
    'NOT "hearing loss"[Title] NOT "pictorial essay"[Title] NOT healthcare[Title] NOT CT[Title]',
    'NOT "rare occurence"[Title] NOT update*[Title] NOT initiative*[Title] NOT male[Title] NOT social[Title]',
    'NOT people[Title] NOT decision*[Title] NOT autopsy*[Title] NOT isolated[Title] NOT solitary[Title]',
    'NOT "JA clinical reports"[Journal])',
    'AND (hasabstract)',
    'AND (free full text[Filter])',
    'AND (Journal Article[Publication Type])'
]


def load_query_config() -> Dict:
    """Load query configurations from JSON file."""
    config_path = Path(__file__).parent.parent / 'config' / 'pubmed_queries.json'
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Warning: Could not load query config: {e}")
        print(f"   Using legacy bench science query")
        return None


def get_query_filters(query_type: str = 'bench') -> Tuple[List[str], List[str]]:
    """
    Get PubMed query filters and title exclusions for a specific query type.

    Returns:
        (pubmed_filters, title_exclusions)
    """
    # Map CLI query types to config keys
    query_type_map = {
        'bench': 'bench_science',
        'clinical': 'clinical_assessment',
        'organoid': 'organoid_focused'
    }

    config = load_query_config()
    config_key = query_type_map.get(query_type, query_type)

    if config is None or config_key not in config.get('queries', {}):
        # Fallback to legacy bench query
        print(f"   ⚠️  Using legacy bench science filters (config not found)")
        return (
            PUBMED_QUERY_FILTERS,
            ['case report', 'clinical case', 'patient outcome', 'surgical',
             'clinical trial', 'retrospective', 'prospective study',
             'case series', 'clinical experience', 'treatment outcome']
        )

    print(f"   ✓ Loaded {query_type} query from config")
    query_config = config['queries'][config_key]
    filters = query_config.get('filters', [])

    # Determine title exclusions based on query type
    if query_type == 'clinical':
        # Clinical query: minimal exclusions (keep clinical studies!)
        exclusions = [
            'case report', 'case series', 'pictorial essay',
            'autopsy', 'letter to editor', 'erratum'
        ]
    elif query_type == 'organoid':
        # Organoid query: exclude clinical but not bench
        exclusions = [
            'case report', 'clinical case', 'case series',
            'patient outcome', 'treatment outcome'
        ]
    else:  # bench
        # Bench query: exclude clinical studies
        exclusions = [
            'case report', 'clinical case', 'patient outcome', 'surgical',
            'clinical trial', 'retrospective', 'prospective study',
            'case series', 'clinical experience', 'treatment outcome'
        ]

    return (filters, exclusions)


def query_pubmed(query: str, max_results: int = 10000) -> List[str]:
    """Query PubMed for PMIDs matching the query."""
    params = {
        'db': 'pubmed',
        'term': query,
        'retmax': max_results,
        'retmode': 'xml',
        'email': EMAIL,
        'tool': TOOL_NAME
    }

    try:
        time.sleep(0.34)  # Rate limit
        response = requests.get(f"{EUTILS_BASE}esearch.fcgi", params=params, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        pmids = [id_elem.text for id_elem in root.findall('.//Id')]
        return pmids

    except Exception as e:
        print(f"Error querying PubMed: {e}")
        return []


def fetch_pubmed_metadata_batch(pmids: List[str], batch_size: int = 200) -> pd.DataFrame:
    """Fetch metadata for a batch of PMIDs."""
    all_pubs = []

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]
        print(f"   Fetching metadata for PMIDs {i+1}-{min(i+batch_size, len(pmids))}...")

        params = {
            'db': 'pubmed',
            'id': ','.join(batch),
            'retmode': 'xml',
            'email': EMAIL,
            'tool': TOOL_NAME
        }

        try:
            time.sleep(0.34)  # Rate limit
            response = requests.get(f"{EUTILS_BASE}efetch.fcgi", params=params, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            for article in root.findall('.//PubmedArticle'):
                try:
                    pmid_elem = article.find('.//PMID')
                    pmid = f"PMID:{pmid_elem.text}" if pmid_elem is not None else None

                    title_elem = article.find('.//ArticleTitle')
                    title = title_elem.text if title_elem is not None else ''

                    journal_elem = article.find('.//Journal/Title')
                    journal = journal_elem.text if journal_elem is not None else ''

                    year_elem = article.find('.//PubDate/Year')
                    year = year_elem.text if year_elem is not None else ''

                    # Get DOI
                    doi = None
                    for article_id in article.findall('.//ArticleId'):
                        if article_id.get('IdType') == 'doi':
                            doi = article_id.text
                            break

                    if pmid and title:
                        all_pubs.append({
                            'pmid': pmid,
                            'title': title,
                            'journal': journal,
                            'year': year,
                            'doi': doi
                        })

                except Exception as e:
                    print(f"   Error parsing article: {e}")
                    continue

        except Exception as e:
            print(f"   Error fetching batch: {e}")
            continue

    return pd.DataFrame(all_pubs)


def check_pmc_availability(pmids: List[str]) -> Set[str]:
    """Check which PMIDs have full text available in PMC."""
    available_pmids = set()

    # Process in batches of 200
    batch_size = 200
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]

        # Clean PMIDs
        clean_batch = [p.replace('PMID:', '') for p in batch]

        params = {
            'dbfrom': 'pubmed',
            'db': 'pmc',
            'id': ','.join(clean_batch),
            'email': EMAIL,
            'tool': TOOL_NAME
        }

        try:
            time.sleep(0.34)  # Rate limit
            response = requests.get(f"{EUTILS_BASE}elink.fcgi", params=params, timeout=30)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            for linkset in root.findall('.//LinkSet'):
                pmid_elem = linkset.find('.//Id')
                if pmid_elem is not None:
                    pmid = f"PMID:{pmid_elem.text}"

                    # Check if has PMC links
                    pmc_links = linkset.findall('.//Link/Id')
                    if pmc_links:
                        available_pmids.add(pmid)

        except Exception as e:
            print(f"   Warning: Could not check PMC availability for batch: {e}")
            continue

    return available_pmids


def load_previously_reviewed_pmids() -> Set[str]:
    """Load PMIDs that have been reviewed (from YAML files)."""
    reviewed_pmids = set()

    # Check YAML review files
    results_dir = Path('tool_reviews/results')
    if results_dir.exists():
        try:
            yaml_files = results_dir.glob('*_tool_review.yaml')
            for yaml_file in yaml_files:
                filename = yaml_file.stem
                pmid = filename.replace('_tool_review', '')
                if not pmid.startswith('PMID:'):
                    pmid = f"PMID:{pmid}"
                reviewed_pmids.add(pmid)
        except Exception as e:
            print(f"  ⚠️  Could not scan review YAML files: {e}")

    return reviewed_pmids


def should_exclude_publication(title: str, journal: str, exclude_keywords: List[str]) -> bool:
    """Check if publication should be excluded based on title/journal filters."""
    if not title:
        return True

    title_lower = title.lower()
    journal_lower = journal.lower() if journal else ''

    # Check exclusion keywords
    for keyword in exclude_keywords:
        if keyword in title_lower:
            return True

    # Exclude specific journals (universal across all query types)
    exclude_journals = ['ja clinical reports']
    if any(j in journal_lower for j in exclude_journals):
        return True

    return False


def main():
    parser = argparse.ArgumentParser(
        description='Prepare list of publications for title screening (fast - metadata only)'
    )
    parser.add_argument(
        '--query-type',
        choices=['bench', 'clinical', 'organoid'],
        default='bench',
        help='Type of query to run (default: bench)'
    )
    parser.add_argument(
        '--skip-pubmed-query',
        action='store_true',
        help='Skip PubMed query (only use Synapse publications)'
    )
    parser.add_argument(
        '--skip-synapse',
        action='store_true',
        help='Skip Synapse publications (PubMed query only)'
    )
    parser.add_argument(
        '--test-sample',
        type=int,
        help='Test mode: limit to N publications'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Output file for publication list (auto-generated if not specified)'
    )

    args = parser.parse_args()

    # Auto-generate output filename based on query type
    if args.output is None:
        args.output = f'tool_coverage/outputs/publication_list_{args.query_type}.csv'

    print("=" * 80)
    print(f"Prepare Publication List - {args.query_type.upper()} Query")
    print("=" * 80)

    # Get query-specific filters
    pubmed_filters, title_exclusions = get_query_filters(args.query_type)

    print(f"\nQuery Type: {args.query_type}")
    print(f"Title Exclusions: {len(title_exclusions)} keywords")
    if args.test_sample:
        print(f"🧪 TEST MODE: Limited to {args.test_sample} publications")

    all_publications = []

    # Login to Synapse (unless skipped)
    if not args.skip_synapse:
        print("\n1. Connecting to Synapse...")
        syn = synapseclient.Synapse()
        syn.login(silent=True)

        # Load previously reviewed PMIDs
        print("\n2. Loading previously reviewed publications...")
        previously_reviewed = load_previously_reviewed_pmids()
        print(f"   - {len(previously_reviewed)} previously reviewed publications")

        # Load publications from Synapse
        print("\n3. Loading NF Portal publications from Synapse...")
        pub_query = syn.tableQuery('SELECT pmid, title, doi, journal, "year" FROM syn16857542')
        pub_df = pub_query.asDataFrame()

        # Standardize PMID format
        if 'pmid' in pub_df.columns:
            pub_df['pmid'] = pub_df['pmid'].astype(str)
            pub_df.loc[~pub_df['pmid'].str.startswith('PMID:'), 'pmid'] = 'PMID:' + pub_df['pmid']

        print(f"   - {len(pub_df)} total NF Portal publications")

        # Apply title/journal filters
        print(f"\n4. Applying {args.query_type} title/journal filters...")
        initial_count = len(pub_df)
        pub_df['exclude'] = pub_df.apply(
            lambda row: should_exclude_publication(
                row.get('title', ''),
                row.get('journal', ''),
                title_exclusions
            ),
            axis=1
        )
        excluded_count = pub_df['exclude'].sum()
        pub_df = pub_df[~pub_df['exclude']].drop(columns=['exclude'])
        print(f"   - Excluded {excluded_count} publications based on title/journal filters")
        print(f"   - {len(pub_df)} publications remain")

        # Check PMC availability
        print("\n5. Checking PMC full text availability...")
        nf_portal_pmids = pub_df['pmid'].dropna().unique().tolist()

        if args.test_sample:
            nf_portal_pmids = nf_portal_pmids[:args.test_sample]
            print(f"   🧪 TEST MODE: Checking first {len(nf_portal_pmids)} PMIDs")
        else:
            print(f"   - Checking {len(nf_portal_pmids)} PMIDs...")

        pmc_available = set()
        batch_size = 500
        for i in range(0, len(nf_portal_pmids), batch_size):
            batch = nf_portal_pmids[i:i + batch_size]
            batch_available = check_pmc_availability(batch)
            pmc_available.update(batch_available)
            print(f"     Checked {min(i + batch_size, len(nf_portal_pmids))}/{len(nf_portal_pmids)} PMIDs... ({len(pmc_available)} with full text)")

        print(f"   - {len(pmc_available)} publications have full text in PMC")

        # Filter to only PMC-available publications
        before_pmc = len(pub_df)
        pub_df = pub_df[pub_df['pmid'].isin(pmc_available)].copy()
        print(f"   - Excluded {before_pmc - len(pub_df)} publications without PMC full text")

        # Add source tag
        pub_df['source'] = 'synapse'
        all_publications.append(pub_df)
    else:
        print("\n1-5. Skipping Synapse (--skip-synapse enabled)")
        previously_reviewed = set()

    # Query PubMed for additional publications
    if not args.skip_pubmed_query:
        print(f"\n6. Querying PubMed for {args.query_type} publications...")
        pubmed_query = ' '.join(pubmed_filters)
        print(f"   - Query: {pubmed_query[:150]}...")

        max_results = args.test_sample if args.test_sample else 10000
        pubmed_pmids = query_pubmed(pubmed_query, max_results=max_results)
        print(f"   - Found {len(pubmed_pmids)} publications in PubMed")

        if pubmed_pmids:
            # Format with PMID: prefix
            pubmed_pmids_formatted = [f"PMID:{p}" if not p.startswith('PMID:') else p for p in pubmed_pmids]

            # Filter out already loaded and reviewed
            if all_publications:
                synapse_pmids = set(pd.concat(all_publications)['pmid'].dropna().unique())
            else:
                synapse_pmids = set()
            all_existing = synapse_pmids.union(previously_reviewed)
            new_pmids = [p for p in pubmed_pmids_formatted if p not in all_existing]

            print(f"   - {len(new_pmids)} new publications (after excluding loaded/reviewed)")

            if new_pmids:
                # Fetch metadata
                print("   - Fetching metadata for new PubMed publications...")
                new_pmids_clean = [p.replace('PMID:', '') for p in new_pmids]
                pubmed_df = fetch_pubmed_metadata_batch(new_pmids_clean)
                print(f"   - Retrieved metadata for {len(pubmed_df)} publications")

                if len(pubmed_df) > 0:
                    pubmed_df['source'] = 'pubmed'
                    all_publications.append(pubmed_df)
    else:
        print("\n6. Skipping PubMed query (--skip-pubmed-query enabled)")

    # Merge all sources
    if not all_publications:
        print("\n❌ No publications found!")
        return 1

    pub_df = pd.concat(all_publications, ignore_index=True)
    print(f"\n   - Total publications after merge: {len(pub_df)}")

    # Load existing links and exclude (unless testing)
    if not args.test_sample and not args.skip_synapse:
        print("\n7. Filtering out already-linked publications...")
        link_query = syn.tableQuery("SELECT pmid FROM syn51735450")
        link_df = link_query.asDataFrame()

        linked_pmids = set()
        if 'pmid' in link_df.columns:
            linked_pmids = set(link_df['pmid'].dropna().astype(str).unique())
            linked_pmids = {f"PMID:{p.replace('PMID:', '')}" for p in linked_pmids if p and p != 'nan'}

        print(f"   - {len(linked_pmids)} publications already linked to tools")

        # Filter out linked and reviewed
        all_to_exclude = linked_pmids.union(previously_reviewed)
        before_filter = len(pub_df)
        pub_df = pub_df[~pub_df['pmid'].isin(all_to_exclude)].copy()
        print(f"   - Excluded {before_filter - len(pub_df)} publications (already linked/reviewed)")
        print(f"   - {len(pub_df)} publications remain for screening")
    else:
        print("\n7. Skipping already-linked filter (test mode or no Synapse)")

    # Add query type metadata
    pub_df['query_type'] = args.query_type

    # Save output
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    pub_df.to_csv(output_file, index=False)

    print("\n" + "=" * 80)
    print(f"Publication List Prepared ({args.query_type.upper()}):")
    print("=" * 80)
    print(f"   Total publications: {len(pub_df)}")
    print(f"   With PMC full text: {len(pub_df)}")
    print(f"   Query type: {args.query_type}")
    print(f"   Ready for mining")
    print(f"\n✅ Saved to {output_file}")

    return 0


if __name__ == '__main__':
    exit(main())
