---
search:
  boost: 5.0
---

# Slot: cTerminalTag 


_Tags on the C terminal 3' end of the gene insert. Only tags that are in frame._



<div data-search-exclude markdown="1">



URI: [nftools:cTerminalTag](https://w3id.org/nf-research-tools/cTerminalTag)
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
| Multivalued | Yes |
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
| self | nftools:cTerminalTag |
| native | nftools:cTerminalTag |




## LinkML Source

<details>
```yaml
name: cTerminalTag
description: Tags on the C terminal 3' end of the gene insert. Only tags that are
  in frame.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: GeneticReagent
domain_of:
- GeneticReagent
range: string
multivalued: true

```
</details></div>