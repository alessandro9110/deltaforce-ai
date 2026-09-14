---
name: df-status
description: Show where the DeltaForce project stands — phase, features and tasks, what is waiting for the Product Owner, and the team's next step. Read-only.
disable-model-invocation: true
allowed-tools: Bash(bash .deltaforce/bin/df *) Bash(git status *) Bash(git log *) Bash(git branch *)
---

# DeltaForce status

You are the PM. This command only reads: do not change files, do not delegate, do not log events.

1. Read `.deltaforce/status.json`. If DeltaForce is not ready, say so and give the re-check command (see `/df-kickoff`, step 1).
2. If `.deltaforce/state.yaml` does not exist, say the project has not started and suggest `/df-kickoff`.
3. Otherwise read `.deltaforce/state.yaml`, the frontmatter of every file in `.deltaforce/backlog/`, the last 20 lines of `.deltaforce/events.jsonl`, and `git branch --list 'df/*'`.

Answer in the PO's language:

1. **Headline** — one line: phase and overall progress (e.g. *Delivery — 2 of 5 features done, 2 in progress*).
2. **Features** — a table: Feature · Title · Status · Waiting for · Note. *Waiting for* is one of: team, DevOps, QA, PO, dependency F-xxx.
3. **Waiting for you** — what the PO has to review or decide, each with the command to use (`/df-approve F-xxx`, `/df-changes F-xxx <notes>`, `/df-approve` for G1).
4. **Last update** — the time and summary of `last_update`.
5. **Next steps** — the `next_steps` from `state.yaml`, grouped by owner (the PO's own steps first).
