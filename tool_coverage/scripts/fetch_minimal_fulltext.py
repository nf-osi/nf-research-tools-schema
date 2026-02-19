#!/usr/bin/env python3
"""
Fetch minimal full text (title + abstract + methods only) for tool mining.
Optimized Phase 1 caching strategy.

Usage:
    python fetch_minimal_fulltext.py --pmids-file publications.csv
    python fetch_minimal_fulltext.py --pmids 12345678 87654321
"""

import json
import os
import sys
import time
import argparse
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, List
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def batch_fetch_pubmed_metadata(pmids: List[str]) -> Dict[str, Optional[Dict]]:
    """
    Fetch complete publication metadata for multiple PMIDs in a single API call.
    PubMed E-utilities supports batch requests up to 200 IDs.

    Returns dict mapping PMID -> metadata
    """
    if not pmids:
        return {}

    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': ','.join(pmids),  # Comma-separated list
            'retmode': 'xml'
        }

        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            logger.warning(f"PubMed batch API error: {response.status_code}")
            return {pmid: None for pmid in pmids}

        root = ET.fromstring(response.content)

        # Parse each PubmedArticle
        results = {}
        for article in root.findall('.//PubmedArticle'):
            # Extract PMID
            pmid_elem = article.find('.//PMID')
            if pmid_elem is None or not pmid_elem.text:
                continue
            pmid = pmid_elem.text

            # Extract title
            title_elem = article.find('.//ArticleTitle')
            title = title_elem.text if title_elem is not None else ''

            # Extract abstract
            abstract_texts = article.findall('.//AbstractText')
            abstract_parts = []
            for text_elem in abstract_texts:
                label = text_elem.get('Label', '')
                text = text_elem.text if text_elem.text else ''
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            abstract = ' '.join(abstract_parts)

            # Extract authors
            authors = []
            for author in article.findall('.//Author'):
                lastname = author.find('LastName')
                forename = author.find('ForeName')
                if lastname is not None and lastname.text:
                    author_name = lastname.text
                    if forename is not None and forename.text:
                        author_name = f"{forename.text} {author_name}"
                    authors.append(author_name)
            authors_str = '; '.join(authors) if authors else ''

            # Extract journal
            journal_elem = article.find('.//Journal/Title')
            journal = journal_elem.text if journal_elem is not None else ''

            # Extract publication date
            pub_date = None
            pubdate_elem = article.find('.//PubDate')
            if pubdate_elem is not None:
                year = pubdate_elem.find('Year')
                month = pubdate_elem.find('Month')
                day = pubdate_elem.find('Day')

                if year is not None and year.text:
                    pub_date = year.text
                    if month is not None and month.text:
                        # Convert month name to number
                        month_map = {
                            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                        }
                        month_num = month_map.get(month.text, month.text)
                        pub_date = f"{year.text}-{month_num}"
                        if day is not None and day.text:
                            pub_date = f"{year.text}-{month_num}-{day.text.zfill(2)}"

            # Extract DOI
            doi = ''
            for article_id in article.findall('.//ArticleId'):
                if article_id.get('IdType') == 'doi':
                    doi = article_id.text if article_id.text else ''
                    break

            results[pmid] = {
                'title': title,
                'abstract': abstract,
                'authors': authors_str,
                'journal': journal,
                'publicationDate': pub_date if pub_date else '',
                'doi': doi
            }

        # Fill in None for any PMIDs that weren't found
        for pmid in pmids:
            if pmid not in results:
                results[pmid] = None

        return results

    except Exception as e:
        logger.error(f"Error in batch fetch for {len(pmids)} PMIDs: {e}")
        return {pmid: None for pmid in pmids}


def fetch_pubmed_metadata(pmid: str) -> Optional[Dict]:
    """
    Fetch complete publication metadata from PubMed E-utilities API.
    Includes: title, abstract, authors, journal, publicationDate, doi
    Fast, reliable, free.
    """
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': pmid,
            'retmode': 'xml'
        }

        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            logger.warning(f"PubMed API error for PMID:{pmid}: {response.status_code}")
            return None

        root = ET.fromstring(response.content)

        # Extract title
        title_elem = root.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None else ''

        # Extract abstract
        abstract_texts = root.findall('.//AbstractText')
        abstract_parts = []
        for text_elem in abstract_texts:
            label = text_elem.get('Label', '')
            text = text_elem.text if text_elem.text else ''
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = ' '.join(abstract_parts)

        # Extract authors (for FILTERED CSVs)
        authors = []
        for author in root.findall('.//Author'):
            lastname = author.find('LastName')
            forename = author.find('ForeName')
            if lastname is not None and lastname.text:
                author_name = lastname.text
                if forename is not None and forename.text:
                    author_name = f"{forename.text} {author_name}"
                authors.append(author_name)
        authors_str = '; '.join(authors) if authors else ''

        # Extract journal
        journal_elem = root.find('.//Journal/Title')
        journal = journal_elem.text if journal_elem is not None else ''

        # Extract publication date (year-month-day format)
        pub_date = None
        pubdate_elem = root.find('.//PubDate')
        if pubdate_elem is not None:
            year = pubdate_elem.find('Year')
            month = pubdate_elem.find('Month')
            day = pubdate_elem.find('Day')

            if year is not None and year.text:
                pub_date = year.text
                if month is not None and month.text:
                    # Convert month name to number
                    month_map = {
                        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                    }
                    month_num = month_map.get(month.text, month.text)
                    pub_date = f"{year.text}-{month_num}"
                    if day is not None and day.text:
                        pub_date = f"{year.text}-{month_num}-{day.text.zfill(2)}"

        # Extract DOI
        doi = ''
        for article_id in root.findall('.//ArticleId'):
            if article_id.get('IdType') == 'doi':
                doi = article_id.text if article_id.text else ''
                break

        return {
            'title': title,
            'abstract': abstract,
            'authors': authors_str,
            'journal': journal,
            'publicationDate': pub_date if pub_date else '',
            'doi': doi
        }

    except Exception as e:
        logger.error(f"Error fetching PubMed metadata for PMID:{pmid}: {e}")
        return None


def fetch_pmc_methods_section(pmid: str) -> Optional[str]:
    """
    Fetch ONLY the methods section from PMC using official OAI-PMH API.
    Returns None if PMC full text not available.

    Uses PMC OAI-PMH API as recommended by https://pmc.ncbi.nlm.nih.gov/tools/oai/
    """
    try:
        # Get PMC ID from PMID using elink
        eutils_base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        params = {
            'db': 'pmc',
            'id': pmid,
            'idtype': 'pmid',
            'email': 'nf-research@example.com',
            'tool': 'nf-research-tools-miner'
        }

        response = requests.get(f"{eutils_base}elink.fcgi", params=params, timeout=10)
        if response.status_code != 200:
            return None

        # Parse XML to get PMC ID
        root = ET.fromstring(response.content)

        # CRITICAL: Only get the article itself, not citing articles!
        # We need to find the LinkSet with LinkName = "pubmed_pmc"
        pmc_id = None
        for linkset in root.findall('.//LinkSet'):
            linkname_elem = linkset.find('.//LinkName')
            if linkname_elem is not None and linkname_elem.text == 'pubmed_pmc':
                # This is the original article in PMC (not citing articles)
                link_ids = linkset.findall('.//Link/Id')
                if link_ids:
                    pmc_id = link_ids[0].text
                    break

        if not pmc_id:
            # Article not available in PMC (no full text)
            logger.debug(f"PMID:{pmid} not available in PMC (no full text)")
            return None

        # Fetch full text using PMC OAI-PMH API
        time.sleep(0.34)  # Rate limit
        oai_url = (
            f"https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
            f"?verb=GetRecord"
            f"&identifier=oai:pubmedcentral.nih.gov:{pmc_id}"
            f"&metadataPrefix=pmc"  # Full text (vs pmc_fm for front matter only)
        )

        response = requests.get(oai_url, timeout=30)
        if response.status_code != 200:
            return None

        # Parse XML (namespace-aware)
        root = ET.fromstring(response.content)

        # Common section titles for methods
        methods_titles = [
            'methods', 'materials and methods', 'experimental procedures',
            'materials & methods', 'methodology', 'experimental methods',
            'methods and materials', 'materials', 'experimental design'
        ]

        # Find all <sec> elements (works with or without namespaces)
        methods_text = []
        for sec in root.iter():
            if not sec.tag.endswith('sec'):
                continue

            # Find title element within this section
            title_elem = None
            for child in sec:
                if child.tag.endswith('title'):
                    title_elem = child
                    break

            if title_elem is not None and title_elem.text:
                title = title_elem.text.lower().strip()

                # Check if this is a methods section
                if any(methods_title in title for methods_title in methods_titles):
                    # Extract all text from this section
                    text_parts = []
                    for elem in sec.iter():
                        if elem.text:
                            text_parts.append(elem.text)
                        if elem.tail:
                            text_parts.append(elem.tail)

                    methods_text.append(' '.join(text_parts))

        if methods_text:
            return ' '.join(methods_text).strip()

        return None

    except Exception as e:
        logger.debug(f"Could not fetch PMC methods for PMID:{pmid}: {e}")
        return None


def create_minimal_cache(pmid: str, output_dir: Path) -> Dict:
    """
    Create minimal cache entry with title + abstract + methods only.

    Returns cache data dict with status information.
    """
    pmid_clean = pmid.replace('PMID:', '').strip()

    logger.info(f"Fetching minimal cache for PMID:{pmid_clean}")

    # Fetch from PubMed (fast, reliable)
    metadata = fetch_pubmed_metadata(pmid_clean)
    if not metadata:
        logger.error(f"Failed to fetch PubMed metadata for PMID:{pmid_clean}")
        return {
            'pmid': f"PMID:{pmid_clean}",
            'error': 'PubMed fetch failed',
            'cache_level': 'failed'
        }

    # Try to fetch methods from PMC
    logger.info(f"  Attempting PMC methods fetch for PMID:{pmid_clean}")
    methods = fetch_pmc_methods_section(pmid_clean)

    has_fulltext = bool(methods)
    cache_level = 'minimal' if has_fulltext else 'abstract_only'

    cache_data = {
        'pmid': f"PMID:{pmid_clean}",
        'title': metadata['title'],
        'abstract': metadata['abstract'],
        'authors': metadata['authors'],
        'journal': metadata['journal'],
        'publicationDate': metadata['publicationDate'],
        'doi': metadata['doi'],
        'methods': methods if methods else '',
        'cache_level': cache_level,
        'has_fulltext': has_fulltext,
        'fetch_date': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    # Save to cache
    cache_file = output_dir / f"{pmid_clean}_text.json"
    with open(cache_file, 'w') as f:
        json.dump(cache_data, f, indent=2)

    author_count = len(metadata['authors'].split('; ')) if metadata['authors'] else 0
    logger.info(f"  ✓ Cached as '{cache_level}' ({len(metadata['abstract'])} chars abstract, "
                f"{len(methods) if methods else 0} chars methods, {author_count} authors)")

    return cache_data


def main():
    parser = argparse.ArgumentParser(
        description='Fetch minimal full text (title + abstract + methods) for tool mining'
    )
    parser.add_argument('--pmids-file',
                       help='CSV file with PMIDs (must have "pmid" column)')
    parser.add_argument('--pmids', nargs='+',
                       help='List of PMIDs to fetch')
    parser.add_argument('--output-dir', default='tool_reviews/publication_cache',
                       help='Output directory for cache files')
    parser.add_argument('--force', action='store_true',
                       help='Re-fetch even if cache file exists')
    parser.add_argument('--batch-size', type=int, default=10,
                       help='Number of PMIDs to fetch in each batch (default: 10, max: 200)')

    args = parser.parse_args()

    # Collect PMIDs
    pmids = []
    if args.pmids_file:
        import csv
        with open(args.pmids_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pmid = row.get('pmid', '').replace('PMID:', '').strip()
                if pmid:
                    pmids.append(pmid)
    elif args.pmids:
        pmids = [p.replace('PMID:', '').strip() for p in args.pmids]
    else:
        parser.error("Must provide either --pmids-file or --pmids")

    # Setup output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Fetching minimal cache for {len(pmids)} PMIDs...")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Batch size: {args.batch_size} PMIDs per batch")
    logger.info("")

    # Process PMIDs
    stats = {
        'total': len(pmids),
        'minimal': 0,
        'abstract_only': 0,
        'failed': 0,
        'skipped': 0
    }

    # Filter out already cached PMIDs
    pmids_to_fetch = []
    for pmid in pmids:
        pmid_clean = pmid.replace('PMID:', '').strip()
        cache_file = output_dir / f"{pmid_clean}_text.json"
        if cache_file.exists() and not args.force:
            logger.info(f"PMID:{pmid_clean} - Already cached (use --force to re-fetch)")
            stats['skipped'] += 1
        else:
            pmids_to_fetch.append(pmid_clean)

    if not pmids_to_fetch:
        logger.info("No PMIDs to fetch (all already cached)")
    else:
        logger.info(f"Processing {len(pmids_to_fetch)} PMIDs in batches of {args.batch_size}...")
        logger.info("")

        # Process in batches
        for batch_start in range(0, len(pmids_to_fetch), args.batch_size):
            batch_end = min(batch_start + args.batch_size, len(pmids_to_fetch))
            batch_pmids = pmids_to_fetch[batch_start:batch_end]

            logger.info(f"Batch {batch_start//args.batch_size + 1}/{(len(pmids_to_fetch)-1)//args.batch_size + 1}: Fetching metadata for {len(batch_pmids)} PMIDs...")

            # Batch fetch metadata from PubMed
            metadata_results = batch_fetch_pubmed_metadata(batch_pmids)

            # Process each PMID in batch
            for i, pmid_clean in enumerate(batch_pmids):
                global_idx = batch_start + i + 1
                logger.info(f"  [{global_idx}/{len(pmids_to_fetch)}] PMID:{pmid_clean}")

                metadata = metadata_results.get(pmid_clean)
                if not metadata:
                    logger.error(f"    Failed to fetch PubMed metadata")
                    cache_data = {
                        'pmid': f"PMID:{pmid_clean}",
                        'error': 'PubMed fetch failed',
                        'cache_level': 'failed'
                    }
                    stats['failed'] += 1
                else:
                    # Fetch methods from PMC (individual requests)
                    logger.info(f"    Attempting PMC methods fetch...")
                    methods = fetch_pmc_methods_section(pmid_clean)

                    has_fulltext = bool(methods)
                    cache_level = 'minimal' if has_fulltext else 'abstract_only'

                    cache_data = {
                        'pmid': f"PMID:{pmid_clean}",
                        'title': metadata['title'],
                        'abstract': metadata['abstract'],
                        'authors': metadata['authors'],
                        'journal': metadata['journal'],
                        'publicationDate': metadata['publicationDate'],
                        'doi': metadata['doi'],
                        'methods': methods if methods else '',
                        'cache_level': cache_level,
                        'has_fulltext': has_fulltext,
                        'fetch_date': time.strftime('%Y-%m-%d %H:%M:%S')
                    }

                    # Update stats
                    if cache_level in stats:
                        stats[cache_level] += 1

                    author_count = len(metadata['authors'].split('; ')) if metadata['authors'] else 0
                    logger.info(f"    ✓ Cached as '{cache_level}' ({len(metadata['abstract'])} chars abstract, "
                                f"{len(methods) if methods else 0} chars methods, {author_count} authors)")

                # Save to cache
                cache_file = output_dir / f"{pmid_clean}_text.json"
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)

            # Rate limiting between batches
            if batch_end < len(pmids_to_fetch):
                time.sleep(0.34)  # Be nice to NCBI

            logger.info("")

    # Print summary
    logger.info("="*80)
    logger.info("FETCH SUMMARY")
    logger.info("="*80)
    logger.info(f"Total PMIDs: {stats['total']}")
    logger.info(f"Minimal cache (abstract + methods): {stats['minimal']}")
    logger.info(f"Abstract only (no PMC full text): {stats['abstract_only']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Skipped (already cached): {stats['skipped']}")
    logger.info("")

    if stats['minimal'] + stats['abstract_only'] > 0:
        logger.info(f"✓ Successfully cached {stats['minimal'] + stats['abstract_only']} publications")
        logger.info(f"  - {stats['minimal']} with methods section ({stats['minimal']/(stats['minimal']+stats['abstract_only'])*100:.1f}%)")
        logger.info(f"  - {stats['abstract_only']} abstract only ({stats['abstract_only']/(stats['minimal']+stats['abstract_only'])*100:.1f}%)")


if __name__ == '__main__':
    main()
