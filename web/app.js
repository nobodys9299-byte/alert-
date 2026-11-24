// ═══════════════════════════════════════════════════════════════════════════════
// DUAL-BOT APP — FRONTEND CONTROLLER (REAL-TIME ENGINE SYNC)
// ═══════════════════════════════════════════════════════════════════════════════

let currentBot = "bot1";
let allBotsStatus = {};
let templatesData = {};
let activeTemplateKey = "admin_job_alert";
let isEnvRawView = false;
let userListCache = [];

// ── INITIALIZATION ─────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  setupNavigation();
  setupBotSwitcher();
  setupTemplateEditor();
  setupEnvViewToggle();

  // Initial fetch
  refreshAllData();

  // Start polling loops
  setInterval(pollStatus, 2000);
  setInterval(pollLogs, 2500);

  // Global Refresh button
  document.getElementById("btn-global-refresh").addEventListener("click", () => {
    refreshAllData();
  });

  // Clear logs button
  document.getElementById("btn-clear-logs").addEventListener("click", () => {
    document.getElementById("terminal-body").innerHTML = "";
  });

  // Stop engine button
  document.getElementById("btn-stop-engine").addEventListener("click", stopEngine);
  document.getElementById("btn-remote-stop").addEventListener("click", stopEngine);
  document.getElementById("btn-open-start-modal").addEventListener("click", openStartModal);
  document.getElementById("btn-toggle-debug").addEventListener("click", toggleDebug);
});

// ── NAVIGATION & TABS ──────────────────────────────────────────────────────
function setupNavigation() {
  document.querySelectorAll(".nav-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const targetId = tab.getAttribute("data-tab");
      switchTab(targetId);
    });
  });
}

function switchTab(targetId) {
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

  const targetTab = document.querySelector(`.nav-tab[data-tab="${targetId}"]`);
  const targetPane = document.getElementById(targetId);

  if (targetTab) targetTab.classList.add("active");
  if (targetPane) targetPane.classList.add("active");

  // Tab-specific loads
  if (targetId === "tab-users") loadUsers();
  if (targetId === "tab-cookies") loadCookiesAndCreds();
  if (targetId === "tab-templates") loadTemplates();
  if (targetId === "tab-env") loadEnv();
}

// ── BOT SWITCHER ───────────────────────────────────────────────────────────
function setupBotSwitcher() {
  document.getElementById("btn-select-bot1").addEventListener("click", () => selectBot("bot1"));
  document.getElementById("btn-select-bot2").addEventListener("click", () => selectBot("bot2"));
}

function selectBot(botId) {
  currentBot = botId;
  document.querySelectorAll(".bot-pill-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-bot") === botId);
  });

  document.getElementById("current-bot-label").textContent =
    botId === "bot1" ? "BOT 1 · ALERT BOT" : "BOT 2 · HYBRID BOT";
  document.getElementById("term-title").textContent =
    botId === "bot1" ? "Bot 1 Console Stream" : "Bot 2 Console Stream";

  // Re-render current tab for selected bot
  renderCurrentBotStatus();
  loadCookiesAndCreds();
  loadUsers();
  loadEnv();
  pollLogs();
}

// ── STATUS & METRICS SYNC ──────────────────────────────────────────────────
async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.ok) {
      allBotsStatus = data.bots;
      updateHeaderPills();
      renderCurrentBotStatus();
    }
  } catch (err) {
    // console.warn("Poll status failed:", err);
  }
}

function updateHeaderPills() {
  for (const botId of ["bot1", "bot2"]) {
    const s = allBotsStatus[botId];
    const dot = document.getElementById(`pill-dot-${botId}`);
    if (dot && s) {
      dot.className = "status-dot " + s.engine_status.toLowerCase();
    }
  }
}

function renderCurrentBotStatus() {
  const s = allBotsStatus[currentBot];
  if (!s) return;

  const badge = document.getElementById("engine-status-badge");
  badge.textContent = s.engine_status;
  badge.className = "engine-indicator " + s.engine_status.toLowerCase();

  document.getElementById("engine-profile-badge").textContent = `🪪 Profile: ${s.active_profile}`;
  document.getElementById("val-uptime").textContent = s.uptime;
  document.getElementById("val-next-check").textContent = s.next_check;
  document.getElementById("val-fetch-count").textContent = `${s.fetch_count} times`;
  document.getElementById("val-alert-count").textContent = s.alert_count;
  document.getElementById("val-active-users").textContent = s.users_stats ? s.users_stats.receiving_alerts : 0;
  document.getElementById("val-debug-mode").textContent = s.debug_mode ? "ON" : "OFF";

  document.getElementById("info-scan-interval").textContent = s.scan_interval;
  document.getElementById("info-page-time").textContent = s.page_time;
  document.getElementById("info-auto-shutdown").textContent = s.auto_shutdown;
  document.getElementById("info-reminder-at").textContent = s.reminder_at;
  document.getElementById("info-session-start").textContent = s.session_start;
  document.getElementById("info-last-disconnect").textContent = s.last_disconnect;

  // Render cookie badges
  if (s.cookies) {
    for (const slot of ["admin", "user1", "user2"]) {
      const ck = s.cookies[slot];
      const elBadge = document.getElementById(`badge-ck-${slot}`);
      const elMeta  = document.getElementById(`meta-ck-${slot}`);
      if (elBadge && ck) {
        elBadge.textContent = ck.saved ? "Saved" : "Not Saved";
        elBadge.className = "slot-badge " + (ck.saved ? "saved" : "");
        elMeta.textContent = `Valid Until: ${ck.valid_until || 'Unknown'}`;
      }
    }
  }
}

// ── ENGINE ACTIONS ─────────────────────────────────────────────────────────
function openStartModal() {
  document.getElementById("modal-start-engine").classList.add("active");
}

async function executeStartEngine(profile) {
  closeModal("modal-start-engine");
  try {
    const res = await fetch(`/api/bot/${currentBot}/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile })
    });
    const data = await res.json();
    alert((data.ok ? "✅ " : "❌ ") + (data.message || "Action finished."));
    pollStatus();
  } catch (err) {
    alert("Connection error: " + err);
  }
}

async function stopEngine() {
  if (!confirm(`Are you sure you want to STOP ${currentBot.toUpperCase()} engine?`)) return;
  try {
    const res = await fetch(`/api/bot/${currentBot}/stop`, { method: "POST" });
    const data = await res.json();
    alert(data.message || "Engine stopped.");
    pollStatus();
  } catch (err) {
    alert("Error stopping engine: " + err);
  }
}

async function toggleDebug() {
  try {
    const res = await fetch(`/api/bot/${currentBot}/toggle_debug`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    pollStatus();
  } catch (err) {}
}

function openStatusModal() {
  const s = allBotsStatus[currentBot];
  if (!s) return;
  const report = `📊 SYSTEM STATUS [${currentBot.toUpperCase()}]
─────────────────────
Engine        : ${s.engine_status}
Profile       : ${s.active_profile}
Session Start : ${s.session_start}
Uptime        : ${s.uptime}
Auto-Shutdown : ${s.auto_shutdown}
Reminder At   : ${s.reminder_at}
Scan Interval : ${s.scan_interval}
Page Time     : ${s.page_time}
Next Check    : ${s.next_check}
Fetch Count   : ${s.fetch_count} times
Debug Mode    : ${s.debug_mode ? '🟢 ON' : '🔴 OFF'}
Last Disconn  : ${s.last_disconnect}
─────────────────────
👥 User Statistics:
Total Registered : ${s.users_stats ? s.users_stats.total : 0}
Approved : ${s.users_stats ? s.users_stats.approved : 0} | Pending : ${s.users_stats ? s.users_stats.pending : 0} | Rejected : ${s.users_stats ? s.users_stats.rejected : 0}
Receiving Alerts : ${s.users_stats ? s.users_stats.receiving_alerts : 0}
─────────────────────`;
  document.getElementById("status-report-text").textContent = report;
  document.getElementById("modal-status-report").classList.add("active");
}

// ── COOKIES & CREDS TAB ────────────────────────────────────────────────────
async function loadCookiesAndCreds() {
  try {
    const resCookies = await fetch(`/api/bot/${currentBot}/cookies`);
    const cookiesData = (await resCookies.json()).cookies || {};

    for (const slot of ["admin", "user1", "user2"]) {
      const ck = cookiesData[slot];
      const elBadge = document.getElementById(`badge-ck-${slot}`);
      const elMeta  = document.getElementById(`meta-ck-${slot}`);
      if (elBadge) {
        elBadge.textContent = ck ? "Saved" : "Not Saved";
        elBadge.className = "slot-badge " + (ck ? "saved" : "");
      }
      if (elMeta) {
        elMeta.textContent = ck ? `Saved: ${ck.date} | Valid: ${ck.valid_until}` : "Valid Until: Not set";
      }
    }

    const resCreds = await fetch(`/api/bot/${currentBot}/creds`);
    const credsData = (await resCreds.json()).creds || {};

    for (const slot of ["login1", "login2"]) {
      const cr = credsData[slot];
      const elBadge = document.getElementById(`badge-cr-${slot}`);
      const elMeta  = document.getElementById(`meta-cr-${slot}`);
      if (elBadge) {
        elBadge.textContent = (cr && cr.email) ? "Configured" : "Not Set";
        elBadge.className = "slot-badge " + ((cr && cr.email) ? "saved" : "");
      }
      if (elMeta) {
        elMeta.textContent = (cr && cr.email) ? `Email: ${cr.email}` : "Email: Not set";
      }
    }
  } catch (err) {}
}

function openEditCookieModal(slot) {
  document.getElementById("edit-cookie-slot").value = slot;
  document.getElementById("modal-cookie-title").textContent = `Edit Cookie: ${slot.toUpperCase()}`;
  document.getElementById("modal-edit-cookie").classList.add("active");
}

async function saveCookieModal() {
  const slot = document.getElementById("edit-cookie-slot").value;
  const name = document.getElementById("edit-cookie-name").value.trim();
  const val = document.getElementById("edit-cookie-value").value.trim();
  const xsrf = document.getElementById("edit-cookie-xsrf").value.trim();
  const valid = document.getElementById("edit-cookie-valid").value.trim() || "Unknown";

  if (!name || !val) {
    alert("Please provide both Cookie Name and Value.");
    return;
  }

  try {
    const res = await fetch(`/api/bot/${currentBot}/cookies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slot,
        cookie_name: name,
        cookie_value: val,
        xsrf_value: xsrf,
        valid_until: valid
      })
    });
    const d = await res.json();
    alert(d.message || "Cookie saved.");
    closeModal("modal-edit-cookie");
    loadCookiesAndCreds();
  } catch (err) {
    alert("Error saving cookie: " + err);
  }
}

async function confirmResetCookies() {
  if (!confirm(`Are you sure you want to RESET ALL COOKIES for ${currentBot.toUpperCase()}?`)) return;
  try {
    await fetch(`/api/bot/${currentBot}/reset_cookies`, { method: "POST" });
    alert("All cookies reset.");
    loadCookiesAndCreds();
  } catch (err) {}
}

function openEditCredModal(slot) {
  document.getElementById("edit-creds-slot").value = slot;
  document.getElementById("modal-creds-title").textContent = `Set Credentials: ${slot.toUpperCase()}`;
  document.getElementById("modal-edit-creds").classList.add("active");
}

async function saveCredsModal() {
  const slot = document.getElementById("edit-creds-slot").value;
  const email = document.getElementById("edit-creds-email").value.trim();
  const password = document.getElementById("edit-creds-password").value.trim();

  if (!email || !password) {
    alert("Please provide email and password.");
    return;
  }

  try {
    const res = await fetch(`/api/bot/${currentBot}/creds`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot, email, password })
    });
    const d = await res.json();
    alert(d.message || "Credentials saved.");
    closeModal("modal-edit-creds");
    loadCookiesAndCreds();
  } catch (err) {
    alert("Error: " + err);
  }
}

async function confirmResetCreds() {
  if (!confirm(`Are you sure you want to RESET ALL LOGIN IDs for ${currentBot.toUpperCase()}?`)) return;
  try {
    await fetch(`/api/bot/${currentBot}/reset_creds`, { method: "POST" });
    alert("Credentials reset.");
    loadCookiesAndCreds();
  } catch (err) {}
}

// ── USERS & SUBSCRIPTIONS TAB ──────────────────────────────────────────────
async function loadUsers() {
  try {
    const res = await fetch(`/api/bot/${currentBot}/users`);
    const data = await res.json();
    const users = data.users || [];
    const adminId = data.admin_id;
    userListCache = users;

    const nonAdmin = users.filter(u => u.id != adminId);
    document.getElementById("u-stat-total").textContent = nonAdmin.length;
    document.getElementById("u-stat-approved").textContent = nonAdmin.filter(u => u.status === "approved").length;
    document.getElementById("u-stat-pending").textContent = nonAdmin.filter(u => u.status === "pending").length;
    document.getElementById("u-stat-receiving").textContent = nonAdmin.filter(u => u.status === "approved" || u.free_alerts > 0).length;

    const tbody = document.getElementById("users-table-body");
    tbody.innerHTML = "";

    if (nonAdmin.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center">No registered users yet.</td></tr>';
      return;
    }

    nonAdmin.forEach(u => {
      const tr = document.createElement("tr");

      let expiryText = "-";
      if (u.expiry) {
        const days = Math.ceil((new Date(u.expiry) - new Date()) / (1000 * 60 * 60 * 24));
        expiryText = days > 0 ? `${days} days left` : "Expired";
      }

      tr.innerHTML = `
        <td>
          <b>${escapeHtml(u.name || 'Unknown')}</b><br>
          <small class="text-muted">@${escapeHtml(u.username || 'none')}</small>
        </td>
        <td><code>${u.id}</code></td>
        <td><span class="badge-status ${u.status}">${u.status}</span></td>
        <td>${u.free_alerts ?? 0}</td>
        <td>${expiryText}</td>
        <td>
          <div class="user-action-btn-group">
            <button class="btn btn-micro btn-success" onclick="approveUser(${u.id}, '2day')">✅ 2D</button>
            <button class="btn btn-micro btn-success" onclick="approveUser(${u.id}, '30day')">✅ 30D</button>
            <button class="btn btn-micro btn-danger" onclick="rejectUser(${u.id})">❌ Reject</button>
            <button class="btn btn-micro btn-secondary" onclick="openDirectMsgModal(${u.id}, '${escapeHtml(u.name || '')}')">💬 DM</button>
            <button class="btn btn-micro btn-outline-danger" onclick="removeUser(${u.id})">🗑️</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {}
}

async function approveUser(userId, plan) {
  try {
    const res = await fetch(`/api/bot/${currentBot}/users/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, plan })
    });
    const d = await res.json();
    alert(d.message || "Approved.");
    loadUsers();
  } catch (err) {}
}

async function rejectUser(userId) {
  try {
    const res = await fetch(`/api/bot/${currentBot}/users/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId })
    });
    const d = await res.json();
    alert(d.message || "Rejected.");
    loadUsers();
  } catch (err) {}
}

async function removeUser(userId) {
  if (!confirm(`Remove user ${userId}?`)) return;
  try {
    const res = await fetch(`/api/bot/${currentBot}/users/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId })
    });
    const d = await res.json();
    alert(d.message || "Removed.");
    loadUsers();
  } catch (err) {}
}

function openDirectMsgModal(userId, name) {
  document.getElementById("dm-user-id").value = userId;
  document.getElementById("dm-user-name").textContent = `Recipient: ${name} (${userId})`;
  document.getElementById("dm-text").value = "";
  document.getElementById("modal-direct-msg").classList.add("active");
}

async function sendDirectMessage() {
  const userId = document.getElementById("dm-user-id").value;
  const text = document.getElementById("dm-text").value.trim();
  if (!text) return;

  try {
    const res = await fetch(`/api/bot/${currentBot}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, text })
    });
    const d = await res.json();
    alert(d.message || "Message sent!");
    closeModal("modal-direct-msg");
  } catch (err) {
    alert("Error sending message: " + err);
  }
}

function openBroadcastModal() {
  document.getElementById("broadcast-text").value = "";
  document.getElementById("modal-broadcast").classList.add("active");
}

async function sendBroadcast() {
  const text = document.getElementById("broadcast-text").value.trim();
  if (!text) {
    alert("Please type a message to broadcast.");
    return;
  }
  if (!confirm("Are you sure you want to BROADCAST this message to ALL active users?")) return;

  try {
    const res = await fetch(`/api/bot/${currentBot}/broadcast`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const d = await res.json();
    alert(d.message || "Broadcast sent!");
    closeModal("modal-broadcast");
  } catch (err) {
    alert("Broadcast error: " + err);
  }
}

// ── TELEGRAM NOTIFICATION TEMPLATES TAB ────────────────────────────────────
function setupTemplateEditor() {
  const textarea = document.getElementById("template-textarea");
  textarea.addEventListener("input", () => {
    if (templatesData[activeTemplateKey]) {
      templatesData[activeTemplateKey].template = textarea.value;
    }
    updateTelegramPreview();
  });

  document.getElementById("btn-save-templates").addEventListener("click", saveTemplates);
}

async function loadTemplates() {
  try {
    const res = await fetch("/api/templates");
    const data = await res.json();
    if (data.ok) {
      templatesData = data.templates;
      renderTemplatePicker();
      selectTemplate(activeTemplateKey);
    }
  } catch (err) {}
}

function renderTemplatePicker() {
  const picker = document.getElementById("template-picker");
  picker.innerHTML = "";

  for (const [key, tpl] of Object.entries(templatesData)) {
    const btn = document.createElement("button");
    btn.className = `tpl-btn ${key === activeTemplateKey ? 'active' : ''}`;
    btn.textContent = tpl.title || key;
    btn.onclick = () => selectTemplate(key);
    picker.appendChild(btn);
  }
}

function selectTemplate(key) {
  activeTemplateKey = key;
  renderTemplatePicker();

  const tpl = templatesData[key];
  if (!tpl) return;

  document.getElementById("active-tpl-title").textContent = tpl.title || key;
  document.getElementById("active-tpl-mode").textContent = tpl.parse_mode || "HTML";
  document.getElementById("template-textarea").value = tpl.template || "";

  updateTelegramPreview();
}

function insertTag(tag) {
  const textarea = document.getElementById("template-textarea");
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const text = textarea.value;

  textarea.value = text.substring(0, start) + tag + text.substring(end);
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = start + tag.length;

  if (templatesData[activeTemplateKey]) {
    templatesData[activeTemplateKey].template = textarea.value;
  }
  updateTelegramPreview();
}

function updateTelegramPreview() {
  const raw = document.getElementById("template-textarea").value;
  const tpl = templatesData[activeTemplateKey] || {};
  const isHtml = (tpl.parse_mode || "HTML") === "HTML";

  // Dummy simulation data
  let preview = raw
    .replace(/{level_name}/g, "LEVEL 1")
    .replace(/{available}/g, "4")
    .replace(/{booked}/g, "18")
    .replace(/{languages}/g, "Hin 🐸 | 📄 Trans | ⏳ 4H | ⚡ ₹14/m | ₹420\nEng | 📄 Anlys | ⏳ 2H | ⚡ ₹10/m | ₹250")
    .replace(/{quick_link}/g, "https://transcribersnet.com/login")
    .replace(/{profile}/g, "🔴🍪 Admin")
    .replace(/{uptime}/g, "1h 45m 12s")
    .replace(/{first_name}/g, "Alex")
    .replace(/{status}/g, "✅ Active — 14 days left")
    .replace(/{report}/g, "Uptime: 3h 00m\nChecks: 24 times\nAlerts: 6");

  const bubble = document.getElementById("telegram-preview-content");
  if (isHtml) {
    bubble.innerHTML = preview;
  } else {
    // Basic Markdown formatting for preview
    let formatted = escapeHtml(preview)
      .replace(/\*(.*?)\*/g, "<b>$1</b>")
      .replace(/_(.*?)_/g, "<i>$1</i>")
      .replace(/`(.*?)`/g, "<code>$1</code>");
    bubble.innerHTML = formatted;
  }
}

async function saveTemplates() {
  try {
    const res = await fetch("/api/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(templatesData)
    });
    const d = await res.json();
    alert(d.message || "Templates saved successfully!");
  } catch (err) {
    alert("Error saving templates: " + err);
  }
}

// ── .ENV SETTINGS TAB ──────────────────────────────────────────────────────
function setupEnvViewToggle() {
  const btnForm = document.getElementById("btn-env-form-view");
  const btnRaw  = document.getElementById("btn-env-raw-view");
  const formView = document.getElementById("env-form-view");
  const rawView  = document.getElementById("env-raw-view");

  btnForm.addEventListener("click", () => {
    isEnvRawView = false;
    btnForm.classList.add("active");
    btnRaw.classList.remove("active");
    formView.classList.remove("hidden");
    rawView.classList.add("hidden");
  });

  btnRaw.addEventListener("click", () => {
    isEnvRawView = true;
    btnRaw.classList.add("active");
    btnForm.classList.remove("active");
    rawView.classList.remove("hidden");
    formView.classList.add("hidden");
  });

  document.getElementById("btn-save-env").addEventListener("click", saveEnv);
}

async function loadEnv() {
  try {
    const res = await fetch(`/api/bot/${currentBot}/env`);
    const data = await res.json();
    if (data.ok) {
      document.getElementById("env-raw-textarea").value = data.raw || "";

      const kv = data.parsed || {};
      for (const [k, v] of Object.entries(kv)) {
        const input = document.getElementById(`env-${k}`);
        if (input) input.value = v;
      }
    }
  } catch (err) {}
}

async function saveEnv() {
  try {
    let payload = {};
    if (isEnvRawView) {
      payload = { raw: document.getElementById("env-raw-textarea").value };
    } else {
      const kv = {};
      document.querySelectorAll("[id^='env-']").forEach(input => {
        if (input.id !== "env-raw-textarea" && input.id !== "env-form-view" && input.id !== "env-raw-view") {
          const key = input.id.replace("env-", "");
          kv[key] = input.value;
        }
      });
      payload = { kv };
    }

    const res = await fetch(`/api/bot/${currentBot}/env`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const d = await res.json();
    alert(d.message || "Environment saved and reloaded!");
    loadEnv();
    pollStatus();
  } catch (err) {
    alert("Error saving .env: " + err);
  }
}

// ── CONSOLE LOGS TAB ───────────────────────────────────────────────────────
async function pollLogs() {
  try {
    const res = await fetch(`/api/logs?bot_id=${currentBot}`);
    const data = await res.json();
    if (data.ok && data.logs && data.logs[currentBot]) {
      renderLogs(data.logs[currentBot]);
    }
  } catch (err) {}
}

function renderLogs(logs) {
  const term = document.getElementById("terminal-body");
  const shouldScroll = document.getElementById("chk-autoscroll").checked;

  term.innerHTML = "";
  logs.forEach(item => {
    const div = document.createElement("div");
    let cls = "log-line";
    const msg = item.message;

    if (msg.includes("━━━")) cls += " cyan";
    else if (msg.includes("✔") || msg.includes("✅") || msg.includes("Connected")) cls += " green";
    else if (msg.includes("✖") || msg.includes("❌") || msg.includes("Error") || msg.includes("Stopped")) cls += " red";
    else if (msg.includes("⚠️") || msg.includes("⏳") || msg.includes("Switching")) cls += " yellow";
    else if (item.is_debug) cls += " grey";

    div.className = cls;
    div.textContent = `[${item.timestamp}] ${msg}`;
    term.appendChild(div);
  });

  if (shouldScroll) {
    term.scrollTop = term.scrollHeight;
  }
}

// ── HELPERS & MODALS ───────────────────────────────────────────────────────
function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("active");
}

function refreshAllData() {
  pollStatus();
  pollLogs();
  loadCookiesAndCreds();
  loadUsers();
  loadTemplates();
  loadEnv();
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
