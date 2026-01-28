#!/usr/bin/env python3
"""
Format mining results into submission-ready CSVs for Synapse database.

██████████████████████████████████████████████████████████████████████████████
IMPORTANT: Generated SUBMIT_*.csv files contain ONLY NEW ROWS to be APPENDED
to existing Synapse tables after manual verification. These are NOT full tables.
██████████████████████████████████████████████████████████████████████████████

Generates CSVs matching schemas of:
- Resources (syn26450069) - main table with resourceName
- AnimalModelDetails (syn26486808) - animal model specifics
- AntibodyDetails (syn26486811) - antibody specifics
- CellLineDetails (syn26486823) - cell line specifics
- GeneticReagentDetails (syn26486832) - genetic reagent specifics
- Development (syn26486807) - publications where tools were developed
- Publication-Tool Links - many-to-many relationships
"""

import pandas as pd
import uuid
import sys
import os
import json

def generate_uuid():
    """Generate a UUID for new entries."""
    return str(uuid.uuid4())


def get_tool_metadata(row, tool_type, tool_name):
    """
    Extract metadata for a specific tool from the row's metadata JSON.

    Args:
        row: DataFrame row containing tool_metadata column
        tool_type: Type of tool (e.g., 'antibodies', 'cell_lines')
        tool_name: Name of the specific tool

    Returns:
        Dictionary with extracted metadata, or empty dict if not found
    """
    if 'tool_metadata' not in row or pd.isna(row['tool_metadata']):
        return {}

    try:
        all_metadata = json.loads(row['tool_metadata'])
        metadata_key = f"{tool_type}:{tool_name}"
        return all_metadata.get(metadata_key, {})
    except (json.JSONDecodeError, KeyError):
        return {}


def format_existing_tool_links(mining_df):
    """
    Format publication links to EXISTING tools (no new tool creation).

    These are publications that mention tools already in the database.
    Only creates link records, not new tool records.

    Args:
        mining_df: DataFrame with mining results including 'existing_tools' column

    Returns:
        DataFrame with link records to existing tools
    """
    link_rows = []

    for idx, row in mining_df.iterrows():
        if 'existing_tools' not in row or pd.isna(row['existing_tools']):
            continue

        # Parse existing_tools (JSON string: {tool_type: {tool_name: resourceId}})
        try:
            existing_tools = json.loads(row['existing_tools'])
        except:
            continue

        # Get tool sources if available
        tool_sources_dict = {}
        if 'tool_sources' in row and pd.notna(row['tool_sources']):
            try:
                tool_sources_dict = json.loads(row['tool_sources'])
            except:
                pass

        for tool_type, tools_dict in existing_tools.items():
            if not tools_dict:
                continue

            for tool_name, resource_id in tools_dict.items():
                tool_key = f"{tool_type}:{tool_name}"
                sources = tool_sources_dict.get(tool_key, [])

                link_rows.append({
                    'resourceId': resource_id,  # Use existing resourceId
                    'usageId': generate_uuid(),
                    'publicationId': generate_uuid(),
                    'pmid': row.get('pmid', ''),
                    'doi': row.get('doi', ''),
                    'publicationTitle': row.get('title', ''),
                    'authors': '',
                    'journal': row.get('journal', ''),
                    'abstract': '',
                    'publicationDate': row.get('year', ''),
                    'publicationDateUnix': '',
                    'citation': '',
                    # Extra tracking fields
                    '_resourceType': tool_type,
                    '_toolName': tool_name,
                    '_linkType': 'EXISTING_TOOL',
                    '_sources': ', '.join(sources) if isinstance(sources, list) else str(sources),
                    '_fundingAgency': row.get('fundingAgency', ''),
                    '_confidence': 'AUTO - Matched to existing tool - VERIFY'
                })

    return pd.DataFrame(link_rows)


def format_animal_models(mining_df):
    """
    Format animal model suggestions for syn26486808.

    Now processes NOVEL tools only (not existing tools).

    Actual Synapse columns: transplantationDonorId, animalModelId, donorId,
                           backgroundSubstrain, strainNomenclature, backgroundStrain,
                           animalModelOfManifestation, animalModelGeneticDisorder,
                           transplantationType, animalState, generation
    """
    animal_rows = []

    for idx, row in mining_df.iterrows():
        if 'novel_tools' not in row or pd.isna(row['novel_tools']):
            continue

        # Parse novel_tools (JSON string: {tool_type: [tool_names]})
        try:
            novel_tools = json.loads(row['novel_tools'])
        except:
            continue

        models = novel_tools.get('animal_models', [])
        if not models:
            continue

        for model_name in models:
            if not model_name or not str(model_name).strip():
                continue

            # Get extracted metadata
            metadata = get_tool_metadata(row, 'animal_models', model_name)

            # Match actual Synapse table schema with EXACT column order
            is_dev = metadata.get('is_development', False)
            animal_rows.append({
                # EXACT Synapse column order (syn26486808)
                'transplantationDonorId': '',
                'animalModelId': generate_uuid(),
                'donorId': '',
                'backgroundSubstrain': metadata.get('backgroundSubstrain', ''),
                'strainNomenclature': model_name.strip(),
                'backgroundStrain': metadata.get('backgroundStrain', ''),
                'animalModelOfManifestation': metadata.get('animalModelOfManifestation', []),
                'animalModelGeneticDisorder': metadata.get('animalModelGeneticDisorder', []),
                'transplantationType': '',
                'animalState': '',
                'generation': '',
                # Extra fields for tracking (prefix with _ = not in Synapse)
                '_is_development': is_dev,
                '_pmid': row.get('pmid', ''),
                '_doi': row.get('doi', ''),
                '_publicationTitle': row.get('title', ''),
                '_year': row.get('year', ''),
                '_fundingAgency': row.get('fundingAgency', ''),
                '_methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(animal_rows)


def format_antibodies(mining_df):
    """
    Format antibody suggestions for syn26486811.

    Now processes NOVEL tools only (not existing tools).

    Actual Synapse columns: cloneId, uniprotId, antibodyId, reactiveSpecies,
                           hostOrganism, conjugate, clonality, targetAntigen
    """
    antibody_rows = []

    for idx, row in mining_df.iterrows():
        if 'novel_tools' not in row or pd.isna(row['novel_tools']):
            continue

        # Parse novel_tools (JSON string: {tool_type: [tool_names]})
        try:
            novel_tools = json.loads(row['novel_tools'])
        except:
            continue

        antibodies = novel_tools.get('antibodies', [])
        if not antibodies:
            continue

        for antibody_target in antibodies:
            if not antibody_target or not str(antibody_target).strip():
                continue

            # Get extracted metadata
            metadata = get_tool_metadata(row, 'antibodies', antibody_target)

            # Match actual Synapse table schema with EXACT column order
            is_dev = metadata.get('is_development', False)
            antibody_rows.append({
                # EXACT Synapse column order (syn26486811)
                'cloneId': '',
                'uniprotId': '',
                'antibodyId': generate_uuid(),
                'reactiveSpecies': metadata.get('reactiveSpecies', []),
                'hostOrganism': metadata.get('hostOrganism', ''),
                'conjugate': metadata.get('conjugate', ''),  # Only from extracted metadata
                'clonality': metadata.get('clonality', ''),
                'targetAntigen': antibody_target.strip(),
                # Extra fields for tracking (prefix with _ = not in Synapse)
                '_is_development': is_dev,
                '_vendor': metadata.get('vendor', ''),
                '_catalogNumber': metadata.get('catalogNumber', ''),
                '_pmid': row.get('pmid', ''),
                '_doi': row.get('doi', ''),
                '_publicationTitle': row.get('title', ''),
                '_year': row.get('year', ''),
                '_fundingAgency': row.get('fundingAgency', ''),
                '_methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(antibody_rows)


def format_cell_lines(mining_df):
    """
    Format cell line suggestions for syn26486823.

    Now processes NOVEL tools only (not existing tools).

    Actual Synapse columns: cellLineId, donorId, originYear, organ, strProfile, tissue,
                           cellLineManifestation, resistance, cellLineCategory,
                           contaminatedMisidentified, cellLineGeneticDisorder,
                           populationDoublingTime

    NOTE: Cell lines table has NO NAME FIELD in the actual schema.
          This function creates placeholder records that need manual review.
    """
    cell_line_rows = []

    for idx, row in mining_df.iterrows():
        if 'novel_tools' not in row or pd.isna(row['novel_tools']):
            continue

        # Parse novel_tools (JSON string: {tool_type: [tool_names]})
        try:
            novel_tools = json.loads(row['novel_tools'])
        except:
            continue

        cell_lines = novel_tools.get('cell_lines', [])
        if not cell_lines:
            continue

        for cell_line_name in cell_lines:
            if not cell_line_name or not str(cell_line_name).strip():
                continue

            # Get extracted metadata
            metadata = get_tool_metadata(row, 'cell_lines', cell_line_name)

            # Match actual Synapse table schema with EXACT column order
            is_dev = metadata.get('is_development', False)
            cell_line_rows.append({
                # EXACT Synapse column order (syn26486823)
                'cellLineId': generate_uuid(),
                'donorId': '',
                'originYear': '',
                'organ': metadata.get('organ', ''),
                'strProfile': '',
                'tissue': metadata.get('tissue', ''),
                'cellLineManifestation': metadata.get('cellLineManifestation', []),
                'resistance': '',
                'cellLineCategory': metadata.get('cellLineCategory', ''),
                'contaminatedMisidentified': '',
                'cellLineGeneticDisorder': metadata.get('cellLineGeneticDisorder', []),
                'populationDoublingTime': '',
                # Extra fields for tracking (prefix with _ = not in Synapse)
                '_cellLineName': cell_line_name.strip(),  # CRITICAL: No name field in schema!
                '_is_development': is_dev,
                '_pmid': row.get('pmid', ''),
                '_doi': row.get('doi', ''),
                '_publicationTitle': row.get('title', ''),
                '_year': row.get('year', ''),
                '_fundingAgency': row.get('fundingAgency', ''),
                '_methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(cell_line_rows)


def format_genetic_reagents(mining_df):
    """
    Format genetic reagent suggestions for syn26486832.

    Now processes NOVEL tools only (not existing tools).

    Actual Synapse columns: vectorType, insertEntrezId, geneticReagentId, 5primer,
                           cloningMethod, copyNumber, insertSpecies, nTerminalTag,
                           cTerminalTag, totalSize, 5primeCloningSite, growthTemp,
                           insertName, bacterialResistance, hazardous, 3primer,
                           5primeSiteDestroyed, 3primeSiteDestroyed, promoter,
                           backboneSize, insertSize, vectorBackbone, growthStrain,
                           3primeCloningSite, gRNAshRNASequence, selectableMarker
    """
    genetic_reagent_rows = []

    for idx, row in mining_df.iterrows():
        if 'novel_tools' not in row or pd.isna(row['novel_tools']):
            continue

        # Parse novel_tools (JSON string: {tool_type: [tool_names]})
        try:
            novel_tools = json.loads(row['novel_tools'])
        except:
            continue

        reagents = novel_tools.get('genetic_reagents', [])
        if not reagents:
            continue

        for reagent_name in reagents:
            if not reagent_name or not str(reagent_name).strip():
                continue

            # Get extracted metadata
            metadata = get_tool_metadata(row, 'genetic_reagents', reagent_name)

            # Match actual Synapse table schema with EXACT column order
            is_dev = metadata.get('is_development', False)
            genetic_reagent_rows.append({
                # EXACT Synapse column order (syn26486832)
                'vectorType': metadata.get('vectorType', []),
                'insertEntrezId': '',
                'geneticReagentId': generate_uuid(),
                '5primer': '',
                'cloningMethod': '',
                'copyNumber': '',
                'insertSpecies': [],  # List type
                'nTerminalTag': '',
                'cTerminalTag': '',
                'totalSize': '',
                '5primeCloningSite': '',
                'growthTemp': '',
                'insertName': reagent_name.strip(),
                'bacterialResistance': metadata.get('bacterialResistance', ''),
                'hazardous': '',
                '3primer': '',
                '5primeSiteDestroyed': '',
                '3primeSiteDestroyed': '',
                'promoter': '',
                'backboneSize': '',
                'insertSize': '',
                'vectorBackbone': metadata.get('vectorBackbone', ''),
                'growthStrain': '',
                '3primeCloningSite': '',
                'gRNAshRNASequence': '',
                'selectableMarker': '',
                # Extra fields for tracking (prefix with _ = not in Synapse)
                '_is_development': is_dev,
                '_pmid': row.get('pmid', ''),
                '_doi': row.get('doi', ''),
                '_publicationTitle': row.get('title', ''),
                '_year': row.get('year', ''),
                '_fundingAgency': row.get('fundingAgency', ''),
                '_methods_context': f"Found in Methods section (length: {row.get('methods_length', 0)} chars)"
            })

    return pd.DataFrame(genetic_reagent_rows)


def format_publications(mining_df, tool_csvs):
    """
    Format base Publication table entries (syn26486839) for all publications
    that mention tools.

    Args:
        mining_df: DataFrame with mining results containing publication metadata
        tool_csvs: Dictionary of tool type DataFrames (to identify which pubs have tools)

    Returns:
        DataFrame with Publication table entries
    """
    publication_rows = []
    processed_pmids = set()

    # Get all unique PMIDs that have tools
    all_pmids = set()
    for tool_type, tool_df in tool_csvs.items():
        if not tool_df.empty and '_pmid' in tool_df.columns:
            all_pmids.update(tool_df['_pmid'].unique())

    # Create publication entries
    for pmid in all_pmids:
        if pmid in processed_pmids:
            continue
        processed_pmids.add(pmid)

        # Find publication in mining results
        pub_row = mining_df[mining_df['pmid'] == pmid]
        if pub_row.empty:
            continue

        pub_row = pub_row.iloc[0]

        publication_rows.append({
            'publicationId': generate_uuid(),
            'pmid': pmid,
            'doi': pub_row.get('doi', ''),
            'publicationTitle': pub_row.get('title', ''),
            'journal': pub_row.get('journal', ''),
            'year': pub_row.get('year', ''),
            'fundingAgency': pub_row.get('fundingAgency', []),
            # Extra tracking fields
            '_toolCount': sum(1 for df in tool_csvs.values()
                            if not df.empty and '_pmid' in df.columns
                            for _, r in df.iterrows()
                            if r.get('_pmid') == pmid),
            '_source': 'Automated full-text mining'
        })

    return pd.DataFrame(publication_rows)


def format_usage_links(tool_csvs, publication_ids_map):
    """
    Format Usage table entries (syn26486841) for publications where tools
    were USED (not developed).

    Args:
        tool_csvs: Dictionary of tool type DataFrames with _is_development flag
        publication_ids_map: Dict mapping PMID to publicationId from publications table

    Returns:
        DataFrame with Usage table entries
    """
    usage_rows = []

    # Process each tool type
    for tool_type, tool_df in tool_csvs.items():
        if tool_df.empty:
            continue

        for idx, tool_row in tool_df.iterrows():
            # Only include tools where is_development is False (usage, not development)
            is_dev = tool_row.get('_is_development', False)
            if is_dev:
                continue

            pmid = tool_row.get('_pmid', '')
            if not pmid or pmid not in publication_ids_map:
                continue

            # Get the resource ID for this tool
            resource_id = (tool_row.get('animalModelId') or
                          tool_row.get('antibodyId') or
                          tool_row.get('cellLineId') or
                          tool_row.get('geneticReagentId'))

            if not resource_id:
                continue

            usage_rows.append({
                'usageId': generate_uuid(),
                'publicationId': publication_ids_map[pmid],
                'resourceId': resource_id,
                # Extra tracking fields
                '_pmid': pmid,
                '_resourceType': tool_type,
                '_fundingAgency': tool_row.get('_fundingAgency', ''),
                '_source': 'Automated full-text mining - usage context',
                '_notes': tool_row.get('_methods_context', '')
            })

    return pd.DataFrame(usage_rows)


def format_resources(tool_csvs):
    """
    Format Resource table entries (syn26450069) that link to detail tables.

    The Resource table is the main table containing resourceName and foreign keys
    to the detail tables (animalModelId, antibodyId, cellLineId, geneticReagentId).

    Args:
        tool_csvs: Dictionary mapping tool type names to their DataFrames

    Returns:
        DataFrame with Resource table entries
    """
    resource_rows = []

    # Map tool types to their ID columns and resource type names
    type_mapping = {
        'Animal Model': ('animalModelId', 'Animal Model'),
        'Antibody': ('antibodyId', 'Antibody'),
        'Cell Line': ('cellLineId', 'Cell Line'),
        'Genetic Reagent': ('geneticReagentId', 'Genetic Reagent')
    }

    for tool_type_key, tool_df in tool_csvs.items():
        if tool_df.empty:
            continue

        id_column, resource_type = type_mapping[tool_type_key]

        for _, row in tool_df.iterrows():
            # Determine tool name based on type
            if tool_type_key == 'Animal Model':
                tool_name = row.get('strainNomenclature', row.get('backgroundStrain', ''))
            elif tool_type_key == 'Antibody':
                tool_name = row.get('targetAntigen', '')
            elif tool_type_key == 'Cell Line':
                tool_name = row.get('_cellLineName', '')  # Cell lines have no name field in detail table
            elif tool_type_key == 'Genetic Reagent':
                tool_name = row.get('insertName', '')

            if not tool_name:
                continue  # Skip if no name available

            # Create Resource table entry
            resource_entry = {
                'resourceId': generate_uuid(),
                'resourceName': tool_name,
                'resourceType': resource_type,
                # Foreign key to detail table
                'animalModelId': row[id_column] if id_column == 'animalModelId' else '',
                'antibodyId': row[id_column] if id_column == 'antibodyId' else '',
                'cellLineId': row[id_column] if id_column == 'cellLineId' else '',
                'geneticReagentId': row[id_column] if id_column == 'geneticReagentId' else '',
                'biobankId': '',
                # Fields requiring manual curation
                'rrid': '',
                'description': '',
                'synonyms': [],
                'usageRequirements': [],
                'howToAcquire': '',
                'dateAdded': '',  # Will be set by Synapse on upload
                'dateModified': '',
                'aiSummary': '',
                # Extra fields for tracking
                '_is_development': row.get('_is_development', False),
                '_pmid': row.get('_pmid', ''),
                '_publicationTitle': row.get('_publicationTitle', ''),
                '_year': row.get('_year', ''),
                '_fundingAgency': row.get('_fundingAgency', [])
            }

            resource_rows.append(resource_entry)

    return pd.DataFrame(resource_rows)


def format_development_links(tool_csvs, publication_ids_map):
    """
    Format Development table entries (syn26486807) for publications where
    tools were DEVELOPED (not just used).

    Args:
        tool_csvs: Dictionary of tool type DataFrames with _is_development flag
        publication_ids_map: Dict mapping PMID to publicationId from publications table

    Returns:
        DataFrame with Development table entries
    """
    development_rows = []

    # Process each tool type
    for tool_type, tool_df in tool_csvs.items():
        if tool_df.empty:
            continue

        for idx, tool_row in tool_df.iterrows():
            # Only include tools where is_development is True
            is_dev = tool_row.get('_is_development', False)
            if not is_dev:
                continue

            pmid = tool_row.get('_pmid', '')
            if not pmid or pmid not in publication_ids_map:
                continue

            # Get the resource ID for this tool
            resource_id = (tool_row.get('animalModelId') or
                          tool_row.get('antibodyId') or
                          tool_row.get('cellLineId') or
                          tool_row.get('geneticReagentId'))

            if not resource_id:
                continue

            development_rows.append({
                'publicationDevelopmentId': generate_uuid(),
                'publicationId': publication_ids_map[pmid],
                'resourceId': resource_id,
                # Extra tracking fields
                '_pmid': pmid,
                '_resourceType': tool_type,
                '_fundingAgency': tool_row.get('_fundingAgency', ''),
                '_source': 'Automated full-text mining - development context detected',
                '_notes': tool_row.get('_methods_context', '')
            })

    return pd.DataFrame(development_rows)


def main():
    print("=" * 80)
    print("FORMATTING MINING RESULTS FOR TABLE SUBMISSION")
    print("=" * 80)

    # Check for input file
    input_file = 'processed_publications.csv'
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

    # Resources (main table with resourceName)
    print("\n3. Formatting Resource table entries...")
    resources_df = format_resources(tool_csvs)
    if not resources_df.empty:
        output_file = 'SUBMIT_resources.csv'
        resources_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(resources_df)} resources → {output_file}")
    else:
        print("   (no resources to create)")

    # Publications (base table)
    print("\n4. Formatting Publications table (syn26486839)...")
    publications_df = format_publications(mining_df, tool_csvs)
    if not publications_df.empty:
        output_file = 'SUBMIT_publications.csv'
        publications_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(publications_df)} publications → {output_file}")

        # Create PMID -> publicationId mapping for usage/development links
        publication_ids_map = dict(zip(publications_df['pmid'], publications_df['publicationId']))
    else:
        print("   (no publications found)")
        publication_ids_map = {}

    # Usage Links (tools that were USED)
    print("\n5. Formatting Usage table (syn26486841)...")
    usage_df = format_usage_links(tool_csvs, publication_ids_map)
    if not usage_df.empty:
        output_file = 'SUBMIT_usage.csv'
        usage_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(usage_df)} usage links → {output_file}")
    else:
        print("   (no usage links found)")

    # Development Links (tools that were DEVELOPED)
    print("\n6. Formatting Development table (syn26486807)...")
    development_df = format_development_links(tool_csvs, publication_ids_map)
    if not development_df.empty:
        output_file = 'SUBMIT_development.csv'
        development_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(development_df)} development links → {output_file}")
    else:
        print("   (no development links found)")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    total_novel_tools = sum(len(df) for df in tool_csvs.values())
    total_publications = len(publications_df) if not publications_df.empty else 0
    total_usage = len(usage_df) if not usage_df.empty else 0
    total_development = len(development_df) if not development_df.empty else 0

    print(f"\nNovel tool suggestions: {total_novel_tools}")
    print(f"Publications: {total_publications}")
    print(f"Usage links: {total_usage}")
    print(f"Development links: {total_development}")

    # Count development vs usage
    dev_count = 0
    usage_count = 0
    for name, df in tool_csvs.items():
        if '_is_development' in df.columns:
            dev_count += df['_is_development'].sum()
            usage_count += len(df) - df['_is_development'].sum()

    print(f"\n🔬 Development vs Usage breakdown:")
    print(f"   - Development: {dev_count} tools")
    print(f"   - Usage: {usage_count} tools")

    print("\n📋 Submission Files Created (NEW ROWS only - to be appended after verification):")
    print("\n   Core Tables:")
    if not resources_df.empty:
        print(f"   - SUBMIT_resources.csv ({len(resources_df)} entries)")
    print("\n   Detail Tables:")
    if not animal_df.empty:
        print(f"   - SUBMIT_animal_models.csv ({len(animal_df)} entries)")
    if not antibody_df.empty:
        print(f"   - SUBMIT_antibodies.csv ({len(antibody_df)} entries)")
    if not cell_line_df.empty:
        print(f"   - SUBMIT_cell_lines.csv ({len(cell_line_df)} entries)")
    if not genetic_reagent_df.empty:
        print(f"   - SUBMIT_genetic_reagents.csv ({len(genetic_reagent_df)} entries)")
    print("\n   Publication Tables:")
    if not publications_df.empty:
        print(f"   - SUBMIT_publications.csv ({len(publications_df)} publications) → syn26486839")
    if not usage_df.empty:
        print(f"   - SUBMIT_usage.csv ({len(usage_df)} usage links) → syn26486841")
    if not development_df.empty:
        print(f"   - SUBMIT_development.csv ({len(development_df)} development links) → syn26486807")

    print("\n⚠️  CRITICAL: MANUAL VERIFICATION REQUIRED")
    print("   These CSVs are suggestions only and MUST be manually verified:")
    print("   1. Check each publication to confirm tools are actually mentioned")
    print("   2. Verify tool names are correct (watch for fuzzy match errors)")
    print("   3. Fill in empty required fields")
    print("   4. Remove false positives")
    print("   5. Columns prefixed with '_' are NOT in Synapse schema (for reference only)")
    print("   6. Cell lines: Note that actual table has NO name field")
    print("   7. After validation, remove '_' prefixed columns before upload")

    print("\n" + "=" * 80)
    print("FORMATTING COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
