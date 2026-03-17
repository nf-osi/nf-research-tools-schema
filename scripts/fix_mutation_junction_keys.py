#!/usr/bin/env python3
"""
Fix broken foreign keys in the Mutation junction table (syn26486834).

Issue #120: ~29% of cellLineId values and ~15% of animalModelId values are
actually resourceId values from the Resources table (syn26450069) rather than
the type-specific IDs expected by the detail tables.

Actions taken:
  1. Snapshot all affected tables BEFORE any changes.
  2. Replace resourceId → correct cellLineId for 76 fixable cell-line rows.
  3. Delete 8 fully-orphaned rows (IDs not found in any table).
  4. Snapshot the mutation junction table AFTER changes.
"""

import sys
import synapseclient
from synapseclient import Table

MUTATION_TABLE    = 'syn26486834'
CELL_LINE_DETAILS = 'syn26486823'
ANIMAL_MODEL_DETAILS = 'syn26486808'
RESOURCES_TABLE   = 'syn26450069'


def snapshot(syn, table_id: str, label: str) -> int:
    v = syn.create_snapshot_version(table_id, comment=label)
    version = v.get('snapshotVersionNumber', v) if isinstance(v, dict) else v
    print(f'  Snapshot created for {table_id}: version {version}  ({label})')
    return version


def main():
    syn = synapseclient.Synapse()
    syn.login(silent=True)

    # ------------------------------------------------------------------ #
    # Load tables                                                          #
    # ------------------------------------------------------------------ #
    print('Loading tables...')
    mut_res  = syn.tableQuery(f'SELECT * FROM {MUTATION_TABLE}')
    mut      = mut_res.asDataFrame(rowIdAndVersionInIndex=True)
    cl_ids   = set(syn.tableQuery(f'SELECT cellLineId FROM {CELL_LINE_DETAILS}')
                      .asDataFrame()['cellLineId'].dropna())
    am_ids   = set(syn.tableQuery(f'SELECT animalModelId FROM {ANIMAL_MODEL_DETAILS}')
                      .asDataFrame()['animalModelId'].dropna())
    res      = syn.tableQuery(
        f'SELECT resourceId, cellLineId, animalModelId FROM {RESOURCES_TABLE}'
    ).asDataFrame()

    res_to_cl = res[res['cellLineId'].notna()].set_index('resourceId')['cellLineId'].to_dict()
    res_to_am = res[res['animalModelId'].notna()].set_index('resourceId')['animalModelId'].to_dict()

    print(f'  mutation rows: {len(mut)}')
    print(f'  valid cellLineIds: {len(cl_ids)}')
    print(f'  valid animalModelIds: {len(am_ids)}')

    # ------------------------------------------------------------------ #
    # Identify rows to fix / delete                                        #
    # ------------------------------------------------------------------ #
    cl_col = mut['cellLineId']
    am_col = mut['animalModelId']

    bad_cl_mask   = cl_col.notna() & ~cl_col.isin(cl_ids)
    bad_am_mask   = am_col.notna() & ~am_col.isin(am_ids)

    fixable_cl    = mut[bad_cl_mask & cl_col.isin(res_to_cl)]
    unfixable_cl  = mut[bad_cl_mask & ~cl_col.isin(res_to_cl)]
    unfixable_am  = mut[bad_am_mask]          # none are resourceIds → all orphaned

    print(f'\nDiagnosis:')
    print(f'  cellLineId — fixable (resourceId→cellLineId): {len(fixable_cl)}')
    print(f'  cellLineId — orphaned (delete):               {len(unfixable_cl)}')
    print(f'  animalModelId — orphaned (delete):            {len(unfixable_am)}')

    if len(fixable_cl) == 0 and len(unfixable_cl) == 0 and len(unfixable_am) == 0:
        print('\nNothing to fix — exiting.')
        return

    # ------------------------------------------------------------------ #
    # BEFORE snapshots                                                     #
    # ------------------------------------------------------------------ #
    print('\n--- Snapshots BEFORE ---')
    snapshot(syn, MUTATION_TABLE,    'before fix_mutation_junction_keys #120')
    snapshot(syn, CELL_LINE_DETAILS, 'before fix_mutation_junction_keys #120')
    snapshot(syn, ANIMAL_MODEL_DETAILS, 'before fix_mutation_junction_keys #120')
    snapshot(syn, RESOURCES_TABLE,   'before fix_mutation_junction_keys #120')

    # ------------------------------------------------------------------ #
    # Fix: replace resourceId with correct cellLineId                     #
    # ------------------------------------------------------------------ #
    if len(fixable_cl):
        print(f'\n--- Fixing {len(fixable_cl)} cellLineId rows ---')
        fixed = fixable_cl.copy()
        fixed['cellLineId'] = fixed['cellLineId'].map(res_to_cl)
        table = Table(MUTATION_TABLE, fixed)
        syn.store(table)
        print(f'  Stored {len(fixed)} updated rows.')

    # ------------------------------------------------------------------ #
    # Delete: orphaned rows whose IDs cannot be resolved                  #
    # ------------------------------------------------------------------ #
    delete_count = 0
    for label, df, id_col in [('orphaned cellLineId',  unfixable_cl, 'cellLineId'),
                               ('orphaned animalModelId', unfixable_am, 'animalModelId')]:
        if len(df):
            print(f'\n--- Deleting {len(df)} {label} rows ---')
            for idx_str in df.index:
                bad_id = df.loc[idx_str, id_col]
                print(f'  Deleting ROW_ID={idx_str}  ({id_col}={bad_id})')
            # Query just those rows and delete via the CsvFileTable result
            ids_csv = ', '.join(f"'{i}'" for i in df[id_col])
            del_res = syn.tableQuery(
                f"SELECT * FROM {MUTATION_TABLE} WHERE {id_col} IN ({ids_csv})"
            )
            syn.delete(del_res)
            delete_count += len(df)

    if delete_count:
        print(f'\n  Deleted {delete_count} orphaned rows total.')


    # ------------------------------------------------------------------ #
    # AFTER snapshot                                                       #
    # ------------------------------------------------------------------ #
    print('\n--- Snapshot AFTER ---')
    snapshot(syn, MUTATION_TABLE, 'after fix_mutation_junction_keys #120')

    print('\nDone.')
    print(f'  Fixed  : {len(fixable_cl)} cell-line rows (resourceId → cellLineId)')
    print(f'  Deleted: {len(unfixable_cl) + len(unfixable_am)} orphaned rows')


if __name__ == '__main__':
    main()
