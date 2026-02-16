"""
Improved mining functions to fix low hit rate and categorization issues.

Key improvements:
1. More permissive tool detection (higher hit rate)
2. Better development vs usage detection
3. Smarter context analysis
"""

import re
from typing import Dict, List, Set, Tuple
from rapidfuzz import fuzz


def is_development_context_improved(tool_name: str, tool_type: str, text: str,
                                   window_size: int = 500) -> bool:
    """
    Improved detection of tool development vs usage.

    Returns TRUE if this paper describes DEVELOPING the tool (not just using it).

    Strong development indicators:
    - "we developed [tool]"
    - "we created [tool]"
    - "we designed [tool]"
    - "novel [tool]"
    - "new [tool_type]"
    - Paper describes tool creation/generation

    Strong usage indicators (return FALSE):
    - Version numbers: "ImageJ v1.53k", "GraphPad Prism 7.0"
    - Commercial sources: "obtained from", "purchased", "Thermo Fisher"
    - Common tools: known established tools are usage not development

    Args:
        tool_name: Name of the tool
        tool_type: Type of tool (computational_tools, cell_lines, etc.)
        text: Text to analyze (methods, abstract, etc.)
        window_size: Characters to check around tool mention

    Returns:
        True if development context detected, False if usage
    """
    tool_lower = tool_name.lower()
    text_lower = text.lower()

    # First check: Version numbers = USAGE (not development)
    version_patterns = [
        rf'{re.escape(tool_lower)}\s+v\d',
        rf'{re.escape(tool_lower)}\s+version\s+\d',
        rf'{re.escape(tool_lower)}\s+\d+\.\d+',
        rf'{re.escape(tool_lower)}\s+\(v\d',
        rf'{re.escape(tool_lower)}\s+\(version',
    ]

    for pattern in version_patterns:
        if re.search(pattern, text_lower):
            return False  # Has version number = usage of existing tool

    # Find all mentions of the tool
    positions = []
    idx = 0
    while idx < len(text_lower):
        idx = text_lower.find(tool_lower, idx)
        if idx == -1:
            break
        positions.append(idx)
        idx += 1

    if not positions:
        return False

    # Strong development indicators (first person + action)
    strong_dev_patterns = [
        r'we\s+(develop|creat|design|generat|establish|engineer|construct)\w*\s+\w*\s*' + re.escape(tool_lower),
        r'we\s+\w*\s+(develop|creat|design|generat|establish|engineer|construct)\w*\s+' + re.escape(tool_lower),
        r'(novel|new)\s+\w*\s*' + re.escape(tool_lower),
        r'' + re.escape(tool_lower) + r'\s+(was|were)\s+(develop|creat|design|generat|establish)',
        r'to\s+(develop|create|design|generate|establish)\s+\w*\s*' + re.escape(tool_lower),
    ]

    # Strong usage indicators
    strong_usage_keywords = [
        'obtained from', 'purchased from', 'acquired from',
        'provided by', 'bought from', 'commercially available',
        'charles river', 'jackson lab', 'jax', 'taconic',
        'atcc', 'sigma', 'millipore', 'thermo fisher',
        'invitrogen', 'cell signaling', 'abcam', 'santa cruz',
        'available at', 'downloaded from', 'accessed from'
    ]

    # Check context around each mention
    dev_score = 0
    usage_score = 0

    for pos in positions:
        start = max(0, pos - window_size)
        end = min(len(text_lower), pos + len(tool_lower) + window_size)
        context = text_lower[start:end]

        # Check strong development patterns
        for pattern in strong_dev_patterns:
            if re.search(pattern, context):
                dev_score += 3  # Strong evidence

        # Check strong usage indicators
        for keyword in strong_usage_keywords:
            if keyword in context:
                usage_score += 5  # Very strong evidence of usage

    # Development only if strong development indicators and no usage indicators
    return dev_score >= 3 and usage_score == 0


def is_likely_established_tool(tool_name: str, tool_type: str) -> bool:
    """
    Check if a tool is a well-known established tool.

    These are tools that are definitely NOT being developed in typical papers,
    they're being USED.

    Args:
        tool_name: Name of the tool
        tool_type: Type of tool

    Returns:
        True if this is a known established tool
    """
    tool_lower = tool_name.lower()

    # Well-known computational tools
    if tool_type == 'computational_tools':
        established_tools = {
            # Image analysis
            'imagej', 'fiji', 'cellprofiler', 'imaris', 'metamorph',
            # Statistics/graphing
            'graphpad', 'prism', 'graphpad prism', 'spss', 'stata', 'sas',
            'r', 'rstudio', 'excel', 'sigmaplot', 'origin',
            # Sequencing analysis
            'star', 'bwa', 'bowtie', 'tophat', 'hisat', 'kallisto', 'salmon',
            'deseq', 'deseq2', 'edger', 'limma', 'cufflinks', 'htseq',
            'featurecounts', 'gatk', 'picard', 'samtools', 'bedtools', 'igv',
            # Structural biology
            'pymol', 'chimera', 'rosetta', 'swiss-model', 'modeller',
            # Other common tools
            'flowjo', 'prism', 'matlab', 'python', 'perl', 'java',
            'blast', 'clustalw', 'muscle', 'mega', 'phylip',
            'cytoscape', 'string', 'david', 'panther', 'gsea',
        }

        return tool_lower in established_tools

    return False


def mine_text_section_improved(text: str, tool_patterns: Dict[str, List[str]],
                               section_name: str = 'text',
                               require_context: bool = False) -> Tuple[Dict[str, Set[str]], Dict[str, Dict]]:
    """
    Improved mining that's less restrictive and smarter about categorization.

    Key improvements:
    1. More permissive matching (don't require specific context keywords)
    2. Better development vs usage detection
    3. Consider version numbers as usage indicators
    4. Recognize established tools

    Args:
        text: Text to mine
        tool_patterns: Tool patterns to search for
        section_name: Name of section being mined
        require_context: If True, require context keywords (more restrictive)

    Returns:
        Tuple of (found_tools dict, metadata dict)
    """
    found_tools = {
        'cell_lines': set(),
        'antibodies': set(),
        'animal_models': set(),
        'genetic_reagents': set(),
        'computational_tools': set(),
        'advanced_cellular_models': set(),
        'patient_derived_models': set(),
        'clinical_assessment_tools': set()
    }

    tool_metadata = {}

    if not text or len(text) < 50:
        return found_tools, tool_metadata

    text_lower = text.lower()

    # Context keywords (optional - used for higher confidence)
    context_keywords = [
        'using', 'used', 'utilized', 'employed', 'with',
        'analyzed', 'examined', 'studied', 'assessed',
        'measured', 'quantified', 'visualized', 'performed',
        'generated', 'developed', 'created', 'established',
    ]

    # Search for tools
    for tool_type, patterns in tool_patterns.items():
        if not patterns:
            continue

        # Fuzzy match tools (lower threshold for better recall)
        matches = fuzzy_match_tools(text, patterns, threshold=0.85)  # Was 0.88

        for tool_name in matches:
            tool_lower = tool_name.lower()

            # Find tool positions
            positions = []
            idx = 0
            while idx < len(text_lower):
                idx = text_lower.find(tool_lower, idx)
                if idx == -1:
                    break
                positions.append(idx)
                idx += 1

            if not positions:
                continue

            # Check if we require context keywords
            if require_context:
                has_context = False
                for pos in positions:
                    start = max(0, pos - 200)
                    end = min(len(text_lower), pos + len(tool_lower) + 200)
                    context = text_lower[start:end]

                    if any(kw in context for kw in context_keywords):
                        has_context = True
                        break

                if not has_context:
                    continue  # Skip if no context found

            # Tool found! Add it
            found_tools[tool_type].add(tool_name)

            # Extract metadata
            metadata_key = f"{tool_type}:{tool_name}"

            # Get context around first mention
            pos = positions[0]
            start = max(0, pos - 150)
            end = min(len(text), pos + len(tool_name) + 150)
            context = text[start:end]

            # Determine if development or usage
            is_dev = is_development_context_improved(tool_name, tool_type, text)

            # Check if established tool
            is_established = is_likely_established_tool(tool_name, tool_type)

            # Override: established tools are never "development" in typical papers
            if is_established and is_dev:
                is_dev = False

            # Calculate confidence based on context
            confidence = 0.7  # Base confidence
            if any(kw in context.lower() for kw in context_keywords):
                confidence += 0.1
            if is_established:
                confidence += 0.1  # Higher confidence for known tools
            if re.search(r'v\d|version\s+\d|\d+\.\d+', context.lower()):
                confidence += 0.05  # Version number increases confidence

            confidence = min(0.95, confidence)  # Cap at 0.95

            metadata = {
                'context': context,
                'confidence': confidence,
                'is_development': is_dev,
                'is_generic': False,
                'is_established': is_established,
                'section': section_name
            }

            tool_metadata[metadata_key] = metadata

    return found_tools, tool_metadata


def fuzzy_match_tools(text: str, patterns: List[str], threshold: float = 0.85) -> Set[str]:
    """
    Fuzzy match tool names in text.

    Args:
        text: Text to search
        patterns: List of tool names to find
        threshold: Minimum similarity score (0-1)

    Returns:
        Set of matched tool names
    """
    matches = set()
    text_lower = text.lower()

    for pattern in patterns:
        pattern_lower = pattern.lower()

        # Exact match first (fastest)
        if pattern_lower in text_lower:
            matches.add(pattern)
            continue

        # Fuzzy match for slight variations
        # Split text into words and check each
        words = re.findall(r'\b\w+\b', text_lower)
        for word in words:
            score = fuzz.ratio(pattern_lower, word) / 100.0
            if score >= threshold:
                matches.add(pattern)
                break

    return matches
