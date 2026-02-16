#!/usr/bin/env python3
"""
Reconstruct screened_publications.csv from workflow logs.
This allows us to resume the workflow without re-running the expensive screening step.
"""

import re
import pandas as pd
import synapseclient
import sys
from pathlib import Path

def extract_research_pmids_from_logs(log_file):
    """Extract PMIDs marked as research from workflow logs."""
    with open(log_file, 'r') as f:
        logs = f.read()

    # Extract all INCLUDE entries with PMID and reason
    pattern = r'PMID:(\d+): ✅ INCLUDE - (.+?)(?:\n|$)'
    matches = re.findall(pattern, logs)

    research_pmids = {}
    for pmid, reason in matches:
        research_pmids[int(pmid)] = reason.strip()

    print(f"✓ Extracted {len(research_pmids)} research PMIDs from logs")
    return research_pmids


def fetch_publication_metadata_from_pubmed(pmids):
    """
    Fetch publication metadata from PubMed using E-utilities.
    """
    import requests
    from xml.etree import ElementTree as ET
    import time

    print(f"\nFetching metadata for {len(pmids)} publications from PubMed...")

    # Process in batches of 200
    batch_size = 200
    all_records = []

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i+batch_size]
        print(f"  Fetching batch {i//batch_size + 1}/{(len(pmids)-1)//batch_size + 1} ({len(batch)} PMIDs)...")

        # Fetch using esummary
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        params = {
            'db': 'pubmed',
            'id': ','.join(map(str, batch)),
            'retmode': 'xml'
        }

        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"  ⚠️  Warning: Failed to fetch batch (status {response.status_code})")
            continue

        # Parse XML
        root = ET.fromstring(response.content)

        for doc_sum in root.findall('.//DocSum'):
            pmid = doc_sum.find('Id').text if doc_sum.find('Id') is not None else None

            # Extract fields
            title = None
            journal = None
            year = None
            doi = None

            for item in doc_sum.findall('Item'):
                name = item.get('Name')
                if name == 'Title':
                    title = item.text
                elif name == 'Source':
                    journal = item.text
                elif name == 'PubDate':
                    # Extract year from date string (e.g., "2020 Jan 15")
                    date_text = item.text
                    if date_text:
                        parts = date_text.split()
                        if parts and parts[0].isdigit():
                            year = int(parts[0])
                elif name == 'DOI':
                    doi = item.text

            if pmid:
                all_records.append({
                    'pmid': int(pmid),
                    'doi': doi,
                    'title': title,
                    'journal': journal,
                    'year': year
                })

        # Rate limit
        if i + batch_size < len(pmids):
            time.sleep(0.5)

    df = pd.DataFrame(all_records)
    print(f"✓ Fetched metadata for {len(df)} publications from PubMed")
    return df


def main():
    log_file = '/tmp/workflow_full_log.txt'
    output_dir = Path('tool_coverage/outputs')
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("Reconstruct Screened Publications from Workflow Logs")
    print("=" * 80)

    # Check if log file exists
    if not Path(log_file).exists():
        print(f"❌ Log file not found: {log_file}")
        print("   Please run: gh run view --job=<job_id> --log 2>&1 > /tmp/workflow_full_log.txt")
        sys.exit(1)

    # Extract research PMIDs from logs
    print("\n1. Extracting research PMIDs from logs...")
    research_pmids = extract_research_pmids_from_logs(log_file)

    # Fetch metadata from PubMed
    print("\n2. Fetching publication metadata from PubMed...")
    metadata_df = fetch_publication_metadata_from_pubmed(list(research_pmids.keys()))

    # Merge with screening reasons
    screening_df = pd.DataFrame([
        {'pmid': int(pmid), 'screening_reasoning': reason}
        for pmid, reason in research_pmids.items()
    ])

    # Merge metadata with screening results
    result_df = metadata_df.merge(screening_df, on='pmid', how='left')
    result_df['is_research'] = True
    result_df['query_type'] = 'reconstructed'  # Mark as reconstructed

    # Add missing columns
    result_df['source'] = 'pubmed'

    # Reorder columns
    columns = ['pmid', 'doi', 'title', 'journal', 'year',
               'query_type', 'source', 'is_research', 'screening_reasoning']
    result_df = result_df[[col for col in columns if col in result_df.columns]]

    # Save to output
    output_file = output_dir / 'screened_publications.csv'
    result_df.to_csv(output_file, index=False)
    print(f"\n✅ Saved {len(result_df)} screened publications to {output_file}")

    # Also save the screening cache format
    cache_file = output_dir / 'title_screening_cache.csv'
    cache_df = result_df[['pmid', 'title', 'is_research', 'screening_reasoning']].copy()
    cache_df.to_csv(cache_file, index=False)
    print(f"✅ Saved screening cache to {cache_file}")

    # Summary
    print("\n" + "=" * 80)
    print("Summary:")
    print("=" * 80)
    print(f"  Research publications: {len(result_df)}")
    print(f"  Output file: {output_file}")
    print(f"  Cache file: {cache_file}")
    print("\nNext steps:")
    print("  1. Run the workflow again with --max-publications to process in smaller batches")
    print("  2. Or run locally: python tool_coverage/scripts/fetch_publication_fulltext.py --max-publications 100")


if __name__ == '__main__':
    main()
