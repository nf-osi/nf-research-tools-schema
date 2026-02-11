#!/usr/bin/env python3
"""
Test new tool type extraction on real cached publications.

This script:
1. Loads cached publication JSON files
2. Runs extraction on methods/abstract/introduction sections
3. Aggregates results by tool type
4. Reports extraction statistics
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from extract_new_tool_types import extract_all_new_tool_types


def load_publication(file_path):
    """Load a cached publication JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def extract_from_publication(pub_data):
    """Extract tools from all relevant sections of a publication."""
    pmid = pub_data.get('pmid', 'Unknown')

    # Combine relevant sections (prioritize methods, then abstract, then intro)
    sections = []
    if pub_data.get('methods'):
        sections.append(('methods', pub_data['methods']))
    if pub_data.get('abstract'):
        sections.append(('abstract', pub_data['abstract']))
    if pub_data.get('introduction'):
        sections.append(('introduction', pub_data['introduction']))

    all_results = {
        'computational_tools': [],
        'advanced_cellular_models': [],
        'patient_derived_models': [],
        'clinical_assessment_tools': []
    }

    for section_name, text in sections:
        if text and len(text) > 100:  # Only process substantive sections
            results = extract_all_new_tool_types(text)

            # Add section info to each result
            for tool_type, tools in results.items():
                for tool in tools:
                    tool['section'] = section_name
                    tool['pmid'] = pmid
                all_results[tool_type].extend(results[tool_type])

    # Deduplicate across sections (keep highest confidence)
    for tool_type in all_results:
        seen = {}
        for tool in all_results[tool_type]:
            name_lower = tool['name'].lower()
            if name_lower not in seen or tool['confidence'] > seen[name_lower]['confidence']:
                seen[name_lower] = tool
        all_results[tool_type] = list(seen.values())

    return all_results


def analyze_results(all_publications_results):
    """Analyze and summarize extraction results."""
    stats = {
        'total_publications': len(all_publications_results),
        'publications_with_new_tools': 0,
        'tools_by_type': defaultdict(int),
        'tools_by_confidence': defaultdict(int),
        'example_tools': defaultdict(list)
    }

    for pmid, results in all_publications_results.items():
        has_tools = False
        for tool_type, tools in results.items():
            if tools:
                has_tools = True
                stats['tools_by_type'][tool_type] += len(tools)

                # Track confidence distribution
                for tool in tools:
                    conf_bucket = f"{tool['confidence']:.1f}"
                    stats['tools_by_confidence'][conf_bucket] += 1

                    # Collect examples (max 5 per type)
                    if len(stats['example_tools'][tool_type]) < 5:
                        stats['example_tools'][tool_type].append({
                            'name': tool['name'],
                            'pmid': pmid,
                            'confidence': tool['confidence'],
                            'section': tool.get('section', 'unknown')
                        })

        if has_tools:
            stats['publications_with_new_tools'] += 1

    return stats


def print_report(stats, detailed_results):
    """Print a formatted analysis report."""
    print("=" * 80)
    print("REAL-WORLD EXTRACTION TEST RESULTS")
    print("=" * 80)
    print()

    print(f"Total Publications Analyzed: {stats['total_publications']}")
    print(f"Publications with New Tool Types: {stats['publications_with_new_tools']} "
          f"({stats['publications_with_new_tools']/stats['total_publications']*100:.1f}%)")
    print()

    print("Tools Found by Type:")
    print("-" * 80)
    total_tools = sum(stats['tools_by_type'].values())
    for tool_type, count in sorted(stats['tools_by_type'].items()):
        print(f"  {tool_type:35s}: {count:3d} tools")
    print(f"  {'TOTAL':35s}: {total_tools:3d} tools")
    print()

    print("Confidence Score Distribution:")
    print("-" * 80)
    for conf, count in sorted(stats['tools_by_confidence'].items()):
        bar = "█" * int(count / 2)
        print(f"  {conf}: {bar} ({count})")
    print()

    print("Example Extractions by Type:")
    print("-" * 80)
    for tool_type in ['computational_tools', 'advanced_cellular_models',
                      'patient_derived_models', 'clinical_assessment_tools']:
        if stats['example_tools'][tool_type]:
            print(f"\n{tool_type.upper().replace('_', ' ')}:")
            for example in stats['example_tools'][tool_type]:
                print(f"  • {example['name']} (PMID:{example['pmid']}, "
                      f"conf={example['confidence']:.2f}, {example['section']})")
    print()

    print("Publications with Most Tools Found:")
    print("-" * 80)
    # Count tools per publication
    pub_tool_counts = []
    for pmid, results in detailed_results.items():
        total = sum(len(tools) for tools in results.values())
        if total > 0:
            pub_tool_counts.append((pmid, total, results))

    # Show top 10
    pub_tool_counts.sort(key=lambda x: x[1], reverse=True)
    for pmid, count, results in pub_tool_counts[:10]:
        breakdown = ", ".join(f"{k.replace('_', ' ')}: {len(v)}"
                             for k, v in results.items() if v)
        print(f"  PMID:{pmid}: {count} tools ({breakdown})")
    print()

    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


def main(sample_size=20):
    """Run extraction test on sample of cached publications."""
    # Cache is in tool_reviews directory, not tool_coverage
    cache_dir = Path(__file__).parent.parent.parent / 'tool_reviews' / 'publication_cache'

    if not cache_dir.exists():
        print(f"ERROR: Publication cache directory not found: {cache_dir}")
        return 1

    # Get all JSON files
    json_files = list(cache_dir.glob('*_text.json'))

    if not json_files:
        print(f"ERROR: No JSON files found in {cache_dir}")
        return 1

    print(f"Found {len(json_files)} cached publications")
    print(f"Testing on sample of {min(sample_size, len(json_files))} publications...")
    print()

    # Process sample
    sample_files = json_files[:sample_size] if sample_size < len(json_files) else json_files
    all_results = {}

    for i, file_path in enumerate(sample_files, 1):
        try:
            pub_data = load_publication(file_path)
            pmid = pub_data.get('pmid', file_path.stem.replace('_text', ''))

            print(f"[{i}/{len(sample_files)}] Processing PMID:{pmid}...", end='\r')

            results = extract_from_publication(pub_data)
            all_results[pmid] = results

        except Exception as e:
            print(f"\nWARNING: Error processing {file_path}: {e}")
            continue

    print()  # Clear progress line
    print()

    # Analyze results
    stats = analyze_results(all_results)

    # Print report
    print_report(stats, all_results)

    # Save detailed results
    output_file = Path(__file__).parent.parent / 'outputs' / 'real_world_extraction_results.json'
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\nDetailed results saved to: {output_file}")

    return 0


if __name__ == '__main__':
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    sys.exit(main(sample_size))
