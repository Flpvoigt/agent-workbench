const state = {
  data: { sessions: [], repositories: [], generated_at: "" },
  selected: null,
  positions: JSON.parse(localStorage.getItem("agent-workbench.positions") || "{}"),
  paused: false,
  refreshing: false,
  flows: [],
  drag: null,
};

const map = document.querySelector("#mapPanel");
const nodesLayer = document.querySelector("#nodes");
const svg = document.querySelector("#connections");
const inspector = document.querySelector("#inspector");
const toast = document.querySelector("#toast");

const escapeHtml = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const short = (value, length = 42) => {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean;
};

const keyFor = (kind, id) => `${kind}:${id}`;

function notify(message, error = false) {
  toast.textContent = message;
  toast.className = `toast show${error ? " error" : ""}`;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { toast.className = "toast"; }, 2600);
}

async function refresh(silent = false) {
  if (state.refreshing || !window.pywebview?.api) return;
  state.refreshing = true;
  if (!silent) document.body.classList.add("loading");
  document.querySelector("#syncMetric").textContent = "sincronizando";
  try {
    state.data = await window.pywebview.api.snapshot();
    render();
    document.querySelector("#syncMetric").textContent = "agora";
  } catch (error) {
    document.querySelector("#syncMetric").textContent = "erro";
    notify(`Falha ao atualizar: ${error}`, true);
  } finally {
    state.refreshing = false;
    document.body.classList.remove("loading");
  }
}

function visibleSessions() {
  const active = state.data.sessions.filter((item) => item.active);
  return (active.length ? active : state.data.sessions.slice(0, 1)).slice(0, 4);
}

function distribute(count, top, bottom) {
  if (!count) return [];
  if (count === 1) return [(top + bottom) / 2];
  return Array.from({ length: count }, (_, index) => top + (bottom - top) * index / (count - 1));
}

function storedPosition(key, fallback) {
  const saved = state.positions[key];
  if (!saved) return fallback;
  return {
    x: Math.max(150, Math.min(map.clientWidth - 150, saved.x * map.clientWidth)),
    y: Math.max(105, Math.min(map.clientHeight - 70, saved.y * map.clientHeight)),
  };
}

function defaultLayout() {
  const sessions = visibleSessions();
  const repos = state.data.repositories.slice(0, 6);
  const height = map.clientHeight;
  const sessionYs = distribute(sessions.length, 155, Math.min(height - 155, 470));
  const repoYs = distribute(repos.length, 140, height - 105);
  const layout = {};
  sessions.forEach((item, index) => {
    const key = keyFor("session", item.id);
    layout[key] = storedPosition(key, { x: map.clientWidth * 0.17, y: sessionYs[index] });
  });
  repos.forEach((item, index) => {
    const key = keyFor("repository", item.path);
    layout[key] = storedPosition(key, { x: map.clientWidth * 0.84, y: repoYs[index] });
  });
  const idle = state.data.sessions.filter((item) => !item.active);
  if (idle.length) {
    layout.history = storedPosition("history", { x: map.clientWidth * 0.16, y: height - 68 });
  }
  return layout;
}

function render() {
  const sessions = visibleSessions();
  const allSessions = state.data.sessions;
  const repos = state.data.repositories.slice(0, 6);
  const idle = allSessions.filter((item) => !item.active);
  const activeCount = allSessions.filter((item) => item.active).length;
  const layout = defaultLayout();

  document.querySelector("#agentMetric").textContent = `${activeCount} ativos`;
  document.querySelector("#repoMetric").textContent = String(state.data.repositories.length);
  document.querySelector("#coreStatus").textContent = `${activeCount} LIVE`;
  document.querySelector("#emptyState").hidden = allSessions.length > 0;
  document.querySelector("#clock").textContent = state.data.generated_at?.slice(11) || "--:--:--";

  nodesLayer.innerHTML = "";
  sessions.forEach((session) => {
    const key = keyFor("session", session.id);
    const file = session.files.at(-1) || "sem arquivo recente";
    const node = createNode(key, "session", session, layout[key], `
      <div class="node-top">
        <i class="status-dot"></i>
        <span>${session.active ? "WORKING" : "WAITING"}</span>
        <span class="node-time">${escapeHtml(session.updated_time)}</span>
      </div>
      <h3>${escapeHtml(session.project)}</h3>
      <div class="node-detail"><span>${escapeHtml(short(session.activity, 36))}</span></div>
      <div class="node-file">${escapeHtml(file)} → ${escapeHtml(repositoryName(session.repository_path) || "runtime")}</div>
    `);
    node.classList.add("agent");
    if (session.active) node.classList.add("active");
  });

  if (idle.length) {
    createNode("history", "history", idle, layout.history, `
      <div class="node-top"><span>SESSÕES ANTERIORES</span><span class="node-time">${idle.length}</span></div>
      <div class="node-detail"><span>Clique para inspecionar o histórico recente</span></div>
    `).classList.add("history-node");
  }

  repos.forEach((repo) => {
    const key = keyFor("repository", repo.path);
    const badge = repo.error ? "ERROR" : repo.dirty_files ? `DIRTY · ${repo.dirty_files}` : "CLEAN";
    const node = createNode(key, "repository", repo, layout[key], `
      <div class="node-top">
        <i class="repo-icon"></i>
        <span>WORKSPACE</span>
        <span class="node-badge ${repo.dirty_files ? "dirty" : ""}">${escapeHtml(badge)}</span>
      </div>
      <h3>${escapeHtml(repo.name)}</h3>
      <div class="node-detail"><span>${escapeHtml(repo.branch)}</span><span>·</span><span>${repo.pull_requests ?? "—"} PR</span></div>
      <div class="node-file">${escapeHtml(short(repo.path, 48))}</div>
    `);
    node.classList.add("repository");
  });

  renderConnections();
  renderFeed();
  restoreInspector();
  applyFocus();
}

function createNode(key, kind, value, position, markup) {
  const node = document.createElement("article");
  node.className = "node";
  node.dataset.key = key;
  node.dataset.kind = kind;
  node.style.left = `${position.x}px`;
  node.style.top = `${position.y}px`;
  node.innerHTML = markup;
  node.addEventListener("pointerdown", (event) => beginDrag(event, node));
  node.addEventListener("dblclick", () => openNode(kind, value));
  nodesLayer.append(node);
  return node;
}

function beginDrag(event, node) {
  if (event.button !== 0) return;
  event.preventDefault();
  node.setPointerCapture(event.pointerId);
  const key = node.dataset.key;
  const value = valueForNode(node);
  state.drag = {
    node,
    key,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    nodeX: parseFloat(node.style.left),
    nodeY: parseFloat(node.style.top),
    moved: false,
  };
  selectNode(node.dataset.kind, value);
  node.addEventListener("pointermove", moveDrag);
  node.addEventListener("pointerup", endDrag, { once: true });
  node.addEventListener("pointercancel", endDrag, { once: true });
}

function moveDrag(event) {
  const drag = state.drag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const dx = event.clientX - drag.startX;
  const dy = event.clientY - drag.startY;
  if (!drag.moved && Math.hypot(dx, dy) < 5) return;
  drag.moved = true;
  drag.node.classList.add("dragging");
  const x = Math.max(150, Math.min(map.clientWidth - 150, drag.nodeX + dx));
  const y = Math.max(105, Math.min(map.clientHeight - 70, drag.nodeY + dy));
  drag.node.style.left = `${x}px`;
  drag.node.style.top = `${y}px`;
  state.positions[drag.key] = { x: x / map.clientWidth, y: y / map.clientHeight };
  renderConnections();
}

function endDrag(event) {
  const drag = state.drag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  drag.node.classList.remove("dragging");
  drag.node.removeEventListener("pointermove", moveDrag);
  if (drag.moved) localStorage.setItem("agent-workbench.positions", JSON.stringify(state.positions));
  state.drag = null;
}

function valueForNode(node) {
  if (node.dataset.kind === "session") {
    return state.data.sessions.find((item) => keyFor("session", item.id) === node.dataset.key);
  }
  if (node.dataset.kind === "repository") {
    return state.data.repositories.find((item) => keyFor("repository", item.path) === node.dataset.key);
  }
  return state.data.sessions.filter((item) => !item.active);
}

function repositoryName(path) {
  return state.data.repositories.find((item) => item.path === path)?.name || "";
}

function nodeCenter(key) {
  const node = [...document.querySelectorAll(".node")].find((item) => item.dataset.key === key);
  if (!node) return null;
  return { x: parseFloat(node.style.left), y: parseFloat(node.style.top), width: node.offsetWidth };
}

function coreCenter() {
  return { x: map.clientWidth * 0.52, y: map.clientHeight * 0.51 };
}

function curvedPath(start, end) {
  const direction = end.x >= start.x ? 1 : -1;
  const bend = Math.max(70, Math.abs(end.x - start.x) * 0.46);
  return `M ${start.x} ${start.y} C ${start.x + bend * direction} ${start.y}, ${end.x - bend * direction} ${end.y}, ${end.x} ${end.y}`;
}

function edgeAnchors(from, to) {
  const direction = to.x >= from.x ? 1 : -1;
  return {
    start: { x: from.x + direction * (from.width || 90) / 2, y: from.y },
    end: { x: to.x - direction * (to.width || 90) / 2, y: to.y },
  };
}

function addPath(d, className, key, hidden = false) {
  const namespace = "http://www.w3.org/2000/svg";
  if (!hidden) {
    const shadow = document.createElementNS(namespace, "path");
    shadow.setAttribute("d", d);
    shadow.setAttribute("class", "connection-shadow");
    shadow.dataset.key = key;
    svg.append(shadow);
  }
  const path = document.createElementNS(namespace, "path");
  path.setAttribute("d", d);
  path.setAttribute("class", hidden ? "" : className);
  path.dataset.key = key;
  if (hidden) path.style.opacity = "0";
  svg.append(path);
  return path;
}

function renderConnections() {
  svg.setAttribute("viewBox", `0 0 ${map.clientWidth} ${map.clientHeight}`);
  svg.innerHTML = "";
  map.querySelectorAll(".flow-token").forEach((item) => item.remove());
  state.flows = [];
  const core = { ...coreCenter(), width: 90 };

  state.data.repositories.slice(0, 6).forEach((repo) => {
    const center = nodeCenter(keyFor("repository", repo.path));
    if (!center) return;
    const anchors = edgeAnchors(core, center);
    addPath(curvedPath(anchors.start, anchors.end), "connection-line repo", keyFor("repository", repo.path));
  });

  visibleSessions().forEach((session, index) => {
    const center = nodeCenter(keyFor("session", session.id));
    if (!center) return;
    const toCore = edgeAnchors(center, core);
    const d1 = curvedPath(toCore.start, toCore.end);
    addPath(d1, `connection-line${session.active ? " active" : ""}`, keyFor("session", session.id));

    const repoCenter = session.repository_path
      ? nodeCenter(keyFor("repository", session.repository_path))
      : null;
    if (!session.active || !repoCenter || !session.files.length) return;
    const toRepo = edgeAnchors(core, repoCenter);
    const d2 = curvedPath(toRepo.start, toRepo.end).replace(/^M [^C]+/, "");
    const route = addPath(`${d1} ${d2}`, "", `flow:${session.id}`, true);
    const token = document.createElement("div");
    token.className = "flow-token";
    token.textContent = `WRITE  ${session.files.at(-1)}`;
    map.append(token);
    state.flows.push({ path: route, token, offset: index / Math.max(1, visibleSessions().length) });
  });
  applyFocus();
}

function selectNode(kind, value) {
  if (!value) return;
  state.selected = { kind, value };
  renderInspector(kind, value);
  applyFocus();
}

function restoreInspector() {
  if (!state.selected) return;
  const { kind, value } = state.selected;
  if (kind === "session") {
    const current = state.data.sessions.find((item) => item.id === value.id);
    if (current) state.selected.value = current;
  } else if (kind === "repository") {
    const current = state.data.repositories.find((item) => item.path === value.path);
    if (current) state.selected.value = current;
  } else {
    state.selected.value = state.data.sessions.filter((item) => !item.active);
  }
  renderInspector(state.selected.kind, state.selected.value);
}

function renderInspector(kind, value) {
  if (kind === "session") {
    inspector.innerHTML = `
      <span class="overline">AGENT</span>
      <h2>${escapeHtml(value.project)}</h2>
      <div class="inspector-status"><i class="status-dot"></i>${value.active ? "em atividade" : "sessão ociosa"}</div>
      <div class="inspector-rule"></div>
      ${fact("OPERAÇÃO ATUAL", value.activity)}
      ${fact("PEDIDO RECENTE", value.summary || "Sem resumo disponível")}
      ${fact("DIRETÓRIO", value.workspace, true)}
      ${fact("EVENTOS", String(value.event_count))}
      ${files(value.files)}
      <div class="inspector-actions">
        <button class="button primary" data-action="resume" data-id="${escapeHtml(value.id)}">Retomar</button>
        <button class="button" data-action="open" data-path="${escapeHtml(value.workspace)}">Abrir workspace</button>
      </div>`;
  } else if (kind === "repository") {
    const status = value.error || (value.dirty_files ? `${value.dirty_files} alterações locais` : "working tree limpa");
    inspector.innerHTML = `
      <span class="overline">WORKSPACE</span>
      <h2>${escapeHtml(value.name)}</h2>
      <div class="inspector-status"><i class="status-dot"></i>${escapeHtml(status)}</div>
      <div class="inspector-rule"></div>
      ${fact("BRANCH", value.branch, true)}
      ${fact("PULL REQUESTS", value.pull_requests ?? "indisponível")}
      ${fact("REMOTE", value.remote, true)}
      ${fact("CAMINHO", value.path, true)}
      <div class="inspector-actions">
        <button class="button primary" data-action="open" data-path="${escapeHtml(value.path)}">Abrir pasta</button>
        <button class="button danger" data-action="remove" data-path="${escapeHtml(value.path)}">Remover</button>
      </div>`;
  } else {
    inspector.innerHTML = `
      <span class="overline">HISTÓRICO</span>
      <h2>${value.length} sessões anteriores</h2>
      <div class="inspector-status"><i class="status-dot"></i>sem atividade agora</div>
      <div class="inspector-rule"></div>
      ${value.slice(0, 8).map((session) => `
        <button class="button history-row" data-history-id="${escapeHtml(session.id)}">${escapeHtml(session.updated_time)} · ${escapeHtml(session.project)}</button>
      `).join("")}`;
  }
}

function fact(label, value, mono = false) {
  return `<div class="fact"><label>${escapeHtml(label)}</label><p class="${mono ? "mono" : ""}">${escapeHtml(value)}</p></div>`;
}

function files(items) {
  if (!items?.length) return "";
  return `<div class="fact"><label>TIMELINE DE ARQUIVOS</label><div class="file-list">${[...items].reverse().map((item) => `<div class="file-item"><i></i><span>${escapeHtml(item)}</span></div>`).join("")}</div></div>`;
}

function applyFocus() {
  const selected = state.selected;
  document.querySelectorAll(".node").forEach((node) => {
    const isSelected = selected && node.dataset.key === selectedKey(selected);
    node.classList.toggle("selected", Boolean(isSelected));
    node.classList.toggle("dimmed", Boolean(selected && !isSelected && !isRelated(node, selected)));
  });
  svg.querySelectorAll(".connection-line, .connection-shadow").forEach((path) => {
    const related = !selected || path.dataset.key === selectedKey(selected) || connectionRelated(path, selected);
    path.classList.toggle("dimmed", !related);
  });
}

function selectedKey(selected) {
  if (selected.kind === "session") return keyFor("session", selected.value.id);
  if (selected.kind === "repository") return keyFor("repository", selected.value.path);
  return "history";
}

function isRelated(node, selected) {
  if (selected.kind === "session" && node.dataset.kind === "repository") {
    return node.dataset.key === keyFor("repository", selected.value.repository_path);
  }
  if (selected.kind === "repository" && node.dataset.kind === "session") {
    return valueForNode(node)?.repository_path === selected.value.path;
  }
  return false;
}

function connectionRelated(path, selected) {
  if (selected.kind === "session") {
    return path.dataset.key === keyFor("repository", selected.value.repository_path);
  }
  if (selected.kind === "repository") {
    const sessionIds = state.data.sessions
      .filter((item) => item.repository_path === selected.value.path)
      .map((item) => keyFor("session", item.id));
    return sessionIds.includes(path.dataset.key);
  }
  return false;
}

async function openNode(kind, value) {
  if (kind === "session") return runAction(window.pywebview.api.resume(value.id));
  if (kind === "repository") return runAction(window.pywebview.api.open_workspace(value.path));
}

async function runAction(promise, refreshAfter = false) {
  try {
    const result = await promise;
    if (result.error) notify(result.error, true);
    else if (result.ok) notify(result.ok);
    if (refreshAfter && !result.error && !result.cancelled) await refresh(true);
  } catch (error) {
    notify(String(error), true);
  }
}

function renderFeed() {
  const items = state.data.sessions.slice(0, 3);
  document.querySelector("#feedEvents").innerHTML = items.map((item) => `
    <div class="feed-event ${item.active ? "active" : ""}">
      <i></i><div><b>${escapeHtml(item.project)}</b><span>${escapeHtml(item.activity)}</span></div>
    </div>`).join("");
}

function resetLayout() {
  state.positions = {};
  localStorage.removeItem("agent-workbench.positions");
  render();
  notify("Mapa reorganizado.");
}

inspector.addEventListener("click", (event) => {
  const target = event.target.closest("button");
  if (!target) return;
  if (target.dataset.action === "resume") runAction(window.pywebview.api.resume(target.dataset.id));
  if (target.dataset.action === "open") runAction(window.pywebview.api.open_workspace(target.dataset.path));
  if (target.dataset.action === "remove") runAction(window.pywebview.api.remove_repository(target.dataset.path), true);
  if (target.dataset.historyId) {
    const session = state.data.sessions.find((item) => item.id === target.dataset.historyId);
    if (session) selectNode("session", session);
  }
});

document.querySelector("#refreshButton").addEventListener("click", () => refresh());
document.querySelector("#refreshRail").addEventListener("click", () => refresh());
document.querySelector("#fitRail").addEventListener("click", resetLayout);
document.querySelector("#addRail").addEventListener("click", () => runAction(window.pywebview.api.add_repository(), true));
document.querySelector("#pauseButton").addEventListener("click", (event) => {
  state.paused = !state.paused;
  map.classList.toggle("paused", state.paused);
  event.currentTarget.textContent = state.paused ? "Retomar fluxo" : "Pausar fluxo";
});

window.addEventListener("resize", () => requestAnimationFrame(render));
window.addEventListener("keydown", (event) => {
  if (event.key === "F5") { event.preventDefault(); refresh(); }
  if (event.key === "Escape") { state.selected = null; applyFocus(); }
  if (event.code === "Space" && event.target === document.body) document.querySelector("#pauseButton").click();
});

function animateFlows(timestamp) {
  if (!state.paused) {
    state.flows.forEach((flow) => {
      const length = flow.path.getTotalLength();
      const progress = ((timestamp / 11000) + flow.offset) % 1;
      const point = flow.path.getPointAtLength(length * progress);
      flow.token.style.left = `${point.x}px`;
      flow.token.style.top = `${point.y}px`;
    });
  }
  requestAnimationFrame(animateFlows);
}

window.addEventListener("pywebviewready", () => {
  refresh();
  setInterval(() => refresh(true), 12000);
});

requestAnimationFrame(animateFlows);
