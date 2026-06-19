---
search:
  boost: 5.0
---

# Slot: cellLineId 


_Foreign key to CellLine (resourceId). Null if this mutation is linked to an AnimalModel instead._



<div data-search-exclude markdown="1">



URI: [nftools:cellLineId](https://w3id.org/nf-research-tools/cellLineId)
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
| self | nftools:cellLineId |
| native | nftools:cellLineId |




## LinkML Source

<details>
```yaml
name: cellLineId
description: Foreign key to CellLine (resourceId). Null if this mutation is linked
  to an AnimalModel instead.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Mutation
domain_of:
- Mutation
range: string

```
</details></div>