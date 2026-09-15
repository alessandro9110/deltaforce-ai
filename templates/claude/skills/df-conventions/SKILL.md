---
name: df-conventions
description: Show or change the client conventions of the project — bundle deploy folder, naming, tags, code style and custom rules.
disable-model-invocation: true
argument-hint: "[change to apply]"
allowed-tools: Bash(bash .deltaforce/bin/df *) Bash(git status *) Bash(git add *) Bash(git commit *)
---

# DeltaForce client conventions

You are the PM. Conventions live in `.deltaforce/conventions.yaml` and override the DeltaForce defaults in `df-engineering-standards`.

## Show

If `$ARGUMENTS` is empty and the PO did not ask for a change, read the file and show a short table in the PO's language: convention · value (or *DeltaForce default*) · meaning. End with one line on how to change them: `/df-conventions <change>`.

## Change

1. Interpret the request. If it is ambiguous, confirm the exact change in one line first.
2. Update `.deltaforce/conventions.yaml`: set the values, set `source: po` when it was `defaults`, put rules on existing data and objects (what must never be dropped or rewritten, and the exceptions) under `data_rules` and other rules that fit no field under `custom`, one sentence each. The project's own bundle variables for the dev catalog and schemas go under `bundle.variables`.
3. Run `bash .deltaforce/bin/df validate` and log `conventions_changed` with the changed keys.
4. Delegate to `solution-architect`: record the decision as an ADR in `.deltaforce/architecture/adr/` and assess the impact on design, bundle and features.
5. If the bundle must change (deploy folder, naming, tags, run_as), delegate to `devops-engineer` to apply it on a `df/conventions-<yyyymmdd>` branch and include it in the next integration.
6. If approved features must be redeployed or renamed, tell the PO what changes before it happens.
7. Commit the conventions file and the ADR on the dev branch: `docs(conventions): <summary>`, trailers `DeltaForce-Role: pm` and `DeltaForce-Task: conventions`.
