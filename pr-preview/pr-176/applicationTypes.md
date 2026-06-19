---
search:
  boost: 5.0
---

# Slot: applicationTypes 


_One or more uses for the resource (e.g. western blot, immunofluorescence)._



<div data-search-exclude markdown="1">



URI: [nftools:applicationTypes](https://w3id.org/nf-research-tools/applicationTypes)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [ResourceApplication](ResourceApplication.md) | Applications the resource can be used for, such as western blot, immunofluore... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ApplicationTypeEnum](ApplicationTypeEnum.md) |
| Domain Of | [ResourceApplication](ResourceApplication.md) |

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
| self | nftools:applicationTypes |
| native | nftools:applicationTypes |




## LinkML Source

<details>
```yaml
name: applicationTypes
description: One or more uses for the resource (e.g. western blot, immunofluorescence).
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- ResourceApplication
range: ApplicationTypeEnum
required: true
multivalued: true

```
</details></div>