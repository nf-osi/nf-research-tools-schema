---
search:
  boost: 5.0
---

# Slot: transplantationDonor 


_Foreign key to Donor (donorId). The donor used in transplantation experiments._



<div data-search-exclude markdown="1">



URI: [nftools:transplantationDonor](https://w3id.org/nf-research-tools/transplantationDonor)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [AnimalModel](AnimalModel.md) | An animal sufficiently like humans in its anatomy, physiology, or response to... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [AnimalModel](AnimalModel.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:transplantationDonor |
| native | nftools:transplantationDonor |




## LinkML Source

<details>
```yaml
name: transplantationDonor
description: Foreign key to Donor (donorId). The donor used in transplantation experiments.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- AnimalModel
range: string

```
</details></div>