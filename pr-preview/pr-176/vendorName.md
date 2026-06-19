---
search:
  boost: 5.0
---

# Slot: vendorName 


_The name of the vendor._



<div data-search-exclude markdown="1">



URI: [schema:name](http://schema.org/name)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Vendor](Vendor.md) | A person or company offering the resource for sale |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [String](String.md) |
| Domain Of | [Vendor](Vendor.md) |
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
| native | nftools:vendorName |




## LinkML Source

<details>
```yaml
name: vendorName
description: The name of the vendor.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:name
domain_of:
- Vendor
range: string

```
</details></div>