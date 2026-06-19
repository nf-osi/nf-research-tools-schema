---
search:
  boost: 5.0
---

# Slot: publicationTitle 


_The title of the publication._



<div data-search-exclude markdown="1">



URI: [schema:headline](http://schema.org/headline)
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
| Slot URI | [schema:headline](http://schema.org/headline) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | schema:headline |
| native | nftools:publicationTitle |




## LinkML Source

<details>
```yaml
name: publicationTitle
description: The title of the publication.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:headline
domain_of:
- Publication
range: string
required: true

```
</details></div>