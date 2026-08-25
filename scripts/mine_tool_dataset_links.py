#!/usr/bin/env python3
"""
Mine tool<->dataset associations and populate syn16859448 (Tool_Dataset).

nf-research-tools-schema#252: the Tool Details "Data" tab's file-level
Resource_id tagging (#154/#246) and tool<->study junction table (#132/#245)
don't let the frontend answer "which datasets is this tool used in?" --
Tool_Dataset (syn16859448) is a new junction table meant to do that
directly, joinable straight against the Portal Dataset Collection
(syn50913342) the frontend already renders dataset cards from.

Per issue #252's discussion and the NF metadata dictionary's
FIELD_MAPPING.md, a Dataset entity's constituent files identify their
resource via one of two fields (Tool_Dataset's own Synapse description
scopes this to "animal models and cell lines only"):
    - `individualID`      -> Cell Line donor
    - `modelSystemName`   -> Animal Model genetic background

Neither field is exposed at the dataset-collection level (syn50913342) with
useful coverage, and a file's Dataset membership is defined by the Dataset
entity's own item list, not its parentId -- so unlike the file-annotation
mining in review_tool_annotations.py (which reads one shared fileview),
this has to query each Dataset entity individually as a table over its own
constituent items.

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

Usage:
    python mine_tool_dataset_links.py [--dry-run] [--limit LIMIT]
    python mine_tool_dataset_links.py --apply-tool-dataset-links-csv tool_dataset_links_for_review.csv
"""

import argparse
import logging
import os
import sys
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


def query_datasets(syn: Synapse, limit: int = None) -> "pd.DataFrame":
    """
    Query the Portal Dataset Collection for the per-dataset metadata that
    gets mirrored straight into Tool_Dataset rows once a match is found.
    """
    logger.info(f"Querying dataset collection {DATASET_COLLECTION_ID}...")

    query = (
        f"SELECT id, title, description, studyId, dataType, diseaseFocus "
        f"FROM {DATASET_COLLECTION_ID} WHERE id IS NOT NULL"
    )
    if limit:
        query += f" LIMIT {limit}"

    try:
        df = syn.tableQuery(query).asDataFrame()
        logger.info(f"Retrieved {len(df)} dataset(s) from {DATASET_COLLECTION_ID}")
        return df
    except Exception as e:
        logger.error(f"Error querying dataset collection: {e}")
        raise


def _available_match_columns(syn: Synapse, dataset_id: str) -> List[str]:
    """
    Which of individualID/modelSystemName this specific Dataset entity's own
    item table actually has -- these vary per dataset depending on which
    manifest template(s) its constituent files were annotated with, so this
    can't be assumed from one dataset to the next.
    """
    try:
        column_names = {c["name"] for c in syn.getTableColumns(dataset_id)}
    except Exception as e:
        logger.warning(f"Could not get columns for dataset {dataset_id}: {e}")
        return []
    return [field for field in FIELD_TO_RESOURCE_TYPE if field in column_names]


def query_dataset_match_values(syn: Synapse, dataset_ids: List[str], limit: int = None) -> "pd.DataFrame":
    """
    For each dataset, query its own item table (a Dataset entity is itself
    queryable like any other Synapse table, over its constituent file
    items) for the distinct individualID/modelSystemName values used by its
    files -- whichever of the two columns that dataset actually has.

    Returns a DataFrame with columns [datasetId, field, value], one row per
    distinct (dataset, field, value) triple.
    """
    rows = []
    for i, dataset_id in enumerate(dataset_ids, start=1):
        match_columns = _available_match_columns(syn, dataset_id)
        if not match_columns:
            continue

        select_clause = ", ".join(match_columns)
        where_clause = " OR ".join(f"{c} IS NOT NULL" for c in match_columns)
        query = f"SELECT DISTINCT {select_clause} FROM {dataset_id} WHERE {where_clause}"
        if limit:
            query += f" LIMIT {limit}"

        try:
            df = syn.tableQuery(query).asDataFrame()
        except Exception as e:
            logger.warning(f"Could not query dataset {dataset_id} for {match_columns}: {e}")
            continue

        for field in match_columns:
            if field not in df.columns:
                continue
            for value in df[field].dropna().unique():
                value = str(value).strip()
                if value:
                    rows.append({"datasetId": dataset_id, "field": field, "value": value})

        if i % 25 == 0:
            logger.info(f"  ...queried {i}/{len(dataset_ids)} dataset(s)")

    result = pd.DataFrame(rows, columns=["datasetId", "field", "value"])
    logger.info(f"Found {len(result)} distinct (dataset, field, value) occurrence(s) across {len(dataset_ids)} dataset(s)")
    return result


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
        "--apply-tool-dataset-links-csv",
        type=Path,
        help=(
            "Upsert tool<->dataset links from a human-reviewed CSV (see "
            "save_tool_dataset_links_for_review) instead of running the mining "
            "pipeline. This is the only way these get written to Synapse."
        ),
    )
    args = parser.parse_args()

    auth_token = os.environ.get("SYNAPSE_AUTH_TOKEN")
    if not auth_token:
        logger.error("SYNAPSE_AUTH_TOKEN environment variable not set")
        sys.exit(1)

    try:
        syn = Synapse()
        syn.login(authToken=auth_token)
        logger.info("Logged into Synapse")

        if args.apply_tool_dataset_links_csv:
            logger.info(f"\n=== Applying reviewed tool<->dataset links from {args.apply_tool_dataset_links_csv} ===")
            links = load_tool_dataset_links_from_review(args.apply_tool_dataset_links_csv)
            upsert_tool_dataset_links(syn, links)
            return

        logger.info("\n=== Querying Tools Data ===")
        tools_data = rta.query_tools_data(syn, limit=args.limit)

        logger.info("\n=== Querying Dataset Collection ===")
        datasets = query_datasets(syn, limit=args.limit)

        logger.info("\n=== Mining Per-Dataset individualID/modelSystemName Values ===")
        match_values = query_dataset_match_values(syn, datasets["id"].tolist(), limit=args.limit)

        existing_links = query_existing_tool_dataset_links(syn)
        new_links = find_tool_dataset_links(match_values, datasets, tools_data, existing_links)

        review_path = Path("tool_dataset_links_for_review.csv")
        if new_links and not args.dry_run:
            save_tool_dataset_links_for_review(new_links, review_path)
        elif new_links:
            logger.info(f"Dry run -- found {len(new_links)} new tool<->dataset link candidate(s) (not written)")

        logger.info("\n=== Summary ===")
        logger.info(f"  Datasets scanned: {len(datasets)}")
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
