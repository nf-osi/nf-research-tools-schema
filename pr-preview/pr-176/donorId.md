---
search:
  boost: 5.0
---

# Slot: donorId 


_A unique identifier for the donor._



<div data-search-exclude markdown="1">



URI: [nftools:donorId](https://w3id.org/nf-research-tools/donorId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Donor](Donor.md) | A person, animal, or other organism that is the contributor of the resource |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Donor](Donor.md) |

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
| self | nftools:donorId |
| native | nftools:donorId |




## LinkML Source

<details>
```yaml
name: donorId
description: A unique identifier for the donor.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- Donor
range: string
required: true

```
</details></div>