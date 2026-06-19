---
search:
  boost: 5.0
---

# Slot: observationType 


_Type of observation. Valid values depend on the resource type._



<div data-search-exclude markdown="1">



URI: [nftools:observationType](https://w3id.org/nf-research-tools/observationType)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Observation](Observation.md) | A remark, statement, or comment based on the resource |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ObservationTypeEnum](ObservationTypeEnum.md) |
| Domain Of | [Observation](Observation.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
| Multivalued | Yes |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:observationType |
| native | nftools:observationType |




## LinkML Source

<details>
```yaml
name: observationType
description: Type of observation. Valid values depend on the resource type.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- Observation
range: ObservationTypeEnum
required: true
multivalued: true

```
</details></div>