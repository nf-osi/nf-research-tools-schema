---
search:
  boost: 5.0
---

# Slot: nTerminalTag 


_Tags on the N terminal 5' end of the gene insert. Only tags that are in frame._



<div data-search-exclude markdown="1">



URI: [nftools:nTerminalTag](https://w3id.org/nf-research-tools/nTerminalTag)
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
| self | nftools:nTerminalTag |
| native | nftools:nTerminalTag |




## LinkML Source

<details>
```yaml
name: nTerminalTag
description: Tags on the N terminal 5' end of the gene insert. Only tags that are
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