---
name: df-readme
description: How the DeltaForce team documents the project repository for the client — the root README (what the project delivers, what each dashboard shows, which questions the Genie space answers, what each job does, its medallion layer and trigger) and a short README per source folder. Use when creating or updating the README of the project or of a folder under src.
user-invocable: false
---

# DeltaForce — the repository README

The **Business Analyst** owns the README of the project and the README of every source folder. The reader is the client: someone who opens the repository knowing nothing must learn, without reading code, what the project delivers, what every component is for, and where the detail lives.

Functional voice: what a component is for and what it answers, not how it is coded. Technical detail only where it changes what the reader can expect — the trigger of a job, the layer a table belongs to, the freshness of a dashboard.

The README never repeats the Functional Analysis or the Architecture: it introduces and links them.

## When it is written

| Moment | What |
| --- | --- |
| Design, after the as-is, before G1 | Create the root README: intro, objectives, the components the design foresees, each marked *Planned*. The PO sees it at G1 |
| Every feature, during the build | A documentation task: describe the components that feature delivered (drop *Planned*), update the folder README of the source it added. It reaches the PO in `.deltaforce/review/` at G2 |
| Handover | Final pass: no component without a description, no *Planned* left for work that was delivered or dropped |

The documentation task runs like any build task: a task branch off the feature branch, `df-git-flow` rules, the trailers. Edit only the sections the feature touches — Grep for the component, edit in place. Never rewrite the file.

## Root `README.md`

```markdown
# <project name>

<Two or three sentences: what this project delivers and for whom. From the request and
the business objectives, in the client's words, no jargon.>

## What it delivers
| Component | What it is for | Where it lives |
| --- | --- | --- |
<One row per dashboard, Genie space, job, pipeline, model, app, metric view. Links to the sections below.>

## Data
The layers and what each one holds, in business terms (bronze: raw as received;
silver: cleaned and conformed; gold: ready for consumption), with the catalog and schemas
the project uses. Grain and meaning of the main tables, not their DDL.

## Dashboards
### <name>
What question it answers, for which decision and for whom. The KPIs it shows and what each
one means. How fresh the data is and what filters matter.

## Self-service questions (Genie)
### <space name>
The kind of questions it answers and on which data, with three or four real examples.
What it deliberately cannot answer, so nobody trusts it with the wrong question.

## Data flows (jobs and pipelines)
### <job name>
What it produces, from what, through which layers (bronze → silver → gold).
When it runs (trigger or schedule), how long it takes, what happens on a failure.

## Models
### <model name>
What it predicts and on what evidence. How good it is, in the client's units
(an average error, a quality score) against the obvious alternative. When it is retrained
and the rule that decides whether a new version replaces the one in use.

## Applications
### <app name>
Who uses it, for what, and what it does under the hood in one paragraph
(what it reads, which model or endpoint answers, what it cannot do).

## Metrics
One row per KPI: name, meaning, formula in words, grain, where it is defined.
The metric view is the single definition — say so.

## How it is built and deployed
The bundle in one paragraph, the environments and who deploys to each
(the team on dev, CI/CD beyond it). Point to `.devops/` for the pipelines.

## Documents
Functional Analysis, Architecture and ADRs, the delivery reports — with their paths.
```

Drop sections the project has no components for. Keep the order: what it delivers, then the data, then the components, then how it runs.

## Folder READMEs

One short `README.md` — half a page, no more — in every folder under `src/` that holds a deliverable, and in `.devops/` when the project has CI/CD:

- **What these resources are for**, in one or two sentences, and who consumes their output.
- **What each one does**, one line per file or module.
- **How it was built**: the approach and the choices that matter (which technique, which model, why this way and not the obvious alternative), from the builders' reports — not from re-reading the code.
- **What it depends on** and **where the output lands** (tables, endpoints, dashboards).

## Rules

- **Write from the reports.** The builders' task reports and the G2 report say what was built and why. Read code only when a report leaves a component unexplained.
- **Names come from the project**: the catalog, schemas and objects the conventions and the bundle variables define. Never invent a name, never document one the team did not create.
- **An existing project already has a README**: keep every line of it. Add the sections for what the team delivers and edit in place only what the change affects — the same rule as the Functional Analysis. If the client's README has its own structure, follow theirs.
- **Nothing that ages badly**: no run ids, no absolute workspace URLs, no numbers that change every run. Measured results belong here only when they are the point of the component (a model's quality), with the date they were measured.
- **Nothing secret**: no tokens, no host names of the client's workspaces beyond what the repository already carries, no personal data in examples.
- **Say what is not there**: known limitations and what a component deliberately does not do. A reader who discovers the limit by being wrong is a reader the documentation failed.
