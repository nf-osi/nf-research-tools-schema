#!/usr/bin/env python3
"""
Quick test of clinical assessment tool extraction on specific PMIDs.
"""

import json
import sys
from pathlib import Path
from extract_new_tool_types import extract_all_new_tool_types

def test_clinical_pmid(pmid: str):
    """Test extraction on a single PMID."""
    # Clean PMID
    clean_pmid = pmid.replace('PMID:', '')

    # Find cached file
    cache_file = Path(__file__).parent.parent.parent / 'tool_reviews' / 'publication_cache' / f'{clean_pmid}_text.json'

    if not cache_file.exists():
        print(f"❌ {pmid}: Not cached")
        return

    # Load paper
    try:
        with open(cache_file) as f:
            paper = json.load(f)
    except Exception as e:
        print(f"❌ {pmid}: Error loading: {e}")
        return

    # Extract text
    text = ''
    sections = []
    if paper.get('abstract'):
        text += paper['abstract'] + '\n\n'
        sections.append('abstract')
    if paper.get('methods'):
        text += paper['methods']
        sections.append('methods')

    if not text:
        print(f"⚠️  {pmid}: No text available")
        return

    print(f"\n{'='*80}")
    print(f"{pmid}")
    print(f"{'='*80}")
    print(f"Sections: {', '.join(sections)}")
    print(f"Text length: {len(text):,} chars\n")

    # Extract tools
    results = extract_all_new_tool_types(text)

    # Print results
    total_tools = sum(len(tools) for tools in results.values())

    if total_tools == 0:
        print("❌ No tools found\n")
        return

    for tool_type, tools in results.items():
        if tools:
            print(f"{tool_type.upper().replace('_', ' ')}: {len(tools)} found")
            for tool in tools:
                context_snippet = tool.get('context', '')[:80].replace('\n', ' ')
                print(f"  ✓ {tool['name']}")
                print(f"    Confidence: {tool['confidence']}")
                print(f"    Context: ...{context_snippet}...")
            print()

    print(f"✅ Total: {total_tools} tools found\n")


if __name__ == '__main__':
    test_pmids = [
        'PMID:40529476',  # Cached clinical paper
        'PMID:40585258',  # From our previous test (had clinical tools)
        'PMID:41001496',  # From previous test (had PROMIS)
    ]

    print("="*80)
    print("CLINICAL ASSESSMENT TOOL EXTRACTION TEST")
    print("="*80)

    for pmid in test_pmids:
        test_clinical_pmid(pmid)
