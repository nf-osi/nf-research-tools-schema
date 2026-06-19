---
search:
  boost: 5.0
---

# Slot: usageId 


_A unique identifier for this usage record._



<div data-search-exclude markdown="1">



URI: [nftools:usageId](https://w3id.org/nf-research-tools/usageId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Usage](Usage.md) | Junction table linking a resource to publications that cite or use it |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Usage](Usage.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Identifier | Yes |
| Owner | [Usage](Usage.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:usageId |
| native | nftools:usageId |




## LinkML Source

<details>
```yaml
name: usageId
description: A unique identifier for this usage record.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
owner: Usage
domain_of:
- Usage
range: string
required: true

```
</details></div>