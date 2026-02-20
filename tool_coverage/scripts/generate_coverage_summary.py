#!/usr/bin/env python3
"""
Generate a summary report for GitHub Pull Request based on Sonnet validation results.
Reads from tool_coverage/outputs/ which is committed into the PR branch.
"""

import os
import json
import glob
import pandas as pd
from pathlib import Path


OUTPUTS_DIR = Path('tool_coverage/outputs')
VALIDATION_SUMMARY = Path('tool_reviews/validation_summary.json')

TOOL_TYPE_LABELS = {
    'animal_models':           ('🐭', 'Animal Models'),
    'antibodies':              ('🔬', 'Antibodies'),
    'cell_lines':              ('🧫', 'Cell Lines'),
    'genetic_reagents':        ('🧬', 'Genetic Reagents'),
    'computational_tools':     ('💻', 'Computational Tools'),
    'clinical_assessment_tools': ('📋', 'Clinical Assessment Tools'),
    'advanced_cellular_models':  ('🫧', 'Advanced Cellular Models'),
    'patient_derived_models':    ('🧪', 'Patient-Derived Models'),
}


def load_validation_report():
    report_file = OUTPUTS_DIR / 'validation_report.csv'
    if report_file.exists():
        return pd.read_csv(report_file)
    return pd.DataFrame()


def load_validated_counts():
    """Return {stem: row_count} for each VALIDATED_*.csv in outputs dir."""
    counts = {}
    for path in sorted(OUTPUTS_DIR.glob('VALIDATED_*.csv')):
        stem = path.stem.replace('VALIDATED_', '')  # e.g. 'animal_models'
        try:
            df = pd.read_csv(path)
            counts[stem] = len(df)
        except Exception:
            counts[stem] = 0
    return counts


def load_submit_counts():
    """Fallback: SUBMIT_*.csv counts if VALIDATED not present."""
    counts = {}
    for path in sorted(OUTPUTS_DIR.glob('SUBMIT_*.csv')):
        stem = path.stem.replace('SUBMIT_', '')
        try:
            df = pd.read_csv(path)
            counts[stem] = len(df)
        except Exception:
            counts[stem] = 0
    return counts


def main():
    report_df = load_validation_report()
    validated_counts = load_validated_counts()
    # Fall back to SUBMIT counts if VALIDATED files aren't present yet
    tool_counts = validated_counts if validated_counts else load_submit_counts()
    using_validated = bool(validated_counts)

    total_pubs_reviewed = len(report_df)
    total_accepted = int(report_df['accepted'].sum()) if not report_df.empty else 0
    total_rejected = int(report_df['rejected'].sum()) if not report_df.empty else 0
    total_uncertain = int(report_df['uncertain'].sum()) if not report_df.empty else 0
    total_tools = total_accepted + total_rejected + total_uncertain
    pubs_with_accepted = int((report_df['accepted'] > 0).sum()) if not report_df.empty else 0
    pubs_needing_review = int((report_df['uncertain'] > 0).sum()) if not report_df.empty else 0

    print("# 🔍 Tool Coverage Update — Automated Mining Results")
    print()
    print("This PR contains NF research tools discovered by Sonnet reviewing full publication text.")
    print("**Review and merge to automatically upload to Synapse.**")

    # ── Summary counts ──────────────────────────────────────────────────────
    print()
    print("## 📊 Review Summary")
    print()
    print(f"| Metric | Count |")
    print(f"|--------|-------|")
    print(f"| Publications reviewed | {total_pubs_reviewed} |")
    print(f"| Publications with accepted tools | {pubs_with_accepted} |")
    print(f"| Total tools evaluated | {total_tools} |")
    print(f"| ✅ Accepted (Keep) | {total_accepted} |")
    print(f"| ❌ Rejected (Remove) | {total_rejected} |")
    print(f"| ⚠️ Uncertain (Manual Review) | {total_uncertain} |")
    if pubs_needing_review:
        print(f"| 📝 Publications needing manual review | {pubs_needing_review} |")

    # ── Tool type breakdown ─────────────────────────────────────────────────
    if tool_counts:
        csv_label = "VALIDATED_*.csv" if using_validated else "SUBMIT_*.csv (VALIDATED not yet created)"
        total_rows = sum(tool_counts.values())
        print()
        print(f"## 🎯 Novel Tool Suggestions by Type")
        print(f"*From `{csv_label}` — {total_rows} total rows*")
        print()
        print(f"| Type | Count |")
        print(f"|------|-------|")
        for stem, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            emoji, label = TOOL_TYPE_LABELS.get(stem, ('🔧', stem.replace('_', ' ').title()))
            print(f"| {emoji} {label} | {count} |")

    # ── Publications needing manual review ──────────────────────────────────
    if pubs_needing_review and not report_df.empty:
        uncertain_pubs = report_df[report_df['uncertain'] > 0][['pmid', 'title', 'uncertain']].head(10)
        print()
        print("## 📝 Publications Needing Manual Review")
        print(f"*{pubs_needing_review} publication(s) have uncertain tools requiring human judgment:*")
        print()
        for _, row in uncertain_pubs.iterrows():
            pmid_num = str(row['pmid']).replace('PMID:', '')
            print(f"- **{row['pmid']}** ({int(row['uncertain'])} uncertain) — {str(row['title'])[:80]}")
        if pubs_needing_review > 10:
            print(f"- *… and {pubs_needing_review - 10} more — see `validation_report.csv`*")

    # ── Files in this PR ────────────────────────────────────────────────────
    print()
    print("## 📁 Files in This PR")
    print()
    if using_validated:
        print("- `tool_coverage/outputs/VALIDATED_*.csv` — ⭐ **use these for Synapse upload** (false positives filtered)")
        print("- `tool_coverage/outputs/SUBMIT_*.csv` — intermediate files (pre-filter)")
    else:
        print("- `tool_coverage/outputs/SUBMIT_*.csv` — tool suggestions (validation filter did not run)")
    print("- `tool_coverage/outputs/validation_report.csv` — per-publication review summary")

    # ── Review workflow ─────────────────────────────────────────────────────
    print()
    print("## ✅ Review Checklist")
    print()
    print("1. **Check `validation_report.csv`** — review accepted tool names per publication")
    if pubs_needing_review:
        print(f"2. **Manually review {pubs_needing_review} uncertain publication(s)** listed above")
    print("2. **Spot-check `VALIDATED_*.csv`** — remove any remaining false positives")
    print("3. **Fill in missing fields** (vendor info, RRIDs, catalog numbers where blank)")
    print("4. **Merge PR** → triggers Synapse upsert workflow automatically")
    print()
    print("**On merge, the upsert-tools workflow will:**")
    print("- Clean tracking columns from CSV files")
    print("- Upload to Synapse tables (animal models, antibodies, cell lines, etc.)")
    print("- Create snapshot versions for audit trail")

    print()
    print("---")
    print("*Automated via `.github/workflows/check-tool-coverage.yml`*")


if __name__ == "__main__":
    main()
