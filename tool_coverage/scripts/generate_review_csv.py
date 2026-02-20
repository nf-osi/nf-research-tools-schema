#!/usr/bin/env python3
"""
Post-process VALIDATED_*.csv outputs to apply quality filters and generate a
consolidated review CSV for manual inspection.

Filters applied (beyond AI verdict):
  - Computational tools: remove generic stats environments (MATLAB, R, ImageJ, etc.)
  - Computational tools: remove unnamed tools with no version AND no repo at confidence < 0.9
  - Antibodies: remove secondary antibodies (clonality = Secondary)
  - Clinical assessment tools: remove hardware devices misclassified as instruments

Outputs:
  - Updated VALIDATED_*.csv  (filtered in-place)
  - tool_coverage/outputs/review.csv            — all kept tools, sorted by priority
  - tool_coverage/outputs/review_filtered.csv   — tools removed by post-filter (for audit)

Usage:
    python generate_review_csv.py [--output-dir tool_coverage/outputs] [--dry-run]
"""

import csv
import sys
import argparse
from pathlib import Path

# ── Post-filter constants ────────────────────────────────────────────────────

# Generic stats/analysis environments — never NF-specific research tools
GENERIC_COMPUTATIONAL_TOOLS = frozenset({
    'r', 'python', 'python3', 'matlab', 'excel', 'spss', 'sas', 'stata',
    'prism', 'graphpad prism', 'graphpad', 'graphpad prism 7', 'graphpad prism 8',
    'graphpad prism 9', 'graphpad prism 10',
    'imagej', 'fiji', 'image j', 'imagej (fiji)', 'imagej (fiji, nih)',
    'imagej (nih)', 'imagej software', 'image j (nih)', 'imagej (rasband)',
    'imageJ (rasband ws. imagej, u.s. national institutes of health)',
    'imageJ (u.s. national institutes of health)',
})

# Hardware/devices incorrectly classified as clinical assessment instruments
HARDWARE_CLINICAL_PATTERNS = (
    'microscope', 'digital camera', 'camera', 'apple watch', 'smartwatch',
    'wearable', 'eeg device', 'eeg system', 'mri scanner', 'pet scanner',
    'ct scanner', 'sequencer', 'flow cytometer', 'facs', 'patch clamp',
)

# ── Critical fields per type (used for completeness scoring) ─────────────────

CRITICAL_FIELDS: dict[str, list[str]] = {
    'animal_models':             ['strainNomenclature', 'animalModelGeneticDisorder'],
    'antibodies':                ['targetAntigen', 'hostOrganism', 'clonality'],
    'cell_lines':                ['_toolName', 'organ', 'cellLineGeneticDisorder'],
    'genetic_reagents':          ['insertName', 'vectorType'],
    'computational_tools':       ['softwareName', 'softwareType'],
    'advanced_cellular_models':  ['_toolName', 'modelType', 'derivationSource'],
    'patient_derived_models':    ['_toolName', 'modelSystemType', 'patientDiagnosis'],
    'clinical_assessment_tools': ['assessmentName', 'assessmentType', 'targetPopulation', 'diseaseSpecific'],
}

# Primary name column per type
NAME_COLUMN: dict[str, str] = {
    'animal_models':             'strainNomenclature',
    'antibodies':                'targetAntigen',
    'cell_lines':                '_toolName',
    'genetic_reagents':          'insertName',
    'computational_tools':       'softwareName',
    'advanced_cellular_models':  '_toolName',
    'patient_derived_models':    '_toolName',
    'clinical_assessment_tools': 'assessmentName',
    'resources':                 'resourceName',
}

# ── Scoring helpers ───────────────────────────────────────────────────────────

def _is_nf_specific(row: dict, tool_type: str) -> bool:
    """Return True if the tool is specifically linked to NF research."""
    if tool_type == 'animal_models':
        d = row.get('animalModelGeneticDisorder', '').strip()
        return d not in ('', 'No known disease')
    if tool_type == 'cell_lines':
        d = row.get('cellLineGeneticDisorder', '').strip()
        return d not in ('', 'None', 'none')
    if tool_type == 'clinical_assessment_tools':
        return row.get('diseaseSpecific', '').strip() == 'Yes'
    if tool_type == 'genetic_reagents':
        insert = row.get('insertName', '').lower()
        return any(k in insert for k in ('nf1', 'nf2', 'lztr1', 'smarcb1', 'merlin', 'neurofibromin'))
    if tool_type == 'patient_derived_models':
        diag = row.get('patientDiagnosis', '').lower()
        return any(k in diag for k in ('nf1', 'nf2', 'neurofibromatosis', 'schwannomatosis', 'mpnst', 'neurofibroma'))
    if tool_type == 'advanced_cellular_models':
        ctx = (row.get('_context', '') + row.get('_toolName', '')).lower()
        return any(k in ctx for k in ('nf1', 'nf2', 'neurofibromatosis', 'schwannoma', 'neurofibroma'))
    # antibodies, computational_tools, resources: included by default (used in NF-focused publications)
    return True


def _completeness_score(row: dict, tool_type: str) -> float:
    """Return fraction of critical fields that are non-empty."""
    critical = CRITICAL_FIELDS.get(tool_type, [])
    if not critical:
        return 1.0
    # For computational tools, version OR repo counts as one additional critical field
    filled = sum(
        1 for f in critical
        if row.get(f, '').strip() not in ('', 'None', 'Unknown')
    )
    if tool_type == 'computational_tools':
        has_id = bool(row.get('softwareVersion', '').strip() or row.get('sourceRepository', '').strip())
        return (filled + (1 if has_id else 0)) / (len(critical) + 1)
    return filled / len(critical)


def _priority(nf_specific: bool, completeness: float, confidence: float) -> str:
    if nf_specific and completeness >= 0.67 and confidence >= 0.85:
        return 'High'
    if (nf_specific or completeness >= 0.67) and confidence >= 0.8:
        return 'Medium'
    return 'Low'


# ── Post-filter logic ─────────────────────────────────────────────────────────

def _should_post_filter(row: dict, tool_type: str) -> tuple[bool, str]:
    """Return (remove, reason) — additional quality gate beyond AI verdict."""
    confidence = float(row.get('_confidence', 0) or 0)

    if tool_type == 'computational_tools':
        name = row.get('softwareName', '').strip()
        if name.lower() in GENERIC_COMPUTATIONAL_TOOLS:
            return True, f"Generic stats/analysis environment: {name}"
        has_version = bool(row.get('softwareVersion', '').strip())
        has_repo = bool(row.get('sourceRepository', '').strip())
        if not has_version and not has_repo and confidence < 0.9:
            return True, "No version and no repository URL (confidence < 0.9 — unidentifiable)"

    elif tool_type == 'antibodies':
        if row.get('clonality', '').strip() == 'Secondary':
            return True, "Secondary antibody (not an NF-specific research tool)"

    elif tool_type == 'clinical_assessment_tools':
        name = row.get('assessmentName', '').strip().lower()
        if any(p in name for p in HARDWARE_CLINICAL_PATTERNS):
            return True, "Hardware device, not a clinical assessment instrument"

    return False, ''


# ── Review CSV columns ────────────────────────────────────────────────────────

REVIEW_FIELDS = [
    # Identity
    'toolName', 'toolType',
    # Publication
    '_pmid', '_doi', '_publicationTitle', '_year',
    # Quality metrics
    '_confidence', '_usageType', 'nf_specific', 'completeness_score', 'priority',
    # Animal model
    'strainNomenclature', 'animalModelGeneticDisorder', 'animalModelOfManifestation',
    # Antibody
    'targetAntigen', 'hostOrganism', 'clonality',
    # Cell line
    'organ', 'cellLineGeneticDisorder', 'cellLineManifestation', 'cellLineCategory',
    # Genetic reagent
    'insertName', 'vectorType', 'vectorBackbone', 'promoter',
    # Computational tool
    'softwareName', 'softwareType', 'softwareVersion', 'sourceRepository',
    # Advanced cellular model
    'modelType', 'derivationSource', 'cellTypes', 'organoidType',
    # Patient-derived model
    'modelSystemType', 'patientDiagnosis', 'hostStrain', 'tumorType',
    # Clinical assessment tool
    'assessmentName', 'assessmentType', 'targetPopulation', 'diseaseSpecific', 'numberOfItems',
    # Context
    '_context',
]

REVIEW_FILTERED_FIELDS = REVIEW_FIELDS + ['filter_reason']


def _get_tool_name(row: dict, tool_type: str) -> str:
    col = NAME_COLUMN.get(tool_type, '')
    return row.get(col, '').strip() if col else ''


def _make_review_row(row: dict, tool_type: str, nf_specific: bool,
                     completeness: float, priority: str) -> dict:
    tool_name = _get_tool_name(row, tool_type)
    d: dict = {'toolName': tool_name, 'toolType': tool_type}
    for f in REVIEW_FIELDS:
        if f not in ('toolName', 'toolType'):
            d[f] = row.get(f, '')
    # Override computed fields
    d['nf_specific'] = nf_specific
    d['completeness_score'] = f"{completeness:.2f}"
    d['priority'] = priority
    return d


# ── Main processing ───────────────────────────────────────────────────────────

def process(output_dir: str, dry_run: bool = False) -> None:
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"❌ Output directory not found: {output_dir}")
        sys.exit(1)

    validated_files = sorted(output_path.glob('VALIDATED_*.csv'))
    if not validated_files:
        print(f"❌ No VALIDATED_*.csv files found in {output_dir}")
        sys.exit(1)

    all_review_rows: list[dict] = []
    all_filtered_rows: list[dict] = []
    stats: dict = {}

    _PRIORITY_ORDER = {'High': 0, 'Medium': 1, 'Low': 2}

    for validated_file in validated_files:
        tool_type = validated_file.stem.replace('VALIDATED_', '')
        if tool_type == 'resources':
            continue  # resources table has no per-tool metadata to score

        print(f"\n{'='*60}")
        print(f"Processing {validated_file.name}")

        try:
            with open(validated_file, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = list(reader.fieldnames or [])
        except Exception as e:
            print(f"  ❌ Error reading: {e}")
            continue

        kept: list[dict] = []
        filtered: list[dict] = []

        for row in rows:
            remove, reason = _should_post_filter(row, tool_type)
            if remove:
                row['filter_reason'] = reason
                filtered.append(row)
                print(f"  🗑  {_get_tool_name(row, tool_type)[:60]} — {reason}")
            else:
                kept.append(row)
                nf = _is_nf_specific(row, tool_type)
                comp = _completeness_score(row, tool_type)
                conf = float(row.get('_confidence', 0) or 0)
                pri = _priority(nf, comp, conf)
                all_review_rows.append(_make_review_row(row, tool_type, nf, comp, pri))

            if remove and filtered:  # only add first instance of filter log
                pass  # already printed above

        # Collect filtered rows for audit CSV
        for row in filtered:
            nf = _is_nf_specific(row, tool_type)
            comp = _completeness_score(row, tool_type)
            conf = float(row.get('_confidence', 0) or 0)
            pri = _priority(nf, comp, conf)
            fr = _make_review_row(row, tool_type, nf, comp, pri)
            fr['filter_reason'] = row.get('filter_reason', '')
            all_filtered_rows.append(fr)

        stats[tool_type] = {
            'original': len(rows),
            'kept': len(kept),
            'filtered': len(filtered),
        }

        if not dry_run and kept:
            with open(validated_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(kept)
            print(f"  ✅ {len(kept)} kept, {len(filtered)} removed → {validated_file.name}")
        elif dry_run:
            print(f"  [DRY-RUN] {len(kept)} would be kept, {len(filtered)} would be removed")
        else:
            print(f"  ⚠️  All {len(rows)} rows filtered — leaving original file unchanged")

    # Sort review rows: High priority first, then confidence desc, then completeness desc
    all_review_rows.sort(key=lambda r: (
        _PRIORITY_ORDER.get(r['priority'], 3),
        -float(r.get('_confidence', 0) or 0),
        -float(r.get('completeness_score', 0) or 0),
    ))

    # Write review.csv
    review_file = output_path / 'review.csv'
    if not dry_run:
        with open(review_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=REVIEW_FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_review_rows)
        high = sum(1 for r in all_review_rows if r['priority'] == 'High')
        med  = sum(1 for r in all_review_rows if r['priority'] == 'Medium')
        low  = sum(1 for r in all_review_rows if r['priority'] == 'Low')
        print(f"\n✅ review.csv: {len(all_review_rows)} tools  (High={high}, Medium={med}, Low={low})")
        print(f"   → {review_file}")
    else:
        print(f"\n[DRY-RUN] review.csv would contain {len(all_review_rows)} tools")

    # Write review_filtered.csv (audit trail)
    if all_filtered_rows and not dry_run:
        filtered_file = output_path / 'review_filtered.csv'
        with open(filtered_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=REVIEW_FILTERED_FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_filtered_rows)
        print(f"🗑  review_filtered.csv: {len(all_filtered_rows)} post-filtered tools (audit trail)")
        print(f"   → {filtered_file}")

    # Summary
    print(f"\n{'='*60}")
    print("Post-filter summary")
    print(f"{'='*60}")
    total_in = total_out = total_removed = 0
    for t, s in stats.items():
        total_in += s['original']
        total_out += s['kept']
        total_removed += s['filtered']
        if s['filtered']:
            print(f"  {t:<30} {s['original']:>4} → {s['kept']:>4}  (-{s['filtered']})")
        else:
            print(f"  {t:<30} {s['original']:>4} → {s['kept']:>4}")
    print(f"  {'TOTAL':<30} {total_in:>4} → {total_out:>4}  (-{total_removed})")

    if dry_run:
        print("\n[DRY-RUN] No files were modified.")
        return

    print(f"\nNF-specific breakdown in review.csv:")
    nf_types: dict = {}
    for r in all_review_rows:
        tt = r['toolType']
        nf_types.setdefault(tt, {'nf': 0, 'total': 0})
        nf_types[tt]['total'] += 1
        if r.get('nf_specific') is True:
            nf_types[tt]['nf'] += 1
    for tt, c in sorted(nf_types.items()):
        pct = 100 * c['nf'] / c['total'] if c['total'] else 0
        print(f"  {tt:<30} {c['nf']:>4}/{c['total']:<4} NF-specific ({pct:.0f}%)")

    # Generate publication link CSVs from the (now-filtered) review rows
    _write_publication_link_csvs(all_review_rows, output_path)


def _write_publication_link_csvs(review_rows: list[dict], output_path: Path) -> None:
    """Generate SUBMIT_publications.csv, SUBMIT_usage.csv, SUBMIT_development.csv.

    Reads publication metadata from processed_publications.csv (if available) or
    falls back to the tool_reviews/publication_cache/ JSON files.

    Maps to three Synapse tables in NF Research Tools Central (syn26338068):
      - Publication  syn26486839  one row per unique publication
      - Usage        syn26486841  (publicationId × resourceId) for tools used in a pub
      - Development  syn26486807  (resourceId × publicationId) for tools developed in a pub

    ID columns (publicationId, resourceId, usageId, developmentId) are left blank;
    they are Synapse-assigned UUIDs resolved at upsert time.
    """
    print(f"\n{'='*60}")
    print("Generating publication link CSVs")
    print(f"{'='*60}")

    # Load publication metadata from processed_publications.csv
    # Check output_path first (collocated), fall back to the default outputs dir
    pub_meta: dict = {}
    processed_csv = output_path / 'processed_publications.csv'
    if not processed_csv.exists():
        processed_csv = Path('tool_coverage/outputs/processed_publications.csv')
    if processed_csv.exists():
        with open(processed_csv, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                pmid = row.get('pmid', '').strip()
                if pmid:
                    pub_meta[pmid] = row
        print(f"  Loaded metadata for {len(pub_meta)} publications from processed_publications.csv")
    else:
        # Fall back to publication cache JSON files
        cache_dir = Path('tool_reviews/publication_cache')
        if cache_dir.exists():
            import json
            for cache_file in cache_dir.glob('*_text.json'):
                try:
                    with open(cache_file) as f:
                        c = json.load(f)
                    pmid = c.get('pmid', '').strip()
                    if pmid:
                        pub_meta[pmid] = c
                except Exception:
                    pass
            print(f"  Loaded metadata for {len(pub_meta)} publications from cache JSON files")
        else:
            print("  ⚠️  No processed_publications.csv or publication cache found; "
                  "publication metadata will be minimal")

    # First pass: collect all link rows and minimal pub metadata
    # We do NOT build pub_rows yet — a publication only gets a row if it has
    # at least one usage or development link (prevents orphan publications).
    usage_rows: list = []
    dev_rows: list = []
    all_pmid_info: dict = {}  # pmid → {doi, title, year}

    for r in review_rows:
        pmid = r.get('_pmid', '').strip()
        doi = r.get('_doi', '').strip()
        title = r.get('_publicationTitle', '').strip()
        year = r.get('_year', '').strip()
        usage_type = r.get('_usageType', '').strip()
        tool_name = r.get('toolName', '').strip()
        tool_type = r.get('toolType', '').strip()

        if not pmid:
            continue

        # Cache the first-seen metadata for this PMID (used later for pub_rows)
        if pmid not in all_pmid_info:
            all_pmid_info[pmid] = {'doi': doi, 'title': title, 'year': year}

        if not tool_name:
            continue

        link_row = {
            '_pmid':             pmid,
            '_doi':              doi,
            '_publicationTitle': title,
            '_year':             year,
            '_toolName':         tool_name,
            '_toolType':         tool_type,
            '_usageType':        usage_type,
            'publicationId':     '',   # resolved at upsert from pmid
            'resourceId':        '',   # resolved at upsert from toolName+toolType
        }

        if usage_type == 'Development':
            dev_rows.append({**link_row, 'developmentId': ''})
            # Also a usage link for development papers (tool was used here too)
            usage_rows.append({**link_row, 'usageId': ''})
        elif usage_type == 'Experimental Usage':
            usage_rows.append({**link_row, 'usageId': ''})
        # Citation Only / empty usageType → no link rows → publication excluded

    # Second pass: build pub_rows only for PMIDs that appear in at least one link table
    linked_pmids = {r['_pmid'] for r in usage_rows} | {r['_pmid'] for r in dev_rows}
    orphan_pmids = set(all_pmid_info.keys()) - linked_pmids
    if orphan_pmids:
        print(f"  ℹ️  {len(orphan_pmids)} publications excluded (no usage/development links): "
              f"{', '.join(sorted(orphan_pmids)[:5])}"
              + (' ...' if len(orphan_pmids) > 5 else ''))

    pub_rows: list = []
    for pmid in sorted(linked_pmids):
        meta = pub_meta.get(pmid, {})
        info = all_pmid_info.get(pmid, {})
        authors_raw = meta.get('authors', '')
        if isinstance(authors_raw, list):
            authors_raw = ', '.join(authors_raw)
        pub_rows.append({
            # Synapse Publication table (syn26486839) columns
            'doi':              info.get('doi', '') or meta.get('doi', ''),
            'pmid':             pmid,
            'publicationTitle': info.get('title', '') or meta.get('title', ''),
            'abstract':         meta.get('abstract', ''),
            'journal':          meta.get('journal', ''),
            'publicationDate':  meta.get('publicationDate', ''),
            'authors':          authors_raw,
        })
        # Citation Only and Not Found are not linked

    # Write files
    if pub_rows:
        pub_fields = ['doi', 'pmid', 'publicationTitle', 'abstract',
                      'journal', 'publicationDate', 'authors']
        with open(output_path / 'SUBMIT_publications.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=pub_fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(pub_rows)
        print(f"  ✅ SUBMIT_publications.csv: {len(pub_rows)} unique publications")

    if usage_rows:
        usage_fields = ['_pmid', '_doi', '_publicationTitle', '_year',
                        '_toolName', '_toolType', '_usageType',
                        'publicationId', 'resourceId', 'usageId']
        with open(output_path / 'SUBMIT_usage.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=usage_fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(usage_rows)
        print(f"  ✅ SUBMIT_usage.csv: {len(usage_rows)} publication-tool usage links")

    if dev_rows:
        dev_fields = ['_pmid', '_doi', '_publicationTitle', '_year',
                      '_toolName', '_toolType', '_usageType',
                      'publicationId', 'resourceId', 'developmentId']
        with open(output_path / 'SUBMIT_development.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=dev_fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(dev_rows)
        print(f"  ✅ SUBMIT_development.csv: {len(dev_rows)} publication-tool development links")

    if not pub_rows:
        print("  ⚠️  No publication link data — check that _usageType is populated in VALIDATED_*.csv")

    # Summarise publication roles
    if pub_rows:
        dev_pmids = {r['_pmid'] for r in dev_rows}
        usage_only_pmids = {r['_pmid'] for r in usage_rows} - dev_pmids
        mixed_pmids = dev_pmids & {r['_pmid'] for r in usage_rows}
        print(f"\n  Publication roles:")
        print(f"    Development (tool created here): {len(dev_pmids)}")
        print(f"    Usage only (tool used here):     {len(usage_only_pmids)}")
        print(f"    Mixed (both usage + development): {len(mixed_pmids)}")
        print(f"    ⚠️  publicationId/resourceId columns are blank — resolve at upsert time")


def main():
    parser = argparse.ArgumentParser(description='Post-filter VALIDATED_*.csv and generate review.csv')
    parser.add_argument('--output-dir', default='tool_coverage/outputs',
                        help='Directory containing VALIDATED_*.csv files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without modifying any files')
    args = parser.parse_args()
    process(args.output_dir, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
