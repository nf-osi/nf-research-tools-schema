#!/usr/bin/env python3
"""
Mine the 17 GFF-funded publications not yet linked to tools.

Steps:
1. Fetch full text from PubMed Central for uncached GFF publications
2. Run Anthropic AI tool extraction on each publication
3. Save YAML results to tool_reviews/results/
4. Append accepted tools (as new rows) to existing VALIDATED_*.csv files
5. Run generate_review_csv.py to re-filter / deduplicate

Usage:
    python tool_coverage/scripts/mine_gff_publications.py [--dry-run] [--force-rereviews]
"""

import anthropic
import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
import yaml
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

try:
    import requests
except ImportError:
    print("❌ requests not installed: pip install requests")
    sys.exit(1)

# ── GFF publications to mine ──────────────────────────────────────────────────
# 19 total missing; 2 have no PMID (blank in Synapse) — those have published
# equivalents already covered by existing VALIDATED files.  Mine the 17 with
# real PMIDs.
GFF_PMIDS = [
    'PMID:29774626',  # NF1 plexiform intratumor heterogeneity
    'PMID:32572180',  # Late morbidity in childhood glioma NF1 survivors
    'PMID:32369930',  # NF1-MPNST clonal evolution
    'PMID:32152628',  # Longitudinal PNST evaluation in NF1
    'PMID:33519543',  # Autism Spectrum Disorder across RASopathies
    'PMID:33816648',  # miPSC/mESC-derived Retinal Ganglion Cells
    'PMID:29987133',  # Clinical trial design for cNF
    'PMID:33963966',  # Cognitive/EEG NF1 Working Memory (already cached)
    'PMID:34930951',  # Gelatin-HA hybrid IPN scaffold
    'PMID:35945271',  # Nf1 nonsense allele functional restoration
    'PMID:34694046',  # NF1 variants → Ras signaling insights
    'PMID:34945792',  # NF1 antisense morpholino treatment
    'PMID:36796745',  # Unbalancing cAMP/Ras for cNF treatment
    'PMID:34415582',  # Notch signaling in Müller glia regeneration
    'PMID:32396062',  # Tgfb3 in retina regeneration
    'PMID:31836719',  # NF Data Portal community (already cached)
    'PMID:39106942',  # NF1 nonsense suppression mouse model (already cached)
]

# ── Paths ─────────────────────────────────────────────────────────────────────
CACHE_DIR   = Path('tool_reviews/publication_cache')
RESULTS_DIR = Path('tool_reviews/results')
OUTPUT_DIR  = Path('tool_coverage/outputs')
RECIPE_PATH = Path('tool_coverage/scripts/recipes/publication_tool_review.yaml')

# ── NCBI eUtils ───────────────────────────────────────────────────────────────
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EMAIL       = "nf-tools-miner@example.com"
TOOL_NAME   = "nf-research-tools-gff-miner"

# ── Anthropic model ───────────────────────────────────────────────────────────
ANTHROPIC_MODEL = 'claude-sonnet-4-20250514'

TOOL_VALIDATION_YAML_TEMPLATE = """\
toolValidations:
  - toolName: "Exact tool name as it appears in text"
    toolType: "animal_model" | "antibody" | "cell_line" | "genetic_reagent" | "computational_tool" | "advanced_cellular_model" | "patient_derived_model" | "clinical_assessment_tool"
    verdict: "Accept" | "Reject" | "Uncertain"
    confidence: 0.0-1.0
    recommendation: "Keep" | "Remove" | "Manual Review Required"
    contextSnippet: "...up to 200 chars of surrounding text showing tool usage..."
    usageType: "Development" | "Experimental Usage" | "Citation Only" | "Not Found in Context"
    # Type-specific fields (add ALL you can extract; omit fields not found):
    # animal_model:           strainNomenclature*, backgroundStrain, backgroundSubstrain, animalModelGeneticDisorder, animalModelOfManifestation
    # antibody:               targetAntigen*, hostOrganism, clonality, reactiveSpecies, conjugate
    # cell_line:              organ*, tissue, cellLineGeneticDisorder, cellLineManifestation, cellLineCategory
    # genetic_reagent:        insertName*, vectorType, vectorBackbone, promoter, insertSpecies, selectableMarker
    # computational_tool:     softwareType*, softwareVersion, programmingLanguage, sourceRepository
    # advanced_cellular_model: modelType*, derivationSource*, cellTypes, organoidType, matrixType
    # patient_derived_model:  modelSystemType*, patientDiagnosis*, hostStrain, tumorType, engraftmentSite
    # clinical_assessment_tool: assessmentType*, targetPopulation*, diseaseSpecific, numberOfItems
    # (* = critical, fill if at all possible)
  # Repeat for each tool. Use [] if no tools found."""

# ── Recipe loading ─────────────────────────────────────────────────────────────
_system_prompt = None
_task_instructions = None

def _load_recipe():
    global _system_prompt, _task_instructions
    if _system_prompt is not None:
        return
    with open(RECIPE_PATH) as f:
        recipe = yaml.safe_load(f)
    _system_prompt = recipe.get('instructions', '').strip()
    _task_instructions = recipe.get('prompt', '').strip()


# ── Text fetching from PubMed Central ─────────────────────────────────────────

def _clean_pmid(pmid: str) -> str:
    return pmid.replace('PMID:', '').strip()


def _fetch_pmc_id(pmid: str) -> Optional[str]:
    """Get PMC ID from PMID via elink."""
    clean = _clean_pmid(pmid)
    params = {
        'dbfrom': 'pubmed', 'db': 'pmc',
        'id': clean, 'tool': TOOL_NAME, 'email': EMAIL,
        'retmode': 'json',
    }
    try:
        r = requests.get(f"{EUTILS_BASE}elink.fcgi", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        links = (
            data.get('linksets', [{}])[0]
                .get('linksetdbs', [{}])[0]
                .get('links', [])
        )
        return str(links[0]) if links else None
    except Exception as e:
        print(f"    elink error for {pmid}: {e}")
        return None


def _fetch_pmc_fulltext_xml(pmc_id: str) -> str:
    """Fetch full-text XML from PMC for a given PMC ID."""
    params = {
        'db': 'pmc', 'id': pmc_id,
        'rettype': 'full', 'retmode': 'xml',
        'tool': TOOL_NAME, 'email': EMAIL,
    }
    try:
        r = requests.get(f"{EUTILS_BASE}efetch.fcgi", params=params, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    PMC efetch error: {e}")
        return ""


def _extract_sections(xml_text: str) -> dict:
    """Parse PMC XML and return abstract/methods/intro/results/discussion text."""
    sections = {
        'abstract': '',
        'methods': '',
        'introduction': '',
        'results': '',
        'discussion': '',
        'title': '',
        'journal': '',
        'year': '',
        'doi': '',
        'authors': '',
    }
    if not xml_text:
        return sections

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return sections

    def iter_text(el) -> str:
        parts = []
        if el.text:
            parts.append(el.text.strip())
        for child in el:
            parts.append(iter_text(child))
            if child.tail:
                parts.append(child.tail.strip())
        return ' '.join(p for p in parts if p)

    # Title
    for t in root.iter('article-title'):
        sections['title'] = iter_text(t)
        break

    # Journal
    for j in root.iter('journal-title'):
        sections['journal'] = iter_text(j)
        break

    # Year
    for pub_date in root.iter('pub-date'):
        yr = pub_date.find('year')
        if yr is not None:
            sections['year'] = (yr.text or '').strip()
            break

    # DOI
    for article_id in root.iter('article-id'):
        if article_id.get('pub-id-type') == 'doi':
            sections['doi'] = (article_id.text or '').strip()
            break

    # Authors
    authors = []
    for contrib in root.iter('contrib'):
        if contrib.get('contrib-type') == 'author':
            sn = contrib.find('.//surname')
            gn = contrib.find('.//given-names')
            if sn is not None:
                name = (sn.text or '').strip()
                if gn is not None:
                    name = f"{gn.text.strip()} {name}"
                authors.append(name)
    sections['authors'] = '; '.join(authors)

    # Abstract
    for ab in root.iter('abstract'):
        sections['abstract'] = iter_text(ab)
        break

    # Body sections
    keyword_map = {
        'method': 'methods',
        'material': 'methods',
        'experimental': 'methods',
        'introduction': 'introduction',
        'background': 'introduction',
        'result': 'results',
        'finding': 'results',
        'discussion': 'discussion',
        'conclusion': 'discussion',
    }

    for sec in root.iter('sec'):
        # Try to find the section label/title
        title_el = sec.find('title')
        title_text = iter_text(title_el).lower() if title_el is not None else ''

        matched = None
        for kw, slot in keyword_map.items():
            if kw in title_text:
                matched = slot
                break

        if matched:
            body = iter_text(sec)
            if len(body) > len(sections[matched]):
                sections[matched] = body

    return sections


def _fetch_pubmed_abstract(pmid: str) -> dict:
    """Fallback: fetch just abstract + metadata from PubMed efetch."""
    clean = _clean_pmid(pmid)
    params = {
        'db': 'pubmed', 'id': clean,
        'rettype': 'abstract', 'retmode': 'xml',
        'tool': TOOL_NAME, 'email': EMAIL,
    }
    result = {'abstract': '', 'title': '', 'journal': '', 'year': '', 'doi': '', 'authors': ''}
    try:
        r = requests.get(f"{EUTILS_BASE}efetch.fcgi", params=params, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.text)

        def t(el):
            return ''.join(el.itertext()).strip() if el is not None else ''

        result['title'] = t(root.find('.//ArticleTitle'))
        result['journal'] = t(root.find('.//Journal/Title'))
        yr = root.find('.//PubDate/Year') or root.find('.//PubDate/MedlineDate')
        result['year'] = t(yr)[:4] if yr is not None else ''
        doi_el = root.find('.//ArticleId[@IdType="doi"]')
        result['doi'] = t(doi_el)
        abstract_texts = root.findall('.//AbstractText')
        result['abstract'] = ' '.join(t(a) for a in abstract_texts)
        authors_els = root.findall('.//Author')
        names = []
        for a in authors_els[:5]:
            ln = t(a.find('LastName'))
            fn = t(a.find('ForeName'))
            if ln:
                names.append(f"{fn} {ln}".strip())
        result['authors'] = '; '.join(names)
    except Exception as e:
        print(f"    PubMed abstract fetch error for {pmid}: {e}")
    return result


def fetch_and_cache(pmid: str) -> Optional[dict]:
    """
    Fetch full text for a PMID; save to cache and return cache dict.
    Returns None if both PMC full-text and abstract fetch fail.
    """
    clean = _clean_pmid(pmid)
    cache_file = CACHE_DIR / f'{clean}_text.json'

    if cache_file.exists():
        print(f"  ✓ Already cached: {pmid}")
        with open(cache_file) as f:
            return json.load(f)

    print(f"  Fetching: {pmid}")
    time.sleep(0.5)  # NCBI rate limit

    # Try PMC full text first
    pmc_id = _fetch_pmc_id(pmid)
    if pmc_id:
        time.sleep(0.5)
        xml = _fetch_pmc_fulltext_xml(pmc_id)
        if xml:
            secs = _extract_sections(xml)
            cache_level = 'minimal' if not any([
                secs['methods'], secs['results'], secs['discussion']
            ]) else 'full'
            cache = {
                'pmid': pmid,
                'title': secs['title'],
                'abstract': secs['abstract'],
                'methods': secs['methods'],
                'introduction': secs['introduction'],
                'results': secs['results'],
                'discussion': secs['discussion'],
                'authors': secs['authors'],
                'journal': secs['journal'],
                'publicationDate': secs['year'],
                'doi': secs['doi'],
                'cache_level': cache_level,
                'has_fulltext': bool(secs['methods'] or secs['results']),
                'fetch_date': datetime.now().isoformat(),
            }
            with open(cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
            print(f"    ✅ Cached from PMC (level={cache_level}, "
                  f"methods={bool(secs['methods'])}, results={bool(secs['results'])})")
            return cache

    # Fallback to abstract-only
    print(f"    ⚠️  PMC not available — fetching abstract only")
    meta = _fetch_pubmed_abstract(pmid)
    cache = {
        'pmid': pmid,
        'title': meta['title'],
        'abstract': meta['abstract'],
        'methods': '',
        'introduction': '',
        'results': '',
        'discussion': '',
        'authors': meta['authors'],
        'journal': meta['journal'],
        'publicationDate': meta['year'],
        'doi': meta['doi'],
        'cache_level': 'abstract_only',
        'has_fulltext': False,
        'fetch_date': datetime.now().isoformat(),
    }
    if meta['abstract']:
        with open(cache_file, 'w') as f:
            json.dump(cache, f, indent=2)
        print(f"    ✅ Cached abstract-only for {pmid}")
        return cache

    print(f"    ❌ Could not fetch any text for {pmid}")
    return None


# ── AI review ─────────────────────────────────────────────────────────────────

def build_prompt(pmid: str, cached: dict) -> tuple[str, str]:
    """Build (system_prompt, user_message) for the Anthropic API call."""
    _load_recipe()

    def section(label, text):
        return f"**{label}:**\n{text.strip() if text and text.strip() else '(not available)'}"

    user_message = f"""Review publication {pmid} for NF research tool validation.

**PUBLICATION METADATA:**
- PMID: {pmid}
- Title: {cached.get('title', '')}
- DOI: {cached.get('doi', '')}
- Journal: {cached.get('journal', '')}
- Year: {cached.get('publicationDate', '')}
- Has Abstract: {bool(cached.get('abstract', '').strip())}
- Has Methods Section: {bool(cached.get('methods', '').strip())}
- Has Introduction: {bool(cached.get('introduction', '').strip())}
- Has Results: {bool(cached.get('results', '').strip())}
- Has Discussion: {bool(cached.get('discussion', '').strip())}

{section('ABSTRACT', cached.get('abstract', ''))}

{section('METHODS', cached.get('methods', ''))}

{section('INTRODUCTION', cached.get('introduction', ''))}

{section('RESULTS', cached.get('results', ''))}

{section('DISCUSSION', cached.get('discussion', ''))}

**MINED TOOLS (0 total):**
(none — scan the full text for potentially missed tools)

---
{_task_instructions}

Output ONLY the YAML below — no explanation before or after:

```yaml
{TOOL_VALIDATION_YAML_TEMPLATE}
```
"""
    return _system_prompt, user_message


def run_review(pmid: str, cached: dict, client: anthropic.Anthropic,
               force: bool = False) -> Optional[dict]:
    """Run AI tool-extraction review; return parsed YAML dict or None."""
    clean = _clean_pmid(pmid)
    yaml_file = RESULTS_DIR / f'{clean}_tool_review.yaml'

    if yaml_file.exists() and not force:
        print(f"  ⏭️  Already reviewed: {pmid}")
        with open(yaml_file) as f:
            return yaml.safe_load(f)

    if cached.get('cache_level') == 'abstract_only' and not force:
        print(f"  ⏭️  Skipping abstract-only cache: {pmid}")
        return None

    print(f"  🔬 Reviewing {pmid} …")
    system_prompt, user_message = build_prompt(pmid, cached)

    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8192,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            text = msg.content[0].text
            print(f"    {msg.usage.input_tokens}in/{msg.usage.output_tokens}out tokens")

            # Extract YAML
            match = re.search(r'```yaml\s*\n(.*?)\n```', text, re.DOTALL)
            if not match:
                match = re.search(r'(toolValidations:.*)', text, re.DOTALL)
            if not match:
                print(f"    ⚠️  No YAML in response (attempt {attempt+1})")
                time.sleep(2 ** attempt)
                continue

            yaml_text = match.group(1).strip()
            data = yaml.safe_load(yaml_text)
            if not isinstance(data, dict) or 'toolValidations' not in data:
                print(f"    ⚠️  Bad YAML structure (attempt {attempt+1})")
                time.sleep(2 ** attempt)
                continue

            yaml_file.write_text(yaml_text)
            n_keep = sum(1 for t in (data.get('toolValidations') or [])
                         if t.get('recommendation') == 'Keep')
            print(f"    ✅ {n_keep} tools kept → {yaml_file.name}")
            return data

        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)
            print(f"    ⚠️  Rate limit — waiting {wait}s")
            time.sleep(wait)
        except Exception as e:
            print(f"    ❌ Error (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)

    return None


# ── Append tools to VALIDATED_*.csv ───────────────────────────────────────────

_COMMON_KEYS = {
    'toolName', 'toolType', 'verdict', 'confidence',
    'recommendation', 'contextSnippet', 'usageType',
}

TYPE_TO_STEM = {
    'animal_model': 'animal_models',
    'antibody': 'antibodies',
    'cell_line': 'cell_lines',
    'genetic_reagent': 'genetic_reagents',
    'computational_tool': 'computational_tools',
    'advanced_cellular_model': 'advanced_cellular_models',
    'patient_derived_model': 'patient_derived_models',
    'clinical_assessment_tool': 'clinical_assessment_tools',
}

RESOURCE_TYPE_MAP = {
    'animal_model': 'Animal Model',
    'antibody': 'Antibody',
    'cell_line': 'Cell Line',
    'genetic_reagent': 'Genetic Reagent',
    'computational_tool': 'Computational Tool',
    'advanced_cellular_model': 'Advanced Cellular Model',
    'patient_derived_model': 'Patient-Derived Model',
    'clinical_assessment_tool': 'Clinical Assessment Tool',
}


def _stable_id(prefix: str, *parts: str) -> str:
    key = '|'.join(str(p).lower().strip() for p in parts)
    return prefix + hashlib.sha1(key.encode()).hexdigest()[:8]


def _f(fields: dict, key: str, fallback: str = '') -> str:
    return str(fields.get(key, fallback) or fallback)


def make_detail_row(tool_type: str, tool_name: str, fields: dict) -> dict:
    """Return a dict of Synapse detail-table columns for one tool."""
    f = fields
    if tool_type == 'animal_model':
        return {
            'strainNomenclature': _f(f, 'strainNomenclature', tool_name),
            'backgroundStrain': _f(f, 'backgroundStrain'),
            'backgroundSubstrain': _f(f, 'backgroundSubstrain'),
            'animalModelGeneticDisorder': _f(f, 'animalModelGeneticDisorder'),
            'animalModelOfManifestation': _f(f, 'animalModelOfManifestation'),
            'transplantationType': _f(f, 'transplantationType'),
            'animalState': _f(f, 'animalState'),
            'generation': _f(f, 'generation'),
            'donorId': '', 'transplantationDonorId': '',
        }
    elif tool_type == 'antibody':
        return {
            'targetAntigen': _f(f, 'targetAntigen', tool_name),
            'hostOrganism': _f(f, 'hostOrganism'),
            'clonality': _f(f, 'clonality'),
            'reactiveSpecies': _f(f, 'reactiveSpecies'),
            'conjugate': _f(f, 'conjugate'),
            'vendorId': '', 'cloneId': '', 'RRID': '',
        }
    elif tool_type == 'cell_line':
        return {
            'organ': _f(f, 'organ'),
            'tissue': _f(f, 'tissue'),
            'cellLineGeneticDisorder': _f(f, 'cellLineGeneticDisorder'),
            'cellLineManifestation': _f(f, 'cellLineManifestation'),
            'cellLineCategory': _f(f, 'cellLineCategory'),
            'RRID': '',
        }
    elif tool_type == 'genetic_reagent':
        return {
            'insertName': _f(f, 'insertName', tool_name),
            'vectorType': _f(f, 'vectorType'),
            'vectorBackbone': _f(f, 'vectorBackbone'),
            'promoter': _f(f, 'promoter'),
            'insertSpecies': _f(f, 'insertSpecies'),
            'selectableMarker': _f(f, 'selectableMarker'),
            'gRNAshRNASequence': _f(f, 'gRNAshRNASequence'),
            'RRID': '', 'Addgene_id': '',
        }
    elif tool_type == 'computational_tool':
        return {
            'softwareName': _f(f, 'softwareName', tool_name),
            'softwareType': _f(f, 'softwareType'),
            'softwareVersion': _f(f, 'softwareVersion'),
            'programmingLanguage': _f(f, 'programmingLanguage'),
            'sourceRepository': _f(f, 'sourceRepository'),
            'RRID': '',
        }
    elif tool_type == 'advanced_cellular_model':
        return {
            'modelType': _f(f, 'modelType'),
            'derivationSource': _f(f, 'derivationSource'),
            'cellTypes': _f(f, 'cellTypes'),
            'organoidType': _f(f, 'organoidType'),
            'matrixType': _f(f, 'matrixType'),
            'cultureSystem': _f(f, 'cultureSystem'),
        }
    elif tool_type == 'patient_derived_model':
        return {
            'modelSystemType': _f(f, 'modelSystemType'),
            'patientDiagnosis': _f(f, 'patientDiagnosis'),
            'hostStrain': _f(f, 'hostStrain'),
            'tumorType': _f(f, 'tumorType'),
            'engraftmentSite': _f(f, 'engraftmentSite'),
            'passageNumber': _f(f, 'passageNumber'),
            'establishmentRate': _f(f, 'establishmentRate'),
            'molecularCharacterization': _f(f, 'molecularCharacterization'),
        }
    elif tool_type == 'clinical_assessment_tool':
        return {
            'assessmentName': _f(f, 'assessmentName', tool_name),
            'assessmentType': _f(f, 'assessmentType'),
            'targetPopulation': _f(f, 'targetPopulation'),
            'diseaseSpecific': _f(f, 'diseaseSpecific'),
            'numberOfItems': _f(f, 'numberOfItems'),
            'scoringMethod': _f(f, 'scoringMethod'),
        }
    return {}


def build_validated_rows(pmid: str, doi: str, title: str, year: str,
                         tool_validations: list) -> dict[str, list[dict]]:
    """Convert tool validations to rows suitable for appending to VALIDATED_*.csv."""
    by_type: dict[str, list[dict]] = {}

    for tv in tool_validations:
        if tv.get('recommendation') != 'Keep':
            continue

        raw_type = tv.get('toolType', '').lower()
        # Normalise plural/alternate forms
        raw_type = raw_type.rstrip('s').replace('antibodie', 'antibody')
        if raw_type == 'genetic_reagent':
            pass  # already singular
        if raw_type not in TYPE_TO_STEM:
            # Try removing trailing 's' variants
            for k in TYPE_TO_STEM:
                if raw_type == k:
                    break
            else:
                print(f"    ⚠️  Unknown tool type: {tv.get('toolType')} — skipping")
                continue

        tool_name = (tv.get('toolName') or '').strip()
        if not tool_name:
            continue

        extracted = {k: v for k, v in tv.items()
                     if k not in _COMMON_KEYS and not k.startswith('#')
                     and v not in (None, '', [])}

        detail = make_detail_row(raw_type, tool_name, extracted)
        resource_id = _stable_id('RES', tool_name, raw_type)
        pub_id = f'PUB{_clean_pmid(pmid)}'

        row = {
            '_pmid': pmid,
            '_doi': doi,
            '_publicationTitle': title,
            '_year': year,
            '_toolName': tool_name,
            '_toolType': raw_type,
            '_usageType': tv.get('usageType', ''),
            '_context': tv.get('contextSnippet', ''),
            '_confidence': tv.get('confidence', ''),
            '_verdict': tv.get('verdict', ''),
            'resourceId': resource_id,
            'publicationId': pub_id,
            **detail,
        }

        by_type.setdefault(raw_type, []).append(row)

    return by_type


def append_to_validated(by_type: dict[str, list[dict]], dry_run: bool = False):
    """Append new tool rows to the existing VALIDATED_*.csv files."""
    for tool_type, rows in by_type.items():
        stem = TYPE_TO_STEM[tool_type]
        validated_file = OUTPUT_DIR / f'VALIDATED_{stem}.csv'

        if not validated_file.exists():
            print(f"  ⚠️  {validated_file.name} not found — skipping {tool_type}")
            continue

        # Read existing rows to avoid exact duplicates
        with open(validated_file, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)
            fieldnames = list(reader.fieldnames or [])

        # Determine which rows are genuinely new (no matching resourceId or same PMID+name)
        existing_keys = {
            (r.get('resourceId', ''), r.get('_pmid', ''))
            for r in existing_rows
        }
        new_rows = []
        for row in rows:
            key = (row.get('resourceId', ''), row.get('_pmid', ''))
            if key in existing_keys:
                print(f"    ↩️  Already exists: {row.get('_toolName')} ({row.get('_pmid')})")
            else:
                new_rows.append(row)

        if not new_rows:
            print(f"  ℹ️  No new rows for {stem}")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would append {len(new_rows)} rows to {validated_file.name}:")
            for r in new_rows:
                print(f"    + {r.get('_toolName')} ({r.get('_toolType')})")
            continue

        # Merge fieldnames — union of existing and new keys
        new_keys = []
        for r in new_rows:
            for k in r:
                if k not in fieldnames:
                    new_keys.append(k)
                    fieldnames.append(k)

        # Append
        all_rows = existing_rows + new_rows
        with open(validated_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"  ✅ Appended {len(new_rows)} rows to {validated_file.name}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Mine GFF publications not yet linked to tools'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Fetch + review but do not write to VALIDATED files')
    parser.add_argument('--force-rereviews', action='store_true',
                        help='Re-run AI review even if YAML already exists')
    parser.add_argument('--skip-fetch', action='store_true',
                        help='Skip full-text fetching (use existing cache only)')
    args = parser.parse_args()

    print("=" * 80)
    print("GFF Publication Miner")
    print("=" * 80)

    # Ensure directories exist
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Init Anthropic client
    import os
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    # ── Step 1: Fetch full texts ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Step 1: Fetching full texts ({len(GFF_PMIDS)} publications)")
    print(f"{'='*60}")

    caches: dict[str, dict] = {}
    for pmid in GFF_PMIDS:
        if args.skip_fetch:
            clean = _clean_pmid(pmid)
            cache_file = CACHE_DIR / f'{clean}_text.json'
            if cache_file.exists():
                with open(cache_file) as f:
                    caches[pmid] = json.load(f)
            else:
                print(f"  ⏭️  No cache for {pmid} (--skip-fetch active)")
        else:
            cached = fetch_and_cache(pmid)
            if cached:
                caches[pmid] = cached

    print(f"\nFetched/loaded {len(caches)}/{len(GFF_PMIDS)} publications")
    for pmid, c in caches.items():
        has_methods = bool(c.get('methods', '').strip())
        has_abs = bool(c.get('abstract', '').strip())
        print(f"  {pmid}: {c.get('cache_level','?')} "
              f"| abstract={'✓' if has_abs else '✗'} "
              f"| methods={'✓' if has_methods else '✗'}")

    # ── Step 2: AI reviews ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Step 2: Running AI reviews")
    print(f"{'='*60}")

    all_by_type: dict[str, list[dict]] = {}
    reviewed = 0
    skipped = 0
    no_tools = 0

    for pmid in GFF_PMIDS:
        cached = caches.get(pmid)
        if not cached:
            print(f"  ⏭️  No cache for {pmid} — skipping review")
            skipped += 1
            continue

        result = run_review(pmid, cached, client, force=args.force_rereviews)
        if result is None:
            skipped += 1
            continue

        reviewed += 1

        # Get metadata from cache
        doi = cached.get('doi', '')
        title = cached.get('title', '')
        year = cached.get('publicationDate', '')

        tool_validations = result.get('toolValidations') or []
        kept = [t for t in tool_validations if t.get('recommendation') == 'Keep']

        if not kept:
            no_tools += 1
            print(f"    ℹ️  No tools found/kept for {pmid}")
            continue

        by_type = build_validated_rows(pmid, doi, title, year, kept)
        for tt, rows in by_type.items():
            all_by_type.setdefault(tt, []).extend(rows)

        print(f"    📊 {len(kept)} tools accepted: "
              + ', '.join(f"{tt}×{len(rr)}" for tt, rr in by_type.items()))

    print(f"\n{'='*60}")
    print(f"Review Summary:")
    print(f"  Reviewed: {reviewed}")
    print(f"  Skipped:  {skipped}")
    print(f"  No tools: {no_tools}")
    total_new = sum(len(rr) for rr in all_by_type.values())
    print(f"  New tool rows: {total_new}")
    for tt, rr in sorted(all_by_type.items()):
        print(f"    {tt}: {len(rr)} rows")
    print(f"{'='*60}")

    if not all_by_type:
        print("\nℹ️  No new tools found — nothing to append.")
        return

    # ── Step 3: Append to VALIDATED_*.csv ────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Step 3: Appending to VALIDATED_*.csv{'  [DRY-RUN]' if args.dry_run else ''}")
    print(f"{'='*60}")

    append_to_validated(all_by_type, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY-RUN] Skipping generate_review_csv.py")
        return

    # ── Step 4: Re-run generate_review_csv.py ────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Step 4: Running generate_review_csv.py to re-filter & dedup")
    print(f"{'='*60}")

    result = subprocess.run(
        [sys.executable, 'tool_coverage/scripts/generate_review_csv.py',
         '--output-dir', str(OUTPUT_DIR)],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"\n❌ generate_review_csv.py exited with code {result.returncode}")
    else:
        print(f"\n✅ Done — VALIDATED_*.csv files updated.")


if __name__ == '__main__':
    main()
