# DeltaForce AI — Design

Status: **Draft v0.1** · 2026-09-14 · design agreed in discussion with the maintainer, no code yet.

## 1. Goal

DeltaForce AI is an installable Claude Code framework that gives a project repository a team of specialized agents able to design, build, test and deploy on Databricks — data engineering, analytics, data science, ML and GenAI.

It is installed from GitHub with `install.sh` into a **target project repo**, configured through a config file, and wires up the Databricks AI tooling (agent skills + MCP server) so the team can operate against a real Databricks workspace.

## 2. Constraints and decisions

| Topic | Decision |
|---|---|
| Agent runtime | Claude Code only |
| Install scope | **Project only, never global**: skills, MCP server, ai-dev-kit runtime and Claude Code config all live inside the target repo |
| Team OS | Windows (installer and hooks run under Git Bash); CI runners are Linux |
| Deployment unit | Databricks Asset Bundles (DABs) |
| Prod deployment | Only through CI/CD — Azure DevOps now, GitHub Actions later |
| Language | Agent prompts, templates and repo docs in English |
| Data architecture | Medallion (bronze/silver/gold) for every discipline: DE, analytics, ML, AI |
| Parameters | Every environment-specific value (catalog, schemas, table names, endpoints) is a variable |
| Git | Never push to `main`. Work lands in a dev branch. The PR to `main` is opened by a human |
| PO involvement | Approves design + feature list once (G1), validates **every** feature (G2), and is consulted on blockers or changes to the request |
| Feature cadence | One feature at a time; parallelism only inside a feature |
| Backlog | Markdown files in the repo, machine-readable (future monitoring app) |

## 3. Two repositories

- **DeltaForce AI (this repo)** — the framework: agent definitions, skills/commands, hooks, templates, installer, schemas.
- **Target project repo** — where the team works. The installer copies templates into it and configures Databricks tooling. All project state (backlog, events, audit) lives here.

## 4. Team

The PO is the human user. The PM is the main Claude Code session (`claude --agent pm`); every other role is a subagent in `.claude/agents/`.

| Role (id) | Responsibilities | May | May not |
|---|---|---|---|
| **PM** (`pm`) | Intake, planning, feature sequencing, backlog owner, PO reports and escalations | Read everything, write backlog/state/reports, delegate | Write source code, change Databricks resources |
| **Solution Architect** (`solution-architect`) | End-to-end solution design, medallion flows, table naming proposal, ADRs, bundle layout, design conformance review | Read UC metadata, write `docs/architecture/` | Write source code, deploy |
| **Business Analyst** (`business-analyst`) | Requirements, user stories, acceptance criteria, functional support to team and PM | Read-only data discovery, write `docs/requirements/` | Write source code, deploy |
| **Data Engineer** (`data-engineer`) | Ingestion, bronze → silver → gold pipelines, jobs | Write `src/pipelines`, run SQL/code on dev, `bundle validate` | Deploy |
| **Data Analyst** (`data-analyst`) | Gold marts, metric views, AI/BI dashboards, Genie spaces; supports QA on data tests | Query dev, write dashboards/metric views | Deploy |
| **Data Scientist** (`data-scientist`) | EDA, feature engineering, training, MLflow experiments, UC model registration | Run code on dev, MLflow | Deploy |
| **AI Engineer** (`ai-engineer`) | RAG, Vector Search, Agent Bricks / custom agents, GenAI evaluation, serving, apps | Vector Search / serving on dev, write `src/ai`, `src/apps` | Deploy |
| **QA Engineer** (`qa-engineer`) | Data quality tests, integration tests, ML/AI evaluation gates | Run tests on dev, read everything, write `tests/` | Modify source code |
| **DevOps Engineer** (`devops-engineer`) | Integration: merge task branches, `bundle validate/deploy/run` on dev, CI/CD definitions, push to dev branch | Deploy and run on **dev** only, write `cicd/`, git merge/push | Touch prod, write business code, push to `main` |

### Skills per role

Skills come from `databricks aitools` (official `databricks/databricks-agent-skills`) and are preloaded through the subagent `skills:` frontmatter. All roles get `databricks-core`.

| Role | Skills |
|---|---|
| solution-architect | `databricks-dabs`, `databricks-unity-catalog`, `databricks-docs`, `databricks-metric-views` |
| business-analyst | `databricks-data-discovery` |
| data-engineer | `databricks-pipelines`, `databricks-jobs`, `databricks-dabs`, `databricks-lakeflow-connect`, `databricks-spark-structured-streaming` |
| data-analyst | `databricks-dbsql`, `databricks-aibi-dashboards`, `databricks-metric-views`, `databricks-data-discovery` |
| data-scientist | `databricks-ml-training`, `databricks-synthetic-data-gen`, `databricks-python-sdk` |
| ai-engineer | `databricks-agent-bricks`, `databricks-vector-search`, `databricks-model-serving`, `databricks-mlflow-evaluation`, `databricks-ai-functions`, `databricks-apps-python` |
| qa-engineer | `databricks-dbsql`, `databricks-mlflow-evaluation`, `databricks-synthetic-data-gen` |
| devops-engineer | `databricks-dabs`, `databricks-jobs`, `databricks-pipelines` |

Default models (overridable in config): `pm` and `solution-architect` on Opus, the other roles on Sonnet.

### Example agent definition

```markdown
---
name: data-engineer
description: Builds ingestion and medallion pipelines (bronze/silver/gold) and jobs on Databricks. Use for data pipeline tasks of the current feature.
model: sonnet
isolation: worktree
color: blue
skills:
  - databricks-core
  - databricks-pipelines
  - databricks-jobs
  - databricks-dabs
tools: Read, Edit, Write, Grep, Glob, Bash, Agent(data-engineer), mcp__databricks__execute_sql, mcp__databricks__execute_code, mcp__databricks__get_table_stats_and_schema
---
```

## 5. Process

```mermaid
flowchart TD
  K["Phase 0 · Kickoff<br/>PO: what to build + catalog, schema(s), optional table names, dev branch"] --> R[BA: requirements]
  R --> D[SA: solution design]
  D --> B[BA + SA + PM: feature breakdown]
  B --> G1{"G1 · PO approves<br/>design + feature list + proposals"}
  G1 -- changes --> D
  G1 -- approved --> P[PM: plan tasks of next feature]
  P --> W["Developers in parallel<br/>(worktrees, task branches)"]
  W --> I["DevOps: merge, validate, deploy + run on dev"]
  I --> Q["QA: data / integration / evaluation tests"]
  Q -- fail --> W
  Q -- pass --> G2{"G2 · PO validates feature"}
  G2 -- changes --> P
  G2 -- approved --> M[DevOps: merge feature into dev branch, push]
  M --> N{More features?}
  N -- yes --> P
  N -- no --> H["Phase 3 · human opens PR dev → main<br/>CI/CD deploys prod"]
```

- **Phase 0 — Kickoff** (`/df-kickoff`): the PO states *what the team must build* and provides the elements: catalog, schema(s), optional table names, dev branch. Stored in `.deltaforce/config.yaml` and `docs/requirements/request.md`.
- **Phase 1 — Discovery & design**: BA writes requirements; SA designs the full solution (architecture, medallion flows for each discipline, table naming proposal when the PO gave none); BA + SA + PM derive the feature list with dependencies and per-role tasks. **G1**: PO approves once.
- **Phase 2 — Delivery**, one feature at a time: parallel development → integration and dev deploy by DevOps → QA → PM feature report → **G2**: PO validates. No other feature starts before G2.
- **Escalation** at any time, and only then: blocker, ambiguity, or a change compared to the request.
- **Phase 3 — Handover**: dev branch pushed and CI/CD definitions ready; a human opens the PR to `main`; CI/CD deploys prod.

### Status model

- Feature: `todo → in_progress → integrating → in_test → awaiting_po → done`, plus `blocked`. A G2 rejection moves `awaiting_po → in_progress`. Only a PO decision moves a feature to `done`.
- Task: `todo → in_progress → ready_for_integration → integrated → done`, plus `blocked`.

## 6. Orchestration model

**Decision: subagents as the backbone; agent teams evaluated and kept out of the MVP.**

- PM runs as the main session with `claude --agent pm`, so hooks see `agent_type: pm` too.
- Specialist roles are subagents.
- Subagents are stateless between calls; collaboration happens through repo artifacts (requirements, architecture, backlog) plus the delegation prompt written by the PM.

### Nested delegation

Subagents may spawn other subagents. Nesting depth comes from `orchestration.max_spawn_depth` in config (default `3`, Claude Code's own default), written to `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`. Who may spawn whom is restricted per role with the `Agent(<agent_type>)` syntax in the `tools` frontmatter:

| Role | May spawn | Typical use |
|---|---|---|
| pm | every role | normal delegation of phase and feature work |
| solution-architect | data-engineer, data-analyst, data-scientist, ai-engineer, Explore | discipline feasibility checks while designing |
| business-analyst | data-analyst, Explore | data discovery to ground requirements |
| data-engineer | data-engineer | parallel sub-tasks (e.g. bronze, silver, gold of one task) |
| data-scientist | data-scientist, data-analyst | parallel experiments, EDA support |
| ai-engineer | ai-engineer, data-engineer | parallel RAG components, document ingestion pipeline |
| qa-engineer | data-analyst | data test support: profiling, reconciliation queries |
| devops-engineer | none | single integrator, never delegates |

Rules:

- A parent integrates its children's work into its own task branch before reporting. DevOps still sees exactly one branch per backlog task.
- Consultations (e.g. SA → data-engineer feasibility check) produce findings, not branches. DevOps only merges branches listed in the backlog.
- Children report to their parent, parents report to the PM. The PM stays the only backlog writer.
- Guardrails apply at every level: hooks see the child's own `agent_type`, so a data-engineer spawned by the SA still cannot deploy.
- Token cost grows with depth and fan-out. Lower the depth in config if cost becomes an issue.

### Agent teams — evaluation (Claude Code docs, v2.1.2xx)

Agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) run teammates as independent sessions with a shared task list and direct messaging. Reasons they don't fit delivery today:

- **Experimental**; in-process teammates are **not restored by `/resume`** — a project spans days and waits on PO gates.
- The shared task list lives in `~/.claude/tasks/<team>/` (user-local), not in the repo — conflicts with the repo backlog as single source of truth and with the monitoring app.
- Subagent `skills:` are **not applied to teammates** — per-role Databricks skill preloading is lost.
- Teammates inherit the lead's permission mode; no per-teammate mode at spawn; permission prompts bubble to the lead.
- Split panes are not supported in Windows Terminal (in-process mode only).
- Significantly higher token usage.
- When enabled, any subagent Claude names launches as a teammate — so the flag stays off by default.

**Where they could add value**: Phase 1 cross-discipline design review, with SA, DE, DS and AI Engineer challenging the design in parallel. `TaskCreated`, `TaskCompleted` and `TeammateIdle` hooks can act as quality gates there. Planned as an opt-in experiment (roadmap M6).

## 7. Git and branching

- The PO provides the **dev branch** (e.g. `dev` or `dev/customer-360`). The main checkout sits on it. `main` is only for prod / CI/CD triggers.
- Per feature, DevOps creates `df/F-003` from the dev branch and the PM checks it out before delegating.
- Developer subagents use `isolation: worktree`. Project settings set `worktree.baseRef: "head"`, because the default (`"fresh"`) branches from the remote default branch (`main`).
- Task branches: `df/F-003/<role>-T<n>`, pushed to the remote for traceability.
- DevOps merges task branches into `df/F-003`, deploys it to dev, and after G2 merges `df/F-003` into the dev branch and pushes. The dev branch only contains PO-validated features.
- Commit trailers: `DeltaForce-Role: <role>` and `DeltaForce-Task: F-003/T-003.1`.
- Guard hook blocks: push to `main`/`master` (configurable protected list), force push, `reset --hard` on the dev branch, remote deletion of the dev branch.

```json
{
  "env": {
    "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "3",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "0"
  },
  "worktree": { "baseRef": "head" }
}
```

## 8. Databricks conventions

### Parameters

- Config values become DABs variables: `catalog`, `schema_bronze`, `schema_silver`, `schema_gold`, and one variable per table.
- Medallion layout is configurable: `single_schema` (layer prefix on table names, default when the PO gives one schema) or `multi_schema` (one schema per layer).
- Table names: PO-provided, or proposed by the SA and approved at G1. Either way they are stored in config and generated into `resources/variables.yml`.
- **The dev catalog is the boundary, the installer's schemas are the starting point.** The team is free to create further schemas and tables inside the dev catalog when the solution needs them, as long as they are consistent with what is being built: they follow the medallion layers, are described in `docs/architecture/`, and are declared as bundle resources with variables (never created by hand). New objects coherent with the approved design need no PO escalation; objects that change the request do.
- Dev target uses `mode: development`; prod target uses `mode: production` with values injected by CI/CD (`BUNDLE_VAR_<name>`) and a service principal.
- No literal catalog/schema/table names in source: enforced by a hook on edits under `src/` and by QA review.

### Medallion across disciplines

| Layer | Data engineering / analytics | ML | GenAI |
|---|---|---|---|
| Bronze | Raw ingested data, raw files in volumes | Raw training sources | Raw documents (PDF, HTML) in volumes |
| Silver | Cleaned, conformed, deduplicated | Cleaned training data | Parsed and chunked documents |
| Gold | Business aggregates, marts, metric views | Feature tables, inference outputs | Vector index source tables, evaluation datasets |

UC assets follow the same parameters: models `${var.catalog}.${var.schema_gold}.<model>`, vector indexes on gold, serving endpoint and app names suffixed per target.

- **ML lifecycle**: EDA → gold feature table → MLflow training → UC model registration → evaluation → dev serving. QA checks metric thresholds.
- **AI lifecycle**: bronze documents → silver parse/chunk → gold vector index → agent (Agent Bricks or custom) → MLflow evaluation → dev serving or app. QA checks evaluation thresholds.

### Target project layout

```
databricks.yml
resources/              # jobs, pipelines, dashboards, serving, apps, variables.yml
src/
  pipelines/            # bronze/, silver/, gold/
  ml/                   # features/, training/, inference/
  ai/                   # agents/, rag/, evaluation/
  apps/
  dashboards/
tests/
  data_quality/
  integration/
  evaluation/
cicd/
  azure-devops/
  github/               # later
docs/
  requirements/
  architecture/adr/
.deltaforce/            # config, state, backlog, events, audit, reports
.claude/                # agents, skills, hooks, settings.json
CLAUDE.md
```

## 9. Backlog and observability contract

The backlog is designed to be read by a future monitoring app without changes.

```
.deltaforce/
  config.yaml           # installer answers (committed, no secrets); kickoff adds request and tables
  status.json           # doctor result gating /df-kickoff (gitignored)
  .databrickscfg        # project-local CLI profile (gitignored)
  bin/, runtime/        # uv, Databricks CLI, Python, AI Dev Kit, MCP venv (gitignored)
  state.yaml            # current phase, current feature, dev branch
  backlog/F-003-silver-customer-dedup.md
  reports/F-003-po-review.md
  events.jsonl          # lifecycle events
  audit.jsonl           # tool calls per role
```

Feature file:

```markdown
---
id: F-003
title: Silver customer deduplication
status: in_test
depends_on: [F-001]
branch: df/F-003
tasks:
  - id: T-003.1
    role: data-engineer
    status: integrated
    branch: df/F-003/data-engineer-T1
  - id: T-003.2
    role: qa-engineer
    status: in_progress
po_decision: null        # approved | changes_requested, with timestamp and notes
created: 2026-09-14T10:00:00Z
updated: 2026-09-14T15:32:00Z
---
## User story
## Acceptance criteria
## Design references
## PO review
```

Event line: `{"ts", "session_id", "agent_id", "role", "event", "feature", "task", "data"}`. Event types: `phase_changed`, `feature_status_changed`, `task_status_changed`, `subagent_started`, `subagent_stopped`, `deploy_started`, `deploy_finished`, `test_run`, `po_decision`, `escalation`.

Single-writer rules:

- Worktree-isolated subagents cannot edit files in the main checkout, so **the PM is the only writer of backlog and state**, updating them from subagent results. DevOps updates integration status from the main checkout.
- Hooks append `events.jsonl` and `audit.jsonl` through `${CLAUDE_PROJECT_DIR}`, which stays on the main checkout.
- JSON Schemas for config, feature frontmatter and events live in the framework under `schemas/`.

## 10. Permissions, guardrails, audit

- **Tool allowlists** per role in agent frontmatter, including individual MCP tools (`mcp__databricks__execute_sql` yes, `mcp__databricks__manage_jobs` only for DevOps).
- **Hooks in Python**, run with `uv run`, portable between Windows (Git Bash) and Linux CI. Tool-event hooks receive `agent_type`, which maps to the role policy:
  - `PreToolUse` guard: bundle deploy/run only for `devops-engineer` and only on dev target; protected-branch git rules; destructive SQL (`DROP`, `DELETE`, `TRUNCATE`) outside the dev catalog; literal catalog/schema names in `src/`.
  - `PostToolUse` → `audit.jsonl`; `SubagentStart`/`SubagentStop` → `events.jsonl`.
- **Commit trailers** give durable per-role traceability in git history.
- **Databricks identity**: in the MVP all roles share the user's CLI profile, so Databricks audit logs don't distinguish roles and enforcement is Claude-side. Later: dedicated service principals (at least for DevOps) with UC grants for hard enforcement.
- **No secrets in repo**: OAuth via `databricks auth login`, profiles in `~/.databrickscfg`; config stores only the profile name.

## 11. Installer

**The installer only installs.** It asks for the technical environment, installs everything, and finishes with the doctor. `/df-kickoff` (what to build, table names) starts only once the doctor reports ready.

**Everything is project-scoped — nothing is installed globally.** Git for Windows and Claude Code are checked, never installed. With OAuth, the Databricks CLI keeps its token cache in the user profile; that cache is the only user-level artifact.

**The whole installation happens in the IDE's integrated terminal, with one command** — no separate windows, no manual cloning. The command (PowerShell, Command Prompt and Git Bash variants in the README) clones the framework into `.deltaforce/framework` if missing and runs `bash .deltaforce/framework/install.sh`. The same command updates and reconfigures later.

`install.sh` bootstraps itself: when it runs without its `lib/` folder (e.g. piped) it clones `DF_REPO_URL` at `DF_REF` (default `main`) into `.deltaforce/framework`; when it runs from `.deltaforce/framework` it fetches `DF_REF` first; then it re-executes the fresh copy. `--help` and `--doctor` skip the update. The framework copy is gitignored.

```bash
bash .deltaforce/framework/install.sh [--target DIR] [--advanced] [--non-interactive] [--yes] [--dry-run] [--doctor]
```

Steps (implemented in `install.sh` + `lib/`):

1. **Preflight** — bash ≥ 4, `git`, `curl`, `tar`, `unzip` (Windows); offers `git init` when the folder is not a repository (never during `--dry-run`); must be the repository root; Windows path length vs `LongPathsEnabled`; Claude Code detected; conflicting `DATABRICKS_*` environment variables are ignored and reported.
2. **Questions, part 1** — project name, protected branches, dev branch, CI/CD provider (git provider detected from `origin`), workspace URL, CLI profile name (never `DEFAULT`), auth method (`oauth` default, `pat`, `service-principal`). Values from an existing config are the defaults. `--dry-run` prints the plan here and exits.
3. **Git and project-local tools** — after confirmation, the dev branch is checked out; if missing, the installer offers to create it (with an initial empty commit in an empty repository) and to push it when a remote exists. Then uv and Databricks CLI downloaded from their GitHub releases into `.deltaforce/bin/` at the versions pinned in `lib/data/versions.env`; Python installed by uv into `.deltaforce/runtime/python` (`UV_PYTHON_INSTALL_DIR`, `UV_CACHE_DIR`, `UV_LINK_MODE=copy` because OneDrive rejects hardlinks).
4. **Authentication** — profile written to `.deltaforce/.databrickscfg` through `DATABRICKS_CONFIG_FILE`: `databricks auth login` (OAuth), `databricks configure` (PAT, token read hidden) or a client ID/secret section (service principal); verified with `current-user me`.
5. **Questions, part 2** (live lists from the workspace) — SQL warehouse, compute (serverless or cluster), dev catalog (must exist; re-asked otherwise), medallion layout and schema(s); missing schemas are created (`databricks schemas create`). With `--advanced`: roles, default model, nesting depth, AI Dev Kit ref.
6. **Configuration** — `.deltaforce/config.yaml`, validated against `schemas/config.schema.json`.
7. **AI Dev Kit MCP server** — sparse, shallow clone of `databricks-mcp-server` and `databricks-tools-core` at the pinned ref into `.deltaforce/runtime/ai-dev-kit` (`core.longpaths=true`), venv in `.deltaforce/runtime/venv` built directly with uv (the upstream `setup.sh`/`mcp_install.sh` assume Unix venv paths).
8. **Databricks skills** — `databricks aitools install --path .claude/skills --skills <union of role skills>`: plain folders, no symlinks and no global state (aitools project scope symlinks, which Windows restricts).
9. **Generated files** — from the config: `.mcp.json` (absolute paths, gitignored), `.claude/settings.json` (nesting depth, agent teams off, `worktree.baseRef: head`, `enabledMcpjsonServers`), `.claude/settings.local.json` (`DATABRICKS_CONFIG_FILE` + profile for every Bash call), the `CLAUDE.md` project-context block, `databricks.yml` (created once) and `resources/deltaforce.variables.yml` (dev values only; prod values must come from CI/CD), a managed `.gitignore` block.
10. **Doctor** — config, Claude Code, git and dev branch, tool versions, authentication, warehouse/cluster, catalog and schemas, MCP server import, skills, generated files, `bundle validate -t dev` (warning only). Result in `.deltaforce/status.json`; `/df-kickoff` requires `ready: true`. Rerun with `--doctor`.

The installer is idempotent: re-runs reuse downloaded tools, the AI Dev Kit checkout at the same ref, and regenerate managed files without touching user content outside managed blocks.

## 12. Framework repository layout (planned)

```
deltaforce-ai/
  install.sh
  lib/                  # installer modules: prereqs, auth, templates, skills, mcp, doctor
  templates/
    .claude/
      agents/           # pm.md, solution-architect.md, ... devops-engineer.md
      skills/           # df-kickoff, df-status, df-approve, df-changes, df-next
      hooks/            # guard.py, audit.py, events.py, lint_names.py
      settings.json
    CLAUDE.md.tmpl
    databricks.yml.tmpl
    resources/ src/ tests/ cicd/ docs/   # skeletons
    .deltaforce/config.yaml.tmpl
  schemas/              # JSON Schemas: config, feature, event
  docs/                 # design.md, roadmap.md
  tests/                # installer tests, hook unit tests
```

PO-facing commands: `/df-kickoff`, `/df-status`, `/df-approve`, `/df-changes`, `/df-next`.

## 13. Open items to validate during build

- Task branch naming inside Claude-created worktrees: rename on start vs custom `WorktreeCreate` hook.
- `agent_type` present in hook input for every role subagent and for `--agent pm`, on Windows.
- Nested delegation: whether `SubagentStart` exposes the parent agent, so `events.jsonl` can record the full delegation chain; worktree behaviour when a worktree-isolated subagent spawns another (`baseRef: "head"` should resolve to the parent worktree).
- `.mcp.json` MCP server usable from worktree-isolated subagents, together with per-role MCP tool allowlists.
- Whether installed `.claude/skills` are committed (proposed: yes, for reproducibility) and how the `skills:` preload resolves them.
- `targets.dev.variables` defined in the included `resources/deltaforce.variables.yml` being merged by `bundle validate` (doctor reports it as a warning).
- ai-dev-kit MCP server maintenance is best-effort upstream: pin the ref and keep a fallback to the Databricks CLI for critical operations (deploy, run).
