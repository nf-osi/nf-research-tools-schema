#!/usr/bin/env python3
"""
Delete duplicate Mutation junction rows tracked in #189 (#165, #173).

The Mutation junction table (syn26486834) has exactly 3 columns:
mutationId, mutationDetailsId, resourceId. Checked live (2026-08-24) for
rows sharing the same (resourceId, mutationDetailsId) pair -- i.e. the
identical mutation instance recorded on the identical resource -- under
more than one mutationId:

  41 duplicate (resourceId, mutationDetailsId) groups (40 pairs + 1 triple)
  83 total rows involved
  42 rows to delete, keeping exactly 1 (the lowest mutationId) per group

Because the table has ONLY those 3 columns, "only mutationId differs" is
guaranteed by the schema itself for any (resourceId, mutationDetailsId)
duplicate -- there is no other column that could differ. Per Belinda's
2026-08-24 confirmation on #189 ("yes if truly only mutationId differs
then keep the lowest mutationId per group and delete the rest, snapshotting
before & after"), this keeps the row with the lexicographically lowest
mutationId per group (mutationId is a UUID, not sequential -- there's no
data-driven reason to prefer one over another, so lowest-string is an
arbitrary but stable, reproducible tiebreaker) and deletes the rest.

EDGE CASE found during dry-run review (2026-08-24): 2 of the 41 groups
(resourceId f53bdbc7-211a-44c1-9950-f026df094d62, mutationDetailsId
2a86a4da-... and c33eaa9c-...) are not just "same (resourceId,
mutationDetailsId), different mutationId" -- they're exact full-row
duplicates, the SAME mutationId appearing on two distinct physical Synapse
rows (confirmed via ROW_ID: 1689_28/1730_28 and 1690_28/1731_28). Deleting
by "WHERE mutationId IN (...)" would therefore delete BOTH physical copies
of those two mutationIds instead of exactly one -- so this script targets
rows to delete by their own Synapse ROW_ID (captured from the initial
query's index), not by mutationId value, which is correct and unambiguous
regardless of any value collisions like this one.

This is a genuine row deletion, not a value correction -- unlike the other
fix scripts this session (#210, #255), which only insert/update rows. Per
standing policy (scripts/synapse_safety.py's safe_delete/
DeletionNotConfirmedError, and the equivalent auto-mode policy), deletion
is never run without an explicit, in-conversation, per-run confirmation --
this script refuses to execute live (even outside --dry-run) unless
--confirm-delete is also passed, and prints the full before-state of every
row it's about to delete either way.

#165's and #173's own cited resourceIds (0f404e70-..., fc3ae45e-...) do not
appear in this table at all today -- not fixed, just absent (see #189
comment thread; possibly predates the Phase 5 resourceId-consolidation
migration). Not chased further here.
"""

import logging
import sys

import synapseclient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MUTATION_TABLE = 'syn26486834'


def snapshot_table(syn, table_id, comment):
    """Local copy of the shared snapshot helper (scripts/synapse_safety.py,
    not yet on main as of this script -- see #246). Best-effort: a snapshot
    failure is logged, not raised."""
    try:
        v = syn.create_snapshot_version(table_id, comment=comment)
        version = v.get('snapshotVersionNumber', v) if isinstance(v, dict) else v
        logger.info(f"Snapshotted {table_id} as version {version} ({comment})")
        return version
    except Exception as e:
        logger.warning(f"Could not snapshot {table_id}: {e}")
        return None


def find_duplicate_groups(syn):
    """
    Returns (df, groups_summary, row_ids_to_delete) where:
      - df: the full Mutation table as a DataFrame, "rowId_rowVersion"
        index (rowIdAndVersionInIndex=True)
      - groups_summary: list of dicts, one per duplicate
        (resourceId, mutationDetailsId) group: resourceId,
        mutationDetailsId, keptMutationId, keptRowId, deletedMutationIds,
        deletedRowIds
      - row_ids_to_delete: flat list of ROW_ID (int) to delete, identified
        by row POSITION within each group (lowest mutationId kept), not by
        mutationId value -- safe even when two physical rows share the
        same mutationId (see module docstring).
    """
    df = syn.tableQuery(
        f"SELECT mutationId, mutationDetailsId, resourceId FROM {MUTATION_TABLE}"
    ).asDataFrame(rowIdAndVersionInIndex=True)

    groups_summary = []
    row_ids_to_delete = []
    for (resource_id, mutation_details_id), group in df.groupby(['resourceId', 'mutationDetailsId']):
        if len(group) <= 1:
            continue
        sorted_group = group.sort_values('mutationId')
        kept_label = sorted_group.index[0]
        deleted_rows = sorted_group.iloc[1:]
        deleted_row_ids = [int(str(label).split('_')[0]) for label in deleted_rows.index]
        row_ids_to_delete.extend(deleted_row_ids)
        groups_summary.append({
            'resourceId': resource_id,
            'mutationDetailsId': mutation_details_id,
            'keptMutationId': sorted_group.iloc[0]['mutationId'],
            'keptRowLabel': kept_label,
            'deletedMutationIds': deleted_rows['mutationId'].tolist(),
            'deletedRowLabels': deleted_rows.index.tolist(),
        })

    return df, groups_summary, row_ids_to_delete


def main():
    dry_run = '--dry-run' in sys.argv
    confirm_delete = '--confirm-delete' in sys.argv

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    print('\n=== #189: Mutation (syn26486834) duplicate (resourceId, mutationDetailsId) rows ===')
    df, groups_summary, row_ids_to_delete = find_duplicate_groups(syn)

    print(f'  {len(groups_summary)} duplicate group(s), {len(row_ids_to_delete)} row(s) to delete')
    for g in groups_summary:
        same_value_note = ' [SAME mutationId value as kept row -- exact full-row duplicate]' if g['keptMutationId'] in g['deletedMutationIds'] else ''
        print(
            f"    resourceId={g['resourceId']} mutationDetailsId={g['mutationDetailsId']}: "
            f"keep {g['keptMutationId']} ({g['keptRowLabel']}), "
            f"delete {list(zip(g['deletedMutationIds'], g['deletedRowLabels']))}{same_value_note}"
        )

    if not row_ids_to_delete:
        print('  Nothing to do.')
        return

    if dry_run:
        print(f'\n  Dry run -- would delete {len(row_ids_to_delete)} row(s) by ROW_ID. Not writing.')
        return

    if not confirm_delete:
        print(
            f'\n  REFUSING to delete {len(row_ids_to_delete)} row(s) without --confirm-delete. '
            f'This flag must only be passed immediately after Belinda has explicitly reviewed '
            f'the exact group/row list above (in this run, not a prior one) and confirmed '
            f'it in the current conversation -- never inferred from a general policy.'
        )
        sys.exit(1)

    snapshot_table(syn, MUTATION_TABLE, f'Before #189 duplicate-mutation-row deletion ({len(row_ids_to_delete)} rows)')

    ids_csv = ', '.join(str(i) for i in row_ids_to_delete)
    delete_query_result = syn.tableQuery(f"SELECT * FROM {MUTATION_TABLE} WHERE ROW_ID IN ({ids_csv})")
    syn.delete(delete_query_result)
    print(f'  Deleted {len(row_ids_to_delete)} row(s).')

    snapshot_table(syn, MUTATION_TABLE, f'After #189 duplicate-mutation-row deletion ({len(row_ids_to_delete)} rows)')


if __name__ == '__main__':
    main()
