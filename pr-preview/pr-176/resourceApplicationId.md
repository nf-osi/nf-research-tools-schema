---
search:
  boost: 5.0
---

# Slot: resourceApplicationId 


_A unique identifier for the resource application record._



<div data-search-exclude markdown="1">



URI: [nftools:resourceApplicationId](https://w3id.org/nf-research-tools/resourceApplicationId)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [ResourceApplication](ResourceApplication.md) | Applications the resource can be used for, such as western blot, immunofluore... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [ResourceApplication](ResourceApplication.md) |

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
| self | nftools:resourceApplicationId |
| native | nftools:resourceApplicationId |




## LinkML Source

<details>
```yaml
name: resourceApplicationId
description: A unique identifier for the resource application record.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- ResourceApplication
range: string
required: true

```
</details></div>