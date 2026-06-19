---
search:
  boost: 5.0
---

# Slot: alleleType 


_The type of genetic alteration, vocabulary aligned with MGI allele subtypes._



<div data-search-exclude markdown="1">



URI: [nftools:alleleType](https://w3id.org/nf-research-tools/alleleType)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [MutationDetails](MutationDetails.md) | Details of a genetic mutation, including type, method, affected gene, and seq... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [AlleleTypeEnum](AlleleTypeEnum.md) |
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
| self | nftools:alleleType |
| native | nftools:alleleType |




## LinkML Source

<details>
```yaml
name: alleleType
description: The type of genetic alteration, vocabulary aligned with MGI allele subtypes.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- MutationDetails
range: AlleleTypeEnum
multivalued: true

```
</details></div>