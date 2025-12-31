#!/usr/bin/env python3
"""
Improved publication mining using existing tool-publication links as training data.

This script:
1. Analyzes existing tools and their linked publications
2. Learns patterns from actual tool names, descriptions, and contexts
3. Uses these patterns to more accurately identify similar tools in unlinked publications
"""

import synapseclient
import pandas as pd
import re
from collections import defaultdict, Counter
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime
from difflib import SequenceMatcher

# Login to Synapse
syn = synapseclient.Synapse()
syn.login()

print("=" * 80)
print("TRAINED PUBLICATION MINING FOR NOVEL TOOLS")
print("=" * 80)

# Load existing tools from all tables
print("\n1. Loading existing tools from database...")

print("   Loading Animal Models...")
am_query = syn.tableQuery("SELECT * FROM syn26486808")
animal_models = am_query.asDataFrame()
print(f"   - {len(animal_models)} animal models")

print("   Loading Antibodies...")
ab_query = syn.tableQuery("SELECT * FROM syn26486811")
antibodies = ab_query.asDataFrame()
print(f"   - {len(antibodies)} antibodies")

print("   Loading Cell Lines...")
cl_query = syn.tableQuery("SELECT * FROM syn26486823")
cell_lines = cl_query.asDataFrame()
print(f"   - {len(cell_lines)} cell lines")

print("   Loading Genetic Reagents...")
gr_query = syn.tableQuery("SELECT * FROM syn26486832")
genetic_reagents = gr_query.asDataFrame()
print(f"   - {len(genetic_reagents)} genetic reagents")

# Load publications and links
print("\n2. Loading publications and existing links...")
pub_query = syn.tableQuery("SELECT * FROM syn16857542")
all_pubs = pub_query.asDataFrame()

link_query = syn.tableQuery("SELECT * FROM syn51735450")
links_df = link_query.asDataFrame()
print(f"   - {len(all_pubs)} total publications")
print(f"   - {len(links_df)} tool-publication links")

# Build training data from existing tools
print("\n3. Building training patterns from existing tools...")

# Extract actual tool names
tool_patterns = {
    'cell_lines': [],
    'antibodies': [],
    'animal_models': [],
    'genetic_reagents': []
}

# Cell line patterns
if 'resourceName' in cell_lines.columns:
    cell_line_names = cell_lines['resourceName'].dropna().unique()
    tool_patterns['cell_lines'] = list(cell_line_names)
    print(f"   - Learned {len(cell_line_names)} cell line names")

# Antibody patterns - extract targets
if 'targetAntigen' in antibodies.columns:
    antibody_targets = antibodies['targetAntigen'].dropna().unique()
    tool_patterns['antibodies'] = list(antibody_targets)
    print(f"   - Learned {len(antibody_targets)} antibody targets")

# Animal model patterns - extract strain info
if 'backgroundStrain' in animal_models.columns:
    model_strains = animal_models['backgroundStrain'].dropna().unique()
    tool_patterns['animal_models'].extend(list(model_strains))

if 'resourceName' in animal_models.columns:
    model_names = animal_models['resourceName'].dropna().unique()
    tool_patterns['animal_models'].extend(list(model_names))

tool_patterns['animal_models'] = list(set(tool_patterns['animal_models']))
print(f"   - Learned {len(tool_patterns['animal_models'])} animal model names/strains")

# Genetic reagent patterns - extract names
if 'insertName' in genetic_reagents.columns:
    reagent_names = genetic_reagents['insertName'].dropna().unique()
    tool_patterns['genetic_reagents'].extend(list(reagent_names))

if 'resourceName' in genetic_reagents.columns:
    reagent_resource_names = genetic_reagents['resourceName'].dropna().unique()
    tool_patterns['genetic_reagents'].extend(list(reagent_resource_names))

tool_patterns['genetic_reagents'] = list(set(tool_patterns['genetic_reagents']))
print(f"   - Learned {len(tool_patterns['genetic_reagents'])} genetic reagent names")

# Analyze linked publications to understand context
print("\n4. Analyzing context from linked publications...")

linked_pubs = all_pubs[
    all_pubs['pmid'].isin(links_df['pmid'].dropna()) |
    all_pubs['doi'].isin(links_df['doi'].dropna())
].copy()

print(f"   - {len(linked_pubs)} publications with existing tool links")

# Extract common words/phrases from linked publications (if abstract available)
if 'abstract' in linked_pubs.columns:
    linked_abstracts = ' '.join(linked_pubs['abstract'].dropna().astype(str))
    # This gives us context about how tools are described

# Find unlinked publications
linked_pmids = set(links_df['pmid'].dropna().unique())
linked_dois = set(links_df['doi'].dropna().unique())

unlinked_pubs = all_pubs[
    ~all_pubs['pmid'].isin(linked_pmids) &
    ~all_pubs['doi'].isin(linked_dois)
].copy()

print(f"\n5. Found {len(unlinked_pubs)} unlinked publications to mine")

def fuzzy_match(text, patterns, threshold=0.85):
    """Find fuzzy matches for patterns in text"""
    if pd.isna(text):
        return []

    text = str(text)
    matches = []

    for pattern in patterns:
        if pd.isna(pattern) or len(str(pattern)) < 3:
            continue

        pattern_str = str(pattern)

        # Exact match (case-insensitive)
        if re.search(re.escape(pattern_str), text, re.IGNORECASE):
            matches.append(pattern_str)
            continue

        # Fuzzy match for longer patterns
        if len(pattern_str) > 5:
            # Split text into words/phrases
            text_lower = text.lower()
            pattern_lower = pattern_str.lower()

            # Check if pattern appears as substring
            if pattern_lower in text_lower:
                matches.append(pattern_str)
                continue

            # Word-level fuzzy matching
            words = re.findall(r'\b\w+\b', text_lower)
            for i in range(len(words) - len(pattern_lower.split()) + 1):
                window = ' '.join(words[i:i+len(pattern_lower.split())])
                similarity = SequenceMatcher(None, pattern_lower, window).ratio()
                if similarity >= threshold:
                    matches.append(pattern_str)
                    break

    return list(set(matches))

def find_tools_trained(text, tool_patterns):
    """Find tools using trained patterns"""
    results = {
        'cell_lines': [],
        'antibodies': [],
        'animal_models': [],
        'genetic_reagents': []
    }

    if pd.isna(text):
        return results

    # Search for each tool type
    for tool_type, patterns in tool_patterns.items():
        # Use both exact and fuzzy matching
        matches = fuzzy_match(text, patterns, threshold=0.88)
        results[tool_type] = matches[:10]  # Limit to top 10

    return results

# Additional context-based detection
def extract_cell_line_mentions(text):
    """Extract cell line mentions using learned patterns + context"""
    if pd.isna(text):
        return []

    text = str(text)
    mentions = []

    # Look for "cell line" context
    cell_line_contexts = [
        r'cell\s+lines?\s+([A-Z][A-Za-z0-9\-]+)',
        r'([A-Z][A-Za-z0-9\-]+)\s+cells?\s+(?:were|was)',
        r'([A-Z]{2,}[\-\s]?[0-9]+)\s+(?:cells?|cell line)',
    ]

    for pattern in cell_line_contexts:
        matches = re.findall(pattern, text)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            if len(match) > 2 and len(match) < 30:
                mentions.append(match)

    return list(set(mentions))

def extract_antibody_mentions(text):
    """Extract antibody mentions using learned targets + context"""
    if pd.isna(text):
        return []

    text = str(text)
    mentions = []

    # Look for antibody context
    antibody_contexts = [
        r'anti(?:body|-|\s+)([A-Z][A-Za-z0-9]+)',
        r'([A-Z][A-Za-z0-9]+)\s+antibod',
        r'antibod(?:y|ies)\s+(?:to|against)\s+([A-Z][A-Za-z0-9]+)',
    ]

    for pattern in antibody_contexts:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            if len(match) > 2 and len(match) < 30:
                mentions.append(match)

    return list(set(mentions))

def extract_model_mentions(text):
    """Extract animal model mentions using learned strains + context"""
    if pd.isna(text):
        return []

    text = str(text)
    mentions = []

    # Look for mouse strain patterns
    strain_patterns = [
        r'\b(C57BL/6[JN]?|BALB/c|FVB[/]?N?|NOD|NSG|nude)\b',
        r'Nf1[+\-/]+',
        r'\b([A-Z][a-z]+)\s*[;/]\s*([A-Z][a-z]+)',  # Strain nomenclature
    ]

    for pattern in strain_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if isinstance(match, tuple):
                match = '/'.join([m for m in match if m])
            if len(match) > 1:
                mentions.append(match)

    return list(set(mentions))

# Mine publications using trained approach
print("\n6. Mining publications with trained patterns...")

findings = []
stats = {
    'trained_matches': 0,
    'context_matches': 0,
    'combined_matches': 0
}

for idx, row in unlinked_pubs.iterrows():
    # Use title and any available text fields
    text_parts = [row.get('title', '')]
    if 'abstract' in row and pd.notna(row.get('abstract')):
        text_parts.append(row.get('abstract'))
    text = ' '.join(text_parts)

    # Use trained patterns
    trained_tools = find_tools_trained(text, tool_patterns)

    # Use context-based extraction
    context_cell_lines = extract_cell_line_mentions(text)
    context_antibodies = extract_antibody_mentions(text)
    context_models = extract_model_mentions(text)

    # Combine results
    all_cell_lines = list(set(trained_tools['cell_lines'] + context_cell_lines))
    all_antibodies = list(set(trained_tools['antibodies'] + context_antibodies))
    all_models = list(set(trained_tools['animal_models'] + context_models))
    all_reagents = trained_tools['genetic_reagents']

    # Track statistics
    if any(trained_tools.values()):
        stats['trained_matches'] += 1
    if context_cell_lines or context_antibodies or context_models:
        stats['context_matches'] += 1
    if all_cell_lines or all_antibodies or all_models or all_reagents:
        stats['combined_matches'] += 1

        findings.append({
            'pmid': row.get('pmid'),
            'doi': row.get('doi'),
            'title': row.get('title'),
            'journal': row.get('journal'),
            'year': row.get('year'),
            'fundingAgency': row.get('fundingAgency'),
            'cell_lines': ', '.join(all_cell_lines[:5]) if all_cell_lines else '',
            'antibodies': ', '.join(all_antibodies[:5]) if all_antibodies else '',
            'animal_models': ', '.join(all_models[:5]) if all_models else '',
            'genetic_reagents': ', '.join(all_reagents[:5]) if all_reagents else '',
            'tool_count': len(all_cell_lines) + len(all_antibodies) + len(all_models) + len(all_reagents),
            'match_source': 'trained' if any(trained_tools.values()) else 'context'
        })

findings_df = pd.DataFrame(findings)

print(f"\n7. Mining Results (Trained Approach):")
print(f"   Publications with tools found: {len(findings_df)}/{len(unlinked_pubs)}")
print(f"   ({len(findings_df)/len(unlinked_pubs)*100:.1f}% of unlinked publications)")
print(f"\n   Detection breakdown:")
print(f"   - Trained pattern matches: {stats['trained_matches']}")
print(f"   - Context-based matches: {stats['context_matches']}")
print(f"   - Combined unique: {stats['combined_matches']}")

# Summarize by tool type
tool_type_counts = {
    'Cell Lines': len(findings_df[findings_df['cell_lines'] != '']),
    'Antibodies': len(findings_df[findings_df['antibodies'] != '']),
    'Animal Models': len(findings_df[findings_df['animal_models'] != '']),
    'Genetic Reagents': len(findings_df[findings_df['genetic_reagents'] != ''])
}

print(f"\n   Publications by tool type:")
for tool_type, count in sorted(tool_type_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"   - {tool_type}: {count} publications")

# Compare to GFF publications
if 'fundingAgency' in findings_df.columns:
    findings_df['is_gff'] = findings_df['fundingAgency'].astype(str).str.contains('GFF', na=False)
    gff_findings = findings_df[findings_df['is_gff']]
    print(f"\n   GFF-funded publications with tools: {len(gff_findings)}")

# Save results
output_file = 'novel_tools_TRAINED_mining.csv'
findings_df.to_csv(output_file, index=False)
print(f"\n📄 Trained mining results saved to: {output_file}")

# Create prioritized lists
priority_df = findings_df.nlargest(30, 'tool_count')
priority_file = 'priority_publications_TRAINED.csv'
priority_df.to_csv(priority_file, index=False)
print(f"📄 Top 30 priority publications saved to: {priority_file}")

# Save GFF-specific findings
if len(gff_findings) > 0:
    gff_file = 'GFF_publications_with_tools_TRAINED.csv'
    gff_findings.to_csv(gff_file, index=False)
    print(f"📄 GFF publications with tools saved to: {gff_file}")

# Generate comparison report
print("\n8. Generating comparison report...")
pdf_file = 'Trained_Mining_Comparison_Report.pdf'

with PdfPages(pdf_file) as pdf:
    # Page 1: Comparison
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    fig.suptitle(f'Trained vs Untrained Mining Comparison\n{datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 fontsize=16, fontweight='bold')

    # Success rate comparison
    methods = ['Pattern-Based\n(Original)', 'Trained\n(Improved)']
    # Note: Update these with actual original results if available
    success_rates = [15.7, len(findings_df)/len(unlinked_pubs)*100]

    axes[0, 0].bar(methods, success_rates, color=['#95a5a6', '#2ecc71'])
    axes[0, 0].set_ylabel('Success Rate (%)')
    axes[0, 0].set_title('Mining Success Rate Comparison', fontweight='bold')
    axes[0, 0].set_ylim(0, max(success_rates) * 1.2)

    for i, v in enumerate(success_rates):
        axes[0, 0].text(i, v + 1, f'{v:.1f}%', ha='center', fontweight='bold')

    # Tool type distribution
    axes[0, 1].barh(list(tool_type_counts.keys()), list(tool_type_counts.values()), color='#3498db')
    axes[0, 1].set_xlabel('Number of Publications')
    axes[0, 1].set_title('Publications by Tool Type (Trained)', fontweight='bold')
    axes[0, 1].grid(axis='x', alpha=0.3)

    for i, v in enumerate(tool_type_counts.values()):
        axes[0, 1].text(v + 0.5, i, str(v), va='center')

    # Detection method breakdown
    detection_methods = ['Trained\nPatterns', 'Context\nBased', 'Total\nUnique']
    detection_counts = [stats['trained_matches'], stats['context_matches'], stats['combined_matches']]

    axes[1, 0].bar(detection_methods, detection_counts, color=['#e74c3c', '#f39c12', '#9b59b6'])
    axes[1, 0].set_ylabel('Number of Publications')
    axes[1, 0].set_title('Detection Method Breakdown', fontweight='bold')

    for i, v in enumerate(detection_counts):
        axes[1, 0].text(i, v + 0.5, str(v), ha='center', fontweight='bold')

    # Summary statistics
    improvement = len(findings_df)/len(unlinked_pubs)*100 - 15.7
    summary_text = f"""
📊 TRAINING IMPACT

Original (Pattern-Based):
- Success Rate: 15.7%
- Publications Found: 36

Trained Approach:
- Success Rate: {len(findings_df)/len(unlinked_pubs)*100:.1f}%
- Publications Found: {len(findings_df)}
- Improvement: {'+' if improvement >= 0 else ''}{improvement:.1f}%

Training Data Used:
- {len(cell_lines)} cell lines
- {len(antibodies)} antibodies
- {len(animal_models)} animal models
- {len(genetic_reagents)} genetic reagents

Detection Sources:
- Trained patterns: {stats['trained_matches']}
- Context-based: {stats['context_matches']}
- Combined: {stats['combined_matches']}

GFF Publications Found: {len(gff_findings) if 'is_gff' in findings_df.columns else 'N/A'}
    """

    axes[1, 1].text(0.1, 0.5, summary_text, transform=axes[1, 1].transAxes,
                   fontsize=9, verticalalignment='center', fontfamily='monospace',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    axes[1, 1].axis('off')

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()

    # Page 2: Top findings table
    if len(priority_df) > 0:
        fig, ax = plt.subplots(figsize=(11, 8.5))
        fig.suptitle('Top Priority Publications (Trained Mining)',
                    fontsize=14, fontweight='bold')

        table_cols = ['title', 'year', 'cell_lines', 'antibodies', 'animal_models', 'tool_count']
        table_data_cols = [col for col in table_cols if col in priority_df.columns]
        table_data = priority_df[table_data_cols].head(20).copy()

        # Truncate long text
        if 'title' in table_data.columns:
            table_data['title'] = table_data['title'].str[:35] + '...'
        for col in ['cell_lines', 'antibodies', 'animal_models']:
            if col in table_data.columns:
                table_data[col] = table_data[col].str[:25]

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
print("TRAINED WORKFLOW COMPLETE")
print("=" * 80)
print(f"""
Improvements from training:
- Used {len(cell_lines) + len(antibodies) + len(animal_models) + len(genetic_reagents)} existing tools as patterns
- Combined exact matching, fuzzy matching, and context-based detection
- Found {len(findings_df)} publications with potential tools
- {'Improved' if improvement >= 0 else 'Comparable'} success rate: {'+' if improvement >= 0 else ''}{improvement:.1f}%

Next steps:
1. Review {priority_file} for validated tool mentions
2. Compare with original mining results
3. Focus on tools with exact name matches first (highest confidence)
4. Verify fuzzy matches manually in full text
""")
