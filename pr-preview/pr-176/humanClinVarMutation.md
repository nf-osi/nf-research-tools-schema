---
search:
  boost: 5.0
---

# Slot: humanClinVarMutation 


_The human equivalent of the mutation in ClinVar/HGVS notation. Used to link animal model mutations to human disease mutations._



<div data-search-exclude markdown="1">



URI: [nftools:humanClinVarMutation](https://w3id.org/nf-research-tools/humanClinVarMutation)
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
| self | nftools:humanClinVarMutation |
| native | nftools:humanClinVarMutation |




## LinkML Source

<details>
```yaml
name: humanClinVarMutation
description: The human equivalent of the mutation in ClinVar/HGVS notation. Used to
  link animal model mutations to human disease mutations.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- MutationDetails
range: string

```
</details></div>