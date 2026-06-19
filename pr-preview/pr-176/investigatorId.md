---
search:
  boost: 5.0
---

# Slot: investigatorId 


_A unique identifier for the investigator._



<div data-search-exclude markdown="1">



URI: [nftools:investigatorId](https://w3id.org/nf-research-tools/investigatorId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Investigator](Investigator.md) | A person who carries out a formal inquiry or investigation into the developme... |  no  |
| [DevelopmentRecord](DevelopmentRecord.md) | Junction table linking a resource to its investigators, publications, and fun... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [DevelopmentRecord](DevelopmentRecord.md), [Investigator](Investigator.md) |

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
| self | nftools:investigatorId |
| native | nftools:investigatorId |




## LinkML Source

<details>
```yaml
name: investigatorId
description: A unique identifier for the investigator.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- DevelopmentRecord
- Investigator
range: string
required: true

```
</details></div>