---
search:
  boost: 5.0
---

# Slot: mutationDetailsId 


_A unique identifier for the mutation._



<div data-search-exclude markdown="1">



URI: [nftools:mutationDetailsId](https://w3id.org/nf-research-tools/mutationDetailsId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [MutationDetails](MutationDetails.md) | Details of a genetic mutation, including type, method, affected gene, and seq... |  no  |
| [Mutation](Mutation.md) | Junction table linking tool-type resources (AnimalModel, CellLine) to their M... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Mutation](Mutation.md), [MutationDetails](MutationDetails.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Identifier | Yes |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:mutationDetailsId |
| native | nftools:mutationDetailsId |




## LinkML Source

<details>
```yaml
name: mutationDetailsId
description: A unique identifier for the mutation.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- Mutation
- MutationDetails
range: string
required: true

```
</details></div>