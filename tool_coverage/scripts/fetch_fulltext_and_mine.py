#!/usr/bin/env python3
"""
Fetch full text from PubMed Central, extract Methods sections,
and mine for novel tools using trained patterns.

Note: AI validation should be run separately using run_publication_reviews.py
"""

import synapseclient
import pandas as pd
import re
import time
import requests
from difflib import SequenceMatcher
from xml.etree import ElementTree as ET
from typing import Dict, List, Set, Tuple
import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from extract_tool_metadata import extract_all_metadata

# PubMed Central API configuration
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EMAIL = "your.email@example.com"  # Required by NCBI
TOOL_NAME = "nf-research-tools-miner"
API_KEY = None  # Optional: set NCBI API key for higher rate limits

# PubMed query filters (from mine_pubmed_nf.py lines 382-397)
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

def fetch_pmc_fulltext(pmid: str, max_retries: int = 3) -> str:
    """
    Fetch full text XML from PubMed Central using PMID.

    Args:
        pmid: PubMed ID (with or without 'PMID:' prefix)
        max_retries: Number of retry attempts

    Returns:
        Full text as string, or empty string if not available
    """
    # Clean PMID
    clean_pmid = pmid.replace('PMID:', '').strip()
    if not clean_pmid:
        return ""

    # First, check if article is available in PMC
    params = {
        'db': 'pmc',
        'id': clean_pmid,
        'idtype': 'pmid',
        'email': EMAIL,
        'tool': TOOL_NAME
    }
    if API_KEY:
        params['api_key'] = API_KEY

    for attempt in range(max_retries):
        try:
            # Get PMC ID from PMID
            response = requests.get(f"{EUTILS_BASE}elink.fcgi", params=params, timeout=10)
            response.raise_for_status()

            # Parse XML to get PMC ID
            root = ET.fromstring(response.content)
            pmc_ids = root.findall(".//Link/Id")

            if not pmc_ids:
                return ""  # Not available in PMC

            pmc_id = pmc_ids[0].text

            # Fetch full text using PMC ID
            fetch_params = {
                'db': 'pmc',
                'id': pmc_id,
                'retmode': 'xml',
                'email': EMAIL,
                'tool': TOOL_NAME
            }
            if API_KEY:
                fetch_params['api_key'] = API_KEY

            time.sleep(0.34)  # Rate limit: 3 requests/second without API key
            response = requests.get(f"{EUTILS_BASE}efetch.fcgi", params=fetch_params, timeout=30)
            response.raise_for_status()

            return response.text

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed for PMID {clean_pmid}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            continue

    return ""


def check_pmc_availability(pmids: List[str], max_retries: int = 3) -> Set[str]:
    """
    Check which PMIDs have full text available in PubMed Central.

    Args:
        pmids: List of PMIDs to check (without 'PMID:' prefix)
        max_retries: Number of retry attempts

    Returns:
        Set of PMIDs (with 'PMID:' prefix) that have full text in PMC
    """
    if not pmids:
        return set()

    # Clean PMIDs (remove PMID: prefix if present)
    clean_pmids = [p.replace('PMID:', '').strip() for p in pmids if p]

    # PubMed allows checking up to 200 IDs per request
    batch_size = 200
    available_pmids = set()

    for i in range(0, len(clean_pmids), batch_size):
        batch_pmids = clean_pmids[i:i + batch_size]
        pmid_str = ','.join(batch_pmids)

        params = {
            'dbfrom': 'pubmed',
            'db': 'pmc',
            'id': pmid_str,
            'email': EMAIL,
            'tool': TOOL_NAME
        }
        if API_KEY:
            params['api_key'] = API_KEY

        for attempt in range(max_retries):
            try:
                time.sleep(0.34)  # Rate limit
                response = requests.get(f"{EUTILS_BASE}elink.fcgi", params=params, timeout=30)
                response.raise_for_status()

                # Parse XML to find PMIDs with PMC links
                root = ET.fromstring(response.content)

                # Find all LinkSets that have PMC links
                for linkset in root.findall(".//LinkSet"):
                    # Get the source PMID
                    source_id = linkset.find(".//Id")
                    if source_id is not None:
                        source_pmid = source_id.text

                        # Check if this PMID has a link to PMC
                        pmc_links = linkset.findall(".//Link/Id")
                        if pmc_links:
                            # Has full text in PMC
                            available_pmids.add(f"PMID:{source_pmid}")

                break  # Success

            except requests.exceptions.RequestException as e:
                print(f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed checking PMC availability: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
            except ET.ParseError as e:
                print(f"  ⚠️  Failed to parse PMC link XML: {e}")
                break

    return available_pmids


def load_previously_reviewed_pmids(cache_file: str = 'tool_coverage/outputs/previously_reviewed_pmids.csv') -> Set[str]:
    """
    Load set of previously reviewed PMIDs from cache file.

    Args:
        cache_file: Path to CSV file with previously reviewed PMIDs

    Returns:
        Set of previously reviewed PMIDs (with 'PMID:' prefix)
    """
    if not os.path.exists(cache_file):
        return set()

    try:
        df = pd.read_csv(cache_file)
        if 'pmid' in df.columns:
            pmids = set(df['pmid'].dropna().astype(str).unique())
            # Ensure PMID: prefix
            pmids = {f"PMID:{p.replace('PMID:', '')}" for p in pmids if p and p != 'nan'}
            return pmids
    except Exception as e:
        print(f"  ⚠️  Could not load previously reviewed PMIDs: {e}")
        return set()

    return set()


def save_reviewed_pmids(pmids: Set[str], cache_file: str = 'tool_coverage/outputs/previously_reviewed_pmids.csv'):
    """
    Save reviewed PMIDs to cache file (append mode).

    Args:
        pmids: Set of PMIDs that were reviewed (with 'PMID:' prefix)
        cache_file: Path to CSV file
    """
    if not pmids:
        return

    # Create outputs directory if needed
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    # Load existing PMIDs
    existing_pmids = load_previously_reviewed_pmids(cache_file)

    # Merge with new PMIDs
    all_pmids = existing_pmids.union(pmids)

    # Save to CSV
    df = pd.DataFrame({'pmid': sorted(list(all_pmids))})
    df.to_csv(cache_file, index=False)
    print(f"\n   📝 Saved {len(all_pmids)} reviewed PMIDs to cache ({len(pmids)} new)")


def query_pubmed(query: str, max_results: int = 10000, max_retries: int = 3) -> List[str]:
    """
    Query PubMed and return list of PMIDs matching the query.

    Args:
        query: PubMed query string
        max_results: Maximum number of results to return
        max_retries: Number of retry attempts

    Returns:
        List of PMIDs as strings
    """
    params = {
        'db': 'pubmed',
        'term': query,
        'retmax': max_results,
        'retmode': 'xml',
        'email': EMAIL,
        'tool': TOOL_NAME
    }
    if API_KEY:
        params['api_key'] = API_KEY

    for attempt in range(max_retries):
        try:
            time.sleep(0.34)  # Rate limit: 3 requests/second without API key
            response = requests.get(f"{EUTILS_BASE}esearch.fcgi", params=params, timeout=30)
            response.raise_for_status()

            # Parse XML to extract PMIDs
            root = ET.fromstring(response.content)
            pmids = [id_elem.text for id_elem in root.findall(".//Id")]

            return pmids

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed querying PubMed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            continue
        except ET.ParseError as e:
            print(f"  ⚠️  Failed to parse PubMed search XML: {e}")
            return []

    return []


def fetch_pubmed_metadata_batch(pmids: List[str], max_retries: int = 3) -> pd.DataFrame:
    """
    Fetch metadata for a batch of PMIDs from PubMed.

    Args:
        pmids: List of PMIDs to fetch
        max_retries: Number of retry attempts

    Returns:
        DataFrame with columns: pmid, doi, title, journal, year, abstract
    """
    if not pmids:
        return pd.DataFrame()

    # PubMed allows up to 200 IDs per request
    batch_size = 200
    all_records = []

    for i in range(0, len(pmids), batch_size):
        batch_pmids = pmids[i:i + batch_size]
        pmid_str = ','.join(batch_pmids)

        params = {
            'db': 'pubmed',
            'id': pmid_str,
            'retmode': 'xml',
            'email': EMAIL,
            'tool': TOOL_NAME
        }
        if API_KEY:
            params['api_key'] = API_KEY

        for attempt in range(max_retries):
            try:
                time.sleep(0.34)  # Rate limit
                response = requests.get(f"{EUTILS_BASE}efetch.fcgi", params=params, timeout=30)
                response.raise_for_status()

                # Parse XML
                root = ET.fromstring(response.content)

                # Extract article metadata
                for article in root.findall(".//PubmedArticle"):
                    record = {}

                    # PMID
                    pmid_elem = article.find(".//PMID")
                    record['pmid'] = f"PMID:{pmid_elem.text}" if pmid_elem is not None else ""

                    # DOI
                    doi_elem = article.find(".//ArticleId[@IdType='doi']")
                    record['doi'] = doi_elem.text if doi_elem is not None else ""

                    # Title
                    title_elem = article.find(".//ArticleTitle")
                    record['title'] = title_elem.text if title_elem is not None else ""

                    # Journal
                    journal_elem = article.find(".//Journal/Title")
                    record['journal'] = journal_elem.text if journal_elem is not None else ""

                    # Year
                    year_elem = article.find(".//PubDate/Year")
                    record['year'] = year_elem.text if year_elem is not None else ""

                    all_records.append(record)

                break  # Success

            except requests.exceptions.RequestException as e:
                print(f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed fetching batch: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
            except ET.ParseError as e:
                print(f"  ⚠️  Failed to parse batch XML: {e}")
                break

    return pd.DataFrame(all_records)


def fetch_pubmed_abstract(pmid: str, max_retries: int = 3) -> str:
    """
    Fetch abstract from PubMed using PMID.

    Args:
        pmid: PubMed ID (with or without 'PMID:' prefix)
        max_retries: Number of retry attempts

    Returns:
        Abstract text as string, or empty string if not available
    """
    # Clean PMID
    clean_pmid = pmid.replace('PMID:', '').strip()
    if not clean_pmid:
        return ""

    # Fetch abstract from PubMed
    params = {
        'db': 'pubmed',
        'id': clean_pmid,
        'retmode': 'xml',
        'email': EMAIL,
        'tool': TOOL_NAME
    }
    if API_KEY:
        params['api_key'] = API_KEY

    for attempt in range(max_retries):
        try:
            time.sleep(0.34)  # Rate limit: 3 requests/second without API key
            response = requests.get(f"{EUTILS_BASE}efetch.fcgi", params=params, timeout=10)
            response.raise_for_status()

            # Parse XML to extract abstract
            root = ET.fromstring(response.content)

            # Abstract can be in multiple AbstractText elements
            abstract_texts = root.findall(".//Abstract/AbstractText")

            if not abstract_texts:
                return ""  # No abstract available

            # Combine all abstract sections (some have structured abstracts)
            abstract_parts = []
            for abstract_elem in abstract_texts:
                # Check if this is a structured abstract with a label
                label = abstract_elem.get('Label', '')
                text = abstract_elem.text or ''

                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)

            return ' '.join(abstract_parts).strip()

        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Attempt {attempt + 1}/{max_retries} failed fetching abstract for PMID {clean_pmid}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            continue
        except ET.ParseError as e:
            print(f"  ⚠️  Failed to parse abstract XML for PMID {clean_pmid}: {e}")
            return ""

    return ""


def extract_methods_section(fulltext_xml: str) -> str:
    """
    Extract Methods/Materials and Methods section from PMC XML.

    Args:
        fulltext_xml: Full text XML string from PMC

    Returns:
        Methods section text, or empty string if not found
    """
    if not fulltext_xml:
        return ""

    try:
        root = ET.fromstring(fulltext_xml)

        # Common section titles for methods
        methods_titles = [
            'methods', 'materials and methods', 'experimental procedures',
            'materials & methods', 'methodology', 'experimental methods',
            'methods and materials', 'materials', 'experimental design'
        ]

        # Find all sections
        sections = root.findall(".//sec")
        methods_text = []

        for section in sections:
            title_elem = section.find(".//title")
            if title_elem is not None and title_elem.text:
                title = title_elem.text.lower().strip()

                # Check if this is a methods section
                if any(methods_title in title for methods_title in methods_titles):
                    # Extract all text from this section
                    text_parts = []
                    for elem in section.iter():
                        if elem.text:
                            text_parts.append(elem.text)
                        if elem.tail:
                            text_parts.append(elem.tail)

                    methods_text.append(' '.join(text_parts))

        return ' '.join(methods_text)

    except ET.ParseError:
        return ""


def extract_introduction_section(fulltext_xml: str) -> str:
    """
    Extract Introduction section from PMC XML.

    Args:
        fulltext_xml: Full text XML string from PMC

    Returns:
        Introduction section text, or empty string if not found
    """
    if not fulltext_xml:
        return ""

    try:
        root = ET.fromstring(fulltext_xml)

        # Common section titles for introduction
        intro_titles = [
            'introduction', 'background', 'intro'
        ]

        # Find all sections
        sections = root.findall(".//sec")
        intro_text = []

        for section in sections:
            title_elem = section.find(".//title")
            if title_elem is not None and title_elem.text:
                title = title_elem.text.lower().strip()

                # Check if this is an introduction section
                if any(intro_title in title for intro_title in intro_titles):
                    # Extract all text from this section
                    text_parts = []
                    for elem in section.iter():
                        if elem.text:
                            text_parts.append(elem.text)
                        if elem.tail:
                            text_parts.append(elem.tail)

                    intro_text.append(' '.join(text_parts))

        return ' '.join(intro_text)

    except ET.ParseError:
        return ""


def extract_results_section(fulltext_xml: str) -> str:
    """
    Extract Results section from PMC XML.

    Args:
        fulltext_xml: Full text XML string from PMC

    Returns:
        Results section text, or empty string if not found
    """
    if not fulltext_xml:
        return ""

    try:
        root = ET.fromstring(fulltext_xml)

        # Common section titles for results
        results_titles = [
            'results', 'result', 'findings', 'observations'
        ]

        # Find all sections
        sections = root.findall(".//sec")
        results_text = []

        for section in sections:
            title_elem = section.find(".//title")
            if title_elem is not None and title_elem.text:
                title = title_elem.text.lower().strip()

                # Check if this is a results section
                if any(results_title in title for results_title in results_titles):
                    # Extract all text from this section
                    text_parts = []
                    for elem in section.iter():
                        if elem.text:
                            text_parts.append(elem.text)
                        if elem.tail:
                            text_parts.append(elem.tail)

                    results_text.append(' '.join(text_parts))

        return ' '.join(results_text)

    except ET.ParseError:
        return ""


def extract_discussion_section(fulltext_xml: str) -> str:
    """
    Extract Discussion section from PMC XML.

    Args:
        fulltext_xml: Full text XML string from PMC

    Returns:
        Discussion section text, or empty string if not found
    """
    if not fulltext_xml:
        return ""

    try:
        root = ET.fromstring(fulltext_xml)

        # Common section titles for discussion
        discussion_titles = [
            'discussion', 'conclusion', 'conclusions', 'concluding remarks',
            'summary and discussion', 'discussion and conclusions'
        ]

        # Find all sections
        sections = root.findall(".//sec")
        discussion_text = []

        for section in sections:
            title_elem = section.find(".//title")
            if title_elem is not None and title_elem.text:
                title = title_elem.text.lower().strip()

                # Check if this is a discussion section
                if any(discussion_title in title for discussion_title in discussion_titles):
                    # Extract all text from this section
                    text_parts = []
                    for elem in section.iter():
                        if elem.text:
                            text_parts.append(elem.text)
                        if elem.tail:
                            text_parts.append(elem.tail)

                    discussion_text.append(' '.join(text_parts))

        return ' '.join(discussion_text)

    except ET.ParseError:
        return ""


def sanitize_pmid_for_filename(pmid: str) -> str:
    """
    Sanitize PMID for use in filenames by removing invalid characters.

    GitHub Actions artifacts don't allow: " : < > | * ? \r \n

    Args:
        pmid: Publication PMID (may include 'PMID:' prefix)

    Returns:
        Sanitized PMID (numeric only)
    """
    # Remove 'PMID:' prefix if present
    clean_pmid = pmid.replace('PMID:', '').strip()
    # Remove any other invalid characters (keep only alphanumeric and underscore)
    clean_pmid = ''.join(c for c in clean_pmid if c.isalnum() or c == '_')
    return clean_pmid

def cache_publication_text(pmid: str, abstract: str, methods: str, intro: str,
                          results: str = "", discussion: str = "",
                          cache_dir: str = 'tool_reviews/publication_cache'):
    """
    Cache fetched publication text to avoid duplicate API calls during validation.

    Args:
        pmid: Publication PMID
        abstract: Abstract text from PubMed
        methods: Methods section text from PMC
        intro: Introduction section text from PMC
        results: Results section text from PMC
        discussion: Discussion section text from PMC
        cache_dir: Directory to store cache files
    """
    # Create cache directory if it doesn't exist
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    # Prepare cache data
    cache_data = {
        'pmid': pmid,
        'abstract': abstract,
        'methods': methods,
        'introduction': intro,
        'results': results,
        'discussion': discussion,
        'fetched_at': datetime.now().isoformat(),
        'abstract_length': len(abstract) if abstract else 0,
        'methods_length': len(methods) if methods else 0,
        'introduction_length': len(intro) if intro else 0,
        'results_length': len(results) if results else 0,
        'discussion_length': len(discussion) if discussion else 0
    }

    # Write to cache file (sanitize PMID for filename)
    clean_pmid = sanitize_pmid_for_filename(pmid)
    cache_file = cache_path / f'{clean_pmid}_text.json'
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)


def load_existing_tools(syn) -> Dict[str, List[str]]:
    """Load all existing tools from database tables to use as patterns."""
    print("1. Loading existing tools from database...")
    tool_patterns = {}

    # Load Animal Models
    print("   Loading Animal Models...")
    am_query = syn.tableQuery("SELECT * FROM syn26486808")
    am_df = am_query.asDataFrame()
    print(f"   - {len(am_df)} animal models")

    # Load Antibodies
    print("   Loading Antibodies...")
    ab_query = syn.tableQuery("SELECT * FROM syn26486811")
    ab_df = ab_query.asDataFrame()
    print(f"   - {len(ab_df)} antibodies")

    # Load Cell Lines
    print("   Loading Cell Lines...")
    cl_query = syn.tableQuery("SELECT * FROM syn26486823")
    cl_df = cl_query.asDataFrame()
    print(f"   - {len(cl_df)} cell lines")

    # Load Genetic Reagents
    print("   Loading Genetic Reagents...")
    gr_query = syn.tableQuery("SELECT * FROM syn26486832")
    gr_df = gr_query.asDataFrame()
    print(f"   - {len(gr_df)} genetic reagents")

    # Extract actual tool names as patterns
    print("\n2. Building patterns from existing tools...")

    # Cell lines - NO NAME FIELD IN DATABASE
    # Cell lines table only has categories (organ, tissue, cellLineCategory), no unique names
    # Skipping cell line pattern learning
    tool_patterns['cell_lines'] = []
    print(f"   - Cell lines: No name field in database, skipping pattern learning")

    # Antibodies - use targetAntigen
    if 'targetAntigen' in ab_df.columns:
        antibody_targets = ab_df['targetAntigen'].dropna().unique()
        tool_patterns['antibodies'] = [str(target) for target in antibody_targets if str(target).strip()]
        print(f"   - Learned {len(tool_patterns['antibodies'])} antibody targets")

    # Animal models - use strainNomenclature and backgroundStrain
    animal_model_names = []
    if 'strainNomenclature' in am_df.columns:
        animal_model_names.extend(am_df['strainNomenclature'].dropna().unique())
    if 'backgroundStrain' in am_df.columns:
        animal_model_names.extend(am_df['backgroundStrain'].dropna().unique())
    tool_patterns['animal_models'] = [str(name) for name in set(animal_model_names) if str(name).strip()]
    print(f"   - Learned {len(tool_patterns['animal_models'])} animal model strains")

    # Genetic reagents - use insertName
    if 'insertName' in gr_df.columns:
        gr_names = gr_df['insertName'].dropna().unique()
        tool_patterns['genetic_reagents'] = [str(name) for name in gr_names if str(name).strip()]
        print(f"   - Learned {len(tool_patterns['genetic_reagents'])} genetic reagent insert names")

    return tool_patterns


def load_existing_tools_for_matching(syn) -> Dict[str, Dict[str, str]]:
    """
    Load existing tools from Resource table for matching against found tools.

    Returns:
        Dict mapping tool_type -> {resourceId: resourceName}
    """
    print("\n2b. Loading existing tools from Resource table for matching...")

    # Load Resource table (syn51730943 is the materialized view)
    resource_query = syn.tableQuery("SELECT resourceId, resourceName, resourceType FROM syn51730943")
    resource_df = resource_query.asDataFrame()

    # Map resource types to internal naming
    type_mapping = {
        'Animal Model': 'animal_models',
        'Antibody': 'antibodies',
        'Cell Line': 'cell_lines',
        'Genetic Reagent': 'genetic_reagents'
    }

    existing_tools = {t: {} for t in type_mapping.values()}

    for _, row in resource_df.iterrows():
        resource_type = type_mapping.get(row['resourceType'])
        if resource_type and pd.notna(row['resourceId']) and pd.notna(row['resourceName']):
            existing_tools[resource_type][str(row['resourceId'])] = str(row['resourceName'])

    # Print summary
    for tool_type, tools in existing_tools.items():
        print(f"   - {tool_type}: {len(tools)} existing tools")

    return existing_tools


def match_to_existing_tool(tool_name: str, tool_type: str,
                          existing_tools: Dict[str, Dict[str, str]],
                          threshold: float = 0.88) -> str:
    """
    Match a found tool name against existing tools in the database.

    Args:
        tool_name: Name of the found tool
        tool_type: Type category
        existing_tools: Dict from load_existing_tools_for_matching()
        threshold: Fuzzy match threshold

    Returns:
        resourceId of matching existing tool, or empty string if no match
    """
    if tool_type not in existing_tools:
        return ""

    # Get list of existing tool names for this type
    existing_names = list(existing_tools[tool_type].values())

    # Use existing fuzzy_match function
    matches = fuzzy_match(tool_name, existing_names, threshold=threshold)

    if matches:
        # Return resourceId of first match
        matched_name = matches[0]
        for resource_id, name in existing_tools[tool_type].items():
            if name == matched_name:
                return resource_id

    return ""


def extract_abstract_text(pub_row: pd.Series) -> str:
    """
    Extract abstract text from publication row.

    Note: Synapse publications table (syn16857542) does NOT contain abstracts.
    This function fetches abstracts from PubMed API using the PMID.

    Args:
        pub_row: DataFrame row from publications table (must have 'pmid' column)

    Returns:
        Abstract text from PubMed API, or empty string if not available
    """
    # Get PMID from row
    if 'pmid' not in pub_row or pd.isna(pub_row['pmid']):
        return ""

    pmid = str(pub_row['pmid']).strip()
    if not pmid:
        return ""

    # Fetch abstract from PubMed API
    abstract = fetch_pubmed_abstract(pmid)
    return abstract


def fuzzy_match(text: str, patterns: List[str], threshold: float = 0.88) -> List[str]:
    """
    Find fuzzy matches for patterns in text.

    Args:
        text: Text to search in
        patterns: List of patterns to search for
        threshold: Similarity threshold (0-1)

    Returns:
        List of matched patterns
    """
    text_lower = text.lower()
    matches = []

    for pattern in patterns:
        pattern_str = str(pattern)
        pattern_lower = pattern_str.lower()

        # Exact match (case insensitive)
        if re.search(re.escape(pattern_str), text, re.IGNORECASE):
            matches.append(pattern_str)
            continue

        # Fuzzy match for patterns >= 4 chars
        if len(pattern_lower) >= 4:
            # Use sliding window
            pattern_len = len(pattern_lower)
            for i in range(len(text_lower) - pattern_len + 1):
                window = text_lower[i:i + pattern_len]
                similarity = SequenceMatcher(None, pattern_lower, window).ratio()
                if similarity >= threshold:
                    matches.append(pattern_str)
                    break

    return list(set(matches))


def extract_cell_line_names(methods_text: str) -> List[str]:
    """
    Extract potential cell line names from methods text using pattern matching.

    Patterns:
    - Capitalized names with hyphens/underscores (e.g., "dNF1-KO", "ipn02.3")
    - Cell line codes (e.g., "HEK293", "MCF7")
    - Near context words: "cell line", "cells", "cultured"
    """
    cell_lines = []

    # Pattern 1: Common cell line naming patterns
    # Format: Letters/Numbers with optional hyphens/underscores/dots
    # Must be 3+ chars and contain both letters and numbers
    cell_line_pattern = r'\b([A-Z][A-Za-z0-9]*[-_\.][A-Z0-9][-A-Za-z0-9_\.]{1,20})\b'

    # Find all matches
    for match in re.finditer(cell_line_pattern, methods_text):
        candidate = match.group(1)

        # Get surrounding context (200 chars)
        start = max(0, match.start() - 200)
        end = min(len(methods_text), match.end() + 200)
        context = methods_text[start:end].lower()

        # Must be near cell line related terms
        cell_keywords = ['cell line', 'cells', 'cell culture', 'cultured', 'derived', 'generated']
        if any(keyword in context for keyword in cell_keywords):
            cell_lines.append(candidate)

    return list(set(cell_lines))


def is_development_context(tool_name: str, tool_type: str, methods_text: str, window_size: int = 300) -> bool:
    """
    Detect if a tool was developed/generated in this publication or just used.

    Development keywords: "generated", "created", "derived", "developed", "established",
                         "engineered", "constructed", "novel", "new"
    Usage keywords: "obtained from", "purchased", "acquired", "provided by"

    Returns True if development context detected, False if just usage.
    """
    # Find all mentions of the tool
    tool_lower = tool_name.lower()
    text_lower = methods_text.lower()

    development_keywords = [
        'generat', 'creat', 'deriv', 'develop', 'establish',
        'engineer', 'construct', 'novel', 'new ', 'design',
        'produc', 'synthes', 'clone', 'isolat', 'immortaliz'
    ]

    usage_keywords = [
        'obtained from', 'purchased from', 'acquired from',
        'provided by', 'bought from', 'commercial',
        'charles river', 'jax', 'jackson lab', 'taconic',
        'atcc', 'sigma', 'millipore', 'thermo fisher',
        'invitrogen', 'cell signaling', 'abcam', 'santa cruz'
    ]

    # Find positions of tool mentions
    positions = []
    idx = 0
    while idx < len(text_lower):
        idx = text_lower.find(tool_lower, idx)
        if idx == -1:
            break
        positions.append(idx)
        idx += 1

    if not positions:
        return False

    # Check context around each mention
    dev_score = 0
    usage_score = 0

    for pos in positions:
        start = max(0, pos - window_size)
        end = min(len(text_lower), pos + len(tool_lower) + window_size)
        context = text_lower[start:end]

        # Count development keywords
        for keyword in development_keywords:
            if keyword in context:
                dev_score += 1

        # Count usage keywords (weighted higher - more specific)
        for keyword in usage_keywords:
            if keyword in context:
                usage_score += 2

    # Development if development keywords present and no strong usage indicators
    return dev_score > 0 and usage_score == 0


def is_generic_commercial_tool(tool_name: str, tool_type: str, methods_text: str) -> bool:
    """
    Filter out generic commercial tools that aren't novel NF-specific resources.

    Examples to filter:
    - Generic mouse strains: nude, C57BL/6, BALB/c (unless modified for NF)
    - Commercial antibodies without NF context
    - Standard reagents
    - NF1/NF2 gene names (unless explicitly mentioned as tools like "NF1 antibody")
    """
    tool_lower = tool_name.lower()
    text_lower = methods_text.lower()

    # Filter NF1/NF2 unless found with tool-specific keywords
    if tool_lower in ['nf1', 'nf2', 'nf-1', 'nf-2']:
        # Check if mentioned with tool-specific keywords
        tool_keywords = [
            'antibody', 'antibodies', 'plasmid', 'construct', 'vector',
            'cell line', 'cells', 'clone', 'reagent', 'primer',
            'shrna', 'sirna', 'crispr', 'strain'
        ]

        # Find all mentions of the tool
        positions = []
        idx = 0
        while idx < len(text_lower):
            idx = text_lower.find(tool_lower, idx)
            if idx == -1:
                break
            positions.append(idx)
            idx += 1

        # Check if ANY mention has tool keywords nearby
        has_tool_context = False
        for pos in positions:
            start = max(0, pos - 50)
            end = min(len(text_lower), pos + len(tool_lower) + 50)
            context = text_lower[start:end]

            if any(kw in context for kw in tool_keywords):
                has_tool_context = True
                break

        # Filter if no tool context found
        if not has_tool_context:
            return True

    # Generic animal model strains (filter unless NF-modified)
    if tool_type == 'animal_models':
        generic_strains = [
            'nude', 'nude mice', 'athymic nude',
            'c57bl/6', 'balb/c', 'cd-1', 'swiss webster',
            'scid', 'nod scid', 'nsg'
        ]

        # Check if it's a generic strain
        is_generic = any(generic in tool_lower for generic in generic_strains)

        if is_generic:
            # ONLY allow if there's NF-specific genetic modification IN THE STRAIN NAME ITSELF
            # Look for patterns like: Nf1tm1, Nf1-/-, Nf2-/-, etc.
            nf_genetic_modifications = [
                'nf1tm', 'nf2tm', 'nf1-/-', 'nf2-/-',
                'nf1+/-', 'nf2+/-', 'nf1flox', 'nf2flox',
                'nf1 knockout', 'nf2 knockout'
            ]
            has_nf_modification = any(mod in tool_lower for mod in nf_genetic_modifications)

            # Filter if generic and no NF-specific genetic modification in the name
            if not has_nf_modification:
                return True

    # Check for commercial vendor mentions
    commercial_indicators = [
        'charles river', 'jax', 'jackson lab', 'taconic',
        'purchased from', 'obtained from', 'acquired from',
        'provided by', 'bought from', 'commercially available'
    ]

    # Find tool mentions and check nearby text
    idx = text_lower.find(tool_lower)
    if idx != -1:
        context = text_lower[max(0, idx-200):min(len(text_lower), idx+200)]
        if any(indicator in context for indicator in commercial_indicators):
            return True

    return False


def mine_abstract(abstract_text: str, tool_patterns: Dict[str, List[str]]) -> Tuple[Dict[str, Set[str]], Dict[str, Dict]]:
    """
    Mine abstract for tool mentions using trained patterns.

    Similar to mine_methods_section() but:
    - No cell line extraction (abstracts too short for patterns)
    - Same fuzzy matching and context detection
    - Shorter context window (100 chars vs 300 chars)

    Args:
        abstract_text: Abstract text
        tool_patterns: Dictionary of tool patterns by type

    Returns:
        Tuple of (found tools dict, metadata dict)
    """
    found_tools = {
        'cell_lines': set(),
        'antibodies': set(),
        'animal_models': set(),
        'genetic_reagents': set()
    }

    tool_metadata = {}

    if not abstract_text or len(abstract_text) < 50:
        return found_tools, tool_metadata

    # Search for tool types using patterns (skip cell lines - abstracts too short)
    for tool_type, patterns in tool_patterns.items():
        if not patterns or tool_type == 'cell_lines':  # Skip cell_lines in abstracts
            continue

        matches = fuzzy_match(abstract_text, patterns, threshold=0.88)

        for tool_name in matches:
            # Filter generic/commercial tools
            if is_generic_commercial_tool(tool_name, tool_type, abstract_text):
                continue  # Skip this tool

            # Check development context (use shorter window for abstracts)
            is_dev = is_development_context(tool_name, tool_type, abstract_text, window_size=100)

            # Include tool (either development or usage)
            found_tools[tool_type].add(tool_name)

            # Extract metadata (abstracts have less context)
            metadata_key = f"{tool_type}:{tool_name}"
            metadata = extract_all_metadata(tool_name, tool_type, abstract_text)
            metadata['is_development'] = is_dev
            metadata['is_generic'] = False  # Already filtered generics
            tool_metadata[metadata_key] = metadata

    return found_tools, tool_metadata


def mine_introduction_section(intro_text: str, tool_patterns: Dict[str, List[str]]) -> Tuple[Dict[str, Set[str]], Dict[str, Dict]]:
    """
    Mine Introduction section for tool mentions with context keywords.

    Introduction sections often describe tools used/developed with phrases like:
    - "using [tool]"
    - "we developed [tool]"
    - "characterized [tool]"
    - "generated [tool]"

    Args:
        intro_text: Introduction section text
        tool_patterns: Dictionary of tool patterns by type

    Returns:
        Tuple of (found tools dict, metadata dict)
    """
    found_tools = {
        'cell_lines': set(),
        'antibodies': set(),
        'animal_models': set(),
        'genetic_reagents': set()
    }

    tool_metadata = {}

    if not intro_text or len(intro_text) < 50:
        return found_tools, tool_metadata

    # Context keywords for Introduction sections
    context_keywords = [
        'using', 'used', 'utilized', 'employed',
        'generated', 'developed', 'created', 'established',
        'characterized', 'analyzed', 'studied', 'investigated'
    ]

    # Search for tools near context keywords
    for tool_type, patterns in tool_patterns.items():
        if not patterns or tool_type == 'cell_lines':  # Skip cell lines
            continue

        matches = fuzzy_match(intro_text, patterns, threshold=0.88)

        for tool_name in matches:
            # Check if tool appears near context keywords
            tool_lower = tool_name.lower()
            text_lower = intro_text.lower()

            positions = []
            idx = 0
            while idx < len(text_lower):
                idx = text_lower.find(tool_lower, idx)
                if idx == -1:
                    break
                positions.append(idx)
                idx += 1

            # Check context around each mention
            has_context = False
            for pos in positions:
                start = max(0, pos - 150)
                end = min(len(text_lower), pos + len(tool_lower) + 150)
                context = text_lower[start:end]

                if any(kw in context for kw in context_keywords):
                    has_context = True
                    break

            if not has_context:
                continue  # Skip if no context keywords nearby

            # Filter generic/commercial tools
            if is_generic_commercial_tool(tool_name, tool_type, intro_text):
                continue

            # Check development context
            is_dev = is_development_context(tool_name, tool_type, intro_text, window_size=200)

            # Include tool
            found_tools[tool_type].add(tool_name)

            # Extract metadata
            metadata_key = f"{tool_type}:{tool_name}"
            metadata = extract_all_metadata(tool_name, tool_type, intro_text)
            metadata['is_development'] = is_dev
            metadata['is_generic'] = False
            tool_metadata[metadata_key] = metadata

    return found_tools, tool_metadata


def mine_methods_section(methods_text: str, tool_patterns: Dict[str, List[str]]) -> Tuple[Dict[str, Set[str]], Dict[str, Dict]]:
    """
    Mine Methods section for tool mentions using trained patterns and extract metadata.

    Now includes:
    - Cell line name extraction (pattern-based)
    - Development vs usage detection
    - Generic/commercial tool filtering

    Args:
        methods_text: Methods section text
        tool_patterns: Dictionary of tool patterns by type

    Returns:
        Tuple of (found tools dict, metadata dict)
    """
    found_tools = {
        'cell_lines': set(),
        'antibodies': set(),
        'animal_models': set(),
        'genetic_reagents': set()
    }

    tool_metadata = {}

    if not methods_text or len(methods_text) < 50:
        return found_tools, tool_metadata

    # 1. Extract cell lines using pattern matching (no pre-existing patterns)
    cell_line_names = extract_cell_line_names(methods_text)
    for cell_line_name in cell_line_names:
        # Check if it's a development (not just usage)
        is_dev = is_development_context(cell_line_name, 'cell_lines', methods_text)

        # Check if it's generic/commercial
        is_generic = is_generic_commercial_tool(cell_line_name, 'cell_lines', methods_text)

        # Only include if development context and not generic
        if is_dev and not is_generic:
            found_tools['cell_lines'].add(cell_line_name)
            metadata_key = f"cell_lines:{cell_line_name}"
            metadata = extract_all_metadata(cell_line_name, 'cell_lines', methods_text)
            metadata['is_development'] = True
            metadata['is_generic'] = False
            tool_metadata[metadata_key] = metadata

    # 2. Search for other tool types using patterns
    for tool_type, patterns in tool_patterns.items():
        if not patterns or tool_type == 'cell_lines':  # Skip cell_lines (handled above)
            continue

        matches = fuzzy_match(methods_text, patterns, threshold=0.88)

        for tool_name in matches:
            # Filter generic/commercial tools
            if is_generic_commercial_tool(tool_name, tool_type, methods_text):
                continue  # Skip this tool

            # Check development context
            is_dev = is_development_context(tool_name, tool_type, methods_text)

            # Include tool (either development or usage)
            found_tools[tool_type].add(tool_name)

            # Extract metadata
            metadata_key = f"{tool_type}:{tool_name}"
            metadata = extract_all_metadata(tool_name, tool_type, methods_text)
            metadata['is_development'] = is_dev
            metadata['is_generic'] = False  # Already filtered generics
            tool_metadata[metadata_key] = metadata

    return found_tools, tool_metadata


def merge_mining_results(abstract_results: Tuple, methods_results: Tuple,
                        intro_results: Tuple) -> Tuple[Dict[str, Set[str]], Dict[str, Dict], Dict[str, Set[str]]]:
    """
    Merge mining results from abstract, methods, and introduction sections.

    Handles deduplication and tracks which source(s) found each tool.

    Args:
        abstract_results: Tuple of (found_tools, tool_metadata) from abstract
        methods_results: Tuple of (found_tools, tool_metadata) from methods
        intro_results: Tuple of (found_tools, tool_metadata) from introduction

    Returns:
        Tuple of (merged_found_tools, merged_metadata, tool_sources)
    """
    merged_tools = {
        'cell_lines': set(),
        'antibodies': set(),
        'animal_models': set(),
        'genetic_reagents': set()
    }

    merged_metadata = {}
    tool_sources = {}  # tool_key -> set of sources

    # Merge from each source
    for source_name, (found_tools, metadata) in [
        ('abstract', abstract_results),
        ('methods', methods_results),
        ('introduction', intro_results)
    ]:
        for tool_type, tools in found_tools.items():
            for tool_name in tools:
                # Add tool to merged set
                merged_tools[tool_type].add(tool_name)

                # Track source
                tool_key = f"{tool_type}:{tool_name}"
                if tool_key not in tool_sources:
                    tool_sources[tool_key] = set()
                tool_sources[tool_key].add(source_name)

                # Merge metadata (prefer Methods > Introduction > Abstract)
                if tool_key in metadata:
                    if tool_key not in merged_metadata:
                        merged_metadata[tool_key] = metadata[tool_key].copy()
                    else:
                        # Merge, preferring more complete data
                        # Methods > Introduction > Abstract priority
                        if source_name == 'methods':
                            # Methods has priority - overwrite with non-empty values
                            for key, value in metadata[tool_key].items():
                                if value:
                                    merged_metadata[tool_key][key] = value
                        else:
                            # Only fill in missing fields from abstract/intro
                            for key, value in metadata[tool_key].items():
                                if value and not merged_metadata[tool_key].get(key):
                                    merged_metadata[tool_key][key] = value

    return merged_tools, merged_metadata, tool_sources


def mine_publication(pub_row: pd.Series, tool_patterns: Dict[str, List[str]],
                    existing_tools: Dict[str, Dict[str, str]]) -> Dict:
    """
    Mine a single publication from abstract + full text (if available).

    Pipeline:
    1. Mine abstract (always available)
    2. Fetch full text if available
    3. Mine Methods section if found
    4. Mine Introduction section if found
    5. Merge results with deduplication
    6. Match against existing tools
    7. Categorize as existing-link or new-tool

    Args:
        pub_row: Publication DataFrame row
        tool_patterns: Tool patterns for fuzzy matching
        existing_tools: Existing tools from Resource table

    Returns:
        Dict with mining results and categorization
    """
    pmid = pub_row.get('pmid', '')
    result = {
        'pmid': pmid,
        'doi': pub_row.get('doi', ''),
        'title': pub_row.get('title', ''),
        'journal': pub_row.get('journal', ''),
        'year': pub_row.get('year', ''),
        'fundingAgency': pub_row.get('fundingAgency', ''),
        'abstract_available': False,
        'fulltext_available': False,
        'methods_found': False,
        'introduction_found': False,
        'abstract_length': 0,
        'methods_length': 0,
        'intro_length': 0,
        'existing_tools': {},  # tool_type -> {tool_name: resourceId}
        'novel_tools': {},  # tool_type -> set(tool_names)
        'tool_metadata': {},
        'tool_sources': {},
        'is_gff': str(pub_row.get('fundingAgency', '')).find('GFF') != -1
    }

    # 1. Mine abstract (always)
    abstract_text = extract_abstract_text(pub_row)
    if abstract_text:
        result['abstract_available'] = True
        result['abstract_length'] = len(abstract_text)
        abstract_results = mine_abstract(abstract_text, tool_patterns)
    else:
        abstract_results = ({t: set() for t in tool_patterns.keys()}, {})

    # 2. Fetch full text
    fulltext = fetch_pmc_fulltext(pmid)

    # 3. Mine Methods section
    methods_text = extract_methods_section(fulltext) if fulltext else ""
    if methods_text and len(methods_text) >= 50:
        result['methods_found'] = True
        result['methods_length'] = len(methods_text)
        methods_results = mine_methods_section(methods_text, tool_patterns)
    else:
        methods_results = ({t: set() for t in tool_patterns.keys()}, {})

    # 4. Mine Introduction section
    intro_text = extract_introduction_section(fulltext) if fulltext else ""
    if intro_text and len(intro_text) >= 50:
        result['introduction_found'] = True
        result['intro_length'] = len(intro_text)
        intro_results = mine_introduction_section(intro_text, tool_patterns)
    else:
        intro_results = ({t: set() for t in tool_patterns.keys()}, {})

    # 5. Extract Results section (for observation mining during AI validation)
    results_text = extract_results_section(fulltext) if fulltext else ""
    if results_text and len(results_text) >= 50:
        result['results_found'] = True
        result['results_length'] = len(results_text)

    # 6. Extract Discussion section (for observation mining during AI validation)
    discussion_text = extract_discussion_section(fulltext) if fulltext else ""
    if discussion_text and len(discussion_text) >= 50:
        result['discussion_found'] = True
        result['discussion_length'] = len(discussion_text)

    # Mark fulltext as available only if we got meaningful content
    if methods_text or intro_text or results_text or discussion_text:
        result['fulltext_available'] = True

    # 7. Merge results
    merged_tools, merged_metadata, tool_sources = merge_mining_results(
        abstract_results, methods_results, intro_results
    )

    result['tool_sources'] = tool_sources
    result['tool_metadata'] = merged_metadata

    # Store fetched text for caching (to avoid duplicate API calls during validation)
    result['abstract_text'] = abstract_text
    result['methods_text'] = methods_text
    result['intro_text'] = intro_text
    result['results_text'] = results_text
    result['discussion_text'] = discussion_text

    # 6. Match against existing tools
    for tool_type, tools in merged_tools.items():
        result['existing_tools'][tool_type] = {}
        result['novel_tools'][tool_type] = set()

        for tool_name in tools:
            resource_id = match_to_existing_tool(tool_name, tool_type, existing_tools)
            if resource_id:
                result['existing_tools'][tool_type][tool_name] = resource_id
            else:
                result['novel_tools'][tool_type].add(tool_name)

    return result


def should_exclude_publication(title, journal):
    """
    Check if a publication should be excluded based on title and journal filters.
    Applies the same exclusion criteria from mine_pubmed_nf.py lines 382-397.

    Returns True if the publication should be excluded, False otherwise.
    """
    if pd.isna(title):
        return True  # Exclude if no title

    title_lower = str(title).lower()

    # Excluded title terms (case-insensitive)
    excluded_terms = [
        'case', 'review', 'pain', 'tomography', 'outcomes',
        'individual', 'individuals', 'patient', 'patients', 'population',
        'clinic', 'clinical', 'clinics', 'cohort', 'cohorts',
        'child', 'children', 'childhood', 'current', 'mri', 'mris',
        'guideline', 'guidelines', 'perspective', 'perspectives',
        'retrospective', 'after',
        'quality of life', 'pediatric', 'pediatrics', 'adult', 'adults', 'resection',
        'parent', 'parents', 'parental', 'prognostic', 'surg', 'surgery',
        'surgical', 'surgeries', 'facial',
        'prevalence', 'experience', 'famil', 'family', 'families', 'presentation',
        'trial', 'novel mutation', 'presenting', 'overview',
        'pregnancy', 'lady', 'female', 'woman', 'women',
        'hearing loss', 'pictorial essay'
    ]

    # Check each excluded term
    for term in excluded_terms:
        if term in title_lower:
            return True

    # Excluded journals
    if pd.notna(journal):
        journal_lower = str(journal).lower()
        excluded_journals = [
            'clinical case reports',
            'ja clinical reports'
        ]

        for excluded_journal in excluded_journals:
            if excluded_journal in journal_lower:
                return True

    return False


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Mine publications for research tools using filtered NF research publications',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Mine publications from NF Portal + PubMed query
  python fetch_fulltext_and_mine.py

  # Mine with custom limits
  python fetch_fulltext_and_mine.py --max-publications 100

  # Mine only from NF Portal (skip PubMed query)
  python fetch_fulltext_and_mine.py --skip-pubmed-query

Workflow:
  1. Loads publications from NF Portal (Synapse)
  2. Applies research-focused filters (excludes clinical case reports, reviews, etc.)
  3. Queries PubMed for additional NF research publications (unless --skip-pubmed-query)
  4. Merges and deduplicates all publications
  5. Mines full text for research tools (cell lines, antibodies, animal models, genetic reagents)

Note: Run run_publication_reviews.py separately for AI validation
        """
    )
    parser.add_argument(
        '--max-publications',
        type=int,
        default=None,
        help='Limit number of publications to mine (for testing)'
    )
    parser.add_argument(
        '--skip-pubmed-query',
        action='store_true',
        default=False,
        help='Skip querying PubMed for additional publications (only use NF Portal)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("FULL TEXT MINING FOR NOVEL TOOLS")
    print("=" * 80)
    print("\nThis script will:")
    print("1. Load publications from NF Portal (Synapse)")
    print("2. Apply research-focused filters (exclude clinical case reports, etc.)")
    if not args.skip_pubmed_query:
        print("3. Query PubMed for additional NF research publications")
        print("4. Merge and deduplicate publications")
    print(f"{4 if not args.skip_pubmed_query else 3}. Mine full text for research tools (cell lines, antibodies, animal models, genetic reagents)")
    if args.max_publications:
        print(f"\n⚙️  Configuration:")
        print(f"   - Max Publications: {args.max_publications}")
    if args.skip_pubmed_query:
        print(f"   - PubMed Query: Disabled")
    print()

    # Login to Synapse
    syn = synapseclient.Synapse()
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token)
    else:
        syn.login()  # Interactive login if no token

    # Load existing tools
    tool_patterns = load_existing_tools(syn)

    # Load existing tools for matching
    existing_tools = load_existing_tools_for_matching(syn)

    # Load previously reviewed PMIDs
    print("\n3. Loading and filtering publications...")
    print("   Step 3a: Loading previously reviewed PMIDs...")
    previously_reviewed = load_previously_reviewed_pmids()
    print(f"   - {len(previously_reviewed)} previously reviewed publications")

    # Load publications from Synapse
    print("\n   Step 3b: Loading NF Portal publications from Synapse...")
    pub_query = syn.tableQuery("SELECT * FROM syn16857542")
    pub_df = pub_query.asDataFrame()
    print(f"   - {len(pub_df)} total NF Portal publications")

    # Standardize PMID format early
    if 'pmid' in pub_df.columns:
        pub_df['pmid'] = pub_df['pmid'].astype(str)
        pub_df.loc[~pub_df['pmid'].str.startswith('PMID:'), 'pmid'] = 'PMID:' + pub_df['pmid']

    # Apply query filters to Synapse publications
    print("   Step 3c: Applying query filters to NF Portal publications...")
    if 'publicationTitle' in pub_df.columns:
        title_col = 'publicationTitle'
    elif 'title' in pub_df.columns:
        title_col = 'title'
    else:
        print("   ⚠️  No title column found in publications table")
        title_col = None

    initial_count = len(pub_df)
    if title_col:
        pub_df['exclude'] = pub_df.apply(
            lambda row: should_exclude_publication(
                row[title_col],
                row.get('journal', '')
            ),
            axis=1
        )
        excluded_count = pub_df['exclude'].sum()
        pub_df = pub_df[~pub_df['exclude']].drop(columns=['exclude'])
        print(f"   - Excluded {excluded_count} publications based on title/journal filters")
        print(f"   - {len(pub_df)} publications remain after filtering")

    # Check PMC full text availability for NF Portal publications
    print("\n   Step 3d: Checking PMC full text availability for NF Portal publications...")
    nf_portal_pmids = pub_df['pmid'].dropna().astype(str).unique().tolist()
    print(f"   - Checking {len(nf_portal_pmids)} PMIDs for full text availability...")

    # Check in batches to show progress
    pmc_available = set()
    batch_size = 500
    for i in range(0, len(nf_portal_pmids), batch_size):
        batch = nf_portal_pmids[i:i + batch_size]
        batch_available = check_pmc_availability(batch)
        pmc_available.update(batch_available)
        print(f"     Checked {min(i + batch_size, len(nf_portal_pmids))}/{len(nf_portal_pmids)} PMIDs... ({len(pmc_available)} with full text so far)")

    print(f"   - {len(pmc_available)} publications have full text in PMC")

    # Filter to only publications with PMC full text
    before_pmc_filter = len(pub_df)
    pub_df = pub_df[pub_df['pmid'].isin(pmc_available)].copy()
    print(f"   - Excluded {before_pmc_filter - len(pub_df)} publications without PMC full text")
    print(f"   - {len(pub_df)} NF Portal publications with full text remain")

    # Query PubMed for additional publications (unless disabled)
    if not args.skip_pubmed_query:
        print("\n   Step 3e: Querying PubMed for additional publications...")
        print("   - Building PubMed query with NF research filters...")
        pubmed_query = ' '.join(PUBMED_QUERY_FILTERS)
        print(f"   - Query: {pubmed_query[:200]}...")

        print("   - Searching PubMed (this may take a moment)...")
        pubmed_pmids = query_pubmed(pubmed_query, max_results=10000)
        print(f"   - Found {len(pubmed_pmids)} publications in PubMed")

        # Fetch metadata for PubMed results
        if pubmed_pmids:
            # Format PMIDs with prefix
            pubmed_pmids_formatted = [f"PMID:{p}" if not p.startswith('PMID:') else p for p in pubmed_pmids]

            # Filter out previously reviewed and already loaded publications
            synapse_pmids = set(pub_df['pmid'].dropna().unique())
            all_existing = synapse_pmids.union(previously_reviewed)
            new_pmids = [p for p in pubmed_pmids_formatted if p not in all_existing]

            print(f"   - {len(new_pmids)} new publications (after excluding already reviewed/loaded)")

            if new_pmids:
                print("   - Fetching metadata for new PubMed publications...")
                # Remove PMID: prefix for API call
                new_pmids_clean = [p.replace('PMID:', '') for p in new_pmids]
                pubmed_df = fetch_pubmed_metadata_batch(new_pmids_clean)
                print(f"   - Retrieved metadata for {len(pubmed_df)} publications")

                if len(pubmed_df) > 0:
                    # Standardize PMID format
                    pubmed_df['pmid'] = pubmed_df['pmid'].astype(str)

                    # Note: PubMed query already includes 'free full text[Filter]',
                    # so these should all have PMC full text available
                    print(f"   - Adding {len(pubmed_df)} new publications from PubMed")

                    # Align column names
                    if title_col and title_col != 'title':
                        pubmed_df = pubmed_df.rename(columns={'title': title_col})

                    pub_df = pd.concat([pub_df, pubmed_df], ignore_index=True)
                    print(f"   - Total publications after merge: {len(pub_df)}")
            else:
                print("   - No new publications to add (all already reviewed/loaded)")
        else:
            print("   - No publications found in PubMed query")
    else:
        print("\n   Step 3e: Skipping PubMed query (--skip-pubmed-query enabled)")

    # Standardize column names
    column_mapping = {
        'publicationTitle': 'title',
        'publicationDate': 'year'  # Will need additional processing
    }
    for old_col, new_col in column_mapping.items():
        if old_col in pub_df.columns and new_col not in pub_df.columns:
            pub_df = pub_df.rename(columns={old_col: new_col})

    # Load existing links
    print("\n   Step 3f: Filtering out already-linked and previously reviewed publications...")
    link_query = syn.tableQuery("SELECT * FROM syn51735450")
    link_df = link_query.asDataFrame()

    # Identify publications already linked to tools
    linked_pmids = set()
    if 'pmid' in link_df.columns and 'pmid' in pub_df.columns:
        linked_pmids = set(link_df['pmid'].dropna().astype(str).unique())
        # Ensure PMID: prefix
        linked_pmids = {f"PMID:{p.replace('PMID:', '')}" for p in linked_pmids if p and p != 'nan'}

    print(f"   - {len(linked_pmids)} publications already linked to tools")
    print(f"   - {len(previously_reviewed)} publications previously reviewed")

    # Filter to unlinked and not previously reviewed publications
    pub_df['pmid'] = pub_df['pmid'].astype(str)
    all_to_exclude = linked_pmids.union(previously_reviewed)
    unlinked_pubs = pub_df[~pub_df['pmid'].isin(all_to_exclude)].copy()
    print(f"   - {len(pub_df) - len(unlinked_pubs)} publications excluded (already linked or reviewed)")
    print(f"   - {len(unlinked_pubs)} new publications to mine")

    # Check for previously mined publications to avoid re-mining
    previously_mined_pmids = set()
    mining_results_file = 'processed_publications.csv'
    if os.path.exists(mining_results_file):
        try:
            previous_results = pd.read_csv(mining_results_file)
            if 'pmid' in previous_results.columns:
                previously_mined_pmids = set(previous_results['pmid'].dropna().astype(str).unique())
                print(f"   - {len(previously_mined_pmids)} previously mined publications found")

                # Filter out previously mined
                before_filter = len(unlinked_pubs)
                unlinked_pubs = unlinked_pubs[~unlinked_pubs['pmid'].isin(previously_mined_pmids)].copy()
                skipped = before_filter - len(unlinked_pubs)
                if skipped > 0:
                    print(f"   - Skipping {skipped} already-mined publications")
        except Exception as e:
            print(f"   ⚠️  Could not load previous mining results: {e}")

    # Apply max_publications limit if specified
    if args.max_publications and len(unlinked_pubs) > args.max_publications:
        print(f"   - Limiting to first {args.max_publications} publications (--max-publications)")
        unlinked_pubs = unlinked_pubs.head(args.max_publications)

    # Check GFF funding
    unlinked_pubs['is_gff'] = unlinked_pubs['fundingAgency'].astype(str).str.contains('GFF', na=False)
    gff_unlinked = unlinked_pubs[unlinked_pubs['is_gff']]
    print(f"   - {len(gff_unlinked)} GFF-funded unlinked publications")

    # Mine publications
    print("\n4. Mining publications (abstract + full text when available)...")
    print(f"   (This may take a while - ~0.3s per publication)")

    results = []
    summary = []
    abstract_mined = 0
    fetch_success = 0
    methods_found = 0
    intro_found = 0
    existing_tool_matches = 0
    novel_tools_found = 0
    pub_counter = 0

    for idx, row in unlinked_pubs.iterrows():
        pmid = row.get('pmid', '')
        if not pmid or pmid == 'nan':
            continue

        pub_counter += 1
        print(f"\n   [{pub_counter}/{len(unlinked_pubs)}] Mining PMID {pmid}...")

        # Mine publication (abstract + full text)
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
            print(f"     ✓ Abstract: {mining_result['abstract_length']} chars")

        if mining_result['methods_found']:
            methods_found += 1
            print(f"     ✓ Methods section: {mining_result['methods_length']} chars")

        if mining_result['introduction_found']:
            intro_found += 1
            print(f"     ✓ Introduction section: {mining_result['intro_length']} chars")

        if mining_result.get('results_found'):
            print(f"     ✓ Results section: {mining_result['results_length']} chars")

        if mining_result.get('discussion_found'):
            print(f"     ✓ Discussion section: {mining_result['discussion_length']} chars")

        if mining_result['fulltext_available']:
            fetch_success += 1
            print(f"     ✓ Full text sections extracted")

        # Count existing vs novel tools
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
            # Flatten for CSV storage
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

    # Save newly reviewed PMIDs to cache
    if summary:
        reviewed_pmids = set(s['pmid'] for s in summary if s.get('pmid'))
        save_reviewed_pmids(reviewed_pmids)

    print("\n\n" + "=" * 80)
    print("5. Mining Results:")
    print("=" * 80)
    print(f"   Total publications mined: {len(summary)}")
    print(f"   Abstracts mined: {abstract_mined}/{len(unlinked_pubs)} ({100*abstract_mined/len(unlinked_pubs):.1f}%)")
    print(f"   Methods sections found: {methods_found}/{len(unlinked_pubs)} ({100*methods_found/len(unlinked_pubs):.1f}%)")
    print(f"   Introduction sections found: {intro_found}/{len(unlinked_pubs)} ({100*intro_found/len(unlinked_pubs):.1f}%)")
    if fetch_success > 0:
        print(f"   Full text sections extracted: {fetch_success}/{len(unlinked_pubs)} ({100*fetch_success/len(unlinked_pubs):.1f}%)")
    print(f"\n   Tool Matching:")
    print(f"   - Existing tools matched: {existing_tool_matches}")
    print(f"   - Novel tools found: {novel_tools_found}")
    print(f"   - Publications with tools: {len(results)}")

    # Create outputs directory if it doesn't exist
    os.makedirs('tool_coverage/outputs', exist_ok=True)

    # Save summary of ALL publications
    if summary:
        summary_df = pd.DataFrame(summary)
        summary_file = 'tool_coverage/outputs/mining_summary_ALL_publications.csv'
        summary_df.to_csv(summary_file, index=False)
        print(f"\n📄 Summary of all publications saved to: {summary_file}")
        print(f"   - {len(summary_df)} total publications")
        print(f"   - {summary_df['abstract_available'].sum()} with abstracts")
        print(f"   - {summary_df['fulltext_available'].sum()} with full text")
        print(f"   - {summary_df['methods_found'].sum()} with Methods sections")
        print(f"   - {summary_df['introduction_found'].sum()} with Introduction sections")
        print(f"   - {(summary_df['total_tool_count'] > 0).sum()} with potential tools")

    if results:
        results_df = pd.DataFrame(results)

        # Sort by total tool count
        results_df = results_df.sort_values('total_tool_count', ascending=False)

        # Save full results (append to existing if present)
        output_file = 'tool_coverage/outputs/processed_publications.csv'
        if os.path.exists(output_file) and len(previously_mined_pmids) > 0:
            # Append to existing file
            existing_df = pd.read_csv(output_file)
            combined_df = pd.concat([existing_df, results_df], ignore_index=True)
            # Remove duplicates (in case of re-mining)
            combined_df = combined_df.drop_duplicates(subset='pmid', keep='last')
            combined_df.to_csv(output_file, index=False)
            print(f"\n📄 Results appended to: {output_file}")
            print(f"   - {len(existing_df)} previous + {len(results_df)} new = {len(combined_df)} total")
        else:
            # Create new file
            results_df.to_csv(output_file, index=False)
            print(f"\n📄 Full results saved to: {output_file}")

        # Save priority publications (top 30 from combined results)
        if os.path.exists(output_file) and len(previously_mined_pmids) > 0:
            # Use combined results for priority list
            priority_df = combined_df.sort_values('total_tool_count', ascending=False).head(30)
        else:
            priority_df = results_df.head(30)
        priority_file = 'tool_coverage/outputs/priority_publications_FULLTEXT.csv'
        priority_df.to_csv(priority_file, index=False)
        print(f"📄 Top 30 priority publications saved to: {priority_file}")

        # Save GFF publications with tools
        gff_df = results_df[results_df['is_gff'] == True]
        if not gff_df.empty:
            gff_file = 'tool_coverage/outputs/GFF_publications_with_tools_FULLTEXT.csv'
            gff_df.to_csv(gff_file, index=False)
            print(f"📄 GFF publications with tools saved to: {gff_file}")
            print(f"   - {len(gff_df)} GFF publications with tools found")

        # Tool matching breakdown
        print(f"\n   Tool Matching Breakdown:")
        print(f"   - Publications with existing tool matches: {(results_df['existing_tool_count'] > 0).sum()}")
        print(f"   - Publications with novel tools: {(results_df['novel_tool_count'] > 0).sum()}")
        print(f"   - Publications with both: {((results_df['existing_tool_count'] > 0) & (results_df['novel_tool_count'] > 0)).sum()}")
    else:
        print("\n   ⚠️  No tools found in any publications")

    print("\n" + "=" * 80)
    print("FULL TEXT MINING COMPLETE")
    print("=" * 80)
    print("\n📋 Next Steps:")
    print("   1. Run AI validation (recommended):")
    print("      python tool_coverage/scripts/run_publication_reviews.py")
    print("   2. Format mining results for submission:")
    print("      python tool_coverage/scripts/format_mining_for_submission.py")
    print("   3. Use VALIDATED_*.csv files (after validation) or SUBMIT_*.csv files")
    print("=" * 80)


if __name__ == "__main__":
    main()
