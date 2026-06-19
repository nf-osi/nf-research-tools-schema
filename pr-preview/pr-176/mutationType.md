---
search:
  boost: 5.0
---

# Slot: mutationType 


_The type of mutation, vocabulary aligned with MGI mutation types._



<div data-search-exclude markdown="1">



URI: [nftools:mutationType](https://w3id.org/nf-research-tools/mutationType)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [MutationDetails](MutationDetails.md) | Details of a genetic mutation, including type, method, affected gene, and seq... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [MutationTypeEnum](MutationTypeEnum.md) |
| Domain Of | [MutationDetails](MutationDetails.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Multivalued | Yes |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:mutationType |
| native | nftools:mutationType |




## LinkML Source

<details>
```yaml
name: mutationType
description: The type of mutation, vocabulary aligned with MGI mutation types.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- MutationDetails
range: MutationTypeEnum
multivalued: true

```
</details></div>