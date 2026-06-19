---
search:
  boost: 5.0
---

# Slot: donor 


_Foreign key to Donor (donorId). The biological donor from which the resource was derived._



<div data-search-exclude markdown="1">



URI: [nftools:donor](https://w3id.org/nf-research-tools/donor)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [AnimalModel](AnimalModel.md) | An animal sufficiently like humans in its anatomy, physiology, or response to... |  no  |
| [CellLine](CellLine.md) | A cell culture selected for uniformity from a cell population derived from a ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [AnimalModel](AnimalModel.md), [CellLine](CellLine.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:donor |
| native | nftools:donor |




## LinkML Source

<details>
```yaml
name: donor
description: Foreign key to Donor (donorId). The biological donor from which the resource
  was derived.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- AnimalModel
- CellLine
range: string

```
</details></div>