---
name: df-engineering-standards
description: DeltaForce engineering standards for Databricks — medallion layers for data engineering, analytics, ML and GenAI, bundle variables instead of literal names, project layout, naming, data quality and how client conventions override the defaults. Use before designing or writing any code, SQL or bundle resource.
user-invocable: false
---

# DeltaForce engineering standards

## Precedence

1. `.deltaforce/conventions.yaml` — client conventions (deploy path, naming, tags, code style, custom rules)
2. `.deltaforce/architecture/architecture.md` and ADRs — the approved design
3. These standards

When they conflict, follow the higher one and mention it in your report.

## Environment

- The dev target, catalog and schemas are in the *DeltaForce project context* block of `CLAUDE.md` and in `.deltaforce/config.yaml`. The bundle target is usually `dev` but the project may name it differently: wherever these instructions say `-t <dev target>`, use the *Bundle target* from `CLAUDE.md`.
- **The dev catalog is the boundary.** Inside it the team may create the schemas, tables, volumes and models the solution needs, as long as they are consistent with the design and the medallion layers. Never write outside it, except in the catalogs of an environment the team deploys to.
- **Other environments** are declared under `environments` in `.deltaforce/conventions.yaml`; those the team deploys to are listed in `CLAUDE.md`. Work there only when the design and your delegation say so, follow that environment's `data_rules`, never write where the team has `read` or `none`, and never deploy to production.
- Databricks CLI: `"$DF_ROOT/.deltaforce/bin/databricks"` (profile preselected), never another Databricks CLI installed on the machine — not even when a command is blocked: report the block instead. Databricks MCP tools use the same profile.
- Serverless compute first. Classic clusters only when the design says so.

## Existing projects

When `.deltaforce/conventions.yaml` says `project.kind: existing`, the team extends a project that already works:

- Follow `.deltaforce/architecture/as-is.md` and the conventions derived from the code. Do not restructure, rename or move existing code, resources or tables unless the design says so.
- Use the project's own bundle variables recorded in `bundle.variables` for the dev catalog and the schemas. DeltaForce does not redefine variables the bundle already has.
- The `data_rules` are binding. Unless a rule allows it, never drop, replace or truncate existing tables, delete their data or remove their checkpoints — neither directly nor in code that will run. If a task needs it, stop and report `needs-decision`.
- List every destructive operation on existing data or objects — `DROP`, `TRUNCATE`, `CREATE OR REPLACE`, overwrite writes, `DELETE` or `UPDATE` without `WHERE`, checkpoint removal — in your report, with the rule that allows it.
- Keep the existing CI/CD pipelines working; change them only when the design says so.

## Everything on Databricks goes through the asset bundle

Every Databricks resource of the project — jobs, pipelines, schemas, volumes, dashboards, metric views, Genie spaces, apps, model serving endpoints, vector search endpoints and indexes, registered models, experiments, monitors — is declared in the bundle (`databricks.yml` and `resources/*.yml`) and deployed to dev by the DevOps Engineer with `bundle deploy`. Nothing is created, changed or deleted by hand.

- Databricks MCP tools are for **reading, querying and running**: explore data and metadata, run SQL and code on dev, query endpoints and indexes, trigger runs of deployed jobs and pipelines. Their create, update and delete actions are blocked by the guardrails.
- A resource type the bundle cannot declare yet is created by a job task in the bundle (a Python script using the Databricks SDK, idempotent), and the choice is recorded in an ADR.
- Exception: Agent Bricks Knowledge Assistants and Supervisor Agents are created and updated on dev by the AI Engineer with the MCP tools, as `df-aiops` describes; deleting one needs a person.
- Data is not a resource: tables are produced by the deployed pipelines and jobs; SQL writes inside the dev catalog are allowed for development and tests.

## Production data (read-only)

Realistic data for development, ML and GenAI comes from the dev catalog; production data is used only when the conventions or the kickoff request say so. When `CLAUDE.md` lists a production workspace, the `databricks-prod` MCP tools read from it: `execute_sql` and `execute_sql_multi` (only `SELECT`, `WITH … SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`), `get_table_stats_and_schema`, `get_volume_folder_details`, `manage_serving_endpoint` (get, list, query), `query_vs_index`, `ask_genie`. Everything else on production is blocked, including the Databricks CLI.

- Pass the production warehouse from `CLAUDE.md` to every production query.
- Read the minimum: schemas, aggregates, samples. Copy production data into dev only when the Functional Analysis requires it and the PO approved it; never copy sensitive data.
- Model and AI function calls on production consume the client's credits: keep them few and small.
- Every production call is audited with your role.

## Guardrails

Hooks block, whatever the instructions say: resource changes outside the bundle (Agent Bricks: creates and updates by anyone but the AI Engineer, and deletes); publishing to the Hugging Face Hub (`hf upload`, an enabled `push_to_hub`) and Hugging Face Jobs; writes outside the dev catalog and SQL writes that do not name it; Unity Catalog permission, sharing, connection and storage changes; anything but reads on production; `bundle deploy`/`run` by anyone but the DevOps Engineer or outside dev, and `bundle destroy`; pushes to protected branches, force pushes, remote branch deletions, pushing `df/integration`, `reset --hard`, `rebase`; changes to or commits of what DeltaForce installed (agents, skills, Claude settings, `.mcp.json`, `CLAUDE.md`, `.gitignore`, `resources/deltaforce.variables.yml`, `.deltaforce/config.yaml`, framework, tools, runtime); conventions changes by anyone but the PM; the credentials file and its backups. A blocked action returns `DeltaForce guardrail: <reason>`: do not work around it, report it to your caller.

## Few tool calls

Every tool call re-reads your whole context. Read the sections you need rather than whole documents, chain related shell commands in one call, and never poll a run or a deployment in a loop. Load `df-testing` with the Skill tool when you write or run tests, `df-mlops` for ML work and `df-aiops` for GenAI work.

## Names come from bundle variables

Never write catalog, schema or table names literally in code or resources. The installer defines these variables (`resources/deltaforce.variables.yml`, generated — do not edit), except those the project's bundle already defines; in an existing project the variables in `bundle.variables` of the conventions take their place:

| Variable | Meaning |
| --- | --- |
| `catalog` | dev catalog |
| `schema_bronze`, `schema_silver`, `schema_gold` | schema of each layer (the same schema when the layout is single-schema) |
| `prefix_bronze`, `prefix_silver`, `prefix_gold` | table name prefix of each layer (`bronze_`… in single-schema layout, empty otherwise) |
| `warehouse_id` | SQL warehouse |

Add project variables (for example a table name agreed at G1) in `resources/variables.yml`, with no defaults for environment-specific values.

Pass them to code as parameters:

```yaml
# resources/customers.pipeline.yml
resources:
  pipelines:
    customers:
      name: "[${bundle.name}] customers"
      catalog: ${var.catalog}
      schema: ${var.schema_silver}
      serverless: true
      configuration:
        schema_bronze: ${var.schema_bronze}
        prefix_bronze: ${var.prefix_bronze}
        prefix_silver: ${var.prefix_silver}
      libraries:
        - file:
            path: ../src/pipelines/silver/customers.py
```

```python
# src/pipelines/silver/customers.py
from pyspark import pipelines as dp

catalog = spark.conf.get("catalog", None) or spark.catalog.currentCatalog()
bronze = f"{catalog}.{spark.conf.get('schema_bronze')}.{spark.conf.get('prefix_bronze')}customers"

@dp.table(name=f"{spark.conf.get('prefix_silver')}customers")
@dp.expect_or_drop("valid_id", "customer_id IS NOT NULL")
def customers():
    return spark.read.table(bronze).dropDuplicates(["customer_id"])
```

```sql
-- SQL with named parameters
SELECT * FROM IDENTIFIER(:catalog || '.' || :schema_gold || '.' || :prefix_gold || 'sales_daily')
```

Jobs pass variables as job or task parameters; notebooks read them with widgets.

## Medallion layers

| Layer | Data engineering and analytics | ML | GenAI |
| --- | --- | --- | --- |
| Bronze | Raw ingested data as received, raw files in volumes; append-only, with ingestion metadata | Raw training sources | Raw documents (PDF, HTML, …) in volumes |
| Silver | Cleaned, typed, deduplicated, conformed; data quality expectations | Cleaned training data | Parsed and chunked text with metadata |
| Gold | Business aggregates, marts, metric views, dashboard sources | Feature tables, predictions | Vector index source tables, evaluation datasets |

- Data flows only bronze → silver → gold. Gold never reads bronze.
- Models are registered in Unity Catalog in the gold schema; vector indexes are built on gold tables.
- Declare schemas and volumes the solution adds as bundle resources (`resources.schemas`, `resources.volumes`), never by hand.

## Project layout

```text
databricks.yml
resources/            # *.yml per domain or feature; deltaforce.variables.yml is generated
src/
  pipelines/bronze|silver|gold/
  ml/features|training|inference/
  ai/agents|rag|evaluation|agent_bricks/
  apps/
  dashboards/
tests/
  data_quality/
  integration/
  evaluation/
.devops/             # CI/CD pipelines, built on the client's templates
.deltaforce/          # team documents and state: requirements, architecture, backlog, reports — not product code
```

## Naming defaults

Used unless `.deltaforce/conventions.yaml` says otherwise.

- Tables, columns, schemas, volumes: `snake_case`; tables carry the layer prefix variable
- Jobs and pipelines: `[${bundle.name}] <purpose>`
- Files: `snake_case.py`, `snake_case.sql`; resource files `<domain>.<kind>.yml`
- Comments on every table and on non-obvious columns

## Quality

- Idempotent pipelines and jobs: re-running must not duplicate data.
- Expectations on silver and gold for keys, nulls, ranges and referential integrity.
- Python files over notebooks for production code unless the client conventions say `notebooks`.
- No secrets in code or resources: Databricks secret scopes or CI/CD variables.
- Keep changes inside the scope of your task; note anything else as an open point.
