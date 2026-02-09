#!/usr/bin/env python3
"""
Mine PubMed for neurofibromatosis-related research articles.

Focuses on research articles (not reviews) where full text is freely available.
Outputs publications for addition to NF Research Tools database (syn26486839).
"""

import os
import sys
import time
import argparse
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Set
import requests
from xml.etree import ElementTree as ET
import pandas as pd
from dateutil import parser as date_parser

try:
    import synapseclient
    SYNAPSE_AVAILABLE = True
except ImportError:
    SYNAPSE_AVAILABLE = False
    print("⚠️  synapseclient not available - duplicate checking will be skipped")

# PubMed E-utilities base URLs
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"
ESUMMARY_URL = f"{EUTILS_BASE}/esummary.fcgi"

# Email for PubMed API (required for large queries)
EMAIL = os.getenv('PUBMED_EMAIL', 'nf-osi@sagebionetworks.org')


def search_pubmed(query: str, max_results: int = 1000, retstart: int = 0) -> List[str]:
    """
    Search PubMed and return list of PMIDs.

    Args:
        query: PubMed search query
        max_results: Maximum number of results to return
        retstart: Starting index for pagination

    Returns:
        List of PMIDs
    """
    params = {
        'db': 'pubmed',
        'term': query,
        'retmax': max_results,
        'retstart': retstart,
        'retmode': 'json',
        'email': EMAIL,
        'tool': 'nf-osi-tools'
    }

    try:
        response = requests.get(ESEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        pmids = data.get('esearchresult', {}).get('idlist', [])
        count = int(data.get('esearchresult', {}).get('count', 0))

        print(f"   Found {count} total results, retrieved {len(pmids)} PMIDs (offset {retstart})")
        return pmids, count

    except Exception as e:
        print(f"   ❌ Error searching PubMed: {e}")
        return [], 0


def fetch_publication_details(pmids: List[str]) -> List[Dict]:
    """
    Fetch detailed metadata for a list of PMIDs.

    Args:
        pmids: List of PubMed IDs

    Returns:
        List of publication dictionaries
    """
    if not pmids:
        return []

    # Batch fetch (max 200 at a time)
    batch_size = 200
    all_pubs = []

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i+batch_size]

        params = {
            'db': 'pubmed',
            'id': ','.join(batch),
            'retmode': 'xml',
            'email': EMAIL,
            'tool': 'nf-osi-tools'
        }

        try:
            response = requests.get(EFETCH_URL, params=params, timeout=60)
            response.raise_for_status()

            root = ET.fromstring(response.content)

            for article in root.findall('.//PubmedArticle'):
                pub = extract_article_metadata(article)
                if pub:
                    all_pubs.append(pub)

            # Be nice to NCBI servers
            if i + batch_size < len(pmids):
                time.sleep(0.5)

        except Exception as e:
            print(f"   ⚠️  Error fetching batch {i}-{i+batch_size}: {e}")
            continue

    return all_pubs


def extract_article_metadata(article) -> Optional[Dict]:
    """
    Extract metadata from PubMed XML article element.

    Args:
        article: XML element for a PubmedArticle

    Returns:
        Dictionary with publication metadata
    """
    try:
        medline = article.find('.//MedlineCitation')
        if medline is None:
            return None

        # PMID
        pmid_elem = medline.find('.//PMID')
        pmid = f"PMID:{pmid_elem.text}" if pmid_elem is not None else None

        # Article details
        article_elem = medline.find('.//Article')
        if article_elem is None:
            return None

        # Title
        title_elem = article_elem.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None else ''

        # Abstract - extract all text elements and labels
        abstract_parts = []
        abstract_texts = article_elem.findall('.//AbstractText')
        for abstract_elem in abstract_texts:
            # Check for labeled sections (BACKGROUND:, METHODS:, etc.)
            label = abstract_elem.get('Label', '')
            text = ''.join(abstract_elem.itertext()).strip()
            if text:
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
        abstract = ' '.join(abstract_parts) if abstract_parts else ''

        # Authors - format: LastName Initials. (comma-separated)
        # Example: "Pong WW, Higer SB, Gianino SM, Emnett RJ, Gutmann DH."
        author_list = article_elem.findall('.//Author')
        authors = []
        for author in author_list:
            last_name = author.find('.//LastName')
            fore_name = author.find('.//ForeName')
            initials_elem = author.find('.//Initials')

            if last_name is not None:
                last = last_name.text or ''

                # Try to get initials from Initials field first
                if initials_elem is not None and initials_elem.text:
                    initials = initials_elem.text
                # Otherwise extract from ForeName
                elif fore_name is not None and fore_name.text:
                    # Extract initials from first name
                    name_parts = fore_name.text.split()
                    initials = ''.join([part[0].upper() for part in name_parts if part])
                else:
                    initials = ''

                if initials:
                    authors.append(f"{last} {initials}.")
                else:
                    authors.append(f"{last}.")

        authors_str = ', '.join(authors) if authors else ''

        # Journal
        journal_elem = article_elem.find('.//Journal')
        journal = ''
        if journal_elem is not None:
            title_elem = journal_elem.find('.//Title')
            journal = title_elem.text if title_elem is not None else ''

        # Publication date - get full date
        pub_date = medline.find('.//PubDate')
        year = ''
        month = ''
        day = ''
        full_date = ''
        if pub_date is not None:
            year_elem = pub_date.find('.//Year')
            year = year_elem.text if year_elem is not None else ''
            month_elem = pub_date.find('.//Month')
            month = month_elem.text if month_elem is not None else ''
            day_elem = pub_date.find('.//Day')
            day = day_elem.text if day_elem is not None else ''

            # Create full date string
            if year and month and day:
                full_date = f"{year}-{month}-{day}"
            elif year and month:
                full_date = f"{year}-{month}"
            elif year:
                full_date = year

        # DOI
        doi = ''
        article_ids = article.findall('.//ArticleId')
        for aid in article_ids:
            if aid.get('IdType') == 'doi':
                doi = aid.text
                break

        # Publication types (to filter out reviews)
        pub_types = []
        pub_type_list = medline.findall('.//PublicationType')
        for pt in pub_type_list:
            if pt.text:
                pub_types.append(pt.text)

        # Check if free full text is available
        pmc_id = None
        for aid in article_ids:
            if aid.get('IdType') == 'pmc':
                pmc_id = aid.text
                break

        has_free_fulltext = pmc_id is not None

        return {
            'pmid': pmid,
            'doi': doi,
            'title': title,
            'journal': journal,
            'year': year,
            'publicationDate': full_date,
            'abstract': abstract,
            'authors': authors_str,
            'publication_types': '|'.join(pub_types),
            'pmc_id': pmc_id,
            'has_free_fulltext': has_free_fulltext
        }

    except Exception as e:
        print(f"   ⚠️  Error parsing article: {e}")
        return None


def get_existing_publications() -> Set[str]:
    """
    Get list of existing PMIDs from Synapse NF Research Tools publication table.

    Returns:
        Set of PMIDs already in the database
    """
    if not SYNAPSE_AVAILABLE:
        print("   ⚠️  Synapse client not available, skipping duplicate check")
        return set()

    try:
        syn = synapseclient.Synapse()
        auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
        if auth_token:
            syn.login(authToken=auth_token, silent=True)
        else:
            # Try anonymous login for public data
            print("   ℹ️  No SYNAPSE_AUTH_TOKEN found, trying anonymous access")
            syn.login(silent=True)

        # Query publications table for existing PMIDs
        query = "SELECT pmid FROM syn26486839"
        results = syn.tableQuery(query)
        df = results.asDataFrame()

        # Normalize PMIDs to uppercase for comparison
        existing_pmids = set(df['pmid'].dropna().str.upper().tolist())
        print(f"   Found {len(existing_pmids)} existing publications in syn26486839")

        return existing_pmids

    except Exception as e:
        print(f"   ⚠️  Error checking existing publications: {e}")
        return set()


def filter_publications(pubs: List[Dict], existing_pmids: Set[str] = None) -> List[Dict]:
    """
    Filter publications to include only research articles with free full text.

    Args:
        pubs: List of publication dictionaries
        existing_pmids: Set of PMIDs already in database

    Returns:
        Filtered list of publications
    """
    if existing_pmids is None:
        existing_pmids = set()

    filtered = []
    skipped_duplicate = 0
    skipped_not_journal_article = 0

    for pub in pubs:
        # Skip duplicates
        if pub.get('pmid', '').upper() in existing_pmids:
            skipped_duplicate += 1
            continue

        # Only include publications with EXACTLY "Journal Article" type (no concatenated types)
        pub_types = pub.get('publication_types', '')
        if pub_types != 'Journal Article':
            skipped_not_journal_article += 1
            continue

        # Only include publications with free full text
        if not pub.get('has_free_fulltext', False):
            continue

        filtered.append(pub)

    if skipped_duplicate > 0:
        print(f"   Skipped {skipped_duplicate} duplicate publications")
    if skipped_not_journal_article > 0:
        print(f"   Skipped {skipped_not_journal_article} non-journal articles")

    return filtered


def main():
    parser = argparse.ArgumentParser(
        description='Mine PubMed for neurofibromatosis-related research articles'
    )
    parser.add_argument(
        '--max-results',
        type=int,
        default=1000,
        help='Maximum number of results to retrieve (default: 1000)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='tool_coverage/outputs/pubmed_nf_publications.csv',
        help='Output CSV file path'
    )
    parser.add_argument(
        '--years',
        type=str,
        help='Year range (e.g., 2020:2024) to limit search'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("PUBMED MINING: Neurofibromatosis Research Articles")
    print("=" * 80)

    # Build search query
    # Include neurofibromatosis terms, exclude reviews, require free full text
    query_parts = [
        '(neurofibromatosis[Title/Abstract] OR neurofibromatoses[Title/Abstract]',
        'OR "neurofibromatosis type 1"[Title/Abstract] OR "neurofibromatosis type 2"[Title/Abstract]',
        'OR NF1[Title/Abstract] OR NF2[Title/Abstract] OR schwannomatosis[Title/Abstract])',
        'AND (hasabstract)',
        'AND (free full text[Filter])',
        'NOT (review[Publication Type])',
        'NOT (systematic review[Publication Type])'
    ]

    if args.years:
        query_parts.append(f'AND ({args.years}[Publication Date])')

    query = ' '.join(query_parts)

    print(f"\n📋 Search Query:")
    print(f"   {query}")
    print(f"\n🔍 Searching PubMed...")

    # Search PubMed
    pmids, total_count = search_pubmed(query, max_results=args.max_results)

    if not pmids:
        print("\n❌ No publications found")
        sys.exit(1)

    print(f"\n📚 Fetching details for {len(pmids)} publications...")
    pubs = fetch_publication_details(pmids)

    print(f"   Retrieved metadata for {len(pubs)} publications")

    # Check for existing publications in Synapse
    print(f"\n🔍 Checking for duplicates in Synapse (syn26486839)...")
    existing_pmids = get_existing_publications()

    # Filter publications
    print(f"\n🔬 Filtering for research articles with free full text...")
    filtered_pubs = filter_publications(pubs, existing_pmids)

    print(f"   {len(filtered_pubs)} publications match criteria")

    if not filtered_pubs:
        print("\n❌ No publications passed filtering")
        sys.exit(1)

    # Save to CSV
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    df = pd.DataFrame(filtered_pubs)
    df = df[['pmid', 'doi', 'title', 'journal', 'year', 'pmc_id', 'publication_types']]
    df.to_csv(args.output, index=False)

    print(f"\n✅ Saved {len(df)} publications to: {args.output}")

    # Save Synapse-ready version matching syn26486839 schema
    synapse_output = args.output.replace('.csv', '_synapse.csv')
    df_synapse = pd.DataFrame(filtered_pubs)

    def generate_citation(row):
        """Generate citation string from publication metadata."""
        authors = str(row.get('authors', '')) if row.get('authors') else ''
        title = str(row.get('title', '')) if row.get('title') else ''
        journal = str(row.get('journal', '')) if row.get('journal') else ''
        year = str(row.get('year', '')) if row.get('year') else ''
        doi = str(row.get('doi', '')) if row.get('doi') else ''

        # Format: Authors. Title. Journal. Year. DOI
        parts = []
        if authors:
            parts.append(authors)
        if title:
            parts.append(title)
        if journal:
            parts.append(journal)
        if year:
            parts.append(f"({year})")
        if doi:
            parts.append(f"doi:{doi}")

        return '. '.join(parts) if parts else ''

    def parse_date_to_unix(date_str):
        """Convert publication date to Unix timestamp (milliseconds)."""
        if not date_str:
            return ''
        try:
            # Handle various date formats
            if '-' in date_str:
                # Try parsing full date
                dt = date_parser.parse(date_str)
            else:
                # Just a year
                dt = datetime(int(date_str), 1, 1)
            # Return Unix timestamp in milliseconds
            return int(dt.timestamp() * 1000)
        except:
            return ''

    # Generate citation, Unix timestamps, and unique publicationIds
    citations = []
    unix_timestamps = []
    publication_ids = []
    for _, row in df_synapse.iterrows():
        citations.append(generate_citation(row))
        unix_timestamps.append(parse_date_to_unix(row.get('publicationDate', '')))
        # Generate unique UUID for each publication
        publication_ids.append(str(uuid.uuid4()))

    # Map to Synapse table column names
    df_synapse_formatted = pd.DataFrame({
        'publicationId': publication_ids,
        'doi': df_synapse['doi'],
        'pmid': df_synapse['pmid'],
        'abstract': df_synapse['abstract'],
        'journal': df_synapse['journal'],
        'publicationDate': df_synapse['publicationDate'],
        'citation': citations,
        'publicationDateUnix': unix_timestamps,
        'authors': df_synapse['authors'],
        'publicationTitle': df_synapse['title']
    })

    # Reorder columns to match Synapse schema
    synapse_cols = ['publicationId', 'doi', 'pmid', 'abstract', 'journal',
                    'publicationDate', 'citation', 'publicationDateUnix',
                    'authors', 'publicationTitle']
    df_synapse_formatted = df_synapse_formatted[synapse_cols]
    df_synapse_formatted.to_csv(synapse_output, index=False)

    print(f"✅ Saved Synapse-ready version to: {synapse_output}")

    # Summary statistics
    print(f"\n📊 Summary:")
    print(f"   Total found: {total_count}")
    print(f"   Journal articles with free full text: {len(filtered_pubs)}")
    print(f"   Year range: {df['year'].min()} - {df['year'].max()}")
    print(f"   Journals: {df['journal'].nunique()} unique")

    print("\n" + "=" * 80)
    print("✅ PubMed mining complete!")
    print("=" * 80)


if __name__ == '__main__':
    main()
