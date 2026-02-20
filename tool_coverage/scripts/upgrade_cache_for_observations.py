#!/usr/bin/env python3
"""
Upgrade minimal caches to full caches for observation extraction.

Only upgrades caches for publications with:
1. High-confidence validated tools (verdict=Accept, confidence ≥0.8)
2. Sufficient metadata completeness (≥0.6)
3. Appropriate publication type (Lab Research, Clinical Study)

Fetches Results + Discussion sections from PMC for observation extraction.

Usage:
    python upgrade_cache_for_observations.py --reviews-dir tool_reviews/results
    python upgrade_cache_for_observations.py --dry-run  # Preview without upgrading
"""

import json
import yaml
import requests
import xml.etree.ElementTree as ET
import time
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def should_upgrade_cache(review_file: Path) -> tuple[bool, str, int]:
    """
    Determine if cache should be upgraded based on validation results.

    Returns:
        (should_upgrade, reason, num_tools)
    """
    try:
        with open(review_file) as f:
            review = yaml.safe_load(f)

        # Check for accepted tools with high confidence
        accepted_tools = [
            t for t in review.get('toolValidations', []) or []
            if t.get('verdict') == 'Accept' and t.get('confidence', 0) >= 0.8
        ]

        if len(accepted_tools) == 0:
            return False, "No high-confidence validated tools", 0

        # Check publication type if available (optional field in new YAML format)
        pub_type = review.get('publicationMetadata', {}).get('publicationType', '')
        skip_types = ['Review Article', 'Editorial', 'Letter', 'Comment', 'News']
        if pub_type in skip_types:
            return False, f"Publication type: {pub_type}", len(accepted_tools)

        # Check metadata completeness (if available)
        completeness_scores = [
            t.get('metadata', {}).get('_completenessScore', 0)
            for t in accepted_tools
            if '_completenessScore' in t.get('metadata', {})
        ]

        if completeness_scores:
            avg_completeness = sum(completeness_scores) / len(completeness_scores)
            if avg_completeness < 0.6:
                return False, f"Low completeness: {avg_completeness:.2f}", len(accepted_tools)

        return True, f"{len(accepted_tools)} high-quality tools validated", len(accepted_tools)

    except Exception as e:
        logger.error(f"Error analyzing {review_file.name}: {e}")
        return False, f"Error: {e}", 0


def fetch_pmc_full_sections(pmid: str) -> Optional[Dict[str, str]]:
    """
    Fetch Results and Discussion sections from PMC using official OAI-PMH API.

    Uses PMC OAI-PMH API as recommended by https://pmc.ncbi.nlm.nih.gov/tools/oai/

    Returns dict with 'introduction', 'results', 'discussion' keys, or None if fetch fails.
    """
    try:
        # Get PMC ID from PMID using elink
        eutils_base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        params = {
            'db': 'pmc',
            'id': pmid,
            'idtype': 'pmid'
        }

        response = requests.get(f"{eutils_base}elink.fcgi", params=params, timeout=10)
        if response.status_code != 200:
            return None

        # Parse XML to get PMC ID
        root = ET.fromstring(response.content)

        # CRITICAL: Only get the article itself, not citing articles!
        # We need to find the LinkSet with LinkName = "pubmed_pmc"
        pmc_id = None
        for linkset in root.findall('.//LinkSet'):
            linkname_elem = linkset.find('.//LinkName')
            if linkname_elem is not None and linkname_elem.text == 'pubmed_pmc':
                # This is the original article in PMC (not citing articles)
                link_ids = linkset.findall('.//Link/Id')
                if link_ids:
                    pmc_id = link_ids[0].text
                    break

        if not pmc_id:
            # Article not available in PMC (no full text)
            logger.debug(f"PMID:{pmid} not available in PMC (no full text)")
            return None

        # Fetch full text using PMC OAI-PMH API
        oai_url = (
            f"https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
            f"?verb=GetRecord"
            f"&identifier=oai:pubmedcentral.nih.gov:{pmc_id}"
            f"&metadataPrefix=pmc"  # Full text
        )

        response = requests.get(oai_url, timeout=30)
        if response.status_code != 200:
            return None

        # Parse XML (namespace-aware)
        root = ET.fromstring(response.content)

        sections = {
            'introduction': '',
            'results': '',
            'discussion': ''
        }

        # Section title mappings
        section_mappings = {
            'introduction': ['introduction', 'background'],
            'results': ['results', 'findings'],
            'discussion': ['discussion', 'conclusions', 'conclusion']
        }

        # Find all <sec> elements (works with or without namespaces)
        for sec in root.iter():
            if not sec.tag.endswith('sec'):
                continue

            # Find title element within this section
            title_elem = None
            for child in sec:
                if child.tag.endswith('title'):
                    title_elem = child
                    break

            if title_elem is not None and title_elem.text:
                section_title = title_elem.text.lower().strip()

                # Determine which section this is
                matched_section = None
                for section_key, title_variants in section_mappings.items():
                    if any(variant in section_title for variant in title_variants):
                        matched_section = section_key
                        break

                if matched_section:
                    # Extract all text from this section
                    text_parts = []
                    for elem in sec.iter():
                        if elem.text:
                            text_parts.append(elem.text)
                        if elem.tail:
                            text_parts.append(elem.tail)

                    sections[matched_section] = ' '.join(text_parts).strip()

        # Return only if we got at least results or discussion
        if sections['results'] or sections['discussion']:
            return sections

        return None

    except Exception as e:
        logger.debug(f"Could not fetch PMC sections for PMID:{pmid}: {e}")
        return None


def upgrade_cache_to_full(pmid: str, cache_dir: Path) -> Optional[Dict]:
    """
    Upgrade minimal cache to full cache by adding Results + Discussion.

    Returns updated cache data, or None if upgrade fails.
    """
    pmid_clean = pmid.replace('PMID:', '').strip()
    cache_file = cache_dir / f"{pmid_clean}_text.json"

    # Load existing minimal cache
    if not cache_file.exists():
        logger.warning(f"Cache file not found for PMID:{pmid_clean}")
        return None

    with open(cache_file) as f:
        cache = json.load(f)

    # Check if already upgraded
    current_level = cache.get('cache_level', 'unknown')
    if current_level == 'full':
        logger.info(f"  Already at full cache level")
        return cache

    if current_level == 'abstract_only':
        logger.warning(f"  Cannot upgrade abstract_only cache (no PMC full text)")
        return None

    # Fetch additional sections from PMC
    logger.info(f"  Fetching Results + Discussion from PMC...")
    full_sections = fetch_pmc_full_sections(pmid_clean)

    if not full_sections:
        logger.warning(f"  Failed to fetch full sections from PMC")
        return None

    # Update cache
    cache.update({
        'introduction': full_sections.get('introduction', ''),
        'results': full_sections.get('results', ''),
        'discussion': full_sections.get('discussion', ''),
        'cache_level': 'full',
        'upgrade_date': time.strftime('%Y-%m-%d %H:%M:%S')
    })

    # Save updated cache
    with open(cache_file, 'w') as f:
        json.dump(cache, f, indent=2)

    logger.info(f"  ✓ Upgraded to full cache "
                f"({len(full_sections.get('results', ''))} chars results, "
                f"{len(full_sections.get('discussion', ''))} chars discussion)")

    return cache


def main():
    parser = argparse.ArgumentParser(
        description='Upgrade minimal caches to full for observation extraction'
    )
    parser.add_argument('--reviews-dir', default='tool_reviews/results',
                       help='Directory containing Sonnet validation YAML files')
    parser.add_argument('--cache-dir', default='tool_reviews/publication_cache',
                       help='Directory containing cache files')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview which caches would be upgraded without actually upgrading')
    parser.add_argument('--force', action='store_true',
                       help='Force upgrade even if already at full level')

    args = parser.parse_args()

    reviews_dir = Path(args.reviews_dir)
    cache_dir = Path(args.cache_dir)

    if not reviews_dir.exists():
        logger.error(f"Reviews directory not found: {reviews_dir}")
        return 1

    if not cache_dir.exists():
        logger.error(f"Cache directory not found: {cache_dir}")
        return 1

    # Find all review YAML files
    review_files = list(reviews_dir.glob('*_tool_review.yaml'))
    logger.info(f"Analyzing {len(review_files)} review files...")
    logger.info("")

    # Analyze which caches should be upgraded
    upgrade_candidates = []
    skip_reasons = {
        'no_tools': [],
        'low_completeness': [],
        'review_article': [],
        'already_full': [],
        'abstract_only': []
    }

    for review_file in review_files:
        should_upgrade, reason, num_tools = should_upgrade_cache(review_file)

        pmid = review_file.stem.replace('_tool_review', '')

        if should_upgrade:
            upgrade_candidates.append({
                'pmid': pmid,
                'review_file': review_file,
                'reason': reason,
                'num_tools': num_tools
            })
        else:
            # Categorize skip reason
            if 'No high-confidence' in reason:
                skip_reasons['no_tools'].append(pmid)
            elif 'Low completeness' in reason:
                skip_reasons['low_completeness'].append(pmid)
            elif 'Publication type' in reason:
                skip_reasons['review_article'].append(pmid)

    logger.info(f"Upgrade candidates: {len(upgrade_candidates)} publications")
    logger.info(f"  - High-quality tools: {len(upgrade_candidates)}")
    logger.info(f"  - Low completeness: {len(skip_reasons['low_completeness'])} (skipped)")
    logger.info(f"  - Review articles: {len(skip_reasons['review_article'])} (skipped)")
    logger.info(f"  - No tools: {len(skip_reasons['no_tools'])} (skipped)")
    logger.info("")

    if args.dry_run:
        logger.info("DRY RUN - Would upgrade the following caches:")
        logger.info("")
        for candidate in upgrade_candidates[:20]:  # Show first 20
            logger.info(f"  PMID:{candidate['pmid']} - {candidate['reason']}")
        if len(upgrade_candidates) > 20:
            logger.info(f"  ... and {len(upgrade_candidates) - 20} more")
        logger.info("")
        logger.info("Run without --dry-run to actually upgrade caches")
        return 0

    if len(upgrade_candidates) == 0:
        logger.info("No caches need upgrading")
        return 0

    # Perform upgrades
    logger.info(f"Upgrading {len(upgrade_candidates)} caches...")
    logger.info("")

    stats = {
        'upgraded': 0,
        'failed': 0,
        'skipped': 0
    }
    upgraded_pmids = []

    for i, candidate in enumerate(upgrade_candidates, 1):
        pmid = candidate['pmid']
        logger.info(f"[{i}/{len(upgrade_candidates)}] PMID:{pmid}")

        result = upgrade_cache_to_full(pmid, cache_dir)

        if result:
            stats['upgraded'] += 1
            upgraded_pmids.append(f"PMID:{pmid}")
        else:
            stats['failed'] += 1

        # Rate limiting
        time.sleep(0.34)
        logger.info("")

    # Write list of upgraded PMIDs for phase 2 re-review step
    upgraded_pmids_file = Path('tool_coverage/outputs/phase2_upgraded_pmids.txt')
    upgraded_pmids_file.parent.mkdir(parents=True, exist_ok=True)
    with open(upgraded_pmids_file, 'w') as f:
        f.write('\n'.join(upgraded_pmids))
    logger.info(f"Wrote {len(upgraded_pmids)} upgraded PMIDs to {upgraded_pmids_file}")

    # Print summary
    logger.info("="*80)
    logger.info("UPGRADE SUMMARY")
    logger.info("="*80)
    logger.info(f"Total candidates: {len(upgrade_candidates)}")
    logger.info(f"Successfully upgraded: {stats['upgraded']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info("")

    if stats['upgraded'] > 0:
        logger.info(f"✓ Upgraded {stats['upgraded']} caches to full level")
        logger.info(f"  These caches now have Results + Discussion sections")
        logger.info(f"  Ready for observation extraction via phase 2 re-review")


if __name__ == '__main__':
    main()
