---
name: df-testing
description: DeltaForce testing practices on Databricks — data quality, integration and end-to-end tests, ML metrics and GenAI evaluation thresholds, test data and evidence for the PO review. Use when writing or running tests or verifying acceptance criteria.
user-invocable: false
---

# DeltaForce testing

Every acceptance criterion needs at least one test with recorded evidence. Tests run against the dev target.

## Test types

| Type | Where | What | How |
| --- | --- | --- | --- |
| Data quality | `tests/data_quality/` + pipeline expectations | Keys unique and not null, ranges, referential integrity, freshness, row count reconciliation between layers | SQL assertions that return zero violating rows; expectations in pipelines for silver and gold |
| Transformation | `tests/data_quality/` or `tests/integration/` | Business rules on small, known inputs | Synthetic input rows in a test table, expected output compared with `EXCEPT` both ways |
| Integration / end-to-end | `tests/integration/` | Deployed jobs and pipelines run successfully and produce the expected objects | Run results from the DevOps Engineer plus checks on the produced tables |
| ML | `tests/evaluation/` | Metrics of the registered model (by alias) on the held-out test split versus the baseline and the thresholds in the acceptance criteria, per segment; no leakage | Recomputed from the model and the saved split, not from logged numbers; fail when below threshold (`df-mlops`) |
| GenAI | `tests/evaluation/` | Answer quality, groundedness, retrieval relevance, safety, latency and cost on the versioned evaluation dataset | MLflow GenAI evaluation with judges on the deployed endpoint or registered version; thresholds from the acceptance criteria (`df-aiops`) |

## Writing SQL assertions

```sql
-- tests/data_quality/silver_customers_unique.sql
-- Expect: 0 rows
SELECT customer_id, COUNT(*) AS n
FROM IDENTIFIER(:catalog || '.' || :schema_silver || '.' || :prefix_silver || 'customers')
GROUP BY customer_id
HAVING COUNT(*) > 1
```

- One assertion per file, a comment with the expectation, parameters instead of literal names.
- Prefer assertions that return violating rows: easy to read in evidence.

## Test data

- Use synthetic data (`databricks-synthetic-data-gen`) in the dev catalog for transformation tests; never copy production data.
- ML and GenAI evaluation uses realistic samples of the real data in the dev catalog (`df-mlops`, `df-aiops`); production data only when the conventions or the kickoff request allow it.
- Clean up test tables you create, or give them a `test_` prefix.

## Running

- Run SQL assertions with the Databricks MCP tools or the CLI against the dev warehouse.
- Group runnable tests in a bundle job (`resources/tests.job.yml`) so the DevOps Engineer can run them after each deployment.
- Test runners that run as Python tasks on serverless compute must not call `sys.exit()`, not even `sys.exit(0)`: Databricks reports any `SystemExit` as a failed task. Return normally when every check passes; raise an exception with the summary when some fail.

## Evidence

Record for every criterion: the test, the result, and the evidence — query and result, job or pipeline run id, or MLflow run id. The QA Engineer's report table is copied into the PO review report.
