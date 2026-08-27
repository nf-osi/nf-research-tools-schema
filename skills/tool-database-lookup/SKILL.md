---
name: tool-database-lookup
description: >
  Reference for looking up a single tool/resource record on the live NF
  Research Tools Central Synapse tables — e.g. checking whether a tool
  from an nf.synapse.org Explore/Tools/{id}/Details URL exists in the
  database, and what's actually filled in for it. Use when asked "is
  there info about this tool" for a specific ID, or when auditing a
  record's completeness/link data (publications, development, usage).
---

# Tool database lookup

The NF Data Portal's Explore Tools detail page URL is
`https://nf.synapse.org/Explore/Tools/{resourceId}/Details` — that `{id}`
is a **`resourceId` UUID**, not a Synapse entity ID (`syn...`). It won't
be findable via `syn.get()`; you have to query the resource tables
directly with `synapseclient`.

## Table map (live Synapse tables, not this repo's local files)

There's no single base "Resource" table anymore (retired in the
2026-08 LinkML migration — see `docs/MIGRATION.md`); each tool type has
its own table, keyed by `resourceId`:

| Tool type | Synapse table |
|---|---|
| Animal Model | `syn26486808` |
| Antibody | `syn26486811` |
| Biobank | `syn26486821` |
| Cell Line | `syn26486823` |
| Genetic Reagent | `syn26486832` |
| Computational Tool | `syn73709226` |
| Organoid Protocol | `syn73709227` |
| Patient-Derived Model | `syn73709228` |
| Clinical Assessment Tool | `syn73709229` |

Shared/junction tables, also keyed by `resourceId` (not by a `Resource`
FK):

| Table | Synapse table | Columns |
|---|---|---|
| Donor | `syn26486829` | `donorId` (join via the tool row's `donorId`, not `resourceId`) |
| Development links | `syn26486807` | `resourceId`, `investigatorId`, `publicationId`, `funderId` |
| Usage links | `syn26486841` | `resourceId`, `publicationId` |
| Publications | `syn26486839` | `publicationId` (join via development/usage links, not directly by `resourceId`) |

`syn26450069` is the legacy `Resource` table annotation left on the
LinkML `Tool` abstract class — it's stale/retired data (Phase-1
snapshot), don't query it for current info (see #242 in this repo).

## How to look up an ID

1. `python3 -c "import synapseclient; syn = synapseclient.Synapse(); syn.login(silent=True)"` — uses cached local credentials if already logged in via the `synapse` CLI.
2. Query each of the 9 type tables above with
   `SELECT * FROM {table} WHERE resourceId = '{id}'` until you get a
   hit (a resourceId only exists in exactly one type table).
3. Once you know the type and have the row, follow any FK columns
   (e.g. `donorId`) into their own tables, and check
   `syn26486807`/`syn26486841` for linked publications/development/usage
   context.
4. Also grep this repo's `submissions/`, `tool_reviews/`, and
   `tool_coverage/` for the ID — a record with no local trace was likely
   auto-mined and never went through manual review.

## Interpreting what you find

A row with only `resourceName` (often an auto-generated placeholder
like "`{tissue} {category}`"), a couple of enum fields, and everything
else (RRID, description, `aiSummary`, dates, usage requirements,
how-to-acquire) empty is a **stub** — auto-mined but never curated. Report
it as such rather than treating a sparse record as "no information."
