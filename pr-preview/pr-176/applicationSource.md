---
search:
  boost: 5.0
---

# Slot: applicationSource 


_The source of resource application information._



<div data-search-exclude markdown="1">



URI: [nftools:applicationSource](https://w3id.org/nf-research-tools/applicationSource)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [ResourceApplication](ResourceApplication.md) | Applications the resource can be used for, such as western blot, immunofluore... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [ApplicationSourceEnum](ApplicationSourceEnum.md) |
| Domain Of | [ResourceApplication](ResourceApplication.md) |

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
| self | nftools:applicationSource |
| native | nftools:applicationSource |




## LinkML Source

<details>
```yaml
name: applicationSource
description: The source of resource application information.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- ResourceApplication
range: ApplicationSourceEnum
required: true

```
</details></div>