# Names, code and layout

Read this before writing the first resource or code file of a task.

## Names come from bundle variables

Never write catalog, schema or table names literally in code or resources. The installer defines these variables
(`resources/deltaforce.variables.yml`, generated — do not edit), except those the project's bundle already has; in an
existing project the variables in `bundle.variables` of the conventions take their place.

| Variable | Meaning |
| --- | --- |
| `catalog` | dev catalog |
| `schema_bronze`, `schema_silver`, `schema_gold` | schema of each layer (the same schema when the layout is single-schema) |
| `prefix_bronze`, `prefix_silver`, `prefix_gold` | table name prefix of each layer (`bronze_`… in single-schema layout, empty otherwise) |
| `warehouse_id` | SQL warehouse |

Add project variables (for example a table name agreed at G1) in `resources/variables.yml`, with no defaults for
environment-specific values. Resources renamed by development mode — schemas, registered models, experiments — are
consumed through `${resources.schemas|registered_models|experiments.<key>.name}`, never rebuilt by hand from a variable.

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

## Python that runs as a job task

A file that will run as a `spark_python_task` runs inside a wrapper, not as a script: `__file__` does not exist, the
working directory is not the file's folder, and `sys.exit()` — even `sys.exit(0)` — is reported as a failed task.

```python
import argparse, os, sys

# Imports from a sibling module: resolve the folder from the module, never from __file__.
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.modules[__name__].__file__ or ".")))
```

The reliable shape is simpler: keep each task file self-contained, or ship shared code as a wheel declared in the
bundle. Parameters arrive with `argparse`; results are written to a table or returned by `dbutils.jobs.taskValues.set`,
never printed and parsed. See `references/known-failures.md`.

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
.devops/              # CI/CD pipelines, built on the client's templates
.deltaforce/          # team documents and state: requirements, architecture, backlog, reports — not product code
```

## Naming defaults

Used unless `.deltaforce/conventions.yaml` says otherwise.

- Tables, columns, schemas, volumes: `snake_case`; tables carry the layer prefix variable
- Jobs and pipelines: `[${bundle.name}] <purpose>`
- Files: `snake_case.py`, `snake_case.sql`; resource files `<domain>.<kind>.yml`
