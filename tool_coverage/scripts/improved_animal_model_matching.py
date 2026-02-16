#!/usr/bin/env python3
"""
Improved animal model matching with alias support.

Addresses issue where descriptive text like "heterozygous Nf1 mice"
doesn't match genetic nomenclature like "Nf1+/-".
"""

import re
import json
from pathlib import Path
from typing import List, Set, Optional
from rapidfuzz import fuzz


def load_animal_model_aliases() -> dict:
    """Load animal model alias mappings."""
    alias_file = Path('tool_coverage/config/animal_model_aliases.json')

    if alias_file.exists():
        with open(alias_file, 'r') as f:
            return json.load(f)

    # Fallback: basic aliases
    return {
        "aliases": {
            "Nf1+/-": [
                "heterozygous Nf1", "Nf1 heterozygous",
                "heterozygous Nf1 knockout", "heterozygous Nf1 mice"
            ],
            "Nf1-/-": [
                "Nf1 knockout", "Nf1 null", "homozygous Nf1 knockout"
            ],
            "Nf2+/-": [
                "heterozygous Nf2", "Nf2 heterozygous",
                "heterozygous Nf2 knockout"
            ],
            "Nf2-/-": [
                "Nf2 knockout", "Nf2 null", "homozygous Nf2 knockout"
            ]
        }
    }


def expand_animal_model_patterns(base_patterns: List[str]) -> List[str]:
    """
    Expand animal model patterns with aliases.

    For each pattern like "Nf1+/-", add aliases like
    "heterozygous Nf1", "heterozygous Nf1 mice", etc.

    Args:
        base_patterns: List of base pattern names (e.g., ["Nf1+/-", "Nf2+/-"])

    Returns:
        Expanded list including aliases
    """
    config = load_animal_model_aliases()
    aliases_map = config.get('aliases', {})

    expanded = set(base_patterns)  # Start with base patterns

    for pattern in base_patterns:
        # Add any aliases defined for this pattern
        if pattern in aliases_map:
            expanded.update(aliases_map[pattern])

    return list(expanded)


def match_animal_model_with_aliases(text: str,
                                   existing_models: dict,
                                   threshold: float = 0.85) -> Set[str]:
    """
    Match animal models in text, including alias matching.

    Args:
        text: Text to search
        existing_models: Dict of {resourceId: resourceName} from database
        threshold: Fuzzy matching threshold

    Returns:
        Set of matched resource IDs
    """
    matches = set()
    text_lower = text.lower()

    config = load_animal_model_aliases()
    aliases_map = config.get('aliases', {})

    # For each known model in database
    for resource_id, model_name in existing_models.items():
        model_lower = model_name.lower()

        # Direct fuzzy match on model name
        if model_lower in text_lower:
            matches.add(resource_id)
            continue

        # Try fuzzy match
        words = re.findall(r'\b[\w\-\+/]+\b', text_lower)
        for word in words:
            if len(word) >= 3:
                score = fuzz.ratio(model_lower, word) / 100.0
                if score >= threshold:
                    matches.add(resource_id)
                    break

        # Check aliases
        if model_name in aliases_map:
            for alias in aliases_map[model_name]:
                alias_lower = alias.lower()
                if alias_lower in text_lower:
                    matches.add(resource_id)
                    break

    # Also check regex patterns for common forms
    patterns = config.get('patterns', {})

    if 'heterozygous_pattern' in patterns:
        pattern_info = patterns['heterozygous_pattern']
        regex = pattern_info['regex']
        matches_found = re.findall(regex, text, re.IGNORECASE)

        for match in matches_found:
            # match is like ('Nf1', 'knockout')
            gene = match[0] if isinstance(match, tuple) else match
            # Try to find corresponding model
            target_name = f"{gene}+/-"

            for resource_id, model_name in existing_models.items():
                if model_name.lower() == target_name.lower():
                    matches.add(resource_id)
                    break

    return matches


def get_canonical_name(text_mention: str) -> Optional[str]:
    """
    Convert descriptive text to canonical nomenclature.

    Example:
        "heterozygous Nf1 mice" -> "Nf1+/-"
        "Nf1 knockout" -> "Nf1-/-"

    Args:
        text_mention: Text found in publication

    Returns:
        Canonical name or None
    """
    text_lower = text_mention.lower()

    # Pattern: heterozygous + gene
    hetero_match = re.search(r'heterozygous\s+(nf\d+)', text_lower)
    if hetero_match:
        gene = hetero_match.group(1).upper()
        return f"{gene}+/-"

    # Pattern: gene + knockout/null (homozygous)
    ko_match = re.search(r'(nf\d+)\s+(knockout|null)', text_lower)
    if ko_match and 'heterozygous' not in text_lower:
        gene = ko_match.group(1).upper()
        return f"{gene}-/-"

    return None


# Example usage
if __name__ == '__main__':
    # Test with the PMID 10339466 abstract snippet
    test_text = "heterozygous Nf1 knockout mice"

    print("Testing animal model alias matching:")
    print(f"Text: '{test_text}'")
    print()

    # Simulate existing models
    existing_models = {
        'd27fd7b0-ed8f-4ee2-a8d9-26748c12518c': 'Nf1+/-',
        'some-other-id': 'Nf1-/-'
    }

    matches = match_animal_model_with_aliases(test_text, existing_models)

    if matches:
        print(f"✓ Matched {len(matches)} models:")
        for resource_id in matches:
            print(f"  - {existing_models[resource_id]} (ID: {resource_id})")
    else:
        print("✗ No matches found")

    print()
    canonical = get_canonical_name(test_text)
    print(f"Canonical name: {canonical}")
