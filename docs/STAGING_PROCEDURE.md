# Staging procedure for live Synapse table/MV changes

A repeatable version of the procedure worked out ad hoc in
[#261](https://github.com/nf-osi/nf-research-tools-schema/issues/261) for
staging a change to the tools search MaterializedView (`syn51730943`) and
the union chain that feeds it (`syn77019684/5/6` → `syn77019730` →
`syn51730943`). Use this for any change to that chain, or to a source
detail table (Biobank, CellLine, etc.) that the chain reads from — for
example the field-unification/rename work in
[#262](https://github.com/nf-osi/nf-research-tools-schema/issues/262).

Read the gotchas below before starting; all five caused real incidents.

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

3. **Pinned `FROM`/`JOIN` clauses silently rot, and there are more of
   them than the union chain** (found 2026-08-26, after sitting broken
   since #261): step 2 below pins `Group0/1/2`'s `FROM` clauses during
   staging, but `syn51730943` (FinalMV) *also* reads several facet
   columns via its own **direct, independently version-pinned `LEFT
   JOIN`s** that bypass the union chain entirely (the #247 workaround —
   see gotcha 1). As of 2026-08-26 these are:
   - FinalMV's own `JOIN`s: `syn26486808` (AnimalModel → `animalState`),
     `syn26486832` (GeneticReagent → `vectorType`), `syn26486811`
     (Antibody → `targetAntigen`), `syn73709226` (ComputationalTool →
     `softwareType`), `syn73709229` (ClinicalAssessmentTool, currently
     unused in the SELECT list).
   - Four dedicated single-column helper MVs, each its *own*
     `UNION ALL` across several source tables, each branch
     independently version-pinned: `syn77130552` (`tissue`, from
     Biobank + CellLine's `tissueList` mirror — see gotcha 5),
     `syn77130553` (`manifestation`, from CellLine/AnimalModel/
     Biobank/PatientDerivedModel), `syn77130554` (`modelType`, from
     OrganoidProtocol/PatientDerivedModel), `syn77130555`
     (`availability`, from all 9 detail tables).

   **Every one of these pins needs unpinning in step 2b below, not just
   the 3 `Group*` MVs** — missing any of them means some columns keep
   serving stale data indefinitely while everything else looks fixed.
   Grep the *entire* chain for `\.\d+ ` (a versioned table reference)
   before considering a migration done, not just the 3 entities you
   remember pinning.

4. **An MV doesn't recompute just because an upstream MV's `definingSQL`
   changed — even after unpinning** (found alongside gotcha 3):
   `syn51730943` kept serving stale values for a full pin-removal cycle
   even though `syn77019730` (Union) and the helper MVs immediately
   below it were verifiably correct on direct query. Fix: after
   unpinning, force a recompute of the *specific* MV that's still
   stale with a trivial no-op edit to its own `definingSQL` (see step
   6's search-reindex trick — the same technique, but here it's for
   the MV's own materialization, not the downstream search index) —
   then verify with an exact-value Python-side check (`x == 'the old
   value'`, not a SQL `WHERE`, since Synapse string comparison is
   case-insensitive and will silently match the fixed value too). If a
   nested chain (helper MV → FinalMV) is still stale after unpinning
   the helper MV, you likely need to touch *both* levels — fix the
   helper MV's data/pins first, verify the helper MV directly, then
   separately force FinalMV's own recompute.

5. **A "unified" facet column can have its own separate mirror column
   with a different name, decoupled from the field you think you're
   editing** (found 2026-08-26): `CellLine.tissue` (the real, primary
   LinkML slot) and `CellLine.tissueList` (a `STRING_LIST` mirror
   created ad hoc during the #247/#259/#261 facet work, feeding the
   `syn77130552` helper MV above) are two *different* Synapse columns
   holding the same information in different shapes. Fixing data on
   `tissue` does not touch `tissueList`, and vice versa — before
   declaring a data fix complete, check `getTableColumns()` for every
   table you touched for a same-concept `<field>List`-style sibling
   column, and check every helper MV in gotcha 3 for which literal
   column name each branch actually reads.

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

**Pin every entity in gotcha 3's list that your staging touches, not
just `Group0/1/2`** — write down every `syn` ID + version you pin, in
the tracking issue, so step 2b can find and reverse all of them later.

### 2b. Unpin everything once staging is done — don't skip this

This is the step that got skipped after #261 and stayed broken for a
full day of subsequent work (#272, #278, #282's data fixes were all
invisible on the live portal until 2026-08-26). Pinning is a
*temporary* concurrency guard for the duration of active staging, not
a permanent state. Once your change is verified and applied to
production (step 5):

1. Remove the version pin (`.N` suffix) from every `FROM`/`JOIN` you
   pinned in step 2 — restore the bare `syn<id> alias` form so it
   floats to latest again. A regex like
   `re.sub(r'(FROM\s+syn\d+)\.\d+(\s+\w+)', r'\1\2', sql)` (and the
   equivalent for `JOIN`) does this safely across a whole
   `definingSQL` string.
2. Verify row counts and `facetType` are unchanged after unpinning
   (same check as step 2).
3. Force a recompute per gotcha 4, then verify with an **exact-value,
   case-sensitive** check (Python `==`, not SQL `WHERE`) that the
   specific value(s) your change was supposed to fix are actually
   gone from `syn51730943` — not just that the pin was removed.
4. Grep the full chain once more for `\.\d+ ` before considering the
   migration closed.

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
