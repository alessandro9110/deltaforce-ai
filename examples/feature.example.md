---
id: F-001
title: Silver customer deduplication
status: in_test
depends_on: []
branch: df/F-001
tasks:
  - id: T-001.1
    title: Deduplicate customers in silver
    role: data-engineer
    status: integrated
    branch: df/F-001-data-engineer-T1
  - id: T-001.2
    title: Data quality tests for silver customers
    role: qa-engineer
    status: in_progress
    branch: null
  - id: T-001.3
    title: Keep the latest record when a customer id repeats
    role: data-engineer
    status: integrated
    branch: df/F-001-data-engineer-T3
bugs:
  - id: B-001
    title: Duplicate customers when the same id arrives twice in one batch
    severity: major
    status: fixed
    found_by: qa-engineer
    found_during: test
    found_in: F-001
    evidence: "SELECT customer_id, count(*) FROM silver_customers GROUP BY 1 HAVING count(*) > 1 returned 42 rows"
    fix_tasks: [T-001.3]
    opened: 2026-09-14T13:10:00Z
    closed: null
po_decision: null
started: 2026-09-14T11:00:00Z
completed: null
created: 2026-09-14T10:00:00Z
updated: 2026-09-14T15:32:00Z
---

## Business value

Objectives: O1. Correct customer counts make campaign targeting and budget allocation reliable.

## User stories

As a marketing analyst, I want one row per customer in silver, so that campaign counts are correct.

## Acceptance criteria

1. `customer_id` is unique and never null in the silver customers table.
2. Row count equals the number of distinct customer ids in bronze.

## Design references

- .deltaforce/architecture/architecture.md#customers

## Log

- 2026-09-14 — integrated and deployed to dev
