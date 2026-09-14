---
name: df-kickoff
description: Start a DeltaForce project — check readiness, collect the Product Owner's request, known tables and client conventions, record them and start discovery and design.
disable-model-invocation: true
argument-hint: "[what the team should build]"
allowed-tools: Bash(bash .deltaforce/bin/df *) Bash(git status *) Bash(git switch *) Bash(git add *) Bash(git commit *)
---

# DeltaForce kickoff

You are the PM. Talk to the PO in their language; write files in English.

## 1. Check that the project can start

1. Read `.deltaforce/status.json`. If it is missing or `"ready"` is not `true`, stop. Tell the PO DeltaForce is not ready, list the failed checks (title and detail), and give the re-check command for the VS Code terminal:
   - PowerShell: `& "$env:ProgramFiles\Git\bin\bash.exe" -c 'bash .deltaforce/framework/install.sh --doctor'`
   - Git Bash: `bash .deltaforce/framework/install.sh --doctor`
2. If `.deltaforce/state.yaml` exists, the project already started: show the status as `/df-status` does and stop. Never overwrite state, backlog or requirements.
3. Run `git status`. If files installed by DeltaForce (`.claude/`, `CLAUDE.md`, `.gitignore`, `databricks.yml`, `resources/deltaforce.variables.yml`, `.deltaforce/config.yaml`) are not committed, stop and ask the PO to re-run the installer and accept its commit: agents cannot commit them. If the main checkout is not on the dev branch from `.deltaforce/config.yaml` and the working tree is clean, `git switch <dev_branch>`; if it is not clean, ask the PO how to proceed.

## 2. Collect the request

1. If `$ARGUMENTS` is not empty, that is the request. Otherwise ask: *What should the team build?* and let the PO answer freely.
2. Ask only what is still missing to start, in one round of at most four questions (use AskUserQuestion when there are clear options):
   - the business goal and the expected benefit for the client — why build it now, what improves (revenue, cost, time, risk, decisions) and how success will be measured — and who will use the result;
   - the data sources — already in Databricks (catalogs, schemas, tables, volumes), files to upload, external systems;
   - the expected outputs — tables, dashboards, ML models, GenAI assistants or agents, apps;
   - constraints — deadlines, sensitive data, performance, cost.
3. Ask whether the PO already has names for the tables to create:
   - **No, the team proposes them** (default) — the Solution Architect proposes names at G1;
   - **Yes** — collect layer, table name and meaning for each.

## 3. Client conventions

Ask how this client organizes Databricks projects, with these options:

- **DeltaForce defaults** — recommended when unsure; they can be changed at any time with `/df-conventions`.
- **Define them now** — ask: the bundle deploy folder (e.g. `/Workspace/Shared/<project>`), the prefix for job and pipeline names, mandatory tags, Python files or notebooks, any other rule in free text.
- **Later** — keep the defaults for now.
- **From an existing repository or document** — ask for the path or link, delegate to `solution-architect` to extract the conventions (read-only), show the result to the PO and confirm.

Update `.deltaforce/conventions.yaml`: set `source` (`defaults`, `po` or `derived` with `source_reference`) and only the values the PO gave; everything else stays as it is.

## 4. Record

1. Write `.deltaforce/requirements/request.md`:

   ```markdown
   # Request

   ## In the PO's words
   > <the request, verbatim>

   ## Summary
   ## Business goal and expected value
   ## How success is measured
   ## Users
   ## Data sources
   ## Expected outputs
   ## Constraints
   ## Tables provided by the PO
   | Layer | Table | Meaning |
   (or: None — the team proposes names at G1)

   ## Open questions
   ## Change requests
   ```

2. Write `.deltaforce/state.yaml` with `phase: discovery`, the dev branch, `active_features: []`, `g1: {status: pending, at: null, notes: ""}`, `next_steps` (the Business Analyst's Functional Analysis and the Solution Architect's technical discovery, in parallel), `last_update` (kickoff completed) and the current UTC time (format in `df-backlog`).
3. Log `kickoff_completed` (data: conventions source) and `phase_changed` (to `discovery`) with `bash .deltaforce/bin/df event ...`, then `bash .deltaforce/bin/df validate`.
4. Commit on the dev branch what the kickoff produced — specialists work in git worktrees, which contain only committed files: `.deltaforce/conventions.yaml`, `.deltaforce/state.yaml`, `.deltaforce/events.jsonl`, `.deltaforce/requirements/`. Message `docs(kickoff): record request and conventions` with the trailers `DeltaForce-Role: pm` and `DeltaForce-Task: kickoff`. Never add files that `.gitignore` excludes.

## 5. Start discovery

Tell the PO in two or three lines what happens now — requirements, design, feature list, then their review at G1 — and that you will ask only if something needs them. Then continue immediately with Phase 1 of your process.
