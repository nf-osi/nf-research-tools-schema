---
search:
  boost: 5.0
---

# Slot: uniprotId 


_The UniProt ID of the protein targeted by the antibody._



<div data-search-exclude markdown="1">



URI: [nftools:uniprotId](https://w3id.org/nf-research-tools/uniprotId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Antibody](Antibody.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [Antibody](Antibody.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:uniprotId |
| native | nftools:uniprotId |




## LinkML Source

<details>
```yaml
name: uniprotId
description: The UniProt ID of the protein targeted by the antibody.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Antibody
domain_of:
- Antibody
range: string

```
</details></div>