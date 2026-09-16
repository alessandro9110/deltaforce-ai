---
name: df-bi
description: DeltaForce BI practices on Databricks — the analytics strategy in the Architecture, one definition per KPI in a metric view, gold modelled for consumption, AI/BI dashboard design, Genie space curation and how its answers are verified, permissions and cost. Use when designing, building or testing dashboards, metric views, semantic layers or Genie spaces.
---

# DeltaForce — BI and self-service analytics

The Data Analyst builds it; the Solution Architect designs the analytics layer with them; the DevOps Engineer deploys; the QA Engineer verifies on their own. For current APIs load `databricks-aibi-dashboards`, `databricks-metric-views`, `databricks-dbsql` and `databricks-data-discovery`.

## 1. Strategy — Architecture section *Analytics*

Decided before G1:

| Topic | Decide and write down |
| --- | --- |
| Audience | Who reads it, what decision each one makes, how often they look |
| Questions | The questions the solution must answer, and the ones it deliberately does not |
| KPIs | Name, business definition in one sentence, formula, grain, filters that belong to the definition, who owns it |
| Freshness | How current the numbers must be, and what the dashboard shows while data is being refreshed |
| Delivery | Dashboard for known questions, Genie space for the questions nobody listed, or both — with the reason |
| Access and cost | Who may see what (row and column level if needed), which warehouse serves it, the expected query cost |

## 2. One definition per KPI

- A KPI is defined **once**, in a metric view: measures, dimensions and the joins behind them. Dashboards, Genie and downstream queries read that view — never a formula copied into a widget.
- A number recomputed in two places is a bug waiting: when a dashboard needs a variant (different filter, different grain), it is a dimension or a new measure in the metric view, not a second formula.
- Every measure and dimension carries a description, in business words. The PO must recognize the definition without reading SQL.
- Reconcile every measure against the silver layer before it is published: totals, counts and a couple of slices, with the query kept as a data quality test.

## 3. Gold modelled for consumption

- Model for the question, not for the source: a wide table or a star the analyst can filter without joins nobody remembers.
- Declare the grain in the table description — one row per what — and enforce it with a uniqueness test.
- Heavy aggregation belongs in the gold pipeline, not in the dashboard query: materialize what is asked for on every page load.
- Names and layers from bundle variables, like everywhere else (`df-engineering-standards`).

## 4. Dashboard design

- One page answers one question; the number that matters goes at the top, the detail below. A page nobody can read in ten seconds needs splitting.
- Filters mirror the dimensions of the metric view, with sensible defaults; every widget states what it counts and over which period.
- Performance: query the metric view or the gold aggregate, limit rows returned, avoid per-widget recomputation of the same measure. Note the warehouse the dashboard runs on.
- Permissions are part of the design: who can see the dashboard, who can see the data behind it. Never rely on a widget to hide sensitive columns.
- Declare dashboards as bundle resources with the definition in `src/dashboards/`, and give every dashboard a description of what it answers.

## 5. Genie space curation

A Genie space is a product, not a switch: what makes it good is curation.

- **Scope**: give it the metric views and the certified gold tables that answer the intended questions — not the whole catalog. Everything you add is something it can get wrong.
- **Instructions**: business glossary, synonyms users actually say, default filters and time grain, join rules, and what the space does *not* cover so it can refuse instead of inventing.
- **Examples**: for the frequent questions, an example question with its trusted SQL. They teach the shape of a correct answer better than any instruction.
- **Descriptions carry the semantics**: table, column, measure and dimension descriptions are what Genie reads first — the same descriptions the standards already require.
- **Feedback loop**: review the questions people actually ask, and turn the wrong answers into instructions, examples or a missing measure.

A Genie space is a bundle resource like any other, in two paired files:

- `resources/<slug>.genie_space.yml` — `title`, `description`, `warehouse_id` (from the bundle variable), `permissions` (`CAN_VIEW`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE`) and `file_path` pointing to the definition;
- `src/dashboards/<slug>.geniespace.json` — the serialized space: data sources, instructions, example questions. Keep it in git: it is the curation, and it is reviewed like code.

Two commands help, run by the Data Analyst in their worktree (never a deploy):

- `databricks bundle generate genie-space --existing-id <id>` imports a space someone built in the UI into those two files;
- `databricks bundle generate genie-space --resource <name> --watch` pulls back changes made in the UI while curating, so git stays the source of truth.

**Genie spaces are not bindable**: deploying does not adopt a space that already exists in the workspace, it creates a new one. Never point a bundle resource at a hand-made space without importing it first — the original, with its chat history, would be left behind or overwritten. Record the import in the task report.

## 6. Verify the answers

- Build a set of expected questions with their reference answers — the BI equivalent of an evaluation dataset — covering the main KPIs, a couple of ambiguous phrasings and at least one out-of-scope question that must be refused.
- Run it against the Genie space and compare with the reference: the SQL it generates and the number it returns. Keep it as a test under `tests/integration/`, versioned with the space.
- The QA Engineer recomputes the reference numbers independently from the gold tables — never from what the dashboard or Genie reported — and re-runs the question set after every change to the space, the metric view or the underlying tables.

## 7. Rules

- Dashboards, metric views, Genie spaces and their underlying tables are bundle resources, deployed by the DevOps Engineer — never created by hand. The MCP tools that would create or change them are blocked by the guardrails; `ask_genie` stays available to question a deployed space.
- Genie spaces need the bundle **direct deployment engine** (Databricks CLI 1.3.0 or later; the project's CLI is newer). A bundle still on the Terraform engine migrates by itself after a successful deploy, or with `databricks bundle deployment migrate`. If a deploy refuses the resource, the DevOps Engineer checks `engine` in `databricks.yml` — `bundle.engine` or `targets.<target>.engine` — and reports it rather than switching engines under a delivery.
- Descriptions are mandatory on all of them (`df-engineering-standards`), and they double as the semantic layer Genie relies on.
- No literal catalog, schema or table names: bundle variables everywhere, including inside dashboard definitions.
