---
name: df-pipelines
description: DeltaForce data engineering practices on Databricks — ingestion and schema evolution, change data capture and slowly changing dimensions, quarantine instead of silent drops, idempotency, backfills and late data, incremental reads. Use when designing or building a pipeline, a job that loads or transforms data, or a table that others will trust.
---

# DeltaForce — pipelines that can be trusted

The Data Engineer builds them; the Solution Architect designs the flow; QA checks the data, not the code. For current
APIs load `databricks-pipelines`, `databricks-lakeflow-connect`, `databricks-spark-structured-streaming` and
`databricks-jobs` — this skill is about the decisions those APIs do not make for you.

## 1. Ingestion

- **Bronze keeps what arrived**: the source columns as received, plus ingestion metadata (source file or offset, ingestion
  timestamp, batch id). No business logic, no renaming, nothing dropped — bronze is what lets you prove what the source sent.
- Files arrive incrementally: Auto Loader, not a directory listing rebuilt every run. Checkpoints live with the pipeline
  and are never deleted to "make it re-run" (in an existing project that is a destructive operation, `df-engineering-standards`).
- **Schema evolution is a decision, not a surprise.** Say in the design what happens when the source adds a column
  (take it), renames one (map it), or changes a type (fail, do not coerce silently). New columns land in bronze;
  everything downstream names the columns it needs.
- Record in the table description where the data comes from and how often it lands.

## 2. Quarantine, never a silent drop

A row that fails a rule is evidence, not noise. Dropping it silently makes the numbers wrong and nobody knows.

- Expectations that **fail the row into a quarantine table** with the rule that rejected it, the batch id and the
  timestamp — not `expect_or_drop` on a rule that matters.
- `expect_or_drop` and `expect_or_fail` stay for the rules where dropping or stopping is the intended behaviour, and the
  design says which ones those are.
- Quarantine is monitored like any other table: a count per rule, a threshold agreed at G1, and a data quality test that
  fails when it grows past it. A quarantine nobody looks at is a silent drop with extra steps.
- The report says how many rows were quarantined, by rule — QA re-runs that count.

## 3. Change data capture and history

- Ask first what the business needs: the current state (SCD type 1) or the history of changes (SCD type 2). The answer
  belongs in the Architecture, and it decides the shape of silver.
- Apply changes with the platform's CDC support (Lakeflow declarative pipelines' AUTO CDC / `APPLY CHANGES`, or the
  equivalent in the project's stack) rather than a hand-written merge: ordering, deletes and out-of-order events are
  the part that is easy to get subtly wrong.
- Whatever the mechanism, be explicit about: the **key**, the **sequence column** that orders events, how **deletes**
  arrive (a flag, a tombstone, nothing at all), and what happens to a late event that belongs before rows already written.
- SCD type 2 tables carry validity columns and exactly one current row per key; that is a uniqueness test, not a comment.

## 4. Idempotency and backfills

- Running a pipeline twice must not change the result: no `INSERT` into a table that a re-run also inserts into, no
  aggregation that adds to what is already there. Merge on a key, or overwrite a partition you own.
- A backfill is a parameter (a date range), not a copy of the code with the dates edited in. The same job runs the
  backfill and the daily load.
- State that can be rebuilt is worth more than state that cannot: keep the source in bronze so silver and gold can be
  rebuilt from scratch, and say in the report how long a full rebuild takes.

## 5. Late, duplicated and out-of-order data

- Deduplicate on a business key with a deterministic rule (latest by sequence column), not on "whatever arrived last".
- Say how late an event may be and still be counted, and what happens to one that arrives later — restated numbers or a
  correction table. A KPI that silently changes after the fact is a bug the business finds before you do.
- Watermarks and windows in streaming are part of the design, with the business meaning written down.

## 6. What every pipeline owes the team

- Bundle resource, names from variables, description on every table and column (`df-engineering-standards`).
- Expectations on silver and gold, a quarantine where rows can fail, and reconciliation between layers as a test
  (`df-testing`).
- Ran at least once before the handover, and the run id in the report.
- A note of what it costs: how long it runs, on what compute, and how it grows when the data grows.
