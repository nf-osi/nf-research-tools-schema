#!/usr/bin/env python3
"""
IMPROVED MINING: Better tool detection and categorization.

Key improvements over original:
1. Less restrictive context requirements (higher recall)
2. Better development vs usage detection
3. Recognizes established tools (ImageJ, GraphPad Prism, etc.)
4. Smarter pattern matching

This addresses:
- Low hit rate (was 0.4%, only 5/1128 publications)
- Incorrect categorization (established tools marked as "developed")
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from fetch_fulltext_and_mine import (
    fetch_pmc_fulltext,
    extract_methods_section,
    extract_introduction_section,
    extract_results_section,
    extract_discussion_section,
    extract_abstract_text,
    match_to_existing_tool,
    cache_publication_text,
    load_existing_tools_for_matching,
    sanitize_pmid_for_filename
)

import pandas as pd
import synapseclient
import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from rapidfuzz import fuzz

# Import improved animal model matching
from improved_animal_model_matching import (
    load_animal_model_aliases,
    expand_animal_model_patterns,
    match_animal_model_with_aliases,
    get_canonical_name
)


def load_known_computational_tools() -> Dict:
    """Load curated list of known computational tools."""
    config_file = Path(__file__).parent.parent / 'config' / 'known_computational_tools.json'

    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)

    return {'categories': {}, 'excluded_tools': {}, 'novel_tool_indicators': {}}


def get_all_known_tools(config: Dict) -> Set[str]:
    """Get set of all known tool names (case-insensitive)."""
    known = set()

    for category, tools in config.get('categories', {}).items():
        for tool in tools:
            known.add(tool.lower())

    return known


def get_excluded_tools(config: Dict) -> Set[str]:
    """Get set of excluded tools (lab instruments, etc.)."""
    excluded = set()

    for category, tools in config.get('excluded_tools', {}).items():
        for tool in tools:
            excluded.add(tool.lower())

    return excluded


def should_filter_tool(tool_name: str, tool_type: str, config: Dict) -> bool:
    """Check if tool should be filtered out (e.g., lab instruments)."""
    if tool_type != 'computational_tools':
        return False

    excluded_tools = get_excluded_tools(config)
    return tool_name.lower() in excluded_tools


def is_truly_novel(tool_name: str, title: str, metadata: dict, config: Dict) -> bool:
    """
    Determine if a computational tool is truly novel.

    Novel tools are typically:
    1. Mentioned in the publication title
    2. Described with development language ("we developed", "new tool")
    3. NOT in the known tools list

    Args:
        tool_name: Name of the tool
        title: Publication title
        metadata: Tool metadata with context
        config: Configuration with novel tool indicators

    Returns:
        True if truly novel, False if likely existing/common
    """
    tool_lower = tool_name.lower()
    title_lower = title.lower() if title else ""
    context = metadata.get('context', '').lower()

    # Check if in title (strong indicator of novel tool)
    if tool_lower in title_lower:
        # Check for development language
        title_patterns = config.get('novel_tool_indicators', {}).get('title_patterns', [])
        for pattern in title_patterns:
            if pattern in title_lower:
                return True  # Mentioned in title with novel/new language

    # Check context for strong development indicators
    context_patterns = config.get('novel_tool_indicators', {}).get('context_patterns', [])
    dev_count = sum(1 for pattern in context_patterns if pattern in context)

    if dev_count >= 2:  # Multiple strong development indicators
        return True

    # Check if it's already marked as development
    if metadata.get('is_development', False):
        return True

    # Default: not novel (likely existing tool)
    return False


def is_likely_established_tool(tool_name: str, tool_type: str, config: Dict) -> bool:
    """Check if a tool is a well-known established tool."""
    if tool_type != 'computational_tools':
        return False

    known_tools = get_all_known_tools(config)
    return tool_name.lower() in known_tools


def is_development_context_improved(tool_name: str, tool_type: str, text: str) -> bool:
    """
    Improved detection: TRUE if paper describes DEVELOPING the tool.

    Development indicators:
    - "we developed/created/designed [tool]"
    - "novel [tool]"
    - "[tool] was developed"

    Usage indicators (NOT development):
    - Version numbers: "ImageJ v1.53k"
    - Commercial sources: "obtained from", "purchased"
    - Established tools with version numbers
    """
    tool_lower = tool_name.lower()
    text_lower = text.lower()

    # Version number = USAGE (not development)
    version_patterns = [
        rf'{re.escape(tool_lower)}\s+v\d',
        rf'{re.escape(tool_lower)}\s+version\s+\d',
        rf'{re.escape(tool_lower)}\s+\d+\.\d+',
        rf'{re.escape(tool_lower)}\s+\(v\d',
    ]
    for pattern in version_patterns:
        if re.search(pattern, text_lower):
            return False

    # Find mentions
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

    # Strong development patterns
    strong_dev_patterns = [
        r'we\s+(develop|creat|design|generat|establish|engineer|construct)\w*\s+\w*\s*' + re.escape(tool_lower),
        r'(novel|new)\s+\w*\s*' + re.escape(tool_lower),
        r'' + re.escape(tool_lower) + r'\s+(was|were)\s+(develop|creat|design|establish)',
    ]

    # Strong usage indicators
    strong_usage_keywords = [
        'obtained from', 'purchased from', 'acquired from', 'provided by',
        'commercially available', 'charles river', 'jackson lab', 'jax',
        'atcc', 'sigma', 'millipore', 'thermo fisher', 'invitrogen',
        'downloaded from', 'available at'
    ]

    dev_score = 0
    usage_score = 0

    for pos in positions:
        start = max(0, pos - 300)
        end = min(len(text_lower), pos + len(tool_lower) + 300)
        context = text_lower[start:end]

        for pattern in strong_dev_patterns:
            if re.search(pattern, context):
                dev_score += 3

        for keyword in strong_usage_keywords:
            if keyword in context:
                usage_score += 5

    return dev_score >= 3 and usage_score == 0


def fuzzy_match_tools(text: str, patterns: List[str], threshold: float = 0.85) -> Set[str]:
    """Fuzzy match tool names in text."""
    matches = set()
    text_lower = text.lower()

    for pattern in patterns:
        pattern_lower = pattern.lower()

        # Exact match first
        if pattern_lower in text_lower:
            matches.add(pattern)
            continue

        # Fuzzy match
        words = re.findall(r'\b[\w\-\.]+\b', text_lower)
        for word in words:
            if len(word) < 3:
                continue
            score = fuzz.ratio(pattern_lower, word) / 100.0
            if score >= threshold:
                matches.add(pattern)
                break

    return matches


def mine_text_section_improved(text: str, tool_patterns: Dict[str, List[str]],
                               section_name: str = 'methods',
                               require_context: bool = False,
                               config: Optional[Dict] = None) -> Tuple[Dict[str, Set[str]], Dict[str, Dict]]:
    """
    Improved mining: less restrictive, smarter categorization.

    Args:
        text: Text to mine
        tool_patterns: Tool patterns by type
        section_name: Section name for metadata
        require_context: If True, require tool near context keywords
        config: Known computational tools config (optional)

    Returns:
        (found_tools dict, metadata dict)
    """
    found_tools = {
        'cell_lines': set(),
        'antibodies': set(),
        'animal_models': set(),
        'genetic_reagents': set(),
        'computational_tools': set(),
        'advanced_cellular_models': set(),
        'patient_derived_models': set(),
        'clinical_assessment_tools': set()
    }
    tool_metadata = {}

    if not text or len(text) < 50:
        return found_tools, tool_metadata

    text_lower = text.lower()

    # Load config if not provided
    if config is None:
        config = load_known_computational_tools()

    # Context keywords (for higher confidence when present)
    context_keywords = [
        'using', 'used', 'utilized', 'employed', 'with',
        'analyzed', 'examined', 'studied', 'assessed',
        'measured', 'quantified', 'visualized', 'performed',
        'generated', 'developed', 'created', 'obtained',
    ]

    for tool_type, patterns in tool_patterns.items():
        if not patterns:
            continue

        # Fuzzy match (lower threshold for better recall)
        matches = fuzzy_match_tools(text, patterns, threshold=0.83)  # Was 0.88

        for tool_name in matches:
            tool_lower = tool_name.lower()

            # Find positions
            positions = []
            idx = 0
            while idx < len(text_lower):
                idx = text_lower.find(tool_lower, idx)
                if idx == -1:
                    break
                positions.append(idx)
                idx += 1

            if not positions:
                continue

            # Filter out lab instruments (e.g., NanoDrop)
            if should_filter_tool(tool_name, tool_type, config):
                continue

            # Check context requirement
            if require_context:
                has_context = False
                for pos in positions:
                    start = max(0, pos - 200)
                    end = min(len(text_lower), pos + len(tool_lower) + 200)
                    context = text_lower[start:end]
                    if any(kw in context for kw in context_keywords):
                        has_context = True
                        break
                if not has_context:
                    continue

            # Tool found!
            found_tools[tool_type].add(tool_name)

            # Extract metadata
            metadata_key = f"{tool_type}:{tool_name}"
            pos = positions[0]
            start = max(0, pos - 150)
            end = min(len(text), pos + len(tool_name) + 150)
            context = text[start:end]

            # Determine development vs usage
            is_dev = is_development_context_improved(tool_name, tool_type, text)
            is_established = is_likely_established_tool(tool_name, tool_type, config)

            # Override: established tools are usage not development
            if is_established and is_dev:
                is_dev = False

            # Calculate confidence
            confidence = 0.7
            if any(kw in context.lower() for kw in context_keywords):
                confidence += 0.1
            if is_established:
                confidence += 0.1
            if re.search(r'v\d|version\s+\d|\d+\.\d+', context.lower()):
                confidence += 0.05
            confidence = min(0.95, confidence)

            tool_metadata[metadata_key] = {
                'context': context,
                'confidence': confidence,
                'is_development': is_dev,
                'is_generic': False,
                'is_established': is_established,
                'section': section_name
            }

    return found_tools, tool_metadata


def mine_publication_improved(pub_row: pd.Series, tool_patterns: Dict[str, List[str]],
                              existing_tools: Dict[str, Dict[str, str]], enable_tool_mining: bool = False) -> Dict:
    """
    Mine publication with improved logic.

    Args:
        pub_row: Publication row from DataFrame
        tool_patterns: Tool patterns by type
        existing_tools: Existing tools from database
        enable_tool_mining: If True, perform tool mining. If False, only extract sections.
    """
    pmid = str(pub_row.get('pmid', ''))
    title = pub_row.get('title', '')
    result = {
        'pmid': pmid,
        'doi': pub_row.get('doi', ''),
        'title': title,
        'journal': pub_row.get('journal', ''),
        'year': pub_row.get('year', ''),
        'abstract_length': 0,
        'methods_length': 0,
        'intro_length': 0,
        'results_length': 0,
        'discussion_length': 0,
        'existing_tools': {},
        'novel_tools': {},
        'tool_metadata': {},
        'tool_sources': {},
        'is_gff': 'GFF' in str(pub_row.get('fundingAgency', ''))
    }

    # Load known computational tools config
    config = load_known_computational_tools()
    known_tools = get_all_known_tools(config)

    # 1. Extract abstract
    abstract_text = extract_abstract_text(pub_row)
    if abstract_text:
        result['abstract_length'] = len(abstract_text)

    # 2. Fetch full text
    fulltext = fetch_pmc_fulltext(pmid)

    # 3. Extract all sections (needed for Sonnet review later)
    intro_text = extract_introduction_section(fulltext) if fulltext else ""
    methods_text = extract_methods_section(fulltext) if fulltext else ""
    results_text = extract_results_section(fulltext) if fulltext else ""
    discussion_text = extract_discussion_section(fulltext) if fulltext else ""

    if intro_text:
        result['intro_length'] = len(intro_text)
    if methods_text:
        result['methods_length'] = len(methods_text)
    if results_text:
        result['results_length'] = len(results_text)
    if discussion_text:
        result['discussion_length'] = len(discussion_text)

    # Cache all extracted text for later Sonnet review
    cache_publication_text(
        pmid=pmid,
        abstract=abstract_text,
        methods=methods_text,
        intro=intro_text,
        results=results_text,
        discussion=discussion_text
    )

    # 4. Optionally perform tool mining (disabled by default)
    if enable_tool_mining:
        # Mine abstract (relaxed - no context requirement)
        if abstract_text:
            abstract_results = mine_text_section_improved(
                abstract_text, tool_patterns, 'abstract', require_context=False, config=config
            )
        else:
            abstract_results = ({t: set() for t in tool_patterns.keys()}, {})

        # Mine Methods (relaxed - no strict context requirement)
        if methods_text and len(methods_text) >= 50:
            methods_results = mine_text_section_improved(
                methods_text, tool_patterns, 'methods', require_context=False, config=config
            )
        else:
            methods_results = ({t: set() for t in tool_patterns.keys()}, {})

        # Merge results (abstract + methods only)
        all_tools = {}
        all_metadata = {}
        tool_sources = {}

        for source_name, (tools_dict, metadata_dict) in [
            ('abstract', abstract_results),
            ('methods', methods_results)
        ]:
            for tool_type, tools in tools_dict.items():
                if tool_type not in all_tools:
                    all_tools[tool_type] = set()

                for tool_name in tools:
                    all_tools[tool_type].add(tool_name)

                    # Track sources
                    tool_key = f"{tool_type}:{tool_name}"
                    if tool_key not in tool_sources:
                        tool_sources[tool_key] = set()
                    tool_sources[tool_key].add(source_name)

                    # Merge metadata (prefer methods > intro > abstract)
                    if tool_key in metadata_dict:
                        if tool_key not in all_metadata:
                            all_metadata[tool_key] = metadata_dict[tool_key]
                        elif source_name == 'methods':
                            # Methods has priority
                            all_metadata[tool_key] = metadata_dict[tool_key]

        result['tool_metadata'] = all_metadata
        result['tool_sources'] = {k: list(v) for k, v in tool_sources.items()}
    else:
        # Tool mining disabled - initialize empty results
        all_tools = {t: set() for t in tool_patterns.keys()}

    # 5. Match against existing tools (only if tool mining enabled)
    if enable_tool_mining:
        for tool_type, tools in all_tools.items():
            result['existing_tools'][tool_type] = {}
            result['novel_tools'][tool_type] = set()

            # Special handling for animal models with alias matching
            if tool_type == 'animal_models':
                # Combine abstract + methods text for better context
                full_text = (abstract_text or "") + " " + (methods_text or "")

                # Use improved alias-aware matching
                matched_ids = match_animal_model_with_aliases(
                    full_text,
                    existing_tools.get('animal_models', {}),
                    threshold=0.85
                )

                # Map matched IDs back to tool names
                # existing_tools structure: {resourceId: resourceName}
                # So we don't need to reverse it
                id_to_name = existing_tools.get('animal_models', {})

                for resource_id in matched_ids:
                    if resource_id in id_to_name:
                        resource_name = id_to_name[resource_id]
                        # Find which detected tool name matched
                        for tool_name in tools:
                            # Check if this tool_name could have matched this resource
                            # Use canonical name conversion (case-insensitive comparison)
                            canonical = get_canonical_name(tool_name)
                            if canonical and canonical.lower() == resource_name.lower():
                                result['existing_tools'][tool_type][tool_name] = resource_id
                                break
                        else:
                            # No specific tool name matched, use resource name
                            result['existing_tools'][tool_type][resource_name] = resource_id

                # Any tools not matched are novel
                for tool_name in tools:
                    matched = False
                    for matched_name in result['existing_tools'][tool_type].keys():
                        canonical = get_canonical_name(tool_name)
                        if (tool_name == matched_name or
                            (canonical and canonical.lower() == matched_name.lower())):
                            matched = True
                            break
                    if not matched:
                        result['novel_tools'][tool_type].add(tool_name)
            elif tool_type == 'computational_tools':
                # Special handling for computational tools with known tools list
                for tool_name in tools:
                    tool_lower = tool_name.lower()
                    tool_key = f"{tool_type}:{tool_name}"
                    tool_meta = all_metadata.get(tool_key, {})

                    # First check against existing tools in database
                    resource_id = match_to_existing_tool(tool_name, tool_type, existing_tools)
                    if resource_id:
                        result['existing_tools'][tool_type][tool_name] = resource_id
                    # Then check against known tools list
                    elif tool_lower in known_tools:
                        # Known tool but not in database - mark for review
                        result['existing_tools'][tool_type][tool_name] = "NEEDS_REVIEW"
                    # Check if truly novel (in title, development language)
                    elif is_truly_novel(tool_name, title, tool_meta, config):
                        result['novel_tools'][tool_type].add(tool_name)
                    else:
                        # Likely an existing tool we don't know about
                        # Mark for manual review rather than claiming it's novel
                        result['existing_tools'][tool_type][tool_name] = "NEEDS_REVIEW"
            else:
                # Standard matching for other tool types
                for tool_name in tools:
                    resource_id = match_to_existing_tool(tool_name, tool_type, existing_tools)
                    if resource_id:
                        result['existing_tools'][tool_type][tool_name] = resource_id
                    else:
                        result['novel_tools'][tool_type].add(tool_name)

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Improved mining with better detection and categorization'
    )
    parser.add_argument(
        '--input',
        default='tool_coverage/outputs/screened_publications.csv',
        help='Input CSV with screened publications'
    )
    parser.add_argument(
        '--output',
        default='tool_coverage/outputs/processed_publications_improved.csv',
        help='Output CSV with mined tools'
    )
    parser.add_argument(
        '--max-publications',
        type=int,
        default=None,
        help='Limit for testing'
    )
    parser.add_argument(
        '--enable-tool-mining',
        action='store_true',
        default=False,
        help='Enable tool mining (disabled by default, only extracts sections)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("PUBLICATION TEXT EXTRACTION")
    if args.enable_tool_mining:
        print(" + TOOL MINING")
    print("=" * 80)
    if args.enable_tool_mining:
        print("\nImprovements:")
        print("  ✓ Less restrictive context requirements (higher recall)")
        print("  ✓ Better development vs usage detection")
        print("  ✓ Recognizes established tools (ImageJ, GraphPad, etc.)")
        print("  ✓ Smarter pattern matching (lower threshold)")
    else:
        print("\nMode: Section extraction only (tool mining disabled)")
        print("  ✓ Extracts abstract, introduction, methods, results, discussion")
        print("  ✓ Caches text for later Sonnet review")
        print("  ✓ No tool mining performed (use --enable-tool-mining to enable)")
    print()

    # Login to Synapse
    syn = synapseclient.Synapse()
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token)
    else:
        syn.login()

    # Load publications
    print("1. Loading screened publications...")
    pubs_df = pd.read_csv(args.input)
    print(f"   - {len(pubs_df)} publications")

    if args.max_publications:
        pubs_df = pubs_df.head(args.max_publications)
        print(f"   - Limited to {len(pubs_df)} for testing")

    # Load tool patterns
    print("\n2. Loading tool patterns...")
    existing_tools = load_existing_tools_for_matching(syn)

    # Initialize all tool types (including those not in Resource table)
    all_tool_types = ['cell_lines', 'antibodies', 'animal_models', 'genetic_reagents',
                      'computational_tools', 'advanced_cellular_models',
                      'patient_derived_models', 'clinical_assessment_tools']

    # Ensure existing_tools has all types (empty dict if not present)
    for tool_type in all_tool_types:
        if tool_type not in existing_tools:
            existing_tools[tool_type] = {}

    tool_patterns = {}
    for tool_type, tools_dict in existing_tools.items():
        tool_patterns[tool_type] = list(tools_dict.keys())  # Use keys (tool names) not values (metadata)

    # Expand animal model patterns with aliases
    if 'animal_models' in tool_patterns:
        print("\n2b. Expanding animal model patterns with aliases...")
        original_count = len(tool_patterns['animal_models'])
        tool_patterns['animal_models'] = expand_animal_model_patterns(
            tool_patterns['animal_models']
        )
        expanded_count = len(tool_patterns['animal_models'])
        print(f"   - Expanded from {original_count} to {expanded_count} patterns (+{expanded_count - original_count} aliases)")

    # Load computational tools and other patterns from mining_patterns.json
    print("\n2c. Loading additional patterns from mining_patterns.json...")
    patterns_file = Path('tool_coverage/config/mining_patterns.json')
    if patterns_file.exists():
        with open(patterns_file, 'r') as f:
            patterns_config = json.load(f)

        # Add computational tool names
        if 'computational_tools' in patterns_config.get('patterns', {}):
            comp_patterns = patterns_config['patterns']['computational_tools']
            if 'tool_names' in comp_patterns:
                tool_patterns['computational_tools'] = comp_patterns['tool_names']
                print(f"   - Loaded {len(comp_patterns['tool_names'])} computational tool names")

        # Add other pattern types if they have tool_names
        for tool_type in ['advanced_cellular_models', 'patient_derived_models', 'clinical_assessment_tools']:
            if tool_type not in tool_patterns:
                tool_patterns[tool_type] = []
            # These will be empty for now but structure is ready
    else:
        print(f"   ⚠️  Warning: {patterns_file} not found")
        tool_patterns['computational_tools'] = []
        tool_patterns['advanced_cellular_models'] = []
        tool_patterns['patient_derived_models'] = []
        tool_patterns['clinical_assessment_tools'] = []

    print(f"   - Total tool types loaded: {len(tool_patterns)}")

    # Mine publications
    action_verb = "Mining" if args.enable_tool_mining else "Extracting sections from"
    print(f"\n3. {action_verb} {len(pubs_df)} publications...\n")

    results = []
    Path('tool_reviews/publication_cache').mkdir(parents=True, exist_ok=True)

    for idx, row in pubs_df.iterrows():
        pmid = row.get('pmid', '')
        if not pmid:
            continue

        print(f"   [{idx+1}/{len(pubs_df)}] PMID {pmid}...")

        result = mine_publication_improved(row, tool_patterns, existing_tools, enable_tool_mining=args.enable_tool_mining)

        # Report on what was extracted
        sections_extracted = []
        if result['abstract_length'] > 0:
            sections_extracted.append(f"abstract:{result['abstract_length']}")
        if result['intro_length'] > 0:
            sections_extracted.append(f"intro:{result['intro_length']}")
        if result['methods_length'] > 0:
            sections_extracted.append(f"methods:{result['methods_length']}")
        if result['results_length'] > 0:
            sections_extracted.append(f"results:{result['results_length']}")
        if result['discussion_length'] > 0:
            sections_extracted.append(f"discussion:{result['discussion_length']}")

        if sections_extracted:
            print(f"     ✓ Extracted: {', '.join(sections_extracted)}")

        # Count tools (if mining enabled)
        if args.enable_tool_mining:
            existing_count = sum(len(tools) for tools in result['existing_tools'].values())
            novel_count = sum(len(tools) for tools in result['novel_tools'].values())
            total_count = existing_count + novel_count

            if total_count > 0:
                print(f"     ✓ Found {total_count} tools ({existing_count} existing, {novel_count} novel)")
        else:
            existing_count = 0
            novel_count = 0
            total_count = 0

        # Store result (always store when sections extracted or tools found)
        if sections_extracted or total_count > 0:
            result_row = {
                'pmid': result['pmid'],
                'doi': result['doi'],
                'title': result['title'],
                'journal': result['journal'],
                'year': result['year'],
                'abstract_length': result['abstract_length'],
                'methods_length': result['methods_length'],
                'intro_length': result['intro_length'],
                'results_length': result.get('results_length', 0),
                'discussion_length': result.get('discussion_length', 0),
                'existing_tool_count': existing_count,
                'novel_tool_count': novel_count,
                'total_tool_count': total_count,
                'existing_tools': json.dumps(result['existing_tools']),
                'novel_tools': json.dumps({k: list(v) for k, v in result['novel_tools'].items()}),
                'tool_metadata': json.dumps(result['tool_metadata']),
                'tool_sources': json.dumps(result['tool_sources']),
                'is_gff': result['is_gff']
            }
            results.append(result_row)
        else:
            print(f"     ⊘ No sections extracted")

    # Save results
    print(f"\n4. Saving results...")
    if results:
        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        results_df = pd.DataFrame(results)
        results_df.to_csv(output_file, index=False)
        if args.enable_tool_mining:
            print(f"   ✓ Saved {len(results_df)} publications with tools to {output_file}")
        else:
            print(f"   ✓ Saved {len(results_df)} publications with extracted sections to {output_file}")
    else:
        if args.enable_tool_mining:
            print("   ⚠️  No tools found in any publications")
        else:
            print("   ⚠️  No sections extracted from any publications")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total publications: {len(pubs_df)}")
    if args.enable_tool_mining:
        print(f"  Publications with tools: {len(results)}")
        print(f"  Hit rate: {len(results)/len(pubs_df)*100:.1f}%")
    else:
        print(f"  Publications with extracted sections: {len(results)}")
        print(f"  Extraction rate: {len(results)/len(pubs_df)*100:.1f}%")
        print("\n  Note: Tool mining disabled. To enable, use --enable-tool-mining flag")
    print()


if __name__ == '__main__':
    main()
