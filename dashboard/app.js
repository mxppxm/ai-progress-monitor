// AI 进度监控看板 — 泳道布局
(() => {
  const board = document.getElementById("board");
  const empty = document.getElementById("empty");
  const badge = document.getElementById("conn-badge");
  const timeEl = document.getElementById("updated-at");

  let tasks = [];
  let nodesCache = {};
  const POLL_INTERVAL = 5000;
  let lastSSEMsgAt = Date.now();

  const AGENT_META = {
    codex:    { label: "Codex",    icon: "▣" },
    cursor:   { label: "Cursor",   icon: "✕" },
    claude:   { label: "Claude",   icon: "◉" },
    opencode: { label: "OpenCode", icon: "◈" },
    clacky:   { label: "Clacky",   icon: "✦" },
  };

  // ── SSE ──
  function connectSSE() {
    const es = new EventSource("/api/stream");
    es.onopen = () => { badge.textContent = "● 实时连接"; badge.classList.add("on"); };
    es.onmessage = (e) => {
      lastSSEMsgAt = Date.now();
      badge.textContent = "● 实时连接"; badge.classList.add("on");
      try { render(JSON.parse(e.data).tasks); } catch (_) {}
    };
    es.onerror = () => { badge.textContent = "○ 重连中…"; badge.classList.remove("on"); };
  }

  async function poll() {
    try {
      const j = await (await fetch("/api/tasks")).json();
      render(j.tasks);
      badge.textContent = "◌ 轮询"; badge.classList.add("poll");
    } catch (_) {}
  }
  setInterval(() => { if (Date.now() - lastSSEMsgAt > POLL_INTERVAL * 2) poll(); }, POLL_INTERVAL);

  // ── 泳道渲染 ──
  function isDone(t) { return t.status !== "running"; }
  const DONE_LABEL = { done: "完成", failed: "失败", paused: "暂停" };

  function render(list) {
    tasks = list || [];
    empty.classList.toggle("hidden", tasks.length > 0);

    // 按 agent 分组
    const groups = {};
    tasks.forEach(t => { (groups[t.agent] = groups[t.agent] || []).push(t); });
    const agents = Object.keys(groups).sort();

    timeEl.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });

    board.innerHTML = agents.map(agent => {
      const pool = groups[agent].slice();
      // 排序：运行中在最上层，其余下沉
      pool.sort((a, b) => (isDone(a) - isDone(b)) || (b.updated_at - a.updated_at));
      const run = pool.filter(t => !isDone(t)).length;
      const done = pool.length - run;
      const meta = AGENT_META[agent] || { label: agent, icon: "•" };
      const cards = pool.map(cardHTML).join("");
      return `
        <section class="lane" data-agent="${agent}">
          <header class="lane-head">
            <span class="lane-icon">${meta.icon}</span>
            <h2 class="lane-title">${escapeHtml(meta.label)}</h2>
            <div class="lane-stats">
              ${run ? `<span class="st running">运行中 ${run}</span>` : ""}
              ${done ? `<span class="st muted">完成 ${done}</span>` : ""}
            </div>
          </header>
          <div class="lane-body">${cards || `<p class="lane-empty">暂无任务</p>`}</div>
        </section>`;
    }).join("");
  }

  function cardHTML(t) {
    const meta = AGENT_META[t.agent] || { label: t.agent };
    const done = isDone(t);
    const statusLabel = done ? (DONE_LABEL[t.status] || "完成") : "运行中";
    const fillClass = done ? " done" : "";
    return `
      <article class="task${done ? " done" : ""}" data-id="${escapeAttr(t.task_id)}">
        <div class="task-top">
          <span class="dot ${done ? "off" : "on"}"></span>
          <h3 class="task-name">${escapeHtml(t.name)}</h3>
          <span class="task-status ${done ? "done" : "running"}">${statusLabel}</span>
        </div>
        ${t.detail ? `<p class="task-detail">${escapeHtml(t.detail)}</p>` : ""}
        <div class="task-stage">${escapeHtml(t.stage || "—")}</div>
        <div class="progress"><span style="width:${t.progress}%"></span></div>
        <footer class="task-foot">
          <span>${t.progress}%</span>
          <span>${ftime(t.updated_at)}</span>
        </footer>
      </article>`;
  }

  // ── 节点弹窗 ──
  async function loadNodes(taskId) {
    if (nodesCache[taskId]) return nodesCache[taskId];
    try {
      const j = await (await fetch(`/api/tasks/${taskId}/nodes`)).json();
      nodesCache[taskId] = j.nodes || [];
      return nodesCache[taskId];
    } catch (_) { return []; }
  }

  function openModal(id) {
    const t = tasks.find(x => x.task_id === id);
    if (!t) return;
    document.getElementById("m-title").textContent = `${t.name} · 节点`;
    document.getElementById("m-timeline").innerHTML = "";
    document.getElementById("modal").classList.remove("hidden");
    loadNodes(id).then(nodes => {
      document.getElementById("m-timeline").innerHTML =
        nodes.length ? nodes.map(nodeHTML).join("") : "<p class='m-none'>暂无节点记录</p>";
    });
  }

  function nodeHTML(n) {
    return `<div class="node ${n.node_type}">
      <div class="node-type">${n.node_type}</div>
      <div class="node-msg">${escapeHtml(n.message)}</div>
      <div class="node-time">${ftime(n.ts)}</div></div>`;
  }

  board.addEventListener("click", e => {
    const card = e.target.closest(".task");
    if (card) openModal(card.dataset.id);
  });
  window.closeModal = () => document.getElementById("modal").classList.add("hidden");

  // ── utils ──
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c =>
      ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  }
  function escapeAttr(s) { return String(s ?? "").replace(/"/g, "&quot;"); }
  function ftime(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    const now = Date.now();
    const diff = (now - ts * 1000) / 60000;
    if (diff < 60) return Math.max(0, Math.round(diff)) + " 分钟前";
    if (diff < 1440) return Math.round(diff / 60) + " 小时前";
    return d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  }

  // ── boot ──
  fetch("/api/tasks").then(r => r.json()).then(j => { render(j.tasks); lastSSEMsgAt = Date.now(); }).catch(() => render([]));
  connectSSE();
})();