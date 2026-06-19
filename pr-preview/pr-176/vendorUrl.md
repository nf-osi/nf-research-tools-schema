---
search:
  boost: 5.0
---

# Slot: vendorUrl 


_The vendor website URL._



<div data-search-exclude markdown="1">



URI: [schema:url](http://schema.org/url)
<!-- no inheritance hierarchy -->





## Applicable Classes

| Name | Description | Modifies Slot |
| --- | --- | --- |
| [Vendor](Vendor.md) | A person or company offering the resource for sale |  no  |






## Properties

### Type and Range

| Property | Value |
| --- | --- |
| Range | [Uri](Uri.md) |
| Domain Of | [Vendor](Vendor.md) |
| Slot URI | [schema:url](http://schema.org/url) |

### Cardinality and Requirements

| Property | Value |
| --- | --- |










## Identifier and Mapping Information





### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | schema:url |
| native | nftools:vendorUrl |




## LinkML Source

<details>
```yaml
name: vendorUrl
description: The vendor website URL.
from_schema: https://w3id.org/nf-research-tools
rank: 1000
slot_uri: schema:url
domain_of:
- Vendor
range: uri

```
</details></div>