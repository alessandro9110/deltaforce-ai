---
name: df-prepare
description: What the Product Owner should bring to the kickoff — the request and its business goal, data sources, expected outputs, constraints, schema and table names, rules on existing data, client conventions, CI/CD templates and environments — with the boundaries the team works within. Read-only.
disable-model-invocation: true
argument-hint: ""
allowed-tools: Read, Glob
---

# Prepare the kickoff

You are the PM. **Answer in the language of this conversation** — the command takes no arguments, so the language of the PO's previous messages is the only signal; when there is none, ask in one line. This command only informs: read files, write nothing.

## 1. Where the project stands

Read `.deltaforce/state.yaml`. If it exists, the project already started: say so in one line, point to `/df-status` for where it stands and to `/df-changes` for a change to the request, and stop — unless the PO explicitly asks to see the kickoff topics anyway.

Read `.deltaforce/status.json`. If `ready` is not `true`, say DeltaForce is not ready yet, list the failed checks briefly and give the re-check command (`bash .deltaforce/framework/install.sh --doctor`, from PowerShell wrapped in `& "$env:ProgramFiles\Git\bin\bash.exe" -c '…'`). The PO can still prepare: continue with the rest.

## 2. What to bring

Read the *DeltaForce project context* block in `CLAUDE.md`, `.deltaforce/config.yaml` and `.deltaforce/conventions.yaml`, and look at what the repository contains (`Glob` on `src/`, `resources/`, `databricks.yml`) to tell the PO whether the team will extend an existing project or start from scratch.

Then show a short table — topic · what the PM will ask · what is already known — filling the last column from the files above so the PO only prepares what is missing:

| Topic | What the PM will ask |
| --- | --- |
| Request | What to build or change, why now, what improves (revenue, cost, time, risk, decisions), how success is measured, who uses the result |
| Data | Sources: catalogs, schemas, tables and volumes already on Databricks, files to upload, external systems |
| Outputs | Tables, dashboards, ML models, GenAI assistants or agents, apps |
| Constraints | Deadlines, sensitive data, performance, cost |
| Names | Schema and table names the PO already has in mind, including where particular objects belong — for example the schema holding registered models, feature tables and predictions. Otherwise the team proposes them and the PO confirms at G1 |
| Existing data | Only when the team extends an existing project: what may be dropped or rewritten and what may not, and the jobs, pipelines or folders the team must not touch |
| Conventions | How the client organizes Databricks projects: deploy folder, naming prefixes, mandatory tags, notebooks or Python files — or the DeltaForce defaults, changeable later with `/df-conventions` |
| CI/CD | The provider is already chosen: read `project.cicd` from `.deltaforce/config.yaml` and name it (`azure-devops`, `github-actions` or `none`). What to bring is where the client's pipeline templates are — a repository (URL and branch), files in this repository, provided later, or none — which the kickoff records in `cicd` of `.deltaforce/conventions.yaml`. An empty `cicd` there means the templates are not recorded yet, not that there is no CI/CD |
| Environments | Every environment besides the dev target — prototyping, test, UAT, pre-production, production: what it is for, where it is, its catalogs and bundle target, whether the team may deploy, only read or not go there, whether the team or CI/CD deploys it, and its data rules |

Nothing has to be complete: the kickoff is a conversation and the PM asks only what is missing.

## 3. How the team works

Say it in a few lines, with the project's real values from `CLAUDE.md` — the boundaries the PO is agreeing to and what stays in their hands:

- Reads anywhere it has access to, writes only in the dev catalog and in the environments confirmed in the installer; production is read-only and audited.
- Every Databricks resource is declared in the asset bundle and deployed by the DevOps Engineer — nothing created by hand.
- Every object the team creates carries a description, and every ML or GenAI result exists as an MLflow run; QA checks both.
- Never pushes to the protected branches and never deploys production: the pull request to `main` and the production deployment stay with the PO.
- The PO approves twice: G1 on the design and the feature list, G2 on each delivered feature.

## 4. Close

End with the next step: `/df-kickoff <what the team should build or change, in a few words>` — or without arguments to be asked.
