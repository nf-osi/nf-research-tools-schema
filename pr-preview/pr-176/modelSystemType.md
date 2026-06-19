---
search:
  boost: 5.0
---

# Slot: modelSystemType 


_Type of patient-derived model system._



<div data-search-exclude markdown="1">



URI: [nftools:modelSystemType](https://w3id.org/nf-research-tools/modelSystemType)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [PatientDerivedModel](PatientDerivedModel.md) | Patient-derived models including patient-derived xenografts (PDX), humanized ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ModelSystemTypeEnum](ModelSystemTypeEnum.md) |
| Domain Of | [PatientDerivedModel](PatientDerivedModel.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [PatientDerivedModel](PatientDerivedModel.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:modelSystemType |
| native | nftools:modelSystemType |




## LinkML Source

<details>
```yaml
name: modelSystemType
description: Type of patient-derived model system.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: PatientDerivedModel
domain_of:
- PatientDerivedModel
range: ModelSystemTypeEnum
required: true

```
</details></div>