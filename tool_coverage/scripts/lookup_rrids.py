#!/usr/bin/env python3
"""lookup_rrids.py — Populate rrid column in VALIDATED_resources.csv.

Queries public registries by tool name; writes discovered RRIDs back to
VALIDATED_resources.csv and the matching type-specific VALIDATED_*.csv.

Registries used (all public, no API key required by default):
  cell_line / patient_derived_model
      → Cellosaurus REST API  https://api.cellosaurus.org/
        Returns RRID:CVCL_XXXX
  genetic_reagent
      → Addgene search  https://www.addgene.org/search/catalog/plasmids/
        Returns RRID:Addgene_XXXXX
  animal_model
      → IMSR (International Mouse Strain Resource)
          https://www.findmice.org/summary?gfAccessionIds=&strainsOnly=1&q=
        Returns RRID:IMSR_JAX:XXXXX  (Jackson Laboratory strains)
  antibody
      → SciCrunch Antibody Registry (requires --api-key or SCICRUNCH_API_KEY)
        Returns RRID:AB_XXXXXX

For any tool type, if the context already contains an explicit RRID: string it
is extracted directly without a network call.

Usage:
  python tool_coverage/scripts/lookup_rrids.py
  python tool_coverage/scripts/lookup_rrids.py --output-dir tool_coverage/outputs
  python tool_coverage/scripts/lookup_rrids.py --dry-run
  python tool_coverage/scripts/lookup_rrids.py --force            # re-query even if rrid filled
  python tool_coverage/scripts/lookup_rrids.py --api-key KEY      # SciCrunch key for antibodies
  python tool_coverage/scripts/lookup_rrids.py --tool-type cell_line  # single type only
"""

import argparse
import csv
import os
import re
import time
import urllib.parse
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RRID_IN_TEXT_RE = re.compile(r'RRID:\s*([A-Za-z0-9_:\-]+)', re.IGNORECASE)


def _extract_rrid_from_text(text: str) -> str:
    """Return the first RRID:XXXX string found in text, or ''."""
    m = _RRID_IN_TEXT_RE.search(text or '')
    return f'RRID:{m.group(1)}' if m else ''


def _get(url: str, params: dict | None = None, headers: dict | None = None,
         timeout: int = 10, quiet: bool = False) -> dict | list | None:
    """Simple HTTP GET returning parsed JSON, or None on error."""
    import urllib.request
    import json

    if params:
        url = url + '?' + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers=headers or {
        'User-Agent': 'nf-research-tools-rrid-lookup/1.0 (contact: bgarana@synapse.org)',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        if not quiet:
            print(f'    ⚠️  GET {url} → {exc}')
        return None


# ---------------------------------------------------------------------------
# Registry lookup functions
# ---------------------------------------------------------------------------

def _lookup_cellosaurus(name: str) -> str:
    """Search Cellosaurus for a cell line by name; return RRID:CVCL_XXXX or ''.

    Uses the ExPASy Cellosaurus REST API (public, no key required).
    Response structure:
      {"Cellosaurus": {"cell-line-list": [
        {"name-list": [{"type": "identifier", "value": "MCF-7"}, ...],
         "accession-list": [{"type": "primary", "value": "CVCL_0031"}], ...}
      ]}}
    The RRID is formed as f"RRID:{accession}" where accession already includes
    the "CVCL_" prefix (e.g. "CVCL_0031" → "RRID:CVCL_0031").
    """
    params = {
        'q': name,
        'format': 'json',
        'rows': '50',   # broad search; we filter for exact name match below
    }
    data = _get('https://api.cellosaurus.org/search/cell-line', params=params)
    if not data:
        return ''

    results = data.get('Cellosaurus', {}).get('cell-line-list', []) or []
    if not results:
        return ''

    norm = name.lower().strip()

    def _primary_accession(entry: dict) -> str:
        for acc in entry.get('accession-list', []):
            if acc.get('type') == 'primary':
                return acc.get('value', '')
        return ''

    def _all_names(entry: dict) -> list[str]:
        return [n.get('value', '').lower() for n in entry.get('name-list', [])]

    # Exact match in name-list (identifier or synonym)
    for entry in results:
        if norm in _all_names(entry):
            accession = _primary_accession(entry)
            if accession:
                return f'RRID:{accession}'

    return ''


def _lookup_addgene(name: str) -> str:
    """Search Addgene for a plasmid by name; return RRID:Addgene_XXXXX or ''."""
    # Addgene does not have an official public JSON API, but their search endpoint
    # returns structured HTML.  We use the JSON search API they expose internally.
    params = {
        'q': name,
        'page_size': '5',
    }
    data = _get('https://www.addgene.org/api/plasmid/search/', params=params, quiet=True)
    if not data:
        return ''

    results = data.get('results', []) or []
    norm = name.lower().strip()
    for entry in results:
        plasmid_name = (entry.get('name', '') or '').lower()
        if _fuzzy_match(norm, plasmid_name):
            pid = entry.get('id') or entry.get('addgene_id', '')
            if pid:
                return f'RRID:Addgene_{pid}'
    return ''


def _lookup_imsr(name: str) -> str:
    """Search IMSR for a mouse strain by name; return RRID:IMSR_JAX:XXXXX or ''."""
    # IMSR summary endpoint returns JSON when called with the right parameters.
    params = {
        'gfAccessionIds': '',
        'strainsOnly': '1',
        'q': name,
        'type': 'json',
    }
    data = _get('https://www.findmice.org/summary', params=params, quiet=True)
    if not isinstance(data, dict):
        return ''

    strains = data.get('strains', []) or []
    norm = name.lower().strip()
    for strain in strains:
        strain_name = (strain.get('name', '') or '').lower()
        if _fuzzy_match(norm, strain_name):
            # IMSR IDs look like "JAX:000664" — convert to RRID format
            strain_id = strain.get('id', '') or ''
            if strain_id.startswith('JAX:'):
                return f'RRID:IMSR_{strain_id}'
            elif strain_id:
                return f'RRID:IMSR_{strain_id}'
    return ''


def _lookup_scicrunch_antibody(name: str, api_key: str) -> str:
    """Search SciCrunch Antibody Registry; return RRID:AB_XXXXXX or ''."""
    params = {
        'q': name,
        'type': 'Antibody',
        'key': api_key,
        'count': '5',
    }
    data = _get('https://scicrunch.org/api/1/resource/fields/search.json', params=params)
    if not data:
        return ''

    results = (data.get('data', {}) or {}).get('results', []) or []
    norm = name.lower().strip()
    for entry in results:
        entry_name = (entry.get('name', '') or '').lower()
        if _fuzzy_match(norm, entry_name):
            rid = entry.get('rid', '') or ''
            if rid:
                return f'RRID:AB_{rid}'
    return ''


def _fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    """Return True if strings are similar enough (simple token overlap)."""
    if a == b:
        return True
    # Strip common suffixes/prefixes before comparing
    a = re.sub(r'[\s\-_]+', ' ', a).strip()
    b = re.sub(r'[\s\-_]+', ' ', b).strip()
    if a == b:
        return True
    # Token overlap
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return overlap >= threshold


# ---------------------------------------------------------------------------
# Per-type dispatch
# ---------------------------------------------------------------------------

_CONTEXT_FIELDS = ('_context', 'context')  # field names to check for embedded RRIDs

_TYPE_TO_TYPED_FILE = {
    'animal_model':             'VALIDATED_animal_models.csv',
    'antibody':                 'VALIDATED_antibodies.csv',
    'cell_line':                'VALIDATED_cell_lines.csv',
    'genetic_reagent':          'VALIDATED_genetic_reagents.csv',
    'patient_derived_model':    'VALIDATED_patient_derived_models.csv',
    'advanced_cellular_model':  'VALIDATED_advanced_cellular_models.csv',
    'clinical_assessment_tool': 'VALIDATED_clinical_assessment_tools.csv',
    'computational_tool':       'VALIDATED_computational_tools.csv',
}


def _lookup_rrid(name: str, tool_type: str, context: str, api_key: str,
                 rate_limit: float) -> str:
    """Return RRID for a single resource, or '' if not found."""
    # 1. Try to extract an explicit RRID from the context text first (no network call).
    rrid = _extract_rrid_from_text(context)
    if rrid:
        return rrid

    # 2. Registry lookup by tool type.
    time.sleep(rate_limit)

    if tool_type in ('cell_line', 'patient_derived_model'):
        return _lookup_cellosaurus(name)

    if tool_type == 'genetic_reagent':
        return _lookup_addgene(name)

    if tool_type == 'animal_model':
        return _lookup_imsr(name)

    if tool_type == 'antibody' and api_key:
        return _lookup_scicrunch_antibody(name, api_key)

    return ''


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_lookup(output_dir: Path, dry_run: bool, force: bool,
               api_key: str, tool_types: list[str], rate_limit: float) -> None:
    resources_file = output_dir / 'VALIDATED_resources.csv'
    if not resources_file.exists():
        print(f'❌  {resources_file} not found')
        return

    with open(resources_file, newline='', encoding='utf-8') as f:
        res_rows = list(csv.DictReader(f))
        res_fieldnames = list(csv.DictReader(open(resources_file)).fieldnames or [])

    # Ensure rrid column exists
    if 'rrid' not in res_fieldnames:
        res_fieldnames.insert(res_fieldnames.index('synonyms') + 1 if 'synonyms' in res_fieldnames else 3, 'rrid')

    # Build lookup map from type-specific files: resourceId → context text
    context_by_id: dict[str, str] = {}
    for ttype, filename in _TYPE_TO_TYPED_FILE.items():
        typed_file = output_dir / filename
        if not typed_file.exists():
            continue
        with open(typed_file, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                rid = row.get('resourceId', '').strip()
                ctx = ' | '.join(row.get(cf, '') for cf in _CONTEXT_FIELDS if row.get(cf, ''))
                if rid and ctx:
                    context_by_id[rid] = ctx

    # Build vendorItem-derived RRID map: for resources sold by Addgene, construct
    # RRID:Addgene_{catalogNumber} directly from the vendor/vendorItem CSVs.
    rrid_from_vendor: dict[str, str] = {}
    vendor_file    = output_dir / 'VALIDATED_vendor.csv'
    vendoritem_file = output_dir / 'VALIDATED_vendorItem.csv'
    if vendor_file.exists() and vendoritem_file.exists():
        with open(vendor_file, newline='', encoding='utf-8') as f:
            vendors = {row['vendorId']: row.get('vendorName', '') for row in csv.DictReader(f)}
        with open(vendoritem_file, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                vname = vendors.get(row.get('vendorId', ''), '').lower()
                cat   = row.get('catalogNumber', '').strip()
                rid   = row.get('resourceId', '').strip()
                if rid and cat:
                    if 'addgene' in vname:
                        rrid_from_vendor[rid] = f'RRID:Addgene_{cat}'
                    elif 'jax' in vname or 'jackson' in vname:
                        rrid_from_vendor[rid] = f'RRID:IMSR_JAX:{cat}'

    total = attempted = found = skipped = 0
    for row in res_rows:
        ttype = row.get('_toolType', '').strip()
        if tool_types and ttype not in tool_types:
            continue
        total += 1

        existing_rrid = row.get('rrid', '').strip()
        if existing_rrid and not force:
            skipped += 1
            continue

        name = row.get('resourceName', '').strip()
        rid  = row.get('resourceId', '').strip()
        ctx  = context_by_id.get(rid, '')

        attempted += 1
        print(f'  [{ttype}] {name[:55]}', end=' ... ', flush=True)
        rrid = _lookup_rrid(name, ttype, ctx, api_key, rate_limit)
        # Fallback: use vendorItem-derived RRID if registry lookup failed
        if not rrid and rid in rrid_from_vendor:
            rrid = rrid_from_vendor[rid]

        if rrid:
            found += 1
            print(f'✅ {rrid}')
            if not dry_run:
                row['rrid'] = rrid
        else:
            print('—')

    print(f'\nSummary: {found}/{attempted} RRIDs found '
          f'({skipped} already filled, {total - attempted - skipped} other types skipped)')

    if dry_run:
        print('(dry-run: no files written)')
        return

    # Write updated VALIDATED_resources.csv
    with open(resources_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=res_fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(res_rows)

    # Propagate rrid back to type-specific files
    rid_to_rrid = {r['resourceId']: r['rrid'] for r in res_rows if r.get('rrid', '').strip()}
    updated_typed: list[str] = []
    for ttype, filename in _TYPE_TO_TYPED_FILE.items():
        typed_file = output_dir / filename
        if not typed_file.exists():
            continue
        with open(typed_file, newline='', encoding='utf-8') as f:
            typed_rows = list(csv.DictReader(f))
            typed_fieldnames = list(csv.DictReader(open(typed_file)).fieldnames or [])

        changed = 0
        for row in typed_rows:
            rid = row.get('resourceId', '').strip()
            if rid in rid_to_rrid:
                if 'rrid' not in typed_fieldnames:
                    typed_fieldnames.insert(1, 'rrid')
                if row.get('rrid', '') != rid_to_rrid[rid]:
                    row['rrid'] = rid_to_rrid[rid]
                    changed += 1

        if changed:
            with open(typed_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=typed_fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(typed_rows)
            updated_typed.append(f'{filename} ({changed} rows)')

    if updated_typed:
        print('Updated type-specific files:')
        for name in updated_typed:
            print(f'  {name}')

    print(f'\n✅  RRID lookup complete — {resources_file}')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Populate rrid column in VALIDATED_resources.csv from public registries.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--output-dir', default='tool_coverage/outputs',
        help='Directory containing VALIDATED_*.csv (default: tool_coverage/outputs)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print discovered RRIDs without writing any files',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Re-query even for resources that already have an rrid value',
    )
    parser.add_argument(
        '--api-key', default='',
        help='SciCrunch API key for antibody lookups '
             '(or set SCICRUNCH_API_KEY environment variable)',
    )
    parser.add_argument(
        '--tool-type', dest='tool_types', action='append', default=[],
        choices=list(_TYPE_TO_TYPED_FILE.keys()),
        help='Restrict to one tool type (can be repeated; default: all)',
    )
    parser.add_argument(
        '--rate-limit', type=float, default=0.3,
        help='Seconds to sleep between API calls (default: 0.3)',
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get('SCICRUNCH_API_KEY', '')

    output_dir = Path(args.output_dir)
    if not output_dir.is_dir():
        print(f'❌  Output directory not found: {output_dir}')
        return

    print(f'RRID lookup — output dir: {output_dir}')
    if args.dry_run:
        print('(DRY RUN — no files will be modified)')
    if not api_key:
        print('⚠️   No SciCrunch API key — antibody lookups will be skipped')
        print('    Set SCICRUNCH_API_KEY or pass --api-key to enable')
    print()

    run_lookup(
        output_dir=output_dir,
        dry_run=args.dry_run,
        force=args.force,
        api_key=api_key,
        tool_types=args.tool_types,
        rate_limit=args.rate_limit,
    )


if __name__ == '__main__':
    main()
