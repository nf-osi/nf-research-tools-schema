---
search:
  boost: 5.0
---

# Slot: resourceType 


_Type of resource._



<div data-search-exclude markdown="1">



URI: [nftools:resourceType](https://w3id.org/nf-research-tools/resourceType)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Tool](Tool.md) | A research tool or resource used in the NF research process |  no  |
| [AnimalModel](AnimalModel.md) | An animal sufficiently like humans in its anatomy, physiology, or response to... |  yes  |
| [CellLine](CellLine.md) | A cell culture selected for uniformity from a cell population derived from a ... |  yes  |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  yes  |
| [GeneticReagent](GeneticReagent.md) | Genetic reagents including plasmids, viral vectors, CRISPR constructs, and ot... |  yes  |
| [Biobank](Biobank.md) | A large collection of biological or medical data and tissue samples, amassed ... |  yes  |
| [ComputationalTool](ComputationalTool.md) | Computational tools including software and analysis pipelines used in NF rese... |  yes  |
| [OrganoidProtocol](OrganoidProtocol.md) | Advanced 3D cellular models including organoids, assembloids, spheroids, and ... |  yes  |
| [PatientDerivedModel](PatientDerivedModel.md) | Patient-derived models including patient-derived xenografts (PDX), humanized ... |  yes  |
| [ClinicalAssessmentTool](ClinicalAssessmentTool.md) | Clinical assessment tools including questionnaires, quality of life instrumen... |  yes  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ResourceTypeEnum](ResourceTypeEnum.md) |
| Domain Of | [Tool](Tool.md) |

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
| self | nftools:resourceType |
| native | nftools:resourceType |




## LinkML Source

<details>
```yaml
name: resourceType
description: Type of resource.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- Tool
range: ResourceTypeEnum
required: true

```
</details></div>