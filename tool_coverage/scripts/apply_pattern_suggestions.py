#!/usr/bin/env python3
"""
Apply AI-suggested patterns to mining configuration.

This script implements a hybrid approach to pattern improvement:
1. Automatically adds high-confidence patterns (>0.9) to mining_patterns.json
2. Generates a report for medium-confidence patterns (0.7-0.9) for human review

Usage:
    python apply_pattern_suggestions.py [--dry-run]
"""

import json
import pandas as pd
import os
import sys
from pathlib import Path
from datetime import datetime

# File paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CONFIG_DIR = PROJECT_ROOT / 'tool_coverage' / 'config'
PATTERNS_FILE = CONFIG_DIR / 'mining_patterns.json'
SUGGESTED_PATTERNS_CSV = PROJECT_ROOT / 'tool_coverage' / 'output' / 'suggested_patterns.csv'
REPORT_FILE = PROJECT_ROOT / 'PATTERN_IMPROVEMENTS.md'

# Confidence thresholds
AUTO_ADD_THRESHOLD = 0.9
MANUAL_REVIEW_THRESHOLD = 0.7


def load_mining_patterns():
    """Load existing mining patterns from JSON config."""
    if not PATTERNS_FILE.exists():
        print(f"❌ Mining patterns file not found: {PATTERNS_FILE}")
        sys.exit(1)

    with open(PATTERNS_FILE, 'r') as f:
        return json.load(f)


def load_suggested_patterns():
    """Load AI-suggested patterns from CSV."""
    if not SUGGESTED_PATTERNS_CSV.exists():
        print(f"ℹ️  No suggested patterns file found at {SUGGESTED_PATTERNS_CSV}")
        return pd.DataFrame()

    df = pd.read_csv(SUGGESTED_PATTERNS_CSV)

    # Validate required columns
    required_cols = ['patternType', 'pattern', 'reasoning', 'confidence']
    if not all(col in df.columns for col in required_cols):
        print(f"⚠️  Suggested patterns CSV missing required columns: {required_cols}")
        return pd.DataFrame()

    return df


def categorize_suggestions(df):
    """Categorize suggestions by confidence level."""
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    auto_add = df[df['confidence'] > AUTO_ADD_THRESHOLD].copy()
    manual_review = df[
        (df['confidence'] >= MANUAL_REVIEW_THRESHOLD) &
        (df['confidence'] <= AUTO_ADD_THRESHOLD)
    ].copy()

    return auto_add, manual_review


def map_pattern_type_to_section(pattern_type, tool_category=None):
    """
    Map pattern type to the appropriate section in mining_patterns.json.

    Args:
        pattern_type: "term", "context_phrase", or "naming_convention"
        tool_category: "antibodies", "cell_lines", "animal_models", "genetic_reagents"

    Returns:
        Tuple of (category, section_key) or None if unmappable
    """
    # Define mappings for each pattern type
    type_mappings = {
        'term': {
            'antibodies': 'vendor_indicators',
            'cell_lines': 'naming_conventions',
            'animal_models': 'strain_nomenclature',
            'genetic_reagents': 'vector_indicators'
        },
        'context_phrase': {
            'antibodies': 'context_phrases',
            'cell_lines': 'context_phrases',
            'animal_models': 'context_phrases',
            'genetic_reagents': 'context_phrases'
        },
        'naming_convention': {
            'antibodies': 'vendor_indicators',
            'cell_lines': 'naming_conventions',
            'animal_models': 'strain_nomenclature',
            'genetic_reagents': 'vector_indicators'
        }
    }

    if pattern_type not in type_mappings:
        return None

    if tool_category and tool_category in type_mappings[pattern_type]:
        section = type_mappings[pattern_type][tool_category]
        return (tool_category, section)

    return None


def apply_high_confidence_patterns(patterns_config, auto_add_df, dry_run=False):
    """Apply high-confidence patterns to the configuration."""
    additions = []

    for _, row in auto_add_df.iterrows():
        pattern_type = row['patternType']
        pattern = row['pattern']
        reasoning = row['reasoning']
        confidence = row['confidence']
        tool_category = row.get('toolCategory', '')

        # Map to configuration section
        mapping = map_pattern_type_to_section(pattern_type, tool_category)

        if not mapping:
            print(f"⚠️  Cannot map pattern type '{pattern_type}' for category '{tool_category}' - skipping")
            continue

        category, section = mapping

        # Check if pattern already exists
        if pattern in patterns_config['patterns'][category][section]:
            print(f"ℹ️  Pattern '{pattern}' already exists in {category}.{section} - skipping")
            continue

        # Add pattern
        if not dry_run:
            patterns_config['patterns'][category][section].append(pattern)

        # Track addition
        addition_record = {
            'category': category,
            'section': section,
            'pattern': pattern,
            'reasoning': reasoning,
            'confidence': confidence,
            'added_date': datetime.now().strftime('%Y-%m-%d')
        }
        additions.append(addition_record)

        print(f"✅ {'[DRY RUN] Would add' if dry_run else 'Added'} pattern to {category}.{section}: {pattern}")

    # Update ai_suggested_patterns section
    if additions and not dry_run:
        patterns_config['ai_suggested_patterns']['additions'].extend(additions)
        patterns_config['last_updated'] = datetime.now().strftime('%Y-%m-%d')

    return len(additions)


def generate_manual_review_report(manual_review_df, dry_run=False):
    """Generate markdown report for patterns requiring manual review."""
    if manual_review_df.empty:
        print("ℹ️  No medium-confidence patterns requiring manual review")
        return 0

    report_lines = [
        "# Pattern Improvement Suggestions - Manual Review Required",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "The following patterns were suggested by AI validation with confidence between "
        f"{MANUAL_REVIEW_THRESHOLD} and {AUTO_ADD_THRESHOLD}. Please review and manually "
        "add any patterns that seem useful.",
        ""
    ]

    # Group by tool category if available
    if 'toolCategory' in manual_review_df.columns:
        grouped = manual_review_df.groupby('toolCategory')
    else:
        grouped = [('Unknown', manual_review_df)]

    for category, group_df in grouped:
        report_lines.extend([
            f"## {category.replace('_', ' ').title()}",
            ""
        ])

        for _, row in group_df.iterrows():
            pattern_type = row['patternType']
            pattern = row['pattern']
            reasoning = row['reasoning']
            confidence = row['confidence']
            pmid = row.get('pmid', 'N/A')

            report_lines.extend([
                f"### Pattern: `{pattern}`",
                "",
                f"- **Type**: {pattern_type}",
                f"- **Confidence**: {confidence:.2f}",
                f"- **Source PMID**: {pmid}",
                f"- **Reasoning**: {reasoning}",
                "",
                "**Action**: Review and manually add to `tool_coverage/config/mining_patterns.json` if appropriate.",
                "",
                "---",
                ""
            ])

    report_content = '\n'.join(report_lines)

    if not dry_run:
        with open(REPORT_FILE, 'w') as f:
            f.write(report_content)
        print(f"📝 Generated manual review report: {REPORT_FILE}")
    else:
        print(f"📝 [DRY RUN] Would generate manual review report: {REPORT_FILE}")

    return len(manual_review_df)


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description='Apply AI-suggested patterns to mining configuration')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying files')
    args = parser.parse_args()

    print("=" * 80)
    print("PATTERN IMPROVEMENT APPLICATION")
    print("=" * 80)
    print()

    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no files will be modified")
        print()

    # Load data
    print("📂 Loading mining patterns configuration...")
    patterns_config = load_mining_patterns()

    print("📂 Loading AI-suggested patterns...")
    suggested_df = load_suggested_patterns()

    if suggested_df.empty:
        print("\n✅ No pattern suggestions to process")
        return 0

    print(f"   Found {len(suggested_df)} suggested patterns")
    print()

    # Categorize suggestions
    print("📊 Categorizing suggestions by confidence...")
    auto_add_df, manual_review_df = categorize_suggestions(suggested_df)

    print(f"   High confidence (>{AUTO_ADD_THRESHOLD}): {len(auto_add_df)} patterns")
    print(f"   Medium confidence ({MANUAL_REVIEW_THRESHOLD}-{AUTO_ADD_THRESHOLD}): {len(manual_review_df)} patterns")
    print(f"   Low confidence (<{MANUAL_REVIEW_THRESHOLD}): {len(suggested_df) - len(auto_add_df) - len(manual_review_df)} patterns (ignored)")
    print()

    # Apply high-confidence patterns
    print("🤖 Processing high-confidence patterns...")
    num_added = apply_high_confidence_patterns(patterns_config, auto_add_df, dry_run=args.dry_run)
    print()

    # Generate manual review report
    print("📝 Generating manual review report...")
    num_for_review = generate_manual_review_report(manual_review_df, dry_run=args.dry_run)
    print()

    # Save updated configuration
    if num_added > 0 and not args.dry_run:
        print(f"💾 Saving updated mining patterns to {PATTERNS_FILE}...")
        with open(PATTERNS_FILE, 'w') as f:
            json.dump(patterns_config, f, indent=2)
        print("   ✅ Configuration updated")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Automatically added: {num_added} patterns")
    print(f"📋 Requiring manual review: {num_for_review} patterns")

    if args.dry_run:
        print()
        print("🔍 This was a DRY RUN - no files were modified")
        print("   Run without --dry-run to apply changes")

    return 0


if __name__ == '__main__':
    sys.exit(main())
