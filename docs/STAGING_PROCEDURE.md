# Staging procedure for live Synapse table/MV changes

A repeatable version of the procedure worked out ad hoc in
[#261](https://github.com/nf-osi/nf-research-tools-schema/issues/261) for
staging a change to the tools search MaterializedView (`syn51730943`) and
the union chain that feeds it (`syn77019684/5/6` → `syn77019730` →
`syn51730943`). Use this for any change to that chain, or to a source
detail table (Biobank, CellLine, etc.) that the chain reads from — for
example the field-unification/rename work in
[#262](https://github.com/nf-osi/nf-research-tools-schema/issues/262).

Read the two gotchas below before starting; both caused real incidents.

## Gotchas to design around

1. **Union-branch-order + query-alias bugs** (root-caused in #247): a
   `UNION ALL`'s output schema only inherits `facetType` from its literal
   *first* branch, and any `SELECT src.col AS renamedCol` expression
   (rename, `CAST`, `COALESCE`) strips `facetType` regardless of union
   position. Only a bare `table.column AS column` (same name) reference
   preserves it. Route around this with direct `LEFT JOIN`s rather than
   trying to fix the union itself.
2. **CSV-based `STRING_LIST` writes don't explode into facets** (#266,
   open): `clean_submission_csvs.py`'s `upsert_to_synapse()` writes
   multi-valued columns via `Table(table_id, df)` + `syn.store()`, which
   produces one opaque combo-string facet value per row instead of
   exploding into per-element options. Only `PartialRowset`/`PartialRow`
   with native Python list values explode correctly. If your change adds
   or renames a multi-valued column that new submissions will write to,
   fix #266 first (or you'll reproduce the bug on day one of the new
   column).

Also: Synapse doesn't support altering a `ColumnModel`'s `facetType` in
place. Making a column facetable requires the deterministic swap pattern —
create a new `ColumnModel` via `POST /column` with the desired
`facetType`, swap `columnIds` on the table, write data back under the new
column ID — not an in-place edit.

## Never delete without explicit per-entity go-ahead

Every write in this procedure must go through `scripts/synapse_safety.py`'s
`safe_store()`/`safe_delete()` wrappers, not raw `syn.store()`/`syn.delete()`
calls — see that module's docstring for the incident that established this.
`safe_delete()` hard-fails unless `confirmed=True` is set immediately after
Belinda has explicitly approved deleting *that specific entity* in the
current conversation; never infer that from a general policy or a
different entity's approval.

## Procedure

### 1. Snapshot everything you're about to touch

```bash
# Every schema-mapped detail table
python scripts/snapshot_synapse_tables.py --from-schema \
    --comment "pre-migration snapshot for #<issue>"

# Plus any non-schema-mapped entities you'll edit, e.g. the union-chain MVs
python scripts/snapshot_synapse_tables.py \
    --table-id syn77019684 --table-id syn77019685 --table-id syn77019686 \
    --table-id syn77019730 --table-id syn51730943 \
    --comment "pre-migration snapshot for #<issue>"
```

This writes a `rollback_record_<date>.json` manifest (entity id, name,
`versionNumber`, `etag`, `columnIds`, and — for MaterializedViews —
`definingSQL`) and prints a markdown summary table. **Paste that summary
table into the tracking issue** so the pinned versions are on the record,
the way #261 did.

Rolling back a source **Table**: `syn.store()` a query/table reference
pinned to the recorded `versionNumber`.

Rolling back a **MaterializedView**: `safe_store()` the entity with
`definingSQL` reset to the exact text captured in the manifest.
`columnIds` are server-derived from `definingSQL` on store, so there's
nothing separate to restore for those. If a `definingSQL` restore doesn't
cleanly re-derive, **do not** fall back to delete+recreate — that caused
the production incident `synapse_safety.py` exists to prevent. Stop and
get explicit sign-off before attempting that path.

### 2. Pin the union chain to the snapshot versions

If your change touches source tables the union chain reads from, update
each `Group*` MV's `FROM` clause to reference the exact snapshotted
version (`FROM syn26486823.30 CL` style) instead of floating to latest, so
concurrent submissions during staging can't shift results out from under
you. Verify row counts and `facetType` state (via `getTableColumns()`)
are unchanged after pinning, before doing anything else.

### 3. Build a staging spine + MV reproducing the intended design

Create new, throwaway `STAGING_*` entities (spine query + MV) that
implement the target change — new/renamed columns, new joins, whatever
#262-style migration you're doing — **without touching production**.

### 4. Verify against the staging entities

Confirm every intended facet column shows `facetType: enumeration` via
`getTableColumns()`, and that every resourceType that's supposed to get
data on a given facet actually does, before touching `syn51730943`.

### 5. Apply to production

`safe_store()` the real MV (`syn51730943`) with the verified `definingSQL`.
Before applying, diff the new column list against anything with an
external dependency — e.g. check
[synapse-web-monorepo#3103](https://github.com/Sage-Bionetworks/synapse-web-monorepo/pull/3103)'s
card-label column references still resolve. Confirm row count is
unchanged before/after (a changed row count on an MV edit that shouldn't
affect row count is a sign something's wrong).

### 6. Trigger a search reindex

There's no known Synapse API to directly trigger a reindex. The workaround
used in #261: make a trivial no-op edit to the downstream SearchIndex
entity's `definingSQL` (e.g. an extra space), wait ~45s, then revert to
the exact original text. Spot-check the portal UI afterward — there's no
API to confirm the rebuild completed.

### 7. If something breaks

1. Restore each touched entity per the "Rolling back" notes in step 1,
   working from the `rollback_record_<date>.json` manifest.
2. Re-verify `getTableColumns()` facetType state matches the pre-change
   baseline recorded in that manifest.
3. If a `definingSQL` restore doesn't cleanly re-derive: stop, don't
   delete+recreate, get explicit sign-off (see step 1).

## Reference: full worked example

#261 is a complete worked run of this procedure end to end, including the
verbatim pre-change `definingSQL` for every entity in the chain and the
final per-resourceType facet-coverage table. Useful as a template for what
the tracking-issue comments should look like.
