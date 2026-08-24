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

Issue #250: computational tool curation for CAVS-NF1
(resourceId abfa1b2d-af4c-58d4-b92b-725d65ef9fd7, currently registered under
its non-abbreviated resourceName "Central AI-enabled Volumetric Service for
NF1"). Per Belinda's request:
  - Make "CAVS-NF1" the resourceName; move the current resourceName to
    synonyms.
  - Add the dev publication (https://pmc.ncbi.nlm.nih.gov/articles/PMC12577033/,
    PMID:41168866, DOI:10.1186/s13023-025-04093-5) as a new Publication
    (syn26486839) row.
  - Add the corresponding investigator (Fabio Hellmann, University of
    Augsburg -- per that publication) as a new Investigator (syn26486833)
    row, and link both to CAVS-NF1's resourceId via a new Development
    (syn26486807) row.
  - Add a short description of the tool (from the publication's abstract/
    methods) to ComputationalToolDetails (syn73709226).
  NOTE: that publication is a review of AI methods for NF1 glial tumors
  that discusses CAVS-NF1 (among other tools) -- it does not explicitly
  identify itself as CAVS-NF1's own original development paper. Proceeding
  per Belinda's explicit identification of it as "the dev publication";
  flagged in the PR/issue for her awareness in case that's not quite right.
  No investigatorSynapseId or ORCID is set -- neither was confirmable from
  the publication, and both are left null rather than guessed.

  "add synonyms (non-abbreviated versions)" was also requested for
  computational tools generally (not just CAVS-NF1) -- NOT done for the
  other 2 (DINs, RENOVO-NF1) here: their non-abbreviated names aren't in
  any data already queried, and guessing an expansion without a citable
  source would be fabrication. Left as a follow-up needing a source.

Actions taken:
  1. Snapshot every affected table BEFORE any changes.
  2. Fix the 2 geneticDisorder rows in CellLineDetails.
  3. Fix the Human/Mouse species rows in Donor.
  4. Fix the 2 orphaned-resourceId rows and 1 mislabeled row in Observations.
  5. Rename CAVS-NF1, add its Publication/Investigator/Development rows.
  6. Snapshot every affected table AFTER changes.
"""

import os
import sys
import uuid

import pandas as pd
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

# #250: CAVS-NF1 curation
COMPUTATIONAL_TOOL_DETAILS = 'syn73709226'
PUBLICATION_TABLE = 'syn26486839'
INVESTIGATOR_TABLE = 'syn26486833'
DEVELOPMENT_TABLE = 'syn26486807'

CAVS_NF1_RESOURCE_ID = 'abfa1b2d-af4c-58d4-b92b-725d65ef9fd7'
CAVS_NF1_OLD_NAME = 'Central AI-enabled Volumetric Service for NF1'
CAVS_NF1_NEW_NAME = 'CAVS-NF1'
CAVS_NF1_DESCRIPTION = (
    'AI-powered web tool for MR-T1 volumetric analysis of NF1-associated '
    'optic pathway gliomas (OPG), based on SwinUNETR segmentation. '
    'Processing time ~100 seconds per case; reported volume error ~16.7%. '
    'Used in the NF1-OPG natural history study and ACNS 1831.'
)

CAVS_NF1_PUBLICATION = {
    'doi': 'https://www.doi.org/10.1186/s13023-025-04093-5',
    'pmid': 'PMID:41168866',
    'abstract': (
        'Modern Artificial Intelligence (AI) has demonstrated its effectiveness by '
        'achieving human-level performance in various complex tasks, including the '
        'biomedical field. Cancer research, adapting to a fast-changing world, is '
        'leveraging AI as a promising framework to better understand tumor '
        'development. Moreover, current AI methods can help predict more suitable '
        'and personalized treatment strategies for specific types of tumors. We '
        'explored AI methods applied to Neurofibromatosis Type 1, focusing on glial '
        'tumors. Additionally, we have reviewed all publicly available datasets to '
        'date. Discussion of future challenges is highly desirable since '
        'Neurofibromatosis Type 1 is one of the most common hereditary tumor '
        'syndromes and is associated with an increased rate of glial tumors as '
        'well as a reduced life expectancy due to malignancy.'
    ),
    'journal': 'Orphanet Journal of Rare Diseases',
    'publicationDate': '2025-10-30',
    'publicationDateUnix': 1761782400,  # 2025-10-30 UTC, in seconds (matches this table's existing convention, not ms)
    'authors': ['Hellmann F', 'Ristow I', 'Well L', 'Lohse S', 'Anokhin M', 'Kuhlen M', 'André E', 'Harder A'],
    'publicationTitle': (
        'Artificial intelligence-based tools for precision diagnosis and treatment '
        'of neurofibromatosis type 1 associated peripheral and central glial tumors'
    ),
    'year': 2025,
}

CAVS_NF1_INVESTIGATOR = {
    'investigatorName': 'Fabio Hellmann',
    'institution': 'University of Augsburg',
    # investigatorSynapseId and orcid intentionally left null -- not
    # confirmable from the publication, not guessed.
}


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


def _build_citation(pub: dict) -> str:
    """Match this repo's existing Publication.citation format, e.g.
    'Authors. Title <i>Journal.</i> Date. DOI:url PMID:id'."""
    return (
        f"{', '.join(pub['authors'])}. {pub['publicationTitle']} "
        f"<i>{pub['journal']}.</i> {pub['publicationDate']}. "
        f"DOI:{pub['doi']} {pub['pmid']}"
    )


def fix_cavs_nf1(syn, dry_run: bool) -> bool:
    print('\n=== #250: CAVS-NF1 rename + publication/investigator/development ===')
    tool_df = syn.tableQuery(
        f"SELECT resourceId, resourceName, synonyms, description FROM {COMPUTATIONAL_TOOL_DETAILS} "
        f"WHERE resourceId = '{CAVS_NF1_RESOURCE_ID}'"
    ).asDataFrame(rowIdAndVersionInIndex=True)
    if tool_df.empty:
        print(f'  resourceId {CAVS_NF1_RESOURCE_ID} not found -- nothing to do.')
        return False

    current_name = tool_df.iloc[0]['resourceName']
    if current_name == CAVS_NF1_NEW_NAME:
        print(f'  Already renamed to {CAVS_NF1_NEW_NAME} -- nothing to do (idempotent skip).')
        return False

    existing_dev = syn.tableQuery(
        f"SELECT developmentId FROM {DEVELOPMENT_TABLE} WHERE resourceId = '{CAVS_NF1_RESOURCE_ID}'"
    ).asDataFrame()
    if not existing_dev.empty:
        print(
            f'  A Development row already exists for {CAVS_NF1_RESOURCE_ID} -- skipping '
            f'publication/investigator/development inserts to avoid duplicating them '
            f'(rename/description would still proceed below).'
        )

    print(f'  Current: resourceName={current_name!r}, synonyms={tool_df.iloc[0]["synonyms"]}')
    print(f'  New: resourceName={CAVS_NF1_NEW_NAME!r}, synonyms=[{CAVS_NF1_OLD_NAME!r}]')
    print(f'  Publication: {CAVS_NF1_PUBLICATION["pmid"]}, {CAVS_NF1_PUBLICATION["doi"]}')
    print(f'  Investigator: {CAVS_NF1_INVESTIGATOR["investigatorName"]} ({CAVS_NF1_INVESTIGATOR["institution"]})')

    if dry_run:
        print('  Dry run -- not writing.')
        return True

    publication_id = str(uuid.uuid4())
    investigator_id = str(uuid.uuid4())
    development_id = str(uuid.uuid4())

    publication_row = dict(CAVS_NF1_PUBLICATION)
    publication_row['publicationId'] = publication_id
    publication_row['citation'] = _build_citation(publication_row)

    investigator_row = dict(CAVS_NF1_INVESTIGATOR)
    investigator_row['investigatorId'] = investigator_id

    development_row = {
        'developmentId': development_id,
        'resourceId': CAVS_NF1_RESOURCE_ID,
        'investigatorId': investigator_id,
        'publicationId': publication_id,
    }

    snapshot_table(syn, PUBLICATION_TABLE, 'Before #250 CAVS-NF1 publication insert')
    snapshot_table(syn, INVESTIGATOR_TABLE, 'Before #250 CAVS-NF1 investigator insert')
    snapshot_table(syn, DEVELOPMENT_TABLE, 'Before #250 CAVS-NF1 development insert')
    snapshot_table(syn, COMPUTATIONAL_TOOL_DETAILS, 'Before #250 CAVS-NF1 rename')

    if existing_dev.empty:
        syn.store(Table(PUBLICATION_TABLE, pd.DataFrame([publication_row])))
        syn.store(Table(INVESTIGATOR_TABLE, pd.DataFrame([investigator_row])))
        syn.store(Table(DEVELOPMENT_TABLE, pd.DataFrame([development_row])))
        print('  Inserted Publication, Investigator, and Development rows.')

    tool_df.loc[:, 'resourceName'] = CAVS_NF1_NEW_NAME
    tool_df.loc[:, 'synonyms'] = tool_df['synonyms'].apply(lambda existing: list(existing) + [CAVS_NF1_OLD_NAME])
    tool_df.loc[:, 'description'] = CAVS_NF1_DESCRIPTION
    syn.store(Table(COMPUTATIONAL_TOOL_DETAILS, tool_df[['resourceName', 'synonyms', 'description']]))
    print(f'  Renamed {CAVS_NF1_RESOURCE_ID} and updated its description.')

    snapshot_table(syn, PUBLICATION_TABLE, 'After #250 CAVS-NF1 publication insert')
    snapshot_table(syn, INVESTIGATOR_TABLE, 'After #250 CAVS-NF1 investigator insert')
    snapshot_table(syn, DEVELOPMENT_TABLE, 'After #250 CAVS-NF1 development insert')
    snapshot_table(syn, COMPUTATIONAL_TOOL_DETAILS, 'After #250 CAVS-NF1 rename')
    return True


def main():
    dry_run = '--dry-run' in sys.argv

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    n_genetic_disorder = fix_genetic_disorder(syn, dry_run)
    n_species = fix_species(syn, dry_run)
    n_observations = fix_observations(syn, dry_run)
    cavs_nf1_done = fix_cavs_nf1(syn, dry_run)

    print('\n=== Summary ===')
    print(f'  #192 geneticDisorder rows {"would be" if dry_run else ""} fixed: {n_genetic_disorder}')
    print(f'  #209 species rows {"would be" if dry_run else ""} fixed: {n_species}')
    print(f'  #248 Observations rows {"would be" if dry_run else ""} fixed: {n_observations}')
    print(f'  #250 CAVS-NF1 curation {"would be" if dry_run else ""} applied: {cavs_nf1_done}')
    print('  #218 reactiveSpecies: no change (no confirming evidence per-resourceId -- see docstring)')


if __name__ == '__main__':
    main()
