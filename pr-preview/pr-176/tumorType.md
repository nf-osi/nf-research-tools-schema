---
search:
  boost: 5.0
---

# Slot: tumorType 


_Tumor types associated with the resource._



<div data-search-exclude markdown="1">



URI: [nftools:tumorType](https://w3id.org/nf-research-tools/tumorType)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [HasTumorType](HasTumorType.md) | Mixin for tool types that model or bank specific tumor types |  no  |
| [Biobank](Biobank.md) | A large collection of biological or medical data and tissue samples, amassed ... |  yes  |
| [PatientDerivedModel](PatientDerivedModel.md) | Patient-derived models including patient-derived xenografts (PDX), humanized ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [TumorTypeEnum](TumorTypeEnum.md) |
| Domain Of | [HasTumorType](HasTumorType.md) |

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
| self | nftools:tumorType |
| native | nftools:tumorType |




## LinkML Source

<details>
```yaml
name: tumorType
description: Tumor types associated with the resource.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- HasTumorType
range: TumorTypeEnum
multivalued: true

```
</details></div>