# NF Research Tools Central Schema

Data model for the NF Research Tools Central registry, covering 9 types of NF research resources (animal models, cell lines, antibodies, genetic reagents, biobanks, computational tools, organoid protocols, patient-derived models, and clinical assessment tools) along with supporting entities (publications, investigators, funders, vendors, observations).

URI: https://w3id.org/nf-research-tools

Name: nf_research_tools



## Schema Diagram

```mermaid
None
```


## Classes

| Class | Description |
| --- | --- |
| [DevelopmentRecord](DevelopmentRecord.md) | Junction table linking a resource to its investigators, publications, and fun... |
| [Donor](Donor.md) | A person, animal, or other organism that is the contributor of the resource |
| [Funder](Funder.md) | A person or organization that provides money for a particular resource |
| [HasGeneticDisorder](HasGeneticDisorder.md) | Mixin for tool types associated with a genetic disorder and its manifestation... |
| [HasPassageNumber](HasPassageNumber.md) | Mixin for tool types that track passage number |
| [HasTumorType](HasTumorType.md) | Mixin for tool types that model or bank specific tumor types |
| [Investigator](Investigator.md) | A person who carries out a formal inquiry or investigation into the developme... |
| [Mutation](Mutation.md) | Junction table linking tool-type resources (AnimalModel, CellLine) to their M... |
| [MutationDetails](MutationDetails.md) | Details of a genetic mutation, including type, method, affected gene, and seq... |
| [Observation](Observation.md) | A remark, statement, or comment based on the resource |
| [Publication](Publication.md) | A publication associated with the development or usage of a resource |
| [ResourceApplication](ResourceApplication.md) | Applications the resource can be used for, such as western blot, immunofluore... |
| [Tool](Tool.md) | A research tool or resource used in the NF research process |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[AnimalModel](AnimalModel.md) | An animal sufficiently like humans in its anatomy, physiology, or response to... |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Antibody](Antibody.md) | A blood protein produced in response to and counteracting a specific antigen |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Biobank](Biobank.md) | A large collection of biological or medical data and tissue samples, amassed ... |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[CellLine](CellLine.md) | A cell culture selected for uniformity from a cell population derived from a ... |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[ClinicalAssessmentTool](ClinicalAssessmentTool.md) | Clinical assessment tools including questionnaires, quality of life instrumen... |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[ComputationalTool](ComputationalTool.md) | Computational tools including software and analysis pipelines used in NF rese... |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[GeneticReagent](GeneticReagent.md) | Genetic reagents including plasmids, viral vectors, CRISPR constructs, and ot... |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[OrganoidProtocol](OrganoidProtocol.md) | Advanced 3D cellular models including organoids, assembloids, spheroids, and ... |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[PatientDerivedModel](PatientDerivedModel.md) | Patient-derived models including patient-derived xenografts (PDX), humanized ... |
| [Usage](Usage.md) | Junction table linking a resource to publications that cite or use it |
| [Vendor](Vendor.md) | A person or company offering the resource for sale |
| [VendorItem](VendorItem.md) | A resource listing from a specific vendor, including catalog information and ... |



## Slots

| Slot | Description |
| --- | --- |
| [3primeCloningSite](3primeCloningSite.md) | If Restriction Enzyme was selected as the cloning method, the enzyme used on ... |
| [3primer](3primer.md) | Primer to sequence the 3' end (C-terminal) of the insert |
| [3primeSiteDestroyed](3primeSiteDestroyed.md) | Whether 3' site was destroyed during cloning |
| [5primeCloningSite](5primeCloningSite.md) | If Restriction Enzyme was selected as the cloning method, the enzyme used on ... |
| [5primer](5primer.md) | Primer to sequence the 5' end (N-terminal) of the insert |
| [5primeSiteDestroyed](5primeSiteDestroyed.md) | Whether 5' site was destroyed during cloning |
| [abstract](abstract.md) | A brief, comprehensive summary of the contents of the publication |
| [administrationTime](administrationTime.md) | Typical time required to complete the assessment |
| [affectedGeneName](affectedGeneName.md) | Gene name for the affected gene (e |
| [affectedGeneSymbol](affectedGeneSymbol.md) | The gene symbol for the mutated gene (e |
| [age](age.md) | The age of the individual from which the resource was derived |
| [aiSummary](aiSummary.md) | A large language model-generated summary of the resource |
| [alleleType](alleleType.md) | The type of genetic alteration, vocabulary aligned with MGI allele subtypes |
| [animalModelId](animalModelId.md) | Foreign key to AnimalModel (resourceId) |
| [animalModelMutation](animalModelMutation.md) | A description of the specific mutation(s) created in the genome |
| [animalState](animalState.md) | State the animal is in according to the vendor/developer (e |
| [applicationLinks](applicationLinks.md) | Shareable links related to the resource application |
| [applicationSource](applicationSource.md) | The source of resource application information |
| [applicationTypes](applicationTypes.md) | One or more uses for the resource (e |
| [assessmentName](assessmentName.md) | Name of the assessment tool or instrument |
| [assessmentType](assessmentType.md) | Type of clinical assessment |
| [authors](authors.md) | Writers of the publication |
| [availabilityStatus](availabilityStatus.md) | Availability status of the tool |
| [backboneSize](backboneSize.md) | Size in bp of the backbone without the insert |
| [backgroundStrain](backgroundStrain.md) | The genetic background strain name |
| [backgroundSubstrain](backgroundSubstrain.md) | The substrain variety of a strain (e |
| [bacterialResistance](bacterialResistance.md) | Antibiotic(s) for selection in bacteria |
| [biobankName](biobankName.md) | The name of the biobank |
| [biobankURL](biobankURL.md) | A URL for the biobank landing page |
| [catalogNumber](catalogNumber.md) | The catalog number associated with the resource pertaining to the vendor |
| [catalogNumberURL](catalogNumberURL.md) | The URL linking to the resource on the vendor's website |
| [cellLineCategory](cellLineCategory.md) | The category to which the cell line belongs |
| [cellLineId](cellLineId.md) | Foreign key to CellLine (resourceId) |
| [cellTypes](cellTypes.md) | Cell types present in the model |
| [characterizationMethods](characterizationMethods.md) | Methods used to characterize the model |
| [chromosome](chromosome.md) | Chromosome number of the affected gene (e |
| [citation](citation.md) | A merged citation string for the publication, used to render citation on deta... |
| [clinicalData](clinicalData.md) | Available clinical data from the patient |
| [clonality](clonality.md) | The type of clonality of the antibody |
| [cloneId](cloneId.md) | Identification of clone (e |
| [cloningMethod](cloningMethod.md) | How the vector was constructed |
| [conjugate](conjugate.md) | Whether the antibody is conjugated or nonconjugated |
| [contact](contact.md) | Guidance on where to find additional information about the biobank |
| [containerized](containerized.md) | Whether containerized versions (Docker, Singularity) are available |
| [copyNumber](copyNumber.md) | Whether the plasmid produces sufficient DNA from a normal miniprep or require... |
| [cryopreservationProtocol](cryopreservationProtocol.md) | Protocol for freezing/thawing, if available |
| [cTerminalTag](cTerminalTag.md) | Tags on the C terminal 3' end of the gene insert |
| [cultureMedia](cultureMedia.md) | The base culture medium and supplements used to maintain the cell line (e |
| [cultureSystem](cultureSystem.md) | Culture system used for maintenance |
| [dateAdded](dateAdded.md) | The date that the resource was originally added |
| [dateModified](dateModified.md) | The last update of the resource metadata |
| [dependencies](dependencies.md) | Key software dependencies or requirements |
| [derivationSource](derivationSource.md) | Source of cells used to generate the model |
| [description](description.md) | Free text description, summary, or purpose of the resource |
| [digitalVersion](digitalVersion.md) | Whether a digital/electronic version is available |
| [diseaseSpecific](diseaseSpecific.md) | Whether the assessment is specific to NF or general |
| [documentation](documentation.md) | URL to documentation or user manual |
| [doi](doi.md) | The digital object identifier in the form https://www |
| [donor](donor.md) | Foreign key to Donor (donorId) |
| [donorId](donorId.md) | A unique identifier for the donor |
| [easeOfUseRating](easeOfUseRating.md) | A 1-5 rating of ease of use: how easy is it to obtain the resource, comply wi... |
| [engraftmentSite](engraftmentSite.md) | Site of engraftment in host organism |
| [establishmentRate](establishmentRate.md) | Success rate of model establishment |
| [externalMutationId](externalMutationId.md) | An identifier from an organism database such as MGI or other curated variant ... |
| [funderId](funderId.md) | A unique identifier for the funder |
| [funderName](funderName.md) | The name of the person or agency that funded the development of the resource |
| [generation](generation.md) | The generation of the animal model (e |
| [geneticDisorder](geneticDisorder.md) | Genetic disorders associated with the resource |
| [gRNAshRNASequence](gRNAshRNASequence.md) | The sequence of the gRNA or shRNA for the gene insert, if present |
| [growthStrain](growthStrain.md) | The E |
| [growthTemp](growthTemp.md) | Temperature for growing the bacteria hosting the plasmid |
| [hazardous](hazardous.md) | Whether the unmodified plasmid DNA requires handling at Biosafety Level 2 or ... |
| [hostOrganism](hostOrganism.md) | The species of the organism that hosts the antibody |
| [hostStrain](hostStrain.md) | Host organism strain for xenografts |
| [howToAcquire](howToAcquire.md) | How to acquire a particular resource |
| [humanClinVarMutation](humanClinVarMutation.md) | The human equivalent of the mutation in ClinVar/HGVS notation |
| [insertEntrezId](insertEntrezId.md) | The Entrez Gene ID for the gene insert |
| [insertName](insertName.md) | Name of the main gene insert in the plasmid |
| [insertSize](insertSize.md) | Size, in bp, of the gene insert as it is in the plasmid |
| [insertSpecies](insertSpecies.md) | Species of the insert |
| [institution](institution.md) | The institution of the investigator |
| [investigatorId](investigatorId.md) | A unique identifier for the investigator |
| [investigatorName](investigatorName.md) | The name of the investigator |
| [investigatorSynapseId](investigatorSynapseId.md) | The Synapse identifier for the investigator |
| [journal](journal.md) | The name of the periodical publication in which the paper was published |
| [lastUpdate](lastUpdate.md) | Date of last software update or release |
| [licenseType](licenseType.md) | Software license type |
| [licensingRequirements](licensingRequirements.md) | Licensing or permission requirements |
| [maintainer](maintainer.md) | Name or organization maintaining the software |
| [manifestation](manifestation.md) | Manifestations or symptoms that this resource is used to model (e |
| [matrixType](matrixType.md) | Extracellular matrix or scaffold used |
| [maturationTime](maturationTime.md) | Time required for model maturation |
| [modelSystemType](modelSystemType.md) | Type of patient-derived model system |
| [modelType](modelType.md) | Type of 3D cellular model |
| [molecularCharacterization](molecularCharacterization.md) | Molecular characterization performed |
| [mutationDetailsId](mutationDetailsId.md) | A unique identifier for the mutation |
| [mutationId](mutationId.md) | A unique identifier for this junction record |
| [mutationMethod](mutationMethod.md) | The method used to alter the resource, vocabulary aligned with MGI allele ori... |
| [mutationType](mutationType.md) | The type of mutation, vocabulary aligned with MGI mutation types |
| [nTerminalTag](nTerminalTag.md) | Tags on the N terminal 5' end of the gene insert |
| [numberOfItems](numberOfItems.md) | Number of items or questions in the assessment |
| [observationId](observationId.md) | A unique identifier for the observation |
| [observationLink](observationLink.md) | A link/reference related to the observation |
| [observationPhase](observationPhase.md) | What t=0 for the observation time is (life stage or phase) |
| [observationPublication](observationPublication.md) | Publication associated with this observation |
| [observationResourceId](observationResourceId.md) | The resource this observation is about |
| [observationSubmitterName](observationSubmitterName.md) | The name of the person submitting the observation |
| [observationSynapseId](observationSynapseId.md) | The Synapse identifier for the person submitting the observation |
| [observationText](observationText.md) | Free text observation about the resource |
| [observationTime](observationTime.md) | When the observation was made |
| [observationTimeUnits](observationTimeUnits.md) | The unit of time pertaining to the observation |
| [observationType](observationType.md) | Type of observation |
| [observationTypeOntologyId](observationTypeOntologyId.md) | Mammalian Phenotype Ontology (MP) term identifier |
| [orcid](orcid.md) | The ORCID iD of the investigator |
| [organ](organ.md) | The organ the cell line is derived from |
| [organoidType](organoidType.md) | Specific type of organoid, if applicable |
| [originYear](originYear.md) | The year the cell line originated |
| [parentDonorId](parentDonorId.md) | The ID of the parent donor |
| [passageNumber](passageNumber.md) | Current passage number, if applicable |
| [patientDiagnosis](patientDiagnosis.md) | Original patient diagnosis or condition |
| [pmid](pmid.md) | The PubMed Identifier associated with the publication |
| [populationDoublingTime](populationDoublingTime.md) | Time for cell line to double |
| [programmingLanguage](programmingLanguage.md) | Primary programming language(s) used |
| [promoter](promoter.md) | Promoter driving the expression of the insert in the plasmid |
| [proteinVariation](proteinVariation.md) | The protein consequence of the mutation (e |
| [psychometricProperties](psychometricProperties.md) | Validated psychometric properties (reliability, validity) |
| [publicationDate](publicationDate.md) | The date of the paper's publication |
| [publicationDateUnix](publicationDateUnix.md) | The date of the paper's publication in UNIX time |
| [publicationId](publicationId.md) | A unique identifier for the publication |
| [publicationTitle](publicationTitle.md) | The title of the publication |
| [qualityControlMetrics](qualityControlMetrics.md) | Quality control metrics used |
| [race](race.md) | The ethnicity of the individual the resource was derived from |
| [reactiveSpecies](reactiveSpecies.md) | Species the antibody has been shown to crossreact with the target protein |
| [reliabilityRating](reliabilityRating.md) | A 1-5 rating of reliability: does the resource produce consistent results and... |
| [resistance](resistance.md) | List of compounds the cell line has been selected for |
| [resourceApplicationId](resourceApplicationId.md) | A unique identifier for the resource application record |
| [resourceId](resourceId.md) | A unique identifier for the resource |
| [resourceName](resourceName.md) | The canonical name of the resource |
| [resourceType](resourceType.md) | Type of resource |
| [rrid](rrid.md) | The RRID, a standard resource identifier for interoperability with other data... |
| [scoringMethod](scoringMethod.md) | Description of scoring methodology |
| [selectableMarker](selectableMarker.md) | Additional selection markers, such as mammalian selection markers or fluoresc... |
| [sequenceVariation](sequenceVariation.md) | Important sequence variations in HGVS notation (e |
| [sex](sex.md) | The sex of the individual from which the resource was derived |
| [softwareName](softwareName.md) | The name of the software or computational tool |
| [softwareType](softwareType.md) | Type of computational tool |
| [softwareVersion](softwareVersion.md) | Version number or identifier of the software |
| [sourceRepository](sourceRepository.md) | URL to source code repository (e |
| [species](species.md) | The species of the individual the resource was derived from |
| [specimenFormat](specimenFormat.md) | How specimens have been processed in preparation for distribution |
| [specimenPreparationMethod](specimenPreparationMethod.md) | The preservation methods used by the biobank |
| [specimenTissueType](specimenTissueType.md) | The types of tissues that are banked |
| [specimenType](specimenType.md) | The types of specimens that are banked |
| [strainNomenclature](strainNomenclature.md) | The standard nomenclature for the strain (e |
| [strProfile](strProfile.md) | Short tandem repeat profile information |
| [synonyms](synonyms.md) | Synonyms of the resource |
| [systemRequirements](systemRequirements.md) | System requirements (OS, memory, compute) |
| [targetAntigen](targetAntigen.md) | Antigen that is targeted by antibody (e |
| [targetPopulation](targetPopulation.md) | Intended population for the assessment |
| [tissue](tissue.md) | The tissue the cell line is derived from |
| [totalSize](totalSize.md) | Size of vector with insert |
| [transplantationDonor](transplantationDonor.md) | Foreign key to Donor (donorId) |
| [transplantationType](transplantationType.md) | Type of transplantation involved |
| [tumorType](tumorType.md) | Tumor types associated with the resource |
| [uniprotId](uniprotId.md) | The UniProt ID of the protein targeted by the antibody |
| [usageId](usageId.md) | A unique identifier for this usage record |
| [usageRequirements](usageRequirements.md) | Any known restrictions on use of the resource |
| [validatedLanguages](validatedLanguages.md) | Languages in which the tool has been validated |
| [validationMethods](validationMethods.md) | Methods used to validate model fidelity to patient |
| [vectorBackbone](vectorBackbone.md) | Name of the backbone the plasmid is built on (e |
| [vectorType](vectorType.md) | Primary function of the plasmid |
| [vendor](vendor.md) | The vendor offering this item |
| [vendorId](vendorId.md) | A unique identifier for the vendor |
| [vendorItemId](vendorItemId.md) | A unique identifier for the vendor item listing |
| [vendorName](vendorName.md) | The name of the vendor |
| [vendorUrl](vendorUrl.md) | The vendor website URL |


## Enumerations

| Enumeration | Description |
| --- | --- |
| [AlleleTypeEnum](AlleleTypeEnum.md) | Type of genetic alteration, aligned with MGI allele subtypes |
| [ApplicationSourceEnum](ApplicationSourceEnum.md) | Source of application information |
| [ApplicationTypeEnum](ApplicationTypeEnum.md) | Types of resource applications |
| [AssessmentTypeEnum](AssessmentTypeEnum.md) | Types of clinical assessments |
| [AvailabilityStatusEnum](AvailabilityStatusEnum.md) | Availability status of assessment tools |
| [BacterialResistanceEnum](BacterialResistanceEnum.md) | Antibiotics for bacterial selection |
| [CellLineCategoryEnum](CellLineCategoryEnum.md) | Categories of cell lines |
| [CharacterizationMethodEnum](CharacterizationMethodEnum.md) | Methods for model characterization |
| [ClonalityEnum](ClonalityEnum.md) | Antibody clonality types |
| [CloningMethodEnum](CloningMethodEnum.md) | Methods for constructing vectors |
| [ConjugateEnum](ConjugateEnum.md) | Antibody conjugation status |
| [CopyNumberEnum](CopyNumberEnum.md) | Plasmid copy number |
| [CultureSystemEnum](CultureSystemEnum.md) | Culture systems for model maintenance |
| [DerivationSourceEnum](DerivationSourceEnum.md) | Sources of cells for model generation |
| [DigitalVersionEnum](DigitalVersionEnum.md) | Digital version availability |
| [DiseaseSpecificEnum](DiseaseSpecificEnum.md) | Whether an assessment is NF-specific |
| [EngraftmentSiteEnum](EngraftmentSiteEnum.md) | Engraftment sites in host organisms |
| [GeneticDisorderEnum](GeneticDisorderEnum.md) | Genetic disorders relevant to NF research |
| [GrowthStrainEnum](GrowthStrainEnum.md) | E |
| [GrowthTempEnum](GrowthTempEnum.md) | Bacterial growth temperature |
| [HostOrganismEnum](HostOrganismEnum.md) | Antibody host organism species |
| [HostStrainEnum](HostStrainEnum.md) | Host organism strains for xenografts |
| [LicenseTypeEnum](LicenseTypeEnum.md) | Software license types |
| [MatrixTypeEnum](MatrixTypeEnum.md) | Extracellular matrix or scaffold types |
| [ModelSystemTypeEnum](ModelSystemTypeEnum.md) | Types of patient-derived model systems |
| [MolecularCharacterizationEnum](MolecularCharacterizationEnum.md) | Molecular characterization methods |
| [MutationMethodEnum](MutationMethodEnum.md) | Method used to alter the resource, aligned with MGI allele origin types |
| [MutationTypeEnum](MutationTypeEnum.md) | Type of mutation, aligned with MGI mutation types |
| [ObservationPhaseEnum](ObservationPhaseEnum.md) | Life stage or phase at the time of observation |
| [ObservationTypeEnum](ObservationTypeEnum.md) | Types of observations, organized by resource type context |
| [OrganEnum](OrganEnum.md) | Organs from which cell lines can be derived |
| [OrganoidModelTypeEnum](OrganoidModelTypeEnum.md) | Types of 3D cellular models |
| [OrganoidTypeEnum](OrganoidTypeEnum.md) | Specific types of organoids |
| [ProgrammingLanguageEnum](ProgrammingLanguageEnum.md) | Programming languages |
| [RatingEnum](RatingEnum.md) | A 1-5 rating scale |
| [ReactiveSpeciesEnum](ReactiveSpeciesEnum.md) | Species the antibody crossreacts with |
| [ResourceTypeEnum](ResourceTypeEnum.md) | Type of NF research resource |
| [SelectableMarkerEnum](SelectableMarkerEnum.md) | Selectable markers on plasmids |
| [SexEnum](SexEnum.md) | Biological sex |
| [SoftwareTypeEnum](SoftwareTypeEnum.md) | Types of computational tools |
| [SpeciesEnum](SpeciesEnum.md) | Species of organisms |
| [SpecimenFormatEnum](SpecimenFormatEnum.md) | Specimen processing formats |
| [SpecimenPreparationMethodEnum](SpecimenPreparationMethodEnum.md) | Specimen preservation methods |
| [SpecimenTissueTypeEnum](SpecimenTissueTypeEnum.md) | Types of banked tissues |
| [SpecimenTypeEnum](SpecimenTypeEnum.md) | Types of banked specimens |
| [TargetPopulationEnum](TargetPopulationEnum.md) | Target populations for assessments |
| [TimeUnitEnum](TimeUnitEnum.md) | Units of time |
| [TissueEnum](TissueEnum.md) | Tissues from which cell lines can be derived |
| [TransplantationTypeEnum](TransplantationTypeEnum.md) | Type of transplantation |
| [TumorTypeEnum](TumorTypeEnum.md) | Tumor types relevant to NF research |
| [UsageRequirementEnum](UsageRequirementEnum.md) | Known restrictions on use of the resource |
| [VectorTypeEnum](VectorTypeEnum.md) | Primary functions of plasmids |
| [YesNoUnknownEnum](YesNoUnknownEnum.md) | Yes, No, or Unknown |


## Types

| Type | Description |
| --- | --- |
| [Boolean](Boolean.md) | A binary (true or false) value |
| [Curie](Curie.md) | a compact URI |
| [Date](Date.md) | a date (year, month and day) in an idealized calendar |
| [DateOrDatetime](DateOrDatetime.md) | Either a date or a datetime |
| [Datetime](Datetime.md) | The combination of a date and time |
| [Decimal](Decimal.md) | A real number with arbitrary precision that conforms to the xsd:decimal speci... |
| [Double](Double.md) | A real number that conforms to the xsd:double specification |
| [Float](Float.md) | A real number that conforms to the xsd:float specification |
| [Integer](Integer.md) | An integer |
| [Jsonpath](Jsonpath.md) | A string encoding a JSON Path |
| [Jsonpointer](Jsonpointer.md) | A string encoding a JSON Pointer |
| [Ncname](Ncname.md) | Prefix part of CURIE |
| [Nodeidentifier](Nodeidentifier.md) | A URI, CURIE or BNODE that represents a node in a model |
| [Objectidentifier](Objectidentifier.md) | A URI or CURIE that represents an object in the model |
| [Sparqlpath](Sparqlpath.md) | A string encoding a SPARQL Property Path |
| [String](String.md) | A character string |
| [Time](Time.md) | A time object represents a (local) time of day, independent of any particular... |
| [Uri](Uri.md) | a complete URI |
| [Uriorcurie](Uriorcurie.md) | a URI or a CURIE |


## Subsets

| Subset | Description |
| --- | --- |
