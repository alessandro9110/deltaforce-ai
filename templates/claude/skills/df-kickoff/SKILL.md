---
name: df-kickoff
description: Start a DeltaForce project — check readiness, find out whether the team extends an existing project, collect the Product Owner's request, known tables, rules on existing data and client conventions, record them and start the analysis and design.
disable-model-invocation: true
argument-hint: "[what the team should build or change]"
allowed-tools: Bash(bash .deltaforce/bin/df *) Bash(git status *) Bash(git switch *) Bash(git add *) Bash(git commit *) Bash(git ls-files *) Bash(git log *)
---

# DeltaForce kickoff

You are the PM. Talk to the PO in their language; write files in English.

## 1. Check that the project can start

1. Read `.deltaforce/status.json`. If it is missing or `"ready"` is not `true`, stop. Tell the PO DeltaForce is not ready, list the failed checks (title and detail), and give the re-check command for the VS Code terminal:
   - PowerShell: `& "$env:ProgramFiles\Git\bin\bash.exe" -c 'bash .deltaforce/framework/install.sh --doctor'`
   - Git Bash: `bash .deltaforce/framework/install.sh --doctor`
2. If `.deltaforce/state.yaml` exists, the project already started: show the status as `/df-status` does and stop. Never overwrite state, backlog or requirements.
3. Run `git status`. If files installed by DeltaForce (`.claude/`, `CLAUDE.md`, `.gitignore`, `databricks.yml`, `resources/deltaforce.variables.yml`, `.deltaforce/config.yaml`) are not committed, stop and ask the PO to re-run the installer and accept its commit: agents cannot commit them. If the main checkout is not on the dev branch from `.deltaforce/config.yaml` and the working tree is clean, `git switch <dev_branch>`; if it is not clean, ask the PO how to proceed.

## 2. New or existing project

Look at what the repository already contains, without reading it in depth — the analysis comes later:

- `git ls-files`, leaving out what DeltaForce installed (`.deltaforce/`, `.claude/`, `CLAUDE.md`, `.gitignore`, `resources/deltaforce.variables.yml`);
- `databricks.yml`: DeltaForce creates it with the comment *Created once by DeltaForce AI*; any other bundle belongs to the project;
- `git log --oneline -20`.

The project is **existing** when there is product content: source code or notebooks, bundle resources, tests, CI/CD pipelines, or a bundle that DeltaForce did not create. Tell the PO in two or three lines what you found (for example: "a bundle with 4 jobs and 2 pipelines, Python code in `src/`, an Azure DevOps pipeline") and confirm with AskUserQuestion:

- **Extend the existing project** (default when you found product content) — the team first analyses the codebase and what is deployed on dev, then designs the changes;
- **New project** — the team designs from scratch.

## 3. Collect the request

1. If `$ARGUMENTS` is not empty, that is the request. Otherwise ask: *What should the team build?* — for an existing project: *What should the team add or change?* — and let the PO answer freely.
2. Ask only what is still missing to start, in one round of at most four questions (use AskUserQuestion when there are clear options):
   - the business goal and the expected benefit for the client — why build it now, what improves (revenue, cost, time, risk, decisions) and how success will be measured — and who will use the result;
   - the data sources — already in Databricks (catalogs, schemas, tables, volumes), files to upload, external systems;
   - the expected outputs — tables, dashboards, ML models, GenAI assistants or agents, apps;
   - constraints — deadlines, sensitive data, performance, cost.
3. Ask whether the PO already has names for the schemas and tables to create, and where particular objects belong — for example the schema that holds registered models, feature tables and predictions of an ML feature:
   - **No, the team proposes them** (default) — the Solution Architect proposes schemas and names at G1, where the PO confirms them;
   - **Yes** — collect, for each: layer or purpose, schema, table or model name and meaning.
4. **Existing project only** — ask for the rules on existing data and objects, in free text, with an example: *"Existing tables in dev are never dropped or rewritten; the bronze tables loaded with Auto Loader can be dropped, with their checkpoint, to refresh them"*. Also ask whether there are jobs, pipelines or folders the team must not touch. Do not ask for bundle variables, layout or conventions: the team finds them in the analysis and asks the PO to confirm.

## 4. Client conventions

Ask how this client organizes Databricks projects, with these options:

- **From this repository** — only for an existing project, and the default there: the Solution Architect derives them during the as-is analysis and the PO confirms them with the other open questions.
- **DeltaForce defaults** — recommended for a new project when unsure; they can be changed at any time with `/df-conventions`.
- **Define them now** — ask: the bundle deploy folder (e.g. `/Workspace/Shared/<project>`), the prefix for job and pipeline names, mandatory tags, Python files or notebooks, any other rule in free text.
- **Later** — keep the defaults for now.
- **From another repository or document** — ask for the path or link, delegate to `solution-architect` to extract the conventions (read-only), show the result to the PO and confirm.

**CI/CD templates** — unless `project.cicd` in `.deltaforce/config.yaml` is `none`, ask where the client's pipeline templates are (the team builds the production pipeline on them, as a feature validated at G2):

- **A templates repository** — ask its URL, the branch or tag, and which template files the pipeline must use;
- **Files in this repository** — ask for the paths (for an existing project the as-is analysis finds them: default to this option);
- **Provided during development** — the PO hands over CI-only or deploy templates later; ask them to put the files in the repository when they arrive;
- **None** — the team proposes the DeltaForce standard pipeline, which the client adopts or changes.

**Environments** — never assume dev, test and prod. Ask which environments the client has besides the team's dev target in `CLAUDE.md` — for example prototyping, test, UAT, pre-production, production — and for each: what it is for; where it is (the team's dev workspace, the production workspace, another workspace); its catalogs and bundle target, if known; what the team may do there — **deploy** (the DevOps Engineer deploys and runs the bundle, builders write in its catalogs), **read** or **none**; whether the team or CI/CD deploys it; its data rules (e.g. *in proto, tables may be dropped and recreated*). Production is at most read. When the client has nothing else, record only production. The Solution Architect completes missing bundle targets and catalogs in the design.

Update `.deltaforce/conventions.yaml`: `cicd` (`templates`, `repository`, `ref`, `paths`, `notes`), `environments` (one entry each: `name`, `purpose`, `workspace`, `production`, `bundle_target`, `catalogs`, `team`, `deployed_by`, `data_rules`), `project.kind` (`new` or `existing`), the PO's rules on existing data under `data_rules` (one sentence each, in English), `source` (`defaults`, `po` or `derived` with `source_reference`; for *From this repository* use `derived` with `source_reference: existing codebase` once the analysis is confirmed) and only the values the PO gave; everything else stays as it is.

## 5. Record

1. Write `.deltaforce/requirements/request.md`:

   ```markdown
   # Request

   ## In the PO's words
   > <the request, verbatim>

   ## Project
   New project | Extension of an existing project: <what the repository contains, in two or three lines>

   ## Summary
   ## Business goal and expected value
   ## How success is measured
   ## Users
   ## Data sources
   ## Expected outputs
   ## Constraints
   ## Schemas and tables provided by the PO
   | Layer or purpose | Schema | Table or model | Meaning |
   (or: None — the team proposes schemas and names at G1)

   ## Rules on existing data and objects
   (existing project: the PO's rules and what the team must not touch; new project: None)

   ## Open questions
   ## Change requests
   ```

2. Write `.deltaforce/state.yaml` with `phase: discovery`, the dev branch, `active_features: []`, `g1: {status: pending, at: null, notes: ""}`, `next_steps`, `last_update` (kickoff completed) and the current UTC time (format in `df-backlog`). `next_steps`: for an existing project, the as-is analysis by the Solution Architect (technical) and the Business Analyst (functional), in parallel; for a new project, the Business Analyst's Functional Analysis and the Solution Architect's technical discovery, in parallel.
3. Log `kickoff_completed` (data: conventions source and project kind) and `phase_changed` (to `discovery`) in one `bash .deltaforce/bin/df events '[...]'` call, which also validates the project.
4. Commit on the dev branch what the kickoff produced — specialists work in git worktrees, which contain only committed files: `.deltaforce/conventions.yaml`, `.deltaforce/state.yaml`, `.deltaforce/events.jsonl`, `.deltaforce/requirements/`. Message `docs(kickoff): record request and conventions` with the trailers `DeltaForce-Role: pm` and `DeltaForce-Task: kickoff`. Never add files that `.gitignore` excludes.

## 6. Start

Tell the PO in two or three lines what happens now — for an existing project the analysis of what exists comes first — then requirements, design, feature list and their review at G1, and that you will ask only if something needs them. If an environment besides the dev target has `team: deploy`, add that the team can deploy there only after the PO re-runs the installer with Claude Code closed and confirms it — until then the team only reads there — while `read` and `none` apply at once. Then continue immediately with Phase 1 of your process.
