---
name: df-testing
description: DeltaForce testing practices on Databricks — how to run code before handing it over, data quality, integration and end-to-end tests, ML metrics and GenAI evaluation thresholds, test data and evidence for the PO review. Use when writing or running tests or verifying acceptance criteria.
user-invocable: false
---

# DeltaForce testing

Every acceptance criterion needs at least one test with recorded evidence. Tests run against the dev target.

## Run it before you hand it over

**A task is `ready_for_integration` only when its code has run at least once in the context it will run in.** Code that
was only read, or only validated, is untested code: the first deploy then becomes the test, the DevOps Engineer finds
the bug, and the whole feature goes back a step. Deploying is how resources are created, not how code is tried out.

Climb only as far as the task needs:

| Rung | Use it for | Cost |
| --- | --- | --- |
| `pytest` locally | Pure Python: parsing, transformations on small inputs, argument handling | seconds |
| `execute_sql` (MCP) or the CLI on the dev warehouse | SQL: queries, assertions, metric view statements, DDL inside the dev catalog | seconds |
| `execute_code` (MCP) or Databricks Connect serverless | Python that needs Spark or Unity Catalog, without any deployment | a minute |
| A one-off run: upload the file (dev-catalog volume or your own workspace folder) and `databricks jobs submit` | Code that must run **exactly as a job task**: the wrapper, the serverless image, the libraries, the task parameters | two minutes |
| `bundle deploy` + `bundle run` (DevOps Engineer) | Creating the resources and the end-to-end run | minutes, and a step back when it fails |

- The one-off run creates no bundle resource and disappears with the run: it is not a deployment and does not belong to
  the DevOps Engineer. Delete the uploaded file afterwards.
- `execute_code` fails on workspaces without a REPL channel. That is not a reason to deploy: use Databricks Connect or
  the one-off run (`df-engineering-standards/references/known-failures.md`).
- Report what you ran and where: "ran as a one-off job task, run id …" is evidence; "code reviewed" is not.

## Probe and capability checks

When a task exists to find out whether something works on this workspace:

- One check, one task, **no `depends_on` between unrelated checks** — a failure must not take the others down with it.
- Every check writes its own row (check id, `pass`/`fail`, details) to a results table; a final task with
  `run_if: ALL_DONE` reads the table and reports what is missing.
- A check cleans up what it creates, and says in its row what it left behind.

## Test types

| Type | Where | What | How |
| --- | --- | --- | --- |
| Data quality | `tests/data_quality/` + pipeline expectations | Keys unique and not null, ranges, referential integrity, freshness, row count reconciliation between layers, and a description on every object the feature creates | SQL assertions that return zero violating rows; expectations in pipelines for silver and gold; descriptions checked against `information_schema` or the object's metadata |
| Transformation | `tests/data_quality/` or `tests/integration/` | Business rules on small, known inputs | Synthetic input rows in a test table, expected output compared with `EXCEPT` both ways |
| Integration / end-to-end | `tests/integration/` | Deployed jobs and pipelines run successfully and produce the expected objects | Run results from the DevOps Engineer plus checks on the produced tables |
| BI | `tests/integration/` | Dashboard, metric view and Genie return the same number; the Genie space answers its question set and refuses what is out of scope | The expected-question set recomputed from the tables, never from what the dashboard reported (`df-bi`) |
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

## Running the suite

- Run SQL assertions with the Databricks MCP tools or the CLI against the dev warehouse.
- Group runnable tests in a bundle job (`resources/tests.job.yml`) so the DevOps Engineer can run them after each deployment.
- Test runners that run as Python tasks must not call `sys.exit()`, not even `sys.exit(0)`: Databricks reports any
  `SystemExit` as a failed task. Return normally when every check passes; raise an exception with the summary when some fail.

## Quality regression after G2

A model or an assistant that was approved carries its numbers forward: the metric values, the evaluation dataset and its
version, and the thresholds the PO accepted at G2 (they are in `reports/F-xxx-po-review.md`).

- Every later change — a new model version, a new prompt, a changed index, new data — is measured against that baseline
  **on the same dataset version**, and the comparison goes in the report: metric, baseline, delta, threshold.
- A drop below the threshold is a bug in the feature the change belongs to, not a note in a report.
- When the evaluation dataset itself changes, say so and recompute the baseline on the new version before comparing;
  never compare numbers from two different dataset versions.

## Evidence

Record for every criterion: the test, the result, and the evidence — query and result, job or pipeline run id, or MLflow
run id. The QA Engineer's report table is copied into the PO review report.
