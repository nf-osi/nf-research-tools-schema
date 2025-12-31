#!/usr/bin/env python3
"""
Mine Methods sections from publications to identify novel tools.

This script:
1. Identifies publications NOT yet linked to tools
2. Extracts Methods sections or full text
3. Uses text mining to identify mentions of:
   - Cell lines
   - Antibodies
   - Animal models
   - Genetic reagents (plasmids, vectors, CRISPR constructs)
   - Biobanks
4. Proposes new tools to add to the database
"""

import synapseclient
import pandas as pd
import re
from collections import defaultdict
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime

# Login to Synapse
syn = synapseclient.Synapse()
syn.login()

print("=" * 80)
print("PUBLICATION MINING FOR NOVEL TOOLS")
print("=" * 80)

# Query publications
print("\n1. Loading publications table (syn16857542)...")
pub_query = syn.tableQuery("SELECT * FROM syn16857542")
all_pubs = pub_query.asDataFrame()
print(f"   Total publications: {len(all_pubs)}")

# Query existing tool-publication links
print("\n2. Loading existing tool-publication links (syn51735450)...")
link_query = syn.tableQuery("SELECT pmid, doi FROM syn51735450")
links_df = link_query.asDataFrame()
print(f"   Total tool-publication links: {len(links_df)}")

# Find publications NOT yet linked
linked_pmids = set(links_df['pmid'].dropna().unique())
linked_dois = set(links_df['doi'].dropna().unique())

unlinked_pubs = all_pubs[
    ~all_pubs['pmid'].isin(linked_pmids) &
    ~all_pubs['doi'].isin(linked_dois)
].copy()

print(f"\n3. Found {len(unlinked_pubs)} publications WITHOUT tool links")
print(f"   These publications will be mined for novel tools")

# Tool detection patterns
print("\n4. Setting up tool detection patterns...")

# Cell line patterns - specific names and common patterns
CELL_LINE_PATTERNS = {
    'specific_lines': [
        # NF-specific cell lines
        r'\b(ST88-14|S462|STS26T|T265|SNF[0-9]{2}\.[0-9]+|NF1-MPNST)\b',
        r'\b(ipn[0-9]+\.[0-9]+|ipNF[0-9]+\.[0-9]+)\b',
        r'\b(HEK[-\s]?293T?|HeLa|U2OS|NIH3T3|MEF)\b',
        r'\b(Schwann|schwann)\s+cell(?:s)?\s+(?:line|culture)',
        r'\b(plexiform neurofibroma|pNF)\s+cell(?:s)?\s+(?:line|culture)',
        r'\b(MPNST|mpnst)\s+cell(?:s)?\s+(?:line|culture)',
    ],
    'generic_patterns': [
        r'cell\s+line[s]?\s+([A-Z][A-Za-z0-9\-]+)',
        r'([A-Z]{2,}[\-\s]?[0-9]+[A-Za-z]*)\s+cells?',
    ]
}

# Antibody patterns
ANTIBODY_PATTERNS = {
    'catalog_numbers': [
        r'(?:catalog|cat\.?|#)\s*([A-Z0-9\-]+)',
        r'\(([A-Z][a-z]+),\s*([A-Z0-9\-]+)\)',  # (Vendor, catalog#)
    ],
    'antibody_targets': [
        r'anti-([A-Z][A-Za-z0-9]+)\s+antibod',
        r'([A-Z][A-Za-z0-9]+)\s+antibod',
        r'antibod(?:y|ies)\s+(?:to|against|targeting)\s+([A-Z][A-Za-z0-9]+)',
    ],
    'vendors': [
        r'\((Abcam|Cell Signaling|Santa Cruz|Sigma|Thermo|Invitrogen|BD Biosciences|R&D Systems|BioLegend)',
    ]
}

# Animal model patterns
ANIMAL_MODEL_PATTERNS = {
    'mouse_strains': [
        r'\b(C57BL/6J?|C57BL/6N|BALB/c|FVB|NOD|NSG|nude)\b',
        r'Nf1\s*[+\-/]+',
        r'\b(wildtype|wild-type|WT|mutant|knockout|KO)\s+mice',
    ],
    'genetic_modifications': [
        r'(Cre|loxP|flox)',
        r'(transgenic|knock-?in|knock-?out)',
        r'Nf1[-/]?([A-Za-z0-9]+)',
    ],
    'models': [
        r'(xenograft|allograft|syngeneic)\s+model',
        r'(GEM|genetically engineered)\s+(?:mouse|mice)',
    ]
}

# Genetic reagent patterns
GENETIC_REAGENT_PATTERNS = {
    'plasmids': [
        r'plasmid[s]?\s+([A-Za-z0-9\-]+)',
        r'vector[s]?\s+([A-Za-z0-9\-]+)',
        r'(p[A-Z][A-Za-z0-9\-]+)\s+(?:plasmid|vector)',
    ],
    'crispr': [
        r'(sg|guide)\s*RNA[s]?\s+targeting\s+([A-Z][A-Za-z0-9]+)',
        r'CRISPR[/-]Cas9',
        r'(sg|g)RNA[s]?\s+([A-Z0-9\-]+)',
    ],
    'shrna': [
        r'sh(?:RNA|rna)[s]?\s+(?:targeting|against)\s+([A-Z][A-Za-z0-9]+)',
        r'([A-Z][A-Za-z0-9]+)\s+sh(?:RNA|rna)',
    ]
}

def extract_methods_section(text):
    """Extract Methods section from publication text"""
    if pd.isna(text):
        return ""

    text = str(text).lower()

    # Common Methods section headers
    methods_patterns = [
        r'methods?\s+and\s+materials?',
        r'materials?\s+and\s+methods?',
        r'experimental\s+procedures?',
        r'methods?',
    ]

    for pattern in methods_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Extract text after Methods header (next 2000 characters)
            start = match.end()
            return text[start:start+2000]

    # If no Methods section found, return full text (truncated)
    return text[:2000]

def find_cell_lines(text):
    """Identify cell line mentions in text"""
    if pd.isna(text):
        return []

    text = str(text)
    found = []

    # Check specific cell lines
    for pattern in CELL_LINE_PATTERNS['specific_lines']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found.extend(matches)

    # Check generic patterns
    for pattern in CELL_LINE_PATTERNS['generic_patterns']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if isinstance(matches[0], tuple) if matches else False:
            found.extend([m[0] if isinstance(m, tuple) else m for m in matches])
        else:
            found.extend(matches)

    return list(set([m for m in found if len(str(m)) > 2]))

def find_antibodies(text):
    """Identify antibody mentions in text"""
    if pd.isna(text):
        return []

    text = str(text)
    found = []

    # Find targets
    for pattern in ANTIBODY_PATTERNS['antibody_targets']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found.extend([f"anti-{m}" if not m.startswith('anti-') else m for m in matches])

    # Find vendors and catalog numbers
    vendors = []
    for pattern in ANTIBODY_PATTERNS['vendors']:
        vendors.extend(re.findall(pattern, text))

    catalogs = []
    for pattern in ANTIBODY_PATTERNS['catalog_numbers']:
        catalogs.extend(re.findall(pattern, text))

    # Combine if both found
    if vendors and catalogs:
        found.extend([f"{v}:{c}" for v in vendors[:3] for c in catalogs[:3]])

    return list(set([m for m in found if len(str(m)) > 2]))[:10]

def find_animal_models(text):
    """Identify animal model mentions in text"""
    if pd.isna(text):
        return []

    text = str(text)
    found = []

    # Mouse strains
    for pattern in ANIMAL_MODEL_PATTERNS['mouse_strains']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found.extend(matches)

    # Genetic modifications
    for pattern in ANIMAL_MODEL_PATTERNS['genetic_modifications']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found.extend(matches)

    return list(set([m for m in found if len(str(m)) > 1]))[:10]

def find_genetic_reagents(text):
    """Identify genetic reagent mentions in text"""
    if pd.isna(text):
        return []

    text = str(text)
    found = []

    # Plasmids
    for pattern in GENETIC_REAGENT_PATTERNS['plasmids']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if isinstance(matches[0], str) if matches else False:
            found.extend([m for m in matches if len(str(m)) > 2])

    # CRISPR
    for pattern in GENETIC_REAGENT_PATTERNS['crispr']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            found.append('CRISPR/Cas9')

    # shRNA
    for pattern in GENETIC_REAGENT_PATTERNS['shrna']:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if isinstance(matches[0], str) if matches else False:
            found.extend([f"shRNA-{m}" for m in matches if len(str(m)) > 2])

    return list(set(found))[:10]

# Mine publications
print("\n5. Mining publications for tools...")
print(f"   Processing {len(unlinked_pubs)} unlinked publications...")

tool_findings = []

for idx, row in unlinked_pubs.iterrows():
    # Combine abstract and title for mining
    text = f"{row.get('title', '')} {row.get('abstract', '')}"
    methods_text = extract_methods_section(row.get('abstract', ''))

    # Mine for tools
    cell_lines = find_cell_lines(text + ' ' + methods_text)
    antibodies = find_antibodies(text + ' ' + methods_text)
    models = find_animal_models(text + ' ' + methods_text)
    reagents = find_genetic_reagents(text + ' ' + methods_text)

    if cell_lines or antibodies or models or reagents:
        tool_findings.append({
            'pmid': row.get('pmid'),
            'doi': row.get('doi'),
            'title': row.get('title'),
            'journal': row.get('journal'),
            'year': row.get('year'),
            'cell_lines': ', '.join(cell_lines[:5]) if cell_lines else '',
            'antibodies': ', '.join(antibodies[:5]) if antibodies else '',
            'animal_models': ', '.join(models[:5]) if models else '',
            'genetic_reagents': ', '.join(reagents[:5]) if reagents else '',
            'tool_count': len(cell_lines) + len(antibodies) + len(models) + len(reagents)
        })

findings_df = pd.DataFrame(tool_findings)

print(f"\n6. Mining Results:")
print(f"   Publications with potential tools: {len(findings_df)}/{len(unlinked_pubs)}")
print(f"   ({len(findings_df)/len(unlinked_pubs)*100:.1f}% of unlinked publications)")

# Summarize by tool type
tool_type_counts = {
    'Cell Lines': len(findings_df[findings_df['cell_lines'] != '']),
    'Antibodies': len(findings_df[findings_df['antibodies'] != '']),
    'Animal Models': len(findings_df[findings_df['animal_models'] != '']),
    'Genetic Reagents': len(findings_df[findings_df['genetic_reagents'] != ''])
}

print(f"\n   Publications mentioning each tool type:")
for tool_type, count in sorted(tool_type_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"   - {tool_type}: {count} publications")

# Save findings
output_file = 'novel_tools_mined_from_publications.csv'
findings_df.to_csv(output_file, index=False)
print(f"\n📄 Novel tool findings saved to: {output_file}")

# Generate prioritized list
priority_df = findings_df.nlargest(20, 'tool_count')
priority_file = 'priority_publications_to_review.csv'
priority_df.to_csv(priority_file, index=False)
print(f"📄 Top 20 priority publications saved to: {priority_file}")

# Generate PDF report
print("\n7. Generating PDF report...")
pdf_file = 'Novel_Tools_Mining_Report.pdf'

with PdfPages(pdf_file) as pdf:
    # Page 1: Summary
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    fig.suptitle(f'Publication Mining for Novel Tools\n{datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 fontsize=16, fontweight='bold')

    # Mining success rate
    success_data = [len(findings_df), len(unlinked_pubs) - len(findings_df)]
    colors = ['#2ecc71', '#95a5a6']
    labels = [f'With Tools\n({len(findings_df)})', f'No Tools Found\n({len(unlinked_pubs) - len(findings_df)})']

    axes[0, 0].pie(success_data, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    axes[0, 0].set_title('Mining Success Rate', fontweight='bold')

    # Tool type distribution
    axes[0, 1].barh(list(tool_type_counts.keys()), list(tool_type_counts.values()), color='#3498db')
    axes[0, 1].set_xlabel('Number of Publications')
    axes[0, 1].set_title('Publications by Tool Type', fontweight='bold')
    axes[0, 1].grid(axis='x', alpha=0.3)

    for i, v in enumerate(tool_type_counts.values()):
        axes[0, 1].text(v + 0.5, i, str(v), va='center')

    # Publications by year (if year data available)
    if 'year' in findings_df.columns:
        year_counts = findings_df['year'].value_counts().sort_index()
        axes[1, 0].bar(year_counts.index, year_counts.values, color='#e74c3c')
        axes[1, 0].set_xlabel('Year')
        axes[1, 0].set_ylabel('Number of Publications')
        axes[1, 0].set_title('Publications with Tools by Year', fontweight='bold')
        axes[1, 0].grid(axis='y', alpha=0.3)

    # Summary statistics
    summary_text = f"""
📊 MINING SUMMARY

Total Publications Analyzed: {len(unlinked_pubs)}
Publications with Tools Found: {len(findings_df)}
Success Rate: {len(findings_df)/len(unlinked_pubs)*100:.1f}%

Tool Mentions by Type:
- Cell Lines: {tool_type_counts['Cell Lines']} pubs
- Antibodies: {tool_type_counts['Antibodies']} pubs
- Animal Models: {tool_type_counts['Animal Models']} pubs
- Genetic Reagents: {tool_type_counts['Genetic Reagents']} pubs

Next Steps:
1. Review priority_publications_to_review.csv
2. Verify tool mentions in full text
3. Add confirmed tools to database
4. Link tools to publications in syn51735450
    """

    axes[1, 1].text(0.1, 0.5, summary_text, transform=axes[1, 1].transAxes,
                   fontsize=9, verticalalignment='center', fontfamily='monospace',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    axes[1, 1].axis('off')

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()

    # Page 2: Top priority publications
    if len(priority_df) > 0:
        fig, ax = plt.subplots(figsize=(11, 8.5))
        fig.suptitle('Top 20 Publications to Review (Most Tool Mentions)',
                    fontsize=14, fontweight='bold')

        table_cols = ['title', 'year', 'cell_lines', 'antibodies', 'animal_models', 'tool_count']
        table_data_cols = [col for col in table_cols if col in priority_df.columns]
        table_data = priority_df[table_data_cols].head(20).copy()

        # Truncate long text
        if 'title' in table_data.columns:
            table_data['title'] = table_data['title'].str[:40] + '...'
        for col in ['cell_lines', 'antibodies', 'animal_models']:
            if col in table_data.columns:
                table_data[col] = table_data[col].str[:30]

        ax.axis('tight')
        ax.axis('off')

        table = ax.table(cellText=table_data.values,
                        colLabels=table_data.columns,
                        cellLoc='left',
                        loc='center')

        table.auto_set_font_size(False)
        table.set_fontsize(7)
        table.scale(1, 2)

        for i in range(len(table_data.columns)):
            table[(0, i)].set_facecolor('#3498db')
            table[(0, i)].set_text_props(weight='bold', color='white')

        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

print(f"📊 PDF report generated: {pdf_file}")

print("\n" + "=" * 80)
print("WORKFLOW COMPLETE")
print("=" * 80)
print(f"""
Next steps:
1. Review {priority_file} for high-priority publications
2. Access full text to verify tool mentions
3. For each confirmed tool:
   - Add to appropriate table (syn26486808, syn26486811, etc.)
   - Get detailed information (vendor, catalog#, etc.)
   - Link to publication in syn51735450
4. Focus on publications with highest tool_count first
""")
