---
search:
  boost: 5.0
---

# Slot: authors 


_Writers of the publication._



<div data-search-exclude markdown="1">



URI: [schema:author](http://schema.org/author)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Publication](Publication.md) | A publication associated with the development or usage of a resource |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Publication](Publication.md) |
| Slot URI | [schema:author](http://schema.org/author) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Multivalued | Yes |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | schema:author |
| native | nftools:authors |




## LinkML Source

<details>
```yaml
name: authors
description: Writers of the publication.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:author
domain_of:
- Publication
range: string
multivalued: true

```
</details></div>