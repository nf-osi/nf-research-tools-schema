---
search:
  boost: 5.0
---

# Slot: funderId 


_A unique identifier for the funder._



<div data-search-exclude markdown="1">



URI: [nftools:funderId](https://w3id.org/nf-research-tools/funderId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Funder](Funder.md) | A person or organization that provides money for a particular resource |  no  |
| [DevelopmentRecord](DevelopmentRecord.md) | Junction table linking a resource to its investigators, publications, and fun... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [DevelopmentRecord](DevelopmentRecord.md), [Funder](Funder.md) |

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
| self | nftools:funderId |
| native | nftools:funderId |




## LinkML Source

<details>
```yaml
name: funderId
description: A unique identifier for the funder.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- DevelopmentRecord
- Funder
range: string
required: true

```
</details></div>