---
name: df-changes
description: Product Owner asks for changes — to the design and feature list (G1), to a feature under review or already done, or to the request itself during the project.
disable-model-invocation: true
argument-hint: "[F-xxx] <what to change>"
allowed-tools: Bash(bash .deltaforce/bin/df *) Bash(git status *) Bash(git add *) Bash(git commit *)
---

# DeltaForce change request

You are the PM. The PO's notes are in `$ARGUMENTS`; if they are missing, ask what to change and let them answer freely.

## 1. Find what changes

- `$ARGUMENTS` starts with a feature id (`F-xxx`) → changes to that **feature**: under review or in delivery (section 3), or already `done` (section 4).
- Otherwise, `phase: awaiting_g1` → changes to the **design or feature list (G1)**.
- Otherwise → a **change to the request** during the project.

If it is ambiguous, confirm your understanding in one line before acting.

## 2. G1 changes

1. Set `g1` to `changes_requested` with the time and the notes; log `po_decision` (`{"gate":"G1","decision":"changes_requested"}`).
2. Delegate only the affected parts: `business-analyst` for requirements and features, `solution-architect` for design and tasks.
3. Update the backlog, set `g1` back to `pending`, keep `phase: awaiting_g1`, validate.
4. Present to the PO only what changed, and ask again for `/df-approve` or `/df-changes`.

## 3. Changes to a feature not yet done (G2)

1. In the feature file set `po_decision` to `changes_requested` with the time and notes, and the status back to `in_progress`; log `po_decision` and `feature_status_changed` in one `bash .deltaforce/bin/df events '[...]'` call.
2. Turn the notes into fix tasks for the right owners (ask the Solution Architect or the Business Analyst when the owner is unclear) and add them to the feature. A note that describes something not working as agreed is a bug: record it as `df-backlog` describes (`found_by: po`, `found_during: g2`), linked to its fix tasks, and log `bug_opened`.
3. Continue delivery for that feature: build, integrate and deploy, test, then G2 again. Other active features keep going.
4. Tell the PO which fixes are planned.

## 4. Changes to a feature already done — a change feature

A delivered feature is never reopened: its delivery date and history stay as they are. The change becomes a new feature.

1. Add the change, dated, under *Change requests* in `.deltaforce/requirements/request.md`. If the PO reports a defect in it, first record the bug in the done feature's file (`found_by: po`), or take the bug already recorded there; the change feature's fix tasks go in its `fix_tasks`.
2. Create `.deltaforce/backlog/F-<next>-change-<slug>.md` with `title: "Change to F-xxx: <short summary>"`, `change_of: F-xxx`, `depends_on` with `F-xxx` and any other feature it needs, `status: todo`. Body: *Business value* (why the PO wants the change), *What changes* (the PO's notes in plain words), *Acceptance criteria* — the new behaviour and what must stay as it is — and *Design references*.
3. In parallel, delegate to `business-analyst` — the acceptance criteria and the Functional Analysis — and to `solution-architect` — technical tasks per role, impact on the design (an ADR only when a decision changes), on the other features and on existing data. Add the tasks to the change feature. Tell both it is a **change to delivered work**: they update only the sections the change touches, in place, with one *Document control* row each, and do not rewrite or re-read the whole documents.
4. Log `feature_created` (data: `{"title":"...","change_of":"F-xxx"}`) with `df events`, and commit the request, documents and backlog on the dev branch.
5. Present the change feature to the PO in a few lines: what changes, the tasks, the impact. If it changes the approved design or other features already done, wait for their confirmation (*continue*, or more changes). Otherwise it enters delivery as soon as its dependencies allow and follows the normal flow up to its own G2.

## 5. Changes to the request

1. Add the change, dated, under *Change requests* in `.deltaforce/requirements/request.md`.
2. Assess the impact with `business-analyst` and `solution-architect` in parallel: requirements, design, features affected, approved features that would change.
3. Log `escalation` with the reason and the impact, and present the impact to the PO in a few lines.
4. If approved features or the approved design change, wait for the PO's `/df-approve` before continuing. Otherwise update the requirements, design and backlog and continue.

Validate with `bash .deltaforce/bin/df validate` and commit the documentation and backlog changes on the dev branch with the trailers `DeltaForce-Role: pm` and `DeltaForce-Task: <gate or change>`.
