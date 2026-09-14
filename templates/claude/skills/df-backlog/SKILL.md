---
name: df-backlog
description: DeltaForce project state, backlog and event formats — state.yaml, feature files, task and feature statuses, PO review reports and the df event/validate helper. Use whenever reading or updating project state or logging lifecycle events.
user-invocable: false
---

# DeltaForce backlog and state

The PM is the only writer of these files. Specialists report; the PM records. The files are a contract read by tools, so keep the formats exact and run `bash .deltaforce/bin/df validate` after every change.

## Layout

```text
.deltaforce/
  config.yaml            # installer answers (read-only for the team)
  conventions.yaml       # client conventions
  state.yaml             # where the project stands
  backlog/F-001-<slug>.md
  reports/F-001-po-review.md, handover.md
  events.jsonl           # lifecycle events, append-only
docs/requirements/request.md, requirements.md
docs/architecture/solution.md, adr/
```

## state.yaml

```yaml
version: 1
phase: delivery              # discovery | awaiting_g1 | delivery | handover | done
dev_branch: dev
active_features: [F-001, F-002]
g1:
  status: approved           # pending | approved | changes_requested
  at: 2026-09-14T10:30:00Z   # null while pending
  notes: ""
updated: 2026-09-14T15:32:00Z
```

## Feature file — `.deltaforce/backlog/F-003-<slug>.md`

```markdown
---
id: F-003
title: Silver customer deduplication
status: in_test
depends_on: [F-001]
branch: df/F-003
tasks:
  - id: T-003.1
    title: Deduplicate customers in silver
    role: data-engineer
    status: integrated
    branch: df/F-003/data-engineer-T1
  - id: T-003.2
    title: Data quality tests for silver customers
    role: qa-engineer
    status: in_progress
    branch: null
po_decision: null            # or {decision: approved|changes_requested, at: <timestamp>, notes: "..."}
created: 2026-09-14T10:00:00Z
updated: 2026-09-14T15:32:00Z
---

## Business value

Objectives: O1, O3 (see docs/requirements/requirements.md). One or two sentences on what this feature brings to the client.

## User stories

## Acceptance criteria

1. ...

## Design references

- docs/architecture/solution.md#...

## Log

- 2026-09-14 — integrated and deployed to dev (run 123456)
```

Ids: features `F-001`, `F-002`, …; tasks `T-<feature number>.<n>`. Slugs are lowercase words joined by `-`. Timestamps are UTC ISO 8601.

## Statuses

Feature: `todo → in_progress → integrating → in_test → awaiting_po → done`, plus `blocked`.

- `changes_requested` at G2 moves `awaiting_po → in_progress` with new fix tasks.
- Only a PO decision (`/df-approve`) moves a feature to `done`, after the DevOps Engineer merged it into the dev branch.
- A feature can start only when all `depends_on` features are `done`.

Task: `todo → in_progress → ready_for_integration → integrated → done`, plus `blocked`.

## Events

Append one event per lifecycle change:

```bash
bash .deltaforce/bin/df event <type> --role pm [--feature F-003] [--task T-003.1] [--data '{"from":"in_progress","to":"integrating"}']
```

| Type | When | Typical data |
| --- | --- | --- |
| `kickoff_completed` | `/df-kickoff` finished collecting input | `{"conventions":"defaults"}` |
| `phase_changed` | `state.yaml` phase changes | `{"from":"discovery","to":"awaiting_g1"}` |
| `feature_created` | a feature file is created | `{"title":"..."}` |
| `feature_status_changed` | a feature status changes | `{"from":"...","to":"..."}` |
| `task_status_changed` | a task status changes | `{"from":"...","to":"..."}` |
| `delegation_started` / `delegation_finished` | a specialist is called / reports | `{"agent":"data-engineer","result":"done"}` |
| `deploy_started` / `deploy_finished` | the DevOps Engineer deploys to dev | `{"features":["F-003"],"result":"success"}` |
| `test_run` | QA results recorded | `{"passed":12,"failed":0}` |
| `po_decision` | G1 or G2 decision | `{"gate":"G2","decision":"approved"}` |
| `escalation` | something needs the PO | `{"reason":"..."}` |
| `conventions_changed` | `.deltaforce/conventions.yaml` changes | `{"keys":["bundle.root_path"]}` |

The helper adds the timestamp and validates the event.

## PO review report — `.deltaforce/reports/F-xxx-po-review.md`

```markdown
# F-003 — Silver customer deduplication

## What was built
## Business value delivered
Objectives served, and how the result moves the success metrics (or how it will be measured).
## Databricks objects created or changed
## Test evidence
| Acceptance criterion | Test | Result | Evidence |
## Where to look
## Deviations from the design and known limitations
```
