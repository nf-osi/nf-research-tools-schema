#!/usr/bin/env python3
"""
Re-categorize computational tools to fix issues:
1. Mark well-known tools as "existing" not "novel"
2. Filter out laboratory instruments (NanoDrop, etc.)
3. Identify truly novel tools (usually mentioned in title)
"""

import pandas as pd
import json
import re
from pathlib import Path
from typing import Set, Dict


def load_known_tools() -> Dict:
    """Load curated list of known computational tools."""
    config_file = Path('tool_coverage/config/known_computational_tools.json')

    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)

    return {'categories': {}, 'excluded_tools': {}}


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


def recategorize_computational_tools(input_file: Path, output_file: Path) -> dict:
    """
    Re-categorize computational tools in processed publications.

    Args:
        input_file: Input CSV with processed publications
        output_file: Output CSV with corrected categorization

    Returns:
        Dict with statistics
    """
    # Load publications
    df = pd.read_csv(input_file)

    # Load known tools config
    config = load_known_tools()
    known_tools = get_all_known_tools(config)
    excluded_tools = get_excluded_tools(config)

    stats = {
        'total_publications': len(df),
        'recategorized_count': 0,
        'filtered_count': 0,
        'novel_to_existing': 0,
        'filtered_instruments': 0,
        'truly_novel_kept': 0
    }

    # Process each publication
    for idx, row in df.iterrows():
        existing_tools = json.loads(row['existing_tools'])
        novel_tools = json.loads(row['novel_tools'])
        metadata = json.loads(row['tool_metadata'])

        title = row.get('title', '')

        # Get computational tools
        comp_novel = novel_tools.get('computational_tools', [])
        comp_existing = existing_tools.get('computational_tools', {})

        if not comp_novel and not comp_existing:
            continue  # No computational tools

        # Process novel tools
        tools_to_remove = []
        tools_to_recategorize = {}  # tool_name -> "existing" or "filter"

        for tool_name in comp_novel:
            tool_lower = tool_name.lower()
            tool_key = f"computational_tools:{tool_name}"
            tool_meta = metadata.get(tool_key, {})

            # Check if it's a lab instrument (should be filtered)
            if tool_lower in excluded_tools:
                tools_to_recategorize[tool_name] = "filter"
                stats['filtered_instruments'] += 1
                continue

            # Check if it's a known tool (should be existing, not novel)
            if tool_lower in known_tools:
                tools_to_recategorize[tool_name] = "existing"
                stats['novel_to_existing'] += 1
                continue

            # Check if it's truly novel
            if not is_truly_novel(tool_name, title, tool_meta, config):
                # Likely a known tool we don't have in our list
                # Move to existing for manual review
                tools_to_recategorize[tool_name] = "existing"
                stats['novel_to_existing'] += 1
            else:
                # Keep as novel
                stats['truly_novel_kept'] += 1

        # Apply recategorization
        if tools_to_recategorize:
            stats['recategorized_count'] += 1

            # Update novel tools list
            comp_novel = [t for t in comp_novel if tools_to_recategorize.get(t) != "filter" and tools_to_recategorize.get(t) != "existing"]

            # Move to existing
            for tool_name, action in tools_to_recategorize.items():
                if action == "existing":
                    # Add to existing (without resourceId since we don't have it)
                    comp_existing[tool_name] = "NEEDS_REVIEW"
                elif action == "filter":
                    # Remove from metadata
                    tool_key = f"computational_tools:{tool_name}"
                    if tool_key in metadata:
                        metadata[tool_key]['filtered'] = True
                        metadata[tool_key]['reason'] = "Laboratory instrument, not computational tool"
                    stats['filtered_count'] += 1

            # Update row
            existing_tools['computational_tools'] = comp_existing
            novel_tools['computational_tools'] = comp_novel

            df.at[idx, 'existing_tools'] = json.dumps(existing_tools)
            df.at[idx, 'novel_tools'] = json.dumps(novel_tools)
            df.at[idx, 'tool_metadata'] = json.dumps(metadata)

            # Update counts
            existing_count = sum(len(tools) for tools in existing_tools.values())
            novel_count = sum(len(tools) for tools in novel_tools.values() if isinstance(tools, list))

            df.at[idx, 'existing_tool_count'] = existing_count
            df.at[idx, 'novel_tool_count'] = novel_count
            df.at[idx, 'total_tool_count'] = existing_count + novel_count

    # Save corrected file
    df.to_csv(output_file, index=False)

    return stats


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Re-categorize computational tools'
    )
    parser.add_argument(
        '--input',
        default='tool_coverage/outputs/processed_publications_improved.csv',
        help='Input CSV'
    )
    parser.add_argument(
        '--output',
        default='tool_coverage/outputs/processed_publications_corrected.csv',
        help='Output CSV'
    )

    args = parser.parse_args()

    print("Re-categorizing computational tools...")
    print()

    stats = recategorize_computational_tools(
        Path(args.input),
        Path(args.output)
    )

    print("✓ Re-categorization complete:")
    print(f"  Total publications: {stats['total_publications']}")
    print(f"  Publications updated: {stats['recategorized_count']}")
    print()
    print("  Changes:")
    print(f"    Novel → Existing: {stats['novel_to_existing']} (known tools)")
    print(f"    Filtered out: {stats['filtered_instruments']} (lab instruments)")
    print(f"    Kept as novel: {stats['truly_novel_kept']} (in title or strong indicators)")
    print()
    print(f"  Saved to: {args.output}")
