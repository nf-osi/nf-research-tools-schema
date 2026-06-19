---
search:
  boost: 5.0
---

# Slot: insertSpecies 


_Species of the insert._



<div data-search-exclude markdown="1">



URI: [nftools:insertSpecies](https://w3id.org/nf-research-tools/insertSpecies)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [GeneticReagent](GeneticReagent.md) | Genetic reagents including plasmids, viral vectors, CRISPR constructs, and ot... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [SpeciesEnum](SpeciesEnum.md) |
| Domain Of | [GeneticReagent](GeneticReagent.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
| Multivalued | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [GeneticReagent](GeneticReagent.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:insertSpecies |
| native | nftools:insertSpecies |




## LinkML Source

<details>
```yaml
name: insertSpecies
description: Species of the insert.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: GeneticReagent
domain_of:
- GeneticReagent
range: SpeciesEnum
required: true
multivalued: true

```
</details></div>