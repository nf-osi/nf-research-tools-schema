<img alt="GitHub release (latest by date)" src="https://img.shields.io/github/v/release/nf-osi/nf-research-tools-schema?label=latest%20release&display_name=release&style=flat-square">  <img alt="GitHub Release Date" src="https://img.shields.io/github/release-date/nf-osi/nf-research-tools-schema?style=flat-square&color=orange">  <img alt="GitHub" src="https://img.shields.io/github/license/nf-osi/nf-research-tools-schema?style=flat-square&color=red">
# NF Research Tools Central Schema

This repository contains the released versions of the JSON-LD schema for the NF Research Tools Central. You can learn more about the schema/data model and other aspects of this project in our [project documentation](https://help.nf.synapse.org/NFdocs/Data-Model-&-Schema.2463596640.html).

## Tool Types Supported

The schema supports **9 resource types** for cataloging research tools:

**Established Types (v1.0):**
- **Antibodies** - Immunological reagents for detection/purification
- **Cell Lines** - Immortalized cell cultures
- **Animal Models** - Genetically modified organisms (mice, zebrafish, etc.)
- **Genetic Reagents** - Plasmids, constructs, CRISPR reagents
- **Biobanks** - Collections of biological samples

**New Types (v2.0):**
- **Computational Tools** - Software, pipelines, analysis tools (50+ known tools)
- **Advanced Cellular Models** - Organoids, assembloids, 3D cultures
- **Patient-Derived Models** - PDX, xenografts, humanized systems
- **Clinical Assessment Tools** - Questionnaires, scales, patient-reported outcomes (SF-36, PROMIS, PedsQL)

Each tool type has specific metadata fields and validation rules. See [`tool_coverage/MULTI_QUERY_IMPLEMENTATION.md`](tool_coverage/MULTI_QUERY_IMPLEMENTATION.md) for details on tool mining strategies.

Learn more about the goals for this project by checking out the following documents and presentations: 

> Ashley Clayton, Mialy DeFelice, Brynn Zalmanek, Jay Hodgson, Caroline Morin, Stockard Simon, Julie A Bletz, James A Eddy, Milen Nikolov, Jineta Banerjee, Kalyan Vinnakota, Marco Marasca, Kevin J Boske, Bruce Hoff, Ljubomir Bradic, YooRi Kim, James R Goss, Robert J Allaway, Centralizing neurofibromatosis experimental tool knowledge with the NF Research Tools Database, Database, Volume 2022, 2022, baac045, https://doi.org/10.1093/database/baac045
> 
>Clayton, A., DeFelice, M., Zalmanek, B., Hodgson, J., Morin, C., Simon, S., … Allaway, R. (2022, January 25). Centralizing neurofibromatosis experimental tool knowledge with the NF Research Tools Database. https://doi.org/10.31222/osf.io/t6zaf

>Zalmanek, Brynn; Allaway, Robert; Goss, James; Clayton, Ashley; Eddy, James; Throgmorton, Kaitlin; et al. (2021): NF Research Tools Database: An experimental resource database for the neurofibromatosis community. figshare. Poster. https://doi.org/10.6084/m9.figshare.14825271.v1 

>[Gilbert Family Foundation Press Release](https://www.gilbertfamilyfoundation.org/press-release/gff-and-sage-bionetworks-collaborate-on-an-nf1-research-tools-database/). 

# Automated Workflows

This repository uses automated GitHub Actions workflows that run in a coordinated sequence to maintain and improve the tools schema. Each workflow creates a PR, and when merged, triggers the next workflow in the chain.

## Workflow Sequence

**Entry Point:**
1. **review-tool-annotations.yml** (Monday 9 AM UTC) - Analyzes individualID annotations, suggests new cell lines

**Main Sequence (PR-merge triggered):**
2. **check-tool-coverage.yml** - Multi-query mining (bench + clinical) for ALL 9 tool types with AI validation
3. **link-tool-datasets.yml** - Links datasets to tools via publications
4. **score-tools.yml** - Calculates tool completeness scores, uploads to Synapse
5. **update-observation-schema.yml** - Updates observation schema from Synapse data

**Supporting Workflows:**
- **upsert-tools.yml** - Uploads validated tool data to Synapse (triggered by CSV files on main)
- **upsert-tool-datasets.yml** - Uploads tool-dataset linkages to Synapse
- **publish-schema-viz.yml** - Generates interactive schema visualization
- **schematic-schema-convert.yml** - Converts schema between CSV and JSON-LD formats

**Coordination Pattern:** Each workflow creates a PR with specific labels. When that PR is merged, it triggers the next workflow in the sequence, providing manual review gates between steps.

## Documentation

- **Comprehensive workflow guide:** [`.github/workflows/README.md`](.github/workflows/README.md)
- **Workflow coordination details:** [`docs/WORKFLOW_COORDINATION.md`](docs/WORKFLOW_COORDINATION.md)
- **Tool annotation review:** [`docs/TOOL_ANNOTATION_REVIEW.md`](docs/TOOL_ANNOTATION_REVIEW.md)
- **Tool completeness scoring:** [`docs/TOOL_SCORING.md`](docs/TOOL_SCORING.md)
- **Tool coverage system:** [`tool_coverage/README.md`](tool_coverage/README.md)

# Contributing

To contribute changes to the schema, please create a new branch, modify the schema CSV as desired, commit, and file a PR. The jsonld will automatically be updated. Please do not modify the jsonld manually. 

## Updating Schema-viz Files

To update the nf-research-tools-attributes.csv and nf-research-tools.json:

1) Run the following command in Schematic and save the json output file as nf-research-tools.json in the schema-viz/data directory.

```
schematic viz -c config.yml tangled_tree_layers -ft component 
```
2) Run the following command in Schematic and save the csv output file as nf-research-tools-attributes.csv in the schema-viz/data directory.
```
schematic viz -c config.yml attributes
```
