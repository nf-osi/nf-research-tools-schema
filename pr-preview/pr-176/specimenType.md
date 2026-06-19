---
search:
  boost: 5.0
---

# Slot: specimenType 


_The types of specimens that are banked._



<div data-search-exclude markdown="1">



URI: [nftools:specimenType](https://w3id.org/nf-research-tools/specimenType)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Biobank](Biobank.md) | A large collection of biological or medical data and tissue samples, amassed ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [SpecimenTypeEnum](SpecimenTypeEnum.md) |
| Domain Of | [Biobank](Biobank.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
| Multivalued | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [Biobank](Biobank.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:specimenType |
| native | nftools:specimenType |




## LinkML Source

<details>
```yaml
name: specimenType
description: The types of specimens that are banked.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Biobank
domain_of:
- Biobank
range: SpecimenTypeEnum
required: true
multivalued: true

```
</details></div>