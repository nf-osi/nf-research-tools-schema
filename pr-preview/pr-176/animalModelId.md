---
search:
  boost: 5.0
---

# Slot: animalModelId 


_Foreign key to AnimalModel (resourceId). Null if this mutation is linked to a CellLine instead._



<div data-search-exclude markdown="1">



URI: [nftools:animalModelId](https://w3id.org/nf-research-tools/animalModelId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Mutation](Mutation.md) | Junction table linking tool-type resources (AnimalModel, CellLine) to their M... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Mutation](Mutation.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [Mutation](Mutation.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:animalModelId |
| native | nftools:animalModelId |




## LinkML Source

<details>
```yaml
name: animalModelId
description: Foreign key to AnimalModel (resourceId). Null if this mutation is linked
  to a CellLine instead.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Mutation
domain_of:
- Mutation
range: string

```
</details></div>