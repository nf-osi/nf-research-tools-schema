---
search:
  boost: 10.0
---

# Class: AnimalModel 


_An animal sufficiently like humans in its anatomy, physiology, or response to a pathogen to be used in medical research in order to obtain results that can be extrapolated to human medicine._



<div data-search-exclude markdown="1">



URI: [nftools:AnimalModel](https://w3id.org/nf-research-tools/AnimalModel)





```mermaid
 classDiagram
    class AnimalModel
    click AnimalModel href "../AnimalModel/"
      HasGeneticDisorder <|-- AnimalModel
        click HasGeneticDisorder href "../HasGeneticDisorder/"
      Tool <|-- AnimalModel
        click Tool href "../Tool/"
      
      AnimalModel : aiSummary
        
      AnimalModel : animalState
        
      AnimalModel : backgroundStrain
        
      AnimalModel : backgroundSubstrain
        
      AnimalModel : dateAdded
        
      AnimalModel : dateModified
        
      AnimalModel : description
        
      AnimalModel : donor
        
      AnimalModel : generation
        
      AnimalModel : geneticDisorder
        
          
    
        
        
        AnimalModel --> "1..*" GeneticDisorderEnum : geneticDisorder
        click GeneticDisorderEnum href "../GeneticDisorderEnum/"
    

        
      AnimalModel : howToAcquire
        
      AnimalModel : manifestation
        
      AnimalModel : resourceId
        
      AnimalModel : resourceName
        
      AnimalModel : resourceType
        
          
    
        
        
        AnimalModel --> "1" ResourceTypeEnum : resourceType
        click ResourceTypeEnum href "../ResourceTypeEnum/"
    

        
      AnimalModel : rrid
        
      AnimalModel : strainNomenclature
        
      AnimalModel : synonyms
        
      AnimalModel : transplantationDonor
        
      AnimalModel : transplantationType
        
          
    
        
        
        AnimalModel --> "0..1" TransplantationTypeEnum : transplantationType
        click TransplantationTypeEnum href "../TransplantationTypeEnum/"
    

        
      AnimalModel : usageRequirements
        
          
    
        
        
        AnimalModel --> "*" UsageRequirementEnum : usageRequirements
        click UsageRequirementEnum href "../UsageRequirementEnum/"
    

        
      
```





## Inheritance
* [Tool](Tool.md)
    * **AnimalModel** [ [HasGeneticDisorder](HasGeneticDisorder.md)]


## Slots

| Name | Cardinality and Range | Description | Inheritance |
| ---  | --- | --- | --- |
| [donor](donor.md) | 0..1 <br/> [String](String.md) | Foreign key to Donor (donorId) | direct |
| [transplantationDonor](transplantationDonor.md) | 0..1 <br/> [String](String.md) | Foreign key to Donor (donorId) | direct |
| [transplantationType](transplantationType.md) | 0..1 <br/> [TransplantationTypeEnum](TransplantationTypeEnum.md) | Type of transplantation involved | direct |
| [animalState](animalState.md) | 0..1 <br/> [String](String.md) | State the animal is in according to the vendor/developer (e | direct |
| [backgroundStrain](backgroundStrain.md) | 0..1 <br/> [String](String.md) | The genetic background strain name | direct |
| [backgroundSubstrain](backgroundSubstrain.md) | 0..1 <br/> [String](String.md) | The substrain variety of a strain (e | direct |
| [strainNomenclature](strainNomenclature.md) | 0..1 <br/> [String](String.md) | The standard nomenclature for the strain (e | direct |
| [generation](generation.md) | 0..1 <br/> [String](String.md) | The generation of the animal model (e | direct |
| [geneticDisorder](geneticDisorder.md) | 1..* <br/> [GeneticDisorderEnum](GeneticDisorderEnum.md) | Genetic disorders associated with the resource | [HasGeneticDisorder](HasGeneticDisorder.md) |
| [manifestation](manifestation.md) | 1..* <br/> [String](String.md) | Manifestations or symptoms that this resource is used to model (e | [HasGeneticDisorder](HasGeneticDisorder.md) |
| [resourceId](resourceId.md) | 1 <br/> [String](String.md) | A unique identifier for the resource | [Tool](Tool.md) |
| [rrid](rrid.md) | 0..1 <br/> [String](String.md) | The RRID, a standard resource identifier for interoperability with other data... | [Tool](Tool.md) |
| [resourceName](resourceName.md) | 1 <br/> [String](String.md) | The canonical name of the resource | [Tool](Tool.md) |
| [synonyms](synonyms.md) | * <br/> [String](String.md) | Synonyms of the resource | [Tool](Tool.md) |
| [resourceType](resourceType.md) | 1 <br/> [ResourceTypeEnum](ResourceTypeEnum.md) | Type of resource | [Tool](Tool.md) |
| [description](description.md) | 0..1 <br/> [String](String.md) | Free text description, summary, or purpose of the resource | [Tool](Tool.md) |
| [aiSummary](aiSummary.md) | 0..1 <br/> [String](String.md) | A large language model-generated summary of the resource | [Tool](Tool.md) |
| [usageRequirements](usageRequirements.md) | * <br/> [UsageRequirementEnum](UsageRequirementEnum.md) | Any known restrictions on use of the resource | [Tool](Tool.md) |
| [howToAcquire](howToAcquire.md) | 1 <br/> [String](String.md) | How to acquire a particular resource | [Tool](Tool.md) |
| [dateAdded](dateAdded.md) | 1 <br/> [Date](Date.md) | The date that the resource was originally added | [Tool](Tool.md) |
| [dateModified](dateModified.md) | 1 <br/> [Date](Date.md) | The last update of the resource metadata | [Tool](Tool.md) |















## Identifier and Mapping Information



### Annotations

| property | value |
| --- | --- |
| synapse_table_id | syn26486808 |




### Schema Source


* from schema: https://w3id.org/nf-research-tools




## Mappings

| Mapping Type | Mapped Value |
| ---  | ---  |
| self | nftools:AnimalModel |
| native | nftools:AnimalModel |






## LinkML Source

<!-- TODO: investigate https://stackoverflow.com/questions/37606292/how-to-create-tabbed-code-blocks-in-mkdocs-or-sphinx -->

### Direct

<details>
```yaml
name: AnimalModel
annotations:
  synapse_table_id:
    tag: synapse_table_id
    value: syn26486808
description: An animal sufficiently like humans in its anatomy, physiology, or response
  to a pathogen to be used in medical research in order to obtain results that can
  be extrapolated to human medicine.
from_schema: https://w3id.org/nf-research-tools
is_a: Tool
mixins:
- HasGeneticDisorder
slots:
- donor
- transplantationDonor
- transplantationType
slot_usage:
  resourceType:
    name: resourceType
    ifabsent: string(Animal Model)
  geneticDisorder:
    name: geneticDisorder
    required: true
  manifestation:
    name: manifestation
    required: true
attributes:
  animalState:
    name: animalState
    description: State the animal is in according to the vendor/developer (e.g. embryo,
      sperm, live).
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    domain_of:
    - AnimalModel
  backgroundStrain:
    name: backgroundStrain
    description: The genetic background strain name. Correct strain nomenclature indicates
      what a mutant strain's background is.
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    domain_of:
    - AnimalModel
  backgroundSubstrain:
    name: backgroundSubstrain
    description: The substrain variety of a strain (e.g. C57BL/6J, C57BL/6Tac).
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    domain_of:
    - AnimalModel
  strainNomenclature:
    name: strainNomenclature
    description: The standard nomenclature for the strain (e.g. B6.129S2-NF1tm1Tyj/J).
      Set by the International Committee on Standardized Genetic Nomenclature for
      Mice.
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    domain_of:
    - AnimalModel
  generation:
    name: generation
    description: The generation of the animal model (e.g. 13).
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    domain_of:
    - AnimalModel

```
</details>

### Induced

<details>
```yaml
name: AnimalModel
annotations:
  synapse_table_id:
    tag: synapse_table_id
    value: syn26486808
description: An animal sufficiently like humans in its anatomy, physiology, or response
  to a pathogen to be used in medical research in order to obtain results that can
  be extrapolated to human medicine.
from_schema: https://w3id.org/nf-research-tools
is_a: Tool
mixins:
- HasGeneticDisorder
slot_usage:
  resourceType:
    name: resourceType
    ifabsent: string(Animal Model)
  geneticDisorder:
    name: geneticDisorder
    required: true
  manifestation:
    name: manifestation
    required: true
attributes:
  animalState:
    name: animalState
    description: State the animal is in according to the vendor/developer (e.g. embryo,
      sperm, live).
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    range: string
  backgroundStrain:
    name: backgroundStrain
    description: The genetic background strain name. Correct strain nomenclature indicates
      what a mutant strain's background is.
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    range: string
  backgroundSubstrain:
    name: backgroundSubstrain
    description: The substrain variety of a strain (e.g. C57BL/6J, C57BL/6Tac).
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    range: string
  strainNomenclature:
    name: strainNomenclature
    description: The standard nomenclature for the strain (e.g. B6.129S2-NF1tm1Tyj/J).
      Set by the International Committee on Standardized Genetic Nomenclature for
      Mice.
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    range: string
  generation:
    name: generation
    description: The generation of the animal model (e.g. 13).
    from_schema: https://w3id.org/nf-research-tools/animal_model
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    range: string
  donor:
    name: donor
    description: Foreign key to Donor (donorId). The biological donor from which the
      resource was derived.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    - CellLine
    range: string
  transplantationDonor:
    name: transplantationDonor
    description: Foreign key to Donor (donorId). The donor used in transplantation
      experiments.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    range: string
  transplantationType:
    name: transplantationType
    description: Type of transplantation involved.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - AnimalModel
    range: TransplantationTypeEnum
  geneticDisorder:
    name: geneticDisorder
    description: Genetic disorders associated with the resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - HasGeneticDisorder
    range: GeneticDisorderEnum
    required: true
    multivalued: true
  manifestation:
    name: manifestation
    description: Manifestations or symptoms that this resource is used to model (e.g.
      tumor type, behavioral phenotype).
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - HasGeneticDisorder
    range: string
    required: true
    multivalued: true
  resourceId:
    name: resourceId
    description: A unique identifier for the resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    slot_uri: schema:identifier
    identifier: true
    owner: AnimalModel
    domain_of:
    - Tool
    - DevelopmentRecord
    - Usage
    range: string
    required: true
  rrid:
    name: rrid
    description: The RRID, a standard resource identifier for interoperability with
      other databases. Must include the lowercase 'rrid:' prefix.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - Tool
    range: string
    pattern: ^rrid:[a-zA-Z]+.+$
  resourceName:
    name: resourceName
    description: The canonical name of the resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    slot_uri: schema:name
    owner: AnimalModel
    domain_of:
    - Tool
    range: string
    required: true
  synonyms:
    name: synonyms
    description: Synonyms of the resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - Tool
    range: string
    multivalued: true
  resourceType:
    name: resourceType
    description: Type of resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    ifabsent: string(Animal Model)
    owner: AnimalModel
    domain_of:
    - Tool
    range: ResourceTypeEnum
    required: true
  description:
    name: description
    description: Free text description, summary, or purpose of the resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    slot_uri: schema:description
    owner: AnimalModel
    domain_of:
    - Tool
    range: string
  aiSummary:
    name: aiSummary
    description: A large language model-generated summary of the resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - Tool
    range: string
  usageRequirements:
    name: usageRequirements
    description: Any known restrictions on use of the resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - Tool
    range: UsageRequirementEnum
    multivalued: true
  howToAcquire:
    name: howToAcquire
    description: How to acquire a particular resource.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - Tool
    range: string
    required: true
  dateAdded:
    name: dateAdded
    description: The date that the resource was originally added.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - Tool
    range: date
    required: true
  dateModified:
    name: dateModified
    description: The last update of the resource metadata.
    from_schema: https://w3id.org/nf-research-tools
    rank: 1000
    owner: AnimalModel
    domain_of:
    - Tool
    range: date
    required: true

```
</details></div>