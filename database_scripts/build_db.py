import os
from schematic_db.schema.schema import Schema, SchemaConfig
from schematic_db.manifest_store.manifest_store import ManifestStore, ManifestStoreConfig

schema_link = "https://raw.githubusercontent.com/nf-osi/nf-research-tools-schema/main/nf-research-tools.jsonld"
os.environ["API_URL"] = "http://127.0.0.1:3001/v1"

config = SchemaConfig(
        schema_url=schema_link
    )
schema = Schema(config)

config = ManifestStoreConfig(
        schema_url = schema_link,
        synapse_project_id = "syn38296792",
        synapse_asset_view_id = "syn38308526",
        synapse_input_token = os.environ["NF_SERVICE_TOKEN"]
        )

manifest_store = ManifestStore(config)

