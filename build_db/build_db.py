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

# NOTE: the LinkML migration (see docs/MIGRATION.md) collapsed the separate
# `Resource` table and each tool-type table's own `<type>Id` primary key into a
# single unified `resourceId` column, present directly on every one of the 9
# tool-type tables. There is no longer a single central "Resource" table for
# other entities to point a foreign key at -- resourceId is now a distributed
# identifier owned collectively by whichever tool-type table a given resource
# actually lives in. The tables below that used to declare a
# `"foreign_table_name": "Resource"` FK (VendorItem, BiobankDetails,
# Observation, ResourceApplication, Development, Usage) keep `resourceId` as a
# plain column but no longer declare that FK, since there's no single parent
# table to reference and this tool's DatabaseConfig has no notion of a
# polymorphic/multi-table FK.
db_config = [
    {
        "name": "GeneticReagentDetails",
        "primary_key": "resourceId"
    },
    {
        "name": "ComputationalToolDetails",
        "primary_key": "resourceId"
    },
    {
        "name": "OrganoidProtocolDetails",
        "primary_key": "resourceId"
    },
    {
        "name": "PatientDerivedModelDetails",
        "primary_key": "resourceId"
    },
    {
        "name": "ClinicalAssessmentToolDetails",
        "primary_key": "resourceId"
    },
    {
        "name": "VendorItem",
        "primary_key": "vendorItemId",
        "foreign_keys": [
            {
                "column_name": "vendorId",
                "foreign_table_name": "Vendor",
                "foreign_column_name": "vendorId"
            }
        ]
    },
    {
        "name": "Vendor",
        "primary_key": "vendorId",
    },
    {
        "name": "BiobankDetails",
        "primary_key": "resourceId"
    },
    {
        "name": "Observation",
        "primary_key": "observationId",
        "foreign_keys": [
            {
                "column_name": "publicationId",
                "foreign_table_name": "Publication",
                "foreign_column_name": "publicationId"
            }
        ]
    },
    {
        "name": "ResourceApplication",
        "primary_key": "resourceApplicationId"
    },
    {
        "name": "AntibodyDetails",
        "primary_key": "resourceId",
    },
    {
        "name": "Donor",
        "primary_key": "donorId"
    },
    {
        "name": "CellLineDetails",
        "primary_key": "resourceId",
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
            }
        ]
    },
    {
        "name": "AnimalModelDetails",
        "primary_key": "resourceId",
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
