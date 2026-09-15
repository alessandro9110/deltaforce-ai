# DeltaForce AI — Roadmap

Each milestone ends with a demo against a real Databricks dev workspace. See [design.md](design.md) for the architecture.

## Status — what exists and what is left

Updated with every change that adds or completes something. Last update: 2026-09-14.

### Done

- [x] Guided, project-scoped installer started with one command from the IDE terminal; self-bootstrap and update; readiness checks gate `/df-kickoff`
- [x] Project configuration and JSON Schemas (config, conventions, state, feature, event)
- [x] Nine agents rendered from the role catalog, five process skills, PO commands (`/df-kickoff`, `/df-status`, `/df-approve`, `/df-changes`, `/df-conventions`)
- [x] Parallel discovery (Business Analyst and Solution Architect) and parallel delivery of independent features through a local integration branch
- [x] Functional Analysis and Architecture as versioned deliverables; business objectives, value and success metrics
- [x] Team documents and state under `.deltaforce/`
- [x] Guardrail and audit hooks; read-only access to a separate production workspace; Databricks resources only through the asset bundle
- [x] Tracking for the board and for resuming work: feature start/completion times, saved task reports, `next_steps` and `last_update`, session and agent activity
- [x] End-to-end install validated on Windows against Databricks Free Edition
- [x] PO sees work in progress before G2 in `.deltaforce/review/` (integration worktree); main checkout never leaves dev; agent worktrees cleaned up at feature close
- [x] Fixes from the first sandbox run: task branch naming, `sys.exit` on serverless, PM checks before answering
- [x] Installed files are off-limits to agents (edits, write commands, commits); the installer commits them; the doctor checks agents and skills are unchanged; conventions changed only by the PM
- [x] Monitor workflow view: handoffs, steps back with causes, deploys and test runs, phase durations, PO involvement (questions and messages counted, never recorded); path of each feature
- [x] Credential backups: `.deltaforce/.databrickscfg.bak` written by the Databricks CLI is deleted by the installer, ignored by git and off-limits to agents like the credentials file
- [x] Existing projects: the kickoff detects them and collects the PO's rules on existing data; as-is analysis (SA technical, BA functional) before requirements and design; design of the change; data rules binding for builders, destructive operations reported, QA regression checks, G2 report sections; the installer does not redefine existing bundle variables
- [x] Monitor (M5 base): local read-only page in the system browser — now and waiting for the PO, team with current work, feature board with dates, clickable features, agents and documents; starts with the session, opens on the team's first work, stops by itself; clickable link, phase and what waits for the PO in the Claude Code status line (no tokens); `df monitor`

### Next

- [ ] First MVP run in the sandbox (kickoff → G1 → parallel features → G2) and fixes for what it reveals
- [ ] Monitor: first live run with the new hooks in the sandbox (re-install with Claude Code closed), then timeline, deploys and tests, audit and guardrail views
- [ ] CI/CD templates (M4): Azure DevOps, then GitHub Actions
- [ ] Installer warning when a Claude Code session is open on the project

### Later

- [ ] Per-role service principals with Unity Catalog grants
- [ ] `--uninstall`
- [ ] Opt-in agent teams for design review
- [ ] macOS and Linux installer validation
- [ ] Repository visibility and a `curl` bootstrap

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
