#!/usr/bin/env python3
"""
Review Synapse annotations and tools schema to suggest additions and facet configuration.

This script:
1. Queries Synapse materialized view syn52702673 for individualID annotations
2. Queries Synapse materialized view syn51730943 for tools data
3. Compares individualID values against resourceName and synonyms in tools
4. Suggests new resourceName values or synonyms to add based on fuzzy matching
5. Analyzes which columns in syn51730943 are already facets
6. Suggests new facets based on value diversity in tools data
7. Outputs suggestions in a format suitable for PR creation

Usage:
    python review_tool_annotations.py [--output OUTPUT_FILE] [--dry-run] [--limit LIMIT]
"""

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple

try:
    import synapseclient
    from synapseclient import Synapse
    import pandas as pd
except ImportError:
    print("Error: Required packages not installed. Install with: pip install synapseclient pandas")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
ANNOTATIONS_VIEW_ID = "syn52702673"  # "Portal - MV Files": a MaterializedView (read-only query
    # result, joined from ANNOTATIONS_FILEVIEW_ID) -- fine for reads (individualID, studyId, etc.)
    # but Resource_id writes must NOT target this; a MaterializedView has no writable row-to-entity
    # mapping of its own.
ANNOTATIONS_FILEVIEW_ID = "syn16858331"  # "Portal - Files": the real, writable EntityView backing
    # ANNOTATIONS_VIEW_ID above. Resource_id annotation writes (nf-research-tools-schema#154) go
    # here, and must be read from here too, so the rowId_rowVersion identity used to target the
    # write matches this table, not the MV's.
TOOLS_VIEW_ID = "syn51730943"  # Tools materialized view (for resourceName, synonyms, facets)
TOOL_STUDY_LINKS_TABLE_ID = "syn26461958"  # tool<->study junction table (nf-research-tools-schema#132)

# Minimum frequency threshold for suggesting new individualID values
MIN_FREQUENCY = 2

# Minimum unique values for suggesting search filters/facets
MIN_FILTER_FREQUENCY = 5

# Fuzzy match threshold for synonym suggestions (0.0 to 1.0)
FUZZY_MATCH_THRESHOLD = 0.85






def query_individual_ids(syn: Synapse, limit: int = None) -> List[str]:
    """
    Query Synapse annotations view for individualID values.

    Args:
        syn: Synapse client
        limit: Optional limit on number of rows to retrieve

    Returns:
        List of unique individualID values
    """
    logger.info(f"Querying Synapse annotations view {ANNOTATIONS_VIEW_ID} for individualID...")

    query = f"SELECT individualID FROM {ANNOTATIONS_VIEW_ID} WHERE individualID IS NOT NULL"
    if limit:
        query += f" LIMIT {limit}"

    try:
        results = syn.tableQuery(query)
        df = results.asDataFrame()

        logger.info(f"Retrieved {len(df)} records with individualID")

        # Get unique non-null values
        individual_ids = df['individualID'].dropna().unique().tolist()
        logger.info(f"Found {len(individual_ids)} unique individualID values")

        return individual_ids

    except Exception as e:
        logger.error(f"Error querying Synapse annotations: {e}")
        raise


def query_individual_id_study_occurrences(syn: Synapse, limit: int = None) -> "pd.DataFrame":
    """
    Query the file annotations view for individualID values together with the
    study each occurrence belongs to (syn52702673 already carries studyId/
    studyName per file -- no extra join needed).

    Used to trace an individualID that exactly matches a known tool back to
    the study/studies whose files reference it, for automated tool<->study
    linking (nf-osi/nf-research-tools-schema#132, #154).

    Args:
        syn: Synapse client
        limit: Optional limit on number of rows to retrieve

    Returns:
        DataFrame with columns [individualID, studyId, studyName], one row
        per (individualID, studyId) occurrence (not deduplicated).
    """
    logger.info(f"Querying {ANNOTATIONS_VIEW_ID} for individualID/studyId occurrences...")

    query = (
        f"SELECT individualID, studyId, studyName FROM {ANNOTATIONS_VIEW_ID} "
        f"WHERE individualID IS NOT NULL AND studyId IS NOT NULL"
    )
    if limit:
        query += f" LIMIT {limit}"

    try:
        df = syn.tableQuery(query).asDataFrame()
        logger.info(f"Retrieved {len(df)} individualID/studyId occurrence row(s)")
        return df
    except Exception as e:
        logger.error(f"Error querying individualID/studyId occurrences: {e}")
        raise


def query_individual_id_file_occurrences(syn: Synapse, limit: int = None) -> "pd.DataFrame":
    """
    Query the writable file annotations EntityView (ANNOTATIONS_FILEVIEW_ID,
    NOT the ANNOTATIONS_VIEW_ID MaterializedView -- see the constants'
    comments) for each file's individualID together with its own id and
    existing Resource_id annotation.

    Deliberately reads from the same table that upsert_resource_id_annotations
    writes to: the rowId_rowVersion identity a write targets (see that
    function's docstring) has to come from the table actually being written
    to, not a MaterializedView built on top of it.

    Used to backfill Resource_id directly onto files whose individualID
    matches a known tool, so the existing Tool Details "Data > Files" tab
    (which already renders based on Resource_id) picks them up without any
    frontend change -- nf-osi/nf-research-tools-schema#154.

    Args:
        syn: Synapse client
        limit: Optional limit on number of rows to retrieve

    Returns:
        DataFrame with columns [id, individualID, Resource_id], one row per
        file. Resource_id is a list (possibly empty/NaN) since it's a
        STRING_LIST column.
    """
    logger.info(f"Querying {ANNOTATIONS_FILEVIEW_ID} for individualID/Resource_id per file...")

    query = (
        f"SELECT id, individualID, Resource_id FROM {ANNOTATIONS_FILEVIEW_ID} "
        f"WHERE individualID IS NOT NULL"
    )
    if limit:
        query += f" LIMIT {limit}"

    try:
        df = syn.tableQuery(query).asDataFrame()
        logger.info(f"Retrieved {len(df)} file/individualID row(s)")
        return df
    except Exception as e:
        logger.error(f"Error querying individualID/Resource_id file occurrences: {e}")
        raise


def snapshot_table(syn: Synapse, table_id: str, comment: str) -> Optional[int]:
    """
    Create a snapshot version of a table/view before or after an automated
    write, so every change this script makes is recoverable independent of
    Synapse's trash can (per standing policy: snapshot before AND after any
    write, not just one or the other).

    Best-effort: a snapshot failure is logged but does not raise, so a
    snapshotting hiccup never blocks (or gets blocked by) the write itself
    being wrapped.
    """
    try:
        version = syn.create_snapshot_version(table_id, comment=comment)
        logger.info(f"Snapshotted {table_id} as version {version} ({comment})")
        return version
    except Exception as e:
        logger.warning(f"Could not snapshot {table_id}: {e}")
        return None


def query_existing_tool_study_links(syn: Synapse) -> Set[tuple]:
    """
    Query the existing tool<->study junction table for (resourceId, studyId)
    pairs already recorded, so newly-mined associations can be de-duplicated
    against it.
    """
    logger.info(f"Querying existing links from {TOOL_STUDY_LINKS_TABLE_ID}...")
    try:
        df = syn.tableQuery(
            f"SELECT resourceId, studyId FROM {TOOL_STUDY_LINKS_TABLE_ID}"
        ).asDataFrame()
        existing = {(row.resourceId, row.studyId) for row in df.itertuples()}
        logger.info(f"Found {len(existing)} existing tool<->study link(s)")
        return existing
    except Exception as e:
        logger.warning(f"Could not query existing tool<->study links, treating as empty: {e}")
        return set()


def _strip_disambiguation_suffix(name: str) -> str:
    """Strip a single trailing parenthetical, e.g. 'JH-2-002 (MPNST)' ->
    'JH-2-002'. Used only to build a best-effort fallback match key below --
    never to rewrite an actual resourceName/synonym."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def _build_resource_match_lookups(
    tools_data: List[Dict],
) -> Tuple[Dict[str, Dict], Dict[str, Dict], Dict[str, Dict]]:
    """
    Build the three matching tiers shared by find_tool_study_links and
    find_resource_id_annotations: exact resourceName, exact synonym, and a
    lower-confidence stripped-disambiguation-suffix fallback (e.g. an
    individualID of "JH-2-002" against a resourceName of
    "JH-2-002 (MPNST)") -- common for Cell Line/Patient-Derived Model/
    Antibody/Genetic Reagent/Animal Model resources that share a parent
    specimen or clone ID but are registered as distinct resources per tumor
    type, epitope, etc.

    The stripped-name tier is ONLY trusted when it resolves to exactly one
    resourceId. Several base names are genuinely shared by more than one
    resourceId (e.g. "JH-2-002 (MPNST)" and "JH-2-002 (pNF)" are two
    different sublines of the same specimen) -- an individualID of
    "JH-2-002" in that case is truly ambiguous between them, and must not be
    auto-linked to either.

    Returns (resource_by_name, resource_by_synonym, stripped_lookup).
    """
    resource_by_name: Dict[str, Dict] = {}
    resource_by_synonym: Dict[str, Dict] = {}
    stripped_candidates: Dict[str, Set[str]] = {}
    stripped_lookup: Dict[str, Dict] = {}
    for tool in tools_data:
        name = tool.get('resourceName')
        rid = tool.get('resourceId')
        if not name or not rid:
            continue
        resource_by_name[name] = tool
        synonyms_str = tool.get('synonyms', '')
        if synonyms_str and isinstance(synonyms_str, str):
            for syn_name in (s.strip() for s in synonyms_str.split(',')):
                if syn_name:
                    resource_by_synonym[syn_name] = tool

        stripped = _strip_disambiguation_suffix(name)
        if stripped and stripped != name:
            stripped_candidates.setdefault(stripped, set()).add(rid)
            stripped_lookup[stripped] = tool

    ambiguous_stripped = {s for s, rids in stripped_candidates.items() if len(rids) > 1}
    for s in ambiguous_stripped:
        stripped_lookup.pop(s, None)
    if ambiguous_stripped:
        example = ', '.join(sorted(ambiguous_stripped)[:3])
        logger.info(
            f"Skipping {len(ambiguous_stripped)} ambiguous disambiguation-suffix "
            f"base name(s) shared by >1 resourceId -- not safe to auto-link "
            f"(e.g. {example}...)"
        )

    return resource_by_name, resource_by_synonym, stripped_lookup


def find_tool_study_links(
    occurrences: "pd.DataFrame",
    tools_data: List[Dict],
    existing_links: Set[tuple],
) -> List[Dict]:
    """
    For each individualID that matches a known tool's resourceName or
    synonym, collect the (resourceId, studyId) pairs it co-occurs with in
    file annotations, filtered down to ones not already in
    TOOL_STUDY_LINKS_TABLE_ID.

    See _build_resource_match_lookups for the matching tiers used.
    """
    resource_by_name, resource_by_synonym, stripped_lookup = _build_resource_match_lookups(tools_data)

    new_links: Dict[tuple, Dict] = {}
    for row in occurrences.itertuples():
        individual_id = str(row.individualID).strip()
        study_id = row.studyId
        if not individual_id or not study_id:
            continue

        tool = (
            resource_by_name.get(individual_id)
            or resource_by_synonym.get(individual_id)
            or stripped_lookup.get(individual_id)
        )
        if not tool:
            continue

        key = (tool['resourceId'], study_id)
        if key in existing_links or key in new_links:
            continue

        new_links[key] = {
            'resourceId': tool['resourceId'],
            'resourceName': tool.get('resourceName'),
            'resourceType': tool.get('resourceType'),
            'rrid': tool.get('rrid'),
            'description': tool.get('description'),
            'synonyms': tool.get('synonyms'),
            'studyId': study_id,
            'studyName': getattr(row, 'studyName', None),
            'matchedVia': individual_id,
        }

    logger.info(f"Found {len(new_links)} new tool<->study association(s) not already in {TOOL_STUDY_LINKS_TABLE_ID}")
    return list(new_links.values())


RESOURCE_ID_MAX_LIST_LENGTH = 10  # matches the Resource_id column's maxListLength on syn52702673


def find_resource_id_annotations(
    file_occurrences: "pd.DataFrame",
    tools_data: List[Dict],
) -> "pd.DataFrame":
    """
    For each file whose individualID matches a known tool (same tiered
    matching as find_tool_study_links -- see _build_resource_match_lookups),
    determine whether its existing Resource_id annotation needs the matched
    resourceId appended.

    Additive only: an existing Resource_id value is never removed, and a
    resourceId already present is left alone. Files where appending would
    exceed RESOURCE_ID_MAX_LIST_LENGTH are skipped and logged rather than
    silently truncated or left to fail on write.

    IMPORTANT: file_occurrences must be the DataFrame returned directly by
    query_individual_id_file_occurrences (or another syn.tableQuery(...)
    .asDataFrame() call against ANNOTATIONS_FILEVIEW_ID -- NOT the
    ANNOTATIONS_VIEW_ID MaterializedView) -- its pandas index encodes
    Synapse's rowId_rowVersion for each row, which is preserved on
    the returned DataFrame and is what tells Synapse to UPDATE those
    specific existing file rows rather than attempt to insert new ones (a
    fileview's rows can't be inserted directly; membership is derived from
    entity scope). Rebuilding a plain DataFrame from scratch here would lose
    that and break the write in upsert_resource_id_annotations.

    Returns a DataFrame with columns [id, Resource_id], index preserved from
    file_occurrences -- ready to upsert via upsert_resource_id_annotations
    -- containing only files that actually need a change.
    """
    resource_by_name, resource_by_synonym, stripped_lookup = _build_resource_match_lookups(tools_data)

    updates = []
    row_labels = []
    skipped_full = 0
    for row_label, row in zip(file_occurrences.index, file_occurrences.itertuples()):
        file_id = row.id
        individual_id = str(row.individualID).strip() if row.individualID else ''
        if not file_id or not individual_id:
            continue

        tool = (
            resource_by_name.get(individual_id)
            or resource_by_synonym.get(individual_id)
            or stripped_lookup.get(individual_id)
        )
        if not tool:
            continue

        existing = row.Resource_id
        existing_list = list(existing) if isinstance(existing, list) else []
        if tool['resourceId'] in existing_list:
            continue

        if len(existing_list) >= RESOURCE_ID_MAX_LIST_LENGTH:
            skipped_full += 1
            continue

        updates.append({'id': file_id, 'Resource_id': existing_list + [tool['resourceId']]})
        row_labels.append(row_label)

    if skipped_full:
        logger.info(
            f"Skipping Resource_id update on {skipped_full} file(s) already at "
            f"the {RESOURCE_ID_MAX_LIST_LENGTH}-value list limit"
        )

    logger.info(f"Found {len(updates)} file(s) needing a new Resource_id annotation")
    return pd.DataFrame(updates, columns=['id', 'Resource_id'], index=row_labels)


def upsert_resource_id_annotations(syn: Synapse, updates: "pd.DataFrame") -> None:
    """
    Write the mined Resource_id values back onto their files via
    ANNOTATIONS_FILEVIEW_ID (the writable EntityView -- NOT
    ANNOTATIONS_VIEW_ID, which is a read-only MaterializedView built on top
    of it and has no writable row-to-entity mapping of its own). Additive
    only (see find_resource_id_annotations) -- safe to run unattended for
    the same reason upsert_tool_study_links is: an exact
    individualID<->resourceName/synonym match, or an unambiguous
    stripped-suffix match, is a high-confidence, mechanical signal.

    `updates` must carry the rowId_rowVersion index from the original query
    against ANNOTATIONS_FILEVIEW_ID (see find_resource_id_annotations) --
    that's what makes this an UPDATE of the named files' existing
    Resource_id annotation rather than an attempted insert. It does not
    touch any other annotation or create a new file version, only the
    Resource_id value.

    Snapshots ANNOTATIONS_FILEVIEW_ID immediately before and after the write
    (standing policy: every automated table/view write is bracketed by a
    snapshot on both sides, not just one).
    """
    if updates.empty:
        logger.info("No new Resource_id annotations to upsert")
        return

    snapshot_table(syn, ANNOTATIONS_FILEVIEW_ID, f"Before Resource_id backfill of {len(updates)} file(s) (nf-research-tools-schema#154)")
    syn.store(synapseclient.Table(ANNOTATIONS_FILEVIEW_ID, updates))
    logger.info(f"Upserted Resource_id annotation on {len(updates)} file(s) via {ANNOTATIONS_FILEVIEW_ID}")
    snapshot_table(syn, ANNOTATIONS_FILEVIEW_ID, f"After Resource_id backfill of {len(updates)} file(s) (nf-research-tools-schema#154)")


def upsert_tool_study_links(syn: Synapse, links: List[Dict]) -> None:
    """
    Upsert newly-mined tool<->study associations directly into
    TOOL_STUDY_LINKS_TABLE_ID. Additive only -- never modifies or removes any
    existing row, so this is safe to run unattended even though it writes to
    Synapse without a review step (unlike new-resource suggestions, which
    still go through the PR-based submission flow since those require human
    curation judgment; an exact individualID<->resourceName/synonym match is
    a high-confidence, mechanical signal that doesn't).

    Snapshots TOOL_STUDY_LINKS_TABLE_ID immediately before and after the
    write (standing policy: every automated table/view write is bracketed
    by a snapshot on both sides, not just one).
    """
    if not links:
        logger.info("No new tool<->study links to upsert")
        return

    rows = [
        {
            'studyId': link['studyId'],
            'resourceId': link['resourceId'],
            'resourceName': link['resourceName'],
            'resourceType': link['resourceType'],
            'rrid': link['rrid'],
            'description': link['description'],
            'synonyms': link['synonyms'],
        }
        for link in links
    ]
    df = pd.DataFrame(rows)
    snapshot_table(syn, TOOL_STUDY_LINKS_TABLE_ID, f"Before upserting {len(rows)} new tool<->study link(s) (nf-research-tools-schema#132, #154)")
    syn.store(synapseclient.Table(TOOL_STUDY_LINKS_TABLE_ID, df))
    logger.info(f"Upserted {len(rows)} new tool<->study link(s) to {TOOL_STUDY_LINKS_TABLE_ID}")
    snapshot_table(syn, TOOL_STUDY_LINKS_TABLE_ID, f"After upserting {len(rows)} new tool<->study link(s) (nf-research-tools-schema#132, #154)")


def query_tools_data(syn: Synapse, limit: int = None) -> List[Dict]:
    """
    Query Synapse tools view for all tool data.

    Args:
        syn: Synapse client
        limit: Optional limit on number of rows to retrieve

    Returns:
        List of tool records
    """
    logger.info(f"Querying Synapse tools view {TOOLS_VIEW_ID}...")

    query = f"SELECT * FROM {TOOLS_VIEW_ID}"
    if limit:
        query += f" LIMIT {limit}"

    try:
        results = syn.tableQuery(query)
        df = results.asDataFrame()

        logger.info(f"Retrieved {len(df)} tools with {len(df.columns)} columns")

        # Convert to list of dicts
        records = df.to_dict('records')
        return records

    except Exception as e:
        logger.error(f"Error querying Synapse tools: {e}")
        raise


def get_facet_columns(syn: Synapse) -> Set[str]:
    """
    Get the list of columns configured as facets in the tools view.

    Args:
        syn: Synapse client

    Returns:
        Set of column names that are configured as facets
    """
    logger.info(f"Getting facet configuration for {TOOLS_VIEW_ID}...")

    try:
        # Get the table/view entity
        entity = syn.get(TOOLS_VIEW_ID)

        facet_columns = set()

        # Check if the entity has column models
        if hasattr(entity, 'columnIds'):
            for col_id in entity.columnIds:
                col = syn.getColumn(col_id)
                # Check if column has facet type set
                if hasattr(col, 'facetType') and col.facetType:
                    facet_columns.add(col.name)
                    logger.debug(f"Found facet column: {col.name} (type: {col.facetType})")

        logger.info(f"Found {len(facet_columns)} columns configured as facets")
        return facet_columns

    except Exception as e:
        logger.warning(f"Error getting facet configuration: {e}")
        return set()


def fuzzy_match(s1: str, s2: str) -> float:
    """
    Calculate fuzzy match score between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Similarity score between 0.0 and 1.0
    """
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def find_best_synonym_match(value: str, synonyms_list: List[str]) -> Optional[Tuple[str, float]]:
    """
    Find the best fuzzy match for a value among a list of synonyms.

    Args:
        value: Value to match
        synonyms_list: List of synonym strings

    Returns:
        Tuple of (best_match, score) or None if no good match
    """
    best_match = None
    best_score = 0.0

    for synonym in synonyms_list:
        score = fuzzy_match(value, synonym)
        if score > best_score:
            best_score = score
            best_match = synonym

    if best_score >= FUZZY_MATCH_THRESHOLD:
        return (best_match, best_score)

    return None


def analyze_individual_ids(
    individual_ids: List[str],
    tools_data: List[Dict]
) -> Dict[str, List[Dict]]:
    """
    Analyze individualID values against tools data to suggest additions.

    Args:
        individual_ids: List of unique individualID values from annotations
        tools_data: List of tool records from tools view

    Returns:
        Dictionary with suggestions categorized by type:
        - 'new_resources': individualIDs to add as new resourceName
        - 'new_synonyms': individualIDs to add as synonyms (with fuzzy match info)
        - 'existing_exact': individualIDs that exactly match existing resourceName
        - 'existing_synonyms': individualIDs that match existing synonyms
    """
    logger.info("Analyzing individualID values against tools data...")

    # Build lookup structures from tools data
    resource_names = set()
    synonyms_by_resource = {}  # resourceName -> list of synonyms

    for tool in tools_data:
        resource_name = tool.get('resourceName')
        if resource_name:
            resource_names.add(resource_name)

            # Parse synonyms (comma-separated)
            synonyms_str = tool.get('synonyms', '')
            if synonyms_str and isinstance(synonyms_str, str):
                synonyms = [s.strip() for s in synonyms_str.split(',') if s.strip()]
                synonyms_by_resource[resource_name] = synonyms

    # Count frequencies of individualIDs
    id_counts = defaultdict(int)
    for individual_id in individual_ids:
        if individual_id:
            id_counts[str(individual_id).strip()] += 1

    # Categorize suggestions
    suggestions = {
        'new_resources': [],  # List of (individualID, count)
        'new_synonyms': [],  # List of (individualID, best_match_resource, match_score, count)
        'existing_exact': [],  # List of (individualID, count)
        'existing_synonyms': []  # List of (individualID, matching_resource, count)
    }

    for individual_id, count in id_counts.items():
        if count < MIN_FREQUENCY:
            continue

        # Check for exact match with resourceName
        if individual_id in resource_names:
            suggestions['existing_exact'].append({
                'value': individual_id,
                'count': count
            })
            continue

        # Check for exact match with any synonym
        found_in_synonyms = False
        for resource_name, synonyms in synonyms_by_resource.items():
            if individual_id in synonyms:
                suggestions['existing_synonyms'].append({
                    'value': individual_id,
                    'resource': resource_name,
                    'count': count
                })
                found_in_synonyms = True
                break

        if found_in_synonyms:
            continue

        # Try fuzzy matching with synonyms
        best_match = None
        best_score = 0.0
        best_resource = None

        for resource_name, synonyms in synonyms_by_resource.items():
            match_result = find_best_synonym_match(individual_id, synonyms)
            if match_result and match_result[1] > best_score:
                best_match, best_score = match_result
                best_resource = resource_name

        if best_match and best_resource:
            suggestions['new_synonyms'].append({
                'value': individual_id,
                'resource': best_resource,
                'matched_synonym': best_match,
                'match_score': best_score,
                'count': count
            })
        else:
            # No match found - suggest as new resource
            suggestions['new_resources'].append({
                'value': individual_id,
                'count': count
            })

    # Sort by count (descending)
    for category in suggestions:
        suggestions[category].sort(key=lambda x: x['count'], reverse=True)

    logger.info(f"Found {len(suggestions['new_resources'])} new resource suggestions")
    logger.info(f"Found {len(suggestions['new_synonyms'])} new synonym suggestions")
    logger.info(f"Found {len(suggestions['existing_exact'])} exact matches with resourceName")
    logger.info(f"Found {len(suggestions['existing_synonyms'])} matches with existing synonyms")

    return suggestions


def analyze_facets(
    tools_data: List[Dict],
    existing_facets: Set[str]
) -> Dict[str, Dict]:
    """
    Analyze tools data to suggest facet configuration.

    Args:
        tools_data: List of tool records
        existing_facets: Set of column names already configured as facets

    Returns:
        Dictionary with facet analysis:
        - 'existing_facets': Info about existing facets (diversity, sample values)
        - 'suggested_new_facets': Columns that could be good facets
    """
    logger.info("Analyzing facet configuration...")

    if not tools_data:
        return {'existing_facets': {}, 'suggested_new_facets': {}}

    # Count unique values per column
    column_values = defaultdict(set)

    for tool in tools_data:
        for column, value in tool.items():
            if value is not None and str(value).strip():
                # Handle comma-separated lists
                value_str = str(value).strip()
                if ',' in value_str:
                    # Split and add each value
                    for v in value_str.split(','):
                        if v.strip():
                            column_values[column].add(v.strip())
                else:
                    column_values[column].add(value_str)

    # Analyze existing facets
    existing_facets_info = {}
    for column in existing_facets:
        if column in column_values:
            values = column_values[column]
            existing_facets_info[column] = {
                'unique_count': len(values),
                'sample_values': sorted(list(values))[:10]
            }

    # Suggest new facets (columns with good diversity, not already facets)
    suggested_new_facets = {}
    for column, values in column_values.items():
        unique_count = len(values)

        # Skip if already a facet
        if column in existing_facets:
            continue

        # Only suggest if has enough diversity
        if unique_count >= MIN_FILTER_FREQUENCY and unique_count <= 100:  # Not too many
            suggested_new_facets[column] = {
                'unique_count': unique_count,
                'sample_values': sorted(list(values))[:10]
            }

    # Sort by unique count
    suggested_new_facets = dict(sorted(
        suggested_new_facets.items(),
        key=lambda x: x[1]['unique_count'],
        reverse=True
    ))

    logger.info(f"Analyzed {len(existing_facets_info)} existing facets")
    logger.info(f"Suggested {len(suggested_new_facets)} new facets")

    return {
        'existing_facets': existing_facets_info,
        'suggested_new_facets': suggested_new_facets
    }


def format_suggestions_as_markdown(
    individual_id_suggestions: Dict[str, List[Dict]],
    facet_analysis: Dict[str, Dict]
) -> str:
    """
    Format suggestions as markdown for PR description.

    Args:
        individual_id_suggestions: Categorized individualID suggestions
        facet_analysis: Facet configuration analysis

    Returns:
        Markdown formatted string
    """
    md = ["# Tool Annotation Review - Schema Updates and Facet Suggestions\n\n"]
    md.append("This PR contains automatic updates based on analysis of:\n")
    md.append(f"- **Annotations**: individualID values from {ANNOTATIONS_VIEW_ID}\n")
    md.append(f"- **Tools data**: resourceName, synonyms, and facets from {TOOLS_VIEW_ID}\n\n")

    # Section 1: individualID value suggestions
    md.append("## 1. IndividualID Value Suggestions\n\n")

    new_resources = individual_id_suggestions.get('new_resources', [])
    new_synonyms = individual_id_suggestions.get('new_synonyms', [])
    existing_exact = individual_id_suggestions.get('existing_exact', [])
    existing_synonyms = individual_id_suggestions.get('existing_synonyms', [])

    if new_resources:
        md.append(f"### New Resources to Add ({len(new_resources)})\n")
        md.append("These individualID values don't match any existing resourceName or synonyms:\n\n")
        for item in new_resources[:20]:
            md.append(f"- `{item['value']}` (used {item['count']} times)\n")
        if len(new_resources) > 20:
            md.append(f"\n*...and {len(new_resources) - 20} more*\n")
        md.append("\n")

    if new_synonyms:
        md.append(f"### Synonyms to Add ({len(new_synonyms)})\n")
        md.append("These individualID values fuzzy-match existing synonyms and could be added as synonyms:\n\n")
        for item in new_synonyms[:20]:
            md.append(f"- `{item['value']}` → add as synonym to `{item['resource']}` ")
            md.append(f"(matches `{item['matched_synonym']}`, score: {item['match_score']:.2f}, ")
            md.append(f"used {item['count']} times)\n")
        if len(new_synonyms) > 20:
            md.append(f"\n*...and {len(new_synonyms) - 20} more*\n")
        md.append("\n")

    if existing_exact:
        md.append(f"### ✓ Existing Resources ({len(existing_exact)})\n")
        md.append("These individualID values already match resourceName exactly:\n\n")
        for item in existing_exact[:10]:
            md.append(f"- `{item['value']}` (used {item['count']} times)\n")
        if len(existing_exact) > 10:
            md.append(f"\n*...and {len(existing_exact) - 10} more*\n")
        md.append("\n")

    if existing_synonyms:
        md.append(f"### ✓ Existing Synonyms ({len(existing_synonyms)})\n")
        md.append("These individualID values already match existing synonyms:\n\n")
        for item in existing_synonyms[:10]:
            md.append(f"- `{item['value']}` (synonym of `{item['resource']}`, used {item['count']} times)\n")
        if len(existing_synonyms) > 10:
            md.append(f"\n*...and {len(existing_synonyms) - 10} more*\n")
        md.append("\n")

    # Section 2: Facet analysis
    md.append("## 2. Facet Configuration Analysis\n\n")

    existing_facets = facet_analysis.get('existing_facets', {})
    suggested_facets = facet_analysis.get('suggested_new_facets', {})

    if existing_facets:
        md.append(f"### Current Facets ({len(existing_facets)})\n")
        md.append("Columns currently configured as facets:\n\n")
        for column, info in sorted(existing_facets.items(), key=lambda x: x[1]['unique_count'], reverse=True):
            md.append(f"- `{column}` ({info['unique_count']} unique values)\n")
            sample = ", ".join([f"`{v}`" for v in info['sample_values'][:5]])
            md.append(f"  - Sample values: {sample}\n")
        md.append("\n")

    if suggested_facets:
        md.append(f"### Suggested New Facets ({len(suggested_facets)})\n")
        md.append("Columns with good value diversity that could be added as facets:\n\n")
        for column, info in list(suggested_facets.items())[:15]:
            md.append(f"- `{column}` ({info['unique_count']} unique values)\n")
            sample = ", ".join([f"`{v}`" for v in info['sample_values'][:5]])
            md.append(f"  - Sample values: {sample}\n")
        if len(suggested_facets) > 15:
            md.append(f"\n*...and {len(suggested_facets) - 15} more*\n")
        md.append("\n")
    else:
        md.append("### No New Facets Suggested\n")
        md.append("All columns with good diversity are already configured as facets.\n\n")

    md.append("---\n")
    md.append("*Generated by automated tool annotation review workflow*\n")

    return ''.join(md)


def save_suggestions_to_file(
    individual_id_suggestions: Dict[str, List[Dict]],
    facet_analysis: Dict[str, Dict],
    output_file: Path
) -> None:
    """
    Save suggestions to JSON file for potential automated processing.

    Args:
        individual_id_suggestions: Categorized individualID suggestions
        facet_analysis: Facet configuration analysis
        output_file: Path to output file
    """
    data = {
        'individual_id_suggestions': individual_id_suggestions,
        'facet_analysis': facet_analysis,
        'annotations_view': ANNOTATIONS_VIEW_ID,
        'tools_view': TOOLS_VIEW_ID,
        'min_frequency': MIN_FREQUENCY,
        'fuzzy_match_threshold': FUZZY_MATCH_THRESHOLD
    }

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved suggestions to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Review Synapse annotations and tools schema, suggest additions and facet configuration'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('tool_annotation_suggestions.json'),
        help='Output file for suggestions (JSON format)'
    )
    parser.add_argument(
        '--markdown',
        type=Path,
        default=Path('tool_annotation_suggestions.md'),
        help='Output file for markdown summary'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print suggestions without modifying files'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of records to query (for testing)'
    )

    args = parser.parse_args()

    # Check for Synapse authentication
    auth_token = os.environ.get('SYNAPSE_AUTH_TOKEN')
    if not auth_token:
        logger.error("SYNAPSE_AUTH_TOKEN environment variable not set")
        sys.exit(1)

    try:
        # Initialize Synapse client
        syn = Synapse()
        syn.login(authToken=auth_token)
        logger.info("Logged into Synapse")

        # Query individualID from annotations
        logger.info("\n=== Querying Annotations ===")
        individual_ids = query_individual_ids(syn, limit=args.limit)

        # Query tools data
        logger.info("\n=== Querying Tools Data ===")
        tools_data = query_tools_data(syn, limit=args.limit)

        # Get facet configuration
        logger.info("\n=== Getting Facet Configuration ===")
        existing_facets = get_facet_columns(syn)

        # Analyze individualID values
        logger.info("\n=== Analyzing IndividualID Values ===")
        individual_id_suggestions = analyze_individual_ids(individual_ids, tools_data)

        # Mine tool<->study associations (nf-osi/nf-research-tools-schema#132, #154)
        logger.info("\n=== Mining Tool<->Study Associations ===")
        occurrences = query_individual_id_study_occurrences(syn, limit=args.limit)
        existing_links = query_existing_tool_study_links(syn)
        new_tool_study_links = find_tool_study_links(occurrences, tools_data, existing_links)
        if new_tool_study_links and not args.dry_run:
            upsert_tool_study_links(syn, new_tool_study_links)
        elif new_tool_study_links:
            logger.info(f"Dry run -- would upsert {len(new_tool_study_links)} new tool<->study link(s)")

        # Backfill Resource_id file annotations (nf-osi/nf-research-tools-schema#154,
        # https://github.com/nf-osi/nf-research-tools-schema/issues/154#issuecomment-5394955094)
        # so the existing Tool Details "Data > Files" tab -- which already renders
        # off Resource_id -- picks up files without any frontend change.
        logger.info("\n=== Mining Resource_id File Annotations ===")
        file_occurrences = query_individual_id_file_occurrences(syn, limit=args.limit)
        resource_id_updates = find_resource_id_annotations(file_occurrences, tools_data)
        if not resource_id_updates.empty and not args.dry_run:
            upsert_resource_id_annotations(syn, resource_id_updates)
        elif not resource_id_updates.empty:
            logger.info(f"Dry run -- would upsert Resource_id on {len(resource_id_updates)} file(s)")

        # Analyze facet configuration
        logger.info("\n=== Analyzing Facet Configuration ===")
        facet_analysis = analyze_facets(tools_data, existing_facets)

        # Format as markdown
        markdown = format_suggestions_as_markdown(
            individual_id_suggestions,
            facet_analysis
        )

        if args.dry_run:
            logger.info("\n=== Dry Run - Printing Results ===")
            print("\n" + "="*80)
            print(markdown)
            print("="*80)
        else:
            # Save files
            save_suggestions_to_file(
                individual_id_suggestions,
                facet_analysis,
                args.output
            )

            with open(args.markdown, 'w') as f:
                f.write(markdown)
            logger.info(f"Saved markdown to {args.markdown}")

        # Summary
        logger.info(f"\n=== Summary ===")
        logger.info(f"  IndividualID Analysis:")
        logger.info(f"    - {len(individual_id_suggestions.get('new_resources', []))} new resources to add")
        logger.info(f"    - {len(individual_id_suggestions.get('new_synonyms', []))} synonyms to add")
        logger.info(f"    - {len(individual_id_suggestions.get('existing_exact', []))} exact matches")
        logger.info(f"    - {len(individual_id_suggestions.get('existing_synonyms', []))} synonym matches")
        logger.info(f"  Tool<->Study Links:")
        logger.info(f"    - {len(new_tool_study_links)} new association(s) {'upserted' if not args.dry_run else '(dry run, not upserted)'}")
        logger.info(f"  Resource_id File Annotations:")
        logger.info(f"    - {len(resource_id_updates)} file(s) {'updated' if not args.dry_run else '(dry run, not updated)'}")
        logger.info(f"  Facet Analysis:")
        logger.info(f"    - {len(facet_analysis.get('existing_facets', {}))} existing facets")
        logger.info(f"    - {len(facet_analysis.get('suggested_new_facets', {}))} suggested new facets")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
