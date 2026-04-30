# Tool Submissions

This folder holds pending tool records awaiting review before upload to the [NF Research Tools registry](https://nf.synapse.org/Explore/Tools) on the NF Data Portal.

## Folder structure

```
submissions/
  {tool_type}/              ← pending review (delete or revise before merging)
    {tool_name}.json        ← one file per tool
    observations/           ← per-tool observation records from mining
      {tool_name}_{pmid}_{idx}.json
```

Tool types: `animal_models`, `antibodies`, `cell_lines`, `genetic_reagents`,
`patient_derived_models`, `organoid_protocols`, `computational_tools`,
`clinical_assessment_tools`

## How submissions get into this folder

**Automated (publication mining):** The `publication-mining.yml` workflow runs monthly and opens a PR with newly mined tools in `submissions/{type}/`.

**Internal manual submissions:** Team members and collaborators can add tools directly by opening a pull request (see below).

**External submissions:** External contributors use the [Formspark submission forms](https://nf.synapse.org/Explore/Tools) on the NF Portal. Those are exported and processed via `process_formspark_export.py`, which writes JSON files into `submissions/{type}/`. After manual review and moving accepted files to `submissions/{type}/accepted/`, `upsert-tools.yml` uploads them to Synapse.

## Internal manual submission instructions

### 1. Create a JSON file for the tool

Copy an existing JSON from the appropriate `submissions/{type}/` directory as a template, or use the corresponding schema in `NF-Tools-Schemas/{type}/submit*.json` to understand required fields.

Minimal required fields vary by type — see the schema for `"required"` annotations. At minimum include:
- `resourceName` — canonical tool name
- `resourceType` — must match the folder type
- `developmentPublicationDOI` — DOI of the paper that first described/used this tool (if known)

### 2. Open a pull request

- Branch off `main`
- Add your JSON file(s) to `submissions/{type}/`
- Open a PR with title format: `Add [tool name] to [type]` (e.g., `Add NF1-/- MEF cell line to cell_lines`)
- Apply the **`tool-submissions`** label to the PR

On merge, `upsert-tools.yml` automatically compiles the JSON files into the Synapse upload CSVs and uploads them to the registry.

### 3. Review process

PRs with the `tool-submissions` label will be reviewed by a maintainer. During review:
- **Edit** the JSON if fields are incorrect or incomplete
- **Delete** the file if the tool should not be added
- Remaining files at merge time are what gets uploaded

### Labels

| Label | Purpose |
|-------|---------|
| `tool-submissions` | Required on all tool submission PRs — triggers `upsert-tools.yml` on merge |

### Tips

- One JSON file per tool. Multiple tools can be in the same PR.
- Observation JSONs (`observations/` subfolder) are optional but helpful context; they are uploaded to the observations table (syn26486836). Pipeline-extracted observations set `observationSubmitterName` to '🤖 AI-extracted'; Formspark observations use `first_name`/`last_name` or 'Anonymous'.
- If you're unsure about a field value, leave it blank — curators will fill it in.
- RRIDs can be looked up after submission via `lookup_rrids.py`.
