---
search:
  boost: 5.0
---

# Slot: hostOrganism 


_The species of the organism that hosts the antibody._



<div data-search-exclude markdown="1">



URI: [nftools:hostOrganism](https://w3id.org/nf-research-tools/hostOrganism)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [HostOrganismEnum](HostOrganismEnum.md) |
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
| self | nftools:hostOrganism |
| native | nftools:hostOrganism |




## LinkML Source

<details>
```yaml
name: hostOrganism
description: The species of the organism that hosts the antibody.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
owner: Antibody
domain_of:
- Antibody
range: HostOrganismEnum
required: true

```
</details></div>