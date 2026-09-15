"use strict";

// DeltaForce monitor page: polls the local server for the project snapshot and renders it. Read-only.

const POLL_MS = 3000;
const LOCALE = "en-GB";
const ROLE_COLORS = {
  pm: "#6b4fb3", "solution-architect": "#2f5fb3", "business-analyst": "#1f8a9a", "data-engineer": "#c0661e",
  "data-analyst": "#2e8a4f", "data-scientist": "#a88414", "ai-engineer": "#b0457c", "qa-engineer": "#b8352b",
  "devops-engineer": "#4d5c6b",
};
const COLUMNS = [["todo", "To do"], ["doing", "In progress"], ["po", "Waiting for you"], ["done", "Done"]];
const EMPTY_COLUMN = {
  todo: "Nothing left to start.",
  doing: "Nothing in progress.",
  po: "Nothing to review.",
  done: "Approved features appear here with their completion date.",
};
const FINISHED_TASKS = ["integrated", "done"];
const isApproved = (feature) => Boolean(feature.po_decision && feature.po_decision.decision === "approved");

const stored = {
  get(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* storage blocked: keep the choice for this page only */ }
  },
};

const requestedView = new URLSearchParams(location.search).get("view"); // e.g. /?view=backlog

const app = {
  snapshot: null, etag: null, online: null, docs: new Map(), loading: new Set(), shown: null,
  featuresView: ["board", "backlog"].includes(requestedView) ? requestedView : stored.get("deltaforce.featuresView", "board"),
  backlogFilter: stored.get("deltaforce.backlogFilter", "all"),
  openBacklog: new Set(),
  waitingOpen: false,
};

const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const roleColor = (role) => ROLE_COLORS[role] || "#66737f";
const joinNames = (names) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

// ─── time ─────────────────────────────────────────────────────

function toDate(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

function when(iso) {
  const date = toDate(iso);
  if (!date) return "";
  const clock = date.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
  if (date.toDateString() === new Date().toDateString()) return clock;
  return `${date.toLocaleDateString(LOCALE, { day: "numeric", month: "short" })} ${clock}`;
}

function day(iso) {
  const date = toDate(iso);
  return date ? date.toLocaleDateString(LOCALE, { day: "numeric", month: "short", year: "numeric" }) : "";
}

function duration(seconds) {
  if (seconds == null) return "";
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return "less than a minute";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 ? `${hours} h ${String(minutes % 60).padStart(2, "0")} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  return hours % 24 ? `${days} d ${hours % 24} h` : `${days} d`;
}

const since = (iso) => (toDate(iso) ? duration((Date.now() - toDate(iso).getTime()) / 1000) : "");

// ─── markdown ─────────────────────────────────────────────────

function inline(text) {
  return String(text)
    .split(/(`[^`]*`)/)
    .map((part, index) => {
      if (index % 2 === 1) return `<code>${esc(part.slice(1, -1))}</code>`;
      return esc(part)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|[\s(])\*([^*\s](?:[^*]*[^*\s])?)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>")
        .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
        .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, "$1")
        .replace(/(^|\s)(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
    })
    .join("");
}

function listHtml(items) {
  let html = "";
  const stack = [];
  for (const item of items) {
    while (stack.length && item.indent < stack[stack.length - 1].indent) html += `</li></${stack.pop().tag}>`;
    const top = stack[stack.length - 1];
    if (!top || item.indent > top.indent) {
      const tag = item.ordered ? "ol" : "ul";
      stack.push({ indent: item.indent, tag });
      html += `<${tag}><li>`;
    } else {
      html += "</li><li>";
    }
    html += inline(item.text);
  }
  while (stack.length) html += `</li></${stack.pop().tag}>`;
  return html;
}

const BLOCK_START = /^(```|#{1,6}\s|\s*([-*+]|\d+[.)])\s+|\s*>|\s*\|.*\|\s*$|\s*(---|\*\*\*|___)\s*$)/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;

function markdown(source) {
  const lines = String(source || "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    if (line.startsWith("```")) {
      const code = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++;
      out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      i++;
      continue;
    }
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { out.push("<hr>"); i++; continue; }
    if (TABLE_ROW.test(line) && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1] || "")) {
      const cells = (row) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
      const head = cells(line);
      const rows = [];
      i += 2;
      while (i < lines.length && TABLE_ROW.test(lines[i])) rows.push(cells(lines[i++]));
      out.push(
        `<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead>` +
          `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      );
      continue;
    }
    if (/^\s*>/.test(line)) {
      const quote = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push(`<blockquote>${markdown(quote.join("\n"))}</blockquote>`);
      continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const items = [];
      while (i < lines.length) {
        const item = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]);
        if (item) {
          items.push({ indent: item[1].replace(/\t/g, "    ").length, ordered: /\d/.test(item[2]), text: item[3] });
          i++;
        } else if (items.length && lines[i].trim() && /^\s+/.test(lines[i])) {
          items[items.length - 1].text += ` ${lines[i].trim()}`;
          i++;
        } else {
          break;
        }
      }
      out.push(listHtml(items));
      continue;
    }
    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !BLOCK_START.test(lines[i])) paragraph.push(lines[i++].trim());
    if (!paragraph.length) paragraph.push(lines[i++].trim());
    out.push(`<p>${inline(paragraph.join(" "))}</p>`);
  }
  return out.join("\n");
}

// ─── main view ────────────────────────────────────────────────

function render() {
  const s = app.snapshot;
  if (!s) return;
  document.title = `${s.project.name} · DeltaForce`;
  $("project").textContent = s.project.name;
  $("phase").textContent = s.phase_label;
  renderLive();

  const kind = s.project.kind === "existing" ? `<span class="chip">Existing project</span> ` : "";
  $("intro").innerHTML =
    (s.project.description ? `<p class="project-description">${esc(s.project.description)}</p>` : "") +
    `<p class="overview">${kind}${esc(s.overview)}</p>`;

  $("now").innerHTML = nowHtml(s);

  const working = s.team.filter((role) => role.status === "working").length;
  $("team-count").textContent = working ? `${working} working` : "Nobody working right now";
  $("team").innerHTML = s.team.map(agentCard).join("");

  const done = s.features.filter((feature) => feature.status === "done").length;
  $("board-count").textContent = s.features.length ? `${done} of ${s.features.length} done` : "";
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === app.featuresView);
    button.setAttribute("aria-selected", String(button.dataset.view === app.featuresView));
  });
  const backlog = app.featuresView === "backlog";
  $("board").className = backlog ? "backlog" : "board";
  $("board").innerHTML = backlog ? backlogHtml(s) : boardHtml(s);

  const problems = $("problems");
  problems.hidden = !s.problems.length;
  problems.textContent = s.problems.length ? `Some files could not be read: ${s.problems.join("; ")}` : "";

  renderDrawer();
}

function renderLive() {
  const live = $("live");
  const s = app.snapshot;
  let state = "offline";
  let text = "Offline";
  let title = "The monitor stopped. It starts again when the team works, or with: bash .deltaforce/bin/df monitor";
  if (app.online) {
    state = s && s.session.open ? "on" : "idle";
    text = s && s.session.open ? "Session open" : "No session open";
    title = s && s.session.last_activity ? `Last team activity ${when(s.session.last_activity)}` : "No team activity recorded yet";
  }
  live.className = `live ${state}`;
  live.title = title;
  live.querySelector("span").textContent = text;
}

function nowHtml(s) {
  let headline;
  let label = "Now";
  if (!s.started) {
    headline = "The team has not started yet. In Claude Code, run <code>/df-kickoff</code> and describe what to build.";
  } else if (s.latest) {
    headline = esc(s.latest.text);
    if (s.latest.ts) label += ` · ${esc(when(s.latest.ts))}`;
  } else {
    headline = "The team is getting started.";
  }
  const next = s.next_steps.find((step) => step.owner !== "po");
  const nextHtml = next
    ? `<p class="next"><span class="label">Next</span>${esc(next.owner_title)}: ${esc(next.action)}</p>`
    : "";

  // A notification: count and short titles; the full requests and commands when expanded.
  const waiting = s.waiting.length
    ? `<details class="po-chip waiting" data-waiting${app.waitingOpen ? " open" : ""}>` +
      `<summary><span class="label">Waiting for you</span><span class="count">${s.waiting.length}</span>` +
      `<span class="titles">${s.waiting.map((item) => esc(item.title || item.text)).join(" · ")}</span></summary>` +
      `<div class="items">${s.waiting
        .map((item) => `<div class="item"><a href="#${esc(item.route || "")}">${esc(item.text)}</a>${item.command ? `<code>${esc(item.command)}</code>` : ""}</div>`)
        .join("")}</div></details>`
    : `<div class="po-chip" title="The team asks you at G1, at G2 and when something blocks."><span class="label">Waiting for you</span><strong>Nothing</strong></div>`;

  return `<div class="text"><span class="label">${label}</span><p class="headline">${headline}</p>${nextHtml}</div>${waiting}`;
}

function agentLine(role) {
  if (role.status === "working") return (role.current && role.current.text) || (role.last_action && role.last_action.text) || "Working";
  if (role.status === "waiting") return `Waiting for ${joinNames(role.waiting_for)}`;
  if (role.next_task) return `Next: ${role.next_task.id} ${role.next_task.title}`;
  if (role.last_action) return `Last: ${role.last_action.text}`;
  return role.involved ? "Idle" : "No tasks yet";
}

function agentCard(role) {
  const classes = ["agent", role.status, role.involved ? "" : "quiet"].join(" ").trim();
  const count = role.instances > 1 ? `<span class="count">×${role.instances}</span>` : "";
  return (
    `<a class="${classes}" href="#agent/${esc(role.id)}">` +
    `<span class="avatar" style="--role:${roleColor(role.id)}">${esc(role.short)}</span>` +
    `<span class="name"><i class="pip"></i>${esc(role.title)}${count}</span>` +
    `<span class="doing">${esc(agentLine(role))}</span></a>`
  );
}

function boardHtml(s) {
  if (!s.features.length) {
    return `<p class="empty wide">${s.started ? "Features appear here once the team breaks the design down." : "Features appear here after kickoff and design."}</p>`;
  }
  return COLUMNS.map(([key, label]) => {
    const items = s.features.filter((feature) => feature.column === key);
    if (key === "done") items.sort((a, b) => String(b.completed || "").localeCompare(String(a.completed || "")));
    const body = items.length ? items.map(featureCard).join("") : `<p class="empty">${EMPTY_COLUMN[key]}</p>`;
    return `<div class="col ${key}"><div class="col-head"><h3>${label}</h3><span>${items.length}</span></div>${body}</div>`;
  }).join("");
}

function progressHtml(feature) {
  const total = feature.tasks.length;
  const percent = total ? Math.round((100 * feature.tasks_done) / total) : 0;
  return (
    `<span class="progress"><span class="row"><span>${feature.tasks_done} of ${total} tasks</span>` +
    `<span>${feature.started ? `started ${esc(when(feature.started))}` : ""}</span></span>` +
    `<span class="track"><b style="width:${percent}%"></b></span></span>`
  );
}

function featureCard(feature) {
  let middle = "";
  let foot = "";
  if (feature.column === "todo") {
    middle = feature.status === "blocked"
      ? `<span class="chip bad">Blocked</span>`
      : `<span class="sub">${feature.blocked_by.length ? `After ${esc(feature.blocked_by.join(", "))}` : "Ready to start"}</span>`;
  } else if (feature.column === "doing") {
    middle = `<span class="chip stage">${esc(feature.status_label)}</span>`;
    foot = progressHtml(feature);
  } else if (feature.column === "po") {
    middle = isApproved(feature) ? `<span class="chip ok">Approved · closing</span>` : `<span class="chip po">Your review</span>`;
    foot = progressHtml(feature);
  } else {
    const cycle = feature.cycle_seconds != null ? ` · took ${esc(duration(feature.cycle_seconds))}` : "";
    foot = `<span class="sub">${feature.completed ? `Completed ${esc(day(feature.completed))}${cycle}` : "Completed"}</span>`;
  }
  const description = feature.description ? `<span class="card-desc">${esc(feature.description)}</span>` : "";
  return (
    `<a class="card${feature.column === "doing" ? " active" : ""}" href="#feature/${esc(feature.id)}">` +
    `<span class="fid">${esc(feature.id)}</span><h4>${esc(feature.title)}</h4>${changeChip(feature)}${description}${middle}${foot}</a>`
  );
}

// ─── backlog ──────────────────────────────────────────────────

const BACKLOG_FILTERS = [["all", "All"], ["doing", "In progress"], ["po", "Waiting for you"], ["todo", "To do"], ["done", "Done"]];
const COLUMN_ORDER = { doing: 0, po: 1, todo: 2, done: 3 };

function changeChip(feature) {
  return feature.change_of ? `<span class="chip change">Change to ${esc(feature.change_of)}</span>` : "";
}

function statusChip(feature) {
  const tone = { done: "ok", po: "po", doing: "stage" }[feature.column] || (feature.status === "blocked" ? "bad" : "");
  const label = feature.column === "po" && isApproved(feature) ? "Approved · closing" : feature.status_label;
  return `<span class="chip ${tone}">${esc(label)}</span>`;
}

function criteriaLabel(count) {
  return `${count} acceptance ${count === 1 ? "criterion" : "criteria"}`;
}

function tasksTable(tasks) {
  return (
    `<div class="table-wrap"><table class="grid tasks-table"><thead><tr><th>Task</th><th>What</th><th>Who</th><th>Status</th><th>Report</th></tr></thead><tbody>` +
    tasks.map((task) =>
      `<tr class="${esc(task.status)}"><td><a class="mono" href="#task/${esc(task.id)}">${esc(task.id)}</a></td>` +
      `<td class="wrap"><a class="plain" href="#task/${esc(task.id)}">${esc(task.title)}</a></td>` +
      `<td>${task.role ? roleBadge(task.role) : "—"}</td><td><i class="state-dot"></i>${esc(task.status_label)}</td>` +
      `<td>${task.report ? `<a href="#doc/${esc(task.report)}">report</a>` : "—"}</td></tr>`).join("") +
    `</tbody></table></div>`
  );
}

function backlogItem(feature) {
  const dependencies = feature.depends_on.length
    ? `Depends on ${feature.depends_on.map((id) => `<a href="#feature/${esc(id)}">${esc(id)}</a>`).join(", ")}${feature.column === "todo" && feature.blocked_by.length ? " (not done yet)" : ""}`
    : "No dependencies";
  const meta = [
    dependencies,
    feature.criteria_count ? criteriaLabel(feature.criteria_count) : "",
    feature.tasks.length ? `${feature.tasks_done} of ${feature.tasks.length} tasks done` : "no tasks yet",
    feature.completed ? `completed ${esc(day(feature.completed))}` : feature.started ? `started ${esc(when(feature.started))}` : "",
  ].filter(Boolean).join(" · ");
  const tasks = feature.tasks.length
    ? `<details data-feature="${esc(feature.id)}"${app.openBacklog.has(feature.id) ? " open" : ""}><summary>${plural(feature.tasks.length, "task")}</summary>${tasksTable(feature.tasks)}</details>`
    : "";
  return (
    `<article class="backlog-item"><div class="backlog-head"><a class="fid" href="#feature/${esc(feature.id)}">${esc(feature.id)}</a>` +
    `<a class="backlog-title" href="#feature/${esc(feature.id)}">${esc(feature.title)}</a>${changeChip(feature)}${statusChip(feature)}</div>` +
    (feature.description ? `<p class="card-desc">${esc(feature.description)}</p>` : "") +
    `<div class="backlog-meta">${meta}</div>${tasks}</article>`
  );
}

function backlogHtml(s) {
  if (!s.features.length) {
    return `<p class="empty">${s.started ? "Features appear here once the team breaks the design down." : "Features appear here after kickoff and design."}</p>`;
  }
  const filters = `<div class="filters">${BACKLOG_FILTERS.map(([key, label]) => {
    const count = key === "all" ? s.features.length : s.features.filter((feature) => feature.column === key).length;
    return `<button type="button" data-filter="${key}" class="${app.backlogFilter === key ? "active" : ""}">${label} <span>${count}</span></button>`;
  }).join("")}</div>`;
  const items = s.features
    .filter((feature) => app.backlogFilter === "all" || feature.column === app.backlogFilter)
    .sort((a, b) => COLUMN_ORDER[a.column] - COLUMN_ORDER[b.column] || a.id.localeCompare(b.id));
  return filters + (items.length ? items.map(backlogItem).join("") : `<p class="empty">No features here.</p>`);
}

// ─── drawer ───────────────────────────────────────────────────

function currentRoute() {
  const hash = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  const [kind, ...rest] = hash.split("/");
  return { kind: kind || "", id: rest.join("/") };
}

function closeDrawer() {
  if (location.hash) location.hash = "";
}

function drawerHead(eyebrow, title, back) {
  const backLink = back ? `<a class="back" href="#${esc(back.route)}">← ${esc(back.label)}</a>` : "";
  return (
    `<div class="drawer-head"><div>${backLink}<span class="label">${eyebrow}</span><h2>${title}</h2></div>` +
    `<a class="close" href="#" aria-label="Close">×</a></div>`
  );
}

function timelineHtml(items) {
  return `<ol class="timeline">${items
    .map((item) => `<li class="${esc(item.tone || "info")}"><time>${esc(when(item.ts))}</time><i></i><span>${esc(item.text)}</span></li>`)
    .join("")}</ol>`;
}

function roleBadge(roleId) {
  const role = app.snapshot.team.find((item) => item.id === roleId);
  const short = role ? role.short : String(roleId || "?").slice(0, 2).toUpperCase();
  return `<a class="mini-avatar" href="#agent/${esc(roleId)}" title="${esc(role ? role.title : roleId)}" style="--role:${roleColor(roleId)}">${esc(short)}</a>`;
}

function featureDrawer(feature) {
  const decision = feature.po_decision;
  const facts = [
    ["Status", `<span class="chip ${feature.column === "done" ? "ok" : feature.column === "po" ? "po" : feature.status === "blocked" ? "bad" : "stage"}">${esc(feature.status_label)}</span>`],
    ["Depends on", feature.depends_on.length
      ? feature.depends_on.map((id) => `<a href="#feature/${esc(id)}">${esc(id)}</a>`).join(", ")
      : "Nothing"],
    ["Branch", feature.branch ? `<span class="mono">${esc(feature.branch)}</span>` : "—"],
    ["Started", feature.started ? esc(when(feature.started)) : "Not yet"],
    ["Completed", feature.completed
      ? `${esc(when(feature.completed))}${feature.cycle_seconds != null ? ` · took ${esc(duration(feature.cycle_seconds))}` : ""}`
      : "—"],
  ];
  const featureLinks = (ids) => ids.map((id) => `<a href="#feature/${esc(id)}">${esc(id)}</a>`).join(", ");
  if (feature.change_of) facts.splice(1, 0, ["Changes", `${featureLinks([feature.change_of])}, already delivered`]);
  if (feature.changed_by.length) facts.push(["Changed later by", featureLinks(feature.changed_by)]);
  if (decision) {
    const notes = decision.notes ? `<br><span class="muted">${esc(decision.notes)}</span>` : "";
    facts.push(["Your decision", `${decision.decision === "approved" ? "Approved" : "Changes requested"} · ${esc(when(decision.at))}${notes}`]);
  }

  const reportLink = feature.review_report ? ` · <a href="#doc/${esc(feature.review_report)}">Read the review report</a>` : "";
  let review = "";
  if (feature.status === "awaiting_po" && isApproved(feature)) {
    review = `<div class="callout ok"><strong>You approved it.</strong> The DevOps Engineer is merging it into the dev branch.${reportLink}</div>`;
  } else if (feature.status === "awaiting_po") {
    review = `<div class="callout po"><strong>Waiting for your review.</strong> In Claude Code: <code>/df-approve ${esc(feature.id)}</code> or ` +
      `<code>/df-changes ${esc(feature.id)} …</code>${reportLink}</div>`;
  }

  const tasks = feature.tasks.length
    ? `<ul class="tasks">${feature.tasks
        .map((task) =>
          `<li class="task ${esc(task.status)}"><i class="state"></i><a class="mono" href="#task/${esc(task.id)}">${esc(task.id)}</a>` +
          `<span class="task-title"><a class="plain" href="#task/${esc(task.id)}">${esc(task.title)}</a>${task.branch ? `<span class="mono muted small">${esc(task.branch)}</span>` : ""}</span>` +
          `${roleBadge(task.role)}<span class="task-status">${esc(task.status_label)}` +
          `${task.report ? ` · <a href="#doc/${esc(task.report)}">report</a>` : ""}</span></li>`)
        .join("")}</ul>`
    : `<p class="muted">No tasks yet.</p>`;

  const activity = feature.events.length ? timelineHtml(feature.events.slice(0, 40)) : `<p class="muted">No activity recorded yet.</p>`;

  const section = (key) => (feature.sections.find((item) => item.key === key) || {}).markdown || "";
  const value = section("business value");
  const stories = section("user stories") || section("user story");
  const criteria = section("acceptance criteria");
  const references = section("design references");
  const log = section("log");
  const known = new Set(["business value", "user stories", "user story", "acceptance criteria", "design references", "log"]);
  const others = feature.sections.filter((item) => !known.has(item.key) && item.markdown);
  const what = value || stories
    ? `<h3 class="drawer-section">What it is</h3><article class="md">${markdown(value)}${stories ? markdown(`### User stories\n\n${stories}`) : ""}</article>`
    : "";

  return (
    drawerHead(esc(feature.id), esc(feature.title)) +
    review +
    (feature.description && !what ? `<p class="description">${esc(feature.description)}</p>` : "") +
    `<dl class="facts">${facts.map(([key, val]) => `<dt>${key}</dt><dd>${val}</dd>`).join("")}</dl>` +
    what +
    (criteria ? `<h3 class="drawer-section">Acceptance criteria <span class="muted">${criteriaLabel(feature.criteria_count)}</span></h3><article class="md">${markdown(criteria)}</article>` : "") +
    evidenceHtml(feature) +
    `<h3 class="drawer-section">Tasks <span class="muted">${feature.tasks_done} of ${feature.tasks.length} done</span></h3>${tasks}` +
    flowHtml(feature.flow) +
    `<h3 class="drawer-section">Activity</h3>${activity}` +
    others.map((item) => `<h3 class="drawer-section">${esc(item.title || "Notes")}</h3><article class="md">${markdown(item.markdown)}</article>`).join("") +
    (references ? `<h3 class="drawer-section">Design references</h3><article class="md">${markdown(references)}</article>` : "") +
    (log ? `<details class="log"><summary>Log</summary><article class="md">${markdown(log)}</article></details>` : "")
  );
}

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

function countLabel(count, noun) {
  if (!count || !count.total) return "";
  const failed = count.failed ? ` · <span class="warn-text">${count.failed} failed</span>` : "";
  return `${count.passed} of ${plural(count.total, noun)} passed${failed}`;
}

function evidenceHtml(feature) {
  const evidence = feature.evidence;
  const runs = feature.flow ? feature.flow.tests.passed + feature.flow.tests.failed : 0;
  if (!evidence) {
    if (!runs) return "";
    const failed = feature.flow.tests.failed ? ` (${feature.flow.tests.failed} failed)` : "";
    return `<h3 class="drawer-section">Test evidence</h3><p class="muted">${plural(runs, "test run")} so far${failed}. The table of tests per acceptance criterion appears when the PM writes the review report.</p>`;
  }
  const source = feature.review_report ? ` · <a href="#doc/${esc(feature.review_report)}">from the review report</a>` : "";
  let html = "";
  if (evidence.tests) {
    html += `<h3 class="drawer-section">Test evidence <span class="muted">${countLabel(evidence.tests_count, "test")}${source}</span></h3><article class="md">${markdown(evidence.tests)}</article>`;
  }
  if (evidence.regression) {
    html += `<h3 class="drawer-section">Regression checks <span class="muted">${countLabel(evidence.regression_count, "check")}</span></h3><article class="md">${markdown(evidence.regression)}</article>`;
  }
  if (evidence.destructive) {
    html += `<h3 class="drawer-section">Destructive operations</h3><article class="md">${markdown(evidence.destructive)}</article>`;
  }
  return html;
}

function flowHtml(flow) {
  if (!flow) return "";
  const path = `<ol class="path">${flow.path
    .map((step) =>
      `<li class="${step.back ? "back" : ""}"${step.cause ? ` title="${esc(step.cause)}"` : ""}>` +
      `<span>${step.back ? "↺ " : ""}${esc(step.label)}</span>${step.ts ? `<small>${esc(when(step.ts))}</small>` : ""}</li>`)
    .join("")}</ol>`;
  const deploys = flow.deploys.ok + flow.deploys.failed;
  const tests = flow.tests.passed + flow.tests.failed;
  const summary = [
    flow.loops ? `<strong class="warn-text">${plural(flow.loops, "step")} back</strong>` : "no steps back",
    deploys ? `${plural(deploys, "deploy")}${flow.deploys.failed ? ` (${flow.deploys.failed} failed)` : ""}` : "",
    tests ? `${plural(tests, "test run")}${flow.tests.failed ? ` (${flow.tests.failed} failed)` : ""}` : "",
    flow.po_decisions ? plural(flow.po_decisions, "decision") + " by you" : "",
  ].filter(Boolean).join(" · ");
  const causes = flow.path.filter((step) => step.back);
  const causeList = causes.length
    ? `<ul class="causes">${causes.map((step) => `<li>↺ ${esc(step.label)} · ${esc(when(step.ts))} — ${esc(step.cause)}</li>`).join("")}</ul>`
    : "";
  return `<h3 class="drawer-section">Flow <span class="muted">${summary}</span></h3>${path}${causeList}`;
}

function workflowDrawer(s) {
  const flow = s.workflow;
  const counts = flow.counts;
  const tile = (value, label, sub, tone) =>
    `<div class="tile ${tone || ""}"><strong>${esc(value)}</strong><span class="label">${esc(label)}</span>` +
    `${sub ? `<span class="muted small">${esc(sub)}</span>` : ""}</div>`;
  const deploys = counts.deploys.ok + counts.deploys.failed;
  const tests = counts.tests.passed + counts.tests.failed;
  const tiles =
    `<div class="tiles">` +
    tile(counts.handoffs, "Handoffs", "work passed between team members") +
    tile(counts.loops, "Steps back", counts.loops ? "work sent back to be redone" : "nothing sent back", counts.loops ? "warn" : "") +
    tile(deploys ? `${counts.deploys.ok}/${deploys}` : "0", "Deploys ok", counts.deploys.failed ? `${counts.deploys.failed} failed` : "none failed", counts.deploys.failed ? "warn" : "") +
    tile(tests ? `${counts.tests.passed}/${tests}` : "0", "Test runs passed", counts.tests.failed ? `${counts.tests.failed} failed` : "none failed", counts.tests.failed ? "warn" : "") +
    tile(counts.po.total, "Your involvement", `${plural(counts.po.gates, "decision")} · ${plural(counts.po.questions, "question")} · ${plural(counts.po.escalations, "escalation")}`, "po") +
    tile(counts.changes_after_delivery || 0, "Changes after delivery", "features done that you asked to change") +
    `</div>`;

  const phases = flow.phases.length
    ? `<ul class="rows">${flow.phases
        .map((phase) => {
          const start = toDate(phase.start);
          const end = phase.end ? toDate(phase.end) : null;
          const length = start ? duration(((end ? end.getTime() : Date.now()) - start.getTime()) / 1000) : "";
          return `<li><span>${esc(phase.label)}</span><span class="muted">${esc(when(phase.start))}</span><span>${esc(length)}${end ? "" : " so far"}</span></li>`;
        })
        .join("")}</ul>`
    : `<p class="muted">The project has not started yet.</p>`;

  const featureLink = (id) => (id ? `<a href="#feature/${esc(id)}">${esc(id)}</a>: ` : "");
  const loops = flow.loops.length
    ? `<ol class="timeline">${flow.loops
        .map((loop) => `<li class="bad"><time>${esc(when(loop.ts))}</time><i></i><span>${featureLink(loop.feature)}${esc(loop.text)} — ${esc(loop.cause)}</span></li>`)
        .join("")}</ol>`
    : `<p class="muted">No work was sent back.</p>`;

  const handoffs = flow.handoffs.length
    ? `<div class="table-wrap"><table class="grid"><thead><tr><th>From</th><th>To</th><th>Times</th><th>Outcome</th></tr></thead><tbody>${flow.handoffs
        .map((item) => {
          const outcome = [item.done ? `${item.done} done` : "", item.not_done ? `<span class="warn-text">${item.not_done} blocked</span>` : ""].filter(Boolean).join(" · ");
          return `<tr><td>${roleBadge(item.from)} ${esc(item.from_title)}</td><td>${roleBadge(item.to)} ${esc(item.to_title)}</td>` +
            `<td class="num">${item.count}</td><td>${outcome || "—"}</td></tr>`;
        })
        .join("")}</tbody></table></div>`
    : `<p class="muted">No handoffs recorded yet.</p>`;

  const involvement = flow.po.length
    ? `<ol class="timeline">${flow.po
        .map((item) => `<li class="${item.kind === "escalation" ? "bad" : "po"}"><time>${esc(when(item.ts))}</time><i></i><span>${featureLink(item.feature)}${esc(item.text)}</span></li>`)
        .join("")}</ol>`
    : `<p class="muted">The team has not needed you yet.</p>`;

  return (
    drawerHead("Workflow", "How the work flowed") +
    workflowTabs("summary") +
    tiles +
    `<h3 class="drawer-section">Phases</h3>${phases}` +
    `<h3 class="drawer-section">Steps back <span class="muted">work sent back to be redone</span></h3>${loops}` +
    `<h3 class="drawer-section">Handoffs <span class="muted">who passed work to whom</span></h3>${handoffs}` +
    `<h3 class="drawer-section">Your involvement <span class="muted">${plural(counts.po.messages, "message")} from you in total</span></h3>${involvement}`
  );
}

function workflowTabs(active) {
  return `<nav class="tabs"><a class="${active === "summary" ? "active" : ""}" href="#workflow">Summary</a>` +
    `<a class="${active === "timeline" ? "active" : ""}" href="#workflow/timeline">Timeline</a></nav>`;
}

const LANES = [
  "pm", "solution-architect", "business-analyst", "data-engineer", "data-analyst", "data-scientist",
  "ai-engineer", "qa-engineer", "devops-engineer",
];
const IDLE_GAP_MS = 30 * 60 * 1000;
const GAP_PX = 34;

function timelineDrawer(s) {
  const { runs, markers } = s.workflow.timeline;
  const head = drawerHead("Workflow", "Who worked when") + workflowTabs("timeline");
  if (!runs.length && !markers.length) return `${head}<p class="muted">No work recorded yet.</p>`;

  const now = Date.now();
  const ms = (iso) => (toDate(iso) ? toDate(iso).getTime() : null);
  const spans = [
    ...runs.map((r) => [ms(r.start), r.end ? ms(r.end) : r.running ? now : ms(r.start) + 60000]),
    ...markers.map((m) => [ms(m.ts), ms(m.ts)]),
  ].filter(([a, b]) => a != null && b != null).sort((a, b) => a[0] - b[0]);

  // Active periods; idle stretches longer than 30 minutes (nights, pauses) collapse into a short break.
  const segments = [];
  for (const [a, b] of spans) {
    const last = segments[segments.length - 1];
    if (last && a - last.end <= IDLE_GAP_MS) last.end = Math.max(last.end, b);
    else segments.push({ start: a, end: Math.max(a, b) });
  }
  const minutes = segments.reduce((sum, seg) => sum + (seg.end - seg.start) / 60000, 0) || 1;
  const pxPerMin = Math.min(14, Math.max(3, 1500 / minutes));
  let offset = 0;
  for (const seg of segments) {
    seg.x = offset;
    seg.width = Math.max(8, ((seg.end - seg.start) / 60000) * pxPerMin);
    offset += seg.width + GAP_PX;
  }
  const width = Math.max(offset - GAP_PX, 200) + 24;
  const x = (t) => {
    let seg = segments[0];
    for (const candidate of segments) if (candidate.start <= t) seg = candidate;
    return seg.x + (Math.min(Math.max(t, seg.start), seg.end) - seg.start) / 60000 * pxPerMin;
  };

  const lanes = [...LANES, ...new Set(runs.map((r) => r.role).filter((role) => !LANES.includes(role)))]
    .filter((lane) => runs.some((r) => r.role === lane) || markers.some((m) => m.lane === lane));
  if (markers.some((m) => m.lane === "po")) lanes.push("po");

  const axis = segments.map((seg, index) => {
    const gap = index > 0 ? `<span class="gap" style="left:${seg.x - GAP_PX / 2 - 8}px" title="idle">⋯</span>` : "";
    return `${gap}<span class="tick" style="left:${seg.x}px">${esc(when(new Date(seg.start).toISOString()))}</span>`;
  }).join("");

  const rows = lanes.map((lane) => {
    const role = s.team.find((item) => item.id === lane);
    const label = lane === "po" ? "You" : role ? role.title : (runs.find((r) => r.role === lane) || {}).role_title || lane;
    const bars = runs.filter((r) => r.role === lane).map((r) => {
      const left = x(ms(r.start));
      const right = r.end ? x(ms(r.end)) : r.running ? x(now) : left + 6;
      const length = r.end ? duration((ms(r.end) - ms(r.start)) / 1000) : r.running ? `running for ${since(r.start)}` : "";
      const tip = `${r.from_title} → ${r.role_title}: ${r.summary || "task"} · ${when(r.start)}${length ? ` · ${length}` : ""}${r.result ? ` · ${r.result}` : ""}`;
      const tone = ["blocked", "failed", "needs-decision"].includes(String(r.result)) ? " bad" : "";
      const tag = r.feature ? "a" : "span";
      const href = r.feature ? ` href="#feature/${esc(r.feature)}"` : "";
      return `<${tag}${href} class="bar${r.running ? " running" : ""}${tone}" style="left:${left}px;width:${Math.max(6, right - left)}px;--role:${roleColor(lane)}" title="${esc(tip)}"></${tag}>`;
    }).join("");
    const dots = markers.filter((m) => m.lane === lane).map((m) =>
      `<span class="mark ${esc(m.tone)}" style="left:${x(ms(m.ts)) - 5}px" title="${esc(`${when(m.ts)} · ${m.text}`)}"></span>`).join("");
    return `<div class="lane"><span class="lane-label">${esc(label)}</span><div class="lane-track" style="width:${width}px">${bars}${dots}</div></div>`;
  }).join("");

  const list = runs.slice().reverse().map((r) => {
    const length = r.end ? duration((ms(r.end) - ms(r.start)) / 1000) : r.running ? "running" : "";
    const result = r.result ? ` · ${["blocked", "failed", "needs-decision"].includes(String(r.result)) ? `<span class="warn-text">${esc(r.result)}</span>` : esc(r.result)}` : "";
    const feature = r.feature ? ` · <a href="#feature/${esc(r.feature)}">${esc(r.feature)}</a>` : "";
    return `<li><time>${esc(when(r.start))}</time><span class="who-line">${roleBadge(r.from)}<span class="arrow">→</span>${roleBadge(r.role)}</span>` +
      `<span>${esc(r.summary || `${r.role_title}`)}<small class="muted"> ${esc(length)}${result}${feature}</small></span></li>`;
  }).join("");

  return (
    head +
    `<p class="muted small">Each bar is a team member working on a delegation; hover for who asked and the result. Dots: your decisions and questions, deploys, test runs, work sent back. Idle stretches are shortened (⋯).</p>` +
    `<div class="gantt"><div class="lane axis"><span class="lane-label"></span><div class="lane-track" style="width:${width}px">${axis}</div></div>${rows}</div>` +
    `<h3 class="drawer-section">Handoffs in order <span class="muted">newest first</span></h3><ol class="handoff-list">${list}</ol>`
  );
}

function taskDrawer(s, id) {
  const feature = s.features.find((item) => item.tasks.some((task) => task.id === id));
  if (!feature) return `${drawerHead("Task", esc(id))}<p class="muted">This task is not in the backlog.</p>`;
  const task = feature.tasks.find((item) => item.id === id);
  const role = s.team.find((item) => item.id === task.role);
  const facts = [
    ["Status", `<span class="chip ${["integrated", "done"].includes(task.status) ? "ok" : task.status === "blocked" ? "bad" : task.status === "todo" ? "" : "stage"}">${esc(task.status_label)}</span>`],
    ["Feature", `<a href="#feature/${esc(feature.id)}">${esc(feature.id)}</a> ${esc(feature.title)}`],
    ["Who", task.role ? `${roleBadge(task.role)} ${esc(role ? role.title : task.role)}` : "—"],
    ["Branch", task.branch ? `<span class="mono">${esc(task.branch)}</span>` : "—"],
  ];

  const asked = [...new Set(task.runs.map((item) => item.summary).filter(Boolean))];
  const askedHtml = asked.length
    ? `<ul class="causes">${asked.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>`
    : `<p class="muted">No delegation recorded for this task yet.</p>`;

  const runs = task.runs.length
    ? `<ol class="handoff-list">${task.runs.slice().reverse().map((item) => {
        const length = item.end ? duration((toDate(item.end) - toDate(item.start)) / 1000) : item.running ? "running" : "";
        const result = item.result ? ` · ${["blocked", "failed", "needs-decision"].includes(String(item.result)) ? `<span class="warn-text">${esc(item.result)}</span>` : esc(item.result)}` : "";
        return `<li><time>${esc(when(item.start))}</time><span class="who-line">${roleBadge(item.from)}<span class="arrow">→</span>${roleBadge(item.role)}</span>` +
          `<span>${esc(item.from_title)} asked ${esc(item.role_title)}<small class="muted"> ${esc(length)}${result}</small></span></li>`;
      }).join("")}</ol>`
    : `<p class="muted">Nobody has worked on it yet.</p>`;

  let report = `<p class="muted">No report saved for this task yet.</p>`;
  if (task.report) {
    const cached = app.docs.get(task.report);
    if (!cached) {
      loadDocument(task.report);
      report = `<p class="muted">Loading…</p>`;
    } else if (cached.error) {
      report = `<p class="muted">The report ${esc(task.report)} cannot be shown.</p>`;
    } else {
      report = `<article class="md">${markdown(cached.text)}</article>`;
    }
  }

  return (
    drawerHead(`Task · ${esc(feature.id)}`, `${esc(task.id)} ${esc(task.title)}`, { route: `feature/${feature.id}`, label: `${feature.id} ${feature.title}` }) +
    `<dl class="facts">${facts.map(([key, val]) => `<dt>${key}</dt><dd>${val}</dd>`).join("")}</dl>` +
    `<h3 class="drawer-section">What was asked</h3>${askedHtml}` +
    `<h3 class="drawer-section">Work <span class="muted">who worked on it, when, and the result</span></h3>${runs}` +
    `<h3 class="drawer-section">Report</h3>${report}`
  );
}

// ─── usage ────────────────────────────────────────────────────

const compact = (value) => {
  const number = Number(value) || 0;
  if (number >= 1e6) return `${(number / 1e6).toFixed(number >= 1e7 ? 0 : 1)} M`;
  if (number >= 1e3) return `${Math.round(number / 1e3)} k`;
  return String(Math.round(number));
};

function money(value, currency) {
  if (value == null || !currency) return "";
  return `${value.toFixed(value < 10 ? 2 : 0)} ${currency}`;
}

async function loadUsage() {
  if (app.usageLoading) return;
  app.usageLoading = true;
  try {
    const response = await fetch("/api/usage", { cache: "no-store" });
    app.usage = response.ok ? await response.json() : { available: false };
  } catch {
    app.usage = { available: false };
  } finally {
    app.usageLoading = false;
    app.usageLoaded = Date.now();
    renderDrawer();
  }
}

function usageTable(rows, label, name, u) {
  const total = u.total.weighted || 1;
  const cost = u.currency ? "<th>Cost</th>" : "";
  return (
    `<div class="table-wrap"><table class="grid usage-table"><thead><tr><th>${label}</th><th>Runs</th><th>Calls</th><th>Output</th><th>Cache read</th><th>Weighted</th>${cost}<th>Share</th></tr></thead><tbody>` +
    rows.map((row) => {
      const share = (100 * row.weighted) / total;
      return `<tr><td class="wrap">${name(row)}</td><td class="num">${row.runs || "—"}</td><td class="num">${row.calls}</td>` +
        `<td class="num">${compact(row.output_tokens)}</td><td class="num">${compact(row.cache_read_input_tokens)}</td>` +
        `<td class="num">${compact(row.weighted)}</td>${u.currency ? `<td class="num">${esc(money(row.cost, u.currency)) || "—"}</td>` : ""}` +
        `<td><span class="share"><b style="width:${share.toFixed(1)}%"></b></span><span class="num small">${share.toFixed(0)}%</span></td></tr>`;
    }).join("") +
    `</tbody></table></div>`
  );
}

function usageDrawer(s) {
  if (!app.usage || Date.now() - (app.usageLoaded || 0) > 15000) loadUsage();
  const head = drawerHead("Usage", "Tokens the team used");
  const u = app.usage;
  if (!u) return `${head}<p class="muted">Reading the Claude Code session files…</p>`;
  if (!u.available) {
    return `${head}<p class="muted">No Claude Code session files for this project on this computer yet${u.folder ? ` (${esc(u.folder)})` : ""}. The numbers appear after the team has worked here.</p>`;
  }
  const t = u.total;
  const tile = (value, label, sub) => `<div class="tile"><strong>${esc(value)}</strong><span class="label">${esc(label)}</span>${sub ? `<span class="muted small">${esc(sub)}</span>` : ""}</div>`;
  const agents = u.sessions.reduce((sum, session) => sum + session.agents, 0);
  const peak = Math.max(0, ...u.sessions.map((session) => session.pm_peak_context));
  const tiles =
    `<div class="tiles">` +
    tile(compact(t.weighted), "Weighted tokens", "input-equivalent: cache read ×0.1, cache write ×1.25, output ×5") +
    (u.currency ? tile(money(t.cost, u.currency), "Estimated cost", "from .deltaforce/pricing.yaml") : "") +
    tile(compact(t.output_tokens), "Output tokens", `${compact(t.calls)} model calls`) +
    tile(u.sessions.length, "Sessions", `${agents} agent runs`) +
    tile(compact(peak), "PM peak context", "largest conversation re-read by the PM") +
    `</div>`;

  const roleName = (row) => {
    const role = s.team.find((item) => item.id === row.role);
    return `${roleBadge(row.role)} ${esc(role ? role.title : row.role)}`;
  };
  const featureName = (row) => {
    if (row.feature === "coordination") return "Coordination <span class=\"muted small\">(Project Manager)</span>";
    if (row.feature === "unlinked") return "Not linked to a feature <span class=\"muted small\">(discovery, design, checks)</span>";
    return `<a href="#feature/${esc(row.feature)}">${esc(row.feature)}</a> ${esc(row.title || "")}`;
  };
  const sessionRows = u.sessions.slice().reverse().map((session) =>
    `<tr><td>${esc(when(session.start))} → ${esc(when(session.end))}</td><td class="num">${session.agents}</td><td class="num">${session.calls}</td>` +
    `<td class="num">${compact(session.pm_peak_context)}</td><td class="num">${compact(session.weighted)}</td>` +
    `${u.currency ? `<td class="num">${esc(money(session.cost, u.currency)) || "—"}</td>` : ""}</tr>`).join("");
  const sessions =
    `<div class="table-wrap"><table class="grid usage-table"><thead><tr><th>Session</th><th>Agents</th><th>Calls</th><th>PM peak context</th><th>Weighted</th>${u.currency ? "<th>Cost</th>" : ""}</tr></thead><tbody>${sessionRows}</tbody></table></div>`;
  const models = u.models.map((row) => `${esc(row.model)} ${compact(row.weighted)} (${((100 * row.weighted) / (t.weighted || 1)).toFixed(0)}%)`).join(" · ");

  return (
    head +
    `<p class="muted small">Counted from the Claude Code session files of this project on this computer; nothing is sent anywhere and no prompt is read out. Models: ${models}.</p>` +
    tiles +
    `<h3 class="drawer-section">By role</h3>${usageTable(u.roles, "Role", roleName, u)}` +
    `<h3 class="drawer-section">By feature <span class="muted">agent runs linked through the feature or task id in their delegation</span></h3>${usageTable(u.features, "Feature", featureName, u)}` +
    `<h3 class="drawer-section">By phase</h3>${usageTable(u.phases, "Phase", (row) => esc(row.label || row.phase), u)}` +
    `<h3 class="drawer-section">By session <span class="muted">a fresh session (/clear) keeps the PM context small</span></h3>${sessions}`
  );
}

function agentDrawer(role) {
  const status = { working: "Working", waiting: "Waiting", idle: "Idle" }[role.status] || role.status;
  let now = "";
  if (role.status === "working") {
    const current = role.current || {};
    const text = current.text || (role.last_action && role.last_action.text) || "Working";
    const parts = [current.since ? `for ${esc(since(current.since))}` : "", role.instances > 1 ? `${role.instances} in parallel` : ""].filter(Boolean);
    const link = current.feature ? ` · <a href="#feature/${esc(current.feature)}">${esc(current.feature)}</a>` : "";
    now = `<div class="callout ok"><strong>${esc(text)}</strong>${parts.length ? `<span class="muted"> · ${parts.join(" · ")}</span>` : ""}${link}</div>`;
  } else if (role.status === "waiting") {
    now = `<div class="callout">Waiting for ${esc(joinNames(role.waiting_for))}</div>`;
  }

  const taskRows = (tasks) => `<ul class="tasks">${tasks
    .map((task) =>
      `<li class="task ${esc(task.status)}"><i class="state"></i><span class="mono">${esc(task.id)}</span>` +
      `<span class="task-title">${esc(task.title)}</span><a class="mono small" href="#feature/${esc(task.feature)}">${esc(task.feature)}</a>` +
      `<span class="task-status">${esc(task.status_label)}</span></li>`)
    .join("")}</ul>`;
  const open = role.tasks.filter((task) => !FINISHED_TASKS.includes(task.status));
  const finished = role.tasks.filter((task) => FINISHED_TASKS.includes(task.status));
  let tasks = "";
  if (!role.tasks.length) tasks = `<p class="muted">No tasks assigned in the backlog.</p>`;
  if (open.length) tasks += taskRows(open);
  if (finished.length) tasks += `<p class="muted small">Completed</p>${taskRows(finished)}`;

  const recent = role.recent.length ? timelineHtml(role.recent) : `<p class="muted">No activity recorded yet.</p>`;
  const eyebrow = [status, role.model].filter(Boolean).map(esc).join(" · ");
  const title = `<span class="who"><span class="avatar" style="--role:${roleColor(role.id)}">${esc(role.short)}</span>${esc(role.title)}</span>`;

  return (
    drawerHead(eyebrow, title) +
    now +
    (role.description ? `<p class="description">${esc(role.description)}</p>` : "") +
    `<h3 class="drawer-section">Tasks</h3>${tasks}` +
    `<h3 class="drawer-section">Recent activity</h3>${recent}`
  );
}

function docsDrawer(s) {
  const head = drawerHead("Documents", "Team documents");
  if (!s.documents.length) {
    return `${head}<p class="muted">The Functional Analysis, the Architecture and the reports appear here as soon as the team writes them.</p>`;
  }
  const groups = new Map();
  for (const doc of s.documents) {
    if (!groups.has(doc.group)) groups.set(doc.group, []);
    groups.get(doc.group).push(doc);
  }
  return head + [...groups.entries()]
    .map(([group, docs]) =>
      `<h3 class="drawer-section">${esc(group)}</h3><ul class="doc-list">${docs
        .map((doc) =>
          `<li><a href="#doc/${esc(doc.path)}"><span class="doc-title">${esc(doc.title)}</span>` +
          `<span class="mono muted small">${esc(doc.path.replace(/^\.deltaforce\//, ""))} · ${esc(when(doc.modified))}</span></a></li>`)
        .join("")}</ul>`)
    .join("");
}

async function loadDocument(path) {
  if (app.loading.has(path)) return;
  app.loading.add(path);
  try {
    const response = await fetch(`/api/doc?path=${encodeURIComponent(path)}`, { cache: "no-store" });
    app.docs.set(path, response.ok ? await response.json() : { error: true, path });
  } catch {
    app.docs.set(path, { error: true, path });
  } finally {
    app.loading.delete(path);
    renderDrawer();
  }
}

function documentDrawer(path) {
  const cached = app.docs.get(path);
  const listed = app.snapshot && app.snapshot.documents.find((doc) => doc.path === path);
  if (!cached || (!cached.error && listed && listed.modified !== cached.modified)) loadDocument(path);
  const back = { route: "docs", label: "All documents" };
  if (!cached) return `${drawerHead("Document", esc(path.split("/").pop()), back)}<p class="muted">Loading…</p>`;
  if (cached.error) return `${drawerHead("Document", esc(path.split("/").pop()), back)}<p class="muted">This document does not exist or cannot be shown.</p>`;
  return (
    drawerHead("Document", esc(cached.title), back) +
    `<div class="doc-meta"><span class="mono">${esc(cached.path)}</span><span>Updated ${esc(when(cached.modified))}</span></div>` +
    `<article class="md">${markdown(cached.text)}</article>`
  );
}

function renderDrawer() {
  const { kind, id } = currentRoute();
  const s = app.snapshot;
  let html = null;
  if (s && kind === "feature") {
    const feature = s.features.find((item) => item.id === id);
    html = feature ? featureDrawer(feature) : `${drawerHead("Feature", esc(id))}<p class="muted">This feature is not in the backlog.</p>`;
  } else if (s && kind === "agent") {
    const role = s.team.find((item) => item.id === id);
    html = role ? agentDrawer(role) : `${drawerHead("Team", esc(id))}<p class="muted">This role is not part of the team.</p>`;
  } else if (s && kind === "task") {
    html = taskDrawer(s, id);
  } else if (s && kind === "workflow") {
    html = id === "timeline" ? timelineDrawer(s) : workflowDrawer(s);
  } else if (s && kind === "usage") {
    html = usageDrawer(s);
  } else if (s && kind === "docs") {
    html = docsDrawer(s);
  } else if (kind === "doc" && id) {
    html = documentDrawer(id);
  }

  const open = html !== null;
  const key = `${kind}/${id}`;
  const body = $("drawer-body");
  const scroll = open && app.shown === key ? body.scrollTop : 0;
  $("drawer").hidden = !open;
  $("drawer").classList.toggle("wide", key === "workflow/timeline" || key === "usage/");
  $("scrim").hidden = !open;
  document.body.classList.toggle("drawer-open", open);
  if (open) {
    body.innerHTML = html;
    body.scrollTop = scroll;
  }
  app.shown = open ? key : null;
}

// ─── updates ──────────────────────────────────────────────────

async function poll() {
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store", headers: app.etag ? { "If-None-Match": app.etag } : {} });
    if (response.status === 200) {
      app.etag = response.headers.get("ETag");
      app.snapshot = await response.json();
      app.online = true;
      render();
    } else if (response.status === 304) {
      if (app.online !== true) { app.online = true; renderLive(); }
    } else {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch {
    if (app.online !== false) { app.online = false; renderLive(); }
  } finally {
    setTimeout(poll, POLL_MS);
  }
}

window.addEventListener("hashchange", renderDrawer);
document.addEventListener("click", (event) => {
  const view = event.target.closest("[data-view]");
  const filter = event.target.closest("[data-filter]");
  if (view) {
    app.featuresView = view.dataset.view;
    stored.set("deltaforce.featuresView", app.featuresView);
    render();
  } else if (filter) {
    app.backlogFilter = filter.dataset.filter;
    stored.set("deltaforce.backlogFilter", app.backlogFilter);
    render();
  }
});
// Keep expanded task lists and the expanded Waiting for you box open when the page refreshes its data.
document.addEventListener("toggle", (event) => {
  const details = event.target;
  if (details.matches && details.matches("details[data-feature]")) {
    if (details.open) app.openBacklog.add(details.dataset.feature);
    else app.openBacklog.delete(details.dataset.feature);
  } else if (details.matches && details.matches("details[data-waiting]")) {
    app.waitingOpen = details.open;
  }
}, true);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("drawer").hidden) closeDrawer();
});
$("scrim").addEventListener("click", closeDrawer);
setInterval(render, 30000); // keep relative times fresh
poll();
