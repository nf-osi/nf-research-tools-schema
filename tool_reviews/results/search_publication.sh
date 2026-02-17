#!/bin/bash

# Search for PMID 32353955 using various APIs

echo "Searching for PMID: 32353955, DOI: 10.3390/genes11050477"
echo "=================================================="

# Try PubMed E-utilities
echo "=== PubMed E-utilities Summary ==="
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=32353955&retmode=json" | python3 -m json.tool

echo -e "\n=== PubMed E-utilities Full Record ==="
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=32353955&retmode=xml" | head -100

echo -e "\n=== CrossRef API ==="
curl -s "https://api.crossref.org/works/10.3390/genes11050477" | python3 -m json.tool | head -100

echo -e "\n=== DOI.org API ==="
curl -s -H "Accept: application/json" "https://doi.org/10.3390/genes11050477" | python3 -m json.tool | head -50
