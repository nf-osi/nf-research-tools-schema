---
search:
  boost: 5.0
---

# Slot: hazardous 


_Whether the unmodified plasmid DNA requires handling at Biosafety Level 2 or higher._



<div data-search-exclude markdown="1">



URI: [nftools:hazardous](https://w3id.org/nf-research-tools/hazardous)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [GeneticReagent](GeneticReagent.md) | Genetic reagents including plasmids, viral vectors, CRISPR constructs, and ot... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [YesNoUnknownEnum](YesNoUnknownEnum.md) |
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
| self | nftools:hazardous |
| native | nftools:hazardous |




## LinkML Source

<details>
```yaml
name: hazardous
description: Whether the unmodified plasmid DNA requires handling at Biosafety Level
  2 or higher.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: GeneticReagent
domain_of:
- GeneticReagent
range: YesNoUnknownEnum
required: true

```
</details></div>