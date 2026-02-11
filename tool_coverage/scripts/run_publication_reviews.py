#!/usr/bin/env python3
"""
Run goose AI validation reviews for mined tools from publications.
Filters false positives and generates validated submission CSVs.
"""

import pandas as pd
import json
import yaml
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import os
import argparse
import synapseclient
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configuration
RECIPE_PATH = 'tool_coverage/scripts/recipes/publication_tool_review.yaml'
REVIEW_OUTPUT_DIR = 'tool_reviews'
MINING_RESULTS_FILE = 'processed_publications.csv'

def setup_directories():
    """Create output directories."""
    review_dir = Path(REVIEW_OUTPUT_DIR)
    results_dir = review_dir / 'results'
    inputs_dir = review_dir / 'inputs'

    review_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)

    print(f"Created directories: {review_dir}, {results_dir}, {inputs_dir}")
    return str(review_dir), str(results_dir), str(inputs_dir)

def load_mining_results(mining_file):
    """Load mining results CSV."""
    try:
        df = pd.read_csv(mining_file)
        print(f"Loaded {len(df)} publications from {mining_file}")
        return df
    except Exception as e:
        print(f"Error loading mining results: {e}")
        return None


def fetch_unlinked_publications(syn):
    """
    Fetch publications from Synapse that should be reviewed for potential tool links:
    1. Publications in NF portal (syn16857542) not yet in tools publications (syn26486839)
    2. Publications in tools publications (syn26486839) not linked to tools in usage (syn26486841) or development (syn26486807)

    Args:
        syn: Synapse client (no auth needed - tables are open access)

    Returns:
        DataFrame with unlinked publications (pmid, title, doi, source)
    """
    print("\n" + "=" * 80)
    print("Fetching candidate publications from Synapse")
    print("=" * 80)

    all_unlinked = []

    try:
        # Part 1: NF portal publications not in tools publications
        print("\n[1] Checking NF portal publications (syn16857542) not in tools publications (syn26486839)...")

        portal_query = syn.tableQuery("SELECT pmid, title, doi FROM syn16857542")
        portal_df = portal_query.asDataFrame()
        print(f"  Found {len(portal_df)} publications in NF portal")

        tools_pubs_query = syn.tableQuery("SELECT pmid FROM syn26486839")
        tools_pubs_df = tools_pubs_query.asDataFrame()
        tools_pmids = set(tools_pubs_df['pmid'].dropna().tolist())
        print(f"  Found {len(tools_pmids)} publications already in tools table")

        # Find portal pubs not in tools table
        portal_not_in_tools = portal_df[~portal_df['pmid'].isin(tools_pmids)].copy()
        portal_not_in_tools['source'] = 'nf_portal_not_in_tools'

        print(f"  ✅ Found {len(portal_not_in_tools)} NF portal publications not in tools table")

        if len(portal_not_in_tools) > 0:
            all_unlinked.append(portal_not_in_tools[['pmid', 'title', 'doi', 'source']])
            print(f"\n  Sample:")
            for idx, row in portal_not_in_tools.head(3).iterrows():
                pmid = row['pmid']
                title = row.get('title', 'N/A')
                print(f"    - {pmid}: {title[:70]}...")

    except Exception as e:
        print(f"  ⚠️  Error fetching NF portal publications: {e}")

    try:
        # Part 2: Tools publications not linked to any tools
        print("\n[2] Checking tools publications (syn26486839) not linked to usage or development...")

        # Fetch publications with usage links
        usage_query = syn.tableQuery("SELECT DISTINCT publicationId FROM syn26486841")
        usage_df = usage_query.asDataFrame()
        usage_pub_ids = set(usage_df['publicationId'].dropna().tolist())
        print(f"  Found {len(usage_pub_ids)} publications with usage links")

        # Fetch publications with development links
        dev_query = syn.tableQuery("SELECT DISTINCT publicationId FROM syn26486807")
        dev_df = dev_query.asDataFrame()
        dev_pub_ids = set(dev_df['publicationId'].dropna().tolist())
        print(f"  Found {len(dev_pub_ids)} publications with development links")

        # Combine all linked publication IDs
        linked_pub_ids = usage_pub_ids | dev_pub_ids
        print(f"  Total unique publications with tool links: {len(linked_pub_ids)}")

        # Get all tools publications with publicationId
        # Note: publicationId column contains the row IDs used in usage/development tables
        pubs_query_with_id = syn.tableQuery("SELECT publicationId, pmid, publicationTitle, doi FROM syn26486839")
        pubs_with_id_df = pubs_query_with_id.asDataFrame()

        # Filter to unlinked (where publicationId not in linked_pub_ids)
        tools_pubs_unlinked = pubs_with_id_df[~pubs_with_id_df['publicationId'].isin(linked_pub_ids)].copy()
        tools_pubs_unlinked['source'] = 'tools_table_unlinked'

        # Rename publicationTitle to title for consistency
        tools_pubs_unlinked = tools_pubs_unlinked.rename(columns={'publicationTitle': 'title'})

        print(f"  ✅ Found {len(tools_pubs_unlinked)} tools publications without tool links")

        if len(tools_pubs_unlinked) > 0:
            all_unlinked.append(tools_pubs_unlinked[['pmid', 'title', 'doi', 'source']])
            print(f"\n  Sample:")
            for idx, row in tools_pubs_unlinked.head(3).iterrows():
                pmid = row['pmid']
                title = row.get('title', 'N/A')
                print(f"    - {pmid}: {title[:70]}...")

    except Exception as e:
        print(f"  ⚠️  Error fetching unlinked tools publications: {e}")

    # Combine all unlinked publications
    if all_unlinked:
        combined_df = pd.concat(all_unlinked, ignore_index=True)

        # Remove duplicates (some might be in both lists)
        combined_df = combined_df.drop_duplicates(subset=['pmid'])

        print(f"\n{'='*80}")
        print(f"✅ Total unique candidate publications: {len(combined_df)}")
        print(f"{'='*80}")

        return combined_df
    else:
        print("\n✅ No candidate publications found")
        return pd.DataFrame(columns=['pmid', 'title', 'doi', 'source'])

def load_cached_text(pmid, cache_dir='tool_reviews/publication_cache'):
    """
    Load cached publication text if available.

    Args:
        pmid: Publication PMID
        cache_dir: Cache directory

    Returns:
        Dict with cached text, or None if not found
    """
    cache_file = Path(cache_dir) / f'{pmid}_text.json'

    if cache_file.exists():
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def prepare_goose_input(pub_row, inputs_dir):
    """Prepare input JSON file for goose review.

    Args:
        pub_row: DataFrame row with publication and mining data
        inputs_dir: Directory to save input files

    Returns:
        Path to input JSON file
    """
    pmid = pub_row['pmid']

    # Try to load from cache first
    cached = load_cached_text(pmid)

    if cached:
        print(f"  ✅ Using cached text (skipping API calls)")
        abstract_text = cached['abstract']
        methods_text = cached['methods']
        intro_text = cached['introduction']
        # Load Results and Discussion sections (with backwards compatibility)
        results_text = cached.get('results', '')
        discussion_text = cached.get('discussion', '')
    else:
        # Fall back to fetching (backwards compatibility)
        # Import mining functions to fetch text
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from fetch_fulltext_and_mine import (
            fetch_pubmed_abstract,
            fetch_pmc_fulltext,
            extract_methods_section,
            extract_introduction_section,
            extract_results_section,
            extract_discussion_section
        )

        # Fetch abstract from PubMed
        print(f"  Fetching abstract from PubMed...")
        abstract_text = fetch_pubmed_abstract(pmid)

        # Fetch full text from PMC
        print(f"  Fetching full text from PMC...")
        fulltext_xml = fetch_pmc_fulltext(pmid)
        methods_text = ""
        intro_text = ""
        results_text = ""
        discussion_text = ""

        if fulltext_xml:
            print(f"  Extracting sections from full text...")
            methods_text = extract_methods_section(fulltext_xml)
            intro_text = extract_introduction_section(fulltext_xml)
            results_text = extract_results_section(fulltext_xml)
            discussion_text = extract_discussion_section(fulltext_xml)

    # Parse mined tools from JSON columns
    novel_tools = json.loads(pub_row.get('novel_tools', '{}'))
    tool_metadata = json.loads(pub_row.get('tool_metadata', '{}'))
    tool_sources = json.loads(pub_row.get('tool_sources', '{}'))

    # Prepare tool list with context
    tools_list = []
    for tool_type in ['antibodies', 'cell_lines', 'animal_models', 'genetic_reagents']:
        tool_names = novel_tools.get(tool_type, [])
        for tool_name in tool_names:
            tool_key = f"{tool_type}:{tool_name}"
            metadata = tool_metadata.get(tool_key, {})
            sources = tool_sources.get(tool_key, [])

            tools_list.append({
                'toolName': tool_name,
                'toolType': tool_type.rstrip('s'),  # Remove plural
                'minedFrom': sources,
                'metadata': metadata,
                'contextSnippet': metadata.get('context_snippet', '')
            })

    # Prepare input data (handle both mined and unlinked publications)
    input_data = {
        'publicationMetadata': {
            'pmid': pmid,
            'doi': pub_row.get('doi', ''),
            'title': pub_row.get('title', pub_row.get('publicationTitle', '')),
            'journal': pub_row.get('journal', ''),
            'year': pub_row.get('year', ''),
            'fundingAgency': pub_row.get('fundingAgency', '')
        },
        'abstractText': abstract_text,
        'methodsText': methods_text,
        'introductionText': intro_text,
        'resultsText': results_text,
        'discussionText': discussion_text,
        'hasAbstract': bool(abstract_text),
        'hasMethodsSection': bool(methods_text),
        'hasIntroduction': bool(intro_text),
        'hasResults': bool(results_text),
        'hasDiscussion': bool(discussion_text),
        'minedTools': tools_list,
        'miningMetrics': {
            'totalTools': len(tools_list),
            'toolsByType': {
                'antibodies': len(novel_tools.get('antibodies', [])),
                'cellLines': len(novel_tools.get('cell_lines', [])),
                'animalModels': len(novel_tools.get('animal_models', [])),
                'geneticReagents': len(novel_tools.get('genetic_reagents', []))
            }
        }
    }

    # Save to JSON file
    input_file = Path(inputs_dir) / f"{pmid}_input.json"
    with open(input_file, 'w') as f:
        json.dump(input_data, f, indent=2)

    print(f"  Created input file: {input_file}")
    return str(input_file.resolve())

# Thread-safe print lock
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with print_lock:
        print(*args, **kwargs)

def run_goose_review(pmid, input_file, results_dir):
    """Run goose tool validation for a single publication."""
    safe_print(f"\n{'='*80}")
    safe_print(f"Reviewing {pmid}")
    safe_print(f"Input: {input_file}")
    safe_print(f"{'='*80}")

    # Change to results directory (thread-safe since each uses different files)
    original_dir = os.getcwd()
    # Don't change directory - use absolute paths instead
    results_path = Path(results_dir).resolve()

    try:
        # Build goose command
        recipe_path = Path(RECIPE_PATH).resolve()

        cmd = [
            'goose', 'run',
            '--recipe', str(recipe_path),
            '--params', f'pmid={pmid}',
            '--params', f'inputFile={input_file}',
            '--no-session'  # Don't create session files for automated runs
        ]

        safe_print(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=str(results_path)  # Run in results directory
        )

        safe_print(result.stdout)

        if result.returncode != 0:
            safe_print(f"❌ Error (exit code {result.returncode}):")
            safe_print(result.stderr)
            return None

        # Look for generated YAML file
        yaml_file = results_path / f'{pmid}_tool_review.yaml'
        if yaml_file.exists():
            safe_print(f"✅ Review completed: {yaml_file}")
            return yaml_file
        else:
            safe_print(f"⚠️  No YAML file generated")
            return None

    except subprocess.TimeoutExpired:
        safe_print(f"❌ Timeout after 10 minutes")
        return None
    except Exception as e:
        safe_print(f"❌ Error: {e}")
        return None

def process_single_publication(row, idx, total_pubs, results_dir, inputs_dir, force_rereviews):
    """
    Process a single publication (for parallel execution).

    Returns:
        tuple: (pmid, status, result) where status is 'skipped', 'reviewed', or 'failed'
    """
    pmid = row['pmid']
    current_num = idx + 1

    # Show progress
    safe_print(f"\n📊 Progress: {current_num}/{total_pubs} ({current_num/total_pubs*100:.1f}%)")

    # Check if already reviewed
    yaml_path = Path(results_dir) / f'{pmid}_tool_review.yaml'
    if yaml_path.exists() and not force_rereviews:
        safe_print(f"⏭️  Skipping {pmid} (already reviewed)")
        return (pmid, 'skipped', None)
    elif yaml_path.exists() and force_rereviews:
        safe_print(f"🔄 Re-reviewing {pmid} (force flag set)")

    # Prepare input file
    input_file = prepare_goose_input(row, inputs_dir)

    # Run goose review
    result = run_goose_review(pmid, input_file, results_dir)

    if result:
        return (pmid, 'reviewed', result)
    else:
        return (pmid, 'failed', None)

def parse_review_yaml(yaml_path):
    """Parse goose review YAML file."""
    try:
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        return data
    except Exception as e:
        print(f"Error parsing {yaml_path}: {e}")
        return None

def compile_validation_results(mining_df, results_dir):
    """Compile validation results from YAML files."""
    print("\n" + "=" * 80)
    print("Compiling Validation Results")
    print("=" * 80)

    validation_results = []
    all_missed_tools = []
    all_suggested_patterns = []
    all_observations = []

    for _, row in mining_df.iterrows():
        pmid = row['pmid']
        doi = row.get('doi', '')

        # Check if YAML file exists
        yaml_path = Path(results_dir) / f'{pmid}_tool_review.yaml'
        if not yaml_path.exists():
            print(f"\nSkipping {pmid} (no review YAML found)")
            continue

        print(f"\nProcessing {pmid}...")

        # Load review data
        review_data = parse_review_yaml(yaml_path)
        if not review_data:
            continue

        # Extract validation results
        pub_meta = review_data.get('publicationMetadata', {})
        tool_validations = review_data.get('toolValidations', [])
        summary = review_data.get('summary', {})
        missed_tools = review_data.get('potentiallyMissedTools', [])
        suggested_patterns = review_data.get('suggestedPatterns', [])
        observations = review_data.get('observations', [])

        # Categorize tools by recommendation
        accepted_tools = []
        rejected_tools = []
        uncertain_tools = []

        for tool_val in tool_validations:
            tool_info = {
                'pmid': pmid,
                'toolName': tool_val.get('toolName'),
                'toolType': tool_val.get('toolType'),
                'verdict': tool_val.get('verdict'),
                'confidence': tool_val.get('confidence'),
                'recommendation': tool_val.get('recommendation'),
                'reasoning': tool_val.get('reasoning', '')
            }

            if tool_val.get('recommendation') == 'Keep':
                accepted_tools.append(tool_info)
            elif tool_val.get('recommendation') == 'Remove':
                rejected_tools.append(tool_info)
            else:  # Manual Review Required
                uncertain_tools.append(tool_info)

        # Collect missed tools
        for missed_tool in missed_tools:
            missed_tool['pmid'] = pmid
            all_missed_tools.append(missed_tool)

        # Collect suggested patterns
        for pattern in suggested_patterns:
            pattern['pmid'] = pmid
            all_suggested_patterns.append(pattern)

        # Collect observations
        for obs in observations:
            obs_info = {
                'pmid': pmid,
                'doi': doi if doi else obs.get('doi', ''),
                'resourceName': obs.get('resourceName'),
                'resourceType': obs.get('resourceType'),
                'observationType': obs.get('observationType'),
                'details': obs.get('details', ''),
                'foundIn': obs.get('foundIn', ''),
                'confidence': obs.get('confidence', 1.0)
            }
            all_observations.append(obs_info)

        validation_results.append({
            'pmid': pmid,
            'title': pub_meta.get('title', ''),
            'publicationType': pub_meta.get('publicationType', ''),
            'likelyContainsTools': pub_meta.get('likelyContainsTools', ''),
            'totalToolsMined': summary.get('totalToolsMined', 0),
            'toolsAccepted': summary.get('toolsAccepted', 0),
            'toolsRejected': summary.get('toolsRejected', 0),
            'toolsUncertain': summary.get('toolsUncertain', 0),
            'potentiallyMissedCount': summary.get('potentiallyMissedCount', 0),
            'newPatternsCount': summary.get('newPatternsCount', 0),
            'observationsExtracted': summary.get('observationsExtracted', 0),
            'acceptedTools': accepted_tools,
            'rejectedTools': rejected_tools,
            'uncertainTools': uncertain_tools,
            'missedTools': missed_tools,
            'suggestedPatterns': suggested_patterns,
            'overallAssessment': pub_meta.get('overallAssessment', ''),
            'majorIssues': summary.get('majorIssuesFound', ''),
            'recommendations': summary.get('recommendations', '')
        })

    print(f"\n✅ Compiled {len(validation_results)} publication reviews")
    print(f"   - Total potentially missed tools: {len(all_missed_tools)}")
    print(f"   - Total suggested patterns: {len(all_suggested_patterns)}")
    print(f"   - Total observations extracted: {len(all_observations)}")

    return validation_results, all_missed_tools, all_suggested_patterns, all_observations

def normalize_tool_type(tool_type):
    """Normalize tool type to match CSV file naming convention."""
    # Map various forms to canonical singular forms used in CSV filtering
    type_map = {
        'antibodie': 'antibody',  # Fix Goose typo
        'antibodies': 'antibody',
        'cell_line': 'cell_line',
        'cell_lines': 'cell_line',
        'animal_model': 'animal_model',
        'animal_models': 'animal_model',
        'genetic_reagent': 'genetic_reagent',
        'genetic_reagents': 'genetic_reagent'
    }
    return type_map.get(tool_type, tool_type)

def filter_submission_csvs(validation_results, output_dir='.'):
    """Filter SUBMIT_*.csv files to remove rejected tools."""
    print("\n" + "=" * 80)
    print("Filtering Submission CSVs")
    print("=" * 80)

    # Create a set of (pmid, toolName, toolType) tuples for tools to KEEP
    tools_to_keep = set()
    tools_to_remove = set()

    for result in validation_results:
        pmid = result['pmid']

        for tool in result['acceptedTools']:
            normalized_type = normalize_tool_type(tool['toolType'])
            tools_to_keep.add((pmid, tool['toolName'], normalized_type))

        for tool in result['rejectedTools']:
            normalized_type = normalize_tool_type(tool['toolType'])
            tools_to_remove.add((pmid, tool['toolName'], normalized_type))

    print(f"\nTools to keep: {len(tools_to_keep)}")
    print(f"Tools to remove: {len(tools_to_remove)}")

    # Find all SUBMIT_*.csv files
    submit_files = list(Path(output_dir).glob('SUBMIT_*.csv'))

    if not submit_files:
        print("⚠️  No SUBMIT_*.csv files found")
        return

    print(f"\nFound {len(submit_files)} SUBMIT files to filter:\n")

    for submit_file in submit_files:
        print(f"Processing {submit_file.name}...")

        try:
            df = pd.read_csv(submit_file)
            original_count = len(df)

            # Filter based on validation results
            # Need to match on PMID + tool name from tracking columns
            if '_pmid' in df.columns:
                # Create keep mask
                def should_keep_row(row):
                    pmid = row.get('_pmid', '')
                    # Try to extract tool name from different possible columns
                    tool_name = None
                    tool_type = None

                    # Determine tool type from file name
                    if 'antibodies' in submit_file.name:
                        tool_type = 'antibody'
                        tool_name = row.get('targetAntigen', '')
                    elif 'cell_lines' in submit_file.name:
                        tool_type = 'cell_line'
                        tool_name = row.get('_cellLineName', '')
                    elif 'animal_models' in submit_file.name:
                        tool_type = 'animal_model'
                        tool_name = row.get('name', '')
                    elif 'genetic_reagents' in submit_file.name:
                        tool_type = 'genetic_reagent'
                        tool_name = row.get('insertName', '')

                    if not tool_name or not pmid:
                        return True  # Keep if we can't determine (conservative)

                    # Check if this tool should be removed
                    if (pmid, tool_name, tool_type) in tools_to_remove:
                        return False

                    return True

                df_filtered = df[df.apply(should_keep_row, axis=1)]
                removed_count = original_count - len(df_filtered)

                # Save filtered version
                output_file = Path(output_dir) / f"VALIDATED_{submit_file.name}"
                df_filtered.to_csv(output_file, index=False)

                print(f"  ✅ Removed {removed_count} rows → {output_file.name}")
            else:
                print(f"  ⚠️  No _pmid column found, skipping")

        except Exception as e:
            print(f"  ❌ Error: {e}")

    print("\n" + "=" * 80)
    print("Filtering complete. Review VALIDATED_*.csv files.")
    print("=" * 80)

def main():
    """Main execution."""
    parser = argparse.ArgumentParser(
        description='Run goose AI validation on mined publication tools',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--mining-file',
        default=MINING_RESULTS_FILE,
        help=f'Mining results CSV file (default: {MINING_RESULTS_FILE})'
    )
    parser.add_argument(
        '--pmids',
        type=str,
        help='Comma-separated PMIDs to review (e.g., PMID:28078640,PMID:29415745)'
    )
    parser.add_argument(
        '--compile-only',
        action='store_true',
        help='Compile results from existing YAML files only'
    )
    parser.add_argument(
        '--skip-goose',
        action='store_true',
        help='Skip goose reviews, only filter CSVs from existing YAMLs'
    )
    parser.add_argument(
        '--force-rereviews',
        action='store_true',
        help='Force re-review of publications even if YAML files already exist'
    )
    parser.add_argument(
        '--parallel-workers',
        type=int,
        default=1,
        help='Number of parallel workers for AI validation (default: 1, recommended: 3-5)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Publication Tool Validation with Goose AI")
    print("=" * 80)

    # Setup directories
    review_dir, results_dir, inputs_dir = setup_directories()

    # Load mining results
    mining_df = load_mining_results(args.mining_file)
    if mining_df is None or len(mining_df) == 0:
        print("\n❌ Failed to load mining results")
        sys.exit(1)

    # Add candidate publications from Synapse (always enabled)
    print("\nFetching candidate publications from Synapse...")

    # Initialize Synapse client (no auth needed for open access tables)
    try:
        syn = synapseclient.Synapse()
        print("✅ Synapse client initialized (no auth needed - tables are open access)")
    except Exception as e:
        print(f"⚠️  Synapse client initialization failed: {e}")
        print("   Continuing with only mined publications...")
        syn = None

    if syn:
        candidate_df = fetch_unlinked_publications(syn)

        if len(candidate_df) > 0:
            # Add empty tool columns to match mining_df structure
            candidate_df['novel_tools'] = '{}'
            candidate_df['tool_metadata'] = '{}'
            candidate_df['tool_sources'] = '{}'
            candidate_df['fulltext_available'] = False

            # Append to mining_df
            original_count = len(mining_df)
            mining_df = pd.concat([mining_df, candidate_df], ignore_index=True)

            # Remove duplicates by pmid (keep first occurrence - mined takes precedence)
            before_dedup = len(mining_df)
            mining_df = mining_df.drop_duplicates(subset=['pmid'], keep='first')
            duplicates_removed = before_dedup - len(mining_df)

            added_count = len(mining_df) - original_count
            print(f"\n✅ Added {added_count} unique candidate publications to review queue")
            if duplicates_removed > 0:
                print(f"   ({duplicates_removed} duplicates removed)")
            print(f"   Total publications to review: {len(mining_df)}")
        else:
            print("\n✅ No additional candidate publications found")

    # Filter by specific PMIDs if requested
    if args.pmids:
        pmid_list = [p.strip() for p in args.pmids.split(',')]
        mining_df = mining_df[mining_df['pmid'].isin(pmid_list)]
        print(f"\nFiltered to {len(mining_df)} publications: {', '.join(pmid_list)}")

    # Run goose reviews (unless skip or compile-only)
    if not args.skip_goose and not args.compile_only:
        print(f"\n{'='*80}")
        print(f"Running Goose Reviews for {len(mining_df)} publications")
        if args.parallel_workers > 1:
            print(f"Using {args.parallel_workers} parallel workers")
        print(f"{'='*80}")

        total_pubs = len(mining_df)
        reviewed_count = 0
        skipped_count = 0
        failed_count = 0

        # Use parallel processing if requested
        if args.parallel_workers > 1:
            with ThreadPoolExecutor(max_workers=args.parallel_workers) as executor:
                # Submit all tasks
                futures = {}
                for idx, row in mining_df.iterrows():
                    future = executor.submit(
                        process_single_publication,
                        row, idx, total_pubs, results_dir, inputs_dir, args.force_rereviews
                    )
                    futures[future] = row['pmid']

                # Process results as they complete
                for future in as_completed(futures):
                    pmid, status, result = future.result()
                    if status == 'reviewed':
                        reviewed_count += 1
                    elif status == 'skipped':
                        skipped_count += 1
                    elif status == 'failed':
                        failed_count += 1
        else:
            # Sequential processing (original behavior)
            for idx, row in mining_df.iterrows():
                pmid, status, result = process_single_publication(
                    row, idx, total_pubs, results_dir, inputs_dir, args.force_rereviews
                )
                if status == 'reviewed':
                    reviewed_count += 1
                elif status == 'skipped':
                    skipped_count += 1
                elif status == 'failed':
                    failed_count += 1

        # Print final summary
        print(f"\n{'='*80}")
        print(f"Review Summary:")
        print(f"  ✅ Reviewed: {reviewed_count}")
        print(f"  ⏭️  Skipped (cached): {skipped_count}")
        if failed_count > 0:
            print(f"  ❌ Failed: {failed_count}")
        print(f"  📊 Total processed: {total_pubs}")
        print(f"{'='*80}")

    # Compile validation results
    validation_results, all_missed_tools, all_suggested_patterns, all_observations = compile_validation_results(mining_df, results_dir)

    # Save validation summary
    summary_file = Path(review_dir) / 'validation_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(validation_results, f, indent=2)
    print(f"\n✅ Validation summary saved: {summary_file}")

    # Create detailed report CSV
    report_rows = []
    for result in validation_results:
        report_rows.append({
            'pmid': result['pmid'],
            'title': result['title'],
            'publicationType': result['publicationType'],
            'likelyContainsTools': result['likelyContainsTools'],
            'totalMined': result['totalToolsMined'],
            'accepted': result['toolsAccepted'],
            'rejected': result['toolsRejected'],
            'uncertain': result['toolsUncertain'],
            'potentiallyMissed': result['potentiallyMissedCount'],
            'suggestedPatterns': result['newPatternsCount'],
            'observationsExtracted': result.get('observationsExtracted', 0),
            'majorIssues': result['majorIssues'],
            'recommendations': result['recommendations']
        })

    report_df = pd.DataFrame(report_rows)
    report_file = Path(review_dir) / 'validation_report.xlsx'
    report_df.to_excel(report_file, index=False)
    print(f"✅ Validation report saved: {report_file}")

    # Save missed tools report
    if all_missed_tools:
        missed_tools_df = pd.DataFrame(all_missed_tools)
        missed_tools_file = Path(review_dir) / 'potentially_missed_tools.csv'
        missed_tools_df.to_csv(missed_tools_file, index=False)
        print(f"✅ Potentially missed tools saved: {missed_tools_file}")
        print(f"   - {len(all_missed_tools)} tools that may have been missed")

    # Save suggested patterns report
    if all_suggested_patterns:
        patterns_df = pd.DataFrame(all_suggested_patterns)
        patterns_file = Path(review_dir) / 'suggested_patterns.csv'
        patterns_df.to_csv(patterns_file, index=False)
        print(f"✅ Suggested patterns saved: {patterns_file}")
        print(f"   - {len(all_suggested_patterns)} patterns to improve mining")

    # Save observations report
    if all_observations:
        observations_df = pd.DataFrame(all_observations)
        observations_file = Path(review_dir) / 'observations.csv'
        observations_df.to_csv(observations_file, index=False)
        print(f"✅ Observations saved: {observations_file}")
        print(f"   - {len(all_observations)} scientific observations extracted")

        # Print observation breakdown by type
        if 'observationType' in observations_df.columns:
            obs_counts = observations_df['observationType'].value_counts()
            print(f"   - Breakdown by type:")
            for obs_type, count in obs_counts.head(5).items():
                print(f"     • {obs_type}: {count}")
            if len(obs_counts) > 5:
                print(f"     • ... and {len(obs_counts) - 5} more types")

    # Filter SUBMIT_*.csv files
    if not args.compile_only:
        filter_submission_csvs(validation_results)

    print("\n" + "=" * 80)
    print("Validation Complete!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Review validation_report.xlsx for summary")
    print("  2. Check VALIDATED_*.csv files (rejected tools removed)")
    print("  3. Manually review 'uncertain' tools if any")
    print("  4. Review potentially_missed_tools.csv for tools that may need manual addition")
    print("  5. Review suggested_patterns.csv to improve future mining accuracy")
    print("  6. Review observations.csv for scientific observations extracted")
    print("  7. Run format_mining_for_submission.py to create SUBMIT files (includes observations)")
    print("  8. Manually verify SUBMIT_*.csv files before uploading to Synapse")
    print("=" * 80)

if __name__ == '__main__':
    main()
