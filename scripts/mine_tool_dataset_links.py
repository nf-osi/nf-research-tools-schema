#!/usr/bin/env python3
"""
Mine tool<->dataset associations and populate syn16859448 (Tool_Dataset).

nf-research-tools-schema#252: Meant for Tool Details "Data" tab, 
Tool_Dataset (syn16859448) is a new junction table that 
links tools to datasets in the prod Portal Dataset Collection (syn50913342).

A Dataset entity's constituent files identify their
resource via one of two fields (Tool_Dataset's own Synapse description
scopes this to "animal models and cell lines only"):
    - `individualID`      -> Cell Line donor
    - `modelSystemName`   -> Animal Model genetic background

Neither field is exposed at the dataset-collection level (syn50913342), 
so a file's Dataset membership is defined by the Dataset
entity's own item list; we have to query each Dataset entity 
individually as a table over its own constituent items.

Reuses review_tool_annotations.py's tools-view query and disambiguation-
aware matching lookup (_build_resource_match_lookups) rather than
duplicating that logic -- see this repo's #246 for why the matching tiers
(exact resourceName, exact synonym, stripped-disambiguation-suffix
fallback, all ambiguous-key-safe) exist.

Same review-then-apply policy as review_tool_annotations.py's tool<->study
link mining (per #246 review): a match against a known resourceName/
synonym is additive-only but NOT auto-upserted. A single individualID/
modelSystemName can legitimately span more than one downstream resource in
ways the tools registry alone can't rule out, so a human reviews the
generated CSV before anything is written to Synapse.

Per-dataset queries are fanned out across a thread pool (--workers, default
DEFAULT_MAX_WORKERS): each dataset's values are independent of every other
dataset's, and these are network-I/O-bound calls (the GIL is released
during the actual request), so threads are a straightforward win here.

Deliberately does NOT call getTableColumns to discover which of
individualID/modelSystemName a dataset has before querying (see
_query_one_dataset's docstring for the full story): that hits Synapse's
/entity/{id}/column endpoint, which carries a much stricter server-side
throttle than tableQuery itself -- confirmed live, a handful of concurrent
worker threads calling it tripped a 6-requests-per-60-seconds limit and
fell into synapseclient's own internal 30s backoff, making the parallel
case slower than the original sequential pass. Querying directly and
narrowing the SELECT list on Synapse's "Unknown column" error instead
avoids that endpoint entirely and confirmed live to be both correct (a
Dataset's declared column list can lag what its query engine actually
resolves) and fast: a full 189-dataset mining pass completed in ~87s at 8
workers with no throttling (vs. ~590s for the original sequential,
getTableColumns-based approach -- roughly a 7x speedup). A 429 from
tableQuery itself is still retried with exponential backoff per-call (see
_call_with_rate_limit_retry) as defense in depth, though none was observed
live once getTableColumns was removed.

Usage:
    python mine_tool_dataset_links.py [--dry-run] [--limit LIMIT] [--workers N]
    python mine_tool_dataset_links.py --dataset-id syn123 --dataset-id syn456  # newly-added datasets only
    python mine_tool_dataset_links.py --apply-tool-dataset-links-csv tool_dataset_links_for_review.csv
"""

import argparse
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    import synapseclient
    from synapseclient import Synapse
    import pandas as pd
except ImportError:
    print("Error: Required packages not installed. Install with: pip install synapseclient pandas")
    sys.exit(1)

# Ensure this script's own directory is importable regardless of how this
# module was loaded, so the sibling modules below resolve either way.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synapse_safety import snapshot_table  # noqa: E402 -- shared before/after-snapshot policy
import review_tool_annotations as rta  # noqa: E402 -- reuse query_tools_data + matching lookups

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DATASET_COLLECTION_ID = "syn50913342"  # "Portal - Dataset Collection (Production)": a
    # DatasetCollection of every Dataset entity on the NF Data Portal. Also the direct
    # source of the per-dataset metadata (title, description, studyId, dataType,
    # diseaseFocus) mirrored into TOOL_DATASET_TABLE_ID below -- its columns were chosen
    # to match this collection's columns exactly.
TOOL_DATASET_TABLE_ID = "syn16859448"  # "Tool_Dataset" junction table (nf-research-tools-schema#252)

# Which file-level annotation field identifies which resourceType, per the NF metadata
# dictionary's FIELD_MAPPING.md. Order matters only for logging determinism.
FIELD_TO_RESOURCE_TYPE = {
    "individualID": "Cell Line",
    "modelSystemName": "Animal Model",
}

DEFAULT_MAX_WORKERS = 8  # concurrent threads for per-dataset Synapse queries; see module docstring
RATE_LIMIT_MAX_RETRIES = 4
RATE_LIMIT_BASE_DELAY_SECONDS = 1.0


def query_datasets(syn: Synapse, limit: int = None, dataset_ids: List[str] = None) -> "pd.DataFrame":
    """
    Query the Portal Dataset Collection for the per-dataset metadata that
    gets mirrored straight into Tool_Dataset rows once a match is found.

    If dataset_ids is given, restricts to just those dataset(s) instead of
    the full collection -- e.g. for reviewing newly-added datasets without
    re-mining ones that have already been reviewed and either matched or
    ruled out.
    """
    logger.info(f"Querying dataset collection {DATASET_COLLECTION_ID}...")

    query = (
        f"SELECT id, title, description, studyId, dataType, diseaseFocus "
        f"FROM {DATASET_COLLECTION_ID} WHERE id IS NOT NULL"
    )
    if dataset_ids:
        ids_clause = ", ".join(f"'{d}'" for d in dataset_ids)
        query += f" AND id IN ({ids_clause})"
    if limit:
        query += f" LIMIT {limit}"

    try:
        df = syn.tableQuery(query).asDataFrame()
        logger.info(f"Retrieved {len(df)} dataset(s) from {DATASET_COLLECTION_ID}")
        if dataset_ids and len(df) < len(set(dataset_ids)):
            found = set(df["id"]) if "id" in df.columns else set()
            missing = sorted(set(dataset_ids) - found)
            logger.warning(f"{len(missing)} requested dataset id(s) not found in {DATASET_COLLECTION_ID}: {missing}")
        return df
    except Exception as e:
        logger.error(f"Error querying dataset collection: {e}")
        raise


def _is_rate_limit_error(exc: Exception) -> bool:
    """True if exc is (or wraps) an HTTP 429 -- synapseclient's
    SynapseHTTPError subclasses requests.exceptions.HTTPError, which carries
    the original response on .response."""
    return getattr(getattr(exc, "response", None), "status_code", None) == 429


def _call_with_rate_limit_retry(func, *args, **kwargs):
    """
    Call func(*args, **kwargs), retrying with exponential backoff (plus
    jitter, to avoid every worker thread retrying in lockstep) on a 429 from
    Synapse. Any other exception propagates immediately -- only rate limits
    are worth retrying here, not e.g. a genuinely malformed query.
    """
    for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if not _is_rate_limit_error(e) or attempt == RATE_LIMIT_MAX_RETRIES:
                raise
            delay = RATE_LIMIT_BASE_DELAY_SECONDS * (2 ** attempt) + random.uniform(0, RATE_LIMIT_BASE_DELAY_SECONDS)
            logger.warning(f"Rate limited (429) -- retrying in {delay:.1f}s (attempt {attempt + 1}/{RATE_LIMIT_MAX_RETRIES})")
            time.sleep(delay)


def _unknown_column_from_error(exc: Exception, candidate_fields: List[str]) -> "str | None":
    """
    Synapse's query engine reports a missing column as a plain "Unknown
    column <name>" 400 -- parse that out so _query_one_dataset can drop just
    that field and retry, rather than treating any query failure as "this
    dataset has neither field."
    """
    text = str(exc)
    for field in candidate_fields:
        if f"Unknown column {field}" in text:
            return field
    return None


def _query_one_dataset(syn: Synapse, dataset_id: str, limit: int = None) -> Tuple[List[Dict], "str | None"]:
    """
    Query a single Dataset entity's own item table (a Dataset is itself
    queryable like any other Synapse table, over its constituent file
    items) for the distinct individualID/modelSystemName values used by its
    files -- whichever of the two columns that dataset actually has (this
    varies per dataset depending on which manifest template(s) its
    constituent files were annotated with, so it can't be assumed from one
    dataset to the next).

    Deliberately does NOT call getTableColumns first to discover which
    columns exist: that hits Synapse's /entity/{id}/column endpoint, which
    carries its own much stricter server-side throttle (confirmed live --
    "Allowed 6 requests every 60 seconds" -- independent of the 429 handling
    in _call_with_rate_limit_retry, since synapseclient retries that one
    internally with a blocking 30s sleep before it ever surfaces as an
    exception here) that a handful of concurrent worker threads trips
    almost immediately, making the parallel case *slower* than sequential.
    A Dataset's declared column list can also lag what its query engine will
    actually resolve (confirmed live: syn29654184 queried cleanly for
    modelSystemName despite getTableColumns not listing it), so querying
    directly is both faster and more correct. Instead, this just tries the
    combined query and narrows the SELECT list on an "Unknown column" error
    (see _unknown_column_from_error) until it either succeeds or has ruled
    out both fields -- one tableQuery call for the common case (a dataset
    with both fields, or the query engine resolving both), up to three for a
    dataset missing one or both.

    Runs on a worker thread via query_dataset_match_values's thread pool;
    has no side effects on shared state beyond issuing read-only Synapse
    queries, so it's safe to run concurrently across datasets.

    Returns (rows, error): rows is a list of {datasetId, field, value}
    dicts (possibly empty); error is None on success, or a short string
    describing why this dataset couldn't be queried at all (a genuine query
    failure unrelated to a missing column -- e.g. a stale column-size
    declaration on the dataset itself, confirmed live to affect whole
    batches of datasets sharing a schema, not just isolated one-offs).
    """
    remaining_fields = list(FIELD_TO_RESOURCE_TYPE)

    while remaining_fields:
        select_clause = ", ".join(remaining_fields)
        where_clause = " OR ".join(f"{c} IS NOT NULL" for c in remaining_fields)
        query = f"SELECT DISTINCT {select_clause} FROM {dataset_id} WHERE {where_clause}"
        if limit:
            query += f" LIMIT {limit}"

        try:
            df = _call_with_rate_limit_retry(lambda q=query: syn.tableQuery(q).asDataFrame())
        except Exception as e:
            missing_field = _unknown_column_from_error(e, remaining_fields)
            if missing_field:
                remaining_fields = [f for f in remaining_fields if f != missing_field]
                continue
            error = str(e).strip().splitlines()[-1] if str(e).strip() else str(e)
            logger.warning(f"Could not query dataset {dataset_id} for {remaining_fields}: {error}")
            return [], error

        rows = []
        for field in remaining_fields:
            if field not in df.columns:
                continue
            for value in df[field].dropna().unique():
                value = str(value).strip()
                if value:
                    rows.append({"datasetId": dataset_id, "field": field, "value": value})
        return rows, None

    return [], None


def query_dataset_match_values(
    syn: Synapse,
    dataset_ids: List[str],
    limit: int = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> Tuple["pd.DataFrame", List[Dict]]:
    """
    Fan _query_one_dataset out across a thread pool -- see module docstring
    for why this is safe and worthwhile (independent, read-only, I/O-bound
    per-dataset calls).

    Returns (match_values, failed_datasets):
    - match_values: a DataFrame with columns [datasetId, field, value], one
      row per distinct (dataset, field, value) triple.
    - failed_datasets: a list of {datasetId, error} dicts, one per dataset
      that couldn't be queried at all (as opposed to one that queried fine
      but simply had neither field) -- collected here rather than left as
      scattered per-dataset warnings, since these tend to cluster (e.g. a
      whole batch of datasets sharing the same stale column-size
      declaration, confirmed live) and a caller needs the full list to
      decide whether a schema fix is warranted.
    """
    rows = []
    failed_datasets = []
    total = len(dataset_ids)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dataset = {
            executor.submit(_query_one_dataset, syn, dataset_id, limit): dataset_id
            for dataset_id in dataset_ids
        }
        for future in as_completed(future_to_dataset):
            dataset_id = future_to_dataset[future]
            try:
                dataset_rows, error = future.result()
                rows.extend(dataset_rows)
                if error:
                    failed_datasets.append({"datasetId": dataset_id, "error": error})
            except Exception as e:
                logger.warning(f"Unexpected error mining dataset {dataset_id}: {e}")
                failed_datasets.append({"datasetId": dataset_id, "error": str(e)})

            completed += 1
            if completed % 25 == 0 or completed == total:
                logger.info(f"  ...queried {completed}/{total} dataset(s)")

    result = pd.DataFrame(rows, columns=["datasetId", "field", "value"])
    logger.info(f"Found {len(result)} distinct (dataset, field, value) occurrence(s) across {total} dataset(s)")
    if failed_datasets:
        logger.warning(f"{len(failed_datasets)}/{total} dataset(s) could not be queried at all -- see below")
        for failure in failed_datasets:
            logger.warning(f"  {failure['datasetId']}: {failure['error']}")
    return result, failed_datasets


def query_existing_tool_dataset_links(syn: Synapse) -> Set[tuple]:
    """
    Query the existing Tool_Dataset rows for (resourceId, id) pairs already
    recorded, so newly-mined associations can be de-duplicated against it.
    """
    logger.info(f"Querying existing links from {TOOL_DATASET_TABLE_ID}...")
    try:
        df = syn.tableQuery(f"SELECT resourceId, id FROM {TOOL_DATASET_TABLE_ID}").asDataFrame()
        existing = {(row.resourceId, row.id) for row in df.itertuples()}
        logger.info(f"Found {len(existing)} existing tool<->dataset link(s)")
        return existing
    except Exception as e:
        logger.warning(f"Could not query existing tool<->dataset links, treating as empty: {e}")
        return set()


def _match_lookups_for_resource_type(tools_data: List[Dict], resource_type: str) -> Tuple[Dict, Dict, Dict]:
    """
    Build review_tool_annotations' three matching tiers (exact resourceName,
    exact synonym, stripped-disambiguation-suffix fallback -- see that
    module's _build_resource_match_lookups docstring), restricted to tools
    of the given resourceType. Restricting first, rather than matching
    against every tool and checking resourceType after, keeps an
    individualID from ever being checked against an Animal Model (or vice
    versa) -- the two fields are documented as identifying different
    resourceTypes, not interchangeable identifiers.
    """
    filtered = [t for t in tools_data if t.get("resourceType") == resource_type]
    return rta._build_resource_match_lookups(filtered)


def find_tool_dataset_links(
    match_values: "pd.DataFrame",
    datasets: "pd.DataFrame",
    tools_data: List[Dict],
    existing_links: Set[tuple],
) -> List[Dict]:
    """
    For each (dataset, field, value) occurrence whose value matches a known
    tool of the resourceType that field identifies (see
    FIELD_TO_RESOURCE_TYPE), emit a Tool_Dataset candidate row carrying that
    dataset's metadata (title/description/studyId/dataType/diseaseFocus),
    filtered down to ones not already in TOOL_DATASET_TABLE_ID.
    """
    lookups_by_field = {
        field: _match_lookups_for_resource_type(tools_data, resource_type)
        for field, resource_type in FIELD_TO_RESOURCE_TYPE.items()
    }
    dataset_info_by_id = datasets.set_index("id").to_dict("index")

    new_links: Dict[tuple, Dict] = {}
    for row in match_values.itertuples():
        field = row.field
        lookups = lookups_by_field.get(field)
        if lookups is None:
            continue
        resource_by_name, resource_by_synonym, stripped_lookup = lookups

        tool = (
            resource_by_name.get(row.value)
            or resource_by_synonym.get(row.value)
            or stripped_lookup.get(row.value)
        )
        if not tool:
            continue

        dataset_id = row.datasetId
        key = (tool["resourceId"], dataset_id)
        if key in existing_links or key in new_links:
            continue

        dataset_info = dataset_info_by_id.get(dataset_id, {})
        new_links[key] = {
            "resourceId": tool["resourceId"],
            "resourceName": tool.get("resourceName"),
            "resourceType": tool.get("resourceType"),
            "id": dataset_id,
            "title": dataset_info.get("title"),
            "description": dataset_info.get("description"),
            "studyId": dataset_info.get("studyId"),
            "dataType": dataset_info.get("dataType"),
            "diseaseFocus": dataset_info.get("diseaseFocus"),
            "matchedField": field,
            "matchedVia": row.value,
        }

    logger.info(f"Found {len(new_links)} new tool<->dataset association(s) not already in {TOOL_DATASET_TABLE_ID}")
    return list(new_links.values())


# ---------------------------------------------------------------------------
# Human-review CSV (same review-then-apply policy as review_tool_annotations.py's
# tool<->study link mining -- see this repo's #246 review for why an
# individualID/modelSystemName match, even an "unambiguous within the tools
# registry" one, isn't a safe signal to write unattended).
# ---------------------------------------------------------------------------

def save_tool_dataset_links_for_review(links: List[Dict], path: Path) -> None:
    """Write mined tool<->dataset link candidates to a CSV. Not upserted."""
    if not links:
        return
    pd.DataFrame(links).to_csv(path, index=False)
    logger.info(f"Wrote {len(links)} tool<->dataset link candidate(s) to {path} for manual review")


def load_tool_dataset_links_from_review(path: Path) -> List[Dict]:
    """
    Read a (human-reviewed, possibly row-deleted) CSV written by
    save_tool_dataset_links_for_review back into the list-of-dicts shape
    upsert_tool_dataset_links expects.
    """
    df = pd.read_csv(path)
    # dataType round-trips through CSV as a Python-list literal string
    # (e.g. "['gene expression']"); Tool_Dataset.dataType is a STRING_LIST
    # column, so it must be restored to an actual list before upserting.
    if "dataType" in df.columns:
        import ast
        df["dataType"] = df["dataType"].apply(
            lambda v: ast.literal_eval(v) if isinstance(v, str) and v.startswith("[") else v
        )
    return df.to_dict("records")


def upsert_tool_dataset_links(syn: Synapse, links: List[Dict]) -> None:
    """
    Upsert newly-mined tool<->dataset associations directly into
    TOOL_DATASET_TABLE_ID. Additive only -- never modifies or removes any
    existing row. Only ever invoked from main() via
    --apply-tool-dataset-links-csv, against a CSV a human has reviewed (and
    possibly trimmed) -- see the module note above
    save_tool_dataset_links_for_review.

    Snapshots TOOL_DATASET_TABLE_ID immediately before and after the write
    (standing policy: every automated table/view write is bracketed by a
    snapshot on both sides, not just one).
    """
    if not links:
        logger.info("No new tool<->dataset links to upsert")
        return

    table_columns = {"resourceId", "id", "title", "description", "studyId", "dataType", "diseaseFocus"}
    rows = [{k: v for k, v in link.items() if k in table_columns} for link in links]
    df = pd.DataFrame(rows)

    snapshot_table(syn, TOOL_DATASET_TABLE_ID, f"Before upserting {len(rows)} new tool<->dataset link(s) (nf-research-tools-schema#252)")
    syn.store(synapseclient.Table(TOOL_DATASET_TABLE_ID, df))
    logger.info(f"Upserted {len(rows)} new tool<->dataset link(s) to {TOOL_DATASET_TABLE_ID}")
    snapshot_table(syn, TOOL_DATASET_TABLE_ID, f"After upserting {len(rows)} new tool<->dataset link(s) (nf-research-tools-schema#252)")


def main():
    parser = argparse.ArgumentParser(
        description="Mine tool<->dataset associations and populate syn16859448 (Tool_Dataset)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing the review CSV")
    parser.add_argument("--limit", type=int, help="Limit number of records queried per table (for testing)")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Concurrent threads for per-dataset Synapse queries (default: {DEFAULT_MAX_WORKERS})",
    )
    parser.add_argument(
        "--dataset-id",
        action="append",
        dest="dataset_ids",
        help=(
            "Limit mining to specific dataset id(s) (repeatable), e.g. to review "
            "newly-added datasets without re-scanning the whole collection. "
            "Default: scan the full Portal Dataset Collection."
        ),
    )
    parser.add_argument(
        "--apply-tool-dataset-links-csv",
        type=Path,
        help=(
            "Upsert tool<->dataset links from a human-reviewed CSV (see "
            "save_tool_dataset_links_for_review) instead of running the mining "
            "pipeline. This is the only way these get written to Synapse."
        ),
    )
    args = parser.parse_args()

    # All of this script's read path (tools view, dataset collection, and each
    # individual Dataset entity's own item table) is public -- confirmed live,
    # anonymous tableQuery succeeds against all of them. A SYNAPSE_AUTH_TOKEN is
    # only required for --apply-tool-dataset-links-csv, which writes to
    # syn16859448 and needs write permission on the NFRTC project.
    auth_token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if args.apply_tool_dataset_links_csv and not auth_token:
        logger.error("SYNAPSE_AUTH_TOKEN environment variable not set -- required to write to Synapse")
        sys.exit(1)

    try:
        syn = Synapse()
        if auth_token:
            syn.login(authToken=auth_token, silent=True)
            logger.info("Logged into Synapse")
        else:
            logger.info("No SYNAPSE_AUTH_TOKEN set -- querying anonymously (all source tables are public)")

        if args.apply_tool_dataset_links_csv:
            logger.info(f"\n=== Applying reviewed tool<->dataset links from {args.apply_tool_dataset_links_csv} ===")
            links = load_tool_dataset_links_from_review(args.apply_tool_dataset_links_csv)
            upsert_tool_dataset_links(syn, links)
            return

        logger.info("\n=== Querying Tools Data ===")
        tools_data = rta.query_tools_data(syn, limit=args.limit)

        logger.info("\n=== Querying Dataset Collection ===")
        datasets = query_datasets(syn, limit=args.limit, dataset_ids=args.dataset_ids)

        logger.info("\n=== Mining Per-Dataset individualID/modelSystemName Values ===")
        match_values, failed_datasets = query_dataset_match_values(
            syn, datasets["id"].tolist(), limit=args.limit, max_workers=args.workers
        )

        existing_links = query_existing_tool_dataset_links(syn)
        new_links = find_tool_dataset_links(match_values, datasets, tools_data, existing_links)

        review_path = Path("tool_dataset_links_for_review.csv")
        if new_links and not args.dry_run:
            save_tool_dataset_links_for_review(new_links, review_path)
        elif new_links:
            logger.info(f"Dry run -- found {len(new_links)} new tool<->dataset link candidate(s) (not written)")

        # Written unconditionally (even on --dry-run) since this is diagnostic
        # output about Synapse-side data quality, not a mining result -- per
        # feedback, a single count in the log isn't enough to act on (same
        # reasoning as review_tool_annotations.py's resource_id_skipped_full.csv).
        failed_datasets_path = Path("dataset_query_failures.csv")
        if failed_datasets:
            pd.DataFrame(failed_datasets).to_csv(failed_datasets_path, index=False)

        logger.info("\n=== Summary ===")
        logger.info(f"  Datasets scanned: {len(datasets)}")
        logger.info(f"  Datasets with query failures: {len(failed_datasets)}/{len(datasets)}" + (f" -- see {failed_datasets_path}" if failed_datasets else ""))
        logger.info(f"  individualID/modelSystemName occurrences found: {len(match_values)}")
        if new_links and not args.dry_run:
            logger.info(f"  {len(new_links)} new candidate(s) written to {review_path} -- review, then re-run with --apply-tool-dataset-links-csv")
        else:
            logger.info(f"  {len(new_links)} new candidate(s) found{' (dry run, not written)' if new_links else ''}")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
