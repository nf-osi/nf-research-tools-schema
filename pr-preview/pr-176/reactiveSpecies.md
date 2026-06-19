---
search:
  boost: 5.0
---

# Slot: reactiveSpecies 


_Species the antibody has been shown to crossreact with the target protein._



<div data-search-exclude markdown="1">



URI: [nftools:reactiveSpecies](https://w3id.org/nf-research-tools/reactiveSpecies)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ReactiveSpeciesEnum](ReactiveSpeciesEnum.md) |
| Domain Of | [Antibody](Antibody.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
| Multivalued | Yes |
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
| self | nftools:reactiveSpecies |
| native | nftools:reactiveSpecies |




## LinkML Source

<details>
```yaml
name: reactiveSpecies
description: Species the antibody has been shown to crossreact with the target protein.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Antibody
domain_of:
- Antibody
range: ReactiveSpeciesEnum
required: true
multivalued: true

```
</details></div>