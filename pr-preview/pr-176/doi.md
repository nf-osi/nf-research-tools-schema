---
search:
  boost: 5.0
---

# Slot: doi 


_The digital object identifier in the form https://www.doi.org/{doi}, per CrossRef DOI display guidelines._



<div data-search-exclude markdown="1">



URI: [schema:identifier](http://schema.org/identifier)
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
| Slot URI | [schema:identifier](http://schema.org/identifier) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | schema:identifier |
| native | nftools:doi |




## LinkML Source

<details>
```yaml
name: doi
description: The digital object identifier in the form https://www.doi.org/{doi},
  per CrossRef DOI display guidelines.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:identifier
domain_of:
- Publication
range: string

```
</details></div>