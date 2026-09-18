---
name: df-engineering-standards
description: DeltaForce engineering standards for Databricks — medallion layers for data engineering, analytics, ML and GenAI, bundle variables instead of literal names, project layout, naming, data quality and how client conventions override the defaults. Use before designing or writing any code, SQL or bundle resource.
user-invocable: false
---

# DeltaForce engineering standards

## Precedence

1. `.deltaforce/conventions.yaml` — client conventions (deploy path, naming, tags, code style, custom rules)
2. `.deltaforce/architecture/architecture.md` and ADRs — the approved design
3. These standards

When they conflict, follow the higher one and mention it in your report.

## References — read the one your task needs

| Read | When |
| --- | --- |
| `references/code-and-layout.md` | Before writing the first resource or code file: bundle variables, the shape of a job-task Python file, project layout, naming |
| `references/known-failures.md` | When something fails, and before writing code of a kind a run already broke on |
| `references/existing-projects.md` | When the conventions say `project.kind: existing` — its rules are binding |
| `references/production-data.md` | Only when `CLAUDE.md` lists a production workspace |

Load `df-testing` when you write or run tests, `df-pipelines` for ingestion, change data capture and data quality,
`df-bi` for dashboards, metric views and Genie, `df-mlops` for ML work, `df-aiops` for GenAI work.

## Environment

- The dev target, catalog and schemas are in the *DeltaForce project context* block of `CLAUDE.md` and in
  `.deltaforce/config.yaml`. The bundle target is usually `dev` but the project may name it differently: wherever these
  instructions say `-t <dev target>`, use the *Bundle target* from `CLAUDE.md`.
- **The dev catalog is the boundary.** Inside it the team may create the schemas, tables, volumes and models the
  solution needs, as long as they are consistent with the design and the medallion layers. Never write outside it,
  except in the catalogs of an environment the team deploys to.
- **Other environments** are declared under `environments` in `.deltaforce/conventions.yaml`; those the team deploys to
  are listed in `CLAUDE.md`. Work there only when the design and your delegation say so, follow that environment's
  `data_rules`, never write where the team has `read` or `none`, and never deploy to production.
- Databricks CLI: `"$DF_ROOT/.deltaforce/bin/databricks"` (profile preselected), never another Databricks CLI installed
  on the machine — not even when a command is blocked: report the block instead. Databricks MCP tools use the same profile.
- Serverless compute first. Classic clusters only when the design says so.

## Everything on Databricks goes through the asset bundle

Every Databricks resource of the project — jobs, pipelines, schemas, volumes, dashboards, metric views, Genie spaces,
apps, model serving endpoints, vector search endpoints and indexes, registered models, experiments, monitors — is
declared in the bundle (`databricks.yml` and `resources/*.yml`) and deployed to dev by the DevOps Engineer with
`bundle deploy`. Nothing is created, changed or deleted by hand.

- Databricks MCP tools are for **reading, querying and running**: explore data and metadata, run SQL and code on dev,
  query endpoints and indexes, trigger runs of deployed jobs and pipelines. Their create, update and delete actions are
  blocked by the guardrails.
- A resource type the bundle cannot declare yet is created by a job task in the bundle (a Python script using the
  Databricks SDK, idempotent), and the choice is recorded in an ADR.
- Exception: Agent Bricks Knowledge Assistants and Supervisor Agents are created and updated on dev by the AI Engineer,
  as `df-aiops` describes; deleting one needs a person.
- Data is not a resource: tables are produced by the deployed pipelines and jobs; SQL writes inside the dev catalog are
  allowed for development and tests. A one-off run that tries your code out is not a resource either (`df-testing`).

## Guardrails

Hooks block, whatever the instructions say: resource changes outside the bundle (Agent Bricks: creates and updates by
anyone but the AI Engineer, and deletes); publishing to the Hugging Face Hub (`hf upload`, an enabled `push_to_hub`) and
Hugging Face Jobs; writes outside the dev catalog and SQL writes that do not name it; Unity Catalog permission, sharing,
connection and storage changes; anything but reads on production; `bundle deploy`/`run` by anyone but the DevOps
Engineer or outside dev, and `bundle destroy`; pushes to protected branches, force pushes, remote branch deletions,
pushing `df/integration`, `reset --hard`, `rebase`; changes to or commits of what DeltaForce installed (agents, skills,
Claude settings, `.mcp.json`, `CLAUDE.md`, `.gitignore`, `resources/deltaforce.variables.yml`, `.deltaforce/config.yaml`,
framework, tools, runtime); conventions changes by anyone but the PM; the credentials file and its backups. A blocked
action returns `DeltaForce guardrail: <reason>`: do not work around it, report it to your caller.

## Few tool calls

Every tool call re-reads your whole context. Read the sections you need rather than whole documents, chain related shell
commands in one call, and never poll a run or a deployment in a loop.

## Medallion layers

| Layer | Data engineering and analytics | ML | GenAI |
| --- | --- | --- | --- |
| Bronze | Raw ingested data as received, raw files in volumes; append-only, with ingestion metadata | Raw training sources | Raw documents (PDF, HTML, …) in volumes |
| Silver | Cleaned, typed, deduplicated, conformed; data quality expectations | Cleaned training data | Parsed and chunked text with metadata |
| Gold | Business aggregates, marts, metric views, dashboard sources | Feature tables, predictions | Vector index source tables, evaluation datasets |

- Data flows only bronze → silver → gold. Gold never reads bronze.
- Models are registered in Unity Catalog in the gold schema; vector indexes are built on gold tables.
- Declare schemas and volumes the solution adds as bundle resources (`resources.schemas`, `resources.volumes`), never by hand.
- When the client's data is already modelled and the work starts from it, the existing tables are the layer they are:
  do not rebuild a medallion around them (`references/existing-projects.md`).

## Quality

- **Descriptions are mandatory and never left empty.** Every object the team creates on Databricks carries a description
  of what it holds or does: schemas, tables, views and their columns, volumes, functions, registered models and their
  versions, vector search indexes, serving endpoints, jobs, pipelines, dashboards and Genie spaces. `COMMENT` in SQL and
  DDL, `comment` or `description` in bundle resources, the description argument when an MCP tool or the MLflow API
  creates the object. Say what it is for and where the data comes from, not what the name already says.
- Idempotent pipelines and jobs: re-running must not duplicate data.
- Expectations on silver and gold for keys, nulls, ranges and referential integrity.
- Python files over notebooks for production code unless the client conventions say `notebooks`.
- No secrets in code or resources: Databricks secret scopes or CI/CD variables.
- Keep changes inside the scope of your task; note anything else as an open point.
