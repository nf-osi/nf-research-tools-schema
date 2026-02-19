#!/usr/bin/env python3
"""
Script to search for publication PMID 32353955 using available methods
"""

import requests
import json
from urllib.parse import quote

def search_pubmed(pmid):
    """Search PubMed for the given PMID"""
    try:
        # PubMed E-utilities API
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        
        # First, get the summary
        esummary_url = f"{base_url}esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
        response = requests.get(esummary_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("=== PubMed Summary ===")
            print(json.dumps(data, indent=2))
            
        # Then get the full record
        efetch_url = f"{base_url}efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
        response = requests.get(efetch_url, timeout=10)
        
        if response.status_code == 200:
            print("\n=== PubMed XML Record ===")
            print(response.text[:2000] + "..." if len(response.text) > 2000 else response.text)
            
    except Exception as e:
        print(f"Error searching PubMed: {e}")

def search_doi(doi):
    """Search using DOI"""
    try:
        # Try DOI.org API
        url = f"https://doi.org/{doi}"
        headers = {'Accept': 'application/json'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("=== DOI Information ===")
            print(json.dumps(response.json(), indent=2))
            
    except Exception as e:
        print(f"Error searching DOI: {e}")

def search_crossref(doi):
    """Search CrossRef for DOI information"""
    try:
        url = f"https://api.crossref.org/works/{doi}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("=== CrossRef Information ===")
            print(json.dumps(data, indent=2))
            
    except Exception as e:
        print(f"Error searching CrossRef: {e}")

if __name__ == "__main__":
    pmid = "32353955"
    doi = "10.3390/genes11050477"
    
    print(f"Searching for PMID: {pmid}, DOI: {doi}")
    print("=" * 50)
    
    search_pubmed(pmid)
    search_doi(doi)
    search_crossref(doi)
