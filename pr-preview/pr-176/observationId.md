---
search:
  boost: 5.0
---

# Slot: observationId 


_A unique identifier for the observation._



<div data-search-exclude markdown="1">



URI: [nftools:observationId](https://w3id.org/nf-research-tools/observationId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Observation](Observation.md) | A remark, statement, or comment based on the resource |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Observation](Observation.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Identifier | Yes |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:observationId |
| native | nftools:observationId |




## LinkML Source

<details>
```yaml
name: observationId
description: A unique identifier for the observation.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- Observation
range: string
required: true

```
</details></div>