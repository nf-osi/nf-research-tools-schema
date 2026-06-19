---
search:
  boost: 5.0
---

# Slot: clinicalData 


_Available clinical data from the patient._



<div data-search-exclude markdown="1">



URI: [nftools:clinicalData](https://w3id.org/nf-research-tools/clinicalData)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [PatientDerivedModel](PatientDerivedModel.md) | Patient-derived models including patient-derived xenografts (PDX), humanized ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [PatientDerivedModel](PatientDerivedModel.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
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
| self | nftools:clinicalData |
| native | nftools:clinicalData |




## LinkML Source

<details>
```yaml
name: clinicalData
description: Available clinical data from the patient.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: PatientDerivedModel
domain_of:
- PatientDerivedModel
range: string

```
</details></div>