---
search:
  boost: 5.0
---

# Slot: observationLink 


_A link/reference related to the observation. If the reference has a DOI or PubMed ID, use the publication field instead._



<div data-search-exclude markdown="1">



URI: [nftools:observationLink](https://w3id.org/nf-research-tools/observationLink)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Observation](Observation.md) | A remark, statement, or comment based on the resource |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [Uri](Uri.md) |
| Domain Of | [Observation](Observation.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:observationLink |
| native | nftools:observationLink |




## LinkML Source

<details>
```yaml
name: observationLink
description: A link/reference related to the observation. If the reference has a DOI
  or PubMed ID, use the publication field instead.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- Observation
range: uri

```
</details></div>