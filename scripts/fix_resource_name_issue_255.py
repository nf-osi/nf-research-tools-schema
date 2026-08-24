#!/usr/bin/env python3
"""
Apply the confirmed resourceName fix tracked in #255.

Issue #255: three CellLineDetails (syn26486823) rows use a " (pNF)"
disambiguation suffix ("pNF" = plexiform neurofibroma) on JH-2-xxx specimen
sublines, inconsistent with their sibling sublines' "(MPNST)" suffix
convention. Per Belinda's request on #246
(https://github.com/nf-osi/nf-research-tools-schema/pull/246#issuecomment-5402634097),
standardize to " (PN)" -- moving each old resourceName to synonyms, matching
the pattern already used for #250's CAVS-NF1 rename.

Affected rows (confirmed live, 2026-08-24):
  d53f3a73-f8b3-5fe5-9467-3a2e1ef690d3  JH-2-002 (MPNST)  -- unaffected, sibling for reference
  23d83c87-acef-552c-8206-89753968fe3f  JH-2-002 (pNF)    -> JH-2-002 (PN)
  c358fb31-58a3-526f-a951-fce43b456d75  JH-2-009 (MPNST)  -- unaffected, sibling for reference
  74e27a8f-2ab9-57c3-bf26-af6c83af724e  JH-2-009 (pNF)    -> JH-2-009 (PN)
  262c44f5-ce9b-543c-88c7-9eb71d957b91  JH-2-031 (MPNST)  -- unaffected, sibling for reference
  5429a063-fd90-51e0-a9f5-97a6546b6150  JH-2-031 (pNF)    -> JH-2-031 (PN)

Only the 3 "(pNF)"-suffixed rows are touched. No deletions -- pure rename,
old name moved to synonyms, snapshotted before and after.
"""

import os
import sys

import synapseclient
from synapseclient import Table

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synapse_safety import snapshot_table

CELL_LINE_DETAILS = 'syn26486823'

# old resourceName -> new resourceName
PNF_TO_PN_RENAMES = {
    'JH-2-002 (pNF)': 'JH-2-002 (PN)',
    'JH-2-009 (pNF)': 'JH-2-009 (PN)',
    'JH-2-031 (pNF)': 'JH-2-031 (PN)',
}


def fix_pnf_to_pn(syn, dry_run: bool) -> int:
    print('\n=== #255: CellLineDetails " (pNF)" -> " (PN)" resourceName ===')
    old_names = list(PNF_TO_PN_RENAMES.keys())
    quoted = ', '.join(f"'{n}'" for n in old_names)
    query = (
        f"SELECT resourceId, resourceName, synonyms FROM {CELL_LINE_DETAILS} "
        f"WHERE resourceName IN ({quoted})"
    )
    df = syn.tableQuery(query).asDataFrame(rowIdAndVersionInIndex=True)
    print(f'  Found {len(df)} row(s) to fix')
    for rid, row in df.iterrows():
        print(f"    {row['resourceId']}: {row['resourceName']!r} -> {PNF_TO_PN_RENAMES[row['resourceName']]!r}")

    if df.empty:
        print('  Nothing to do.')
        return 0

    if dry_run:
        print('  Dry run -- not writing.')
        return len(df)

    snapshot_table(syn, CELL_LINE_DETAILS, 'Before #255 pNF->PN resourceName fix')
    for old_name, new_name in PNF_TO_PN_RENAMES.items():
        mask = df['resourceName'] == old_name
        if not mask.any():
            continue
        df.loc[mask, 'synonyms'] = df.loc[mask, 'synonyms'].apply(lambda existing: list(existing) + [old_name])
        df.loc[mask, 'resourceName'] = new_name
    syn.store(Table(CELL_LINE_DETAILS, df[['resourceName', 'synonyms']]))
    print(f'  Renamed {len(df)} row(s).')
    snapshot_table(syn, CELL_LINE_DETAILS, 'After #255 pNF->PN resourceName fix')
    return len(df)


def main():
    dry_run = '--dry-run' in sys.argv

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    n_fixed = fix_pnf_to_pn(syn, dry_run)

    print('\n=== Summary ===')
    print(f'  #255 resourceName rows {"would be" if dry_run else ""} fixed: {n_fixed}')


if __name__ == '__main__':
    main()
