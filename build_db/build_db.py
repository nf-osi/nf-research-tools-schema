import os
from schematic_db.schema.schema import Schema, SchemaConfig, DatabaseConfig
from schematic_db.manifest_store.manifest_store import ManifestStore, ManifestStoreConfig

schema_link = "https://raw.githubusercontent.com/nf-osi/nf-research-tools-schema/main/nf-research-tools.jsonld"
#os.environ["API_URL"] = "http://127.0.0.1:3001/v1"
storage_project_id = 'syn51710208'

schema_config= SchemaConfig(
        schema_url=schema_link
    )

db_config = [
    {
        "name": "Resource",
        "primary_key": "Resource_id",
        "foreign_keys": [
            {
                "column_name": "Genetic Reagent_id",
                "foreign_table_name": "Genetic Reagent",
                "foreign_column_name": "Genetic Reagent_id"
            },
            {
                "column_name": "Antibody_id",
                "foreign_table_name": "Antibody",
                "foreign_column_name": "Antibody_id"
            },
            {
                "column_name": "Cell Line_id",
                "foreign_table_name": "Cell Line",
                "foreign_column_name": "Cell Line_id"
            },
            {
                "column_name": "Animal Model_id",
                "foreign_table_name": "Animal Model",
                "foreign_column_name": "Animal Model_id"
            }
        ]
    },
    {
        "name": "Genetic Reagent",
        "primary_key": "Genetic Reagent_id"
    },
    {
        "name": "Vendor Item",
        "primary_key": "Vendor Item_id",
        "foreign_keys": [
            {
                "column_name": "Vendor_id",
                "foreign_table_name": "Vendor",
                "foreign_column_name": "Vendor_id"
            },
            {
                "column_name": "Resource_id",
                "foreign_table_name": "Resource",
                "foreign_column_name": "Resource_id"
            }
        ]
    },
    {
        "name": "Vendor",
        "primary_key": "Vendor_id",
    },
    {
        "name": "Biobank",
        "primary_key": "Biobank_id",
        "foreign_keys": [
            {
                "column_name": "Resource_id",
                "foreign_table_name": "Resource",
                "foreign_column_name": "Resource_id"
            }
        ]
    },
    {
        "name": "Observation",
        "primary_key": "Observation_id",
        "foreign_keys": [
            {
                "column_name": "Resource_id",
                "foreign_table_name": "Resource",
                "foreign_column_name": "Resource_id"
            },
            {
                "column_name": "Publication_id",
                "foreign_table_name": "Publication",
                "foreign_column_name": "Publication_id"
            }
        ]
    },
    {
        "name": "Resource Application",
        "primary_key": "Resource Application_id",
        "foreign_keys": [
            {
                "column_name": "Resource_id",
                "foreign_table_name": "Resource",
                "foreign_column_name": "Resource_id"
            }
        ]
    },
    {
        "name": "Antibody",
        "primary_key": "Antibody_id",
    },
    {
        "name": "Donor",
        "primary_key": "Donor_id"
    },
    {
        "name": "Cell Line",
        "primary_key": "Cell Line_id",
        "foreign_keys": [
            {
                "column_name": "Donor_id",
                "foreign_table_name": "Donor",
                "foreign_column_name": "Donor_id",
            }
        ]
    },
    {
        "name": "Mutation Details",
        "primary_key": "Mutation Details_id",
    },
    {
        "name": "Mutation",
        "primary_key": "Mutation_id",
        "foreign_keys": [
            {
                "column_name": "Mutation Details_id",
                "foreign_table_name": "Mutation Details",
                "foreign_column_name": "Mutation Details_id"
            },
            {
                "column_name": "Animal Model_id",
                "foreign_table_name": "Animal Model",
                "foreign_column_name": "Animal Model_id"
            },
            {
                "column_name": "Cell Line_id",
                "foreign_table_name": "Cell Line",
                "foreign_column_name": "Cell Line_id"
            }
        ]
    },
    {
        "name": "Animal Model",
        "primary_key": "Animal Model_id",
        "foreign_keys": [
            {
                "column_name": "Donor_id",
                "foreign_table_name": "Donor",
                "foreign_column_name": "Donor_id"
            },
            {
                "column_name": "Transplantation Donor_id",
                "foreign_table_name": "Donor",
                "foreign_column_name": "Donor_id"
            }
        ]
    },
    {
        "name": "Development",
        "primary_key": "Development_id",
        "foreign_keys": [
            {
                "column_name": "Resource_id",
                "foreign_table_name": "Resource",
                "foreign_column_name": "Resource_id"
            },
            {
                "column_name": "Investigator_id",
                "foreign_table_name": "Investigator",
                "foreign_column_name": "Investigator_id"
            },
            {
                "column_name": "Publication_id",
                "foreign_table_name": "Publication",
                "foreign_column_name": "Publication_id"
            },
            {
                "column_name": "Funder_id",
                "foreign_table_name": "Funder",
                "foreign_column_name": "Funder_id"
            }
        ]
    },
    {
        "name": "Funder",
        "primary_key": "Funder_id",
    },
    {
        "name": "Investigator",
        "primary_key": "Investigator_id",
    },
    {
        "name": "Publication",
        "primary_key": "Publication_id",
    },
    {
        "name": "Usage",
        "primary_key": "Usage_id",
        "foreign_keys": [
            {
                "column_name": "Publication_id",
                "foreign_table_name": "Publication",
                "foreign_column_name": "Publication_id"
            },
            {
                "column_name": "Resource_id",
                "foreign_table_name": "Resource",
                "foreign_column_name": "Resource_id"
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
        synapse_asset_view_id = "syn51717771",
        synapse_input_token = os.environ["NF_SERVICE_TOKEN"]
        )

manifest_store = ManifestStore(config)

from schematic_db.rdb.synapse_database import SynapseDatabase
from schematic_db.synapse.synapse import SynapseConfig

config = SynapseConfig(
        project_id=storage_project_id,
        username="nf-osi-service",
        auth_token= os.environ["NF_SERVICE_TOKEN"]
    )


database =  SynapseDatabase(config)

from schematic_db.rdb_builder.rdb_builder import RDBBuilder

rdb_builder = RDBBuilder(rdb=database, schema=schema)
rdb_builder.build_database()
