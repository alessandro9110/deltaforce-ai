# DeltaForce AI — Roadmap

Each milestone ends with a demo against a real Databricks dev workspace. See [design.md](design.md) for the architecture.

## Status — what exists and what is left

Updated with every change that adds or completes something. Last update: 2026-09-19.

Open work is tracked as [GitHub issues](https://github.com/alessandro9110/deltaforce-ai/issues), grouped by the three [milestones](https://github.com/alessandro9110/deltaforce-ai/milestones) below; this page stays the overview of what exists. Every change ships with its tests, and the CI workflow is ready in `docs/ci/tests.yml`, waiting for the `workflow` scope on the repository token ([issue #19](https://github.com/alessandro9110/deltaforce-ai/issues/19)).

### Done

- [x] Fix from the M3 run (2026-09-19): the PM wrote the timestamps of `state.yaml` and of the feature files from memory - the sandbox had the state updated `2026-09-20T02:15:00Z` while the clock said `2026-09-19T08:41Z`, and every feature `started` and `completed` was ahead of now, so the monitor showed work that had not happened yet. `df validate` now rejects any timestamp more than five minutes ahead of the clock, wherever it sits in state, features, bugs or events, and `df-backlog` says to read the clock (`date -u`), never to guess it
- [x] The repository documents itself: the Business Analyst owns the root `README.md` — what the project delivers and for whom, then one section per component in functional language (what a dashboard shows and for which decision, which questions the Genie space answers and which it refuses, what a job produces through which medallion layers and on which trigger, what a model predicts and how good it is against the obvious alternative, what an app is for) — and a short `README.md` in every folder under `src/` and in `.devops/`, saying what those resources are for, how they were built and where their output lands. Contract in the new preloaded skill `df-readme`: the README is created at the feature breakdown with the components marked *Planned*, each feature carries a documentation task on its own task branch (delegated when the build tasks are ready, integrated with them, so the PO reads it at G2 with the code), the handover closes it; written from the task reports and not by re-reading the code, nothing in it ages badly, and an existing project's README is added to, never rewritten. The Business Analyst gained `Bash` and `df-git-flow` to work on a branch like every other role
- [x] What the M3 run taught, in the framework: a task is `ready_for_integration` only when its code has run once in the context it will run in (`df-testing` has the ladder from a local test to a one-off `databricks jobs submit`, and probe jobs keep their checks independent); `df-engineering-standards` split into a ~100-line SKILL.md plus `references/` (code and layout, existing projects, production data, and a **known-failures** table fed by the runs: `__file__` in a job task, MLflow experiment, Apps source deploy, Lakeview `displayName`, Genie `data_sources`, `execute_code` without a REPL channel); `df-bi` corrected on the Genie space format with `references/genie-space.md` and a new §0 on studying the client's data first; `df-pipelines` for the Data Engineer (ingestion, CDC and SCD, quarantine instead of silent drops, idempotency, late data); point-in-time features, inference tables and drift in `df-mlops`, AI Gateway guardrails and a red-team slice in `df-aiops`, quality regression after G2 in `df-testing`; LangChain, LangGraph and Deep Agents skills installed for the AI Engineer through the same mechanism as the Hugging Face ones; monitor **audit view** (what was blocked, with reason and command, and production reads per role) and token attribution through the recorded delegations; installer: table prefixes configurable in a single schema, an existing project's own bundle values as the defaults with a doctor check for disagreement, and a one-item list answered by Enter
- [x] Monitor redesign, from the mockup agreed on 2026-09-17: the overview reads as a control room — phase stepper with the time worked, key figures (features, tests, deploys, bugs, steps back, your involvement), delivery chart where nights and pauses shrink to a dashed link, features as a list with task rings, team graph around the PM (line width the work passed, circle size the time worked); every role is drawn as a person with the badge of what it does, and the feature panel opens on its path with times, three figures and your decision. Time worked leaves out stretches of 30 minutes or more without activity — phases and features show it first, the time on the clock second
- [x] Bugs linked to features: a defect found during development — by QA, DevOps, a builder in another feature's work, or the PO at G2 — is recorded in the feature where it lives (a `done` one too), numbered across the backlog (`B-001`), with severity, who found it, during what and in which feature, evidence and fix tasks; QA verifies every fix; no blocker or major bug open at G2 (`df validate`); open minor bugs decided by the PO; events `bug_opened`/`bug_status_changed`; monitor chips, bug table per feature, timeline markers and a workflow tile
- [x] Every change is tested and tracked: structural tests for skills and agent templates (own name, trigger description, PO commands the model cannot invoke, preloaded skills under 200 lines, every `df-*` reference resolvable, the generated `CLAUDE.md` block listing every PO command), a test for the generated bundle skeleton, a GitHub Actions workflow ready to enable, and the open work as GitHub issues under three milestones
- [x] BI as a discipline of the Data Analyst (no separate role — dashboards, metric views and Genie already belong to it, and Databricks assigns Genie curation to the analyst): `df-bi` with the *Analytics* section of the Architecture, one definition per KPI in a metric view, gold modelled for consumption, dashboard design, Genie space curation (scope, instructions, examples, descriptions as the semantic layer, feedback loop) and an expected-question set that QA recomputes independently; a Genie space is a bundle resource like any other (`resources/<slug>.genie_space.yml` plus the `.geniespace.json` definition in git, imported or kept in sync with `bundle generate genie-space`, never bound to a hand-made space), and a new project's `databricks.yml` declares `engine: direct`, which those resources require
- [x] Databricks discipline in the team's standards: descriptions mandatory on every object the team creates (schemas, tables, columns, volumes, models, indexes, endpoints, jobs, pipelines, dashboards), checked by QA as a data quality test; every experiment and evaluation is an MLflow run, no metric reported from outside MLflow; schemas beyond the configured ones — for instance one for models, feature tables and predictions — proposed in the Architecture and confirmed by the PO at G1, unless the kickoff already placed those objects
- [x] One-line install from the public repository, nothing created by hand: `irm <raw>/install.ps1 | iex` in PowerShell (`install.ps1` finds the bash of Git for Windows, downloads `install.sh` and runs it, options in `$env:DF_INSTALL_ARGS`) or `curl -fsSL <raw>/install.sh | bash` in Git Bash; `install.sh` clones the framework into `.deltaforce/framework` and continues from there
- [x] ML and GenAI builders as experts: `df-mlops` and `df-aiops` — ML or AI operations strategy in the Architecture designed with the Data Scientist and the AI Engineer, realistic samples from dev, splits without leakage, baselines, model challenges and leaderboards, champion and challenger aliases, evaluation datasets, Prompt Registry, tracing, AI Gateway, monitoring and retraining; QA recomputes results independently; official Hugging Face skills (latest `main`, commit recorded) for the Data Scientist and the AI Engineer, with Hub publishing and Hugging Face Jobs blocked by the hook; Agent Bricks created and updated on dev by the AI Engineer, deletes by a person; `databricks-execution-compute`, `databricks-model-serving` (Data Scientist) and `databricks-unstructured-pdf-generation` added
- [x] Client environments: nothing assumed — the PO declares environments at kickoff (purpose, workspace, catalogs, bundle target, deploy/read/none, deployed by team or CI/CD, data rules); declarations narrow access at once, deploy access beyond dev only after the PO confirms each environment in the installer; SA designs targets and promotion, CI/CD deploys the `cicd` environments; production never deployed by the team
- [x] QA reads dashboards with the MCP tool (`manage_dashboard`, read actions) instead of the CLI — sandbox audit: 63% of Databricks calls through MCP, the CLI used for bundle commands and for reads without an MCP tool
- [x] Agent templates in the Claude Code subagent format: frontmatter (`name`, `description`, `tools`, `model`, `skills`, `isolation`, `color`) and prompt in `templates/claude/agents/<role>.md`; the installer adds delegates, MCP tools and the configured model
- [x] Monitor test evidence in the feature panel: tests per acceptance criterion with passed/failed counts, regression checks and destructive operations, from the review report
- [x] Changes after delivery: `/df-changes` on a done feature creates a change feature (`change_of`) with its own tasks and G2; the original keeps its history; monitor links both and counts them. Status line second row with the PO commands, led by the one to use now
- [x] Monitor backlog: one-line description on feature cards, Backlog view with descriptions, dependencies, acceptance criteria and task tables, task panel (what was asked, who worked on it and when, report), feature panel ordered from what it is to how it went
- [x] Guided, project-scoped installer started with one command from the IDE terminal; self-bootstrap and update; readiness checks gate `/df-kickoff`
- [x] Project configuration and JSON Schemas (config, conventions, state, feature, event)
- [x] Nine agents rendered from the role catalog, five process skills, PO commands (`/df-prepare`, `/df-kickoff`, `/df-status`, `/df-approve`, `/df-changes`, `/df-conventions`)
- [x] Parallel discovery (Business Analyst and Solution Architect) and parallel delivery of independent features through a local integration branch
- [x] Functional Analysis and Architecture as versioned deliverables; business objectives, value and success metrics
- [x] Team documents and state under `.deltaforce/`
- [x] Guardrail and audit hooks; read-only access to a separate production workspace; Databricks resources only through the asset bundle
- [x] Tracking for the board and for resuming work: feature start/completion times, saved task reports, `next_steps` and `last_update`, session and agent activity
- [x] End-to-end install validated on Windows against Databricks Free Edition
- [x] PO sees work in progress before G2 in `.deltaforce/review/` (integration worktree); main checkout never leaves dev; agent worktrees cleaned up at feature close
- [x] Fixes from the first sandbox run: task branch naming, `sys.exit` on serverless, PM checks before answering
- [x] Token use, from the sandbox measurements: PM suggests `/clear` at clean points (after G1, after an approved feature is merged); `df events` batches events and validation; DevOps never polls runs and chains git commands; leaner skill preloads (design §6 *Token use*)
- [x] Fixes from the second sandbox run: the installed-files guardrail looks only at what a command writes (redirection targets, file arguments of write commands), so running the project CLI with `2>&1` is no longer blocked; agents never fall back to another Databricks CLI; the doctor self-test covers it
- [x] Installed files are off-limits to agents (edits, write commands, commits); the installer commits them; the doctor checks agents and skills are unchanged; conventions changed only by the PM
- [x] Monitor project summary (description from the request, one sentence on what the team is doing); the installer stops a running monitor before rebuilding the runtime (`df monitor --stop`)
- [x] Monitor timeline: one lane per role with a bar per run (who asked, task, duration, result), nested delegations, markers for decisions, questions, deploys, tests and steps back; README introduction on what DeltaForce does, where it works, what it can and cannot do
- [x] Monitor workflow view: handoffs, steps back with causes, deploys and test runs, phase durations, PO involvement (questions and messages counted, never recorded); path of each feature
- [x] Credential backups: `.deltaforce/.databrickscfg.bak` written by the Databricks CLI is deleted by the installer, ignored by git and off-limits to agents like the credentials file
- [x] Existing projects: the kickoff detects them and collects the PO's rules on existing data; as-is analysis (SA technical, BA functional) before requirements and design; design of the change; data rules binding for builders, destructive operations reported, QA regression checks, G2 report sections; the installer does not redefine existing bundle variables
- [x] Monitor (M5 base): local read-only page in the system browser — now and waiting for the PO, team with current work, feature board with dates, clickable features, agents and documents; starts with the session, opens on the team's first work, stops by itself; clickable link, phase and what waits for the PO in the Claude Code status line (no tokens); `df monitor`

### Next — phase 1: stabilize what exists

- [x] Sandbox MVP complete (2026-09-15): four features — NYC taxi bronze/silver, gold KPIs, AI/BI dashboard, TPC-H revenue — delivered through G1 and four G2, 34 tests passed, handover written; 37 handoffs, 2 steps back, 7 deploys (1 blocked by a guardrail bug, fixed)
- [x] Run on the latest version (change feature F-005 to the delivered dashboard): change feature, `/clear` suggestion, `df events`, no polling, status line and monitor views confirmed live; PM context peak 159 k (MVP up to 277 k), PM share 38% (MVP up to 48%), DevOps 27 calls (MVP up to 130)
- [x] Lighter document updates for change features: only the affected sections of the Functional Analysis and the Architecture, in place; handover updated with the change feature only (the Solution Architect took 25% of the F-005 session)
- [x] Installer asks to close Claude Code when its MCP server or hooks run from the project runtime (and stops the monitor by itself)
- [x] Fix from the update run (2026-09-15): a status line refresh left behind by a closed session kept the installer asking to close Claude Code — the status line no longer counts, the warning lists the processes found (id and name) with how to end them; the monitor no longer logs clients that gave up; *Waiting for you* in the monitor is a compact notification (count and short titles) that expands to the full requests; README section on all the skills
- [x] Configurable bundle target name (`targets.dev.bundle_target`, default `dev`, chosen from the project's own bundle when it has no `dev` target) for guardrails, generated files, `CLAUDE.md`, agents and doctor
- [x] Fix from the M3 run (2026-09-16): after a PC restart the monitor kept showing the agents of the dead session as working for three hours — an agent that never stopped is now *interrupted* when its session ended or a new session started after its last activity
- [ ] Validate on a real existing project (its own bundle variables, target names and conventions)

### Next — phase 2: complete the cycle to production

- [x] CI/CD in the framework (M4): kickoff records the client's templates (`cicd` in the conventions); CI/CD feature in the breakdown with its G2; DevOps builds on the templates (reference, not copy) with the standard Azure DevOps and GitHub Actions pipelines as fallback; G2 report lists what to configure. Pipeline files in `.devops/` at the repository root. Pending: a live run on a project with real client templates
- [ ] ML and GenAI MVP with the Data Scientist and the AI Engineer (M3), within Free Edition limits — next: a sandbox run with an ML feature (NYC taxi tip prediction: baseline and model challenge) and a GenAI feature (bakehouse reviews: a Hugging Face model, `ai_classify` and an LLM challenged, then RAG with evaluation); Agent Bricks are not available on Free Edition
- [ ] Stronger builders, what is left: `databricks-ai-runtime` (serverless GPU workloads — experimental, needs the separate `air` CLI) once stable, and the Databricks agent framework with MLflow written up in `df-aiops` from a real run. Done: engineering skills for the Data Engineer (`df-pipelines`) and the LangChain, LangGraph and Deep Agents skills, installed project-scoped from the latest `main` with the commit recorded, never through their global install or plugin
- [ ] Builder gaps from the comparison with community data and AI agents (VoltAgent `awesome-claude-code-subagents`, MIT — ideas rewritten, nothing copied): written as practice in `df-pipelines` (CDC and SCD, quarantine instead of silent drops, schema evolution), `df-mlops` (point-in-time feature tables, inference tables, drift), `df-aiops` (AI Gateway guardrails, red-team slice) and `df-testing` (quality regression against the G2 baseline on the same dataset version). What is left is the API detail of each one, to add against current docs after the first run that needs it
- [x] Monitor usage view: tokens per role, feature, phase, session and model from the Claude Code session files of the project (read incrementally, counts only), weighted tokens, PM peak context per session, optional cost from `.deltaforce/pricing.yaml`

### Later — team and client use

- [ ] Team access to environments on other workspaces (a profile and MCP server per workspace, deploys with its profile) — declared today, deployed through CI/CD
- [ ] Several people using DeltaForce on the same repository: state and backlog coordination, who acts as PO
- [ ] Per-role service principals with Unity Catalog grants (at least the DevOps Engineer)
- [ ] GitHub Actions template; macOS and Linux installer validation; `--uninstall`
- [ ] Opt-in agent teams for design review
- [ ] Beyond Databricks: the team is Databricks-focused today; keep roles, process, guardrails and monitor platform-neutral enough to add other data and AI platforms later

## M0 — Foundations

- Framework repo skeleton (layout in design §12), `.gitignore`, license, README.
- JSON Schemas: `config.yaml`, feature frontmatter, event line.
- Template `CLAUDE.md` for target projects.

**Exit**: schemas validated with sample files.

## M1 — Installer MVP (Windows, Git Bash)

- Prerequisite checks with versions; consent-based install via winget; manual fallback.
- Databricks OAuth profile setup and verification.
- `databricks aitools install` at project scope with the role skill union.
- ai-dev-kit MCP server at pinned ref, uv venv, per-machine registration.
- Template copy with manifest; `--dry-run`, `--doctor`, `--yes`.

**Exit**: fresh Windows machine → `install.sh` → `--doctor` all green → Claude Code sees skills and MCP tools.

**Status (2026-09-14)**: implemented. One-command install from the VS Code terminal validated end to end on Windows against a Databricks Free Edition workspace: OAuth, live lists, schema creation, MCP server, 21 skills, generated files, all doctor checks green. Pending: a second machine, and Claude Code actually loading the MCP tools and skills.

## M2 — Core team and guardrails

- Agents: `pm`, `business-analyst`, `solution-architect`, `data-engineer`, `devops-engineer`, `qa-engineer`.
- Commands: `/df-kickoff`, `/df-status`, `/df-approve`, `/df-changes`, `/df-next`.
- Hooks: guard (role policy, git protection, destructive SQL, hardcoded names), audit, events.
- Nested delegation with per-role `Agent(...)` allowlists and configurable spawn depth.
- Git flow: feature branch, worktree task branches, DevOps merge, dev branch push.
- DABs skeleton with parametric variables and medallion layout.

**Exit**: kickoff → G1 → one data engineering feature bronze → silver → gold deployed and run on dev → QA data tests → G2 approved → merged into dev branch.

**Status (2026-09-14)**: all nine agents, the five process skills and the PO commands (`/df-kickoff`, `/df-status`, `/df-approve`, `/df-changes`, `/df-conventions`) are implemented and installed by the installer, with schemas and `df validate` / `df event`. Parallel delivery of independent features uses a local integration branch. Guardrail and audit hooks are implemented, including read-only access to a separate production workspace. Pending: the end-to-end run in the sandbox.

## M3 — Full team: analytics, ML, GenAI

- Agents: `data-analyst`, `data-scientist`, `ai-engineer`.
- ML lifecycle (feature table, MLflow training, UC registration, dev serving) and AI lifecycle (documents, chunking, vector index, agent, MLflow evaluation).
- QA evaluation gates with configurable thresholds; dashboards / metric views / Genie.

**Exit**: one feature per discipline delivered end-to-end with PO validation.

## M4 — CI/CD

- Azure DevOps pipeline template: validate on PR, deploy prod from `main` with service principal, `BUNDLE_VAR_*` injection.
- GitHub Actions template with the same contract.

**Exit**: human PR dev → main triggers a prod deploy of the M2 feature in a test workspace.

## M5 — Monitoring app

- Read-only backend over `.deltaforce/` (backlog, events, audit, reports) and git history; live agent activity from the M2 hooks.
- Views: virtual office (agents, current action, delegations); project board with every feature by status, including the delivered ones with when they started and were completed, cycle time and PO decisions; event timeline; branches.
- **Starts automatically** when the team works: no manual command. The server starts with the Claude Code session, the page opens the first time the team starts working in that session, and the server stops by itself when no session is active.

**Exit**: live view of an M3 run.

**Status (2026-09-14)**: base implemented in `lib/monitor/` (design §9 *Monitor*): header, now and waiting for the PO, team, feature board, side panels for features, agents and documents; automatic start from the hooks, validated on Windows (a server started by an async `SessionStart` hook survives Claude Code) and against the sandbox backlog. Pending: a live run with the new hooks, timeline, deploys and tests, audit, branches.

## M6 — Hardening

- Per-role service principals with UC grants (at least DevOps).
- `--update` with manifest-based merge; `--uninstall`.
- Opt-in agent teams experiment for Phase 1 design review.
- macOS/Linux installer support.
