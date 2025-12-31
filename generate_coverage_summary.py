#!/usr/bin/env python3
"""
Generate a summary report for GitHub issue based on coverage analysis and mining results.
"""

import os
import pandas as pd
import synapseclient
from datetime import datetime

def main():
    """Generate markdown summary for GitHub issue."""

    # Login to Synapse
    syn = synapseclient.Synapse()
    auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
    if auth_token:
        syn.login(authToken=auth_token)
    else:
        syn.login()  # Interactive login if no token

    print(f"# 🔍 Tool Coverage Report")
    print(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"\n---")

    # ========================================================================
    # Section 1: Coverage Analysis
    # ========================================================================
    print(f"\n## 📊 Current Coverage Status")

    try:
        # Load publications
        pub_query = syn.tableQuery("SELECT * FROM syn16857542")
        pub_df = pub_query.asDataFrame()

        # Load links
        link_query = syn.tableQuery("SELECT * FROM syn51735450")
        link_df = link_query.asDataFrame()

        # Identify GFF publications
        pub_df['is_gff'] = pub_df['fundingAgency'].astype(str).str.contains('GFF', na=False)
        gff_pubs = pub_df[pub_df['is_gff']]

        # Count GFF publications with links
        if 'pmid' in link_df.columns and 'pmid' in pub_df.columns:
            linked_pmids = set(link_df['pmid'].dropna().unique())
            gff_linked = gff_pubs[gff_pubs['pmid'].isin(linked_pmids)]
        else:
            gff_linked = pd.DataFrame()

        total_gff = len(gff_pubs)
        gff_with_tools = len(gff_linked)
        coverage_pct = (gff_with_tools / total_gff * 100) if total_gff > 0 else 0
        target_count = int(total_gff * 0.8)
        needed = max(0, target_count - gff_with_tools)

        print(f"\n### GFF-Funded Publications")
        print(f"- **Total GFF Publications:** {total_gff}")
        print(f"- **With Linked Tools:** {gff_with_tools} ({coverage_pct:.1f}%)")
        print(f"- **Target (80%):** {target_count} publications")
        print(f"- **Still Needed:** {needed} publications")

        # Coverage status indicator
        if coverage_pct >= 80:
            print(f"\n✅ **Target achieved!** Coverage is at {coverage_pct:.1f}%")
        elif coverage_pct >= 60:
            print(f"\n⚠️ **Approaching target.** Need {needed} more publications with tools.")
        else:
            print(f"\n❌ **Below target.** Need {needed} more publications with tools.")

    except Exception as e:
        print(f"\n⚠️ Error loading coverage data: {e}")

    # ========================================================================
    # Section 2: Novel Tools Found
    # ========================================================================
    print(f"\n---")
    print(f"\n## 🎯 Novel Tools Discovery")

    # Check if full text mining results exist
    fulltext_file = 'priority_publications_FULLTEXT.csv'
    if os.path.exists(fulltext_file):
        try:
            fulltext_df = pd.read_csv(fulltext_file)

            print(f"\n### Full Text Mining Results")
            print(f"- **Publications Analyzed:** {len(fulltext_df)}")
            print(f"- **Publications with Novel Tools:** {len(fulltext_df)}")

            # Tool type breakdown
            cell_lines_count = fulltext_df['cell_lines'].str.len().gt(0).sum()
            antibodies_count = fulltext_df['antibodies'].str.len().gt(0).sum()
            animal_models_count = fulltext_df['animal_models'].str.len().gt(0).sum()
            genetic_reagents_count = fulltext_df['genetic_reagents'].str.len().gt(0).sum()

            print(f"\n**Tool Types Found:**")
            if cell_lines_count > 0:
                print(f"- 🧫 Cell Lines: {cell_lines_count} publications")
            if antibodies_count > 0:
                print(f"- 🔬 Antibodies: {antibodies_count} publications")
            if animal_models_count > 0:
                print(f"- 🐭 Animal Models: {animal_models_count} publications")
            if genetic_reagents_count > 0:
                print(f"- 🧬 Genetic Reagents: {genetic_reagents_count} publications")

            # Top 5 priority publications
            print(f"\n### 📋 Top Priority Publications")
            print(f"\nPublications with the most potential tools to add:\n")

            top_5 = fulltext_df.head(5)
            for idx, row in top_5.iterrows():
                pmid = row.get('pmid', 'N/A')
                title = row.get('title', 'No title')
                tool_count = row.get('tool_count', 0)
                year = row.get('year', 'N/A')

                # Truncate title if too long
                if len(title) > 80:
                    title = title[:77] + "..."

                print(f"{idx + 1}. **[{pmid}]** ({year}) - {tool_count} tools")
                print(f"   {title}\n")

            # Check for GFF publications
            gff_file = 'GFF_publications_with_tools_FULLTEXT.csv'
            if os.path.exists(gff_file):
                gff_mining_df = pd.read_csv(gff_file)
                if not gff_mining_df.empty:
                    print(f"\n### 🎓 GFF-Funded Publications with Novel Tools")
                    print(f"\nFound **{len(gff_mining_df)} GFF publications** with potential tools:\n")

                    for idx, row in gff_mining_df.iterrows():
                        pmid = row.get('pmid', 'N/A')
                        title = row.get('title', 'No title')
                        tool_count = row.get('tool_count', 0)

                        if len(title) > 80:
                            title = title[:77] + "..."

                        print(f"- **[{pmid}]** - {tool_count} tools")
                        print(f"  {title}\n")

        except Exception as e:
            print(f"\n⚠️ Error reading mining results: {e}")
    else:
        print(f"\n⚠️ Full text mining results not found. The mining process may have failed or not completed.")

    # ========================================================================
    # Section 3: Action Items
    # ========================================================================
    print(f"\n---")
    print(f"\n## 📝 Recommended Actions")
    print(f"\n1. **Review Priority Publications:** Check the CSV files in the workflow artifacts")
    print(f"2. **Verify Tool Mentions:** Manually review full text to confirm tool usage in Methods sections")
    print(f"3. **Add Validated Tools:** Submit confirmed tools to the database")
    print(f"4. **Track Progress:** Monitor coverage percentage toward 80% target")

    # ========================================================================
    # Section 4: Submission Files
    # ========================================================================
    print(f"\n---")
    print(f"\n## 📤 Submission-Ready Files")

    # Check for submission files
    submission_files = [
        ('SUBMIT_animal_models.csv', 'Animal Models (syn26486808)'),
        ('SUBMIT_antibodies.csv', 'Antibodies (syn26486811)'),
        ('SUBMIT_cell_lines.csv', 'Cell Lines (syn26486823)'),
        ('SUBMIT_genetic_reagents.csv', 'Genetic Reagents (syn26486832)'),
        ('SUBMIT_publication_links.csv', 'Publication Links (syn51735450)')
    ]

    found_submissions = []
    for filename, description in submission_files:
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            found_submissions.append((filename, description, len(df)))

    if found_submissions:
        print(f"\n**Formatted CSVs ready for table submission:**\n")
        for filename, description, count in found_submissions:
            print(f"- `{filename}` - {count} entries for {description}")

        print(f"\n**⚠️ Manual Review Required:**")
        print(f"- Verify tool mentions in full text")
        print(f"- Fill in required empty fields")
        print(f"- Remove false positives")
        print(f"- Check for duplicates with existing entries")
    else:
        print(f"\n⚠️ No submission files found. Mining may not have discovered novel tools.")

    # ========================================================================
    # Section 5: Artifacts
    # ========================================================================
    print(f"\n---")
    print(f"\n## 📎 Downloadable Reports")
    print(f"\nAll detailed reports are available in the [workflow artifacts](${{{{ github.server_url }}}}/${{{{ github.repository }}}}/actions/runs/${{{{ github.run_id }}}}):")
    print(f"\n**Analysis Reports:**")
    print(f"- `GFF_Tool_Coverage_Report.pdf` - Visual coverage analysis")
    print(f"- `gff_publications_MISSING_tools.csv` - GFF publications without tools")
    print(f"- `priority_publications_FULLTEXT.csv` - Top publications with novel tools")
    print(f"- `novel_tools_FULLTEXT_mining.csv` - Complete mining results")

    print(f"\n**Submission Files:**")
    print(f"- `SUBMIT_*.csv` - Formatted CSVs for table submission")

    print(f"\n**Logs:**")
    print(f"- `coverage_output.log` - Coverage analysis log")
    print(f"- `mining_output.log` - Mining process log")
    print(f"- `formatting_output.log` - Formatting process log")

    print(f"\n---")
    print(f"\n*This report is automatically generated weekly. To run manually, use the [workflow dispatch](${{{{ github.server_url }}}}/${{{{ github.repository }}}}/actions/workflows/check-tool-coverage.yml).*")


if __name__ == "__main__":
    main()
