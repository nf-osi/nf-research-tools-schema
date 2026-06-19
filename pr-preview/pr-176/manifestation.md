---
search:
  boost: 5.0
---

# Slot: manifestation 


_Manifestations or symptoms that this resource is used to model (e.g. tumor type, behavioral phenotype)._



<div data-search-exclude markdown="1">



URI: [nftools:manifestation](https://w3id.org/nf-research-tools/manifestation)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [HasGeneticDisorder](HasGeneticDisorder.md) | Mixin for tool types associated with a genetic disorder and its manifestation... |  no  |
| [AnimalModel](AnimalModel.md) | An animal sufficiently like humans in its anatomy, physiology, or response to... |  yes  |
| [CellLine](CellLine.md) | A cell culture selected for uniformity from a cell population derived from a ... |  no  |
| [Biobank](Biobank.md) | A large collection of biological or medical data and tissue samples, amassed ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
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
| self | nftools:manifestation |
| native | nftools:manifestation |




## LinkML Source

<details>
```yaml
name: manifestation
description: Manifestations or symptoms that this resource is used to model (e.g.
  tumor type, behavioral phenotype).
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- HasGeneticDisorder
range: string
multivalued: true

```
</details></div>