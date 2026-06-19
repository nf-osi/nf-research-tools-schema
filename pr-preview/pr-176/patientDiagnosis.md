---
search:
  boost: 5.0
---

# Slot: patientDiagnosis 


_Original patient diagnosis or condition._



<div data-search-exclude markdown="1">



URI: [nftools:patientDiagnosis](https://w3id.org/nf-research-tools/patientDiagnosis)
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
| self | nftools:patientDiagnosis |
| native | nftools:patientDiagnosis |




## LinkML Source

<details>
```yaml
name: patientDiagnosis
description: Original patient diagnosis or condition.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: PatientDerivedModel
domain_of:
- PatientDerivedModel
range: string
required: true

```
</details></div>