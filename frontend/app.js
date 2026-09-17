/**
 * app.js
 * Logic giao diện Frontend SPA cho Hệ thống Điều phối Phê duyệt Nghỉ phép (The Escalation Referee).
 * Kết nối với Backend FastAPI tại http://localhost:8000.
 */

const API_BASE = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
  ? window.location.origin
  : "http://localhost:8000";


// Biến lưu trữ state
let employeesCache = [];
let activeRequests = [];

// Khởi chạy khi tài liệu sẵn sàng
document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initVerifyHarness();
  initCustomVerify();
  initDashboard();
  initSubmitLeave();
  initEscalationInbox();
  initPolicyViewer();
  loadEmployees();
  checkServerHealth();
  checkLlmHealth();
  setInterval(checkServerHealth, 10000);
  setInterval(checkLlmHealth, 5000);
});


/* ========================================================================= */
/* 1. ĐIỀU HƯỚNG TABS                                                        */
/* ========================================================================= */
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTabId = btn.getAttribute("data-tab");
      switchTab(targetTabId);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

  const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  const targetPane = document.getElementById(tabId);

  if (targetBtn && targetPane) {
    targetBtn.classList.add("active");
    targetPane.classList.add("active");

    // Kích hoạt nạp dữ liệu theo tab
    if (tabId === "tab-dashboard") loadDashboardData();
    if (tabId === "tab-escalation") loadEscalationInbox();
    if (tabId === "tab-policy") loadPolicyDocument();
  }
}

/* ========================================================================= */
/* 2. TAB 1: VERIFY HARNESS (BAN GIÁM KHẢO 90 GIÂY)                          */
/* ========================================================================= */
function initVerifyHarness() {
  const btnRun = document.getElementById("btn-exec-harness");
  if (!btnRun) return;

  btnRun.addEventListener("click", async () => {
    btnRun.disabled = true;
    btnRun.innerHTML = `<span>⏳</span><span>ĐANG THỰC THI 5 KỊCH BẢN KIỂM THỬ...</span>`;

    try {
      const res = await fetch(`${API_BASE}/api/verify/escalation`, { method: "POST" });
      const data = await res.json();

      if (!data.success) throw new Error(data.detail || "Lỗi chạy harness");

      renderHarnessResults(data);
      showToast("Đã thực thi thành công 5 ca kiểm thử Harness!", "success");
    } catch (err) {
      showToast(`Lỗi: ${err.message}`, "error");
    } finally {
      btnRun.disabled = false;
      btnRun.innerHTML = `<span>⚡</span><span>CHẠY LẠI BỘ KIỂM THỬ HARNESS</span>`;
    }
  });
}

function renderHarnessResults(data) {
  const stats = data.summary;
  const details = data.details;

  // Hiển thị stats bar
  const statsBar = document.getElementById("harness-stats");
  statsBar.style.display = "grid";

  document.getElementById("stat-total").innerText = stats.total_cases;
  document.getElementById("stat-auto").innerText = `${stats.auto_approved_cases} / ${stats.target_auto}`;
  document.getElementById("stat-escalate").innerText = `${stats.escalated_cases} / ${stats.target_escalate}`;
  document.getElementById("stat-overall").innerText = stats.overall_status;

  // Hiển thị bảng chi tiết
  const cardTable = document.getElementById("card-harness-table");
  cardTable.style.display = "block";

  const tbody = document.getElementById("harness-results-body");
  tbody.innerHTML = "";

  details.forEach(item => {
    const tr = document.createElement("tr");

    const expectedBadge = item.expected_decision === "AUTO_APPROVE"
      ? `<span class="tag-decision tag-auto">AUTO</span>`
      : `<span class="tag-decision tag-escalate">ESCALATE</span>`;

    const actualBadge = item.actual_decision === "AUTO_APPROVE"
      ? `<span class="tag-decision tag-auto">AUTO</span>`
      : `<span class="tag-decision tag-escalate">ESCALATE</span>`;

    const catTag = item.actual_category 
      ? `<span class="tag-category">${item.actual_category}</span>` 
      : `<span style="color: var(--text-dim);">-</span>`;

    const statusBadge = item.is_passed
      ? `<span style="color: var(--emerald); font-weight: 700; display: inline-flex; align-items: center; gap: 4px;">✅ PASS</span>`
      : `<span style="color: var(--rose); font-weight: 700;">❌ FAIL</span>`;

    tr.innerHTML = `
      <td style="font-family: var(--font-mono); font-weight: 700; color: var(--primary);">${item.test_id}</td>
      <td style="font-weight: 600;">${item.scenario_name}</td>
      <td>${expectedBadge}</td>
      <td>${actualBadge}</td>
      <td>${catTag}</td>
      <td style="color: var(--text-muted); font-size: 0.8rem;">${item.target_role || "Hệ thống tự duyệt"}</td>
      <td>
        <div class="question-preview">${item.actionable_question}</div>
      </td>
      <td>${statusBadge}</td>
    `;
    tbody.appendChild(tr);
  });

  // Tự cuộn xuống xem bảng
  cardTable.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ========================================================================= */
/* 3. INTERACTIVE PLAYGROUND (GIÁM KHẢO TEST CA MỚI)                         */
/* ========================================================================= */
function initCustomVerify() {
  const form = document.getElementById("form-custom-verify");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-submit-custom");
    btn.disabled = true;
    btn.innerHTML = `<span>⏳</span><span>Đang phân tích...</span>`;

    const payload = {
      employee_name: document.getElementById("custom-emp-name").value,
      department: document.getElementById("custom-dept").value,
      remaining_leave_days: parseFloat(document.getElementById("custom-remaining-days").value),
      from_date: document.getElementById("custom-from-date").value,
      to_date: document.getElementById("custom-to-date").value,
      leave_type: document.getElementById("custom-leave-type").value,
      reason: document.getElementById("custom-reason").value,
      handover_person_id: document.getElementById("custom-handover").value || null,
      attachment_type: document.getElementById("custom-attachment").value,
      team_absent_count: 0,
      total_team_members: 10
    };

    try {
      const res = await fetch(`${API_BASE}/api/verify/custom`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!data.success && data.decision !== "LLM_OFFLINE") throw new Error(data.detail || "Lỗi xử lý");

      renderCustomVerifyResult(data);
      if (data.decision === "LLM_OFFLINE") {
        showToast("⚠️ Local LLM Qwen 7B chưa được bật trong tmux!", "error");
      } else {
        showToast("Đã phân tích ca kiểm thử mới!", "success");
      }
    } catch (err) {
      showToast(`Lỗi: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>🚀</span><span>ĐÁNH GIÁ CA KIỂM THỬ NÀY</span>`;
    }
  });
}

function renderCustomVerifyResult(data) {
  const container = document.getElementById("custom-result-card");
  container.style.display = "block";

  if (data.decision === "LLM_OFFLINE") {
    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <h4 style="font-weight: 700; color: #b91c1c;">KẾT QUẢ ĐÁNH GIÁ:</h4>
        <span class="tag-decision" style="background: #fef2f2; color: #b91c1c; border: 1px solid #f87171; font-size: 0.9rem; font-weight: 700; padding: 4px 10px; border-radius: 6px;">
          🔴 LLM SERVER OFFLINE
        </span>
      </div>
      <div style="background: #fff5f5; border: 1px solid #fca5a5; border-radius: 8px; padding: 14px; margin-bottom: 12px; color: #991b1b;">
        <div style="font-weight: 700; margin-bottom: 6px;">⚠️ Mô hình Local LLM (Qwen 2.5 7B) chưa được khởi chạy:</div>
        <div style="font-size: 0.88rem; line-height: 1.5;">${data.plain_reason}</div>
        <div style="margin-top: 10px; padding: 8px 12px; background: #ffffff; border-radius: 6px; font-family: monospace; font-size: 0.84rem; color: #1e293b; border: 1px solid #e2e8f0;">
          👉 Cách bật trong tmux: <code>bash '/workingspace_aiclub/WorkingSpace/Personal/phongnh/ML AI /LLM-KIET/run_qwen7b_vllm.sh'</code>
        </div>
      </div>
    `;
    container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }

  const isAuto = data.decision === "AUTO_APPROVE";
  const badge = isAuto
    ? `<span class="tag-decision tag-auto" style="font-size: 0.9rem;">✅ TỰ ĐỘNG PHÊ DUYỆT (AUTO_APPROVE)</span>`
    : `<span class="tag-decision tag-escalate" style="font-size: 0.9rem;">⚠️ CHUYỂN TIẾP CHO CON NGƯỜI (ESCALATE)</span>`;

  let clausesHtml = "";
  if (data.applied_policy_clauses && data.applied_policy_clauses.length > 0) {
    clausesHtml = `
      <div style="margin-top: 12px; font-size: 0.8rem; color: var(--text-dim);">
        <strong>Căn cứ điều khoản:</strong> ${data.applied_policy_clauses.join(" | ")}
      </div>
    `;
  }

  container.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
      <h4 style="font-weight: 700; color: var(--text-main);">KẾT QUẢ ĐÁNH GIÁ CỦA AI REFEREE:</h4>
      ${badge}
    </div>
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px; font-size: 0.84rem;">
      <div class="stat-box" style="padding: 10px;">
        <div class="stat-label">Số ngày làm việc tính ra</div>
        <div style="font-weight: 700; font-size: 1.1rem; color: var(--primary);">${data.calculated_workdays} ngày</div>
      </div>
      <div class="stat-box" style="padding: 10px;">
        <div class="stat-label">Nhóm bất định</div>
        <div style="font-weight: 700; color: #d97706;">${data.uncertainty_category || "None"}</div>
      </div>
      <div class="stat-box" style="padding: 10px;">
        <div class="stat-label">Cấp xử lý đích</div>
        <div style="font-weight: 700; color: var(--primary);">${data.target_role || "Tự động"}</div>
      </div>
    </div>
    ${!isAuto ? `
      <div class="action-question-box">
        <div class="action-question-title">CÂU HỎI HÀNH ĐỘNG DÀNH CHO NGƯỜI DUYỆT:</div>
        <div class="action-question-text">"${data.actionable_question}"</div>
      </div>
    ` : `
      <div style="color: #047857; font-weight: 600; padding: 12px; background: rgba(16, 185, 129, 0.1); border-radius: 8px;">
        ${data.plain_reason}
      </div>
    `}
    ${clausesHtml}
  `;

  container.scrollIntoView({ behavior: "smooth", block: "nearest" });
}


/* ========================================================================= */
/* 4. TAB 2: DASHBOARD & DANH SÁCH ĐƠN                                       */
/* ========================================================================= */
function initDashboard() {
  document.getElementById("btn-refresh-list").addEventListener("click", loadDashboardData);
  document.getElementById("filter-status").addEventListener("change", loadDashboardData);
}

async function loadDashboardData() {
  const tbody = document.getElementById("leave-requests-body");
  const filter = document.getElementById("filter-status").value;

  try {
    const url = filter && filter !== "ALL" 
      ? `${API_BASE}/api/leave/requests?status=${filter}`
      : `${API_BASE}/api/leave/requests`;

    const res = await fetch(url);
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    activeRequests = json.data;
    renderDashboardStats(activeRequests);
    renderRequestsTable(activeRequests);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--rose);">Lỗi: ${err.message}</td></tr>`;
  }
}

function renderDashboardStats(requests) {
  let auto = 0, pending = 0, resolved = 0;
  requests.forEach(r => {
    if (r.decision === "AUTO_APPROVE") auto++;
    if (r.status === "PENDING_ESCALATION") pending++;
    if (r.decision === "APPROVED_BY_HUMAN_OVERRIDE") resolved++;
  });

  document.getElementById("kpi-total").innerText = requests.length;
  document.getElementById("kpi-auto").innerText = auto;
  document.getElementById("kpi-pending").innerText = pending;
  document.getElementById("kpi-resolved").innerText = resolved;

  // Cập nhật badge trên menu
  const inboxBadge = document.getElementById("inbox-badge");
  if (pending > 0) {
    inboxBadge.innerText = pending;
    inboxBadge.style.display = "inline";
  } else {
    inboxBadge.style.display = "none";
  }
}

function renderRequestsTable(requests) {
  const tbody = document.getElementById("leave-requests-body");
  if (requests.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 30px;">Chưa có đơn nào trong danh sách.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  requests.forEach(req => {
    const tr = document.createElement("tr");

    let decBadge = `<span class="tag-decision tag-auto">AUTO</span>`;
    if (req.decision === "ESCALATE" || req.decision === "ESCALATED_PENDING_HUMAN") {
      decBadge = `<span class="tag-decision tag-escalate">ESCALATE</span>`;
    } else if (req.decision === "APPROVED_BY_HUMAN_OVERRIDE") {
      decBadge = `<span class="tag-decision tag-approved-override">OVERRIDE</span>`;
    } else if (req.decision === "REJECTED" || req.decision === "REJECTED_BY_HUMAN") {
      decBadge = `<span class="tag-decision tag-rejected">REJECTED</span>`;
    }

    const statusBadge = req.status === "COMPLETED"
      ? `<span style="color: var(--emerald); font-weight: 600;">● Hoàn tất</span>`
      : (req.status === "PENDING_ESCALATION" 
          ? `<span style="color: var(--amber); font-weight: 600; animation: pulse-dot 2s infinite;">● Chờ sếp duyệt</span>`
          : `<span style="color: var(--rose);">● Đã đóng</span>`);

    tr.innerHTML = `
      <td style="font-family: var(--font-mono); font-weight: 700; color: var(--primary);">${req.id}</td>
      <td style="font-weight: 600;">${req.employee_name}</td>
      <td style="color: var(--text-muted);">${req.department}</td>
      <td style="font-size: 0.84rem;">${req.from_date || "N/A"} → ${req.to_date || "N/A"}</td>
      <td style="font-family: var(--font-mono); font-weight: 700;">${req.workdays}d</td>
      <td>${req.leave_type}</td>
      <td>${decBadge}</td>
      <td>${statusBadge}</td>
      <td>
        <button class="btn-secondary" onclick="openAuditModal('${req.id}')" style="padding: 4px 10px; font-size: 0.78rem;">
          🔍 Audit Trail
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

/* ========================================================================= */
/* 5. TAB 3: NỘP ĐƠN NGHỈ PHÉP (AI CHAT / FORM)                             */
/* ========================================================================= */
function initSubmitLeave() {
  const modeChatBtn = document.getElementById("mode-chat-btn");
  const modeFormBtn = document.getElementById("mode-form-btn");
  const chatModeDiv = document.getElementById("submit-chat-mode");
  const formModeDiv = document.getElementById("submit-form-mode");

  modeChatBtn.addEventListener("click", () => {
    modeChatBtn.className = "btn-primary";
    modeFormBtn.className = "btn-secondary";
    chatModeDiv.style.display = "block";
    formModeDiv.style.display = "none";
  });

  modeFormBtn.addEventListener("click", () => {
    modeFormBtn.className = "btn-primary";
    modeChatBtn.className = "btn-secondary";
    formModeDiv.style.display = "block";
    chatModeDiv.style.display = "none";
  });

  // Nộp dạng Chat NLP
  document.getElementById("btn-submit-chat").addEventListener("click", async () => {
    const text = document.getElementById("chat-raw-input").value.trim();
    if (!text) return showToast("Vui lòng nhập nội dung tin nhắn xin nghỉ.", "error");

    const empId = document.getElementById("chat-employee-select").value;
    const btn = document.getElementById("btn-submit-chat");
    btn.disabled = true;
    btn.innerHTML = `<span>⏳</span><span>AI đang xử lý...</span>`;

    try {
      const res = await fetch(`${API_BASE}/api/leave/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: text, employee_id: empId })
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.detail);

      showToast(`Đã tạo đơn ${data.data.id}! Quyết định: ${data.data.decision}`, "success");
      document.getElementById("chat-raw-input").value = "";
      loadDashboardData();
      
      if (data.data.status === "PENDING_ESCALATION") {
        switchTab("tab-escalation");
      } else {
        switchTab("tab-dashboard");
      }
    } catch (err) {
      showToast(`Lỗi: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>🤖</span><span>AI PHÂN TÍCH & ĐIỀU PHỐI ĐƠN</span>`;
    }
  });

  // Nộp dạng Form chuẩn
  document.getElementById("form-standard-submit").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      employee_id: document.getElementById("form-employee-select").value,
      leave_type: document.getElementById("form-leave-type").value,
      from_date: document.getElementById("form-from-date").value,
      to_date: document.getElementById("form-to-date").value,
      handover_person_id: document.getElementById("form-handover-select").value || null,
      attachment_type: document.getElementById("form-attachment-type").value,
      reason: document.getElementById("form-reason").value
    };

    try {
      const res = await fetch(`${API_BASE}/api/leave/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.detail);

      showToast(`Đã nộp đơn thành công (${data.data.id})!`, "success");
      loadDashboardData();
      switchTab("tab-dashboard");
    } catch (err) {
      showToast(`Lỗi: ${err.message}`, "error");
    }
  });
}

/* ========================================================================= */
/* 6. TAB 4: ESCALATION INBOX (HUMAN-IN-THE-LOOP)                           */
/* ========================================================================= */
function initEscalationInbox() {
  document.getElementById("btn-refresh-inbox").addEventListener("click", loadEscalationInbox);
}

async function loadEscalationInbox() {
  const container = document.getElementById("escalation-inbox-list");
  try {
    const res = await fetch(`${API_BASE}/api/leave/requests?status=PENDING_ESCALATION`);
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    const pending = json.data;
    if (pending.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; color: var(--text-dim); padding: 48px 0;">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">🎉</div>
          <div style="font-weight: 700; color: var(--text-main); font-size: 1.1rem;">Hộp thư trống!</div>
          <div style="font-size: 0.85rem; margin-top: 4px; color: var(--text-muted);">Tất cả các đơn thường quy đã được AI tự động phê duyệt an toàn.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    pending.forEach(item => {
      const card = document.createElement("div");
      card.className = "escalation-card";

      // Render options pills
      let pillsHtml = "";
      if (item.quick_action_options && item.quick_action_options.length > 0) {
        pillsHtml = `
          <div style="font-size: 0.76rem; color: var(--text-dim); margin-bottom: 6px; font-weight: 600;">GỢI Ý HÀNH ĐỘNG NHANH:</div>
          <div class="quick-options-container">
            ${item.quick_action_options.map(opt => `
              <button class="btn-option-pill" onclick="selectQuickOption('${item.id}', '${opt.replace(/'/g, "\\'")}')">
                👉 ${opt}
              </button>
            `).join("")}
          </div>
        `;
      }

      card.innerHTML = `
        <div class="escalation-header">
          <div>
            <span style="font-family: var(--font-mono); font-weight: 700; color: var(--primary); font-size: 0.85rem;">${item.id}</span>
            <h3 style="font-size: 1.15rem; font-weight: 700; margin-top: 2px;">
              ${item.employee_name} xin nghỉ ${item.workdays} ngày (${item.from_date} → ${item.to_date})
            </h3>
            <div style="font-size: 0.82rem; color: var(--text-muted);">Phòng ban: ${item.department} · Loại: ${item.leave_type}</div>
          </div>
          <span class="approver-badge">Định tuyến: ${item.target_role || "Quản lý"}</span>
        </div>

        <div class="action-question-box">
          <div class="action-question-title">CÂU HỎI HÀNH ĐỘNG DÀNH CHO CẤP THẨM QUYỀN (CHUẨN 6/6 ĐIỂM BGK):</div>
          <div class="action-question-text">"${item.actionable_question || "Vui lòng xem xét đơn nghỉ này."}"</div>
        </div>

        <div style="background: #f8fbff; border: 1px solid #e2e8f0; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 0.84rem; color: var(--text-muted);">
          <strong>Lý do từ hệ thống:</strong> ${item.human_readable_explanation || "Vi phạm quy chế hoặc vượt thẩm quyền tự duyệt."}
        </div>

        ${pillsHtml}

        <div style="display: flex; gap: 12px; align-items: center; margin-top: 12px;">
          <input type="text" id="feedback-input-${item.id}" placeholder="Gõ câu trả lời / chỉ đạo của bạn (ví dụ: Đồng ý duyệt đặc cách...)" style="flex: 1;">
          <button class="btn-primary" onclick="submitHumanDecision('${item.id}')" style="white-space: nowrap;">
            <span>✍️</span><span>Gửi Phê Duyệt / Re-check</span>
          </button>
        </div>
      `;

      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<div style="color: var(--rose);">Lỗi: ${err.message}</div>`;
  }
}

function selectQuickOption(requestId, optionText) {
  const input = document.getElementById(`feedback-input-${requestId}`);
  if (input) {
    input.value = optionText;
    input.focus();
  }
}

async function submitHumanDecision(requestId) {
  const input = document.getElementById(`feedback-input-${requestId}`);
  const feedback = input ? input.value.trim() : "";
  if (!feedback) return showToast("Vui lòng nhập câu trả lời hoặc chọn một gợi ý hành động!", "error");

  try {
    const res = await fetch(`${API_BASE}/api/leave/${requestId}/human-decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback_text: feedback, approver_id: "MANAGER_DEMO" })
    });
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    showToast(`Đã ghi nhận chỉ đạo và Re-check thành công (${json.data.decision})!`, "success");
    loadEscalationInbox();
    loadDashboardData();
  } catch (err) {
    showToast(`Lỗi: ${err.message}`, "error");
  }
}

/* ========================================================================= */
/* 7. TAB 5: QUY CHẾ NGHỈ PHÉP (POLICY VIEWER)                               */
/* ========================================================================= */
async function loadPolicyDocument() {
  const container = document.getElementById("policy-content");
  try {
    const res = await fetch(`${API_BASE}/api/meta/policy`);
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    // Format markdown đơn giản
    let md = json.content_markdown;
    md = md.replace(/### (.*)/g, '<h3 style="color: #0284c7; margin: 18px 0 8px 0; font-size: 1.15rem;">$1</h3>');
    md = md.replace(/## (.*)/g, '<h2 style="color: #0369a1; margin: 24px 0 12px 0; border-bottom: 1px solid var(--border-subtle); padding-bottom: 6px; font-size: 1.35rem;">$1</h2>');
    md = md.replace(/# (.*)/g, '<h1 style="color: #0f172a; margin: 0 0 16px 0; font-size: 1.6rem;">$1</h1>');
    md = md.replace(/\*\*(.*?)\*\*/g, '<strong style="color: #0f172a;">$1</strong>');
    md = md.replace(/\* (.*)/g, '<li style="margin-left: 20px; color: #334155;">$1</li>');
    md = md.replace(/\n\n/g, '<br><br>');

    container.innerHTML = md;
  } catch (err) {
    container.innerHTML = `<div style="color: var(--rose);">Lỗi nạp quy chế: ${err.message}</div>`;
  }
}

/* ========================================================================= */
/* 8. MODAL AUDIT TRAIL (TRÁCH NHIỆM GIẢI TRÌNH)                            */
/* ========================================================================= */
async function openAuditModal(requestId) {
  const modal = document.getElementById("modal-audit");
  document.getElementById("modal-audit-sub").innerText = `Mã đơn: ${requestId}`;
  const timeline = document.getElementById("audit-timeline");
  timeline.innerHTML = `<div style="color: var(--text-dim);">Đang nạp nhật ký kiểm tra...</div>`;
  modal.classList.add("open");

  try {
    const res = await fetch(`${API_BASE}/api/leave/${requestId}`);
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    const logs = json.audit_trail;
    if (logs.length === 0) {
      timeline.innerHTML = `<div style="color: var(--text-dim);">Không có nhật ký nào.</div>`;
      return;
    }

    timeline.innerHTML = "";
    logs.forEach(l => {
      const item = document.createElement("div");
      item.className = "timeline-item";
      item.innerHTML = `
        <div class="timeline-dot"></div>
        <div class="timeline-time">${l.created_at ? l.created_at.replace("T", " ").substring(0, 19) : ""}</div>
        <div class="timeline-title">${l.step_name} · <span style="color: var(--primary);">${l.action}</span></div>
        <div class="timeline-desc">${l.details}</div>
      `;
      timeline.appendChild(item);
    });
  } catch (err) {
    timeline.innerHTML = `<div style="color: var(--rose);">Lỗi: ${err.message}</div>`;
  }
}

document.getElementById("btn-close-modal").addEventListener("click", () => {
  document.getElementById("modal-audit").classList.remove("open");
});

document.getElementById("modal-audit").addEventListener("click", (e) => {
  if (e.target === document.getElementById("modal-audit")) {
    document.getElementById("modal-audit").classList.remove("open");
  }
});

/* ========================================================================= */
/* 9. NẠP DỮ LIỆU NHÂN VIÊN & TIỆN ÍCH                                      */
/* ========================================================================= */
async function loadEmployees() {
  try {
    const res = await fetch(`${API_BASE}/api/meta/employees`);
    const json = await res.json();
    if (!json.success) return;

    employeesCache = json.data;
    const chatSelect = document.getElementById("chat-employee-select");
    const formSelect = document.getElementById("form-employee-select");
    const handoverSelect = document.getElementById("form-handover-select");

    chatSelect.innerHTML = "";
    formSelect.innerHTML = "";
    handoverSelect.innerHTML = `<option value="">-- Không chỉ định --</option>`;

    employeesCache.forEach(emp => {
      const optText = `${emp.name} (${emp.employee_id} - ${emp.department}) [Phép: ${emp.remaining_leave_days}d]`;
      const opt = new Option(optText, emp.employee_id);
      chatSelect.appendChild(opt.cloneNode(true));
      formSelect.appendChild(opt.cloneNode(true));

      const optHandover = new Option(`${emp.name} (${emp.department})`, emp.employee_id);
      handoverSelect.appendChild(optHandover);
    });
  } catch (e) {
    console.error("Lỗi nạp nhân viên:", e);
  }
}

async function checkServerHealth() {
  const statusElem = document.getElementById("server-status-text");
  try {
    const res = await fetch(`${API_BASE}/api/meta/health`);
    if (res.ok) {
      statusElem.innerText = "Backend: Online (:8000)";
      statusElem.parentElement.className = "badge badge-online";
    } else {
      throw new Error();
    }
  } catch {
    statusElem.innerText = "Backend: Disconnected";
    statusElem.parentElement.style.borderColor = "var(--rose)";
  }
}

async function checkLlmHealth() {
  const badgeElem = document.getElementById("badge-llm-status");
  const textElem = document.getElementById("llm-status-text");
  const dotElem = document.getElementById("llm-dot");
  if (!badgeElem || !textElem) return;

  try {
    const res = await fetch(`${API_BASE}/api/meta/llm-status`);
    if (res.ok) {
      const data = await res.json();
      if (data.online) {
        textElem.innerText = `LLM: Online (Qwen 2.5 7B)`;
        badgeElem.style.borderColor = "var(--emerald)";
        badgeElem.style.background = "#ecfdf5";
        badgeElem.style.color = "#047857";
        badgeElem.style.cursor = "default";
        if (dotElem) dotElem.style.background = "var(--emerald)";
      } else if (data.loading) {
        textElem.innerText = `LLM: Đang nạp vào GPU...`;
        badgeElem.style.borderColor = "var(--amber)";
        badgeElem.style.background = "#fffbeb";
        badgeElem.style.color = "#b45309";
        badgeElem.style.cursor = "wait";
        if (dotElem) dotElem.style.background = "var(--amber)";
      } else {
        textElem.innerText = `LLM: Bấm để nạp Qwen 7B`;
        badgeElem.style.borderColor = "#94a3b8";
        badgeElem.style.background = "#f8fafc";
        badgeElem.style.color = "#475569";
        badgeElem.style.cursor = "pointer";
        if (dotElem) dotElem.style.background = "#94a3b8";
        badgeElem.onclick = async () => {
          showToast("🚀 Đang bắt đầu nạp model Qwen 2.5 7B vào GPU...", "info");
          await fetch(`${API_BASE}/api/meta/llm-load`, { method: "POST" });
          checkLlmHealth();
        };
      }
    } else {
      throw new Error();
    }
  } catch {
    textElem.innerText = `LLM: Chưa nạp Model`;
    badgeElem.style.borderColor = "#f87171";
    badgeElem.style.background = "#fff1f2";
    badgeElem.style.color = "#e11d48";
    if (dotElem) dotElem.style.background = "#ef4444";
  }
}



function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  if (type === "success") toast.style.borderLeftColor = "var(--emerald)";
  if (type === "error") toast.style.borderLeftColor = "var(--rose)";

  const icon = type === "success" ? "✅" : (type === "error" ? "❌" : "ℹ️");
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
