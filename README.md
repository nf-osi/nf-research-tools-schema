<img alt="GitHub release (latest by date)" src="https://img.shields.io/github/v/release/nf-osi/nf-research-tools-schema?label=latest%20release&display_name=release&style=flat-square">  <img alt="GitHub Release Date" src="https://img.shields.io/github/release-date/nf-osi/nf-research-tools-schema?style=flat-square&color=orange">  <img alt="GitHub" src="https://img.shields.io/github/license/nf-osi/nf-research-tools-schema?style=flat-square&color=red">
# NF Research Tools Central Schema

This repository contains the released versions of the JSON-LD schema for the NF Research Tools Central. You can learn more about the schema/data model and other aspects of this project in our [project documentation](https://help.nf.synapse.org/NFdocs/Data-Model-&-Schema.2463596640.html).

Learn more about the goals for this project by checking out the following documents and presentations: 

> Ashley Clayton, Mialy DeFelice, Brynn Zalmanek, Jay Hodgson, Caroline Morin, Stockard Simon, Julie A Bletz, James A Eddy, Milen Nikolov, Jineta Banerjee, Kalyan Vinnakota, Marco Marasca, Kevin J Boske, Bruce Hoff, Ljubomir Bradic, YooRi Kim, James R Goss, Robert J Allaway, Centralizing neurofibromatosis experimental tool knowledge with the NF Research Tools Database, Database, Volume 2022, 2022, baac045, https://doi.org/10.1093/database/baac045
> 
>Clayton, A., DeFelice, M., Zalmanek, B., Hodgson, J., Morin, C., Simon, S., … Allaway, R. (2022, January 25). Centralizing neurofibromatosis experimental tool knowledge with the NF Research Tools Database. https://doi.org/10.31222/osf.io/t6zaf

>Zalmanek, Brynn; Allaway, Robert; Goss, James; Clayton, Ashley; Eddy, James; Throgmorton, Kaitlin; et al. (2021): NF Research Tools Database: An experimental resource database for the neurofibromatosis community. figshare. Poster. https://doi.org/10.6084/m9.figshare.14825271.v1 

>[Gilbert Family Foundation Press Release](https://www.gilbertfamilyfoundation.org/press-release/gff-and-sage-bionetworks-collaborate-on-an-nf1-research-tools-database/). 

# Contributing:

To contribute changes to the schema, please create a new branch, modify the schema CSV as desired, commit, and file a PR. The jsonld will automatically be updated. Please do not modify the jsonld manually. 

## Updating Schema-viz Files

To update the nf-research-tools-attributes.csv and nf-research-tools.json:

1) Run the following command in Schematic and save the json output file as nf-research-tools.json in the schema-viz/data directory.

```
schematic viz -c config.yml tangled_tree_layers -ft component 
```
2) Run the following command in Schematic and save the csv output file as nf-research-tools-attributes.csv in the schema-viz/data directory.
```
schematic viz -c config.yml attributes
```
