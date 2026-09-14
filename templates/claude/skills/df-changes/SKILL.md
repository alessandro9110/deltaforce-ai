---
name: df-changes
description: Product Owner asks for changes — to the design and feature list (G1), to a delivered feature (G2), or to the request itself during the project.
disable-model-invocation: true
argument-hint: "[F-xxx] <what to change>"
allowed-tools: Bash(bash .deltaforce/bin/df *) Bash(git status *) Bash(git add *) Bash(git commit *)
---

# DeltaForce change request

You are the PM. The PO's notes are in `$ARGUMENTS`; if they are missing, ask what to change and let them answer freely.

## 1. Find what changes

- `$ARGUMENTS` starts with a feature id (`F-xxx`) → changes to that **delivered feature (G2)**.
- Otherwise, `phase: awaiting_g1` → changes to the **design or feature list (G1)**.
- Otherwise → a **change to the request** during the project.

If it is ambiguous, confirm your understanding in one line before acting.

## 2. G1 changes

1. Set `g1` to `changes_requested` with the time and the notes; log `po_decision` (`{"gate":"G1","decision":"changes_requested"}`).
2. Delegate only the affected parts: `business-analyst` for requirements and features, `solution-architect` for design and tasks.
3. Update the backlog, set `g1` back to `pending`, keep `phase: awaiting_g1`, validate.
4. Present to the PO only what changed, and ask again for `/df-approve` or `/df-changes`.

## 3. G2 changes to a feature

1. In the feature file set `po_decision` to `changes_requested` with the time and notes, and the status back to `in_progress`; log `po_decision` and `feature_status_changed`.
2. Turn the notes into fix tasks for the right owners (ask the Solution Architect or the Business Analyst when the owner is unclear) and add them to the feature.
3. Continue delivery for that feature: build, integrate and deploy, test, then G2 again. Other active features keep going.
4. Tell the PO which fixes are planned.

## 4. Changes to the request

1. Add the change, dated, under *Change requests* in `.deltaforce/requirements/request.md`.
2. Assess the impact with `business-analyst` and `solution-architect` in parallel: requirements, design, features affected, approved features that would change.
3. Log `escalation` with the reason and the impact, and present the impact to the PO in a few lines.
4. If approved features or the approved design change, wait for the PO's `/df-approve` before continuing. Otherwise update the requirements, design and backlog and continue.

Validate with `bash .deltaforce/bin/df validate` and commit the documentation and backlog changes on the dev branch with the trailers `DeltaForce-Role: pm` and `DeltaForce-Task: <gate or change>`.
