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

# Parse funding agencies from all publications
print(f"   Found {len(pub_df)} total publications")
print(f"   Columns: {', '.join(pub_df.columns.tolist())}")

# Extract individual funding agencies
if 'fundingAgency' in pub_df.columns:
    import ast

    def parse_funding_agencies(funding_str):
        """Parse funding agency string into list"""
        # Handle scalar NaN values
        if isinstance(funding_str, (float, int)) and pd.isna(funding_str):
            return []
        # Handle None
        if funding_str is None:
            return []
        # Handle empty string
        if not funding_str or (isinstance(funding_str, str) and not funding_str.strip()):
            return []
        try:
            # Try to parse as Python list string
            agencies = ast.literal_eval(str(funding_str))
            if isinstance(agencies, list):
                return [str(a).strip() for a in agencies if a]
            return [str(agencies).strip()]
        except:
            # If parsing fails, treat as single string
            return [str(funding_str).strip()]

    pub_df['funding_agencies'] = pub_df['fundingAgency'].apply(parse_funding_agencies)

    # Get all unique agencies
    all_agencies = set()
    for agencies in pub_df['funding_agencies']:
        all_agencies.update(agencies)

    print(f"   Funding agencies found: {sorted(all_agencies)}")

    # Create indicator columns for each agency
    for agency in all_agencies:
        pub_df[f'is_{agency}'] = pub_df['funding_agencies'].apply(lambda x: agency in x)
else:
    print("   WARNING: No fundingAgency column found")
    all_agencies = set()

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

print("\n5. Analyzing publications against linked tools by funding agency...")

# Merge publications with linking table to see which are already represented
# The linking table might use pmid or doi to link rather than publicationId
link_key = None
if 'publicationId' in link_df.columns and 'publicationId' in pub_df.columns:
    link_key = 'publicationId'
elif 'pmid' in link_df.columns and 'pmid' in pub_df.columns:
    link_key = 'pmid'
elif 'doi' in link_df.columns and 'doi' in pub_df.columns:
    link_key = 'doi'

# Store coverage data for all agencies
agency_coverage = {}

if link_key:
    print(f"   Using '{link_key}' to link publications with tools")

    # Get publications that have tools linked
    linked_pub_ids = set(link_df[link_key].dropna().unique())

    # Mark publications as having linked tools
    pub_df['has_linked_tools'] = pub_df[link_key].isin(linked_pub_ids)
    pub_df['is_missing'] = ~pub_df['has_linked_tools']

    # Calculate coverage for each funding agency
    for agency in sorted(all_agencies):
        agency_pubs = pub_df[pub_df[f'is_{agency}']]
        if len(agency_pubs) > 0:
            agency_pub_ids = set(agency_pubs[link_key].dropna().unique())
            represented_pubs = agency_pub_ids & linked_pub_ids
            missing_pubs = agency_pub_ids - linked_pub_ids

            coverage_pct = (len(represented_pubs) / len(agency_pub_ids) * 100) if len(agency_pub_ids) > 0 else 0

            agency_coverage[agency] = {
                'total': len(agency_pub_ids),
                'with_tools': len(represented_pubs),
                'without_tools': len(missing_pubs),
                'coverage_pct': coverage_pct
            }

            print(f"\n   {agency}:")
            print(f"      Total publications: {len(agency_pub_ids)}")
            print(f"      With linked tools: {len(represented_pubs)} ({coverage_pct:.1f}%)")
            print(f"      Without linked tools: {len(missing_pubs)} ({100-coverage_pct:.1f}%)")

            # Get tools linked to this agency's publications
            agency_links = link_df[link_df[link_key].isin(agency_pub_ids)]
            if len(agency_links) > 0 and 'resourceId' in agency_links.columns:
                agency_tools = tools_df[tools_df['resourceId'].isin(agency_links['resourceId'])]
                print(f"      Linked tools by type:")
                for resource_type, count in agency_tools['resourceType'].value_counts().items():
                    print(f"         - {resource_type}: {count}")

    # Get missing publications details (for primary focus agency, e.g., GFF)
    missing_pubs_df = pub_df[pub_df['is_missing']]
    print(f"\n   Total publications WITHOUT linked tools: {len(missing_pubs_df)}")

else:
    print("   WARNING: Could not find publication ID column to link publications")
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

print(f"\n   Tool types mentioned in all publications:")
for tool_type, count in sorted(tool_type_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"   - {tool_type}: {count} publications")

print("\n7. Sample publications (focusing on those without linked tools):")
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
print("COVERAGE ANALYSIS BY FUNDING AGENCY")
print("=" * 80)

# Display coverage for all agencies
if agency_coverage:
    print(f"\n📊 CURRENT COVERAGE BY FUNDING AGENCY:")
    print(f"\n{'Agency':<15} {'Total':<8} {'With Tools':<12} {'Coverage':<10} {'80% Target':<12}")
    print("-" * 65)

    for agency in sorted(agency_coverage.keys()):
        data = agency_coverage[agency]
        target_pubs = int(data['total'] * 0.8)
        status = '✅' if data['coverage_pct'] >= 80 else '⚠️'

        print(f"{agency:<15} {data['total']:<8} {data['with_tools']:<12} "
              f"{data['coverage_pct']:>6.1f}%    {status} {target_pubs} needed")

    # Focus on GFF for detailed analysis (primary funding agency)
    if 'GFF' in agency_coverage:
        gff_data = agency_coverage['GFF']
        print(f"\n🎯 GFF TARGET: 80% COVERAGE")
        print(f"   Total GFF publications: {gff_data['total']}")
        print(f"   Publications with tools: {gff_data['with_tools']} ({gff_data['coverage_pct']:.1f}%)")
        print(f"   Publications without tools: {gff_data['without_tools']}")

        target_pubs = int(gff_data['total'] * 0.8)
        pubs_needed = target_pubs - gff_data['with_tools']

        if pubs_needed > 0:
            print(f"   STILL NEED: {pubs_needed} more publications with tools")
            print(f"   STATUS: ⚠️ BELOW TARGET")
        else:
            print(f"   STATUS: ✅ ABOVE TARGET!")
else:
    print(f"\n⚠️ No coverage data available (could not link publications to tools)")

print(f"\nTools in database by type:")
for resource_type in tools_df['resourceType'].unique():
    count = len(tools_df[tools_df['resourceType'] == resource_type])
    print(f"  - {resource_type}: {count}")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

if agency_coverage and 'GFF' in agency_coverage:
    gff_data = agency_coverage['GFF']
    target_pubs = int(gff_data['total'] * 0.8)
    pubs_needed = target_pubs - gff_data['with_tools']

    if gff_data['coverage_pct'] >= 80:
        print(f"""
✅ EXCELLENT! GFF coverage of {gff_data['coverage_pct']:.1f}% exceeds the 80% target.

Recommendations for maintenance:
1. Review the {gff_data['without_tools']} remaining publications without tools
2. Verify that existing tool-publication links are accurate
3. Continue adding tools from new publications as they are published
""")
    else:
        print(f"""
⚠️  GFF coverage of {gff_data['coverage_pct']:.1f}% is BELOW the 80% target.

ACTION REQUIRED: Add tools from {pubs_needed} more publications to reach 80% coverage.

Priority actions:
1. Review the {len(missing_pubs_df)} publications WITHOUT linked tools
2. Focus on publications mentioning tool types
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
To achieve 80% coverage:
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
    # Page 1: Coverage Comparison Across Funding Agencies
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    fig.suptitle(f'Tool Coverage Analysis by Funding Agency\n{datetime.now().strftime("%Y-%m-%d %H:%M")}',
                 fontsize=16, fontweight='bold')

    # Plot 1: Coverage percentage comparison across agencies
    if agency_coverage:
        agencies = sorted(agency_coverage.keys())
        coverage_pcts = [agency_coverage[a]['coverage_pct'] for a in agencies]
        colors = ['#2ecc71' if pct >= 80 else '#e74c3c' for pct in coverage_pcts]

        bars = axes[0, 0].barh(agencies, coverage_pcts, color=colors)
        axes[0, 0].set_xlabel('Coverage (%)')
        axes[0, 0].set_title('Publication Coverage by Funding Agency', fontweight='bold')
        axes[0, 0].axvline(x=80, color='orange', linestyle='--', linewidth=2, label='80% Target')
        axes[0, 0].legend()
        axes[0, 0].grid(axis='x', alpha=0.3)

        # Add percentage labels
        for i, (bar, pct) in enumerate(zip(bars, coverage_pcts)):
            axes[0, 0].text(pct + 1, i, f'{pct:.1f}%', va='center')

    # Plot 2: Resource type distribution across agencies
    if agency_coverage and link_key:
        # Get resource types for each agency
        resource_types = sorted(tools_df['resourceType'].unique())
        agency_tool_counts = {}

        for agency in sorted(agency_coverage.keys()):
            agency_pubs = pub_df[pub_df[f'is_{agency}']]
            agency_pub_ids = set(agency_pubs[link_key].dropna().unique())
            agency_links = link_df[link_df[link_key].isin(agency_pub_ids)]

            if len(agency_links) > 0 and 'resourceId' in agency_links.columns:
                agency_tools = tools_df[tools_df['resourceId'].isin(agency_links['resourceId'])]
                agency_tool_counts[agency] = {
                    rt: len(agency_tools[agency_tools['resourceType'] == rt])
                    for rt in resource_types
                }
            else:
                agency_tool_counts[agency] = {rt: 0 for rt in resource_types}

        # Create grouped bar chart
        x = range(len(resource_types))
        width = 0.8 / len(agency_tool_counts)
        colors_palette = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c']

        for i, (agency, counts) in enumerate(sorted(agency_tool_counts.items())):
            values = [counts[rt] for rt in resource_types]
            offset = (i - len(agency_tool_counts)/2 + 0.5) * width
            axes[0, 1].bar([p + offset for p in x], values,
                          width=width, label=agency,
                          color=colors_palette[i % len(colors_palette)])

        axes[0, 1].set_xlabel('Resource Type')
        axes[0, 1].set_ylabel('Number of Tools')
        axes[0, 1].set_title('Linked Tools by Type and Agency', fontweight='bold')
        axes[0, 1].set_xticks(x)
        axes[0, 1].set_xticklabels(resource_types, rotation=45, ha='right')
        axes[0, 1].legend(loc='upper right', fontsize=8)
        axes[0, 1].grid(axis='y', alpha=0.3)

    # Plot 3: All tools distribution
    all_resource_counts = tools_df['resourceType'].value_counts()
    axes[1, 0].barh(all_resource_counts.index, all_resource_counts.values, color='#95a5a6')
    axes[1, 0].set_xlabel('Number of Tools')
    axes[1, 0].set_title('All Tools in Database by Type', fontweight='bold')
    axes[1, 0].grid(axis='x', alpha=0.3)

    for i, v in enumerate(all_resource_counts.values):
        axes[1, 0].text(v + 5, i, str(v), va='center')

    # Plot 4: Summary statistics text
    summary_lines = ["\n📊 SUMMARY STATISTICS\n"]

    if agency_coverage:
        summary_lines.append("Coverage by Agency:")
        for agency in sorted(agency_coverage.keys()):
            data = agency_coverage[agency]
            status = '✅' if data['coverage_pct'] >= 80 else '⚠️'
            summary_lines.append(f"{agency}: {data['with_tools']}/{data['total']} "
                               f"({data['coverage_pct']:.1f}%) {status}")

    summary_lines.append(f"\nTotal Tools: {len(tools_df)}")
    for rt in sorted(tools_df['resourceType'].unique()):
        count = len(tools_df[tools_df['resourceType']==rt])
        summary_lines.append(f"  {rt}: {count}")

    summary_text = '\n'.join(summary_lines)

    axes[1, 1].text(0.1, 0.5, summary_text, transform=axes[1, 1].transAxes,
                   fontsize=9, verticalalignment='center', fontfamily='monospace',
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
