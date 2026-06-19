---
search:
  boost: 5.0
---

# Slot: insertName 


_Name of the main gene insert in the plasmid._



<div data-search-exclude markdown="1">



URI: [nftools:insertName](https://w3id.org/nf-research-tools/insertName)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [GeneticReagent](GeneticReagent.md) | Genetic reagents including plasmids, viral vectors, CRISPR constructs, and ot... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [GeneticReagent](GeneticReagent.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [GeneticReagent](GeneticReagent.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:insertName |
| native | nftools:insertName |




## LinkML Source

<details>
```yaml
name: insertName
description: Name of the main gene insert in the plasmid.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: GeneticReagent
domain_of:
- GeneticReagent
range: string
required: true

```
</details></div>