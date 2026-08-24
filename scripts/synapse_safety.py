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
    """
    resolved_id = table_id or _resolve_table_id(table_or_entity)
    snapshot_table(syn, resolved_id, f"{comment} -- before")
    result = syn.store(table_or_entity)
    snapshot_table(syn, resolved_id, f"{comment} -- after")
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
