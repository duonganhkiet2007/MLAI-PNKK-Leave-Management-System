/**
 * app.js — Team PNKK
 * AI Leave Approval & Routing System Frontend Logic.
 * Supports VI / EN Language Switching (Default: VI).
 */

const API_BASE = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
  ? window.location.origin
  : "http://localhost:8000";

let currentLang = localStorage.getItem("app_lang") || "vi";
let employeesCache = [];
let activeRequests = [];
let inboxInterval = null;

// i18n Translation Dictionary
const I18N = {
  vi: {
    header_sub: "Hệ Thống Phê Duyệt Nghỉ Phép AI · Team PNKK · MLAI Hackathon 2026",
    tab_verify: "Kiểm thử tự động",
    tab_dashboard: "Tổng quan đơn nghỉ",
    tab_submit: "Nộp đơn nghỉ phép",
    tab_escalation: "Hộp thư chuyển tiếp",
    tab_policy: "Quy chế nội bộ",
    hero_title: "BỘ KIỂM THỬ TỰ ĐỘNG (HARNESS 90 GIÂY)",
    hero_desc: "Thực thi 5 kịch bản kiểm thử chuẩn để xác minh khả năng tự duyệt và chuyển tiếp.",
    btn_run_harness: "CHẠY BỘ KIỂM THỬ HARNESS (5 KỊCH BẢN)",
    stat_total: "Tổng số ca",
    stat_auto: "Tự động duyệt",
    stat_escalate: "Chuyển cấp duyệt",
    stat_overall: "Kết quả chung",
    table_harness_title: "BẢNG KẾT QUẢ KIỂM THỬ",
    table_harness_sub: "So sánh kết quả kỳ vọng và quyết định thực tế của AI",
    th_test_id: "Mã",
    th_scenario: "Kịch bản kiểm thử",
    th_expected: "Kỳ vọng",
    th_actual: "AI Thực tế",
    th_category: "Phân loại",
    th_authority: "Thẩm quyền",
    th_question: "Câu hỏi xử lý",
    th_status: "Trạng thái",
    playground_title: "THỬ NGHIỆM CA MỚI",
    playground_sub: "Nhập thông tin đơn nghỉ để kiểm tra phản hồi hệ thống thực tế",
    lbl_emp_name: "Họ tên nhân viên",
    lbl_dept: "Phòng ban",
    lbl_leave_type: "Loại nghỉ phép",
    lbl_balance: "Số ngày phép còn lại",
    lbl_start_date: "Ngày bắt đầu",
    lbl_end_date: "Ngày kết thúc",
    lbl_attachment: "Chứng từ đính kèm",
    lbl_handover: "Mã nhân sự nhận bàn giao",
    lbl_reason: "Lý do xin nghỉ",
    btn_evaluate: "ĐÁNH GIÁ ĐƠN NÀY",
    dash_total: "Tổng số đơn",
    dash_auto: "Tự động duyệt",
    dash_pending: "Chờ duyệt",
    dash_override: "Duyệt đặc cách",
    dash_title: "DANH SÁCH ĐƠN NGHỈ PHÉP",
    dash_sub: "Theo dõi hồ sơ và nhật ký xử lý",
    opt_all: "Tất cả trạng thái",
    opt_pending: "Chờ duyệt",
    opt_completed: "Hoàn tất",
    opt_rejected: "Đã từ chối",
    btn_refresh: "Làm mới",
    th_req_id: "Mã đơn",
    th_employee: "Nhân viên",
    th_department: "Phòng ban",
    th_period: "Thời gian",
    th_days: "Số ngày",
    th_type: "Loại nghỉ",
    th_decision: "Quyết định",
    th_req_status: "Trạng thái",
    th_action: "Thao tác",
    submit_title: "NỘP ĐƠN NGHỈ PHÉP",
    submit_sub: "Nhập tin nhắn tự do hoặc điền biểu mẫu chuẩn",
    btn_nlp: "Nhập văn bản",
    btn_form: "Biểu mẫu chuẩn",
    lbl_chat_emp: "Chọn nhân viên gửi đơn",
    lbl_chat_input: "Nội dung tin nhắn xin nghỉ",
    btn_submit_req: "GỬI ĐƠN NGHỈ PHÉP",
    esc_title: "HỘP THƯ CHUYỂN TIẾP",
    esc_sub: "Đơn nghỉ cần Cấp quản lý xem xét và phê duyệt",
    esc_empty: "Hộp thư trống! Tất cả các đơn hợp lệ đã được tự động xử lý.",
    esc_pills_title: "GỢI Ý HÀNH ĐỘNG NHANH (ẤN ĐỂ DUYỆT NGAY):",
    policy_title: "QUY CHẾ NGHỈ PHÉP NỘI BỘ",
    policy_sub: "Mã văn bản: POL-HR-2026-01 | Quy chuẩn quản lý",
    modal_audit_title: "NHẬT KÝ XỬ LÝ ĐƠN",
    badge_auto: "Tự động duyệt",
    badge_escalate: "Chuyển tiếp",
    badge_override: "Duyệt đặc cách",
    badge_rejected: "Từ chối",
    badge_completed: "Hoàn tất",
    badge_pending: "Chờ duyệt",
    btn_audit: "Nhật ký"
  },
  en: {
    header_sub: "AI Leave Approval & Routing System · Team PNKK · MLAI Hackathon 2026",
    tab_verify: "Harness Verification",
    tab_dashboard: "Dashboard",
    tab_submit: "Submit Request",
    tab_escalation: "Escalation Inbox",
    tab_policy: "Company Policy",
    hero_title: "AUTOMATED HARNESS VERIFICATION",
    hero_desc: "Executes 5 benchmark test scenarios to verify automated approval and escalation routing logic.",
    btn_run_harness: "RUN HARNESS TEST (5 SCENARIOS)",
    stat_total: "Total Cases",
    stat_auto: "Auto Approved",
    stat_escalate: "Escalated",
    stat_overall: "Overall Result",
    table_harness_title: "HARNESS BENCHMARK RESULTS",
    table_harness_sub: "Comparison of expected outcomes vs. AI agent decisions",
    th_test_id: "ID",
    th_scenario: "Scenario Description",
    th_expected: "Expected",
    th_actual: "AI Decision",
    th_category: "Category",
    th_authority: "Authority",
    th_question: "Actionable Question",
    th_status: "Status",
    playground_title: "CUSTOM TEST PLAYGROUND",
    playground_sub: "Submit a custom scenario to evaluate real-time agent responses",
    lbl_emp_name: "Employee Name",
    lbl_dept: "Department",
    lbl_leave_type: "Leave Type",
    lbl_balance: "Remaining Leave Balance (Days)",
    lbl_start_date: "Start Date",
    lbl_end_date: "End Date",
    lbl_attachment: "Attachment Status",
    lbl_handover: "Handover Employee ID",
    lbl_reason: "Leave Reason",
    btn_evaluate: "EVALUATE REQUEST",
    dash_total: "Total Requests",
    dash_auto: "Auto Approved",
    dash_pending: "Pending Approval",
    dash_override: "Override Approved",
    dash_title: "LEAVE REQUESTS HISTORY",
    dash_sub: "Track leave records and audit trail logs",
    opt_all: "All Statuses",
    opt_pending: "Pending Approval",
    opt_completed: "Completed",
    opt_rejected: "Rejected",
    btn_refresh: "Refresh",
    th_req_id: "ID",
    th_employee: "Employee",
    th_department: "Department",
    th_period: "Period",
    th_days: "Days",
    th_type: "Type",
    th_decision: "Decision",
    th_req_status: "Status",
    th_action: "Action",
    submit_title: "SUBMIT LEAVE REQUEST",
    submit_sub: "Submit via natural language text input or standard structured form",
    btn_nlp: "NLP Text Input",
    btn_form: "Standard Form",
    lbl_chat_emp: "Select Employee",
    lbl_chat_input: "Leave Request Message",
    btn_submit_req: "SUBMIT LEAVE REQUEST",
    esc_title: "ESCALATION INBOX (HUMAN-IN-THE-LOOP)",
    esc_sub: "Requests requiring Manager or Executive review",
    esc_empty: "Inbox Empty! All compliant leave requests have been automatically processed.",
    esc_pills_title: "QUICK ACTION SUGGESTIONS (CLICK TO APPROVE INSTANTLY):",
    policy_title: "CORPORATE LEAVE POLICY (GROUND TRUTH)",
    policy_sub: "Document Code: POL-HR-2026-01 | Governance Framework",
    modal_audit_title: "AUDIT TRAIL LOG",
    badge_auto: "Auto Approved",
    badge_escalate: "Escalated",
    badge_override: "Override Approved",
    badge_rejected: "Rejected",
    badge_completed: "Completed",
    badge_pending: "Pending Review",
    btn_audit: "Audit Log"
  }
};

document.addEventListener("DOMContentLoaded", () => {
  checkServerHealth();
  checkLlmHealth();

  const safeInit = (fn, name) => {
    try { fn(); } catch (e) { console.warn(`[Init] ${name} error:`, e); }
  };

  safeInit(initLanguage, "Language");
  safeInit(initTabs, "Tabs");
  safeInit(initVerifyHarness, "VerifyHarness");
  safeInit(initCustomVerify, "CustomVerify");
  safeInit(initDashboard, "Dashboard");
  safeInit(initSubmitLeave, "SubmitLeave");
  safeInit(initEscalationInbox, "EscalationInbox");
  safeInit(initPolicyViewer, "PolicyViewer");
  safeInit(loadEmployees, "Employees");

  setInterval(checkServerHealth, 10000);
  setInterval(checkLlmHealth, 5000);
  
  inboxInterval = setInterval(() => {
    const escTab = document.getElementById("tab-escalation");
    if (escTab && escTab.classList.contains("active")) {
      loadEscalationInbox(true);
    }
  }, 5000);
});

/* ========================================================================= */
/* 0. LANGUAGE SWITCHER                                                      */
/* ========================================================================= */
function initLanguage() {
  const langBtn = document.getElementById("btn-lang-toggle");
  if (langBtn) {
    langBtn.innerText = currentLang === "vi" ? "🌐 VI (Bật EN)" : "🌐 EN (Switch VI)";
    langBtn.addEventListener("click", () => {
      currentLang = currentLang === "vi" ? "en" : "vi";
      localStorage.setItem("app_lang", currentLang);
      langBtn.innerText = currentLang === "vi" ? "🌐 VI (Bật EN)" : "🌐 EN (Switch VI)";
      applyLanguage();
    });
  }
  applyLanguage();
}

function applyLanguage() {
  const dict = I18N[currentLang] || I18N.vi;
  document.querySelectorAll("[data-i18n]").forEach(elem => {
    const key = elem.getAttribute("data-i18n");
    if (dict[key]) {
      elem.innerText = dict[key];
    }
  });

  // Re-render dynamic components
  if (activeRequests.length > 0) renderRequestsTable(activeRequests);
  const escTab = document.getElementById("tab-escalation");
  if (escTab && escTab.classList.contains("active")) loadEscalationInbox(false);
}

function t(key) {
  return (I18N[currentLang] && I18N[currentLang][key]) || (I18N.vi[key] || key);
}

function initPolicyViewer() {
  // Loaded when policy tab is active
}

/* ========================================================================= */
/* 1. TAB NAVIGATION                                                         */
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

    if (tabId === "tab-dashboard") loadDashboardData();
    if (tabId === "tab-escalation") loadEscalationInbox();
    if (tabId === "tab-policy") loadPolicyDocument();
  }
}

/* ========================================================================= */
/* 2. HARNESS VERIFICATION                                                   */
/* ========================================================================= */
function initVerifyHarness() {
  const btnRun = document.getElementById("btn-exec-harness");
  if (!btnRun) return;

  btnRun.addEventListener("click", async () => {
    btnRun.disabled = true;
    btnRun.innerHTML = `<span>${currentLang === "vi" ? "Đang chạy 5 kịch bản..." : "Executing 5 scenarios..."}</span>`;

    try {
      const res = await fetch(`${API_BASE}/api/verify/escalation`, { method: "POST" });
      const data = await res.json();

      if (!data.success) throw new Error(data.detail || "Lỗi kịch bản kiểm thử");

      renderHarnessResults(data);
      showToast(currentLang === "vi" ? "Đã thực thi xong 5 kịch bản kiểm thử!" : "5 benchmark scenarios executed!", "success");
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      btnRun.disabled = false;
      btnRun.innerHTML = `<span>${t("btn_run_harness")}</span>`;
    }
  });
}

function renderHarnessResults(data) {
  const stats = data.summary;
  const details = data.details;

  const statsBar = document.getElementById("harness-stats");
  statsBar.style.display = "grid";

  document.getElementById("stat-total").innerText = stats.total_cases;
  document.getElementById("stat-auto").innerText = `${stats.auto_approved_cases} / ${stats.target_auto}`;
  document.getElementById("stat-escalate").innerText = `${stats.escalated_cases} / ${stats.target_escalate}`;
  document.getElementById("stat-overall").innerText = stats.overall_status === "PASS" ? "ĐẠT (PASS 100%)" : stats.overall_status;

  const cardTable = document.getElementById("card-harness-table");
  cardTable.style.display = "block";

  const tbody = document.getElementById("harness-results-body");
  tbody.innerHTML = "";

  details.forEach(item => {
    const tr = document.createElement("tr");

    const expectedBadge = item.expected_decision === "AUTO_APPROVE"
      ? `<span class="tag-decision tag-auto">${t("badge_auto")}</span>`
      : `<span class="tag-decision tag-escalate">${t("badge_escalate")}</span>`;

    const actualBadge = item.actual_decision === "AUTO_APPROVE"
      ? `<span class="tag-decision tag-auto">${t("badge_auto")}</span>`
      : `<span class="tag-decision tag-escalate">${t("badge_escalate")}</span>`;

    const catTag = item.actual_category 
      ? `<span class="tag-category">${item.actual_category}</span>` 
      : `<span style="color: var(--text-dim);">-</span>`;

    const statusBadge = item.is_passed
      ? `<span style="color: var(--emerald); font-weight: 700;">ĐẠT / PASS</span>`
      : `<span style="color: var(--rose); font-weight: 700;">FAIL</span>`;

    tr.innerHTML = `
      <td style="font-family: var(--font-mono); font-weight: 700; color: var(--primary);">${item.test_id}</td>
      <td style="font-weight: 600;">${item.scenario_name}</td>
      <td>${expectedBadge}</td>
      <td>${actualBadge}</td>
      <td>${catTag}</td>
      <td style="color: var(--text-muted); font-size: 0.8rem;">${item.target_role || "Tự động"}</td>
      <td>
        <div class="question-preview">${item.actionable_question}</div>
      </td>
      <td>${statusBadge}</td>
    `;
    tbody.appendChild(tr);
  });

  cardTable.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ========================================================================= */
/* 3. CUSTOM TEST PLAYGROUND                                                 */
/* ========================================================================= */
function initCustomVerify() {
  const form = document.getElementById("form-custom-verify");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-submit-custom");
    btn.disabled = true;
    btn.innerHTML = `<span>${currentLang === "vi" ? "Đang phân tích..." : "Evaluating..."}</span>`;

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
        showToast(currentLang === "vi" ? "Mô hình LLM chưa được bật!" : "LLM server offline!", "error");
      } else {
        showToast(currentLang === "vi" ? "Đã phân tích xong ca kiểm thử!" : "Scenario evaluated!", "success");
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>${t("btn_evaluate")}</span>`;
    }
  });
}

function renderCustomVerifyResult(data) {
  const container = document.getElementById("custom-result-card");
  container.style.display = "block";

  if (data.decision === "LLM_OFFLINE") {
    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <h4 style="font-weight: 700; color: #b91c1c;">${currentLang === "vi" ? "KẾT QUẢ ĐÁNH GIÁ:" : "RESULT:"}</h4>
        <span class="tag-decision" style="background: #fef2f2; color: #b91c1c; border: 1px solid #f87171; font-size: 0.85rem; font-weight: 700; padding: 4px 10px; border-radius: 6px;">
          LLM OFFLINE
        </span>
      </div>
      <div style="background: #fff5f5; border: 1px solid #fca5a5; border-radius: 8px; padding: 14px; color: #991b1b; font-size: 0.88rem;">
        ${data.plain_reason}
      </div>
    `;
    container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }

  const isAuto = data.decision === "AUTO_APPROVE";
  const badge = isAuto
    ? `<span class="tag-decision tag-auto" style="font-size: 0.85rem;">${t("badge_auto")}</span>`
    : `<span class="tag-decision tag-escalate" style="font-size: 0.85rem;">${t("badge_escalate")}</span>`;

  let clausesHtml = "";
  if (data.applied_policy_clauses && data.applied_policy_clauses.length > 0) {
    clausesHtml = `
      <div style="margin-top: 12px; font-size: 0.8rem; color: var(--text-dim);">
        <strong>${currentLang === "vi" ? "Căn cứ quy chế:" : "Applicable Policy Clauses:"}</strong> ${data.applied_policy_clauses.join(" | ")}
      </div>
    `;
  }

  container.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
      <h4 style="font-weight: 700; color: var(--text-main);">${currentLang === "vi" ? "KẾT QUẢ PHÂN TÍCH:" : "AI EVALUATION RESULT:"}</h4>
      ${badge}
    </div>
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px; font-size: 0.84rem;">
      <div class="stat-box" style="padding: 10px;">
        <div class="stat-label">${currentLang === "vi" ? "Số ngày làm việc" : "Calculated Workdays"}</div>
        <div style="font-weight: 700; font-size: 1.1rem; color: var(--primary);">${data.calculated_workdays} ${currentLang === "vi" ? "ngày" : "days"}</div>
      </div>
      <div class="stat-box" style="padding: 10px;">
        <div class="stat-label">${currentLang === "vi" ? "Phân loại" : "Category"}</div>
        <div style="font-weight: 700; color: #d97706;">${data.uncertainty_category || "None"}</div>
      </div>
      <div class="stat-box" style="padding: 10px;">
        <div class="stat-label">${currentLang === "vi" ? "Thẩm quyền" : "Target Role"}</div>
        <div style="font-weight: 700; color: var(--primary);">${data.target_role || "Tự động"}</div>
      </div>
    </div>
    ${!isAuto ? `
      <div class="action-question-box">
        <div class="action-question-title">${currentLang === "vi" ? "CÂU HỎI XỬ LÝ DÀNH CHO QUẢN LÝ:" : "ACTIONABLE QUESTION FOR APPROVER:"}</div>
        <div class="action-question-text">"${data.actionable_question}"</div>
      </div>
    ` : `
      <div style="color: #047857; font-weight: 600; padding: 12px; background: rgba(16, 185, 129, 0.1); border-radius: 8px; font-size: 0.88rem;">
        ${data.plain_reason}
      </div>
    `}
    ${clausesHtml}
  `;

  container.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ========================================================================= */
/* 4. DASHBOARD & REQUESTS TABLE                                             */
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
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 30px;">${currentLang === "vi" ? "Không có đơn nào." : "No leave requests found."}</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  requests.forEach(req => {
    const tr = document.createElement("tr");

    let decBadge = `<span class="tag-decision tag-auto">${t("badge_auto")}</span>`;
    if (req.decision === "ESCALATE" || req.decision === "ESCALATED_PENDING_HUMAN") {
      decBadge = `<span class="tag-decision tag-escalate">${t("badge_escalate")}</span>`;
    } else if (req.decision === "APPROVED_BY_HUMAN_OVERRIDE") {
      decBadge = `<span class="tag-decision tag-approved-override">${t("badge_override")}</span>`;
    } else if (req.decision === "REJECTED" || req.decision === "REJECTED_BY_HUMAN") {
      decBadge = `<span class="tag-decision tag-rejected">${t("badge_rejected")}</span>`;
    }

    const statusBadge = req.status === "COMPLETED"
      ? `<span style="color: var(--emerald); font-weight: 600;">${t("badge_completed")}</span>`
      : (req.status === "PENDING_ESCALATION" 
          ? `<span style="color: var(--amber); font-weight: 600;">${t("badge_pending")}</span>`
          : `<span style="color: var(--rose);">${currentLang === "vi" ? "Đã đóng" : "Closed"}</span>`);

    tr.innerHTML = `
      <td style="font-family: var(--font-mono); font-weight: 700; color: var(--primary);">${req.id}</td>
      <td style="font-weight: 600;">${req.employee_name}</td>
      <td style="color: var(--text-muted);">${req.department}</td>
      <td style="font-size: 0.84rem;">${req.from_date || "N/A"} → ${req.to_date || "N/A"}</td>
      <td style="font-family: var(--font-mono); font-weight: 700;">${req.workdays} ${currentLang === "vi" ? "ngày" : "d"}</td>
      <td>${req.leave_type}</td>
      <td>${decBadge}</td>
      <td>${statusBadge}</td>
      <td>
        <button class="btn-secondary" onclick="openAuditModal('${req.id}')" style="padding: 4px 10px; font-size: 0.78rem;">
          ${t("btn_audit")}
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

/* ========================================================================= */
/* 5. SUBMIT LEAVE REQUEST                                                   */
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

  document.getElementById("btn-submit-chat").addEventListener("click", async () => {
    const text = document.getElementById("chat-raw-input").value.trim();
    if (!text) return showToast(currentLang === "vi" ? "Vui lòng nhập nội dung xin nghỉ!" : "Please enter leave request text!", "error");

    const empId = document.getElementById("chat-employee-select").value;
    const btn = document.getElementById("btn-submit-chat");
    btn.disabled = true;
    btn.innerHTML = `<span>${currentLang === "vi" ? "Đang phân tích..." : "Analyzing..."}</span>`;

    try {
      const res = await fetch(`${API_BASE}/api/leave/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: text, employee_id: empId })
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.detail);

      showToast(currentLang === "vi" ? `Đã nộp đơn ${data.data.id} thành công!` : `Request ${data.data.id} submitted!`, "success");
      document.getElementById("chat-raw-input").value = "";
      loadDashboardData();
      
      if (data.data.status === "PENDING_ESCALATION") {
        switchTab("tab-escalation");
      } else {
        switchTab("tab-dashboard");
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>${t("btn_submit_req")}</span>`;
    }
  });

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

      showToast(currentLang === "vi" ? `Đã nộp đơn thành công (${data.data.id})!` : `Request submitted (${data.data.id})!`, "success");
      loadDashboardData();
      switchTab("tab-dashboard");
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    }
  });
}

/* ========================================================================= */
/* 6. ESCALATION INBOX (1-CLICK INSTANT OPTION SUBMISSION)                   */
/* ========================================================================= */
function initEscalationInbox() {
  document.getElementById("btn-refresh-inbox").addEventListener("click", () => loadEscalationInbox(false));
}

async function loadEscalationInbox(isSilent = false) {
  const container = document.getElementById("escalation-inbox-list");
  try {
    const res = await fetch(`${API_BASE}/api/leave/requests?status=PENDING_ESCALATION`);
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    const pending = json.data;
    
    const inboxBadge = document.getElementById("inbox-badge");
    if (pending.length > 0) {
      inboxBadge.innerText = pending.length;
      inboxBadge.style.display = "inline";
    } else {
      inboxBadge.style.display = "none";
    }

    if (pending.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; color: var(--text-dim); padding: 48px 0;">
          <div style="font-weight: 700; color: var(--text-main); font-size: 1.05rem;">${t("esc_empty")}</div>
        </div>
      `;
      return;
    }

    if (isSilent && container.querySelectorAll(".escalation-card").length === pending.length) {
      return;
    }

    container.innerHTML = "";
    pending.forEach(item => {
      const card = document.createElement("div");
      card.className = "escalation-card";
      card.id = `card-escalation-${item.id}`;

      let pillsHtml = "";
      if (item.quick_action_options && item.quick_action_options.length > 0) {
        pillsHtml = `
          <div style="font-size: 0.76rem; color: var(--text-dim); margin-bottom: 6px; font-weight: 600;">${t("esc_pills_title")}</div>
          <div class="quick-options-container">
            ${item.quick_action_options.map(opt => `
              <button class="btn-option-pill" onclick="selectQuickOption('${item.id}', '${opt.replace(/'/g, "\\'")}')">
                ${opt}
              </button>
            `).join("")}
          </div>
        `;
      }

      card.innerHTML = `
        <div class="escalation-header">
          <div>
            <span style="font-family: var(--font-mono); font-weight: 700; color: var(--primary); font-size: 0.85rem;">${item.id}</span>
            <h3 style="font-size: 1.1rem; font-weight: 700; margin-top: 2px;">
              ${item.employee_name} ${currentLang === "vi" ? "xin nghỉ" : "requested"} ${item.workdays} ${currentLang === "vi" ? "ngày" : "days"} (${item.from_date} → ${item.to_date})
            </h3>
            <div style="font-size: 0.82rem; color: var(--text-muted);">${currentLang === "vi" ? "Phòng ban" : "Dept"}: ${item.department} · ${currentLang === "vi" ? "Loại" : "Type"}: ${item.leave_type}</div>
          </div>
          <span class="approver-badge">${currentLang === "vi" ? "Cấp duyệt" : "Target Role"}: ${item.target_role || "Quản lý"}</span>
        </div>

        <div class="action-question-box">
          <div class="action-question-title">${currentLang === "vi" ? "CÂU HỎI XỬ LÝ DÀNH CHO CẤP THẨM QUYỀN:" : "ACTIONABLE QUESTION FOR APPROVER:"}</div>
          <div class="action-question-text">"${item.actionable_question || "Vui lòng xem xét đơn nghỉ này."}"</div>
        </div>

        <div style="background: #f8fbff; border: 1px solid #e2e8f0; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 0.84rem; color: var(--text-muted);">
          <strong>${currentLang === "vi" ? "Lý do chuyển tiếp:" : "System Explanation:"}</strong> ${item.human_readable_explanation || "Vi phạm quy chế hoặc vượt trần tự duyệt."}
        </div>

        ${pillsHtml}

        <div style="display: flex; gap: 12px; align-items: center; margin-top: 12px;" id="action-row-${item.id}">
          <input type="text" id="feedback-input-${item.id}" placeholder="${currentLang === "vi" ? "Gõ câu trả lời hoặc chỉ đạo..." : "Type decision feedback or click an option above..."}" style="flex: 1;">
          <button class="btn-primary" id="btn-submit-human-${item.id}" onclick="submitHumanDecision('${item.id}')" style="white-space: nowrap;">
            <span>${currentLang === "vi" ? "Gửi chỉ đạo & Phê duyệt" : "Submit Decision"}</span>
          </button>
        </div>
      `;

      container.appendChild(card);
    });
  } catch (err) {
    if (!isSilent) container.innerHTML = `<div style="color: var(--rose);">Lỗi: ${err.message}</div>`;
  }
}

async function selectQuickOption(requestId, optionText) {
  const input = document.getElementById(`feedback-input-${requestId}`);
  if (input) {
    input.value = optionText;
  }
  await submitHumanDecision(requestId);
}

async function submitHumanDecision(requestId) {
  const input = document.getElementById(`feedback-input-${requestId}`);
  const feedback = input ? input.value.trim() : "";
  if (!feedback) return showToast(currentLang === "vi" ? "Vui lòng nhập chỉ đạo hoặc chọn gợi ý!" : "Please enter feedback or select a quick option!", "error");

  const btn = document.getElementById(`btn-submit-human-${requestId}`);
  const card = document.getElementById(`card-escalation-${requestId}`);

  if (btn) {
    btn.disabled = true;
    btn.innerText = currentLang === "vi" ? "Đang xử lý..." : "Processing...";
  }
  if (card) {
    card.style.opacity = "0.6";
    card.style.pointerEvents = "none";
  }

  try {
    const res = await fetch(`${API_BASE}/api/leave/${requestId}/human-decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback_text: feedback, approver_id: "MANAGER_DEMO" })
    });
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    showToast(currentLang === "vi" ? `Đã ghi nhận chỉ đạo thành công (${json.data.decision})!` : `Decision recorded successfully (${json.data.decision})!`, "success");
    
    await loadEscalationInbox(false);
    await loadDashboardData();
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    if (btn) {
      btn.disabled = false;
      btn.innerText = currentLang === "vi" ? "Gửi chỉ đạo & Phê duyệt" : "Submit Decision";
    }
    if (card) {
      card.style.opacity = "1";
      card.style.pointerEvents = "auto";
    }
  }
}

/* ========================================================================= */
/* 7. POLICY VIEWER                                                          */
/* ========================================================================= */
async function loadPolicyDocument() {
  const container = document.getElementById("policy-content");
  try {
    const res = await fetch(`${API_BASE}/api/meta/policy`);
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    let md = json.content_markdown;

    // Convert blockquotes to callout boxes
    md = md.replace(/^> (.*$)/gim, '<div class="policy-blockquote">$1</div>');

    // Parse Markdown tables
    const tableRegex = /\|(.+)\|\n\|[-:\s|]+\|\n((?:\|.+\|\n?)+)/g;
    md = md.replace(tableRegex, (match, header, body) => {
      const headersHtml = header.split('|').filter(h => h.trim()).map(h => `<th>${h.trim()}</th>`).join('');
      const rowsHtml = body.trim().split('\n').map(row => {
        const cols = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
        return `<tr>${cols}</tr>`;
      }).join('');
      return `<div class="table-responsive" style="margin: 16px 0;"><table class="custom-table"><thead><tr>${headersHtml}</tr></thead><tbody>${rowsHtml}</tbody></table></div>`;
    });

    md = md.replace(/### (.*)/g, '<h3 style="color: #0284c7; margin: 20px 0 8px 0; font-size: 1.15rem; font-weight: 700; border-left: 3px solid #0284c7; padding-left: 10px;">$1</h3>');
    md = md.replace(/## (.*)/g, '<h2 style="color: #0369a1; margin: 26px 0 12px 0; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; font-size: 1.35rem; font-weight: 700;">$1</h2>');
    md = md.replace(/# (.*)/g, '<h1 style="color: #0f172a; margin: 0 0 16px 0; font-size: 1.55rem; font-weight: 800; text-align: center; text-transform: uppercase;">$1</h1>');
    md = md.replace(/\*\*(.*?)\*\*/g, '<strong style="color: #0f172a;">$1</strong>');
    md = md.replace(/\* (.*)/g, '<li style="margin-left: 20px; color: #334155; margin-bottom: 4px;">$1</li>');
    md = md.replace(/\n\n/g, '<br>');

    container.innerHTML = md;
  } catch (err) {
    container.innerHTML = `<div style="color: var(--rose);">Lỗi nạp quy chế: ${err.message}</div>`;
  }
}

/* ========================================================================= */
/* 8. MODAL AUDIT TRAIL LOG                                                 */
/* ========================================================================= */
async function openAuditModal(requestId) {
  const modal = document.getElementById("modal-audit");
  document.getElementById("modal-audit-sub").innerText = `${currentLang === "vi" ? "Mã đơn" : "Request ID"}: ${requestId}`;
  const timeline = document.getElementById("audit-timeline");
  timeline.innerHTML = `<div style="color: var(--text-dim);">${currentLang === "vi" ? "Đang tải nhật ký..." : "Loading audit logs..."}</div>`;
  modal.classList.add("open");

  try {
    const res = await fetch(`${API_BASE}/api/leave/${requestId}`);
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    const logs = json.audit_trail;
    if (logs.length === 0) {
      timeline.innerHTML = `<div style="color: var(--text-dim);">${currentLang === "vi" ? "Không có nhật ký." : "No audit logs available."}</div>`;
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
    timeline.innerHTML = `<div style="color: var(--rose);">Error: ${err.message}</div>`;
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
/* 9. METADATA & HEALTH                                                     */
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
    handoverSelect.innerHTML = `<option value="">-- ${currentLang === "vi" ? "Không chỉ định" : "None Specified"} --</option>`;

    employeesCache.forEach(emp => {
      const optText = `${emp.name} (${emp.employee_id} - ${emp.department}) [${currentLang === "vi" ? "Phép:" : "Balance:"} ${emp.remaining_leave_days}d]`;
      const opt = new Option(optText, emp.employee_id);
      chatSelect.appendChild(opt.cloneNode(true));
      formSelect.appendChild(opt.cloneNode(true));

      const optHandover = new Option(`${emp.name} (${emp.department})`, emp.employee_id);
      handoverSelect.appendChild(optHandover);
    });
  } catch (e) {
    console.error("Error loading employees list:", e);
  }
}

async function checkServerHealth() {
  const statusElem = document.getElementById("server-status-text");
  try {
    const res = await fetch(`${API_BASE}/api/meta/health`);
    if (res.ok) {
      statusElem.innerText = currentLang === "vi" ? "Máy chủ: Đang chạy (:8000)" : "Backend: Online (:8000)";
      statusElem.parentElement.className = "badge badge-online";
    } else {
      throw new Error();
    }
  } catch {
    statusElem.innerText = currentLang === "vi" ? "Máy chủ: Mất kết nối" : "Backend: Disconnected";
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
        textElem.innerText = `LLM: Qwen 2.5 7B (${currentLang === "vi" ? "Sẵn sàng" : "Ready"})`;
        badgeElem.style.borderColor = "var(--emerald)";
        badgeElem.style.background = "#ecfdf5";
        badgeElem.style.color = "#047857";
        badgeElem.style.cursor = "default";
        if (dotElem) dotElem.style.background = "var(--emerald)";
      } else if (data.loading) {
        textElem.innerText = `LLM: ${currentLang === "vi" ? "Đang nạp vào GPU..." : "Loading into GPU..."}`;
        badgeElem.style.borderColor = "var(--amber)";
        badgeElem.style.background = "#fffbeb";
        badgeElem.style.color = "#b45309";
        badgeElem.style.cursor = "wait";
        if (dotElem) dotElem.style.background = "var(--amber)";
      } else {
        textElem.innerText = `LLM: ${currentLang === "vi" ? "Bấm nạp Qwen 2.5 7B" : "Load Qwen 2.5 7B"}`;
        badgeElem.style.borderColor = "#94a3b8";
        badgeElem.style.background = "#f8fafc";
        badgeElem.style.color = "#475569";
        badgeElem.style.cursor = "pointer";
        if (dotElem) dotElem.style.background = "#94a3b8";
        badgeElem.onclick = async () => {
          showToast(currentLang === "vi" ? "Đang nạp mô hình Qwen 2.5 7B..." : "Loading Qwen 2.5 7B model...", "info");
          await fetch(`${API_BASE}/api/meta/llm-load`, { method: "POST" });
          checkLlmHealth();
        };
      }
    } else {
      throw new Error();
    }
  } catch {
    textElem.innerText = `LLM: ${currentLang === "vi" ? "Chưa nạp" : "Offline"}`;
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

  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
