#!/usr/bin/env python3
"""
Create test data to validate the formatting script.
"""

import pandas as pd

# Create realistic test data that simulates full text mining results
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
        'is_gff': False
    },
    {
        'pmid': 'PMID:35945271',
        'doi': '10.1038/s10038-022-01072-7',
        'title': 'Functional restoration of mouse Nf1 nonsense alleles',
        'journal': 'Journal of Human Genetics',
        'year': 2022,
        'fundingAgency': "['GFF']",
        'cell_lines': '',
        'antibodies': 'NF1, phospho-ERK',
        'animal_models': 'Nf1tm1.1Tyj',
        'genetic_reagents': 'TC7 antisense morpholino',
        'tool_count': 4,
        'methods_length': 2890,
        'is_gff': True
    },
    {
        'pmid': 'PMID:34694046',
        'doi': '10.1002/humu.24290',
        'title': 'Analysis of patient-specific NF1 variants',
        'journal': 'Human Mutation',
        'year': 2022,
        'fundingAgency': "['GFF']",
        'cell_lines': 'HEK293T',
        'antibodies': 'NF1-GAP',
        'animal_models': '',
        'genetic_reagents': 'pcDNA3.1-NF1',
        'tool_count': 3,
        'methods_length': 4123,
        'is_gff': True
    }
]

# Save as novel_tools_FULLTEXT_mining.csv
df = pd.DataFrame(test_data)
df.to_csv('novel_tools_FULLTEXT_mining.csv', index=False)

print("✓ Created test data: novel_tools_FULLTEXT_mining.csv")
print(f"  - {len(df)} publications")
print(f"  - {df['tool_count'].sum()} total tools")
print(f"  - {df['is_gff'].sum()} GFF publications")
