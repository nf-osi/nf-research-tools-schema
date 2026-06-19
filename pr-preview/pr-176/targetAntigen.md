---
search:
  boost: 5.0
---

# Slot: targetAntigen 


_Antigen that is targeted by antibody (e.g. Neurofibromin 1 human)._



<div data-search-exclude markdown="1">



URI: [nftools:targetAntigen](https://w3id.org/nf-research-tools/targetAntigen)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Antibody](Antibody.md) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |
| Required | Yes |
### Slot Characteristics

| Property | Value |
| --- | --- |
| Owner | [Antibody](Antibody.md) |












## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:targetAntigen |
| native | nftools:targetAntigen |




## LinkML Source

<details>
```yaml
name: targetAntigen
description: Antigen that is targeted by antibody (e.g. Neurofibromin 1 human).
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Antibody
domain_of:
- Antibody
range: string
required: true

```
</details></div>