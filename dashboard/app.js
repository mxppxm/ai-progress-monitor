// AI 进度监控看板 — 泳道布局
(() => {
  const board = document.getElementById("board");
  const empty = document.getElementById("empty");
  const badge = document.getElementById("conn-badge");
  const timeEl = document.getElementById("updated-at");
  const clearBtn = document.getElementById("clear-btn");

  let tasks = [];
  const POLL_INTERVAL = 5000;
  let lastSSEMsgAt = Date.now();

  const LANE_ORDER_KEY = "apm-lane-order";

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

  // ── 泳道顺序：首次出现顺序固定，新泳道追加到右侧 ──
  function loadLaneOrder() {
    try { return JSON.parse(localStorage.getItem(LANE_ORDER_KEY) || "[]"); }
    catch (_) { return []; }
  }
  function saveLaneOrder(order) {
    localStorage.setItem(LANE_ORDER_KEY, JSON.stringify(order));
  }
  function orderedAgents(present) {
    const seen = new Set();
    const order = [];
    for (const a of loadLaneOrder()) {
      if (present.includes(a) && !seen.has(a)) {
        order.push(a);
        seen.add(a);
      }
    }
    for (const a of present) {
      if (!seen.has(a)) {
        order.push(a);
        seen.add(a);
      }
    }
    saveLaneOrder(order);
    return order;
  }

  // ── 泳道渲染 ──
  function isRunning(t) { return t.status === "running"; }
  function isPending(t) { return t.status === "pending"; }
  function isEnded(t)   { return !isRunning(t) && !isPending(t); }
  const DONE_LABEL = { done: "已结束", failed: "已结束", paused: "暂停", pending: "待选择" };

  /** 运行中 > 待选择 > 已结束；同组内按更新时间倒序 */
  function statusRank(t) {
    if (isRunning(t)) return 0;
    if (isPending(t)) return 1;
    return 2;
  }
  function sortTasks(pool) {
    pool.sort((a, b) => {
      const d = statusRank(a) - statusRank(b);
      return d !== 0 ? d : b.updated_at - a.updated_at;
    });
    return pool;
  }

  function render(list) {
    tasks = list || [];
    empty.classList.toggle("hidden", tasks.length > 0);

    const groups = {};
    tasks.forEach(t => { (groups[t.agent] = groups[t.agent] || []).push(t); });
    const agents = orderedAgents(Object.keys(groups));

    timeEl.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });

    const scrollMap = {};
    board.querySelectorAll(".lane-body").forEach(el => {
      const agent = el.closest(".lane")?.dataset.agent;
      if (agent) scrollMap[agent] = el.scrollTop;
    });

    board.innerHTML = agents.map(agent => {
      const pool = sortTasks(groups[agent].slice());
      const run = pool.filter(isRunning).length;
      const pend = pool.filter(isPending).length;
      const ended = pool.length - run - pend;
      const meta = AGENT_META[agent] || { label: agent, icon: "•" };
      const cards = pool.map(cardHTML).join("");
      return `
        <section class="lane" data-agent="${agent}">
          <header class="lane-head">
            <span class="lane-icon">${meta.icon}</span>
            <h2 class="lane-title">${escapeHtml(meta.label)}</h2>
            <div class="lane-stats">
              ${run ? `<span class="st running">运行中 ${run}</span>` : ""}
              ${pend ? `<span class="st pending">待选择 ${pend}</span>` : ""}
              ${ended ? `<span class="st muted">已结束 ${ended}</span>` : ""}
            </div>
          </header>
          <div class="lane-body">${cards || `<p class="lane-empty">暂无任务</p>`}</div>
        </section>`;
    }).join("");

    board.querySelectorAll(".lane-body").forEach(el => {
      const agent = el.closest(".lane")?.dataset.agent;
      if (agent && scrollMap[agent] != null) el.scrollTop = scrollMap[agent];
    });
  }

  function cardHTML(t) {
    const cls = isEnded(t) ? " ended" : (isPending(t) ? " pending" : "");
    const dotCls = isEnded(t) ? " off" : (isPending(t) ? " pending" : " on");
    const statusLabel = isRunning(t) ? "运行中"
                       : isPending(t) ? "待选择"
                       : (DONE_LABEL[t.status] || "已结束");
    const endBtn = !isEnded(t)
      ? `<button type="button" class="task-end" data-end="${escapeAttr(t.task_id)}" title="手动结束">结束</button>`
      : "";
    return `
      <article class="task${cls}" data-id="${escapeAttr(t.task_id)}">
        <div class="task-top">
          <span class="dot ${dotCls.trim()}"></span>
          <h3 class="task-name">${escapeHtml(t.name)}</h3>
          <span class="task-status ${isRunning(t) ? "running" : isPending(t) ? "pending" : "ended"}">${statusLabel}</span>
        </div>
        ${t.detail ? `<p class="task-detail">${escapeHtml(t.detail)}</p>` : ""}
        <div class="task-stage">${escapeHtml(t.stage || "—")}</div>
        <footer class="task-foot">
          <span>${ftime(t.updated_at)}</span>
          ${endBtn}
        </footer>
      </article>`;
  }

  async function endTask(taskId) {
    try {
      const res = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/end`, { method: "POST" });
      if (!res.ok) return;
      const j = await res.json();
      if (j.task) {
        const idx = tasks.findIndex(t => t.task_id === taskId);
        if (idx >= 0) {
          tasks[idx] = j.task;
          render(tasks);
        }
      }
    } catch (_) {}
  }

  board.addEventListener("click", e => {
    const endBtn = e.target.closest(".task-end");
    if (endBtn) {
      e.preventDefault();
      endTask(endBtn.dataset.end);
    }
  });

  async function clearAll() {
    if (!confirm("确定清空全部任务？此操作不可恢复。")) return;
    clearBtn.disabled = true;
    try {
      const res = await fetch("/api/tasks/clear", { method: "POST" });
      if (!res.ok) return;
      render([]);
    } catch (_) {}
    finally { clearBtn.disabled = false; }
  }
  clearBtn.addEventListener("click", clearAll);

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
