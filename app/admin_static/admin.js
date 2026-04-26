const state = {
  token: sessionStorage.getItem("schedule_admin_token") || "",
  page: 1,
  pageSize: 20,
  total: 0,
  search: "",
  deleteTarget: null,
};

const els = {
  loginView: document.querySelector("#loginView"),
  dashboardView: document.querySelector("#dashboardView"),
  loginForm: document.querySelector("#loginForm"),
  loginEmail: document.querySelector("#loginEmail"),
  loginPassword: document.querySelector("#loginPassword"),
  loginError: document.querySelector("#loginError"),
  logoutButton: document.querySelector("#logoutButton"),
  refreshButton: document.querySelector("#refreshButton"),
  searchForm: document.querySelector("#searchForm"),
  searchInput: document.querySelector("#searchInput"),
  usersTable: document.querySelector("#usersTable"),
  pageInfo: document.querySelector("#pageInfo"),
  prevPage: document.querySelector("#prevPage"),
  nextPage: document.querySelector("#nextPage"),
  detailDrawer: document.querySelector("#detailDrawer"),
  closeDetail: document.querySelector("#closeDetail"),
  detailEmail: document.querySelector("#detailEmail"),
  detailBody: document.querySelector("#detailBody"),
  deleteModal: document.querySelector("#deleteModal"),
  deleteForm: document.querySelector("#deleteForm"),
  deleteEmailText: document.querySelector("#deleteEmailText"),
  deleteEmailInput: document.querySelector("#deleteEmailInput"),
  cancelDelete: document.querySelector("#cancelDelete"),
  toast: document.querySelector("#toast"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle("error", isError);
  els.toast.classList.remove("hidden");
  window.setTimeout(() => els.toast.classList.add("hidden"), 3600);
}

function setLoggedIn(loggedIn) {
  els.loginView.classList.toggle("hidden", loggedIn);
  els.dashboardView.classList.toggle("hidden", !loggedIn);
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload || payload.code !== 0) {
    const message = payload?.message || `请求失败：HTTP ${response.status}`;
    if (response.status === 401 || response.status === 403) {
      sessionStorage.removeItem("schedule_admin_token");
      state.token = "";
      setLoggedIn(false);
    }
    throw new Error(message);
  }
  return payload.data;
}

async function login(event) {
  event.preventDefault();
  els.loginError.textContent = "";
  try {
    const data = await api("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({
        email: els.loginEmail.value,
        password: els.loginPassword.value,
      }),
    });
    state.token = data.access_token;
    sessionStorage.setItem("schedule_admin_token", state.token);
    setLoggedIn(true);
    await refreshAll();
  } catch (error) {
    els.loginError.textContent = error.message;
  }
}

function logout() {
  sessionStorage.removeItem("schedule_admin_token");
  state.token = "";
  setLoggedIn(false);
}

async function refreshAll() {
  await Promise.all([loadOverview(), loadUsers()]);
}

async function loadOverview() {
  try {
    const data = await api("/api/admin/overview");
    document.querySelector("#metricUsers").textContent = data.total_users;
    document.querySelector("#metricActive30").textContent = data.active_users_30d;
    document.querySelector("#metricDevices").textContent = data.total_devices;
    document.querySelector("#metricRecords").textContent = data.total_sync_records;
    document.querySelector("#metricToday").textContent = data.today_active_users;
    renderChart(data.daily_active || []);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadUsers() {
  try {
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: String(state.pageSize),
    });
    if (state.search) {
      params.set("search", state.search);
    }
    const data = await api(`/api/admin/users?${params.toString()}`);
    state.total = data.total;
    renderUsers(data.items || []);
    const maxPage = Math.max(1, Math.ceil(state.total / state.pageSize));
    els.pageInfo.textContent = `第 ${state.page} / ${maxPage} 页，共 ${state.total} 人`;
    els.prevPage.disabled = state.page <= 1;
    els.nextPage.disabled = state.page >= maxPage;
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderUsers(users) {
  if (!users.length) {
    els.usersTable.innerHTML = '<tr><td colspan="8">暂无用户</td></tr>';
    return;
  }
  els.usersTable.innerHTML = users
    .map(
      (user) => `
      <tr>
        <td>${escapeHtml(user.email)}</td>
        <td>${escapeHtml(user.display_name || "-")}</td>
        <td><span class="status-pill ${user.is_active ? "active" : "disabled"}">${
          user.is_active ? "启用" : "停用"
        }</span></td>
        <td>${user.device_count}</td>
        <td>${user.sync_record_count}</td>
        <td>${escapeHtml(user.last_active_at || "-")}</td>
        <td>${escapeHtml(user.created_at || "-")}</td>
        <td>
          <button class="ghost-button" data-detail="${user.id}" type="button">详情</button>
          <button class="danger-button" data-delete-id="${user.id}" data-delete-email="${escapeHtml(
            user.email
          )}" type="button">删除</button>
        </td>
      </tr>
    `
    )
    .join("");
}

function renderChart(points) {
  const svg = document.querySelector("#activeChart");
  const width = 900;
  const height = 260;
  const pad = 34;
  const maxValue = Math.max(1, ...points.map((item) => Number(item.active_users || 0)));
  const barGap = 5;
  const barWidth = (width - pad * 2 - barGap * Math.max(points.length - 1, 0)) / Math.max(points.length, 1);

  const bars = points
    .map((item, index) => {
      const value = Number(item.active_users || 0);
      const x = pad + index * (barWidth + barGap);
      const barHeight = ((height - pad * 2) * value) / maxValue;
      const y = height - pad - barHeight;
      const label = item.date.slice(5);
      return `
        <g>
          <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="5" fill="#2563eb">
            <title>${item.date}: ${value} 人活跃，${item.sync_changes || 0} 条同步变更</title>
          </rect>
          ${index % 5 === 0 ? `<text x="${x}" y="${height - 8}" font-size="11" fill="#64748b">${label}</text>` : ""}
        </g>
      `;
    })
    .join("");

  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" rx="16" fill="#f8fafc"></rect>
    <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="#d8e1ec"></line>
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" stroke="#d8e1ec"></line>
    <text x="${pad}" y="22" font-size="12" fill="#64748b">最高 ${maxValue} 人</text>
    ${bars}
  `;
}

async function openDetail(userId) {
  try {
    const detail = await api(`/api/admin/users/${userId}`);
    els.detailEmail.textContent = detail.user.email;
    const devices = detail.devices.length
      ? detail.devices
          .map(
            (device) => `
            <div class="detail-row">
              <span>${escapeHtml(device.device_name)}</span>
              <strong>${escapeHtml(device.device_type)} · ${escapeHtml(device.last_seen_at || "-")}</strong>
            </div>
          `
          )
          .join("")
      : '<div class="detail-row"><span>设备</span><strong>暂无</strong></div>';
    const entityCounts = detail.entity_counts.length
      ? detail.entity_counts
          .map(
            (item) => `
            <div class="detail-row">
              <span>${escapeHtml(item.entity_type)}</span>
              <strong>${item.count}</strong>
            </div>
          `
          )
          .join("")
      : '<div class="detail-row"><span>同步实体</span><strong>暂无</strong></div>';

    els.detailBody.innerHTML = `
      <section class="detail-list">
        <h3>账号</h3>
        <div class="detail-row"><span>昵称</span><strong>${escapeHtml(detail.user.display_name || "-")}</strong></div>
        <div class="detail-row"><span>状态</span><strong>${detail.user.is_active ? "启用" : "停用"}</strong></div>
        <div class="detail-row"><span>最后登录</span><strong>${escapeHtml(detail.user.last_login_at || "-")}</strong></div>
        <div class="detail-row"><span>最后活跃</span><strong>${escapeHtml(detail.user.last_active_at || "-")}</strong></div>
      </section>
      <section class="detail-list">
        <h3>设备</h3>
        ${devices}
      </section>
      <section class="detail-list">
        <h3>同步实体分布</h3>
        ${entityCounts}
      </section>
    `;
    els.detailDrawer.classList.remove("hidden");
  } catch (error) {
    showToast(error.message, true);
  }
}

function openDeleteModal(userId, email) {
  state.deleteTarget = { id: userId, email };
  els.deleteEmailText.textContent = email;
  els.deleteEmailInput.value = "";
  els.deleteModal.classList.remove("hidden");
}

async function submitDelete(event) {
  event.preventDefault();
  if (!state.deleteTarget) return;
  try {
    await api(`/api/admin/users/${state.deleteTarget.id}`, {
      method: "DELETE",
      body: JSON.stringify({ confirm_email: els.deleteEmailInput.value }),
    });
    closeDeleteModal();
    showToast("用户已删除");
    await refreshAll();
  } catch (error) {
    showToast(error.message, true);
  }
}

function closeDeleteModal() {
  state.deleteTarget = null;
  els.deleteModal.classList.add("hidden");
}

els.loginForm.addEventListener("submit", login);
els.logoutButton.addEventListener("click", logout);
els.refreshButton.addEventListener("click", () => refreshAll().catch((error) => showToast(error.message, true)));
els.searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.search = els.searchInput.value.trim();
  state.page = 1;
  loadUsers();
});
els.prevPage.addEventListener("click", () => {
  state.page = Math.max(1, state.page - 1);
  loadUsers();
});
els.nextPage.addEventListener("click", () => {
  state.page += 1;
  loadUsers();
});
els.usersTable.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const detailId = target.dataset.detail;
  const deleteId = target.dataset.deleteId;
  if (detailId) {
    openDetail(detailId);
  }
  if (deleteId) {
    openDeleteModal(deleteId, target.dataset.deleteEmail || "");
  }
});
els.closeDetail.addEventListener("click", () => els.detailDrawer.classList.add("hidden"));
els.cancelDelete.addEventListener("click", closeDeleteModal);
els.deleteForm.addEventListener("submit", submitDelete);

if (state.token) {
  setLoggedIn(true);
  refreshAll().catch((error) => showToast(error.message, true));
} else {
  setLoggedIn(false);
}
