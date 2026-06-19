---
search:
  boost: 5.0
---

# Slot: species 


_The species of the individual the resource was derived from._



<div data-search-exclude markdown="1">



URI: [nftools:species](https://w3id.org/nf-research-tools/species)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Donor](Donor.md) | A person, animal, or other organism that is the contributor of the resource |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [SpeciesEnum](SpeciesEnum.md) |
| Domain Of | [Donor](Donor.md) |

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
| self | nftools:species |
| native | nftools:species |




## LinkML Source

<details>
```yaml
name: species
description: The species of the individual the resource was derived from.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- Donor
range: SpeciesEnum
required: true
multivalued: true

```
</details></div>