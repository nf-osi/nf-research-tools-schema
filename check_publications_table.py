#!/usr/bin/env python3
"""
Check the structure and values in the publications table to understand
how to identify GFF-funded publications.
"""

import synapseclient
import pandas as pd

# Login to Synapse
syn = synapseclient.Synapse()
syn.login()

print("Checking publications table structure (syn16857542)...")
print("=" * 80)

# Query all publications
query = syn.tableQuery("SELECT * FROM syn16857542 LIMIT 10")
df = query.asDataFrame()

print(f"\nTotal columns: {len(df.columns)}")
print(f"Columns: {', '.join(df.columns.tolist())}")

print(f"\nFirst few rows:")
print(df.head())

# Check fundingAgency column
if 'fundingAgency' in df.columns:
    print(f"\nFundingAgency column unique values:")
    full_query = syn.tableQuery("SELECT fundingAgency FROM syn16857542")
    full_df = full_query.asDataFrame()
    print(full_df['fundingAgency'].value_counts())
else:
    print("\n⚠️  No 'fundingAgency' column found!")
    print("Looking for columns that might indicate funding...")
    funding_cols = [col for col in df.columns if any(
        keyword in col.lower() for keyword in ['fund', 'grant', 'gff', 'agency']
    )]
    print(f"Possible funding-related columns: {funding_cols}")
