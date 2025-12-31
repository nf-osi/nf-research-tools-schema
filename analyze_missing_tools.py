#!/usr/bin/env python3
"""
Analyze publications in syn16857542 to identify missing tools that should be
represented in the tools materialized view syn51730943.

Focus on GFF-funded tools and aim for 80% coverage.
"""

import synapseclient
import pandas as pd
import re
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime
import os

# Login to Synapse
syn = synapseclient.Synapse()
auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
if auth_token:
    syn.login(authToken=auth_token)
else:
    syn.login()  # Interactive login if no token

print("=" * 80)
print("TOOL COVERAGE ANALYSIS: Publications vs Tools Database")
print("=" * 80)

# Query publications table
print("\n1. Querying publications table (syn16857542)...")
pub_query = syn.tableQuery("SELECT * FROM syn16857542")
pub_df = pub_query.asDataFrame()

# Filter for GFF-funded publications (GFF can appear alone or with other funders)
if 'fundingAgency' in pub_df.columns:
    # fundingAgency is stored as string representations of lists, e.g., "[GFF]" or "[NTAP, CTF, GFF]"
    pub_df['is_gff'] = pub_df['fundingAgency'].astype(str).str.contains('GFF', na=False)
    pub_df = pub_df[pub_df['is_gff']].copy()

print(f"   Found {len(pub_df)} GFF-funded publications")
print(f"   Columns: {', '.join(pub_df.columns.tolist())}")

# Query tools materialized view
print("\n2. Querying tools materialized view (syn51730943)...")
tools_query = syn.tableQuery("SELECT resourceId, resourceName, resourceType FROM syn51730943")
tools_df = tools_query.asDataFrame()

print(f"   Found {len(tools_df)} total tools in database")
print(f"   Resource types: {tools_df['resourceType'].value_counts().to_dict()}")

# Query resource-publication linking table
print("\n3. Querying resource-publication linking table (syn51735450)...")
link_query = syn.tableQuery("SELECT * FROM syn51735450")
link_df = link_query.asDataFrame()

print(f"   Found {len(link_df)} resource-publication links")
if len(link_df) > 0:
    print(f"   Columns: {', '.join(link_df.columns.tolist())}")
    print(f"   Unique resources linked: {link_df['resourceId'].nunique() if 'resourceId' in link_df.columns else 'N/A'}")
    print(f"   Unique publications linked: {link_df['publicationId'].nunique() if 'publicationId' in link_df.columns else 'N/A'}")

# Query individual tool type tables to get more details
print("\n4. Querying individual tool type tables...")

# Animal models
am_query = syn.tableQuery("SELECT * FROM syn26486808")
am_df = am_query.asDataFrame()
print(f"   Animal Models (syn26486808): {len(am_df)} records")

# Antibodies
ab_query = syn.tableQuery("SELECT * FROM syn26486811")
ab_df = ab_query.asDataFrame()
print(f"   Antibodies (syn26486811): {len(ab_df)} records")

# Biobanks
bb_query = syn.tableQuery("SELECT * FROM syn26486821")
bb_df = bb_query.asDataFrame()
print(f"   Biobanks (syn26486821): {len(bb_df)} records")

# Cell lines
cl_query = syn.tableQuery("SELECT * FROM syn26486823")
cl_df = cl_query.asDataFrame()
print(f"   Cell Lines (syn26486823): {len(cl_df)} records")

# Genetic reagents
gr_query = syn.tableQuery("SELECT * FROM syn26486832")
gr_df = gr_query.asDataFrame()
print(f"   Genetic Reagents (syn26486832): {len(gr_df)} records")

print("\n5. Analyzing GFF publications against linked tools...")

# Merge publications with linking table to see which are already represented
# The linking table might use pmid or doi to link rather than publicationId
link_key = None
if 'publicationId' in link_df.columns and 'publicationId' in pub_df.columns:
    link_key = 'publicationId'
elif 'pmid' in link_df.columns and 'pmid' in pub_df.columns:
    link_key = 'pmid'
elif 'doi' in link_df.columns and 'doi' in pub_df.columns:
    link_key = 'doi'

if link_key:
    print(f"   Using '{link_key}' to link publications with tools")

    # Get publications that have tools linked
    linked_pub_ids = link_df[link_key].dropna().unique()
    gff_pub_ids = pub_df[link_key].dropna().unique()

    represented_pubs = set(gff_pub_ids) & set(linked_pub_ids)
    missing_pubs = set(gff_pub_ids) - set(linked_pub_ids)

    print(f"   Total GFF publications: {len(gff_pub_ids)}")
    print(f"   GFF publications with linked tools: {len(represented_pubs)} ({len(represented_pubs)/len(gff_pub_ids)*100:.1f}%)")
    print(f"   GFF publications WITHOUT linked tools: {len(missing_pubs)} ({len(missing_pubs)/len(gff_pub_ids)*100:.1f}%)")

    # Get details of linked tools for GFF publications
    gff_links = link_df[link_df[link_key].isin(gff_pub_ids)]
    print(f"   Total tool-publication links for GFF pubs: {len(gff_links)}")

    # Merge with tools to see what types
    if len(gff_links) > 0 and 'resourceId' in gff_links.columns:
        gff_tools = tools_df[tools_df['resourceId'].isin(gff_links['resourceId'])]
        print(f"\n   GFF-linked tools by type:")
        for resource_type, count in gff_tools['resourceType'].value_counts().items():
            print(f"   - {resource_type}: {count}")

    # Mark publications as represented or not
    pub_df['has_linked_tools'] = pub_df[link_key].isin(represented_pubs)
    pub_df['is_missing'] = ~pub_df['has_linked_tools']

    # Get missing publications details
    missing_pubs_df = pub_df[pub_df['is_missing']]
    print(f"\n   Missing publications that need tools added: {len(missing_pubs_df)}")

else:
    print("   WARNING: Could not find publicationId column to link publications")
    missing_pubs_df = pub_df
    pub_df['has_linked_tools'] = False
    pub_df['is_missing'] = True

print("\n6. Analyzing publication content for tool mentions...")

# Look for tool-related keywords in publication titles and abstracts
tool_keywords = {
    'animal_model': [
        r'\bmouse\b', r'\bmice\b', r'\brat\b', r'\brats\b', r'\bmodel\b',
        r'\bzebrafish\b', r'\banimal model\b', r'\bin vivo\b'
    ],
    'antibody': [
        r'\bantibod(y|ies)\b', r'\bimmuno\b', r'\bwestern blot\b',
        r'\bIHC\b', r'\bIF\b', r'\bflow cytometry\b'
    ],
    'cell_line': [
        r'\bcell line\b', r'\bcell culture\b', r'\bin vitro\b',
        r'\bHEK\b', r'\bHeLa\b', r'\bST88\b', r'\bSNF\b'
    ],
    'genetic_reagent': [
        r'\bplasmid\b', r'\bvector\b', r'\bCRISPR\b', r'\bshRNA\b',
        r'\bsiRNA\b', r'\bconstruct\b', r'\btransfection\b'
    ],
    'biobank': [
        r'\bbiobank\b', r'\btissue bank\b', r'\bspecimen\b', r'\btissue collection\b'
    ]
}

def detect_tool_types(text):
    """Detect potential tool types mentioned in text"""
    if pd.isna(text):
        return []

    text_lower = str(text).lower()
    mentioned_types = []

    for tool_type, patterns in tool_keywords.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                mentioned_types.append(tool_type)
                break

    return list(set(mentioned_types))

# Analyze each publication
pub_df['tool_types_mentioned'] = pub_df.apply(
    lambda row: detect_tool_types(str(row.get('title', '')) + ' ' + str(row.get('abstract', ''))),
    axis=1
)

# Count publications mentioning each tool type
tool_type_counts = defaultdict(int)
for tool_types in pub_df['tool_types_mentioned']:
    for tool_type in tool_types:
        tool_type_counts[tool_type] += 1

print(f"\n   Tool types mentioned in GFF publications:")
for tool_type, count in sorted(tool_type_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"   - {tool_type}: {count} publications")

print("\n5. Identifying specific tools mentioned...")

# Check if publications have resourceId or tool name columns
print(f"\n   Publication columns that might reference tools:")
possible_tool_cols = [col for col in pub_df.columns if any(
    keyword in col.lower() for keyword in ['resource', 'tool', 'model', 'reagent', 'antibody', 'cell']
)]
print(f"   {possible_tool_cols}")

# Display sample of publications
print(f"\n7. Sample GFF-funded publications (focusing on those without linked tools):")
sample_cols = ['title', 'journal', 'year', 'tool_types_mentioned']
available_cols = [col for col in sample_cols if col in pub_df.columns]

# Prioritize showing missing publications
if 'is_missing' in pub_df.columns and len(missing_pubs_df) > 0:
    # Ensure columns exist in missing dataframe
    available_missing_cols = [col for col in available_cols if col in missing_pubs_df.columns]
    display_df = missing_pubs_df[available_missing_cols].head(10)
    print("   (Showing publications WITHOUT linked tools - these need review)")
else:
    display_df = pub_df[available_cols].head(10)

if len(display_df) > 0:
    print(display_df.to_string(index=False))
else:
    print("   (No publications to display)")

print("\n" + "=" * 80)
print("COVERAGE ANALYSIS")
print("=" * 80)

# Calculate actual coverage
total_gff_pubs = len(pub_df)
if 'has_linked_tools' in pub_df.columns:
    pubs_with_linked_tools = len(pub_df[pub_df['has_linked_tools']])
    current_coverage = (pubs_with_linked_tools / total_gff_pubs * 100) if total_gff_pubs > 0 else 0

    print(f"\n📊 CURRENT COVERAGE:")
    print(f"   Total GFF-funded publications: {total_gff_pubs}")
    print(f"   Publications with linked tools: {pubs_with_linked_tools} ({current_coverage:.1f}%)")
    print(f"   Publications WITHOUT linked tools: {total_gff_pubs - pubs_with_linked_tools} ({100-current_coverage:.1f}%)")

    # Calculate what's needed for 80% coverage
    target_coverage = 80
    target_pubs = int(total_gff_pubs * target_coverage / 100)
    pubs_needed = target_pubs - pubs_with_linked_tools

    print(f"\n🎯 TARGET: 80% COVERAGE")
    print(f"   Need tools from: {target_pubs} publications")
    print(f"   Currently have: {pubs_with_linked_tools} publications")
    if pubs_needed > 0:
        print(f"   STILL NEED: {pubs_needed} more publications with tools ({pubs_needed/total_gff_pubs*100:.1f}% of total)")
        print(f"   ✅ STATUS: {'ABOVE TARGET' if current_coverage >= target_coverage else 'BELOW TARGET'}")
    else:
        print(f"   ✅ STATUS: ABOVE TARGET! Currently at {current_coverage:.1f}%")
else:
    pubs_with_tools = len(pub_df[pub_df['tool_types_mentioned'].apply(len) > 0])
    print(f"\nTotal GFF-funded publications: {total_gff_pubs}")
    print(f"Publications mentioning tools (estimated): {pubs_with_tools} ({pubs_with_tools/total_gff_pubs*100:.1f}%)")

print(f"\nTools in database by type:")
for resource_type in tools_df['resourceType'].unique():
    count = len(tools_df[tools_df['resourceType'] == resource_type])
    print(f"  - {resource_type}: {count}")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

if 'has_linked_tools' in pub_df.columns:
    if current_coverage >= 80:
        print(f"""
✅ EXCELLENT! Current coverage of {current_coverage:.1f}% exceeds the 80% target.

Recommendations for maintenance:
1. Review the {total_gff_pubs - pubs_with_linked_tools} remaining publications without tools
2. Verify that existing tool-publication links are accurate
3. Continue adding tools from new GFF publications as they are published
""")
    else:
        pubs_to_review = missing_pubs_df if len(missing_pubs_df) > 0 else pub_df
        print(f"""
⚠️  Current coverage of {current_coverage:.1f}% is BELOW the 80% target.

ACTION REQUIRED: Add tools from {pubs_needed} more publications to reach 80% coverage.

Priority actions:
1. Review the {len(missing_pubs_df)} publications WITHOUT linked tools
2. Focus on publications mentioning these tool types:
""")
        for tool_type, count in sorted(tool_type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {tool_type}: {count} publications")

        print(f"""
3. For each publication:
   - Check if tools are mentioned in abstract/methods
   - Search for tool names, model names, cell line names, etc.
   - Add missing tools to appropriate tables:
     * Animal models: syn26486808
     * Antibodies: syn26486811
     * Biobanks: syn26486821
     * Cell lines: syn26486823
     * Genetic reagents: syn26486832
   - Link tools to publications in syn51735450

4. Contact publication authors if tool details are unclear
""")
else:
    print(f"""
To achieve 80% coverage of GFF-funded tools:
1. Review publications that mention tools
2. Identify specific tools mentioned in abstracts/methods
3. Cross-reference with existing tools in syn51730943
4. Add missing tools to appropriate tool type tables
""")

# Save detailed analysis
output_file = 'gff_publications_tool_analysis.csv'
pub_df.to_csv(output_file, index=False)
print(f"\n📄 Detailed analysis saved to: {output_file}")

if 'is_missing' in pub_df.columns and len(missing_pubs_df) > 0:
    missing_file = 'gff_publications_MISSING_tools.csv'
    missing_pubs_df.to_csv(missing_file, index=False)
    print(f"📄 Publications needing tools saved to: {missing_file}")

# Generate PDF report
print("\n" + "=" * 80)
print("GENERATING PDF REPORT")
print("=" * 80)

pdf_file = 'GFF_Tool_Coverage_Report.pdf'
with PdfPages(pdf_file) as pdf:
    # Page 1: Coverage Summary
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    fig.suptitle(f'GFF Tool Coverage Analysis\n{datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 fontsize=16, fontweight='bold')

    # Coverage pie chart
    if 'has_linked_tools' in pub_df.columns:
        coverage_data = [pubs_with_linked_tools, total_gff_pubs - pubs_with_linked_tools]
        colors = ['#2ecc71', '#e74c3c']
        labels = [f'With Tools\n({pubs_with_linked_tools})',
                 f'Without Tools\n({total_gff_pubs - pubs_with_linked_tools})']

        axes[0, 0].pie(coverage_data, labels=labels, colors=colors, autopct='%1.1f%%',
                      startangle=90)
        axes[0, 0].set_title(f'GFF Publication Coverage\n({current_coverage:.1f}% have tools)',
                            fontweight='bold')

    # Resource type distribution for GFF tools
    if len(gff_links) > 0 and 'resourceId' in gff_links.columns:
        gff_tools = tools_df[tools_df['resourceId'].isin(gff_links['resourceId'])]
        resource_counts = gff_tools['resourceType'].value_counts()

        axes[0, 1].barh(resource_counts.index, resource_counts.values, color='#3498db')
        axes[0, 1].set_xlabel('Number of Tools')
        axes[0, 1].set_title('GFF-Linked Tools by Type', fontweight='bold')
        axes[0, 1].grid(axis='x', alpha=0.3)

        # Add counts at the end of bars
        for i, v in enumerate(resource_counts.values):
            axes[0, 1].text(v + 0.1, i, str(v), va='center')

    # All tools distribution
    all_resource_counts = tools_df['resourceType'].value_counts()
    axes[1, 0].barh(all_resource_counts.index, all_resource_counts.values, color='#95a5a6')
    axes[1, 0].set_xlabel('Number of Tools')
    axes[1, 0].set_title('All Tools in Database by Type', fontweight='bold')
    axes[1, 0].grid(axis='x', alpha=0.3)

    for i, v in enumerate(all_resource_counts.values):
        axes[1, 0].text(v + 5, i, str(v), va='center')

    # Summary statistics text
    coverage_pct = f"{current_coverage:.1f}%" if 'has_linked_tools' in pub_df.columns else 'N/A'
    coverage_status = '✅ ABOVE TARGET' if (current_coverage >= 80 if 'has_linked_tools' in pub_df.columns else False) else '⚠️ BELOW TARGET'
    gff_tool_count = len(gff_tools) if (len(gff_links) > 0 and 'resourceId' in gff_links.columns) else 0

    summary_text = f"""
📊 SUMMARY STATISTICS

Total GFF Publications: {total_gff_pubs}
Publications with Tools: {pubs_with_linked_tools if 'has_linked_tools' in pub_df.columns else 'N/A'}
Current Coverage: {coverage_pct}

TARGET: 80% coverage
Status: {coverage_status}

Tools in Database: {len(tools_df)}
- Animal Models: {len(tools_df[tools_df['resourceType']=='Animal Model'])}
- Antibodies: {len(tools_df[tools_df['resourceType']=='Antibody'])}
- Cell Lines: {len(tools_df[tools_df['resourceType']=='Cell Line'])}
- Genetic Reagents: {len(tools_df[tools_df['resourceType']=='Genetic Reagent'])}
- Biobanks: {len(tools_df[tools_df['resourceType']=='Biobank'])}

GFF-Linked Tools: {gff_tool_count}
    """

    axes[1, 1].text(0.1, 0.5, summary_text, transform=axes[1, 1].transAxes,
                   fontsize=10, verticalalignment='center', fontfamily='monospace',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    axes[1, 1].axis('off')

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()

    # Page 2: Missing publications table
    if len(missing_pubs_df) > 0:
        fig, ax = plt.subplots(figsize=(11, 8.5))
        fig.suptitle('GFF Publications WITHOUT Linked Tools (Need Review)',
                    fontsize=14, fontweight='bold')

        # Prepare data for table
        table_cols = ['title', 'journal', 'year', 'pmid']
        table_data_cols = [col for col in table_cols if col in missing_pubs_df.columns]
        table_data = missing_pubs_df[table_data_cols].head(20)

        # Truncate long titles
        if 'title' in table_data.columns:
            table_data['title'] = table_data['title'].str[:60] + '...'

        ax.axis('tight')
        ax.axis('off')

        table = ax.table(cellText=table_data.values,
                        colLabels=table_data.columns,
                        cellLoc='left',
                        loc='center')

        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 2)

        # Style header
        for i in range(len(table_data.columns)):
            table[(0, i)].set_facecolor('#3498db')
            table[(0, i)].set_text_props(weight='bold', color='white')

        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

print(f"\n📊 PDF report generated: {pdf_file}")

print("\n" + "=" * 80)
