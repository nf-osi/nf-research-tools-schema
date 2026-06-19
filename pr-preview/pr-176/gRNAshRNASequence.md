---
search:
  boost: 5.0
---

# Slot: gRNAshRNASequence 


_The sequence of the gRNA or shRNA for the gene insert, if present._



<div data-search-exclude markdown="1">



URI: [nftools:gRNAshRNASequence](https://w3id.org/nf-research-tools/gRNAshRNASequence)
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
| self | nftools:gRNAshRNASequence |
| native | nftools:gRNAshRNASequence |




## LinkML Source

<details>
```yaml
name: gRNAshRNASequence
description: The sequence of the gRNA or shRNA for the gene insert, if present.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: GeneticReagent
domain_of:
- GeneticReagent
range: string

```
</details></div>