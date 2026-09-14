# DeltaForce AI — Roadmap

Each milestone ends with a demo against a real Databricks dev workspace. See [design.md](design.md) for the architecture.

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

**Status (2026-09-14)**: all nine agents, the five process skills and the PO commands (`/df-kickoff`, `/df-status`, `/df-approve`, `/df-changes`, `/df-conventions`) are implemented and installed by the installer, with schemas and `df validate` / `df event`. Parallel delivery of independent features uses a local integration branch. Pending: hooks (guardrails, audit) and the end-to-end run in the sandbox.

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

## M6 — Hardening

- Per-role service principals with UC grants (at least DevOps).
- `--update` with manifest-based merge; `--uninstall`.
- Opt-in agent teams experiment for Phase 1 design review.
- macOS/Linux installer support.
