---
name: df-backlog
description: DeltaForce project state, backlog and event formats — state.yaml, feature files, task and feature statuses, PO review reports and the df events/validate helper. Use whenever reading or updating project state or logging lifecycle events.
user-invocable: false
---

# DeltaForce backlog and state

The PM is the only writer of these files. Specialists report; the PM records. The files are a contract read by tools, so keep the formats exact and validate after every change (`df events` does it for you).

## Layout

```text
.deltaforce/
  config.yaml            # installer answers (read-only for the team)
  conventions.yaml       # client conventions
  state.yaml             # where the project stands
  requirements/          # request.md (PM), as-is.md and functional-analysis.md (Business Analyst)
  architecture/          # as-is.md, discovery.md, architecture.md, adr/ (Solution Architect)
  backlog/F-001-<slug>.md
  reports/F-001-po-review.md, handover.md
  events.jsonl           # lifecycle events, append-only
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
next_steps:                  # the to-do list a resumed session and the PO read first
  - owner: devops-engineer     # po or a role id
    feature: F-002
    action: Integrate T-002.1 and T-002.2 into df/F-002 and deploy to dev
  - owner: po
    feature: F-001
    action: Review F-001 (/df-approve F-001 or /df-changes F-001)
last_update:
  at: 2026-09-14T15:32:00Z
  summary: QA passed on F-001; F-002 build tasks ready for integration
updated: 2026-09-14T15:32:00Z
```

Rewrite `next_steps` and `last_update` at every state change. Anyone opening the project — a new session, the PO, the monitoring app — must be able to tell from them what was just done and what comes next, without the conversation.

## Feature file — `.deltaforce/backlog/F-003-<slug>.md`

```markdown
---
id: F-003
title: Silver customer deduplication
status: in_test
depends_on: [F-001]
change_of: null              # on a change feature: the done feature it changes, e.g. F-001
branch: df/F-003
tasks:
  - id: T-003.1
    title: Deduplicate customers in silver
    role: data-engineer
    status: integrated
    branch: df/F-003-data-engineer-T1
    report: .deltaforce/reports/tasks/T-003.1.md
  - id: T-003.2
    title: Data quality tests for silver customers
    role: qa-engineer
    status: in_progress
    branch: null
po_decision: null            # or {decision: approved|changes_requested, at: <timestamp>, notes: "..."}
started: 2026-09-14T11:00:00Z  # first time the feature went in_progress; null before
completed: null              # when it became done; null until then
created: 2026-09-14T10:00:00Z
updated: 2026-09-14T15:32:00Z
---

## Business value

Objectives: O1, O3 (see .deltaforce/requirements/functional-analysis.md). One or two sentences on what this feature brings to the client.

## User stories

## Acceptance criteria

1. ...

## Design references

- .deltaforce/architecture/architecture.md#...

## Log

- 2026-09-14 — integrated and deployed to dev (run 123456)
```

Ids: features `F-001`, `F-002`, …; tasks `T-<feature number>.<n>`. Slugs are lowercase words joined by `-`. Timestamps are UTC ISO 8601.

## Statuses

Feature: `todo → in_progress → integrating → in_test → awaiting_po → done`, plus `blocked`.

- `changes_requested` at G2 moves `awaiting_po → in_progress` with new fix tasks.
- Only a PO decision (`/df-approve`) moves a feature to `done`, after the DevOps Engineer merged it into the dev branch.
- Set `started` the first time a feature moves to `in_progress` and never change it afterwards; set `completed` when it moves to `done`. They feed the project board (what was delivered and when, cycle time).
- A feature can start only when all `depends_on` features are `done`.
- A `done` feature is never reopened. A change the PO asks for after delivery is a new **change feature**: `change_of` names the original, `depends_on` includes it, and it has its own tasks, branch and G2.

Task: `todo → in_progress → ready_for_integration → integrated → done`, plus `blocked`.

## Events

Record the events of one change together, in a single call — it appends all of them (or none, when one is invalid) and then validates the whole project:

```bash
bash .deltaforce/bin/df events '[{"type":"task_status_changed","role":"pm","feature":"F-003","task":"T-003.1","data":{"from":"in_progress","to":"ready_for_integration"}},{"type":"feature_status_changed","role":"pm","feature":"F-003","data":{"from":"in_progress","to":"integrating"}}]'
```

Every tool call re-reads the whole conversation: do not run one command per event, and do not run `df validate` separately after `df events`. `bash .deltaforce/bin/df event <type> --role pm [--feature] [--task] [--data]` records a single event.

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

## Task reports — `.deltaforce/reports/tasks/T-xxx.n.md`

Specialists' reports exist only in the conversation until the PM saves them. Save every report, verbatim, as soon as it arrives — also `blocked` and `needs-decision` ones — and set the task's `report` field to the file:

```markdown
# T-003.1 — Deduplicate customers in silver

## 2026-09-14T14:05:00Z — data-engineer — done
<the report as received>

## 2026-09-14T16:40:00Z — data-engineer — done (fix round)
<the next report>
```

One file per task; each delegation round adds a dated section. Consultation reports without a task go to `.deltaforce/reports/tasks/F-xxx-<topic>.md`.

## PO review report — `.deltaforce/reports/F-xxx-po-review.md`

```markdown
# F-003 — Silver customer deduplication

## What was built
## Business value delivered
Objectives served, and how the result moves the success metrics (or how it will be measured).
## Databricks objects created or changed
## Destructive operations on existing data or objects
None, or each operation with the object and the data rule that allows it (existing projects).
## Test evidence
| Acceptance criterion | Test | Result | Evidence |
## Regression checks
| Existing object or test | Check | Result | Evidence |
(existing projects)
## Model and AI evaluation
(ML and GenAI features: baseline, leaderboard, chosen model or setup with version and alias, evaluation dataset version, thresholds met, MLflow run ids)
## Created outside the bundle
(Agent Bricks: each Knowledge Assistant or Supervisor Agent, its definition in src/ai/agent_bricks/ and how other environments get it)
## Where to look
## What to configure before the first run
(CI/CD feature: service principal and permissions, variable group or secrets with each BUNDLE_VAR_ value, environments and approvals, production workspace)
## Deviations from the design and known limitations
```
