#!/usr/bin/env python3
"""
Extraction functions for new tool types: Computational Tools, Advanced Cellular Models,
Patient-Derived Models, and Clinical Assessment Tools.

These functions use pattern-based extraction since these tool types don't yet exist
in the Synapse database.
"""

import re
from typing import List, Set, Dict, Tuple
import json
from pathlib import Path


def load_mining_patterns() -> Dict:
    """Load mining patterns from config file."""
    config_path = Path(__file__).parent.parent / 'config' / 'mining_patterns.json'
    with open(config_path, 'r') as f:
        data = json.load(f)
    return data.get('patterns', {})


def extract_context(text: str, match_text: str, window_size: int = 150) -> str:
    """Extract context around a match."""
    match_pos = text.lower().find(match_text.lower())
    if match_pos == -1:
        return ""

    start = max(0, match_pos - window_size)
    end = min(len(text), match_pos + len(match_text) + window_size)
    return text[start:end]


def extract_computational_tools(text: str, patterns: Dict = None) -> List[Dict]:
    """
    Extract computational tools (software, pipelines) from text.

    Uses:
    - Software version patterns (v1.0, version 2.3)
    - Repository URLs (GitHub, GitLab, Zenodo)
    - Known tool names from patterns
    - Context phrases indicating tool usage

    Args:
        text: Text to search
        patterns: Mining patterns dict (will load if not provided)

    Returns:
        List of dicts with tool name, context, confidence
    """
    if patterns is None:
        all_patterns = load_mining_patterns()
        patterns = all_patterns.get('computational_tools', {})

    tools = []
    seen_tools = set()

    # Pattern 1: Repository URLs
    repo_patterns = patterns.get('repository_indicators', [])
    for pattern in repo_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            url = match.group(0)
            # Extract tool name from URL
            tool_name = extract_tool_name_from_url(url)
            if tool_name and tool_name.lower() not in seen_tools:
                context = extract_context(text, url)
                tools.append({
                    'name': tool_name,
                    'type': 'computational_tools',
                    'context': context,
                    'confidence': 0.9,
                    'repository': url
                })
                seen_tools.add(tool_name.lower())

    # Pattern 2: Software name with version (e.g., "ImageJ v1.52", "Python 3.8")
    version_pattern = r'(\w+(?:\s+\w+)?)\s+(?:v\.?|version\s+)?(\d+(?:\.\d+)*[a-z]*)'
    for match in re.finditer(version_pattern, text, re.IGNORECASE):
        tool_name = match.group(1).strip()
        version = match.group(2)
        full_match = match.group(0)

        # Skip if looks like a year or just numbers
        if len(tool_name) < 3 or tool_name.isdigit():
            continue

        context = extract_context(text, full_match, 200)

        # Check for usage context
        context_phrases = patterns.get('context_phrases', [])
        has_context = any(re.search(phrase, context, re.IGNORECASE)
                        for phrase in context_phrases)

        if has_context and tool_name.lower() not in seen_tools:
            tools.append({
                'name': tool_name,
                'type': 'computational_tools',
                'context': context,
                'confidence': 0.75,
                'version': version
            })
            seen_tools.add(tool_name.lower())

    # Pattern 3: Known tool names
    tool_names = patterns.get('tool_names', [])
    for tool_name in tool_names:
        if tool_name.lower() in text.lower() and tool_name.lower() not in seen_tools:
            context = extract_context(text, tool_name, 200)
            # Must have usage context
            context_phrases = patterns.get('context_phrases', [])
            if any(re.search(phrase, context, re.IGNORECASE)
                  for phrase in context_phrases):
                tools.append({
                    'name': tool_name,
                    'type': 'computational_tools',
                    'context': context,
                    'confidence': 0.85
                })
                seen_tools.add(tool_name.lower())

    return tools


def extract_tool_name_from_url(url: str) -> str:
    """Extract tool name from repository URL."""
    # Extract from GitHub/GitLab URLs
    match = re.search(r'(?:github|gitlab|bitbucket)\.(?:com|org)/[\w-]+/([\w-]+)', url)
    if match:
        repo_name = match.group(1)
        # Clean up common suffixes
        repo_name = re.sub(r'(-analysis|-analyzer|-tool|-pipeline)$', '', repo_name, flags=re.IGNORECASE)
        return repo_name.replace('-', ' ').replace('_', ' ').title()

    # Extract from DOI
    match = re.search(r'doi\.org/[^/]+/(.+)', url)
    if match:
        return match.group(1).replace('.', ' ').title()

    # Return URL as fallback (better than "Unknown Tool")
    return url


def extract_tool_name_from_context(context: str, version_str: str) -> str:
    """Extract full tool name from context given a version string."""
    # Look for word before version string
    pattern = r'([\w-]+)\s+' + re.escape(version_str)
    match = re.search(pattern, context, re.IGNORECASE)
    if match:
        return match.group(1)
    return version_str


def extract_advanced_cellular_models(text: str, patterns: Dict = None) -> List[Dict]:
    """
    Extract advanced cellular models (organoids, assembloids) from text.

    Uses:
    - Organoid/assembloid indicators
    - Matrix/scaffold indicators
    - Context phrases for generation/culture

    Args:
        text: Text to search
        patterns: Mining patterns dict

    Returns:
        List of dicts with model info
    """
    if patterns is None:
        all_patterns = load_mining_patterns()
        patterns = all_patterns.get('advanced_cellular_models', {})

    models = []
    seen_models = set()

    # Combine all indicators
    all_indicators = (
        patterns.get('organoid_indicators', []) +
        patterns.get('assembloid_indicators', [])
    )

    for pattern in all_indicators:
        # Make pattern case-insensitive and handle word boundaries
        search_pattern = r'\b' + pattern + r's?\b'  # Handle plural
        for match in re.finditer(search_pattern, text, re.IGNORECASE):
            candidate = match.group(0)
            context = extract_context(text, candidate, 200)

            # Check for generation/culture context
            context_phrases = patterns.get('context_phrases', [])
            has_context = any(re.search(phrase, context, re.IGNORECASE)
                            for phrase in context_phrases)

            if has_context:
                # Try to extract fuller model description
                model_desc = extract_model_description(context, candidate)

                # Deduplicate based on base term (organoid, assembloid, etc.)
                base_term = candidate.lower().rstrip('s')
                if base_term not in seen_models:
                    models.append({
                        'name': model_desc,
                        'type': 'advanced_cellular_models',
                        'context': context,
                        'confidence': 0.8
                    })
                    seen_models.add(base_term)

    return models


def extract_model_description(context: str, base_name: str) -> str:
    """Extract fuller model description from context."""
    # Look for adjectives/modifiers before the base name
    pattern = r'([\w-]+\s+)?' + re.escape(base_name)
    match = re.search(pattern, context, re.IGNORECASE)
    if match and match.group(1):
        return match.group(0).strip()
    return base_name


def extract_patient_derived_models(text: str, patterns: Dict = None) -> List[Dict]:
    """
    Extract patient-derived models (PDX, humanized systems) from text.

    Uses:
    - PDX indicators
    - Humanized mouse indicators
    - Host strain patterns
    - Engraftment context phrases

    Args:
        text: Text to search
        patterns: Mining patterns dict

    Returns:
        List of dicts with model info
    """
    if patterns is None:
        all_patterns = load_mining_patterns()
        patterns = all_patterns.get('patient_derived_models', {})

    models = []
    seen_models = set()

    # PDX indicators
    pdx_indicators = patterns.get('pdx_indicators', [])
    for pattern in pdx_indicators:
        # Handle word boundaries and optional hyphens
        search_pattern = pattern.replace('-', r'[-\s]?')  # Allow hyphen or space
        for match in re.finditer(search_pattern, text, re.IGNORECASE):
            candidate = match.group(0)
            context = extract_context(text, candidate, 200)

            # Check for establishment/engraftment context
            context_phrases = patterns.get('context_phrases', [])
            has_context = any(re.search(phrase, context, re.IGNORECASE)
                            for phrase in context_phrases)

            if has_context:
                # Try to extract model ID/name from context
                model_name = extract_pdx_model_name(context, candidate)

                # Normalize for deduplication (PDX/PDX model are same)
                base_name = re.sub(r'\s+(model|xenograft)$', '', model_name, flags=re.IGNORECASE).lower()

                if base_name not in seen_models:
                    models.append({
                        'name': model_name,
                        'type': 'patient_derived_models',
                        'subtype': 'PDX',
                        'context': context,
                        'confidence': 0.85
                    })
                    seen_models.add(base_name)

    # Humanized mouse indicators
    humanized_indicators = patterns.get('humanized_indicators', [])
    for pattern in humanized_indicators:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            candidate = match.group(0)
            if candidate.lower() not in seen_models:
                context = extract_context(text, candidate, 200)
                models.append({
                    'name': candidate,
                    'type': 'patient_derived_models',
                    'subtype': 'Humanized Mouse',
                    'context': context,
                    'confidence': 0.8
                })
                seen_models.add(candidate.lower())

    # Host strain patterns
    host_strains = patterns.get('host_strains', [])
    for strain in host_strains:
        if strain in text:
            context = extract_context(text, strain, 200)
            # Only include if in xenograft/PDX context
            if any(term in context.lower() for term in ['xenograft', 'pdx', 'engraft', 'transplant']):
                if strain.lower() not in seen_models:
                    models.append({
                        'name': strain,
                        'type': 'patient_derived_models',
                        'subtype': 'Host Strain',
                        'context': context,
                        'confidence': 0.7
                    })
                    seen_models.add(strain.lower())

    return models


def extract_pdx_model_name(context: str, base_name: str) -> str:
    """Extract PDX model name/ID from context."""
    # Look for model IDs like "PDX-123", "PDX-NF1-001"
    pattern = r'PDX[-_]?[A-Z0-9-]+\d+'
    match = re.search(pattern, context, re.IGNORECASE)
    if match:
        return match.group(0)
    return base_name


def extract_clinical_assessment_tools(text: str, patterns: Dict = None) -> List[Dict]:
    """
    Extract clinical assessment tools (questionnaires, scales) from text.

    Uses:
    - Validated instrument names (SF-36, PedsQL, etc.)
    - Questionnaire/scale indicators
    - Administration context phrases

    Args:
        text: Text to search
        patterns: Mining patterns dict

    Returns:
        List of dicts with tool info
    """
    if patterns is None:
        all_patterns = load_mining_patterns()
        patterns = all_patterns.get('clinical_assessment_tools', {})

    tools = []
    seen_tools = set()

    # Validated instruments (high confidence)
    validated_instruments = patterns.get('validated_instruments', [])
    for instrument in validated_instruments:
        # Use word boundary matching for better precision
        pattern = r'\b' + re.escape(instrument) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            # Check if already seen (avoid duplicates)
            if instrument.lower() in seen_tools:
                continue

            context = extract_context(text, instrument, 200)

            # Check for administration context
            context_phrases = patterns.get('context_phrases', [])
            has_context = any(re.search(phrase, context, re.IGNORECASE)
                            for phrase in context_phrases)

            if has_context:
                tools.append({
                    'name': instrument,
                    'type': 'clinical_assessment_tools',
                    'context': context,
                    'confidence': 0.95  # High confidence for validated instruments
                })
                seen_tools.add(instrument.lower())

    # Generic questionnaire/scale indicators (lower confidence)
    questionnaire_indicators = patterns.get('questionnaire_indicators', [])
    for pattern in questionnaire_indicators:
        # Look for "X questionnaire", "Y scale", etc. (max 4 words before indicator)
        search_pattern = rf'((?:\w+\s+){{1,4}}){pattern}(?:s)?\b'
        for match in re.finditer(search_pattern, text, re.IGNORECASE):
            candidate = match.group(0).strip()

            # Skip if too long (likely caught whole sentence)
            if len(candidate.split()) > 6:
                continue

            # Skip if already seen (including validated instruments)
            if candidate.lower() in seen_tools:
                continue

            # Skip if this is just "quality of life" without instrument context
            if re.match(r'^quality\s+of\s+life', candidate, re.IGNORECASE):
                continue

            context = extract_context(text, candidate, 200)

            # Must have administration context
            context_phrases = patterns.get('context_phrases', [])
            if any(re.search(phrase, context, re.IGNORECASE)
                  for phrase in context_phrases):
                tools.append({
                    'name': candidate,
                    'type': 'clinical_assessment_tools',
                    'context': context,
                    'confidence': 0.7
                })
                seen_tools.add(candidate.lower())

    return tools


def extract_all_new_tool_types(text: str) -> Dict[str, List[Dict]]:
    """
    Extract all new tool types from text.

    Args:
        text: Text to search

    Returns:
        Dict mapping tool_type -> list of found tools
    """
    patterns = load_mining_patterns()

    results = {
        'computational_tools': extract_computational_tools(text,
            patterns.get('computational_tools', {})),
        'advanced_cellular_models': extract_advanced_cellular_models(text,
            patterns.get('advanced_cellular_models', {})),
        'patient_derived_models': extract_patient_derived_models(text,
            patterns.get('patient_derived_models', {})),
        'clinical_assessment_tools': extract_clinical_assessment_tools(text,
            patterns.get('clinical_assessment_tools', {}))
    }

    return results


if __name__ == '__main__':
    # Test extraction functions
    test_text = """
    We analyzed the data using Python v3.8 and the ImageJ software package.
    Code is available at https://github.com/user/nf-analyzer. Cerebral organoids
    were generated from patient-derived iPSCs and cultured in Matrigel. PDX models
    were established from MPNST tumors in NSG mice. Quality of life was assessed
    using the SF-36 questionnaire and a custom pain scale.
    """

    results = extract_all_new_tool_types(test_text)

    print("Extraction Results:")
    print("==================")
    for tool_type, tools in results.items():
        print(f"\n{tool_type}: {len(tools)} found")
        for tool in tools:
            print(f"  - {tool['name']} (confidence: {tool['confidence']})")
