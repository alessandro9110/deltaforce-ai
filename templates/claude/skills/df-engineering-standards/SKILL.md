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

- The dev target, catalog and schemas are in the *DeltaForce project context* block of `CLAUDE.md` and in `.deltaforce/config.yaml`.
- **The dev catalog is the boundary.** Inside it the team may create the schemas, tables, volumes and models the solution needs, as long as they are consistent with the design and the medallion layers. Never write outside it.
- Databricks CLI: `"$DF_ROOT/.deltaforce/bin/databricks"` (profile preselected). Databricks MCP tools use the same profile.
- Serverless compute first. Classic clusters only when the design says so.

## Everything on Databricks goes through the asset bundle

Every Databricks resource of the project — jobs, pipelines, schemas, volumes, dashboards, metric views, Genie spaces, apps, model serving endpoints, vector search endpoints and indexes, registered models, experiments, monitors — is declared in the bundle (`databricks.yml` and `resources/*.yml`) and deployed to dev by the DevOps Engineer with `bundle deploy`. Nothing is created, changed or deleted by hand.

- Databricks MCP tools are for **reading, querying and running**: explore data and metadata, run SQL and code on dev, query endpoints and indexes, trigger runs of deployed jobs and pipelines. Their create, update and delete actions are blocked by the guardrails.
- A resource type the bundle cannot declare yet is created by a job task in the bundle (a Python script using the Databricks SDK, idempotent), and the choice is recorded in an ADR.
- Data is not a resource: tables are produced by the deployed pipelines and jobs; SQL writes inside the dev catalog are allowed for development and tests.

## Production data (read-only)

When `CLAUDE.md` lists a production workspace, the `databricks-prod` MCP tools read from it: `execute_sql` and `execute_sql_multi` (only `SELECT`, `WITH … SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`), `get_table_stats_and_schema`, `get_volume_folder_details`, `manage_serving_endpoint` (get, list, query), `query_vs_index`, `ask_genie`. Everything else on production is blocked, including the Databricks CLI.

- Pass the production warehouse from `CLAUDE.md` to every production query.
- Read the minimum: schemas, aggregates, samples. Copy production data into dev only when the Functional Analysis requires it and the PO approved it; never copy sensitive data.
- Model and AI function calls on production consume the client's credits: keep them few and small.
- Every production call is audited with your role.

## Guardrails

Hooks block these actions whatever the instructions say:

- creating, changing or deleting Databricks resources with MCP tools instead of the asset bundle;
- writes outside the dev catalog, and SQL writes that do not name the dev catalog explicitly;
- permission, sharing, connection and storage changes in Unity Catalog;
- any non-read activity on production, and any Databricks CLI call to it;
- `bundle deploy` or `bundle run` by anyone but the DevOps Engineer or to a target other than dev, and `bundle destroy`;
- pushes to protected branches, force pushes, remote branch deletions, pushing `df/integration`, `reset --hard`, `rebase`;
- edits of installer-managed files (`.claude/settings*.json`, `.mcp.json`, `.deltaforce/config.yaml`) and any access to `.deltaforce/.databrickscfg`.

A blocked action returns `DeltaForce guardrail: <reason>`. Do not work around it: report it to your caller.

## Names come from bundle variables

Never write catalog, schema or table names literally in code or resources. The installer defines these variables (`resources/deltaforce.variables.yml`, generated — do not edit):

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
  ai/agents|rag|evaluation/
  apps/
  dashboards/
tests/
  data_quality/
  integration/
  evaluation/
cicd/
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
