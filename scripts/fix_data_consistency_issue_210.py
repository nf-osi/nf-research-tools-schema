#!/usr/bin/env python3
"""
Apply the confirmed data-consistency fixes tracked in #210.

Issue #192: 2 rows in CellLineDetails (syn26486823) have
geneticDisorder = "Neurofibromatosis Type 2" (capital "Type"), inconsistent
with the 216 rows using lowercase "type" in "Neurofibromatosis type 1".
Per the confirmed rule ("defer to case with more entries"), rename those 2
rows to lowercase "type".

Issue #209: The Donor table (syn26486829) has rows with common-name species
values ("Human", "Mouse") instead of the scientific names used everywhere
else in the column (Homo sapiens, Mus musculus, Danio rerio, ...). Per the
confirmed call ("switch to scientific names"), rename all such rows.

Issue #218 (reactiveSpecies redundancy in AntibodyDetails, syn26486811) is
NOT included here: investigated per-resourceId (see #210/#218 comments) and
found no confirming evidence in any of the 5 affected records (all have a
null description, no other field indicating a more specific species) that
would justify asserting e.g. "Avian" specifically means "Chicken" for that
exact antibody. Per the explicit instruction on #218 ("if we cannot
confirm... then leave alone"), those values are intentionally left as-is.

Issue #248: two Observations (syn26486836) fixes, both confirmed by Belinda:
  1. Two rows (matched by resourceId + observationText -- their own
     observationId column is null in the live table for these rows, so
     that's not usable as a match key) reference a resourceId
     (0bc812b4-f2af-40c4-8245-1070ab12f627) with no matching row in
     Resources -- an orphaned pre-split "JH-2-009" cell line row. Repoint
     to the JH-2-009 (MPNST) resourceId (c358fb31-58a3-526f-a951-fce43b456d75).
  2. One row's observationType is "Tumor susceptibility|Issue" but describes
     a negative-result phenotype caveat, not a QC/resource issue -- drop
     "Issue" from its observationType list.

Actions taken:
  1. Snapshot every affected table BEFORE any changes.
  2. Fix the 2 geneticDisorder rows in CellLineDetails.
  3. Fix the Human/Mouse species rows in Donor.
  4. Fix the 2 orphaned-resourceId rows and 1 mislabeled row in Observations.
  5. Snapshot every affected table AFTER changes.
"""

import os
import sys

import synapseclient
from synapseclient import Table

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synapse_safety import snapshot_table

CELL_LINE_DETAILS = 'syn26486823'
DONOR_TABLE = 'syn26486829'
OBSERVATIONS_TABLE = 'syn26486836'

GENETIC_DISORDER_FIX = {'Neurofibromatosis Type 2': 'Neurofibromatosis type 2'}
SPECIES_FIX = {'Human': 'Homo sapiens', 'Mouse': 'Mus musculus'}

# #248 fix 1: orphaned pre-split "JH-2-009" resourceId -> JH-2-009 (MPNST)
ORPHANED_JH_2_009_RESOURCE_ID = '0bc812b4-f2af-40c4-8245-1070ab12f627'
JH_2_009_MPNST_RESOURCE_ID = 'c358fb31-58a3-526f-a951-fce43b456d75'

# #248 fix 2: the one mislabeled row, matched by resourceId (unique in this table)
MISLABELED_ISSUE_RESOURCE_ID = '669641d6-2e7c-4679-bfe8-0d31c53c2dfc'


def fix_genetic_disorder(syn, dry_run: bool) -> int:
    print('\n=== #192: CellLineDetails.geneticDisorder casing ===')
    query = (
        "SELECT resourceId, resourceName, geneticDisorder FROM {} "
        "WHERE geneticDisorder HAS ('Neurofibromatosis Type 2')"
    ).format(CELL_LINE_DETAILS)
    df = syn.tableQuery(query).asDataFrame(rowIdAndVersionInIndex=True)
    print(f'  Found {len(df)} row(s) to fix')
    for rid, row in df.iterrows():
        print(f"    {row['resourceId']} ({row['resourceName']}): {row['geneticDisorder']}")

    if df.empty:
        print('  Nothing to do.')
        return 0

    df['geneticDisorder'] = df['geneticDisorder'].apply(
        lambda values: [GENETIC_DISORDER_FIX.get(v, v) for v in values]
    )

    if dry_run:
        print('  Dry run -- not writing.')
        return len(df)

    snapshot_table(syn, CELL_LINE_DETAILS, 'Before #192 geneticDisorder casing fix')
    syn.store(Table(CELL_LINE_DETAILS, df[['geneticDisorder']]))
    print(f'  Updated {len(df)} row(s).')
    snapshot_table(syn, CELL_LINE_DETAILS, 'After #192 geneticDisorder casing fix')
    return len(df)


def fix_species(syn, dry_run: bool) -> int:
    print('\n=== #209: Donor.species common name -> scientific name ===')
    query = (
        "SELECT donorId, species FROM {} "
        "WHERE species HAS ('Human') OR species HAS ('Mouse')"
    ).format(DONOR_TABLE)
    df = syn.tableQuery(query).asDataFrame(rowIdAndVersionInIndex=True)
    n_human = sum(1 for v in df['species'] if 'Human' in v)
    n_mouse = sum(1 for v in df['species'] if 'Mouse' in v)
    print(f'  Found {len(df)} row(s) to fix ({n_human} Human, {n_mouse} Mouse)')
    print(
        "  Note: #209's original estimate was ~34 rows based on the smaller "
        "syn51735419 join view (which only reflects donors currently linked "
        "to a resource); the Donor table itself has more unlinked rows."
    )

    if df.empty:
        print('  Nothing to do.')
        return 0

    df['species'] = df['species'].apply(
        lambda values: [SPECIES_FIX.get(v, v) for v in values]
    )

    if dry_run:
        print('  Dry run -- not writing.')
        return len(df)

    snapshot_table(syn, DONOR_TABLE, 'Before #209 species common-to-scientific-name fix')
    syn.store(Table(DONOR_TABLE, df[['species']]))
    print(f'  Updated {len(df)} row(s).')
    snapshot_table(syn, DONOR_TABLE, 'After #209 species common-to-scientific-name fix')
    return len(df)


def fix_observations(syn, dry_run: bool) -> int:
    print('\n=== #248: Observations resourceId + mislabeled Issue ===')
    # resourceId alone isn't a precise-enough filter for the mislabeled-row
    # fix: MISLABELED_ISSUE_RESOURCE_ID has 8 other, unrelated Observations
    # rows (only 1 of which actually has "Issue" in observationType) -- so
    # also require observationType HAS ('Issue') there, to fetch (and later
    # write back) only rows that actually need a change.
    query = (
        "SELECT resourceId, observationType, observationText FROM {} "
        "WHERE resourceId = '{}' "
        "OR (resourceId = '{}' AND observationType HAS ('Issue'))"
    ).format(OBSERVATIONS_TABLE, ORPHANED_JH_2_009_RESOURCE_ID, MISLABELED_ISSUE_RESOURCE_ID)
    df = syn.tableQuery(query).asDataFrame(rowIdAndVersionInIndex=True)
    print(f'  Found {len(df)} row(s) to fix')
    for rid, row in df.iterrows():
        print(f"    {row['resourceId']}: {row['observationType']} -- {row['observationText'][:80]}")

    if df.empty:
        print('  Nothing to do.')
        return 0

    is_orphaned = df['resourceId'] == ORPHANED_JH_2_009_RESOURCE_ID
    is_mislabeled = df['resourceId'] == MISLABELED_ISSUE_RESOURCE_ID

    df.loc[is_orphaned, 'resourceId'] = JH_2_009_MPNST_RESOURCE_ID
    df.loc[is_mislabeled, 'observationType'] = df.loc[is_mislabeled, 'observationType'].apply(
        lambda values: [v for v in values if v != 'Issue']
    )

    if dry_run:
        print('  Dry run -- not writing.')
        return len(df)

    snapshot_table(syn, OBSERVATIONS_TABLE, 'Before #248 resourceId + mislabeled Issue fix')
    syn.store(Table(OBSERVATIONS_TABLE, df[['resourceId', 'observationType']]))
    print(f'  Updated {len(df)} row(s).')
    snapshot_table(syn, OBSERVATIONS_TABLE, 'After #248 resourceId + mislabeled Issue fix')
    return len(df)


def main():
    dry_run = '--dry-run' in sys.argv

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    n_genetic_disorder = fix_genetic_disorder(syn, dry_run)
    n_species = fix_species(syn, dry_run)
    n_observations = fix_observations(syn, dry_run)

    print('\n=== Summary ===')
    print(f'  #192 geneticDisorder rows {"would be" if dry_run else ""} fixed: {n_genetic_disorder}')
    print(f'  #209 species rows {"would be" if dry_run else ""} fixed: {n_species}')
    print(f'  #248 Observations rows {"would be" if dry_run else ""} fixed: {n_observations}')
    print('  #218 reactiveSpecies: no change (no confirming evidence per-resourceId -- see docstring)')


if __name__ == '__main__':
    main()
