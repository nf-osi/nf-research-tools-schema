---
search:
  boost: 5.0
---

# Slot: validationMethods 


_Methods used to validate model fidelity to patient._



<div data-search-exclude markdown="1">



URI: [nftools:validationMethods](https://w3id.org/nf-research-tools/validationMethods)
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
| Multivalued | Yes |
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
| self | nftools:validationMethods |
| native | nftools:validationMethods |




## LinkML Source

<details>
```yaml
name: validationMethods
description: Methods used to validate model fidelity to patient.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: PatientDerivedModel
domain_of:
- PatientDerivedModel
range: string
multivalued: true

```
</details></div>