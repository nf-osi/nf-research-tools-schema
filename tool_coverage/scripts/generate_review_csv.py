#!/usr/bin/env python3
"""
Post-process VALIDATED_*.csv outputs to apply quality filters and generate outputs.

Filters applied (beyond AI verdict):
  All tool types:
    - Publications whose title lacks NF-specific terms (NF1/NF2/MPNST/etc.)
  Computational tools:
    - Generic stats/analysis environments (MATLAB, R, ImageJ, etc.)
    - Generic bioinformatics tools (STAR, DESeq2, Cytoscape, MaxQuant, etc.)
    - Sequencing hardware/platforms (Illumina HiSeq, NovaSeq, etc.)
    - Unnamed tools with no version AND no repo at confidence < 0.9
  Antibodies:
    - Secondary antibodies (clonality = Secondary)
    - Generic loading control antibodies (Beta-actin, GAPDH, alpha-tubulin, etc.)
    - _resourceName prefixed with 'anti-' for clarity
  Animal models:
    - Wildtype controls / Cre drivers with no known disease
    - fl/flox synonym consolidation (NF1 fl/fl ≡ NF1 flox/flox)
  Genetic reagents:
    - Lab consumables, kits, and chemical probes misclassified as genetic reagents
    - Generic names without specific identifiers (Gateway entry vector, etc.)
  Patient-derived models:
    - Vague generic PDX descriptors with no specific model ID or NF context
    - Trailing ' PDX' suffix stripped (kept if followed by number, e.g. PDX-1)
  Clinical assessment tools:
    - Hardware devices (microscopes, scanners, EEG systems, etc.)
    - Lab assays/kits misclassified as clinical tools (ELISA, caspase kits, etc.)
    - Generic physical performance tests (gait test, treadmill, BBB locomotor, etc.)
    - Generic psychological scales not specific to NF (Perceived Stress Scale, etc.)
    - Tools whose name is not in the publication title AND 'tool' not in title
  Advanced cellular models:
    - Publications whose title lacks 3D/organoid/spheroid/sphere terms
  Cell lines:
    - Generic names (Primary Schwannoma Cells, etc.)
    - Trailing ' cells' / ' cell line' stripped from _resourceName

Outputs:
  - Updated VALIDATED_*.csv: deduplicated (1 row per unique tool, synonyms merged),
    blank resourceId column added (populated at Synapse upsert time)
  - VALIDATED_donor.csv: species-level donor info for animal models (→ syn26486829)
  - VALIDATED_vendor.csv: vendor names extracted from antibody contexts (→ syn26486850)
  - VALIDATED_vendorItem.csv: catalog numbers per vendor-resource (→ syn26486843)
  - review.csv: 1 row per PMID, novel tools listed by category (pub-centric)
  - review_filtered.csv: tools removed by post-filter, tool-centric (audit trail)

Usage:
    python generate_review_csv.py [--output-dir tool_coverage/outputs] [--dry-run]
"""

import csv
import hashlib
import re
import sys
import argparse
from collections import defaultdict
from pathlib import Path

# ── NF gene sets for antibody / genetic-reagent NF-specificity filter ─────────
#
# NF_CORE_GENES  (default) — Only the disease-causing NF genes and their direct
#   protein products.  Antibodies must target one of these to pass the hard
#   NF-specificity filter.  Use this when you want the registry to contain only
#   reagents that directly probe the causal NF biology.
#
# NF_PATHWAY_GENES  (--include-pathway-genes) — Adds the full RAS/MAPK/PI3K/AKT
#   signalling cascade, Schwann-cell markers, tumor microenvironment proteins, and
#   other proteins commonly studied in NF research.  Use for a broader registry.
#
# _active_nf_genes is set at runtime by process() based on the CLI flag.

NF_CORE_GENES = frozenset({
    # NF1 — Neurofibromatosis type 1
    'nf1', 'neurofibromin',
    # NF2 — Neurofibromatosis type 2 / schwannomatosis
    'nf2', 'merlin',
    # Schwannomatosis genes (LZTR1, SMARCB1/INI1)
    'lztr1', 'smarcb1', 'ini1',
    # SWN-related PRC2 subunits (EED/SUZ12 schwannomatosis)
    'eed', 'suz12',
    # NF1-related syndrome genes (Legius: SPRED1; CBL syndrome; Carney: PRKAR1A)
    'prkar1a', 'spred1', 'cbl',
})

NF_PATHWAY_GENES = NF_CORE_GENES | frozenset({
    # RAS/MAPK pathway (primary NF1 downstream) — include hyphenated RAF forms
    'kras', 'nras', 'hras', 'ras', 'raf1', 'braf', 'craf', 'araf',
    'b-raf', 'c-raf', 'a-raf',
    'map2k1', 'map2k2', 'mek1', 'mek2', 'mek', 'erk1', 'erk2', 'erk', 'mapk',
    'p-erk', 'perk', 'p-mek', 'pmek', 'p-ras', 'rsk', 'p90rsk', 'dusp6',
    # PI3K / AKT / mTOR — include S6K/S6 readable variants
    'pi3k', 'pik3ca', 'pik3r1', 'akt', 'p-akt', 'pakt', 'mtor', 'pmtor',
    'pten', 'tsc1', 'tsc2', 's6k', 'p70s6k', 'p70s6', 's6 kinase', 'ribosomal s6',
    '4ebp1', 'p-4ebp1', 'p4ebp1', 'rps6', 'p-s6', 'ps6', 'rictor', 'raptor',
    # PAK / RAC / CDC42 (RAS→RAC effectors in NF)
    'pak1', 'pak2', 'pak3', 'pak ',
    'rac1', ' rac ', 'cdc42',
    # JAK-STAT (studied in NF tumors)
    'stat3', 'p-stat3', 'jak2', 'p-jak2',
    # NF-κB (inflammation in NF tumor)
    'nf-κb', 'nfkb', 'nf-kb',
    # GSK-3β / CREB (NF1 cAMP / Wnt pathway)
    'gsk3', 'gsk-3', 'creb',
    # Autophagy markers (NF treatment studies)
    'lc3', 'lc3b', 'beclin',
    # Hypoxia (NF tumor)
    'hif1', 'hif-1',
    # AMPK (NF metabolic studies)
    'ampk',
    # VEGF (NF tumor angiogenesis)
    'vegf', 'vegfa',
    # Schwann cell / nerve sheath markers
    'sox10', 's100b', 's100', 'mbp', 'mpz', 'p0', 'plp1', 'ncam',
    'egr2', 'oct6', 'krox20', 'pmp22', 'periaxin',
    # Schwann cell identity / nerve markers
    'ngfr', 'p75', 'ng2', 'cnpase', 'mag ', 'pgp9.5',
    # Glial / neural progenitor (NF optic glioma, neurological phenotype)
    'olig2', 'sox2', 'sox9', 'map2', 'neun', 'neurofilament', 'nf-200', 'nf-h',
    'blbp', 'gfap',
    # YAP/Hippo (NF2/schwannoma)
    'yap', 'taz', 'tead', 'lats1', 'lats2', 'mob1',
    # MPNST / tumor markers
    'h3k27me3', 'h3k27', 'ezh2', 'bmi1', 'ring1b', 'cdkn2a', 'p16', 'p14',
    'cdkn2b', 'p15', 'rb ', 'rb1', 'mdm2', 'p53', 'tp53', 'aurora',
    # NF2/schwannoma-specific
    'ndrg1', 'rabl6a', 'p55/mpp1', 'mpp1',
    # PDE4A (NF1 cAMP / gliomagenesis)
    'pde4',
    # EPHA2 (studied in NF schwannoma)
    'epha2', 'epha',
    # Survivin (NF tumor treatment)
    'survivin',
    # Growth factor receptors commonly studied in NF
    'egfr', 'erbb', 'her2', 'her3', 'her1',
    'pdgfr', 'pdgfra', 'pdgfrb',
    'vegfr', 'met ', 'c-met', 'axl', 'igf1r', 'igfr', 'kit', 'c-kit',
    # Immune checkpoint / microenvironment (NF tumor)
    'pd-l1', 'pdl1', 'pd-1', 'ctla-4', 'ctla4',
    'gzmb', 'granzyme',
    # Macrophage / myeloid (NF tumor microenvironment)
    'cd3', 'cd4', 'cd8', 'cd11b', 'cd11c', 'cd14',
    'cd34', 'cd56', 'cd57', 'cd68', 'cd163',
    'foxp3', 'csf1r', 'csf1', 'iba1',
    # Tumor ECM (NF tumor stroma)
    'tgf-β', 'tgfb', 'tgf', 'cxcl12', 'cxcr4',
    'postn', 'periostin', 'ctgf', 'collagen', 'endoglin',
    # Apoptosis / cell death (used in NF drug studies)
    'bcl2', 'bcl-2', 'bclxl', 'bcl-xl', 'bax', 'bad', 'bid', 'noxa', 'puma',
    'caspase', 'parp', 'cytochrome c',
    # Proliferation
    'ki67', 'pcna', 'cyclin', 'cdk4', 'cdk6', 'cdk2',
    # Neuronal / glial
    'vimentin', 'nestin',
    # Innate immune signaling (NF)
    'sting', 'tbk1', 'irf3',
    # Miscellaneous proteins specifically used as NF tools
    'rheb', 'rabl6a', 'atrx', 'apc',
})

# Runtime-selected gene set — default strict; overridden to NF_PATHWAY_GENES
# by --include-pathway-genes flag.
_active_nf_genes: frozenset = NF_CORE_GENES

# ── NF-specific publication title filter ─────────────────────────────────────
# Publications must mention at least one of these terms (case-insensitive) to
# contribute tools of any category.  Prevents off-topic papers from diluting the
# registry.  Mesothelioma and meningioma are included as NF2-associated cancers.
_NF_TITLE_RE = re.compile(
    r'\b(nf[\-\s]?1|nf[\-\s]?2|swn|schwannomatosis|neurofibromatosis|neurofibroma'
    r'|schwannoma|mpnst|malignant\s+peripheral\s+nerve\s+sheath'
    r'|mesothelioma|meningioma'
    r'|lztr1|smarcb1|ini1|spred1)',
    re.IGNORECASE,
)


def _has_nf_title(pub_title: str) -> bool:
    """Return True if the publication title mentions NF-relevant terminology."""
    return bool(_NF_TITLE_RE.search(pub_title))


# ── Computational tools blocklist ─────────────────────────────────────────────

# Exact-match generic tools (lowercase)
GENERIC_COMPUTATIONAL_TOOLS = frozenset({
    # Self-referential: this registry itself should not appear as an entry
    'nf research tools database',
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

# Prefix-based blocking: any tool whose lowercased name *starts with* one of
# these strings is generic, regardless of version suffix appended.
GENERIC_COMPUTATIONAL_PREFIXES = (
    'imagej',            # ImageJ 1.53a, ImageJ (NIH), etc.
    'image j',           # Image J variants with space
    'graphpad prism',    # GraphPad Prism 8, Prism version 9, etc.
    'prism version',     # "Prism version 9" (bare prism without GraphPad)
    'upsetr',            # UpSetR version 1.4.0
    'upset ',            # UpSet (other capitalizations)
    'sas, version',      # "SAS, version 9.4"
    'sas version',       # "SAS version 9.4"
    'r version',         # "R version 3.5.0" (generic R)
    'python version',    # "Python version 3.9"
    'string version',    # "STRING version 11.5"
    'string v',          # "STRING v11"
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

# Exact-match names for genetic reagents that are too generic for the registry.
# Checked case-insensitively against the lowercased insertName.
GENERIC_GENETIC_REAGENT_NAMES = frozenset({
    # Generic cloning / expression systems
    'gateway entry vector',
    'baculovirus expression vector',
    'e. coli expression vector',
    'empty vector',
    'plko', 'plko.1',               # generic lentiviral backbone
    'pcdna3.1',                     # generic mammalian expression vector
    'pcr2.1-topo',                  # generic TOPO cloning vector
    'mscv',                         # generic retroviral backbone (without NF insert)
    # Generic luciferase reporters (vague — no NF-specific promoter)
    'luciferase reporter',
    'dual luciferase reporter',
    'ap-1 luciferase',              # generic AP-1 reporter (not NF-specific)
    'firefly luciferase-gfp fusion',
    'firefly luciferase-egfp fusion',
    'luciferase-ires-gfp',
    'fluc and mcherry',
    # Generic fluorescent protein inserts (labels, not NF-specific constructs)
    'gfp', 'egfp', 'eyfp',
    'rfp', 'mrfp',
    'nuclear rfp',
    'nuclight red', 'nuclight',
    'mcherry',
    'mruby',
    'mturquoise',
    # Generic CRISPR machinery / silencing controls (NF-targeted variants kept below)
    'cas9',
    'crispr-cas9', 'crispr/cas9',
    'guide rna',
    'grna',
    'sgrna',
    'shrna', 'shrnas',              # bare class names without specific target
    'scramble',                     # scrambled control without named target
    'scrambled sirna',
    'non-targeting control',
    # Generic inducible systems (too vague without NF-specific cargo)
    'tet-on',
    'tet-inducible',
    # Generic viral vector components
    'packaging',
    'envelope',
    # Generic sequencing / capture probes (not NF-specific panels)
    'human all exon',
    'human all exon capture probes',
    'human exome',
    'dna capture system',
    'microsatellite markers',
    # Generic primers / oligonucleotides
    'oligo-dt',
    # Cell isolation (not a genetic construct)
    'pan-t-cell isolation',
})

# NF-specific terms that rescue an otherwise-generic CRISPR/silencing name.
# If the insertName contains any of these, the reagent is NF-specific and kept.
_NF_INSERT_TERMS: tuple = (
    'nf1', 'nf2', 'lztr1', 'smarcb1', 'merlin', 'neurofibromin', 'spred1',
    'schwann', 'neurofibr',
)

# Generic CRISPR/silencing patterns: if an insert matches these AND has no
# NF-specific term, it is too generic to register.
_GENERIC_CRISPR_RE = re.compile(
    r'^(?:cas9|crispr|guide\s+rna|grna|sgrna|shrna|rna\s+interference|rnai'
    r'|short\s+hairpin|short\s+interfering)\b',
    re.IGNORECASE,
)

# ── Generic antibodies that must be filtered regardless of NF context ─────────
# These target generic reporter proteins, affinity tags, or housekeeping
# proteins that carry no NF-pathway information.
GENERIC_CONTROL_ANTIBODIES = frozenset({
    # Loading controls / housekeeping proteins
    'beta-actin', 'β-actin', 'b-actin', 'beta actin', 'actin',
    'alpha-tubulin', 'α-tubulin', 'alpha tubulin',
    'tubulin', 'beta-tubulin', 'β-tubulin', 'beta tubulin',
    'gamma-tubulin', 'γ-tubulin', 'gamma tubulin',
    'acetylated tubulin',
    'gapdh',
    'lamin b', 'lamin b1', 'lamin a/c',
    'histone h3', 'total histone h3',
    'vinculin',
    # Fluorescent reporter proteins (antibodies against GFP/RFP/mCherry etc.
    # are generic reagents with no NF-pathway specificity)
    'gfp', 'egfp', 'eyfp', 'yfp',
    'rfp', 'mrfp', 'mcherry', 'cherry',
    'tomato', 'tdtomato', 'td-tomato',
    'mruby', 'ruby', 'mturquoise', 'turquoise',
    # Generic affinity tags (same reason — used in any biochemistry)
    'ha', 'ha tag', 'ha-tag',
    'flag', 'flag tag', 'flag-tag',
    'v5', 'v5 tag', 'v5-tag',
    'gst',                          # when used as pure tag (not NF-GRD fusion)
    # Generic reporters / lineage tracers
    'β-gal', 'beta-gal', 'β-galactosidase', 'lacz',
    # Generic conjugate / detection markers (not primary targets)
    'cy3/cy5', 'cy3', 'cy5', 'dig-fab',
    # Generic xenograft markers
    'human nuclear antigen', 'human nuclei',
    # Generic proliferation dye (not a specific target)
    'brdu',
})

# ── Generic cell line names (too vague for NF tool registry) ─────────────────
GENERIC_CELL_LINE_NAMES = frozenset({
    'primary schwannoma cells',
    'primary neurofibroma cells',
    'primary schwann cells',
    'normal schwann cells',
    'normal human schwann cells',
})

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
    # Per-tool publication cross-reference: "ToolName: PMID1 | PMID2; ..."
    'tool_usage_publications',
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
        return any(gene in antigen for gene in _active_nf_genes)
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

    # ── Global: publication title must mention NF-related terms ──────────────
    pub_title = row.get('_publicationTitle', '').strip()
    if pub_title and not _has_nf_title(pub_title):
        return True, f"Publication title lacks NF-specific terms: {pub_title[:80]}"

    if tool_type == 'computational_tools':
        name = row.get('softwareName', '').strip()
        name_lc = name.lower()
        if name_lc in GENERIC_COMPUTATIONAL_TOOLS:
            return True, f"Generic bioinformatics/stats tool: {name}"
        if any(p in name_lc for p in GENERIC_COMPUTATIONAL_PATTERNS):
            return True, f"Sequencing hardware or generic assay protocol: {name}"
        # Block versioned generics by prefix (e.g. "ImageJ 1.53a", "GraphPad Prism 9")
        if any(name_lc.startswith(p) for p in GENERIC_COMPUTATIONAL_PREFIXES):
            return True, f"Generic tool (versioned): {name}"
        has_version = bool(row.get('softwareVersion', '').strip())
        has_repo = bool(row.get('sourceRepository', '').strip())
        if not has_version and not has_repo and confidence < 0.9:
            return True, "No version and no repository URL (confidence < 0.9 — unidentifiable)"
        # The software name (or its acronym) must appear in the publication title.
        # Generic analysis pipelines used in NF papers are captured by antibody/animal model
        # rows; the computational tools registry is for NF-specific, purpose-built software
        # whose development is the focus of the paper (e.g. RENOVO-NF1, DINs).
        title_lc = pub_title.lower()
        # Strip version suffix to get the base name: "STAR v2.7" → "STAR"
        base = re.sub(r'\s+v?\d[\d.]*\w*$', '', name, flags=re.IGNORECASE)
        base = re.sub(r'\s+version\s+\d[\d.]*\w*$', '', base, flags=re.IGNORECASE)
        base = re.sub(r'\s*\(v?\d[\d.]*[^)]*\)\s*', ' ', base).strip()
        # Extract acronym from parenthetical (e.g. "Deep Interactive Networks (DINs)" → "DINs")
        # Require ≥3 chars to avoid matching single letters like "R"
        abbrev_m = re.search(r'\(([A-Za-z0-9][A-Za-z0-9\-_]{2,15})\)', name)
        acronym  = abbrev_m.group(1).lower() if abbrev_m else ''
        base_lc  = re.sub(r'\s*\([^)]*\)\s*', ' ', base).strip().lower()
        in_title = (name_lc in title_lc or
                    (len(base_lc) >= 3 and base_lc in title_lc) or
                    (len(acronym) >= 3 and acronym in title_lc))
        if not in_title:
            return True, f"Software name not in publication title — likely generic usage: {name}"

    elif tool_type == 'antibodies':
        if row.get('clonality', '').strip() == 'Secondary':
            return True, "Secondary antibody (not an NF-specific research tool)"
        antigen_lc = row.get('targetAntigen', '').lower().strip()
        # Blocklist: reporter proteins, affinity tags, generic housekeeping
        if antigen_lc in GENERIC_CONTROL_ANTIBODIES:
            return True, f"Generic reporter/tag/housekeeping antibody: {antigen_lc}"
        # Hard NF-pathway filter: target must map to a protein studied in NF biology.
        # _is_nf_specific checks NF_PATHWAY_GENES against the lowercase targetAntigen.
        if not _is_nf_specific(row, 'antibodies'):
            return True, f"Antibody target not in NF pathway/tumor biology gene list: {row.get('targetAntigen','')}"

    elif tool_type == 'cell_lines':
        cell_name = (row.get('_toolName', '') or '').strip()
        cell_name_lc = cell_name.lower()
        if cell_name_lc in GENERIC_CELL_LINE_NAMES:
            return True, f"Generic cell line name: {cell_name}"

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
        # Exact-match generic reagent class names (fluorescents, packaging, controls, …)
        if insert_lc in GENERIC_GENETIC_REAGENT_NAMES:
            return True, f"Generic reagent (fluorescent label / control / probe): {insert}"
        # Non-genetic lab consumables, assay kits, media, reagents
        if any(p in insert_lc for p in GENETIC_NON_REAGENT_PATTERNS):
            return True, f"Non-genetic lab reagent/kit/consumable: {insert}"
        # Generic CRISPR/silencing machinery without an NF-specific target.
        # Names like "Cas9", "sgRNA", "shRNA" are filtered unless they also contain
        # an NF gene name (e.g. "NF1 gRNA", "shNF1", "nf2a/b-4sgRNA" are kept).
        if _GENERIC_CRISPR_RE.match(insert_lc):
            has_nf_target = any(t in insert_lc for t in _NF_INSERT_TERMS)
            if not has_nf_target:
                return True, f"Generic CRISPR/silencing tool — no NF-specific target: {insert}"
        # Generic fluorescent-protein inserts (substring patterns not covered by exact match)
        _FLUOR_PATTERNS = ('egfp', 'mcherry', 'mrfp', 'mruby', 'mturquoise',
                           'ires-gfp', 'ires-rfp', 'nuclight', 'nuclear rfp',
                           'tdtomato', 'td-tomato')
        if any(p in insert_lc for p in _FLUOR_PATTERNS):
            has_nf_target = any(t in insert_lc for t in _NF_INSERT_TERMS)
            if not has_nf_target:
                return True, f"Generic fluorescent-label insert without NF-specific cargo: {insert}"
        # Hard NF core-gene filter: insertName must reference a core NF disease gene.
        # This ensures only reagents that directly target/encode an NF gene are registered.
        if not any(g in insert_lc for g in NF_CORE_GENES):
            return True, f"Insert does not reference a core NF disease gene: {insert}"

    elif tool_type == 'patient_derived_models':
        name = row.get('_toolName', '').strip()
        name_lc = name.lower()
        _NF_TERMS = ('nf1', 'nf2', 'neurofibromatosis', 'schwannoma', 'neurofibroma',
                     'mpnst', 'spnst', 'neurofibroma')
        _GENERIC_PDX = ('patient-derived xenograft', 'pdx model', 'xenograft model',
                        'xenograft models', 'tumor xenograft')
        is_generic = any(p in name_lc for p in _GENERIC_PDX)
        has_nf = any(t in name_lc for t in _NF_TERMS)
        has_id = bool(re.search(r'[A-Z]{2,4}[-–]\d{1,4}|(?:pdox|pdx)-?\d', name, re.IGNORECASE))
        if is_generic and not has_nf and not has_id:
            return True, f"Vague PDX descriptor — no specific model ID or NF context: {name}"
        # Vague PDX names: end in bare '-PDX' or '-pdx' with no following number
        # (e.g. 'NF1-associated MPNST-PDX', 'NF1-MPNST patient-derived xenografts')
        if not has_id:
            if re.search(r'[-\s]pdx$', name_lc):
                return True, f"Vague PDX name — no specific model ID (e.g. PDX-1): {name}"
            if name_lc.endswith('patient-derived xenografts'):
                return True, f"Plural/generic PDX description — re-mine for specific model IDs: {name}"

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
        # Only keep tools that appear in the publication title or that the paper developed:
        # Criterion: tool name (or bracketed abbreviation) in title, OR 'tool' in title.
        title_lc = pub_title.lower()
        # Extract abbreviation from parenthetical: e.g. "(INF1-QOL)" → "inf1-qol"
        abbrev_m = re.search(r'\(([A-Z0-9\-]{3,15})\)', name)
        abbrev = abbrev_m.group(1).lower() if abbrev_m else ''
        name_in_title   = name_lc in title_lc
        abbrev_in_title = bool(abbrev and abbrev in title_lc)
        tool_in_title   = 'tool' in title_lc
        if not name_in_title and not abbrev_in_title and not tool_in_title:
            return True, (f"Assessment name not in title and 'tool' not in title — "
                          f"likely generic usage, not development: {name}")

    elif tool_type == 'advanced_cellular_models':
        # The publication title should mention 3D/organoid/spheroid terminology
        title_lc = pub_title.lower()
        _3D_TERMS = ('3d', '3-d', 'organoid', 'spheroid', 'sphere', 'tumoroid',
                     'assembloid', 'microtissue', 'organ-on')
        if not any(t in title_lc for t in _3D_TERMS):
            return True, "Publication title lacks 3D/organoid/spheroid terminology"

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
    # Strip trailing animal suffixes; normalize fl ↔ flox synonym
    if tool_type == 'animal_models':
        name = re.sub(r'[\s,]+(?:mice?|rats?|animals?|mouse)$', '', name, flags=re.IGNORECASE)
        # 'fl' is the official abbreviation for 'flox' (loxP-flanked allele).
        # Normalise so that 'Nf1 fl/fl' and 'Nf1 flox/flox' collapse to one key.
        name = re.sub(r'\bfl\b', 'flox', name, flags=re.IGNORECASE)
    # Strip leading/trailing PDX / PDOX labels for patient-derived models
    # so "PDX JH-2-002", "JH-2-002 PDX", "JH-2-002" all normalize to the same key.
    # But keep "MPNST PDX-1" style names (PDX followed by hyphen + number).
    if tool_type == 'patient_derived_models':
        name = re.sub(r'^(?:PDX|PDOX)\s+', '', name, flags=re.IGNORECASE)
        # Only strip trailing ' PDX' if NOT followed by a dash+number (PDX-1, PDX-01…)
        name = re.sub(r'\s+(?:PDX|PDOX)$', '', name, flags=re.IGNORECASE)
    # Normalize all hyphens, spaces, slashes, punctuation → empty
    name = re.sub(r'[-\s/.,;:+‐–—]+', '', name.lower())
    name = re.sub(r'[^\w\d]', '', name)
    return name.strip()


def _smart_split(s: str, sep: str = ';') -> list:
    """Split on sep but not inside parentheses or brackets.

    Handles tool names like 'Human Schwann cells (HSC; ScienCell, Carlsbad, CA)'
    that contain the separator inside parentheses.
    """
    parts, depth, cur = [], 0, []
    for c in s:
        if c in '([':
            depth += 1
            cur.append(c)
        elif c in ')]':
            depth = max(depth - 1, 0)
            cur.append(c)
        elif c == sep and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(c)
    if cur:
        parts.append(''.join(cur).strip())
    return [p for p in parts if p]


def _build_validated_lookup(output_path: Path) -> dict:
    """Build a (ttype, norm_key) → (canonical_name, [pmids]) lookup from VALIDATED_*.csv.

    Indexes canonical names, synonyms column entries, and for antibodies also
    indexes names without the 'anti-' prefix (to match review.csv which omits it).
    """
    validated_stems = {
        'VALIDATED_animal_models':             'animal_models',
        'VALIDATED_antibodies':                'antibodies',
        'VALIDATED_cell_lines':                'cell_lines',
        'VALIDATED_genetic_reagents':          'genetic_reagents',
        'VALIDATED_computational_tools':       'computational_tools',
        'VALIDATED_advanced_cellular_models':  'advanced_cellular_models',
        'VALIDATED_patient_derived_models':    'patient_derived_models',
        'VALIDATED_clinical_assessment_tools': 'clinical_assessment_tools',
    }
    lookup: dict = {}
    for stem, ttype in validated_stems.items():
        vfile = output_path / f'{stem}.csv'
        if not vfile.exists():
            continue
        try:
            with open(vfile, newline='', encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
        except Exception:
            continue
        name_col = NAME_COLUMN.get(ttype, '_toolName')
        for row in rows:
            canonical = (
                row.get(name_col, '') or row.get('_toolName', '') or
                row.get('_resourceName', '')
            ).strip()
            if not canonical:
                continue
            pmids = [p.strip() for p in row.get('_pmid', '').split('|') if p.strip()]
            # Index canonical name
            norm = _normalize_tool_name(canonical, ttype)
            if norm:
                lookup.setdefault((ttype, norm), (canonical, pmids))
            # For antibodies: also index without the 'anti-' prefix so that
            # review.csv entries like 'SUZ12' match VALIDATED entry 'anti-SUZ12'
            if ttype == 'antibodies' and canonical.lower().startswith('anti-'):
                bare_norm = _normalize_tool_name(canonical[5:].strip(), ttype)
                if bare_norm:
                    lookup.setdefault((ttype, bare_norm), (canonical, pmids))
            # Index synonyms column entries
            for syn in _smart_split(row.get('synonyms', ''), ';'):
                syn_norm = _normalize_tool_name(syn, ttype)
                if syn_norm:
                    lookup.setdefault((ttype, syn_norm), (canonical, pmids))
    return lookup


def _lookup_tool_pmids(tool_name: str, ttype: str,
                        lookup: dict) -> tuple[str, list]:
    """Return (canonical_name, pmids) for tool_name in the validated lookup.

    Falls back to:
    1. Antibody anti- prefix (review.csv strips it; VALIDATED always has it)
    2. Component-of-compound substring matching for animal_models
       (e.g. 'Olig2-Cre' matches compound key 'Nf1flox/flox; Olig2-Cre')

    Returns (tool_name, []) when no match is found.
    """
    norm = _normalize_tool_name(tool_name, ttype)
    if not norm:
        return tool_name, []
    # Direct match
    if (ttype, norm) in lookup:
        return lookup[(ttype, norm)]
    # Antibody: try with 'anti-' prefix prepended
    if ttype == 'antibodies' and not tool_name.lower().startswith('anti-'):
        anti_norm = _normalize_tool_name('anti-' + tool_name, ttype)
        if (ttype, anti_norm) in lookup:
            return lookup[(ttype, anti_norm)]
    # Component-of-compound: find entries whose normalized key contains this norm
    candidates = [
        v for (tt, k), v in lookup.items()
        if tt == ttype and len(k) > len(norm) and norm in k
    ]
    if candidates:
        best = min(candidates, key=lambda v: len(_normalize_tool_name(v[0], ttype)))
        return best
    return tool_name, []


def _compute_tool_usage_publications(pub_row: dict, lookup: dict) -> str:
    """Build 'ToolName: PMID1 | PMID2; ToolName2: PMID3' for all novel tools in pub_row.

    Looks up each novel tool listed in the novel_* columns against the validated
    lookup to find which publications used it.  Uses smart_split to handle tool
    names that contain semicolons inside parentheses.
    """
    parts: list[str] = []
    for col, ttype in CATEGORY_TO_TYPE.items():
        raw = pub_row.get(col, '').strip()
        if not raw:
            continue
        for tool in _smart_split(raw, ';'):
            tool = tool.strip()
            if not tool:
                continue
            _canonical, pmids = _lookup_tool_pmids(tool, ttype, lookup)
            if pmids:
                parts.append(f"{tool}: {' | '.join(pmids)}")
    return '; '.join(parts)


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

def _pivot_to_pub_centric(tool_rows: list, pub_meta: dict,
                          validated_lookup: dict | None = None) -> list:
    """Pivot per-tool rows to one row per publication.

    Each output row has: pub metadata + per-category novel tool lists + summary stats.
    'existing_tools' is left blank (populated via Synapse resourceId lookup at upsert).
    'tool_usage_publications' shows which publications used each novel tool.
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

    # Populate tool_usage_publications for each row
    lu = validated_lookup or {}
    for row in pub_rows:
        row['tool_usage_publications'] = _compute_tool_usage_publications(row, lu)

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

def process(output_dir: str, dry_run: bool = False,
            include_pathway_genes: bool = False) -> None:
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"❌ Output directory not found: {output_dir}")
        sys.exit(1)

    validated_files = sorted(output_path.glob('VALIDATED_*.csv'))
    if not validated_files:
        print(f"❌ No VALIDATED_*.csv files found in {output_dir}")
        sys.exit(1)

    # Apply NF gene set selection before any filtering begins
    global _active_nf_genes
    if include_pathway_genes:
        _active_nf_genes = NF_PATHWAY_GENES
        print(f"\n[NF gene filter] Using EXTENDED pathway gene set ({len(NF_PATHWAY_GENES)} terms)")
    else:
        _active_nf_genes = NF_CORE_GENES
        print(f"\n[NF gene filter] Using CORE NF disease gene set ({len(NF_CORE_GENES)} terms) "
              f"— use --include-pathway-genes for broader antibody coverage")

    # Load publication metadata once (reused for pub-centric pivot + link CSVs)
    pub_meta = _load_pub_meta(output_path)

    # Per-tool rows (pre-dedup) — used for pub-centric pivot and link CSVs
    all_tool_rows: list[dict] = []
    all_filtered_rows: list[dict] = []
    stats: dict = {}
    # Normalized kept names per type — used to filter SUBMIT_resources.csv
    kept_norm_names: dict[str, set] = {}

    # Link / auxiliary tables that are regenerated by dedicated functions — skip in main loop
    _LINK_TABLE_TYPES = frozenset({
        'resources', 'publications', 'usage', 'development',
        'donor', 'vendor', 'vendorItem',
    })

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
                raw_name = (row.get(name_col, '') if name_col else '') or row.get('_toolName', '')
                # Save original (pre-transformation) name for resourceId computation so that
                # the ID matches what _write_publication_link_csvs computes from the same
                # raw NAME_COLUMN value (toolName comes from _get_tool_name which uses NAME_COLUMN).
                _raw_for_id = raw_name

                if tool_type == 'antibodies':
                    # Prefix with 'anti-' so the registry name matches literature usage
                    # (e.g. 'anti-collagen IV', not just 'collagen IV')
                    if raw_name and not raw_name.lower().startswith('anti-'):
                        raw_name = 'anti-' + raw_name

                elif tool_type == 'cell_lines':
                    # Strip trailing ' cells' / ' cell line' from output name
                    raw_name = re.sub(
                        r'[\s,]+(?:cell(?:s)?(?:[\s-]?line(?:s)?)?|cell[\s-]?line(?:s)?)$',
                        '', raw_name, flags=re.IGNORECASE
                    ).strip()

                elif tool_type == 'patient_derived_models':
                    # Strip trailing bare ' PDX' / ' PDOX' unless followed by hyphen+number
                    # e.g. 'JH-2-079c PDX' → 'JH-2-079c'; 'MPNST PDX-1' unchanged
                    raw_name = re.sub(r'\s+(?:PDX|PDOX)$', '', raw_name, flags=re.IGNORECASE).strip()

                row['_resourceName'] = raw_name
                # resourceId uses the pre-transformation name so it stays consistent with
                # the IDs computed in _write_publication_link_csvs (which sees the same raw value)
                _norm_key = _normalize_tool_name(_raw_for_id or row.get('_toolName', ''), tool_type)
                row['resourceId'] = _make_resource_id(_norm_key, tool_type) if _norm_key else ''

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
    # Build validated lookup from final VALIDATED_*.csv files (post-dedup) for
    # tool_usage_publications cross-reference column.
    validated_lookup = _build_validated_lookup(output_path)

    review_file = output_path / 'review.csv'
    pub_rows = _pivot_to_pub_centric(all_tool_rows, pub_meta, validated_lookup)
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

    # ── Donor / vendor CSVs ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Generating donor / vendor CSVs")
    print(f"{'='*60}")
    _write_donor_csv(output_path)
    _write_vendor_csvs(output_path)

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


# ── ID generation ─────────────────────────────────────────────────────────────

def _make_resource_id(normalized_name: str, tool_type: str) -> str:
    """Generate a stable 8-char hex resource ID from normalized name + type.

    IDs are deterministic so resourceId is consistent across VALIDATED_*.csv
    files and the link tables (usage, development).  These are temporary
    placeholders replaced by real Synapse IDs at upsert time.
    """
    key = f"{tool_type}:{normalized_name.strip()}"
    return 'RES' + hashlib.sha1(key.encode()).hexdigest()[:8]


def _make_pub_id(pmid: str) -> str:
    """Generate a stable publication ID from PMID.

    Numeric PMIDs become 'PUBnnnnnnn'; non-numeric get a short hash suffix.
    """
    pmid = pmid.strip()
    numeric = pmid.lstrip('PMID:').strip()
    if numeric.isdigit():
        return f'PUB{numeric}'
    return 'PUB' + hashlib.sha1(pmid.encode()).hexdigest()[:8]


# ── Species inference for donor CSV ───────────────────────────────────────────

# (compiled pattern, latin_name) — ordered most-specific first
_SPECIES_PATTERNS: list = [
    (re.compile(r'\b(?:mouse|mice|murine|mus\s+musculus)\b', re.IGNORECASE),   'Mus musculus'),
    (re.compile(r'\b(?:rat|rats|rattus|sprague[- ]dawley|wistar)\b', re.IGNORECASE), 'Rattus norvegicus'),
    (re.compile(r'\b(?:zebrafish|danio\s+rerio)\b', re.IGNORECASE),            'Danio rerio'),
    (re.compile(r'\b(?:drosophila|fruit\s+fly|melanogaster)\b', re.IGNORECASE),'Drosophila melanogaster'),
    (re.compile(r'\b(?:pig|swine|sus\s+scrofa|porcine)\b', re.IGNORECASE),     'Sus scrofa'),
    (re.compile(r'\b(?:rabbit|oryctolagus|cuniculus)\b', re.IGNORECASE),       'Oryctolagus cuniculus'),
    (re.compile(r'\b(?:\bdog\b|canine|canis\b|familiaris)\b', re.IGNORECASE),  'Canis lupus familiaris'),
    (re.compile(r'\b(?:frog|xenopus)\b', re.IGNORECASE),                       'Xenopus laevis'),
    (re.compile(r'\b(?:yeast|saccharomyces|cerevisiae)\b', re.IGNORECASE),     'Saccharomyces cerevisiae'),
    (re.compile(r'\b(?:human|homo\s+sapiens|patient)\b', re.IGNORECASE),       'Homo sapiens'),
]

# Common inbred/outbred mouse strain patterns that don't contain 'mouse'/'mice'
_MOUSE_STRAIN_RE = re.compile(
    r'\b(?:C57BL|BALB|FVB|NOD|NRG|NSG|SCID|athymic|nu/nu|nude'
    r'|CB-17|CBA|DBA|SJL|A/J|AKR|129[/S]?v?|B6|C3H|transgenic'
    r'|Nf[12][+\-]|p53[+\-])\b',
    re.IGNORECASE,
)


def _infer_species(strain: str, context: str = '') -> str:
    """Return the Latin species name inferred from strain + context text.

    Returns '' if species cannot be determined.
    """
    text = f'{strain} {context}'
    for pattern, latin in _SPECIES_PATTERNS:
        if pattern.search(text):
            return latin
    # Fallback: common mouse strain nomenclature lacking explicit 'mouse'/'mice'
    if _MOUSE_STRAIN_RE.search(strain):
        return 'Mus musculus'
    return ''


def _write_donor_csv(output_path: Path) -> None:
    """Generate VALIDATED_donor.csv (→ syn26486829) from animal model strain data.

    One row per unique species found across all kept animal model rows.
    Schema: donorId, parentDonorId, transplantationDonorId, species, sex, age, race
    """
    animal_file = output_path / 'VALIDATED_animal_models.csv'
    if not animal_file.exists():
        print('  ⏭  VALIDATED_animal_models.csv not found — skipping donor CSV')
        return
    try:
        with open(animal_file, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        print(f'  ❌ Error reading animal models: {e}')
        return

    species_seen: set = set()
    donor_rows: list = []
    for row in rows:
        strain  = row.get('strainNomenclature', '').strip()
        context = row.get('_context', '').strip()
        species = _infer_species(strain, context)
        if species and species not in species_seen:
            species_seen.add(species)
            donor_id = 'DON' + hashlib.sha1(species.encode()).hexdigest()[:8]
            donor_rows.append({
                'donorId':                donor_id,
                'parentDonorId':          '',
                'transplantationDonorId': '',
                'species':                species,
                'sex':                    '',
                'age':                    '',
                'race':                   '',
            })

    if not donor_rows:
        print('  ⚠️  No species inferred from animal model strains — VALIDATED_donor.csv not written')
        return

    donor_rows.sort(key=lambda r: r['species'])
    donor_file   = output_path / 'VALIDATED_donor.csv'
    donor_fields = ['donorId', 'parentDonorId', 'transplantationDonorId',
                    'species', 'sex', 'age', 'race']
    with open(donor_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=donor_fields)
        writer.writeheader()
        writer.writerows(donor_rows)
    print(f'  ✅ VALIDATED_donor.csv: {len(donor_rows)} unique species → {donor_file}')


# ── Vendor / catalog extraction for antibody rows ─────────────────────────────

# Parenthetical form: "(Cell Signaling Technology, Cat# 4370)"
_VENDOR_PAREN_RE = re.compile(
    r'\(([A-Za-z][^()\n]{3,50}?),?\s*[Cc]at(?!alog)\.?(?:\s*[Nn]o\.?|#|:)?\s*'
    r'([A-Za-z0-9][A-Za-z0-9\-._]{2,20})\)',
    re.IGNORECASE,
)
# Bracket form: "[eBioscience; Cat# 553087]"
_VENDOR_BRACKET_RE = re.compile(
    r'\[([A-Za-z][^\[\]\n;]{2,35}?)(?:;|,)?\s*[Cc]at(?!alog)\.?(?:\s*[Nn]o\.?|#|:)?\s*'
    r'([A-Za-z0-9][A-Za-z0-9\-._]{2,20})\]',
    re.IGNORECASE,
)
# Short inline form: 1–4 capitalised words immediately before "Cat#/Cat No"
# Require first word to be Capitalised to avoid matching antibody descriptors.
_VENDOR_INLINE_RE = re.compile(
    r'(?<![A-Za-z])((?:[A-Z][A-Za-z\-&]+(?:\s+[A-Za-z\-&]+){0,3}))\s+'
    r'[Cc]at(?!alog)\.?\s*(?:[Nn]o\.?|#|:)?\s*([A-Za-z0-9][A-Za-z0-9\-._]{2,20})',
)

# Words that indicate the captured text is an antibody descriptor, not a vendor
_VENDOR_ANTIBODY_WORDS = frozenset({
    'anti', 'rabbit', 'mouse', 'goat', 'rat', 'sheep', 'donkey', 'human',
    'monoclonal', 'polyclonal', 'secondary', 'primary',
    'used', 'dilution', 'prediluted', 'stem', 'tibody', 'antibody',
})


def _extract_vendor_from_context(context: str) -> tuple[str, str]:
    """Extract (vendor_name, catalog_number) from an antibody context string.

    Tries parenthetical, bracket, then short-inline forms.
    Returns ('', '') when no vendor/catalog info is found.
    """
    for pattern in (_VENDOR_PAREN_RE, _VENDOR_BRACKET_RE, _VENDOR_INLINE_RE):
        for m in pattern.finditer(context):
            vendor_raw = m.group(1).strip().rstrip(',;').strip()
            cat        = m.group(2).strip()
            if len(vendor_raw) < 3 or len(cat) < 2:
                continue
            # Reject if the first word is a known antibody/descriptor word
            first_word = vendor_raw.split()[0].lower().rstrip('-')
            if first_word in _VENDOR_ANTIBODY_WORDS:
                continue
            # Reject vendor names with bracket/semicolon characters (noisy captures)
            if '[' in vendor_raw or ';' in vendor_raw:
                continue
            return vendor_raw, cat
    return '', ''


def _write_vendor_csvs(output_path: Path) -> None:
    """Generate VALIDATED_vendor.csv (→ syn26486850) and VALIDATED_vendorItem.csv (→ syn26486843).

    Parses antibody context strings for vendor names and catalog numbers.
    vendor schema:     vendorId, vendorName, vendorUrl
    vendorItem schema: vendorItemId, vendorId, resourceId, catalogNumber, catalogNumberURL
    """
    antibody_file = output_path / 'VALIDATED_antibodies.csv'
    if not antibody_file.exists():
        print('  ⏭  VALIDATED_antibodies.csv not found — skipping vendor CSVs')
        return
    try:
        with open(antibody_file, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        print(f'  ❌ Error reading antibodies: {e}')
        return

    vendor_map: dict[str, dict] = {}   # norm_name → vendor row
    vendor_items: list[dict]    = []

    for row in rows:
        context     = row.get('_context', '').strip()
        resource_id = row.get('resourceId', '').strip()
        vendor_name, cat_num = _extract_vendor_from_context(context)
        if not vendor_name or not cat_num:
            continue

        vendor_norm = re.sub(r'\s+', ' ', vendor_name.lower().strip())
        if vendor_norm not in vendor_map:
            vendor_id = 'VEN' + hashlib.sha1(vendor_norm.encode()).hexdigest()[:8]
            vendor_map[vendor_norm] = {
                'vendorId':   vendor_id,
                'vendorName': vendor_name,
                'vendorUrl':  '',
            }

        vendor_id = vendor_map[vendor_norm]['vendorId']
        item_key  = f'{vendor_norm}:{cat_num.lower()}'
        item_id   = 'VIT' + hashlib.sha1(item_key.encode()).hexdigest()[:8]
        vendor_items.append({
            'vendorItemId':     item_id,
            'vendorId':         vendor_id,
            'resourceId':       resource_id,
            'catalogNumber':    cat_num,
            'catalogNumberURL': '',
        })

    if vendor_map:
        vendor_rows = sorted(vendor_map.values(), key=lambda r: r['vendorName'])
        vendor_file = output_path / 'VALIDATED_vendor.csv'
        with open(vendor_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['vendorId', 'vendorName', 'vendorUrl'])
            writer.writeheader()
            writer.writerows(vendor_rows)
        print(f'  ✅ VALIDATED_vendor.csv: {len(vendor_rows)} unique vendors → {vendor_file}')

    if vendor_items:
        item_file = output_path / 'VALIDATED_vendorItem.csv'
        with open(item_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(
                f, fieldnames=['vendorItemId', 'vendorId', 'resourceId',
                               'catalogNumber', 'catalogNumberURL'],
            )
            writer.writeheader()
            writer.writerows(vendor_items)
        print(f'  ✅ VALIDATED_vendorItem.csv: {len(vendor_items)} vendor-resource items → {item_file}')

    if not vendor_map:
        print('  ⚠️  No vendor/catalog info found in antibody contexts')


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

        pub_id = _make_pub_id(pmid)
        res_id = _make_resource_id(_normalize_tool_name(tool_name, tool_type), tool_type)
        link_row = {
            '_pmid': pmid, '_doi': doi, '_publicationTitle': title, '_year': year,
            '_toolName': tool_name, '_toolType': tool_type, '_usageType': usage_type,
            'publicationId': pub_id, 'resourceId': res_id,
        }
        if usage_type == 'Development':
            dev_id = 'DEV' + hashlib.sha1(f'{pmid}:{tool_name}:{tool_type}'.encode()).hexdigest()[:8]
            dev_rows.append({**link_row, 'developmentId': dev_id})
            use_id = 'USE' + hashlib.sha1(f'{pmid}:{tool_name}:{tool_type}:dev'.encode()).hexdigest()[:8]
            usage_rows.append({**link_row, 'usageId': use_id})
        elif usage_type == 'Experimental Usage':
            use_id = 'USE' + hashlib.sha1(f'{pmid}:{tool_name}:{tool_type}'.encode()).hexdigest()[:8]
            usage_rows.append({**link_row, 'usageId': use_id})

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
            'publicationId':   _make_pub_id(pmid),
            'doi':             info.get('doi', '') or meta.get('doi', ''),
            'pmid':            pmid,
            'publicationTitle': info.get('title', '') or meta.get('title', ''),
            'abstract':        meta.get('abstract', ''),
            'journal':         meta.get('journal', ''),
            'publicationDate': meta.get('publicationDate', ''),
            'authors':         authors_raw,
        })

    pub_fields = ['publicationId', 'doi', 'pmid', 'publicationTitle', 'abstract',
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
        print(f"    ℹ️  publicationId/resourceId are stable hashes — replace with Synapse IDs at upsert time")


def main():
    parser = argparse.ArgumentParser(
        description='Post-filter VALIDATED_*.csv and generate pub-centric review.csv'
    )
    parser.add_argument('--output-dir', default='tool_coverage/outputs',
                        help='Directory containing VALIDATED_*.csv files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without modifying any files')
    parser.add_argument('--include-pathway-genes', action='store_true',
                        help=('Broaden the antibody NF-specificity filter to include the full '
                              'RAS/MAPK/PI3K downstream pathway, Schwann-cell markers, and '
                              'NF tumor microenvironment genes in addition to core NF disease genes. '
                              'Default: only antibodies against NF1/NF2/LZTR1/SMARCB1/SPRED1 '
                              'and their direct protein products are kept.'))
    args = parser.parse_args()
    process(args.output_dir, dry_run=args.dry_run,
            include_pathway_genes=args.include_pathway_genes)


if __name__ == '__main__':
    main()
