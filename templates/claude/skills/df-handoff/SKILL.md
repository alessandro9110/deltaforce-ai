---
name: df-handoff
description: DeltaForce delegation and reporting format — what a delegation prompt must contain, how specialists report back, nested delegation and when to escalate. Use when delegating to another agent or reporting results.
user-invocable: false
---

# DeltaForce hand-offs

Agents do not share memory. Everything the receiver needs must be in the delegation prompt or in files it is told to read; everything the caller needs must be in the report.

## Delegation prompt

```markdown
## Context
Project phase, feature F-xxx (title), task T-xxx.n, why this task exists.

## Read first
- CLAUDE.md, .deltaforce/conventions.yaml
- .deltaforce/architecture/architecture.md#<section>
- .deltaforce/backlog/F-xxx-<slug>.md
- <other files>

## Goal
One or two sentences on the outcome.

## Acceptance criteria
1. ...

## Branch
Start point df/F-xxx, task branch df/F-xxx-<role>-T<n>   (build tasks only)

## Constraints
Dev target only, bundle variables for names, anything else specific.

## Definition of done and report
What must be true when you finish; report with the df-handoff report format.
```

Keep it specific: name files, sections, tables and criteria. Do not paste whole documents the receiver can read.

**Paths**: builders run in git worktrees that contain only committed files, while requirements, design, backlog and conventions are updated in the main checkout. In *Read first*, give those files as absolute paths under the main checkout (the PM's working directory, also `$DF_ROOT`), e.g. `C:/Users/me/Projects/my-project/.deltaforce/architecture/architecture.md`. Code and bundle files are read from the worktree.

## Report

Reports go back to the caller and stay under 300 words unless test tables need more.

```markdown
## Status
done | blocked | needs-decision

## Summary
What was done, in three to five lines.

## Changes
- Branch and commits
- Files created or changed
- Databricks objects created, changed or to be created at deployment

## Verification
Commands, queries, runs or tests executed and their results.

## Open points
Questions, risks, decisions needed — each with who can answer (PM, SA, BA, PO).
```

## Nested delegation

- Delegate only what you are allowed to (your agent definition lists it) and only when it saves time: separate files, or a consultation.
- Consultations (a question to another role) return findings, never branches.
- Before reporting, integrate your sub-agents' branches into your own task branch and include their results in your report.

## Escalation

- Blocked or unsure → report `blocked` or `needs-decision` to your caller with the specific question. Do not guess on architecture, requirements or data meaning.
- Only the PM talks to the PO. The PM escalates to the PO for blockers the team cannot solve, ambiguities in the request, changes to what the PO asked for, and the gates.
