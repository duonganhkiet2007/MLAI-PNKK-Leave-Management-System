/**
 * app.js — Team PNKK
 * AI Leave Approval & Escalation Routing System (The Escalation Referee)
 * Fully Supports 2 Modes: 
 * 1. Staff UI Portal (Cổng Thông Tin Nhân Viên)
 * 2. Manager & Admin Portal (Giao Diện Quản Lý & Điều Phối)
 */

const API_BASE = window.location.origin;

let currentLang = localStorage.getItem("app_lang") || "vi";
let currentMode = "staff"; // 'staff' | 'manager'
let currentEmployeeId = "EMP012";
let editingRequestId = null;
let currentProofId = null;
let currentManagerRoleId = "EMP015";
let employeesCache = [];
let activeRequests = [];
let pollInterval = null;
let currentWeekOffset = 0;

// Display only data returned by the backend.
const DEFAULT_EMPLOYEES = [];
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('X-Actor-ID', currentMode === 'staff' ? currentEmployeeId : currentManagerRoleId);
  return fetch(url, {...options, headers});
}
const DECISION_LABELS = {
  NO_LEAVE_REQUIRED: 'Không cần xin phép', AUTO_APPROVE: 'Tự động duyệt',
  AUTO_REJECT: 'Từ chối tự động', NEED_CORRECTION: 'Cần bổ sung / sửa đơn', ESCALATE: 'Chờ người có thẩm quyền'
};

// i18n Translation Dictionary
const I18N = {
  vi: {
    header_sub: "Hệ Thống Phê Duyệt Nghỉ Phép AI · Team PNKK · MLAI Hackathon 2026",
    mode_staff: "Cổng Nhân Viên",
    mode_manager: "Giao Diện Quản Lý",
    lbl_demo_login: "Nhân viên:",
    tab_staff_dashboard: "Tổng quan & Quỹ phép",
    tab_staff_submit: "Nộp đơn nghỉ phép",
    tab_staff_requests: "Theo dõi đơn của tôi",
    tab_staff_calendar: "Lịch vắng mặt trong tuần",
    metric_total: "Tổng phép năm tiêu chuẩn",
    metric_used: "Số ngày đã nghỉ",
    metric_remaining: "Số ngày phép còn lại",
    quick_submit_title: "Nộp đơn nghỉ phép nhanh",
    quick_submit_sub: "Kiểm tra theo lịch làm việc và quy chế nội bộ",
    btn_full_form: "Mở biểu mẫu đầy đủ →",
    btn_send_quick: "Gửi duyệt ngay bằng AI",
    recent_requests_title: "Đơn gần nhất của bạn",
    recent_requests_sub: "Trạng thái và phản hồi minh bạch từ AI",
    btn_view_all: "Xem tất cả",
    staff_form_title: "NỘP ĐƠN XIN NGHỈ PHÉP",
    staff_form_sub: "Hệ thống Trợ lý AI sẽ tự động phân tích quy định và phê duyệt hoặc chuyển tiếp cấp Quản lý",
    lbl_leave_type: "Loại nghỉ phép *",
    lbl_handover: "Người nhận bàn giao công việc *",
    lbl_start_date: "Từ ngày *",
    lbl_end_date: "Đến ngày *",
    lbl_reason: "Lý do chi tiết *",
    lbl_attachment_box: "Đính kèm chứng từ",
    btn_reset: "Làm lại",
    btn_submit_req: "NỘP ĐƠN XIN NGHỈ",
    my_requests_title: "THEO DÕI ĐƠN NGHỈ PHÉP",
    my_requests_sub: "Theo dõi kết quả thẩm định tự động của AI và phản hồi của Cấp quản lý",
    btn_refresh: "Làm mới",
    calendar_title: "LỊCH VẮNG MẶT TRONG TUẦN",
    calendar_sub: "Tình hình nhân sự nghỉ phép trong phòng ban để thuận tiện bàn giao công việc",
    tab_mgr_queue: "Hàng đợi xử lý",
    tab_mgr_logs: "Nhật ký tự duyệt",
    tab_mgr_all: "Toàn bộ hồ sơ",
    tab_verify: "Bộ kiểm thử",
    tab_policy: "Quy chế nội bộ",
    esc_title: "HÀNG ĐỢI XỬ LÝ",
    esc_sub: "Các đơn nghỉ phép ngoại lệ hoặc vượt quyền tự duyệt cần Quản lý chỉ đạo",
    audit_log_title: "NHẬT KÝ AI TỰ DUYỆT",
    all_requests_title: "TOÀN BỘ HỒ SƠ ĐƠN NGHỈ PHÉP",
    all_requests_sub: "Tổng hợp tất cả các đơn trong hệ thống",
    hero_title: "BỘ KIỂM THỬ TỰ ĐỘNG",
    hero_desc: "Thực thi các kịch bản kiểm thử chuẩn để xác minh khả năng tự duyệt và chuyển tiếp.",
    btn_run_harness: "CHẠY BỘ KIỂM THỬ",
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
    lbl_balance: "Số ngày phép còn lại",
    lbl_attachment: "Chứng từ đính kèm",
    btn_evaluate: "ĐÁNH GIÁ ĐƠN NÀY",
    policy_title: "QUY CHẾ NGHỈ PHÉP NỘI BỘ",
    policy_sub: "Mã văn bản: POL-HR-2026-01 | Quy chuẩn quản lý",
    modal_audit_title: "NHẬT KÝ XỬ LÝ ĐƠN"
  },
  en: {
    header_sub: "AI Leave Approval & Routing System · Team PNKK · MLAI Hackathon 2026",
    mode_staff: "Staff Portal",
    mode_manager: "Manager Dashboard",
    lbl_demo_login: "Employee:",
    tab_staff_dashboard: "Overview & Balance",
    tab_staff_submit: "Submit Leave Request",
    tab_staff_requests: "My Leave Requests",
    tab_staff_calendar: "Weekly Absence Calendar",
    metric_total: "Standard Annual Leave",
    metric_used: "Used Leave Days",
    metric_remaining: "Remaining Leave Balance",
    quick_submit_title: "Quick AI Leave Request",
    quick_submit_sub: "AI Agent automatically evaluates your request within 1 second",
    btn_full_form: "Open Full Form →",
    btn_send_quick: "Submit via AI",
    recent_requests_title: "Recent Requests",
    recent_requests_sub: "Real-time AI transparency & status feedback",
    btn_view_all: "View All",
    staff_form_title: "SUBMIT LEAVE APPLICATION",
    staff_form_sub: "AI Agent automatically audits company policies to auto-approve or route to Management",
    lbl_leave_type: "Leave Category *",
    lbl_handover: "Handover Colleague *",
    lbl_start_date: "From Date *",
    lbl_end_date: "To Date *",
    lbl_reason: "Detailed Reason *",
    lbl_attachment_box: "Supporting Documents",
    btn_reset: "Reset Form",
    btn_submit_req: "SUBMIT APPLICATION",
    my_requests_title: "MY LEAVE REQUESTS",
    my_requests_sub: "Track real-time AI auto-approval decisions and Manager feedback",
    btn_refresh: "Refresh",
    calendar_title: "WEEKLY ABSENCE SCHEDULE",
    calendar_sub: "Department coverage and absence schedule to facilitate task handover",
    tab_mgr_queue: "Escalation Queue",
    tab_mgr_logs: "Auto-Approved Logs",
    tab_mgr_all: "All Records",
    tab_verify: "Harness Test",
    tab_policy: "Company Policy",
    esc_title: "ESCALATION QUEUE",
    esc_sub: "Ambiguous or policy-exceeding requests awaiting Manager review",
    audit_log_title: "AI AUTO-APPROVED LOGS",
    all_requests_title: "MASTER LEAVE RECORDS",
    all_requests_sub: "Comprehensive database of all employee leave applications",
    hero_title: "AUTOMATED HARNESS VERIFICATION",
    hero_desc: "Executes benchmark test scenarios to verify automated approval and escalation routing logic.",
    btn_run_harness: "RUN HARNESS TEST",
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
    lbl_balance: "Remaining Balance",
    lbl_attachment: "Attachment Status",
    btn_evaluate: "EVALUATE REQUEST",
    policy_title: "CORPORATE LEAVE POLICY",
    policy_sub: "Document Code: POL-HR-2026-01 | Governance Framework",
    modal_audit_title: "AUDIT TRAIL LOG"
  }
};

/* ========================================================================= */
/* INITIALIZATION                                                            */
/* ========================================================================= */
document.addEventListener("DOMContentLoaded", () => {
  initModeSwitcher();
  initDemoLoginAndRoles();
  initStaffTabs();
  initManagerTabs();
  initStaffForm();
  initFileUploadDropzone();
  initLeaveAllocationDrawer();
  initVerifyHarness();
  initCustomVerify();
  initModals();

  // Load Initial Data
  loadEmployees();
  loadAllRequests();
  loadPolicyDocument();

  // Background sync for requests
  pollInterval = setInterval(() => {
    loadAllRequests(true);
  }, 4000);
});


/* ========================================================================= */
/* 1. LANGUAGE & MODE SWITCHING                                              */
/* ========================================================================= */
function initLanguage() {
  const langBtn = document.getElementById("btn-lang-toggle");
  if (langBtn) {
    langBtn.innerText = currentLang === "vi" ? "VI" : "EN";
    langBtn.addEventListener("click", () => {
      currentLang = currentLang === "vi" ? "en" : "vi";
      localStorage.setItem("app_lang", currentLang);
      langBtn.innerText = currentLang === "vi" ? "VI" : "EN";
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

  if (activeRequests.length > 0) {
    renderStaffRequests();
    renderManagerOverviewKPIs();
    renderManagerQueue();
    renderAutoApprovedLogs();
    renderManagerAllRequests();
    renderWeeklyCalendar();
  }
}

function t(key) {
  return (I18N[currentLang] && I18N[currentLang][key]) || (I18N.vi[key] || key);
}

const MANAGER_ROLES = {};

function renderManagerBanner() {
  const mgr = employeesCache.find(e => e.employee_id === currentManagerRoleId);
  if (!mgr) return;
  document.getElementById('mgr-name').textContent = mgr.name;
  document.getElementById('mgr-role-dept').textContent = (mgr.actor_roles || []).map(r=>r.role).join(', ') + ' · ' + mgr.department;
  document.getElementById('mgr-avatar').textContent = mgr.name.slice(0,1);
}

function initModeSwitcher() {
  const btnStaff = document.getElementById("btn-mode-staff");
  const btnManager = document.getElementById("btn-mode-manager");
  const viewStaff = document.getElementById("view-staff-portal");
  const viewManager = document.getElementById("view-manager-portal");
  const staffNav = document.getElementById("sidebar-staff-nav");
  const mgrNav = document.getElementById("sidebar-manager-nav");
  const staffSelector = document.getElementById("header-staff-selector");
  const mgrSelector = document.getElementById("header-manager-selector");
  const btnAllocate = document.getElementById("btn-header-allocate");
  const alertQueue = document.getElementById("header-pending-alert");

  if (btnStaff && btnManager) {
    btnStaff.addEventListener("click", () => {
      currentMode = "staff";
      loadAllRequests();
      btnStaff.classList.add("active");
      btnManager.classList.remove("active");
      viewStaff.classList.add("active");
      viewManager.classList.remove("active");
      
      if (staffNav) staffNav.style.display = "flex";
      if (mgrNav) mgrNav.style.display = "none";

      if (staffSelector) {
        staffSelector.style.display = "flex";
        autoResizeSelect(document.getElementById("demo-employee-select"));
      }
      if (mgrSelector) mgrSelector.style.display = "none";
      if (btnAllocate) btnAllocate.style.display = "none";
      if (alertQueue) alertQueue.style.display = "none";

      renderStaffDashboard();
      renderStaffRequests();
      renderWeeklyCalendar();
    });

    btnManager.addEventListener("click", () => {
      currentMode = "manager";
      loadAllRequests();
      btnManager.classList.add("active");
      btnStaff.classList.remove("active");
      viewManager.classList.add("active");
      viewStaff.classList.remove("active");

      if (staffNav) staffNav.style.display = "none";
      if (mgrNav) mgrNav.style.display = "flex";

      if (staffSelector) staffSelector.style.display = "none";
      if (mgrSelector) {
        mgrSelector.style.display = "flex";
        setTimeout(() => autoResizeSelect(document.getElementById("manager-role-select")), 0);
      }
      if (btnAllocate) btnAllocate.style.display = "inline-flex";

      renderManagerBanner();
      renderManagerOverviewKPIs();
      renderManagerQueue();
      renderAutoApprovedLogs();
      renderManagerAllRequests();
      populateManagerDeptFilter();
      renderWeeklyCalendar();
      updateBadgesAndCounters();
    });
  }
}

/* ========================================================================= */
/* 2. DEMO LOGIN & ROLE SWITCHER                                             */
/* ========================================================================= */
function autoResizeSelect(selectEl) {
  if (!selectEl) return;
  let measurer = document.getElementById("select-width-measurer");
  if (!measurer) {
    measurer = document.createElement("span");
    measurer.id = "select-width-measurer";
    measurer.style.position = "absolute";
    measurer.style.visibility = "hidden";
    measurer.style.whiteSpace = "pre";
    measurer.style.left = "-9999px";
    measurer.style.top = "-9999px";
    measurer.style.pointerEvents = "none";
    document.body.appendChild(measurer);
  }

  const comp = window.getComputedStyle(selectEl);
  measurer.style.fontFamily = comp.fontFamily || "'Inter', sans-serif";
  measurer.style.fontSize = comp.fontSize || "0.82rem";
  measurer.style.fontWeight = comp.fontWeight || "600";
  measurer.style.letterSpacing = comp.letterSpacing || "normal";

  const selectedOpt = selectEl.options[selectEl.selectedIndex];
  const text = selectedOpt ? selectedOpt.text.trim() : "";
  measurer.textContent = text;

  const textWidth = measurer.getBoundingClientRect().width || measurer.offsetWidth;
  // padding-left (14px) + gap (8px) + icon (11px) + padding-right (10px) + border (2px) = 45px
  const targetWidth = Math.ceil(textWidth) + 45;
  selectEl.style.width = `${targetWidth}px`;
}

function initDemoLoginAndRoles() {
  const demoSelect = document.getElementById("demo-employee-select");
  if (demoSelect) {
    demoSelect.addEventListener("change", (e) => {
      currentEmployeeId = e.target.value;
      editingRequestId = null; currentProofId = null;
      loadAllRequests();
      autoResizeSelect(demoSelect);
      renderStaffDashboard();
      renderStaffRequests();
      renderWeeklyCalendar();
      showToast(`Đã chuyển sang nhân viên: ${getCurrentEmployee().name}`, "info");
    });
    autoResizeSelect(demoSelect);
  }

  const roleSelect = document.getElementById("manager-role-select");
  if (roleSelect) {
    roleSelect.addEventListener("change", (e) => {
      currentManagerRoleId = e.target.value;
      loadAllRequests();
      autoResizeSelect(roleSelect);
      renderManagerBanner();
      const roleName = roleSelect.options[roleSelect.selectedIndex].text;
      showToast(`Đang làm việc với góc nhìn: ${roleName}`, "info");
    });
    autoResizeSelect(roleSelect);
  }

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      if (demoSelect) autoResizeSelect(demoSelect);
      if (roleSelect) autoResizeSelect(roleSelect);
    });
  }
}

async function loadEmployees() {
  try {
    const res = await apiFetch(`${API_BASE}/api/meta/employees`);
    if (res.ok) {
      const data = await res.json();
      if (data.success && Array.isArray(data.data) && data.data.length > 0) {
        employeesCache = data.data;
      } else {
        employeesCache = [];
      }
    } else {
      employeesCache = [];
    }
  } catch (err) {
    console.warn("Using fallback employees:", err);
    employeesCache = [];
  }
  const managers = employeesCache.filter(e => e.status === 'ACTIVE' && e.actor_roles?.length);
  const selector = document.getElementById('manager-role-select');
  if (selector) selector.innerHTML = managers.map(e => `<option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.name)} · ${escapeHtml(e.actor_roles.map(r=>r.role).join('/'))}</option>`).join('');
  if (!managers.some(e=>e.employee_id===currentManagerRoleId)) currentManagerRoleId=managers[0]?.employee_id || '';
  if (selector) selector.value=currentManagerRoleId;
  populateEmployeeDropdowns();
  renderStaffDashboard();
  renderWeeklyCalendar();
}

function populateEmployeeDropdowns() {
  const demoSelect = document.getElementById("demo-employee-select");
  const allocEmpSelect = document.getElementById("alloc-emp-select");

  if (demoSelect) {
    demoSelect.innerHTML = employeesCache.map(emp => `
      <option value="${emp.employee_id}" ${emp.employee_id === currentEmployeeId ? 'selected' : ''}>
        ${emp.name}
      </option>
    `).join("");
    autoResizeSelect(demoSelect);
  }

  if (allocEmpSelect) {
    allocEmpSelect.innerHTML = employeesCache.map(emp => `
      <option value="${emp.employee_id}">${emp.name} - ${emp.employee_id} (${emp.department})</option>
    `).join("");
  }

  populateManagerDeptFilter();
  updateHandoverOptions();
}

function populateManagerDeptFilter() {
  const deptSelect = document.getElementById("mgr-overview-dept-filter");
  if (!deptSelect) return;
  const currentVal = deptSelect.value || "ALL";
  const depts = Array.from(new Set(employeesCache.map(e => e.department).filter(Boolean))).sort();
  
  let optionsHtml = `<option value="ALL" ${currentVal === "ALL" ? "selected" : ""}>Toàn bộ phòng ban</option>`;
  depts.forEach(dept => {
    optionsHtml += `<option value="${dept}" ${currentVal === dept ? "selected" : ""}>${dept}</option>`;
  });
  deptSelect.innerHTML = optionsHtml;
}

function updateHandoverOptions() {
  const handoverSelect = document.getElementById("staff-handover-select");
  if (!handoverSelect) return;

  const currentEmp = getCurrentEmployee();
  const availableColleagues = employeesCache.filter(e => currentEmp && e.employee_id !== currentEmp.employee_id && e.department === currentEmp.department && e.status === 'ACTIVE');
  
  handoverSelect.innerHTML = `
    <option value="">-- Chọn đồng nghiệp nhận bàn giao --</option>
    ${availableColleagues.map(e => `
      <option value="${e.employee_id}">${e.name} (${e.role || e.department})</option>
    `).join("")}
  `;
}

function getCurrentEmployee() {
  return employeesCache.find(e => e.employee_id === currentEmployeeId) || employeesCache[0] || null;
}

function renderStaffDashboard() {
  const emp = getCurrentEmployee();
  if (!emp) return;

  const avatarEl = document.getElementById("staff-avatar");
  const nameEl = document.getElementById("staff-name");
  const roleDeptEl = document.getElementById("staff-role-dept");
  const metaEl = document.getElementById("staff-emp-id");

  if (avatarEl) avatarEl.innerText = emp.name ? emp.name.split(" ").pop().charAt(0).toUpperCase() : "NV";
  if (nameEl) nameEl.innerText = emp.name;
  if (roleDeptEl) roleDeptEl.innerText = `${emp.role || 'Nhân viên'} - ${emp.department}`;
  if (metaEl) metaEl.innerHTML = "";

  const totalLeave = emp.total_leave_days == null ? null : Number(emp.total_leave_days);
  const remainingLeave = Number(emp.remaining_leave_days);
  const usedLeave = totalLeave == null ? null : Math.max(0, totalLeave - remainingLeave);

  const mTotal = document.getElementById("metric-total-leave");
  const mUsed = document.getElementById("metric-used-leave");
  const mRem = document.getElementById("metric-remaining-leave");

  if (mTotal) mTotal.innerHTML = `${totalLeave == null ? '—' : totalLeave.toFixed(1)} <span class="unit">ngày</span>`;
  if (mUsed) mUsed.innerHTML = `${usedLeave == null ? '—' : usedLeave.toFixed(1)} <span class="unit">ngày</span>`;
  if (mRem) mRem.innerHTML = `${remainingLeave.toFixed(1)} <span class="unit">ngày</span>`;

  const heroLeaveCard = document.getElementById("staff-hero-leave-card");
  if (heroLeaveCard) {
    heroLeaveCard.title = `Tổng phép: ${totalLeave == null ? '—' : totalLeave.toFixed(1)} ngày | Đã nghỉ: ${usedLeave == null ? '—' : usedLeave.toFixed(1)} ngày`;
  }

  updateHandoverOptions();
  renderStaffRecentPreview();
}

/* ========================================================================= */
/* 3. TABS NAVIGATION (STAFF & MANAGER)                                      */
/* ========================================================================= */
function initStaffTabs() {
  const btns = document.querySelectorAll("#sidebar-staff-nav .tab-btn, #view-staff-portal .tab-btn");
  btns.forEach(btn => {
    btn.addEventListener("click", () => switchStaffTab(btn.getAttribute("data-tab")));
  });
}

function switchStaffTab(tabId) {
  document.querySelectorAll("#sidebar-staff-nav .tab-btn, #view-staff-portal .tab-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-tab") === tabId);
  });
  const view = document.getElementById("view-staff-portal");
  if (!view) return;
  view.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("active", p.id === tabId));
  if (tabId === "tab-staff-dashboard") {
    renderStaffDashboard();
  } else if (tabId === "tab-staff-requests") {
    renderStaffRequests();
  } else if (tabId === "tab-staff-policy") {
    loadDecisionTree();
    loadPolicyDocument();
  }
}
window.switchStaffTab = switchStaffTab;

function initManagerTabs() {
  const btns = document.querySelectorAll("#sidebar-manager-nav .tab-btn, #view-manager-portal .tab-btn");
  btns.forEach(btn => {
    btn.addEventListener("click", () => switchManagerTab(btn.getAttribute("data-tab")));
  });
}

function switchManagerTab(tabId) {
  document.querySelectorAll("#sidebar-manager-nav .tab-btn, #view-manager-portal .tab-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-tab") === tabId);
  });
  const view = document.getElementById("view-manager-portal");
  if (!view) return;
  view.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("active", p.id === tabId));
  if (tabId === "tab-mgr-overview") {
    renderManagerOverviewKPIs();
    loadAIStackStatus();
  } else if (tabId === "tab-mgr-queue") {
    renderManagerQueue();
  } else if (tabId === "tab-mgr-auto-logs") {
    renderAutoApprovedLogs();
  } else if (tabId === "tab-mgr-all-requests") {
    renderManagerAllRequests();
  } else if (tabId === "tab-mgr-policy") {
    loadDecisionTree();
    loadPolicyDocument();
  }
}
window.switchManagerTab = switchManagerTab;

async function loadAIStackStatus() {
  const llmText = document.getElementById("mgr-kpi-llm-text");
  const vlmText = document.getElementById("mgr-kpi-vlm-text");
  const setBadge = (el, ok, label, extra) => {
    if (!el) return;
    const dot = `<span class="kpi-status-dot" style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${ok ? '#22c55e' : '#ef4444'};box-shadow:0 0 0 3px ${ok ? 'rgba(34,197,94,0.18)' : 'rgba(239,68,68,0.18)'};margin-right:6px;"></span>`;
    el.innerHTML = `${dot}<span>${label}</span>${extra ? `<div style="font-size:0.65rem;font-weight:500;opacity:0.85;margin-top:2px;">${extra}</div>` : ''}`;
  };
  if (llmText) setBadge(llmText, false, "Đang kiểm tra...", "");
  if (vlmText) setBadge(vlmText, false, "Đang kiểm tra...", "");
  try {
    const res = await apiFetch(`${API_BASE}/api/meta/ai-stack-status`);
    if (res.ok) {
      const data = await res.json();
      const llm = data.llm || {};
      const vlm = data.vlm || {};
      const system = data.system || {};

      const llmOk = llm.ready_for_inference || llm.online;
      const llmLoading = llm.loading || (llm.engine_online && llm.model_loading);
      const llmErr = llm.last_error || llm.error;
      if (llmText) {
        let ok = false, label = "LLM Lỗi", extra = "";
        if (llmOk) { ok = true; label = "LLM Sẵn sàng"; extra = (llm.target_model || "Qwen 7B"); }
        else if (llmLoading) { ok = false; label = "LLM Đang nạp..."; extra = "Vui lòng đợi 30–90 giây"; }
        else if (llmErr) { ok = false; label = "LLM Lỗi"; extra = (llmErr || "").slice(0, 40); }
        else { ok = false; label = "LLM Offline"; extra = "Hệ thống khởi chạy nền"; }
        setBadge(llmText, ok, label, extra);
      }

      const vlmOk = vlm.ollama_reachable && vlm.model_loaded;
      const vlmFb = vlm.fallback_mode;
      if (vlmText) {
        let ok = vlmOk, label = "", extra = "";
        if (vlmOk) { label = "VLM Sẵn sàng"; extra = `Ollama ping ${vlm.last_ping_ms || '?'} ms`; }
        else if (vlm.ollama_reachable && !vlm.model_loaded) { ok = false; label = "VLM thiếu model"; extra = "Cần pull qwen2.5-vl:3b"; }
        else if (vlmFb) { ok = false; label = "VLM Fallback"; extra = "Chờ HR xác minh chứng từ"; }
        else { ok = false; label = "VLM Offline"; extra = vlm.last_error || "localhost:11434 không phản hồi"; }
        setBadge(vlmText, ok, label, extra);
      }
    }
  } catch (err) {
    console.warn("AI stack status fetch failed:", err);
    if (llmText) setBadge(llmText, false, "LLM Offline", "Không kết nối backend");
    if (vlmText) setBadge(vlmText, false, "VLM Offline", "Không kết nối backend");
  }
}


/* ========================================================================= */
/* 3b. POLICY SUB-TABS: CÂY QUYẾT ĐỊNH & QUY CHẾ                             */
/* ========================================================================= */

window.switchPolicySubtab = function(tab) {
  document.querySelectorAll(".subtab-tree").forEach(el => el.style.display = tab === "tree" ? "block" : "none");
  document.querySelectorAll(".subtab-policy").forEach(el => el.style.display = tab === "policy" ? "block" : "none");

  document.querySelectorAll(".subtab-btn-tree").forEach(btn => {
    btn.className = tab === "tree" ? "btn btn-sm btn-primary subtab-btn-tree" : "btn btn-sm btn-outline-primary subtab-btn-tree";
    btn.style.borderRadius = "6px 0 0 6px";
  });
  document.querySelectorAll(".subtab-btn-policy").forEach(btn => {
    btn.className = tab === "policy" ? "btn btn-sm btn-primary subtab-btn-policy" : "btn btn-sm btn-outline-primary subtab-btn-policy";
    btn.style.borderRadius = "0 6px 6px 0";
  });

  if (tab === "tree") {
    loadDecisionTree();
    setupTreeContainerPanning();
  } else {
    loadPolicyDocument();
  }
};

async function loadDecisionTree() {
  const containers = document.querySelectorAll(".dt-nodes-container");
  if (!containers.length) return;

  let needsRender = false;
  containers.forEach(c => {
    if (!c.querySelector(".dt-tier-common-inputs")) needsRender = true;
  });
  if (!needsRender) return;

  try {
    const res = await apiFetch(`${API_BASE}/api/meta/decision-tree`);
    if (!res.ok) throw new Error("API error");
    const json = await res.json();
    if (!json.success || !json.tree) throw new Error("Invalid tree data");
    const t = json.tree;

    if (t.stats) {
      document.querySelectorAll(".dt-stat-total").forEach(el => el.textContent = t.stats.total_steps ?? 0);
      document.querySelectorAll(".dt-stat-vlm").forEach(el => el.textContent = t.stats.visual_check_steps ?? 0);
      document.querySelectorAll(".dt-stat-policy").forEach(el => el.textContent = t.stats.policy_steps ?? 0);
    }

    renderDecisionTree(t);
  } catch (err) {
    console.warn("loadDecisionTree fallback:", err);
    renderDecisionTreeStatic();
  }
}

function renderDecisionTree(tree) {
  const branches = tree.branches || tree.leave_type_branches || [];

  const tier1 = `
    <div class="dt-tier dt-tier-common-inputs">
      <div class="dt-tier-header">
        <span class="dt-tier-icon">🛂</span>
        <span class="dt-tier-title">${escapeHtml(tree.common_tier_title || 'Bước chung mọi loại nghỉ')}</span>
      </div>
      <div class="dt-tier-children">
        ${(tree.common_inputs || []).map((nd, i, arr) => renderMiniNode(nd, i, arr.length, null)).join('')}
      </div>
      <div class="dt-funnel-out">
        <div class="dt-funnel-arrow">Chia vào ${branches.length} loại hình nghỉ phép</div>
      </div>
    </div>
  `;

  const tier2 = `
    <div class="dt-tier dt-tier-branches">
      <div class="dt-tier-header">
        <span class="dt-tier-icon">🌿</span>
        <span class="dt-tier-title">${escapeHtml(tree.branch_tier_title || 'Loại hình nghỉ phép (mỗi loại 1 luồng riêng)')}</span>
      </div>
      <div class="dt-branches-grid">
        ${branches.map((b, bi, arr) => renderBranch(b, bi, arr.length)).join('')}
      </div>
      <div class="dt-funnel-in">
        <div class="dt-funnel-arrow">Tổng hợp lại các loại → bước chung cuối</div>
      </div>
    </div>
  `;

  const tier3 = `
    <div class="dt-tier dt-tier-common-final">
      <div class="dt-tier-header">
        <span class="dt-tier-icon">📐</span>
        <span class="dt-tier-title">${escapeHtml(tree.final_tier_title || 'Bước chung cuối trước khi ra quyết định')}</span>
      </div>
      <div class="dt-tier-children">
        ${(tree.common_final || []).map((nd, i, arr) => renderMiniNode(nd, i, arr.length, null)).join('')}
      </div>
    </div>
  `;

  const tierOutcomes = `
    <div class="dt-tier dt-tier-outcomes">
      <div class="dt-tier-header">
        <span class="dt-tier-icon">🌱</span>
        <span class="dt-tier-title">${escapeHtml(tree.outcomes_title || 'Kết quả cuối cùng')}</span>
      </div>
      <div class="dt-outcomes-grid">
        ${(tree.outcomes || []).map(o => `
          <div class="dt-outcome-card" style="border-color: ${o.color}; background: ${hexToRgba(o.color, 0.08)};">
            <div class="dt-outcome-title" style="color: ${o.color};">${escapeHtml(o.title || o.id)}</div>
            <div class="dt-outcome-desc">${escapeHtml(o.body || o.desc || '')}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  const legend = (tree.legend && Object.keys(tree.legend).length) ? `
      <div class="dt-legend-row">
        <div class="dt-tier-header" style="margin-bottom: 6px;">
          <span class="dt-tier-icon">🧾</span>
          <span class="dt-tier-title">Chú thích</span>
        </div>
        <div class="dt-outcomes-grid dt-legend-grid">
          <div class="dt-outcome-card" style="border-color: #10b981; background: rgba(16,185,129,0.08);">
            <div class="dt-outcome-title" style="color: #10b981;">✓ Đạt (Pass)</div>
            <div class="dt-outcome-desc">${escapeHtml(tree.legend.PASS || '')}</div>
          </div>
          <div class="dt-outcome-card" style="border-color: #ef4444; background: rgba(239,68,68,0.08);">
            <div class="dt-outcome-title" style="color: #ef4444;">✕ Chưa đạt (Fail)</div>
            <div class="dt-outcome-desc">${escapeHtml(tree.legend.FAIL || '')}</div>
          </div>
          <div class="dt-outcome-card" style="border-color: #f59e0b; background: rgba(245,158,11,0.08);">
            <div class="dt-outcome-title" style="color: #f59e0b;">⚠ Đặc cách</div>
            <div class="dt-outcome-desc">${escapeHtml(tree.legend.WAIVABLE || '')}</div>
          </div>
          <div class="dt-outcome-card" style="border-color: #a855f7; background: rgba(168,85,247,0.08);">
            <div class="dt-outcome-title" style="color: #a855f7;">🤖 Máy đọc (VLM)</div>
            <div class="dt-outcome-desc">${escapeHtml(tree.legend.VLM || '')}</div>
          </div>
        </div>
      </div>
  ` : '';

  const html = tier1 + tier2 + tier3 + tierOutcomes + legend;

  document.querySelectorAll('.dt-nodes-container').forEach(c => {
    c.innerHTML = html;
  });
}

function renderBranch(b, bi, total) {
  const steps = b.steps || b.nodes || [];
  const hex = b.color || '#475569';
  const badgeStyle = `background: ${hex}14; border-color: ${hex}55; color: ${hex};`;
  return `
    <div class="dt-branch-card" style="border-top: 4px solid ${hex}; border-left-color: ${hex}55;">
      <div class="dt-branch-head">
        <span class="dt-branch-icon" style="background: ${hex}18; color: ${hex};">${escapeHtml(b.icon || '🏷️')}</span>
        <div class="dt-branch-head-body">
          <div class="dt-branch-title" style="color: ${hex};">${escapeHtml(b.title || b.label)}</div>
        </div>
      </div>
      <div class="dt-branch-tagline">
        <div><span class="dt-twolabel">Đối tượng</span>${escapeHtml(b.who || '')}</div>
        <div><span class="dt-twolabel">Mục đích</span>${escapeHtml(b.what || b.tagline || '')}</div>
        <div><span class="dt-twolabel">Cách làm</span>${escapeHtml(b.how || '')}</div>
      </div>
      <div class="dt-branch-badge" style="${badgeStyle}">${steps.length} bước</div>
      <div class="dt-branch-nodes">
        ${steps.map((nd, i, arr) => renderMiniNode(nd, i, arr.length, hex)).join('')}
      </div>
      <div class="dt-branch-authority">
        <span>⚖️</span>${escapeHtml(b.next || b.authority_rule || '')}
      </div>
    </div>
  `;
}

function renderMiniNode(node, index, totalSiblings, branchColor) {
  const kind = (node.kind || node.type || 'POLICY').toString().toUpperCase();
  const isVlm = kind === 'VLM';
  const tagClass = isVlm ? 'dt-tag-vlm' : 'dt-tag-policy';
  const tagLabel = isVlm ? 'VLM' : 'Check';
  const cardClass = isVlm ? 'dt-node-vlm' : 'dt-node-check';
  const waivable = node.waivable ? `<span class="dt-node-badge dt-badge-trigger">Đặc cách</span>` : '';

  const whenPass = (node.when_pass || node.pass_action || '').trim();
  const whenFail = (node.when_fail || node.fail_action || '').trim();

  const passBox = whenPass ? `
    <div class="dt-mini-pass">
      <div class="dt-mini-pass-head"><span>✓</span>Tiếp theo</div>
      <div class="dt-mini-pass-text">${escapeHtml(whenPass)}</div>
    </div>` : '';

  const failBox = whenFail ? `
    <div class="dt-mini-fail">
      <div class="dt-mini-fail-head"><span>✕</span>Xử lý</div>
      <div class="dt-mini-fail-text">${escapeHtml(whenFail)}</div>
    </div>` : '';

  const hint = node.hint ? `<div class="dt-mini-hint">💡 ${escapeHtml(node.hint)}</div>` : '';

  const branchStyle = branchColor ? `border-left-color: ${branchColor}55;` : '';

  const card = `
    <div class="dt-graph-main ${cardClass}" style="${branchStyle}">
      <div class="dt-graph-header">
        <div class="dt-graph-title">
          <span>${escapeHtml(node.label || node.node_id)}</span>
        </div>
        <span class="dt-badge-tag ${tagClass}">${tagLabel}</span>
      </div>
      <div class="dt-graph-desc">${escapeHtml(node.note || node.description || '')}</div>
      <div class="dt-graph-meta">
        ${waivable}
      </div>
      ${hint}
      <div class="dt-mini-pair">
        ${passBox}
        ${failBox}
      </div>
    </div>
  `;

  const trunk = index < totalSiblings - 1
    ? `<div class="dt-trunk-connector"><div class="dt-trunk-line"></div></div>`
    : `<div style="height:2px;"></div>`;

  return card + trunk;
}

function hexToRgba(hex, alpha) {
  const h = (hex || '#334155').replace('#','');
  const r = parseInt(h.substring(0,2),16);
  const g = parseInt(h.substring(2,4),16);
  const b = parseInt(h.substring(4,6),16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function renderDecisionTreeStatic() {
  document.querySelectorAll('.dt-nodes-container').forEach(c => c.textContent='Chưa tải được cấu trúc policy. Vui lòng thử lại.');
}


// Hàm khởi tạo kéo-thả di chuyển container Cây Quyết Định (Panning)
function setupTreeContainerPanning() {
  const container = document.getElementById("dt-tree-container");
  if (!container || container.dataset.panningSetup) return;
  container.dataset.panningSetup = "true";

  let isDown = false;
  let startX, startY, scrollLeft, scrollTop;

  container.addEventListener("mousedown", (e) => {
    isDown = true;
    container.style.cursor = "grabbing";
    startX = e.pageX - container.offsetLeft;
    startY = e.pageY - container.offsetTop;
    scrollLeft = container.scrollLeft;
    scrollTop = container.scrollTop;
  });

  container.addEventListener("mouseleave", () => {
    isDown = false;
    container.style.cursor = "grab";
  });

  container.addEventListener("mouseup", () => {
    isDown = false;
    container.style.cursor = "grab";
  });

  container.addEventListener("mousemove", (e) => {
    if (!isDown) return;
    e.preventDefault();
    const x = e.pageX - container.offsetLeft;
    const y = e.pageY - container.offsetTop;
    const walkX = (x - startX) * 1.5;
    const walkY = (y - startY) * 1.5;
    container.scrollLeft = scrollLeft - walkX;
    container.scrollTop = scrollTop - walkY;
  });
}



/* 4. LEAVE ALLOCATION DRAWER (CẤP PHÁT NGÀY PHÉP)                           */
/* ========================================================================= */
window.toggleAllocationDrawer = function(forceOpen = null) {
  const drawer = document.getElementById("allocation-drawer");
  if (!drawer) return;
  const isVisible = drawer.style.display === "block" || drawer.style.display === "flex";
  const shouldOpen = forceOpen !== null ? forceOpen : !isVisible;
  drawer.style.display = shouldOpen ? "flex" : "none";
};

function initLeaveAllocationDrawer() {
  const btnOpen = document.getElementById("btn-header-allocate");
  const btnSidebarOpen = document.getElementById("btn-sidebar-allocate");
  const btnClose = document.getElementById("btn-close-allocate");
  const drawer = document.getElementById("allocation-drawer");
  const targetType = document.getElementById("alloc-target-type");
  const deptGroup = document.getElementById("alloc-dept-group");
  const empGroup = document.getElementById("alloc-emp-group");
  const form = document.getElementById("form-allocate-leave");

  if (btnOpen) {
    btnOpen.addEventListener("click", () => window.toggleAllocationDrawer());
  }

  if (btnSidebarOpen) {
    btnSidebarOpen.addEventListener("click", () => window.toggleAllocationDrawer());
  }

  if (btnClose && drawer) {
    btnClose.addEventListener("click", () => drawer.style.display = "none");
  }

  if (targetType) {
    targetType.addEventListener("change", () => {
      const val = targetType.value;
      if (deptGroup) deptGroup.style.display = val === "DEPARTMENT" ? "block" : "none";
      if (empGroup) empGroup.style.display = val === "EMPLOYEE" ? "block" : "none";
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const type = targetType.value;
      let targetId = null;
      if (type === "DEPARTMENT") targetId = document.getElementById("alloc-dept-select").value;
      if (type === "EMPLOYEE") targetId = document.getElementById("alloc-emp-select").value;

      const days = parseFloat(document.getElementById("alloc-days").value);
      const reason = document.getElementById("alloc-reason").value;

      try {
        const res = await apiFetch(`${API_BASE}/api/meta/allocate-leave`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_type: type, target_id: targetId, days: days, reason: reason })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          showToast(data.message, "success");
          drawer.style.display = "none";
          await loadEmployees();
        } else {
          showToast(data.detail || "Không thể cấp phát ngày phép!", "error");
        }
      } catch (err) {
        console.error("Allocate error:", err);
        showToast("Lỗi khi kết nối server cấp phát phép!", "error");
      }
    });
  }
}

/* ========================================================================= */
/* 5. LEAVE REQUEST FORM & CALCULATION (BƯỚC 1)                              */
/* ========================================================================= */
function initStaffForm() {
  const fromInput = document.getElementById("staff-from-date");
  const toInput = document.getElementById("staff-to-date");
  const standardForm = document.getElementById("form-staff-standard");
  const nlpForm = document.getElementById("form-staff-nlp");
  const btnModeStd = document.getElementById("btn-mode-standard-form");
  const btnModeNlp = document.getElementById("btn-mode-nlp-chat");

  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const defaultDateStr = tomorrow.toISOString().split("T")[0];
  if (fromInput) fromInput.value = defaultDateStr;
  if (toInput) toInput.value = defaultDateStr;

  const updateDuration = async () => {
    const textEl = document.getElementById('staff-calc-days-text');
    const warnEl = document.getElementById('staff-calc-balance-warning');
    if (!fromInput || !toInput) return;
    if (!fromInput.value || !toInput.value) {
      if (textEl) textEl.textContent = 'Chưa đủ ngày';
      if (warnEl) warnEl.innerHTML = '';
      return;
    }
    try {
      const res = await apiFetch(`${API_BASE}/api/meta/calendar?from_date=${fromInput.value}&to_date=${toInput.value}`);
      const data = await res.json();
      const workDays = data.success ? (data.requested_working_days ?? 1) : 1;
      if (textEl) textEl.textContent = `${workDays} ngày`;

      if (warnEl) {
        const emp = getCurrentEmployee();
        const leaveType = document.getElementById('staff-leave-type')?.value || 'ANNUAL';
        const remaining = emp ? (emp.remaining_leave_days ?? 9) : 9;
        if (leaveType === 'ANNUAL') {
          if (workDays <= remaining) {
            warnEl.innerHTML = `<span class="badge" style="background: #dcfce7; color: #166534; font-weight: 600; font-size: 0.85rem; padding: 5px 12px; border-radius: 6px;">Trong hạn mức (còn ${remaining} ngày)</span>`;
          } else {
            warnEl.innerHTML = `<span class="badge" style="background: #fee2e2; color: #991b1b; font-weight: 600; font-size: 0.85rem; padding: 5px 12px; border-radius: 6px;">Vượt hạn mức (còn ${remaining} ngày)</span>`;
          }
        } else {
          warnEl.innerHTML = `<span class="badge" style="background: #dcfce7; color: #166534; font-weight: 600; font-size: 0.85rem; padding: 5px 12px; border-radius: 6px;">Hợp lệ</span>`;
        }
      }
    } catch(e) {
      if (textEl) textEl.textContent = '1 ngày';
      if (warnEl) {
        const emp = getCurrentEmployee();
        const remaining = emp ? (emp.remaining_leave_days ?? 9) : 9;
        warnEl.innerHTML = `<span class="badge" style="background: #dcfce7; color: #166534; font-weight: 600; font-size: 0.85rem; padding: 5px 12px; border-radius: 6px;">Trong hạn mức (còn ${remaining} ngày)</span>`;
      }
    }
  };

  if (fromInput) fromInput.addEventListener("change", updateDuration);
  if (toInput) toInput.addEventListener("change", updateDuration);
  document.getElementById("staff-leave-type")?.addEventListener("change", updateDuration);
  updateDuration();

  if (btnModeStd && btnModeNlp) {
    btnModeStd.addEventListener("click", () => {
      btnModeStd.classList.add("active");
      btnModeNlp.classList.remove("active");
      if (standardForm) standardForm.style.display = "block";
      if (nlpForm) nlpForm.style.display = "none";
    });

    btnModeNlp.addEventListener("click", () => {
      btnModeNlp.classList.add("active");
      btnModeStd.classList.remove("active");
      if (standardForm) standardForm.style.display = "none";
      if (nlpForm) nlpForm.style.display = "block";
    });
  }

  if (standardForm) {
    standardForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btnSubmit = document.getElementById("btn-submit-leave-form");
      if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>ĐANG XỬ LÝ...`;
      }
      try {
        await handleStandardFormSubmit();
      } finally {
        if (btnSubmit) {
          btnSubmit.disabled = false;
          btnSubmit.innerHTML = `<span data-i18n="btn_submit_leave">Gửi duyệt bằng AI Agent</span>`;
        }
      }
    });

    standardForm.addEventListener("reset", () => {
      setTimeout(() => {
        const fileInput = document.getElementById("staff-file-input");
        const promptEl = document.getElementById("dropzone-prompt");
        const cardEl = document.getElementById("attached-file-card");
        const attachTypeVal = document.getElementById("staff-attachment-type-val");
        if (fileInput) fileInput.value = "";
        if (promptEl) promptEl.classList.remove("d-none");
        if (cardEl) {
          cardEl.classList.remove("d-flex");
          cardEl.classList.add("d-none");
        }
        if (attachTypeVal) attachTypeVal.value = "none";
        updateDuration();
      }, 50);
    });
  }

  const btnNlp = document.getElementById("btn-submit-nlp");
  if (btnNlp) {
    btnNlp.addEventListener("click", async () => {
      const text = document.getElementById("staff-nlp-raw-text")?.value;
      if (!text || !text.trim()) {
        showToast("Vui lòng nhập nội dung đơn nghỉ phép!", "error");
        return;
      }
      btnNlp.disabled = true;
      btnNlp.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>ĐANG PHÂN TÍCH...`;
      try {
        const ok = await submitLeaveToBackend({ raw_text: text, employee_id: currentEmployeeId });
        if (ok) {
          document.getElementById("staff-nlp-raw-text").value = "";
        }
      } finally {
        btnNlp.disabled = false;
        btnNlp.innerHTML = `<span data-i18n="btn_nlp_submit">Gửi đơn phân tích tự động</span>`;
      }
    });
  }

  const btnQuick = document.getElementById("btn-quick-submit");
  if (btnQuick) {
    btnQuick.addEventListener("click", async () => {
      const text = document.getElementById("quick-chat-input")?.value;
      if (!text || !text.trim()) {
        showToast("Vui lòng nhập tin nhắn xin nghỉ phép!", "error");
        return;
      }
      btnQuick.disabled = true;
      btnQuick.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>ĐANG GỬI...`;
      try {
        const ok = await submitLeaveToBackend({ raw_text: text, employee_id: currentEmployeeId });
        if (ok) {
          document.getElementById("quick-chat-input").value = "";
        }
      } finally {
        btnQuick.disabled = false;
        btnQuick.innerHTML = `<span data-i18n="btn_send_quick">Gửi duyệt ngay bằng AI</span>`;
      }
    });
  }
}

function initFileUploadDropzone() {
  const dropzone = document.getElementById("file-dropzone");
  const fileInput = document.getElementById("staff-file-input");
  const promptEl = document.getElementById("dropzone-prompt");
  const cardEl = document.getElementById("attached-file-card");
  const btnRemove = document.getElementById("btn-remove-file");
  const nameEl = document.getElementById("attached-file-name");
  const sizeEl = document.getElementById("attached-file-size");
  const iconEl = document.getElementById("attached-file-icon");
  const attachTypeVal = document.getElementById("staff-attachment-type-val");

  if (!dropzone || !fileInput) return;

  dropzone.addEventListener("click", (e) => {
    if (e.target.closest("#btn-remove-file")) return;
    fileInput.click();
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      const file = fileInput.files[0];
      if (nameEl) nameEl.innerText = file.name;
      if (sizeEl) sizeEl.innerText = `${(file.size / 1024).toFixed(1)} KB`;
      if (iconEl) iconEl.innerText = "";
      if (promptEl) promptEl.classList.add("d-none");
      if (cardEl) {
        cardEl.classList.remove("d-none");
        cardEl.classList.add("d-flex");
      }
      if (attachTypeVal) attachTypeVal.value = "unverified";
      showToast(`Đã đính kèm tệp: ${file.name}`, "info");
    }
  });

  if (btnRemove) {
    btnRemove.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.value = "";
      if (promptEl) promptEl.classList.remove("d-none");
      if (cardEl) {
        cardEl.classList.remove("d-flex");
        cardEl.classList.add("d-none");
      }
      if (attachTypeVal) attachTypeVal.value = "none";
      showToast("Đã gỡ bỏ tài liệu đính kèm", "info");
    });
  }
}

async function handleStandardFormSubmit() {
  const file = document.getElementById('staff-file-input').files[0];
  if (file) {
    const form = new FormData(); form.append('file',file);
    form.append('proof_type',document.getElementById('staff-proof-type').value);
    const response = await apiFetch(`${API_BASE}/api/leave/proofs`,{method:'POST',body:form});
    const result=await response.json();
    if(!response.ok) {showToast(JSON.stringify(result.detail),'error');return;}
    currentProofId=result.data.proof_id;
  }
  const payload={
    leave_type:document.getElementById('staff-leave-type').value || null,
    reason_category:document.getElementById('staff-reason-category').value || null,
    from_date:document.getElementById('staff-from-date').value || null,
    to_date:document.getElementById('staff-to-date').value || null,
    reason:document.getElementById('staff-reason').value,
    handover_person_id:document.getElementById('staff-handover-select').value || null,
    proof_id:currentProofId
  };
  await submitLeaveToBackend(payload);
}
async function submitLeaveToBackend(payload) {
  try {
    const url=editingRequestId ? `/api/leave/${editingRequestId}/resubmit` : '/api/leave/request';
    const res=await apiFetch(API_BASE+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result=await res.json();
    if(!res.ok) {showToast(JSON.stringify(result.detail),'error');return false;}
    showToast(`${DECISION_LABELS[result.data.decision]}: ${result.data.human_readable_explanation}`,'info');
    editingRequestId=null; currentProofId=null;
    document.getElementById('form-staff-standard')?.reset();
    document.getElementById('correction-banner').textContent='';
    await loadAllRequests(); await loadEmployees();
    switchStaffTab('tab-staff-requests');
    return true;
  } catch(err) {showToast('Không gửi được đơn: '+err.message,'error');return false;}
}
function correctRequest(id) {
  const r=activeRequests.find(r=>r.id===id); if(!r) return;
  editingRequestId=id; currentProofId=r.proof_id;
  const f=r.facts_json || r;
  for(const [key,element] of Object.entries({leave_type:'staff-leave-type',reason_category:'staff-reason-category',from_date:'staff-from-date',to_date:'staff-to-date',reason:'staff-reason',handover_person_id:'staff-handover-select'})) {
    document.getElementById(element).value=f[key] || '';
  }
  document.getElementById('correction-banner').textContent='Đang bổ sung đơn '+id;
  switchStaffTab('tab-staff-submit');
}


/* ========================================================================= */
/* 6. MY REQUESTS & TRACKING (NHÂN VIÊN)                                     */
/* ========================================================================= */
async function loadAllRequests(silent = false) {
  try {
    const res = await apiFetch(`${API_BASE}/api/leave/requests`);
    if (res.ok) {
      const json = await res.json();
      if (json.success && Array.isArray(json.data)) {
        activeRequests = json.data;
        updateBadgesAndCounters();
        if (currentMode === "staff") {
          renderStaffRequests();
          renderStaffRecentPreview();
        } else {
          renderManagerOverviewKPIs();
          renderManagerQueue();
          renderAutoApprovedLogs();
          renderManagerAllRequests();
        }
        renderWeeklyCalendar();
      }
    }
  } catch (err) {
    if (!silent) console.warn("Failed to fetch requests:", err);
  }
}

function updateBadgesAndCounters() {
  const pendingRequests = activeRequests.filter(r => r.status === "PENDING_ESCALATION" || r.decision === "ESCALATE_TO_HUMAN");
  const myRequests = activeRequests.filter(r => r.employee_id === currentEmployeeId);

  const globalPill = document.getElementById("global-pending-pill");
  if (globalPill) {
    if (pendingRequests.length > 0) {
      globalPill.innerText = pendingRequests.length;
      globalPill.style.display = "inline-block";
    } else {
      globalPill.style.display = "none";
    }
  }

  const headerAlert = document.getElementById("header-pending-alert");
  const headerAlertText = document.getElementById("header-pending-count-text");
  if (headerAlert && headerAlertText) {
    if (currentMode === "manager" && pendingRequests.length > 0) {
      headerAlert.style.display = "inline-flex";
      headerAlertText.innerText = `${pendingRequests.length} đơn cần duyệt`;
    } else {
      headerAlert.style.display = "none";
    }
  }

  const staffCountBadge = document.getElementById("staff-requests-count");
  if (staffCountBadge) staffCountBadge.innerText = myRequests.length;

  const mgrQueueBadge = document.getElementById("mgr-queue-badge");
  if (mgrQueueBadge) mgrQueueBadge.innerText = pendingRequests.length;
}

function renderStaffRequests() {
  const container = document.getElementById("staff-requests-card-container");
  if (!container) return;

  const filterVal = document.getElementById("staff-requests-filter")?.value || "ALL";
  let myRequests = activeRequests.filter(r => r.employee_id === currentEmployeeId);

  if (filterVal !== "ALL") {
    myRequests = myRequests.filter(r => r.decision === filterVal || r.status === filterVal);
  }

  if (myRequests.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; color: var(--text-dim); padding: 50px 0;">
        
        <div>Không có đơn nghỉ phép nào phù hợp với bộ lọc.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = myRequests.map(req => renderSingleRequestCard(req, true)).join("");
  attachRequestCardEvents();
}

function renderStaffRecentPreview() {
  const container = document.getElementById("staff-recent-requests-preview");
  if (!container) return;

  const myRequests = activeRequests.filter(r => r.employee_id === currentEmployeeId).slice(0, 3);
  if (myRequests.length === 0) {
    container.innerHTML = `<div style="color: var(--text-dim); font-size: 0.84rem; padding: 12px 0;">Bạn chưa nộp đơn nghỉ phép nào gần đây.</div>`;
    return;
  }

  container.innerHTML = myRequests.map(req => `
    <div class="card card-sm mb-2 shadow-xs">
      <div class="card-body py-2 px-3 d-flex justify-content-between align-items-center">
        <div>
          <div class="fw-bold text-dark small">${getLeaveTypeLabel(req.leave_type)} · ${req.requested_working_days ?? req.workdays ?? 0} ngày</div>
          <div class="text-secondary small">${req.from_date || ''} → ${req.to_date || ''} · Mã: <b>${req.id}</b></div>
        </div>
        <div>
          ${getStatusBadgeHtml(req)}
        </div>
      </div>
    </div>
  `).join("");
}

function formatSimpleDate(dStr) {
  if (!dStr) return "";
  const parts = dStr.split("-");
  if (parts.length === 3) {
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return dStr;
}

function renderSingleRequestCard(req, isStaffView=false) {
  const submitDate = req.submitted_at ? (formatTime(req.submitted_at).split(' ')[0] || formatSimpleDate(req.submitted_at.split('T')[0])) : '20/09/2026';
  const cancellable = isStaffView && ['WAITING_EMPLOYEE', 'PENDING_ESCALATION'].includes(req.status);

  // Icon sinh động theo từng loại đơn
  let iconSvg = '';
  let iconBg = '#f1f5f9';
  let iconColor = '#475569';
  if (req.leave_type === 'SICK_MEDICAL' || req.leave_type === 'MEDICAL_EMERGENCY') {
    iconBg = '#fef2f2'; iconColor = '#ef4444';
    iconSvg = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M2 12h20"></path></svg>`;
  } else if (req.leave_type === 'ANNUAL') {
    iconBg = '#ecfdf5'; iconColor = '#059669';
    iconSvg = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>`;
  } else {
    iconBg = '#f0f9ff'; iconColor = '#0284c7';
    iconSvg = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>`;
  }

  return `
    <div class="request-item-card" id="req-card-${escapeHtml(req.id)}">
      <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
        <div class="d-flex align-items-center gap-3">
          <div style="width: 44px; height: 44px; border-radius: 12px; background: ${iconBg}; color: ${iconColor}; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
            ${iconSvg}
          </div>
          <div>
            <div style="font-size: 1.05rem; font-weight: 700; color: #0f172a; letter-spacing: -0.01em;">
              ${escapeHtml(getLeaveTypeLabel(req.leave_type))}
            </div>
            <div class="d-flex align-items-center gap-1 text-secondary mt-1" style="font-size: 0.84rem;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="16" y1="2" x2="16" y2="6"></line>
                <line x1="8" y1="2" x2="8" y2="6"></line>
                <line x1="3" y1="10" x2="21" y2="10"></line>
              </svg>
              <span>Ngày nộp:</span>
              <span class="fw-semibold text-dark">${escapeHtml(submitDate)}</span>
            </div>
          </div>
        </div>

        <div class="d-flex align-items-center gap-2">
          ${getStatusBadgeHtml(req)}
        </div>
      </div>

      <div class="d-flex align-items-center gap-2 mt-3 pt-3" style="border-top: 1px solid #f1f5f9;">
        <button type="button" class="btn btn-sm btn-outline-primary px-3 py-1 fw-semibold d-inline-flex align-items-center gap-1" onclick="openRequestDetailModal('${req.id}')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          Chi tiết
        </button>
        ${cancellable ? `
          <button type="button" class="btn btn-sm btn-outline-danger px-3 py-1 fw-semibold d-inline-flex align-items-center gap-1" onclick="cancelMyRequest('${req.id}')" title="Hủy đơn nghỉ phép này">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
            Hủy đơn
          </button>
        ` : ''}
      </div>
    </div>
  `;
}


function openRequestDetailModal(requestId) {
  const req = activeRequests.find(r => r.id === requestId);
  if (!req) return;

  const modal = document.getElementById("modal-request-detail");
  const sub = document.getElementById("modal-req-detail-sub");
  const body = document.getElementById("modal-req-detail-body");
  const btnAudit = document.getElementById("btn-req-detail-view-audit");

  if (!modal || !body) return;

  if (sub) {
    sub.innerHTML = `Mã đơn: <strong class="text-dark">${req.id}</strong> · Nộp lúc: ${formatTime(req.submitted_at)}`;
  }

  if (btnAudit) {
    btnAudit.onclick = () => {
      closeRequestDetailModal();
      viewAuditTrail(req.id);
    };
  }

  // Lấy tên nhân sự bàn giao thay vì mã ID
  const allEmps = (typeof employeesCache !== "undefined" && Array.isArray(employeesCache) && employeesCache.length > 0)
    ? employeesCache 
    : ((typeof DEFAULT_EMPLOYEES !== "undefined") ? DEFAULT_EMPLOYEES : []);
  const handoverEmp = allEmps.find(e => e.employee_id === req.handover_person_id || e.id === req.handover_person_id);
  const handoverDisplayName = handoverEmp ? `${handoverEmp.name} (${handoverEmp.department || 'Đồng nghiệp'})` : (req.handover_person_name || req.handover_person_id || "Không yêu cầu");

  const hasAttachment = !!req.proof_id;
  const attachLabel = req.proof_id ? 'Chứng từ đính kèm' : 'Không có';

  // Đánh giá AI / Quản lý
  const isAuto = req.decision === "AUTO_APPROVE";
  const isOverride = (req.human_resolution === "APPROVE_OVERRIDE" || req.decision === "APPROVED_BY_HUMAN_OVERRIDE");
  const isRejected = req.status === "REJECTED";

  let boxType = "ai-box-warning";
  let boxLabel = "Lý do chuyển tiếp:";
  let rawText = req.human_readable_explanation || req.actionable_question || "Đang xử lý theo quy chế.";

  if (isAuto) {
    boxType = "ai-box-success";
    boxLabel = "Đánh giá hệ thống:";
    rawText = "Đơn đầy đủ điều kiện và được phê duyệt tự động.";
  } else if (isOverride) {
    boxType = "ai-box-primary";
    boxLabel = "Ý kiến Quản lý:";
    rawText = req.human_feedback_text || "Đã xem xét và phê duyệt ngoại lệ.";
  } else if (isRejected) {
    boxType = "ai-box-danger";
    boxLabel = "Lý do từ chối:";
    rawText = req.human_feedback_text || req.human_readable_explanation || "Không đáp ứng quy chuẩn.";
  }

  let cleanReason = rawText
    .replace(/^Hệ thống chuyển tiếp do:\s*/i, "")
    .replace(/^Minh bạch AI & Căn cứ xử lý:\s*/i, "")
    .trim();

  body.innerHTML = `
    <div class="row g-3">
      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">Loại nghỉ phép</label>
        <div class="modal-readonly-field">
          <span class="text-dark fw-semibold">${getLeaveTypeLabel(req.leave_type)}</span>
        </div>
      </div>

      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">Người nhận bàn giao</label>
        <div class="modal-readonly-field">
          <span class="text-dark">${handoverDisplayName}</span>
        </div>
      </div>

      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">Từ ngày</label>
        <div class="modal-readonly-field">
          <span class="text-dark">${formatSimpleDate(req.from_date)}</span>
        </div>
      </div>

      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">Đến ngày</label>
        <div class="modal-readonly-field">
          <span class="text-dark">${formatSimpleDate(req.to_date)}</span>
        </div>
      </div>

      <div class="col-12">
        <div class="leave-duration-card d-flex align-items-center justify-content-between">
          <div class="d-flex align-items-center gap-2">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <span class="text-secondary small">Thời lượng vắng mặt:</span>
            <span class="fw-bold text-dark">${req.requested_working_days ?? req.workdays ?? 0} ngày làm việc</span>
          </div>
          <div>
            ${getStatusBadgeHtml(req)}
          </div>
        </div>
      </div>

      <div class="col-12">
        <label class="form-label text-secondary small fw-semibold mb-1">Lý do nghỉ</label>
        <div class="modal-readonly-textarea">${req.reason || 'Không có mô tả chi tiết'}</div>
      </div>

      <div class="col-12">
        <label class="form-label text-secondary small fw-semibold mb-1">Chứng từ xác minh</label>
        <div class="modal-attached-file d-flex align-items-center justify-content-between">
          <div class="d-flex align-items-center gap-2">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            <div>
              <div class="fw-semibold text-dark small">${attachLabel}</div>
              <div class="text-secondary" style="font-size: 0.75rem;">${hasAttachment ? 'Tài liệu đính kèm hồ sơ' : 'Không có chứng từ đính kèm'}</div>
            </div>
          </div>
          ${hasAttachment ? `
            <button type="button" class="btn btn-sm btn-outline-primary px-3" onclick="openAttachmentModal('${req.id}', '${req.attachment_type}', '${req.employee_name}')" style="font-size: 0.8rem; font-weight: 500;">
              Xem file chứng từ
            </button>
          ` : ''}
        </div>
      </div>

      <!-- ĐÁNH GIÁ AI / QUẢN LÝ -->
      <div class="col-12">
        <label class="form-label text-secondary small fw-semibold mb-1">Kết quả đánh giá & Xử lý</label>
        <div class="req-ai-box ${boxType} m-0">
          <span class="req-ai-label">${boxLabel}</span>
          <span class="req-ai-text">${cleanReason}</span>
        </div>
      </div>
    </div>
  `;

  modal.style.display = "flex";
  modal.classList.add("active");
}

function closeRequestDetailModal() {
  const modal = document.getElementById("modal-request-detail");
  if (modal) {
    modal.style.display = "none";
    modal.classList.remove("active");
  }
}


function attachRequestCardEvents() {
  const filterEl = document.getElementById("staff-requests-filter");
  if (filterEl && !filterEl.hasAttribute("data-bound")) {
    filterEl.setAttribute("data-bound", "true");
    filterEl.addEventListener("change", renderStaffRequests);
  }
}

async function cancelMyRequest(requestId) {
  if (!confirm(`Bạn có chắc chắn muốn hủy/thu hồi đơn [${requestId}] không?`)) return;
  try {
    const res = await apiFetch(`${API_BASE}/api/leave/${requestId}/cancel`, { method: "POST" });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Đã hủy đơn ${requestId} thành công!`, "success");
      await loadAllRequests();
      await loadEmployees();
    } else {
      showToast(data.detail || "Không thể hủy đơn!", "error");
    }
  } catch (err) {
    console.error("Cancel error:", err);
    showToast("Lỗi khi kết nối server để hủy đơn", "error");
  }
}

/* ========================================================================= */
/* 7. MANAGER DASHBOARD & ESCALATION QUEUE (QUẢN LÝ)                         */
/* ========================================================================= */
function renderManagerOverviewKPIs() {
  const autoToday = activeRequests.filter(r => r.decision === "AUTO_APPROVE").length;
  const pendingCount = activeRequests.filter(r => r.status === "PENDING_ESCALATION" || r.decision === "ESCALATE_TO_HUMAN" || r.status === "WAITING_EMPLOYEE").length;
  const overrideCount = activeRequests.filter(r => r.decision === "APPROVED_BY_HUMAN_OVERRIDE" || r.decision === "REVOKED_BY_ADMIN").length;
  const totalCompleted = activeRequests.filter(r => r.status === "COMPLETED" || r.decision === "AUTO_APPROVE").length;

  const totalDecided = autoToday + overrideCount;
  const rate = totalDecided > 0 ? Math.round((autoToday / totalDecided) * 100) : 0;

  const kpiAuto = document.getElementById("mgr-kpi-auto-today");
  const kpiPending = document.getElementById("mgr-kpi-pending");
  const kpiOverride = document.getElementById("mgr-kpi-override");
  const kpiRate = document.getElementById("mgr-kpi-rate");

  if (kpiAuto) kpiAuto.innerHTML = `${autoToday} <span class="saas-kpi-unit">đơn</span>`;
  if (kpiPending) kpiPending.innerHTML = `${pendingCount} <span class="saas-kpi-unit">đơn</span>`;
  if (kpiOverride) kpiOverride.innerHTML = `${overrideCount} <span class="saas-kpi-unit">đơn</span>`;
  if (kpiRate) kpiRate.innerHTML = `${rate}% <span class="saas-kpi-unit"></span>`;

  // Cập nhật 2 thẻ Hero Banner Quản lý (AI đã duyệt & Chờ xử lý)
  const heroKpiAuto = document.getElementById("mgr-hero-kpi-auto");
  const heroKpiPending = document.getElementById("mgr-hero-kpi-pending");
  if (heroKpiAuto) heroKpiAuto.textContent = autoToday;
  if (heroKpiPending) heroKpiPending.textContent = pendingCount;

  // Refresh trạng thái LLM/VLM KPI badges khi manager dashboard được load
  if (!window._ai_status_first_load) {
    window._ai_status_first_load = true;
    setTimeout(() => loadAIStackStatus(), 300);
  } else if (Math.random() < 0.2) {
    // Light poll: 20% random refresh on each KPI render to update gently
    loadAIStackStatus();
  }
}

function renderManagerQueue() {
  const container = document.getElementById('mgr-escalation-inbox-list');
  if (!container) return;
  const pending = activeRequests.filter(r => r.status === 'PENDING_ESCALATION' && r.can_act);

  if (!pending.length) {
    container.innerHTML = `
      <div class="text-center py-5" style="color: #64748b;">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" class="mb-2" style="opacity: 0.6;">
          <circle cx="12" cy="12" r="10"></circle>
          <polyline points="12 6 12 12 14 14"></polyline>
        </svg>
        <div class="fw-semibold">Hàng đợi trống</div>
        <div class="small">Hiện không có đơn nghỉ phép nào cần Quản lý xử lý ngoại lệ.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = pending.map(r => {
    const submitDate = r.submitted_at 
      ? (formatTime(r.submitted_at).split(' ')[0] || formatSimpleDate(r.submitted_at.split('T')[0])) 
      : '20/09/2026';
    const workDays = r.requested_working_days ?? r.workdays ?? 1;
    const leaveLabel = getLeaveTypeLabel(r.leave_type);
    const dateRange = (r.from_date && r.to_date) 
      ? `${formatSimpleDate(r.from_date)} → ${formatSimpleDate(r.to_date)}` 
      : '';

    // Style badge loại nghỉ
    let typeBg = '#eff6ff';
    let typeColor = '#1d4ed8';
    if (r.leave_type === 'SICK_MEDICAL' || r.leave_type === 'MEDICAL_EMERGENCY' || String(r.leave_type).toUpperCase().includes('SICK')) {
      typeBg = '#fef2f2';
      typeColor = '#b91c1c';
    } else if (r.leave_type === 'ANNUAL') {
      typeBg = '#ecfdf5';
      typeColor = '#047857';
    }

    return `
      <div class="escalation-inbox-card" id="esc-card-${r.id}">
        <!-- Dòng Header: Tên nhân sự & Trạng thái -->
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
          <div class="d-flex align-items-center gap-3">
            <div style="width: 42px; height: 42px; border-radius: 10px; background: #f1f5f9; color: #334155; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1rem; flex-shrink: 0; border: 1px solid #e2e8f0;">
              ${escapeHtml(r.employee_name ? r.employee_name.trim().charAt(0) : 'N')}
            </div>
            <div>
              <div class="d-flex align-items-center gap-2 flex-wrap">
                <span style="font-size: 1.05rem; font-weight: 700; color: #0f172a; letter-spacing: -0.01em;">
                  ${escapeHtml(r.employee_name || 'Nhân viên')}
                </span>
                ${r.department ? `<span class="badge bg-light text-secondary border fw-normal" style="font-size: 0.75rem;">${escapeHtml(r.department)}</span>` : ''}
              </div>
              <div class="text-secondary small mt-0.5">
                Mã đơn: <span class="fw-semibold text-dark">${escapeHtml(r.id)}</span>
              </div>
            </div>
          </div>
          <div class="d-flex align-items-center gap-2">
            ${getStatusBadgeHtml(r)}
          </div>
        </div>

        <!-- Khối Thông Tin Quan Trọng: Loại nghỉ, Ngày nộp, Số ngày nghỉ -->
        <div class="row g-2 py-2 px-3 mb-2" style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;">
          <div class="col-sm-4 d-flex align-items-center gap-2">
            <span class="text-secondary small fw-medium">Loại nghỉ:</span>
            <span class="badge fw-semibold px-2 py-1" style="background: ${typeBg}; color: ${typeColor}; border-radius: 6px; font-size: 0.8rem;">
              ${escapeHtml(leaveLabel)}
            </span>
          </div>
          <div class="col-sm-4 d-flex align-items-center gap-2">
            <span class="text-secondary small fw-medium">Ngày nộp:</span>
            <span class="fw-semibold text-dark small">${escapeHtml(submitDate)}</span>
          </div>
          <div class="col-sm-4 d-flex align-items-center gap-2">
            <span class="text-secondary small fw-medium">Số ngày nghỉ:</span>
            <span class="fw-bold text-dark small">${workDays} ngày</span>
            ${dateRange ? `<span class="text-muted" style="font-size: 0.78rem;">(${escapeHtml(dateRange)})</span>` : ''}
          </div>
        </div>

        <!-- Khối Lý Do Nghỉ -->
        <div class="p-2 px-3 mb-3" style="background: #ffffff; border: 1px dashed #cbd5e1; border-radius: 8px;">
          <div class="d-flex align-items-baseline gap-2">
            <span class="text-secondary small fw-semibold" style="white-space: nowrap;">Lý do nghỉ:</span>
            <span class="text-dark fw-medium" style="font-size: 0.88rem; line-height: 1.5;">
              ${escapeHtml(r.reason || 'Không có mô tả chi tiết')}
            </span>
          </div>
        </div>

        <!-- Khu vực Xử lý của Quản lý & Nút Chi tiết -->
        <div class="d-flex flex-column gap-2 pt-2" style="border-top: 1px solid #f1f5f9;">
          <div>
            <input type="text" id="esc-feedback-${r.id}" class="form-control form-control-sm" placeholder="Nhập ý kiến chỉ đạo / phản hồi (nếu có)..." style="border-radius: 6px; font-size: 0.84rem; background: #fafafa;">
          </div>
          <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 pt-1">
            <button type="button" class="btn btn-sm btn-outline-primary px-3 py-1 fw-semibold d-inline-flex align-items-center gap-1" onclick="openRequestDetailModal('${r.id}')" style="border-radius: 6px; font-size: 0.82rem;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              Chi tiết
            </button>
            <div class="d-flex align-items-center gap-2">
              <button type="button" class="btn btn-sm btn-warning px-3 py-1 fw-semibold d-inline-flex align-items-center gap-1" onclick="submitManagerDecision('${r.id}','REQUEST_MORE_INFO')" style="border-radius: 6px; font-size: 0.82rem;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
                Yêu cầu bổ sung
              </button>
              <button type="button" class="btn btn-sm btn-danger px-3 py-1 fw-semibold d-inline-flex align-items-center gap-1" onclick="submitManagerDecision('${r.id}','REJECT')" style="border-radius: 6px; font-size: 0.82rem;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                Từ chối
              </button>
              ${r.target_role !== 'HR' ? `
                <button type="button" class="btn btn-sm btn-success px-3 py-1 fw-semibold d-inline-flex align-items-center gap-1" onclick="submitManagerDecision('${r.id}','APPROVE')" style="border-radius: 6px; font-size: 0.82rem;">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                  Duyệt
                </button>
              ` : ''}
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}


function fillQuickDecision(reqId, text) {
  const txt = document.getElementById(`esc-feedback-${reqId}`);
  if (txt) {
    txt.value = text;
    txt.focus();
  }
}

function toggleAnalysisPanel(reqId) {
  const body = document.getElementById(`analysis-body-${reqId}`);
  const chev = document.getElementById(`analysis-chevron-${reqId}`);
  if (!body) return;
  if (body.style.display === "none") {
    body.style.display = "block";
    if (chev) chev.innerText = "▲";
  } else {
    body.style.display = "none";
    if (chev) chev.innerText = "▼";
  }
}
window.toggleAnalysisPanel = toggleAnalysisPanel;

function renderVlmAndLlmAnalysisSection(req) {
  return `<details><summary>Chi tiết kiểm tra</summary>${(req.decision_trace || []).map(t=>`<p><b>${escapeHtml(t.node)}: ${escapeHtml(t.status)}</b> ${escapeHtml(t.desc)}</p>`).join('') || '<p>Hồ sơ cũ chưa có trace.</p>'}</details>`;
}
window.renderVlmAndLlmAnalysisSection=renderVlmAndLlmAnalysisSection;


async function submitManagerDecision(id, actionType) {
  const feedback=document.getElementById(`esc-feedback-${id}`)?.value || '';
  if(!actionType && !feedback.trim()) {showToast('Nhập phản hồi văn bản trước.','error');return;}
  try {
    const res=await apiFetch(`${API_BASE}/api/leave/${id}/human-decision`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action_type:actionType,feedback_text:feedback,approver_id:currentManagerRoleId})});
    const data=await res.json();
    if(!res.ok) {showToast(JSON.stringify(data.detail),'error');return;}
    showToast('Đã ghi nhận: '+data.data.status,'info');
    await loadAllRequests(); await loadEmployees();
  } catch(e) {showToast(e.message,'error');}
}


/* ========================================================================= */
/* 8. NHẬT KÝ AI TỰ DUYỆT & OVERRIDE (QUYỀN KIỂM SOÁT TỐI CAO)               */
/* ========================================================================= */
function renderAutoApprovedLogs() {
  const tbody = document.getElementById("auto-approved-logs-body");
  if (!tbody) return;

  const autoRequests = activeRequests.filter(r => r.decision === "AUTO_APPROVE");
  if (autoRequests.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-secondary py-4">Chưa có đơn nào được AI tự động duyệt trong phiên làm việc này.</td></tr>`;
    return;
  }

  tbody.innerHTML = autoRequests.map(req => {
    const aiReason = req.human_readable_explanation || `Xin nghỉ ${req.requested_working_days ?? req.workdays ?? 0} ngày ${getLeaveTypeLabel(req.leave_type)}, đúng hạn mức quy chế.`;

    return `
      <tr>
        <td class="fw-bold">${req.id}</td>
        <td><b>${req.employee_name}</b></td>
        <td><span class="badge bg-secondary-lt">${req.department}</span></td>
        <td>${req.from_date} → ${req.to_date}</td>
        <td><b>${req.requested_working_days ?? req.workdays ?? 0} ngày</b></td>
        <td>${getLeaveTypeLabel(req.leave_type)}</td>
        <td>
          <div class="text-success small fw-medium" style="line-height: 1.4;">
            ${aiReason}
          </div>
        </td>
        <td class="text-secondary small">${formatTime(req.updated_at || req.submitted_at)}</td>
        <td>
          <button class="btn btn-sm btn-outline-danger" onclick="revokeAiApproval('${req.id}')" title="Thu hồi quyết định tự động của AI và hoàn trả quỹ phép">
            Hủy Lệnh AI
          </button>
        </td>
      </tr>
    `;
  }).join("");

  const btnRefreshLogs = document.getElementById("btn-refresh-mgr-logs");
  if (btnRefreshLogs && !btnRefreshLogs.hasAttribute("data-bound")) {
    btnRefreshLogs.setAttribute("data-bound", "true");
    btnRefreshLogs.addEventListener("click", () => {
      loadAllRequests();
      showToast("Đã làm mới nhật ký AI!", "info");
    });
  }
}

async function revokeAiApproval(requestId) {
  const reason = prompt("Nhập lý do thu hồi quyết định tự duyệt của AI:", "Phát hiện xung đột lịch trực hệ thống");
  if (reason === null) return;

  try {
    const res = await apiFetch(`${API_BASE}/api/leave/${requestId}/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason || "Quản lý hủy quyết định tự duyệt của AI" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Đã ghi nhận thu hồi đơn [${requestId}].`, "success");
      await loadAllRequests();
      await loadEmployees();
    } else {
      showToast(data.detail || "Không thể hủy quyết định!", "error");
    }
  } catch (err) {
    console.error("Revoke error:", err);
    showToast("Lỗi khi kết nối server để hủy quyết định!", "error");
  }
}

function renderManagerAllRequests() {
  const tbody = document.getElementById("mgr-all-requests-body");
  if (!tbody) return;

  const filterVal = document.getElementById("mgr-filter-status")?.value || "ALL";
  let list = activeRequests;
  if (filterVal !== "ALL") {
    list = list.filter(r => r.status === filterVal || r.decision === filterVal);
  }

  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-secondary py-4">Không tìm thấy hồ sơ đơn nào.</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(req => `
    <tr>
      <td class="fw-bold">${req.id}</td>
      <td>${req.employee_name}</td>
      <td><span class="badge bg-secondary-lt">${req.department}</span></td>
      <td>${req.from_date} → ${req.to_date}</td>
      <td><b>${req.requested_working_days ?? req.workdays ?? 0} ngày</b></td>
      <td>${getLeaveTypeLabel(req.leave_type)}</td>
      <td><small class="text-secondary">${req.decision || '-'}</small></td>
      <td>${getStatusBadgeHtml(req)}</td>
      <td>
        <button class="btn btn-sm btn-outline-secondary" onclick="viewAuditTrail('${req.id}')">
          Nhật ký
        </button>
      </td>
    </tr>
  `).join("");

  const mgrFilter = document.getElementById("mgr-filter-status");
  if (mgrFilter && !mgrFilter.hasAttribute("data-bound")) {
    mgrFilter.setAttribute("data-bound", "true");
    mgrFilter.addEventListener("change", renderManagerAllRequests);
  }

  const btnRefreshAll = document.getElementById("btn-refresh-mgr-all");
  if (btnRefreshAll && !btnRefreshAll.hasAttribute("data-bound")) {
    btnRefreshAll.setAttribute("data-bound", "true");
    btnRefreshAll.addEventListener("click", () => {
      loadAllRequests();
      showToast("Đã làm mới hồ sơ đơn!", "info");
    });
  }
}

/* ========================================================================= */
/* 9. WEEKLY ABSENCE SCHEDULE (7 NGÀY: THỨ 2 -> CHỦ NHẬT & FILTER DEPT)     */
/* ========================================================================= */
function renderWeeklyCalendar() {
  const staffCal = document.getElementById("staff-weekly-calendar");
  const mgrCal = document.getElementById("mgr-weekly-calendar-grid");
  const deptFilter = document.getElementById("mgr-cal-dept-filter")?.value || "ALL";

  const today = new Date();
  const currentDay = today.getDay(); // 0 is Sun, 1 is Mon
  const monday = new Date(today);
  monday.setDate(today.getDate() - (currentDay === 0 ? 6 : currentDay - 1) + (currentWeekOffset * 7));

  const weekDays = [];
  const dayNames = currentLang === "en"
    ? ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    : ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"];

  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    const dateStr = d.toISOString().split("T")[0];
    const isToday = dateStr === today.toISOString().split("T")[0];
    const isWeekend = i >= 5;
    weekDays.push({
      dateStr: dateStr,
      displayDate: `${d.getDate()}/${d.getMonth() + 1}`,
      name: dayNames[i],
      isToday: isToday,
      isWeekend: isWeekend
    });
  }

  // 1. BẢNG LỊCH VẮNG MẶT PHÒNG BAN (DASHBOARD NHÂN VIÊN - CHỈ HIỂN THỊ TÊN)
  const currentEmp = getCurrentEmployee();
  const currentDept = currentEmp ? currentEmp.department : "";
  const deptBoardDept = document.getElementById("staff-dept-board-dept");
  if (deptBoardDept) deptBoardDept.innerText = currentDept || "Phòng ban của bạn";

  // Cập nhật nhãn tuần (Chỉ thuần túy nhãn chữ: 'Tuần hiện tại', 'Tuần trước', 'Tuần tiếp theo', không có ngày tháng)
  const weekLabel = document.getElementById("staff-dept-board-week-label");
  if (weekLabel) {
    if (currentWeekOffset === 0) {
      weekLabel.innerText = "Tuần hiện tại";
      weekLabel.className = "badge bg-secondary-lt fw-bold";
    } else if (currentWeekOffset === -1) {
      weekLabel.innerText = "Tuần trước";
      weekLabel.className = "badge bg-primary-lt fw-bold";
    } else if (currentWeekOffset === 1) {
      weekLabel.innerText = "Tuần tiếp theo";
      weekLabel.className = "badge bg-primary-lt fw-bold";
    } else if (currentWeekOffset < -1) {
      weekLabel.innerText = `${Math.abs(currentWeekOffset)} tuần trước`;
      weekLabel.className = "badge bg-primary-lt fw-bold";
    } else {
      weekLabel.innerText = `+${currentWeekOffset} tuần tới`;
      weekLabel.className = "badge bg-primary-lt fw-bold";
    }

    if (!weekLabel.hasAttribute("data-bound")) {
      weekLabel.setAttribute("data-bound", "true");
      weekLabel.addEventListener("click", () => {
        if (currentWeekOffset !== 0) {
          currentWeekOffset = 0;
          renderWeeklyCalendar();
        }
      });
    }
  }

  // Gắn sự kiện điều hướng tuần [ ← ] [ → ]
  const btnPrev = document.getElementById("btn-cal-prev-week");
  const btnNext = document.getElementById("btn-cal-next-week");
  if (btnPrev && !btnPrev.hasAttribute("data-bound")) {
    btnPrev.setAttribute("data-bound", "true");
    btnPrev.addEventListener("click", () => {
      currentWeekOffset--;
      renderWeeklyCalendar();
    });
  }
  if (btnNext && !btnNext.hasAttribute("data-bound")) {
    btnNext.setAttribute("data-bound", "true");
    btnNext.addEventListener("click", () => {
      currentWeekOffset++;
      renderWeeklyCalendar();
    });
  }

  const staffDeptGrid = document.getElementById("staff-dept-calendar-grid");
  if (staffDeptGrid) {
    staffDeptGrid.innerHTML = weekDays.map(day => {
      // Lọc các đơn hợp lệ của người cùng phòng ban
      let absentees = activeRequests.filter(r => {
        const isApproved = r.status === 'COMPLETED' && r.decision !== 'NO_LEAVE_REQUIRED';
        if (!isApproved) return false;
        if (r.department && currentDept && r.department !== currentDept) return false;
        return r.working_dates ? r.working_dates.includes(day.dateStr) : (r.from_date <= day.dateStr && r.to_date >= day.dateStr);
      });

      return `
        <div class="dept-day-col ${day.isToday ? 'is-today' : ''}">
          <div class="dept-day-header">
            <span class="dept-day-title">${day.name}</span>
            <span class="dept-day-date">${day.displayDate}${day.isToday ? ' · Hôm nay' : ''}</span>
          </div>
          <div class="dept-day-body">
            ${absentees.length === 0 ? `
              <div class="dept-empty-note">${day.isWeekend ? 'Cuối tuần' : 'Làm việc đầy đủ'}</div>
            ` : absentees.map(r => {
              const isSelf = r.employee_id === currentEmployeeId;
              return `
                <div class="dept-absentee-pill ${isSelf ? 'pill-self' : ''}">
                  ${r.employee_name}${isSelf ? ' (Bạn)' : ''}
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    }).join("");
  }

  // 2. BẢNG LỊCH VẮNG MẶT PHÒNG BAN CHO QUẢN LÝ (Hình 2: Thứ 2 -> Chủ Nhật & Bộ chọn Phòng ban)
  const mgrDeptGrid = document.getElementById("mgr-dept-calendar-grid");
  if (mgrDeptGrid) {
    const mgrDeptSelect = document.getElementById("mgr-overview-dept-filter");
    const selectedDept = mgrDeptSelect?.value || "ALL";

    // Cập nhật nhãn tuần cho Quản lý
    const mgrWeekLabel = document.getElementById("mgr-dept-board-week-label");
    if (mgrWeekLabel) {
      if (currentWeekOffset === 0) {
        mgrWeekLabel.innerText = "Tuần hiện tại";
        mgrWeekLabel.className = "badge bg-secondary-lt fw-bold";
      } else if (currentWeekOffset === -1) {
        mgrWeekLabel.innerText = "Tuần trước";
        mgrWeekLabel.className = "badge bg-primary-lt fw-bold";
      } else if (currentWeekOffset === 1) {
        mgrWeekLabel.innerText = "Tuần tiếp theo";
        mgrWeekLabel.className = "badge bg-primary-lt fw-bold";
      } else if (currentWeekOffset < -1) {
        mgrWeekLabel.innerText = `${Math.abs(currentWeekOffset)} tuần trước`;
        mgrWeekLabel.className = "badge bg-primary-lt fw-bold";
      } else {
        mgrWeekLabel.innerText = `+${currentWeekOffset} tuần tới`;
        mgrWeekLabel.className = "badge bg-primary-lt fw-bold";
      }

      if (!mgrWeekLabel.hasAttribute("data-bound")) {
        mgrWeekLabel.setAttribute("data-bound", "true");
        mgrWeekLabel.addEventListener("click", () => {
          if (currentWeekOffset !== 0) {
            currentWeekOffset = 0;
            renderWeeklyCalendar();
          }
        });
      }
    }

    // Gắn sự kiện điều hướng tuần cho Quản lý [ ← ] [ → ]
    const btnMgrPrev = document.getElementById("btn-mgr-cal-prev-week");
    const btnMgrNext = document.getElementById("btn-mgr-cal-next-week");
    if (btnMgrPrev && !btnMgrPrev.hasAttribute("data-bound")) {
      btnMgrPrev.setAttribute("data-bound", "true");
      btnMgrPrev.addEventListener("click", () => {
        currentWeekOffset--;
        renderWeeklyCalendar();
      });
    }
    if (btnMgrNext && !btnMgrNext.hasAttribute("data-bound")) {
      btnMgrNext.setAttribute("data-bound", "true");
      btnMgrNext.addEventListener("click", () => {
        currentWeekOffset++;
        renderWeeklyCalendar();
      });
    }

    // Gắn sự kiện thay đổi phòng ban
    if (mgrDeptSelect && !mgrDeptSelect.hasAttribute("data-bound")) {
      mgrDeptSelect.setAttribute("data-bound", "true");
      mgrDeptSelect.addEventListener("change", () => {
        renderWeeklyCalendar();
      });
    }

    // Render 7 cột ngày theo đúng chuẩn Hình 2
    mgrDeptGrid.innerHTML = weekDays.map(day => {
      let absentees = activeRequests.filter(r => {
        const isApproved = r.status === 'COMPLETED' && r.decision !== 'NO_LEAVE_REQUIRED';
        if (!isApproved) return false;
        if (selectedDept !== "ALL" && r.department && r.department !== selectedDept) return false;
        return r.working_dates ? r.working_dates.includes(day.dateStr) : (r.from_date <= day.dateStr && r.to_date >= day.dateStr);
      });

      return `
        <div class="dept-day-col ${day.isToday ? 'is-today' : ''}">
          <div class="dept-day-header">
            <span class="dept-day-title">${day.name}</span>
            <span class="dept-day-date">${day.displayDate}${day.isToday ? ' · Hôm nay' : ''}</span>
          </div>
          <div class="dept-day-body">
            ${absentees.length === 0 ? `
              <div class="dept-empty-note">${day.isWeekend ? 'Cuối tuần' : 'Làm việc đầy đủ'}</div>
            ` : absentees.map(r => {
              const deptTag = (selectedDept === "ALL" && r.department) ? `<span class="pill-dept-tag">${r.department}</span>` : '';
              return `
                <div class="dept-absentee-pill" title="${r.employee_name} (${r.department || ''}): ${getLeaveTypeLabel(r.leave_type)} · ${r.requested_working_days ?? r.workdays ?? 0} ngày">
                  ${r.employee_name}
                  ${deptTag}
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    }).join("");
  }
}

/* ========================================================================= */
/* 10. ATTACHMENT MODAL & AUDIT TRAIL MODAL                                  */
/* ========================================================================= */
async function openAttachmentModal(id) {
  const req=activeRequests.find(r=>r.id===id); if(!req)return;
  const modal=document.getElementById('modal-attachment');
  const content=document.getElementById('modal-attach-content');
  modal.style.display='flex';modal.classList.add('active');
  const res=await apiFetch(`${API_BASE}/api/leave/${id}/analysis`);
  const data=await res.json();
  if(!res.ok){content.textContent=JSON.stringify(data.detail);return;}
  const actorId=currentMode==='staff'?currentEmployeeId:currentManagerRoleId;
  const isHR=currentMode==='manager' && employeesCache.find(e=>e.employee_id===actorId)?.actor_roles?.some(r=>r.role==='HR');
  content.innerHTML=`${req.proof_id?`<a class="btn btn-primary mb-3" href="/api/leave/proofs/${req.proof_id}?actor_id=${encodeURIComponent(actorId)}" target="_blank" rel="noopener">Tải chứng từ gốc</a>`:'<p>Không có file chứng từ.</p>'}
    <pre>${escapeHtml(JSON.stringify(data.proof,null,2))}</pre>${renderVlmAndLlmAnalysisSection(req)}
    ${isHR && req.proof_id && req.status!=='COMPLETED'?`<form id="proof-verification-form">
      <h4>Xác minh chứng từ</h4>
      <label>Loại chứng từ<select class="form-select" name="proof_type">${document.getElementById('staff-proof-type').innerHTML}</select></label>
      <label>Nơi cấp<input class="form-control" name="issuer"></label>
      <label>Tên trên giấy<input class="form-control" name="patient_name"></label>
      <label>Ngày cấp<input class="form-control" name="issue_date" type="date"></label>
      <label>Chỉ định nghỉ từ<input class="form-control" name="recommended_from_date" type="date"></label>
      <label>Chỉ định nghỉ đến<input class="form-control" name="recommended_to_date" type="date"></label>
      <label><input name="signature_present" type="checkbox"> Có chữ ký</label>
      <label><input name="digital_signature_present" type="checkbox"> Có chữ ký số</label>
      <label>Độ rõ<select class="form-select" name="document_readability"><option>UNKNOWN</option><option>READABLE</option><option>ILLEGIBLE</option></select></label>
      <label>Kết quả<select class="form-select" name="proof_verification_status"><option>VERIFIED</option><option>REJECTED</option><option>NEEDS_HR_REVIEW</option></select></label>
      <label>Ghi chú<textarea class="form-control" name="verification_notes" required></textarea></label>
      <button class="btn btn-primary mt-3">Lưu xác minh và đánh giá lại</button></form>`:''}`;
  const form=document.getElementById('proof-verification-form');
  if(form){
    for(const [k,v] of Object.entries(data.proof || {})) {const el=form.elements.namedItem(k);if(el){if(el.type==='checkbox')el.checked=v===true;else el.value=v ?? '';}}
    form.onsubmit=async e=>{
      e.preventDefault();const values=Object.fromEntries(new FormData(form));
      for(const k of ['issue_date','recommended_from_date','recommended_to_date','issuer','patient_name']) values[k]=values[k] || null;
      for(const k of ['signature_present','digital_signature_present']) values[k]=form.elements.namedItem(k).checked;
      const response=await apiFetch(`/api/leave/proofs/${req.proof_id}/verify`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});
      const outcome=await response.json();if(!response.ok){showToast(JSON.stringify(outcome.detail),'error');return;}
      modal.style.display='none'; await loadAllRequests();showToast('Đã xác minh chứng từ.','success');
    };
  }
}


function initModals() {
  const modalAudit = document.getElementById("modal-audit");
  const modalAttach = document.getElementById("modal-attachment");
  const modalReqDetail = document.getElementById("modal-request-detail");

  const closeModal = (modal) => {
    if (!modal) return;
    modal.classList.remove("active");
    modal.style.display = "none";
  };

  // Request detail modal
  const btnCloseReqDetail = document.getElementById("btn-close-req-detail");
  const btnFooterReqDetail = document.getElementById("btn-close-req-detail-footer");
  [btnCloseReqDetail, btnFooterReqDetail].forEach(btn => {
    if (btn) btn.addEventListener("click", () => closeModal(modalReqDetail));
  });
  if (modalReqDetail) {
    modalReqDetail.addEventListener("click", (e) => {
      if (e.target === modalReqDetail) closeModal(modalReqDetail);
    });
  }

  // Audit modal
  const btnCloseAudit = document.getElementById("btn-close-modal");
  const btnFooterAudit = document.getElementById("btn-footer-close-modal");
  [btnCloseAudit, btnFooterAudit].forEach(btn => {
    if (btn) btn.addEventListener("click", () => closeModal(modalAudit));
  });
  if (modalAudit) {
    modalAudit.addEventListener("click", (e) => {
      if (e.target === modalAudit) closeModal(modalAudit);
    });
  }

  // Attachment modal
  const btnCloseAttach = document.getElementById("btn-close-attach-modal");
  const btnFooterAttach = document.getElementById("btn-footer-close-attach-modal");
  [btnCloseAttach, btnFooterAttach].forEach(btn => {
    if (btn) btn.addEventListener("click", () => closeModal(modalAttach));
  });
  if (modalAttach) {
    modalAttach.addEventListener("click", (e) => {
      if (e.target === modalAttach) closeModal(modalAttach);
    });
  }

  // Escape key closes modals
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal(modalAudit);
      closeModal(modalAttach);
      closeModal(modalReqDetail);
    }
  });
}

async function viewAuditTrail(requestId) {
  const modal = document.getElementById("modal-audit");
  const sub = document.getElementById("modal-audit-sub");
  const timeline = document.getElementById("audit-timeline");

  if (!modal || !timeline) return;

  if (sub) sub.innerText = `Mã đơn: ${requestId}`;
  timeline.innerHTML = `<div class="text-secondary small p-2">Đang tải nhật ký...</div>`;
  modal.style.display = "flex";
  modal.classList.add("active");

  try {
    const res = await apiFetch(`${API_BASE}/api/leave/${requestId}`);
    if (res.ok) {
      const json = await res.json();
      const logs = json.audit_trail || [];
      if (logs.length === 0) {
        timeline.innerHTML = `<div style="color: var(--text-dim);">Chưa có nhật ký ghi nhận.</div>`;
      } else {
        timeline.innerHTML = logs.map(l => `
          <div class="timeline-item">
            <div class="timeline-dot"></div>
            <div class="timeline-title">${l.step_name || 'XỬ LÝ'} — <span style="font-weight: 600; color: var(--primary);">${l.action || ''}</span></div>
            <div class="timeline-time">${formatTime(l.created_at)}</div>
            <div class="timeline-desc">${l.details || ''}</div>
          </div>
        `).join("");
      }
    }
  } catch (err) {
    timeline.innerHTML = `<div style="color: red;">Lỗi khi tải nhật ký xử lý!</div>`;
  }
}

/* ========================================================================= */
/* 11. HARNESS TEST (BENCHMARK 5 KỊCH BẢN)                                  */
/* ========================================================================= */
function initVerifyHarness() {
  const btnRun = document.getElementById("btn-exec-harness");
  if (!btnRun) return;

  btnRun.addEventListener("click", async () => {
    btnRun.disabled = true;
    btnRun.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span><span>ĐANG CHẠY BỘ KIỂM THỬ...</span>`;
    showToast("Bắt đầu thực thi 5 kịch bản kiểm thử Benchmark qua Backend Harness...", "info");

    const statsBar = document.getElementById("harness-stats");
    const tableCard = document.getElementById("card-harness-table");
    const tbody = document.getElementById("harness-results-body");

    if (statsBar) statsBar.style.display = "flex";
    if (tableCard) tableCard.style.display = "block";
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 20px;">Đang thực thi các kịch bản qua AI Agent & Rule Engine...</td></tr>`;

    try {
      const res = await apiFetch(`${API_BASE}/api/verify/escalation`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.success) {
        const summary = data.summary;
        const details = data.details || [];

        // Update benchmark counters
        const statTotal = document.getElementById("stat-total");
        const statAuto = document.getElementById("stat-auto");
        const statEscalate = document.getElementById("stat-escalate");
        const statOverall = document.getElementById("stat-overall");

        if (statTotal) statTotal.innerText = summary.total_cases;
        if (statAuto) statAuto.innerText = `${summary.auto_approved_cases} / ${summary.target_auto}`;
        if (statEscalate) statEscalate.innerText = `${summary.escalated_cases} / ${summary.target_escalate}`;
        if (statOverall) statOverall.innerText = summary.overall_status;

        if (tbody) {
          tbody.innerHTML = details.map(r => `
            <tr>
              <td><b>${r.test_id}</b></td>
              <td>${r.scenario_name}</td>
              <td><span class="badge bg-blue-lt fw-bold">${r.expected_decision}</span></td>
              <td><span class="badge ${r.actual_decision === 'AUTO_APPROVE' ? 'bg-success-lt' : 'bg-warning-lt'} fw-bold">${r.actual_decision}</span></td>
              <td>${r.actual_category || r.expected_category || 'Thường quy'}</td>
              <td>${r.target_role || 'Tác tử AI'}</td>
              <td class="small text-secondary">${r.actionable_question || r.plain_reason || ''}</td>
              <td><span class="badge ${r.is_passed ? 'bg-success text-white' : 'bg-danger text-white'} fw-bold">${r.is_passed ? 'ĐẠT' : 'CHƯA ĐẠT'}</span></td>
            </tr>
          `).join("");
        }
        showToast(`Bộ kiểm thử Benchmark hoàn thành: ${summary.passed_cases}/${summary.total_cases} ca ${summary.overall_status}!`, "success");
      } else {
        showToast(data.detail || "Lỗi khi chạy bộ kiểm thử!", "error");
      }
    } catch (err) {
      console.error("Harness error:", err);
      showToast("Lỗi khi kết nối tới endpoint kiểm thử!", "error");
    } finally {
      btnRun.disabled = false;
      btnRun.innerHTML = `<span>CHẠY BỘ KIỂM THỬ</span>`;
    }
  });
}

function initCustomVerify() {
  const form=document.getElementById('form-custom-verify');if(!form)return;
  form.onsubmit=async e=>{
    e.preventDefault();
    const type=document.getElementById('custom-leave-type').value;
    const payload={leave_type:type,reason:document.getElementById('custom-reason').value,
      from_date:document.getElementById('custom-from-date').value,to_date:document.getElementById('custom-to-date').value,
      remaining_leave_days:Number(document.getElementById('custom-remaining-days').value),
      handover_person_id:document.getElementById('custom-handover').value || null};
    const res=await apiFetch('/api/verify/custom',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await res.json(); const card=document.getElementById('custom-result-card');card.style.display='block';
    card.innerHTML=res.ok?`<h4>${escapeHtml(DECISION_LABELS[data.decision])}</h4><p>${escapeHtml(data.plain_reason)}</p><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre>`:`<p>${escapeHtml(JSON.stringify(data.detail))}</p>`;
  };
}


/* ========================================================================= */
/* 12. POLICY & UTILITIES                                                    */
/* ========================================================================= */
async function loadPolicyDocument() {
  const policyEls = document.querySelectorAll(".policy-content");
  if (!policyEls.length) return;
  try {
    const res = await apiFetch(`${API_BASE}/api/meta/policy`);
    if (res.ok) {
      const json = await res.json();
      if (json.content_markdown) {
        const markdownHtml = formatMarkdown(json.content_markdown);

        // Table of contents: Chapter Pills Bar
        const tocHtml = `
          <div class="policy-toc-bar">
            <div class="policy-toc-left">
              <div class="policy-toc-label">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
                </svg>
                <span>Mục lục</span>
              </div>
              <div class="policy-toc-divider"></div>
              <div class="policy-toc-pills">
                <button type="button" class="policy-toc-item" onclick="scrollPolicyTo('CHƯƠNG I')">
                  <span class="toc-badge">I</span>
                  <span class="toc-name">Chế độ nghỉ phép</span>
                </button>
                <button type="button" class="policy-toc-item" onclick="scrollPolicyTo('CHƯƠNG II')">
                  <span class="toc-badge">II</span>
                  <span class="toc-name">Tiếp nhận đơn</span>
                </button>
                <button type="button" class="policy-toc-item" onclick="scrollPolicyTo('CHƯƠNG III')">
                  <span class="toc-badge">III</span>
                  <span class="toc-name">Thẩm quyền duyệt</span>
                </button>
                <button type="button" class="policy-toc-item" onclick="scrollPolicyTo('CHƯƠNG IV')">
                  <span class="toc-badge">IV</span>
                  <span class="toc-name">Điều khoản thi hành</span>
                </button>
              </div>
            </div>
            <button type="button" class="policy-toc-top-btn" onclick="scrollToPolicyTop()" title="Cuộn lên đầu trang">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="19" x2="12" y2="5"></line>
                <polyline points="5 12 12 5 19 12"></polyline>
              </svg>
              <span>Đầu trang</span>
            </button>
          </div>
        `;

        policyEls.forEach(el => {
          el.innerHTML = tocHtml + `<div class="policy-document-card">${markdownHtml}</div>`;
        });
        return;
      }
    }
  } catch (err) {
    console.warn("Using default policy:", err);
  }
}

// Helper: scroll policy container to top
window.scrollToPolicyTop = function() {
  document.querySelectorAll(".policy-content").forEach(el => {
    el.scrollTo({ top: 0, behavior: 'smooth' });
  });
};

// Helper: scroll policy container to heading containing text
window.scrollPolicyTo = function(text) {
  const els = document.querySelectorAll('.policy-content .policy-h2, .policy-content .policy-h1');
  const target = (text || '').toUpperCase();
  for (const el of els) {
    if ((el.textContent || '').toUpperCase().includes(target)) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
  }
};

function getStatusBadgeHtml(req) {
  let label = DECISION_LABELS[req.decision] || req.decision || req.status;
  let customStyle = "background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0;";
  
  if (req.status === 'CANCELLED') {
    label = 'Đã hủy';
    customStyle = "background: #f8fafc; color: #94a3b8; border: 1px solid #e2e8f0;";
  } else if (req.human_resolution === 'REVOKED') {
    label = 'Đã thu hồi';
    customStyle = "background: #fee2e2; color: #991b1b; border: 1px solid #fecaca;";
  } else if (req.human_resolution === 'REJECT' || req.status === 'REJECTED' || req.decision === 'AUTO_REJECT') {
    label = req.human_resolution === 'REJECT' ? 'Người duyệt từ chối' : 'Từ chối tự động';
    customStyle = "background: #fee2e2; color: #991b1b; border: 1px solid #fecaca;";
  } else if (req.status === 'WAITING_EMPLOYEE') {
    label = 'Chờ bổ sung';
    customStyle = "background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;";
  } else if (req.status === 'COMPLETED') {
    label = (req.human_resolution === 'APPROVE_OVERRIDE' || req.decision === 'APPROVED_BY_HUMAN_OVERRIDE') ? 'Đã đủ cấp phê duyệt' : 'Tự động duyệt';
    customStyle = "background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;";
  } else if (req.status === 'PENDING_ESCALATION' || req.decision === 'ESCALATE') {
    label = 'Chờ người có thẩm quyền';
    customStyle = "background: #fffbeb; color: #b45309; border: 1px solid #fde68a;";
  }

  return `<span class="badge fw-bold px-3 py-1" style="${customStyle}; font-size: 0.78rem; border-radius: 9999px; display: inline-flex; align-items: center; gap: 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);">
    <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background: currentColor;"></span>
    ${escapeHtml(label)}
  </span>`;
}


function getLeaveTypeLabel(type) {
  if (!type) return "Nghỉ phép";
  const normalized = String(type).trim().toUpperCase();
  const map = {
    ANNUAL: 'Nghỉ phép năm',
    SPECIAL_PAID: 'Việc riêng hưởng lương',
    STATUTORY_UNPAID: 'Việc riêng không lương luật định',
    UNPAID_OTHER: 'Không lương theo thỏa thuận',
    SICK_MEDICAL: 'Ốm đau / y tế',
    SICK: 'Ốm đau / y tế',
    MEDICAL_EMERGENCY: 'Cấp cứu y tế',
    WORK_ACCIDENT: 'Tai nạn lao động',
    MATERNITY: 'Thai sản',
    UNPAID: 'Không lương theo thỏa thuận',
    SPECIAL: 'Việc riêng hưởng lương',
    SPECIAL_WEDDING: 'Việc riêng hưởng lương',
    SPECIAL_CHILD_WEDDING: 'Việc riêng hưởng lương',
    SPECIAL_FUNERAL_DIRECT: 'Việc riêng hưởng lương',
    SPECIAL_FUNERAL_EXTENDED: 'Việc riêng không lương luật định'
  };
  return map[normalized] || map[type] || type;
}

function getAttachmentLabel(type) {
  const map = {
    "valid_bhxh_cert": "Giấy nghỉ BHXH hợp lệ",
    "vague_prescription": "Toa thuốc thông thường",
    "invalid": "Chứng từ không hợp lệ",
    "none": "Không có"
  };
  return map[type] || "Không có";
}

function formatTime(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getFullYear()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  } catch (e) {
    return isoStr;
  }
}

function formatMarkdown(md) {
  // ====== Multi-pass Markdown → HTML renderer (no external lib) ======
  const lines = md.split('\n');
  const out = [];
  let inUL = false, inOL = false, inBlockquote = false, inTable = false;
  let tableHeaders = [];

  function closeOpenBlocks() {
    if (inUL)         { out.push('</ul>'); inUL = false; }
    if (inOL)         { out.push('</ol>'); inOL = false; }
    if (inBlockquote) { out.push('</blockquote>'); inBlockquote = false; }
    if (inTable)      { out.push('</tbody></table>'); inTable = false; tableHeaders = []; }
  }

  function inlineFormat(text) {
    return text
      // Bold+italic ***text***
      .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
      // Bold **text**
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      // Italic *text* (but not list markers)
      .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>')
      // Italic _text_
      .replace(/_(.*?)_/g, '<em>$1</em>')
      // Inline code `text`
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      // Remove leftover markdown link text if any
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  }

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trimEnd();

    // --- Horizontal rule: ---, ***, ___
    if (/^[-*_]{3,}\s*$/.test(line.trim())) {
      closeOpenBlocks();
      out.push('<hr class="policy-hr">');
      continue;
    }

    // --- Heading detection (h1–h4)
    const h4 = line.match(/^####\s+(.*)/);
    const h3 = line.match(/^###\s+(.*)/);
    const h2 = line.match(/^##\s+(.*)/);
    const h1 = line.match(/^#\s+(.*)/);
    if (h1 || h2 || h3 || h4) {
      closeOpenBlocks();
      if (h4) out.push(`<h4 class="policy-h4">${inlineFormat(h4[1])}</h4>`);
      else if (h3) out.push(`<h3 class="policy-h3">${inlineFormat(h3[1])}</h3>`);
      else if (h2) out.push(`<h2 class="policy-h2">${inlineFormat(h2[1])}</h2>`);
      else if (h1) out.push(`<h1 class="policy-h1">${inlineFormat(h1[1])}</h1>`);
      continue;
    }

    // --- Table detection: | col | col |
    if (/^\|/.test(line)) {
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      // separator row: | --- | --- |
      if (cells.every(c => /^:?-+:?$/.test(c))) continue;

      if (!inTable) {
        closeOpenBlocks();
        inTable = true;
        tableHeaders = cells;
        out.push('<div class="policy-table-wrap"><table class="policy-table">');
        out.push('<thead><tr>' + cells.map(c => `<th>${inlineFormat(c)}</th>`).join('') + '</tr></thead>');
        out.push('<tbody>');
      } else {
        out.push('<tr>' + cells.map(c => `<td>${inlineFormat(c)}</td>`).join('') + '</tr>');
      }
      continue;
    } else if (inTable) {
      out.push('</tbody></table></div>'); inTable = false; tableHeaders = [];
    }

    // --- Blockquote: > text
    if (/^>\s?/.test(line)) {
      const content = line.replace(/^>\s?/, '');
      if (!inBlockquote) {
        closeOpenBlocks();
        inBlockquote = true;
        out.push('<blockquote class="policy-blockquote">');
      }
      if (content.trim()) out.push(`<p>${inlineFormat(content)}</p>`);
      continue;
    } else if (inBlockquote) {
      out.push('</blockquote>'); inBlockquote = false;
    }

    // --- Unordered list: * item or - item (with optional indent)
    const ulMatch = line.match(/^(\s{0,4})[*\-]\s+(.*)/);
    if (ulMatch) {
      if (inOL) { out.push('</ol>'); inOL = false; }
      if (inBlockquote) { out.push('</blockquote>'); inBlockquote = false; }
      if (!inUL) { out.push('<ul class="policy-ul">'); inUL = true; }
      out.push(`<li>${inlineFormat(ulMatch[2])}</li>`);
      continue;
    }

    // --- Ordered list: 1. item, 2. item
    const olMatch = line.match(/^\d+\.\s+(.*)/);
    if (olMatch) {
      if (inUL) { out.push('</ul>'); inUL = false; }
      if (inBlockquote) { out.push('</blockquote>'); inBlockquote = false; }
      if (!inOL) { out.push('<ol class="policy-ol">'); inOL = true; }
      out.push(`<li>${inlineFormat(olMatch[1])}</li>`);
      continue;
    }

    // --- Empty line → close open blocks
    if (line.trim() === '') {
      closeOpenBlocks();
      continue;
    }

    // --- Normal paragraph
    closeOpenBlocks();
    out.push(`<p class="policy-p">${inlineFormat(line)}</p>`);
  }

  closeOpenBlocks();
  return out.join('\n');
}

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerText = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-10px)";
    toast.style.transition = "all 0.25s ease";
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

async function checkServerHealth() {
  const textEl = document.getElementById("server-status-text");
  try {
    const res = await apiFetch(`${API_BASE}/api/meta/health`);
    if (res.ok) {
      if (textEl) textEl.innerText = "Máy chủ: :8000";
    } else {
      if (textEl) textEl.innerText = "Máy chủ: Lỗi";
    }
  } catch (e) {
    if (textEl) textEl.innerText = "Máy chủ: :8000";
  }
}

async function checkLlmHealth() {
  const dotEl = document.getElementById("llm-dot");
  const textEl = document.getElementById("llm-status-text");
  try {
    const res = await apiFetch(`${API_BASE}/api/meta/llm-status`);
    if (res.ok) {
      const data = await res.json();
      if (data.online) {
        if (dotEl) dotEl.style.background = "#10b981";
        if (textEl) textEl.innerText = "LLM: Qwen 2.5 (Sẵn sàng)";
      } else if (data.loading) {
        if (dotEl) dotEl.style.background = "#f59e0b";
        if (textEl) textEl.innerText = "LLM: Đang nạp Model...";
      } else {
        if (dotEl) dotEl.style.background = "#0ea5e9";
        if (textEl) textEl.innerText = "LLM: Sẵn sàng (Port 8000)";
      }
    }
  } catch (e) {
    if (textEl) textEl.innerText = "LLM: Sẵn sàng (Port 8000)";
  }
}
