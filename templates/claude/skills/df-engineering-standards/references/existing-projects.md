# Existing projects

Read this when `.deltaforce/conventions.yaml` says `project.kind: existing`, before writing code or resources.

The team extends a project that already works. Nothing here is advice: the rules below are binding.

- Follow `.deltaforce/architecture/as-is.md` and the conventions derived from the code. Do not restructure, rename or
  move existing code, resources or tables unless the design says so.
- Use the project's own bundle variables recorded in `bundle.variables` for the dev catalog and the schemas.
  DeltaForce does not redefine variables the bundle already has.
- The `data_rules` are binding. Unless a rule allows it, never drop, replace or truncate existing tables, delete their
  data or remove their checkpoints — neither directly nor in code that will run. If a task needs it, stop and report
  `needs-decision`.
- List every destructive operation on existing data or objects — `DROP`, `TRUNCATE`, `CREATE OR REPLACE`, overwrite
  writes, `DELETE` or `UPDATE` without `WHERE`, checkpoint removal — in your report, with the rule that allows it.
- Resources that already exist in the workspace are adopted with `bundle deployment bind` before the first deploy
  (DevOps Engineer). A plain deploy would create a second copy and collide on table ownership.
- Keep the existing CI/CD pipelines working; change them only when the design says so.
- Existing tests may flag the objects the change adds. That is an obsolete test, not a regression: widen it and say so
  in the report.
