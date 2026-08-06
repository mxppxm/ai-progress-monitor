// AI 进度监控看板 — 泳道布局
(() => {
  const board = document.getElementById("board");
  const empty = document.getElementById("empty");
  const badge = document.getElementById("conn-badge");
  const timeEl = document.getElementById("updated-at");
  const clearBtn = document.getElementById("clear-btn");

  let tasks = [];
  let registeredAgents = [];
  let lastRenderKey = "";
  const POLL_INTERVAL = 5000;
  let lastSSEMsgAt = Date.now();

  const LANE_ORDER_KEY = "apm-lane-order";

  const AGENT_META = {
    cursor:   { label: "Cursor",   icon: "✕" },
    codex:    { label: "Codex",    icon: "▣" },
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
      try { applyPayload(JSON.parse(e.data)); } catch (_) {}
    };
    es.onerror = () => { badge.textContent = "○ 重连中…"; badge.classList.remove("on"); };
  }

  async function poll() {
    try {
      const j = await (await fetch("/api/tasks")).json();
      applyPayload(j);
      badge.textContent = "◌ 轮询"; badge.classList.add("poll");
    } catch (_) {}
  }
  setInterval(() => { if (Date.now() - lastSSEMsgAt > POLL_INTERVAL * 2) poll(); }, POLL_INTERVAL);

  function applyPayload(j) {
    if (Array.isArray(j?.agents) && j.agents.length) registeredAgents = j.agents;
    render(j?.tasks);
  }

  // ── 泳道顺序：用户拖拽顺序优先，新工作台追加到右侧 ──
  function loadLaneOrder() {
    try { return JSON.parse(localStorage.getItem(LANE_ORDER_KEY) || "[]"); }
    catch (_) { return []; }
  }
  function saveLaneOrder(order) {
    localStorage.setItem(LANE_ORDER_KEY, JSON.stringify(order));
  }
  function persistLaneDomOrder() {
    const order = [...board.querySelectorAll(".lane")].map(el => el.dataset.agent).filter(Boolean);
    if (order.length) saveLaneOrder(order);
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
    for (const a of registeredAgents) {
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
  const JUST_ENDED_SEC = 30;

  /** 结束多久了（秒）；非刚结束返回 null */
  function justEndedAge(t) {
    if (!isEnded(t)) return null;
    const age = Date.now() / 1000 - Number(t.updated_at || 0);
    if (age < 0 || age >= JUST_ENDED_SEC) return null;
    return age;
  }

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
    const groups = {};
    tasks.forEach(t => { (groups[t.agent] = groups[t.agent] || []).push(t); });

    const present = new Set([...registeredAgents, ...Object.keys(groups)]);
    // 兜底：后端未返回 agents 时仍展示本地已知工作台
    if (!registeredAgents.length) {
      Object.keys(AGENT_META).forEach(a => present.add(a));
    }
    const agents = orderedAgents([...present]);
    empty.classList.toggle("hidden", agents.length > 0);

    // 内容键不含 updated_at：心跳只改时间时不整板重绘，避免打断 :hover
    const renderKey = agents.join("|") + "#" + tasks.map(t =>
      [t.task_id, t.agent, t.status, t.name, t.detail || ""].join(":")
    ).join(";");
    timeEl.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });

    if (renderKey === lastRenderKey && board.children.length) {
      // 轻量刷新卡片时间戳
      tasks.forEach(t => {
        const span = board.querySelector(`.task[data-id="${CSS.escape(t.task_id)}"] .task-time`);
        if (span) {
          span.textContent = ftime(t.updated_at);
          span.className = timeClass(t.updated_at);
        }
      });
      return;
    }
    lastRenderKey = renderKey;

    const scrollMap = {};
    const boardScroll = board.scrollLeft;
    const hoveredAgent = board.querySelector(".lane:hover")?.dataset.agent;
    const hoveredTask = board.querySelector(".task:hover")?.dataset.id;
    board.querySelectorAll(".lane-body").forEach(el => {
      const agent = el.closest(".lane")?.dataset.agent;
      if (agent) scrollMap[agent] = el.scrollTop;
    });

    board.innerHTML = agents.map(agent => {
      const pool = sortTasks((groups[agent] || []).slice());
      const run = pool.filter(isRunning).length;
      const pend = pool.filter(isPending).length;
      const ended = pool.length - run - pend;
      const meta = AGENT_META[agent] || { label: agent, icon: "•" };
      const cards = pool.map(cardHTML).join("");
      return `
        <section class="lane" data-agent="${escapeAttr(agent)}">
          <header class="lane-head" draggable="true" title="拖拽排序">
            <span class="lane-grip" aria-hidden="true">⠿</span>
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
    board.scrollLeft = boardScroll;

    // 重绘后瞬时补回 hover 高亮（指针仍在上方时）
    if (hoveredTask) {
      board.querySelector(`.task[data-id="${CSS.escape(hoveredTask)}"]`)?.classList.add("is-hot");
    } else if (hoveredAgent) {
      board.querySelector(`.lane[data-agent="${CSS.escape(hoveredAgent)}"]`)?.classList.add("is-hot");
    }

    // 边框进度条播完 → 去掉 just-ended，恢复普通已结束样式
    board.querySelectorAll(".task.just-ended").forEach(el => {
      const finish = () => {
        if (!el.isConnected || !el.classList.contains("just-ended")) return;
        el.classList.remove("just-ended");
        el.style.removeProperty("--drain-delay");
        const st = el.querySelector(".task-status");
        if (st) {
          st.textContent = "已结束";
          st.classList.remove("fresh");
          st.classList.add("ended");
        }
        const dot = el.querySelector(".dot");
        if (dot) {
          dot.classList.remove("fresh");
          dot.classList.add("off");
        }
      };
      el.addEventListener("animationend", (e) => {
        if (e.animationName === "just-ended-drain") finish();
      }, { once: true });
      const delayRaw = el.style.getPropertyValue("--drain-delay") || "0s";
      const delayMs = Number.parseFloat(delayRaw) || 0;
      // --drain-delay 为负（已过秒数），剩余 = 30 + delay
      const remainMs = Math.max(0, (JUST_ENDED_SEC + delayMs) * 1000) + 50;
      setTimeout(finish, remainMs);
    });
  }

  function cardHTML(t) {
    const age = justEndedAge(t);
    const fresh = age != null;
    const cls = isEnded(t)
      ? (fresh ? " ended just-ended" : " ended")
      : (isPending(t) ? " pending" : "");
    const dotCls = isEnded(t) ? (fresh ? " fresh" : " off") : (isPending(t) ? " pending" : " on");
    const statusLabel = isRunning(t) ? "运行中"
                       : isPending(t) ? "待选择"
                       : (fresh ? "刚结束" : (DONE_LABEL[t.status] || "已结束"));
    const statusCls = isRunning(t) ? "running"
                    : isPending(t) ? "pending"
                    : (fresh ? "fresh" : "ended");
    const drainStyle = fresh ? ` style="--drain-delay: -${age.toFixed(2)}s"` : "";
    const endBtn = !isEnded(t)
      ? `<button type="button" class="task-end" data-end="${escapeAttr(t.task_id)}" title="手动结束">结束</button>`
      : "";
    const detail = (t.detail || "").trim();
    const detailHtml = detail
      ? `<p class="task-detail tippable${isEnded(t) || isPending(t) ? " last-reply" : ""}" data-tip="${escapeAttr(detail)}">${escapeHtml(detail)}</p>`
      : "";
    return `
      <article class="task${cls}" data-id="${escapeAttr(t.task_id)}"${drainStyle}>
        <div class="task-top">
          <span class="dot ${dotCls.trim()}"></span>
          <h3 class="task-name tippable" data-tip="${escapeAttr(t.name || "")}">${escapeHtml(t.name)}</h3>
          <span class="task-status ${statusCls}">${statusLabel}</span>
        </div>
        ${detailHtml}
        <footer class="task-foot">
          <span class="${timeClass(t.updated_at)}">${ftime(t.updated_at)}</span>
          ${endBtn}
        </footer>
      </article>`;
  }

  function focusAgent(agent, taskId) {
    if (!agent) return;
    const q = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    // 不 await：聚焦走本机 open/osascript，等返回会让点击像「没反应」
    fetch(`/api/focus/${encodeURIComponent(agent)}${q}`, { method: "POST", keepalive: true }).catch(() => {});
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

  let skipNextFocus = false;

  // 按下立刻高亮，松手/离开再清
  board.addEventListener("pointerdown", e => {
    if (e.button != null && e.button !== 0) return;
    if (e.target.closest(".task-end")) return;
    const task = e.target.closest(".task");
    const lane = e.target.closest(".lane");
    board.querySelectorAll(".is-press, .is-hot").forEach(el => el.classList.remove("is-press", "is-hot"));
    if (task) task.classList.add("is-press");
    else if (lane) lane.classList.add("is-press");
  });
  const clearPress = () => board.querySelectorAll(".is-press").forEach(el => el.classList.remove("is-press"));
  board.addEventListener("pointerup", clearPress);
  board.addEventListener("pointercancel", clearPress);
  board.addEventListener("pointerleave", clearPress);
  // 指针一动就清掉重绘补的 is-hot，交还真正的 :hover
  board.addEventListener("pointermove", () => {
    const hot = board.querySelectorAll(".is-hot");
    if (hot.length) hot.forEach(el => el.classList.remove("is-hot"));
  }, { passive: true });

  board.addEventListener("click", e => {
    const endBtn = e.target.closest(".task-end");
    if (endBtn) {
      e.preventDefault();
      e.stopPropagation();
      endTask(endBtn.dataset.end);
      return;
    }
    if (skipNextFocus) {
      skipNextFocus = false;
      return;
    }
    const lane = e.target.closest(".lane");
    if (lane) {
      const task = e.target.closest(".task");
      focusAgent(lane.dataset.agent, task?.dataset.id);
    }
  });

  // 拖拽泳道排序（拖标题栏）
  let dragAgent = null;
  board.addEventListener("dragstart", e => {
    const head = e.target.closest(".lane-head");
    if (!head) { e.preventDefault(); return; }
    const lane = head.closest(".lane");
    if (!lane) return;
    dragAgent = lane.dataset.agent;
    skipNextFocus = false;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragAgent);
    requestAnimationFrame(() => lane.classList.add("dragging"));
  });
  board.addEventListener("dragover", e => {
    if (!dragAgent) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const over = e.target.closest(".lane");
    if (!over || over.dataset.agent === dragAgent) return;
    const dragging = board.querySelector(`.lane[data-agent="${CSS.escape(dragAgent)}"]`);
    if (!dragging || dragging === over) return;
    skipNextFocus = true;
    const rect = over.getBoundingClientRect();
    const before = e.clientX < rect.left + rect.width / 2;
    board.insertBefore(dragging, before ? over : over.nextSibling);
    // 拖到边缘时自动横向滚动
    const edge = 48;
    const bRect = board.getBoundingClientRect();
    if (e.clientX < bRect.left + edge) board.scrollLeft -= 18;
    else if (e.clientX > bRect.right - edge) board.scrollLeft += 18;
  });
  board.addEventListener("drop", e => {
    e.preventDefault();
    persistLaneDomOrder();
  });
  board.addEventListener("dragend", () => {
    board.querySelectorAll(".lane.dragging, .lane.drag-over").forEach(el => {
      el.classList.remove("dragging", "drag-over");
    });
    persistLaneDomOrder();
    dragAgent = null;
  });

  // 触控板/滚轮：横向始终滚看板；纵向在泳道内可竖滚，否则转为看板左右
  board.addEventListener("wheel", e => {
    if (board.scrollWidth <= board.clientWidth) return;
    const absX = Math.abs(e.deltaX);
    const absY = Math.abs(e.deltaY);

    // 泳道不吃横向，一律交给看板
    if (absX > absY) {
      e.preventDefault();
      board.scrollLeft += e.deltaX;
      return;
    }

    const body = e.target.closest(".lane-body");
    if (body && body.scrollHeight > body.clientHeight + 1) {
      const top = body.scrollTop <= 0;
      const bottom = body.scrollTop + body.clientHeight >= body.scrollHeight - 1;
      if (!(top && e.deltaY < 0) && !(bottom && e.deltaY > 0)) return;
    }
    e.preventDefault();
    board.scrollLeft += e.deltaY;
  }, { passive: false });

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

  // ── floating tooltip ──
  const tipEl = document.createElement("div");
  tipEl.className = "apm-tip";
  tipEl.setAttribute("role", "tooltip");
  document.body.appendChild(tipEl);

  let tipAnchor = null;
  let tipTimer = null;
  let overTip = false;
  const TIP_SHOW_MS = 480;
  const TIP_HIDE_MS = 180;

  function hideTip() {
    clearTimeout(tipTimer);
    tipTimer = null;
    tipAnchor = null;
    overTip = false;
    tipEl.classList.remove("show");
    tipEl.textContent = "";
  }

  function scheduleHide() {
    clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      if (overTip) return;
      if (tipAnchor && tipAnchor.matches(":hover")) return;
      hideTip();
    }, TIP_HIDE_MS);
  }

  function scheduleShow(anchor) {
    clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      if (!anchor.isConnected || !anchor.matches(":hover")) return;
      showTip(anchor);
    }, TIP_SHOW_MS);
  }

  function placeTip(anchor) {
    const rect = anchor.getBoundingClientRect();
    const pad = 10;
    tipEl.classList.add("show");
    const tw = tipEl.offsetWidth || 280;
    const th = tipEl.offsetHeight || 40;
    let left = rect.left;
    let top = rect.bottom + 6;
    if (left + tw > window.innerWidth - pad) left = Math.max(pad, window.innerWidth - tw - pad);
    if (left < pad) left = pad;
    if (top + th > window.innerHeight - pad) top = Math.max(pad, rect.top - th - 6);
    tipEl.style.left = left + "px";
    tipEl.style.top = top + "px";
  }

  function showTip(anchor) {
    const text = (anchor.getAttribute("data-tip") || "").trim();
    if (!text) return;
    clearTimeout(tipTimer);
    tipAnchor = anchor;
    tipEl.textContent = text;
    placeTip(anchor);
  }

  function relatedInsideTipArea(related) {
    if (!related || !(related instanceof Node)) return false;
    if (related === tipEl || tipEl.contains(related)) return true;
    if (tipAnchor && (related === tipAnchor || tipAnchor.contains(related))) return true;
    return false;
  }

  board.addEventListener("mouseover", e => {
    const el = e.target.closest(".tippable");
    if (!el || !board.contains(el)) return;
    if (tipAnchor === el && tipEl.classList.contains("show")) {
      clearTimeout(tipTimer);
      return;
    }
    scheduleShow(el);
  });

  board.addEventListener("mouseout", e => {
    const el = e.target.closest(".tippable");
    if (!el) return;
    // 还在延迟展示中就离开 → 取消弹出
    if (tipAnchor !== el && !tipEl.classList.contains("show")) {
      if (relatedInsideTipArea(e.relatedTarget)) return;
      clearTimeout(tipTimer);
      tipTimer = null;
      return;
    }
    if (el !== tipAnchor) return;
    if (relatedInsideTipArea(e.relatedTarget)) {
      clearTimeout(tipTimer);
      return;
    }
    scheduleHide();
  });

  tipEl.addEventListener("mouseenter", () => {
    overTip = true;
    clearTimeout(tipTimer);
  });
  tipEl.addEventListener("mouseleave", e => {
    overTip = false;
    if (relatedInsideTipArea(e.relatedTarget)) return;
    scheduleHide();
  });

  board.addEventListener("scroll", hideTip, true);
  window.addEventListener("scroll", hideTip, true);

  // ── utils ──
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c =>
      ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  }
  function escapeAttr(s) { return String(s ?? "").replace(/"/g, "&quot;"); }
  const FRESH_MIN = 20;
  function isFreshTime(ts) {
    if (!ts) return false;
    const diffMin = (Date.now() - ts * 1000) / 60000;
    return diffMin >= 0 && diffMin <= FRESH_MIN;
  }
  function timeClass(ts) {
    return isFreshTime(ts) ? "task-time task-time--fresh" : "task-time";
  }
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
  fetch("/api/tasks").then(r => r.json()).then(j => {
    applyPayload(j);
    lastSSEMsgAt = Date.now();
  }).catch(() => render([]));
  connectSSE();
})();
