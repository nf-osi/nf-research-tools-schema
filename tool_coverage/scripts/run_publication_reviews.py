#!/usr/bin/env python3
"""
Run Anthropic API validation reviews for mined tools from publications.
Filters false positives and generates validated submission CSVs.
"""

import pandas as pd
import json
import yaml
import re
import sys
from pathlib import Path
from datetime import datetime
import os
import argparse
import anthropic
import synapseclient
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# Configuration
RECIPE_PATH = 'tool_coverage/scripts/recipes/publication_tool_review.yaml'
REVIEW_OUTPUT_DIR = 'tool_reviews'
MINING_RESULTS_FILE = 'processed_publications.csv'
ANTHROPIC_MODEL = 'claude-sonnet-4-20250514'

# Module-level cache for recipe content (loaded once)
_recipe_system_prompt = None
_recipe_task_instructions = None

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

def _load_recipe():
    """Load recipe YAML once and cache system prompt + task instructions."""
    global _recipe_system_prompt, _recipe_task_instructions
    if _recipe_system_prompt is not None:
        return

    recipe_path = Path(RECIPE_PATH)
    with open(recipe_path) as f:
        recipe = yaml.safe_load(f)

    _recipe_system_prompt = recipe.get('instructions', '').strip()

    full_prompt = recipe.get('prompt', '')
    # Drop step 1 (file reading) — we embed content directly in the message.
    # Task instructions start at "2. For each mined tool".
    lines = full_prompt.split('\n')
    start = next(
        (i for i, l in enumerate(lines) if l.strip().startswith('2. For each mined tool')),
        0
    )
    # Also drop the final "9. Create a YAML file..." step — we handle file writing in Python.
    end = next(
        (i for i, l in enumerate(lines) if l.strip().startswith('9. Create a YAML file')),
        len(lines)
    )
    _recipe_task_instructions = '\n'.join(lines[start:end]).strip()


def _format_mined_tools(tools_list):
    """Format mined tools list for embedding in the prompt."""
    if not tools_list:
        return '(none — scan the full text for potentially missed tools)'
    lines = []
    for i, t in enumerate(tools_list, 1):
        lines.append(f"  {i}. {t['toolName']} (type: {t['toolType']})")
        if t.get('contextSnippet'):
            lines.append(f"     Context: ...{t['contextSnippet'][:200]}...")
        if t.get('minedFrom'):
            lines.append(f"     Found in: {t['minedFrom']}")
    return '\n'.join(lines)


def build_review_prompt(input_data):
    """Return (system_prompt, user_message) for the Anthropic API call."""
    _load_recipe()

    meta = input_data['publicationMetadata']
    pmid = meta['pmid']
    doi = meta.get('doi', '') or ''

    def section(label, text):
        return f"**{label}:**\n{text.strip() if text and text.strip() else '(not available)'}"

    tools_text = _format_mined_tools(input_data.get('minedTools', []))

    # Extract the YAML output template from the recipe (between the ``` fences)
    recipe_path = Path(RECIPE_PATH)
    with open(recipe_path) as f:
        raw = f.read()
    yaml_template_match = re.search(r'(```yaml.*?```)', raw, re.DOTALL)
    yaml_template = yaml_template_match.group(1) if yaml_template_match else ''
    # Substitute template variables
    yaml_template = yaml_template.replace('{{ pmid }}', pmid).replace('{{ doi }}', doi)

    user_message = f"""Review publication {pmid} for NF research tool validation.

**PUBLICATION METADATA:**
- PMID: {pmid}
- Title: {meta.get('title', '')}
- DOI: {doi}
- Journal: {meta.get('journal', '')}
- Year: {meta.get('year', '')}
- Query Type: {meta.get('queryType', 'unknown')}
- Has Abstract: {input_data.get('hasAbstract', False)}
- Has Methods Section: {input_data.get('hasMethodsSection', False)}
- Has Introduction: {input_data.get('hasIntroduction', False)}
- Has Results: {input_data.get('hasResults', False)}
- Has Discussion: {input_data.get('hasDiscussion', False)}

{section('ABSTRACT', input_data.get('abstractText', ''))}

{section('METHODS', input_data.get('methodsText', ''))}

{section('INTRODUCTION', input_data.get('introductionText', ''))}

{section('RESULTS', input_data.get('resultsText', ''))}

{section('DISCUSSION', input_data.get('discussionText', ''))}

**MINED TOOLS ({len(input_data.get('minedTools', []))} total):**
{tools_text}

---
Using the publication data above, perform the following:

{_recipe_task_instructions}

9. Output ONLY the YAML content below (no explanation before or after). Use this exact structure:

{yaml_template}
"""
    return _recipe_system_prompt, user_message


def extract_yaml_from_response(text):
    """Extract YAML content from Claude's response text."""
    # Try ```yaml ... ``` block
    match = re.search(r'```yaml\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try plain ``` ... ``` block whose content starts with publicationMetadata:
    match = re.search(r'```\s*\n(publicationMetadata:.*?)\n```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Bare YAML starting at publicationMetadata:
    match = re.search(r'(publicationMetadata:.*)', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


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

def sanitize_pmid_for_filename(pmid: str) -> str:
    """
    Sanitize PMID for use in filenames by removing invalid characters.

    GitHub Actions artifacts don't allow: " : < > | * ? \r \n

    Args:
        pmid: Publication PMID (may include 'PMID:' prefix, may be int or str)

    Returns:
        Sanitized PMID (numeric only)
    """
    # Convert to string if needed (some PMIDs come as integers from Synapse)
    pmid = str(pmid)
    # Remove 'PMID:' prefix if present
    clean_pmid = pmid.replace('PMID:', '').strip()
    # Remove any other invalid characters (keep only alphanumeric and underscore)
    clean_pmid = ''.join(c for c in clean_pmid if c.isalnum() or c == '_')
    return clean_pmid

def load_cached_text(pmid, cache_dir='tool_reviews/publication_cache'):
    """
    Load cached publication text if available.

    Args:
        pmid: Publication PMID
        cache_dir: Cache directory

    Returns:
        Dict with cached text, or None if not found
    """
    clean_pmid = sanitize_pmid_for_filename(pmid)
    cache_file = Path(cache_dir) / f'{clean_pmid}_text.json'

    if cache_file.exists():
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def prepare_input_data(pub_row, cached):
    """Build input data dict for the API review from a DataFrame row and cached text.

    Args:
        pub_row: DataFrame row with publication and mining data
        cached: Dict from load_cached_text() — must not be None

    Returns:
        Dict with all publication text and mined tools
    """
    pmid = pub_row['pmid']

    abstract_text = cached.get('abstract', '')
    methods_text = cached.get('methods', '')
    intro_text = cached.get('introduction', '')
    results_text = cached.get('results', '')
    discussion_text = cached.get('discussion', '')

    # Parse mined tools from JSON columns (handle NaN values)
    novel_tools_raw = pub_row.get('novel_tools', '{}')
    tool_metadata_raw = pub_row.get('tool_metadata', '{}')
    tool_sources_raw = pub_row.get('tool_sources', '{}')

    if pd.isna(novel_tools_raw):
        novel_tools_raw = '{}'
    if pd.isna(tool_metadata_raw):
        tool_metadata_raw = '{}'
    if pd.isna(tool_sources_raw):
        tool_sources_raw = '{}'

    novel_tools = json.loads(novel_tools_raw)
    tool_metadata = json.loads(tool_metadata_raw)
    tool_sources = json.loads(tool_sources_raw)

    tools_list = []
    for tool_type in [
        'antibodies', 'cell_lines', 'animal_models', 'genetic_reagents',
        'computational_tools', 'advanced_cellular_models',
        'patient_derived_models', 'clinical_assessment_tools'
    ]:
        for tool_name in novel_tools.get(tool_type, []):
            tool_key = f"{tool_type}:{tool_name}"
            metadata = tool_metadata.get(tool_key, {})
            tools_list.append({
                'toolName': tool_name,
                'toolType': tool_type.rstrip('s'),
                'minedFrom': tool_sources.get(tool_key, []),
                'contextSnippet': metadata.get('context_snippet', '')
            })

    return {
        'publicationMetadata': {
            'pmid': pmid,
            'doi': pub_row.get('doi', ''),
            'title': pub_row.get('title', pub_row.get('publicationTitle', '')),
            'journal': pub_row.get('journal', ''),
            'year': pub_row.get('year', ''),
            'queryType': pub_row.get('query_type', 'unknown'),
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
    }

# Thread-safe print lock
print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with print_lock:
        print(*args, **kwargs)


def run_direct_review(pmid, input_data, results_dir, client, max_retries=3):
    """Run a single publication review via direct Anthropic API call.

    Replaces Goose: one API call instead of a multi-turn agent session.
    Typical latency: 20-60s vs 3-8 minutes with Goose.
    """
    safe_print(f"\n{'='*80}")
    safe_print(f"Reviewing {pmid}")
    safe_print(f"{'='*80}")

    clean_pmid = sanitize_pmid_for_filename(pmid)
    yaml_file = Path(results_dir).resolve() / f'{clean_pmid}_tool_review.yaml'

    system_prompt, user_message = build_review_prompt(input_data)

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                safe_print(f"Retry attempt {attempt + 1}/{max_retries}...")

            message = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8192,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )

            response_text = message.content[0].text
            safe_print(f"  Response: {len(response_text)} chars, "
                       f"~{message.usage.input_tokens}in/{message.usage.output_tokens}out tokens")

            yaml_text = extract_yaml_from_response(response_text)
            if not yaml_text:
                safe_print(f"⚠️  No YAML found in response")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

            # Validate structure
            try:
                data = yaml.safe_load(yaml_text)
                if not isinstance(data, dict) or 'publicationMetadata' not in data:
                    safe_print(f"⚠️  Invalid YAML structure (missing publicationMetadata)")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
            except yaml.YAMLError as e:
                safe_print(f"⚠️  YAML parse error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

            yaml_file.write_text(yaml_text, encoding='utf-8')
            safe_print(f"✅ Review completed: {yaml_file}")
            return yaml_file

        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)
            safe_print(f"⚠️  Rate limit — waiting {wait}s before retry...")
            time.sleep(wait)
        except anthropic.APIError as e:
            safe_print(f"❌ API error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            safe_print(f"❌ Error: {e}")
            return None

    return None

def process_single_publication(row, idx, total_pubs, results_dir, client, force_rereviews):
    """
    Process a single publication via direct Anthropic API call (for parallel execution).

    Returns:
        tuple: (pmid, status, result) where status is one of:
               'skipped', 'skipped_abstract_only', 'skipped_no_cache', 'reviewed', 'failed'
    """
    pmid = row['pmid']
    current_num = idx + 1

    safe_print(f"\n📊 Progress: {current_num}/{total_pubs} ({current_num/total_pubs*100:.1f}%)")

    # Check if already reviewed
    clean_pmid = sanitize_pmid_for_filename(pmid)
    yaml_path = Path(results_dir) / f'{clean_pmid}_tool_review.yaml'
    if yaml_path.exists() and not force_rereviews:
        safe_print(f"⏭️  Skipping {pmid} (already reviewed)")
        return (pmid, 'skipped', None)
    elif yaml_path.exists() and force_rereviews:
        safe_print(f"🔄 Re-reviewing {pmid} (force flag set)")

    # Load cache — skip immediately if absent (no file → no review possible)
    cached = load_cached_text(pmid)
    if cached is None:
        safe_print(f"⏭️  Skipping {pmid} (no cache file - run Phase 1 first)")
        return (pmid, 'skipped_no_cache', None)

    # Skip abstract_only — no methods section means tool mining will find nothing
    if cached.get('cache_level') == 'abstract_only' and not force_rereviews:
        safe_print(f"⏭️  Skipping {pmid} (abstract_only cache - no methods for tool mining)")
        return (pmid, 'skipped_abstract_only', None)

    # Build input data and run direct API review
    input_data = prepare_input_data(row, cached)
    result = run_direct_review(pmid, input_data, results_dir, client)

    return (pmid, 'reviewed', result) if result else (pmid, 'failed', None)

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
        clean_pmid = sanitize_pmid_for_filename(pmid)
        yaml_path = Path(results_dir) / f'{clean_pmid}_tool_review.yaml'
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

        if tool_validations:
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
        '--pmids-file',
        type=str,
        help='File with one PMID per line to review (e.g., phase2_upgraded_pmids.txt)'
    )
    parser.add_argument(
        '--compile-only',
        action='store_true',
        help='Compile results from existing YAML files only'
    )
    parser.add_argument(
        '--skip-goose',
        action='store_true',
        help='Skip API reviews, only compile results from existing YAML files'
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
    parser.add_argument(
        '--max-reviews',
        type=int,
        default=None,
        help='Maximum number of Goose reviews to run in this invocation (caps queue after skips)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Publication Tool Validation with Anthropic API")
    print("=" * 80)

    # Setup directories
    review_dir, results_dir, inputs_dir = setup_directories()

    # Create shared Anthropic client (thread-safe, uses connection pooling)
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key and not args.skip_goose and not args.compile_only:
        print("❌ ANTHROPIC_API_KEY not set — cannot run reviews")
        sys.exit(1)
    anthropic_client = anthropic.Anthropic(api_key=api_key) if api_key else None

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
            mining_df = mining_df.drop_duplicates(subset=['pmid'], keep='first').reset_index(drop=True)
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

    if args.pmids_file:
        with open(args.pmids_file, 'r') as f:
            pmid_file_list = [line.strip() for line in f if line.strip()]
        mining_df = mining_df[mining_df['pmid'].isin(pmid_file_list)]
        print(f"\nFiltered to {len(mining_df)} publications from {args.pmids_file}")

    # Run goose reviews (unless skip or compile-only)
    if not args.skip_goose and not args.compile_only:
        # Apply --max-reviews cap: pre-filter out already-reviewed and no-cache publications,
        # then limit actual Goose calls to avoid exceeding the GitHub Actions timeout.
        if args.max_reviews is not None:
            results_path = Path(results_dir)
            cache_dir = Path('tool_reviews/publication_cache')
            eligible = []
            for _, row in mining_df.iterrows():
                pmid = row['pmid']
                clean_pmid = sanitize_pmid_for_filename(pmid)
                yaml_path = results_path / f'{clean_pmid}_tool_review.yaml'
                if yaml_path.exists() and not args.force_rereviews:
                    continue  # will be skipped anyway - don't count against limit
                cache_file = cache_dir / f"{clean_pmid.replace('PMID:', '')}_text.json"
                if not cache_file.exists():
                    continue  # no cache - will be skipped anyway
                eligible.append(pmid)
            if len(eligible) > args.max_reviews:
                cap_pmids = set(eligible[:args.max_reviews])
                # Keep rows that are either already-reviewed (fast skip) or in the cap
                def keep_row(row):
                    pmid = row['pmid']
                    clean_pmid = sanitize_pmid_for_filename(pmid)
                    yaml_path = results_path / f'{clean_pmid}_tool_review.yaml'
                    return yaml_path.exists() or pmid in cap_pmids
                mining_df = mining_df[mining_df.apply(keep_row, axis=1)]
                print(f"\n⚠️  Capped to {args.max_reviews} Goose reviews this run "
                      f"({len(eligible) - args.max_reviews} deferred to next run)")
            else:
                print(f"\n✅ {len(eligible)} publications need Goose review (within --max-reviews {args.max_reviews})")

        print(f"\n{'='*80}")
        print(f"Running Goose Reviews for {len(mining_df)} publications")
        if args.parallel_workers > 1:
            print(f"Using {args.parallel_workers} parallel workers")
        print(f"{'='*80}")

        total_pubs = len(mining_df)
        reviewed_count = 0
        skipped_count = 0
        skipped_abstract_only_count = 0
        skipped_no_cache_count = 0
        failed_count = 0

        # Use parallel processing if requested
        if args.parallel_workers > 1:
            with ThreadPoolExecutor(max_workers=args.parallel_workers) as executor:
                futures = {}
                for idx, row in mining_df.iterrows():
                    future = executor.submit(
                        process_single_publication,
                        row, idx, total_pubs, results_dir, anthropic_client, args.force_rereviews
                    )
                    futures[future] = row['pmid']

                for future in as_completed(futures):
                    pmid, status, result = future.result()
                    if status == 'reviewed':
                        reviewed_count += 1
                    elif status == 'skipped':
                        skipped_count += 1
                    elif status == 'skipped_abstract_only':
                        skipped_abstract_only_count += 1
                    elif status == 'skipped_no_cache':
                        skipped_no_cache_count += 1
                    elif status == 'failed':
                        failed_count += 1
        else:
            for idx, row in mining_df.iterrows():
                pmid, status, result = process_single_publication(
                    row, idx, total_pubs, results_dir, anthropic_client, args.force_rereviews
                )
                if status == 'reviewed':
                    reviewed_count += 1
                elif status == 'skipped':
                    skipped_count += 1
                elif status == 'skipped_abstract_only':
                    skipped_abstract_only_count += 1
                elif status == 'skipped_no_cache':
                    skipped_no_cache_count += 1
                elif status == 'failed':
                    failed_count += 1

        # Print final summary
        print(f"\n{'='*80}")
        print(f"Review Summary:")
        print(f"  ✅ Reviewed: {reviewed_count}")
        print(f"  ⏭️  Skipped (cached): {skipped_count}")
        if skipped_abstract_only_count > 0:
            print(f"  ⏭️  Skipped (abstract_only, no methods): {skipped_abstract_only_count}")
        if skipped_no_cache_count > 0:
            print(f"  ⏭️  Skipped (no cache file): {skipped_no_cache_count}")
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
