---
search:
  boost: 5.0
---

# Slot: softwareName 


_The name of the software or computational tool._



<div data-search-exclude markdown="1">



URI: [nftools:softwareName](https://w3id.org/nf-research-tools/softwareName)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [ComputationalTool](ComputationalTool.md) | Computational tools including software and analysis pipelines used in NF rese... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [ComputationalTool](ComputationalTool.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
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
| self | nftools:softwareName |
| native | nftools:softwareName |




## LinkML Source

<details>
```yaml
name: softwareName
description: The name of the software or computational tool.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: ComputationalTool
domain_of:
- ComputationalTool
range: string
required: true

```
</details></div>