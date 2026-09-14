---
name: df-git-flow
description: DeltaForce git rules — dev, feature, task and integration branches, worktrees, commit trailers, merges and forbidden operations. Use before creating branches, committing, merging or pushing.
user-invocable: false
---

# DeltaForce git flow

Values come from `.deltaforce/config.yaml`: `project.dev_branch` and `project.protected_branches`.

## Branches

| Branch | Created by | From | Purpose |
| --- | --- | --- | --- |
| `<dev_branch>` | PO / installer | — | Everything the PO approved. The main checkout stays on it |
| `df/F-xxx` | PM | `<dev_branch>` | One feature |
| `df/F-xxx-<role>-T<n>` | the specialist | `df/F-xxx` | One task, e.g. `df/F-003-data-engineer-T1` |
| `df/integration` | DevOps Engineer | `<dev_branch>` + active features | What is deployed on the dev target. Local only, never pushed |
| protected branches | people | — | Production. The team never pushes to them; a person opens the pull request |

Several features can be active at the same time when they do not depend on each other.

## Task branches in worktrees

Specialists that change code run in their own git worktree. The first command of every task:

```bash
git switch -c df/F-xxx-<role>-T<n> df/F-xxx
```

The explicit start point matters: the worktree starts from whatever the main checkout has checked out, not from the feature. Use `-`, not `/`, after the feature id: git cannot create `df/F-003/...` while the branch `df/F-003` exists.

Sub-agents of a specialist create `df/F-xxx-<role>-T<n>-<m>` from the parent's task branch; the parent merges them into its task branch before reporting.

## Commits

- Small, focused commits with Conventional Commit subjects: `feat(silver): deduplicate customers`, `fix(pipeline): ...`, `test(dq): ...`, `docs(architecture): ...`
- Always add the trailers:

```text
DeltaForce-Role: data-engineer
DeltaForce-Task: F-003/T-003.1
```

- Never commit secrets, `.deltaforce/.databrickscfg`, `.mcp.json` or anything under `.deltaforce/bin` and `.deltaforce/runtime`.

## Push

- Push task and feature branches when the repository has a remote: `git push -u origin <branch>`. That keeps the work traceable.
- Only the DevOps Engineer pushes `<dev_branch>`.
- Never push `df/integration`.

## Merges

- Only the DevOps Engineer merges: task → feature, features → `df/integration`, approved feature → `<dev_branch>`.
- Always `git merge --no-ff` so each feature and task stays visible in history.

## Forbidden

- Pushing to, merging into or committing on a protected branch
- `git push --force` / `--force-with-lease` on any shared branch
- `git reset --hard`, `git rebase` or other history rewrites on `<dev_branch>`, feature branches or task branches that were pushed (`git switch -C df/integration` is the one allowed reset: that branch is local and disposable)
- Deleting remote branches
