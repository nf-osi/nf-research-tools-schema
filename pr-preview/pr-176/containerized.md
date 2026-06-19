---
search:
  boost: 5.0
---

# Slot: containerized 


_Whether containerized versions (Docker, Singularity) are available._



<div data-search-exclude markdown="1">



URI: [nftools:containerized](https://w3id.org/nf-research-tools/containerized)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [ComputationalTool](ComputationalTool.md) | Computational tools including software and analysis pipelines used in NF rese... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [YesNoUnknownEnum](YesNoUnknownEnum.md) |
| Domain Of | [ComputationalTool](ComputationalTool.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [ComputationalTool](ComputationalTool.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:containerized |
| native | nftools:containerized |




## LinkML Source

<details>
```yaml
name: containerized
description: Whether containerized versions (Docker, Singularity) are available.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: ComputationalTool
domain_of:
- ComputationalTool
range: YesNoUnknownEnum

```
</details></div>