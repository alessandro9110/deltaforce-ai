# DeltaForce AI

**A Databricks delivery team made of Claude Code agents, working inside your repository, with you as the Product Owner.**

You describe what you need — a new data product, or a change to a project that already exists — and a team of nine specialized agents analyses, designs, builds, tests and deploys it on Databricks: data engineering pipelines, analytics and dashboards, ML models, GenAI assistants and agents. You approve the design and every feature; the team does the rest and asks you only when something needs your decision.

> **Status**: installer, configuration, the nine agents, the team skills, the Product Owner commands, guardrail and audit hooks, support for existing projects and the monitor are implemented — see [docs/roadmap.md](docs/roadmap.md). Architecture and process: [docs/design.md](docs/design.md).

## What DeltaForce does

| You, the Product Owner | The team |
| --- | --- |
| Describe what to build or change — `/df-kickoff` | Analyses the request, the data and, in an existing project, the codebase and what is deployed |
| Approve the design and the feature list — gate **G1** | Writes the Functional Analysis and the Architecture, splits the work into features |
| Validate every delivered feature — gate **G2** | Builds features in parallel, deploys them to dev, tests them, reports the evidence |
| Open the pull request to production | Keeps the dev branch ready for CI/CD |

| Role | What it does |
| --- | --- |
| Project Manager | The only one who talks to you. Plans, delegates, tracks the backlog and the state, runs the gates |
| Solution Architect | Designs the solution — medallion flows, tables, bundle layout — and checks that the work follows it |
| Business Analyst | Business objectives, expected value, requirements and acceptance criteria |
| Data Engineer | Ingestion and bronze, silver, gold pipelines and jobs |
| Data Analyst | Gold marts, metric views, AI/BI dashboards, Genie spaces |
| Data Scientist | Exploration, features, ML training and evaluation with MLflow |
| AI Engineer | GenAI: document processing, vector search, agents, evaluation, serving, apps |
| QA Engineer | Data quality, integration and regression tests on the deployed feature |
| DevOps Engineer | The only one who integrates, deploys to dev and merges into the dev branch; owns CI/CD |

## How it works

- **Agents in Claude Code.** Every Claude Code session in the project starts as the Project Manager. The PM delegates to the specialists, several at the same time when their work is independent. Each specialist that writes code works in its own git worktree and branch.
- **Everything is in files.** Request, Functional Analysis, Architecture, backlog, task reports, review reports and project state live in `.deltaforce/`, committed with the code. You can close Claude Code at any time: the next session continues from there.
- **Databricks through official tooling.** Agents query and explore Databricks with the [Databricks AI Dev Kit](https://github.com/databricks-solutions/ai-dev-kit) MCP server, follow current patterns from the Databricks agent skills, and declare every resource — jobs, pipelines, dashboards, models, endpoints — in a **Databricks Asset Bundle**. Names of catalogs, schemas and tables are always bundle variables.
- **The process**: kickoff → (existing project: as-is analysis) → requirements and design → **G1** → for each feature: build → integrate and deploy to dev → test → **G2** → merge into the dev branch → a person opens the pull request → CI/CD deploys to production.

## Where the team works

**The repository.** The team works on the dev branch you choose at installation, never on the protected branches (`main`…). Each feature gets a branch `df/F-001`, each task a branch of its own. The code currently deployed on dev is always visible in `.deltaforce/review/`, so you can read it before you approve. Only the DevOps Engineer merges into the dev branch, only after your approval; a person opens the pull request to production. Every commit says which role made it.

**The dev workspace.** The Databricks workspace and the dev catalog and schemas you pick at installation. The team reads and queries data there, creates the schemas and tables the solution needs inside the dev catalog, and deploys and runs the bundle on the dev target. It signs in with a project-local Databricks CLI profile — with OAuth, your own identity.

**The production workspace** (optional). A separate workspace the team can only **read**: SQL queries, model serving and vector search queries, Genie and table statistics, useful when some data exists only in production. Every access is audited with the role that made it. Deployments to production happen only through your CI/CD, from the protected branch.

## What the team can and cannot do

| The team can | The team cannot |
| --- | --- |
| Read and query data on dev, and read production when configured | Write outside the dev catalog, or do anything but read on production |
| Create schemas, tables, jobs, pipelines, dashboards, models and endpoints on dev — through the asset bundle | Create, change or delete Databricks resources by hand, or run `bundle destroy` |
| Deploy and run the bundle on the dev target (the DevOps Engineer only) | Deploy to production, push to protected branches, force-push or rewrite history |
| Commit and push feature and task branches; merge approved features into the dev branch | Change Unity Catalog grants, sharing, connections or storage |
| Extend an existing project, following its conventions and your rules on existing data | Change what DeltaForce installed — agents, skills, settings, framework — or read the credentials |

These rules are not just instructions: hooks check every action of every agent before it runs, also in auto mode, and every Databricks call, shell command and blocked action is recorded in `.deltaforce/audit.jsonl` (details in [Guardrails](#guardrails)).

## Watch the team

The **monitor** opens in your browser when the team starts working: what is happening now and what waits for you, each agent with what it is doing, the feature board with delivery dates, and the workflow — handoffs, work sent back, your involvement and a timeline of who worked when. A link is always in the Claude Code status line. It runs on your computer, only reads `.deltaforce/`, and uses no tokens. See [Watch the team in the browser](#watch-the-team-in-the-browser).

## Why the installer sets up so much

Everything stays inside the project, so every team member gets the same versions without administrator rights or global installs.

| What | Why |
| --- | --- |
| uv, Python and the Databricks CLI in `.deltaforce/bin` and `.deltaforce/runtime` | The same tool versions for everyone, nothing installed on the machine |
| Databricks AI Dev Kit MCP server | Lets the agents explore and query Databricks |
| Databricks agent skills in `.claude/skills/databricks-*` | Current Databricks patterns for each role |
| Agents in `.claude/agents` and DeltaForce skills in `.claude/skills/df-*` | The team, its process, formats and rules, and your commands |
| Hooks, guard policy and Claude settings | The guardrails, the audit trail, the PM as main session, the project profile |
| `CLAUDE.md` block, `databricks.yml`, bundle variables | Project context for every agent; parametric names and the dev target |
| Monitor and status line | Watching the team without spending tokens |

The full list, with what is committed and what is not, is in [section 4](#4-what-gets-installed-and-where).

## Contents

1. [Requirements](#1-requirements)
2. [Install](#2-install)
3. [What the installer asks](#3-what-the-installer-asks)
4. [What gets installed and where](#4-what-gets-installed-and-where)
5. [Check that everything is ready](#5-check-that-everything-is-ready)
6. [Work with the team](#6-work-with-the-team)
7. [Command reference](#7-command-reference)
8. [Update, reconfigure or remove](#8-update-reconfigure-or-remove)
9. [Troubleshooting](#9-troubleshooting)
10. [Developing DeltaForce AI](#10-developing-deltaforce-ai)

## 1. Requirements

On your machine:

| Requirement | Notes |
| --- | --- |
| Windows 10/11 | macOS and Linux are planned |
| [VS Code](https://code.visualstudio.com/) (or another IDE with an integrated terminal) | The whole installation happens in its terminal |
| [Git for Windows](https://git-scm.com/download/win) | Provides the `bash` that runs the installer. Claude Code needs it too |
| [Claude Code](https://code.claude.com/docs) | Checked by the installer, not installed |
| Access to `github.com` | The installer downloads DeltaForce, uv, the Databricks CLI, Python and the AI Dev Kit |

Nothing else: no administrator rights, no global installs. The installer brings its own uv, Databricks CLI and Python.

On Databricks:

| Requirement | Notes |
| --- | --- |
| Access to a workspace | Sign-in through the browser (OAuth), a personal access token or a service principal |
| A SQL warehouse you can use | Chosen from a list during installation |
| An existing dev **catalog** | The installer can create the dev schema(s) in it if you have the `CREATE SCHEMA` privilege |

Where the project should live:

- **Short path** — at most 140 characters, ideally under 100 (e.g. `C:\Users\<you>\Projects\my-project`). Windows limits file paths to 260 characters unless long paths are enabled, and the Python packages installed inside the project are deeply nested.
- **Outside OneDrive** — `.deltaforce/runtime` holds several hundred MB that OneDrive would otherwise sync.

## 2. Install

### Step 1 — Open the project folder in VS Code

**File → Open Folder…** and pick the project folder:

- an existing repository you cloned, or
- a new empty folder (create it from the same dialog) — the installer offers to initialise git.

### Step 2 — Open the integrated terminal

**Terminal → New Terminal**. On Windows VS Code opens PowerShell by default.

### Step 3 — Paste one command and press Enter

Use the line that matches the terminal shown in the terminal panel's drop-down.

The commands are split into short lines on purpose, so they survive copy and paste: paste all the lines at once.

**PowerShell** (VS Code default on Windows):

```powershell
& "$env:ProgramFiles\Git\bin\bash.exe" -c '
d=.deltaforce/framework
u=https://github.com/alessandro9110/deltaforce-ai
test -d $d || git clone -q --depth 1 $u $d
bash $d/install.sh'
```

**Git Bash**:

```bash
d=.deltaforce/framework
u=https://github.com/alessandro9110/deltaforce-ai
test -d $d || git clone -q --depth 1 $u $d
bash $d/install.sh
```

**Command Prompt** cannot take multi-line commands: switch the terminal to PowerShell or Git Bash from the terminal panel's drop-down. (The prompt ends with `>` without `PS` in front: that is Command Prompt.)

The command downloads DeltaForce into `.deltaforce/framework` (the first time) and starts the guided installer. The repository is private: the first time, Git may open a browser window to sign in to GitHub.

From here on, just answer the questions in the terminal. The first run takes a few minutes; later runs reuse what is already installed.

To paste in the terminal use **Ctrl+V** (PowerShell, Command Prompt) or **right-click → Paste** / **Shift+Insert** (Git Bash).

### Installer options

Add options after `install.sh` in the command, e.g. `bash .deltaforce/framework/install.sh --dry-run`:

| Option | Effect |
| --- | --- |
| `--dry-run` | Ask the first questions, print the plan, change nothing |
| `--advanced` | Also ask team options: enabled roles, default model, subagent nesting depth, AI Dev Kit version |
| `--doctor` | Only run the readiness checks (see [section 5](#5-check-that-everything-is-ready)) |
| `-y`, `--yes` | Skip the confirmations |
| `--non-interactive` | Never prompt; reuse the existing configuration (or `DF_*` environment variables) |
| `-h`, `--help` | Show the help |

## 3. What the installer asks

Type the answer and press Enter. When a question shows `[Enter = value]`, just press Enter to accept that value, e.g. `Project name [Enter = my-project]:`. In menus, type the number of an option; where allowed you can also type a value (e.g. a catalog name not shown in the list). Ctrl+C stops the installer at any time without breaking anything.

### Project

1. **Project name** — lowercase letters, digits, `-`, `_`. Defaults to the folder name.
2. **Protected branches** — branches the team never pushes to. Default `main,master`.
3. **Dev branch** — the branch the team works and pushes on. Default `dev`.
4. **CI/CD provider** — Azure DevOps Pipelines, GitHub Actions or none.

### Databricks workspace

1. **Workspace URL** — e.g. `https://adb-1234567890123456.7.azuredatabricks.net`. A URL copied from the browser address bar works too (`...net/?o=123...`): the installer keeps only the host.
2. **CLI profile name** — default `deltaforce-<project>`. `DEFAULT` is not allowed.
3. **Authentication method**:
   - **OAuth** (recommended) — a browser window opens; sign in and return to the terminal.
   - **Personal access token** — typed with hidden input.
   - **Service principal** — client ID and client secret (hidden input).

### Production workspace (optional)

1. **Read data from a separate production workspace?** — answer *Yes* when some source data exists only in production.
2. **Production workspace URL**, **CLI profile name** (default `<dev profile>-prod`) and **authentication method**.

After signing in, the installer also asks for the **production SQL warehouse** used for read queries. On production the team can only read — SQL queries (`SELECT`, `WITH … SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`), model serving and vector search calls, Genie, table statistics — and every access is audited with the role that made it. Everything else is blocked (see [Guardrails](#guardrails)).

The installer then shows the plan and asks **Proceed?**. After that it:

- checks out the dev branch, offering to create it (and to push it when the repository has a remote);
- downloads the tools and signs you in to Databricks.

### Dev target

These lists are read from your workspace:

1. **SQL warehouse**.
2. **Compute** for notebooks and Python code — serverless (recommended) or an existing cluster.
3. **Dev catalog** — from the list, or type its name. It must exist.
4. **Medallion layout**:
   - **One schema** — bronze, silver and gold tables in the same schema, with `bronze_`, `silver_`, `gold_` name prefixes.
   - **One schema per layer** — three schemas.
5. **Schema name(s)** — schemas that do not exist are created by the installer. They are the team's starting point: during the project the team can add the schemas and tables the solution needs inside the dev catalog.

With `--advanced` it also asks the enabled roles, the default model, the maximum subagent nesting depth and the AI Dev Kit version.

Finally it shows a summary and asks **Write this configuration?**, then installs everything, offers to **commit the files it installed** on the dev branch (agents are not allowed to change or commit them) and runs the readiness checks.

## 4. What gets installed and where

Everything lives inside the project repository.

| Path | Content | In git? |
| --- | --- | --- |
| `.deltaforce/framework/` | DeltaForce AI itself (installer, schemas, role catalog) | ignored |
| `.deltaforce/config.yaml` | Your answers. No secrets | committed |
| `.deltaforce/conventions.yaml` | Client conventions, DeltaForce defaults until you change them | committed |
| `.deltaforce/requirements/`, `architecture/`, `backlog/`, `reports/`, `state.yaml`, `events.jsonl` | The team's working documents and progress — request, Functional Analysis, Architecture, features, task reports, PO reports, next steps — created from `/df-kickoff` on | committed |
| `.deltaforce/.databrickscfg` | The Databricks CLI profile (and the token or secret for PAT or service principal). The backup copy the CLI writes (`.databrickscfg.bak`) is deleted by the installer and ignored as well | ignored |
| `.deltaforce/bin/` | uv and the Databricks CLI | ignored |
| `.deltaforce/runtime/` | Python, AI Dev Kit MCP server source and its virtual environment | ignored |
| `.deltaforce/status.json` | Result of the last readiness check | ignored |
| `.deltaforce/bin/df` | Helper the team uses to validate state and log events | ignored |
| `.deltaforce/audit.jsonl` | Audit trail: every Databricks call, shell command and blocked action, with the role that made it | ignored |
| `.deltaforce/runtime/guard-policy.json` | Guardrail rules generated from your configuration | ignored |
| `.deltaforce/runtime/activity.jsonl`, `monitor.json`, `monitor.log` | What the agents are doing, read by the monitor page; the monitor's address and log | ignored |
| `.claude/agents/` | The DeltaForce agents for the enabled roles | committed |
| `.claude/skills/df-*` | Team skills and Product Owner commands | committed |
| `.claude/skills/databricks-*` | Databricks agent skills for the enabled roles | committed |
| `.claude/settings.json` | Team settings: sessions start as the PM, MCP server approval, subagent nesting, worktree base | committed |
| `.claude/settings.local.json` | Points every Databricks command to the project profile, registers the guardrail and audit hooks and the status line with the monitor link | ignored |
| `.mcp.json` | Registers the `databricks` MCP server, and `databricks-prod` when production is configured (absolute paths on this machine) | ignored |
| `CLAUDE.md` | A *DeltaForce project context* block: workspace, warehouse, catalog, schemas, branches | committed |
| `databricks.yml` | Databricks Asset Bundle skeleton, created only if missing | committed |
| `resources/deltaforce.variables.yml` | Bundle variables with the dev values; prod values come from CI/CD | committed |
| `.gitignore` | A managed block ignoring the machine-specific files above | committed |

Content you write yourself in `CLAUDE.md`, `.gitignore` and `.claude/settings.json` is preserved: the installer only rewrites its own blocks and keys.

With OAuth, the Databricks CLI keeps its sign-in tokens in its own cache under your user profile — the only thing outside the project.

## 5. Check that everything is ready

The installer ends with the readiness checks. To run them again, in the VS Code terminal:

| Terminal | Command |
| --- | --- |
| PowerShell | `& "$env:ProgramFiles\Git\bin\bash.exe" -c 'bash .deltaforce/framework/install.sh --doctor'` |
| Command Prompt | `"%ProgramFiles%\Git\bin\bash.exe" -c "bash .deltaforce/framework/install.sh --doctor"` |
| Git Bash | `bash .deltaforce/framework/install.sh --doctor` |

The checks cover the configuration, Claude Code, git and the dev branch, tool versions, the Databricks sign-in, the warehouse (or cluster), the catalog and schemas, the MCP server, the monitor (warning only), the skills, the generated files, and `databricks bundle validate -t dev` (warning only).

- **DeltaForce is ready** — open Claude Code in the project and start with `/df-kickoff` (see [section 6](#6-work-with-the-team)).
- **Not ready yet** — each failed check says what to fix. Fix it and run the checks again. `/df-kickoff` only starts when `.deltaforce/status.json` says `"ready": true`.

## 6. Work with the team

Open the project in VS Code and start Claude Code. Every session in a DeltaForce project starts as the **Project Manager**: it talks to you as the Product Owner and coordinates the other agents.

You talk to the team in plain language and with the Product Owner commands `/df-kickoff`, `/df-status`, `/df-approve`, `/df-changes` and `/df-conventions` — all listed in the [command reference](#7-command-reference).

How a project runs:

1. **Kickoff** — you describe what to build, or what to add or change in an existing project.
2. **As-is analysis — existing projects only** — the PM notices that the repository already contains a project (code, bundle resources, tests, CI/CD) and asks you to confirm. It also asks for your rules on existing data and objects, for example *"existing tables in dev are never dropped; the bronze tables loaded with Auto Loader can be dropped, with their checkpoint, to refresh them"*, and what the team must not touch. Before designing anything, the Solution Architect analyses the codebase and what is deployed on dev (`.deltaforce/architecture/as-is.md`) and the Business Analyst what the solution does for its users (`.deltaforce/requirements/as-is.md`). The conventions and the bundle variables they find come to you for confirmation. From then on the team designs the change, follows your rules, reports every destructive operation and checks that what existed still works.
3. **Discovery and design** — in parallel, the Business Analyst writes the **Functional Analysis** and the Solution Architect the technical discovery; then the Solution Architect writes the **Architecture** document, and together they derive a feature list with dependencies. Both documents are in English and Markdown, versioned, in `.deltaforce/requirements/` and `.deltaforce/architecture/`.
4. **G1** — you approve the design and the feature list, or ask for changes.
5. **Delivery** — features that do not depend on each other are built in parallel, up to three at a time: specialists work in their own branches, the DevOps Engineer integrates and deploys to dev, the QA Engineer tests.
6. **G2** — you validate each feature. Approved features are merged into the dev branch and unblock the features that depend on them. If later you want a delivered feature to work differently, `/df-changes F-001 <how>` opens a change feature: the team designs, builds and tests the change, and you validate it at its own G2.
7. **Handover** — when every feature is done, a person opens the pull request to the protected branch and CI/CD deploys to production.

**See the work in progress.** Until you approve a feature at G2, its code is not in your project folder: the dev branch only holds approved work. The code currently deployed on dev — bundle resources, pipelines, tests of every active feature — is in `.deltaforce/review/`. Add that folder to your VS Code workspace once (**File → Add Folder to Workspace…**) and it stays up to date after every deployment.

**Start fresh at clean points.** The conversation grows with every report, and every step of the PM re-reads it, which costs tokens. After you approve the design (G1) and after an approved feature is merged — when no specialist is still working — the PM tells you everything is saved: run `/clear`, then write *continue*. The team resumes from `.deltaforce/` with a short conversation.

**You can close Claude Code at any time.** Nothing depends on the conversation: the next session starts from `.deltaforce/` — `state.yaml` (phase, next steps, last update), the backlog and the saved task reports — checks unfinished tasks on their branches and continues. `/df-status` shows you the same.

### Watch the team in the browser

The first time the team starts working in a Claude Code session, DeltaForce opens the **monitor** in your default browser. Under the project name it shows a short description of the project, taken from the request recorded at kickoff, and one sentence on what the team is doing. Then it shows what is happening now and what is waiting for you, each agent with what it is doing, and every feature on a board — to do, in progress, waiting for your review, done with its completion date and how long it took. Feature cards say in a line what each feature is; switch the features to **Backlog** for a readable list — description, dependencies, acceptance criteria and the tasks of every feature, filtered by status. Click a task for what the agent was asked, who worked on it and when, and its report. Click a feature for what it is (business value, user stories), its acceptance criteria, its path through the statuses (with the steps back and why), tasks, activity and details, an agent for its tasks and recent actions, **Workflow** for how the work flowed — handoffs between team members, work sent back to be redone, deploys and test runs, phase durations, every time the team needed you (decisions, questions, escalations) and a **Timeline** of who worked when and who asked them — and **Documents** for the Functional Analysis, the Architecture and the reports. Questions and messages to and from you are counted, never recorded.

- It runs on your computer only (`http://127.0.0.1:87xx`, always the same address for a project) and only reads the files in `.deltaforce/`: it uses no tokens and changes nothing. Approvals stay in Claude Code (`/df-approve`, `/df-changes`).
- It updates by itself every few seconds, and stops on its own about half an hour after the last session closes.
- **Always one click away**: the Claude Code status line shows `DeltaForce · Delivery · 1/4 features done · 1 waiting for you · monitor http://127.0.0.1:87xx`. Ctrl+click the link to open the page. A second row lists your commands (`/df-status`, `/df-approve`, `/df-changes`, `/df-conventions`, `/clear`) and, when something waits for you, starts with the one to use, e.g. `Your turn: /df-approve F-004 or /df-changes F-004 <what to change>`. The status line starts the monitor again when it is off and uses no tokens. If `.claude/settings.local.json` already has a status line of your own, DeltaForce keeps yours.
- To open it from a terminal instead, in Git Bash: `bash .deltaforce/bin/df monitor` (PowerShell: `& "$env:ProgramFiles\Git\bin\bash.exe" -c 'bash .deltaforce/bin/df monitor'`).
- To stop it from opening automatically, set the environment variable `DELTAFORCE_MONITOR=off` before starting Claude Code.

The team asks you only at G1, at G2, and when something blocks or changes what you asked for. Everything the team writes to organize itself — request, requirements, design, backlog, reports, state and events — lives in `.deltaforce/`; outside it there is only the product: `src/`, `resources/`, `tests/`, `databricks.yml`.

### Guardrails

Claude Code runs DeltaForce hooks before every action of every agent, also in auto mode. Whatever an agent is asked to do, these actions are blocked:

| Area | Blocked |
| --- | --- |
| Dev workspace | Creating, changing or deleting Databricks resources (jobs, pipelines, dashboards, apps, endpoints, indexes, Unity Catalog objects…) outside the asset bundle; writes outside the dev catalog; SQL writes that do not name the catalog; permission, sharing, connection and storage changes |
| Production workspace | Anything but reads: SQL other than `SELECT`/`WITH … SELECT`/`SHOW`/`DESCRIBE`/`EXPLAIN`, code execution, jobs, pipelines, Unity Catalog changes, any Databricks CLI call to production |
| Deployments | `bundle deploy` and `bundle run` by anyone but the DevOps Engineer or to a target other than dev; `bundle destroy` |
| Git | Pushes to protected branches, force pushes, remote branch deletions, pushing `df/integration`, `reset --hard`, `rebase`, merges into the dev branch by anyone but the DevOps Engineer |
| Files | Changes to anything DeltaForce installed — agents and their roles, DeltaForce and Databricks skills, Claude settings, `.mcp.json`, `CLAUDE.md`, `.gitignore`, generated bundle variables, `.deltaforce/config.yaml`, the framework, tools and runtime — including commits that contain them; changes to the client conventions by anyone but the PM; any access to the credentials file |

A blocked action shows up as `DeltaForce guardrail: <reason>` and is recorded in `.deltaforce/audit.jsonl`. Static deny rules in `.claude/settings.json` back up the hooks, and the readiness checks run a self-test of the guardrails.

## 7. Command reference

### In Claude Code — Product Owner commands

| Command | When |
| --- | --- |
| `/df-kickoff [what to build or change]` | Start the project: the PM checks whether the repository already holds a project, asks what to build or change, known table names, your rules on existing data (existing projects) and the client conventions, then the team starts the analysis and the design |
| `/df-status` | See where the project stands and what is waiting for you |
| `/df-approve` | Approve the design and the feature list (G1) |
| `/df-approve F-001 [notes]` | Approve a delivered feature (G2) |
| `/df-changes [F-001] <what to change>` | Ask for changes: to the design at G1; to a feature under review (it goes back to the team and returns to you); to a feature already done (the team opens a *change feature* linked to it, with its own tasks and G2 — the original keeps its delivery date); or, without a feature id, to the request |
| `/df-conventions [change]` | Show or change the client conventions: bundle deploy folder, naming, tags, code style, rules on existing data, other rules |

The monitor needs no command: it opens by itself when the team starts working, and the link is always in the Claude Code status line (Ctrl+click).

### In the VS Code terminal

The commands below are for **Git Bash**. From **PowerShell** wrap them like this: `& "$env:ProgramFiles\Git\bin\bash.exe" -c '<command>'`. From **Command Prompt**: `"%ProgramFiles%\Git\bin\bash.exe" -c "<command>"`. Run them from the project root.

| Command | What it does |
| --- | --- |
| The command in [Step 3](#step-3--paste-one-command-and-press-enter) | First installation: downloads DeltaForce and starts the guided installer |
| `bash .deltaforce/framework/install.sh` | Update DeltaForce and reinstall, keeping your answers as defaults — with Claude Code closed |
| `bash .deltaforce/framework/install.sh --doctor` | Run the readiness checks only |
| `bash .deltaforce/framework/install.sh --dry-run` | Ask the first questions and print the plan, changing nothing |
| `bash .deltaforce/framework/install.sh --advanced` | Also ask the team options (roles, model, nesting depth, AI Dev Kit version) |
| `bash .deltaforce/framework/install.sh --yes` / `--non-interactive` | Skip the confirmations / never ask, reuse the existing configuration |
| `git -C .deltaforce/framework pull` | Download the latest DeltaForce by hand, when the installer cannot update itself |
| `bash .deltaforce/bin/df monitor` | Start the monitor and open it in the browser (`--no-open` only prints the address) |
| `bash .deltaforce/bin/df validate` | Check that state, backlog, events and conventions are valid |
| `bash .deltaforce/bin/df doctor` | The readiness checks, without going through the installer |
| `bash .deltaforce/bin/df events '[...]'` / `df event <type> --role <role> ...` | Record the lifecycle events of a change (and validate) — used by the team, not needed by you |
| `.deltaforce/bin/databricks <command>` | The project's Databricks CLI, e.g. `.deltaforce/bin/databricks bundle validate -t dev` |

### Environment variables

| Variable | Effect |
| --- | --- |
| `DELTAFORCE_MONITOR=off` | Set before starting Claude Code: the monitor does not start or open by itself, and the status line shows *monitor off* |
| `DF_REPO_URL`, `DF_REF` | Repository and branch the installer downloads DeltaForce from (default: this repository, `main`) |

## 8. Update, reconfigure or remove

**Update or change the configuration** — run the install command from [Step 3](#step-3--paste-one-command-and-press-enter) again. It updates `.deltaforce/framework`, offers your current answers as defaults (press Enter to keep them) and refreshes everything.

> Run it with Claude Code **closed**: it rebuilds the MCP server environment and replaces the agents and skills, which would disrupt a working session.

The installer never touches the team's work: requirements, design, backlog, reports, state, code, tests, bundle resources (except the generated `resources/deltaforce.variables.yml`), `databricks.yml` and `.deltaforce/conventions.yaml` once they exist, and data on Databricks. It replaces only DeltaForce's own files: agents, `df-*` and `databricks-*` skills, and its managed blocks and keys in `CLAUDE.md`, `.gitignore`, `.mcp.json` and the Claude settings.

**Another team member** — after cloning the project (which already contains `.deltaforce/config.yaml`), open it in VS Code and run the same install command: it downloads the framework and tools, signs them in with their own account and regenerates the machine-specific files.

**Remove DeltaForce from a project** (no uninstall option yet). In Git Bash, or wrapped like the commands above:

```bash
rm -rf .deltaforce/framework .deltaforce/bin .deltaforce/runtime .deltaforce/.databrickscfg* .deltaforce/status.json .mcp.json .claude/settings.local.json
```

To remove it completely, also delete `.deltaforce/`, the `.claude/skills/databricks-*` folders, the `deltaforce` blocks in `CLAUDE.md` and `.gitignore`, and `resources/deltaforce.variables.yml`.

## 9. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `...\Git\bin\bash.exe ... is not recognized` / `The system cannot find the path specified` | Git for Windows is missing or installed elsewhere: install it, or replace the path with your `bash.exe` |
| `DeltaForce guardrail: …` in the conversation | An agent tried a blocked action and the reason names the rule. This is expected: the team reports it instead of working around it. If the action is legitimate, a person does it |
| `Could not download https://github.com/...` | Check access to the DeltaForce repository and sign in to GitHub when Git asks |
| `The repository path is N characters and Windows long paths are disabled` | Move the project to a shorter path (≤ 140 characters), or have an administrator enable Windows long paths (`LongPathsEnabled`) |
| `Run the installer from the repository root` | Open the repository's root folder in VS Code, not a subfolder |
| `Could not create the initial commit` | Set your git identity: `git config --global user.name "Your Name"` and `git config --global user.email you@example.com` |
| `Ignoring DATABRICKS_HOST, ...` warning | Remove those variables from your Windows environment: they override the project profile in Claude Code |
| OAuth browser window does not open | Copy the URL printed in the terminal into your browser |
| Authentication check fails | Run the install command again and sign in, or check that your account can access the workspace |
| Catalog or schema check fails | Create them in Databricks (or ask an administrator), or run the installer again and pick existing ones |
| The PM warns that `.deltaforce/.databrickscfg.bak` is not ignored by git | A backup the Databricks CLI wrote during sign-in, left by an older DeltaForce version. Re-run the install command with Claude Code closed: it deletes the backup and ignores such files from then on |
| `Failed to create virtual environment ... Access is denied. (os error 5)` | A program still uses the project's Python — usually an open Claude Code session. Close Claude Code and run the install command again: the installer stops the monitor by itself |
| The monitor page does not open | Run `bash .deltaforce/bin/df monitor` in Git Bash; if it reports an error, look at `.deltaforce/runtime/monitor.log`, then re-run the install command. The page shows *Offline* when the monitor stopped after the sessions closed: it starts again when the team works |
| `databricks bundle validate` warning | Not blocking. Run `.deltaforce/bin/databricks bundle validate -t dev` in Git Bash to see the details |
| Downloads fail | Check access to `github.com`, including through a corporate proxy |

## 10. Developing DeltaForce AI

For contributors to this repository: commands, layout and conventions are in [CLAUDE.md](CLAUDE.md); architecture, process and open items in [docs/design.md](docs/design.md); milestones in [docs/roadmap.md](docs/roadmap.md).
