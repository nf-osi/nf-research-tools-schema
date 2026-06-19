---
search:
  boost: 5.0
---

# Slot: geneticDisorder 


_Genetic disorders associated with the resource._



<div data-search-exclude markdown="1">



URI: [nftools:geneticDisorder](https://w3id.org/nf-research-tools/geneticDisorder)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [HasGeneticDisorder](HasGeneticDisorder.md) | Mixin for tool types associated with a genetic disorder and its manifestation... |  no  |
| [AnimalModel](AnimalModel.md) | An animal sufficiently like humans in its anatomy, physiology, or response to... |  yes  |
| [CellLine](CellLine.md) | A cell culture selected for uniformity from a cell population derived from a ... |  no  |
| [Biobank](Biobank.md) | A large collection of biological or medical data and tissue samples, amassed ... |  yes  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [GeneticDisorderEnum](GeneticDisorderEnum.md) |
| Domain Of | [HasGeneticDisorder](HasGeneticDisorder.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Multivalued | Yes |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:geneticDisorder |
| native | nftools:geneticDisorder |




## LinkML Source

<details>
```yaml
name: geneticDisorder
description: Genetic disorders associated with the resource.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- HasGeneticDisorder
range: GeneticDisorderEnum
multivalued: true

```
</details></div>