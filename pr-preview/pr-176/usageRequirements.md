---
search:
  boost: 5.0
---

# Slot: usageRequirements 


_Any known restrictions on use of the resource._



<div data-search-exclude markdown="1">



URI: [nftools:usageRequirements](https://w3id.org/nf-research-tools/usageRequirements)
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
| Range | [UsageRequirementEnum](UsageRequirementEnum.md) |
| Domain Of | [Tool](Tool.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Multivalued | Yes |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:usageRequirements |
| native | nftools:usageRequirements |




## LinkML Source

<details>
```yaml
name: usageRequirements
description: Any known restrictions on use of the resource.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- Tool
range: UsageRequirementEnum
multivalued: true

```
</details></div>