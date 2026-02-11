#!/usr/bin/env python3
"""
Prepare list of publications for screening by fetching titles from Synapse and PubMed.
Fast operation - only gets metadata, not full text.
"""

import synapseclient
import pandas as pd
import requests
import time
import os
import argparse
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import List, Set

# PubMed API configuration
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EMAIL = "your.email@example.com"
TOOL_NAME = "nf-research-tools-miner"

# PubMed query filters
PUBMED_QUERY_FILTERS = [
    '(neurofibroma*[Abstract] NOT case[Title] NOT review[Title] NOT pain[Title] NOT tomography[Title]',
    'NOT outcomes[Title] NOT individiual*[Title] NOT patient*[Title] NOT population[Title]',
    'NOT clinic*[Title] NOT cohort*[Title] NOT child*[Title] NOT current[Title] NOT MRI*[Title]',
    'NOT guideline*[Title] NOT perspective*[Title] NOT retrospective[Title] NOT after[Title]',
    'NOT "quality of life"[Title] NOT pediatric*[Title] NOT adult*[Title] NOT resection[Title]',
    'NOT parent*[Title] NOT prognostic[Title] NOT surg*[Title] NOT facial[Title]',
    'NOT prevalence[Title] NOT experience[Title] NOT famil*[Title] NOT presentation[Title]',
    'NOT trial[Title] NOT "novel mutation"[Title] NOT presenting[Title] NOT overview[Title]',
    'NOT pregnancy[Title] NOT lady[Title] NOT female[Title] NOT woman[Title] NOT women[Title]',
    'NOT "hearing loss"[Title] NOT "pictorial essay"[Title]',
    'NOT "Clinical case reports"[Journal] NOT "JA clinical reports"[Journal])',
    'AND (hasabstract)',
    'AND (free full text[Filter])',
    'AND (Journal Article[Publication Type])'
]


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


def should_exclude_publication(title: str, journal: str) -> bool:
    """Check if publication should be excluded based on title/journal filters."""
    if not title:
        return True

    title_lower = title.lower()
    journal_lower = journal.lower() if journal else ''

    # Exclude clinical/case report keywords
    exclude_keywords = [
        'case report', 'clinical case', 'patient outcome', 'surgical',
        'clinical trial', 'retrospective', 'prospective study',
        'case series', 'clinical experience', 'treatment outcome'
    ]

    for keyword in exclude_keywords:
        if keyword in title_lower:
            return True

    # Exclude specific journals
    exclude_journals = ['clinical case reports', 'ja clinical reports']
    if any(j in journal_lower for j in exclude_journals):
        return True

    return False


def main():
    parser = argparse.ArgumentParser(
        description='Prepare list of publications for title screening (fast - metadata only)'
    )
    parser.add_argument(
        '--skip-pubmed-query',
        action='store_true',
        help='Skip PubMed query (only use Synapse publications)'
    )
    parser.add_argument(
        '--output',
        default='tool_coverage/outputs/publication_list.csv',
        help='Output file for publication list'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Prepare Publication List (Step 1: Metadata Only)")
    print("=" * 80)

    # Login to Synapse
    print("\n1. Connecting to Synapse...")
    syn = synapseclient.Synapse()
    syn.login(silent=True)

    # Load previously reviewed PMIDs
    print("\n2. Loading previously reviewed publications...")
    previously_reviewed = load_previously_reviewed_pmids()
    print(f"   - {len(previously_reviewed)} previously reviewed publications")

    # Load publications from Synapse
    print("\n3. Loading NF Portal publications from Synapse...")
    pub_query = syn.tableQuery("SELECT pmid, publicationTitle, title, doi, journal, year FROM syn16857542")
    pub_df = pub_query.asDataFrame()

    # Standardize columns
    if 'publicationTitle' in pub_df.columns and 'title' not in pub_df.columns:
        pub_df['title'] = pub_df['publicationTitle']

    # Standardize PMID format
    if 'pmid' in pub_df.columns:
        pub_df['pmid'] = pub_df['pmid'].astype(str)
        pub_df.loc[~pub_df['pmid'].str.startswith('PMID:'), 'pmid'] = 'PMID:' + pub_df['pmid']

    print(f"   - {len(pub_df)} total NF Portal publications")

    # Apply title/journal filters
    print("\n4. Applying title/journal filters...")
    initial_count = len(pub_df)
    pub_df['exclude'] = pub_df.apply(
        lambda row: should_exclude_publication(
            row.get('title', ''),
            row.get('journal', '')
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

    # Query PubMed for additional publications
    if not args.skip_pubmed_query:
        print("\n6. Querying PubMed for additional publications...")
        pubmed_query = ' '.join(PUBMED_QUERY_FILTERS)
        print(f"   - Query: {pubmed_query[:200]}...")

        pubmed_pmids = query_pubmed(pubmed_query, max_results=10000)
        print(f"   - Found {len(pubmed_pmids)} publications in PubMed")

        if pubmed_pmids:
            # Format with PMID: prefix
            pubmed_pmids_formatted = [f"PMID:{p}" if not p.startswith('PMID:') else p for p in pubmed_pmids]

            # Filter out already loaded and reviewed
            synapse_pmids = set(pub_df['pmid'].dropna().unique())
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
                    pub_df = pd.concat([pub_df, pubmed_df], ignore_index=True)
                    print(f"   - Total publications after merge: {len(pub_df)}")
    else:
        print("\n6. Skipping PubMed query (--skip-pubmed-query enabled)")

    # Load existing links and exclude
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

    # Save output
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    pub_df.to_csv(output_file, index=False)

    print("\n" + "=" * 80)
    print("Publication List Prepared:")
    print("=" * 80)
    print(f"   Total publications: {len(pub_df)}")
    print(f"   With PMC full text: {len(pub_df)}")
    print(f"   Ready for title screening")
    print(f"\n✅ Saved to {output_file}")


if __name__ == '__main__':
    main()
