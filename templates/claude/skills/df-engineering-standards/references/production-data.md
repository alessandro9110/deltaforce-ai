# Production data (read-only)

Read this only when `CLAUDE.md` lists a production workspace.

Realistic data for development, ML and GenAI comes from the dev catalog; production data is used only when the
conventions or the kickoff request say so. The `databricks-prod` MCP tools read from it: `execute_sql` and
`execute_sql_multi` (only `SELECT`, `WITH … SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`), `get_table_stats_and_schema`,
`get_volume_folder_details`, `manage_serving_endpoint` (get, list, query), `query_vs_index`, `ask_genie`. Everything
else on production is blocked, including the Databricks CLI.

- Pass the production warehouse from `CLAUDE.md` to every production query.
- Read the minimum: schemas, aggregates, samples. Copy production data into dev only when the Functional Analysis
  requires it and the PO approved it; never copy sensitive data.
- Model and AI function calls on production consume the client's credits: keep them few and small.
- Every production call is audited with your role.
