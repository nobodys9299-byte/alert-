// ═══════════════════════════════════════════════════════════════════════════════
// TRANSPULSE PRO — CLEAN MENU-DRIVEN CONTROLLER
// ═══════════════════════════════════════════════════════════════════════════════

const API_BASE = (window.location.protocol === 'file:' || !window.location.host)
  ? (localStorage.getItem('bot_server_url') || 'http://localhost:8080')
  : '';

let currentBot = "bot1";
let navigationState = "home"; // "home" | "bot-menu" | "subview"
let activeSubFeatureId = null;

let allBotsStatus = {};
let templatesData = {};
let activeTemplateKey = "admin_job_alert";
let isEnvRawView = false;
let userListCache = [];

// ── INITIALIZATION ─────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  setupNavigationHandlers();
  setupTemplateEditor();
  setupEnvViewToggle();

  // Initial fetch
  refreshAllData();

  // Periodic Polling
  setInterval(pollStatus, 2000);
  setInterval(pollLogs, 2500);

  // Sync button
  document.getElementById("btn-global-refresh").addEventListener("click", refreshAllData);

  // Clear logs button
  document.getElementById("btn-clear-logs").addEventListener("click", () => {
    document.getElementById("terminal-body").innerHTML = "";
  });
});

// ── MENU & VIEW NAVIGATION ─────────────────────────────────────────────────
function setupNavigationHandlers() {
  document.getElementById("btn-top-back").addEventListener("click", navigateBack);
}

function openBotMenu(botId) {
  currentBot = botId;
  navigationState = "bot-menu";

  // Hide Home, Show Bot Menu
  document.getElementById("view-home").classList.remove("active");
  document.getElementById("view-feature").classList.remove("active");
  document.getElementById("view-bot-menu").classList.add("active");

  // Update Topbar
  document.getElementById("brand-home").classList.add("hidden");
  const subTitle = document.getElementById("subview-header-title");
  subTitle.classList.remove("hidden");
  subTitle.textContent = botId === "bot1" ? "Bot 1 · Alert Bot" : "Bot 2 · Hybrid Bot";

  const backBtn = document.getElementById("btn-top-back");
  backBtn.classList.remove("hidden");
  document.getElementById("back-btn-text").textContent = "All Bots";

  // Render Bot Menu Status
  renderBotMenuState();
  pollStatus();
}

function openSubFeature(featureId) {
  navigationState = "subview";
  activeSubFeatureId = featureId;

  // Hide Bot Menu, Show Sub-Feature view
  document.getElementById("view-bot-menu").classList.remove("active");
  document.getElementById("view-feature").classList.add("active");

  // Hide all sub-panes and show target
  document.querySelectorAll(".feature-pane").forEach(pane => pane.classList.remove("active"));
  const targetPane = document.getElementById(featureId);
  if (targetPane) targetPane.classList.add("active");

  // Update Topbar
  const titles = {
    "sub-connect": "Start & Login",
    "sub-status": "Bot Status",
    "sub-cookies": "Cookies & Creds",
    "sub-users": "Users & Plans",
    "sub-templates": "Telegram Messages",
    "sub-env": ".env Settings",
    "sub-logs": "Console Logs"
  };

  document.getElementById("subview-header-title").textContent = titles[featureId] || "Feature";
  document.getElementById("back-btn-text").textContent = "Menu";

  // Load sub-feature specific data
  if (featureId === "sub-users") loadUsers();
  if (featureId === "sub-cookies") loadCookiesAndCreds();
  if (featureId === "sub-templates") loadTemplates();
  if (featureId === "sub-env") loadEnv();
  if (featureId === "sub-logs") pollLogs();
  if (featureId === "sub-status") renderDetailStatus();
}

function navigateBack() {
  if (navigationState === "subview") {
    // Go back to Bot Menu
    document.getElementById("view-feature").classList.remove("active");
    document.getElementById("view-bot-menu").classList.add("active");
    navigationState = "bot-menu";

    const subTitle = document.getElementById("subview-header-title");
    subTitle.textContent = currentBot === "bot1" ? "Bot 1 · Alert Bot" : "Bot 2 · Hybrid Bot";
    document.getElementById("back-btn-text").textContent = "All Bots";
    renderBotMenuState();
  } else if (navigationState === "bot-menu") {
    // Go back to Home
    document.getElementById("view-bot-menu").classList.remove("active");
    document.getElementById("view-home").classList.add("active");
    navigationState = "home";

    document.getElementById("btn-top-back").classList.add("hidden");
    document.getElementById("subview-header-title").classList.add("hidden");
    document.getElementById("brand-home").classList.remove("hidden");
  }
}

// ── STATUS & POLLING ───────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();
    if (data.ok) {
      allBotsStatus = data.bots;
      renderHomeScreenStatus();
      if (navigationState === "bot-menu") renderBotMenuState();
      if (navigationState === "subview" && activeSubFeatureId === "sub-status") renderDetailStatus();
    }
  } catch (err) {}
}

function renderHomeScreenStatus() {
  for (const botId of ["bot1", "bot2"]) {
    const s = allBotsStatus[botId];
    if (!s) continue;

    const pill = document.getElementById(`home-status-${botId}`);
    if (pill) {
      pill.textContent = s.engine_status;
      pill.className = "status-pill " + s.engine_status.toLowerCase();
    }

    const prof = document.getElementById(`home-prof-${botId}`);
    if (prof) prof.textContent = s.active_profile || "None";

    const uptime = document.getElementById(`home-uptime-${botId}`);
    if (uptime) uptime.textContent = s.uptime;

    const alerts = document.getElementById(`home-alerts-${botId}`);
    if (alerts) alerts.textContent = s.alert_count;
  }
}

function renderBotMenuState() {
  const s = allBotsStatus[currentBot];
  if (!s) return;

  const badge = document.getElementById("menu-engine-badge");
  badge.textContent = s.engine_status;
  badge.className = "banner-badge " + s.engine_status.toLowerCase();

  document.getElementById("menu-bot-title").textContent =
    currentBot === "bot1" ? "Bot 1 · Alert Bot" : "Bot 2 · Hybrid Bot";

  document.getElementById("menu-banner-sub").textContent =
    `Profile: ${s.active_profile} · Uptime: ${s.uptime}`;

  const btnToggle = document.getElementById("btn-quick-toggle-engine");
  if (s.engine_status === "ONLINE") {
    btnToggle.textContent = "Stop";
    btnToggle.className = "btn-quick-stop running";
  } else {
    btnToggle.textContent = "Start";
    btnToggle.className = "btn-quick-stop";
  }
}

function renderDetailStatus() {
  const s = allBotsStatus[currentBot];
  if (!s) return;

  document.getElementById("det-engine-status").textContent = s.engine_status;
  document.getElementById("det-active-profile").textContent = s.active_profile;
  document.getElementById("det-uptime").textContent = s.uptime;
  document.getElementById("det-next-check").textContent = s.next_check;
  document.getElementById("det-fetch-count").textContent = `${s.fetch_count} times`;
  document.getElementById("det-alert-count").textContent = s.alert_count;
  document.getElementById("det-scan-interval").textContent = s.scan_interval;
  document.getElementById("det-auto-shutdown").textContent = s.auto_shutdown;
  document.getElementById("det-session-start").textContent = s.session_start;
  document.getElementById("det-debug-mode").textContent = s.debug_mode ? "ON" : "OFF";
}

function handleQuickEngineAction() {
  const s = allBotsStatus[currentBot];
  if (s && s.engine_status === "ONLINE") {
    stopEngine();
  } else {
    openSubFeature("sub-connect");
  }
}

// ── ENGINE START & STOP ────────────────────────────────────────────────────
async function executeStartEngine(profile) {
  try {
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile })
    });
    const data = await res.json();
    alert((data.ok ? "✅ " : "❌ ") + (data.message || "Action finished."));
    pollStatus();
    navigateBack();
  } catch (err) {
    alert("Connection error: " + err);
  }
}

async function stopEngine() {
  if (!confirm(`Are you sure you want to STOP ${currentBot.toUpperCase()} engine?`)) return;
  try {
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/stop`, { method: "POST" });
    const data = await res.json();
    alert(data.message || "Engine stopped.");
    pollStatus();
  } catch (err) {
    alert("Error stopping engine: " + err);
  }
}

async function toggleDebug() {
  try {
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/toggle_debug`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    pollStatus();
  } catch (err) {}
}

// ── COOKIES & CREDENTIALS ──────────────────────────────────────────────────
async function loadCookiesAndCreds() {
  try {
    const resCookies = await fetch(`${API_BASE}/api/bot/${currentBot}/cookies`);
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

    const resCreds = await fetch(`${API_BASE}/api/bot/${currentBot}/creds`);
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
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/cookies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot, cookie_name: name, cookie_value: val, xsrf_value: xsrf, valid_until: valid })
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
    await fetch(`${API_BASE}/api/bot/${currentBot}/reset_cookies`, { method: "POST" });
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
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/creds`, {
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
    await fetch(`${API_BASE}/api/bot/${currentBot}/reset_creds`, { method: "POST" });
    alert("Credentials reset.");
    loadCookiesAndCreds();
  } catch (err) {}
}

// ── USERS & PLANS ──────────────────────────────────────────────────────────
async function loadUsers() {
  try {
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/users`);
    const data = await res.json();
    const users = data.users || [];
    const adminId = data.admin_id;
    userListCache = users;

    const nonAdmin = users.filter(u => u.id != adminId);
    document.getElementById("u-stat-total").textContent = nonAdmin.length;
    document.getElementById("u-stat-approved").textContent = nonAdmin.filter(u => u.status === "approved").length;
    document.getElementById("u-stat-pending").textContent = nonAdmin.filter(u => u.status === "pending").length;

    const container = document.getElementById("users-cards-container");
    container.innerHTML = "";

    if (nonAdmin.length === 0) {
      container.innerHTML = '<p class="text-muted" style="text-align:center; padding:20px;">No registered users yet.</p>';
      return;
    }

    nonAdmin.forEach(u => {
      let expiryText = "Trial / No Expiry";
      if (u.expiry) {
        const days = Math.ceil((new Date(u.expiry) - new Date()) / (1000 * 60 * 60 * 24));
        expiryText = days > 0 ? `${days} days left` : "Expired";
      }

      const card = document.createElement("div");
      card.className = "user-card";
      card.innerHTML = `
        <div class="uc-top">
          <div>
            <span class="uc-name">${escapeHtml(u.name || 'Unknown')}</span>
            <span class="uc-username">@${escapeHtml(u.username || 'none')}</span>
          </div>
          <span class="uc-badge ${u.status}">${u.status}</span>
        </div>
        <div class="uc-meta-line">
          <span>ID: <code>${u.id}</code></span> · 
          <span>Free Alerts: <b>${u.free_alerts ?? 0}</b></span> · 
          <span>${expiryText}</span>
        </div>
        <div class="uc-actions">
          <button class="btn btn-micro btn-success" onclick="approveUser(${u.id}, '2day')">✅ 2D</button>
          <button class="btn btn-micro btn-success" onclick="approveUser(${u.id}, '30day')">✅ 30D</button>
          <button class="btn btn-micro btn-danger" onclick="rejectUser(${u.id})">❌ Reject</button>
          <button class="btn btn-micro btn-secondary" onclick="openDirectMsgModal(${u.id}, '${escapeHtml(u.name || '')}')">💬 DM</button>
          <button class="btn btn-micro btn-outline-danger" onclick="removeUser(${u.id})">🗑️</button>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {}
}

async function approveUser(userId, plan) {
  try {
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/users/approve`, {
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
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/users/reject`, {
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
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/users/remove`, {
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
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/message`, {
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
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/broadcast`, {
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

// ── TELEGRAM TEMPLATES ─────────────────────────────────────────────────────
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
    const res = await fetch(`${API_BASE}/api/templates`);
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
    btn.className = `tpl-pill ${key === activeTemplateKey ? 'active' : ''}`;
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
    let formatted = escapeHtml(preview)
      .replace(/\*(.*?)\*/g, "<b>$1</b>")
      .replace(/_(.*?)_/g, "<i>$1</i>")
      .replace(/`(.*?)`/g, "<code>$1</code>");
    bubble.innerHTML = formatted;
  }
}

async function saveTemplates() {
  try {
    const res = await fetch(`${API_BASE}/api/templates`, {
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

// ── .ENV SETTINGS ──────────────────────────────────────────────────────────
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
    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/env`);
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

    const res = await fetch(`${API_BASE}/api/bot/${currentBot}/env`, {
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

// ── CONSOLE LOGS ───────────────────────────────────────────────────────────
async function pollLogs() {
  try {
    const res = await fetch(`${API_BASE}/api/logs?bot_id=${currentBot}`);
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
  if (navigationState === "bot-menu") renderBotMenuState();
  if (navigationState === "subview") {
    if (activeSubFeatureId === "sub-users") loadUsers();
    if (activeSubFeatureId === "sub-cookies") loadCookiesAndCreds();
    if (activeSubFeatureId === "sub-templates") loadTemplates();
    if (activeSubFeatureId === "sub-env") loadEnv();
    if (activeSubFeatureId === "sub-status") renderDetailStatus();
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
