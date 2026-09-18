# A Genie space as a bundle resource

Verified on a real deploy (2026-09-18). When the platform contradicts this file, the platform wins: fix the file in the
same task and say so in the report.

## One file, everything inline

```yaml
# resources/<slug>.genie_space.yml
resources:
  genie_spaces:
    <slug>:
      title: "Sales questions"
      description: "Ad hoc questions on sales; KPIs from the governed metric view, detail from silver."
      warehouse_id: ${var.warehouse_id}
      # No permissions block: the space is visible to the deploying identity only.
      serialized_space:
        version: 2
        data_sources:
          tables:
            - identifier: ${var.catalog}.${var.schema_gold}.${var.prefix_gold}sales_metrics
              description: "Governed KPIs. Always query through MEASURE(...)."
            - identifier: ${var.catalog}.${var.schema_silver}.${var.prefix_silver}orders
              description: "One row per order line, for detail questions."
        instructions:
          text_instructions:
            - id: "0f3c1d2b4a5e6f708192a3b4c5d6e7f8"
              content:
                - "Revenue always comes from MEASURE(`Revenue`) on the metric view, never from a hand-written SUM."
                - "Test accounts (account_type = 'internal') are excluded from every answer."
                - "Out of scope: anything that is not sales — say so instead of guessing."
          example_question_sqls:
            - id: "1a2b3c4d5e6f708192a3b4c5d6e7f809"
              question: "Revenue per region last month"
              sql: "SELECT region, MEASURE(`Revenue`) ..."
        config:
          sample_questions:
            - id: "2b3c4d5e6f708192a3b4c5d6e7f8091a"
              question: "How much did we sell last week?"
        benchmarks:
          questions:
            - id: "3c4d5e6f708192a3b4c5d6e7f8091a2b"
              question: "Revenue per region last month"
              answer_sql: "SELECT region, MEASURE(`Revenue`) ..."
```

Rules the platform enforces, none of which `bundle validate` checks (`serialized_space` is opaque to the CLI schema):

- **Every source goes under `data_sources.tables`, metric views included.** `data_sources.metric_views` is accepted by
  the CLI and **dropped by the server**: keeping it produces a spurious `update` on every `bundle plan`, forever. What
  marks a metric view as such is the instruction to query it through `MEASURE(...)`, not the structure.
- **Inline `serialized_space`, never `file_path`.** A referenced file is not interpolated, so `${var.catalog}` would
  reach the workspace literally — and literal identifiers are forbidden by the standards.
- Ids are 32-character lowercase hex strings, unique across `text_instructions`, `example_question_sqls`,
  `sample_questions` and `benchmarks.questions`; arrays sorted by id; ids stay stable across edits.
- `version: 2` with `instructions.text_instructions` (one entry, a `content` array), `instructions.example_question_sqls`,
  `config.sample_questions`, `benchmarks.questions`. The older `sql_instructions` shape is gone.

## Importing a space someone built in the interface

```bash
databricks bundle generate genie-space --existing-id <space id>
databricks bundle generate genie-space --resource <slug> --watch   # pull back edits made in the UI while curating
```

Both are run by the Data Analyst in their worktree; neither is a deploy. Move the generated content into the inline
form above and replace the literal identifiers with bundle variables before committing.

## After the first deploy, check the round trip

The deploy is the first real validation, and the server rewrites part of what it receives:

```bash
databricks genie get-space <space id> --include-serialized-space -o json
databricks bundle plan -t <dev target>     # must show no update on the space
```

Diff what comes back against the committed file. Anything the server moved or dropped belongs in the committed file in
the server's own shape, otherwise every future deploy carries a phantom change. `benchmarks.questions` coming back in a
different order is cosmetic; a missing key is not. Record the check in the task report — it is the acceptance criterion
that proves the space is really the one in git.

## What makes the space answer well

Curation, not configuration: scope kept to the sources that answer the intended questions, instructions that carry the
glossary and the exclusions, example SQL for the frequent questions, descriptions on every table, column, measure and
dimension, and a benchmark question set QA re-runs after every change (`df-bi` §5 and §6).
