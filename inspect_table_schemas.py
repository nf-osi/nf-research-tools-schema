#!/usr/bin/env python3
"""
Inspect the schemas of all tool type tables to understand their column structure.
"""

import synapseclient
import pandas as pd
import os

# Login to Synapse
syn = synapseclient.Synapse()
auth_token = os.getenv('SYNAPSE_AUTH_TOKEN')
if auth_token:
    syn.login(authToken=auth_token)
else:
    syn.login()

tables = {
    'Animal Models': 'syn26486808',
    'Antibodies': 'syn26486811',
    'Biobanks': 'syn26486821',
    'Cell Lines': 'syn26486823',
    'Genetic Reagents': 'syn26486832',
    'Publication Links': 'syn51735450'
}

for name, syn_id in tables.items():
    print(f"\n{'=' * 80}")
    print(f"{name} ({syn_id})")
    print('=' * 80)

    # Query table to get schema
    query = syn.tableQuery(f"SELECT * FROM {syn_id} LIMIT 1")
    df = query.asDataFrame()

    print(f"\nColumns ({len(df.columns)}):")
    for col in df.columns:
        dtype = df[col].dtype
        print(f"  - {col}: {dtype}")

    # Show sample data if available
    if not df.empty:
        print(f"\nSample data:")
        print(df.head(1).to_string())
