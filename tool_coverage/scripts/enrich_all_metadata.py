#!/usr/bin/env python3
"""
Unified metadata enrichment script for ALL 8 tool types.

Extracts high-priority metadata fields using pattern matching on existing context snippets.
Only fills fields with confirmed data from publications - NO GUESSING.

Tool Types:
1. Cell Lines
2. Animal Models
3. Genetic Reagents
4. Antibodies
5. Computational Tools
6. Patient-Derived Models
7. Advanced Cellular Models
8. Clinical Assessment Tools
"""

import pandas as pd
import re
from typing import Dict, Optional, List
from pathlib import Path


def extract_cell_line_metadata_from_text(tool_name: str, context: str, obs_text: str) -> Dict:
    """Extract cell line metadata using pattern matching."""
    if pd.isna(context):
        context = ""
    if pd.isna(obs_text):
        obs_text = ""

    metadata = {}
    full_text = f"{context} {obs_text}".lower()

    # Extract organ
    organ_patterns = [
        (r'\b(brain|nerve|blood|peripheral nerve|spinal cord|skin)\b', {
            'brain': 'Brain',
            'nerve': 'Nerve',
            'blood': 'Blood',
            'peripheral nerve': 'Peripheral nerve',
            'spinal cord': 'Spinal cord',
            'skin': 'Skin'
        })
    ]
    for pattern, organ_map in organ_patterns:
        matches = re.findall(pattern, full_text)
        if matches:
            for term in ['peripheral nerve', 'spinal cord', 'brain', 'nerve', 'blood', 'skin']:
                if term in matches or term in full_text:
                    metadata['organ'] = organ_map.get(term, term.title())
                    break

    # Extract tissue type
    tissue_patterns = [
        r'(schwann cells?|fibroblasts?|neurons?|astrocytes?|mast cells?|neural progenitor cells?)',
        r'(meningioma|schwannoma|neurofibroma|glioma|glioblastoma) (?:cells?|cell lines?)',
    ]
    for pattern in tissue_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            metadata['tissue'] = match.group(1).strip().title()
            break

    # Extract cellLineManifestation
    manifestation_map = {
        'mpnst': 'MPNST',
        'malignant peripheral nerve sheath tumor': 'MPNST',
        'neurofibroma': 'Neurofibroma',
        'plexiform neurofibroma': 'Plexiform Neurofibroma',
        'cutaneous neurofibroma': 'Cutaneous Neurofibroma',
        'schwannoma': 'Schwannoma',
        'vestibular schwannoma': 'Vestibular Schwannoma',
        'meningioma': 'Meningioma',
        'glioma': 'Glioma',
        'glioblastoma': 'Glioblastoma',
    }
    for disease_key, disease_name in manifestation_map.items():
        if re.search(rf'\b{disease_key}\b', full_text, re.IGNORECASE):
            metadata['cellLineManifestation'] = f"['{disease_name}']"
            break

    # Extract cellLineCategory
    if 'primary cells' in full_text or 'primary culture' in full_text:
        metadata['cellLineCategory'] = 'Primary cells'
    elif 'immortalized' in full_text:
        metadata['cellLineCategory'] = 'Immortalized cells'
    elif any(term in full_text for term in ['cancer', 'tumor', 'mpnst', 'glioblastoma', 'meningioma', 'schwannoma']):
        metadata['cellLineCategory'] = 'Cancer cell line'

    # Extract cellLineGeneticDisorder
    if 'neurofibromatosis type 1' in full_text or 'nf1' in full_text or 'nf-1' in full_text:
        metadata['cellLineGeneticDisorder'] = "['Neurofibromatosis type 1']"
    elif 'neurofibromatosis type 2' in full_text or 'nf2' in full_text or 'nf-2' in full_text:
        metadata['cellLineGeneticDisorder'] = "['Neurofibromatosis type 2']"

    return metadata


def extract_animal_model_metadata_from_text(tool_name: str, context: str, obs_text: str) -> Dict:
    """Extract animal model metadata using pattern matching."""
    if pd.isna(context):
        context = ""
    if pd.isna(obs_text):
        obs_text = ""

    metadata = {}
    full_text = f"{context} {obs_text}".lower()

    # Extract backgroundStrain
    strain_map = {
        'c57bl/6': 'C57BL/6', 'c57bl6': 'C57BL/6', 'bl6': 'C57BL/6',
        'black 6': 'C57BL/6', '129': '129/SvEv', 'fvb': 'FVB',
        'balb/c': 'BALB/c', 'dba/2': 'DBA/2',
    }
    for pattern, strain_name in strain_map.items():
        if re.search(rf'\b{pattern}\b', full_text, re.IGNORECASE):
            metadata['backgroundStrain'] = strain_name
            break

    # Extract animalModelOfManifestation
    manifestation_patterns = [
        (r'\b(neurofibroma|plexiform neurofibroma)', 'Neurofibroma'),
        (r'\b(optic (?:pathway )?glioma)', 'Optic Glioma'),
        (r'\b(mpnst|malignant peripheral nerve sheath tumor)', 'MPNST'),
        (r'\b(schwannoma)', 'Schwannoma'),
        (r'\b(learning deficits?|cognitive deficits?)', 'Learning Deficits'),
    ]
    for pattern, disease_name in manifestation_patterns:
        if re.search(pattern, full_text, re.IGNORECASE):
            metadata['animalModelOfManifestation'] = f"['{disease_name}']"
            break

    # Extract animalModelGeneticDisorder
    if 'nf1' in tool_name.lower() or 'neurofibromin' in full_text:
        metadata['animalModelGeneticDisorder'] = "['Neurofibromatosis type 1']"
    elif 'nf2' in tool_name.lower() or 'merlin' in full_text or 'schwannomin' in full_text:
        metadata['animalModelGeneticDisorder'] = "['Neurofibromatosis type 2']"

    return metadata


def extract_genetic_reagent_metadata_from_text(tool_name: str, context: str, obs_text: str) -> Dict:
    """Extract genetic reagent metadata using pattern matching."""
    if pd.isna(context):
        context = ""
    if pd.isna(obs_text):
        obs_text = ""

    metadata = {}
    full_text = f"{context} {obs_text}".lower()

    # Extract vectorType
    vector_type_patterns = [
        (r'\b(plasmid|expression plasmid)', 'Plasmid'),
        (r'\b(lentiviral vector|lentivirus)', 'Lentiviral vector'),
        (r'\b(aav|adeno-associated virus)', 'AAV'),
        (r'\b(adenoviral vector|adenovirus)', 'Adenoviral vector'),
        (r'\b(retroviral vector|retrovirus)', 'Retroviral vector'),
        (r'\b(shrna)', 'shRNA'),
        (r'\b(sirna)', 'siRNA'),
        (r'\b(crispr|grna|guide rna)', 'CRISPR guide RNA'),
    ]
    for pattern, vtype in vector_type_patterns:
        if re.search(pattern, full_text, re.IGNORECASE):
            metadata['vectorType'] = f"['{vtype}']"
            break

    # Extract vectorBackbone
    backbone_match = re.search(r'\b(p[A-Z]{2,}[0-9]*|pcdna[0-9]?\.?[0-9]?|pegfp)\b', context, re.IGNORECASE)
    if backbone_match:
        metadata['vectorBackbone'] = backbone_match.group(1)

    # Extract insertSpecies
    species_patterns = [
        (r'\bhuman\b', 'Homo sapiens'),
        (r'\bmouse\b', 'Mus musculus'),
        (r'\brat\b', 'Rattus norvegicus'),
    ]
    for pattern, species in species_patterns:
        if re.search(pattern, full_text, re.IGNORECASE):
            metadata['insertSpecies'] = f"['{species}']"
            break

    return metadata


def extract_antibody_metadata_from_text(tool_name: str, context: str, obs_text: str) -> Dict:
    """Extract antibody metadata using pattern matching."""
    if pd.isna(context):
        context = ""
    if pd.isna(obs_text):
        obs_text = ""

    metadata = {}
    full_text = f"{context} {obs_text}".lower()

    # Extract targetAntigen
    antigen_map = {
        'nf1': 'NF1', 'neurofibromin': 'Neurofibromin',
        'nf2': 'NF2', 'merlin': 'Merlin', 'schwannomin': 'Schwannomin',
        'p-erk': 'p-ERK', 'phospho-erk': 'p-ERK',
        's100': 'S100', 'gfap': 'GFAP', 'ki-67': 'Ki-67',
    }
    tool_lower = tool_name.lower()
    for pattern, antigen_name in antigen_map.items():
        if re.search(rf'\b{pattern}\b', tool_lower, re.IGNORECASE):
            metadata['targetAntigen'] = antigen_name
            break

    # Extract reactiveSpecies
    species_mentioned = []
    if re.search(r'\bhuman\b', full_text):
        species_mentioned.append('Human')
    if re.search(r'\b(mouse|murine)\b', full_text):
        species_mentioned.append('Mouse')
    if species_mentioned:
        metadata['reactiveSpecies'] = str(species_mentioned)

    # Extract hostOrganism
    host_patterns = [
        (r'\brabbit\b', 'Rabbit'),
        (r'\bmouse monoclonal\b', 'Mouse'),
        (r'\bgoat\b', 'Goat'),
    ]
    for pattern, host in host_patterns:
        if re.search(pattern, full_text, re.IGNORECASE):
            metadata['hostOrganism'] = host
            break

    return metadata


def extract_computational_tool_metadata(tool_name, context, reasoning):
    """Extract metadata for computational tools from text."""
    if pd.isna(context):
        context = ""
    if pd.isna(reasoning):
        reasoning = ""
    if pd.isna(tool_name):
        tool_name = ""

    text = f"{tool_name} {context} {reasoning}".lower()
    metadata = {}

    # Software Type patterns
    software_types = []
    if re.search(r'\b(web.based|web interface|website|online tool|web.?tool)\b', text):
        software_types.append('Web application')
    if re.search(r'\b(command.?line|cli|terminal|shell)\b', text):
        software_types.append('Command-line tool')
    if re.search(r'\b(package|library|module)\b', text):
        software_types.append('Software library')
    if re.search(r'\b(algorithm|method|approach|predictor)\b', text):
        software_types.append('Algorithm/Method')
    if re.search(r'\b(convolutional neural network|neural network|deep learning|machine learning|u-net|random forest)\b', text):
        software_types.append('Machine learning model')
    if re.search(r'\b(sequencing|ngs|next.generation sequencing)\b', text):
        software_types.append('Sequencing analysis tool')
    if re.search(r'\b(image analy|image processing)\b', text):
        software_types.append('Image analysis tool')

    if software_types:
        metadata['softwareType'] = software_types

    # Programming Language patterns
    languages = []
    if re.search(r'\bpython\b', text):
        languages.append('Python')
    if re.search(r'\b(r\s|r\-|^r$)\b', text):
        languages.append('R')
    if re.search(r'\bjava\b', text):
        languages.append('Java')
    if languages:
        metadata['programmingLanguage'] = languages

    # Source Repository - extract URLs
    repo_urls = re.findall(r'https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[^\s,)]+', context + reasoning)
    if repo_urls:
        metadata['sourceRepository'] = [repo_urls[0]]

    # Documentation - extract website URLs
    doc_urls = re.findall(r'https?://[^\s,)]+', context)
    if doc_urls and 'sourceRepository' not in metadata:
        metadata['documentation'] = [doc_urls[0]]

    return metadata


def extract_patient_derived_model_metadata(model_name, context, reasoning):
    """Extract metadata for patient-derived models from text."""
    if pd.isna(context):
        context = ""
    if pd.isna(reasoning):
        reasoning = ""
    if pd.isna(model_name):
        model_name = ""

    text = f"{model_name} {context} {reasoning}".lower()
    metadata = {}

    # Model System Type
    system_types = []
    if re.search(r'\b(pdx|patient.derived xenograft|xenograft|pdox)\b', text):
        system_types.append('Patient-derived xenograft (PDX)')
    if re.search(r'\b(primary.*cultur|patient.derived.*cultur|primary.*cell|patient.derived.*cell)\b', text):
        system_types.append('Primary cell culture')
    if re.search(r'\b(organoid|spheroid|neurofibromasphere)\b', text):
        system_types.append('Organoid/Spheroid culture')
    if re.search(r'\b(xenoline)\b', text):
        system_types.append('Patient-derived xenoline')

    if system_types:
        metadata['modelSystemType'] = system_types

    # Patient Diagnosis
    diagnoses = []
    if re.search(r'\bnf1\b', text) and not re.search(r'\bnf2\b', text):
        diagnoses.append('Neurofibromatosis type 1 (NF1)')
    if re.search(r'\bnf2\b', text):
        diagnoses.append('Neurofibromatosis type 2 (NF2)')
    if re.search(r'\b(sporadic|non.nf1)\b', text):
        diagnoses.append('Sporadic (non-NF1)')

    if diagnoses:
        metadata['patientDiagnosis'] = diagnoses

    # Tumor Type
    tumor_types = []
    if re.search(r'\b(mpnst|malignant peripheral nerve sheath tumor)\b', text):
        tumor_types.append('Malignant peripheral nerve sheath tumor (MPNST)')
    if re.search(r'\b(plexiform neurofibroma|pnf)\b', text):
        tumor_types.append('Plexiform neurofibroma')
    if re.search(r'\b(neurofibroma)\b', text) and not tumor_types:
        tumor_types.append('Neurofibroma')
    if re.search(r'\b(vestibular schwannoma|acoustic neuroma)\b', text):
        tumor_types.append('Vestibular schwannoma')
    if re.search(r'\b(schwannoma)\b', text) and not tumor_types:
        tumor_types.append('Schwannoma')
    if re.search(r'\b(glioma|opg|optic pathway glioma)\b', text):
        tumor_types.append('Glioma')

    if tumor_types:
        metadata['tumorType'] = tumor_types

    # Engraftment Site
    sites = []
    if re.search(r'\b(subcutaneous|subcutaneously)\b', text):
        sites.append('Subcutaneous')
    if re.search(r'\b(orthotopic|orthotopically)\b', text):
        sites.append('Orthotopic')
    if re.search(r'\b(intracranial|stereotactically|brain)\b', text):
        sites.append('Intracranial')
    if re.search(r'\b(sciatic nerve)\b', text):
        sites.append('Sciatic nerve')

    if sites:
        metadata['engraftmentSite'] = sites

    # Host Strain
    strains = []
    if re.search(r'\b(nod[/\s]?scid|nod\.cg-prkdc)\b', text):
        strains.append('NOD/SCID')
    if re.search(r'\b(nude mice|nude mouse|athymic nude)\b', text):
        strains.append('Nude mice')
    if re.search(r'\b(nsg|nod\.cg-prkdc.*il2rg)\b', text):
        strains.append('NSG (NOD scid gamma)')
    if re.search(r'\b(scid mice|scid mouse)\b', text) and not strains:
        strains.append('SCID mice')

    if strains:
        metadata['hostStrain'] = strains

    return metadata


def extract_advanced_cellular_model_metadata(model_name, context, reasoning):
    """Extract metadata for advanced cellular models from text."""
    if pd.isna(context):
        context = ""
    if pd.isna(reasoning):
        reasoning = ""
    if pd.isna(model_name):
        model_name = ""

    text = f"{model_name} {context} {reasoning}".lower()
    metadata = {}

    # Model Type
    model_types = []
    if re.search(r'\b(organoid|mini.?brain)\b', text):
        model_types.append('Organoid')
    if re.search(r'\b(spheroid|sphere|neurofibromasphere)\b', text):
        model_types.append('Spheroid')
    if re.search(r'\b(3d.*cultur|three.dimensional.*cultur)\b', text):
        model_types.append('3D culture')
    if re.search(r'\b(ipsc.derived|induced pluripotent stem cell|hips?c)\b', text):
        model_types.append('iPSC-derived model')
    if re.search(r'\b(primary.*cultur|primary.*neuron|primary.*cell)\b', text):
        model_types.append('Primary cell culture')
    if re.search(r'\b(brain slice|tumor slice|slice cultur)\b', text):
        model_types.append('Slice culture')
    if re.search(r'\b(microfluidic|tame chip)\b', text):
        model_types.append('Microfluidic culture')

    if model_types:
        metadata['modelType'] = model_types

    # Derivation Source
    sources = []
    if re.search(r'\b(patient.derived|patient.*tissue|human.*tissue|surgical.*specimen)\b', text):
        sources.append('Patient-derived tissue')
    if re.search(r'\b(ipsc|induced pluripotent stem cell|hips?c)\b', text):
        sources.append('Induced pluripotent stem cells (iPSC)')
    if re.search(r'\b(hesc|human embryonic stem cell)\b', text):
        sources.append('Human embryonic stem cells')

    if sources:
        metadata['derivationSource'] = sources

    # Cell Types
    cell_types = []
    if re.search(r'\b(schwann cell|sc)\b', text):
        cell_types.append('Schwann cells')
    if re.search(r'\b(neuron|neuronal)\b', text):
        cell_types.append('Neurons')
    if re.search(r'\b(fibroblast)\b', text):
        cell_types.append('Fibroblasts')
    if re.search(r'\b(microglia|himgl)\b', text):
        cell_types.append('Microglia')
    if re.search(r'\b(neural crest)\b', text):
        cell_types.append('Neural crest cells')

    if cell_types:
        metadata['cellTypes'] = cell_types

    # Organoid Type
    organoid_types = []
    if re.search(r'\b(neurofibromasphere|neurofibroma.*sphere)\b', text):
        organoid_types.append('Neurofibromasphere')
    if re.search(r'\b(cerebral organoid|brain organoid)\b', text):
        organoid_types.append('Cerebral organoid')

    if organoid_types:
        metadata['organoidType'] = organoid_types

    # Culture System
    systems = []
    if re.search(r'\b(3d.*overlay|rbm overlay|matrigel overlay)\b', text):
        systems.append('3D overlay culture')
    if re.search(r'\b(suspension cultur|sphere.*cultur)\b', text):
        systems.append('Suspension culture')
    if re.search(r'\b(microfluidic|tame chip)\b', text):
        systems.append('Microfluidic system')

    if systems:
        metadata['cultureSystem'] = systems

    return metadata


def extract_clinical_assessment_metadata(tool_name, context, reasoning):
    """Extract metadata for clinical assessment tools from text."""
    if pd.isna(context):
        context = ""
    if pd.isna(reasoning):
        reasoning = ""
    if pd.isna(tool_name):
        tool_name = ""

    text = f"{tool_name} {context} {reasoning}".lower()
    metadata = {}

    # Assessment Type
    assessment_types = []
    if re.search(r'\b(questionnaire|survey|scale)\b', text):
        assessment_types.append('Questionnaire/Scale')
    if re.search(r'\b(neuropsychological test|cognitive test|memory test)\b', text):
        assessment_types.append('Neuropsychological test')
    if re.search(r'\b(diagnostic criteria|clinical criteria|classification system)\b', text):
        assessment_types.append('Diagnostic criteria')
    if re.search(r'\b(imaging|mri|scan|ophthalmoscopy)\b', text):
        assessment_types.append('Imaging-based assessment')
    if re.search(r'\b(quality of life|qol|hrqol)\b', text):
        assessment_types.append('Quality of life measure')
    if re.search(r'\b(pain.*scale|pain.*rating|pain assessment)\b', text):
        assessment_types.append('Pain assessment scale')
    if re.search(r'\b(visual acuity|vision test|eye test)\b', text):
        assessment_types.append('Visual assessment')
    if re.search(r'\b(motor.*test|motor.*assessment|rotarod)\b', text):
        assessment_types.append('Motor function assessment')
    if re.search(r'\b(intelligence test|iq test|wisc|wasi)\b', text):
        assessment_types.append('Intelligence assessment')
    if re.search(r'\b(hearing.*test|auditory.*test|audiolog)\b', text):
        assessment_types.append('Auditory assessment')
    if re.search(r'\b(tumor.*response|response criteria|recist)\b', text):
        assessment_types.append('Tumor response criteria')
    if re.search(r'\b(guideline|recommendation)\b', text):
        assessment_types.append('Clinical guideline')

    if assessment_types:
        metadata['assessmentType'] = assessment_types

    # Target Population
    populations = []
    if re.search(r'\b(pediatric|child|children|adolescent)\b', text):
        populations.append('Pediatric')
    if re.search(r'\badult\b', text):
        populations.append('Adult')
    if re.search(r'\bnf1\b', text):
        populations.append('NF1 patients')
    if re.search(r'\bnf2\b', text):
        populations.append('NF2 patients')

    if populations:
        metadata['targetPopulation'] = populations

    # Disease Specific
    if re.search(r'\bnf1\b.*\b(module|specific|nf1.?related)\b', text) or \
       re.search(r'\bnf2\b.*\b(module|specific|nf2.?related)\b', text) or \
       re.search(r'\b(nf1 module|nf2 module|nf.specific)\b', text):
        metadata['diseaseSpecific'] = ['Yes']
    elif re.search(r'\b(generic|general population|normative)\b', text):
        metadata['diseaseSpecific'] = ['No']

    # Scoring Method
    scoring = []
    if re.search(r'\b(likert.*scale|5.point scale|7.point scale)\b', text):
        scoring.append('Likert scale')
    if re.search(r'\b(numerical rating|0.?10 scale|0.?11 scale|nrs.11)\b', text):
        scoring.append('Numerical rating scale')
    if re.search(r'\b(visual analogue)\b', text):
        scoring.append('Visual analogue scale')

    if scoring:
        metadata['scoringMethod'] = scoring

    return metadata


def enrich_all_tool_types():
    """Main enrichment function for all 8 tool types."""
    print("=" * 80)
    print("UNIFIED METADATA ENRICHMENT FOR ALL TOOL TYPES")
    print("=" * 80)
    print("\nExtracting metadata from existing context snippets and observations")
    print("NO API calls - using text analysis only")
    print()

    # Tool type configurations (all 8 types)
    tool_configs = [
        {
            'name': 'Cell Lines',
            'file': 'tool_coverage/outputs/VALIDATED_cell_lines.csv',
            'name_col': '_cellLineName',
            'extractor': extract_cell_line_metadata_from_text,
            'use_observations': True
        },
        {
            'name': 'Animal Models',
            'file': 'tool_coverage/outputs/VALIDATED_animal_models.csv',
            'name_col': 'strainNomenclature',
            'extractor': extract_animal_model_metadata_from_text,
            'use_observations': True
        },
        {
            'name': 'Genetic Reagents',
            'file': 'tool_coverage/outputs/VALIDATED_genetic_reagents.csv',
            'name_col': 'insertName',
            'extractor': extract_genetic_reagent_metadata_from_text,
            'use_observations': True
        },
        {
            'name': 'Antibodies',
            'file': 'tool_coverage/outputs/VALIDATED_antibodies.csv',
            'name_col': 'targetAntigen',
            'extractor': extract_antibody_metadata_from_text,
            'use_observations': True
        },
        {
            'name': 'Computational Tools',
            'file': 'tool_coverage/outputs/VALIDATED_computational_tools.csv',
            'name_col': 'softwareName',
            'extractor': extract_computational_tool_metadata,
            'use_observations': False
        },
        {
            'name': 'Patient-Derived Models',
            'file': 'tool_coverage/outputs/VALIDATED_patient_derived_models.csv',
            'name_col': '_modelName',
            'extractor': extract_patient_derived_model_metadata,
            'use_observations': False
        },
        {
            'name': 'Advanced Cellular Models',
            'file': 'tool_coverage/outputs/VALIDATED_advanced_cellular_models.csv',
            'name_col': '_modelName',
            'extractor': extract_advanced_cellular_model_metadata,
            'use_observations': False
        },
        {
            'name': 'Clinical Assessment Tools',
            'file': 'tool_coverage/outputs/VALIDATED_clinical_assessment_tools.csv',
            'name_col': 'assessmentName',
            'extractor': extract_clinical_assessment_metadata,
            'use_observations': False
        }
    ]

    # Load observations if available
    observations_df = pd.DataFrame()
    obs_file = 'tool_reviews/observations.csv'
    if Path(obs_file).exists():
        observations_df = pd.read_csv(obs_file)
        print(f"✓ Loaded {len(observations_df)} observations")
    else:
        print("  No observations file found (skipping)")

    total_enriched_all = 0

    # Process each tool type
    for config in tool_configs:
        print(f"\n{'=' * 80}")
        print(f"PROCESSING {config['name'].upper()}")
        print('=' * 80)

        if not Path(config['file']).exists():
            print(f"  ⚠️ File not found: {config['file']}")
            continue

        # Load CSV
        df = pd.read_csv(config['file'])
        print(f"  {len(df)} tools loaded")

        enriched_count = 0
        fields_enriched = {}

        for idx, row in df.iterrows():
            # Get tool identifier
            tool_name = row.get(config['name_col'], '')
            if pd.isna(tool_name):
                tool_name = ""

            context = row.get('_contextSnippet', '')
            reasoning = row.get('_reasoning', '')
            if pd.isna(context):
                context = ""
            if pd.isna(reasoning):
                reasoning = ""

            # Get related observations if enabled
            obs_text = ""
            if config['use_observations'] and not observations_df.empty:
                related_obs = observations_df[
                    (observations_df.get('resourceName', '') == tool_name)
                ]
                if len(related_obs) > 0:
                    obs_text = " ".join(related_obs['details'].astype(str).tolist())

            # Extract metadata
            metadata = config['extractor'](tool_name, context, reasoning if not config['use_observations'] else obs_text)

            # Update dataframe
            if metadata:
                for field, value in metadata.items():
                    if value and value != "" and value != "[]":
                        # Only fill if field is currently empty
                        if field in df.columns and (pd.isna(df.at[idx, field]) or df.at[idx, field] == ''):
                            df.at[idx, field] = str(value)
                            enriched_count += 1
                            fields_enriched[field] = fields_enriched.get(field, 0) + 1

        # Save enriched data
        df.to_csv(config['file'], index=False)
        print(f"\n  ✓ Enriched {enriched_count} fields")
        total_enriched_all += enriched_count

        if fields_enriched:
            print(f"  Fields enriched:")
            for field, count in sorted(fields_enriched.items()):
                print(f"    - {field}: {count} entries")

    print("\n" + "=" * 80)
    print("✅ METADATA ENRICHMENT COMPLETE")
    print("=" * 80)
    print(f"\nTotal fields enriched across all tool types: {total_enriched_all}")
    print("All VALIDATED_*.csv files have been updated with extracted metadata")


if __name__ == '__main__':
    enrich_all_tool_types()
