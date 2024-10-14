import os
from schematic_db.schema.schema import Schema, SchemaConfig, DatabaseConfig
from schematic_db.manifest_store.api_manifest_store import APIManifestStore
from schematic_db.manifest_store.manifest_store import ManifestStoreConfig

schema_link = "https://raw.githubusercontent.com/nf-osi/nf-research-tools-schema/update_schema/nf-research-tools.jsonld"
#os.environ["API_URL"] = "http://127.0.0.1:3001/v1"
storage_project_id = 'syn51710208'
asset_view_id = 'syn51717771'

schema_config= SchemaConfig(
        schema_url=schema_link
    )

db_config = [
    {
        "name": "Resource",
        "primary_key": "resourceId",
        "foreign_keys": [
            {
                "column_name": "geneticReagentId",
                "foreign_table_name": "GeneticReagentDetails",
                "foreign_column_name": "geneticReagentId"
            },
            {
                "column_name": "antibodyId",
                "foreign_table_name": "AntibodyDetails",
                "foreign_column_name": "antibodyId"
            },
            {
                "column_name": "cellLineId",
                "foreign_table_name": "CellLineDetails",
                "foreign_column_name": "cellLineId"
            },
            {
                "column_name": "animalModelId",
                "foreign_table_name": "AnimalModelDetails",
                "foreign_column_name": "animalModelId"
            }
        ]
    },
    {
        "name": "GeneticReagentDetails",
        "primary_key": "geneticReagentId"
    },
    {
        "name": "VendorItem",
        "primary_key": "vendorItemId",
        "foreign_keys": [
            {
                "column_name": "vendorId",
                "foreign_table_name": "Vendor",
                "foreign_column_name": "vendorId"
            },
            {
                "column_name": "resourceId",
                "foreign_table_name": "Resource",
                "foreign_column_name": "resourceId"
            }
        ]
    },
    {
        "name": "Vendor",
        "primary_key": "vendorId",
    },
    {
        "name": "BiobankDetails",
        "primary_key": "biobankId",
        "foreign_keys": [
            {
                "column_name": "resourceId",
                "foreign_table_name": "Resource",
                "foreign_column_name": "resourceId"
            }
        ]
    },
    {
        "name": "Observation",
        "primary_key": "observationId",
        "foreign_keys": [
            {
                "column_name": "resourceId",
                "foreign_table_name": "Resource",
                "foreign_column_name": "resourceId"
            },
            {
                "column_name": "publicationId",
                "foreign_table_name": "Publication",
                "foreign_column_name": "publicationId"
            }
        ]
    },
    {
        "name": "ResourceApplication",
        "primary_key": "resourceApplicationId",
        "foreign_keys": [
            {
                "column_name": "resourceId",
                "foreign_table_name": "Resource",
                "foreign_column_name": "resourceId"
            }
        ]
    },
    {
        "name": "AntibodyDetails",
        "primary_key": "antibodyId",
    },
    {
        "name": "Donor",
        "primary_key": "donorId"
    },
    {
        "name": "CellLineDetails",
        "primary_key": "cellLineId",
        "foreign_keys": [
            {
                "column_name": "donorId",
                "foreign_table_name": "Donor",
                "foreign_column_name": "donorId",
            }
        ]
    },
    {
        "name": "MutationDetails",
        "primary_key": "mutationDetailsId",
    },
    {
        "name": "Mutation",
        "primary_key": "mutationId",
        "foreign_keys": [
            {
                "column_name": "mutationDetailsId",
                "foreign_table_name": "MutationDetails",
                "foreign_column_name": "mutationDetailsId"
            },
            {
                "column_name": "animalModelId",
                "foreign_table_name": "AnimalModelDetails",
                "foreign_column_name": "animalModelId"
            },
            {
                "column_name": "cellLineId",
                "foreign_table_name": "CellLineDetails",
                "foreign_column_name": "cellLineId"
            }
        ]
    },
    {
        "name": "AnimalModelDetails",
        "primary_key": "animalModelId",
        "foreign_keys": [
            {
                "column_name": "donorId",
                "foreign_table_name": "Donor",
                "foreign_column_name": "donorId"
            },
            {
                "column_name": "transplantationDonorId",
                "foreign_table_name": "Donor",
                "foreign_column_name": "donorId"
            }
        ]
    },
    {
        "name": "Development",
        "primary_key": "developmentId",
        "foreign_keys": [
            {
                "column_name": "resourceId",
                "foreign_table_name": "Resource",
                "foreign_column_name": "resourceId"
            },
            {
                "column_name": "investigatorId",
                "foreign_table_name": "Investigator",
                "foreign_column_name": "investigatorId"
            },
            {
                "column_name": "publicationId",
                "foreign_table_name": "Publication",
                "foreign_column_name": "publicationId"
            },
            {
                "column_name": "funderId",
                "foreign_table_name": "Funder",
                "foreign_column_name": "funderId"
            }
        ]
    },
    {
        "name": "Funder",
        "primary_key": "funderId",
    },
    {
        "name": "Investigator",
        "primary_key": "investigatorId",
    },
    {
        "name": "Publication",
        "primary_key": "publicationId",
    },
    {
        "name": "Usage",
        "primary_key": "usageId",
        "foreign_keys": [
            {
                "column_name": "publicationId",
                "foreign_table_name": "Publication",
                "foreign_column_name": "publicationId"
            },
            {
                "column_name": "resourceId",
                "foreign_table_name": "Resource",
                "foreign_column_name": "resourceId"
            }
        ]
    }
]

schema = Schema(
    schema_config,
    DatabaseConfig(db_config)
)


config = ManifestStoreConfig(
        schema_url = schema_link,
        synapse_project_id = storage_project_id,
        synapse_asset_view_id = asset_view_id,
        synapse_auth_token = os.environ["NF_SERVICE_TOKEN"]
    )
manifest_store = APIManifestStore(config)


from schematic_db.rdb.synapse_database import SynapseDatabase

database = SynapseDatabase(
        project_id=storage_project_id,
        auth_token= os.environ["NF_SERVICE_TOKEN"]
    )


from schematic_db.rdb_builder.rdb_builder import RDBBuilder

rdb_builder = RDBBuilder(rdb=database, schema=schema)
rdb_builder.build_database()
