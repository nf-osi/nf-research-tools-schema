#!/usr/bin/env python3
"""
Fix the remaining casing inconsistency tracked in #192.

The GeneticDisorderEnum permissible value is lowercase "Neurofibromatosis
type 1" (modules/enums.yaml). #251 already fixed the 2 CellLineDetails rows
using capital "Neurofibromatosis Type 2" (syn26486823). The portal's
"Genetic Disorder" facet (see #192's 2026-08-25 comment) shows the same
capital-"Type" mistake still live for "Type 1" -- and this time it spans
more than one resourceType table.

Every LinkML class mixing in HasGeneticDisorder/geneticDisorder was checked
for a `geneticDisorder` column and queried for the capital-case value:

  - AnimalModelDetails         (syn26486808): 4 rows   -- fix
  - BiobankDetails             (syn26486821): 0 rows   -- already consistent
  - CellLineDetails            (syn26486823): 30 rows  -- fix
  - OrganoidProtocolDetails    (syn73709227): column empty for all rows
  - PatientDerivedModelDetails (syn73709228): column empty for all rows

30 + 4 = 34, matching the portal facet's "Neurofibromatosis Type 1" count
exactly, so this is the full remaining scope -- no other resourceType has
this casing outlier.

Actions taken per affected table:
  1. Snapshot BEFORE any changes.
  2. Rename "Neurofibromatosis Type 1" -> "Neurofibromatosis type 1".
  3. Snapshot AFTER changes.
"""

import sys

import synapseclient
from synapseclient import Table

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from synapse_safety import snapshot_table

TABLES = {
    'syn26486808': 'AnimalModelDetails',
    'syn26486823': 'CellLineDetails',
}

CASING_FIX = {'Neurofibromatosis Type 1': 'Neurofibromatosis type 1'}


def fix_table(syn, table_id: str, name: str, dry_run: bool) -> int:
    print(f'\n=== {name} ({table_id}) ===')
    # Synapse SQL's HAS operator is case-insensitive, so it can't distinguish
    # "Neurofibromatosis Type 1" from the already-correct lowercase value --
    # pull the (small) candidate superset, then filter case-sensitively in
    # pandas for an exact match on the capitalized string.
    query = (
        "SELECT resourceId, resourceName, geneticDisorder FROM {} "
        "WHERE geneticDisorder HAS ('Neurofibromatosis Type 1')"
    ).format(table_id)
    candidates = syn.tableQuery(query).asDataFrame(rowIdAndVersionInIndex=True)
    df = candidates[candidates['geneticDisorder'].apply(
        lambda values: 'Neurofibromatosis Type 1' in values
    )].copy()
    print(f'  Found {len(df)} row(s) to fix (of {len(candidates)} case-insensitive candidates)')
    for _, row in df.iterrows():
        print(f"    {row['resourceId']} ({row['resourceName']}): {row['geneticDisorder']}")

    if df.empty:
        print('  Nothing to do.')
        return 0

    df['geneticDisorder'] = df['geneticDisorder'].apply(
        lambda values: [CASING_FIX.get(v, v) for v in values]
    )

    if dry_run:
        print('  Dry run -- not writing.')
        return len(df)

    snapshot_table(syn, table_id, f'Before #192 {name} geneticDisorder casing fix')
    syn.store(Table(table_id, df[['geneticDisorder']]))
    print(f'  Updated {len(df)} row(s).')
    snapshot_table(syn, table_id, f'After #192 {name} geneticDisorder casing fix')
    return len(df)


def main():
    dry_run = '--dry-run' in sys.argv

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    total = 0
    for table_id, name in TABLES.items():
        total += fix_table(syn, table_id, name, dry_run)

    print('\n=== Summary ===')
    print(f'  #192 "Neurofibromatosis Type 1" -> "type 1" rows {"would be" if dry_run else ""} fixed: {total}')


if __name__ == '__main__':
    main()
