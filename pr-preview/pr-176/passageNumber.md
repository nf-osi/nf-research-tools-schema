---
search:
  boost: 5.0
---

# Slot: passageNumber 


_Current passage number, if applicable._



<div data-search-exclude markdown="1">



URI: [nftools:passageNumber](https://w3id.org/nf-research-tools/passageNumber)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [HasPassageNumber](HasPassageNumber.md) | Mixin for tool types that track passage number |  no  |
| [OrganoidProtocol](OrganoidProtocol.md) | Advanced 3D cellular models including organoids, assembloids, spheroids, and ... |  no  |
| [PatientDerivedModel](PatientDerivedModel.md) | Patient-derived models including patient-derived xenografts (PDX), humanized ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [HasPassageNumber](HasPassageNumber.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:passageNumber |
| native | nftools:passageNumber |




## LinkML Source

<details>
```yaml
name: passageNumber
description: Current passage number, if applicable.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- HasPassageNumber
range: string

```
</details></div>