---
search:
  boost: 10.0
---

# Class: DevelopmentRecord 


_Junction table linking a resource to its investigators, publications, and funders. Stored as a separate Synapse table; searchable via MaterializedView JOINs._



<div data-search-exclude markdown="1">



URI: [nftools:DevelopmentRecord](https://w3id.org/nf-research-tools/DevelopmentRecord)





```mermaid
 classDiagram
    class DevelopmentRecord
    click DevelopmentRecord href "../DevelopmentRecord/"
      DevelopmentRecord : funderId
        
      DevelopmentRecord : investigatorId
        
      DevelopmentRecord : publicationId
        
      DevelopmentRecord : resourceId
        
      
```




<!-- no inheritance hierarchy -->

## Slots

| Name | Cardinality and Range | Description | Inheritance |
| ---  | --- | --- | --- |
| [resourceId](resourceId.md) | 1 <br/> [String](String.md) | Foreign key to a tool-type table (resourceId) | direct |
| [investigatorId](investigatorId.md) | 0..1 <br/> [String](String.md) | Foreign key to Investigator (investigatorId) | direct |
| [publicationId](publicationId.md) | 0..1 <br/> [String](String.md) | Foreign key to Publication (publicationId) | direct |
| [funderId](funderId.md) | 0..1 <br/> [String](String.md) | Foreign key to Funder (funderId) | direct |















## Identifier and Mapping Information



### Annotations

| property | value |
| --- | --- |
| synapse_table_id | syn26486807 |




### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:DevelopmentRecord |
| native | nftools:DevelopmentRecord |






## LinkML Source

<!-- TODO: investigate https://stackoverflow.com/questions/37606292/how-to-create-tabbed-code-blocks-in-mkdocs-or-sphinx -->

### Direct

<details>
```yaml
name: DevelopmentRecord
annotations:
  synapse_table_id:
    tag: synapse_table_id
    value: syn26486807
description: Junction table linking a resource to its investigators, publications,
  and funders. Stored as a separate Synapse table; searchable via MaterializedView
  JOINs.
from_schema: https://w3id.org/nf-research-tools
attributes:
  resourceId:
    name: resourceId
    description: Foreign key to a tool-type table (resourceId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    domain_of:
    - Tool
    - DevelopmentRecord
    - Usage
    required: true
  investigatorId:
    name: investigatorId
    description: Foreign key to Investigator (investigatorId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    domain_of:
    - DevelopmentRecord
    - Investigator
  publicationId:
    name: publicationId
    description: Foreign key to Publication (publicationId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    domain_of:
    - DevelopmentRecord
    - Usage
    - Publication
  funderId:
    name: funderId
    description: Foreign key to Funder (funderId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    domain_of:
    - DevelopmentRecord
    - Funder

```
</details>

### Induced

<details>
```yaml
name: DevelopmentRecord
annotations:
  synapse_table_id:
    tag: synapse_table_id
    value: syn26486807
description: Junction table linking a resource to its investigators, publications,
  and funders. Stored as a separate Synapse table; searchable via MaterializedView
  JOINs.
from_schema: https://w3id.org/nf-research-tools
attributes:
  resourceId:
    name: resourceId
    description: Foreign key to a tool-type table (resourceId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    owner: DevelopmentRecord
    domain_of:
    - Tool
    - DevelopmentRecord
    - Usage
    range: string
    required: true
  investigatorId:
    name: investigatorId
    description: Foreign key to Investigator (investigatorId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    owner: DevelopmentRecord
    domain_of:
    - DevelopmentRecord
    - Investigator
    range: string
  publicationId:
    name: publicationId
    description: Foreign key to Publication (publicationId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    owner: DevelopmentRecord
    domain_of:
    - DevelopmentRecord
    - Usage
    - Publication
    range: string
  funderId:
    name: funderId
    description: Foreign key to Funder (funderId).
    from_schema: https://w3id.org/nf-research-tools/tool_base
    owner: DevelopmentRecord
    domain_of:
    - DevelopmentRecord
    - Funder
    range: string

```
</details></div>