---
search:
  boost: 5.0
---

# Slot: affectedGeneSymbol 


_The gene symbol for the mutated gene (e.g. NF1, SUZ12, SMARCB1)._



<div data-search-exclude markdown="1">



URI: [nftools:affectedGeneSymbol](https://w3id.org/nf-research-tools/affectedGeneSymbol)
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
| self | nftools:affectedGeneSymbol |
| native | nftools:affectedGeneSymbol |




## LinkML Source

<details>
```yaml
name: affectedGeneSymbol
description: The gene symbol for the mutated gene (e.g. NF1, SUZ12, SMARCB1).
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- MutationDetails
range: string

```
</details></div>