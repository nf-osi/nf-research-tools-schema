# Production MaterializedViews (NFRTC project, syn26338068)

Living reference of every MaterializedView (MV) in the NFRTC Synapse
project that's an actual production dependency, what it's for, and how
they chain together. Last audited 2026-08-27 (see that date's entry in
`SESSION_LOG.md` for how — a full `definingSQL` cross-reference across
every MV in the project, not just a name-based read).

**For the procedure to safely change any of these** (staging a change,
pinning versions, forcing a recompute, rolling back), see
`STAGING_PROCEDURE.md` — this doc is what/why, that doc is how.

## The hub: the tools search MV

Everything below ultimately feeds **`syn51730943`**
(`Resource_CellLine_AnimalModel_GeneticReagent_Antibody_Biobank_Development_Funder_Donor_Investigator`,
called "FinalMV" in `STAGING_PROCEDURE.md`) — the flattened, one-row-per-`resourceId`
view that OpenSearch indexes to power the NF Data Portal's Explore Tools
search and facets. If you're trying to find "the MV that drives the
portal," it's this one.

## Dependency graph

```
AllTools_Group0 (syn77019684) ─┐
AllTools_Group1 (syn77019685) ─┼→ AllTools_Union (syn77019730) ─┐
AllTools_Group2 (syn77019686) ─┘                                │
                                                                 │
AnimalModel_Donor (syn51735412) ─┐                               │
CellLine_Donor (syn51735403) ────┴→ CellLine_AnimalModel_Donor  │
                                     (syn51735419) ──────────────┼→ syn51730943 (FinalMV)
Development_Investigator (syn51734029) ──────────────────────────┤   │
                                                                  │   │
Usage_Publication (syn51735450) → LastPublicationDate            │   │
                                     (syn62139114) ───────────────┤   │
                                                                  │   │
unified_tissue (syn77130552) ────────────────────────────────────┤   │
unified_manifestation (syn77130553) ──────────────────────────────┤   │
unified_modeltype (syn77130554) ──────────────────────────────────┤   │
unified_availability (syn77130555) ───────────────────────────────┘   │
                                                                       ↓
                                              Resource_VendorItem_Vendor (syn51735470)
```

`CellLine_AnimalModel_Donor` (syn51735419) also separately feeds
`Observation_Publication_Donor` (syn51735464) — a standalone output, not
chained further (see table below).

## Full inventory

| MV | Purpose | Feeds into |
|---|---|---|
| `syn77019684` `AllTools_Group0` | One branch of a 3-way UNION assembling all 9 tool-type detail tables into a common shape (some columns `NULL`-cast per branch where a field doesn't apply to that group) | `AllTools_Union` |
| `syn77019685` `AllTools_Group1` | Same, 2nd branch | `AllTools_Union` |
| `syn77019686` `AllTools_Group2` | Same, 3rd branch | `AllTools_Union` |
| `syn77019730` `AllTools_Union` | `UNION ALL` of the 3 groups above — flat cross-type tool table | `syn51730943` |
| `syn51735412` `AnimalModel_Donor` | AnimalModel LEFT JOIN Donor (species/sex/race/age) | `CellLine_AnimalModel_Donor` |
| `syn51735403` `CellLine_Donor` | CellLine LEFT JOIN Donor, same shape as above | `CellLine_AnimalModel_Donor` |
| `syn51735419` `CellLine_AnimalModel_Donor` | `UNION` of the two Donor joins above | `syn51730943`, `Observation_Publication_Donor` |
| `syn51734029` `Development_Investigator` | Development JOIN Investigator — who developed a tool | `syn51730943` |
| `syn51734076` `Development_Funder` | Development RIGHT JOIN Funder — which funder(s) backed a tool's development | standalone (no MV reads it; queried directly) |
| `syn51735467` `Development_Publication` | Development INNER JOIN Publication — publications tied to a tool's development | standalone |
| `syn51735450` `Usage_Publication` | Usage LEFT JOIN Publication — publications citing/using a tool | `LastPublicationDate` |
| `syn62139114` `LastPublicationDate` | `MAX(publicationDate)` per `resourceId` over `Usage_Publication` | `syn51730943` |
| `syn51735464` `Observation_Publication_Donor` | Observation JOIN Publication + species from `CellLine_AnimalModel_Donor` | standalone |
| `syn77130552` `unified_tissue` | Single-column facet helper: unified `tissue` across Biobank + CellLine (renamed from `STAGING_unified_tissue` 2026-08-27 — see gotcha 3 in `STAGING_PROCEDURE.md`) | `syn51730943` |
| `syn77130553` `unified_manifestation` | Same pattern for `manifestation`, across CellLine/AnimalModel/Biobank/PatientDerivedModel/OrganoidProtocol | `syn51730943` |
| `syn77130554` `unified_modeltype` | Same pattern for `modelType`, across OrganoidProtocol/PatientDerivedModel | `syn51730943` |
| `syn77130555` `unified_availability` | Same pattern for `availability`, across all 9 detail tables | `syn51730943` |
| `syn51730943` FinalMV (long name above) | **The hub** — flattens `AllTools_Union` + donor + development-investigator + last-publication-date + the 4 `unified_*` facets + completeness scores into one portal-search-ready row per `resourceId`; also directly LEFT JOINs 5 of the 9 detail tables a second time (AnimalModel/GeneticReagent/Antibody/ComputationalTool/ClinicalAssessmentTool) for single-value columns the union chain can't carry a `facetType` through (see gotcha 1 in `STAGING_PROCEDURE.md`) | `Resource_VendorItem_Vendor`; also directly read by `TOOL_ANNOTATION_REVIEW.md`'s annotation-completeness check |
| `syn51735470` `Resource_VendorItem_Vendor` | VendorItem + Vendor LEFT JOINed onto FinalMV — vendor/catalog info per tool | leaf, no further reader |

**Separate chain, not part of search** — mutation/gene detail, not
currently read by FinalMV:

| MV | Purpose | Feeds into |
|---|---|---|
| `syn51750819` `Resource_AnimalModel_Mutation_MutationDetails` | AnimalModel → Mutation → MutationDetails | `Resource_AnimalModel_CellLine_Mutation_MutationDetails` |
| `syn51735479` `Resource_CellLine_Mutation_MutationDetails` | CellLine → Mutation → MutationDetails, same shape | `Resource_AnimalModel_CellLine_Mutation_MutationDetails` |
| `syn51750823` `Resource_AnimalModel_CellLine_Mutation_MutationDetails` | `UNION ALL` of the two above, filtered to rows with a mutation | leaf, no further reader |

## Base tables read by production MVs

Every non-MV `TableEntity` that a production MV above reads from
directly. `Read by` lists the *first-line* readers only (an MV further
downstream, like `syn51730943`, inherits these transitively through the
MVs above rather than reading the base table itself, except where noted).

| Table | Synapse ID | Read directly by |
|---|---|---|
| AnimalModelDetails | `syn26486808` | `AllTools_Group0`, `AnimalModel_Donor`, `unified_manifestation`, `unified_availability`, `Resource_AnimalModel_Mutation_MutationDetails`, and FinalMV's own direct JOIN (`animalState`) |
| AntibodyDetails | `syn26486811` | `AllTools_Group1`, `unified_availability`, and FinalMV's own direct JOIN (`targetAntigen`) |
| BiobankDetails | `syn26486821` | `AllTools_Group1`, `unified_tissue`, `unified_manifestation`, `unified_availability` |
| CellLineDetails | `syn26486823` | `AllTools_Group0`, `CellLine_Donor`, `unified_tissue`, `unified_manifestation`, `unified_availability`, `Resource_CellLine_Mutation_MutationDetails` |
| GeneticReagentDetails | `syn26486832` | `AllTools_Group0`, `unified_availability`, and FinalMV's own direct JOIN (`vectorType`) |
| ComputationalToolDetails | `syn73709226` | `AllTools_Group2`, `unified_manifestation`, `unified_availability`, and FinalMV's own direct JOIN (`softwareType`) |
| OrganoidProtocolDetails | `syn73709227` | `AllTools_Group2`, `unified_manifestation`, `unified_modeltype`, `unified_availability` |
| PatientDerivedModelDetails | `syn73709228` | `AllTools_Group1`, `unified_manifestation`, `unified_modeltype`, `unified_availability` |
| ClinicalAssessmentToolDetails | `syn73709229` | `AllTools_Group2`, `unified_manifestation`, `unified_availability`, and FinalMV's own direct JOIN (unused in its SELECT list) |
| Donor | `syn26486829` | `AnimalModel_Donor`, `CellLine_Donor` |
| Development | `syn26486807` | `Development_Investigator`, `Development_Funder`, `Development_Publication` |
| Investigator | `syn26486833` | `Development_Investigator` |
| Funder | `syn26486830` | `Development_Funder` |
| Publication | `syn26486839` | `Development_Publication`, `Usage_Publication`, `Observation_Publication_Donor` |
| Usage | `syn26486841` | `Usage_Publication` |
| Observation | `syn26486836` | `Observation_Publication_Donor` |
| Mutation | `syn26486834` | `Resource_AnimalModel_Mutation_MutationDetails`, `Resource_CellLine_Mutation_MutationDetails` |
| MutationDetails | `syn26486835` | same two above |
| VendorItem | `syn26486843` | `Resource_VendorItem_Vendor` |
| Vendor | `syn26486850` | `Resource_VendorItem_Vendor` |
| ToolCompletenessScores | `syn71218777` | FinalMV's own direct JOIN (completeness/availability/criticalInfo/otherInfo/observation category columns) |

All 9 tool-type detail tables above plus the junction tables are also
documented from the opposite direction (looking up a single `resourceId`
rather than tracing the MV graph) in
`skills/tool-database-lookup/SKILL.md`.

**Not read by any current production MV:** `syn26450069` (legacy
`Resource` table) — retired in the 2026-08 LinkML migration, see
`MIGRATION.md`. Don't add a new dependency on it.

## Naming convention going forward

`STAGING_`/`TEST_`/`CLAUDE_TEST_`/`_new`-style prefixes are reserved for
genuinely throwaway entities meant to be deleted once their staging work
is done. If a staged entity gets promoted into the permanent dependency
chain above (as happened with the 4 `unified_*` helpers), rename it to
drop that prefix in the same change — don't leave a production entity
looking like disposable scratch work. See `STAGING_PROCEDURE.md` gotcha 3
for the incident this rule comes from.

## Keeping this doc current

If you add, remove, or rewire an MV in this project, update the table
and diagram above in the same PR. To re-verify the whole graph from
scratch (e.g. before trusting this doc after a long gap): fetch
`definingSQL` for every MaterializedView under `syn26338068` via
`synapseclient`, then grep each entity's own ID against every other
entity's SQL to find real readers — don't infer dependencies from names
or table/doc descriptions alone.
