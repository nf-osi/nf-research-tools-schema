#!/usr/bin/env python3
"""
Post-process VALIDATED_*.csv outputs to apply quality filters and generate outputs.

Filters applied (beyond AI verdict):
  Computational tools:
    - Generic stats/analysis environments (MATLAB, R, ImageJ, etc.)
    - Generic bioinformatics tools (STAR, DESeq2, Cytoscape, MaxQuant, etc.)
    - Sequencing hardware/platforms (Illumina HiSeq, NovaSeq, etc.)
    - Unnamed tools with no version AND no repo at confidence < 0.9
  Antibodies:
    - Secondary antibodies (clonality = Secondary)
  Animal models:
    - Wildtype controls / Cre drivers with no known disease
      (animalModelGeneticDisorder is empty or "No known disease")
  Genetic reagents:
    - Lab consumables, kits, and chemical probes misclassified as genetic reagents
  Patient-derived models:
    - Vague generic PDX descriptors with no specific model ID or NF context
  Clinical assessment tools:
    - Hardware devices (microscopes, scanners, EEG systems, etc.)
    - Lab assays/kits misclassified as clinical tools (ELISA, caspase kits, etc.)
    - Generic physical performance tests (gait test, treadmill, BBB locomotor, etc.)
    - Generic psychological scales not specific to NF (Perceived Stress Scale, etc.)

Outputs:
  - Updated VALIDATED_*.csv: deduplicated (1 row per unique tool, synonyms merged),
    blank resourceId column added (populated at Synapse upsert time)
  - review.csv: 1 row per PMID, novel tools listed by category (pub-centric)
  - review_filtered.csv: tools removed by post-filter, tool-centric (audit trail)

Usage:
    python generate_review_csv.py [--output-dir tool_coverage/outputs] [--dry-run]
"""

import csv
import re
import sys
import argparse
from collections import defaultdict
from pathlib import Path

# ── NF-pathway gene/protein list (for antibody NF-specificity) (for antibody NF-specificity) ────────────────
# If targetAntigen contains any of these (case-insensitive substring), the
# antibody is considered NF-pathway-relevant.
NF_PATHWAY_GENES = frozenset({
    # Core NF genes
    'nf1', 'neurofibromin', 'nf2', 'merlin', 'lztr1', 'smarcb1', 'ini1',
    'eed', 'suz12', 'prkar1a', 'spred1', 'cbl',
    # RAS/MAPK pathway (primary NF1 downstream)
    'kras', 'nras', 'hras', 'ras', 'raf1', 'braf', 'craf', 'araf',
    'map2k1', 'map2k2', 'mek1', 'mek2', 'mek', 'erk1', 'erk2', 'mapk',
    'p-erk', 'perk', 'p-mek', 'pmek', 'p-ras', 'rsk', 'p90rsk', 'dusp6',
    # PI3K / AKT / mTOR
    'pi3k', 'pik3ca', 'pik3r1', 'akt', 'p-akt', 'pakt', 'mtor', 'pmtor',
    'pten', 'tsc1', 'tsc2', 's6k', 'p70s6k', '4ebp1', 'p-4ebp1', 'p4ebp1',
    'rps6', 'p-s6', 'ps6', 'rictor', 'raptor',
    # Schwann cell / nerve sheath markers
    'sox10', 's100b', 's100', 'mbp', 'mpz', 'p0', 'plp1', 'ncam',
    'egr2', 'oct6', 'krox20', 'pmp22', 'periaxin',
    # YAP/Hippo (NF2/schwannoma)
    'yap', 'taz', 'tead', 'lats1', 'lats2', 'mob1',
    # MPNST / tumor markers
    'h3k27me3', 'h3k27', 'ezh2', 'bmi1', 'ring1b', 'cdkn2a', 'p16', 'p14',
    'cdkn2b', 'p15', 'rb ', 'rb1', 'mdm2', 'p53', 'tp53', 'aurora',
    # Growth factor receptors commonly studied in NF
    'egfr', 'erbb', 'her2', 'her3', 'pdgfr', 'pdgfra', 'pdgfrb',
    'vegfr', 'met ', 'c-met', 'axl', 'igf1r', 'igfr', 'kit', 'c-kit',
    # Apoptosis / cell death (used in NF drug studies)
    'bcl2', 'bcl-2', 'bclxl', 'bcl-xl', 'bax', 'bad', 'bid', 'noxa', 'puma',
    'caspase', 'parp', 'cytochrome c',
    # Proliferation
    'ki67', 'pcna', 'cyclin', 'cdk4', 'cdk6', 'cdk2',
    # Neuronal / glial
    'gfap', 'vimentin', 'nestin', 'cd34', 'cd56', 'cd57',
    # Immune / microenvironment (NF tumor)
    'cd3', 'cd8', 'cd4', 'cd68', 'cd163', 'foxp3', 'pd-l1', 'pdl1', 'pd-1',
    'csf1r', 'iba1',
})

# ── Computational tools blocklist ─────────────────────────────────────────────

# Exact-match generic tools (lowercase)
GENERIC_COMPUTATIONAL_TOOLS = frozenset({
    # Statistical environments
    'r', 'python', 'python3', 'matlab', 'excel', 'spss', 'sas', 'stata', 'octave',
    'prism', 'graphpad prism', 'graphpad',
    'graphpad prism 7', 'graphpad prism 8', 'graphpad prism 9', 'graphpad prism 10',
    # Image analysis
    'imagej', 'fiji', 'image j', 'imagej (fiji)', 'imagej (fiji, nih)',
    'imagej (nih)', 'imagej software', 'image j (nih)', 'imagej (rasband)',
    'imagej (rasband ws. imagej, u.s. national institutes of health)',
    'imagej (u.s. national institutes of health)',
    'cellprofiler', 'imaris', 'nis-elements', 'zen',
    # Aligners
    'star', 'hisat2', 'hisat', 'bwa', 'bowtie', 'bowtie2', 'tophat', 'tophat2',
    'kallisto', 'salmon', 'rsem', 'subread',
    # Differential expression
    'deseq', 'deseq2', 'edger', 'limma', 'limma-voom', 'voom',
    # Enrichment / pathway
    'gsea', 'david', 'enrichr', 'gprofiler', 'clusterprofiler',
    'reactome', 'kegg', 'ingenuity pathway analysis', 'ipa', 'metascape',
    # Network / interaction
    'cytoscape', 'string', 'string database', 'stringdb',
    # Proteomics
    'maxquant', 'perseus', 'skyline', 'peaks', 'scaffold', 'spectronaut',
    # CNV / variant calling
    'cnvkit', 'gatk', 'mutect', 'mutect2', 'haplotypecaller',
    'varscan', 'varscan2', 'strelka', 'strelka2',
    'annovar', 'vep', 'snpeff',
    # Assembly / quantification
    'stringtie', 'cufflinks', 'cuffdiff', 'featurecounts', 'htseq',
    # Processing / QC
    'samtools', 'picard', 'fastqc', 'trimmomatic', 'cutadapt', 'trim galore',
    'bedtools', 'bedops', 'deeptools', 'homer', 'macs2', 'macs3',
    'multiqc', 'fastp',
    # Fusion / SV detection
    'star-fusion', 'arriba', 'delly', 'lumpy',
    # Visualization
    'ggplot2', 'seaborn', 'matplotlib', 'plotly', 'tableau',
    # Generic databases (not tools)
    'ncbi', 'uniprot', 'ensembl', 'ucsc', 'genbank', 'pdb',
    'the cancer genome atlas', 'tcga', 'geo', 'sra',
})

# Substring-based blocking for computational tools (checked against lowercase name)
GENERIC_COMPUTATIONAL_PATTERNS = (
    # Sequencing hardware / platforms
    'hiseq', 'novaseq', 'nextseq', 'miseq', 'iseq', 'pacbio', 'nanopore',
    'infinium', 'methylation array', 'methylationepic', 'snp array',
    'beadchip',
    # Generic assay descriptors (not named software)
    'whole exome sequencing', 'whole genome sequencing',
    'bulk rna sequencing', 'single-cell rna sequencing',
    'chip-seq', 'atac-seq', 'hi-c', 'clip-seq',
)

# ── Clinical assessment tools filters ─────────────────────────────────────────

# Hardware / imaging devices
HARDWARE_CLINICAL_PATTERNS = (
    'microscope', 'digital camera', 'camera', 'apple watch', 'smartwatch',
    'wearable', 'eeg device', 'eeg system', 'mri scanner', 'pet scanner',
    'ct scanner', 'sequencer', 'flow cytometer', 'facs', 'patch clamp',
    'neuroscan', 'electrophysiology rig',
)

# Lab assays / kits misclassified as clinical tools
LAB_ASSAY_CLINICAL_PATTERNS = (
    'elisa', 'duoset', 'quantikine', 'luminex',
    'caspase', 'promega', 'cell viability', 'mtt assay', 'xtt assay',
    'annexin', 'flow cytometr',
    'luciferase assay', 'luminescence assay',
)

# Generic physical / functional performance tests
GENERIC_PHYSICAL_TEST_PATTERNS = (
    'gait test', 'gait analysis', 'treadmill test', 'jump test',
    'bbb open-field', 'bbb locomotor', 'open-field locomotor',
    'compound motor action potential', ' cmap',
)

# Generic psychological / stress scales (not NF-specific)
GENERIC_STRESS_SCALE_NAMES = frozenset({
    'perceived stress scale', 'perceived stress scale (pss)',
    'rating of overall stress scale', 'rating of overall stress scale (ross)',
})

# ── Genetic reagents filter ───────────────────────────────────────────────────

# Drug class suffixes — if insertName ends with any of these it is a drug compound,
# not a genetic insert.  All major kinase inhibitor (-nib), therapeutic antibody
# (-mab), HDAC/proteasome inhibitor (-ostat), and antibiotic (-mycin) classes.
DRUG_COMPOUND_SUFFIXES = (
    'nib',    # kinase inhibitors: lapatinib, erlotinib, trametinib, ruxolitinib, sorafenib…
    'mab',    # therapeutic mAbs: trastuzumab, bevacizumab, cetuximab…
    'ostat',  # epigenetic/proteasome inhibitors: panobinostat, vorinostat…
    'mycin',  # antibiotics / natural products: puromycin, gentamicin, rapamycin…
)

# Explicit drug names that don't match a suffix pattern above.
# Checked as exact match on lowercased insertName.
DRUG_COMPOUND_NAMES = frozenset({
    # Hormones / retinoids
    'tamoxifen', 'progesterone', 'atra',
    # mTOR inhibitors
    'everolimus', 'nvp-bez235', 'azd2014', 'tak-228',
    # MEK / RAS inhibitors
    'pd0325901',
    # Dual-class inhibitors
    'cudc-907',
    # IGF1R / receptor inhibitors
    'bms-754807',
    # Cell death / MDM2
    'nutlin-3', 'nutlin3', 'at101',
    # Miscellaneous pathway inhibitors
    'nsc23766', 'frax597', 'lgk-974', 'gsk2126458',
    'ink128', 'mln8237', 'ly294002', 'mg-132',
    'arry-520', 'vx680', 'su-11274', 'sgx2943',
    'apx2009', 'apx2014', 'apx3330', 'c1368',
    'gant61', 'napabucasin',
    # NMD suppressor
    'ataluren',
    # YAP inhibitor
    'verteporfin',
    # Anticonvulsants / other CNS drugs
    'lamotrigine', 'ketotifen fumarate',
    # Adenylyl cyclase activator
    'forskolin',
    # Neuroimaging / PET tracers
    'ogerin', 'raclopride', 'dtbz', 'sch23390', 'win 35428',
    # Selection antibiotic
    'g418',
    # Drug screening library
    'mipe 4.0',
})

# Substring patterns identifying non-genetic lab consumables/kits/chemicals
# that were misclassified as genetic reagents
GENETIC_NON_REAGENT_PATTERNS = (
    # Lab consumables
    'bead', 'resin', 'spin column', 'silica column', 'gel bead',
    # Generic reagent kits (not vector/construct-specific)
    ' kit', ' kit v', 'extraction kit', 'viability kit', 'staining kit',
    'library kit', 'library prep kit', 'protein extraction kit',
    'immunoassay kit', 'detection kit', 'pull-down kit', 'co-ip kit',
    # Chemical reagents / small molecules / probes
    'aminoactinomycin',     # 7-AAD, a viability dye
    '8cpt', '8-cpt',        # cAMP analogue
    'adu-s100',             # STING agonist
    'ag825',                # small molecule inhibitor
    # Lab reagents
    'delivery reagent', 'staining reagent', 'detection reagent',
    'transfection reagent', 'blocking reagent', 'permeabilization reagent',
    'protease inhibitor', 'phosphatase inhibitor',
    # Generic sequencing / library prep
    'sureselect', 'nextera', 'truseq',
    # General lab assay kits (should be in clinical/other categories)
    'brdu staining', 'annexin v',
    # Drug salt forms (sorafenib p-Toluenesulfonate salt, imatinib mesylate, etc.)
    'mesylate', 'toluenesulfonate', ' salt',
    # Cell viability / proliferation / apoptosis detection kits
    'assay',        # gene expression assay, cell migration assay, p21 ras activation assay…
    'celltiter', 'cytotox', 'cck8', 'alamarblue', 'realtime-glo',
    # PCR / RT reagents
    'polymerase', ' ligase', 'sybr', 'taqman mirna', 'reverse transcriptase',
    'superscript', 'taq ', 'pcr enzyme', 't7 transcription',
    # Cell culture media
    'dmem', 'rpmi', 'l15 medium', 'mem alpha',
    # Sample processing / dissociation enzymes
    'collagenase', 'papain', 'dispase',
    # Staining dyes / viability indicators (not labeled antibodies or genetic labels)
    'dapi', 'calcein am', 'to-pro', 'mitosox', 'hematoxylin',
    # RNA / DNA extraction and cleanup
    'trizol', 'paxgene', 'ampure', 'rneasy',
    # Density gradient / buffer reagents
    'ficoll', 'gadolinium', 'microbubble',
    # RNA / DNA processing steps (not constructs)
    'cdna synthesis', 'bisulfite', 'rna extraction', 'dna extraction',
    'rna library prep', 'dna library prep', 'library preparation', 'sequencing library',
    'sequencing reagent', 'dna quantification', 'methylation conversion',
    'rna depletion', 'rna isolation', 'reverse transcription reagent',
    'target enrichment', 'mutagenesis reagent', 'str analysis',
    'ffpe extraction', 'edu detection', 'click-it edu',
    # Additional sequencing / library chemistry reagents
    'bigdye', 'sequenase',      # Sanger sequencing reagents
    'riboerase',                # rRNA depletion kit
    'exome capture',            # target enrichment
    'probe library',            # capture probe library
    # Extraction / purification reagents
    'extraction reagent',       # NE-PER, nuclear/cytoplasmic extraction kits
    'purification reagent',     # PCR purification
    'rnase inhibitor',          # RNasin and similar RNA protection reagents
    # Other misclassified lab reagents
    'enzyme mix',               # End Repair Enzyme Mix, ligation enzyme mixes
    'vectastain', 'vecta stain',  # Vectastain Elite ABC — IHC detection kit
)

# ── Critical fields per type (for completeness scoring) ──────────────────────

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

# ── review.csv: pub-centric format ────────────────────────────────────────────

# Tool type → category column name in review.csv
CATEGORY_TO_TYPE: dict[str, str] = {
    'novel_animal_models':             'animal_models',
    'novel_antibodies':                'antibodies',
    'novel_cell_lines':                'cell_lines',
    'novel_genetic_reagents':          'genetic_reagents',
    'novel_computational_tools':       'computational_tools',
    'novel_advanced_cellular_models':  'advanced_cellular_models',
    'novel_patient_derived_models':    'patient_derived_models',
    'novel_clinical_assessment_tools': 'clinical_assessment_tools',
}

PUB_REVIEW_FIELDS = [
    # Publication identity
    'pmid', 'doi', 'publicationTitle', 'year', 'journal',
    # Novel tools mined this run, by category (semicolon-separated names)
    'novel_animal_models',
    'novel_antibodies',
    'novel_cell_lines',
    'novel_genetic_reagents',
    'novel_computational_tools',
    'novel_advanced_cellular_models',
    'novel_patient_derived_models',
    'novel_clinical_assessment_tools',
    # Tools already in Synapse Resource table (populated from resourceId lookup at upsert)
    'existing_tools',
    # Summary
    'total_novel_tools', 'nf_specific_count', 'max_priority',
]

# review_filtered.csv stays tool-centric (audit trail)
TOOL_REVIEW_FIELDS = [
    'toolName', 'toolType',
    '_pmid', '_doi', '_publicationTitle', '_year',
    '_confidence', '_usageType', 'nf_specific', 'completeness_score', 'priority',
    'strainNomenclature', 'animalModelGeneticDisorder', 'animalModelOfManifestation',
    'targetAntigen', 'hostOrganism', 'clonality',
    'organ', 'cellLineGeneticDisorder', 'cellLineManifestation', 'cellLineCategory',
    'insertName', 'vectorType', 'vectorBackbone', 'promoter',
    'softwareName', 'softwareType', 'softwareVersion', 'sourceRepository',
    'modelType', 'derivationSource', 'cellTypes', 'organoidType',
    'modelSystemType', 'patientDiagnosis', 'hostStrain', 'tumorType',
    'assessmentName', 'assessmentType', 'targetPopulation', 'diseaseSpecific', 'numberOfItems',
    '_context',
]
TOOL_REVIEW_FILTERED_FIELDS = TOOL_REVIEW_FIELDS + ['filter_reason']


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
    if tool_type == 'antibodies':
        antigen = row.get('targetAntigen', '').lower()
        return any(gene in antigen for gene in NF_PATHWAY_GENES)
    # computational_tools, resources: included by default (used in NF-focused publications)
    return True


def _completeness_score(row: dict, tool_type: str) -> float:
    """Return fraction of critical fields that are non-empty."""
    critical = CRITICAL_FIELDS.get(tool_type, [])
    if not critical:
        return 1.0
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
        name_lc = name.lower()
        if name_lc in GENERIC_COMPUTATIONAL_TOOLS:
            return True, f"Generic bioinformatics/stats tool: {name}"
        if any(p in name_lc for p in GENERIC_COMPUTATIONAL_PATTERNS):
            return True, f"Sequencing hardware or generic assay protocol: {name}"
        has_version = bool(row.get('softwareVersion', '').strip())
        has_repo = bool(row.get('sourceRepository', '').strip())
        if not has_version and not has_repo and confidence < 0.9:
            return True, "No version and no repository URL (confidence < 0.9 — unidentifiable)"

    elif tool_type == 'antibodies':
        if row.get('clonality', '').strip() == 'Secondary':
            return True, "Secondary antibody (not an NF-specific research tool)"

    elif tool_type == 'animal_models':
        disorder = row.get('animalModelGeneticDisorder', '').strip()
        if disorder in ('', 'No known disease'):
            strain = row.get('strainNomenclature', '').strip()
            return True, f"Wildtype/control with no known disease: {strain}"

    elif tool_type == 'genetic_reagents':
        insert = row.get('insertName', '').strip()
        insert_lc = insert.lower()
        # Drug compounds: kinase inhibitors, mAbs, HDAC inhibitors, antibiotics, etc.
        if any(insert_lc.endswith(suffix) for suffix in DRUG_COMPOUND_SUFFIXES):
            return True, f"Drug compound (class suffix): {insert}"
        if insert_lc in DRUG_COMPOUND_NAMES:
            return True, f"Drug compound: {insert}"
        # Non-genetic lab consumables, assay kits, media, reagents
        if any(p in insert_lc for p in GENETIC_NON_REAGENT_PATTERNS):
            return True, f"Non-genetic lab reagent/kit/consumable: {insert}"

    elif tool_type == 'patient_derived_models':
        name = row.get('_toolName', '').strip()
        name_lc = name.lower()
        _NF_TERMS = ('nf1', 'nf2', 'neurofibromatosis', 'schwannoma', 'neurofibroma',
                     'mpnst', 'spnst', 'neurofibroma')
        _GENERIC_PDX = ('patient-derived xenograft', 'pdx model', 'xenograft model',
                        'xenograft models', 'tumor xenograft')
        is_generic = any(p in name_lc for p in _GENERIC_PDX)
        has_nf = any(t in name_lc for t in _NF_TERMS)
        has_id  = bool(re.search(r'[A-Z]{2,4}[-–]\d{1,4}|(?:pdox|pdx)-?\d', name, re.IGNORECASE))
        if is_generic and not has_nf and not has_id:
            return True, f"Vague PDX descriptor — no specific model ID or NF context: {name}"

    elif tool_type == 'clinical_assessment_tools':
        name = row.get('assessmentName', '').strip()
        name_lc = name.lower()
        if any(p in name_lc for p in HARDWARE_CLINICAL_PATTERNS):
            return True, "Hardware device, not a clinical assessment instrument"
        if any(p in name_lc for p in LAB_ASSAY_CLINICAL_PATTERNS):
            return True, "Lab assay/kit misclassified as clinical assessment tool"
        if any(p in name_lc for p in GENERIC_PHYSICAL_TEST_PATTERNS):
            return True, "Generic physical performance test, not a validated clinical instrument"
        if name_lc in GENERIC_STRESS_SCALE_NAMES:
            return True, "Generic psychological scale (not NF-specific)"

    return False, ''


# ── Synonym deduplication ─────────────────────────────────────────────────────

def _normalize_tool_name(name: str, tool_type: str) -> str:
    """Normalize a tool name to a canonical key for deduplication."""
    # Strip RRID, ATCC, catalog info in parentheses
    name = re.sub(
        r'\s*\([^)]*(?:RRID|ATCC|cat\.?|catalog|CRL-|CVCL_|lot)[^)]*\)',
        '', name, flags=re.IGNORECASE
    )
    # Strip trailing cell line type suffixes
    if tool_type == 'cell_lines':
        name = re.sub(
            r'[\s,]+(?:cell(?:s)?(?:[\s-]?line(?:s)?)?|cell[\s-]?line(?:s)?)$',
            '', name, flags=re.IGNORECASE
        )
    # Strip trailing animal suffixes
    if tool_type == 'animal_models':
        name = re.sub(r'[\s,]+(?:mice?|rats?|animals?|mouse)$', '', name, flags=re.IGNORECASE)
    # Strip leading/trailing PDX / PDOX labels for patient-derived models
    # so "PDX JH-2-002", "JH-2-002 PDX", "JH-2-002" all normalize to the same key
    if tool_type == 'patient_derived_models':
        name = re.sub(r'^(?:PDX|PDOX)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+(?:PDX|PDOX)$', '', name, flags=re.IGNORECASE)
    # Normalize all hyphens, spaces, slashes, punctuation → empty
    name = re.sub(r'[-\s/.,;:+‐–—]+', '', name.lower())
    name = re.sub(r'[^\w\d]', '', name)
    return name.strip()


def _deduplicate_validated_rows(rows: list, tool_type: str) -> list:
    """Collapse synonym/duplicate tool rows into one row per unique tool.

    Groups rows by normalized tool name. For each group:
    - Keeps the highest-confidence row as the base for all scalar fields
    - Concatenates _pmid, _doi, _publicationTitle, _year, _context with ' | '
    - Prefers Development > Experimental Usage > Citation Only for _usageType
    - Adds blank resourceId column (populated at Synapse upsert time)
    """
    if not rows:
        return rows

    USAGE_PRIO = {'Development': 0, 'Experimental Usage': 1, 'Citation Only': 2, '': 3}
    CONCAT_FIELDS = ['_pmid', '_doi', '_publicationTitle', '_year', '_context']
    name_col = NAME_COLUMN.get(tool_type, '_toolName')

    groups: dict = defaultdict(list)
    for row in rows:
        raw_name = row.get(name_col, '') or row.get('_toolName', '')
        norm = _normalize_tool_name(raw_name, tool_type)
        groups[norm].append(row)

    merged: list = []
    for norm, group_rows in groups.items():
        # Best row: highest confidence, then most informative usageType
        group_rows.sort(key=lambda r: (
            -float(r.get('_confidence', 0) or 0),
            USAGE_PRIO.get(r.get('_usageType', ''), 3),
        ))
        base = dict(group_rows[0])
        if len(group_rows) > 1:
            for field in CONCAT_FIELDS:
                seen: list = []
                seen_set: set = set()
                for r in group_rows:
                    val = r.get(field, '').strip()
                    if val and val not in seen_set:
                        seen.append(val)
                        seen_set.add(val)
                base[field] = ' | '.join(seen)
        base.setdefault('resourceId', '')
        merged.append(base)

    return merged


# ── Publication metadata loading ──────────────────────────────────────────────

def _load_pub_meta(output_path: Path) -> dict:
    """Load publication metadata from processed_publications.csv or JSON cache."""
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
        return pub_meta
    # Fall back to JSON cache files
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
        if pub_meta:
            print(f"  Loaded metadata for {len(pub_meta)} publications from cache JSON files")
    return pub_meta


# ── Pub-centric pivot (for review.csv) ───────────────────────────────────────

def _pivot_to_pub_centric(tool_rows: list, pub_meta: dict) -> list:
    """Pivot per-tool rows to one row per publication.

    Each output row has: pub metadata + per-category novel tool lists + summary stats.
    'existing_tools' is left blank (populated via Synapse resourceId lookup at upsert).
    """
    PRIORITY_ORDER = {'High': 0, 'Medium': 1, 'Low': 2}

    pub_tools: dict = defaultdict(lambda: defaultdict(list))
    pub_info: dict = {}

    for r in tool_rows:
        pmid = r.get('_pmid', '').strip()
        if not pmid:
            continue
        tool_type = r.get('toolType', '')
        tool_name = r.get('toolName', '').strip()
        if tool_name:
            pub_tools[pmid][tool_type].append({
                'name': tool_name,
                'nf':   r.get('nf_specific', False),
                'pri':  r.get('priority', 'Low'),
            })
        if pmid not in pub_info:
            meta = pub_meta.get(pmid, {})
            pub_date = meta.get('publicationDate', '')
            year = r.get('_year', '') or (pub_date[:4] if pub_date else '')
            pub_info[pmid] = {
                'pmid':             pmid,
                'doi':              r.get('_doi', '') or meta.get('doi', ''),
                'publicationTitle': r.get('_publicationTitle', '') or meta.get('title', ''),
                'year':             year,
                'journal':          meta.get('journal', ''),
            }

    pub_rows: list = []
    for pmid in sorted(pub_tools.keys()):
        info = pub_info.get(pmid, {
            'pmid': pmid, 'doi': '', 'publicationTitle': '', 'year': '', 'journal': '',
        })
        row: dict = dict(info)
        all_pris: list = []
        nf_count = total = 0
        for col, tt in CATEGORY_TO_TYPE.items():
            tools = pub_tools[pmid].get(tt, [])
            row[col] = '; '.join(t['name'] for t in tools)
            for t in tools:
                all_pris.append(PRIORITY_ORDER.get(t['pri'], 2))
                total += 1
                if t['nf']:
                    nf_count += 1
        row['existing_tools']    = ''
        row['total_novel_tools'] = total
        row['nf_specific_count'] = nf_count
        row['max_priority']      = (
            ['High', 'Medium', 'Low'][min(all_pris)] if all_pris else 'Low'
        )
        pub_rows.append(row)

    pub_rows.sort(key=lambda r: (
        PRIORITY_ORDER.get(r['max_priority'], 2),
        -r['total_novel_tools'],
    ))
    return pub_rows


# ── Tool-centric row builder (for audit trail) ────────────────────────────────

def _get_tool_name(row: dict, tool_type: str) -> str:
    col = NAME_COLUMN.get(tool_type, '')
    return row.get(col, '').strip() if col else ''


def _make_tool_review_row(row: dict, tool_type: str, nf_specific: bool,
                          completeness: float, priority: str) -> dict:
    tool_name = _get_tool_name(row, tool_type)
    d: dict = {'toolName': tool_name, 'toolType': tool_type}
    for f in TOOL_REVIEW_FIELDS:
        if f not in ('toolName', 'toolType'):
            d[f] = row.get(f, '')
    d['nf_specific']      = nf_specific
    d['completeness_score'] = f"{completeness:.2f}"
    d['priority']         = priority
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

    # Load publication metadata once (reused for pub-centric pivot + link CSVs)
    pub_meta = _load_pub_meta(output_path)

    # Per-tool rows (pre-dedup) — used for pub-centric pivot and link CSVs
    all_tool_rows: list[dict] = []
    all_filtered_rows: list[dict] = []
    stats: dict = {}
    # Normalized kept names per type — used to filter SUBMIT_resources.csv
    kept_norm_names: dict[str, set] = {}

    # Link tables are regenerated by _write_publication_link_csvs(); skip here
    _LINK_TABLE_TYPES = frozenset({'resources', 'publications', 'usage', 'development'})

    for validated_file in validated_files:
        tool_type = validated_file.stem.replace('VALIDATED_', '')
        if tool_type in _LINK_TABLE_TYPES:
            continue

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
                nf   = _is_nf_specific(row, tool_type)
                comp = _completeness_score(row, tool_type)
                conf = float(row.get('_confidence', 0) or 0)
                pri  = _priority(nf, comp, conf)
                all_tool_rows.append(_make_tool_review_row(row, tool_type, nf, comp, pri))

        for row in filtered:
            nf   = _is_nf_specific(row, tool_type)
            comp = _completeness_score(row, tool_type)
            conf = float(row.get('_confidence', 0) or 0)
            pri  = _priority(nf, comp, conf)
            fr   = _make_tool_review_row(row, tool_type, nf, comp, pri)
            fr['filter_reason'] = row.get('filter_reason', '')
            all_filtered_rows.append(fr)

        stats[tool_type] = {
            'original': len(rows),
            'kept':     len(kept),
            'filtered': len(filtered),
        }

        if not dry_run and kept:
            # Deduplicate synonyms, add blank resourceId column
            kept_out  = _deduplicate_validated_rows(kept, tool_type)
            n_deduped = len(kept) - len(kept_out)

            # Populate _resourceName from the primary name column (consistent cross-type field)
            name_col = NAME_COLUMN.get(tool_type)
            for row in kept_out:
                row['_resourceName'] = (
                    row.get(name_col, '') if name_col else ''
                ) or row.get('_toolName', '')

            # Build output column order: resourceId + name + domain cols + tracking cols
            tracking_prefix = ['_pmid', '_doi', '_publicationTitle', '_year', '_context',
                                '_confidence', '_verdict', '_usageType']
            out_fieldnames = ['resourceId']
            if name_col and name_col in fieldnames:
                out_fieldnames.append(name_col)
            # Remaining domain columns (non-tracking, non-name)
            out_fieldnames += [f for f in fieldnames
                               if f not in out_fieldnames and not f.startswith('_')]
            # Tracking columns last (_resourceName first among tracking, then ordered prefix)
            out_fieldnames.append('_resourceName')
            out_fieldnames += [f for f in tracking_prefix if f in fieldnames]
            out_fieldnames += [f for f in fieldnames
                               if f not in out_fieldnames and f.startswith('_')]

            with open(validated_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=out_fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(kept_out)

            # Track normalized kept names to filter VALIDATED_resources.csv
            name_col_key = NAME_COLUMN.get(tool_type, '_toolName')
            kept_norm_names[tool_type] = {
                _normalize_tool_name(r.get(name_col_key, '') or r.get('_toolName', ''), tool_type)
                for r in kept_out
            }

            dedup_msg = f", {n_deduped} synonyms merged" if n_deduped else ""
            print(f"  ✅ {len(kept_out)} kept{dedup_msg}, {len(filtered)} removed "
                  f"→ {validated_file.name}")
        elif dry_run:
            deduped   = _deduplicate_validated_rows(kept, tool_type)
            n_deduped = len(kept) - len(deduped)
            print(f"  [DRY-RUN] {len(deduped)} kept ({n_deduped} synonyms merged), "
                  f"{len(filtered)} removed")
        else:
            print(f"  ⚠️  All {len(rows)} rows filtered — leaving original file unchanged")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Post-filter summary")
    print(f"{'='*60}")
    total_in = total_out = total_removed = 0
    for t, s in stats.items():
        total_in    += s['original']
        total_out   += s['kept']
        total_removed += s['filtered']
        if s['filtered']:
            print(f"  {t:<30} {s['original']:>4} → {s['kept']:>4}  (-{s['filtered']})")
        else:
            print(f"  {t:<30} {s['original']:>4} → {s['kept']:>4}")
    print(f"  {'TOTAL':<30} {total_in:>4} → {total_out:>4}  (-{total_removed})")

    if dry_run:
        print("\n[DRY-RUN] No files were modified.")
        return

    # ── Pub-centric review.csv ─────────────────────────────────────────────────
    review_file = output_path / 'review.csv'
    pub_rows = _pivot_to_pub_centric(all_tool_rows, pub_meta)
    with open(review_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=PUB_REVIEW_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(pub_rows)
    high = sum(1 for r in pub_rows if r['max_priority'] == 'High')
    med  = sum(1 for r in pub_rows if r['max_priority'] == 'Medium')
    low  = sum(1 for r in pub_rows if r['max_priority'] == 'Low')
    print(f"\n✅ review.csv: {len(pub_rows)} publications  (High={high}, Medium={med}, Low={low})")
    print(f"   One row per PMID — novel tools listed per category, existing_tools blank until Synapse lookup")
    print(f"   → {review_file}")

    # ── Tool-centric review_filtered.csv (audit trail) ────────────────────────
    if all_filtered_rows:
        filtered_file = output_path / 'review_filtered.csv'
        with open(filtered_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=TOOL_REVIEW_FILTERED_FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_filtered_rows)
        print(f"🗑  review_filtered.csv: {len(all_filtered_rows)} post-filtered tools (audit trail)")
        print(f"   → {filtered_file}")

    # ── NF-specific breakdown ─────────────────────────────────────────────────
    print(f"\nNF-specific breakdown (kept tools):")
    nf_types: dict = {}
    for r in all_tool_rows:
        tt = r['toolType']
        nf_types.setdefault(tt, {'nf': 0, 'total': 0})
        nf_types[tt]['total'] += 1
        if r.get('nf_specific') is True:
            nf_types[tt]['nf'] += 1
    for tt, c in sorted(nf_types.items()):
        pct = 100 * c['nf'] / c['total'] if c['total'] else 0
        print(f"  {tt:<30} {c['nf']:>4}/{c['total']:<4} NF-specific ({pct:.0f}%)")

    # ── Sync SUBMIT_resources.csv ─────────────────────────────────────────────
    _filter_submit_resources(output_path, kept_norm_names)

    # ── Publication link CSVs ─────────────────────────────────────────────────
    _write_publication_link_csvs(all_tool_rows, output_path, pub_meta)

    # ── Remove superseded SUBMIT_*.csv intermediates ──────────────────────────
    # run_publication_reviews.py writes SUBMIT_*.csv as intermediates.
    # generate_review_csv.py produces VALIDATED_*.csv for everything.
    # Any SUBMIT_*.csv that has a VALIDATED equivalent is now redundant.
    removed_submits: list[str] = []
    for submit_file in sorted(output_path.glob('SUBMIT_*.csv')):
        validated_equiv = output_path / submit_file.name.replace('SUBMIT_', 'VALIDATED_')
        if validated_equiv.exists():
            submit_file.unlink()
            removed_submits.append(submit_file.name)
    if removed_submits:
        print(f"\n🗑  Removed {len(removed_submits)} superseded SUBMIT_*.csv files "
              f"(VALIDATED_*.csv are canonical):")
        for name in removed_submits:
            print(f"    {name}")


def _filter_submit_resources(output_path: Path, kept_norm_names: dict) -> None:
    """Filter SUBMIT_resources.csv and VALIDATED_resources.csv to keep only rows
    for tools that passed post-filtering in their respective type-specific files.

    kept_norm_names maps plural tool type (e.g. 'animal_models') → set of normalized names.
    The resources CSV uses singular _toolType values (e.g. 'animal_model'), so we map them.
    """
    SINGULAR_TO_PLURAL = {
        'animal_model':             'animal_models',
        'antibody':                 'antibodies',
        'cell_line':                'cell_lines',
        'genetic_reagent':          'genetic_reagents',
        'computational_tool':       'computational_tools',
        'advanced_cellular_model':  'advanced_cellular_models',
        'patient_derived_model':    'patient_derived_models',
        'clinical_assessment_tool': 'clinical_assessment_tools',
    }

    print(f"\n{'='*60}")
    print("Filtering VALIDATED_resources.csv")
    print(f"{'='*60}")

    for fname in ('VALIDATED_resources.csv',):
        resources_file = output_path / fname
        if not resources_file.exists():
            print(f"  ⏭  {fname} not found — skipping")
            continue

        try:
            with open(resources_file, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                rows = list(reader)
        except Exception as e:
            print(f"  ❌ Error reading {fname}: {e}")
            continue

        kept: list = []
        removed = 0
        for row in rows:
            tool_type_singular = row.get('_toolType', '').strip()
            tool_type_plural   = SINGULAR_TO_PLURAL.get(tool_type_singular)

            if tool_type_plural not in kept_norm_names:
                # Type not processed this run (or unknown) — keep row unchanged
                kept.append(row)
                continue

            resource_name = row.get('resourceName', '').strip()
            norm = _normalize_tool_name(resource_name, tool_type_plural)
            if norm in kept_norm_names[tool_type_plural]:
                row['_resourceName'] = resource_name
                kept.append(row)
            else:
                removed += 1

        # Ensure _resourceName is in fieldnames
        if '_resourceName' not in fieldnames:
            fieldnames.append('_resourceName')

        with open(resources_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(kept)

        print(f"  ✅ {fname}: {len(kept)} kept, {removed} removed")


def _write_publication_link_csvs(review_rows: list[dict], output_path: Path,
                                  pub_meta: dict | None = None) -> None:
    """Generate SUBMIT_publications.csv, SUBMIT_usage.csv, SUBMIT_development.csv."""
    print(f"\n{'='*60}")
    print("Generating publication link CSVs")
    print(f"{'='*60}")

    if pub_meta is None:
        pub_meta = _load_pub_meta(output_path)

    # First pass: collect link rows
    usage_rows: list = []
    dev_rows: list = []
    all_pmid_info: dict = {}

    for r in review_rows:
        pmid       = r.get('_pmid', '').strip()
        doi        = r.get('_doi', '').strip()
        title      = r.get('_publicationTitle', '').strip()
        year       = r.get('_year', '').strip()
        usage_type = r.get('_usageType', '').strip()
        tool_name  = r.get('toolName', '').strip()
        tool_type  = r.get('toolType', '').strip()

        if not pmid:
            continue
        if pmid not in all_pmid_info:
            all_pmid_info[pmid] = {'doi': doi, 'title': title, 'year': year}
        if not tool_name:
            continue

        link_row = {
            '_pmid': pmid, '_doi': doi, '_publicationTitle': title, '_year': year,
            '_toolName': tool_name, '_toolType': tool_type, '_usageType': usage_type,
            'publicationId': '', 'resourceId': '',
        }
        if usage_type == 'Development':
            dev_rows.append({**link_row, 'developmentId': ''})
            usage_rows.append({**link_row, 'usageId': ''})
        elif usage_type == 'Experimental Usage':
            usage_rows.append({**link_row, 'usageId': ''})

    # Second pass: build pub_rows only for PMIDs with at least one link
    linked_pmids  = {r['_pmid'] for r in usage_rows} | {r['_pmid'] for r in dev_rows}
    orphan_pmids  = set(all_pmid_info.keys()) - linked_pmids
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
            'doi':             info.get('doi', '') or meta.get('doi', ''),
            'pmid':            pmid,
            'publicationTitle': info.get('title', '') or meta.get('title', ''),
            'abstract':        meta.get('abstract', ''),
            'journal':         meta.get('journal', ''),
            'publicationDate': meta.get('publicationDate', ''),
            'authors':         authors_raw,
        })

    pub_fields = ['doi', 'pmid', 'publicationTitle', 'abstract',
                  'journal', 'publicationDate', 'authors']
    if pub_rows:
        with open(output_path / 'VALIDATED_publications.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=pub_fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(pub_rows)
        print(f"  ✅ VALIDATED_publications.csv: {len(pub_rows)} unique publications")

    usage_fields = ['_pmid', '_doi', '_publicationTitle', '_year',
                    '_toolName', '_toolType', '_usageType',
                    'publicationId', 'resourceId', 'usageId']
    if usage_rows:
        with open(output_path / 'VALIDATED_usage.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=usage_fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(usage_rows)
        print(f"  ✅ VALIDATED_usage.csv: {len(usage_rows)} publication-tool usage links")

    dev_fields = ['_pmid', '_doi', '_publicationTitle', '_year',
                  '_toolName', '_toolType', '_usageType',
                  'publicationId', 'resourceId', 'developmentId']
    if dev_rows:
        with open(output_path / 'VALIDATED_development.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=dev_fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(dev_rows)
        print(f"  ✅ VALIDATED_development.csv: {len(dev_rows)} publication-tool development links")

    if pub_rows:
        dev_pmids        = {r['_pmid'] for r in dev_rows}
        usage_only_pmids = {r['_pmid'] for r in usage_rows} - dev_pmids
        mixed_pmids      = dev_pmids & {r['_pmid'] for r in usage_rows}
        print(f"\n  Publication roles:")
        print(f"    Development (tool created here):  {len(dev_pmids)}")
        print(f"    Usage only (tool used here):      {len(usage_only_pmids)}")
        print(f"    Mixed (both usage + development): {len(mixed_pmids)}")
        print(f"    ⚠️  publicationId/resourceId are blank — resolved at Synapse upsert time")


def main():
    parser = argparse.ArgumentParser(
        description='Post-filter VALIDATED_*.csv and generate pub-centric review.csv'
    )
    parser.add_argument('--output-dir', default='tool_coverage/outputs',
                        help='Directory containing VALIDATED_*.csv files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without modifying any files')
    args = parser.parse_args()
    process(args.output_dir, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
