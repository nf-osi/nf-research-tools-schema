---
search:
  boost: 5.0
---

# Slot: catalogNumber 


_The catalog number associated with the resource pertaining to the vendor._



<div data-search-exclude markdown="1">



URI: [nftools:catalogNumber](https://w3id.org/nf-research-tools/catalogNumber)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [VendorItem](VendorItem.md) | A resource listing from a specific vendor, including catalog information and ... |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [VendorItem](VendorItem.md) |

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
| self | nftools:catalogNumber |
| native | nftools:catalogNumber |




## LinkML Source

<details>
```yaml
name: catalogNumber
description: The catalog number associated with the resource pertaining to the vendor.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
domain_of:
- VendorItem
range: string
required: true

```
</details></div>