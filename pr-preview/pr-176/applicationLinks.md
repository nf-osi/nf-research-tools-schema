---
search:
  boost: 5.0
---

# Slot: applicationLinks 


_Shareable links related to the resource application._



<div data-search-exclude markdown="1">



URI: [nftools:applicationLinks](https://w3id.org/nf-research-tools/applicationLinks)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [ResourceApplication](ResourceApplication.md) | Applications the resource can be used for, such as western blot, immunofluore... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [Uri](Uri.md) |
| Domain Of | [ResourceApplication](ResourceApplication.md) |

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
| self | nftools:applicationLinks |
| native | nftools:applicationLinks |




## LinkML Source

<details>
```yaml
name: applicationLinks
description: Shareable links related to the resource application.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- ResourceApplication
range: uri
multivalued: true

```
</details></div>