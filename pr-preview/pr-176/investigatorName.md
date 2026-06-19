---
search:
  boost: 5.0
---

# Slot: investigatorName 


_The name of the investigator._



<div data-search-exclude markdown="1">



URI: [schema:name](http://schema.org/name)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Investigator](Investigator.md) | A person who carries out a formal inquiry or investigation into the developme... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Investigator](Investigator.md) |
| Slot URI | [schema:name](http://schema.org/name) |

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
| self | schema:name |
| native | nftools:investigatorName |




## LinkML Source

<details>
```yaml
name: investigatorName
description: The name of the investigator.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:name
domain_of:
- Investigator
range: string
required: true

```
</details></div>