# Tool JSON Schema Pipeline

Automates: **LinkML modules updated → PR merged → per-tool JSON Schemas
generated, registered in Synapse, and (once bootstrapped) re-bound to Record
Sets** in the tools project [syn26338068](https://www.synapse.org/Synapse:syn26338068)
(*Neurofibromatosis Research Tools Central*).

Modeled on the
[nf-metadata-dictionary](https://github.com/nf-osi/nf-metadata-dictionary)
release + curation-task workflows.

## Pieces

| File | Role |
| --- | --- |
| `scripts/tool_schema_config.yaml` | Single source of truth: org, project, per-tool class → schema name, title, upsert keys |
| `scripts/generate_tool_schemas.py` | LinkML class → flat draft-07 JSON Schema (`registered-json-schemas/<Class>.json`) |
| `scripts/register_tool_schemas.py` | Register a new version of each schema with Synapse; optionally rebind to Record Sets |
| `scripts/create_tool_record_sets.py` | Create the shared folder + a Record Set per tool type (idempotent create-if-missing) |
| `scripts/record_sets.json` | Generated map `Class → {record_set_id, folder_id, schema}` (commit it) |
| `.github/workflows/register-tool-schemas.yml` | **Automatic** on merge to `main` touching `modules/**` |
| `.github/workflows/create-tool-record-sets.yml` | **Manual** control (`workflow_dispatch`) — `--replace` / target specific types |
| `registered-json-schemas/*.json` | Generated, committed schemas (reviewable in PRs) |

## Flow

```
PR edits modules/*.yaml  ──merge to main──►  register-tool-schemas.yml
                                               1. generate_tool_schemas.py
                                               2. register_tool_schemas.py --version <M.m.run#> --rebind
                                               3. create_tool_record_sets.py --version <M.m.run#>
                                                    (creates only tool types missing from record_sets.json)
                                               4. commit registered-json-schemas/ + scripts/record_sets.json

(manual, optional)        ──workflow_dispatch─►  create-tool-record-sets.yml
                                               create_tool_record_sets.py --replace / --only <Class>
```

Record Set creation is **idempotent**: the per-merge pipeline creates a Record
Set only for tool types not already in `record_sets.json`, and rebinds the new
schema version to the ones that already exist. So merging module changes keeps
every tool type's Record Set bound to the latest schema without ever creating
duplicates. The manual workflow remains for recreating (`--replace`) or
targeting specific types.

## Versioning

`MAJOR.MINOR` comes from the `version:` field of
`modules/nf_research_tools.yaml`; `PATCH` is the GitHub Actions `run_number`.
So merging a module change produces e.g. `2.0.57`. Bump `MAJOR.MINOR` in the
LinkML schema when you want a deliberate version step. Synapse requires
versions ≥ `0.0.1`.

## Schema shape

Each schema is **flat draft-07 with enums inlined** (no `$defs`/`$ref`),
matching the format Synapse's registry and Record Sets accept. `gen-json-schema`
emits draft-2019-09 with enum `$ref`s and the full model as `$defs`; the
generator rewrites the dialect, inlines enums as `{"type": "string", "enum":
[...]}`, collapses `["string","null"]` unions, and sets
`additionalProperties: {}` (Synapse rejects `false`).

## Prerequisites (Synapse)

- **`SYNAPSE_AUTH_TOKEN`** secret with a token for the account CI uses (the
  nf-osi service account; the secret is already configured for the existing
  Synapse workflows). That account must have **CREATE permission on the
  organization** `org.synapse.nf` (id `223`). A validated dry-run showed the
  schemas are structurally accepted, but registration returns
  `403 CREATE permission for ORGANIZATION : 223` until this is granted.
- **Granting access (org admin only).** `org.synapse.nf` (id 223) was created by
  principal `3421893`; an admin of that org must add the service account's
  principal id with `CREATE` (and `UPDATE`) access. To find the service
  account's id: `Synapse().restGET("/userProfile")["ownerId"]` while logged in
  as it. Then an **admin** runs:

  ```python
  import synapseclient
  syn = synapseclient.login()                       # must be an org 223 admin
  acl = syn.restGET("/schema/organization/223/acl")
  acl["resourceAccess"].append({
      "principalId": <SERVICE_ACCOUNT_ID>,
      "accessType": ["READ", "CREATE", "UPDATE"],
  })
  syn.restPUT("/schema/organization/223/acl", body=__import__("json").dumps(acl))
  ```

  Add principal `3459953` (christina.conrad.parry) too if you want to register
  from a local machine. Alternatively, create a dedicated org (e.g.
  `org.synapse.nftools`) the tools team owns and set it as `organization:` in
  the config — the scripts read the org from config, so any name works.
- The same account needs write access to project `syn26338068` for record sets.

## Local usage

```bash
pip install linkml "synapseclient>=4.13.0" pyyaml

# 1. Generate (writes registered-json-schemas/*.json)
python scripts/generate_tool_schemas.py
python scripts/generate_tool_schemas.py --check      # CI: fail if stale

# 2. Register (needs SYNAPSE_AUTH_TOKEN)
python scripts/register_tool_schemas.py --patch 1 --dry-run   # no Synapse calls
python scripts/register_tool_schemas.py --patch 1             # real
python scripts/register_tool_schemas.py --patch 1 --rebind    # + rebind record sets

# 3. Bootstrap record sets (one time)
python scripts/create_tool_record_sets.py --version 2.0.1
python scripts/create_tool_record_sets.py --version 2.0.1 --only CellLine
```

## Testing

Offline pipeline tests live in `tests/test_tool_schema_pipeline.py` and run on
every PR that touches the pipeline (workflow: `test-tool-schema-pipeline.yml`).
They use **no Synapse access and no secrets**, and verify that the committed
schemas will register and that Record Sets can be built from them:

- committed `registered-json-schemas/*.json` are not stale (`generate --check`);
- each schema is valid draft-07 and fully self-contained (no `$ref` / `$defs`);
- every tool's `upsert_keys` and `required` entries are real schema properties;
- `register_tool_schemas.py --dry-run` resolves versions and finds every file.

```bash
pip install -r tests/requirements.txt
pytest tests/test_tool_schema_pipeline.py -v
```

These are the deterministic guardrails. A full round-trip against Synapse (real
registration + record-set creation) is **not** part of PR CI — it needs network,
`SYNAPSE_AUTH_TOKEN`, CREATE permission on the org, and creates persistent
objects. That live smoke test is left as an opt-in follow-up (manual dispatch /
scheduled), not a PR gate.

## Adding a new tool type

1. Add the module under `modules/` and wire it into `modules/nf_research_tools.yaml`.
2. Add an entry to `scripts/tool_schema_config.yaml` (class, schema_name, title, upsert_keys).
3. Merge → the pipeline registers the schema **and** creates its Record Set
   automatically (create-if-missing). No manual step needed.

## Upsert keys

Set per tool in `tool_schema_config.yaml` under `upsert_keys`. They are passed
to `create_record_based_metadata_task(..., upsert_keys=...)` and define which
field(s) identify a record for upsert. All tools default to `[resourceId]`; use
a list for a composite key, e.g. `[resourceId, resourceName]`.
