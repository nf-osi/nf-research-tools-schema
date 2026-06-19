---
search:
  boost: 5.0
---

# Slot: externalMutationId 


_An identifier from an organism database such as MGI or other curated variant resource, if available._



<div data-search-exclude markdown="1">



URI: [nftools:externalMutationId](https://w3id.org/nf-research-tools/externalMutationId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [MutationDetails](MutationDetails.md) | Details of a genetic mutation, including type, method, affected gene, and seq... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [MutationDetails](MutationDetails.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:externalMutationId |
| native | nftools:externalMutationId |




## LinkML Source

<details>
```yaml
name: externalMutationId
description: An identifier from an organism database such as MGI or other curated
  variant resource, if available.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- MutationDetails
range: string

```
</details></div>