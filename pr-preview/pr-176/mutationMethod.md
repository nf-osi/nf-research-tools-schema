---
search:
  boost: 5.0
---

# Slot: mutationMethod 


_The method used to alter the resource, vocabulary aligned with MGI allele origin types._



<div data-search-exclude markdown="1">



URI: [nftools:mutationMethod](https://w3id.org/nf-research-tools/mutationMethod)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [MutationDetails](MutationDetails.md) | Details of a genetic mutation, including type, method, affected gene, and seq... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [MutationMethodEnum](MutationMethodEnum.md) |
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
| self | nftools:mutationMethod |
| native | nftools:mutationMethod |




## LinkML Source

<details>
```yaml
name: mutationMethod
description: The method used to alter the resource, vocabulary aligned with MGI allele
  origin types.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- MutationDetails
range: MutationMethodEnum
multivalued: true

```
</details></div>