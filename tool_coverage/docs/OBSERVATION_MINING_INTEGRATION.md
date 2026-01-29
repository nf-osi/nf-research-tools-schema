# Observation Mining Integration Guide

## Overview
This guide documents the integration of observation mining into the NF research tools publication review pipeline. Observations are scientific characterizations of research tools (e.g., phenotypic data, performance metrics, usage notes) that are stored in the Synapse observations table (syn26486836).

## Changes Made to Support Observation Mining

### 1. Enhanced Text Extraction (fetch_fulltext_and_mine.py)

**New Functions Added:**
- `extract_results_section(fulltext_xml)` - Extracts Results section from PMC XML
- `extract_discussion_section(fulltext_xml)` - Extracts Discussion section from PMC XML

**Rationale:** Observations about tool performance, phenotypes, and behaviors are typically reported in Results and Discussion sections rather than Methods or Introduction.

**Section Title Patterns:**
- **Results**: 'results', 'result', 'findings', 'observations'
- **Discussion**: 'discussion', 'conclusion', 'conclusions', 'concluding remarks', 'summary and discussion', 'discussion and conclusions'

### 2. Updated Caching System

**Modified Function:** `cache_publication_text()`
- Now accepts and caches `results` and `discussion` parameters
- Cache structure now includes:
  ```json
  {
    "pmid": "12345678",
    "abstract": "...",
    "methods": "...",
    "introduction": "...",
    "results": "...",          // NEW
    "discussion": "...",        // NEW
    "fetched_at": "2026-01-29T...",
    "abstract_length": 1234,
    "methods_length": 5678,
    "introduction_length": 890,
    "results_length": 4567,     // NEW
    "discussion_length": 2345   // NEW
  }
  ```

**Backwards Compatibility:** The `load_cached_text()` function uses `.get('results', '')` and `.get('discussion', '')` to support older cache files without these sections.

### 3. Updated Mining Flow

**Changes to `mine_publication()` function:**
1. Extracts Results section and stores in `results_text`
2. Extracts Discussion section and stores in `discussion_text`
3. Updates `fulltext_available` flag to include these sections
4. Stores both in mining result dictionary for caching
5. Logs when Results and Discussion sections are found

**Output:** Mining logs now show:
```
✓ Abstract: 1234 chars
✓ Methods section: 5678 chars
✓ Introduction section: 890 chars
✓ Results section: 4567 chars      # NEW
✓ Discussion section: 2345 chars   # NEW
```

### 4. Updated AI Validation Input (run_publication_reviews.py)

**Modified Function:** `prepare_goose_input()`
- Loads Results and Discussion from cache (with backwards compatibility)
- Fallback fetching now extracts all 5 sections
- Passes Results and Discussion to Goose AI in input JSON:
  ```json
  {
    "abstractText": "...",
    "methodsText": "...",
    "introductionText": "...",
    "resultsText": "...",        // NEW
    "discussionText": "...",     // NEW
    "hasResults": true,          // NEW
    "hasDiscussion": true,       // NEW
    "minedTools": [...]
  }
  ```

---

## Next Steps: Implementing Observation Extraction

### Step 1: Update Goose AI Recipe

**File:** `tool_coverage/scripts/recipes/publication_tool_review.yaml`

**Current Focus:** Tool validation (validate mined tools, detect false positives, find missed tools)

**New Task to Add:** Observation extraction

**Recommended Recipe Enhancement:**

```yaml
# Add to existing recipe after tool validation section

## TASK 4: Extract Scientific Observations

For each validated tool (both mined and potentially missed), extract scientific observations from the Results and Discussion sections.

### Observation Types (from schema):
**Phenotypic Observations:**
- Body Length
- Body Weight
- Coat Color
- Organ Development
- Growth Rate
- Lifespan

**Behavioral Observations:**
- Motor Activity
- Swimming Behavior
- Social Behavior
- Reproductive Behavior
- Reflex Development
- Feed Intake
- Feeding Behavior

**Disease-Related:**
- Disease Susceptibility
- Tumor Growth

**Practical Information:**
- Usage Instructions
- Issue (problems encountered)
- Depositor Comment
- General Comment or Review

**Other:**
- Other (specify in details)

### Extraction Guidelines:

1. **Focus on Results and Discussion sections** - these contain reported findings
2. **Link observations to specific tools** - each observation must reference a tool name
3. **Include quantitative data** when available (e.g., "Body Weight: Nf1+/- mice weighed 15% less than wild-type at 8 weeks")
4. **Capture context** - include enough detail to understand the observation
5. **Note publication DOI** - for proper attribution and scoring

### Output Format:

```json
{
  "observations": [
    {
      "resourceName": "Nf1+/-",
      "resourceType": "Animal Model",
      "observationType": "Body Weight",
      "details": "Nf1+/- mice showed significantly reduced body weight (15% decrease) compared to wild-type littermates at 8 weeks of age (p<0.01). This weight difference persisted throughout adulthood.",
      "doi": "10.1234/journal.2023.12345"
    },
    {
      "resourceName": "Nf1+/-",
      "resourceType": "Animal Model",
      "observationType": "Tumor Growth",
      "details": "Nf1+/- mice developed optic gliomas with 30% penetrance by 12 months of age. Tumor growth was accelerated in female mice compared to males.",
      "doi": "10.1234/journal.2023.12345"
    }
  ]
}
```

### Validation Rules:
- Only extract observations explicitly stated in the text
- Do not infer or extrapolate beyond what's written
- If observation type is unclear, use "Other" and provide descriptive details
- Include page/section references when possible
```

### Step 2: Update run_publication_reviews.py

**Modify the output parsing to extract observations:**

```python
def parse_goose_output(output_file):
    """Parse goose output YAML file."""
    with open(output_file, 'r') as f:
        data = yaml.safe_load(f)

    # Existing parsing for tool validation
    validated_tools = data.get('validated_tools', [])
    rejected_tools = data.get('rejected_tools', [])
    potentially_missed = data.get('potentially_missed_tools', [])
    suggested_patterns = data.get('suggested_patterns', [])

    # NEW: Parse observations
    observations = data.get('observations', [])

    return {
        'validated_tools': validated_tools,
        'rejected_tools': rejected_tools,
        'potentially_missed': potentially_missed,
        'suggested_patterns': suggested_patterns,
        'observations': observations  # NEW
    }
```

### Step 3: Save Observations to CSV

**Add observation CSV generation:**

```python
def save_observations_csv(all_observations, output_dir):
    """Save extracted observations to CSV."""
    obs_data = []

    for pub_pmid, observations in all_observations.items():
        for obs in observations:
            obs_data.append({
                'pmid': pub_pmid,
                'resourceName': obs['resourceName'],
                'resourceType': obs['resourceType'],
                'observationType': obs['observationType'],
                'details': obs['details'],
                'doi': obs.get('doi', '')
            })

    if obs_data:
        obs_df = pd.DataFrame(obs_data)
        obs_csv = Path(output_dir) / 'observations.csv'
        obs_df.to_csv(obs_csv, index=False)
        print(f"\n✓ Observations saved to: {obs_csv}")
        print(f"  Total observations: {len(obs_data)}")
        return obs_csv
    return None
```

### Step 4: Create Observation Uploader Script

**New File:** `tool_coverage/scripts/upload_observations.py`

**Purpose:** Match extracted observations to existing resourceIds and upload to syn26486836

**Key Functions:**
1. Load observations CSV from AI validation
2. Match resourceName to resourceId (via syn51730943 materialized view)
3. Validate observation types against schema
4. Upload to syn26486836 (ADD only, never modify existing)
5. Handle multiple observations per tool

**Matching Logic:**
```python
def match_observation_to_resource(resource_name, resource_type, syn):
    """Match observation to existing resource."""
    query = f"""
        SELECT resourceId, resourceName
        FROM syn51730943
        WHERE resourceType = '{resource_type}'
        AND resourceName = '{resource_name}'
    """
    result = syn.tableQuery(query).asDataFrame()

    if len(result) == 1:
        return result.iloc[0]['resourceId']
    elif len(result) > 1:
        print(f"⚠️  Multiple matches for {resource_name}")
        return result.iloc[0]['resourceId']  # Take first
    else:
        print(f"⚠️  No match found for {resource_name} ({resource_type})")
        return None
```

**Upload Logic:**
```python
def upload_observations(observations_df, syn):
    """Upload observations to Synapse table syn26486836."""

    # Match observations to resourceIds
    matched = []
    unmatched = []

    for _, obs in observations_df.iterrows():
        resource_id = match_observation_to_resource(
            obs['resourceName'],
            obs['resourceType'],
            syn
        )

        if resource_id:
            matched.append({
                'resourceId': resource_id,
                'resourceType': obs['resourceType'],
                'resourceName': obs['resourceName'],
                'observationType': obs['observationType'],
                'details': obs['details'],
                'referencePublication': obs['doi']
            })
        else:
            unmatched.append(obs)

    if matched:
        # Upload to syn26486836
        obs_table = syn.get('syn26486836')
        new_rows = pd.DataFrame(matched)
        syn.store(synapseclient.Table(obs_table, new_rows))
        print(f"\n✓ Uploaded {len(matched)} observations to syn26486836")

    if unmatched:
        print(f"\n⚠️  {len(unmatched)} observations could not be matched to resources")
        # Save unmatched for manual review
        pd.DataFrame(unmatched).to_csv('unmatched_observations.csv', index=False)
```

---

## Observation Types Reference

From `SubmitObservationSchema.json`:

| Category | Observation Types |
|----------|-------------------|
| **Morphometric** | Body Length, Body Weight, Coat Color, Organ Development |
| **Growth** | Growth Rate, Lifespan, Feed Intake, Feeding Behavior |
| **Behavioral** | Motor Activity, Swimming Behavior, Social Behavior, Reproductive Behavior, Reflex Development |
| **Disease** | Disease Susceptibility, Tumor Growth |
| **Documentation** | Usage Instructions, Issue, Depositor Comment, General Comment or Review |
| **Flexible** | Other |

---

## Example Workflow

### Complete Observation Mining Pipeline:

```bash
# Step 1: Mine publications (extracts all 5 sections + caches them)
python tool_coverage/scripts/fetch_fulltext_and_mine.py

# Step 2: AI validation + observation extraction (uses cached text)
python tool_coverage/scripts/run_publication_reviews.py

# Output:
# - VALIDATED_tools.csv (validated tool mentions)
# - observations.csv (NEW - extracted observations)
# - potentially_missed_tools.csv
# - suggested_patterns.csv

# Step 3: Upload observations to Synapse
python tool_coverage/scripts/upload_observations.py observations.csv

# Output:
# - Observations uploaded to syn26486836
# - unmatched_observations.csv (for manual review)
```

---

## Benefits of This Approach

1. **No Extra API Calls** - Results/Discussion sections fetched once during mining
2. **Cached for Reuse** - AI validation reads from cache
3. **Comprehensive Context** - AI sees all relevant sections for observation extraction
4. **Automated Linking** - Observations automatically linked to tools via resourceId
5. **Quality Data** - DOI attribution enables observation scoring (7.5 points vs 2.5)
6. **Continuous Improvement** - Same feedback loop as tool mining

---

## Testing Strategy

### Phase 1: Enhance Recipe
1. Update Goose recipe with observation extraction instructions
2. Test on 5-10 publications with known observations
3. Validate observation extraction accuracy

### Phase 2: Integrate Parsing
1. Add observation parsing to run_publication_reviews.py
2. Generate observations.csv
3. Manual review of extracted observations

### Phase 3: Build Uploader
1. Create upload_observations.py
2. Test matching logic with sample data
3. Test upload to syn26486836 (development table first)

### Phase 4: Production
1. Run on full publication corpus
2. Monitor observation extraction rates
3. Refine observation type categorization based on results

---

## Notes

- **Multiple observations per tool are supported** - syn26486836 allows many-to-one relationships
- **Only add, never modify** - Existing observations in syn26486836 should not be changed
- **DOI is crucial** - Observations with DOI references receive higher scoring weight (7.5 vs 2.5 points)
- **Backwards compatibility maintained** - Older cache files without Results/Discussion still work
- **Observation scoring** - Observations contribute 25 points (25%) to tool completeness score

---

## File Modifications Summary

### Modified Files:
1. **fetch_fulltext_and_mine.py** (lines 265-380, 1016-1065, 1296-1318)
   - Added `extract_results_section()`
   - Added `extract_discussion_section()`
   - Updated `cache_publication_text()` signature
   - Updated mining flow to extract and cache new sections
   - Updated logging to report new sections

2. **run_publication_reviews.py** (lines 156-277)
   - Updated `load_cached_text()` usage to load results/discussion
   - Updated fallback fetching to extract results/discussion
   - Updated `prepare_goose_input()` to pass new sections to AI

### Files to Create:
1. **upload_observations.py** (new script)
   - Match observations to resources
   - Upload to syn26486836

### Files to Update Next:
1. **recipes/publication_tool_review.yaml**
   - Add observation extraction task
   - Define output format
