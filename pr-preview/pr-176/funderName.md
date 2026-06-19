---
search:
  boost: 5.0
---

# Slot: funderName 


_The name of the person or agency that funded the development of the resource._



<div data-search-exclude markdown="1">



URI: [schema:name](http://schema.org/name)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Funder](Funder.md) | A person or organization that provides money for a particular resource |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Funder](Funder.md) |
| Slot URI | [schema:name](http://schema.org/name) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | schema:name |
| native | nftools:funderName |




## LinkML Source

<details>
```yaml
name: funderName
description: The name of the person or agency that funded the development of the resource.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:name
domain_of:
- Funder
range: string

```
</details></div>