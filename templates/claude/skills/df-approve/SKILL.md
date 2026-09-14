---
name: df-approve
description: Product Owner approval of a gate — the design and feature list (G1) or a delivered feature (G2) — after which the PM continues the process.
disable-model-invocation: true
argument-hint: "[F-xxx] [notes]"
allowed-tools: Bash(bash .deltaforce/bin/df *) Bash(git status *) Bash(git add *) Bash(git commit *)
---

# DeltaForce approval

You are the PM. Only the PO approves: act on this command, never approve on your own.

## 1. Find the gate

- `$ARGUMENTS` starts with a feature id (`F-xxx`) → **G2** for that feature. It must be `awaiting_po`; otherwise explain its status and stop.
- Otherwise, `phase: awaiting_g1` → **G1**.
- Otherwise, exactly one feature is `awaiting_po` → **G2** for that feature.
- Otherwise list what is waiting and ask which one to approve.

The rest of `$ARGUMENTS` are the PO's notes.

## 2. G1 — design and feature list

1. In `.deltaforce/state.yaml` set `g1` to `approved` with the time and notes, and `phase: delivery`.
2. Log `po_decision` (`{"gate":"G1","decision":"approved"}`) and `phase_changed`; run `bash .deltaforce/bin/df validate`.
3. Commit the `.deltaforce/` changes on the dev branch: `docs(g1): approve design and feature list`, trailers `DeltaForce-Role: pm`, `DeltaForce-Task: G1`.
4. Tell the PO which features start now (those without dependencies, up to three) and start Phase 2.

## 3. G2 — a delivered feature

1. In the feature file set `po_decision` to `approved` with the time and notes; log `po_decision` (`{"gate":"G2","decision":"approved"}`).
2. Delegate to `devops-engineer`: merge `df/F-xxx` into the dev branch, push, rebuild `df/integration` with the features still active.
3. When the merge is confirmed: set the feature `done`, remove it from `active_features`, log `feature_status_changed`, validate, and commit the backlog and state changes on the dev branch.
4. Tell the PO in one or two lines what was merged and what starts or continues now, then go on with Phase 2: start the features this one unblocked.
5. When every feature is `done`, move to Phase 3 (handover).
