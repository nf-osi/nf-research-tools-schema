#!/usr/bin/env python3
"""
Test metadata extraction and pre-filling workflow.
"""

import pandas as pd
import json

# Create test data with realistic metadata
test_metadata = {
    "antibodies:CD117": {
        "clonality": "Monoclonal",
        "hostOrganism": "Mouse",
        "vendor": "BD Biosciences",
        "catalogNumber": "553869",
        "reactiveSpecies": ["Human", "Mouse"]
    },
    "antibodies:KIT": {
        "clonality": "Polyclonal",
        "hostOrganism": "Rabbit",
        "vendor": "Cell Signaling",
        "catalogNumber": "3074S",
        "reactiveSpecies": ["Human", "Mouse", "Rat"]
    },
    "cell_lines:ST88-14": {
        "cellLineCategory": "Cancer cell line",
        "organ": "Nerve",
        "tissue": "Tumor"
    },
    "cell_lines:ipNF95.11C": {
        "cellLineCategory": "Normal cell line",
        "organ": "Nerve",
        "tissue": "Nerve"
    },
    "animal_models:Nf1flox/flox; PostnCre": {
        "backgroundStrain": "C57BL/6",
        "backgroundSubstrain": "C57BL/6J",
        "animalModelOfManifestation": ["Malignant Peripheral Nerve Sheath Tumor"],
        "alleleType": ["Conditional ready", "Recombinase"]
    },
    "genetic_reagents:pLKO.1-shKIT": {
        "vectorType": ["Lentiviral Vector", "shRNA Vector"],
        "bacterialResistance": "Ampicillin",
        "vectorBackbone": "pLKO"
    }
}

test_data = [
    {
        'pmid': 'PMID:31527226',
        'doi': '10.1158/1535-7163.MCT-19-0123',
        'title': 'Ketotifen Modulates Mast Cell Chemotaxis to Kit-Ligand',
        'journal': 'Molecular Cancer Therapeutics',
        'year': 2019,
        'fundingAgency': "['NTAP']",
        'cell_lines': 'ipNF95.11C, ST88-14',
        'antibodies': 'CD117, KIT',
        'animal_models': 'Nf1flox/flox; PostnCre',
        'genetic_reagents': 'pLKO.1-shKIT',
        'tool_count': 6,
        'methods_length': 3542,
        'is_gff': False,
        'tool_metadata': json.dumps(test_metadata)
    }
]

# Save as novel_tools_FULLTEXT_mining.csv
df = pd.DataFrame(test_data)
df.to_csv('novel_tools_FULLTEXT_mining.csv', index=False)

print("✓ Created test data with rich metadata: novel_tools_FULLTEXT_mining.csv")
print(f"  - {len(df)} publications")
print(f"  - {df['tool_count'].sum()} total tools")
print(f"\nMetadata examples:")
print(f"  - CD117 antibody: {test_metadata['antibodies:CD117']}")
print(f"  - ST88-14 cell line: {test_metadata['cell_lines:ST88-14']}")
print(f"  - Nf1flox/flox mouse: {test_metadata['animal_models:Nf1flox/flox; PostnCre']}")
print(f"  - pLKO.1-shKIT vector: {test_metadata['genetic_reagents:pLKO.1-shKIT']}")
