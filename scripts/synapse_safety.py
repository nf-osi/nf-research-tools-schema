#!/usr/bin/env python3
"""
Shared safety wrappers for scripts that write to or delete Synapse entities.

Standing policy, established 2026-08 after an automated MV rebuild
accidentally trashed live production entities:

1. Every table/view write is snapshotted immediately before AND after,
   independent of Synapse's trash can, so any automated change is
   recoverable without relying on undo/trash-restore.
2. No Synapse entity is ever deleted by automation without an explicit,
   per-entity confirmation that traces back to Belinda's actual permission
   for THAT entity -- never inferred, never batch-applied.

Any script that calls syn.store() on a Table/EntityView, or syn.delete()
on any entity, should go through safe_store()/safe_delete() here instead of
calling the raw synapseclient methods directly.
"""

import logging

logger = logging.getLogger(__name__)


class DeletionNotConfirmedError(RuntimeError):
    """
    Raised when safe_delete() is called without confirmed=True.

    This is not a prompt or a warning -- it's a hard stop. Seeing this
    error means the calling code was about to delete a Synapse entity
    without the caller having deliberately set confirmed=True, which must
    only ever be set immediately after Belinda has explicitly granted
    permission for THIS SPECIFIC entity in the current conversation. Never
    set confirmed=True based on inferred authorization, a policy written
    for a different entity, or "this seems obviously fine to clean up."
    """


def snapshot_table(syn, table_id: str, comment: str):
    """
    Create a snapshot version of a table/view. Best-effort: a snapshot
    failure is logged, not raised, so a snapshotting hiccup never blocks
    (or gets blocked by) the write/delete it's bracketing.

    Returns the snapshot version number, or None if snapshotting failed.
    """
    try:
        v = syn.create_snapshot_version(table_id, comment=comment)
        version = v.get('snapshotVersionNumber', v) if isinstance(v, dict) else v
        logger.info(f"Snapshotted {table_id} as version {version} ({comment})")
        return version
    except Exception as e:
        logger.warning(f"Could not snapshot {table_id}: {e}")
        return None


def _resolve_table_id(table_or_entity) -> str:
    """Best-effort extraction of the table/view id a synapseclient Table/
    Schema/EntityView object targets, across the attribute names different
    synapseclient constructs use."""
    for attr in ('tableId', 'schema', 'id'):
        value = getattr(table_or_entity, attr, None)
        if value:
            return value if isinstance(value, str) else str(value)
    raise ValueError(
        f"Could not determine a table/view id from {table_or_entity!r} -- "
        f"pass table_id explicitly to safe_store()."
    )


def safe_store(syn, table_or_entity, comment: str, table_id: str = None):
    """
    Wraps syn.store() for a Table/Schema/EntityView write with mandatory
    before/after snapshotting (policy #1 above).

    Args:
        syn: Synapse client
        table_or_entity: a synapseclient Table (or similar) ready to store
        comment: human-readable description of the write, used as the
            snapshot comment (suffixed with " -- before"/" -- after")
        table_id: the table/view id being written to. Inferred from
            table_or_entity if omitted (see _resolve_table_id) -- pass it
            explicitly if that inference might be wrong for your object.

    Returns whatever syn.store() returns.

    Note: the pre-write snapshot bumps the target entity's version/etag
    server-side. For a freshly-constructed Table(table_id, df) or
    PartialRowset -- no etag baggage -- this is harmless. But if
    table_or_entity is a *fetched* Schema/Entity object you mutated in
    place (e.g. syn.get(table_id) then edited .columnIds), its etag is
    now stale and syn.store() below would fail with "updated since you
    last fetched" -- so this refreshes .etag from the server after the
    snapshot, immediately before storing, whenever the object has one.

    Does NOT correctly handle a row-level patch (a Table(table_id, df)
    whose df carries ROW_ID/ROW_VERSION, i.e. an update to existing rows
    rather than an insert): Synapse's row-update endpoint checks
    `.etag` against the *query RowSet's own changeset etag* (from
    tableQuery(...).etag), not the table entity's etag -- refreshing to
    the entity's etag here, as this function does, gets a value the
    endpoint will reject with "Invalid etag" even though it's genuinely
    current. Use safe_store_row_patch() for that case instead (confirmed
    live against nf-research-tools-schema#306's DevelopmentRecord fix,
    2026-08-27 -- see that function's docstring for the full story).
    """
    resolved_id = table_id or _resolve_table_id(table_or_entity)
    snapshot_table(syn, resolved_id, f"{comment} -- before")
    if hasattr(table_or_entity, "etag"):
        try:
            table_or_entity.etag = syn.get(resolved_id, downloadFile=False).etag
        except Exception as e:
            logger.warning(f"Could not refresh etag for {resolved_id} before store: {e}")
    result = syn.store(table_or_entity)
    snapshot_table(syn, resolved_id, f"{comment} -- after")
    return result


def safe_store_row_patch(syn, table_id: str, build_patch, comment: str):
    """
    Safely apply a row-level patch (a Table(table_id, df) update where df
    carries ROW_ID/ROW_VERSION for existing rows) -- the case safe_store()
    above cannot handle correctly.

    Background: synapseclient's row-update path (CsvFileTable._update_self
    -> Synapse._uploadCsv(updateEtag=...)) requires the etag of the
    tableQuery() RowSet that read those exact rows, not the table entity's
    own etag from syn.get(). And ANY entity modification between that read
    and the store -- including a snapshot -- invalidates that RowSet
    etag, so "read, then snapshot, then store with the etag you already
    had" always fails with "Invalid etag", no matter how current the
    entity's own etag looks at that moment.

    So the order here is deliberately snapshot -> read -> store, not
    read -> snapshot -> store:

    Args:
        syn: Synapse client
        table_id: the table being patched
        build_patch: callable(syn) -> a synapseclient.Table ready to
            store, built from a *fresh* tableQuery() run inside this
            callback (after the before-snapshot below, not before it),
            with `.etag` set from that query result's own `.etag` --
            or None if there's nothing to patch (skips the store, but
            the before-snapshot has already happened, which is harmless)
        comment: human-readable description, used as the snapshot
            comment (suffixed with " -- before"/" -- after")

    Returns whatever syn.store() returns, or None if build_patch
    returned None.

    Confirmed live against nf-research-tools-schema#306's
    DevelopmentRecord investigatorId/funderId fix (2026-08-27): the
    entity-etag-refresh path in safe_store() failed with "Invalid etag"
    on every attempt, including immediately after a fresh snapshot --
    because it was refreshing to the wrong kind of etag, not because the
    value was stale. Re-querying after the snapshot and using that
    query's own .etag fixed it on the first try.
    """
    snapshot_table(syn, table_id, f"{comment} -- before")
    table_or_entity = build_patch(syn)
    if table_or_entity is None:
        logger.info(f"{table_id}: build_patch found nothing to patch, skipping store")
        return None
    result = syn.store(table_or_entity)
    snapshot_table(syn, table_id, f"{comment} -- after")
    return result


def safe_delete(syn, entity_id: str, confirmed: bool = False, reason: str = ""):
    """
    Wraps syn.delete(). Refuses to run unless confirmed=True is explicitly
    passed (policy #2 above) -- see DeletionNotConfirmedError's docstring
    for what "explicitly" means here.

    Args:
        syn: Synapse client
        entity_id: the Synapse entity id to delete
        confirmed: must be True, set only immediately after Belinda has
            granted permission for this specific entity in this
            conversation. Defaults to False so an accidental/copy-pasted
            call fails safe.
        reason: short note on why this entity is being deleted (logged,
            not enforced) -- for the audit trail.
    """
    if not confirmed:
        raise DeletionNotConfirmedError(
            f"Refusing to delete {entity_id}: safe_delete() requires "
            f"confirmed=True, which must only be set after explicit, "
            f"individual permission from Belinda for THIS entity. Never "
            f"infer this from a general policy or a different entity's "
            f"approval."
        )
    logger.warning(f"Deleting {entity_id} (explicitly confirmed){f' -- {reason}' if reason else ''}")
    syn.delete(entity_id)
