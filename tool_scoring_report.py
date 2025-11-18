#!/usr/bin/env python3
"""
Research Tools Completeness Score Report Generator

This script generates a comprehensive PDF report analyzing the completeness scores
for research tools and biobanks in the NF-OSI database.
"""

import synapseclient
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime
import os
import warnings
warnings.filterwarnings('ignore')

# Set style for better-looking plots
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 10


def load_data_from_synapse(syn):
    """Load scores and summary data from Synapse tables"""
    print("Loading data from Synapse...")
    all_scores = syn.tableQuery("SELECT * FROM syn71218777").asDataFrame()
    summary_by_type = syn.tableQuery("SELECT * FROM syn71219401").asDataFrame()
    print(f"\nAnalyzed {len(all_scores)} resources across {all_scores['resourceType'].nunique()} resource types\n")
    return all_scores, summary_by_type


def create_title_page(pdf, all_scores):
    """Create title page for the report"""
    fig = plt.figure(figsize=(8.5, 11))
    fig.text(0.5, 0.7, 'Research Tools\nCompleteness Score Report',
             ha='center', va='center', fontsize=28, fontweight='bold')
    fig.text(0.5, 0.55, 'NF-OSI',
             ha='center', va='center', fontsize=18)
    fig.text(0.5, 0.45, f'Date: {datetime.now().strftime("%Y-%m-%d")}',
             ha='center', va='center', fontsize=14)

    # Add executive summary text
    summary_text = f"""
    This report provides a comprehensive analysis of the completeness scores
    for research tools and biobanks in the NF-OSI database.

    Total Resources Analyzed: {len(all_scores)}
    Resource Types: {all_scores['resourceType'].nunique()}

    Scoring System (Total: 100 points):
    • Availability (30 points): Biobank URL, vendor/developer info, RRID, and DOI
    • Critical Info (30 points): Type-specific essential fields
    • Other Info (15 points): Type-specific additional fields
    • Observations (25 points): Scientific characterizations with DOI weighting

    Completeness Categories:
    • Excellent: 80+ points
    • Good: 60-80 points
    • Fair: 40-60 points
    • Poor: 20-40 points
    • Minimal: <20 points
    """
    fig.text(0.1, 0.35, summary_text, ha='left', va='top', fontsize=10,
             family='monospace', wrap=True)

    plt.axis('off')
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def plot_category_distribution(pdf, all_scores):
    """Plot overall completeness category distribution"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Pie chart
    category_counts = all_scores['completeness_category'].value_counts()
    category_order = ['Excellent', 'Good', 'Fair', 'Poor', 'Minimal']
    category_counts = category_counts.reindex(category_order, fill_value=0)

    colors = {'Excellent': '#27ae60', 'Good': '#2ecc71', 'Fair': '#f39c12',
              'Poor': '#e67e22', 'Minimal': '#e74c3c'}
    color_list = [colors.get(cat, '#95a5a6') for cat in category_counts.index]

    wedges, texts, autotexts = ax1.pie(category_counts, labels=category_counts.index,
                                        autopct=lambda pct: f'{int(pct/100*category_counts.sum())}\n({pct:.1f}%)',
                                        colors=color_list, startangle=90)
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(10)

    ax1.set_title('Overall Distribution of Completeness Categories\n'
                  f'Total: {len(all_scores)} resources', fontsize=14, fontweight='bold')

    # Bar chart
    category_counts.plot(kind='bar', ax=ax2, color=color_list)
    ax2.set_xlabel('Completeness Category', fontweight='bold')
    ax2.set_ylabel('Number of Resources', fontweight='bold')
    ax2.set_title('Completeness Category Counts', fontsize=14, fontweight='bold')
    ax2.tick_params(axis='x', rotation=45)

    for i, v in enumerate(category_counts):
        ax2.text(i, v + 0.5, str(v), ha='center', va='bottom', fontweight='bold')

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def plot_category_by_type(pdf, all_scores):
    """Plot completeness category distribution by resource type"""
    category_by_type = pd.crosstab(all_scores['resourceType'],
                                    all_scores['completeness_category'],
                                    normalize='index') * 100

    category_order = ['Excellent', 'Good', 'Fair', 'Poor', 'Minimal']
    category_by_type = category_by_type.reindex(columns=category_order, fill_value=0)

    colors = ['#27ae60', '#2ecc71', '#f39c12', '#e67e22', '#e74c3c']

    fig, ax = plt.subplots(figsize=(12, 6))
    category_by_type.plot(kind='bar', stacked=True, ax=ax, color=colors)

    ax.set_xlabel('Resource Type', fontweight='bold', fontsize=12)
    ax.set_ylabel('Percentage (%)', fontweight='bold', fontsize=12)
    ax.set_title('Completeness Category Distribution by Resource Type',
                 fontsize=14, fontweight='bold')
    ax.legend(title='Category', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.tick_params(axis='x', rotation=45)

    # Add resource counts to x-axis labels
    type_counts = all_scores['resourceType'].value_counts()
    labels = [f"{label.get_text()}\n(n={type_counts.get(label.get_text(), 0)})"
              for label in ax.get_xticklabels()]
    ax.set_xticklabels(labels)

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def plot_score_distribution(pdf, all_scores):
    """Plot score distribution histogram and by type"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    # Overall histogram
    ax1.hist(all_scores['total_score'], bins=20, color='#3498db', alpha=0.8, edgecolor='white')
    ax1.axvline(all_scores['total_score'].mean(), color='red', linestyle='--',
                linewidth=2, label=f"Mean: {all_scores['total_score'].mean():.1f}")
    ax1.axvline(all_scores['total_score'].median(), color='green', linestyle='--',
                linewidth=2, label=f"Median: {all_scores['total_score'].median():.1f}")

    ax1.set_xlabel('Total Score (out of 100)', fontweight='bold')
    ax1.set_ylabel('Number of Resources', fontweight='bold')
    ax1.set_title(f'Overall Completeness Score Distribution (N = {len(all_scores)})',
                  fontsize=14, fontweight='bold')
    ax1.legend()

    # Boxplot by resource type
    type_order = all_scores.groupby('resourceType')['total_score'].median().sort_values(ascending=False).index
    all_scores_sorted = all_scores.copy()
    all_scores_sorted['resourceType'] = pd.Categorical(all_scores_sorted['resourceType'],
                                                       categories=type_order, ordered=True)

    sns.boxplot(data=all_scores_sorted, x='resourceType', y='total_score',
                palette='Set3', ax=ax2)
    sns.stripplot(data=all_scores_sorted, x='resourceType', y='total_score',
                  color='black', alpha=0.3, size=3, ax=ax2)

    ax2.set_xlabel('Resource Type', fontweight='bold')
    ax2.set_ylabel('Total Score (out of 100)', fontweight='bold')
    ax2.set_title('Completeness Score Distribution by Resource Type\n'
                  '(Ordered by median score, highest to lowest)',
                  fontsize=14, fontweight='bold')
    ax2.tick_params(axis='x', rotation=45)

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def plot_component_heatmap(pdf, all_scores):
    """Plot heatmap of component scores by resource type"""
    component_cols = ['biobank_url_score', 'vendor_developer_score', 'rrid_score', 'doi_score',
                     'critical_info_score', 'other_info_score', 'observation_score']

    # Calculate mean scores by component and resource type
    component_data = []
    for col in component_cols:
        if col in all_scores.columns:
            means = all_scores.groupby('resourceType')[col].mean()
            component_name = col.replace('_score', '').replace('_', ' ').title()
            for resource_type, mean_val in means.items():
                component_data.append({
                    'Component': component_name,
                    'Resource Type': resource_type,
                    'Mean Score': mean_val
                })

    component_df = pd.DataFrame(component_data)
    pivot_df = component_df.pivot(index='Resource Type', columns='Component', values='Mean Score')

    fig, ax = plt.subplots(figsize=(12, 8))
    sns.heatmap(pivot_df, annot=True, fmt='.1f', cmap='RdYlGn', center=15,
                cbar_kws={'label': 'Mean Score'}, ax=ax)

    ax.set_title('Mean Score by Component and Resource Type\n'
                 '(Higher values indicate better completeness)',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Score Component', fontweight='bold')
    ax.set_ylabel('Resource Type', fontweight='bold')

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def plot_missing_fields(pdf, all_scores):
    """Plot analysis of missing fields"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    # Calculate missing field counts
    missing_data = all_scores.copy()
    missing_data['n_missing_availability'] = missing_data['missing_availability'].apply(
        lambda x: 0 if pd.isna(x) or x == '' else x.count(';') + 1
    )
    missing_data['n_missing_critical'] = missing_data['missing_critical_info'].apply(
        lambda x: 0 if pd.isna(x) or x == '' else x.count(';') + 1
    )
    missing_data['n_missing_other'] = missing_data['missing_other_info'].apply(
        lambda x: 0 if pd.isna(x) or x == '' else x.count(';') + 1
    )

    # Average missing fields by type
    missing_summary = missing_data.groupby('resourceType')[
        ['n_missing_availability', 'n_missing_critical', 'n_missing_other']
    ].mean()

    missing_summary.columns = ['Availability', 'Critical Info', 'Other Info']
    missing_summary.plot(kind='bar', ax=ax1, color=['#e74c3c', '#f39c12', '#3498db'])

    ax1.set_xlabel('Resource Type', fontweight='bold')
    ax1.set_ylabel('Average Number of Missing Fields', fontweight='bold')
    ax1.set_title('Average Number of Missing Fields by Category',
                  fontsize=14, fontweight='bold')
    ax1.legend(title='Field Category')
    ax1.tick_params(axis='x', rotation=45)

    # Observation status
    missing_data['has_observations'] = ~missing_data['observation_status'].str.contains('No observations',
                                                                                        na=False)
    obs_status = pd.crosstab(missing_data['resourceType'], missing_data['has_observations'])
    obs_status.columns = ['No Observations', 'Has Observations']

    obs_status.plot(kind='bar', stacked=True, ax=ax2, color=['#e74c3c', '#27ae60'])

    ax2.set_xlabel('Resource Type', fontweight='bold')
    ax2.set_ylabel('Number of Resources', fontweight='bold')
    ax2.set_title('Observation Status by Resource Type',
                  fontsize=14, fontweight='bold')
    ax2.legend(title='Status')
    ax2.tick_params(axis='x', rotation=45)

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def create_summary_tables(pdf, all_scores, summary_by_type):
    """Create summary statistics tables"""
    fig, axes = plt.subplots(3, 1, figsize=(11, 14))

    # Overall statistics
    overall_stats = pd.DataFrame({
        'Metric': ['Total Resources', 'Mean Score', 'Median Score', 'Std Dev',
                   'Min Score', 'Max Score', 'Range'],
        'Value': [
            len(all_scores),
            round(all_scores['total_score'].mean(), 2),
            round(all_scores['total_score'].median(), 2),
            round(all_scores['total_score'].std(), 2),
            round(all_scores['total_score'].min(), 2),
            round(all_scores['total_score'].max(), 2),
            round(all_scores['total_score'].max() - all_scores['total_score'].min(), 2)
        ]
    })

    axes[0].axis('tight')
    axes[0].axis('off')
    table1 = axes[0].table(cellText=overall_stats.values, colLabels=overall_stats.columns,
                           cellLoc='left', loc='center')
    table1.auto_set_font_size(False)
    table1.set_fontsize(10)
    table1.scale(1, 2)
    axes[0].set_title('Overall Summary Statistics', fontsize=14, fontweight='bold', pad=20)

    # Summary by type
    type_stats = summary_by_type[['resourceType', 'count', 'mean_score', 'median_score',
                                  'sd_score', 'min_score', 'max_score']].round(2)
    type_stats.columns = ['Resource Type', 'Count', 'Mean', 'Median', 'Std Dev', 'Min', 'Max']

    axes[1].axis('tight')
    axes[1].axis('off')
    table2 = axes[1].table(cellText=type_stats.values, colLabels=type_stats.columns,
                           cellLoc='left', loc='center')
    table2.auto_set_font_size(False)
    table2.set_fontsize(9)
    table2.scale(1, 2)
    axes[1].set_title('Summary Statistics by Resource Type', fontsize=14, fontweight='bold', pad=20)

    # Top 10 improvable resources
    top_resources = all_scores.nsmallest(10, 'total_score')[
        ['resourceName', 'resourceType', 'rrid', 'total_score', 'completeness_category']
    ].round(1)
    top_resources.columns = ['Resource Name', 'Type', 'RRID', 'Score', 'Category']

    # Truncate long names
    top_resources['Resource Name'] = top_resources['Resource Name'].str[:40]
    top_resources['RRID'] = top_resources['RRID'].fillna('N/A').str[:20]

    axes[2].axis('tight')
    axes[2].axis('off')
    table3 = axes[2].table(cellText=top_resources.values, colLabels=top_resources.columns,
                           cellLoc='left', loc='center')
    table3.auto_set_font_size(False)
    table3.set_fontsize(8)
    table3.scale(1, 2)
    axes[2].set_title('Resources with 10 Lowest Scores', fontsize=14, fontweight='bold', pad=20)

    plt.tight_layout()
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def create_recommendations_page(pdf, all_scores):
    """Create recommendations page"""
    incomplete_count = len(all_scores[all_scores['total_score'] < 40])

    fig = plt.figure(figsize=(8.5, 11))
    fig.text(0.5, 0.9, 'Recommendations',
             ha='center', va='top', fontsize=24, fontweight='bold')

    recommendations_text = f"""
Based on the analysis, here are key recommendations for improving
resource completeness:

1. Focus on Low-Scoring Components
   Identify which score components (availability, critical info, other info,
   observations) have the lowest average scores across resource types and
   prioritize filling those fields.

2. Resource Type Priorities
   Target resource types with lower median scores for systematic improvement
   efforts. Review the boxplot and summary statistics to identify priorities.

3. Observation Documentation
   Encourage researchers to submit observations with publication DOIs, as
   these contribute more points (7.5 vs 2.5) to the completeness score.
   Currently, many resources lack observations entirely.

4. RRID Registration
   Ensure all resources have registered RRIDs (Research Resource Identifiers)
   to improve findability and citation. This is worth 7.5 points in the
   availability category.

5. Vendor/Developer Information
   Complete vendor or developer information for resources to improve
   availability scores. This accounts for 15 points in the scoring system.

6. Address Low-Scoring Resources
   There are {incomplete_count} resources with scores below 40 that need
   immediate attention. Prioritize improving these to reach at least
   "Fair" completeness status.

7. Type-Specific Fields
   Review the critical info and other info fields specific to each resource
   type. These account for 45 points total and are often incomplete.

8. Regular Monitoring
   Schedule regular reviews of completeness scores to track improvement over
   time and identify new resources that need attention.
    """

    fig.text(0.1, 0.85, recommendations_text, ha='left', va='top', fontsize=10,
             family='monospace', wrap=True)

    plt.axis('off')
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()


def generate_report(output_path='tool_scoring_report.pdf'):
    """Generate the complete PDF report"""
    print("Generating Tool Completeness Score Report...")

    # Login to Synapse
    print("Logging in to Synapse...")
    syn = synapseclient.Synapse()

    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token)
    else:
        syn.login()

    # Load data
    all_scores, summary_by_type = load_data_from_synapse(syn)

    # Create PDF
    print(f"Creating PDF report: {output_path}")
    with PdfPages(output_path) as pdf:
        print("  Creating title page...")
        create_title_page(pdf, all_scores)

        print("  Plotting category distributions...")
        plot_category_distribution(pdf, all_scores)
        plot_category_by_type(pdf, all_scores)

        print("  Plotting score distributions...")
        plot_score_distribution(pdf, all_scores)

        print("  Creating component heatmap...")
        plot_component_heatmap(pdf, all_scores)

        print("  Analyzing missing fields...")
        plot_missing_fields(pdf, all_scores)

        print("  Creating summary tables...")
        create_summary_tables(pdf, all_scores, summary_by_type)

        print("  Adding recommendations...")
        create_recommendations_page(pdf, all_scores)

        # Add metadata
        d = pdf.infodict()
        d['Title'] = 'Research Tools Completeness Score Report'
        d['Author'] = 'NF-OSI'
        d['Subject'] = 'Tool completeness analysis'
        d['Keywords'] = 'NF-OSI, research tools, completeness, scoring'
        d['CreationDate'] = datetime.now()

    print(f"\n✓ Report generated successfully: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_report()
