---
search:
  boost: 5.0
---

# Slot: mutationId 


_A unique identifier for this junction record._



<div data-search-exclude markdown="1">



URI: [nftools:mutationId](https://w3id.org/nf-research-tools/mutationId)
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
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Identifier | Yes |
| Owner | [Mutation](Mutation.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:mutationId |
| native | nftools:mutationId |




## LinkML Source

<details>
```yaml
name: mutationId
description: A unique identifier for this junction record.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
owner: Mutation
domain_of:
- Mutation
range: string
required: true

```
</details></div>