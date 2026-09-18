# Known failures

Failures DeltaForce teams hit on real runs, with the fix that worked. Check this table when something fails before
inventing a theory, and add a row when a run teaches a new one (symptom, cause, fix — keep it one line each).

## Python that runs as a job task

| Symptom | Cause | Fix |
| --- | --- | --- |
| `NameError: name '__file__' is not defined` | A `spark_python_task` runs inside a wrapper, not as a script | Do not build paths from `__file__`: keep the file self-contained, or ship shared code as a wheel declared in the bundle |
| A task that finished its work is reported `FAILED` | `sys.exit()` — `sys.exit(0)` included — raises `SystemExit`, which Databricks reports as a failure | Return normally; raise an exception with the summary when checks fail |
| `RESOURCE_DOES_NOT_EXIST: Could not find experiment with ID None` on `mlflow.start_run()` | A job task has no notebook to infer a default MLflow experiment from | Pass `--experiment_name` (`${resources.experiments.<key>.name}`) and call `mlflow.set_tracking_uri("databricks")` + `mlflow.set_experiment(name)` before `start_run()` |
| Several unrelated checks come back `SKIPPED` / `UPSTREAM_FAILED` | Tasks chained with `depends_on`: one failure skips everything downstream | Probe and check tasks stay independent; collect results in a final task with `run_if: ALL_DONE` |

## Running code without deploying

| Symptom | Cause | Fix |
| --- | --- | --- |
| `execute_code` fails: `Invalid platform channel Client-1 … Workspace doesn't support Client-1 channel for REPL` | The workspace has no REPL channel for serverless (Free Edition, or no classic cluster) | Do not fall back to "deploy everything": use Databricks Connect serverless, or a one-off `databricks jobs submit` (`df-testing`, *Run it before you hand it over*) |

## Bundle resources

| Symptom | Cause | Fix |
| --- | --- | --- |
| A Databricks App stays in `FAILED` and runs `python app.py` instead of its real command | Apps get their `app.yaml` and source only from a full, successful `bundle deploy`; a `--select` deploy never triggers it | Fix whatever breaks the full deploy first, then deploy the whole bundle once; never hand-write `app.yaml` |
| `cannot create resources.dashboards.<name>: [dashboard.datasets[…].parameters[0].displayName] should not be empty (400)` | The Lakeview API requires a `displayName` on every dataset parameter; `bundle validate` does not check inside the definition | Give every dataset parameter a `displayName` in the `.lvdash.json` |
| Every `bundle plan` shows an `update` on a Genie space that nobody touched | `serialized_space.data_sources.metric_views` is accepted by the CLI but dropped by the server, which keeps every source under `tables` | Declare every source, metric views included, under `data_sources.tables` (`df-bi/references/genie-space.md`) |
| Bundle variables appear as literals in a Genie space, or not at all | A `serialized_space` referenced with `file_path` is not interpolated | Inline `serialized_space` in the resource YAML |
| A vector search index stays `NOT_READY` for a long time after the first deploy | The first Delta Sync of an index can take more than ten minutes | Plan for it: check once, continue with other work, verify later — never poll in a loop |
| `bundle deploy` creates a second copy of pipelines and jobs that already exist | The bundle name or target changed since the last deploy of those resources | `bundle deployment bind` each existing resource before the first deploy (`references/existing-projects.md`) |
| A pipeline or a vector search endpoint refuses a `description` | The current CLI does not accept a description on those two resource types | Put the description in a comment in the resource file and say so in the report |

## Validation that proves nothing

| Symptom | Cause | Fix |
| --- | --- | --- |
| `bundle validate` passes and the deploy fails on the same file | Some resource bodies (`serialized_space`, dashboard definitions) are opaque to the CLI schema | Treat the first deploy as the test; for opaque resources run a post-deploy round trip (`bundle generate …` or the `get` API) and diff it against the committed file |
