---
search:
  boost: 5.0
---

# Slot: clonality 


_The type of clonality of the antibody._



<div data-search-exclude markdown="1">



URI: [nftools:clonality](https://w3id.org/nf-research-tools/clonality)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ClonalityEnum](ClonalityEnum.md) |
| Domain Of | [Antibody](Antibody.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [Antibody](Antibody.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:clonality |
| native | nftools:clonality |




## LinkML Source

<details>
```yaml
name: clonality
description: The type of clonality of the antibody.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Antibody
domain_of:
- Antibody
range: ClonalityEnum
required: true

```
</details></div>