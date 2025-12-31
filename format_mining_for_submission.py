#!/usr/bin/env python3
"""
Format mining results into submission-ready CSVs for each tool type table.

Takes the full text mining results and creates properly formatted CSVs
matching the schemas of:
- Animal Models (syn26486808)
- Antibodies (syn26486811)
- Cell Lines (syn26486823)
- Genetic Reagents (syn26486832)
- Publication Links (syn51735450)
"""

import pandas as pd
import uuid
import sys
import os

def generate_uuid():
    """Generate a UUID for new entries."""
    return str(uuid.uuid4())


def format_animal_models(mining_df):
    """
    Format animal model suggestions for syn26486808.

    Columns: transplantationDonorId, animalModelId, donorId, backgroundSubstrain,
             strainNomenclature, backgroundStrain, animalModelOfManifestation,
             animalModelGeneticDisorder, transplantationType, animalState, generation
    """
    animal_rows = []

    for idx, row in mining_df.iterrows():
        if not row.get('animal_models') or pd.isna(row.get('animal_models')):
            continue

        models = str(row['animal_models']).split(', ')

        for model_name in models:
            if not model_name.strip():
                continue

            animal_rows.append({
                'animalModelId': generate_uuid(),
                'resourceName': model_name.strip(),
                'description': f"Animal model mentioned in publication {row.get('pmid', 'N/A')}",
                'backgroundStrain': '',  # To be filled manually
                'backgroundSubstrain': '',
                'strainNomenclature': '',
                'animalModelOfManifestation': '',
                'animalModelGeneticDisorder': '[Neurofibromatosis type 1]',  # Default for NF1 publications
                'species': 'Mouse',  # Default assumption
                'pmid': row.get('pmid', ''),
                'doi': row.get('doi', ''),
                'publicationTitle': row.get('title', ''),
                'year': row.get('year', ''),
                'fundingAgency': row.get('fundingAgency', ''),
                'methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(animal_rows)


def format_antibodies(mining_df):
    """
    Format antibody suggestions for syn26486811.

    Columns: cloneId, uniprotId, antibodyId, reactiveSpecies, hostOrganism,
             conjugate, clonality, targetAntigen
    """
    antibody_rows = []

    for idx, row in mining_df.iterrows():
        if not row.get('antibodies') or pd.isna(row.get('antibodies')):
            continue

        antibodies = str(row['antibodies']).split(', ')

        for antibody_target in antibodies:
            if not antibody_target.strip():
                continue

            antibody_rows.append({
                'antibodyId': generate_uuid(),
                'resourceName': f"Anti-{antibody_target.strip()} antibody",
                'targetAntigen': antibody_target.strip(),
                'description': f"Antibody mentioned in publication {row.get('pmid', 'N/A')}",
                'clonality': '',  # To be filled manually
                'conjugate': 'Nonconjugated',  # Default assumption
                'hostOrganism': '',
                'reactiveSpecies': '',
                'pmid': row.get('pmid', ''),
                'doi': row.get('doi', ''),
                'publicationTitle': row.get('title', ''),
                'year': row.get('year', ''),
                'fundingAgency': row.get('fundingAgency', ''),
                'methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(antibody_rows)


def format_cell_lines(mining_df):
    """
    Format cell line suggestions for syn26486823.

    Columns: cellLineId, donorId, originYear, organ, strProfile, tissue,
             cellLineManifestation, resistance, cellLineCategory,
             contaminatedMisidentified, cellLineGeneticDisorder, populationDoublingTime
    """
    cell_line_rows = []

    for idx, row in mining_df.iterrows():
        if not row.get('cell_lines') or pd.isna(row.get('cell_lines')):
            continue

        cell_lines = str(row['cell_lines']).split(', ')

        for cell_line_name in cell_lines:
            if not cell_line_name.strip():
                continue

            cell_line_rows.append({
                'cellLineId': generate_uuid(),
                'resourceName': cell_line_name.strip(),
                'description': f"Cell line mentioned in publication {row.get('pmid', 'N/A')}",
                'cellLineCategory': '',  # To be filled manually
                'cellLineGeneticDisorder': '[Neurofibromatosis type 1]',  # Default for NF1 publications
                'cellLineManifestation': '',
                'organ': '',
                'tissue': '',
                'species': 'Human',  # Default assumption
                'pmid': row.get('pmid', ''),
                'doi': row.get('doi', ''),
                'publicationTitle': row.get('title', ''),
                'year': row.get('year', ''),
                'fundingAgency': row.get('fundingAgency', ''),
                'methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(cell_line_rows)


def format_genetic_reagents(mining_df):
    """
    Format genetic reagent suggestions for syn26486832.

    Key Columns: geneticReagentId, vectorType, insertName, insertSpecies,
                 vectorBackbone, bacterialResistance, insertEntrezId, etc.
    """
    genetic_reagent_rows = []

    for idx, row in mining_df.iterrows():
        if not row.get('genetic_reagents') or pd.isna(row.get('genetic_reagents')):
            continue

        reagents = str(row['genetic_reagents']).split(', ')

        for reagent_name in reagents:
            if not reagent_name.strip():
                continue

            genetic_reagent_rows.append({
                'geneticReagentId': generate_uuid(),
                'resourceName': reagent_name.strip(),
                'description': f"Genetic reagent mentioned in publication {row.get('pmid', 'N/A')}",
                'vectorType': '',  # To be filled manually
                'insertName': reagent_name.strip(),
                'insertSpecies': '[Homo sapiens]',  # Default assumption
                'vectorBackbone': '',
                'bacterialResistance': '',
                'pmid': row.get('pmid', ''),
                'doi': row.get('doi', ''),
                'publicationTitle': row.get('title', ''),
                'year': row.get('year', ''),
                'fundingAgency': row.get('fundingAgency', ''),
                'methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(genetic_reagent_rows)


def format_publication_links(mining_df, tool_csvs):
    """
    Format publication-tool links for syn51735450.

    Columns: resourceId, usageId, publicationId, doi, pmid, publicationTitle,
             authors, journal, abstract, publicationDate, publicationDateUnix, citation
    """
    link_rows = []

    # Process each tool type's suggestions
    for tool_type, tool_df in tool_csvs.items():
        if tool_df.empty:
            continue

        for idx, tool_row in tool_df.iterrows():
            pmid = tool_row.get('pmid', '')
            doi = tool_row.get('doi', '')

            if not pmid and not doi:
                continue

            link_rows.append({
                'resourceId': tool_row.get('animalModelId') or tool_row.get('antibodyId') or
                              tool_row.get('cellLineId') or tool_row.get('geneticReagentId'),
                'usageId': generate_uuid(),
                'publicationId': generate_uuid(),
                'pmid': pmid,
                'doi': doi,
                'publicationTitle': tool_row.get('publicationTitle', ''),
                'journal': '',  # Would need to fetch from Synapse publications table
                'publicationDate': tool_row.get('year', ''),
                'resourceName': tool_row.get('resourceName', ''),
                'resourceType': tool_type,
                'fundingAgency': tool_row.get('fundingAgency', ''),
                'source': 'Automated full-text mining',
                'confidence': 'Medium',  # Requires manual verification
                'notes': tool_row.get('methods_context', '')
            })

    return pd.DataFrame(link_rows)


def main():
    print("=" * 80)
    print("FORMATTING MINING RESULTS FOR TABLE SUBMISSION")
    print("=" * 80)

    # Check for input file
    input_file = 'novel_tools_FULLTEXT_mining.csv'
    if not os.path.exists(input_file):
        print(f"\n❌ Error: Input file '{input_file}' not found!")
        print("   Please run fetch_fulltext_and_mine.py first.")
        sys.exit(1)

    print(f"\n1. Loading mining results from {input_file}...")
    mining_df = pd.read_csv(input_file)
    print(f"   - {len(mining_df)} publications with potential tools")

    # Format each tool type
    print("\n2. Formatting tool type submissions...")

    tool_csvs = {}

    # Animal Models
    print("   - Animal Models...", end='')
    animal_df = format_animal_models(mining_df)
    tool_csvs['Animal Model'] = animal_df
    if not animal_df.empty:
        output_file = 'SUBMIT_animal_models.csv'
        animal_df.to_csv(output_file, index=False)
        print(f" ✓ {len(animal_df)} entries → {output_file}")
    else:
        print(" (none found)")

    # Antibodies
    print("   - Antibodies...", end='')
    antibody_df = format_antibodies(mining_df)
    tool_csvs['Antibody'] = antibody_df
    if not antibody_df.empty:
        output_file = 'SUBMIT_antibodies.csv'
        antibody_df.to_csv(output_file, index=False)
        print(f" ✓ {len(antibody_df)} entries → {output_file}")
    else:
        print(" (none found)")

    # Cell Lines
    print("   - Cell Lines...", end='')
    cell_line_df = format_cell_lines(mining_df)
    tool_csvs['Cell Line'] = cell_line_df
    if not cell_line_df.empty:
        output_file = 'SUBMIT_cell_lines.csv'
        cell_line_df.to_csv(output_file, index=False)
        print(f" ✓ {len(cell_line_df)} entries → {output_file}")
    else:
        print(" (none found)")

    # Genetic Reagents
    print("   - Genetic Reagents...", end='')
    genetic_reagent_df = format_genetic_reagents(mining_df)
    tool_csvs['Genetic Reagent'] = genetic_reagent_df
    if not genetic_reagent_df.empty:
        output_file = 'SUBMIT_genetic_reagents.csv'
        genetic_reagent_df.to_csv(output_file, index=False)
        print(f" ✓ {len(genetic_reagent_df)} entries → {output_file}")
    else:
        print(" (none found)")

    # Publication Links
    print("\n3. Formatting publication-tool links...")
    links_df = format_publication_links(mining_df, tool_csvs)
    if not links_df.empty:
        output_file = 'SUBMIT_publication_links.csv'
        links_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(links_df)} links → {output_file}")
    else:
        print("   (no links to create)")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total_tools = sum(len(df) for df in tool_csvs.values())
    print(f"\nTotal tool suggestions: {total_tools}")
    print(f"Total publication links: {len(links_df)}")

    print("\n📋 Submission Files Created:")
    if not animal_df.empty:
        print(f"   - SUBMIT_animal_models.csv ({len(animal_df)} entries)")
    if not antibody_df.empty:
        print(f"   - SUBMIT_antibodies.csv ({len(antibody_df)} entries)")
    if not cell_line_df.empty:
        print(f"   - SUBMIT_cell_lines.csv ({len(cell_line_df)} entries)")
    if not genetic_reagent_df.empty:
        print(f"   - SUBMIT_genetic_reagents.csv ({len(genetic_reagent_df)} entries)")
    if not links_df.empty:
        print(f"   - SUBMIT_publication_links.csv ({len(links_df)} entries)")

    print("\n⚠️  IMPORTANT NEXT STEPS:")
    print("   1. Review each CSV file manually for accuracy")
    print("   2. Fill in empty required fields (marked with '')")
    print("   3. Verify tool names and remove false positives")
    print("   4. Check full text of publications to confirm tool usage")
    print("   5. Submit validated entries to appropriate Synapse tables")

    print("\n" + "=" * 80)
    print("FORMATTING COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
