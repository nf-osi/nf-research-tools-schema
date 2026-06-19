---
search:
  boost: 5.0
---

# Slot: resourceName 


_The canonical name of the resource._



<div data-search-exclude markdown="1">



URI: [schema:name](http://schema.org/name)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Tool](Tool.md) | A research tool or resource used in the NF research process |  no  |
| [AnimalModel](AnimalModel.md) | An animal sufficiently like humans in its anatomy, physiology, or response to... |  no  |
| [CellLine](CellLine.md) | A cell culture selected for uniformity from a cell population derived from a ... |  no  |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  no  |
| [GeneticReagent](GeneticReagent.md) | Genetic reagents including plasmids, viral vectors, CRISPR constructs, and ot... |  no  |
| [Biobank](Biobank.md) | A large collection of biological or medical data and tissue samples, amassed ... |  no  |
| [ComputationalTool](ComputationalTool.md) | Computational tools including software and analysis pipelines used in NF rese... |  no  |
| [OrganoidProtocol](OrganoidProtocol.md) | Advanced 3D cellular models including organoids, assembloids, spheroids, and ... |  no  |
| [PatientDerivedModel](PatientDerivedModel.md) | Patient-derived models including patient-derived xenografts (PDX), humanized ... |  no  |
| [ClinicalAssessmentTool](ClinicalAssessmentTool.md) | Clinical assessment tools including questionnaires, quality of life instrumen... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Tool](Tool.md) |
| Slot URI | [schema:name](http://schema.org/name) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | schema:name |
| native | nftools:resourceName |




## LinkML Source

<details>
```yaml
name: resourceName
description: The canonical name of the resource.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:name
domain_of:
- Tool
range: string
required: true

```
</details></div>