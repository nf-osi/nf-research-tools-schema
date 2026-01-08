#!/usr/bin/env python3
"""
Extract rich metadata from Methods sections to pre-fill submission fields.
"""

import re
from typing import Dict, List, Optional, Tuple

# ============================================================================
# Antibody Metadata Extraction
# ============================================================================

CLONALITY_PATTERNS = {
    'monoclonal': r'\b(monoclonal|mAb|clone\s+[A-Z0-9]+)\b',
    'polyclonal': r'\b(polyclonal|pAb|antisera|antiserum)\b'
}

HOST_ORGANISM_PATTERNS = {
    'Rabbit': r'\brabbit\b',
    'Mouse': r'\bmouse\b(?!\s+model)',  # Avoid "mouse model"
    'Goat': r'\bgoat\b',
    'Rat': r'\brat\b',
    'Chicken': r'\bchicken\b',
    'Donkey': r'\bdonkey\b',
    'Guinea Pig': r'\bguinea\s+pig\b',
    'Hamster': r'\bhamster\b',
    'Sheep': r'\bsheep\b'
}

VENDOR_PATTERNS = {
    'Abcam': r'\b(Abcam|ab\d+)\b',
    'Cell Signaling': r'\b(Cell\s+Signaling|CST)\b',
    'Santa Cruz': r'\b(Santa\s+Cruz|sc-\d+)\b',
    'BD Biosciences': r'\b(BD\s+Biosciences|BD\s+Pharmingen)\b',
    'Thermo Fisher': r'\b(Thermo\s+Fisher|Invitrogen|Life\s+Technologies)\b',
    'Millipore': r'\b(Millipore|Sigma|Merck)\b',
    'R&D Systems': r'\b(R&D\s+Systems)\b',
    'BioLegend': r'\b(BioLegend)\b',
    'Proteintech': r'\b(Proteintech)\b',
    'Novus': r'\b(Novus\s+Biologicals)\b'
}

CATALOG_NUMBER_PATTERN = r'\b(?:cat\.?(?:alog)?\s*(?:#|no\.?|number)?\s*:?\s*)?([A-Z]{1,3}[-\s]?\d{3,7}(?:[-\s][A-Z0-9]+)?)\b'

REACTIVE_SPECIES_PATTERNS = {
    'Human': r'\b(human|Homo\s+sapiens)\b',
    'Mouse': r'\b(mouse|Mus\s+musculus)\b',
    'Rat': r'\b(rat|Rattus\s+norvegicus)\b',
    'Rabbit': r'\brabbit\b',
    'Bovine': r'\b(bovine|cow)\b',
    'Porcine': r'\b(porcine|pig)\b',
    'Canine': r'\b(canine|dog)\b'
}


def extract_antibody_metadata(antibody_name: str, context: str, window: int = 200) -> Dict:
    """
    Extract metadata for an antibody from surrounding context.

    Args:
        antibody_name: Name of the antibody
        context: Full methods text
        window: Characters to search around antibody mention

    Returns:
        Dictionary with extracted metadata
    """
    metadata = {
        'clonality': '',
        'hostOrganism': '',
        'vendor': '',
        'catalogNumber': '',
        'reactiveSpecies': []
    }

    # Find antibody mention and get surrounding context
    pattern = re.escape(antibody_name)
    match = re.search(pattern, context, re.IGNORECASE)
    if not match:
        return metadata

    start = max(0, match.start() - window)
    end = min(len(context), match.end() + window)
    local_context = context[start:end]

    # Extract clonality
    for clonality, pattern in CLONALITY_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['clonality'] = clonality.capitalize()
            break

    # Extract host organism
    for host, pattern in HOST_ORGANISM_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['hostOrganism'] = host
            break

    # Extract vendor
    for vendor, pattern in VENDOR_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['vendor'] = vendor
            break

    # Extract catalog number
    catalog_match = re.search(CATALOG_NUMBER_PATTERN, local_context, re.IGNORECASE)
    if catalog_match:
        metadata['catalogNumber'] = catalog_match.group(1).replace(' ', '')

    # Extract reactive species
    for species, pattern in REACTIVE_SPECIES_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['reactiveSpecies'].append(species)

    return metadata


# ============================================================================
# Cell Line Metadata Extraction
# ============================================================================

CELL_LINE_CATEGORY_PATTERNS = {
    'Cancer cell line': r'\b(cancer|tumor|tumour|carcinoma|sarcoma|glioma|melanoma|leukemia)\b',
    'Normal cell line': r'\b(normal|primary|non-transformed|wild[- ]?type)\b',
    'Immortalized cell line': r'\b(immortalized|transformed|hTERT)\b'
}

ORGAN_PATTERNS = {
    'Brain': r'\b(brain|neural|neuronal|glial|astrocyte|glioma)\b',
    'Nerve': r'\b(nerve|schwann|neurofibroma|MPNST)\b',
    'Blood': r'\b(blood|leukemia|lymphoma|PBMC|lymphocyte)\b',
    'Skin': r'\b(skin|dermal|melanoma|fibroblast|keratinocyte)\b',
    'Breast': r'\b(breast|mammary)\b',
    'Lung': r'\b(lung|pulmonary)\b',
    'Kidney': r'\b(kidney|renal)\b',
    'Liver': r'\b(liver|hepatic)\b'
}

TISSUE_PATTERNS = {
    'Blood': r'\b(blood|serum|plasma)\b',
    'Nerve': r'\b(nerve|peripheral\s+nerve)\b',
    'Skin': r'\b(skin|dermal)\b',
    'Tumor': r'\b(tumor|tumour|neoplasm)\b'
}


def extract_cell_line_metadata(cell_line_name: str, context: str, window: int = 200) -> Dict:
    """Extract metadata for a cell line from surrounding context."""
    metadata = {
        'cellLineCategory': '',
        'organ': '',
        'tissue': ''
    }

    # Find cell line mention and get surrounding context
    pattern = re.escape(cell_line_name)
    match = re.search(pattern, context, re.IGNORECASE)
    if not match:
        return metadata

    start = max(0, match.start() - window)
    end = min(len(context), match.end() + window)
    local_context = context[start:end]

    # Extract category
    for category, pattern in CELL_LINE_CATEGORY_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['cellLineCategory'] = category
            break

    # Extract organ
    for organ, pattern in ORGAN_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['organ'] = organ
            break

    # Extract tissue
    for tissue, pattern in TISSUE_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['tissue'] = tissue
            break

    return metadata


# ============================================================================
# Animal Model Metadata Extraction
# ============================================================================

BACKGROUND_STRAIN_PATTERNS = {
    'C57BL/6': r'\b(C57BL/6|C57|B6)\b',
    'FVB': r'\bFVB\b',
    '129': r'\b129[A-Z/]*\b',
    'BALB/c': r'\bBALB/c\b',
    'CD-1': r'\bCD-1\b',
    'NOD': r'\bNOD\b',
    'Swiss': r'\bSwiss\b'
}

SUBSTRAIN_PATTERNS = {
    'C57BL/6J': r'\bC57BL/6J\b',
    'C57BL/6N': r'\bC57BL/6N\b',
    'FVB/N': r'\bFVB/N\b',
    'FVB/NJ': r'\bFVB/NJ\b'
}

MANIFESTATION_PATTERNS = {
    'Malignant Peripheral Nerve Sheath Tumor': r'\b(MPNST|malignant\s+peripheral\s+nerve\s+sheath\s+tumor)\b',
    'Plexiform Neurofibroma': r'\b(plexiform\s+neurofibroma|PNF)\b',
    'Optic Nerve Glioma': r'\b(optic\s+(?:nerve\s+)?glioma|OPG)\b',
    'Astrocytoma': r'\bastrocytoma\b',
    'Cognition': r'\b(cognitive|learning|memory)\s+(deficit|impairment)\b',
    'Growth': r'\b(growth|size)\s+(deficit|reduction)\b'
}

ALLELE_TYPE_PATTERNS = {
    'Null/knockout': r'\b(knockout|null|KO|deletion|del)\b',
    'Conditional ready': r'\b(flox|lox|conditional)\b',
    'Knockdown': r'\b(knockdown|shRNA|siRNA)\b',
    'Reporter': r'\b(reporter|GFP|RFP|luciferase|lacZ)\b',
    'Recombinase': r'\b(Cre|recombinase)\b',
    'Humanized sequence': r'\b(humanized|human\s+sequence)\b'
}


def extract_animal_model_metadata(model_name: str, context: str, window: int = 200) -> Dict:
    """Extract metadata for an animal model from surrounding context."""
    metadata = {
        'backgroundStrain': '',
        'backgroundSubstrain': '',
        'animalModelOfManifestation': [],
        'alleleType': []
    }

    # Find model mention and get surrounding context
    pattern = re.escape(model_name)
    match = re.search(pattern, context, re.IGNORECASE)
    if not match:
        return metadata

    start = max(0, match.start() - window)
    end = min(len(context), match.end() + window)
    local_context = context[start:end]

    # Extract background strain
    for strain, pattern in BACKGROUND_STRAIN_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['backgroundStrain'] = strain
            break

    # Extract substrain
    for substrain, pattern in SUBSTRAIN_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['backgroundSubstrain'] = substrain
            break

    # Extract manifestations
    for manifestation, pattern in MANIFESTATION_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['animalModelOfManifestation'].append(manifestation)

    # Extract allele types
    for allele_type, pattern in ALLELE_TYPE_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['alleleType'].append(allele_type)

    return metadata


# ============================================================================
# Genetic Reagent Metadata Extraction
# ============================================================================

VECTOR_TYPE_PATTERNS = {
    'Plasmid': r'\b(plasmid|pDNA)\b',
    'Lentiviral Vector': r'\b(lentivir[ual]|pLKO|pLenti)\b',
    'Retroviral Vector': r'\b(retrovir[ual]|pMSCV|pBabe)\b',
    'Adenoviral Vector': r'\b(adenovir[ual]|AAV)\b',
    'Expression Vector': r'\b(expression\s+vector|pCMV|pcDNA)\b',
    'shRNA Vector': r'\b(shRNA|pSUPER|pSilencer)\b',
    'CRISPR Vector': r'\b(CRISPR|Cas9|pX)\b',
    'Transfer Vector': r'\btransfer\s+vector\b'
}

BACTERIAL_RESISTANCE_PATTERNS = {
    'Ampicillin': r'\b(ampicillin|Amp|AmpR)\b',
    'Kanamycin': r'\b(kanamycin|Kan|KanR)\b',
    'Chloramphenicol': r'\b(chloramphenicol|Cam|CamR)\b',
    'Tetracycline': r'\b(tetracycline|Tet|TetR)\b',
    'Hygromycin': r'\b(hygromycin|Hyg|HygR)\b',
    'Zeocin': r'\b(zeocin|Zeo|ZeoR)\b',
    'Puromycin': r'\b(puromycin|Puro|PuroR)\b'
}

BACKBONE_PATTERNS = {
    'pcDNA3': r'\bpcDNA3\b',
    'pCMV': r'\bpCMV\b',
    'pLKO': r'\bpLKO\b',
    'pLenti': r'\bpLenti\b',
    'pRetro': r'\bpRetro\b'
}


def extract_genetic_reagent_metadata(reagent_name: str, context: str, window: int = 200) -> Dict:
    """Extract metadata for a genetic reagent from surrounding context."""
    metadata = {
        'vectorType': [],
        'bacterialResistance': '',
        'vectorBackbone': ''
    }

    # Find reagent mention and get surrounding context
    pattern = re.escape(reagent_name)
    match = re.search(pattern, context, re.IGNORECASE)
    if not match:
        return metadata

    start = max(0, match.start() - window)
    end = min(len(context), match.end() + window)
    local_context = context[start:end]

    # Extract vector type
    for vtype, pattern in VECTOR_TYPE_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['vectorType'].append(vtype)

    # Extract bacterial resistance
    for resistance, pattern in BACTERIAL_RESISTANCE_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['bacterialResistance'] = resistance
            break

    # Extract vector backbone
    for backbone, pattern in BACKBONE_PATTERNS.items():
        if re.search(pattern, local_context, re.IGNORECASE):
            metadata['vectorBackbone'] = backbone
            break

    return metadata


# ============================================================================
# Main extraction function
# ============================================================================

def extract_all_metadata(tool_name: str, tool_type: str, methods_text: str) -> Dict:
    """
    Extract all relevant metadata for a tool based on its type.

    Args:
        tool_name: Name of the tool
        tool_type: Type of tool (antibody, cell_line, animal_model, genetic_reagent)
        methods_text: Full methods section text

    Returns:
        Dictionary with extracted metadata
    """
    if tool_type == 'antibodies':
        return extract_antibody_metadata(tool_name, methods_text)
    elif tool_type == 'cell_lines':
        return extract_cell_line_metadata(tool_name, methods_text)
    elif tool_type == 'animal_models':
        return extract_animal_model_metadata(tool_name, methods_text)
    elif tool_type == 'genetic_reagents':
        return extract_genetic_reagent_metadata(tool_name, methods_text)
    else:
        return {}
