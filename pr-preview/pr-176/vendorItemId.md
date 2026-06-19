---
search:
  boost: 5.0
---

# Slot: vendorItemId 


_A unique identifier for the vendor item listing._



<div data-search-exclude markdown="1">



URI: [nftools:vendorItemId](https://w3id.org/nf-research-tools/vendorItemId)
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
| self | nftools:vendorItemId |
| native | nftools:vendorItemId |




## LinkML Source

<details>
```yaml
name: vendorItemId
description: A unique identifier for the vendor item listing.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
identifier: true
domain_of:
- VendorItem
range: string
required: true

```
</details></div>