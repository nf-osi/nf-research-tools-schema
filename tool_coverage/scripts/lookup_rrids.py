#!/usr/bin/env python3
"""lookup_rrids.py — Fill blank `rrid` fields in submission JSONs.

Takes submissions/{type}/*.json paths (as written by format_mining_as_submissions.py
or process_formspark_export.py), queries public registries by tool name for each
file whose rrid is blank, and writes the RRID back into the JSON
(basicInfo.rrid when the file has a basicInfo block, else top-level rrid).
compile_accepted_submissions.py carries that value onto the detail row, so it
reaches Synapse when upsert-tools.yml uploads the submission.

Registries used (all public, no API key required by default):
  cell_line / patient_derived_model
      → Cellosaurus REST API  https://api.cellosaurus.org/
        Returns rrid:CVCL_XXXX
  genetic_reagent
      → Addgene search  https://www.addgene.org/search/catalog/plasmids/
        Returns rrid:Addgene_XXXXX
  animal_model
      → IMSR (International Mouse Strain Resource)
          https://www.findmice.org/summary?gfAccessionIds=&strainsOnly=1&q=
        Returns rrid:IMSR_JAX:XXXXX  (Jackson Laboratory strains)
        Falls back to MMRRC directly (https://api.mmrrc.org, public getCatalog
        endpoint) when IMSR has no match — needed for KOMP-derived strains
        deposited at MMRRC that IMSR's index doesn't always pick up.
        Returns rrid:MMRRC_XXXXXX-CENTER
  antibody
      → SciCrunch Antibody Registry (requires --api-key or SCICRUNCH_API_KEY)
        Returns rrid:AB_XXXXXX

For any tool type, if the context already contains an explicit RRID: string it
is extracted directly without a network call (normalized to lowercase rrid: prefix).

RRIDs use the repo convention: lowercase rrid: prefix, accession case kept
(e.g. rrid:CVCL_0031). Registry errors and timeouts are non-fatal: the file is
left unchanged and the script still exits 0.

Usage:
  python tool_coverage/scripts/lookup_rrids.py submissions/cell_lines/*.json
  python tool_coverage/scripts/lookup_rrids.py --files-list new_submissions.txt
  python tool_coverage/scripts/lookup_rrids.py --dry-run FILE...
  python tool_coverage/scripts/lookup_rrids.py --force FILE...      # re-query even if rrid filled
  python tool_coverage/scripts/lookup_rrids.py --api-key KEY FILE... # SciCrunch key for antibodies
  python tool_coverage/scripts/lookup_rrids.py --mmrrc-cache mmrrc.json FILE...  # reuse MMRRC catalog
  python tool_coverage/scripts/lookup_rrids.py --summary-md rrids.md FILE...     # markdown for PR body
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compile_accepted_submissions import (  # noqa: E402
    _resource_name_from_data,
    _tool_type_from_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RRID_IN_TEXT_RE = re.compile(r'RRID:\s*([A-Za-z0-9_:\-]+)', re.IGNORECASE)


# Registry prefixes an RRID may carry for each tool type. A publication context
# snippet often names several tools, so an RRID is only taken from it when its
# registry fits the tool being looked up.
_RRID_PREFIXES_BY_TYPE = {
    'cell_line':             ('CVCL_',),
    'patient_derived_model': ('CVCL_',),
    'antibody':              ('AB_',),
    'genetic_reagent':       ('Addgene_',),
    'animal_model':          ('IMSR_', 'MMRRC_', 'ZFIN_', 'ZDB-', 'RGD_', 'BDSC_',
                              'WB-STRAIN', 'NXR_', 'Xenbase', 'MGI'),
}


def _extract_rrid_from_text(text: str, tool_type: str | None = None) -> str:
    """Return the first RRID:XXXX string found in text (restricted to registries
    that fit tool_type, when given), or ''."""
    prefixes = _RRID_PREFIXES_BY_TYPE.get(tool_type or '', ())
    for m in _RRID_IN_TEXT_RE.finditer(text or ''):
        acc = m.group(1).rstrip(':-')
        if tool_type is None or acc.lower().startswith(tuple(p.lower() for p in prefixes)):
            return f'rrid:{acc}'
    return ''


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
                return f'rrid:{accession}'

    return ''


def _lookup_addgene(name: str) -> str:
    """Search Addgene for a plasmid by name; return rrid:Addgene_XXXXX or ''."""
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
                return f'rrid:Addgene_{pid}'
    return ''


def _lookup_imsr(name: str) -> str:
    """Search IMSR for a mouse strain by name; return rrid:IMSR_JAX:XXXXX or ''."""
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
                return f'rrid:IMSR_{strain_id}'
            elif strain_id:
                return f'rrid:IMSR_{strain_id}'
    return ''


_MMRRC_CATALOG_CACHE: dict[str, dict] | None = None
_MMRRC_WORKERS = 6  # concurrent page requests; modest, it's a public API
_MMRRC_CACHE_FILE: Path | None = None  # set by --mmrrc-cache; read/written as JSON
_MMRRC_MAX_PAGES = 800  # catalog empties out around page ~650-700 (checked live); safety cap
                         # in case pagination never terminates. ~65-70k strains total, so the
                         # first animal_model lookup in a run is slow (one-time full fetch,
                         # cached for the rest of the run) — acceptable for this periodic script.


def _fetch_mmrrc_catalog() -> dict[str, dict]:
    """Fetch and cache the full MMRRC catalog (public getCatalog endpoint), keyed by
    lowercased strain_name. Paginates 100 entries at a time until a page comes back
    empty. Fetched once per script run and reused for every animal_model lookup,
    since the public API has no by-name search endpoint (only by-page or by-id).
    """
    global _MMRRC_CATALOG_CACHE
    if _MMRRC_CATALOG_CACHE is not None:
        return _MMRRC_CATALOG_CACHE

    if _MMRRC_CACHE_FILE and _MMRRC_CACHE_FILE.exists():
        try:
            _MMRRC_CATALOG_CACHE = json.loads(_MMRRC_CACHE_FILE.read_text())
            print(f'    (MMRRC catalog: {len(_MMRRC_CATALOG_CACHE)} names from {_MMRRC_CACHE_FILE})')
            return _MMRRC_CATALOG_CACHE
        except (OSError, ValueError) as exc:
            print(f'    ⚠️  ignoring unreadable MMRRC cache {_MMRRC_CACHE_FILE}: {exc}')

    # Each page takes ~3s, so fetching ~650 pages one by one is ~35 min. Fetch a
    # small batch of pages concurrently and stop at the first batch that has an
    # empty page (end of catalog) or a failed one (outage; don't keep hammering).
    from concurrent.futures import ThreadPoolExecutor

    def _page(n: int):
        return _get(f'https://api.mmrrc.org/api/v1/catalog/getCatalog/{n}',
                    timeout=30, quiet=True)

    catalog: dict[str, dict] = {}
    page = 1  # API is 1-indexed; page 0 returns a "too big/small" error
    done = failed = False
    with ThreadPoolExecutor(max_workers=_MMRRC_WORKERS) as pool:
        while page <= _MMRRC_MAX_PAGES and not done:
            batch = list(range(page, min(page + _MMRRC_WORKERS, _MMRRC_MAX_PAGES + 1)))
            for data in pool.map(_page, batch):  # in page order
                if not isinstance(data, list):
                    failed = done = True  # error/timeout: catalog is incomplete
                    break
                if not data:
                    done = True  # past the last page
                    break
                for entry in data:
                    strain_name = re.sub(r"\s+", " ", (entry.get('strain_name') or '').strip().lower())
                    if strain_name:
                        catalog[strain_name] = entry
                    published_name = re.sub(r"\s+", " ", (entry.get('published_name') or '').strip().lower())
                    if published_name:
                        catalog.setdefault(published_name, entry)
            page += len(batch)
    print(f'    (MMRRC catalog: fetched {len(catalog)} names'
          f'{", incomplete — not cached" if failed else ""})', end=' ', flush=True)

    _MMRRC_CATALOG_CACHE = catalog
    # Only persist a complete catalog, so an MMRRC outage or a dropped page isn't
    # cached for the month as "no such strain".
    if _MMRRC_CACHE_FILE and catalog and not failed:
        try:
            _MMRRC_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _MMRRC_CACHE_FILE.write_text(json.dumps(catalog))
        except OSError as exc:
            print(f'    ⚠️  could not write MMRRC cache {_MMRRC_CACHE_FILE}: {exc}')
    return catalog


def _lookup_mmrrc(name: str) -> str:
    """Search the cached MMRRC catalog for a mouse strain by name; return
    rrid:MMRRC_XXXXXX-<center> (e.g. rrid:MMRRC_000001-UNC) or ''.

    MMRRC's public REST API (https://api.mmrrc.org/files/MMRRC_API.pdf) only
    supports by-page (getCatalog) or by-id (getCatalogEntry/getStrain) lookups,
    not by-name search, so the full catalog is cached in memory (see
    _fetch_mmrrc_catalog) and matched against here. Each catalog entry already
    carries its own "rrid" field (e.g. "RRID:MMRRC_000001-UNC"), so it's used
    directly rather than reconstructed from mmrrc_id/center_id.
    """
    catalog = _fetch_mmrrc_catalog()
    if not catalog:
        return ''

    # Exact (case/whitespace-insensitive) match only. A fuzzy fallback across
    # ~65k strain names returned the first token-overlap hit, which risks
    # assigning another strain's RRID.
    entry = catalog.get(re.sub(r"\s+", " ", name.lower().strip()))
    if not entry:
        return ''

    # Catalog gives "RRID:MMRRC_000001-UNC"; repo convention lowercases only the
    # prefix (rrid:CVCL_..., rrid:IMSR_JAX:...), keeping the accession's case.
    rrid = (entry.get('rrid') or '').strip()
    return re.sub(r'^rrid:', 'rrid:', rrid, flags=re.IGNORECASE) if rrid else ''


def _lookup_scicrunch_antibody(name: str, api_key: str) -> str:
    """Search SciCrunch Antibody Registry; return rrid:AB_XXXXXX or ''."""
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
                return f'rrid:AB_{rid}'
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

TOOL_TYPES = (
    'animal_model', 'antibody', 'cell_line', 'genetic_reagent', 'patient_derived_model',
    'organoid_protocol', 'clinical_assessment_tool', 'computational_tool',
)


def _lookup_rrid(name: str, tool_type: str, context: str, api_key: str,
                 rate_limit: float) -> tuple[str, str]:
    """Return (rrid, source) for a single resource, or ('', '') if not found."""
    # 1. Explicit RRID in the publication context text (no network call).
    rrid = _extract_rrid_from_text(context, tool_type)
    if rrid:
        return rrid, 'context'

    # 2. Registry lookup by tool type.
    if tool_type in ('cell_line', 'patient_derived_model'):
        time.sleep(rate_limit)
        return _tagged(_lookup_cellosaurus(name), 'Cellosaurus')

    if tool_type == 'genetic_reagent':
        time.sleep(rate_limit)
        return _tagged(_lookup_addgene(name), 'Addgene')

    if tool_type == 'animal_model':
        # IMSR aggregates across repositories (JAX, MMRRC, EMMA, ...) but its index
        # of MMRRC-held strains isn't always complete/matched (see nf-osi/nf-research-
        # tools-schema#169 — KOMP-derived mice sent to MMRRC weren't found via IMSR).
        # Query MMRRC directly as a fallback when IMSR comes up empty.
        time.sleep(rate_limit)
        rrid = _lookup_imsr(name)
        if rrid:
            return rrid, 'IMSR'
        return _tagged(_lookup_mmrrc(name), 'MMRRC')

    if tool_type == 'antibody' and api_key:
        time.sleep(rate_limit)
        return _tagged(_lookup_scicrunch_antibody(name, api_key), 'SciCrunch')

    return '', ''


def _tagged(rrid: str, source: str) -> tuple[str, str]:
    return (rrid, source) if rrid else ('', '')


# ---------------------------------------------------------------------------
# Submission JSON handling
# ---------------------------------------------------------------------------

def _submission_name(data: dict, ttype: str) -> str:
    name = _resource_name_from_data(data, ttype).strip()
    # Mined patient_derived_model/organoid JSONs carry the name in
    # basicInfo.modelName, which _resource_name_from_data doesn't read; a PDM
    # then comes back as just " (suffix)" or "".
    bi = data.get('basicInfo') or {}
    model_name = (bi.get('modelName') or '').strip() if isinstance(bi, dict) else ''
    if model_name and (not name or name.startswith('(')):
        return model_name
    return name


def _existing_rrid(data: dict) -> str:
    bi = data.get('basicInfo')
    if isinstance(bi, dict) and str(bi.get('rrid') or '').strip():
        return str(bi['rrid']).strip()
    return str(data.get('rrid') or '').strip()


def _set_rrid(data: dict, rrid: str) -> None:
    bi = data.get('basicInfo')
    if isinstance(bi, dict):
        bi['rrid'] = rrid
    else:
        data['rrid'] = rrid


def _context_text(data: dict) -> str:
    parts = [data.get('_context') or '']
    for pub in data.get('_publications') or []:
        if isinstance(pub, dict):
            parts.append(pub.get('_context') or '')
    return ' | '.join(p for p in parts if p)


def _is_observation_path(path: Path) -> bool:
    return 'observations' in path.parts


def run_lookup(paths: list[Path], dry_run: bool = False, force: bool = False,
               api_key: str = '', rate_limit: float = 0.3) -> list[dict]:
    """Fill blank rrids in the given submission JSONs. Returns one result dict
    per tool file looked at: {path, name, toolType, rrid, source, status}, where
    status is 'filled', 'not_found', 'already_set', 'skipped' or 'error'."""
    results: list[dict] = []
    for path in paths:
        if path.suffix != '.json' or _is_observation_path(path):
            continue
        res = {'path': str(path), 'name': '', 'toolType': '', 'rrid': '', 'source': '',
               'status': 'skipped'}
        results.append(res)
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            print(f'  ⚠️  {path}: unreadable ({exc})')
            res['status'] = 'error'
            continue
        if not isinstance(data, dict):
            continue

        ttype = _tool_type_from_json(data) or ''
        res['toolType'] = ttype
        if ttype not in TOOL_TYPES:
            continue
        name = _submission_name(data, ttype)
        res['name'] = name

        existing = _existing_rrid(data)
        if existing and not force:
            res['status'] = 'already_set'
            res['rrid'] = existing
            continue
        if not name:
            continue

        print(f'  [{ttype}] {name[:55]}', end=' ... ', flush=True)
        try:
            rrid, source = _lookup_rrid(name, ttype, _context_text(data), api_key, rate_limit)
        except Exception as exc:  # registry quirks must never fail the mining run
            print(f'⚠️  {exc}')
            res['status'] = 'error'
            continue

        if not rrid:
            print('—')
            res['status'] = 'not_found'
            continue

        print(f'✅ {rrid} ({source})')
        res.update(rrid=rrid, source=source, status='filled')
        if not dry_run:
            _set_rrid(data, rrid)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n',
                            encoding='utf-8')
    return results


def summarize(results: list[dict]) -> str:
    counts = {s: sum(r['status'] == s for r in results)
              for s in ('filled', 'not_found', 'already_set', 'error', 'skipped')}
    return (f"{counts['filled']} filled, {counts['not_found']} not found, "
            f"{counts['already_set']} already set, {counts['error']} errors, "
            f"{counts['skipped']} skipped (type without registry / no name)")


def summary_markdown(results: list[dict]) -> str:
    filled = [r for r in results if r['status'] == 'filled']
    lines = ['### RRIDs filled by registry lookup', '']
    if not filled:
        lines.append('_No RRIDs were filled automatically._')
        return '\n'.join(lines) + '\n'
    lines += [
        f'{len(filled)} submission(s) got an `rrid` from a registry name match. '
        'Check each one is the right strain/line — a wrong RRID is worse than a blank one; '
        'clear the field in the JSON if it is not.',
        '',
        '| Tool | Type | RRID | Source | File |',
        '|---|---|---|---|---|',
    ]
    for r in sorted(filled, key=lambda r: (r['toolType'], r['name'].lower())):
        lines.append(f"| {r['name']} | {r['toolType']} | `{r['rrid']}` | {r['source']} "
                     f"| `{r['path']}` |")
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Fill blank rrid fields in submission JSONs from public registries.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('files', nargs='*', help='submissions/{type}/*.json paths')
    parser.add_argument('--files-list', help='File with one submission JSON path per line')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print discovered RRIDs without writing any files')
    parser.add_argument('--force', action='store_true',
                        help='Re-query even for submissions that already have an rrid')
    parser.add_argument('--api-key', default='',
                        help='SciCrunch API key for antibody lookups '
                             '(or set SCICRUNCH_API_KEY environment variable)')
    parser.add_argument('--rate-limit', type=float, default=0.3,
                        help='Seconds to sleep between API calls (default: 0.3)')
    parser.add_argument('--mmrrc-cache', default='',
                        help='JSON file to read the MMRRC catalog from / write it to, '
                             'so the ~650-page fetch happens at most once')
    parser.add_argument('--summary-md', default='',
                        help='Write a markdown table of filled RRIDs here (for the PR body)')
    args = parser.parse_args(argv)

    global _MMRRC_CACHE_FILE
    _MMRRC_CACHE_FILE = Path(args.mmrrc_cache) if args.mmrrc_cache else None

    paths = [Path(f) for f in args.files]
    if args.files_list:
        paths += [Path(line.strip()) for line in Path(args.files_list).read_text().splitlines()
                  if line.strip()]

    api_key = args.api_key or os.environ.get('SCICRUNCH_API_KEY', '')
    print(f'RRID lookup — {len(paths)} file(s)')
    if args.dry_run:
        print('(DRY RUN — no files will be modified)')
    if not api_key:
        print('⚠️   No SciCrunch API key — antibody lookups will be skipped')

    results = run_lookup(paths, dry_run=args.dry_run, force=args.force,
                         api_key=api_key, rate_limit=args.rate_limit)
    print(f'\nSummary: {summarize(results)}')
    if args.summary_md:
        Path(args.summary_md).write_text(summary_markdown(results), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
