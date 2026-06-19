---
search:
  boost: 5.0
---

# Slot: conjugate 


_Whether the antibody is conjugated or nonconjugated._



<div data-search-exclude markdown="1">



URI: [nftools:conjugate](https://w3id.org/nf-research-tools/conjugate)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ConjugateEnum](ConjugateEnum.md) |
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
| self | nftools:conjugate |
| native | nftools:conjugate |




## LinkML Source

<details>
```yaml
name: conjugate
description: Whether the antibody is conjugated or nonconjugated.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Antibody
domain_of:
- Antibody
range: ConjugateEnum
required: true

```
</details></div>