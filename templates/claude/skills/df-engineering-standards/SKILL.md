---
name: df-engineering-standards
description: DeltaForce engineering standards for Databricks — medallion layers for data engineering, analytics, ML and GenAI, bundle variables instead of literal names, project layout, naming, data quality and how client conventions override the defaults. Use before designing or writing any code, SQL or bundle resource.
user-invocable: false
---

# DeltaForce engineering standards

## Precedence

1. `.deltaforce/conventions.yaml` — client conventions (deploy path, naming, tags, code style, custom rules)
2. `docs/architecture/solution.md` and ADRs — the approved design
3. These standards

When they conflict, follow the higher one and mention it in your report.

## Environment

- The dev target, catalog and schemas are in the *DeltaForce project context* block of `CLAUDE.md` and in `.deltaforce/config.yaml`.
- **The dev catalog is the boundary.** Inside it the team may create the schemas, tables, volumes and models the solution needs, as long as they are consistent with the design and the medallion layers. Never write outside it.
- Databricks CLI: `"$DF_ROOT/.deltaforce/bin/databricks"` (profile preselected). Databricks MCP tools use the same profile.
- Serverless compute first. Classic clusters only when the design says so.

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
docs/requirements/  docs/architecture/
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
