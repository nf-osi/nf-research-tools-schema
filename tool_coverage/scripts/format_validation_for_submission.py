#!/usr/bin/env python3
"""
Format Sonnet validation results into VALIDATED_*.csv files for Synapse submission.

This is the CONSOLIDATED formatting script that processes ALL validated tools:
1. Accepted mined tools (from validation_summary.json - tools that passed Sonnet review)
2. Missed tools (from potentially_missed_tools.csv - tools Sonnet found that mining missed)
3. Observations (from observations.csv)
4. Publications metadata
5. Usage and Development links

The output VALIDATED_*.csv files contain ALL tools that passed AI validation,
combining both mining results (filtered for false positives) and newly discovered tools.

All files follow the exact Synapse table schemas for direct upsert.
"""

import pandas as pd
import uuid
import sys
import os
import json
from pathlib import Path

# ============================================================================
# QUALITY FILTERING CONSTANTS
# ============================================================================

# Minimum confidence threshold for tools and observations (0.0-1.0 scale)
MIN_CONFIDENCE_THRESHOLD = 0.7

# Critical metadata fields required for each tool type (from tool_scoring.py)
# These are the minimum fields needed to consider a tool "complete enough" for submission
CRITICAL_FIELDS_BY_TYPE = {
    'Animal Model': ['animalModelGeneticDisorder', 'backgroundStrain', 'animalState'],
    'Cell Line': ['cellLineCategory', 'cellLineGeneticDisorder', 'cellLineManifestation'],
    'Antibody': ['targetAntigen', 'reactiveSpecies', 'hostOrganism', 'clonality'],
    'Genetic Reagent': ['insertName', 'insertSpecies', 'vectorType'],
    'Computational Tool': [],  # No critical fields required (name and type are sufficient)
    'Patient-Derived Model': ['modelSystemType', 'tumorType'],
    'Advanced Cellular Model': ['modelType', 'derivationSource'],
    'Clinical Assessment Tool': ['assessmentType', 'targetPopulation']
}

# Completeness scoring weights (matching tool_scoring.py logic)
COMPLETENESS_WEIGHTS = {
    'critical_fields': 30,  # Maximum points for critical fields
    'other_fields': 15,     # Maximum points for additional fields
    'max_completeness': 45  # Total metadata completeness points (not including observations)
}

# Completeness threshold for FILTERED_*.csv files (priority review)
# This is a percentage of filled critical fields
MIN_COMPLETENESS_FOR_PRIORITY = 0.6  # At least 60% of critical fields filled

# Generic tools that are not NF-specific and should be filtered out
GENERIC_TOOLS = {
    # Generic data analysis/statistics software
    'r', 'python', 'matlab', 'spss', 'stata', 'sas', 'excel', 'microsoft excel',
    'graphpad', 'graphpad prism', 'prism', 'prizm', 'jmp', 'jmp pro', 'origin', 'originpro',
    'microsoft access', 'access', 'filemaker',

    # Generic databases and web technologies
    'mysql', 'postgresql', 'sqlite', 'mongodb', 'oracle', 'sql server',
    'php', 'javascript', 'html', 'css', 'apache', 'nginx', 'phpmyadmin',

    # Generic literature/reference/gene databases
    'pubmed', 'medline', 'embase', 'scopus', 'web of science',
    'genecards', 'gene cards', 'omim', 'ensembl', 'ucsc genome browser',
    'ncbi', 'uniprot', 'expasy', 'string', 'kegg',
    'gene expression omnibus', 'geo', 'gene ontology', 'go',
    'umls metathesaurus', 'mesh',
    'nf data portal',  # Our own resource, not an external tool

    # Generic image analysis
    'imagej', 'fiji', 'image j', 'nih imagej', 'photoshop', 'gimp',
    'flowjo', 'metamorph', 'axiovision', 'nis elements', 'zen', 'las x',
    'cellprofiler', 'cell profiler',

    # Generic bioinformatics/computational tools
    'blast', 'ncbi blast', 'primer3', 'primer 3', 'oligo', 'vector nti',
    'cmap', 'connectivity map', 'cnvkit', 'combat', 'enrichr', 'enrich r',
    'david', 'panther', 'gsea', 'gene set enrichment analysis',
    'crispr design tool', 'crispor', 'chopchop',
    'pymol', 'chimera', 'vmd', 'rasmol', 'swiss-pdb viewer',
    'random forest', 'support vector machine', 'svm', 'neural network',
    'proteome discoverer', 'maxquant', 'mascot', 'sequest',
    'galaxy', 'cytoscape', 'igv', 'ucsc genome browser',
    'samtools', 'bedtools', 'vcftools', 'picard',
    'bowtie', 'bwa', 'star', 'hisat', 'tophat',
    'cufflinks', 'stringtie', 'kallisto', 'salmon', 'rsem',
    'gatk', 'freebayes', 'varscan', 'mutect',
    'annovar', 'vep', 'snpeff',
    'rstudio', 'jupyter', 'spyder',
    # Generic tool descriptors (not specific tool names)
    'gene expression analysis software', 'image analysis software',
    'statistical analysis software', 'ensemble classifier', 'machine learning classifier',
    'next-generation sequencing', 'ngs', 'rna-seq', 'whole exome sequencing', 'wes',

    # Generic lab equipment
    'pcr', 'real-time pcr', 'qpcr', 'rt-pcr', 'qrt-pcr', 'rt qpcr',
    'flow cytometry', 'facs', 'western blot', 'elisa',
    'microscope', 'confocal microscope', 'electron microscope',
    'nanodrop', 'spectrophotometer', 'microct', 'micro-ct',

    # Generic statistical tests (not tools)
    'chi-square test', 'chi-square', 't-test', "student's t-test", 'anova',
    'mann-whitney', 'wilcoxon', 'fisher exact', "fisher's exact test",
    'pearson correlation', 'spearman correlation', 'linear regression',
    'logistic regression', 'cox regression', 'kaplan-meier',

    # Common R/Python packages
    'ggplot2', 'dplyr', 'tidyr', 'pandas', 'numpy', 'scipy', 'matplotlib',
    'seaborn', 'plotly', 'scikit-learn', 'pytorch', 'tensorflow', 'keras',
    'bioconductor', 'limma', 'deseq2', 'edger', 'r/bioconductor',
    'upsetr', 'clusterprofiler', 'survminer', 'pheatmap', 'venndiagram',

    # Generic imaging modalities
    'mri', 'ct', 'pet', 'spect', 'ultrasound', 'x-ray',
    'volumetric mri', 'volumetric mri analysis',

    # Generic model organisms (not NF-specific)
    'zebrafish', 'danio rerio', 'drosophila', 'c. elegans', 'caenorhabditis elegans',
    'xenopus', 'yeast', 'saccharomyces cerevisiae', 'e. coli', 'escherichia coli',
    'wild-type mice', 'nude mice', 'balb/c mice', 'c57bl/6 mice', 'c57bl/6j mice',
    'scid mice', 'nod scid mice', 'nsg mice', 'athymic nude mice',

    # Common FDA-approved drugs and compounds (not NF-specific)
    'bevacizumab', 'imatinib', 'erlotinib', 'sorafenib', 'sunitinib',
    'temozolomide', 'cisplatin', 'carboplatin', 'paclitaxel', 'docetaxel',
    'doxorubicin', 'vincristine', 'cyclophosphamide', 'methotrexate',
    'bortezomib', 'capsaicin', 'hydroxyurea', 'hydroxylamine',
    # MEK inhibitors (small molecule drugs, not genetic reagents)
    'trametinib', 'selumetinib', 'cobimetinib', 'binimetinib', 'mirdametinib',
    'pd0325901', 'azd6244', 'u0126', 'lxh254',
    # Alphanumeric drug/compound codes
    'arry-142886', 'rmc-4550', 'pd-0325901', 'azd-6244',
    # Other common research compounds
    'ogerin', 'tgf-β1', 'tgf-beta1', 'tgfβ1',
    # Commercial assay kits (not genetic reagents)
    'alamarblue', 'alamarblue cell viability assay',
    'celltiter-glo', 'celltiter-glo luminescent cell viability assay',
    'celltiter 96', 'celltiter-fluor',
    'bca protein assay', 'bradford assay', 'lowry assay',
    'lactate dehydrogenase assay', 'ldh assay',
    'dual-luciferase reporter assay system',
    'click-it edu flow cytometry assay',
    'realtime-glo mt cell viability assay',
    # Generic extraction/preparation reagents
    'trizol', 'trizol reagent', 'trizol solution',
    # Growth factors, cytokines, hormones (proteins, not genetic reagents)
    'egf', 'epidermal growth factor', 'fgf', 'fibroblast growth factor',
    'vegf', 'vascular endothelial growth factor', 'pdgf', 'platelet-derived growth factor',
    'tgf-alpha', 'tgf-beta', 'transforming growth factor',
    'bmp2', 'bmp4', 'bone morphogenetic protein',
    'bdnf', 'brain-derived neurotrophic factor', 'ngf', 'nerve growth factor',
    'igf-1', 'igf-2', 'insulin-like growth factor',
    'growth hormone', 'gh', 'hgh', 'human growth hormone',
    'il-1', 'il-2', 'il-6', 'interleukin',
    # Small molecule drugs and compounds
    'lovastatin', 'simvastatin', 'atorvastatin', 'pravastatin',  # Statins
    'forskolin', 'phorbol', 'pma', 'ionomycin',  # Cell signaling modulators
    'bapta', 'bapta-am', 'egta',  # Calcium chelators
    'gleevec', 'imatinib mesylate',  # Already have imatinib
    'artesunate', 'artemisinin',  # Antimalarials
    'cantharidin',  # Protein phosphatase inhibitor
    # Cell culture supplements and matrices
    'cultrex', 'cultrex rbm', 'basement membrane extract',
    'geltrex', 'gelatin', 'poly-l-lysine', 'laminin-coated',
    # Generic drug classes (not specific drugs) - both singular and plural
    'mek inhibitor', 'mek inhibitors', 'mek/erk inhibitor', 'mek/erk inhibitors',
    'pi3k inhibitor', 'pi3k inhibitors', 'mtor inhibitor', 'mtor inhibitors',
    'egfr inhibitor', 'egfr inhibitors', 'vegf inhibitor', 'vegf inhibitors',
    'jak inhibitor', 'jak inhibitors', 'stat inhibitor', 'stat inhibitors',
    'raf inhibitor', 'raf inhibitors', 'akt inhibitor', 'akt inhibitors',
    # Generic CRISPR/gene editing tools (but NOT when part of animal model names)
    'crispr', 'crispr/cas9', 'talens', 'zinc finger nucleases',
    # Generic matrices and reagents
    'matrigel', 'collagen', 'laminin', 'fibronectin',
}

# Brand names that indicate generic tools
GENERIC_TOOL_BRANDS = [
    'ibm spss', 'graphpad', 'abi prism', 'applied biosystems', 'affymetrix',
    'illumina', 'roche', 'thermo fisher', 'life technologies', 'microsoft'
]

# Generic equipment/reagent patterns (case-insensitive regex)
GENERIC_EQUIPMENT_PATTERNS = [
    r'\bkit\b',  # Anything containing "kit"
    r'\bpackage\b',  # R/Python packages
    r'\blibrary\b',  # Software libraries
    r'flow cytometer',
    r'cytometer',  # Any cytometer
    r'\bfacs',  # FACS equipment/software
    r'facsdiva',  # BD FACSDiva software
    r'bd lsr',
    r'fortessa',
    r'lsrii',
    r'aria ii',
    r'microscop',  # Any microscopy/microscope
    r'leica',
    r'zeiss',
    r'olympus',
    r'scanner',  # Any scanner
    r'analyzer',  # Any analyzer
    r'cycler',  # Any cycler
    r'lightcycler',
    r'thermocycler',
    r'barocycler',
    r'sequencer',  # Any sequencer
    r'\belisa',
    r'\bpcr',
    r'qpcr',
    r'reagent',
    r'master mix',
    r'bigdye',  # BigDye sequencing reagents
    r'terminator.*reagent',
    r'terminator.*kit',
    r'microarray',  # Microarray platforms/equipment
    r'array platform',
    r'imaging',  # Generic imaging methods
    r'bioluminescent',
    r'fluorescent',
    r'time-lapse',
    r'dual-energy',
    r'x-ray',
    r'absorptiometry',
    r'\brna array',
    r'\bdna array',
    r'affymetrix',
    r'illumina',
    r'agilent',
]

# Programming language/environment patterns
PROGRAMMING_PATTERNS = [
    r'\br\s+environment',
    r'\br\s+version',
    r'\br\s+v\d',
    r'\br\s+\d+\.',
    r'python\s+\d+\.',
    r'bioconductor/r',
    r'\bmatlab\s+\d',
    r'programming language',
    r'software environment',
]

# Generic methodological terms (not NF-specific tools)
GENERIC_METHODS = {
    'microarray platform', 'biophysical model', 'rna microarray', 'dna microarray',
    'bioluminescent imaging', 'fluorescent imaging', 'time-lapse microscopy',
    'dual-energy x-ray absorptiometry', 'dexa', 'confocal imaging', 'electron microscopy',
    'flow cytometry analysis', 'western blot analysis', 'immunohistochemistry',
    'rna sequencing', 'dna sequencing', 'whole genome sequencing',
    'chromatin immunoprecipitation', 'chip-seq', 'rna-seq', 'atac-seq',
    'quantitative polymerase chain reaction', 'qpcr', 'real-time pcr', 'rt-pcr',
    'quantitative pcr', 'reverse transcription pcr',
    'mri', 'magnetic resonance imaging', 'brain mri', 'mr scan', 'mr scans', 'mri scan',
    'ct scan', 'ct scans', 'pet scan', 'pet scans',
    'echocardiogram', 'echocardiography', 'echo', 'cardiac echo',
    'ultrasound', 'sonography', 'doppler', 'ultrasound imaging',
    'surface plasmon resonance', 'spr', 'mass spectrometry',
    'gene expression analysis', 'taqman assay', 'gene expression assays',
    'cellquest', 'cellquest software',
    'sanger sequencing',
    # Generic clinical/measurement tools
    '3d photography', 'caliper', 'calipers', 'ruler', 'measuring tape',
    'photography', 'digital photography', 'clinical photography',
    'pressure pad', 'pulmonary function tests', 'symptom checklist',
    # Generic assays
    'annexin assay', 'annexin v assay', 'tunel assay', 'tunel', 'mtt assay',
    'elisa', 'elisa assay', 'western blot', 'immunoblot',
    # Generic reporter constructs
    'firefly luciferase', 'renilla luciferase', 'gfp reporter', 'rfp reporter',
    'luciferase reporter', 'luciferase reporters', 'firefly luciferase expressing lentivirus',
    'lentiviral vector', 'adenoviral vector', 'aav vector',
    # Generic CRISPR terminology (too generic without specific constructs)
    'crispr', 'crispr cas9', 'crispr-cas9', 'crispr/cas9',
    'crispr guides',  # Generic term without specific target
}

# NF-relevant genes and proteins for antibody filtering
# Only antibodies targeting these proteins are considered NF-specific
NF_RELEVANT_GENES = {
    # Core NF genes
    'nf1', 'neurofibromin', 'nf2', 'merlin', 'schwannomin', 'lztr1', 'spred1',
    'smarcb1', 'ini1', 'baf47', 'snf5', 'suz12', 'eed',

    # RAS/MAPK pathway (NF1 pathway)
    'kras', 'k-ras', 'nras', 'n-ras', 'hras', 'h-ras',
    'raf', 'braf', 'b-raf', 'craf', 'c-raf', 'araf',
    'mek', 'mek1', 'mek2', 'map2k1', 'map2k2',
    'erk', 'erk1', 'erk2', 'mapk1', 'mapk3', 'p-erk', 'phospho-erk',

    # PI3K/AKT/mTOR pathway
    'mtor', 'p-mtor', 'phospho-mtor', 'raptor', 'rictor',
    's6', 'p-s6', 'phospho-s6', 'p70s6k', '4ebp1', '4e-bp1',

    # Hippo pathway (NF2/Merlin pathway)
    'yap', 'yap1', 'taz', 'wwtr1', 'lats', 'lats1', 'lats2',
    'mst1', 'mst2', 'stk3', 'stk4', 'sav1',

    # Growth factor receptors relevant to NF
    'egfr', 'erbb2', 'erbb3', 'erbb4', 'her2', 'her3',
    'met', 'c-met', 'pdgfra', 'pdgfrb', 'kit', 'c-kit', 'cd117',
    'igf1r', 'insr',

    # Schwann cell and neural markers
    's100', 's100b', 's100a', 'sox10', 'sox9', 'sox2',
    'gfap', 'nestin', 'olig2', 'olig1',
    'mpz', 'p0', 'pmp22', 'mbp', 'mag', 'cnp', 'gap43',
    'ngfr', 'p75', 'p75ntr', 'cd271',

    # Cell cycle and tumor suppressors relevant to NF
    'tp53', 'p53', 'cdkn2a', 'p16', 'p14arf', 'cdkn2b', 'p15',
    'rb', 'rb1', 'prb', 'cdkn1a', 'p21', 'cdkn1b', 'p27',

    # MPNST and malignancy markers
    'h3k27me3', 'ezh2', 'atrx', 'daxx',

    # Proliferation markers
    'ki67', 'ki-67', 'mki67', 'pcna', 'phh3', 'phospho-histone h3',

    # Apoptosis markers (when studying NF tumors)
    'cleaved caspase-3', 'cleaved caspase 3', 'caspase-3', 'caspase 3',
    'cleaved parp', 'parp',

    # Angiogenesis (relevant to NF tumors)
    'vegf', 'vegfa', 'vegfr2', 'kdr', 'flk1', 'cd31', 'pecam1',

    # Immune markers (relevant to NF tumor microenvironment)
    'cd68', 'cd163', 'cd206', 'iba1', 'aif1',  # Macrophages
    'cd3', 'cd4', 'cd8',  # T cells (when studying NF tumors)
    'pd-l1', 'cd274', 'pd1', 'pdcd1',

    # Matrix and ECM (relevant to neurofibromas)
    'collagen i', 'collagen 1', 'col1a1', 'col1a2',
    'fibronectin', 'fn1', 'laminin',

    # Ras regulators
    'gap', 'spred', 'sos', 'gef',
}

# Exceptions - these contain generic patterns but are actually specific NF tools
GENERIC_EXCEPTIONS = {
    'kit antibody',  # c-kit protein antibody (specific to NF)
    'cd117/c-kit antibody',  # c-kit protein antibody (specific to NF)
    'c-kit antibody',
}

# Generic antibody targets (common proteins, not NF-specific)
GENERIC_ANTIBODY_TARGETS = {
    'akt', 'p-akt', 'phospho-akt', 'gapdh', 'beta-actin', 'b-actin', 'α-actin',
    'tubulin', 'alpha-tubulin', 'beta-tubulin', 'histone', 'histone h3',
    'bcl-2', 'bcl2', 'bax', 'bad', 'bid', 'mcl-1', 'bcl-xl',
    'erk', 'p-erk', 'phospho-erk', 'erk1/2', 'p42/44 mapk',
    'mek', 'p38', 'jnk', 'stat3', 'stat5', 'p-stat3', 'phospho-stat3',
    'nf-kb', 'nf-κb', 'ikb', 'p65', 'p50',
    'pi3k', 'mtor', 'p-mtor', 'phospho-mtor', 'pten',
    'egfr', 'her2', 'erbb2', 'vegf', 'vegfr', 'pdgfr', 'fgfr', 'fgfr1', 'fgfr2',
    'cd3', 'cd4', 'cd8', 'cd19', 'cd20', 'cd31', 'cd34', 'cd45', 'cd68', 'cd163',
    'ki67', 'ki-67', 'pcna', 'brdu', 'edu',
    'cleaved caspase-3', 'caspase-3', 'caspase 3', 'cleaved parp',
    'p53', 'p21', 'p27', 'cyclin d1', 'cyclin e', 'cdk4', 'cdk6',
    'vimentin', 'e-cadherin', 'n-cadherin', 'zo-1', 'claudin',
    'collagen', 'fibronectin', 'laminin', 'integrin',
    'aldh', 'aldh1a1', 'sox2', 'oct4', 'nanog',
    'gfp', 'rfp', 'flag', 'ha', 'myc', 'v5', 'his',  # Epitope tags
    'igg', 'igm', 'iga', 'ige',  # Immunoglobulins
}

# Fluorophore conjugates (not specific tools)
FLUOROPHORE_CONJUGATES = [
    'alexa fluor', 'alexa', 'fitc', 'pe', 'apc', 'percp', 'pacific blue',
    'dylight', 'cy3', 'cy5', 'cy7', 'tritc', 'rhodamine', 'texas red',
    'brilliant violet', 'pacific orange', 'qdot',
]

# Common cancer and generic cell lines (not NF-specific)
GENERIC_CELL_LINES = {
    # HEK cell lines (kidney) - including specialized variants
    'hek293', 'hek-293', 'hek 293', '293t', '293-t', 'hek293t', 'hek-293t', 'hek 293t',
    '293ft', '293 cells', 'hek293 cells', '293t cells', 'hek 293t cells', 'hek293t cells',
    'hek293 cell line', 'hek293 t-rex', 'hek293 t-rex flp-in',
    '293t lenti-x cells', 'lenti-x 293t', '293ft packaging cells',

    # Breast cancer cell lines
    'mda-mb-231', 'mda mb 231', 'mda-mb-231 cells', 'mcf7', 'mcf-7', 't47d', 'bt-474', 'sk-br-3',
    'mcf10a', 'mcf-10a', 'mda-mb-468', 'hs578t',

    # Glioblastoma cell lines
    'u87', 'u-87', 'u87mg', 'u-87mg', 'u87-mg',
    'u251', 'u-251', 'u251mg', 'u-251mg', 'u251-mg',
    'a172', 't98g', 'ln229',
    'u87 glioblastoma cells', 'u87 cells',

    # Cervical cancer
    'hela', 'hela cells', 'siha', 'caski',

    # Other common cancer cell lines
    'a549', 'h1299', 'hct116', 'sw480', 'caco-2', 'caco2',
    'pc3', 'du145', 'lncap', 'k562', 'jurkat', 'raji',
    'nih3t3', 'nih 3t3', 'cos-7', 'cos7', 'cho', 'cho cells',
    'a2780', 'ovcar-3', 'skov-3', 'ags', 'bxpc-3', 'bxpc3', 'panc-1',
    '4t1', '4t1 cells', 'emt6', 'b16', 'b16f10', 'b16/f10',

    # Melanoma
    'a375', 'sk-mel-28', '501mel', 'melanoma cell lines', 'b16 melanoma',

    # Stem cells (generic)
    'human embryonic stem cells', 'hesc', 'hescs', 'ipscs', 'human ipscs',
    'embryonic stem cells', 'induced pluripotent stem cells',

    # Generic primary/immortalized cells (without specific NF mutations)
    'human meningeal cells', 'human meningeal cells (hmc)', 'meningeal cells',
    'mammary epithelial cells', 'immortalized mammary epithelial cells',
    'immortalized fibroblasts', 'immortalized schwann cells',
    'primary keratinocytes', 'primary hepatocytes', 'primary neurons',

    # Generic cell line descriptors (not specific names)
    'cultured cells', 'primary cells', 'tumor cells', 'cancer cells',
    'satellite cells', 'myoblasts', 'keratinocytes',
    'mpnst cell line', 'mpnst cell lines', 'mpnst cells',
    'glioma cell line', 'glioma cell lines', 'glioma cells',
    'schwannoma cell line', 'schwannoma cell lines',
    'neurofibroma cell line', 'neurofibroma cell lines',
}

# Generic cell type descriptors (not specific cell line names)
GENERIC_CELL_DESCRIPTORS = {
    'tumor cells', 'cancer cells', 'normal cells', 'primary cells',
    'neurons', 'astrocytes', 'endothelial cells',
    'immune cells', 'lymphocytes', 't cells', 'b cells', 'macrophages',
    'stem cells', 'progenitor cells', 'neural progenitor cells',
    'human cells', 'mouse cells', 'rat cells', 'primary human cells',
    # Generic fibroblasts/schwannoma cells without NF context
    'control fibroblasts', 'normal fibroblasts', 'normal human fibroblasts',
    'wild-type fibroblasts', 'wild type fibroblasts',
    'control schwannoma cells', 'normal schwannoma cells',
    'tumor cells of an established line',
    'primary fibroblasts',
    'primary schwannoma cells',
    'fibroblasts',
    'schwann cells',
    'schwannoma cells',
}

# Generic 3D culture methodologies (not specific named tools)
GENERIC_3D_CULTURE_METHODS = {
    'sphere culture', 'sphere culture system', 'sphere-culture system',
    'tumor spheroids', 'cancer spheroids', 'multicellular spheroids',
    '3d spheres', '3d sphere culture', '3d spheroid culture',
    '3d spheroid culture system', '3d culture system',
    'organoid culture', 'organoid culture system',
    'sphere-formation assays', 'sphere formation assay', 'spheroid assay',
    'hanging drop method', 'liquid overlay technique',
    '3d cell culture', '3d culture', 'three-dimensional culture',
}

def generate_uuid():
    """Generate a UUID for new entries."""
    return str(uuid.uuid4())


def normalize_resource_name(name):
    """
    Normalize resource name for deduplication and fuzzy matching.

    Handles:
    - Hyphenation variations (JH-2-002 vs JH002-2)
    - Common suffixes (CL, cells, mice, antibody)
    - Parentheses and separators

    Args:
        name: Resource name

    Returns:
        Normalized lowercase name for comparison
    """
    import re

    if not name or pd.isna(name):
        return ''

    name = str(name).lower().strip()

    # Remove parentheses (but keep content)
    name = name.replace('(', '').replace(')', '')

    # Remove common suffixes for cell lines and models
    suffixes_to_remove = [
        r'\s+cl$', r'\s+cells?$', r'\s+cell\s*lines?$',
        r'\s+pdx$', r'\s+mice?$', r'\s+rats?$',
        r'\s+antibody$', r'\s+ab$',
    ]
    for suffix_pattern in suffixes_to_remove:
        name = re.sub(suffix_pattern, '', name, flags=re.IGNORECASE)

    # Remove version numbers
    name = re.sub(r'\s+v?\d+(\.\d+)*$', '', name)
    name = re.sub(r'\s+version\s+\d+(\.\d+)*$', '', name)

    # For cell line codes, remove ALL separators for matching
    # This makes 'JH-2-002', 'JH 2 002' normalize to 'jh2002'
    # Only do this if the name looks like a code (mix of letters and numbers)
    if re.search(r'[a-z].*\d|\d.*[a-z]', name, re.IGNORECASE):
        # First normalize different dash types (hyphen, en-dash, em-dash)
        name = name.replace('–', '-').replace('—', '-').replace('−', '-')
        # Remove all hyphens, underscores, spaces
        name = re.sub(r'[-_\s]+', '', name)

    # Normalize remaining multiple spaces
    name = re.sub(r'\s+', ' ', name)

    return name.strip()


def create_synonym_groups(resources_df):
    """
    Group resources that are likely synonyms based on normalized names.

    Args:
        resources_df: DataFrame with resourceName column

    Returns:
        Dictionary mapping canonical name to list of synonyms
    """
    synonym_groups = {}
    normalized_to_original = {}

    for _, row in resources_df.iterrows():
        original_name = row['resourceName']
        normalized = normalize_resource_name(original_name)

        if not normalized:
            continue

        # Group by resource type to avoid false matches across types
        key = f"{row['resourceType']}:{normalized}"

        if key not in normalized_to_original:
            # First occurrence - this becomes the canonical name
            normalized_to_original[key] = original_name
            synonym_groups[key] = [original_name]
        else:
            # Additional occurrence - add as synonym
            synonym_groups[key].append(original_name)

    return synonym_groups, normalized_to_original


def is_generic_tool(tool_name, tool_type):
    """
    Check if a tool is generic (not NF-specific) and should be filtered out.

    AGGRESSIVE FILTERING to remove:
    - Generic software (ImageJ, GraphPad, R, MATLAB, SPSS, Microsoft products, etc.)
    - R/Python packages (ggplot2, PyTorch, irr, etc.)
    - Programming languages/environments (R environment, Python, Bioconductor/R)
    - Lab equipment (flow cytometers, microscopes, scanners, cyclers, etc.)
    - Generic reagents/kits (ELISA kits, PCR kits, master mixes, etc.)
    - Methodological terms (microarray platform, imaging, microscopy, etc.)

    Args:
        tool_name: Name of the tool
        tool_type: Type of tool (computational_tool, antibody, genetic_reagent, etc.)

    Returns:
        True if tool should be filtered out, False otherwise
    """
    import re

    if not tool_name or pd.isna(tool_name):
        return True

    name_lower = str(tool_name).lower().strip()

    # Check exceptions first (specific tools that contain generic patterns)
    if name_lower in GENERIC_EXCEPTIONS:
        return False

    # Check for generic tools across ALL tool types (drugs, databases, etc.)
    if name_lower in GENERIC_TOOLS:
        return True

    # Check for generic methodological terms (across all tool types)
    # Use exact match for methods set
    if name_lower in GENERIC_METHODS:
        return True

    # Also check if any generic method name is CONTAINED in the tool name
    generic_method_substrings = [
        'taqman', 'cellquest', 'dexa', 'sanger seq', 'qpcr', 'real-time pcr',
        'gene expression assay', 'surface plasmon', 'mass spec', 'cytometry software'
    ]
    for substring in generic_method_substrings:
        if substring in name_lower:
            return True

    # Filter computational tools AGGRESSIVELY
    if tool_type == 'computational_tool':
        # Check exact match against known generic tools
        if name_lower in GENERIC_TOOLS:
            return True

        # Check for programming language/environment references
        for pattern in PROGRAMMING_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return True

        # Check if it contains a generic tool brand name
        for brand in GENERIC_TOOL_BRANDS:
            if brand in name_lower:
                return True

        # Check if it's a version-specific name of a generic tool
        for generic in GENERIC_TOOLS:
            # Match "tool name", "tool name vX", "tool name version X", etc.
            if name_lower == generic or \
               name_lower.startswith(generic + ' ') or \
               name_lower.startswith(generic + ' v') or \
               re.match(rf'^{re.escape(generic)}\s+\d+', name_lower):
                return True

        # Check for R/Python package indicators
        if 'package' in name_lower or 'library' in name_lower:
            # Filter if it mentions being a package/library
            return True

        # Check for common R packages (case-insensitive suffix matching)
        for pkg in ['ggplot2', 'dplyr', 'tidyr', 'pandas', 'numpy', 'scipy',
                    'matplotlib', 'seaborn', 'pytorch', 'tensorflow', 'keras',
                    'limma', 'deseq', 'edger']:
            if pkg in name_lower:
                return True

        # Check for generic equipment patterns
        for pattern in GENERIC_EQUIPMENT_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return True

        # Check for MATLAB toolboxes
        if 'matlab' in name_lower:
            return True

        # Check for ImageJ (any variant)
        if 'imagej' in name_lower or 'image j' in name_lower:
            return True

        # Check for Microsoft products
        if 'microsoft' in name_lower or name_lower.startswith('ms '):
            return True

    # Filter genetic reagents (kits, common reagents, generic vectors)
    elif tool_type == 'genetic_reagent':
        # Check for NF-specific context first (used by multiple filters below)
        has_nf_context = any(term in name_lower for term in [
            'nf1', 'nf2', 'neurofibromin', 'merlin', 'neurofibroma', 'schwannoma', 'mpnst'
        ])

        # Filter items that are definitely NOT genetic reagents (misclassified by tool type)
        # These are behavioral/clinical assessment tools
        behavioral_tests = ['rotarod', 'rotarod apparatus', 'rotating rod', 'rota-rod']
        if name_lower in behavioral_tests:
            return True

        # Check for kit/reagent patterns
        for pattern in GENERIC_EQUIPMENT_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return True

        # Filter small molecule drugs/compounds (not genetic reagents)
        # These are chemical compounds that alter protein activity, not genetic material
        drug_suffixes = [
            r'metinib$',  # MEK inhibitors: trametinib, selumetinib, cobimetinib, etc.
            r'tinib$',    # Kinase inhibitors: imatinib, erlotinib, sunitinib, etc.
            r'mab$',      # Monoclonal antibodies: bevacizumab, cetuximab, etc.
            r'ciclib$',   # CDK inhibitors: palbociclib, ribociclib, etc.
        ]
        for suffix_pattern in drug_suffixes:
            if re.search(suffix_pattern, name_lower):
                return True

        # Filter alphanumeric compound codes (pharmaceutical research compounds)
        # Pattern: uppercase letters + dash + digits (e.g., "ARRY-142886", "RMC-4550")
        # Pattern: uppercase letters + digits (e.g., "PD0325901", "AZD6244", "U0126")
        # But keep if it has NF-specific context
        if not has_nf_context:
            compound_patterns = [
                r'^[A-Z]{2,5}-\d{3,6}$',      # e.g., ARRY-142886, RMC-4550, AZD-6244
                r'^[A-Z]{1,3}\d{4,7}$',       # e.g., PD0325901, AZD6244, U0126
                r'^[A-Z]{2,4}-[A-Z]-?\d{3,6}$',  # e.g., GDC-X-1234
            ]
            for pattern in compound_patterns:
                if re.match(pattern, tool_name):  # Use original case
                    return True

        # Filter standalone CRISPR/Cas9 tools (not when part of specific constructs with NF context)
        if not has_nf_context:
            # Filter standalone CRISPR/Cas9 tools
            if name_lower in ['cas9', 'crispr', 'crispr/cas9', 'crispr-cas9']:
                return True

        # Filter assay kits and reagents (NOT genetic reagents)
        # Exception: "reporter assay" constructs with NF genes ARE genetic reagents
        if 'assay' in name_lower:
            # Keep if it's a reporter assay construct (e.g., "NF1 luciferase reporter assay")
            is_reporter_construct = any(term in name_lower for term in [
                'reporter construct', 'reporter plasmid', 'reporter vector'
            ])
            if not is_reporter_construct:
                # Filter assays: cell viability, protein, biochemical, flow cytometry, etc.
                return True

        # Filter small molecule inhibitors (drugs, not genetic reagents)
        # Exception: keep if it's clearly a genetic construct (e.g., "NF1 inhibitor construct")
        if 'inhibitor' in name_lower:
            # Keep if it's a genetic construct for inhibition (e.g., shRNA, siRNA construct)
            is_genetic_inhibitor = any(term in name_lower for term in [
                'construct', 'plasmid', 'vector', 'shrna', 'sirna'
            ])
            if not is_genetic_inhibitor:
                # Filter chemical inhibitors: kinase inhibitors, transferase inhibitors, etc.
                return True

        # Filter "luciferase reporters" that are just the protein/assay, not genetic constructs
        if 'luciferase' in name_lower and 'reporter' in name_lower:
            # Keep if explicitly a construct/plasmid/vector
            is_construct = any(term in name_lower for term in [
                'construct', 'plasmid', 'vector', 'transgenic', 'knock-in'
            ])
            if not is_construct and not has_nf_context:
                # Likely just referring to the assay/protein, not the genetic construct
                return True

        # Filter cell viability/proliferation reagents (not genetic reagents)
        viability_reagents = [
            'celltiter', 'cell titer', 'alamarblue', 'mtt assay', 'xtt assay',
            'wst-1', 'wst-8', 'resazurin', 'presto blue', 'calcein',
            'cell viability', 'cell proliferation', 'cytotoxicity'
        ]
        for reagent in viability_reagents:
            if reagent in name_lower:
                return True

        # Filter generic extraction/purification reagents (not genetic reagents)
        extraction_reagents = [
            'trizol', 'qiazol', 'dnazol', 'phenol-chloroform',
            'extraction kit', 'purification kit', 'isolation kit',
            'saliva kit', 'oragene', 'blood collection'
        ]
        for reagent in extraction_reagents:
            if reagent in name_lower:
                return True

        # Filter protein/biochemical assays (not genetic reagents)
        biochem_assays = [
            'bca assay', 'bradford assay', 'lowry assay', 'protein assay',
            'elisa', 'western blot', 'immunoblot', 'immunoprecipitation',
            'co-ip', 'chip assay', 'emsa'
        ]
        for assay in biochem_assays:
            if assay in name_lower:
                return True

        # Filter recombinant proteins, growth factors, hormones (not genetic reagents)
        # Exception: if it's an expression construct/plasmid FOR the protein
        protein_indicators = [
            'recombinant', 'purified protein', 'protein extract',
            'growth factor', 'growth hormone', 'cytokine',
            'chemokine', 'interleukin', 'interferon'
        ]
        is_protein = any(indicator in name_lower for indicator in protein_indicators)
        if is_protein:
            # Keep if it's a plasmid/vector for expressing the protein
            is_expression_construct = any(term in name_lower for term in [
                'plasmid', 'vector', 'construct', 'expression', 'cdna', 'orf'
            ])
            if not is_expression_construct:
                # It's the protein itself, not a genetic construct
                return True

        # Filter enzyme preparations and protease inhibitor cocktails
        enzyme_preps = [
            'protease inhibitor cocktail', 'protease inhibitors complete',
            'phosphatase inhibitor cocktail', 'rnase inhibitor',
            'dnase', 'rnase', 'proteinase k', 'trypsin', 'collagenase'
        ]
        for prep in enzyme_preps:
            if prep in name_lower:
                return True

        # For true genetic reagents (plasmids, primers, siRNA, etc.), check NF-relevance
        # Similar to antibody filtering - only keep if targeting NF-relevant genes
        # True genetic reagents include: primers, siRNA, shRNA, sgRNA, plasmids, vectors, constructs
        genetic_reagent_indicators = [
            'primer', 'sirna', 'shrna', 'sgrna', 'grna', 'guide rna',
            'plasmid', 'vector', 'construct', 'cdna', 'clone', 'orf',
            'overexpression', 'knockout', 'knockdown', 'knockin'
        ]

        is_true_genetic_reagent = any(indicator in name_lower for indicator in genetic_reagent_indicators)

        if is_true_genetic_reagent and not has_nf_context:
            # Check if targeting an NF-relevant gene
            is_nf_gene_reagent = False
            for gene in NF_RELEVANT_GENES:
                if gene in name_lower:
                    is_nf_gene_reagent = True
                    break

            # If it's a genetic reagent but doesn't target NF genes, filter it
            if not is_nf_gene_reagent:
                return True

        # Filter generic reporter constructs and vectors
        generic_constructs = [
            r'luciferase.*lentivirus', r'luciferase.*vector',
            r'gfp.*lentivirus', r'rfp.*lentivirus',
            r'^lentiviral vector$', r'^adenoviral vector$', r'^aav vector$',
        ]
        import re
        for pattern in generic_constructs:
            if re.search(pattern, name_lower):
                return True

    # Filter clinical assessment tools (generic measurement tools and assays)
    elif tool_type == 'clinical_assessment_tool':
        # Check for generic equipment patterns
        for pattern in GENERIC_EQUIPMENT_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return True

        # Filter generic measurement/imaging tools
        generic_clinical_tools = [
            r'caliper[s]?$', r'^ruler$', r'^measuring tape$',  # Catches "digital calipers"
            r'^photography$', r'3d photography$', r'^clinical photography$',
            r'^mri$', r'^brain mri$', r'^ct scan$', r'^pet scan$',
            r'^ultrasound$', r'^x-ray$',
            r'annexin.*assay', r'tunel assay', r'mtt assay',
        ]
        import re
        for pattern in generic_clinical_tools:
            if re.search(pattern, name_lower):
                return True

    # Filter advanced cellular models (generic culture methods)
    elif tool_type == 'advanced_cellular_model':
        # Check against generic 3D culture methodologies
        if name_lower in GENERIC_3D_CULTURE_METHODS:
            return True

        # Check for generic culture method patterns
        generic_culture_patterns = [
            r'^sphere culture', r'^3d sphere', r'^spheroid culture',
            r'^organoid culture$', r'^3d culture$',
            r'sphere.formation assay', r'spheroid assay',
        ]
        import re
        for pattern in generic_culture_patterns:
            if re.search(pattern, name_lower):
                return True

        # Keep if it has a specific name or NF context
        has_specific_name = any(term in name_lower for term in [
            'nf1', 'nf2', 'neurofibromasphere', 'schwannoma', 'neurofibroma',
            'tame chip', 'microtissue', 'slice model', 'slice culture',
            'pellet culture', 'rbm overlay'  # specific methods with names
        ])

        # If no specific name and it's just a generic methodology, filter it
        if not has_specific_name:
            # Check if it's just describing a generic method
            if any(term in name_lower for term in ['system', 'method', 'assay', 'technique']):
                # Likely a generic methodology description
                return True

    # Filter antibodies - ONLY keep if targeting NF-relevant proteins
    elif tool_type == 'antibody':
        # First check if it's just a fluorophore conjugate or secondary antibody
        for fluor in FLUOROPHORE_CONJUGATES:
            if fluor in name_lower:
                # If it starts with fluorophore name, it's generic
                if name_lower.startswith(fluor):
                    return True

        # Generic secondary antibodies
        generic_secondary = ['goat anti-rabbit', 'goat anti-mouse', 'donkey anti-goat',
                            'rabbit anti-goat', 'mouse anti-rabbit', 'anti-rabbit igg',
                            'anti-mouse igg', 'anti-goat igg', 'secondary antibody',
                            'rabbit igg', 'mouse igg', 'goat igg']
        for secondary in generic_secondary:
            if secondary in name_lower:
                return True

        # Check if antibody targets an NF-relevant protein
        # Extract potential target from antibody name
        is_nf_relevant = False
        for gene in NF_RELEVANT_GENES:
            # Check if the gene/protein name is in the antibody name
            # Handle common antibody naming patterns:
            # "anti-NF1", "NF1 antibody", "p-ERK", "phospho-ERK antibody"
            if gene in name_lower:
                is_nf_relevant = True
                break

        # If not targeting any NF-relevant protein, filter it out
        if not is_nf_relevant:
            return True

    # Filter cell lines (generic cancer cell lines and descriptors)
    elif tool_type == 'cell_line':
        # FIRST: Check if it has NF-specific modifications/engineering
        # Keep NF-engineered cell lines even if based on generic lines
        has_nf_modification = any(term in name_lower for term in [
            'nf1', 'nf2', 'nf-1', 'nf-2', 'neurofibromin', 'merlin', 'schwannomin',
            'neurofibroma', 'mpnst', 'plexiform', 'cnf', 'pnf',
            'nf1-null', 'nf2-null', 'nf1-deficient', 'nf2-deficient',
            'nf1-/-', 'nf2-/-', 'nf1+/-', 'nf2+/-',
        ])

        # If it has NF modifications, keep it regardless of base cell line
        if has_nf_modification:
            return False  # Don't filter

        # Now check if it's a generic cell line (without NF modifications)
        if name_lower in GENERIC_CELL_LINES:
            return True

        # Check for generic cell line patterns (with variations)
        name_normalized = name_lower.replace(' ', '').replace('-', '').replace('_', '')
        for generic in GENERIC_CELL_LINES:
            generic_normalized = generic.replace(' ', '').replace('-', '').replace('_', '')
            if name_normalized == generic_normalized:
                return True

        # Check if it's a generic cell type descriptor
        if name_lower in GENERIC_CELL_DESCRIPTORS:
            return True

        # Filter generic cell line descriptors (e.g., "MPNST cell line", "glioma cells")
        # These are too vague - we need specific cell line names
        generic_descriptors = [
            r'^mpnst cell line[s]?$', r'^mpnst cells?$',
            r'^schwannoma cell line[s]?$', r'^schwannoma cells?$',
            r'^glioma cell line[s]?$', r'^glioma cells?$',
            r'^neurofibroma cell line[s]?$', r'^neurofibroma cells?$',
            r'^tumor cell line[s]?$', r'^cancer cell line[s]?$',
        ]
        import re
        for pattern in generic_descriptors:
            if re.match(pattern, name_lower):
                return True

        # Check for other NF-specific context (patient-derived, specific names)
        has_nf_context = any(term in name_lower for term in [
            'patient-derived', 'patient derived', 'patient derived from'
        ])

        # If it's a generic term with numbers/codes, keep it (likely a specific line)
        # e.g., "MPNST724", "S462", "STS26T"
        has_specific_identifier = bool(re.search(r'\d', name_lower))

        if not has_nf_context and not has_specific_identifier:
            # Without NF context or specific identifier, filter generic descriptors
            generic_prefixes = ['control ', 'normal ', 'wild-type ', 'wild type ', 'wt ']
            for prefix in generic_prefixes:
                if name_lower.startswith(prefix):
                    return True

            # Filter standalone generic cell type names
            standalone_generic = ['fibroblasts', 'schwann cells', 'schwannoma cells',
                                'neurons', 'astrocytes', 'tumor cells', 'cultured cells']
            if name_lower in standalone_generic:
                return True

    # Filter animal models (generic strains without NF mutations)
    elif tool_type == 'animal_model':
        # Check if it has NF-specific context
        has_nf_context = any(term in name_lower for term in [
            'nf1', 'nf2', 'nf-1', 'nf-2', 'neurofibromin', 'merlin',
            'neurofibroma', 'schwannoma', 'mpnst', 'opg', 'plexiform'
        ])

        # If no NF context, filter generic model organisms
        if not has_nf_context:
            generic_organisms = [
                'wild-type', 'wild type', 'wt mice', 'wt control mice', 'control mice',
                'nude mice', 'balb/c', 'c57bl/6', 'nod scid', 'nsg mice', 'athymic nude',
                # Generic rat strains
                'sprague dawley', 'sprague-dawley', 'wistar rats', 'fischer rats',
                'long-evans rats', 'lewis rats',
                # Generic amphibian models
                'frog oocytes', 'xenopus oocytes', 'zebrafish', 'danio rerio',
                # Other generic organisms
                'drosophila', 'xenopus', 'yeast', 'c. elegans', 'caenorhabditis elegans'
            ]
            for organism in generic_organisms:
                if organism in name_lower:
                    return True

            # Filter generic descriptive terms (too vague without specific strain info)
            generic_descriptors = [
                r'^transgenic mouse model$',
                r'^transgenic mouse models$',
                r'^transgenic mouse line[s]?$',
                r'^transgenic mouse embryos$',
                r'^xenograft mouse model$',
                r'^xenograft model$',
                r'^mouse xenograft$',
                r'^tumor xenograft$',
                r'^patient.*xenograft$',  # But "patient-derived xenograft from NF1 patient" would have NF context
            ]
            import re
            for pattern in generic_descriptors:
                if re.match(pattern, name_lower):
                    return True

            # Filter Cas9-expressing strains without NF context
            # These are generic genome-editing tool carriers, not NF-specific models
            if 'cas9' in name_lower and not has_nf_context:
                return True

    return False


def is_nf_relevant_publication(pmid, pub_metadata, context_snippet=''):
    """
    Check if a publication is sufficiently relevant to neurofibromatosis research.

    Filters out publications that only mention NF in passing.

    Args:
        pmid: PubMed ID (cleaned, without "PMID:" prefix)
        pub_metadata: Dictionary mapping PMID to publication metadata
        context_snippet: Optional context snippet from the publication (abstract, methods)

    Returns:
        True if publication is NF-relevant, False otherwise
    """
    pub_info = pub_metadata.get(pmid, {})
    title = pub_info.get('title', '').lower()

    # NF-related terms to check
    nf_terms = [
        'neurofibromatosis', 'neurofibroma', 'schwannoma', 'schwannomatosis',
        'nf1', 'nf2', 'nf-1', 'nf-2', 'neurofibromin', 'merlin',
        'mpnst', 'plexiform', 'optic pathway glioma', 'opg',
        'recklinghausen', 'von recklinghausen'
    ]

    # Check if title mentions NF (strong signal of relevance)
    title_mentions = sum(1 for term in nf_terms if term in title)
    if title_mentions > 0:
        return True

    # If no NF in title, check context snippet for multiple mentions
    if context_snippet:
        context_lower = context_snippet.lower()
        context_mentions = sum(1 for term in nf_terms if term in context_lower)

        # Require at least 2 mentions if not in title
        if context_mentions >= 2:
            return True

    # Filter out publications with minimal NF context
    return False


# ============================================================================
# QUALITY FILTERING FUNCTIONS
# ============================================================================

def has_minimum_critical_fields(tool_row, tool_type):
    """
    Check if a tool has the minimum critical fields required for its type.

    Args:
        tool_row: DataFrame row or dict with tool metadata
        tool_type: Type of tool (e.g., 'Antibody', 'Cell Line')

    Returns:
        Tuple of (has_minimum, filled_count, total_count, missing_fields)
    """
    critical_fields = CRITICAL_FIELDS_BY_TYPE.get(tool_type, [])

    if not critical_fields:
        # No critical fields required for this type
        return True, 0, 0, []

    filled_count = 0
    missing_fields = []

    for field in critical_fields:
        value = tool_row.get(field)
        # Check if field is filled (not None, not empty string, not "NULL")
        if pd.notna(value) and value != "" and value != "NULL":
            filled_count += 1
        else:
            missing_fields.append(field)

    total_count = len(critical_fields)
    # Require at least 1 critical field to be filled (or all if only 1-2 fields total)
    minimum_required = max(1, int(total_count * 0.5))  # At least 50% of critical fields
    has_minimum = filled_count >= minimum_required

    return has_minimum, filled_count, total_count, missing_fields


def calculate_completeness_score(tool_row, tool_type):
    """
    Calculate metadata completeness score for a tool (0-45 points).

    Based on tool_scoring.py logic:
    - Critical fields: 30 points (distributed evenly)
    - Other fields: 15 points (distributed evenly)

    Args:
        tool_row: DataFrame row or dict with tool metadata
        tool_type: Type of tool

    Returns:
        Tuple of (completeness_score, critical_score, missing_critical_fields)
    """
    critical_fields = CRITICAL_FIELDS_BY_TYPE.get(tool_type, [])

    # Calculate critical fields score (30 points max)
    critical_score = 0
    missing_critical = []
    if critical_fields:
        filled_critical = 0
        for field in critical_fields:
            value = tool_row.get(field)
            if pd.notna(value) and value != "" and value != "NULL":
                filled_critical += 1
            else:
                missing_critical.append(field)
        critical_score = (filled_critical / len(critical_fields)) * 30

    # For now, we don't score "other fields" since we'd need to define them per type
    # Just use critical fields score
    completeness_score = critical_score

    return completeness_score, critical_score, missing_critical


def filter_by_confidence(df, confidence_col='confidence', threshold=MIN_CONFIDENCE_THRESHOLD):
    """
    Filter DataFrame to only include rows meeting confidence threshold.

    Args:
        df: DataFrame with tools/observations
        confidence_col: Name of confidence column
        threshold: Minimum confidence (0.0-1.0)

    Returns:
        Filtered DataFrame
    """
    if confidence_col not in df.columns:
        print(f"   ⚠️  Warning: {confidence_col} column not found - skipping confidence filtering")
        return df

    before_count = len(df)
    # Handle confidence as either float or string
    df[confidence_col] = pd.to_numeric(df[confidence_col], errors='coerce')
    filtered_df = df[df[confidence_col] >= threshold].copy()
    after_count = len(filtered_df)
    filtered_count = before_count - after_count

    if filtered_count > 0:
        print(f"   - Filtered {filtered_count} items below confidence threshold {threshold}")

    return filtered_df


def filter_for_priority_review(tools_df):
    """
    Filter tools to high-completeness subset for priority manual review.

    Criteria:
    - Confidence >= 0.7 (already applied)
    - At least 60% of critical fields filled

    Args:
        tools_df: DataFrame with all validated tools

    Returns:
        DataFrame with high-completeness tools for priority review
    """
    priority_tools = []

    for idx, row in tools_df.iterrows():
        tool_type = row.get('toolType', '')

        # Calculate completeness
        has_min, filled, total, missing = has_minimum_critical_fields(row, tool_type)

        if total > 0:
            completeness_pct = filled / total
            if completeness_pct >= MIN_COMPLETENESS_FOR_PRIORITY:
                priority_tools.append(row)
        else:
            # No critical fields required - include by default
            priority_tools.append(row)

    priority_df = pd.DataFrame(priority_tools)
    return priority_df


def load_publication_metadata(validation_summary_file):
    """
    Load publication metadata from validation_summary.json.

    Creates a lookup table: PMID -> {doi, title, journal, year}

    Returns:
        Dictionary mapping PMID to publication metadata
    """
    pub_metadata = {}

    if not os.path.exists(validation_summary_file):
        return pub_metadata

    with open(validation_summary_file, 'r') as f:
        validation_data = json.load(f)

    for pub in validation_data:
        pmid = pub.get('pmid', '')
        if pmid:
            # Remove "PMID:" prefix if present
            pmid_clean = pmid.replace('PMID:', '').strip()
            pub_metadata[pmid_clean] = {
                'doi': pub.get('doi', ''),
                'title': pub.get('title', ''),
                'publicationType': pub.get('publicationType', ''),
            }

    return pub_metadata


def filter_computational_tools_by_development(tools_df, pub_metadata):
    """
    Filter computational tools to only keep those from development publications.

    Development publications typically have the tool name in the title.
    This ensures we only capture novel/specific computational tools rather than
    generic software used in analysis.

    Args:
        tools_df: DataFrame with validated tools
        pub_metadata: Dictionary mapping PMID to publication metadata

    Returns:
        Filtered DataFrame with only computational tools from development papers
    """
    if tools_df.empty:
        return tools_df

    # Separate computational tools from other types
    comp_tools = tools_df[tools_df['toolType'] == 'computational_tool'].copy()
    other_tools = tools_df[tools_df['toolType'] != 'computational_tool'].copy()

    if comp_tools.empty:
        return other_tools

    print(f"   Checking {len(comp_tools)} computational tools for development publications...")

    kept_tools = []
    filtered_count = 0

    for _, tool in comp_tools.iterrows():
        tool_name = tool['toolName']
        pmid = str(tool['pmid']).replace('PMID:', '').strip()

        # Get publication title
        pub_info = pub_metadata.get(pmid, {})
        title = pub_info.get('title', '').lower()

        if not title:
            # No title available - filter it out to be conservative
            filtered_count += 1
            continue

        # Check if tool name (or significant part of it) appears in title
        tool_name_lower = tool_name.lower()

        # Extract key terms from tool name (ignore version numbers, common words)
        tool_name_clean = tool_name_lower
        # Remove version numbers
        import re
        tool_name_clean = re.sub(r'\s+v?\d+(\.\d+)*', '', tool_name_clean)
        tool_name_clean = re.sub(r'\s+version\s+\d+', '', tool_name_clean)

        # Check if tool name appears in title
        # Priority 1: Exact match (most reliable)
        if tool_name_lower in title or tool_name_clean in title:
            kept_tools.append(tool)
            continue

        # Priority 2: For multi-word tool names, check if most words are present
        tool_words = [w for w in tool_name_clean.split() if len(w) > 3]

        if len(tool_words) == 0:
            # Single short word - require exact match (already checked above)
            filtered_count += 1
            continue

        # Check if significant portion of tool name is in title
        matches = sum(1 for word in tool_words if word in title)
        match_ratio = matches / len(tool_words) if tool_words else 0

        # For multi-word names, require at least 75% of words in title
        # AND at least 2 words matching (to avoid false positives)
        if match_ratio >= 0.75 and matches >= 2:
            kept_tools.append(tool)
        else:
            filtered_count += 1

    print(f"   Kept {len(kept_tools)} computational tools from development publications")
    print(f"   Filtered {filtered_count} computational tools (usage-only, not development)")

    # Combine kept computational tools with other tool types
    kept_comp_df = pd.DataFrame(kept_tools) if kept_tools else pd.DataFrame()

    if not kept_comp_df.empty and not other_tools.empty:
        return pd.concat([other_tools, kept_comp_df], ignore_index=True)
    elif not kept_comp_df.empty:
        return kept_comp_df
    else:
        return other_tools


def load_accepted_tools(validation_summary_file, pub_metadata):
    """
    Load accepted tools from validation_summary.json.

    These are tools that were mined and then validated by Sonnet as real tools
    (false positives removed).

    Args:
        validation_summary_file: Path to validation_summary.json
        pub_metadata: Dictionary mapping PMID to publication metadata

    Returns:
        DataFrame with columns: toolName, toolType, pmid, confidence, contextSnippet, etc.
    """
    if not os.path.exists(validation_summary_file):
        print(f"⚠️  {validation_summary_file} not found - skipping accepted mined tools")
        return pd.DataFrame()

    with open(validation_summary_file, 'r') as f:
        validation_data = json.load(f)

    accepted_tools = []

    for pub in validation_data:
        pmid = pub.get('pmid', '').replace('PMID:', '').strip()
        metadata = pub_metadata.get(pmid, {})

        # Extract accepted tools from this publication
        for tool in pub.get('acceptedTools', []):
            tool_name = tool.get('toolName')
            tool_type = tool.get('toolType')

            # Skip generic tools
            if is_generic_tool(tool_name, tool_type):
                continue

            accepted_tools.append({
                'toolName': tool_name,
                'toolType': tool_type,
                'foundIn': tool.get('foundIn', 'methods'),
                'contextSnippet': tool.get('usageContext', ''),
                'confidence': tool.get('confidence', 0.9),
                'pmid': pmid,
                'doi': metadata.get('doi', ''),
                'publicationTitle': metadata.get('title', ''),
                'reasoning': tool.get('reasoning', ''),
                'whyMissed': '',  # Not applicable - this was mined successfully
                'shouldBeAdded': True,  # Already validated as accepted
                'source': 'mined_and_validated'
            })

    return pd.DataFrame(accepted_tools)


def format_validated_tools(tools_df):
    """
    Format validated tools by type.

    Args:
        tools_df: DataFrame from potentially_missed_tools.csv filtered for shouldBeAdded=True

    Returns:
        Dictionary mapping tool type to formatted DataFrames
    """
    tool_dfs = {}

    # Prepare completeness columns lookup (if available)
    completeness_cols = ['_completenessScore', '_criticalFieldsScore', '_missingCriticalFields', '_hasMinimumFields']
    has_completeness = all(col in tools_df.columns for col in completeness_cols)

    # Group by tool type
    for tool_type in tools_df['toolType'].unique():
        if pd.isna(tool_type) or tool_type == 'toolType':
            continue

        type_tools = tools_df[tools_df['toolType'] == tool_type].copy()

        if tool_type == 'computational_tool':
            formatted = format_computational_tools(type_tools)
            tool_dfs['Computational Tool'] = formatted

        elif tool_type == 'animal_model':
            formatted = format_animal_models(type_tools)
            tool_dfs['Animal Model'] = formatted

        elif tool_type == 'antibody':
            formatted = format_antibodies(type_tools)
            tool_dfs['Antibody'] = formatted

        elif tool_type == 'cell_line':
            formatted = format_cell_lines(type_tools)
            tool_dfs['Cell Line'] = formatted

        elif tool_type == 'genetic_reagent':
            formatted = format_genetic_reagents(type_tools)
            tool_dfs['Genetic Reagent'] = formatted

        elif tool_type == 'clinical_assessment_tool':
            formatted = format_clinical_assessment_tools(type_tools)
            tool_dfs['Clinical Assessment Tool'] = formatted

        elif tool_type == 'advanced_cellular_model':
            formatted = format_advanced_cellular_models(type_tools)
            tool_dfs['Advanced Cellular Model'] = formatted

        elif tool_type == 'patient_derived_model':
            formatted = format_patient_derived_models(type_tools)
            tool_dfs['Patient-Derived Model'] = formatted

        # Add completeness tracking columns if available
        # Create lookup by toolName + pmid (use original toolName from source, match with _pmid in formatted)
        if has_completeness and not formatted.empty and '_pmid' in formatted.columns:
            # Create completeness lookup: (toolName, pmid) -> completeness data
            completeness_lookup = {}
            for _, row in type_tools.iterrows():
                key = (str(row['toolName']), str(row['pmid']).replace('PMID:', '').strip())
                completeness_lookup[key] = {
                    '_completenessScore': row.get('_completenessScore', 0),
                    '_criticalFieldsScore': row.get('_criticalFieldsScore', 0),
                    '_missingCriticalFields': row.get('_missingCriticalFields', ''),
                    '_hasMinimumFields': row.get('_hasMinimumFields', True)
                }

            # Get tool name column (varies by type)
            tool_name_col = None
            if 'softwareName' in formatted.columns:
                tool_name_col = 'softwareName'
            elif 'strainNomenclature' in formatted.columns:
                tool_name_col = 'strainNomenclature'
            elif '_cellLineName' in formatted.columns:
                tool_name_col = '_cellLineName'
            elif 'insertName' in formatted.columns:
                tool_name_col = 'insertName'
            elif 'targetAntigen' in formatted.columns:
                # For antibodies, we need to reconstruct from the original toolName
                # This is tricky, so let's use _pmid + index matching instead
                tool_name_col = None

            # Add completeness columns to formatted dataframe
            if tool_name_col:
                for col in completeness_cols:
                    formatted[col] = formatted.apply(
                        lambda row: completeness_lookup.get(
                            (str(row[tool_name_col]), str(row['_pmid']).replace('PMID:', '').strip()),
                            {}
                        ).get(col, 0 if 'Score' in col else ''),
                        axis=1
                    )
            else:
                # Fallback: match by PMID + order (assuming same order)
                # Add default values for now
                for col in completeness_cols:
                    if col not in formatted.columns:
                        formatted[col] = 0 if 'Score' in col else ''

    return tool_dfs


def integrate_nf_modified_cell_lines_into_tool_dfs(tool_dfs):
    """
    Integrate NF-modified cell lines extracted from observations into tool_dfs.

    This recovers cell lines that were captured as observations (e.g., "NF1-deficient U87-MG")
    but not as separate tools during mining.

    Args:
        tool_dfs: Dictionary mapping tool type to formatted DataFrames

    Returns:
        Updated tool_dfs with integrated NF-modified cell lines
    """
    extracted_file = 'tool_coverage/outputs/nf_modified_cell_lines_from_observations.csv'

    # Check if extracted file exists
    if not Path(extracted_file).exists():
        print(f"      No extracted cell lines found at {extracted_file}")
        return tool_dfs

    # Load extracted NF-modified cell lines
    extracted_df = pd.read_csv(extracted_file)

    if len(extracted_df) == 0:
        print("      No extracted cell lines to integrate")
        return tool_dfs

    # Get existing cell lines
    if 'Cell Line' not in tool_dfs or tool_dfs['Cell Line'].empty:
        existing_cell_lines = pd.DataFrame()
    else:
        existing_cell_lines = tool_dfs['Cell Line']

    # Check for duplicates and prepare new entries
    new_entries = []
    duplicate_count = 0

    for _, row in extracted_df.iterrows():
        cell_line_name = row['_cellLineName']
        pmid = row['_pmid']

        # Check if this cell line + PMID combo already exists
        if not existing_cell_lines.empty:
            existing = existing_cell_lines[
                (existing_cell_lines['_cellLineName'] == cell_line_name) &
                (existing_cell_lines['_pmid'] == pmid)
            ]

            if len(existing) > 0:
                duplicate_count += 1
                continue

        # Create new entry matching VALIDATED_cell_lines.csv format
        new_entry = {
            'cellLineId': row['cellLineId'],
            'organ': '',
            'tissue': '',
            'donorId': '',
            'originYear': '',
            'strProfile': '',
            'cellLineManifestation': '',
            'resistance': '',
            'cellLineCategory': '',
            'contaminatedMisidentified': '',
            'cellLineGeneticDisorder': '',
            'populationDoublingTime': '',
            '_cellLineName': cell_line_name,
            '_pmid': pmid,
            '_doi': row.get('_doi', ''),
            '_publicationTitle': '',
            '_foundIn': 'observations',
            '_confidence': row['_confidence'],
            '_contextSnippet': row['_observationDetails'][:200] + '...' if len(row['_observationDetails']) > 200 else row['_observationDetails'],
            '_whyMissed': f"{row['_baseCellLine']} captured as observation, not separate tool. {row['_origin']}.",
            '_reasoning': row['_source'],
            '_source': 'Recovered from observations'
        }
        new_entries.append(new_entry)

    if len(new_entries) > 0:
        # Append to Cell Line dataframe
        new_df = pd.DataFrame(new_entries)
        if existing_cell_lines.empty:
            tool_dfs['Cell Line'] = new_df
        else:
            tool_dfs['Cell Line'] = pd.concat([existing_cell_lines, new_df], ignore_index=True)

        print(f"      ✓ Added {len(new_entries)} NF-modified cell lines from observations")
        if duplicate_count > 0:
            print(f"      ⏭️  Skipped {duplicate_count} duplicates")
    else:
        print(f"      No new cell lines to add ({duplicate_count} duplicates skipped)")

    return tool_dfs


def format_computational_tools(tools_df):
    """Format computational tools for Synapse ComputationalToolDetails table (syn73709226)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'computationalToolId': tool_id,
            'softwareName': tool['toolName'],  # Correct Synapse column name
            'softwareType': '',  # Needs manual curation
            'softwareVersion': '',
            'programmingLanguage': '',
            'sourceRepository': '',
            'documentation': '',
            'licenseType': '',
            'containerized': '',
            'dependencies': '',
            'systemRequirements': '',
            'lastUpdate': '',
            'maintainer': '',
            # Tracking fields (prefixed with _ for removal before upload)
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_animal_models(tools_df):
    """Format animal models for Synapse AnimalModelDetails table (syn26486808)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'animalModelId': tool_id,
            'strainNomenclature': tool['toolName'],
            'backgroundStrain': '',
            'backgroundSubstrain': '',
            'donorId': '',
            'transplantationDonorId': '',
            'animalModelOfManifestation': '',
            'animalModelGeneticDisorder': '',
            'transplantationType': '',
            'animalState': '',
            'generation': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_antibodies(tools_df):
    """Format antibodies for Synapse AntibodyDetails table (syn26486811)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'antibodyId': tool_id,
            'targetAntigen': tool['toolName'],
            'hostOrganism': '',
            'clonality': '',
            'cloneId': '',
            'uniprotId': '',
            'reactiveSpecies': '',
            'conjugate': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_cell_lines(tools_df):
    """Format cell lines for Synapse CellLineDetails table (syn26486823)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        # Note: Cell line table does NOT have a 'lineName' field in Synapse
        # The name goes in the Resource table
        rows.append({
            'cellLineId': tool_id,
            'organ': '',  # Required field
            'tissue': '',
            'donorId': '',
            'originYear': '',
            'strProfile': '',
            'cellLineManifestation': '',
            'resistance': '',
            'cellLineCategory': '',
            'contaminatedMisidentified': '',
            'cellLineGeneticDisorder': '',
            'populationDoublingTime': '',
            # Tracking fields
            '_cellLineName': tool['toolName'],  # Store name for Resource table
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_genetic_reagents(tools_df):
    """Format genetic reagents for Synapse GeneticReagentDetails table (syn26486832)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'geneticReagentId': tool_id,
            'insertName': tool['toolName'],
            'promoter': '',
            'vectorBackbone': '',
            'selectableMarker': '',
            'vectorType': '',
            'insertEntrezId': '',
            '5primer': '',
            'cloningMethod': '',
            'copyNumber': '',
            'insertSpecies': '',
            'nTerminalTag': '',
            'cTerminalTag': '',
            'totalSize': '',
            '5primeCloningSite': '',
            'growthTemp': '',
            'bacterialResistance': '',
            'hazardous': '',
            '3primer': '',
            '5primeSiteDestroyed': '',
            '3primeSiteDestroyed': '',
            'backboneSize': '',
            'insertSize': '',
            'growthStrain': '',
            '3primeCloningSite': '',
            'gRNAshRNASequence': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_clinical_assessment_tools(tools_df):
    """Format clinical assessment tools for Synapse ClinicalAssessmentToolDetails table (syn73709229)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        rows.append({
            'clinicalAssessmentToolId': tool_id,
            'assessmentName': tool['toolName'],  # Correct Synapse column name
            'assessmentType': '',
            'targetPopulation': '',
            'diseaseSpecific': '',
            'numberOfItems': '',
            'scoringMethod': '',
            'validatedLanguages': '',
            'psychometricProperties': '',
            'administrationTime': '',
            'availabilityStatus': '',
            'licensingRequirements': '',
            'digitalVersion': '',
            # Tracking fields
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_advanced_cellular_models(tools_df):
    """Format advanced cellular models for Synapse AdvancedCellularModelDetails table (syn73709227)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        # Note: Synapse table does NOT have 'modelName' - name goes in Resource table
        rows.append({
            'advancedCellularModelId': tool_id,
            'modelType': '',  # organoid, spheroid, etc.
            'derivationSource': '',
            'cellTypes': '',
            'organoidType': '',
            'matrixType': '',
            'cultureSystem': '',
            'maturationTime': '',
            'characterizationMethods': '',
            'passageNumber': '',
            'cryopreservationProtocol': '',
            'qualityControlMetrics': '',
            # Tracking fields
            '_modelName': tool['toolName'],  # Store name for Resource table
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_patient_derived_models(tools_df):
    """Format patient-derived models for Synapse PatientDerivedModelDetails table (syn73709228)."""
    rows = []

    for _, tool in tools_df.iterrows():
        tool_id = generate_uuid()
        # Note: Synapse table does NOT have 'modelName' - name goes in Resource table
        rows.append({
            'patientDerivedModelId': tool_id,
            'modelSystemType': '',  # PDX, PDO, etc.
            'patientDiagnosis': '',
            'hostStrain': '',
            'passageNumber': '',
            'tumorType': '',
            'engraftmentSite': '',
            'establishmentRate': '',
            'molecularCharacterization': '',
            'clinicalData': '',
            'humanizationMethod': '',
            'immuneSystemComponents': '',
            'validationMethods': '',
            # Tracking fields
            '_modelName': tool['toolName'],  # Store name for Resource table
            '_pmid': tool['pmid'],
            '_doi': tool.get('doi', ''),
            '_publicationTitle': tool.get('publicationTitle', ''),
            '_foundIn': tool['foundIn'],
            '_confidence': tool['confidence'],
            '_contextSnippet': tool['contextSnippet'],
            '_whyMissed': tool['whyMissed'],
            '_reasoning': tool.get('reasoning', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def format_resources(tool_dfs):
    """
    Format Resource table entries (syn26450069) that link to detail tables.

    Each unique resource gets ONE row, with foreign key to its detail table.
    Multiple publications using the same resource are handled in Usage table.

    NOTE: The Resources table (syn26450069) currently only has foreign key columns for
    the original 4 tool types. The new tool types need their columns added:
    - computationalToolId (STRING)
    - clinicalAssessmentToolId (STRING)
    - advancedCellularModelId (STRING)
    - patientDerivedModelId (STRING)

    Until then, these IDs are stored in tracking fields (_detailTableId, _detailTableType).

    Args:
        tool_dfs: Dictionary mapping tool type names to their detail table DataFrames

    Returns:
        DataFrame with Resource table entries (one row per unique resource)
    """
    resource_rows = []

    # Map tool types to their ID columns and resource type names
    type_mapping = {
        'Computational Tool': ('computationalToolId', 'Computational Tool'),
        'Animal Model': ('animalModelId', 'Animal Model'),
        'Antibody': ('antibodyId', 'Antibody'),
        'Cell Line': ('cellLineId', 'Cell Line'),
        'Genetic Reagent': ('geneticReagentId', 'Genetic Reagent'),
        'Clinical Assessment Tool': ('clinicalAssessmentToolId', 'Clinical Assessment Tool'),
        'Advanced Cellular Model': ('advancedCellularModelId', 'Advanced Cellular Model'),
        'Patient-Derived Model': ('patientDerivedModelId', 'Patient-Derived Model')
    }

    # Global deduplication across all tool types using normalized names
    seen_normalized = {}  # normalized_name -> (canonical_name, resource_type)
    synonym_tracking = {}  # canonical_name -> [synonyms]

    for tool_type_key, tool_df in tool_dfs.items():
        if tool_df.empty:
            continue

        id_column, resource_type = type_mapping[tool_type_key]

        # Get the name column (varies by type)
        if tool_type_key == 'Computational Tool':
            name_col = 'softwareName'
        elif tool_type_key == 'Animal Model':
            name_col = 'strainNomenclature'
        elif tool_type_key == 'Antibody':
            name_col = 'targetAntigen'
        elif tool_type_key == 'Cell Line':
            name_col = '_cellLineName'  # Special case - name in tracking field
        elif tool_type_key == 'Genetic Reagent':
            name_col = 'insertName'
        elif tool_type_key == 'Clinical Assessment Tool':
            name_col = 'assessmentName'
        elif tool_type_key in ['Advanced Cellular Model', 'Patient-Derived Model']:
            name_col = '_modelName'  # Special case - name in tracking field

        # Create resource entries (deduplicated globally using normalized names)
        for _, row in tool_df.iterrows():
            resource_name = row.get(name_col, '')
            if not resource_name or pd.isna(resource_name):
                continue

            # Normalize for deduplication
            normalized = normalize_resource_name(resource_name)
            normalized_key = f"{resource_type}:{normalized}"

            # Check if this is a duplicate (by normalized name)
            if normalized_key in seen_normalized:
                # It's a synonym - track it but don't create a new resource
                canonical_name = seen_normalized[normalized_key]
                if canonical_name not in synonym_tracking:
                    synonym_tracking[canonical_name] = []
                if resource_name != canonical_name:
                    synonym_tracking[canonical_name].append(resource_name)
                continue

            # First occurrence - create resource entry
            seen_normalized[normalized_key] = resource_name

            # Get synonyms for this resource (will be populated later)
            synonyms_list = []  # Will be filled after all resources are processed

            # Create Resource table entry
            resource_entry = {
                'resourceId': generate_uuid(),
                'resourceName': resource_name,
                'resourceType': resource_type,
                # Foreign keys to detail tables (only existing columns in syn26450069)
                'geneticReagentId': row[id_column] if id_column == 'geneticReagentId' else '',
                'antibodyId': row[id_column] if id_column == 'antibodyId' else '',
                'cellLineId': row[id_column] if id_column == 'cellLineId' else '',
                'animalModelId': row[id_column] if id_column == 'animalModelId' else '',
                'biobankId': '',
                # Fields requiring manual curation
                'rrid': '',
                'description': '',
                'synonyms': '',  # Will be populated below
                'usageRequirements': '',
                'howToAcquire': '',
                'dateAdded': '',
                'dateModified': '',
                'aiSummary': '',
                # Tracking fields (for new tool types not yet in Resources table schema)
                '_detailTableId': row[id_column],
                '_detailTableType': id_column,  # Store which type of ID this is
                '_pmid': row.get('_pmid', ''),
                '_normalized': normalized,  # For matching
                '_source': 'AI validation - Sonnet 4.5'
            }

            resource_rows.append(resource_entry)

    # Add synonyms to resources
    resources_df = pd.DataFrame(resource_rows)
    if not resources_df.empty:
        for idx, row in resources_df.iterrows():
            canonical_name = row['resourceName']
            if canonical_name in synonym_tracking:
                synonyms = synonym_tracking[canonical_name]
                resources_df.at[idx, 'synonyms'] = ', '.join(synonyms[:5])  # Limit to 5 synonyms

    return resources_df

    return pd.DataFrame(resource_rows)


def format_publications(tool_dfs):
    """
    Format Publications table entries (syn26486839) with metadata for each publication.

    Deduplicates by PMID to create one row per unique publication.

    Args:
        tool_dfs: Dictionary mapping tool type names to their detail table DataFrames

    Returns:
        DataFrame with Publication table entries (one row per unique publication)
    """
    pub_data = []

    # Collect all unique PMIDs from all tool types
    for tool_type, tool_df in tool_dfs.items():
        if tool_df.empty:
            continue

        for _, row in tool_df.iterrows():
            pmid = row.get('_pmid', '')
            if pmid and not pd.isna(pmid):
                pub_data.append({
                    'pmid': str(pmid),
                    'doi': row.get('_doi', ''),
                    'publicationTitle': row.get('_publicationTitle', '')
                })

    if not pub_data:
        return pd.DataFrame()

    # Deduplicate by PMID
    pubs_df = pd.DataFrame(pub_data)
    pubs_df = pubs_df.drop_duplicates(subset=['pmid'])

    # Format for Synapse Publications table
    pub_rows = []
    for _, pub in pubs_df.iterrows():
        pub_rows.append({
            'publicationId': generate_uuid(),
            'pmid': pub['pmid'],
            'doi': pub['doi'],
            'publicationTitle': pub['publicationTitle'],
            'abstract': '',  # Would need to fetch from PubMed
            'journal': '',
            'publicationDate': '',
            'citation': '',
            'publicationDateUnix': '',
            'authors': '',
            # Tracking field
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(pub_rows)


def format_usage_links(tool_dfs, resources_df, publications_df):
    """
    Format Usage table entries (syn26486841) linking publications to resources.

    Creates one row for each publication-resource pair.

    Args:
        tool_dfs: Dictionary of detail table DataFrames
        resources_df: DataFrame of resources
        publications_df: DataFrame of publications

    Returns:
        DataFrame with Usage table entries
    """
    usage_rows = []

    # Create lookup dictionaries
    pmid_to_pub_id = dict(zip(publications_df['pmid'], publications_df['publicationId']))

    # For each tool type, link its tools to publications via resources
    for tool_type, tool_df in tool_dfs.items():
        if tool_df.empty:
            continue

        for _, tool_row in tool_df.iterrows():
            pmid = tool_row.get('_pmid', '')
            if not pmid or pd.isna(pmid):
                continue

            # Find the matching resource by detail table ID
            detail_id_col = None
            if tool_type == 'Computational Tool':
                detail_id_col = 'computationalToolId'
            elif tool_type == 'Animal Model':
                detail_id_col = 'animalModelId'
            elif tool_type == 'Antibody':
                detail_id_col = 'antibodyId'
            elif tool_type == 'Cell Line':
                detail_id_col = 'cellLineId'
            elif tool_type == 'Genetic Reagent':
                detail_id_col = 'geneticReagentId'
            elif tool_type == 'Clinical Assessment Tool':
                detail_id_col = 'clinicalAssessmentToolId'
            elif tool_type == 'Advanced Cellular Model':
                detail_id_col = 'advancedCellularModelId'
            elif tool_type == 'Patient-Derived Model':
                detail_id_col = 'patientDerivedModelId'

            if not detail_id_col:
                continue

            detail_id = tool_row.get(detail_id_col, '')
            if not detail_id:
                continue

            # Find matching resource by detail ID
            # For old types, check the foreign key column; for new types, check tracking field
            if detail_id_col in resources_df.columns:
                matching_resources = resources_df[resources_df[detail_id_col] == detail_id]
            else:
                # New tool types: check tracking field
                matching_resources = resources_df[
                    (resources_df['_detailTableId'] == detail_id) &
                    (resources_df['_detailTableType'] == detail_id_col)
                ]

            if matching_resources.empty:
                continue

            resource_id = matching_resources.iloc[0]['resourceId']
            publication_id = pmid_to_pub_id.get(str(pmid), '')

            if resource_id and publication_id:
                usage_rows.append({
                    'usageId': generate_uuid(),
                    'publicationId': publication_id,
                    'resourceId': resource_id,
                    # Tracking fields
                    '_pmid': pmid,
                    '_resourceName': matching_resources.iloc[0]['resourceName'],
                    '_source': 'AI validation - Sonnet 4.5'
                })

    return pd.DataFrame(usage_rows)


def check_existing_resources_in_synapse():
    """
    Query Synapse to get all existing resource names (including synonyms).
    Uses both exact matching, normalized matching, and fuzzy matching for better detection.

    Returns:
        Tuple of (exact_names_set, normalized_names_dict, normalized_list_for_fuzzy)
    """
    try:
        import synapseclient
        from difflib import SequenceMatcher

        syn = synapseclient.Synapse()
        syn.login(authToken=os.getenv('SYNAPSE_AUTH_TOKEN'))

        # Query materialized view with synonyms
        query = 'SELECT resourceName, synonyms, resourceType FROM syn51730943'
        results = syn.tableQuery(query)
        synapse_df = results.asDataFrame()

        # Build sets of exact and normalized names
        exact_names = set()
        normalized_names = {}  # normalized -> (original, type)
        normalized_list = []  # List of (normalized, original, type) for fuzzy matching

        for _, row in synapse_df.iterrows():
            resource_type = row.get('resourceType', '')

            # Add main resource name
            if pd.notna(row['resourceName']) and row['resourceName']:
                name = str(row['resourceName'])
                exact_names.add(name.lower().strip())

                # Store normalized version
                normalized = normalize_resource_name(name)
                key = f"{resource_type}:{normalized}"
                if normalized and key not in normalized_names:
                    normalized_names[key] = name
                    normalized_list.append((normalized, name, resource_type))

            # Add synonyms
            synonyms_val = row['synonyms']
            if isinstance(synonyms_val, list) and len(synonyms_val) > 0:
                for syn_name in synonyms_val:
                    if syn_name and str(syn_name).strip():
                        exact_names.add(str(syn_name).lower().strip())

                        # Store normalized version
                        normalized = normalize_resource_name(syn_name)
                        key = f"{resource_type}:{normalized}"
                        if normalized and key not in normalized_names:
                            normalized_names[key] = syn_name
                            normalized_list.append((normalized, syn_name, resource_type))

        return exact_names, normalized_names, normalized_list
    except Exception as e:
        print(f"   ⚠️  Warning: Could not query Synapse for existing resources: {e}")
        print(f"   Marking all as usage (cannot determine development without Synapse access)")
        return set(), {}, []


def format_development_links(tool_dfs, resources_df, publications_df):
    """
    Format Development table entries (syn26486807) for publications where tools were developed.

    Development = Tool is NEW (not already in Synapse database)
    Usage = Tool already exists in Synapse (just being used/applied)

    Uses both exact and normalized name matching to detect existing tools.

    Args:
        tool_dfs: Dictionary of detail table DataFrames
        resources_df: DataFrame of resources
        publications_df: DataFrame of publications

    Returns:
        DataFrame with Development table entries
    """
    # Get existing resources from Synapse (exact, normalized, and fuzzy)
    print("   Querying Synapse for existing resources...")
    exact_existing, normalized_existing, normalized_list = check_existing_resources_in_synapse()
    print(f"   Found {len(exact_existing)} exact names, {len(normalized_existing)} normalized names in Synapse")

    development_rows = []
    usage_count = 0
    pmid_to_pub_id = dict(zip(publications_df['pmid'], publications_df['publicationId']))

    # Check each resource to see if it's new (development)
    for _, resource in resources_df.iterrows():
        resource_name = resource['resourceName']
        resource_name_lower = str(resource_name).lower().strip()
        resource_type = resource['resourceType']
        normalized = resource.get('_normalized', normalize_resource_name(resource_name))
        normalized_key = f"{resource_type}:{normalized}"

        # Check if resource exists in Synapse (exact or normalized match)
        is_existing = (
            resource_name_lower in exact_existing or
            normalized_key in normalized_existing
        )

        # If not found by exact/normalized, try fuzzy matching for cell lines
        # This catches cases like 'JH002-2' being a variant of 'JH-2-002'
        if not is_existing and resource_type == 'Cell Line' and len(normalized) > 3:
            from difflib import SequenceMatcher
            for synapse_normalized, synapse_original, synapse_type in normalized_list:
                if synapse_type == resource_type:
                    # Calculate similarity ratio
                    ratio = SequenceMatcher(None, normalized, synapse_normalized).ratio()
                    # If >85% similar, consider it a match
                    if ratio > 0.85:
                        is_existing = True
                        break

        if not is_existing:
            # NEW tool - mark as development
            pmid = resource.get('_pmid', '')
            if pmid and str(pmid) in pmid_to_pub_id:
                development_rows.append({
                    'developmentId': generate_uuid(),
                    'resourceId': resource['resourceId'],
                    'publicationId': pmid_to_pub_id[str(pmid)],
                    'investigatorId': '',  # Needs manual curation
                    'funderId': '',  # Needs manual curation
                    # Tracking fields
                    '_pmid': pmid,
                    '_resourceName': resource_name,
                    '_resourceType': resource_type,
                    '_source': 'AI validation - Sonnet 4.5 (NEW tool)'
                })
        else:
            usage_count += 1

    print(f"   {len(development_rows)} NEW tools, {usage_count} existing tools")
    return pd.DataFrame(development_rows)


def format_observations(obs_df):
    """Format observations for Synapse Observations table."""
    rows = []

    for _, obs in obs_df.iterrows():
        rows.append({
            'observationId': generate_uuid(),
            'resourceName': obs.get('resourceName', ''),
            'resourceType': obs.get('resourceType', ''),
            'observationType': obs.get('observationType', ''),
            'details': obs.get('details', ''),
            'referencePublication': obs.get('doi', ''),
            # Tracking fields
            '_pmid': obs.get('pmid', ''),
            '_foundIn': obs.get('foundIn', ''),
            '_confidence': obs.get('confidence', ''),
            '_source': 'AI validation - Sonnet 4.5'
        })

    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print("FORMATTING AI VALIDATION RESULTS FOR SYNAPSE SUBMISSION")
    print("=" * 80)
    print("\nThis script combines ALL validated tools:")
    print("  1. Accepted mined tools (passed Sonnet validation)")
    print("  2. Missed tools (found by Sonnet, not by mining)")
    print("  3. Filters out generic tools (ImageJ, GraphPad, R, MATLAB, etc.)")
    print("  4. Creates proper Resources, Publications, and Usage tables")
    print()

    # Create outputs directory
    os.makedirs('tool_coverage/outputs', exist_ok=True)

    # Load publication metadata first
    print("1. Loading publication metadata from validation_summary.json...")
    validation_summary_file = 'tool_reviews/validation_summary.json'
    pub_metadata = load_publication_metadata(validation_summary_file)
    print(f"   ✓ {len(pub_metadata)} publications with metadata")

    # Load accepted mined tools from validation summary
    print("\n2. Loading accepted mined tools from validation_summary.json...")
    accepted_df = load_accepted_tools(validation_summary_file, pub_metadata)
    print(f"   ✓ {len(accepted_df)} tools mined and validated by Sonnet (after filtering generic tools)")

    # Load potentially missed tools
    print("\n3. Loading missed tools from potentially_missed_tools.csv...")
    tools_file = 'tool_reviews/potentially_missed_tools.csv'
    if not os.path.exists(tools_file):
        print(f"   ⚠️  {tools_file} not found - skipping missed tools")
        missed_df = pd.DataFrame()
    else:
        tools_df = pd.read_csv(tools_file)
        print(f"   - {len(tools_df)} potential tools identified by Sonnet")

        # Filter for validated tools (shouldBeAdded=True or 'True')
        missed_df = tools_df[
            (tools_df['shouldBeAdded'] == True) |
            (tools_df['shouldBeAdded'] == 'True')
        ].copy()

        # Filter out generic tools
        before_filter = len(missed_df)
        missed_df = missed_df[~missed_df.apply(
            lambda row: is_generic_tool(row.get('toolName'), row.get('toolType')),
            axis=1
        )]
        filtered_count = before_filter - len(missed_df)

        # Filter out publications with insufficient NF relevance
        before_pub_filter = len(missed_df)
        missed_df = missed_df[missed_df.apply(
            lambda row: is_nf_relevant_publication(
                str(row['pmid']).replace('PMID:', '').strip(),
                pub_metadata,
                row.get('contextSnippet', '')
            ),
            axis=1
        )]
        pub_filtered_count = before_pub_filter - len(missed_df)
        if pub_filtered_count > 0:
            print(f"   - Filtered {pub_filtered_count} tools from publications with insufficient NF context")

        # Enrich with publication metadata
        missed_df['doi'] = missed_df['pmid'].apply(lambda p: pub_metadata.get(str(p).replace('PMID:', '').strip(), {}).get('doi', ''))
        missed_df['publicationTitle'] = missed_df['pmid'].apply(lambda p: pub_metadata.get(str(p).replace('PMID:', '').strip(), {}).get('title', ''))

        missed_df['source'] = 'found_by_sonnet'
        print(f"   ✓ {len(missed_df)} missed tools validated as real (filtered {filtered_count} generic tools)")

    # Combine accepted and missed tools
    if not accepted_df.empty and not missed_df.empty:
        # Ensure both have the same columns
        all_columns = set(accepted_df.columns) | set(missed_df.columns)
        for col in all_columns:
            if col not in accepted_df.columns:
                accepted_df[col] = ''
            if col not in missed_df.columns:
                missed_df[col] = ''

        validated_df = pd.concat([accepted_df, missed_df], ignore_index=True)
    elif not accepted_df.empty:
        validated_df = accepted_df
    elif not missed_df.empty:
        validated_df = missed_df
    else:
        print("\n⚠️  No validated tools found from either source. Nothing to format.")
        sys.exit(0)

    print(f"\n4. Combined total: {len(validated_df)} validated tools (after filtering)")

    # Additional filtering: Computational tools must be from development publications
    print("\n5. Filtering computational tools to only development publications...")
    validated_df = filter_computational_tools_by_development(validated_df, pub_metadata)

    # Apply confidence threshold
    print(f"\n6. Applying confidence threshold (>= {MIN_CONFIDENCE_THRESHOLD})...")
    before_confidence = len(validated_df)
    validated_df = filter_by_confidence(validated_df, confidence_col='confidence', threshold=MIN_CONFIDENCE_THRESHOLD)
    confidence_filtered = before_confidence - len(validated_df)
    print(f"   ✓ {len(validated_df)} tools remaining ({confidence_filtered} filtered for low confidence)")

    # Check critical fields and calculate completeness
    print("\n7. Calculating metadata completeness scores...")
    completeness_scores = []
    critical_scores = []
    missing_critical_list = []
    has_minimum_list = []

    for idx, row in validated_df.iterrows():
        tool_type = row.get('toolType', '')
        comp_score, crit_score, missing = calculate_completeness_score(row, tool_type)
        has_min, filled, total, _ = has_minimum_critical_fields(row, tool_type)

        completeness_scores.append(comp_score)
        critical_scores.append(crit_score)
        missing_critical_list.append('; '.join(missing) if missing else '')
        has_minimum_list.append(has_min)

    validated_df['_completenessScore'] = completeness_scores
    validated_df['_criticalFieldsScore'] = critical_scores
    validated_df['_missingCriticalFields'] = missing_critical_list
    validated_df['_hasMinimumFields'] = has_minimum_list

    # Report completeness stats
    tools_with_minimum = sum(has_minimum_list)
    tools_without_minimum = len(has_minimum_list) - tools_with_minimum
    avg_completeness = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0

    print(f"   ✓ Average completeness score: {avg_completeness:.1f}/30 points")
    print(f"   ✓ Tools with minimum critical fields: {tools_with_minimum}/{len(validated_df)}")
    if tools_without_minimum > 0:
        print(f"   ⚠️  {tools_without_minimum} tools missing critical fields (will be in VALIDATED but not FILTERED)")

    # Create high-completeness subset for priority review
    print(f"\n8. Creating FILTERED_*.csv subset for priority review (>= {int(MIN_COMPLETENESS_FOR_PRIORITY*100)}% critical fields)...")
    priority_df = filter_for_priority_review(validated_df)
    priority_count = len(priority_df)
    print(f"   ✓ {priority_count}/{len(validated_df)} tools meet priority criteria ({priority_count/len(validated_df)*100:.1f}%)")

    # Format tools by type (detail tables)
    print(f"\n9. Formatting VALIDATED detail table submissions ({len(validated_df)} tools)...")
    tool_dfs = format_validated_tools(validated_df)

    # Integrate NF-modified cell lines from observations
    print("\n   Integrating NF-modified cell lines from observations...")
    tool_dfs = integrate_nf_modified_cell_lines_into_tool_dfs(tool_dfs)

    # Also format priority subset
    print(f"\n   Formatting FILTERED (high-completeness) subset ({len(priority_df)} tools)...")
    priority_tool_dfs = format_validated_tools(priority_df)

    # Save each tool type (both VALIDATED and FILTERED)
    type_file_map = {
        'Computational Tool': 'computational_tools',
        'Animal Model': 'animal_models',
        'Antibody': 'antibodies',
        'Cell Line': 'cell_lines',
        'Genetic Reagent': 'genetic_reagents',
        'Clinical Assessment Tool': 'clinical_assessment_tools',
        'Advanced Cellular Model': 'advanced_cellular_models',
        'Patient-Derived Model': 'patient_derived_models'
    }

    print("\n10. Saving VALIDATED_*.csv (all tools passing confidence + NF filters)...")
    for tool_type, file_suffix in type_file_map.items():
        if tool_type in tool_dfs and not tool_dfs[tool_type].empty:
            df = tool_dfs[tool_type]
            output_file = f'tool_coverage/outputs/VALIDATED_{file_suffix}.csv'
            df.to_csv(output_file, index=False)
            print(f"   ✓ {len(df)} {tool_type}s → {output_file}")
        else:
            print(f"   - {tool_type}s... (none validated)")

    print("\n11. Saving FILTERED_*.csv (high-completeness subset for priority review)...")
    for tool_type, file_suffix in type_file_map.items():
        if tool_type in priority_tool_dfs and not priority_tool_dfs[tool_type].empty:
            df = priority_tool_dfs[tool_type]
            output_file = f'tool_coverage/outputs/FILTERED_{file_suffix}.csv'
            df.to_csv(output_file, index=False)
            print(f"   ✓ {len(df)} {tool_type}s → {output_file}")
        else:
            print(f"   - {tool_type}s... (none in priority)")

    # Format resources (main table with one row per unique resource)
    print("\n12. Formatting VALIDATED_resources.csv (one row per unique resource)...")
    resources_df = format_resources(tool_dfs)
    if not resources_df.empty:
        output_file = 'tool_coverage/outputs/VALIDATED_resources.csv'
        resources_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(resources_df)} unique resources → {output_file}")
    else:
        print("   - No resources to format")

    # Format publications
    print("\n13. Formatting VALIDATED_publications.csv (one row per unique publication)...")
    publications_df = format_publications(tool_dfs)
    if not publications_df.empty:
        output_file = 'tool_coverage/outputs/VALIDATED_publications.csv'
        publications_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(publications_df)} unique publications → {output_file}")
    else:
        print("   - No publications to format")

    # Format usage links
    print("\n14. Formatting VALIDATED_usage.csv (publication-resource links)...")
    usage_df = format_usage_links(tool_dfs, resources_df, publications_df)
    if not usage_df.empty:
        output_file = 'tool_coverage/outputs/VALIDATED_usage.csv'
        usage_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(usage_df)} usage links → {output_file}")
    else:
        print("   - No usage links to format")

    # Format development links (NEW tools not in Synapse)
    print("\n15. Formatting VALIDATED_development.csv (NEW tools)...")
    development_df = format_development_links(tool_dfs, resources_df, publications_df)
    if not development_df.empty:
        output_file = 'tool_coverage/outputs/VALIDATED_development.csv'
        development_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(development_df)} development links (new tools) → {output_file}")

        # Calculate usage vs development
        usage_count = len(usage_df) - len(development_df) if not usage_df.empty else 0
        print(f"   ℹ️  {len(development_df)} NEW tools (development)")
        print(f"   ℹ️  {usage_count} existing tools (usage)")
    else:
        print("   - No development links (all tools already exist in Synapse)")

    # Generate simplified new_unique_resources.csv for review
    print("\n16. Formatting new_unique_resources.csv (simplified NEW resources list)...")
    if not development_df.empty and not resources_df.empty:
        # Get only NEW resources (those in development_df)
        new_resource_ids = set(development_df['resourceId'].unique())
        new_resources_df = resources_df[resources_df['resourceId'].isin(new_resource_ids)].copy()

        # Create simplified format matching original new_unique_resources.csv
        simplified_df = pd.DataFrame({
            'resourceId': new_resources_df['resourceId'],
            'resourceName': new_resources_df['resourceName'],
            'resourceType': new_resources_df['resourceType'],
            'synonyms': new_resources_df.get('synonyms', ''),
            'rrid': new_resources_df.get('rrid', ''),
            '_pmid': '',  # Will be populated from development_df
            '_source': 'AI validation - Sonnet 4.5',
            '_normalized': new_resources_df['resourceName'].apply(
                lambda x: normalize_resource_name(x).replace(' ', '').lower()
            )
        })

        # Add PMID from first publication for each resource
        pmid_map = development_df.groupby('resourceId')['_pmid'].first().to_dict()
        simplified_df['_pmid'] = simplified_df['resourceId'].map(pmid_map)

        # Sort by resource type and name
        simplified_df = simplified_df.sort_values(['resourceType', 'resourceName'])

        output_file = 'tool_coverage/outputs/new_unique_resources.csv'
        simplified_df.to_csv(output_file, index=False)
        print(f"   ✓ {len(simplified_df)} NEW unique resources → {output_file}")
    else:
        print("   - No new resources to format")

    # Load and format observations
    print("\n17. Formatting VALIDATED_observations.csv...")
    obs_file = 'tool_reviews/observations.csv'
    if os.path.exists(obs_file):
        obs_df = pd.read_csv(obs_file)
        print(f"   - {len(obs_df)} observations found")

        # Apply confidence threshold to observations
        if not obs_df.empty:
            before_obs_conf = len(obs_df)
            obs_df = filter_by_confidence(obs_df, confidence_col='confidence', threshold=MIN_CONFIDENCE_THRESHOLD)
            obs_conf_filtered = before_obs_conf - len(obs_df)
            if obs_conf_filtered > 0:
                print(f"   - Filtered {obs_conf_filtered} observations for low confidence")

        if not obs_df.empty:
            formatted_obs = format_observations(obs_df)
            output_file = 'tool_coverage/outputs/VALIDATED_observations.csv'
            formatted_obs.to_csv(output_file, index=False)
            print(f"   ✓ {len(formatted_obs)} observations → {output_file}")
        else:
            print("   - No observations to format")
            formatted_obs = pd.DataFrame()
    else:
        print(f"   ⚠️  {obs_file} not found")
        formatted_obs = pd.DataFrame()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_tools = sum(len(df) for df in tool_dfs.values())

    print(f"\nValidated tools by source:")
    print(f"   - Mined and validated: {len(accepted_df)}")
    print(f"   - Found by Sonnet: {len(missed_df)}")
    print(f"   - Total: {total_tools}")

    print(f"\nValidated tools by type:")
    for tool_type in sorted(tool_dfs.keys()):
        if not tool_dfs[tool_type].empty:
            print(f"   - {tool_type}: {len(tool_dfs[tool_type])}")

    if not resources_df.empty:
        print(f"\nResources (deduplicated): {len(resources_df)}")
    if not publications_df.empty:
        print(f"Publications (unique): {len(publications_df)}")
    if not usage_df.empty:
        usage_only = len(usage_df) - len(development_df) if not development_df.empty else len(usage_df)
        print(f"Usage links (existing tools): {usage_only}")
    if not development_df.empty:
        print(f"Development links (NEW tools): {len(development_df)}")
    if not formatted_obs.empty:
        print(f"Observations: {len(formatted_obs)}")

    # Quality metrics
    print(f"\n📊 Quality Metrics:")
    print(f"   - Confidence threshold: {MIN_CONFIDENCE_THRESHOLD} (0.0-1.0 scale)")
    print(f"   - Tools filtered for low confidence: {confidence_filtered}")
    print(f"   - Average completeness score: {avg_completeness:.1f}/30 points")
    print(f"   - Tools with minimum critical fields: {tools_with_minimum}/{total_tools}")
    print(f"   - High-completeness tools (priority): {priority_count}/{total_tools} ({priority_count/total_tools*100:.1f}%)")

    print("\n📋 VALIDATED_*.csv Files (all tools passing confidence + NF filters):")
    print("\n   Core Tables:")
    if not resources_df.empty:
        print(f"   ✓ VALIDATED_resources.csv ({len(resources_df)} unique resources)")
    if not publications_df.empty:
        print(f"   ✓ VALIDATED_publications.csv ({len(publications_df)} unique publications)")

    print("\n   Relationship Tables:")
    if not usage_df.empty:
        print(f"   ✓ VALIDATED_usage.csv ({len(usage_df)} links)")
    if not development_df.empty:
        print(f"   ✓ VALIDATED_development.csv ({len(development_df)} links)")

    print("\n   Detail Tables:")
    for tool_type, file_suffix in type_file_map.items():
        if tool_type in tool_dfs and not tool_dfs[tool_type].empty:
            print(f"   ✓ VALIDATED_{file_suffix}.csv ({len(tool_dfs[tool_type])} entries)")

    print("\n   Observations:")
    if not formatted_obs.empty:
        print(f"   ✓ VALIDATED_observations.csv ({len(formatted_obs)} entries)")

    print("\n📋 FILTERED_*.csv Files (high-completeness subset for priority review):")
    priority_total = sum(len(df) for df in priority_tool_dfs.values())
    print(f"\n   {priority_total} tools with >={int(MIN_COMPLETENESS_FOR_PRIORITY*100)}% critical fields filled")
    for tool_type, file_suffix in type_file_map.items():
        if tool_type in priority_tool_dfs and not priority_tool_dfs[tool_type].empty:
            validated_count = len(tool_dfs.get(tool_type, pd.DataFrame()))
            priority_count_type = len(priority_tool_dfs[tool_type])
            pct = priority_count_type / validated_count * 100 if validated_count > 0 else 0
            print(f"   ✓ FILTERED_{file_suffix}.csv ({priority_count_type}/{validated_count} = {pct:.0f}%)")

    print("\n✅ Validation formatting complete!")
    print(f"\n💡 Next Steps:")
    print(f"   1. Review FILTERED_*.csv files for priority manual review (high completeness)")
    print(f"   2. Use VALIDATED_*.csv files for comprehensive review (all passing tools)")
    print(f"   3. After manual review, upsert approved tools to Synapse")
    print("   - All files follow Synapse table schemas")
    print("   - Generic tools filtered out (ImageJ, GraphPad, R, MATLAB, etc.)")
    print("   - Resources deduplicated (one row per unique resource)")
    print("   - Usage links created (multiple publications per resource)")
    print("   - Ready for manual review and upload via upsert-tools.yml")


if __name__ == '__main__':
    main()
