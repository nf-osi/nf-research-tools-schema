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

Actions taken:
  1. Snapshot both affected tables BEFORE any changes.
  2. Fix the 2 geneticDisorder rows in CellLineDetails.
  3. Fix the Human/Mouse species rows in Donor.
  4. Snapshot both tables AFTER changes.
"""

import sys

import synapseclient
from synapseclient import Table

CELL_LINE_DETAILS = 'syn26486823'
DONOR_TABLE = 'syn26486829'

GENETIC_DISORDER_FIX = {'Neurofibromatosis Type 2': 'Neurofibromatosis type 2'}
SPECIES_FIX = {'Human': 'Homo sapiens', 'Mouse': 'Mus musculus'}


def snapshot(syn, table_id: str, label: str) -> int:
    v = syn.create_snapshot_version(table_id, comment=label)
    version = v.get('snapshotVersionNumber', v) if isinstance(v, dict) else v
    print(f'  Snapshot created for {table_id}: version {version}  ({label})')
    return version


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

    snapshot(syn, CELL_LINE_DETAILS, 'Before #192 geneticDisorder casing fix')
    syn.store(Table(CELL_LINE_DETAILS, df[['geneticDisorder']]))
    print(f'  Updated {len(df)} row(s).')
    snapshot(syn, CELL_LINE_DETAILS, 'After #192 geneticDisorder casing fix')
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

    snapshot(syn, DONOR_TABLE, 'Before #209 species common-to-scientific-name fix')
    syn.store(Table(DONOR_TABLE, df[['species']]))
    print(f'  Updated {len(df)} row(s).')
    snapshot(syn, DONOR_TABLE, 'After #209 species common-to-scientific-name fix')
    return len(df)


def main():
    dry_run = '--dry-run' in sys.argv

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    n_genetic_disorder = fix_genetic_disorder(syn, dry_run)
    n_species = fix_species(syn, dry_run)

    print('\n=== Summary ===')
    print(f'  #192 geneticDisorder rows {"would be" if dry_run else ""} fixed: {n_genetic_disorder}')
    print(f'  #209 species rows {"would be" if dry_run else ""} fixed: {n_species}')
    print('  #218 reactiveSpecies: no change (no confirming evidence per-resourceId -- see docstring)')


if __name__ == '__main__':
    main()
