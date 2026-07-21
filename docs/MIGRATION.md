# Migration: CSV model to LinkML

This documents the migration path from the flat CSV data model
(`nf_research_tools.rdb.model.csv`) to the modular LinkML schema (`modules/`).

## Summary of structural changes

| Current (CSV) | New (LinkML) | Change |
|---|---|---|
| Separate `Resource` table (syn26450069) + type-specific detail tables joined by FK | Core Tool fields denormalized into each tool-type table | Resource table retired |
| Type-specific IDs (`animalModelId`, `cellLineId`, ...) | Inherited `resourceId` on all types | Column rename |
| `animalModelGeneticDisorder`, `cellLineGeneticDisorder`, `diseaseType` | Unified `geneticDisorder` via `HasGeneticDisorder` mixin | Column rename |
| `animalModelOfManifestation`, `cellLineManifestation` | Unified `manifestation` via mixin | Column rename |
| `Mutation` junction table (syn26486834) | Kept — needed to join MutationDetails with tool-type tables | No change |
| `Development` junction table (syn26486807) | Kept — needed to join Investigators/Publications/Funders with tools | No change |
| `Usage` junction table (syn26486841) | Kept — needed to join Publications with tool-type tables | No change |

## Tables retired

| Table | Synapse ID | Reason |
|---|---|---|
| Resource | syn26450069 | Fields absorbed into tool-type tables |

**Synapse storage options for OpenSearch-indexable tables:**

Synapse SQL does not support joining on LIST columns to another table
(`UNNEST` expands rows within a single table only, `HAS()` filters within
a single table only — neither can be used in a JOIN condition). Two options:

1. **MaterializedViews with JOINs via junction tables** (recommended): 
   Keep data normalized in junction tables. Create MaterializedViews that JOIN tool-type tables
   through junction tables to related entities. MVs are indexed by
   OpenSearch, so the flattened result is searchable — e.g. finding an
   AnimalModel by `affectedGeneSymbol`. This requires **new MVs** for each
   relationship that needs to be searchable. Tested and confirmed working:
   ```sql
   -- Example: AnimalModel with mutation details (via junction)
   SELECT am.*, md.affectedGeneSymbol, md.mutationType
   FROM syn26486808 am
   JOIN syn26486834 mut ON am.animalModelId = mut.animalModelId
   JOIN syn26486835 md ON mut.mutationDetailsId = md.mutationDetailsId
   ```

2. **JSON columns** (alternative): Store related data as JSON directly on
   the tool-type row (e.g. `mutations` as array `[{"mutationDetailsId": "...", "affectedGeneSymbol": "NF1"}]`). 
   Enables searching without extra views. **Tradeoffs:** introduces data duplication (same mutation details
   embedded across multiple tool rows, updates must be applied to each);
   Synapse cannot join a LIST/JSON column to another table; LinkML's
   `gen-sqltables` does not produce JSON columns (needs custom logic).

**Current plan:** option 1 — keep junction tables, create new
MaterializedViews for searchability.

**New MaterializedViews to create:**

| MV | Joins | Purpose |
|---|---|---|
| AnimalModel + Mutations | AnimalModel → Mutation → MutationDetails | Search models by gene symbol, mutation type |
| CellLine + Mutations | CellLine → Mutation → MutationDetails | Search cell lines by gene symbol, mutation type |
| Tool + Development | Tool-type → Development → Investigator, Publication, Funder | Search tools by developer, funder, or publication |
| Tool + Usage | Tool-type → Usage → Publication | Search tools by citing publication |

## Migration steps

### Phase 1: Snapshot

**Version all existing tables before any schema changes.** This preserves a
rollback point, prevents current portal UI breakage (for Detail pages), 
and allows the main materialized view (syn51730943) to
continue referencing legacy snapshots during the transition.

1. Create a versioned snapshot of every Synapse table listed below
2. Record snapshot version numbers in tracking issue
3. Ensure syn51730943 view references the legacy snapshots (in defining SQL)

Tables to snapshot:

```
syn26450069  Resource
syn26486808  AnimalModelDetails
syn26486811  AntibodyDetails
syn26486823  CellLineDetails
syn26486832  GeneticReagentDetails
syn26486821  BiobankDetails
syn73709226  ComputationalToolDetails
syn73709227  OrganoidProtocolDetails
syn73709228  PatientDerivedModelDetails
syn73709229  ClinicalAssessmentToolDetails
syn26486829  Donor
syn26486835  MutationDetails
syn26486834  Mutation (junction)
syn26486839  Publication
syn26486833  Investigator
syn26486830  Funder
syn26486850  Vendor
syn26486843  VendorItem
syn26486836  Observation
syn26486807  Development
syn26486841  Usage
```

### Phase 2: Create new tables (preferred) or update existing

**Preferred: create fresh tables.** Synapse tables are append-oriented 
and altering schemas in place is error-prone. 
It's easier to create new tables from the LinkML schema, backfill data from the legacy
tables, then update `synapse_table_id` annotations and workflow references
to point to the new IDs.The legacy tables remain as snapshots from Phase 1. 
**Downside**: Have to make new `OPEN_DATA` requests.

**Alternative: update existing tables in place.** If need to preserve Synapse IDs
(e.g. for portal deep links or external integrations), the
steps below describe adding columns and renaming in place.

---

Each tool-type table currently stores only type-specific fields. Add the
inherited Tool columns so each table is self-contained:

Columns to add to all 9 tool-type tables:

- `resourceId` (will become the primary key, replacing type-specific IDs)
- `rrid`
- `resourceName`
- `synonyms`
- `resourceType`
- `description`
- `aiSummary`
- `usageRequirements`
- `howToAcquire`
- `dateAdded`
- `dateModified`

### Phase 3: Backfill data

Populate the new columns from the Resource table:

```python
"""
Backfill core Tool fields from Resource table into each tool-type table.
"""
import synapseclient

syn = synapseclient.login()

# Current FK column name → tool-type table
TYPE_TABLES = {
    "animalModelId":           "syn26486808",
    "antibodyId":              "syn26486811",
    "cellLineId":              "syn26486823",
    "geneticReagentId":        "syn26486832",
    "biobankId":               "syn26486821",
    "computationalToolId":     "syn73709226",
    "organoidProtocolId":      "syn73709227",
    "patientDerivedModelId":   "syn73709228",
    "clinicalAssessmentToolId":"syn73709229",
}

CORE_COLUMNS = [
    "resourceId", "rrid", "resourceName", "synonyms", "resourceType",
    "description", "aiSummary", "usageRequirements", "howToAcquire",
    "dateAdded", "dateModified",
]

resources = syn.tableQuery("SELECT * FROM syn26450069").asDataFrame()

for fk_col, type_table in TYPE_TABLES.items():
    type_df = syn.tableQuery(f"SELECT * FROM {type_table}").asDataFrame()

    # Join on the FK column
    merged = type_df.merge(
        resources[CORE_COLUMNS + [fk_col]],
        on=fk_col,
        how="left",
        suffixes=("", "_resource"),
    )

    # TODO: upsert merged rows back to type_table with new columns
    print(f"{type_table}: {len(merged)} rows to backfill")
```

### Phase 4: Rename columns

Rename type-prefixed columns to their generic LinkML names:

| Table | Old column | New column |
|---|---|---|
| AnimalModel | `animalModelId` | `resourceId` |
| AnimalModel | `animalModelGeneticDisorder` | `geneticDisorder` |
| AnimalModel | `animalModelOfManifestation` | `manifestation` |
| CellLine | `cellLineId` | `resourceId` |
| CellLine | `cellLineGeneticDisorder` | `geneticDisorder` |
| CellLine | `cellLineManifestation` | `manifestation` |
| Antibody | `antibodyId` | `resourceId` |
| GeneticReagent | `geneticReagentId` | `resourceId` |
| Biobank | `biobankId` | `resourceId` |
| Biobank | `diseaseType` | `geneticDisorder` |
| ComputationalTool | `computationalToolId` | `resourceId` |
| OrganoidProtocol | `organoidProtocolId` | `resourceId` |
| PatientDerivedModel | `patientDerivedModelId` | `resourceId` |
| ClinicalAssessmentTool | `clinicalAssessmentToolId` | `resourceId` |

### Phase 5: Update junction table FKs

Junction tables must be kept (see Synapse constraint above). The only change
is updating FK column names to match the unified `resourceId` primary key.

**Mutation (syn26486834):** Rename `animalModelId` / `cellLineId` columns to
`resourceId` (or add `resourceId` alongside, since both tool types share the
same ID space).

**Usage (syn26486841):** No change needed — already uses `resourceId`.

**Development (syn26486807):** No change needed — already uses `resourceId`.

### Phase 6: Update workflows and scripts

After the table schema changes, update:

1. **`tool_coverage/scripts/clean_submission_csvs.py`** — column mappings,
   remove Resource table upsert, update type-table column lists
2. **`tool_coverage/scripts/upsert_publication_links.py`** — resource lookup
   now queries tool-type tables directly instead of syn51730943/syn26450069
3. **`build_db/build_db.py`** — update `db_config` FK definitions to reflect
   new primary keys and removed junction tables
4. **`.github/workflows/upsert-tools.yml`** — update Synapse table ID
   references in the summary step, remove Resource table upload step
5. **`NF-Tools-Schemas/`** — regenerate submission form JSON schemas from
   LinkML using `gen-json-schema`
6. **`scripts/check_referential_integrity.py`** — should work as-is since it
   reads from schema annotations

### Phase 7: Validate and cut over

1. Run `python scripts/check_referential_integrity.py --mode sqlite --check-enums`
   against the migrated tables
2. Verify submission forms work with updated JSON schemas
3. Point syn51730943 view from legacy snapshots to the migrated live tables
4. Retire the Resource table (syn26450069) — keep the snapshot for reference
5. Archive `nf_research_tools.rdb.model.csv` (no longer the source of truth)

## Rollback

If issues are found post-migration, revert syn51730943 view to reference
the Phase 1 legacy snapshots.
