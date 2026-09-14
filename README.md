# DeltaForce AI

A team of specialized Claude Code agents that design, build, test and deploy on Databricks — data engineering, analytics, data science, ML and GenAI. The human user is the Product Owner; the team is a PM, Solution Architect, Business Analyst, Data Engineer, Data Analyst, Data Scientist, AI Engineer, QA Engineer and DevOps Engineer.

DeltaForce is installed **into a project repository**, from your IDE, with **one command**. A guided installer asks what it needs and keeps everything inside the project: the DeltaForce framework, tools, Python, the Databricks MCP server, agent skills and configuration. Nothing is installed globally.

> **Status**: installer, configuration, the nine agents, the team skills and the Product Owner commands are implemented. Guardrail and audit hooks are next — see [docs/roadmap.md](docs/roadmap.md). Architecture and process: [docs/design.md](docs/design.md).

## Contents

1. [Requirements](#1-requirements)
2. [Install](#2-install)
3. [What the installer asks](#3-what-the-installer-asks)
4. [What gets installed and where](#4-what-gets-installed-and-where)
5. [Check that everything is ready](#5-check-that-everything-is-ready)
6. [Work with the team](#6-work-with-the-team)
7. [Update, reconfigure or remove](#7-update-reconfigure-or-remove)
8. [Troubleshooting](#8-troubleshooting)
9. [Developing DeltaForce AI](#9-developing-deltaforce-ai)

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

**Command Prompt** cannot take multi-line commands: switch the terminal to PowerShell or Git Bash from the terminal panel's drop-down.

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

Finally it shows a summary and asks **Write this configuration?**, then installs everything and runs the readiness checks.

## 4. What gets installed and where

Everything lives inside the project repository.

| Path | Content | In git? |
| --- | --- | --- |
| `.deltaforce/framework/` | DeltaForce AI itself (installer, schemas, role catalog) | ignored |
| `.deltaforce/config.yaml` | Your answers. No secrets | committed |
| `.deltaforce/conventions.yaml` | Client conventions, DeltaForce defaults until you change them | committed |
| `.deltaforce/requirements/`, `architecture/`, `backlog/`, `reports/`, `state.yaml`, `events.jsonl` | The team's working documents and progress — request, requirements, design, features, PO reports — created from `/df-kickoff` on | committed |
| `.deltaforce/.databrickscfg` | The Databricks CLI profile (and the token or secret for PAT or service principal) | ignored |
| `.deltaforce/bin/` | uv and the Databricks CLI | ignored |
| `.deltaforce/runtime/` | Python, AI Dev Kit MCP server source and its virtual environment | ignored |
| `.deltaforce/status.json` | Result of the last readiness check | ignored |
| `.deltaforce/bin/df` | Helper the team uses to validate state and log events | ignored |
| `.claude/agents/` | The DeltaForce agents for the enabled roles | committed |
| `.claude/skills/df-*` | Team skills and Product Owner commands | committed |
| `.claude/skills/databricks-*` | Databricks agent skills for the enabled roles | committed |
| `.claude/settings.json` | Team settings: sessions start as the PM, MCP server approval, subagent nesting, worktree base | committed |
| `.claude/settings.local.json` | Points every Databricks command to the project profile | ignored |
| `.mcp.json` | Registers the `databricks` MCP server for Claude Code (absolute paths on this machine) | ignored |
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

The checks cover the configuration, Claude Code, git and the dev branch, tool versions, the Databricks sign-in, the warehouse (or cluster), the catalog and schemas, the MCP server, the skills, the generated files, and `databricks bundle validate -t dev` (warning only).

- **DeltaForce is ready** — open Claude Code in the project and start with `/df-kickoff` (see [section 6](#6-work-with-the-team)).
- **Not ready yet** — each failed check says what to fix. Fix it and run the checks again. `/df-kickoff` only starts when `.deltaforce/status.json` says `"ready": true`.

## 6. Work with the team

Open the project in VS Code and start Claude Code. Every session in a DeltaForce project starts as the **Project Manager**: it talks to you as the Product Owner and coordinates the other agents.

| Command | When |
| --- | --- |
| `/df-kickoff [what to build]` | Start the project: the PM asks what to build, known table names and the client conventions, then the team starts requirements and design |
| `/df-status` | See where the project stands and what is waiting for you |
| `/df-approve` | Approve the design and the feature list (G1) |
| `/df-approve F-001 [notes]` | Approve a delivered feature (G2) |
| `/df-changes [F-001] <what to change>` | Ask for changes to the design, to a feature, or to the request |
| `/df-conventions [change]` | Show or change the client conventions: bundle deploy folder, naming, tags, code style, other rules |

How a project runs:

1. **Kickoff** — you describe what to build.
2. **Discovery and design** — in parallel, the Business Analyst writes the **Functional Analysis** and the Solution Architect the technical discovery; then the Solution Architect writes the **Architecture** document, and together they derive a feature list with dependencies. Both documents are in English and Markdown, versioned, in `.deltaforce/requirements/` and `.deltaforce/architecture/`.
3. **G1** — you approve the design and the feature list, or ask for changes.
4. **Delivery** — features that do not depend on each other are built in parallel, up to three at a time: specialists work in their own branches, the DevOps Engineer integrates and deploys to dev, the QA Engineer tests.
5. **G2** — you validate each feature. Approved features are merged into the dev branch and unblock the features that depend on them.
6. **Handover** — when every feature is done, a person opens the pull request to the protected branch and CI/CD deploys to production.

The team asks you only at G1, at G2, and when something blocks or changes what you asked for. Everything the team writes to organize itself — request, requirements, design, backlog, reports, state and events — lives in `.deltaforce/`; outside it there is only the product: `src/`, `resources/`, `tests/`, `databricks.yml`.

## 7. Update, reconfigure or remove

**Update or change the configuration** — run the install command from [Step 3](#step-3--paste-one-command-and-press-enter) again. It updates `.deltaforce/framework`, offers your current answers as defaults (press Enter to keep them) and refreshes everything.

> Run it with Claude Code **closed**: it rebuilds the MCP server environment and replaces the agents and skills, which would disrupt a working session.

The installer never touches the team's work: requirements, design, backlog, reports, state, code, tests, bundle resources (except the generated `resources/deltaforce.variables.yml`), `databricks.yml` and `.deltaforce/conventions.yaml` once they exist, and data on Databricks. It replaces only DeltaForce's own files: agents, `df-*` and `databricks-*` skills, and its managed blocks and keys in `CLAUDE.md`, `.gitignore`, `.mcp.json` and the Claude settings.

**Another team member** — after cloning the project (which already contains `.deltaforce/config.yaml`), open it in VS Code and run the same install command: it downloads the framework and tools, signs them in with their own account and regenerates the machine-specific files.

**Remove DeltaForce from a project** (no uninstall option yet). In Git Bash, or wrapped like the commands above:

```bash
rm -rf .deltaforce/framework .deltaforce/bin .deltaforce/runtime .deltaforce/.databrickscfg .deltaforce/status.json .mcp.json .claude/settings.local.json
```

To remove it completely, also delete `.deltaforce/`, the `.claude/skills/databricks-*` folders, the `deltaforce` blocks in `CLAUDE.md` and `.gitignore`, and `resources/deltaforce.variables.yml`.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `...\Git\bin\bash.exe ... is not recognized` / `The system cannot find the path specified` | Git for Windows is missing or installed elsewhere: install it, or replace the path with your `bash.exe` |
| `Could not download https://github.com/...` | Check access to the DeltaForce repository and sign in to GitHub when Git asks |
| `The repository path is N characters and Windows long paths are disabled` | Move the project to a shorter path (≤ 140 characters), or have an administrator enable Windows long paths (`LongPathsEnabled`) |
| `Run the installer from the repository root` | Open the repository's root folder in VS Code, not a subfolder |
| `Could not create the initial commit` | Set your git identity: `git config --global user.name "Your Name"` and `git config --global user.email you@example.com` |
| `Ignoring DATABRICKS_HOST, ...` warning | Remove those variables from your Windows environment: they override the project profile in Claude Code |
| OAuth browser window does not open | Copy the URL printed in the terminal into your browser |
| Authentication check fails | Run the install command again and sign in, or check that your account can access the workspace |
| Catalog or schema check fails | Create them in Databricks (or ask an administrator), or run the installer again and pick existing ones |
| `databricks bundle validate` warning | Not blocking. Run `.deltaforce/bin/databricks bundle validate -t dev` in Git Bash to see the details |
| Downloads fail | Check access to `github.com`, including through a corporate proxy |

## 9. Developing DeltaForce AI

For contributors to this repository: commands, layout and conventions are in [CLAUDE.md](CLAUDE.md); architecture, process and open items in [docs/design.md](docs/design.md); milestones in [docs/roadmap.md](docs/roadmap.md).
