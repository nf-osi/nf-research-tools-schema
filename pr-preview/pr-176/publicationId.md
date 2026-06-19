---
search:
  boost: 5.0
---

# Slot: publicationId 


_A unique identifier for the publication._



<div data-search-exclude markdown="1">



URI: [nftools:publicationId](https://w3id.org/nf-research-tools/publicationId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Publication](Publication.md) | A publication associated with the development or usage of a resource |  no  |
| [DevelopmentRecord](DevelopmentRecord.md) | Junction table linking a resource to its investigators, publications, and fun... |  no  |
| [Usage](Usage.md) | Junction table linking a resource to publications that cite or use it |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [DevelopmentRecord](DevelopmentRecord.md), [Usage](Usage.md), [Publication](Publication.md) |

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
| self | nftools:publicationId |
| native | nftools:publicationId |




## LinkML Source

<details>
```yaml
name: publicationId
description: A unique identifier for the publication.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- DevelopmentRecord
- Usage
- Publication
range: string
required: true

```
</details></div>