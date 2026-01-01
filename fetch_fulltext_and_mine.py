#!/usr/bin/env python3
"""
Fetch full text from PubMed Central, extract Methods sections,
and mine for novel tools using trained patterns.
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
from extract_tool_metadata import extract_all_metadata

# PubMed Central API configuration
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EMAIL = "your.email@example.com"  # Required by NCBI
TOOL_NAME = "nf-research-tools-miner"
API_KEY = None  # Optional: set NCBI API key for higher rate limits

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
    """
    tool_lower = tool_name.lower()
    text_lower = methods_text.lower()

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


def main():
    print("=" * 80)
    print("FULL TEXT MINING FOR NOVEL TOOLS")
    print("=" * 80)

    # Login to Synapse
    syn = synapseclient.Synapse()
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token)
    else:
        syn.login()  # Interactive login if no token

    # Load existing tools
    tool_patterns = load_existing_tools(syn)

    # Load publications
    print("\n3. Loading publications...")
    pub_query = syn.tableQuery("SELECT * FROM syn16857542")
    pub_df = pub_query.asDataFrame()
    print(f"   - {len(pub_df)} total publications")

    # Load existing links
    link_query = syn.tableQuery("SELECT * FROM syn51735450")
    link_df = link_query.asDataFrame()

    # Identify publications already linked to tools
    linked_pmids = set()
    if 'pmid' in link_df.columns and 'pmid' in pub_df.columns:
        linked_pmids = set(link_df['pmid'].dropna().unique())

    # Filter to unlinked publications
    pub_df['pmid'] = pub_df['pmid'].astype(str)
    unlinked_pubs = pub_df[~pub_df['pmid'].isin(linked_pmids)].copy()
    print(f"   - {len(unlinked_pubs)} unlinked publications to mine")

    # Check GFF funding
    unlinked_pubs['is_gff'] = unlinked_pubs['fundingAgency'].astype(str).str.contains('GFF', na=False)
    gff_unlinked = unlinked_pubs[unlinked_pubs['is_gff']]
    print(f"   - {len(gff_unlinked)} GFF-funded unlinked publications")

    # Mine publications
    print("\n4. Fetching full text and mining Methods sections...")
    print(f"   (This may take a while - ~0.3s per publication)")

    results = []
    summary = []  # Track ALL publications
    fetch_success = 0
    fetch_fail = 0
    methods_found = 0
    tools_found = 0

    for idx, row in unlinked_pubs.iterrows():
        pmid = row.get('pmid', '')
        if not pmid or pmid == 'nan':
            continue

        # Fetch full text
        print(f"\n   [{fetch_success + fetch_fail + 1}/{len(unlinked_pubs)}] Fetching PMID {pmid}...", end='')
        fulltext = fetch_pmc_fulltext(pmid)

        if not fulltext:
            print(" ❌ Not available in PMC")
            fetch_fail += 1
            # Track in summary
            summary.append({
                'pmid': pmid,
                'doi': row.get('doi', ''),
                'title': row.get('title', ''),
                'journal': row.get('journal', ''),
                'year': row.get('year', ''),
                'fundingAgency': row.get('fundingAgency', ''),
                'fulltext_available': False,
                'methods_found': False,
                'methods_length': 0,
                'tool_count': 0,
                'antibodies_count': 0,
                'animal_models_count': 0,
                'cell_lines_count': 0,
                'genetic_reagents_count': 0,
                'is_gff': row['is_gff']
            })
            continue

        fetch_success += 1
        print(" ✓ Downloaded")

        # Extract Methods section
        methods_text = extract_methods_section(fulltext)

        if not methods_text or len(methods_text) < 50:
            print("     ⚠️  No Methods section found")
            # Track in summary
            summary.append({
                'pmid': pmid,
                'doi': row.get('doi', ''),
                'title': row.get('title', ''),
                'journal': row.get('journal', ''),
                'year': row.get('year', ''),
                'fundingAgency': row.get('fundingAgency', ''),
                'fulltext_available': True,
                'methods_found': False,
                'methods_length': 0,
                'tool_count': 0,
                'antibodies_count': 0,
                'animal_models_count': 0,
                'cell_lines_count': 0,
                'genetic_reagents_count': 0,
                'is_gff': row['is_gff']
            })
            continue

        methods_found += 1
        print(f"     ✓ Methods section: {len(methods_text)} chars")

        # Mine for tools and extract metadata
        found_tools, tool_metadata = mine_methods_section(methods_text, tool_patterns)

        # Count total tools
        tool_count = sum(len(tools) for tools in found_tools.values())

        # Track in summary (all publications with methods)
        summary.append({
            'pmid': pmid,
            'doi': row.get('doi', ''),
            'title': row.get('title', ''),
            'journal': row.get('journal', ''),
            'year': row.get('year', ''),
            'fundingAgency': row.get('fundingAgency', ''),
            'fulltext_available': True,
            'methods_found': True,
            'methods_length': len(methods_text),
            'tool_count': tool_count,
            'antibodies_count': len(found_tools['antibodies']),
            'animal_models_count': len(found_tools['animal_models']),
            'cell_lines_count': len(found_tools['cell_lines']),
            'genetic_reagents_count': len(found_tools['genetic_reagents']),
            'is_gff': row['is_gff']
        })

        if tool_count > 0:
            tools_found += 1
            print(f"     🎯 Found {tool_count} potential tools!")

            results.append({
                'pmid': pmid,
                'doi': row.get('doi', ''),
                'title': row.get('title', ''),
                'journal': row.get('journal', ''),
                'year': row.get('year', ''),
                'fundingAgency': row.get('fundingAgency', ''),
                'cell_lines': ', '.join(sorted(found_tools['cell_lines'])) if found_tools['cell_lines'] else '',
                'antibodies': ', '.join(sorted(found_tools['antibodies'])) if found_tools['antibodies'] else '',
                'animal_models': ', '.join(sorted(found_tools['animal_models'])) if found_tools['animal_models'] else '',
                'genetic_reagents': ', '.join(sorted(found_tools['genetic_reagents'])) if found_tools['genetic_reagents'] else '',
                'tool_count': tool_count,
                'methods_length': len(methods_text),
                'is_gff': row['is_gff'],
                'tool_metadata': json.dumps(tool_metadata)  # Store as JSON string
            })

    print("\n\n" + "=" * 80)
    print("5. Mining Results:")
    print("=" * 80)
    print(f"   Total publications mined: {len(summary)}")
    print(f"   Full text fetched: {fetch_success}/{len(unlinked_pubs)} ({100*fetch_success/len(unlinked_pubs):.1f}%)")
    if fetch_success > 0:
        print(f"   Methods sections found: {methods_found}/{fetch_success} ({100*methods_found/fetch_success:.1f}% of fetched)")
    if methods_found > 0:
        print(f"   Publications with tools: {tools_found}/{methods_found} ({100*tools_found/methods_found:.1f}% of with Methods)")

    # Save summary of ALL publications
    if summary:
        summary_df = pd.DataFrame(summary)
        summary_file = 'mining_summary_ALL_publications.csv'
        summary_df.to_csv(summary_file, index=False)
        print(f"\n📄 Summary of all publications saved to: {summary_file}")
        print(f"   - {len(summary_df)} total publications")
        print(f"   - {summary_df['fulltext_available'].sum()} with full text")
        print(f"   - {summary_df['methods_found'].sum()} with Methods sections")
        print(f"   - {(summary_df['tool_count'] > 0).sum()} with potential tools")

    if results:
        results_df = pd.DataFrame(results)

        # Sort by tool count
        results_df = results_df.sort_values('tool_count', ascending=False)

        # Save full results
        output_file = 'novel_tools_FULLTEXT_mining.csv'
        results_df.to_csv(output_file, index=False)
        print(f"\n📄 Full results saved to: {output_file}")

        # Save priority publications (top 30)
        priority_df = results_df.head(30)
        priority_file = 'priority_publications_FULLTEXT.csv'
        priority_df.to_csv(priority_file, index=False)
        print(f"📄 Top 30 priority publications saved to: {priority_file}")

        # Save GFF publications with tools
        gff_df = results_df[results_df['is_gff'] == True]
        if not gff_df.empty:
            gff_file = 'GFF_publications_with_tools_FULLTEXT.csv'
            gff_df.to_csv(gff_file, index=False)
            print(f"📄 GFF publications with tools saved to: {gff_file}")
            print(f"   - {len(gff_df)} GFF publications with novel tools found")

        # Tool type breakdown
        print(f"\n   Tool type breakdown:")
        print(f"   - Cell Lines: {results_df['cell_lines'].str.len().gt(0).sum()} publications")
        print(f"   - Antibodies: {results_df['antibodies'].str.len().gt(0).sum()} publications")
        print(f"   - Animal Models: {results_df['animal_models'].str.len().gt(0).sum()} publications")
        print(f"   - Genetic Reagents: {results_df['genetic_reagents'].str.len().gt(0).sum()} publications")
    else:
        print("\n   ⚠️  No novel tools found in any Methods sections")

    print("\n" + "=" * 80)
    print("FULL TEXT MINING COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
