// AI 进度监控看板前端逻辑
(() => {
  const grid = document.getElementById("grid");
  const empty = document.getElementById("empty");
  const countEl = document.getElementById("task-count");
  const badge = document.getElementById("conn-badge");

  let tasks = [];
  let filter = "all";
  let showArchived = false;   // 是否查看已存档任务
  let nodesCache = {};
  const POLL_INTERVAL = 5000;   // 兜底轮询周期（ms）
  let lastSSEMsgAt = Date.now();
  let pollTimer = null;
  let usingPoll = false;

  // ── 兜底轮询：SSE 失联时自动接管，保证无需刷新 ──
  async function poll() {
    try {
      const r = await fetch("/api/tasks");
      const j = await r.json();
      render(j.tasks);
      badge.textContent = "轮询兜底";
      badge.classList.add("poll");
      usingPoll = true;
    } catch (_) {}
  }

  function schedulePoll() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      // 若超过阈值没收到 SSE 消息（含心跳），切换到轮询
      if (Date.now() - lastSSEMsgAt > POLL_INTERVAL * 2) { poll(); }
    }, POLL_INTERVAL);
  }

  const STATUS_LABEL = { running: "运行中", done: "已完成", failed: "失败", paused: "暂停" };

  // ── event source (SSE) ──
  function connectSSE() {
    const es = new EventSource("/api/stream");
    es.onopen = () => {
      badge.textContent = "实时连接"; badge.classList.add("on"); badge.classList.remove("poll");
      usingPoll = false;
    };
    es.onmessage = (e) => {
      lastSSEMsgAt = Date.now();
      usingPoll = false;
      badge.textContent = "实时连接"; badge.classList.add("on"); badge.classList.remove("poll");
      try { render(JSON.parse(e.data).tasks); } catch (_) {}
    };
    es.onerror = () => {
      // EventSource 会自动重连；期间由兜底轮询兜着
      badge.textContent = "重连中…"; badge.classList.remove("on");
    };
  }

  async function loadNodes(taskId) {
    if (nodesCache[taskId]) return nodesCache[taskId];
    try {
      const r = await fetch(`/api/tasks/${taskId}/nodes`);
      const j = await r.json();
      nodesCache[taskId] = j.nodes || [];
      return nodesCache[taskId];
    } catch (_) { return []; }
  }

  function render(list) {
    tasks = list || [];
    // 默认隐藏已存档；showArchived 时连存档一起显示
    const activeTasks = tasks.filter(t => !t.archived);
    const visible = (showArchived ? tasks : activeTasks)
      .filter(t => filter === "all" || t.status === filter);
    countEl.textContent = `${visible.length} 个任务`;
    grid.innerHTML = visible.map(cardHTML).join("");
    document.getElementById("archived-count").textContent =
      `已存档 ${tasks.reduce((n, t) => n + (t.archived ? 1 : 0), 0)}`;
    empty.classList.toggle("hidden", visible.length > 0);
  }

  function cardHTML(t) {
    const aclass = ["codex","cursor","claude","opencode"].includes(t.agent) ? `agent-${t.agent}` : "agent-default";
    const status = STATUS_LABEL[t.status] || t.status;
    const fillClass = t.status === "failed" ? " failed" : t.status === "done" ? " done" : "";
    const archClass = t.archived ? " archived" : "";
    const archBtn = t.archived
      ? `<button class="arch-btn" data-arch="${escapeAttr(t.task_id)}" title="恢复到运行列表">↺ 恢复</button>`
      : `<button class="arch-btn" data-arch="${escapeAttr(t.task_id)}" title="存档，从运行列表隐藏">🗂 存档</button>`;
    return `
      <div class="card${archClass}" data-id="${escapeAttr(t.task_id)}">
        <div class="card-head">
          <span class="agent-tag ${aclass}">${escapeHtml(t.agent)}</span>
          <span class="status ${t.status}">${status}${t.archived ? " · 已存档" : ""}</span>
        </div>
        <div class="card-title">${escapeHtml(t.name)}</div>
        <div class="card-detail">${escapeHtml(t.detail || "")}</div>
        <div class="stage">阶段 · ${escapeHtml(t.stage || "—")}</div>
        <div class="progress-track">
          <div class="progress-fill${fillClass}" style="width:${t.progress}%"></div>
        </div>
        <div class="card-foot">
          <span class="updated">更新于 ${ftime(t.updated_at)}</span>
          <span class="foot-right">${archBtn}<span>${t.progress}%</span></span>
        </div>
      </div>`;
  }

  async function openModal(id) {
    const nodes = await loadNodes(id);
    const t = tasks.find(x => x.task_id === id);
    if (!t) return;
    document.getElementById("m-title").textContent = `${t.name} · 节点时间线`;
    document.getElementById("m-timeline").innerHTML =
      nodes.length ? nodes.map(nodeHTML).join("") : "<p style='color:var(--muted)'>暂无节点记录</p>";
    document.getElementById("modal").classList.remove("hidden");
  }

  function nodeHTML(n) {
    return `
      <div class="node ${n.node_type}">
        <div class="node-type">${n.node_type}</div>
        <div class="node-msg">${escapeHtml(n.message)}</div>
        <div class="node-time">${ftime(n.ts)}</div>
      </div>`;
  }

  function closeModal() { document.getElementById("modal").classList.add("hidden"); }
  window.openModal = (id) => openModal(id);
  window.closeModal = closeModal;

  // ── filters ──
  document.querySelectorAll(".chip").forEach(c => {
    c.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach(x => x.classList.remove("active"));
      c.classList.add("active");
      filter = c.dataset.filter;
      render(tasks);
    });
  });

  // 已存档开关
  document.getElementById("arch-toggle").addEventListener("click", () => {
    showArchived = !showArchived;
    document.getElementById("arch-toggle").classList.toggle("active", showArchived);
    render(tasks);
  });

  // 卡片点击 → 节点详情；但存档/恢复按钮不触发（用冒泡判断）
  grid.addEventListener("click", async (e) => {
    const archBtn = e.target.closest(".arch-btn");
    if (archBtn) {
      e.stopPropagation();
      const id = archBtn.dataset.arch;
      const isRestore = archBtn.textContent.includes("恢复");
      try {
        const r = await fetch(`/api/tasks/${encodeURIComponent(id)}/${isRestore ? "unarchive" : "archive"}`, { method: "POST" });
        if (r.ok) {
          // 后端 _publish 已广播 SSE；这里再本地重拉一次兜底即时刷新
          refreshFromServer();
        }
      } catch (_) {}
      return;
    }
    const card = e.target.closest(".card");
    if (card) openModal(card.dataset.id);
  });

  function refreshFromServer() {
    fetch("/api/tasks").then(r => r.json()).then(j => {
      render(j.tasks || []);
      lastSSEMsgAt = Date.now();
    }).catch(_ => {});
  }

  // ── utils ──
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c =>
      ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  }
  function escapeAttr(s) { return String(s ?? "").replace(/"/g, "&quot;"); }
  function ftime(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString("zh-CN", { hour12: false }) + " " + d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  }

  // ├── boot ──
  fetch("/api/tasks").then(r => r.json()).then(j => { render(j.tasks); lastSSEMsgAt = Date.now(); }).catch(_ => render([]));
  connectSSE();
  schedulePoll();
})();