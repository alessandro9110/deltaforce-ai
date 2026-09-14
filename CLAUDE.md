# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

DeltaForce AI is a **framework**, not an application: an installable Claude Code setup that gives a *target project repo* a team of Databricks-specialized agents (PM, Solution Architect, Business Analyst, Data Engineer, Data Analyst, Data Scientist, AI Engineer, QA Engineer, DevOps Engineer; the human user is the PO). It is installed into target repos with `install.sh` from GitHub.

Current status: **design phase, no code yet**. The source of truth is:

- `docs/design.md` — architecture, process, conventions, open items
- `docs/roadmap.md` — milestones M0–M6 with exit criteria

Read `docs/design.md` before changing anything structural. If an implementation choice diverges from it, update the design doc in the same change.

## Build, lint, test

No tooling exists yet (planned in roadmap M0/M1: installer tests and pytest for hooks). Update this section when it lands.

## Big picture

- **Two repos**: this framework repo holds `templates/` (copied into target repos), `lib/` (installer modules), `schemas/` (JSON Schemas for config, backlog, events). Everything under `templates/` describes the *target* repo, not this one.
- **Orchestration**: PM is the main session (`claude --agent pm`); every other role is a subagent in `.claude/agents/`. Subagents may spawn subagents (depth configurable, default 3) within per-role `Agent(...)` allowlists; DevOps never delegates and the PM stays the only backlog writer. Agent teams are deliberately out of the MVP (reasons in design §6).
- **Process**: kickoff → design → PO gate G1 (design + feature list) → one feature at a time (parallel devs in git worktrees → DevOps integrates and deploys dev → QA) → PO gate G2 per feature → merge to dev branch. Humans open the PR to `main`; prod only through CI/CD.
- **Databricks tooling**: skills from `databricks aitools` (official `databricks/databricks-agent-skills`); execution tools from the `databricks-solutions/ai-dev-kit` MCP server at a pinned ref. The skills inside ai-dev-kit itself are deprecated — don't reference them.
- **State contract**: the target repo's `.deltaforce/` (backlog markdown with YAML frontmatter, `events.jsonl`, `audit.jsonl`) is a stable contract consumed by a future monitoring app. Change it only together with `schemas/`.

## Conventions

- All repo artifacts — agent prompts, templates, docs, code comments — in English. Discussion with the maintainer happens in Italian.
- The team works on Windows: `install.sh` must run under Git Bash; hooks are Python run via `uv run` (no bash/PowerShell-only hooks). Account for Windows venv paths (`.venv\Scripts\python.exe`).
- Templates must never hardcode catalog, schema, table or endpoint names — always DABs variables (`${var.catalog}`, `${var.schema_gold}`, ...). Medallion (bronze/silver/gold) applies to DE, analytics, ML and GenAI.
- Git rules baked into templates: never push to `main`; work lands in the PO-provided dev branch; commit trailers `DeltaForce-Role` and `DeltaForce-Task`.
- When referencing Claude Code features (subagent frontmatter, hooks, worktrees, agent teams) or Databricks CLI flags, verify against current docs — both evolve quickly.
