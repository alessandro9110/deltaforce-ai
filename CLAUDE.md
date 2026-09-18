# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

DeltaForce AI is a **framework**, not an application: an installable Claude Code setup that gives a *target project repo* a team of Databricks-specialized agents (PM, Solution Architect, Business Analyst, Data Engineer, Data Analyst, Data Scientist, AI Engineer, QA Engineer, DevOps Engineer; the human user is the PO). It is installed into target repos with `install.sh` from GitHub.

Current status: **installer, configuration, agents, skills, PO commands, guardrail/audit hooks, existing-project support, CI/CD on the client's templates (project pipelines in `.devops/`) and the local monitor implemented**. The source of truth is:

- `docs/design.md` — architecture, process, conventions, open items
- `docs/roadmap.md` — milestones M0–M6 with exit criteria
- `README.md` — end-user installation guide; update it whenever installer questions, options, generated files or doctor checks change

Read `docs/design.md` before changing anything structural. If an implementation choice diverges from it, update the design doc in the same change.

## Build, lint, test

All commands from the repo root in Git Bash. `UV_LINK_MODE=copy` is required because the repo lives in OneDrive (uv hardlinks fail with os error 396).

```bash
# Python unit tests (config, schema, generation)
UV_LINK_MODE=copy uv run --no-project --python 3.11 --with pytest --with pyyaml --with jsonschema pytest tests -q
# Single test
UV_LINK_MODE=copy uv run --no-project --python 3.11 --with pytest --with pyyaml --with jsonschema pytest tests/test_generate.py::test_medallion_schemas_are_distinct -q
# Shell syntax check
for f in install.sh lib/*.sh; do bash -n "$f"; done
# Run the installer against a sandbox git repo (never this repo)
bash install.sh --target /path/to/sandbox-repo            # add --dry-run to stop after the plan
bash install.sh --target /path/to/sandbox-repo --doctor   # checks only
```

End users never clone this repo by hand and never create a folder: one line in the IDE terminal downloads the installer from the public repository — `irm <raw>/install.ps1 | iex` (PowerShell) or `curl -fsSL <raw>/install.sh | bash` (Git Bash) — and it clones the framework into the target's `.deltaforce/framework` and runs the guided installer (see README). `install.ps1` only finds the bash of Git for Windows and runs `install.sh`, which self-bootstraps and self-updates (`DF_REPO_URL`, `DF_REF`); run from a regular checkout (like this one, with `--target`) it does neither. Keep the installer the single install path — guided, interactive, one line.

Installer layout: `install.sh` orchestrates; `lib/*.sh` hold the steps (prompts in `common.sh` read `/dev/tty`); `lib/py/dfcli.py` is the Python helper the scripts call through the project-local uv (`df_py`) for config, generation and the doctor; `lib/data/versions.env` pins every downloaded version; every role is defined by its agent template `templates/claude/agents/<role>.md`, in the Claude Code subagent format (frontmatter `name`, `description`, `tools`, `model`, `skills` — the preloaded DeltaForce skills —, `isolation`, `color`, then the prompt), plus `lib/data/roles.yaml` for what the installer adds (Databricks MCP tools, production reads, delegates, Databricks skills, Hugging Face skills — installed from the latest `huggingface/skills` main by `df_install_hf_skills`, commit recorded); `config.load_roles()` merges the two, and role ids must match the role enums in `schemas/` (tests enforce it).

The team: `deltaforce/team.py` renders `.claude/agents/<role>.md` from the agent template, adding the `Agent(...)` allowlist, the MCP tools, the configured model and the placeholders `{{delegates}}`, `{{databricks_skills}}`, `{{huggingface_skills}}` (`tools` stays a comma-separated string, `skills` a YAML list, as in the Claude Code docs), and syncs `templates/claude/skills/df-*` into the project. Agent prompts and skills are product code: keep them in English, concise, and consistent with `docs/design.md` (process, gates, git flow, single writer of state). Project state formats are defined by `schemas/{state,feature,event,conventions}.schema.json`; change a format only together with its schema, `df-backlog` and `examples/`. Cross-file rules the schemas cannot express — task ids per feature, dependencies, bugs numbered across the backlog, no `blocker`/`major` bug open at G2 — live in `deltaforce/backlog.py` (`df validate`). `df-backlog` is preloaded by the PM and must stay under 200 lines (tests enforce it). On Windows never delete and recreate a directory in one go (files just written stay locked): sync files instead.

Guardrails: `lib/hooks/deltaforce_hook.py` runs on every matched tool call of every agent, with the MCP venv's Python — keep it standard-library only and fast, and make it fail closed on production. Its rules read `guard-policy.json`, built by `deltaforce/guardrails.py`, which also owns `AI_DEV_KIT_TOOLS`, `PROD_READ_TOOLS`, the static deny rules and the hook registration. Installed files are off-limits to agents (`INSTALLER_FILES`, `INSTALLER_DIRS` in `guardrails.py`) and the installer commits them itself (`df_commit_install` in `lib/project.sh`, whose path list must match `INSTALLED_COMMIT_PATHS`). Environments: deploy grants come only from `config.yaml` (`environments`, confirmed by the PO in the installer); the environments declared in the conventions reach the hook through `.deltaforce/runtime/environments.json` (`deltaforce/environments.py`, written by `df validate` and every install) and can only narrow them. Any new rule needs a case in `tests/test_hook.py` (the full suite takes about a minute because hook tests spawn processes and git). Only the `pre` guard is synchronous; the other hook groups in `HOOK_EVENTS` run with `async: true`.

Monitor (`lib/monitor/`, design §9): `launcher.py` (standard library, imported by the hook and by `df monitor`) starts `server.py` detached with the MCP venv's `pythonw.exe` and opens the page once per session; `server.py` serves `static/` and `/api/snapshot` from `model.py`, which reads `.deltaforce/` and never writes. It needs PyYAML in the MCP venv (installed by `lib/runtime.sh`). The page is plain HTML/CSS/JS with no external requests: charts, rings and the role icons (a person with a badge per role) are inline SVG, fonts are system stacks, and every colour comes from the CSS variables so light and dark both work — new classes must not collide with the existing single-class rules (`.now`, `.decision` did). Try it against a project with `python lib/monitor/server.py --root <project>` (a Python with PyYAML), then open the address printed in `.deltaforce/runtime/monitor.log`. The snapshot is a contract of the page: change `model.py`, `static/app.js` and `tests/test_monitor.py` together. The Claude Code status line sources `statusline.sh`: keep it to bash builtins (no `dirname`, `curl`, `sed`…), because on Windows every extra process adds one to two seconds to each refresh.

## Big picture

- **Two repos**: this framework repo holds `templates/` (copied into target repos), `lib/` (installer modules), `schemas/` (JSON Schemas for config, backlog, events). Everything under `templates/` describes the *target* repo, not this one.
- **Orchestration**: PM is the main session (`claude --agent pm`); every other role is a subagent in `.claude/agents/`. Subagents may spawn subagents (depth configurable, default 3) within per-role `Agent(...)` allowlists; DevOps never delegates and the PM stays the only backlog writer. Agent teams are deliberately out of the MVP (reasons in design §6).
- **Process**: kickoff → design → PO gate G1 (design + feature list) → one feature at a time (parallel devs in git worktrees → DevOps integrates and deploys dev → QA) → PO gate G2 per feature → merge to dev branch. Humans open the PR to `main`; prod only through CI/CD.
- **Databricks tooling**: skills from `databricks aitools` (official `databricks/databricks-agent-skills`); execution tools from the `databricks-solutions/ai-dev-kit` MCP server at a pinned ref. The skills inside ai-dev-kit itself are deprecated — don't reference them.
- **State contract**: the target repo's `.deltaforce/` (backlog markdown with YAML frontmatter, `events.jsonl`, `audit.jsonl`) is a stable contract consumed by a future monitoring app. Change it only together with `schemas/`.

## Conventions

- Keep track of what exists and what is left: every change that adds, completes or defers something updates the *Status* checklist at the top of `docs/roadmap.md`, and `README.md` and this file when behaviour or layout change — in the same commit.
- All repo artifacts — agent prompts, templates, docs, code comments — in English. Discussion with the maintainer happens in Italian.
- The team works on Windows: `install.sh` must run under Git Bash; hooks are Python run via `uv run` (no bash/PowerShell-only hooks). Account for Windows venv paths (`.venv\Scripts\python.exe`).
- Templates must never hardcode catalog, schema, table or endpoint names — always DABs variables (`${var.catalog}`, `${var.schema_gold}`, ...). Medallion (bronze/silver/gold) applies to DE, analytics, ML and GenAI.
- Git rules baked into templates: never push to `main`; work lands in the PO-provided dev branch; commit trailers `DeltaForce-Role` and `DeltaForce-Task`.
- When referencing Claude Code features (subagent frontmatter, hooks, worktrees, agent teams) or Databricks CLI flags, verify against current docs — both evolve quickly.
