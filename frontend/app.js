/**
 * app.js — Team PNKK
 * AI Leave Approval & Escalation Routing System (The Escalation Referee)
 * Fully Supports 2 Modes: 
 * 1. Staff UI Portal (Cổng Thông Tin Nhân Viên)
 * 2. Manager & Admin Portal (Giao Diện Quản Lý & Điều Phối)
 */

const API_BASE = window.location.origin;

let currentLang = localStorage.getItem("app_lang") || "vi";
let currentMode = "test"; // 'test' | 'staff' | 'manager'
let currentEmployeeId = "EMP003";
let editingRequestId = null;
let currentProofId = null;
let selectedProofFile = null;
let currentManagerRoleId = "EMP001";
let employeesCache = [];
let activeRequests = [];
let pollInterval = null;
let requestsLoadInFlight = false;
let currentWeekOffset = 0;

// Display only data returned by the backend.
const DEFAULT_EMPLOYEES = [];
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('X-Actor-ID', currentMode === 'manager' ? currentManagerRoleId : currentEmployeeId);
  return fetch(url, {...options, headers});
}
const DECISION_LABELS = {
  NO_LEAVE_REQUIRED: 'Không cần xin phép', AUTO_APPROVE: 'Tự động duyệt',
  AUTO_REJECT: 'Từ chối tự động', ESCALATE: 'Chờ người có thẩm quyền'
};

const ROLE_LABELS = {
  DIRECT_MANAGER: 'Quản lý trực tiếp',
  DEPARTMENT_HEAD: 'Trưởng bộ phận',
  HR: 'Nhân sự (HR)',
  HRD: 'Giám đốc Nhân sự',
  CEO: 'Tổng Giám đốc',
  EMPLOYEE: 'Nhân viên (nộp lại / bổ sung)',
  NONE: '—',
};

const ERROR_CODE_LABELS = {
  OK: 'Hợp lệ',
  DURATION_OVER_AI_LIMIT: 'Vượt ngưỡng tự duyệt của AI',
  DURATION_OVER_MANAGER_LIMIT: 'Vượt hạn mức duyệt của Quản lý',
  LONG_TERM_UNPAID: 'Nghỉ không lương cần xem xét',
  NOTICE_PERIOD_VIOLATED: 'Vi phạm thời hạn báo trước',
  TEAM_QUOTA_EXCEEDED: 'Vượt tỷ lệ nghỉ đồng thời phòng ban (30%)',
  BALANCE_EXCEEDED: 'Vượt quá số dư phép năm',
  PROOF_MISSING: 'Thiếu chứng từ',
  DOC_ILLEGIBLE: 'Chứng từ mờ / không đọc được',
  PROOF_REVIEW_REQUIRED: 'Cần HR xác minh chứng từ',
  DOC_FIELD_MISSING: 'Thiếu thông tin bắt buộc trên chứng từ',
  NAME_MISMATCH: 'Tên trên chứng từ không khớp',
  MEDICAL_DAYS_MISMATCH: 'Ngày nghỉ ngoài chỉ định bác sĩ',
  FLAG_ABUSE_PATTERN: 'Gắn cờ nghi vấn chia nhỏ phép (Anti-Abuse)',
  LEAVE_TYPE_MISSING: 'Thiếu loại nghỉ phép',
  REASON_REQUIRED: 'Yêu cầu nêu rõ lý do',
  RELATIONSHIP_UNCLEAR: 'Quan hệ thân nhân chưa rõ, cần Quản lý xác minh',
  ENTITLEMENT_EXCEEDED: 'Vượt định mức chế độ',
  HANDOVER_REQUIRED: 'Cần người nhận bàn giao',
  HANDOVER_INVALID: 'Người nhận bàn giao không hợp lệ',
  OVERLAPPING_REQUEST: 'Trùng một phần ngày nghỉ đã duyệt',
  REQUEST_ALREADY_COVERED: 'Toàn bộ ngày nghỉ đã được duyệt trước đó',
  PROBATION_ANNUAL_RESTRICTED: 'Nhân viên thử việc chưa được dùng phép năm',
  AUTOMATION_SCOPE_UNSUPPORTED: 'Chưa hỗ trợ tự động duyệt chế độ này',
  LEGAL_REVIEW_REQUIRED: 'Cần bộ phận Pháp chế / Nhân sự xem xét',
};

const CATEGORY_LABELS = {
  UNCERTAIN_FACTS: 'Thông tin chưa rõ',
  OUT_OF_POLICY: 'Ngoài chính sách',
  AUTHORITY_ESCALATION: 'Thẩm quyền phê duyệt'
};

function getRoleLabel(role) {
  return ROLE_LABELS[role] || role || 'Tác tử AI';
}

function getCategoryLabel(cat) {
  return CATEGORY_LABELS[cat] || cat || 'Thường quy';
}

function getDecisionLabel(dec) {
  return DECISION_LABELS[dec] || dec || 'Chưa có';
}

function getErrorCodeLabel(code) {
  return ERROR_CODE_LABELS[code] || code || '—';
}


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
  initTestTabs();
  initStaffTabs();
  initManagerTabs();
  initStaffForm();
  initStaffTestCaseCard();
  initSprint1Benchmark();
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

  // Activate Test Mode by default
  if (typeof setTestMode === "function") {
    setTestMode();
  }
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
  const btnTest = document.getElementById("btn-mode-test");
  const btnStaff = document.getElementById("btn-mode-staff");
  const btnManager = document.getElementById("btn-mode-manager");
  const viewTest = document.getElementById("view-test-portal");
  const viewStaff = document.getElementById("view-staff-portal");
  const viewManager = document.getElementById("view-manager-portal");
  const testNav = document.getElementById("sidebar-test-nav");
  const staffNav = document.getElementById("sidebar-staff-nav");
  const mgrNav = document.getElementById("sidebar-manager-nav");
  const staffSelector = document.getElementById("header-staff-selector");
  const mgrSelector = document.getElementById("header-manager-selector");
  const btnAllocate = document.getElementById("btn-header-allocate");
  const alertQueue = document.getElementById("header-pending-alert");

  function setTestMode() {
    currentMode = "test";
    if (btnTest) btnTest.classList.add("active");
    if (btnStaff) btnStaff.classList.remove("active");
    if (btnManager) btnManager.classList.remove("active");
    if (viewTest) viewTest.classList.add("active");
    if (viewStaff) viewStaff.classList.remove("active");
    if (viewManager) viewManager.classList.remove("active");

    if (testNav) testNav.style.display = "flex";
    if (staffNav) staffNav.style.display = "none";
    if (mgrNav) mgrNav.style.display = "none";

    if (staffSelector) staffSelector.style.display = "none";
    if (mgrSelector) mgrSelector.style.display = "none";
    if (btnAllocate) btnAllocate.style.display = "none";
    if (alertQueue) alertQueue.style.display = "none";

    // Switch to Kiểm duyệt tab by default
    switchTestTab("tab-test-audit");
    renderStaffTestCaseCard();
  }
  window.setTestMode = setTestMode;

  if (btnTest) {
    btnTest.addEventListener("click", () => {
      setTestMode();
    });
  }

  if (btnStaff) {
    btnStaff.addEventListener("click", () => {
      currentMode = "staff";
      loadAllRequests();
      if (btnTest) btnTest.classList.remove("active");
      btnStaff.classList.add("active");
      btnManager.classList.remove("active");
      if (viewTest) viewTest.classList.remove("active");
      viewStaff.classList.add("active");
      viewManager.classList.remove("active");
      
      if (testNav) testNav.style.display = "none";
      if (staffNav) staffNav.style.display = "flex";
      if (mgrNav) mgrNav.style.display = "none";

      if (staffSelector) {
        staffSelector.style.display = "flex";
        autoResizeSelect(document.getElementById("demo-department-select"));
        autoResizeSelect(document.getElementById("demo-employee-select"));
      }
      if (mgrSelector) mgrSelector.style.display = "none";
      if (btnAllocate) btnAllocate.style.display = "none";
      if (alertQueue) alertQueue.style.display = "none";

      const activeStaffBtn = document.querySelector("#sidebar-staff-nav .tab-btn.active");
      if (!activeStaffBtn) {
        switchStaffTab("tab-staff-dashboard");
      } else {
        switchStaffTab(activeStaffBtn.getAttribute("data-tab"));
      }
      renderWeeklyCalendar();
    });
  }

  if (btnManager) {
    btnManager.addEventListener("click", () => {
      currentMode = "manager";
      loadAllRequests();
      if (btnTest) btnTest.classList.remove("active");
      btnManager.classList.add("active");
      btnStaff.classList.remove("active");
      if (viewTest) viewTest.classList.remove("active");
      viewManager.classList.add("active");
      viewStaff.classList.remove("active");

      if (testNav) testNav.style.display = "none";
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

  // ── NÚT RESET TOÀN BỘ DATABASE TRÊN THANH TOPBAR ──
  const btnResetDb = document.getElementById("btn-reset-database");
  if (btnResetDb) {
    btnResetDb.addEventListener("click", async () => {
      const confirmed = window.confirm("⚠️ BẠN CÓ CHẮC CHẮN MUỐN RESET TOÀN BỘ DATABASE?\n\n- Toàn bộ đơn xin nghỉ đã nộp và các thao tác duyệt/bổ sung sẽ được khôi phục về mặc định.\n- Số dư ngày phép của nhân viên sẽ được reset về ban đầu (12 ngày).\n- 5 đơn mẫu demo sẽ được nạp lại.");
      if (!confirmed) return;

      const originalHtml = btnResetDb.innerHTML;
      btnResetDb.disabled = true;
      btnResetDb.innerHTML = `<span class="spinner-border spinner-border-sm" style="width:0.75rem;height:0.75rem;" role="status"></span><span>Đang reset...</span>`;

      try {
        const res = await apiFetch(`${API_BASE}/api/meta/reset-database`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const result = await res.json();
        if (res.ok && result.success) {
          showToast(result.message || "Đã reset database về trạng thái ban đầu thành công!", "success");
          editingRequestId = null;
          currentProofId = null;
          document.getElementById('form-staff-standard')?.reset();
          await loadEmployees();
          await loadAllRequests();
          if (currentMode === "staff") {
            renderStaffDashboard();
            renderStaffRequests();
          } else {
            renderManagerBanner();
            renderManagerOverviewKPIs();
            renderManagerQueue();
            renderAutoApprovedLogs();
            renderManagerAllRequests();
          }
          renderWeeklyCalendar();
        } else {
          showToast("Lỗi khi reset database: " + (result.detail || "Không rõ nguyên nhân"), "error");
        }
      } catch (err) {
        showToast("Lỗi kết nối tới máy chủ khi reset database: " + err.message, "error");
      } finally {
        btnResetDb.disabled = false;
        btnResetDb.innerHTML = originalHtml;
      }
    });
  }
}

/* ========================================================================= */
/* 2. DEMO LOGIN & ROLE SWITCHER                                             */
/* ========================================================================= */
function autoResizeSelect(selectEl) {
  if (!selectEl) return;
  const selectedOpt = (selectEl.selectedIndex >= 0) ? selectEl.options[selectEl.selectedIndex] : (selectEl.options[0] || null);
  const text = selectedOpt ? selectedOpt.text.trim() : "";
  if (!text) {
    selectEl.style.width = "160px";
    return;
  }
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

  measurer.style.fontFamily = "'Inter', -apple-system, sans-serif";
  measurer.style.fontSize = "0.84rem";
  measurer.style.fontWeight = "600";
  measurer.textContent = text;

  const textWidth = measurer.getBoundingClientRect().width || measurer.offsetWidth || 0;
  const isDept = selectEl.id === "demo-department-select";
  const minW = isDept ? 130 : 160;
  const maxW = isDept ? 220 : 340;
  const targetWidth = Math.max(minW, Math.min(maxW, Math.ceil(textWidth) + 48));
  selectEl.style.width = `${targetWidth}px`;
}

function updateStaffDropdown(selectedDept) {
  const demoSelect = document.getElementById("demo-employee-select");
  if (!demoSelect) return;

  // Lọc danh sách staff thuộc department được chọn (bỏ qua managers/boss có actor_roles)
  const deptStaff = employeesCache.filter(e =>
    e.department === selectedDept &&
    (!e.actor_roles || e.actor_roles.length === 0) &&
    e.status === "ACTIVE"
  );

  demoSelect.innerHTML = deptStaff.map(emp => `
    <option value="${escapeHtml(emp.employee_id)}" ${emp.employee_id === currentEmployeeId ? 'selected' : ''}>
      ${escapeHtml(emp.name)} (${escapeHtml(emp.role)})
    </option>
  `).join("");

  // Nếu nhân viên đang chọn không thuộc phòng ban này thì tự động chọn staff đầu tiên
  if (!deptStaff.some(e => e.employee_id === currentEmployeeId) && deptStaff.length > 0) {
    currentEmployeeId = deptStaff[0].employee_id;
    demoSelect.value = currentEmployeeId;
  }

  autoResizeSelect(demoSelect);
}

function initDemoLoginAndRoles() {
  const deptSelect = document.getElementById("demo-department-select");
  const demoSelect = document.getElementById("demo-employee-select");

  if (deptSelect) {
    deptSelect.addEventListener("change", (e) => {
      const selectedDept = e.target.value;
      autoResizeSelect(deptSelect);
      updateStaffDropdown(selectedDept);

      editingRequestId = null;
      currentProofId = null;
      loadAllRequests();
      renderStaffDashboard();
      renderStaffRequests();
      renderWeeklyCalendar();

      const curr = getCurrentEmployee();
      const empName = curr ? `${curr.name} (${curr.role})` : currentEmployeeId;
      showToast(`Đã chọn bộ phận: ${selectedDept} · Nhân viên: ${empName}`, "info");
    });
    autoResizeSelect(deptSelect);
  }

  if (demoSelect) {
    demoSelect.addEventListener("change", (e) => {
      currentEmployeeId = e.target.value;
      editingRequestId = null;
      currentProofId = null;
      loadAllRequests();
      autoResizeSelect(demoSelect);
      renderStaffDashboard();
      renderStaffRequests();
      renderWeeklyCalendar();
      const curr = getCurrentEmployee();
      const empName = curr ? `${curr.name} (${curr.role})` : (demoSelect.options[demoSelect.selectedIndex]?.text || currentEmployeeId);
      showToast(`Đã chuyển sang nhân viên: ${empName}`, "info");
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
      if (deptSelect) autoResizeSelect(deptSelect);
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
  // Thứ tự hiển thị quản lý: Engineering Manager (EMP001), Marketing Manager (EMP002), CEO (EMP000)
  const rolePriority = { 'EMP001': 1, 'EMP002': 2, 'EMP000': 3 };
  managers.sort((a, b) => (rolePriority[a.employee_id] || 99) - (rolePriority[b.employee_id] || 99));

  const selector = document.getElementById('manager-role-select');
  if (selector) {
    selector.innerHTML = managers.map(e => `
      <option value="${escapeHtml(e.employee_id)}">
        ${escapeHtml(e.name)} · ${escapeHtml(e.role || e.actor_roles.map(r=>r.role).join('/'))}
      </option>
    `).join('');
    if (!managers.some(e=>e.employee_id===currentManagerRoleId)) currentManagerRoleId=managers[0]?.employee_id || '';
    selector.value = currentManagerRoleId;
    autoResizeSelect(selector);
  }
  populateEmployeeDropdowns();
  renderStaffDashboard();
  renderWeeklyCalendar();
}

function populateEmployeeDropdowns() {
  const deptSelect = document.getElementById("demo-department-select");
  const allocEmpSelect = document.getElementById("alloc-emp-select");

  // Lấy danh sách phòng ban có nhân viên (staff)
  let staffDepts = Array.from(new Set(
    employeesCache
      .filter(e => (!e.actor_roles || e.actor_roles.length === 0) && e.status === 'ACTIVE')
      .map(e => e.department)
      .filter(Boolean)
  )).sort();

  if (staffDepts.length === 0) {
    staffDepts = ["Engineering", "Marketing & Operations"];
  }

  const currentEmp = getCurrentEmployee();
  let currentDept = currentEmp?.department || deptSelect?.value || staffDepts[0];
  if (!staffDepts.includes(currentDept)) {
    currentDept = staffDepts[0];
  }

  if (deptSelect) {
    deptSelect.innerHTML = staffDepts.map(dept => `
      <option value="${escapeHtml(dept)}" ${dept === currentDept ? 'selected' : ''}>
        ${escapeHtml(dept)}
      </option>
    `).join("");
    deptSelect.value = currentDept;
    autoResizeSelect(deptSelect);
  }

  updateStaffDropdown(currentDept);

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
  renderStaffTestCaseCard();
}

/* ========================================================================= */
/* 2.5 STAFF TEST CASE SIMULATOR (21 TEST SUITE PRESETS)                     */
/* ========================================================================= */
const EMP_NAME_MAP = {
  "EMP000": "Phạm Minh Hoàng",
  "EMP001": "Đỗ Hoàng Long",
  "EMP002": "Dương Mỹ Duyên",
  "EMP003": "Trần Quốc Hưng",
  "EMP004": "Lê Văn Nam",
  "EMP005": "Nguyễn Văn An",
  "EMP006": "Bùi Tuấn Kiệt",
  "EMP007": "Lê Thị Hương",
  "EMP008": "Nguyễn Thị Kim Ngân",
  "EMP009": "Võ Minh Khang",
  "EMP010": "Phan Thảo My",
  "EMP011": "Hoàng Kim Yến",
  "EMP012": "Lê Mai Loan"
};

const STAFF_TEST_CASES = [
  // =========================================================================
  // EMP003: Trần Quốc Hưng (Senior / Lead Developer - Engineering)
  // =========================================================================
  {
    id: "TC-HARD-03",
    primaryEmpId: "EMP003",
    title: "TC-HARD-03: Nghỉ liên tục 6 ngày -> Vượt trần Quản lý (5 ngày), chuyển Boss",
    badge: "Cấp Sếp · Vượt trần Quản lý",
    badgeClass: "bg-purple-lt",
    desc: "Trần Quốc Hưng xin 6 ngày làm việc liên tiếp có bàn giao cho EMP004 -> Vượt hạn mức 5 ngày của Quản lý trực tiếp, thẩm quyền chuyển Tổng Giám đốc (Boss).",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-12",
      handover_person_id: "EMP004",
      handover: { employee_id: "EMP004", department: "Engineering", status: "ACTIVE", absent_dates: [] },
      reason: "Nghỉ du lịch gia đình dài ngày",
      submitted_at: "2026-09-10T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "CEO",
      error_code: "DURATION_OVER_MANAGER_LIMIT",
      note: "Vượt 5 ngày trần Quản lý: Chuyển cấp trên (Boss/Head)"
    }
  },
  {
    id: "TC-EMP003-01",
    primaryEmpId: "EMP003",
    title: "TC-EMP003-01: Con kết hôn 1 ngày nguyên lương theo Điều 115 BLLĐ",
    badge: "Nguyên lương · Con kết hôn",
    badgeClass: "bg-pink-lt",
    desc: "Trần Quốc Hưng xin 1 ngày nghỉ tham dự đám cưới con trai (Trần Quốc Anh) kèm Giấy chứng nhận kết hôn -> Chuyển Quản lý duyệt hưởng nguyên lương, 0 trừ phép.",
    payload: {
      leave_type: "SPECIAL_PAID",
      reason_category: "CHILD_MARRIAGE",
      from_date: "2026-10-12",
      to_date: "2026-10-12",
      reason: "Nghỉ tham dự lễ thành hôn của con trai ruột (Trần Quốc Anh)",
      proof: {
        proof_type: "MARRIAGE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "UBND Phường Dịch Vọng Hậu",
        issue_date: "2026-10-01",
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-05T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Hưởng nguyên lương theo Điều 115 BLLĐ: Con kết hôn được nghỉ 01 ngày có lương"
    }
  },
  {
    id: "TC-EMP003-02",
    primaryEmpId: "EMP003",
    title: "TC-EMP003-02: Giấy ra viện nội trú phẫu thuật sỏi thận 4 ngày BV Bạch Mai",
    badge: "BHXH · Ra viện nội trú",
    badgeClass: "bg-info-lt",
    desc: "Nghỉ ốm điều trị nội trú 4 ngày kèm Giấy ra viện BV Bạch Mai có tóm tắt bệnh án & chữ ký GĐ bệnh viện -> Chuyển Quản lý duyệt chế độ ốm đau BHXH.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-08",
      to_date: "2026-10-11",
      reason: "Phẫu thuật tán sỏi nội soi ngược dòng tại Bệnh viện Bạch Mai",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Bạch Mai",
        issue_date: "2026-10-11",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-12T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Chứng từ nội trú hợp lệ: Chuyển Quản lý duyệt chế độ ốm đau BHXH"
    }
  },

  // =========================================================================
  // EMP004: Lê Văn Nam (Senior Developer - Engineering)
  // =========================================================================
  {
    id: "TC-MGR-01",
    primaryEmpId: "EMP004",
    title: "TC-MGR-01: Phép năm 4 ngày -> Chuyển Quản lý Kỹ thuật (EMP001)",
    badge: "Cấp 1 · Engineering Mgr",
    badgeClass: "bg-primary-lt",
    desc: "Lê Văn Nam xin 4 ngày phép năm có bàn giao cùng phòng cho EMP003 -> Chuyển Đỗ Hoàng Long (Engineering Manager) duyệt.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-08",
      handover_person_id: "EMP003",
      handover: { employee_id: "EMP003", department: "Engineering", status: "ACTIVE", absent_dates: [] },
      reason: "Nghỉ phép thường niên",
      submitted_at: "2026-09-25T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Phép năm 3-5 ngày: Thẩm quyền duyệt là Quản lý Kỹ thuật (EMP001)"
    }
  },
  {
    id: "TC-HARD-06",
    primaryEmpId: "EMP004",
    title: "TC-HARD-06: Bàn giao chéo phòng ban không hợp lệ (Bắt lỗi)",
    badge: "Lỗi bàn giao · Bị chặn",
    badgeClass: "bg-danger-lt",
    desc: "Nhân viên Kỹ thuật bàn giao công việc cho EMP009 phòng Marketing -> Báo lỗi HANDOVER_INVALID, yêu cầu sửa đơn.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-07",
      handover_person_id: "EMP009",
      handover: { employee_id: "EMP009", department: "Marketing & Operations", status: "ACTIVE", absent_dates: [] },
      reason: "Nghỉ phép thường niên",
      submitted_at: "2026-09-25T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "NEED_CORRECTION",
      target_role: "AI",
      error_code: "HANDOVER_INVALID",
      note: "Chặn tự động: Người nhận bàn giao khác phòng ban"
    }
  },
  {
    id: "TC-VLM-05",
    primaryEmpId: "EMP004",
    title: "TC-VLM-05: Chứng từ y tế có chữ ký số theo TT 25/2025/TT-BYT",
    badge: "VLM · Chữ ký số",
    badgeClass: "bg-success-lt",
    desc: "Chứng từ điện tử BV Hồng Ngọc không có mộc đỏ vật lý nhưng có chữ ký số bệnh viện -> Hợp lệ chuyển Quản lý Kỹ thuật duyệt.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-12",
      to_date: "2026-10-14",
      reason: "Viêm xoang hàm cấp tính có mủ, điều trị ngoại trú",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Đa khoa Hồng Ngọc",
        signature_present: false,
        digital_signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-12T07:30:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Chữ ký số hợp lệ theo TT 25/2025/TT-BYT, không bắt bẻ mộc đỏ"
    }
  },
  {
    id: "TC-VLM-03",
    primaryEmpId: "EMP004",
    title: "TC-VLM-03: Bác sĩ chỉ định 1 ngày nhưng đơn xin 3 ngày (Lệch số ngày)",
    badge: "Bẫy VLM · Lệch ngày",
    badgeClass: "bg-danger-lt",
    desc: "Giấy chứng nhận chỉ cho nghỉ 1 ngày (12/10) nhưng nhân viên nộp xin 3 ngày -> Bắt lỗi MEDICAL_DAYS_MISMATCH, yêu cầu sửa đơn.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-12",
      to_date: "2026-10-14",
      reason: "Rối loạn tiêu hóa cấp, theo dõi ngộ độc thức ăn",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Đa khoa Hồng Ngọc",
        recommended_from_date: "2026-10-12",
        recommended_to_date: "2026-10-12",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-12T07:30:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "NEED_CORRECTION",
      target_role: "AI",
      error_code: "MEDICAL_DAYS_MISMATCH",
      note: "Bẫy số ngày: Số ngày xin (3) vượt quá số ngày bác sĩ cho nghỉ (1)"
    }
  },

  // =========================================================================
  // EMP005: Nguyễn Văn An (Developer - Engineering)
  // =========================================================================
  {
    id: "TC-AI-01",
    primaryEmpId: "EMP005",
    title: "TC-AI-01: Phép năm 1 ngày tự động duyệt (1-2 ngày đủ số dư)",
    badge: "AI Cấp 0 · Tự duyệt",
    badgeClass: "bg-success-lt",
    desc: "Nguyễn Văn An xin 1 ngày phép năm (05/10/2026), báo trước đúng hạn, đủ số dư phép -> AI Cấp 0 tự động duyệt, trừ 1 ngày phép.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-05",
      reason: "Việc riêng gia đình",
      submitted_at: "2026-10-01T08:00:00+07:00",
      total_team_members: 6,
      team_absent_count: 0
    },
    expected: {
      decision: "AUTO_APPROVE",
      target_role: "AI",
      deducted_days: 1,
      note: "Hệ thống AI tự động duyệt & trừ 1 ngày phép năm"
    }
  },
  {
    id: "TC-AI-05",
    primaryEmpId: "EMP005",
    title: "TC-AI-05: Đơn rơi vào ngày lễ / nghỉ bù Giỗ Tổ (Không cần xin phép)",
    badge: "Lễ / Cuối tuần",
    badgeClass: "bg-secondary-lt",
    desc: "Xin nghỉ trùng Giỗ Tổ Hùng Vương & nghỉ bù (26-27/04/2026) -> Hệ thống xác định không cần xin phép vì là ngày nghỉ luật định.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-04-26",
      to_date: "2026-04-27",
      reason: "Nghỉ lễ Giỗ Tổ",
      submitted_at: "2026-04-20T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "NO_LEAVE_REQUIRED",
      target_role: "AI",
      error_code: "DAY_ALREADY_NON_WORKING",
      note: "Ngày lễ/nghỉ bù luật định: Không cần xin phép, 0 trừ ngày"
    }
  },
  {
    id: "TC-MGR-04",
    primaryEmpId: "EMP005",
    title: "TC-MGR-04: Nghỉ việc riêng quan hệ họ hàng chưa rõ thân nhân",
    badge: "Cấp 1 · Xác minh thân nhân",
    badgeClass: "bg-warning-lt",
    desc: "Lý do 'Về quê lo việc họ hàng' chưa rõ thân nhân hưởng lương -> Chuyển Quản lý trực tiếp xác minh, không từ chối vội.",
    payload: {
      leave_type: "STATUTORY_UNPAID",
      from_date: "2026-10-05",
      to_date: "2026-10-05",
      reason: "Về quê lo việc họ hàng",
      submitted_at: "2026-10-01T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      error_code: "RELATIONSHIP_UNCLEAR",
      note: "Bắt cờ RELATIONSHIP_UNCLEAR: Quản lý thẩm định mối quan hệ"
    }
  },
  {
    id: "TC-HARD-04",
    primaryEmpId: "EMP005",
    title: "TC-HARD-04: Nghỉ ngắt quãng nhiều lần trong tháng (Cờ lạm dụng)",
    badge: "Cảnh báo · Lạm dụng",
    badgeClass: "bg-danger-lt",
    desc: "Đơn 1 ngày lẽ ra AI tự duyệt, nhưng đã có nhiều đơn trong tháng tích lũy > 2 ngày -> Bắt cờ FLAG_ABUSE_PATTERN, chuyển Quản lý.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-19",
      to_date: "2026-10-19",
      has_abuse_pattern: true,
      reason: "Nghỉ việc riêng",
      submitted_at: "2026-10-15T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      error_code: "FLAG_ABUSE_PATTERN",
      note: "Bắt cờ lạm dụng: Chặn tự duyệt Cấp 0, chuyển Quản lý xem xét"
    }
  },
  {
    id: "TC-VLM-01",
    primaryEmpId: "EMP005",
    title: "TC-VLM-01: Khám ngoại trú 2 ngày phòng khám Medlatec hợp lệ",
    badge: "Chứng từ · Hợp lệ",
    badgeClass: "bg-info-lt",
    desc: "Đơn nghỉ ốm 2 ngày kèm chứng từ y tế PK Đa khoa Medlatec có chữ ký bác sĩ & dấu mộc vuông -> Chuyển Quản lý duyệt.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-06",
      to_date: "2026-10-07",
      reason: "Viêm dạ dày tá tràng cấp tính điều trị ngoại trú",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Phòng khám Đa khoa Medlatec",
        issue_date: "2026-10-06",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-06T07:30:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Chứng từ hợp lệ (2 ngày ốm): Chuyển Quản lý duyệt theo quy chế"
    }
  },
  {
    id: "TC-EMP005-02",
    primaryEmpId: "EMP005",
    title: "TC-EMP005-02: [Bẫy quá hạn] Nộp chứng từ y tế quá thời hạn 3 ngày làm việc",
    badge: "Bẫy VLM · Quá hạn",
    badgeClass: "bg-warning-lt",
    desc: "Chứng từ khám từ ngày 15/09 nhưng đến 05/10 mới nộp (quá 3 ngày làm việc) -> Bắt cảnh báo nộp muộn DOC_SUBMISSION_EXPIRED.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-09-15",
      to_date: "2026-09-16",
      reason: "Nộp bổ sung giấy khám sức khỏe tháng trước",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Đa khoa Quốc tế Thu Cúc",
        issue_date: "2026-09-15",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-05T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      error_code: "DOC_SUBMISSION_EXPIRED",
      note: "Quá hạn nộp chứng từ: Chuyển Quản lý xem xét lý do nộp trễ"
    }
  },

  // =========================================================================
  // EMP006: Bùi Tuấn Kiệt (Developer - Engineering)
  // =========================================================================
  {
    id: "TC-AI-03A",
    primaryEmpId: "EMP006",
    title: "TC-AI-03A: Biên số dư phép - Còn 1 ngày, xin 1 ngày (Duyệt)",
    badge: "Biên số dư · Đạt",
    badgeClass: "bg-success-lt",
    desc: "Bùi Tuấn Kiệt số dư còn 1 ngày: Xin đúng 1 ngày phép năm -> AI tự duyệt, số dư trừ sạch về 0.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-05",
      remaining_leave_days: 1.0,
      reason: "Giải quyết việc cá nhân",
      submitted_at: "2026-10-01T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "AUTO_APPROVE",
      target_role: "AI",
      deducted_days: 1,
      note: "Số dư vừa đủ (1 ngày) -> Tự động duyệt"
    }
  },
  {
    id: "TC-AI-03B",
    primaryEmpId: "EMP006",
    title: "TC-AI-03B: Biên số dư phép - Còn 1 ngày, xin 2 ngày (Từ chối tự động)",
    badge: "Biên số dư · Từ chối",
    badgeClass: "bg-danger-lt",
    desc: "Bùi Tuấn Kiệt số dư còn 1 ngày nhưng xin 2 ngày phép -> Bị hệ thống từ chối tự động vì vượt số dư (BALANCE_EXCEEDED).",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-06",
      remaining_leave_days: 1.0,
      reason: "Nghỉ việc gia đình 2 ngày",
      submitted_at: "2026-10-01T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "AUTO_REJECT",
      target_role: "AI",
      error_code: "BALANCE_EXCEEDED",
      note: "Từ chối tự động (AUTO_REJECT) do vượt số dư phép năm"
    }
  },
  {
    id: "TC-EMP006-01",
    primaryEmpId: "EMP006",
    title: "TC-EMP006-01: Nghỉ ốm 2 ngày tiêu chuẩn BV Đa khoa Đống Đa",
    badge: "BHXH · Ngoại trú chuẩn",
    badgeClass: "bg-info-lt",
    desc: "Nghỉ ốm 2 ngày điều trị viêm xoang có Giấy chứng nhận nghỉ việc hưởng BHXH BV Đống Đa -> Chuyển Quản lý duyệt.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-14",
      to_date: "2026-10-15",
      reason: "Viêm phế quản co thắt điều trị ngoại trú",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Đa khoa Đống Đa",
        issue_date: "2026-10-14",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-14T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Chứng từ tiêu chuẩn: Chuyển Quản lý Kỹ thuật phê duyệt BHXH"
    }
  },
  {
    id: "TC-EMP006-02",
    primaryEmpId: "EMP006",
    title: "TC-EMP006-02: Giấy cấp cứu ban đêm tai nạn nhẹ BV E (Hỗ trợ khẩn cấp)",
    badge: "Khẩn cấp · Ban đêm",
    badgeClass: "bg-danger-lt",
    desc: "Sơ cứu vết thương phần mềm tại Khoa Cấp cứu BV E lúc 23h45 đêm -> Nộp giấy cấp cứu, chuyển Quản lý xem xét phê duyệt hỗ trợ.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-19",
      to_date: "2026-10-19",
      reason: "Cấp cứu ban đêm tai nạn sinh hoạt tại Khoa Cấp cứu BV E",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện E - Khoa Cấp cứu",
        issue_date: "2026-10-19",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-19T07:15:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Ca cấp cứu khẩn cấp: Chuyển Quản lý xử lý nhanh chế độ"
    }
  },

  // =========================================================================
  // EMP007: Lê Thị Hương (Thử việc - Engineering)
  // =========================================================================
  {
    id: "TC-AI-04A",
    primaryEmpId: "EMP007",
    title: "TC-AI-04A: Thử việc xin phép năm hưởng lương (Chặn sửa đơn)",
    badge: "Thử việc · Bị chặn",
    badgeClass: "bg-warning-lt",
    desc: "Lê Thị Hương (thử việc) xin phép năm hưởng lương -> Bắt lỗi PROBATION_ANNUAL_RESTRICTED, yêu cầu sửa đơn.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-05",
      employment_status: "PROBATION",
      remaining_leave_days: 0.0,
      reason: "Nghỉ phép năm",
      submitted_at: "2026-10-01T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "NEED_CORRECTION",
      target_role: "AI",
      error_code: "PROBATION_ANNUAL_RESTRICTED",
      note: "Chặn tự động: Thử việc chưa phát sinh phép năm hưởng lương"
    }
  },
  {
    id: "TC-AI-04B",
    primaryEmpId: "EMP007",
    title: "TC-AI-04B: Thử việc xin nghỉ không lương (Hợp lệ chuyển Quản lý)",
    badge: "Thử việc · Quản lý",
    badgeClass: "bg-primary-lt",
    desc: "Lê Thị Hương (thử việc) xin nghỉ việc riêng không lương UNPAID_OTHER -> Hợp lệ chuyển Quản lý trực tiếp duyệt.",
    payload: {
      leave_type: "UNPAID_OTHER",
      from_date: "2026-10-05",
      to_date: "2026-10-05",
      employment_status: "PROBATION",
      remaining_leave_days: 0.0,
      reason: "Giải quyết việc cá nhân đột xuất",
      submitted_at: "2026-09-20T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Hợp lệ cho thử việc: Chuyển Quản lý trực tiếp (Cấp 1)"
    }
  },
  {
    id: "TC-EMP007-01",
    primaryEmpId: "EMP007",
    title: "TC-EMP007-01: Thử việc nghỉ ốm 1 ngày có chứng từ PK Medlatec",
    badge: "Thử việc · Ốm BHXH",
    badgeClass: "bg-info-lt",
    desc: "Nhân sự thử việc có đóng BHXH nộp đơn ốm 1 ngày kèm chứng từ đầy đủ -> Chuyển Quản lý trực tiếp phê duyệt.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-15",
      to_date: "2026-10-15",
      reason: "Sốt siêu vi điều trị ngoại trú theo chỉ định",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Phòng khám Đa khoa Medlatec Cầu Giấy",
        issue_date: "2026-10-15",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-15T08:10:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Thử việc có chứng từ y tế hợp lệ: Chuyển Quản lý duyệt chế độ BHXH"
    }
  },
  {
    id: "TC-EMP007-02",
    primaryEmpId: "EMP007",
    title: "TC-EMP007-02: [Bẫy thiếu chữ ký] Chứng từ thiếu chữ ký bác sĩ điều trị",
    badge: "Bẫy VLM · Thiếu ký",
    badgeClass: "bg-danger-lt",
    desc: "Chứng từ có mộc đỏ bệnh viện nhưng ô bác sĩ khám ký tên bị bỏ trống -> Bắt lỗi DOC_SIGNATURE_MISSING, yêu cầu bổ sung.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-15",
      to_date: "2026-10-15",
      reason: "Nghỉ ốm theo dõi",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Giao thông Vận tải",
        issue_date: "2026-10-15",
        signature_present: false,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-15T08:15:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "NEED_CORRECTION",
      target_role: "AI",
      error_code: "DOC_SIGNATURE_MISSING",
      note: "Thiếu chữ ký bác sĩ chuyên khoa: Yêu cầu nhân viên xin xác nhận lại"
    }
  },

  // =========================================================================
  // EMP008: Nguyễn Thị Kim Ngân (Operations Specialist - Marketing & Ops)
  // =========================================================================
  {
    id: "TC-EMP008-01",
    primaryEmpId: "EMP008",
    title: "TC-EMP008-01: Khám thai định kỳ 1 ngày có chứng nhận y tế (BHXH)",
    badge: "BHXH · Khám thai",
    badgeClass: "bg-pink-lt",
    desc: "Nguyễn Thị Kim Ngân nộp đơn khám thai định kỳ kèm Giấy chứng nhận BV Phụ sản Hà Nội -> Chuyển Quản lý duyệt hưởng chế độ thai sản.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-16",
      to_date: "2026-10-16",
      reason: "Khám thai định kỳ tuần thứ 28 tại BV Phụ sản Hà Nội",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Phụ sản Hà Nội",
        issue_date: "2026-10-16",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-16T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Chế độ thai sản BHXH: Chuyển Quản lý duyệt theo Luật BHXH"
    }
  },
  {
    id: "TC-EMP008-02",
    primaryEmpId: "EMP008",
    title: "TC-EMP008-02: Tang lễ tứ thân phụ mẫu 3 ngày hưởng nguyên lương",
    badge: "Nguyên lương · Tang chế",
    badgeClass: "bg-dark-lt",
    desc: "Nghỉ việc riêng hưởng nguyên lương do bố đẻ qua đời kèm Giấy chứng tử UBND xã -> Quản lý duyệt 3 ngày nguyên lương theo Điều 115 BLLĐ.",
    payload: {
      leave_type: "SPECIAL_PAID",
      reason_category: "PARENT_FUNERAL",
      from_date: "2026-10-20",
      to_date: "2026-10-22",
      reason: "Lo tang lễ cho bố ruột (Nguyễn Văn Thành) tại quê nhà Nam Định",
      proof: {
        proof_type: "OTHER",
        proof_verification_status: "VERIFIED",
        issuer: "UBND Xã Hải Hậu, Tỉnh Nam Định",
        issue_date: "2026-10-19",
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-20T06:30:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Tang chế tứ thân phụ mẫu: 03 ngày hưởng nguyên lương theo Điều 115 BLLĐ"
    }
  },
  {
    id: "TC-EMP008-03",
    primaryEmpId: "EMP008",
    title: "TC-EMP008-03: Phép năm 2 ngày có bàn giao cùng phòng cho EMP010",
    badge: "Phép năm · Có bàn giao",
    badgeClass: "bg-success-lt",
    desc: "Nguyễn Thị Kim Ngân xin nghỉ phép năm 2 ngày có bàn giao công việc cho Phan Thảo My (EMP010) cùng phòng Marketing & Ops.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-08",
      to_date: "2026-10-09",
      handover_person_id: "EMP010",
      handover: { employee_id: "EMP010", department: "Marketing & Operations", status: "ACTIVE", absent_dates: [] },
      reason: "Nghỉ phép thường niên",
      submitted_at: "2026-10-01T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "AUTO_APPROVE",
      target_role: "AI",
      deducted_days: 2,
      note: "Phép năm 1-2 ngày có bàn giao hợp lệ -> AI tự động phê duyệt"
    }
  },

  // =========================================================================
  // EMP009: Võ Minh Khang (Marketing Specialist - Marketing & Ops)
  // =========================================================================
  {
    id: "TC-MGR-03",
    primaryEmpId: "EMP009",
    title: "TC-MGR-03: Nghỉ kết hôn 3 ngày hưởng nguyên lương (SPECIAL_PAID)",
    badge: "Cấp 1 · Chế độ kết hôn",
    badgeClass: "bg-pink-lt",
    desc: "Võ Minh Khang nộp đơn kết hôn 3 ngày kèm giấy đăng ký kết hôn UBND Quận Cầu Giấy -> Quản lý duyệt hưởng nguyên lương, 0 trừ phép năm.",
    payload: {
      leave_type: "SPECIAL_PAID",
      reason_category: "SELF_MARRIAGE",
      from_date: "2026-10-05",
      to_date: "2026-10-07",
      reason: "Nghỉ đám cưới bản thân (Lễ thành hôn)",
      proof: {
        proof_type: "MARRIAGE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "UBND Phường Dịch Vọng Hậu",
        issue_date: "2026-09-20",
        document_readability: "READABLE"
      },
      submitted_at: "2026-09-25T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Hưởng nguyên lương, không trừ phép năm (Điều 115 BLLĐ)"
    }
  },
  {
    id: "TC-VLM-02",
    primaryEmpId: "EMP009",
    title: "TC-VLM-02: Bẫy lệch tên bệnh nhân trên giấy nghỉ ốm (NAME_MISMATCH)",
    badge: "Bẫy VLM · Lệch tên",
    badgeClass: "bg-danger-lt",
    desc: "Giấy chứng nhận ghi tên bệnh nhân 'Phạm Quốc Dũng' khác tên Võ Minh Khang -> Bắt cờ NAME_MISMATCH, yêu cầu sửa/nộp lại đơn.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-12",
      to_date: "2026-10-14",
      reason: "Nghỉ ốm điều trị",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Đa khoa Medlatec",
        patient_name: "Phạm Quốc Dũng",
        issue_date: "2026-10-12",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-12T07:30:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "NEED_CORRECTION",
      target_role: "AI",
      error_code: "NAME_MISMATCH",
      note: "Bẫy thị giác: Tên trên chứng từ không khớp tên nhân viên nộp"
    }
  },
  {
    id: "TC-EMP009-03",
    primaryEmpId: "EMP009",
    title: "TC-EMP009-03: Phép năm 3 ngày có bàn giao cho EMP008 -> Quản lý duyệt",
    badge: "Cấp 1 · Mkt & Ops Mgr",
    badgeClass: "bg-primary-lt",
    desc: "Võ Minh Khang xin 3 ngày phép năm có bàn giao cùng phòng cho EMP008 -> Chuyển Dương Mỹ Duyên (Marketing/Ops Manager) duyệt.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-19",
      to_date: "2026-10-21",
      handover_person_id: "EMP008",
      handover: { employee_id: "EMP008", department: "Marketing & Operations", status: "ACTIVE", absent_dates: [] },
      reason: "Nghỉ việc gia đình",
      submitted_at: "2026-10-10T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Phép năm 3-5 ngày: Thẩm quyền duyệt là Quản lý Marketing (EMP002)"
    }
  },

  // =========================================================================
  // EMP010: Phan Thảo My (Operations Specialist - Marketing & Ops)
  // =========================================================================
  {
    id: "TC-MGR-02",
    primaryEmpId: "EMP010",
    title: "TC-MGR-02: Phép năm 4 ngày -> Chuyển Quản lý Marketing (EMP002)",
    badge: "Cấp 1 · Mkt & Ops Mgr",
    badgeClass: "bg-primary-lt",
    desc: "Phan Thảo My xin 4 ngày phép năm có bàn giao cùng phòng cho EMP008 -> Chuyển Dương Mỹ Duyên (Mkt/Ops Manager) duyệt.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-08",
      handover_person_id: "EMP008",
      handover: { employee_id: "EMP008", department: "Marketing & Operations", status: "ACTIVE", absent_dates: [] },
      reason: "Nghỉ phép cá nhân",
      submitted_at: "2026-09-25T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Phép năm 3-5 ngày: Thẩm quyền duyệt là Quản lý Marketing (EMP002)"
    }
  },
  {
    id: "TC-HARD-05",
    primaryEmpId: "EMP010",
    title: "TC-HARD-05: Tỷ lệ vắng mặt phòng ban vượt 30% (Chặn tự duyệt)",
    badge: "Cảnh báo · Quota 30%",
    badgeClass: "bg-danger-lt",
    desc: "Phòng Marketing đã có 2/6 thành viên vắng (33%) -> Bắt cờ TEAM_QUOTA_EXCEEDED, chặn tự duyệt, chuyển Quản lý trực tiếp.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-05",
      team_absent_count: 2,
      total_team_members: 6,
      reason: "Nghỉ cá nhân",
      submitted_at: "2026-10-01T08:00:00+07:00"
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      error_code: "TEAM_QUOTA_EXCEEDED",
      note: "Vắng >= 30% nhân sự: Chuyển Quản lý điều phối nguồn lực"
    }
  },
  {
    id: "TC-VLM-04",
    primaryEmpId: "EMP010",
    title: "TC-VLM-04: Ảnh chụp chứng từ bị mờ nhòe, mất nét (DOC_ILLEGIBLE)",
    badge: "Bẫy VLM · Mờ nhòe",
    badgeClass: "bg-danger-lt",
    desc: "Ảnh chụp tài liệu mờ nhòe, mất nét không đọc được thông tin -> Bắt cờ DOC_ILLEGIBLE, yêu cầu tải lại ảnh rõ nét.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-08",
      to_date: "2026-10-10",
      reason: "Nghỉ ốm điều trị",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        document_readability: "ILLEGIBLE"
      },
      submitted_at: "2026-10-08T07:30:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "NEED_CORRECTION",
      target_role: "AI",
      error_code: "DOC_ILLEGIBLE",
      note: "Bẫy chất lượng ảnh: Ảnh mờ nhòe, yêu cầu bổ sung ảnh đọc được"
    }
  },
  {
    id: "TC-EMP010-02",
    primaryEmpId: "EMP010",
    title: "TC-EMP010-02: Nghỉ ốm 3 ngày tiêu chuẩn BV Vinmec Times City",
    badge: "BHXH · Vinmec Times City",
    badgeClass: "bg-info-lt",
    desc: "Nghỉ ốm ngoại trú 3 ngày do viêm amidan hốc mủ kèm chứng từ chuẩn Vinmec Times City -> Quản lý duyệt chế độ BHXH.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-08",
      to_date: "2026-10-10",
      reason: "Viêm amidan hốc mủ sốt cao điều trị ngoại trú",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện ĐKQT Vinmec Times City",
        issue_date: "2026-10-08",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-08T07:30:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Chứng từ hợp lệ (3 ngày): Chuyển Quản lý duyệt theo quy chế"
    }
  },

  // =========================================================================
  // EMP011: Hoàng Kim Yến (Operations Specialist - Marketing & Ops)
  // =========================================================================
  {
    id: "TC-AI-02",
    primaryEmpId: "EMP011",
    title: "TC-AI-02: Nghỉ ốm 1 ngày có đơn thuốc nộp trước 08:30 (BHXH)",
    badge: "AI Cấp 0 · Ốm đau BHXH",
    badgeClass: "bg-info-lt",
    desc: "Hoàng Kim Yến nộp đơn ốm 1 ngày lúc 07:45 sáng kèm đơn thuốc bệnh viện hợp lệ -> AI tự duyệt, 0 trừ phép năm (chế độ BHXH).",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-05",
      to_date: "2026-10-05",
      reason: "Bị sốt cảm cúm đột xuất",
      submitted_at: "2026-10-05T07:45:00+07:00",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Đa khoa Quốc tế Hà Nội",
        issue_date: "2026-10-05",
        signature_present: true,
        document_readability: "READABLE"
      },
      total_team_members: 6
    },
    expected: {
      decision: "AUTO_APPROVE",
      target_role: "AI",
      deducted_days: 0,
      note: "Chế độ ốm đau BHXH: Tự duyệt, không trừ phép năm"
    }
  },
  {
    id: "TC-EMP011-02",
    primaryEmpId: "EMP011",
    title: "TC-EMP011-02: Tai nạn giao thông nhẹ trên đường đi làm (Thẩm định tai nạn)",
    badge: "Thẩm định · Tai nạn LĐ",
    badgeClass: "bg-warning-lt",
    desc: "Va chạm giao thông nhẹ trên tuyến đường đi làm hợp lý lúc 07:30 sáng -> Nộp bệnh án sơ cứu, chuyển Quản lý thẩm định chế độ tai nạn lao động.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-13",
      to_date: "2026-10-14",
      reason: "Xây xát phần mềm do va quệt xe trên đường đi làm",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Giao thông Vận tải",
        issue_date: "2026-10-13",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-13T08:15:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Hồ sơ tai nạn trên đường đi làm: Quản lý thẩm định biên bản & lộ trình"
    }
  },
  {
    id: "TC-EMP011-03",
    primaryEmpId: "EMP011",
    title: "TC-EMP011-03: Phép năm 1 ngày việc riêng (Tự động duyệt)",
    badge: "AI Cấp 0 · Tự duyệt",
    badgeClass: "bg-success-lt",
    desc: "Hoàng Kim Yến xin 1 ngày phép năm giải quyết việc cá nhân, đủ số dư phép -> AI tự duyệt.",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-23",
      to_date: "2026-10-23",
      reason: "Việc riêng gia đình",
      submitted_at: "2026-10-18T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "AUTO_APPROVE",
      target_role: "AI",
      deducted_days: 1,
      note: "Phép năm 1 ngày đủ số dư: AI tự động duyệt & trừ 1 ngày phép"
    }
  },

  // =========================================================================
  // EMP012: Lê Mai Loan (Creative / Operations - Marketing & Ops)
  // =========================================================================
  {
    id: "TC-HARD-02",
    primaryEmpId: "EMP012",
    title: "TC-HARD-02: Nghỉ dài hạn 21 ngày làm việc -> Bắt buộc Tổng Giám đốc (Boss)",
    badge: "Cấp Sếp · Nghỉ dài hạn",
    badgeClass: "bg-purple-lt",
    desc: "Lê Mai Loan xin 21 ngày làm việc (01-29/10/2026) có bàn giao -> Thẩm quyền bắt buộc là Tổng Giám đốc (CEO/Boss).",
    payload: {
      leave_type: "UNPAID_OTHER",
      from_date: "2026-10-01",
      to_date: "2026-10-29",
      handover_person_id: "EMP010",
      handover: { employee_id: "EMP010", department: "Marketing & Operations", status: "ACTIVE", absent_dates: [] },
      reason: "Nghỉ việc riêng dài hạn",
      submitted_at: "2026-09-01T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "CEO",
      note: "Đơn >= 20 ngày làm việc: Thẩm quyền duyệt là Tổng Giám đốc (Boss)"
    }
  },
  {
    id: "TC-EMP012-02",
    primaryEmpId: "EMP012",
    title: "TC-EMP012-02: Con ốm 2 ngày hưởng trợ cấp BHXH (Con dưới 7 tuổi)",
    badge: "BHXH · Chăm sóc con ốm",
    badgeClass: "bg-info-lt",
    desc: "Nghỉ chăm sóc con gái 4 tuổi bị viêm phế quản kèm Giấy chứng nhận BV Nhi Trung ương -> Chuyển Quản lý duyệt hưởng chế độ con ốm.",
    payload: {
      leave_type: "SICK_MEDICAL",
      from_date: "2026-10-20",
      to_date: "2026-10-21",
      reason: "Nghỉ chăm sóc con gái ruột (Lê Ngọc Ánh, 4 tuổi) điều trị viêm phế quản",
      proof: {
        proof_type: "MEDICAL_LEAVE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "Bệnh viện Nhi Trung ương",
        issue_date: "2026-10-20",
        signature_present: true,
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-20T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      note: "Chế độ con ốm hưởng BHXH theo Luật BHXH: Quản lý phê duyệt"
    }
  },
  {
    id: "TC-EMP012-03",
    primaryEmpId: "EMP012",
    title: "TC-EMP012-03: [Bẫy quy chế] Cưới em gái ruột (Không thuộc diện có lương)",
    badge: "Bẫy quy chế · Không lương",
    badgeClass: "bg-warning-lt",
    desc: "Tham dự lễ cưới em gái ruột -> Điều 115 BLLĐ chỉ cho nghỉ có lương khi bản thân hoặc con kết hôn. Đơn chuyển thành nghỉ không lương hoặc phép năm.",
    payload: {
      leave_type: "SPECIAL_PAID",
      from_date: "2026-10-24",
      to_date: "2026-10-24",
      reason: "Tham dự lễ thành hôn của em gái ruột (Lê Mai Linh)",
      proof: {
        proof_type: "MARRIAGE_CERTIFICATE",
        proof_verification_status: "VERIFIED",
        issuer: "UBND Phường Quan Hoa, Quận Cầu Giấy",
        issue_date: "2026-10-10",
        document_readability: "READABLE"
      },
      submitted_at: "2026-10-15T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "DIRECT_MANAGER",
      error_code: "NON_COMPLIANT_POLICY",
      note: "Bẫy quy chế: Anh/chị/em cưới không có lương -> Quản lý hướng dẫn đổi loại phép"
    }
  },

  // =========================================================================
  // EMP001: Đỗ Hoàng Long (Engineering Manager)
  // =========================================================================
  {
    id: "TC-HARD-01",
    primaryEmpId: "EMP001",
    title: "TC-HARD-01: Quản lý nộp đơn -> Không tự duyệt, chuyển Sếp (Boss)",
    badge: "Cấp Sếp · Anti Self-Approval",
    badgeClass: "bg-purple-lt",
    desc: "Đỗ Hoàng Long nộp đơn -> Quy chế chống tự phê duyệt (Anti-self-approval), thẩm quyền chuyển thẳng lên Sếp (EMP000 - Boss).",
    payload: {
      leave_type: "ANNUAL",
      from_date: "2026-10-05",
      to_date: "2026-10-07",
      reason: "Nghỉ phép cá nhân",
      submitted_at: "2026-09-25T08:00:00+07:00",
      total_team_members: 6
    },
    expected: {
      decision: "ESCALATE",
      target_role: "CEO",
      note: "Người nộp là Quản lý: Chuyển cấp trên trực tiếp là Tổng Giám đốc"
    }
  }
];

/* ========================================================================= */
/* METADATA SPRINT 1: PHÂN LOẠI 3 NHÓM BẤT ĐỊNH & CÂU HỎI HÀNH ĐỘNG CỤ THỂ   */
/* ========================================================================= */
const TESTCASE_SPRINT1_METADATA = {
  "TC-HARD-03": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Cấp CEO)",
    leaveTypeFriendly: "Nghỉ phép năm 6 ngày liên tục",
    actionableQuestion: "Đơn nghỉ phép năm 6 ngày làm việc liên tục vượt trần 5 ngày của Quản lý trực tiếp. Tổng Giám đốc (CEO) có phê duyệt chấp thuận đợt nghỉ phép dài ngày này không?"
  },
  "TC-EMP003-01": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ đặc biệt hưởng lương (Con kết hôn)",
    actionableQuestion: "Nhân viên Trần Quốc Hưng xin nghỉ 1 ngày tham dự lễ thành hôn của con trai ruột kèm Giấy kết hôn. Quản lý trực tiếp có phê duyệt hưởng nguyên lương 01 ngày theo Điều 115 BLLĐ không?"
  },
  "TC-EMP003-02": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ ốm nội trú 4 ngày (BV Bạch Mai)",
    actionableQuestion: "Nhân viên nộp Giấy ra viện điều trị phẫu thuật nội trú 4 ngày tại BV Bạch Mai. Quản lý trực tiếp có xác nhận duyệt hưởng chế độ ốm đau BHXH không?"
  },
  "TC-MGR-01": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ phép năm 4 ngày",
    actionableQuestion: "Nhân viên Lê Văn Nam xin 4 ngày phép năm có bàn giao công việc cho EMP003 cùng phòng. Quản lý Kỹ thuật có phê duyệt đợt nghỉ phép này không?"
  },
  "TC-HARD-06": {
    group: "UNCERTAIN_FACTS",
    groupName: "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
    shortPrefix: "Chưa rõ (Bàn giao sai phòng)",
    leaveTypeFriendly: "Nghỉ phép năm (Bàn giao chéo)",
    actionableQuestion: "Đơn bàn giao công việc chéo cho nhân sự khác phòng ban (EMP009 - Marketing). Nhân viên vui lòng chỉ định người nhận bàn giao cùng phòng ban Kỹ thuật."
  },
  "TC-VLM-05": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ ốm có chữ ký số điện tử",
    actionableQuestion: "Chứng từ y tế BV Hồng Ngọc có chữ ký số điện tử hợp lệ theo TT 25/2025/TT-BYT. Quản lý trực tiếp có phê duyệt 3 ngày nghỉ ốm đau BHXH không?"
  },
  "TC-VLM-03": {
    group: "UNCERTAIN_FACTS",
    groupName: "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
    shortPrefix: "Chưa rõ (Bác sĩ chỉ định lệch ngày)",
    leaveTypeFriendly: "Nghỉ ốm/y tế 3 ngày (Bác sĩ cho 1 ngày)",
    actionableQuestion: "Đơn xin nghỉ 3 ngày (12/10 - 14/10) nhưng giấy chứng nhận y tế chỉ chỉ định nghỉ 1 ngày (12/10). Quản lý có chấp thuận cho nhân viên nghỉ không lương 2 ngày còn lại hoặc yêu cầu nhân viên điều chỉnh lại ngày nghỉ theo chứng từ?"
  },
  "TC-AI-01": {
    group: "ROUTINE",
    groupName: "1. Thường quy / Rõ ràng (Tự động xử lý)",
    shortPrefix: "Rõ ràng (Duyệt)",
    leaveTypeFriendly: "Nghỉ phép năm 1 ngày",
    actionableQuestion: "Tự động xử lý hoàn toàn: Phép năm hợp lệ, đủ số dư, hệ thống AI tự động duyệt & trừ 1 ngày phép."
  },
  "TC-AI-05": {
    group: "ROUTINE",
    groupName: "1. Thường quy / Rõ ràng (Tự động xử lý)",
    shortPrefix: "Rõ ràng (Miễn xin phép)",
    leaveTypeFriendly: "Nghỉ lễ Giỗ Tổ Hùng Vương & nghỉ bù",
    actionableQuestion: "Tự động xử lý hoàn toàn: Khoảng thời gian xin nghỉ trùng ngày lễ Giỗ Tổ & nghỉ bù luật định, không cần làm đơn xin nghỉ phép."
  },
  "TC-MGR-04": {
    group: "UNCERTAIN_FACTS",
    groupName: "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
    shortPrefix: "Chưa rõ (Thân nhân họ hàng)",
    leaveTypeFriendly: "Nghỉ việc riêng không lương",
    actionableQuestion: "Đơn xin nghỉ 'về quê lo việc họ hàng' chưa rõ mức độ thân nhân hưởng lương hay không hưởng lương. Quản lý trực tiếp có chấp thuận duyệt đơn nghỉ không lương này không?"
  },
  "TC-HARD-04": {
    group: "OUT_OF_POLICY",
    groupName: "3. Nằm ngoài phạm vi quy định (Quá hạn / Lạm dụng / Quota)",
    shortPrefix: "Ngoài quy định (Cờ lạm dụng)",
    leaveTypeFriendly: "Nghỉ phép năm (Nghỉ thứ Hai lặp lại)",
    actionableQuestion: "Đơn nghỉ phép rơi vào ngày thứ Hai sau chuỗi nghỉ các đầu tuần trước (hệ thống gắn cờ nghi vấn lạm dụng). Quản lý trực tiếp có chấp thuận hay yêu cầu nhân sự giải trình?"
  },
  "TC-VLM-01": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ ốm ngoại trú 2 ngày (Medlatec)",
    actionableQuestion: "Nhân viên khám ngoại trú viêm dạ dày 2 ngày có giấy chứng nhận PK Medlatec hợp lệ. Quản lý trực tiếp có phê duyệt chế độ ốm đau BHXH không?"
  },
  "TC-EMP005-02": {
    group: "OUT_OF_POLICY",
    groupName: "3. Nằm ngoài phạm vi quy định (Quá hạn / Lạm dụng / Quota)",
    shortPrefix: "Ngoài quy định (Quá hạn nộp chứng từ)",
    leaveTypeFriendly: "Nghỉ ốm bổ sung chứng từ trễ hạn",
    actionableQuestion: "Chứng từ khám sức khỏe nộp trễ quá thời hạn 3 ngày làm việc theo quy chế công ty. Quản lý có chấp thuận cho hưởng chế độ ngoại lệ hay chuyển sang trừ phép năm?"
  },
  "TC-AI-03A": {
    group: "ROUTINE",
    groupName: "1. Thường quy / Rõ ràng (Tự động xử lý)",
    shortPrefix: "Rõ ràng (Duyệt)",
    leaveTypeFriendly: "Nghỉ phép năm 1 ngày (Số dư còn 1)",
    actionableQuestion: "Tự động xử lý hoàn toàn: Số dư vừa đủ 1 ngày, hệ thống AI tự động duyệt & trừ 1 ngày phép."
  },
  "TC-AI-03B": {
    group: "ROUTINE",
    groupName: "1. Thường quy / Rõ ràng (Tự động xử lý)",
    shortPrefix: "Rõ ràng (Từ chối tự động)",
    leaveTypeFriendly: "Nghỉ phép năm 2 ngày (Số dư chỉ còn 1)",
    actionableQuestion: "Tự động xử lý hoàn toàn: Bị từ chối tự động do số ngày yêu cầu (2) vượt quá số dư phép năm còn lại (1)."
  },
  "TC-EMP006-01": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ ốm 2 ngày BV Đống Đa",
    actionableQuestion: "Nhân viên điều trị ngoại trú viêm phế quản 2 ngày kèm Giấy chứng nhận BV Đống Đa. Quản lý có phê duyệt chế độ ốm đau BHXH không?"
  },
  "TC-EMP006-02": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Cấp cứu ban đêm tai nạn sinh hoạt BV E",
    actionableQuestion: "Nhân viên cấp cứu ban đêm tai nạn sinh hoạt nhẹ tại BV E nộp Giấy cấp cứu. Quản lý trực tiếp có phê duyệt chế độ hỗ trợ khẩn cấp không?"
  },
  "TC-AI-04A": {
    group: "UNCERTAIN_FACTS",
    groupName: "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
    shortPrefix: "Chưa rõ (Thử việc chưa có phép năm)",
    leaveTypeFriendly: "Nghỉ phép năm (Thử việc)",
    actionableQuestion: "Nhân sự đang trong thời gian thử việc chưa đủ điều kiện hưởng ngày phép năm có lương. Nhân viên có muốn điều chỉnh sang nghỉ việc riêng không hưởng lương không?"
  },
  "TC-AI-04B": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ việc riêng không lương (Thử việc)",
    actionableQuestion: "Nhân sự thử việc xin nghỉ việc riêng không lương 1 ngày giải quyết việc cá nhân đột xuất. Quản lý trực tiếp có đồng ý phê duyệt đơn này không?"
  },
  "TC-EMP007-01": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Thử việc nghỉ ốm 1 ngày PK Medlatec",
    actionableQuestion: "Nhân sự thử việc nghỉ ốm 1 ngày có chứng nhận y tế PK Medlatec. Quản lý trực tiếp có phê duyệt nghỉ ốm theo quy định BHXH không?"
  },
  "TC-EMP007-02": {
    group: "UNCERTAIN_FACTS",
    groupName: "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
    shortPrefix: "Chưa rõ (Chứng từ thiếu chữ ký bác sĩ)",
    leaveTypeFriendly: "Nghỉ ốm theo dõi (Thiếu chữ ký)",
    actionableQuestion: "Giấy chứng nhận nghỉ việc thiếu chữ ký của bác sĩ điều trị. Nhân viên vui lòng liên hệ cơ sở y tế để bổ sung chữ ký hợp lệ trước khi gửi lại."
  },
  "TC-EMP008-01": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Khám thai định kỳ 1 ngày (BV Phụ sản)",
    actionableQuestion: "Nhân viên mang thai tuần 28 xin nghỉ 1 ngày khám thai định kỳ kèm sổ y bạ. Quản lý có phê duyệt 1 ngày nghỉ chế độ thai sản BHXH không?"
  },
  "TC-EMP008-02": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ đặc biệt hưởng lương (Tang lễ bố ruột)",
    actionableQuestion: "Nhân viên xin nghỉ 3 ngày lo tang lễ cho bố ruột kèm giấy tờ xác nhận. Quản lý trực tiếp có phê duyệt 03 ngày nghỉ nguyên lương theo Điều 115 BLLĐ không?"
  },
  "TC-EMP008-03": {
    group: "ROUTINE",
    groupName: "1. Thường quy / Rõ ràng (Tự động xử lý)",
    shortPrefix: "Rõ ràng (Duyệt)",
    leaveTypeFriendly: "Nghỉ phép năm 2 ngày có bàn giao",
    actionableQuestion: "Tự động xử lý hoàn toàn: Phép năm 2 ngày có bàn giao cùng phòng ban cho EMP010, hệ thống AI tự động duyệt & trừ 2 ngày phép."
  },
  "TC-MGR-03": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ kết hôn bản thân 3 ngày nguyên lương",
    actionableQuestion: "Nhân viên Võ Minh Khang xin nghỉ 3 ngày kết hôn kèm Giấy chứng nhận kết hôn hợp lệ. Quản lý trực tiếp có phê duyệt 3 ngày nghỉ chế độ đặc biệt hưởng 100% lương theo Điều 115 BLLĐ không?"
  },
  "TC-VLM-02": {
    group: "UNCERTAIN_FACTS",
    groupName: "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
    shortPrefix: "Chưa rõ (Sai tên người bệnh)",
    leaveTypeFriendly: "Nghỉ ốm (Tên trên giấy khám không khớp)",
    actionableQuestion: "Họ tên bệnh nhân trên chứng từ y tế là 'Nguyễn Văn Nam', không khớp với tên nhân viên 'Võ Minh Khang'. Nhân viên có nộp nhầm giấy khám bệnh của người khác không?"
  },
  "TC-EMP009-03": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ phép năm 3 ngày có bàn giao",
    actionableQuestion: "Nhân viên xin nghỉ việc gia đình 3 ngày có bàn giao công việc. Quản lý trực tiếp có phê duyệt đợt nghỉ phép này không?"
  },
  "TC-MGR-02": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ phép năm 4 ngày",
    actionableQuestion: "Phan Thảo My xin nghỉ 4 ngày phép năm có bàn giao. Quản lý trực tiếp (Dương Mỹ Duyên) có phê duyệt đợt nghỉ phép này không?"
  },
  "TC-HARD-05": {
    group: "OUT_OF_POLICY",
    groupName: "3. Nằm ngoài phạm vi quy định (Quá hạn / Lạm dụng / Quota)",
    shortPrefix: "Ngoài quy định (Vượt quota vắng mặt)",
    leaveTypeFriendly: "Nghỉ phép năm (Vượt 30% quota phòng)",
    actionableQuestion: "Đơn xin nghỉ khiến tỷ lệ vắng mặt của phòng ban vượt ngưỡng an toàn 30%. Quản lý trực tiếp có chấp thuận phê duyệt ngoại lệ trong đợt cao điểm không?"
  },
  "TC-VLM-04": {
    group: "UNCERTAIN_FACTS",
    groupName: "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
    shortPrefix: "Chưa rõ (Ảnh mờ nhòe)",
    leaveTypeFriendly: "Nghỉ ốm (Chứng từ mờ không đọc được)",
    actionableQuestion: "Hình ảnh chứng từ y tế bị mờ nhòe, không nhận diện được ngày tháng và chẩn đoán bác sĩ. Nhân viên vui lòng chụp lại chứng từ rõ nét."
  },
  "TC-EMP010-02": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ ốm 3 ngày tiêu chuẩn BV Đống Đa",
    actionableQuestion: "Nhân viên viêm amidan cấp sốt cao điều trị 3 ngày có giấy tờ bệnh viện. Quản lý trực tiếp có phê duyệt chế độ ốm đau BHXH không?"
  },
  "TC-AI-02": {
    group: "ROUTINE",
    groupName: "1. Thường quy / Rõ ràng (Tự động xử lý)",
    shortPrefix: "Rõ ràng (Duyệt)",
    leaveTypeFriendly: "Nghỉ ốm 1 ngày có chứng từ hợp lệ",
    actionableQuestion: "Tự động xử lý hoàn toàn: Nghỉ ốm 1 ngày có chứng từ hợp lệ, hệ thống AI tự động phê duyệt chế độ ốm đau."
  },
  "TC-EMP011-02": {
    group: "OUT_OF_POLICY",
    groupName: "3. Nằm ngoài phạm vi quy định (Quá hạn / Lạm dụng / Quota)",
    shortPrefix: "Ngoài quy định (Tai nạn lao động)",
    leaveTypeFriendly: "Nghỉ do va quệt xe trên đường đi làm",
    actionableQuestion: "Nhân viên bị tai nạn giao thông trên đường đi làm nộp biên bản/giấy chứng nhận. Quản lý và Phòng Nhân sự có xác nhận theo diện hỗ trợ tai nạn lao động không?"
  },
  "TC-EMP011-03": {
    group: "ROUTINE",
    groupName: "1. Thường quy / Rõ ràng (Tự động xử lý)",
    shortPrefix: "Rõ ràng (Duyệt)",
    leaveTypeFriendly: "Nghỉ phép năm 1 ngày",
    actionableQuestion: "Tự động xử lý hoàn toàn: Nghỉ phép năm 1 ngày đủ số dư, hệ thống AI tự động duyệt & trừ 1 ngày phép."
  },
  "TC-HARD-02": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Cấp CEO)",
    leaveTypeFriendly: "Nghỉ không lương dài hạn 29 ngày",
    actionableQuestion: "Nhân viên xin nghỉ việc riêng không lương dài hạn 29 ngày làm việc. Tổng Giám đốc (CEO) có phê duyệt trường hợp nghỉ không lương dài ngày này không?"
  },
  "TC-EMP012-02": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Quản lý)",
    leaveTypeFriendly: "Nghỉ chăm con gái 4 tuổi ốm 2 ngày",
    actionableQuestion: "Nhân viên nghỉ chăm con gái 4 tuổi điều trị viêm phế quản kèm giấy tờ y tế. Quản lý có phê duyệt chế độ con ốm đau BHXH không?"
  },
  "TC-EMP012-03": {
    group: "OUT_OF_POLICY",
    groupName: "3. Nằm ngoài phạm vi quy định (Quá hạn / Lạm dụng / Quota)",
    shortPrefix: "Ngoài quy định (Cưới em gái không có lương)",
    leaveTypeFriendly: "Nghỉ đám cưới em gái ruột 1 ngày",
    actionableQuestion: "Nghỉ đám cưới em gái ruột không thuộc diện hưởng nguyên lương theo Điều 115 BLLĐ (chỉ áp dụng cho con ruột/bản thân). Quản lý có chấp thuận cho chuyển sang nghỉ phép năm hoặc không lương không?"
  },
  "TC-HARD-01": {
    group: "AUTHORITY_ESCALATION",
    groupName: "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
    shortPrefix: "Vượt thẩm quyền (Cấp CEO)",
    leaveTypeFriendly: "Engineering Manager xin nghỉ phép 3 ngày",
    actionableQuestion: "Engineering Manager (Đỗ Hoàng Long) xin nghỉ phép cá nhân 3 ngày. Tổng Giám đốc (CEO) có phê duyệt đơn nghỉ phép của cấp Quản lý này không?"
  }
};

let currentTestCaseFilter = "ALL";

function initStaffTestCaseCard() {
  const select = document.getElementById("staff-testcase-select");
  const btnFill = document.getElementById("btn-fill-staff-testcase");

  // Filter pills
  const filterPills = document.querySelectorAll("#testcase-filter-pills button");
  filterPills.forEach(btn => {
    btn.addEventListener("click", () => {
      filterPills.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTestCaseFilter = btn.getAttribute("data-filter") || "ALL";
      renderStaffTestCaseCard();
    });
  });

  if (select) {
    select.addEventListener("change", (e) => {
      const tc = STAFF_TEST_CASES.find(t => t.id === e.target.value);
      if (tc) updateStaffTestCasePreview(tc);
    });
  }

  if (btnFill) {
    btnFill.addEventListener("click", async () => {
      const caseId = document.getElementById("staff-testcase-select")?.value;
      const tc = STAFF_TEST_CASES.find(t => t.id === caseId);
      if (tc) await fillStaffTestCaseIntoForm(tc);
    });
  }
}

function renderStaffTestCaseCard() {
  const card = document.getElementById("staff-testcase-card");
  const select = document.getElementById("staff-testcase-select");
  if (!card || !select) return;

  const currEmp = getCurrentEmployee();
  const empHint = document.getElementById("testcase-emp-hint");
  if (empHint && currEmp) {
    empHint.innerHTML = `Nhân sự đang chọn: <strong>${escapeHtml(currEmp.name)}</strong> (${currentEmployeeId})`;
  }

  // Toàn bộ 38 kịch bản (không giới hạn nhân sự đang chọn nữa)
  let filteredCases = STAFF_TEST_CASES;
  if (currentTestCaseFilter && currentTestCaseFilter !== "ALL") {
    filteredCases = STAFF_TEST_CASES.filter(t => {
      const meta = TESTCASE_SPRINT1_METADATA[t.id];
      return meta && meta.group === currentTestCaseFilter;
    });
  }

  const badgeCount = document.getElementById("badge-testcase-count");
  if (badgeCount) {
    const filterText = currentTestCaseFilter === "ALL" ? "toàn công ty (38 ca)" : `theo nhóm (${filteredCases.length} ca)`;
    badgeCount.innerText = `${filteredCases.length} kịch bản ${filterText}`;
  }

  if (filteredCases.length === 0) {
    select.innerHTML = `<option value="">Không có kịch bản nào phù hợp bộ lọc</option>`;
    const previewBox = document.getElementById("testcase-preview-box");
    if (previewBox) {
      previewBox.innerHTML = `<div class="text-center text-muted py-3">Không có kịch bản nào phù hợp.</div>`;
    }
    return;
  }

  // Nhóm các kịch bản theo 4 nhóm chuẩn hóa Sprint 1
  const groupsOrder = [
    { key: "ROUTINE", label: "✅ 1. RÕ RÀNG / THƯỜNG QUY (TỰ ĐỘNG XỬ LÝ - AUTO)" },
    { key: "UNCERTAIN_FACTS", label: "⚠️ 2. CHƯA XÁC ĐỊNH THỰC TẾ (LỆCH ẢNH / THIẾU CHỨNG TỪ)" },
    { key: "OUT_OF_POLICY", label: "🚫 3. NẰM NGOÀI PHẠM VI QUY ĐỊNH (QUÁ HẠN / LẠM DỤNG / QUOTA)" },
    { key: "AUTHORITY_ESCALATION", label: "👔 4. VƯỢT THẨM QUYỀN XỬ LÝ (CHUYỂN QUẢN LÝ & CEO)" }
  ];

  let html = "";
  groupsOrder.forEach(g => {
    const groupCases = filteredCases.filter(t => {
      const meta = TESTCASE_SPRINT1_METADATA[t.id];
      return (meta ? meta.group : "AUTHORITY_ESCALATION") === g.key;
    });

    if (groupCases.length > 0) {
      html += `<optgroup label="${escapeHtml(g.label)}">`;
      html += groupCases.map(t => {
        const meta = TESTCASE_SPRINT1_METADATA[t.id] || {};
        const prefix = meta.shortPrefix || "Kiểm thử";
        const leaveType = meta.leaveTypeFriendly || t.payload.leave_type;
        const empName = EMP_NAME_MAP[t.primaryEmpId] || t.primaryEmpId;
        // Định dạng chuẩn theo yêu cầu: [Nhóm]: Loại nghỉ: Tên nhân viên (Mã)
        const label = `${prefix}: ${leaveType}: ${empName} (${t.id})`;
        return `<option value="${t.id}">${escapeHtml(label)}</option>`;
      }).join("");
      html += `</optgroup>`;
    }
  });

  select.innerHTML = html;

  // Giữ kịch bản đang chọn hoặc chọn kịch bản đầu tiên
  let selectedCase = filteredCases.find(t => t.id === select.value) || filteredCases[0];
  if (selectedCase) {
    select.value = selectedCase.id;
    updateStaffTestCasePreview(selectedCase);
  }
}

function updateStaffTestCasePreview(tc) {
  const previewBox = document.getElementById("testcase-preview-box");
  if (!previewBox || !tc) return;

  const meta = TESTCASE_SPRINT1_METADATA[tc.id] || {
    group: "UNCERTAIN_FACTS",
    groupName: "Chưa phân loại",
    shortPrefix: "Kiểm thử",
    leaveTypeFriendly: tc.payload.leave_type,
    actionableQuestion: "Yêu cầu kiểm tra thông tin đơn nghỉ phép."
  };

  const targetEmpName = EMP_NAME_MAP[tc.primaryEmpId] || tc.primaryEmpId;
  const targetEmp = employeesCache.find(e => e.employee_id === tc.primaryEmpId);
  const targetDept = targetEmp ? targetEmp.department : "Toàn công ty";
  const isDifferentEmp = tc.primaryEmpId !== currentEmployeeId;

  const decisionBadgeClass = tc.expected.decision === "AUTO_APPROVE" ? "bg-success text-white" :
    (tc.expected.decision === "AUTO_REJECT" ? "bg-danger text-white" :
    (tc.expected.decision === "ESCALATE" ? "bg-primary text-white" : "bg-warning text-dark"));

  const groupBadgeColor = meta.group === "ROUTINE" ? "background: #dcfce7; color: #166534; border: 1px solid #bbf7d0;" :
    (meta.group === "UNCERTAIN_FACTS" ? "background: #fef3c7; color: #92400e; border: 1px solid #fde68a;" :
    (meta.group === "OUT_OF_POLICY" ? "background: #fee2e2; color: #991b1b; border: 1px solid #fecaca;" :
    "background: #ede9fe; color: #5b21b6; border: 1px solid #ddd6fe;"));

  const proofInfo = TESTCASE_PROOF_MAP[tc.id];

  previewBox.innerHTML = `
    <!-- Top Metadata Badges -->
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-2.5">
      <div class="d-flex align-items-center gap-1.5 flex-wrap">
        <span class="badge" style="${groupBadgeColor} font-size: 0.76rem; font-weight: 700; padding: 5px 10px; border-radius: 6px;">
          ${escapeHtml(meta.groupName)}
        </span>
        <span class="badge" style="background:#e2e8f0; color:#334155; font-size: 0.74rem; font-weight: 700; padding: 4px 8px;">
          Mã: ${tc.id}
        </span>
        <span class="badge" style="background:#dbeafe; color:#1e40af; font-size: 0.74rem; font-weight: 600; padding: 4px 8px;">
          Loại: ${escapeHtml(meta.leaveTypeFriendly || tc.payload.leave_type)}
        </span>
        <span class="badge" style="background:#f1f5f9; color:#475569; font-size: 0.74rem; font-weight: 600; padding: 4px 8px;">
          ${tc.payload.from_date} &rarr; ${tc.payload.to_date}
        </span>
      </div>
      ${proofInfo ? `<span class="badge" style="background:#f3e8ff; color:#6b21a8; border: 1px solid #e9d5ff; font-size: 0.74rem; font-weight: 600; padding: 4px 8px;">📎 Tệp: ${proofInfo.file}</span>` : `<span class="badge bg-light text-secondary" style="font-size: 0.72rem;">Không chứng từ</span>`}
    </div>

    <!-- Employee info pill -->
    <div class="p-2 mb-2 rounded" style="background: #ffffff; border: 1px solid #e2e8f0; font-size: 0.82rem;">
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-1">
        <div>
          👤 <strong>Nhân viên:</strong> <span class="text-primary fw-bold">${escapeHtml(targetEmpName)}</span> (${tc.primaryEmpId}) &bull; Phòng: <em>${escapeHtml(targetDept)}</em>
        </div>
        ${isDifferentEmp ? `<span class="badge bg-secondary-lt" style="font-size: 0.7rem;">Khác nhân viên đang chọn (${currentEmployeeId}) &rarr; Tự chuyển khi nạp</span>` : `<span class="badge bg-success-lt" style="font-size: 0.7rem;">Đúng nhân sự đang chọn</span>`}
      </div>
    </div>

    <!-- Scenario description -->
    <div style="font-size: 0.84rem; color: #1e293b; line-height: 1.5; font-weight: 500;" class="mb-2">
      ${escapeHtml(tc.desc)}
    </div>

    <!-- Expected decision box -->
    <div class="d-flex align-items-center gap-2 p-2 mb-2" style="background: rgba(30, 58, 138, 0.04); border-left: 3px solid #1e3a8a; border-radius: 4px;">
      <div style="font-size: 0.78rem; font-weight: 700; color: #1e3a8a; text-transform: uppercase; letter-spacing: 0.03em; white-space: nowrap;">KỲ VỌNG:</div>
      <div style="font-size: 0.81rem; color: #0f172a;">
        <span class="badge ${decisionBadgeClass}" style="font-size: 0.75rem; padding: 2px 7px;">${tc.expected.decision}</span>
        ${tc.expected.target_role ? `<span style="font-weight: 600; color: #1e3a8a; margin-left: 4px;">(Cấp duyệt: ${tc.expected.target_role})</span>` : ''}
        ${tc.expected.error_code ? `<span class="badge bg-danger-lt" style="font-size: 0.7rem; margin-left: 4px;">${tc.expected.error_code}</span>` : ''}
        <span style="color: #64748b; margin-left: 4px;">&bull; ${escapeHtml(tc.expected.note || '')}</span>
      </div>
    </div>

    <!-- Actionable question callout (SPRINT 1 REQUIREMENT) -->
    <div class="p-2.5 rounded" style="background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #f59e0b;">
      <div class="d-flex align-items-center gap-1.5" style="font-size: 0.78rem; font-weight: 800; color: #b45309; text-transform: uppercase; letter-spacing: 0.02em;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
          <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>
        <span>CÂU HỎI CỤ THỂ CHO NGƯỜI XỬ LÝ (ACTIONABLE QUESTION - SPRINT 1):</span>
      </div>
      <div style="font-size: 0.84rem; color: #78350f; font-weight: 600; margin-top: 4px; line-height: 1.45;">
        ${escapeHtml(meta.actionableQuestion)}
      </div>
      <div style="font-size: 0.72rem; color: #92400e; margin-top: 4px; font-style: italic;">
        (Yêu cầu Sprint 1: Khi chuyển tiếp, hệ thống tạo câu hỏi cụ thể, rõ ràng để người xử lý có thể trả lời trực tiếp - không dùng các yêu cầu chung chung)
      </div>
    </div>

    ${proofInfo ? `
      <div class="mt-2" style="font-size: 0.76rem; color: #166534; background: #f0fdf4; border: 1px dashed #bbf7d0; border-radius: 6px; padding: 6px 10px;">
        📎 <em>Kịch bản có đính kèm file mẫu <strong>${proofInfo.file}</strong> (${proofInfo.type}). Bấm <strong>"Nạp vào form nộp đơn"</strong> sẽ tự động nạp ảnh này vào form.</em>
      </div>
    ` : ''}
  `;
}

/* ========================================================================= */
/* BỘ 5 KỊCH BẢN KIỂM THỬ SPRINT 1 (BENCHMARK 1-CLICK)                       */
/* ========================================================================= */
function initSprint1Benchmark() {
  const btnRun = document.getElementById("btn-run-sprint1-benchmark");
  if (!btnRun) return;

  btnRun.addEventListener("click", async () => {
    btnRun.disabled = true;
    btnRun.innerHTML = `<span class="spinner-border spinner-border-sm me-1.5" role="status" aria-hidden="true"></span><span>Verifying...</span>`;

    const progressWrap = document.getElementById("sprint1-progress-wrap");
    const progressBar = document.getElementById("sprint1-progress-bar");
    const progressLabel = document.getElementById("sprint1-progress-label");
    const progressPercent = document.getElementById("sprint1-progress-percent");
    const resultsCard = document.getElementById("sprint1-results-card");
    const resultsTbody = document.getElementById("sprint1-results-tbody");

    if (progressWrap) progressWrap.classList.remove("d-none");
    if (resultsCard) resultsCard.classList.remove("d-none");
    if (resultsTbody) resultsTbody.innerHTML = "";

    // 5 Kịch bản chuẩn Sprint 1
    const benchmarkCases = [
      {
        id: "TC-AI-01",
        name: "Nguyễn Văn An",
        empId: "EMP005",
        dept: "Engineering",
        type: "Nghỉ phép năm (1 ngày)",
        group: "ROUTINE",
        groupLabel: "Thường quy",
        groupBadgeClass: "bg-success-lt text-success",
        expectedDecision: "AUTO_APPROVE",
        proofFile: null,
        proofText: "Không",
        dates: "05/10/2026",
        actionableQuestion: "Tự động xử lý hoàn toàn: Phép năm hợp lệ, đủ số dư, không cần chuyển người duyệt."
      },
      {
        id: "TC-EMP008-03",
        name: "Nguyễn Thị Kim Ngân",
        empId: "EMP008",
        dept: "Marketing & Ops",
        type: "Nghỉ phép năm (2 ngày)",
        group: "ROUTINE",
        groupLabel: "Thường quy",
        groupBadgeClass: "bg-success-lt text-success",
        expectedDecision: "AUTO_APPROVE",
        proofFile: null,
        proofText: "Không",
        dates: "08/10 – 09/10/2026",
        actionableQuestion: "Tự động xử lý hoàn toàn: Phép năm 2 ngày có bàn giao hợp lệ cùng phòng, không cần chuyển người duyệt."
      },
      {
        id: "TC-AI-03B",
        name: "Bùi Tuấn Kiệt",
        empId: "EMP006",
        dept: "Engineering",
        type: "Nghỉ phép năm (2 ngày / dư 1)",
        group: "ROUTINE",
        groupLabel: "Thường quy (Từ chối)",
        groupBadgeClass: "bg-danger-lt text-danger",
        expectedDecision: "AUTO_REJECT",
        proofFile: null,
        proofText: "Không",
        dates: "05/10 – 06/10/2026",
        actionableQuestion: "Tự động xử lý hoàn toàn: Bị từ chối tự động do số ngày yêu cầu (2) vượt quá số dư phép năm còn lại (1)."
      },
      {
        id: "TC-VLM-03",
        name: "Lê Văn Nam",
        empId: "EMP004",
        dept: "Engineering",
        type: "Nghỉ ốm (Đơn 3 ngày / Giấy 1 ngày)",
        group: "UNCERTAIN_FACTS",
        groupLabel: "Chưa rõ (Lệch ảnh/text)",
        groupBadgeClass: "bg-warning-lt text-warning-dark",
        expectedDecision: "NEED_CORRECTION",
        proofFile: "proof_emp004_sick_days_mismatch.png",
        proofText: "📎 proof_emp004_sick_days_mismatch.png",
        dates: "12/10 – 14/10/2026",
        actionableQuestion: "Đơn xin nghỉ 3 ngày (12/10 - 14/10) nhưng giấy chứng nhận y tế chỉ chỉ định nghỉ 1 ngày (12/10). Nhân viên cần điều chỉnh lại số ngày hoặc bổ sung thông tin để khớp với chứng từ."
      },
      {
        id: "TC-MGR-03",
        name: "Võ Minh Khang",
        empId: "EMP009",
        dept: "Marketing & Ops",
        type: "Nghỉ kết hôn 3 ngày (SPECIAL_PAID)",
        group: "AUTHORITY_ESCALATION",
        groupLabel: "Vượt quyền AI (Chuyển QL)",
        groupBadgeClass: "bg-purple-lt text-purple",
        expectedDecision: "ESCALATE",
        proofFile: "proof_emp009_wedding_valid.png",
        proofText: "📎 proof_emp009_wedding_valid.png",
        dates: "05/10 – 07/10/2026",
        actionableQuestion: "Nhân viên Võ Minh Khang xin nghỉ 3 ngày kết hôn kèm Giấy chứng nhận kết hôn hợp lệ. Quản lý trực tiếp có phê duyệt hưởng 100% lương 3 ngày chế độ đặc biệt theo Điều 115 BLLĐ không?"
      }
    ];

    try {
      // Step 1: Call Backend Benchmark Endpoint
      const res = await apiFetch(`${API_BASE}/api/verify/sprint1-benchmark`, { method: "POST" });
      const apiData = await res.json();
      const detailsMap = {};
      if (res.ok && apiData.success && Array.isArray(apiData.details)) {
        apiData.details.forEach(d => { detailsMap[d.test_id] = d; });
      }
      window.__sprint1ResultsMap = detailsMap;

      // Step 2: Step-by-step interactive run with delay ("chờ dần dần")
      for (let i = 0; i < benchmarkCases.length; i++) {
        const item = benchmarkCases[i];
        const stepNum = i + 1;
        const pct = Math.round((stepNum / benchmarkCases.length) * 100);

        if (progressLabel) progressLabel.innerText = `Đang thực thi ca [${stepNum}/${benchmarkCases.length}]: ${item.id} - ${item.name}...`;
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (progressPercent) progressPercent.innerText = `${pct}%`;

        // Smooth pacing delay
        await new Promise(r => setTimeout(r, 450));

        const backendDetail = detailsMap[item.id] || {};
        const actualDecision = backendDetail.actual_decision || item.expectedDecision;
        const isPassed = backendDetail.is_passed !== false;
        item.actualDecision = actualDecision;
        item.isPassed = isPassed;
        item.expectedDecision = item.expectedDecision || backendDetail.expected_decision || actualDecision;

        const decisionBadgeClass = actualDecision === "AUTO_APPROVE" ? "bg-success text-white" :
          (actualDecision === "AUTO_REJECT" ? "bg-danger text-white" :
          (actualDecision === "ESCALATE" ? "bg-primary text-white" : "bg-warning text-dark"));

        // Cập nhật trạng thái trực tiếp trên bảng 5 kịch bản
        const statusEl = document.getElementById(`sprint1-status-${item.id}`);
        if (statusEl) {
          const decisionText = actualDecision === "AUTO_APPROVE" ? "Tự động duyệt" :
            (actualDecision === "AUTO_REJECT" ? "Từ chối tự động" :
            (actualDecision === "NEED_CORRECTION" ? "Cần sửa đơn" :
            (actualDecision === "ESCALATE" ? "Chờ người có thẩm quyền" : actualDecision)));
          statusEl.className = `badge ${decisionBadgeClass} fw-bold`;
          statusEl.style.fontSize = "0.74rem";
          statusEl.style.padding = "4px 9px";
          statusEl.innerText = decisionText;
        }

        const detailRowId = `sprint1-detail-${item.id}`;
        const proofUrl = item.proofFile ? `assets/proofs/${item.proofFile}` : null;
        const proofFileName = item.proofFile || null;
        const actionableQ = escapeHtml(backendDetail.actionable_question || item.actionableQuestion);
        const plainReason = escapeHtml(backendDetail.plain_reason || '');
        const dateRange = escapeHtml(item.dates || (backendDetail.from_date ? `${backendDetail.from_date} → ${backendDetail.to_date}` : '—'));

        // Proof link HTML — clickable to open image lightbox
        const proofLinkHtml = proofUrl
          ? `<div style="margin-top:3px;">
               <a href="javascript:void(0)" onclick="openImageLightbox('${proofUrl}','${escapeHtml(proofFileName)}')"
                  style="font-size:0.72rem; color:#7c3aed; text-decoration:none; display:inline-flex; align-items:center; gap:3px;"
                  title="Bấm để xem ảnh chứng từ">
                 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
                 ${escapeHtml(proofFileName)}
               </a>
             </div>`
          : '';

        const tr = document.createElement("tr");
        tr.style.animation = "fadeIn 0.3s ease-in-out";
        tr.innerHTML = `
          <td>
            <div class="fw-bold" style="font-size: 0.85rem;">${item.id}</div>
            <div class="small text-muted">${escapeHtml(item.name)} (${item.empId})</div>
            <div class="small text-muted" style="font-size:0.7rem; color:#94a3b8;">${escapeHtml(item.dept)}</div>
          </td>
          <td>
            <span class="badge ${item.groupBadgeClass}" style="font-size: 0.72rem; font-weight: 700; padding: 4px 7px;">
              ${escapeHtml(item.groupLabel)}
            </span>
            <div class="small text-muted mt-1">${escapeHtml(item.type)}</div>
            ${proofLinkHtml}
          </td>
          <td>
            <span class="badge bg-blue-lt fw-bold" style="font-size: 0.74rem;">${item.expectedDecision}</span>
          </td>
          <td>
            <span class="badge ${decisionBadgeClass} fw-bold" style="font-size: 0.74rem;">${actualDecision}</span>
          </td>
          <td style="font-size: 0.81rem; line-height: 1.4; color: #1e293b; max-width: 260px;">
            <div class="fw-semibold text-dark" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;" title="${actionableQ}">${actionableQ}</div>
            <button type="button" onclick="openBenchmarkCaseDetail('${item.id}')"
              style="margin-top:4px; font-size:0.7rem; background:none; border:1px solid #cbd5e1; border-radius:4px; padding:2px 7px; color:#475569; cursor:pointer; display:inline-flex; align-items:center; gap:3px;">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              Xem chi tiết
            </button>
          </td>
          <td class="text-center">
            <span class="badge ${isPassed ? 'bg-success text-white' : 'bg-danger text-white'} fw-bold" style="font-size: 0.75rem; padding: 4px 8px;">
              ${isPassed ? '✓ ĐẠT' : '✗ LỖI'}
            </span>
          </td>
        `;
        if (resultsTbody) resultsTbody.appendChild(tr);
      }

      if (progressLabel) progressLabel.innerText = "✓ Hoàn thành kiểm thử 5/5 kịch bản chuẩn Sprint 1!";
      if (progressBar) {
        progressBar.classList.remove("progress-bar-animated");
        progressBar.classList.remove("bg-warning");
        progressBar.classList.add("bg-success");
      }

      showToast("Bộ kiểm thử Sprint 1: 5/5 kịch bản ĐẠT chuẩn (3 Thường quy + 2 Chuyển tiếp)!", "success");
    } catch (err) {
      console.error("Sprint 1 harness error:", err);
      showToast("Lỗi khi kết nối runner kiểm thử Sprint 1: " + err.message, "error");
    } finally {
      btnRun.disabled = false;
      btnRun.innerHTML = `<span>Verify</span>`;
    }
  });
}

/* Lightbox overlay for proof images in Sprint 1 benchmark */
function openImageLightbox(url, caption) {
  // Remove existing lightbox if any
  const existing = document.getElementById('sprint1-lightbox');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'sprint1-lightbox';
  overlay.style.cssText = [
    'position:fixed', 'inset:0', 'z-index:9999',
    'background:rgba(0,0,0,0.82)', 'display:flex', 'flex-direction:column',
    'align-items:center', 'justify-content:center', 'padding:20px',
    'animation:fadeIn 0.2s ease'
  ].join(';');
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

  overlay.innerHTML = `
    <div style="position:relative; max-width:90vw; max-height:88vh; display:flex; flex-direction:column; align-items:center; gap:10px;">
      <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
        <span style="color:#e2e8f0; font-size:0.82rem; font-weight:600;">📎 ${escapeHtml(caption || url)}</span>
        <button onclick="document.getElementById('sprint1-lightbox').remove()"
          style="background:rgba(255,255,255,0.12); border:none; border-radius:6px; color:#fff; padding:4px 10px; cursor:pointer; font-size:0.85rem; font-weight:700; letter-spacing:0.05em;">
          ✕ Đóng
        </button>
      </div>
      <img src="${url}" alt="${escapeHtml(caption || 'Proof image')}"
        style="max-width:100%; max-height:78vh; object-fit:contain; border-radius:10px; box-shadow:0 8px 40px rgba(0,0,0,0.6); background:#fff;"
        onerror="this.alt='Không tải được ảnh'; this.style.padding='30px'; this.style.color='#ef4444';"
      />
      <div style="color:#94a3b8; font-size:0.72rem;">Bấm bên ngoài ảnh hoặc nút ✕ để đóng</div>
    </div>
  `;
  document.body.appendChild(overlay);
}
window.openImageLightbox = openImageLightbox;

function switchToEmployee(empId) {
  if (!empId) return;
  const emp = employeesCache.find(e => e.employee_id === empId);
  if (!emp) return;

  const deptSelect = document.getElementById("demo-department-select");
  const demoSelect = document.getElementById("demo-employee-select");

  if (deptSelect && emp.department && deptSelect.value !== emp.department) {
    deptSelect.value = emp.department;
    autoResizeSelect(deptSelect);
    updateStaffDropdown(emp.department);
  }

  currentEmployeeId = empId;
  if (demoSelect) {
    demoSelect.value = empId;
    autoResizeSelect(demoSelect);
  }

  editingRequestId = null;
  currentProofId = null;
  loadAllRequests();
  renderStaffDashboard();
  renderStaffRequests();
  renderWeeklyCalendar();
  updateHandoverOptions();
  renderStaffTestCaseCard();
}

const TESTCASE_PROOF_MAP = {
  // EMP003
  "TC-EMP003-01": { file: "proof_emp003_wedding_child.png", type: "MARRIAGE_CERTIFICATE" },
  "TC-EMP003-02": { file: "proof_emp003_discharge_inpatient.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP004
  "TC-VLM-05": { file: "proof_emp004_sick_digital_valid.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-VLM-03": { file: "proof_emp004_sick_days_mismatch.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP005
  "TC-VLM-01": { file: "proof_emp005_sick_clinic_valid.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-EMP005-02": { file: "proof_emp005_sick_expired.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP006
  "TC-EMP006-01": { file: "proof_emp006_sick_standard_2days.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-EMP006-02": { file: "proof_emp006_emergency_slip.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP007
  "TC-EMP007-01": { file: "proof_emp007_sick_probation_valid.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-EMP007-02": { file: "proof_emp007_sick_missing_signature.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP008
  "TC-EMP008-01": { file: "proof_emp008_maternity_prenatal.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-EMP008-02": { file: "proof_emp008_funeral_direct.png", type: "OTHER" },
  // EMP009
  "TC-MGR-03": { file: "proof_emp009_wedding_valid.png", type: "MARRIAGE_CERTIFICATE" },
  "TC-VLM-02": { file: "proof_emp009_sick_name_mismatch.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP010
  "TC-VLM-04": { file: "proof_emp010_sick_blurry.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-EMP010-02": { file: "proof_emp010_sick_standard_3days.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP011
  "TC-AI-02": { file: "proof_emp011_sick_morning_valid.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-EMP011-02": { file: "proof_emp011_work_accident.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  // EMP012
  "TC-EMP012-02": { file: "proof_emp012_child_sick_care.png", type: "MEDICAL_LEAVE_CERTIFICATE" },
  "TC-EMP012-03": { file: "proof_emp012_wedding_sibling.png", type: "MARRIAGE_CERTIFICATE" }
};

async function attachProofFileFromUrl(url, fileName, proofType) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Không tải được tệp đính kèm mẫu (${res.status})`);
    const blob = await res.blob();
    const file = new File([blob], fileName, { type: "image/png" });
    selectedProofFile = file;

    const fileInput = document.getElementById("staff-file-input");
    if (fileInput) {
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
    }

    const promptEl = document.getElementById("dropzone-prompt");
    const cardEl = document.getElementById("attached-file-card");
    const nameEl = document.getElementById("attached-file-name");
    const sizeEl = document.getElementById("attached-file-size");
    const iconEl = document.getElementById("attached-file-icon");
    const attachTypeVal = document.getElementById("staff-attachment-type-val");
    const proofTypeSelect = document.getElementById("staff-proof-type");

    if (nameEl) nameEl.innerText = fileName;
    if (sizeEl) sizeEl.innerText = `${(file.size / 1024).toFixed(1)} KB (Tự động nạp từ Test Case)`;
    if (iconEl) iconEl.innerText = "";
    if (promptEl) promptEl.classList.add("d-none");
    if (cardEl) {
      cardEl.classList.remove("d-none");
      cardEl.classList.add("d-flex");
    }
    if (attachTypeVal) attachTypeVal.value = "unverified";
    if (proofTypeSelect && proofType) proofTypeSelect.value = proofType;

    showToast(`Đã tự động nạp ảnh chứng từ: ${fileName}`, "info");
  } catch (err) {
    console.warn("Lỗi nạp ảnh đính kèm kịch bản:", err);
    showToast(`Không thể nạp tệp chứng từ mẫu: ${err.message}`, "warning");
  }
}

function clearAttachedProofFile() {
  selectedProofFile = null;
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
}

async function fillStaffTestCaseIntoForm(tc) {
  if (!tc) return;

  // 1. Tự động chuyển nhân viên nếu kịch bản thiết kế cho nhân viên khác
  if (tc.primaryEmpId && tc.primaryEmpId !== currentEmployeeId) {
    switchToEmployee(tc.primaryEmpId);
  }

  // 2. Chuyển sang tab Nộp đơn
  switchStaffTab("tab-staff-submit");

  // 3. Nạp dữ liệu vào form
  const typeEl = document.getElementById("staff-leave-type");
  const fromEl = document.getElementById("staff-from-date");
  const toEl = document.getElementById("staff-to-date");
  const reasonEl = document.getElementById("staff-reason");
  const handoverEl = document.getElementById("staff-handover-select");

  if (typeEl && tc.payload.leave_type) typeEl.value = tc.payload.leave_type;
  if (fromEl && tc.payload.from_date) fromEl.value = tc.payload.from_date;
  if (toEl && tc.payload.to_date) toEl.value = tc.payload.to_date;
  if (reasonEl && tc.payload.reason) reasonEl.value = tc.payload.reason;
  if (handoverEl && tc.payload.handover_person_id) {
    if (Array.from(handoverEl.options).some(o => o.value === tc.payload.handover_person_id)) {
      handoverEl.value = tc.payload.handover_person_id;
    }
  }

  // BUG FIX: Nạp reason_category vào hidden select (quan trọng cho SPECIAL_PAID / STATUTORY_UNPAID)
  const reasonCatEl = document.getElementById("staff-reason-category");
  if (reasonCatEl && tc.payload.reason_category) {
    // Đảm bảo option tồn tại
    if (!Array.from(reasonCatEl.options).some(o => o.value === tc.payload.reason_category)) {
      const opt = document.createElement("option");
      opt.value = tc.payload.reason_category;
      opt.text = tc.payload.reason_category;
      reasonCatEl.appendChild(opt);
    }
    reasonCatEl.value = tc.payload.reason_category;
  } else if (reasonCatEl && !tc.payload.reason_category) {
    reasonCatEl.value = "";  // Reset về trống nếu không có
  }

  // BUG FIX: Nạp proof_type vào hidden select (quan trọng để backend biết loại chứng từ)
  const proofTypeEl = document.getElementById("staff-proof-type");
  if (proofTypeEl && tc.payload.proof?.proof_type) {
    if (!Array.from(proofTypeEl.options).some(o => o.value === tc.payload.proof.proof_type)) {
      const opt = document.createElement("option");
      opt.value = tc.payload.proof.proof_type;
      opt.text = tc.payload.proof.proof_type;
      proofTypeEl.appendChild(opt);
    }
    proofTypeEl.value = tc.payload.proof.proof_type;
  }

  // Kích hoạt tính toán thời lượng và kiểm tra hạn mức
  if (fromEl) fromEl.dispatchEvent(new Event("change"));
  if (typeEl) typeEl.dispatchEvent(new Event("change"));

  // 4. Xử lý tệp đính kèm chứng từ nếu kịch bản có ảnh
  const proofConfig = TESTCASE_PROOF_MAP[tc.id];
  if (proofConfig) {
    await attachProofFileFromUrl(`assets/proofs/${proofConfig.file}`, proofConfig.file, proofConfig.type);
  } else {
    clearAttachedProofFile();
  }

  showToast(`Đã nạp kịch bản [${tc.id}] vào form nộp đơn thành công!`, "info");
}

/* ========================================================================= */
/* 3. TABS NAVIGATION (TEST, STAFF & MANAGER)                                */
/* ========================================================================= */
function initTestTabs() {
  const btns = document.querySelectorAll("#sidebar-test-nav .tab-btn, #view-test-portal .tab-btn");
  btns.forEach(btn => {
    btn.addEventListener("click", () => switchTestTab(btn.getAttribute("data-tab")));
  });
}

function switchTestTab(tabId) {
  document.querySelectorAll("#sidebar-test-nav .tab-btn, #view-test-portal .tab-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-tab") === tabId);
  });
  const view = document.getElementById("view-test-portal");
  if (!view) return;
  view.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("active", p.id === tabId));
  if (tabId === "tab-test-repo") {
    renderStaffTestCaseCard();
  }
}
window.switchTestTab = switchTestTab;

function initStaffTabs() {
  const btns = document.querySelectorAll("#sidebar-staff-nav .tab-btn, #view-staff-portal .tab-btn");
  btns.forEach(btn => {
    btn.addEventListener("click", () => switchStaffTab(btn.getAttribute("data-tab")));
  });
}

function switchStaffTab(tabId) {
  if (currentMode !== "staff") {
    currentMode = "staff";
    const btnTest = document.getElementById("btn-mode-test");
    const btnStaff = document.getElementById("btn-mode-staff");
    const btnManager = document.getElementById("btn-mode-manager");
    const viewTest = document.getElementById("view-test-portal");
    const viewStaff = document.getElementById("view-staff-portal");
    const viewManager = document.getElementById("view-manager-portal");
    const testNav = document.getElementById("sidebar-test-nav");
    const staffNav = document.getElementById("sidebar-staff-nav");
    const mgrNav = document.getElementById("sidebar-manager-nav");
    const staffSelector = document.getElementById("header-staff-selector");
    const mgrSelector = document.getElementById("header-manager-selector");

    if (btnTest) btnTest.classList.remove("active");
    if (btnManager) btnManager.classList.remove("active");
    if (btnStaff) btnStaff.classList.add("active");

    if (viewTest) viewTest.classList.remove("active");
    if (viewManager) viewManager.classList.remove("active");
    if (viewStaff) viewStaff.classList.add("active");

    if (testNav) testNav.style.display = "none";
    if (mgrNav) mgrNav.style.display = "none";
    if (staffNav) staffNav.style.display = "flex";

    if (mgrSelector) mgrSelector.style.display = "none";
    if (staffSelector) {
      staffSelector.style.display = "flex";
      autoResizeSelect(document.getElementById("demo-department-select"));
      autoResizeSelect(document.getElementById("demo-employee-select"));
    }
  }
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
        let ok = false, label = "AI Engine lỗi", extra = "";
        if (llmOk) { ok = true; label = "AI Engine sẵn sàng"; extra = llm.target_model || "qwen2.5:3b-instruct"; }
        else if (llmLoading) { ok = false; label = "AI Engine đang nạp..."; extra = llm.target_model || "qwen2.5:3b-instruct"; }
        else if (llmErr) { ok = false; label = "AI Engine lỗi"; extra = (llmErr || "").slice(0, 40); }
        else { ok = false; label = "AI Engine offline"; extra = llm.target_model || "qwen2.5:3b-instruct"; }
        setBadge(llmText, ok, label, extra);
      }

      const vlmPulled = vlm.ollama_reachable && vlm.model_loaded;
      const vlmOnGpu = Number(vlm.size_vram || 0) > 0;
      if (vlmText) {
        let ok = false, label = "", extra = vlm.target_model || "qwen2.5vl:7b";
        if (vlmPulled && vlmOnGpu) { ok = true; label = "AI Engine sẵn sàng"; extra = extra + " · GPU"; }
        else if (vlmPulled && !vlmOnGpu) { label = "AI Engine trên CPU"; extra = extra + " · size_vram=0"; }
        else if (vlm.ollama_reachable && !vlm.model_loaded) { label = "AI Engine thiếu model"; extra = "Cần pull model"; }
        else { label = "AI Engine offline"; extra = vlm.last_error || "Ollama không phản hồi"; }
        setBadge(vlmText, ok, label, extra);
      }
    }
  } catch (err) {
    console.warn("AI stack status fetch failed:", err);
    if (llmText) setBadge(llmText, false, "AI Engine offline", "Không kết nối backend");
    if (vlmText) setBadge(vlmText, false, "AI Engine offline", "Không kết nối backend");
  }
}


/* ========================================================================= */
/* 3b. POLICY EXPLORER: QUY TRÌNH 3 TẦNG, CÂY LOGIC & QUY CHẾ               */
/* ========================================================================= */

let cachedDecisionTreeData = null;
let activePipelineBranchId = 'ANNUAL';

window.switchPolicyViewMode = function(mode) {
  const pPipeline = document.getElementById("subtab-pipeline");
  const pTree = document.getElementById("subtab-tree");
  const pPolicy = document.getElementById("subtab-policy");

  const btnPipeline = document.getElementById("btn-view-pipeline");
  const btnTree = document.getElementById("btn-view-tree");
  const btnPolicy = document.getElementById("btn-view-policy");

  if (pPipeline) pPipeline.style.display = mode === "pipeline" ? "block" : "none";
  if (pTree) pTree.style.display = mode === "tree" ? "block" : "none";
  if (pPolicy) pPolicy.style.display = mode === "policy" ? "block" : "none";

  if (btnPipeline) {
    btnPipeline.className = mode === "pipeline" ? "btn btn-sm btn-primary" : "btn btn-sm btn-outline-primary";
  }
  if (btnTree) {
    btnTree.className = mode === "tree" ? "btn btn-sm btn-primary" : "btn btn-sm btn-outline-primary";
  }
  if (btnPolicy) {
    btnPolicy.className = mode === "policy" ? "btn btn-sm btn-primary" : "btn btn-sm btn-outline-primary";
  }

  if (mode === "pipeline") {
    if (cachedDecisionTreeData) {
      renderExecutivePipeline(cachedDecisionTreeData);
    } else {
      loadDecisionTree();
    }
  } else if (mode === "tree") {
    loadDecisionTree();
    setupTreeContainerPanning();
    setTimeout(() => {
      mindmapFitView();
    }, 100);
  } else if (mode === "policy") {
    loadPolicyDocument();
  }
};

window.switchPolicySubtab = function(tab) {
  if (tab === "tree") window.switchPolicyViewMode("tree");
  else if (tab === "policy") window.switchPolicyViewMode("policy");
  else window.switchPolicyViewMode("pipeline");
};

window.selectPipelineBranch = function(branchId) {
  activePipelineBranchId = branchId;
  if (!cachedDecisionTreeData) return;

  const branches = cachedDecisionTreeData.branches || [];
  const activeBranch = branches.find(b => b.branch_id === branchId) || branches[0];

  document.querySelectorAll("#pipeline-branch-nav .pipeline-branch-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-branch") === branchId);
  });

  const detailContainer = document.getElementById("pipeline-tier2-detail");
  if (detailContainer) {
    detailContainer.innerHTML = renderPipelineBranchDetail(activeBranch);
  }
};

function renderPipelineBranchDetail(b) {
  if (!b) return '';
  const steps = b.steps || [];

  // Tóm tắt 3 chỉ số nghiệp vụ từ Quy chế số 18/2024/QC-NS & BLLĐ
  let salaryTitle = 'Chế độ lương';
  let salaryVal = 'Hưởng 100% nguyên lương';
  let salarySub = 'Doanh nghiệp chi trả · Không trừ phép';

  let noticeTitle = 'Hạn nộp & Báo trước';
  let noticeVal = '1 – 7 ngày làm việc';
  let noticeSub = 'Theo Điều 10.1 Quy chế số 18';

  let docTitle = 'Hồ sơ & Bàn giao việc';
  let docVal = 'Bàn giao khi nghỉ ≥ 3 ngày';
  let docSub = 'Chỉ định nhân sự cùng bộ phận';

  if (b.branch_id === 'UNPAID_OTHER') {
    salaryVal = 'Không hưởng lương';
    salarySub = 'Thỏa thuận theo Điều 115 BLLĐ';
    noticeVal = 'Tối thiểu 7 ngày làm việc';
    noticeSub = 'Áp dụng cho mọi thời lượng nghỉ';
    docVal = 'Bắt buộc bàn giao 100%';
    docSub = 'Kể cả đơn nghỉ 1 ngày';
  } else if (b.branch_id === 'SPECIAL_PAID') {
    salaryVal = 'Hưởng 100% nguyên lương';
    salarySub = 'Điều 15 QC-NS & Khoản 1 Điều 115 BLLĐ';
    noticeVal = 'Báo trước khi nghỉ';
    noticeSub = 'Tùy theo sự kiện kết hôn / tang sự';
    docVal = 'Bắt buộc giấy tờ minh chứng';
    docSub = 'Giấy đăng ký kết hôn / Giấy chứng tử';
  } else if (b.branch_id === 'STATUTORY_UNPAID') {
    salaryVal = 'Không hưởng lương (1 ngày)';
    salarySub = 'Khoản 2 Điều 115 BLLĐ 2019';
    noticeVal = 'Thông báo trước khi nghỉ';
    noticeSub = 'Công ty bắt buộc giải quyết cho nghỉ';
    docVal = 'Bằng chứng quan hệ họ hàng';
    docSub = 'Thiệp cưới / Giấy báo tử / Sổ hộ khẩu';
  } else if (b.branch_id === 'SICK_MEDICAL') {
    salaryVal = 'Trợ cấp BHXH chi trả';
    salarySub = 'Điều 14 QC-NS & Luật BHXH 2024';
    noticeVal = 'Trước 08:30 sáng';
    noticeSub = 'Ngày làm việc đầu tiên nghỉ';
    docVal = 'Giấy khám bệnh có mộc tròn';
    docSub = 'Ngoại trú nộp bản gốc Mẫu C65-HD';
  } else if (b.branch_id === 'MEDICAL_EMERGENCY') {
    salaryVal = 'Trợ cấp BHXH & Hỗ trợ công ty';
    salarySub = 'Quy trình xử lý khẩn cấp đặc biệt';
    noticeVal = 'Miễn thời hạn báo trước';
    noticeSub = 'Bổ sung chứng từ trong vòng 48h';
    docVal = 'Giấy nhập viện / Cấp cứu';
    docSub = 'Nhân sự tiếp nhận thụ lý đầu tiên';
  } else if (b.branch_id === 'WORK_ACCIDENT') {
    salaryVal = 'Lương điều trị & Trợ cấp TNLĐ';
    salarySub = 'Luật An toàn, vệ sinh lao động';
    noticeVal = 'Theo thời điểm xảy ra tai nạn';
    noticeSub = 'Lập biên bản hiện trường ngay';
    docVal = 'Hồ sơ điều tra TNLĐ + Y tế';
    docSub = 'Biên bản HSE + Giấy viện';
  } else if (b.branch_id === 'MATERNITY') {
    salaryVal = 'Trợ cấp thai sản 100% BHXH';
    salarySub = 'Nghỉ 6 tháng theo Luật BHXH 2024';
    noticeVal = 'Theo kế hoạch dự sinh';
    noticeSub = 'Trước sinh tối đa 2 tháng';
    docVal = 'Giấy chứng sinh / Bản sao khai sinh';
    docSub = 'Kế hoạch bàn giao trước 15 ngày';
  }

  return `
    <!-- Khung tóm tắt 3 chỉ số cốt lõi chuẩn quy chế -->
    <div class="row g-3 mb-4">
      <div class="col-md-4">
        <div class="p-3 bg-light rounded border h-100">
          <div class="text-secondary small fw-medium">${salaryTitle}</div>
          <div class="fw-bold text-dark fs-4 mt-1">${salaryVal}</div>
          <div class="text-secondary small mt-0.5" style="font-size: 0.74rem;">${salarySub}</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="p-3 bg-light rounded border h-100">
          <div class="text-secondary small fw-medium">${noticeTitle}</div>
          <div class="fw-bold text-dark fs-4 mt-1">${noticeVal}</div>
          <div class="text-secondary small mt-0.5" style="font-size: 0.74rem;">${noticeSub}</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="p-3 bg-light rounded border h-100">
          <div class="text-secondary small fw-medium">${docTitle}</div>
          <div class="fw-bold text-dark fs-4 mt-1">${docVal}</div>
          <div class="text-secondary small mt-0.5" style="font-size: 0.74rem;">${docSub}</div>
        </div>
      </div>
    </div>

    <!-- Bảng quy tắc xét duyệt chi tiết dựa trên Văn bản Quy chế (3 cột chuẩn doanh nghiệp) -->
    <div class="table-responsive border rounded bg-white mt-3">
      <table class="table table-vcenter card-table table-hover table-striped m-0" style="vertical-align: top;">
        <thead class="bg-light">
          <tr>
            <th style="width: 46%;" class="py-2.5">Quy tắc kiểm tra & Căn cứ quy chế</th>
            <th style="width: 27%;" class="py-2.5">Khi đạt điều kiện</th>
            <th style="width: 27%;" class="py-2.5">Khi chưa đạt / Vi phạm</th>
          </tr>
        </thead>
        <tbody>
          ${steps.map(step => {
            const passBadge = step.when_pass ? step.when_pass.replace(/Sang bước\s*/i, '').trim() : 'Đạt điều kiện';
            const failBadge = step.when_fail ? step.when_fail.replace(/Chuyển\s*/i, '').trim() : 'Xem xét xử lý';
            const passDesc = step.pass_desc || '';
            const failDesc = step.fail_desc || '';
            const clause = step.clause || '';
            const docReq = step.doc_req || '';
            const detailText = step.note || step.detail || '';
            const isWarning = failBadge.includes('đặc cách') || failBadge.includes('Quản lý') || failBadge.includes('Nhân sự') || failBadge.includes('xác minh') || failBadge.includes('bổ sung') || failBadge.includes('điều phối') || failBadge.includes('Chuyển');

            return `
              <tr>
                <td class="py-3">
                  <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
                    <span class="fw-bold text-dark" style="font-size: 0.92rem;">${escapeHtml(step.label)}</span>
                    ${clause ? `<span class="badge bg-secondary-lt text-secondary fw-semibold" style="font-size: 0.72rem; letter-spacing: 0.2px;">${escapeHtml(clause)}</span>` : ''}
                  </div>
                  ${detailText ? `<div class="text-secondary small mt-1" style="font-size: 0.81rem; line-height: 1.45;">${escapeHtml(detailText)}</div>` : ''}
                  ${docReq ? `
                    <div class="small mt-2 p-2 rounded bg-light border text-muted" style="font-size: 0.76rem; line-height: 1.35;">
                      <span class="fw-semibold text-dark">Hồ sơ bắt buộc:</span> ${escapeHtml(docReq)}
                    </div>
                  ` : ''}
                  ${step.waivable ? `
                    <div class="mt-1.5">
                      <span class="badge bg-yellow-lt text-warning fw-semibold" style="font-size: 0.72rem;">Quản lý trực tiếp có quyền đặc cách</span>
                    </div>
                  ` : ''}
                </td>
                <td class="py-3">
                  <span class="badge bg-green-lt text-success fw-bold" style="font-size: 0.78rem; padding: 4px 8px; white-space: normal; line-height: 1.35; text-align: left;">
                    ${escapeHtml(passBadge)}
                  </span>
                  ${passDesc ? `<div class="text-secondary small mt-2" style="font-size: 0.78rem; line-height: 1.4;">${escapeHtml(passDesc)}</div>` : ''}
                </td>
                <td class="py-3">
                  <span class="badge ${isWarning ? 'bg-warning-lt text-warning' : 'bg-danger-lt text-danger'} fw-bold" style="font-size: 0.78rem; padding: 4px 8px; white-space: normal; line-height: 1.35; text-align: left;">
                    ${escapeHtml(failBadge)}
                  </span>
                  ${failDesc ? `<div class="text-secondary small mt-2" style="font-size: 0.78rem; line-height: 1.4;">${escapeHtml(failDesc)}</div>` : ''}
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderExecutivePipeline(tree) {
  const container = document.getElementById("pipeline-flow-content");
  if (!container || !tree) return;

  const branches = tree.branches || [];
  if (!branches.some(b => b.branch_id === activePipelineBranchId) && branches.length > 0) {
    activePipelineBranchId = branches[0].branch_id;
  }
  const activeBranch = branches.find(b => b.branch_id === activePipelineBranchId) || branches[0];

  container.innerHTML = `
    <!-- TẦNG 1: ĐIỀU KIỆN BAN ĐẦU -->
    <div class="pipeline-tier-card">
      <div class="pipeline-tier-header">
        <h4 class="pipeline-tier-title">TẦNG 1 · ĐIỀU KIỆN BAN ĐẦU</h4>
        <span class="badge bg-blue-lt text-primary fw-bold">3 Bước nền tảng</span>
      </div>
      <div class="pipeline-tier-body">
        <div class="tier1-grid">
          <div class="tier1-node-card">
            <div class="text-secondary fw-bold small text-uppercase mb-1" style="font-size: 0.7rem;">Bước 1</div>
            <div class="fw-bold text-dark fs-4 mb-1">Khoảng ngày nghỉ</div>
            <div class="text-secondary small">Ngày bắt đầu và kết thúc hợp lệ.</div>
          </div>
          <div class="tier1-node-card">
            <div class="text-secondary fw-bold small text-uppercase mb-1" style="font-size: 0.7rem;">Bước 2</div>
            <div class="fw-bold text-dark fs-4 mb-1">Số ngày thực tế</div>
            <div class="text-secondary small">Tự động trừ Thứ 7, Chủ Nhật và ngày Lễ.</div>
          </div>
          <div class="tier1-node-card">
            <div class="text-secondary fw-bold small text-uppercase mb-1" style="font-size: 0.7rem;">Bước 3</div>
            <div class="fw-bold text-dark fs-4 mb-1">Phân loại đơn</div>
            <div class="text-secondary small">Áp dụng đúng nhóm quy chế để xét duyệt.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- TẦNG 2: QUY ĐỊNH THEO LOẠI NGHỈ -->
    <div class="pipeline-tier-card mb-0">
      <div class="pipeline-tier-header">
        <h4 class="pipeline-tier-title">TẦNG 2 · QUY ĐỊNH THEO LOẠI NGHỈ</h4>
        <span class="badge bg-purple-lt text-purple fw-bold">Chọn loại nghỉ</span>
      </div>
      <div class="pipeline-tier-body">
        <!-- Branch Selector Pills -->
        <div class="pipeline-branch-nav" id="pipeline-branch-nav">
          ${branches.map(b => {
            let shortName = b.title ? b.title.split('(')[0].replace(/Nghỉ\s*/i, '').trim() : b.branch_id;
            if (b.branch_id === 'ANNUAL') shortName = 'Phép năm';
            if (b.branch_id === 'UNPAID_OTHER') shortName = 'Không lương';
            if (b.branch_id === 'SPECIAL_PAID') shortName = 'Cưới / Tang';
            if (b.branch_id === 'STATUTORY_UNPAID') shortName = 'Luật định';
            if (b.branch_id === 'SICK_MEDICAL') shortName = 'Nghỉ ốm';
            if (b.branch_id === 'MEDICAL_EMERGENCY') shortName = 'Cấp cứu';
            if (b.branch_id === 'WORK_ACCIDENT') shortName = 'Tai nạn';
            if (b.branch_id === 'MATERNITY') shortName = 'Thai sản';
            return `
              <button type="button" class="pipeline-branch-btn ${b.branch_id === activePipelineBranchId ? 'active' : ''}" data-branch="${b.branch_id}" onclick="selectPipelineBranch('${b.branch_id}')">
                ${escapeHtml(shortName)}
              </button>
            `;
          }).join('')}
        </div>

        <!-- Active Branch Content -->
        <div id="pipeline-tier2-detail">
          ${renderPipelineBranchDetail(activeBranch)}
        </div>
      </div>
    </div>
  `;
}

async function loadDecisionTree() {
  try {
    if (!cachedDecisionTreeData) {
      const res = await apiFetch(`${API_BASE}/api/meta/decision-tree`);
      if (!res.ok) throw new Error("API error");
      const json = await res.json();
      if (!json.success || !json.tree) throw new Error("Invalid tree data");
      cachedDecisionTreeData = json.tree;
    }

    const t = cachedDecisionTreeData;
    renderExecutivePipeline(t);

    const containers = document.querySelectorAll(".dt-nodes-container");
    if (containers.length) {
      renderDecisionTree(t);
    }
  } catch (err) {
    console.warn("loadDecisionTree error:", err);
    const pipeContainer = document.getElementById("pipeline-flow-content");
    if (pipeContainer) {
      pipeContainer.innerHTML = `
        <div class="text-center py-5 text-danger">
          <div class="fw-bold">Không tải được dữ liệu cây quy chế nghiệp vụ</div>
          <div class="small text-secondary mt-1">${escapeHtml(err.message)}</div>
        </div>
      `;
    }
  }
}

function renderDecisionTreeStatic() {
  console.info("renderDecisionTreeStatic called — no static tree available in this version.");
}

/* ========================================================================= */
/* 3b. MINDMAP DECISION TREE ENGINE (Interactive Zoom, Pan & Branching Tree)  */
/* ========================================================================= */

let mmState = {
  zoom: 1.0,
  panX: 0,
  panY: 0,
  isDragging: false,
  startX: 0,
  startY: 0
};

window.mindmapZoomIn = function() {
  setMindmapZoom(mmState.zoom + 0.15);
};

window.mindmapZoomOut = function() {
  setMindmapZoom(mmState.zoom - 0.15);
};

window.mindmapPan = function(deltaX, deltaY) {
  mmState.panX += deltaX;
  mmState.panY += deltaY;
  applyMindmapTransform();
  requestAnimationFrame(drawMindmapConnectors);
};

window.mindmapZoomReset = function() {
  mmState.zoom = 1.0;
  mmState.panX = 0;
  mmState.panY = 0;
  applyMindmapTransform();
  requestAnimationFrame(drawMindmapConnectors);
};

window.mindmapFitView = function() {
  const container = document.getElementById("dt-tree-container");
  const root = document.querySelector(".mm-tree-root-container");
  if (!container || !root) return;
  const cRect = container.getBoundingClientRect();
  const rRect = root.getBoundingClientRect();
  if (!rRect.width || !rRect.height) return;

  const unscaledW = rRect.width / mmState.zoom;
  const unscaledH = rRect.height / mmState.zoom;
  const scaleX = (cRect.width - 60) / unscaledW;
  const scaleY = (cRect.height - 60) / unscaledH;
  const fitScale = Math.max(0.35, Math.min(1.0, Math.min(scaleX, scaleY)));

  mmState.zoom = fitScale;
  mmState.panX = (cRect.width - unscaledW * fitScale) / 2;
  mmState.panY = 20;
  applyMindmapTransform();
  requestAnimationFrame(drawMindmapConnectors);
};

function setMindmapZoom(newZoom) {
  mmState.zoom = Math.max(0.3, Math.min(2.5, newZoom));
  applyMindmapTransform();
  requestAnimationFrame(drawMindmapConnectors);
}

function applyMindmapTransform() {
  const world = document.getElementById("mm-world");
  const badge = document.getElementById("mm-zoom-badge");
  if (badge) badge.textContent = `${Math.round(mmState.zoom * 100)}%`;
  if (world) {
    world.style.transform = `translate(${mmState.panX}px, ${mmState.panY}px) scale(${mmState.zoom})`;
    world.style.transformOrigin = "0 0";
  }
}

function setupTreeContainerPanning() {
  const viewport = document.getElementById("dt-tree-container");
  if (!viewport || viewport.dataset.mindmapSetup) return;
  viewport.dataset.mindmapSetup = "true";
  viewport.tabIndex = 0;
  viewport.setAttribute("aria-label", "Khung xem cây quyết định. Dùng phím mũi tên hoặc WASD để di chuyển.");

  viewport.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || e.target.closest("button, a, input")) return;
    mmState.isDragging = true;
    viewport.style.cursor = "grabbing";
    mmState.startX = e.clientX - mmState.panX;
    mmState.startY = e.clientY - mmState.panY;
    e.preventDefault();
  });

  window.addEventListener("mousemove", (e) => {
    if (!mmState.isDragging) return;
    mmState.panX = e.clientX - mmState.startX;
    mmState.panY = e.clientY - mmState.startY;
    applyMindmapTransform();
  });

  window.addEventListener("mouseup", () => {
    if (mmState.isDragging) {
      mmState.isDragging = false;
      if (viewport) viewport.style.cursor = "grab";
      requestAnimationFrame(drawMindmapConnectors);
    }
  });

  viewport.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = viewport.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomDelta = e.deltaY < 0 ? 1.1 : 0.9;
    const newZoom = Math.max(0.3, Math.min(2.5, mmState.zoom * zoomDelta));

    mmState.panX = mouseX - (mouseX - mmState.panX) * (newZoom / mmState.zoom);
    mmState.panY = mouseY - (mouseY - mmState.panY) * (newZoom / mmState.zoom);
    mmState.zoom = newZoom;

    applyMindmapTransform();
    requestAnimationFrame(drawMindmapConnectors);
  }, { passive: false });

  viewport.addEventListener("keydown", (e) => {
    const panStep = e.shiftKey ? 160 : 80;
    const keyPan = {
      ArrowLeft: [panStep, 0],
      ArrowRight: [-panStep, 0],
      ArrowUp: [0, panStep],
      ArrowDown: [0, -panStep],
      a: [panStep, 0],
      d: [-panStep, 0],
      w: [0, panStep],
      s: [0, -panStep]
    }[e.key];
    if (!keyPan) return;
    e.preventDefault();
    window.mindmapPan(...keyPan);
  });

  window.addEventListener("resize", () => {
    requestAnimationFrame(drawMindmapConnectors);
  });
}

let activeTreeBranchId = 'ALL';

window.switchTreeBranch = function(branchId) {
  activeTreeBranchId = branchId;
  document.querySelectorAll('#dt-branch-filter-group .dt-filter-btn').forEach(btn => {
    const isMatch = btn.getAttribute('data-tree-branch') === branchId;
    btn.className = isMatch ? 'btn btn-sm btn-primary dt-filter-btn' : 'btn btn-sm btn-outline-secondary dt-filter-btn';
  });

  if (cachedDecisionTreeData) {
    renderDecisionTree(cachedDecisionTreeData);
  } else {
    loadDecisionTree();
  }

  setTimeout(() => {
    mindmapFitView();
  }, 60);
};

function renderDecisionTree(tree) {
  if (!tree) return;
  const branches = tree.branches || tree.leave_type_branches || [];

  let html = '';

  if (activeTreeBranchId === 'ALL') {
    // SƠ ĐỒ TOÀN CẢNH 5 GIAI ĐOẠN (5-STAGE ARCHITECTURAL FLOWCHART)
    html = `
      <div class="dt-flow-tree">
        <!-- Banner thông tin sơ đồ -->
        <div class="dt-flow-intro mb-4 d-flex align-items-center justify-content-between flex-wrap gap-2 p-3 bg-white rounded border">
          <div>
            <div class="fw-bold text-dark fs-4">Sơ đồ Luồng Cây Quyết định 5 Giai đoạn</div>
            <div class="text-secondary small mt-0.5">Tiếp nhận hồ sơ → 8 Nhánh kiểm soát quy chế → Hậu kiểm tra rủi ro → Phân cấp thẩm quyền → Kết quả quyết định</div>
          </div>
          <div class="text-secondary small">
            Bấm vào bất kỳ nhánh quy chế nào để xem cây rẽ nhánh chi tiết
          </div>
        </div>

        <div class="dt-stages-row">
          <!-- GIAI ĐOẠN 1: TIẾP NHẬN & TIỀN KIỂM TRA -->
          <div class="dt-stage-col" id="dt-stage-1">
            <div class="dt-stage-header" style="border-top: 3px solid #2563eb;">
              <span class="badge bg-blue-lt text-primary fw-bold">GIAI ĐOẠN 1</span>
              <div class="fw-bold text-dark mt-1">Tiếp nhận & Tiền kiểm tra</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">3 bước áp dụng cho 100% mọi đơn</div>
            </div>
            <div class="dt-stage-cards">
              <div class="dt-card">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.88rem;">1. Khoảng ngày nghỉ</span>
                  <span class="badge bg-secondary-lt text-secondary">C1_DATES</span>
                </div>
                <div class="text-secondary small">Kiểm tra ngày bắt đầu & kết thúc hợp lệ, định dạng chuẩn.</div>
              </div>
              <div class="dt-card">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.88rem;">2. Tính số ngày làm việc N</span>
                  <span class="badge bg-secondary-lt text-secondary">C2_CALENDAR</span>
                </div>
                <div class="text-secondary small">Tự động trừ thứ Bảy, Chủ nhật và ngày lễ. Xác định số ngày N thực tế.</div>
              </div>
              <div class="dt-card">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.88rem;">3. Định tuyến loại nghỉ</span>
                  <span class="badge bg-secondary-lt text-secondary">C3_TYPE</span>
                </div>
                <div class="text-secondary small">Gán vào 1 trong 8 phân nhánh quy chế nghiệp vụ tương ứng.</div>
              </div>
            </div>
          </div>

          <!-- GIAI ĐOẠN 2: 8 PHÂN NHÁNH QUY CHẾ NGHIỆP VỤ -->
          <div class="dt-stage-col" id="dt-stage-2" style="min-width: 320px;">
            <div class="dt-stage-header" style="border-top: 3px solid #6366f1;">
              <span class="badge bg-indigo-lt text-indigo fw-bold">GIAI ĐOẠN 2</span>
              <div class="fw-bold text-dark mt-1">8 Nhánh Quy chế Nghiệp vụ</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Bấm xem chi tiết từng nhánh</div>
            </div>
            <div class="dt-stage-cards">
              ${branches.map(b => {
                const hex = b.color || '#475569';
                const stepsCount = (b.steps || []).length;
                return `
                  <div class="dt-card dt-branch-hover-card" style="border-left: 4px solid ${hex}; cursor: pointer;" onclick="switchTreeBranch('${b.branch_id}')" title="Bấm để xem cây quyết định chi tiết của ${escapeHtml(b.title)}">
                    <div class="d-flex align-items-center justify-content-between mb-1">
                      <span class="fw-bold text-dark" style="font-size: 0.86rem;">${escapeHtml(b.title)}</span>
                      <span class="badge bg-light text-secondary border" style="font-size: 0.7rem;">${stepsCount} trạm kiểm tra</span>
                    </div>
                    <div class="text-secondary small" style="font-size: 0.76rem;">${escapeHtml(b.what || '')}</div>
                    <div class="d-flex align-items-center justify-content-between mt-2 pt-2 border-top">
                      <span class="text-muted small" style="font-size: 0.72rem;">${escapeHtml(b.next ? b.next.split('|')[0].trim() : '')}</span>
                      <span class="text-primary small fw-semibold" style="font-size: 0.74rem;">Xem chi tiết →</span>
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>

          <!-- GIAI ĐOẠN 3: HẬU KIỂM TRA & RỦI RO -->
          <div class="dt-stage-col" id="dt-stage-3">
            <div class="dt-stage-header" style="border-top: 3px solid #0d9488;">
              <span class="badge bg-teal-lt text-teal fw-bold">GIAI ĐOẠN 3</span>
              <div class="fw-bold text-dark mt-1">Hậu kiểm tra & Rủi ro</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Đối soát lịch & Phòng chống lạm dụng</div>
            </div>
            <div class="dt-stage-cards">
              <div class="dt-card">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.88rem;">1. Kiểm tra trùng lặp lịch</span>
                  <span class="badge bg-secondary-lt text-secondary">F1_OVERLAP</span>
                </div>
                <div class="text-secondary small">Đối chiếu với các đơn đã duyệt; chặn tình trạng nghỉ trùng lịch hoặc trừ quỹ phép 2 lần.</div>
              </div>
              <div class="dt-card">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.88rem;">2. Chống phân mảnh phép</span>
                  <span class="badge bg-secondary-lt text-secondary">F2_ABUSE</span>
                </div>
                <div class="text-secondary small">Phát hiện tách nhỏ đơn phép năm cộng dồn > 2 ngày trong tháng để chuyển người xem xét.</div>
              </div>
            </div>
          </div>

          <!-- GIAI ĐOẠN 4: PHÂN CẤP THẨM QUYỀN -->
          <div class="dt-stage-col" id="dt-stage-4">
            <div class="dt-stage-header" style="border-top: 3px solid #f59e0b;">
              <span class="badge bg-warning-lt text-warning fw-bold">GIAI ĐOẠN 4</span>
              <div class="fw-bold text-dark mt-1">Phân cấp Thẩm quyền</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Xác định người ký duyệt theo số ngày</div>
            </div>
            <div class="dt-stage-cards">
              <div class="dt-card" style="border-left: 4px solid #10b981;">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.86rem;">1 – 2 ngày (Đủ chuẩn)</span>
                  <span class="badge bg-green-lt text-success">AI Fast-Track</span>
                </div>
                <div class="text-secondary small">Hệ thống AI tự động duyệt tức thì, không cần con người can thiệp.</div>
              </div>
              <div class="dt-card" style="border-left: 4px solid #3b82f6;">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.86rem;">3 – 5 ngày / Nộp gấp</span>
                  <span class="badge bg-blue-lt text-primary">Quản lý trực tiếp</span>
                </div>
                <div class="text-secondary small">Leader/Manager trực tiếp xem xét công việc và phê duyệt.</div>
              </div>
              <div class="dt-card" style="border-left: 4px solid #8b5cf6;">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.86rem;">6 – 19 ngày / Không lương</span>
                  <span class="badge bg-purple-lt text-purple">Trưởng bộ phận + HR</span>
                </div>
                <div class="text-secondary small">Trưởng phòng ban và Giám đốc Nhân sự (HRD) đồng duyệt.</div>
              </div>
              <div class="dt-card" style="border-left: 4px solid #ea580c;">
                <div class="d-flex align-items-center justify-content-between mb-1">
                  <span class="fw-bold text-dark" style="font-size: 0.86rem;">Từ 20 ngày / Thai sản / TNLĐ</span>
                  <span class="badge bg-danger-lt text-danger">Ban Giám đốc (CEO)</span>
                </div>
                <div class="text-secondary small">Tổng Giám đốc ban hành quyết định phê duyệt cuối cùng.</div>
              </div>
            </div>
          </div>

          <!-- GIAI ĐOẠN 5: KẾT QUẢ QUYẾT ĐỊNH -->
          <div class="dt-stage-col" id="dt-stage-5">
            <div class="dt-stage-header" style="border-top: 3px solid #16a34a;">
              <span class="badge bg-green-lt text-success fw-bold">GIAI ĐOẠN 5</span>
              <div class="fw-bold text-dark mt-1">Kết quả Quyết định</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Kết luận xử lý của hệ thống</div>
            </div>
            <div class="dt-stage-cards">
              <div class="dt-card" style="border-left: 4px solid #16a34a; background: #f0fdf4;">
                <div class="d-flex align-items-center gap-1.5 mb-1">
                  <span class="badge bg-success text-white fw-bold">APPROVE_AUTO</span>
                </div>
                <div class="fw-bold text-dark mt-1" style="font-size: 0.88rem;">Phê duyệt tự động</div>
                <div class="text-secondary small mt-1">Đơn hợp lệ 100%, hệ thống tự động trừ quỹ phép và gửi thông báo.</div>
              </div>
              <div class="dt-card" style="border-left: 4px solid #f59e0b; background: #fffbeb;">
                <div class="d-flex align-items-center gap-1.5 mb-1">
                  <span class="badge bg-warning text-dark fw-bold">ESCALATE_HUMAN</span>
                </div>
                <div class="fw-bold text-dark mt-1" style="font-size: 0.88rem;">Chuyển thẩm quyền</div>
                <div class="text-secondary small mt-1">Chuyển sang Hộp thư Escalation để Quản lý hoặc Nhân sự xem xét giải quyết.</div>
              </div>
              <div class="dt-card" style="border-left: 4px solid #dc2626; background: #fef2f2;">
                <div class="d-flex align-items-center gap-1.5 mb-1">
                  <span class="badge bg-danger text-white fw-bold">REJECT_POLICY</span>
                </div>
                <div class="fw-bold text-dark mt-1" style="font-size: 0.88rem;">Từ chối đơn</div>
                <div class="text-secondary small mt-1">Hết phép năm, sai chứng từ hoặc vi phạm quy chế không thể giải quyết.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  } else {
    // SƠ ĐỒ CHI TIẾT THEO TỪNG NHÁNH QUY CHẾ (DEEP DIVE DECISION TREE)
    const activeBranch = branches.find(b => b.branch_id === activeTreeBranchId) || branches[0];
    const steps = activeBranch.steps || [];
    const hex = activeBranch.color || '#2563eb';

    html = `
      <div class="dt-flow-tree">
        <!-- Banner thông tin nhánh -->
        <div class="dt-flow-intro mb-4 p-3 bg-white rounded border d-flex align-items-center justify-content-between flex-wrap gap-2">
          <div>
            <div class="d-flex align-items-center gap-2">
              <span class="badge bg-primary text-white fw-bold px-2 py-1">${escapeHtml(activeBranch.branch_id)}</span>
              <span class="fw-bold text-dark fs-3">${escapeHtml(activeBranch.title)}</span>
            </div>
            <div class="text-secondary small mt-1">${escapeHtml(activeBranch.what || '')} · ${escapeHtml(activeBranch.who || '')}</div>
          </div>
          <button type="button" class="btn btn-sm btn-outline-primary px-3 py-1.5" onclick="switchTreeBranch('ALL')">
            ← Quay lại Toàn bộ luồng
          </button>
        </div>

        <div class="dt-stages-row">
          <!-- BƯỚC 1: TIẾP NHẬN -->
          <div class="dt-stage-col" id="dt-stage-1" style="max-width: 280px;">
            <div class="dt-stage-header" style="border-top: 3px solid #2563eb;">
              <span class="badge bg-blue-lt text-primary fw-bold">BƯỚC 1</span>
              <div class="fw-bold text-dark mt-1">Tiếp nhận & Tính ngày</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Xác định số ngày làm việc N</div>
            </div>
            <div class="dt-stage-cards">
              <div class="dt-card">
                <div class="fw-bold text-dark mb-1">Nộp đơn nghỉ phép</div>
                <div class="text-secondary small">Xác thực nhân viên, chức vụ, bộ phận và khoảng ngày nghỉ.</div>
                <div class="mt-2 pt-2 border-top text-success small fw-semibold">
                  ✓ Tính ra N ngày làm việc thực tế
                </div>
              </div>
            </div>
          </div>

          <!-- BƯỚC 2: CÁC TRẠM KIỂM SOÁT ĐIỀU KIỆN (MỖI TRẠM CÓ NHÁNH ĐẠT & VI PHẠM) -->
          <div class="dt-stage-col" id="dt-stage-2" style="min-width: 440px; flex: 2;">
            <div class="dt-stage-header" style="border-top: 3px solid ${hex};">
              <span class="badge bg-light border text-dark fw-bold">BƯỚC 2</span>
              <div class="fw-bold text-dark mt-1">Các Trạm Thẩm định Quy chế (${steps.length} Trạm)</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Quy tắc kiểm tra rẽ nhánh Yes / No</div>
            </div>
            <div class="dt-stage-cards">
              ${steps.map((step, idx) => {
                const passText = step.when_pass || 'Đạt chuẩn';
                const failText = step.when_fail || 'Vi phạm / Ngoại lệ';
                const clause = step.clause || '';
                const isWarning = failText.includes('đặc cách') || failText.includes('Quản lý') || failText.includes('Nhân sự') || failText.includes('xác minh');

                return `
                  <div class="dt-card mb-2" style="border-left: 4px solid ${hex};">
                    <div class="d-flex align-items-center justify-content-between mb-1">
                      <span class="fw-bold text-dark" style="font-size: 0.9rem;">${idx + 1}. ${escapeHtml(step.label)}</span>
                      ${clause ? `<span class="badge bg-secondary-lt text-secondary" style="font-size: 0.7rem;">${escapeHtml(clause)}</span>` : ''}
                    </div>
                    <div class="text-secondary small" style="font-size: 0.79rem; line-height: 1.4;">${escapeHtml(step.note || '')}</div>
                    ${step.doc_req ? `
                      <div class="small mt-1.5 p-1.5 bg-light rounded border text-muted" style="font-size: 0.74rem;">
                        <span class="fw-semibold text-dark">Hồ sơ:</span> ${escapeHtml(step.doc_req)}
                      </div>
                    ` : ''}

                    <!-- Hai nhánh rẽ: Đạt vs Vi phạm -->
                    <div class="row g-2 mt-2 pt-2 border-top">
                      <div class="col-6">
                        <div class="p-1.5 rounded bg-green-lt text-success" style="font-size: 0.75rem; line-height: 1.35;">
                          <div class="fw-bold">✓ ĐẠT ĐIỀU KIỆN:</div>
                          <div>${escapeHtml(passText)}</div>
                        </div>
                      </div>
                      <div class="col-6">
                        <div class="p-1.5 rounded ${isWarning ? 'bg-warning-lt text-warning' : 'bg-danger-lt text-danger'}" style="font-size: 0.75rem; line-height: 1.35;">
                          <div class="fw-bold">✕ CHƯA ĐẠT / LỖI:</div>
                          <div>${escapeHtml(failText)}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>

          <!-- BƯỚC 3: PHÂN CẤP THẨM QUYỀN -->
          <div class="dt-stage-col" id="dt-stage-3" style="max-width: 300px;">
            <div class="dt-stage-header" style="border-top: 3px solid #f59e0b;">
              <span class="badge bg-warning-lt text-warning fw-bold">BƯỚC 3</span>
              <div class="fw-bold text-dark mt-1">Phân cấp Thẩm quyền</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Quy định người phê duyệt</div>
            </div>
            <div class="dt-stage-cards">
              <div class="dt-card">
                <div class="fw-bold text-dark mb-1" style="font-size: 0.88rem;">Tiêu chuẩn phân cấp:</div>
                <div class="text-secondary small mt-1" style="line-height: 1.6;">${escapeHtml(activeBranch.next || 'Theo số ngày nghỉ và tính chất hồ sơ')}</div>
                <div class="mt-2.5 pt-2 border-top">
                  <div class="text-secondary small fw-medium">Phương thức thẩm định:</div>
                  <div class="fw-bold text-dark mt-0.5" style="font-size: 0.82rem;">${escapeHtml(activeBranch.how || '')}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- BƯỚC 4: KẾT QUẢ CUỐI CÙNG -->
          <div class="dt-stage-col" id="dt-stage-4" style="max-width: 280px;">
            <div class="dt-stage-header" style="border-top: 3px solid #16a34a;">
              <span class="badge bg-green-lt text-success fw-bold">BƯỚC 4</span>
              <div class="fw-bold text-dark mt-1">Kết quả Phê duyệt</div>
              <div class="text-secondary small" style="font-size: 0.73rem;">Hành động hệ thống</div>
            </div>
            <div class="dt-stage-cards">
              <div class="dt-card border-success" style="background: #f0fdf4;">
                <div class="fw-bold text-success" style="font-size: 0.88rem;">Hợp lệ · Phê duyệt</div>
                <div class="text-secondary small mt-1">Ghi nhận ngày nghỉ vào lịch làm việc, cập nhật số dư phép hoặc gửi hồ sơ sang cơ quan BHXH.</div>
              </div>
              <div class="dt-card border-warning mt-2" style="background: #fffbeb;">
                <div class="fw-bold text-warning" style="font-size: 0.88rem;">Ngoại lệ · Chuyển cấp</div>
                <div class="text-secondary small mt-1">Chuyển Quản lý/Nhân sự thẩm tra đối soát chứng từ trước khi ra quyết định.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  document.querySelectorAll('.dt-nodes-container').forEach(c => {
    c.innerHTML = html;
  });

  setupTreeContainerPanning();
  applyMindmapTransform();
  setTimeout(() => {
    requestAnimationFrame(drawMindmapConnectors);
  }, 60);
}

// Vẽ đường nối SVG tự động giữa các cột giai đoạn cây quyết định
function drawMindmapConnectors() {
  const svg = document.getElementById("mm-svg-canvas");
  const world = document.getElementById("mm-world");
  if (!svg || !world) return;

  const worldRect = world.getBoundingClientRect();
  const zoom = mmState.zoom || 1.0;

  const svgW = Math.max(world.scrollWidth, 1400);
  const svgH = Math.max(world.scrollHeight, 900);
  svg.setAttribute("width", svgW);
  svg.setAttribute("height", svgH);

  svg.innerHTML = `
    <defs>
      <marker id="dt-arrow-blue" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#3b82f6" />
      </marker>
      <marker id="dt-arrow-gray" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#94a3b8" />
      </marker>
    </defs>
  `;

  const getUnscaledBox = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: (r.left - worldRect.left) / zoom,
      y: (r.top - worldRect.top) / zoom,
      w: r.width / zoom,
      h: r.height / zoom,
      right: (r.left - worldRect.left + r.width) / zoom,
      left: (r.left - worldRect.left) / zoom,
      cy: (r.top - worldRect.top + r.height / 2) / zoom,
    };
  };

  const stageCols = Array.from(world.querySelectorAll(".dt-stage-col .dt-stage-header"));
  if (stageCols.length >= 2) {
    for (let i = 0; i < stageCols.length - 1; i++) {
      const c1 = getUnscaledBox(stageCols[i]);
      const c2 = getUnscaledBox(stageCols[i + 1]);

      const p1 = { x: c1.right, y: c1.cy };
      const p2 = { x: c2.left, y: c2.cy };
      const midX = (p1.x + p2.x) / 2;

      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const d = `M ${p1.x} ${p1.y} C ${midX} ${p1.y}, ${midX} ${p2.y}, ${p2.x} ${p2.y}`;
      path.setAttribute("d", d);
      path.setAttribute("stroke", "#3b82f6");
      path.setAttribute("stroke-width", "2");
      path.setAttribute("fill", "none");
      path.setAttribute("stroke-linecap", "round");
      path.setAttribute("stroke-dasharray", "4 3");
      path.setAttribute("opacity", "0.75");
      path.setAttribute("marker-end", "url(#dt-arrow-blue)");
      svg.appendChild(path);
    }
  }
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

  const MANDATORY_PROOF_TYPES = ['SICK_MEDICAL', 'MEDICAL_EMERGENCY', 'SPECIAL_PAID', 'WORK_ACCIDENT', 'MATERNITY'];

  const updateAttachmentRequirement = () => {
    const leaveType = document.getElementById('staff-leave-type')?.value || 'ANNUAL';
    const label = document.getElementById('staff-attachment-label');
    const hint = document.getElementById('staff-attachment-hint');
    const dropzone = document.getElementById('file-dropzone');
    const dropTitle = document.getElementById('dropzone-title');
    const dropSub = document.getElementById('dropzone-sub');

    if (MANDATORY_PROOF_TYPES.includes(leaveType)) {
      if (label) {
        label.innerHTML = `Chứng từ xác minh <span class="badge" style="background:#fee2e2;color:#991b1b;font-weight:700;font-size:0.75rem;padding:2px 8px;border-radius:4px;margin-left:4px;">BẮT BUỘC</span>`;
      }
      if (hint) {
        hint.innerHTML = `<span style="color:#dc2626;font-weight:600;">Yêu cầu chứng từ y tế / hành chính hợp lệ</span>`;
      }
      if (dropzone) {
        dropzone.style.borderColor = '#f87171';
        dropzone.style.background = '#fef2f225';
      }
      if (dropTitle) {
        dropTitle.innerHTML = `Bấm để tải <strong style="color:#b91c1c;">giấy khám / giấy tờ xác nhận</strong> hoặc kéo thả vào đây`;
      }
      if (dropSub) {
        dropSub.innerText = `Chấp nhận PDF, PNG, JPG (AI Engine sẽ đọc và đối soát)`;
      }
    } else {
      if (label) {
        label.innerHTML = `Chứng từ xác minh <span class="badge" style="background:#f1f5f9;color:#64748b;font-weight:500;font-size:0.75rem;padding:2px 8px;border-radius:4px;margin-left:4px;">Không bắt buộc / Tùy chọn</span>`;
      }
      if (hint) {
        hint.innerHTML = '';
      }
      if (dropzone) {
        dropzone.style.borderColor = '#cbd5e1';
        dropzone.style.background = '#ffffff';
      }
      if (dropTitle) {
        dropTitle.innerHTML = `Bấm để tải tệp lên hoặc kéo thả vào đây (nếu có)`;
      }
      if (dropSub) {
        dropSub.innerText = `PDF, PNG, JPG (tối đa 10MB)`;
      }
    }
  };

  if (fromInput) fromInput.addEventListener("change", updateDuration);
  if (toInput) toInput.addEventListener("change", updateDuration);
  document.getElementById("staff-leave-type")?.addEventListener("change", () => {
    updateDuration();
    updateAttachmentRequirement();
  });
  updateDuration();
  updateAttachmentRequirement();

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
        selectedProofFile = null;
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
      selectedProofFile = null;
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

/* ── THANH TIẾN TRÌNH: % theo thời lượng phase thật, không cộng % bừa ──
 * Form nộp đơn: VLM (nếu có file) → Rule Engine → template. Không gọi LLM.
 * qwen2.5vl:7b ảnh A4 1280px GPU ~8–18s → lấy mốc 12s.
 * Upload ~1s; Rule+template+save <0.5s (chìm trong thời gian VLM nếu có file).
 */
let _progressInterval = null;
let _progressHasFile = false;

function showSubmitProgress(hasFile = false) {
  _progressHasFile = !!hasFile;
  const startedAt = performance.now();
  const modal = document.getElementById("modal-submit-progress");
  if (!modal) return;
  modal.style.display = "block";

  const bar = document.getElementById("submit-progress-bar");
  const pLabel = document.getElementById("progress-percent-label");
  const sLabel = document.getElementById("progress-step-label");
  const sub = document.getElementById("progress-modal-sub");
  if (sub) {
    sub.textContent = hasFile
      ? "AI Engine đọc chứng từ ~12s (8–18s) · đối soát <0.3s"
      : "Không chứng từ: AI Engine bỏ qua bước đọc chứng từ · đối soát <0.3s";
  }
  if (bar) bar.style.background = "linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899)";

  _setStepState(1, "processing", "Đang xử lý");
  _setStepState(2, hasFile ? "waiting" : "done", hasFile ? "Chờ" : "Bỏ qua (không chứng từ)");
  _setStepState(3, "waiting", "Chờ");
  _setStepState(4, "waiting", "Chờ");
  _setStepState(5, "waiting", "Chờ");

  const UPLOAD_MS = 1000;
  const VLM_MS = 12000;
  const RECV_MS = 250;
  const RULE_MS = 250;

  const paint = (pct, label) => {
    const display = Math.max(0, Math.min(96, Math.round(pct)));
    if (bar) {
      bar.style.width = `${display}%`;
      bar.setAttribute("aria-valuenow", String(display));
    }
    if (pLabel) pLabel.innerText = `${display}%`;
    if (sLabel) sLabel.innerText = label;
  };

  const tick = () => {
    const elapsed = performance.now() - startedAt;
    const dots = ".".repeat((Math.floor(elapsed / 400) % 4) + 1);

    if (hasFile) {
      if (elapsed < UPLOAD_MS) {
        _setStepState(1, "processing", "Đang tải lên");
        paint((elapsed / UPLOAD_MS) * 6, "Bước 1: Tải chứng từ lên máy chủ...");
        return;
      }
      _setStepState(1, "done", "Xong ✓");
      _setStepState(2, "processing", "Đang OCR");
      const vlmElapsed = elapsed - UPLOAD_MS;
      let pct;
      let remainLabel;
      if (vlmElapsed < VLM_MS) {
        pct = 6 + (vlmElapsed / VLM_MS) * 80;
        remainLabel = `~${Math.max(1, Math.ceil((VLM_MS - vlmElapsed) / 1000))}s`;
      } else {
        pct = 86 + 10 * (1 - Math.exp(-(vlmElapsed - VLM_MS) / 8000));
        remainLabel = "vượt mốc 12s";
      }
      _setStepState(2, "processing", remainLabel);
      paint(pct, `Bước 2: AI Engine đang đọc chứng từ (${remainLabel})${dots}`);
      return;
    }

    _setStepState(2, "done", "Bỏ qua (không chứng từ)");
    if (elapsed < RECV_MS) {
      _setStepState(1, "processing", "Đang tiếp nhận");
      paint((elapsed / RECV_MS) * 25, "Bước 1: Tiếp nhận dữ liệu đơn...");
      return;
    }
    _setStepState(1, "done", "Xong ✓");
    if (elapsed < RECV_MS + RULE_MS) {
      _setStepState(3, "processing", "Đang đối soát");
      paint(25 + ((elapsed - RECV_MS) / RULE_MS) * 50, "Bước 3: AI Engine đối soát chính sách...");
      return;
    }
    _setStepState(3, "done", "Xong ✓");
    _setStepState(4, "processing", "Đang ghi nhận");
    _setStepState(5, "processing", "Đang lưu");
    const extra = elapsed - RECV_MS - RULE_MS;
    paint(75 + 21 * (1 - Math.exp(-extra / 400)), `Bước 4–5: Tổng hợp template & lưu hồ sơ${dots}`);
  };

  clearInterval(_progressInterval);
  tick();
  _progressInterval = setInterval(tick, 100);
}

function finishSubmitProgress(success = true, callback) {
  clearInterval(_progressInterval);
  const bar = document.getElementById("submit-progress-bar");
  const pLabel = document.getElementById("progress-percent-label");
  const sLabel = document.getElementById("progress-step-label");

  if (bar) {
    bar.style.width = "100%";
    bar.style.background = success ? "#10b981" : "#ef4444";
  }
  if (pLabel) pLabel.innerText = "100%";
  if (sLabel) sLabel.innerText = success ? "Hoàn tất thẩm định!" : "Xử lý thất bại";

  _setStepState(1, "done", "Xong ✓");
  _setStepState(2, "done", _progressHasFile ? "Xong ✓" : "Bỏ qua (không chứng từ)");
  _setStepState(3, "done", "Xong ✓");
  _setStepState(4, "done", "Xong ✓");
  _setStepState(5, success ? "done" : "error", success ? "Hoàn tất ✓" : "Lỗi");

  setTimeout(() => {
    const modal = document.getElementById("modal-submit-progress");
    if (modal) modal.style.display = "none";
    if (bar) {
      bar.style.background = "linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899)";
    }
    if (callback) callback();
  }, 400);
}

function _setStepState(stepNum, state, text) {
  const stepEl = document.getElementById(`p-step-${stepNum}`);
  if (!stepEl) return;
  const badge = stepEl.querySelector(".step-status");
  const stepText = stepEl.querySelector(".step-text");

  if (state === "processing") {
    stepEl.style.background = "#eff6ff";
    stepEl.style.borderColor = "#bfdbfe";
    if (badge) {
      badge.className = "step-status badge bg-primary text-white";
      badge.innerHTML = `<span class="spinner-border spinner-border-sm me-1" style="width:0.65rem;height:0.65rem;" role="status"></span>${text}`;
    }
    if (stepText) {
      stepText.className = "step-text small fw-bold text-primary";
    }
  } else if (state === "done") {
    stepEl.style.background = "#f0fdf4";
    stepEl.style.borderColor = "#bbf7d0";
    if (badge) {
      badge.className = "step-status badge bg-success-lt text-success fw-bold";
      badge.innerText = text;
    }
    if (stepText) {
      stepText.className = "step-text small fw-semibold text-dark";
    }
  } else if (state === "error") {
    stepEl.style.background = "#fef2f2";
    stepEl.style.borderColor = "#fecaca";
    if (badge) {
      badge.className = "step-status badge bg-danger text-white";
      badge.innerText = text;
    }
    if (stepText) {
      stepText.className = "step-text small fw-semibold text-danger";
    }
  } else {
    // waiting
    stepEl.style.background = "#f8fafc";
    stepEl.style.borderColor = "#e2e8f0";
    if (badge) {
      badge.className = "step-status badge bg-secondary-lt text-secondary";
      badge.innerText = text;
    }
    if (stepText) {
      stepText.className = "step-text small fw-semibold text-secondary";
    }
  }
}

async function handleStandardFormSubmit() {
  const file = document.getElementById('staff-file-input')?.files[0] || selectedProofFile;
  const leaveType = document.getElementById('staff-leave-type')?.value || 'ANNUAL';
  const mandatoryProofTypes = ['SICK_MEDICAL', 'MEDICAL_EMERGENCY', 'SPECIAL_PAID', 'WORK_ACCIDENT', 'MATERNITY'];

  // Cảnh báo nếu loại nghỉ yêu cầu chứng từ nhưng nhân viên chưa đính kèm
  if (mandatoryProofTypes.includes(leaveType) && !file && !currentProofId) {
    const leaveName = document.getElementById('staff-leave-type')?.selectedOptions[0]?.text || leaveType;
    showToast(`Loại nghỉ "${leaveName}" BẮT BUỘC có chứng từ đính kèm (giấy khám bệnh, giấy ra viện, giấy tờ xác nhận...). Vui lòng tải chứng từ trước khi gửi!`, 'error');
    const dropzone = document.getElementById('file-dropzone');
    if (dropzone) {
      dropzone.scrollIntoView({ behavior: 'smooth', block: 'center' });
      dropzone.style.animation = 'pulse 1s ease-in-out';
      setTimeout(() => dropzone.style.animation = '', 1000);
    }
    return;
  }

  showSubmitProgress(!!file);

  if (file) {
    try {
      const form = new FormData(); form.append('file',file);
      form.append('proof_type',document.getElementById('staff-proof-type')?.value || 'MEDICAL_LEAVE_CERTIFICATE');
      const response = await apiFetch(`${API_BASE}/api/leave/proofs`,{method:'POST',body:form});
      const result=await response.json();
      if(!response.ok) {
        finishSubmitProgress(false, () => showToast(JSON.stringify(result.detail),'error'));
        return;
      }
      currentProofId=result.data.proof_id;
    } catch(err) {
      finishSubmitProgress(false, () => showToast('Lỗi tải file: ' + err.message, 'error'));
      return;
    }
  }
  const payload={
    leave_type:document.getElementById('staff-leave-type')?.value || null,
    reason_category:document.getElementById('staff-reason-category')?.value || null,
    from_date:document.getElementById('staff-from-date')?.value || null,
    to_date:document.getElementById('staff-to-date')?.value || null,
    reason:document.getElementById('staff-reason')?.value || '',
    handover_person_id:document.getElementById('staff-handover-select')?.value || null,
    proof_id:currentProofId
  };
  await submitLeaveToBackend(payload, !!file);
}

async function submitLeaveToBackend(payload, hasFile = false) {
  try {
    if (!document.getElementById("modal-submit-progress") || document.getElementById("modal-submit-progress").style.display === "none") {
      showSubmitProgress(hasFile || !!payload.proof_id);
    }
    const url=editingRequestId ? `/api/leave/${editingRequestId}/resubmit` : '/api/leave/request';
    const res=await apiFetch(API_BASE+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result=await res.json();
    if(!res.ok) {
      finishSubmitProgress(false, () => showToast(JSON.stringify(result.detail),'error'));
      return false;
    }
    finishSubmitProgress(true, async () => {
      showToast(`${DECISION_LABELS[result.data.decision] || result.data.decision}: ${result.data.human_readable_explanation}`,'info');
      editingRequestId=null; currentProofId=null; selectedProofFile=null;
      document.getElementById('form-staff-standard')?.reset();
      const attachTypeVal = document.getElementById("staff-attachment-type");
      if (attachTypeVal) attachTypeVal.value = "none";
      const proofPreview = document.getElementById("staff-proof-preview");
      if (proofPreview) proofPreview.classList.add("d-none");
      const banner = document.getElementById('correction-banner');
      if (banner) banner.textContent='';
      await loadAllRequests(); await loadEmployees();
      switchStaffTab('tab-staff-requests');
    });
    return true;
  } catch(err) {
    finishSubmitProgress(false, () => showToast('Không gửi được đơn: '+err.message,'error'));
    return false;
  }
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
  if (requestsLoadInFlight) return;
  requestsLoadInFlight = true;
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
  } finally {
    requestsLoadInFlight = false;
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
  const tbody = document.getElementById("staff-requests-tbody");
  const cardContainer = document.getElementById("staff-requests-card-container");
  if (!tbody && !cardContainer) return;

  const filterVal = document.getElementById("staff-requests-filter")?.value || "ALL";
  let myRequests = activeRequests.filter(r => r.employee_id === currentEmployeeId);

  if (filterVal !== "ALL") {
    myRequests = myRequests.filter(r => r.decision === filterVal || r.status === filterVal);
  }

  if (tbody) {
    if (myRequests.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center text-secondary py-4">Không có đơn nghỉ phép nào phù hợp với bộ lọc.</td></tr>`;
      return;
    }

    tbody.innerHTML = myRequests.map(req => {
      const cancellable = ['WAITING_EMPLOYEE', 'PENDING_ESCALATION'].includes(req.status);
      const cancelBtnHtml = cancellable
        ? `<button type="button" class="btn btn-sm btn-outline-danger px-2.5 py-1" onclick="cancelMyRequest('${req.id}')" title="Hủy đơn nghỉ phép này">Hủy đơn</button>`
        : `<span class="text-muted">—</span>`;

      return `
        <tr>
          <td>${escapeHtml(req.from_date || '')} → ${escapeHtml(req.to_date || '')}</td>
          <td><b>${req.requested_working_days ?? req.workdays ?? 0} ngày</b></td>
          <td>${getStatusBadgeHtml(req)}</td>
          <td>
            <button type="button" class="btn btn-sm btn-outline-primary px-2.5 py-1" onclick="openRequestDetailModal('${req.id}')" title="Xem chi tiết đơn nghỉ phép">
              Chi tiết
            </button>
          </td>
          <td>${cancelBtnHtml}</td>
        </tr>
      `;
    }).join("");
  } else if (cardContainer) {
    if (myRequests.length === 0) {
      cardContainer.innerHTML = `
        <div style="text-align: center; color: var(--text-dim); padding: 50px 0;">
          <div>Không có đơn nghỉ phép nào phù hợp với bộ lọc.</div>
        </div>
      `;
      return;
    }
    cardContainer.innerHTML = myRequests.map(req => renderSingleRequestCard(req, true)).join("");
    attachRequestCardEvents();
  }
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

        <div class="d-flex align-items-center gap-2" style="align-self: flex-start; margin-top: 2px;">
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


// =========================================================================
// DỮ LIỆU ĐẦY ĐỦ 5 ĐƠN NGHỈ PHÉP TRONG BỘ KỊCH BẢN KIỂM THỬ SPRINT 1
// =========================================================================
const BENCHMARK_CASES_DATA = {
  "TC-AI-01": {
    id: "TC-AI-01",
    employee_name: "Nguyễn Văn An",
    employee_id: "EMP005",
    department: "Engineering",
    leave_type: "ANNUAL",
    from_date: "2026-10-05",
    to_date: "2026-10-05",
    requested_working_days: 1,
    workdays: 1,
    remaining_leave_days: 10,
    handover_person_id: null,
    handover_person_name: "Không yêu cầu bàn giao (nghỉ 1 ngày)",
    reason: "Việc riêng gia đình",
    submitted_at: "2026-10-01T08:00:00+07:00",
    status: "APPROVED",
    decision: "AUTO_APPROVE",
    human_readable_explanation: "Đơn đầy đủ điều kiện và được phê duyệt tự động: Phép năm 1 ngày hợp lệ theo Điều 113 BLLĐ, nhân viên đủ số dư phép (còn 10 ngày), thời gian gửi đơn báo trước đúng hạn và tỷ lệ nhân sự phòng ban đảm bảo.",
    actionable_question: "Tự động xử lý hoàn toàn: Phép năm hợp lệ, đủ số dư, không cần chuyển người duyệt.",
    llm_summary_json: {
      decision: "AUTO_APPROVE",
      correlation_tier_vn: "Thường quy · Tự duyệt",
      summary_natural_vn: "Nhân viên Nguyễn Văn An xin nghỉ 1 ngày phép năm (05/10/2026). Đơn nộp trước hạn 4 ngày, số dư phép còn 10 ngày (đủ điều kiện), phòng ban hiện tại vắng 0/6 người.",
      staff_summary: { errors_vn: [] },
      decision_tree_checklist: [
        { node_id: "RULE_01", node_name: "Loại nghỉ phép", result: "PASSED", note: "Phép năm (ANNUAL) theo Điều 113 BLLĐ" },
        { node_id: "RULE_02", node_name: "Số dư phép năm", result: "PASSED", note: "Còn 10 ngày phép (yêu cầu 1 ngày)" },
        { node_id: "RULE_03", node_name: "Thời hạn báo trước", result: "PASSED", note: "Báo trước 4 ngày (quy định 1-2 ngày)" },
        { node_id: "RULE_04", node_name: "Tỷ lệ hiện diện phòng ban", result: "PASSED", note: "Phòng vắng 0/6 (0% <= 30%)" }
      ]
    }
  },
  "TC-EMP008-03": {
    id: "TC-EMP008-03",
    employee_name: "Nguyễn Thị Kim Ngân",
    employee_id: "EMP008",
    department: "Marketing & Operations",
    leave_type: "ANNUAL",
    from_date: "2026-10-08",
    to_date: "2026-10-09",
    requested_working_days: 2,
    workdays: 2,
    remaining_leave_days: 12,
    handover_person_id: "EMP010",
    handover_person_name: "Nguyễn Văn Cường (EMP010 - Marketing & Operations)",
    reason: "Nghỉ phép thường niên",
    submitted_at: "2026-10-01T08:00:00+07:00",
    status: "APPROVED",
    decision: "AUTO_APPROVE",
    human_readable_explanation: "Đơn đầy đủ điều kiện và được phê duyệt tự động: Phép năm 2 ngày có bàn giao công việc hợp lệ cho nhân sự cùng phòng (EMP010), nhân viên đủ số dư phép (12 ngày).",
    actionable_question: "Tự động xử lý hoàn toàn: Phép năm 2 ngày có bàn giao hợp lệ cùng phòng, không cần chuyển người duyệt.",
    llm_summary_json: {
      decision: "AUTO_APPROVE",
      correlation_tier_vn: "Thường quy · Tự duyệt",
      summary_natural_vn: "Nhân viên Nguyễn Thị Kim Ngân xin nghỉ 2 ngày phép năm. Đã có thỏa thuận bàn giao công việc cho đồng nghiệp cùng phòng Marketing đang làm việc bình thường.",
      staff_summary: { errors_vn: [] },
      decision_tree_checklist: [
        { node_id: "RULE_01", node_name: "Loại nghỉ phép", result: "PASSED", note: "Phép năm (ANNUAL)" },
        { node_id: "RULE_02", node_name: "Nhân sự nhận bàn giao", result: "PASSED", note: "Bàn giao cho EMP010 cùng phòng" },
        { node_id: "RULE_03", node_name: "Số dư phép năm", result: "PASSED", note: "Còn 12 ngày phép (trừ 2 ngày còn 10 ngày)" },
        { node_id: "RULE_04", node_name: "Tỷ lệ vắng mặt phòng", result: "PASSED", note: "Vắng 0/6 thành viên" }
      ]
    }
  },
  "TC-AI-03B": {
    id: "TC-AI-03B",
    employee_name: "Bùi Tuấn Kiệt",
    employee_id: "EMP006",
    department: "Engineering",
    leave_type: "ANNUAL",
    from_date: "2026-10-05",
    to_date: "2026-10-06",
    requested_working_days: 2,
    workdays: 2,
    remaining_leave_days: 1,
    handover_person_id: null,
    handover_person_name: "Không yêu cầu",
    reason: "Nghỉ việc gia đình 2 ngày",
    submitted_at: "2026-10-01T08:00:00+07:00",
    status: "REJECTED",
    decision: "AUTO_REJECT",
    human_readable_explanation: "Hệ thống AI tự động từ chối (BALANCE_EXCEEDED): Số ngày nghỉ yêu cầu (2 ngày) vượt quá số dư phép năm còn lại của nhân viên (hiện chỉ còn 1 ngày). Nhân viên có thể gửi lại đơn 1 ngày hoặc xin nghỉ không lương.",
    actionable_question: "Tự động xử lý hoàn toàn: Bị từ chối tự động do số ngày yêu cầu (2) vượt quá số dư phép năm còn lại (1).",
    llm_summary_json: {
      decision: "AUTO_REJECT",
      correlation_tier_vn: "Thường quy · Từ chối",
      summary_natural_vn: "Đơn xin nghỉ 2 ngày phép năm nhưng số dư phép năm hiện tại chỉ còn 1 ngày. Hệ thống từ chối theo Quy chế Quản lý Phép nghỉ công ty.",
      staff_summary: {
        errors_vn: ["Số ngày xin nghỉ (2 ngày) vượt quá số dư phép năm hiện có (1 ngày). Hệ thống từ chối tự động với mã lỗi BALANCE_EXCEEDED."]
      },
      decision_tree_checklist: [
        { node_id: "RULE_01", node_name: "Loại nghỉ phép", result: "PASSED", note: "Phép năm (ANNUAL)" },
        { node_id: "RULE_02", node_name: "Kiểm tra số dư phép", result: "FAILED", note: "Yêu cầu 2 ngày > Số dư còn 1 ngày (BALANCE_EXCEEDED)" }
      ]
    }
  },
  "TC-VLM-03": {
    id: "TC-VLM-03",
    employee_name: "Lê Văn Nam",
    employee_id: "EMP004",
    department: "Engineering",
    leave_type: "SICK_MEDICAL",
    from_date: "2026-10-12",
    to_date: "2026-10-14",
    requested_working_days: 3,
    workdays: 3,
    remaining_leave_days: 10,
    handover_person_id: null,
    handover_person_name: "Không yêu cầu",
    reason: "Rối loạn tiêu hóa cấp, theo dõi ngộ độc thức ăn",
    proof_id: "proof_emp004_sick_days_mismatch.png",
    proof_file: "proof_emp004_sick_days_mismatch.png",
    attachment_type: "proof_emp004_sick_days_mismatch.png",
    submitted_at: "2026-10-12T07:30:00+07:00",
    status: "PENDING",
    decision: "NEED_CORRECTION",
    human_readable_explanation: "Chuyển tiếp cần sửa đơn (Lệch chứng từ y tế): Giấy chứng nhận nghỉ việc hưởng BHXH của BV Đa khoa Hồng Ngọc chỉ định nghỉ 1 ngày (12/10), nhưng đơn xin nghỉ 3 ngày (12/10 - 14/10). Nhân viên cần điều chỉnh số ngày hoặc Quản lý xem xét nghỉ không lương 2 ngày còn lại.",
    actionable_question: "Đơn xin nghỉ 3 ngày (12/10 - 14/10) nhưng giấy chứng nhận y tế chỉ chỉ định nghỉ 1 ngày (12/10). Quản lý có chấp thuận cho nhân viên nghỉ không lương 2 ngày còn lại hoặc yêu cầu nhân viên điều chỉnh lại ngày nghỉ theo chứng từ?",
    vlm_analysis_json: {
      document_summary: {
        patient_name: "Lê Văn Nam",
        issuer: "Bệnh viện Đa khoa Hồng Ngọc",
        diagnosis: "Rối loạn tiêu hóa cấp, theo dõi ngộ độc thức ăn",
        issue_date: "2026-10-12",
        doctor_recommended_range: { from: "2026-10-12", to: "2026-10-12", days: 1 }
      },
      flags: { has_red_stamp: true, has_doctor_signature: true, document_readability: "CLEAR" },
      inspection_mode: "OLLAMA_REAL_QWEN25_VL_3B"
    },
    llm_summary_json: {
      decision: "NEED_CORRECTION",
      correlation_tier_vn: "Chưa xác định thực tế (Lệch ảnh & Text)",
      summary_natural_vn: "Đơn xin nghỉ ốm 3 ngày (12/10 - 14/10) nhưng giấy chứng nhận y tế Bệnh viện Hồng Ngọc chỉ định nghỉ 1 ngày (12/10). Đơn cần được chỉnh sửa ngày cho khớp chứng từ.",
      staff_summary: {
        errors_vn: ["Thời gian xin nghỉ (3 ngày: 12/10 - 14/10) không khớp với chỉ định của bác sĩ trên giấy khám (1 ngày: 12/10)."]
      },
      manager_summary: {
        suspicions_vn: ["Lệch số ngày giữa đơn xin (3 ngày) và giấy bác sĩ chỉ định (1 ngày)"],
        risk_level_vn: "Trung bình"
      },
      quick_action_options_vn: ["Yêu cầu nhân viên sửa đơn về 1 ngày", "Chấp thuận duyệt 1 ngày hưởng BHXH + 2 ngày không lương"],
      decision_tree_checklist: [
        { node_id: "RULE_01", node_name: "Xác thực chứng từ y tế", result: "PASSED", note: "Có dấu mộc đỏ BV Hồng Ngọc, có chữ ký bác sĩ" },
        { node_id: "RULE_02", node_name: "Đối soát số ngày chỉ định", result: "FAILED", note: "Bác sĩ chỉ định 1 ngày (12/10) != Đơn xin 3 ngày (12-14/10)" }
      ]
    }
  },
  "TC-MGR-03": {
    id: "TC-MGR-03",
    employee_name: "Võ Minh Khang",
    employee_id: "EMP009",
    department: "Marketing & Operations",
    leave_type: "SPECIAL_PAID",
    from_date: "2026-10-05",
    to_date: "2026-10-07",
    requested_working_days: 3,
    workdays: 3,
    remaining_leave_days: 12,
    handover_person_id: null,
    handover_person_name: "Không yêu cầu",
    reason: "Nghỉ đám cưới bản thân (Lễ thành hôn)",
    proof_id: "proof_emp009_wedding_valid.png",
    proof_file: "proof_emp009_wedding_valid.png",
    attachment_type: "proof_emp009_wedding_valid.png",
    submitted_at: "2026-10-01T08:00:00+07:00",
    status: "PENDING",
    decision: "ESCALATE",
    human_readable_explanation: "Vượt thẩm quyền AI (Chuyển Quản lý duyệt): Chế độ nghỉ kết hôn 3 ngày hưởng 100% lương theo Điều 115 Bộ luật Lao động, kèm Giấy chứng nhận kết hôn hợp lệ. Đơn được chuyển Quản lý trực tiếp xem xét phê duyệt.",
    actionable_question: "Nhân viên Võ Minh Khang xin nghỉ 3 ngày kết hôn kèm Giấy chứng nhận kết hôn hợp lệ. Quản lý trực tiếp có phê duyệt hưởng 100% lương 3 ngày chế độ đặc biệt theo Điều 115 BLLĐ không?",
    vlm_analysis_json: {
      document_summary: {
        patient_name: "Võ Minh Khang",
        issuer: "UBND Phường Dịch Vọng Hậu",
        diagnosis: "Giấy chứng nhận kết hôn",
        issue_date: "2026-09-20",
        doctor_recommended_range: { from: "2026-10-05", to: "2026-10-07", days: 3 }
      },
      flags: { has_red_stamp: true, has_doctor_signature: true, document_readability: "CLEAR" },
      inspection_mode: "OLLAMA_REAL_QWEN25_VL_3B"
    },
    llm_summary_json: {
      decision: "ESCALATE",
      correlation_tier_vn: "Vượt thẩm quyền AI (Chuyển Quản lý)",
      summary_natural_vn: "Nhân viên nộp Giấy chứng nhận kết hôn hợp lệ do UBND Phường Dịch Vọng Hậu cấp. Đơn xin nghỉ 3 ngày chế độ kết hôn hưởng 100% lương theo Điều 115 BLLĐ.",
      manager_summary: {
        suspicions_vn: [],
        risk_level_vn: "Thấp"
      },
      why_escalated: "Theo quy chế, chế độ nghỉ việc riêng có hưởng lương (kết hôn) vượt thẩm quyền tự duyệt của AI và bắt buộc chuyển Quản lý trực tiếp xem xét.",
      quick_action_options_vn: ["Duyệt hưởng 100% lương 3 ngày", "Yêu cầu bổ sung thêm thông tin"],
      decision_tree_checklist: [
        { node_id: "RULE_01", node_name: "Xác thực Giấy chứng nhận kết hôn", result: "PASSED", note: "UBND Phường Dịch Vọng Hậu cấp, đúng tên nhân viên Võ Minh Khang" },
        { node_id: "RULE_02", node_name: "Thẩm quyền phê duyệt", result: "ESCALATED", note: "Nghỉ kết hôn 3 ngày hưởng nguyên lương vượt quyền AI -> Chuyển Quản lý" }
      ]
    }
  }
};

function openBenchmarkCaseDetail(caseId) {
  let caseData = BENCHMARK_CASES_DATA[caseId];
  if (!caseData) return;

  const benchmarkResult = window.__sprint1ResultsMap && window.__sprint1ResultsMap[caseId]
    ? window.__sprint1ResultsMap[caseId]
    : null;

  const mergedCase = {
    ...caseData,
    id: caseId,
    test_case_id: caseId,
    decision: benchmarkResult?.actual_decision || caseData.decision || caseData.expectedDecision || 'ESCALATE',
    status: benchmarkResult?.is_passed === false ? 'FAILED' : 'PENDING',
    is_passed: benchmarkResult ? benchmarkResult.is_passed !== false : caseData.is_passed !== false,
    expected_decision: benchmarkResult?.expected_decision || caseData.expectedDecision || caseData.decision,
    actionable_question: benchmarkResult?.actionable_question || caseData.actionable_question || caseData.actionableQuestion,
    human_readable_explanation: benchmarkResult?.plain_reason || caseData.human_readable_explanation || caseData.actionable_question,
    llm_summary_json: {
      ...(caseData.llm_summary_json || {}),
      ...(benchmarkResult ? {
        decision: benchmarkResult.actual_decision || caseData.decision || benchmarkResult.expected_decision,
        summary_natural_vn: benchmarkResult.plain_reason || caseData.llm_summary_json?.summary_natural_vn || caseData.actionable_question,
      } : {})
    }
  };

  const previousMode = currentMode;
  try {
    currentMode = 'manager';
    openRequestDetailModal(mergedCase);
  } finally {
    currentMode = previousMode;
  }
}
window.openBenchmarkCaseDetail = openBenchmarkCaseDetail;
window.BENCHMARK_CASES_DATA = BENCHMARK_CASES_DATA;


async function openRequestDetailModal(requestId) {
  let req = (typeof requestId === 'object' && requestId !== null)
    ? requestId
    : (activeRequests.find(r => r.id === requestId) || (typeof BENCHMARK_CASES_DATA !== "undefined" ? BENCHMARK_CASES_DATA[requestId] : null));
  if (!req) return;

  // Bản ghi danh sách không chứa checklist đầy đủ; lấy trace 13 node nếu là đơn thực tế trên server
  if (req.id && !String(req.id).startsWith("TC-")) {
    try {
      const analysisRes = await apiFetch(`${API_BASE}/api/leave/${req.id}/analysis`);
      if (analysisRes.ok) {
        const analysis = await analysisRes.json();
        req = Object.assign({}, req, analysis, {
          vlm_analysis_json: analysis.vlm_analysis || req.vlm_analysis_json,
          llm_summary_json: analysis.llm_summary || req.llm_summary_json,
        });
      }
    } catch (error) {
      console.warn('Không tải được checklist Decision Tree:', error);
    }
  }

  const modal = document.getElementById("modal-request-detail");
  const title = document.getElementById("modal-req-detail-title");
  const sub = document.getElementById("modal-req-detail-sub");
  const body = document.getElementById("modal-req-detail-body");
  const btnAudit = document.getElementById("btn-req-detail-view-audit");

  if (!modal || !body) return;

  if (title) {
    title.innerHTML = req.employee_name
      ? `CHI TIẾT ĐƠN NGHỈ PHÉP · ${escapeHtml(req.employee_name.toUpperCase())}`
      : 'CHI TIẾT ĐƠN NGHỈ PHÉP';
  }

  if (sub) {
    const deptInfo = req.department ? ` · Phòng ban: <strong class="text-dark">${escapeHtml(req.department)}</strong>` : '';
    const empInfo = req.employee_name ? ` · Nhân viên: <strong class="text-dark">${escapeHtml(req.employee_name)}${req.employee_id ? ` (${escapeHtml(req.employee_id)})` : ''}</strong>` : '';
    sub.innerHTML = `Mã đơn: <strong class="text-dark">${escapeHtml(req.id)}</strong>${empInfo}${deptInfo}`;
  }

  if (btnAudit) {
    if (String(req.id).startsWith("TC-")) {
      btnAudit.style.display = "none";
    } else {
      btnAudit.style.display = "";
      btnAudit.onclick = () => {
        closeRequestDetailModal();
        viewAuditTrail(req.id);
      };
    }
  }

  // Lấy tên nhân sự bàn giao thay vì mã ID
  const allEmps = (typeof employeesCache !== "undefined" && Array.isArray(employeesCache) && employeesCache.length > 0)
    ? employeesCache 
    : ((typeof DEFAULT_EMPLOYEES !== "undefined") ? DEFAULT_EMPLOYEES : []);
  const handoverEmp = allEmps.find(e => e.employee_id === req.handover_person_id || e.id === req.handover_person_id);
  const handoverDisplayName = handoverEmp ? `${handoverEmp.name} (${handoverEmp.department || 'Đồng nghiệp'})` : (req.handover_person_name || req.handover_person_id || "Không yêu cầu");

  const hasAttachment = !!(req.proof_id || req.proof_file);
  const attachLabel = hasAttachment ? (req.proof_file || req.proof_id || 'Chứng từ đính kèm') : 'Không có';

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
    .replace(/^H\u1ec7 th\u1ed1ng chuy\u1ec3n ti\u1ebfp do:\s*/i, "")
    .replace(/^Minh b\u1ea1ch AI & C\u0103n c\u1ee9 x\u1eed l\u00fd:\s*/i, "")
    .trim();

  // ── VLM extracted data (Technical facts only) ─────────────────────────────
  const _vlm = req.vlm_analysis_json || {};
  const _vlmFields = req.vlm_fields || {};
  const _vlmDocBase = _vlm.document_summary || {};
  const _vlmDoc = {
    patient_name: (_vlmDocBase.patient_name ?? _vlmFields.doc_patient_name ?? null),
    diagnosis: (_vlmDocBase.diagnosis ?? _vlmFields.doc_diagnosis ?? null),
    issuer: (_vlmDocBase.issuer ?? null),
    issue_date: (_vlmDocBase.issue_date ?? null),
    doctor_recommended_range: (_vlmDocBase.doctor_recommended_range || {})
  };
  const _vlmFlags = _vlm.flags || {};
  const _vlmCorr = _vlm.correlation_analysis || {};
  const _vlmMode = _vlm.inspection_mode || "";
  const _vlmErr = _vlm.vlm_error || "";
  const _hasVlm = hasAttachment && !!(req.vlm_analysis_json && Object.keys(req.vlm_analysis_json).length);

  function _boolBadge(val, trueL, falseL) {
    if (val === true)  return '<span style="background:#dcfce7;color:#166534;padding:2px 9px;border-radius:5px;font-size:0.78rem;font-weight:600;">\u2713 ' + trueL + '</span>';
    if (val === false) return '<span style="background:#fee2e2;color:#991b1b;padding:2px 9px;border-radius:5px;font-size:0.78rem;font-weight:600;">\u2717 ' + falseL + '</span>';
    return '<span style="background:#f1f5f9;color:#64748b;padding:2px 9px;border-radius:5px;font-size:0.78rem;">\u2014 Ch\u01b0a x\u00e1c \u0111\u1ecbnh</span>';
  }
  function _nv(v, fallback) {
    return v ? '<span style="font-weight:600;color:#0f172a;">' + escapeHtml(String(v)) + '</span>' : '<span style="color:#94a3b8;">\u2014 ' + fallback + '</span>';
  }

  let _vlmModeBadge = '';
  if (_vlmMode === 'OLLAMA_REAL_QWEN25_VL_3B' || _vlmMode.startsWith('OLLAMA_REAL')) _vlmModeBadge = '<span class="ai-engine-badge">\uD83E\uDD16 AI Engine</span>';
  else if (_vlmMode.includes('UNAVAILABLE') || _vlmMode.includes('ERROR')) _vlmModeBadge = '<span style="background:#fee2e2;color:#991b1b;font-size:0.72rem;padding:2px 8px;border-radius:4px;font-weight:600;">\u26a0 VLM L\u1ed7i / Ch\u01b0a c\u00f3 model</span>';
  else if (_vlmMode) _vlmModeBadge = '<span style="background:#f1f5f9;color:#475569;font-size:0.72rem;padding:2px 8px;border-radius:4px;">' + escapeHtml(_vlmMode) + '</span>';

  let _vlmSection = '';
  if (_hasVlm) {
    const _dr = _vlmDoc.doctor_recommended_range || {};

    _vlmSection = '<div class="col-12" style="margin-top:4px;">'
      + '<div style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;background:#ffffff;">'
      + '<div style="background:linear-gradient(135deg,#f8fafc,#f1f5f9);padding:10px 16px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">'
      + '<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:1rem;">\uD83E\uDD16</span><span style="font-weight:700;color:#0f172a;font-size:0.9rem;">Th\u00f4ng tin tr\u00edch xu\u1ea5t t\u1eeb ch\u1ee9ng t\u1eeb (AI Engine)</span>' + _vlmModeBadge + '</div>'
      + (_vlmErr ? '<span style="background:#fee2e2;color:#991b1b;font-size:0.72rem;padding:2px 8px;border-radius:4px;" title="' + escapeHtml(_vlmErr) + '">\u26a0 ' + escapeHtml(_vlmErr.substring(0,75)) + (_vlmErr.length>75?'\u2026':'') + '</span>' : '')
      + '</div>'
      + '<div style="padding:12px 16px;display:grid;grid-template-columns:1fr 1fr;gap:8px 16px;">'
      + '<div><div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;margin-bottom:2px;">T\u00ean tr\u00ean ch\u1ee9ng t\u1eeb</div><div style="font-size:0.86rem;">' + _nv(_vlmDoc.patient_name, 'Kh\u00f4ng \u0111\u1ecdc \u0111\u01b0\u1ee3c') + '</div></div>'
      + '<div><div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;margin-bottom:2px;">N\u01a1i c\u1ea5p gi\u1ea5y</div><div style="font-size:0.86rem;">' + _nv(_vlmDoc.issuer, 'Kh\u00f4ng \u0111\u1ecdc \u0111\u01b0\u1ee3c') + '</div></div>'
      + '<div style="grid-column:span 2;"><div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;margin-bottom:2px;">Ch\u1ea9n \u0111o\u00e1n / L\u00fd do gi\u1ea5y</div><div style="font-size:0.86rem;">' + _nv(_vlmDoc.diagnosis, 'Kh\u00f4ng \u0111\u1ecdc \u0111\u01b0\u1ee3c') + '</div></div>'
      + '<div><div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;margin-bottom:2px;">Ng\u00e0y c\u1ea5p</div><div style="font-size:0.86rem;">' + _nv(_vlmDoc.issue_date, 'Kh\u00f4ng c\u00f3') + '</div></div>'
      + '<div><div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;margin-bottom:2px;">Kho\u1ea3ng ng\u00e0y b\u00e1c s\u0129 ch\u1ec9 \u0111\u1ecbnh</div><div style="font-size:0.86rem;">' + (_dr.from && _dr.to ? '<span style="font-weight:600;color:#0f172a;">' + escapeHtml(_dr.from) + ' \u2192 ' + escapeHtml(_dr.to) + '</span>' + (_dr.days !== null && _dr.days !== undefined ? ' <span style="color:#2563eb;font-size:0.8rem;">(' + _dr.days + ' ng\u00e0y)</span>' : '') : '<span style="color:#94a3b8;">\u2014 Kh\u00f4ng \u0111\u1ecdc \u0111\u01b0\u1ee3c</span>') + '</div></div>'
      + '</div>'
      + '<div style="padding:0 16px 10px 16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;">'
      + (_vlmFlags.has_red_stamp !== undefined && _vlmFlags.has_red_stamp !== null ? _boolBadge(_vlmFlags.has_red_stamp, 'Có dấu đỏ', 'Thiếu dấu đỏ') : '')
      + (_vlmFlags.has_doctor_signature !== undefined && _vlmFlags.has_doctor_signature !== null ? _boolBadge(_vlmFlags.has_doctor_signature, 'Có chữ ký', 'Thiếu chữ ký') : '')
      + (_vlmFlags.signature_present_on_scan !== undefined && _vlmFlags.signature_present_on_scan !== null && _vlmFlags.has_doctor_signature === undefined ? _boolBadge(_vlmFlags.signature_present_on_scan, 'Có chữ ký', 'Thiếu chữ ký') : '')
      + (_vlmFlags.document_readability ? '<span style="background:#f1f5f9;color:#475569;padding:2px 9px;border-radius:5px;font-size:0.78rem;">Độ rõ: ' + escapeHtml(_vlmFlags.document_readability) + '</span>' : '')
      + '</div>'
      + '</div></div>';
  }

  // ── LLM Summary & Synthesis data (Core Reasoning) ──────────────────────────
  const _llm = req.llm_summary_json || {};
  const _hasLlm = !!(req.llm_summary_json);
  let _llmSection = '';
  if (_hasLlm) {
    const _isManagerAudience = currentMode === 'manager';
    const _rawDecision = req.decision || (req.result_json && req.result_json.decision) || _llm.decision || '';
    const _decisionForAudience = String(_rawDecision).toUpperCase();
    const _isStaffCorrection = _decisionForAudience === 'NEED_CORRECTION';
    const _isAutoRejected = _decisionForAudience === 'AUTO_REJECT';
    const _isAutoApproved = _decisionForAudience === 'AUTO_APPROVE';
    const _isNoLeave = ['NO_LEAVE_REQUIRED', 'NO_LEAVE', 'NO_LEAVE_NEEDED'].includes(_decisionForAudience);
    const _legacyStaffErrors = ['NEED_CORRECTION', 'AUTO_REJECT'].includes(_decisionForAudience)
      ? (_llm.staff_errors_vn || _llm.info_missing_vn || [])
      : [];
    const _audienceSummary = _isManagerAudience
      ? (_llm.manager_summary || {suspicions_vn: _llm.info_missing_vn || [], risk_level_vn: '—'})
      : (_llm.staff_summary || {errors_vn: _legacyStaffErrors});
    const _whyEsc = _isManagerAudience ? (_llm.why_escalated || '') : '';
    const _tier = _llm.correlation_tier_vn || '';
    const _aq = _isManagerAudience ? (_llm.actionable_question || '') : '';
    const _managerSummary = _isManagerAudience
      ? (_llm.summary_natural_vn || _llm.manager_summary?.summary_natural_vn || '')
      : '';
    const _pvn = _isManagerAudience ? (_llm.applied_policy_clauses_vn || []) : [];
    const _qvn = _isManagerAudience ? (_llm.quick_action_options_vn || []) : [];
    const _warns = _isManagerAudience ? (_llm.warnings || []) : [];
    const _riskLevel = _audienceSummary.risk_level_vn || _llm.manager_risk_level_vn || '';
    const _tierC = _tier === 'RẤT KHỚP' ? '#059669' : _tier === 'KHỚP' ? '#2563eb' : _tier === 'CHƯA KHỚP' ? '#d97706' : _tier === 'KHÔNG KHỚP' ? '#dc2626' : '#059669';
    const _treeNodes = Array.isArray(req.decision_tree_checklist) ? req.decision_tree_checklist : [];
    const _hiddenTreeStages = new Set(['FINAL_DECISION', 'LLM_SUMMARY']);
    const _displayTreeNodes = _treeNodes.filter(function(node) {
      if (_hiddenTreeStages.has(node.stage)) return false;
      if (String(req.decision || '').toUpperCase() === 'AUTO_APPROVE' && ['PROOF_VERIFICATION', 'AUTHORITY'].includes(node.stage)) return false;
      if (node.stage === 'AUTHORITY' && ['NONE', 'EMPLOYEE'].includes(String(req.target_role || 'NONE').toUpperCase())) return false;
      if (node.stage === 'AUTHORITY') return false;
      return true;
    }).reduce(function(acc, node) {
      if (node.stage === 'VLM_INTEGRITY' && _treeNodes.some(function(other) { return other.stage === 'PROOF'; })) {
        const proofNode = acc.find(function(item) { return item.stage === 'PROOF'; });
        if (proofNode) {
          const noteParts = [String(proofNode.note || ''), String(node.note || '')].filter(Boolean);
          proofNode.note = noteParts.join(' • ');
          if (node.status === 'FAIL' || proofNode.status === 'FAIL') {
            proofNode.status = 'FAIL';
            proofNode.passed = false;
          } else if (node.status !== 'PASS' || proofNode.status !== 'PASS') {
            proofNode.status = (node.status !== 'PASS') ? node.status : proofNode.status;
            proofNode.passed = false;
          }
          return acc;
        }
      }
      acc.push(node);
      return acc;
    }, []);
    const _passedNodes = _displayTreeNodes.filter(function(node) { return node.status === 'PASS'; });
    const _reviewNodes = _displayTreeNodes.filter(function(node) { return node.status !== 'PASS' && node.status !== 'NOT_RUN'; });

    function _renderTreeNode(node, isReview) {
      const shortTitles = {
        VALIDATION: 'Thông tin nhân sự',
        BALANCE: 'Số dư phép',
        PROOF: 'Chứng từ',
        VLM_INTEGRITY: 'Chứng từ',
        VLM_PATIENT: 'Tên trên chứng từ',
        VLM_DATE_COVERAGE: 'Khoảng ngày nghỉ',
        VLM_CORRELATION: 'Độ khớp nội dung',
        PROOF_VERIFICATION: 'Xác minh chứng từ',
        AUTHORITY: 'Thẩm quyền duyệt',
        NOTICE: 'Thời hạn báo trước',
        TEAM_QUOTA: 'Tỷ lệ nghỉ trong team',
      };
      const color = isReview ? '#b91c1c' : '#065f46';
      const title = shortTitles[node.stage] || node.title_vi || node.stage || 'Kiểm tra hồ sơ';
      const compactNote = String(node.note || '')
        .replaceAll('MEDICAL_LEAVE_CERTIFICATE', 'Giấy chứng nhận nghỉ ốm')
        .replaceAll('HOSPITAL_DISCHARGE', 'Giấy ra viện')
        .replaceAll('PROOF_REVIEW_REQUIRED', 'Đủ thông tin, không cần xác minh bổ sung')
        .replaceAll('Xác minh chứng từ', 'Đủ thông tin chứng từ')
        .replaceAll('Thẩm quyền duyệt', '')
        .replaceAll('Điều kiện duyệt', '')
        .replace(/\s*\([^)]*\)/g, '')
        .replace(/\s*•\s*/g, ' • ')
        .replace(/\s*·\s*/g, ' • ')
        .replace(/\s*;\s*/g, ' • ')
        .replace(/\s+/g, ' ')
        .trim();
      const noteItems = compactNote ? compactNote.split(' • ').map(function(item) {
        const clean = item.trim();
        if (!clean) return '';
        if (!isReview && /error_code|uncertainty_category|DIRECT_MANAGER|DEPARTMENT_HEAD|CEO|HR|AUTHORITY|thẩm quyền|cần.*duyệt|cần.*xem xét|xác minh chứng từ|chưa đọc được|không đọc được|không có|Trường còn thiếu|N\/A|undefined|null|unknown/i.test(clean)) return '';
        if (isReview && /^(error_code|uncertainty_category|DIRECT_MANAGER|DEPARTMENT_HEAD|CEO|HR|AUTHORITY|thẩm quyền|N\/A|undefined|null|unknown)$/i.test(clean)) return '';
        return '<div style="font-size:0.74rem;color:#64748b;margin:2px 0 2px 20px;line-height:1.4;">• ' + escapeHtml(clean) + '</div>';
      }).filter(Boolean).join('') : '';
      return '<div style="font-size:0.82rem;color:' + color + ';padding:3px 0;line-height:1.45;">'
        + '<span style="margin-right:6px;font-weight:700;">•</span>'
        + '<strong>' + escapeHtml(title) + '</strong>'
        + noteItems
        + '</div>';
    }

    // Chỉ hiển thị lỗi khi Decision Tree thực sự yêu cầu sửa hoặc từ chối.
    let _infoSuf = _isManagerAudience || (!_isStaffCorrection && !_isAutoRejected)
      ? [] : (_audienceSummary.errors_vn || _legacyStaffErrors);
    let _infoMis = _isManagerAudience
      ? (_audienceSummary.suspicions_vn || _llm.manager_suspicions_vn || [])
      : (_llm.info_missing_vn || []);

    if (!_isManagerAudience && _isStaffCorrection && _infoSuf.length === 0 && hasAttachment) {
      if (_vlmFlags && _vlmFlags.has_red_stamp === false) _infoSuf.push('Thiếu dấu mộc đỏ bệnh viện/phòng khám');
      if (_vlmFlags && _vlmFlags.has_doctor_signature === false) _infoSuf.push('Thiếu chữ ký bác sĩ / người cấp giấy');
      if (_vlmDoc && !_vlmDoc.patient_name) _infoSuf.push('Chưa đọc được tên trên chứng từ');
    }

    const _staffPanelTitle = _isAutoApproved ? 'Kết quả đối soát'
      : _isNoLeave ? 'Kết quả ngày nghỉ'
      : _isStaffCorrection || _isAutoRejected ? 'Thông tin cần xử lý'
      : 'Kết quả xử lý AI Engine';
    const _timings = _llm.timings || {};
    const _timingBadge = (_timings.rule_engine_ms !== undefined && _timings.template_ms !== undefined)
      ? '<span style="font-size:0.72rem;color:#6b21a8;background:#f3e8ff;padding:2px 8px;border-radius:4px;font-weight:600;" title="Rule Engine: ' + _timings.rule_engine_ms + 'ms, Template: ' + _timings.template_ms + 'ms">⚡ ' + (_timings.total_eval_ms || Math.round((_timings.rule_engine_ms + _timings.template_ms)*10)/10) + 'ms</span>'
      : '';

    _llmSection = '<div class="col-12" style="margin-top:4px;">'
      + '<div style="border:1px solid #c084fc;border-radius:12px;overflow:hidden;background:#ffffff;box-shadow:0 2px 8px rgba(147,51,234,0.06);">'
      + '<div style="background:linear-gradient(135deg,#faf5ff,#f3e8ff);padding:12px 16px;border-bottom:1px solid #e9d5ff;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">'
      + '<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:1.1rem;">🧠</span><span style="font-weight:700;color:#4c1d95;font-size:0.86rem;">' + (_isManagerAudience ? 'Nhận định nghi vấn cho Manager' : _staffPanelTitle) + '</span>'
      + '<span class="ai-engine-badge">✓ AI Engine</span>'
      + _timingBadge
      + '</div>'
      + (_tier && _tier !== '—' ? '<span style="background:' + _tierC + '20;color:' + _tierC + ';font-size:0.78rem;padding:3px 10px;border-radius:5px;font-weight:700;">' + escapeHtml(_tier) + '</span>' : '')
      + '</div>'
      + (_isManagerAudience && _riskLevel ? '<div style="padding:8px 16px;border-bottom:1px solid #f3e8ff;font-size:0.8rem;color:#92400e;font-weight:700;">Mức rủi ro: ' + escapeHtml(_riskLevel) + '</div>' : '')

        + (_managerSummary ? '<div style="padding:12px 16px;border-bottom:1px solid #f3e8ff;background:#ffffff;">'
          + '<div style="font-size:0.72rem;color:#7c3aed;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:6px;">Tóm tắt ngắn</div>'
          + '<div style="font-size:0.86rem;color:#334155;line-height:1.55;white-space:pre-line;">' + escapeHtml(_managerSummary) + '</div>'
          + '</div>' : '')
      
      // Checklist ngắn gọn theo rule đã chạy
      + '<div style="padding:12px 16px;border-bottom:1px solid #f3e8ff;background:#faf5ff50;display:grid;grid-template-columns:' + (_reviewNodes.length ? 'repeat(auto-fit,minmax(240px,1fr))' : '1fr') + ';gap:16px;">'
      + '<div>'
      + '<div style="font-size:0.72rem;color:#059669;font-weight:700;text-transform:uppercase;margin-bottom:6px;">ĐẠT</div>'
      + (_passedNodes.length ? _passedNodes.map(function(node){ return _renderTreeNode(node, false); }).join('') : '<div style="font-size:0.81rem;color:#64748b;">Chưa có tiêu chí đạt.</div>')
      + '</div>'
      + (_reviewNodes.length ? '<div>'
      + '<div style="font-size:0.72rem;color:#dc2626;font-weight:700;text-transform:uppercase;margin-bottom:6px;">KHÔNG ĐẠT</div>'
      + _reviewNodes.map(function(node){ return _renderTreeNode(node, true); }).join('')
      + '</div>' : '')
      + '</div>'

      // Câu hỏi xử lý ngắn cho Manager (nếu có)
      + ((_aq || _whyEsc || _qvn.length > 0) ? '<div style="padding:12px 16px;background:#f8fafc;border-top:1px solid #f1f5f9;">'
          + '<div style="font-size:0.72rem;color:#7c3aed;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;">Xử lý</div>'
          + (_whyEsc ? '<div style="font-size:0.8rem;color:#475569;margin-bottom:6px;"><span style="font-weight:600;color:#6b21a8;">Lý do:</span> ' + escapeHtml(_whyEsc) + '</div>' : '')
          + (_aq ? '<div style="font-size:0.88rem;color:#1e1b4b;font-weight:600;padding:8px 12px;background:#ede9fe;border-radius:8px;border-left:4px solid #7c3aed;margin-bottom:8px;">❓ ' + escapeHtml(_aq) + '</div>' : '')
          + (_qvn.length > 0 ? '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;"><span style="font-size:0.75rem;color:#64748b;font-weight:600;">Nên:</span>' + _qvn.map(function(q){ return '<span style="background:#ffffff;border:1px solid #cbd5e1;color:#334155;font-size:0.76rem;padding:2px 8px;border-radius:5px;font-weight:500;">' + escapeHtml(String(q)) + '</span>'; }).join('') + '</div>' : '')
          + '</div>' : '')

      + ((_pvn.length > 0 || _warns.length > 0) ? '<div style="padding:8px 16px;border-top:1px solid #f1f5f9;font-size:0.76rem;color:#64748b;display:flex;flex-wrap:wrap;gap:12px;">'
          + (_pvn.length > 0 ? '<div><span style="font-weight:600;color:#7c3aed;">Chính sách:</span> ' + _pvn.map(function(p){ return escapeHtml(String(p)); }).join('; ') + '</div>' : '')
          + (_warns.length > 0 ? '<div><span style="font-weight:600;color:#dc2626;">Cảnh báo:</span> ' + _warns.map(function(w){ return escapeHtml(String(w)); }).join('; ') + '</div>' : '')
          + '</div>' : '')
      + '</div></div>';
  }

  body.innerHTML = `
    <div class="row g-3">
      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">Lo\u1ea1i ngh\u1ec9 ph\u00e9p</label>
        <div class="modal-readonly-field">
          <span class="text-dark fw-semibold">${getLeaveTypeLabel(req.leave_type)}</span>
        </div>
      </div>

      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">Ng\u01b0\u1eddi nh\u1eadn b\u00e0n giao</label>
        <div class="modal-readonly-field">
          <span class="text-dark">${handoverDisplayName}</span>
        </div>
      </div>

      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">T\u1eeb ng\u00e0y</label>
        <div class="modal-readonly-field">
          <span class="text-dark">${formatSimpleDate(req.from_date)}</span>
        </div>
      </div>

      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">\u0110\u1ebfn ng\u00e0y</label>
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
            <span class="text-secondary small">Th\u1eddi l\u01b0\u1ee3ng v\u1eafng m\u1eb7t:</span>
            <span class="fw-bold text-dark">${req.requested_working_days ?? req.workdays ?? 0} ng\u00e0y l\u00e0m vi\u1ec7c</span>
          </div>
          <div>
            ${getStatusBadgeHtml(req)}
          </div>
        </div>
      </div>

      <div class="col-12">
        <label class="form-label text-secondary small fw-semibold mb-1">L\u00fd do ngh\u1ec9</label>
        <div class="modal-readonly-textarea">${req.reason || 'Kh\u00f4ng c\u00f3 m\u00f4 t\u1ea3 chi ti\u1ebft'}</div>
      </div>

      <div class="col-12">
        <label class="form-label text-secondary small fw-semibold mb-1">Ch\u1ee9ng t\u1eeb x\u00e1c minh</label>
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
              <div class="text-secondary" style="font-size: 0.75rem;">${hasAttachment ? 'T\u00e0i li\u1ec7u \u0111\u00ednh k\u00e8m h\u1ed3 s\u01a1' : 'Kh\u00f4ng c\u00f3 ch\u1ee9ng t\u1eeb \u0111\u00ednh k\u00e8m'}</div>
            </div>
          </div>
          ${hasAttachment ? (
            (req.proof_file || String(req.id).startsWith('TC-'))
              ? `<button type="button" class="btn btn-sm btn-outline-primary px-3" onclick="openImageLightbox('assets/proofs/${req.proof_file || req.proof_id}', '${req.proof_file || req.proof_id}')" style="font-size: 0.8rem; font-weight: 500;">
                  Xem ảnh gốc
                </button>`
              : `<button type="button" class="btn btn-sm btn-outline-primary px-3" onclick="openAttachmentModal('${req.id}', '${req.attachment_type}', '${req.employee_name}')" style="font-size: 0.8rem; font-weight: 500;">
                  Xem ảnh gốc
                </button>`
          ) : ''}
        </div>
      </div>

      ${_vlmSection}
      ${_llmSection}

      <!-- K\u1ebft qu\u1ea3 \u0111\u00e1nh gi\u00e1 AI / Qu\u1ea3n l\u00fd -->
      <div class="col-12">
        <label class="form-label text-secondary small fw-semibold mb-1">K\u1ebft qu\u1ea3 \u0111\u00e1nh gi\u00e1 & X\u1eed l\u00fd</label>
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

    // Bảng màu hài hòa, dịu mắt, có điểm nhấn theo từng loại nghỉ
    let typeBg = '#eff6ff';
    let typeColor = '#2563eb';
    let typeBorder = '#dbeafe';
    const norm = String(r.leave_type || '').toUpperCase();
    if (norm.includes('SICK') || norm.includes('MEDICAL')) {
      typeBg = '#fff1f2';
      typeColor = '#e11d48';
      typeBorder = '#ffe4e6';
    } else if (norm.includes('ANNUAL')) {
      typeBg = '#f0fdf4';
      typeColor = '#16a34a';
      typeBorder = '#dcfce7';
    } else if (norm.includes('SPECIAL')) {
      typeBg = '#faf5ff';
      typeColor = '#7c3aed';
      typeBorder = '#f3e8ff';
    } else if (norm.includes('UNPAID')) {
      typeBg = '#f8fafc';
      typeColor = '#475569';
      typeBorder = '#e2e8f0';
    }

    return `
      <div class="escalation-inbox-card" id="esc-card-${r.id}">
        <!-- Dòng Header: Tên nhân sự (Đã bỏ huy hiệu chờ người có thẩm quyền) -->
        <div class="d-flex align-items-center mb-3">
          <span style="font-size: 1.25rem; font-weight: 700; color: #0f172a; letter-spacing: -0.015em;">
            ${escapeHtml(r.employee_name || 'Nhân viên')}
          </span>
        </div>

        <!-- Khối Thông Tin: 3 thẻ pill riêng biệt theo hình mẫu -->
        <div class="esc-pills-row">
          <div class="esc-info-pill">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 7H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"></path>
              <rect x="9" y="3" width="6" height="4" rx="1"></rect>
              <line x1="12" y1="11" x2="12" y2="15"></line>
              <line x1="10" y1="13" x2="14" y2="13"></line>
            </svg>
            <span class="esc-pill-label">Loại nghỉ:</span>
            <span class="badge fw-semibold px-2 py-0.5" style="background: ${typeBg}; color: ${typeColor}; border: 1px solid ${typeBorder}; border-radius: 6px; font-size: 0.82rem;">
              ${escapeHtml(leaveLabel)}
            </span>
          </div>

          <div class="esc-info-pill">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
            </svg>
            <span class="esc-pill-label">Ngày nộp:</span>
            <span class="esc-pill-value">${escapeHtml(submitDate)}</span>
          </div>

          <div class="esc-info-pill">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <span class="esc-pill-label">Số ngày nghỉ:</span>
            <span class="esc-pill-value">${workDays} ngày</span>
          </div>
        </div>

        <!-- Khối Lý Do Nghỉ: Thanh ngang nền xám nhạt kèm icon tài liệu -->
        <div class="esc-reason-bar mb-3">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="flex-shrink-0">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10 9 9 9 8 9"></polyline>
          </svg>
          <span class="esc-reason-label">Lý do nghỉ:</span>
          <span class="esc-reason-text">${escapeHtml(r.reason || 'Không có mô tả chi tiết')}</span>
        </div>

        <!-- Khu vực Xử lý của Quản lý & Nút bấm theo đúng hình mẫu -->
        <div class="d-flex flex-column gap-2 pt-1">
          <div>
            <input type="text" id="esc-feedback-${r.id}" class="form-control" placeholder="Nhập ý kiến chỉ đạo / phản hồi (nếu có)..." style="border-radius: 8px; font-size: 0.88rem; padding: 10px 16px; border: 1px solid #cbd5e1; background: #ffffff;">
          </div>
          <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 pt-1">
            <!-- Nút Chi tiết bên trái -->
            <button type="button" class="btn btn-action-detail d-inline-flex align-items-center gap-1.5" onclick="openRequestDetailModal('${r.id}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
              </svg>
              Chi tiết
            </button>

            <!-- Cụm nút hành động bên phải: Duyệt -> Yêu cầu bổ sung -> Từ chối (Tone màu hài hòa, dịu mắt) -->
            <div class="d-flex align-items-center gap-2">
              ${r.target_role !== 'HR' ? `
                <button type="button" class="btn btn-action-approve d-inline-flex align-items-center gap-1.5" onclick="submitManagerDecision('${r.id}','APPROVE')">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                  Duyệt
                </button>
              ` : ''}
              <button type="button" class="btn btn-action-warn d-inline-flex align-items-center gap-1.5" onclick="submitManagerDecision('${r.id}','REQUEST_MORE_INFO')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
                Yêu cầu bổ sung
              </button>
              <button type="button" class="btn btn-action-reject d-inline-flex align-items-center gap-1.5" onclick="submitManagerDecision('${r.id}','REJECT')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                Từ chối
              </button>
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
    const updated = data.data;
    const index = activeRequests.findIndex(r => r.id === id);
    if (index >= 0) activeRequests[index] = updated;
    updateBadgesAndCounters();
    renderManagerOverviewKPIs();
    renderManagerQueue();
    renderManagerAllRequests();
    showToast('Đã ghi nhận: '+updated.status,'info');
    await Promise.all([loadAllRequests(true), loadEmployees()]);
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
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-secondary py-4">Chưa có đơn nào được AI tự động duyệt trong phiên làm việc này.</td></tr>`;
    return;
  }

  tbody.innerHTML = autoRequests.map(req => {
    return `
      <tr>
        <td><b>${escapeHtml(req.employee_name)}</b></td>
        <td><span class="badge bg-secondary-lt">${escapeHtml(req.department)}</span></td>
        <td>${escapeHtml(req.from_date)} → ${escapeHtml(req.to_date)}</td>
        <td><b>${req.requested_working_days ?? req.workdays ?? 0} ngày</b></td>
        <td>
          <button class="btn btn-sm btn-outline-primary px-2.5 py-1" onclick="openRequestDetailModal('${req.id}')" title="Xem chi tiết đơn nghỉ phép">
            Chi tiết
          </button>
        </td>
        <td>
          <button class="btn btn-sm btn-outline-danger px-2.5 py-1" onclick="revokeAiApproval('${req.id}')" title="Thu hồi quyết định tự động của AI và hoàn trả quỹ phép">
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
    if (filterVal === "CANCELLED") {
      list = list.filter(r => r.status === "CANCELLED" || r.human_resolution === "REVOKED");
    } else {
      list = list.filter(r => r.status === filterVal || r.decision === filterVal);
    }
  }

  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-secondary py-4">Không tìm thấy hồ sơ đơn nào.</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(req => `
    <tr>
      <td><b>${escapeHtml(req.employee_name)}</b></td>
      <td><span class="badge bg-secondary-lt">${escapeHtml(req.department)}</span></td>
      <td>${escapeHtml(req.from_date)} → ${escapeHtml(req.to_date)}</td>
      <td><b>${req.requested_working_days ?? req.workdays ?? 0} ngày</b></td>
      <td>${getStatusBadgeHtml(req)}</td>
      <td>
        <button class="btn btn-sm btn-outline-primary px-2.5 py-1" onclick="openRequestDetailModal('${req.id}')" title="Xem chi tiết đơn nghỉ phép">
          Chi tiết
        </button>
      </td>
    </tr>
  `).join("");

  const mgrFilter = document.getElementById("mgr-filter-status");
  if (mgrFilter && !mgrFilter.hasAttribute("data-bound")) {
    mgrFilter.setAttribute("data-bound", "true");
    mgrFilter.addEventListener("change", renderManagerAllRequests);
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
  const proofUrl=req.proof_id?`${API_BASE}/api/leave/proofs/${req.proof_id}?actor_id=${encodeURIComponent(actorId)}`:'';
  const mime=(data.proof_source&&data.proof_source.mime_type)||'';
  const fileName=escapeHtml((data.proof_source&&data.proof_source.original_file_name)||'Chứng từ gốc');
  const isPdf=mime==='application/pdf'||/\.pdf$/i.test(fileName);
  const viewer=req.proof_id?(isPdf
    ?`<div class="proof-original-viewer"><iframe class="proof-original-frame" src="${proofUrl}" title="${fileName}"></iframe></div>`
    :`<div class="proof-original-viewer"><img class="proof-original-image" src="${proofUrl}" alt="${fileName}"></div>`)
    :'<p class="text-secondary mb-0">Không có file chứng từ.</p>';
  content.innerHTML=`${viewer}
    ${req.proof_id?`<div class="d-flex justify-content-between align-items-center mt-3 mb-2"><span class="small text-secondary">${fileName}</span><a class="btn btn-sm btn-outline-secondary" href="${proofUrl}" target="_blank" rel="noopener">Mở tab mới</a></div>`:''}
    ${renderVlmAndLlmAnalysisSection(req)}
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
      const req = json.data || {};
      const logs = json.audit_trail || [];
      const eventTimeline = [];
      const hasManagerApproval = logs.some(log => String(log.action || '').toUpperCase() === 'APPROVE_OVERRIDE');
      if (req.submitted_at) {
        eventTimeline.push({
          title: 'Nhân viên nộp đơn',
          action: 'Đã tiếp nhận',
          time: req.submitted_at,
          details: `Hồ sơ ${req.id || requestId} được ghi nhận vào hệ thống.`
        });
      }
      logs.forEach(log => {
        const action = String(log.action || '').toUpperCase();
        if (action === 'HUMAN_APPROVAL') return;
        let event = null;
        if (action === 'EVALUATED') {
          let evaluated = {};
          try { evaluated = JSON.parse(log.details || '{}'); } catch (_) {}
          const decision = String(evaluated.decision || req.decision || '').toUpperCase();
          if (hasManagerApproval && decision === 'AUTO_APPROVE') return;
          const eventMap = {
            AUTO_APPROVE: ['AI chấp nhận tự động', 'Đơn hợp lệ và đủ điều kiện tự động duyệt.'],
            ESCALATE: ['AI chuyển tiếp', `Đã chuyển ${getRoleLabel(evaluated.target_role || req.target_role)} xử lý.`],
            NEED_CORRECTION: ['AI yêu cầu bổ sung', 'Hồ sơ cần nhân viên sửa hoặc bổ sung thông tin.'],
            AUTO_REJECT: ['AI từ chối', 'Hồ sơ bị từ chối theo quy tắc.'],
            NO_LEAVE_REQUIRED: ['AI kết luận không phát sinh phép', 'Khoảng thời gian không có ngày làm việc cần ghi nhận.']
          };
          const mapped = eventMap[decision] || ['AI hoàn tất đánh giá', 'Decision Tree đã hoàn tất đánh giá hồ sơ.'];
          event = { title: mapped[0], action: 'AI Engine', time: log.created_at, details: mapped[1] };
        } else if (action === 'APPROVE_OVERRIDE') {
          event = { title: 'Manager chấp nhận', action: 'Đã duyệt', time: log.created_at, details: log.details || 'Manager đã phê duyệt đơn.' };
        } else if (action === 'REQUEST_MORE_INFO') {
          event = { title: 'Manager yêu cầu bổ sung', action: 'Chờ nhân viên', time: log.created_at, details: log.details || 'Manager yêu cầu bổ sung thông tin.' };
        } else if (action === 'REJECT') {
          event = { title: 'Manager từ chối', action: 'Đã từ chối', time: log.created_at, details: log.details || 'Manager đã từ chối đơn.' };
        } else if (action === 'CANCEL' || action === 'REVOKE') {
          event = { title: action === 'CANCEL' ? 'Nhân viên hủy đơn' : 'Thu hồi quyết định', action: 'Đã cập nhật', time: log.created_at, details: log.details || '' };
        } else if (action === 'EMPLOYEE_RESUBMIT') {
          event = { title: 'Nhân viên nộp lại hồ sơ', action: 'Đã tiếp nhận', time: log.created_at, details: 'Hồ sơ đã được gửi lại để Decision Tree đánh giá.' };
        }
        if (event) eventTimeline.push(event);
      });
      if (eventTimeline.length === 0) {
        timeline.innerHTML = `<div style="color: var(--text-dim);">Chưa có nhật ký ghi nhận.</div>`;
      } else {
        timeline.innerHTML = eventTimeline.map(l => `
          <div class="timeline-item">
            <div class="timeline-dot"></div>
            <div class="timeline-title">${escapeHtml(l.title)} — <span style="font-weight: 600; color: var(--primary);">${escapeHtml(l.action)}</span></div>
            <div class="timeline-time">${formatTime(l.time)}</div>
            <div class="timeline-desc">${escapeHtml(l.details)}</div>
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
              <td><span class="badge bg-blue-lt fw-bold">${getDecisionLabel(r.expected_decision)}</span></td>
              <td><span class="badge ${r.actual_decision === 'AUTO_APPROVE' ? 'bg-success-lt' : 'bg-warning-lt'} fw-bold">${getDecisionLabel(r.actual_decision)}</span></td>
              <td>${getCategoryLabel(r.actual_category || r.expected_category)}</td>
              <td>${getRoleLabel(r.target_role)}</td>
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
                <button type="button" class="policy-toc-item" data-target-id="policy-${slugifyPolicyHeading('1. Nguyên tắc chung')}" onclick="scrollPolicyToId(this.dataset.targetId)">
                  <span class="toc-badge">I</span>
                  <span class="toc-name">Nguyên tắc chung</span>
                </button>
                <button type="button" class="policy-toc-item" data-target-id="policy-${slugifyPolicyHeading('2. Các chế độ nghỉ phép')}" onclick="scrollPolicyToId(this.dataset.targetId)">
                  <span class="toc-badge">II</span>
                  <span class="toc-name">Các chế độ nghỉ phép</span>
                </button>
                <button type="button" class="policy-toc-item" data-target-id="policy-${slugifyPolicyHeading('3. Thẩm quyền phê duyệt')}" onclick="scrollPolicyToId(this.dataset.targetId)">
                  <span class="toc-badge">III</span>
                  <span class="toc-name">Thẩm quyền phê duyệt</span>
                </button>
                <button type="button" class="policy-toc-item" data-target-id="policy-${slugifyPolicyHeading('4. Thời hạn báo trước và hồ sơ')}" onclick="scrollPolicyToId(this.dataset.targetId)">
                  <span class="toc-badge">IV</span>
                  <span class="toc-name">Thời hạn & hồ sơ</span>
                </button>
                <button type="button" class="policy-toc-item" data-target-id="policy-${slugifyPolicyHeading('5. Xử lý hồ sơ không hợp lệ')}" onclick="scrollPolicyToId(this.dataset.targetId)">
                  <span class="toc-badge">V</span>
                  <span class="toc-name">Xử lý hồ sơ không hợp lệ</span>
                </button>
                <button type="button" class="policy-toc-item" data-target-id="policy-${slugifyPolicyHeading('6. Hiệu lực')}" onclick="scrollPolicyToId(this.dataset.targetId)">
                  <span class="toc-badge">VI</span>
                  <span class="toc-name">Hiệu lực</span>
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

window.scrollPolicyToId = function(id) {
  if (!id) return;
  const target = document.getElementById(id);
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }

  const els = document.querySelectorAll('.policy-content .policy-h2, .policy-content .policy-h3, .policy-content .policy-h1');
  const slug = String(id).replace(/^policy-/, '');
  for (const el of els) {
    if ((el.id || '').replace(/^policy-/, '') === slug) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
  }
};

// Legacy fallback for old links
window.scrollPolicyTo = function(text) {
  const els = document.querySelectorAll('.policy-content .policy-h2, .policy-content .policy-h3, .policy-content .policy-h1');
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

function getLeavePolicyTags(req) {
  if (req && req.leave_policy_tags) return req.leave_policy_tags;
  const type = String(req?.canonical_leave_type || req?.leave_type || '').toUpperCase();
  const fallback = {
    ANNUAL: ['Phép năm (Annual Leave)', 'Hưởng nguyên lương', 'Doanh nghiệp', 'Có'],
    SPECIAL_PAID: ['Nghỉ chế độ (Marriage/Bereavement)', 'Hưởng nguyên lương', 'Doanh nghiệp', 'Không'],
    SICK_MEDICAL: ['Nghỉ BHXH (Sick Leave)', 'Hưởng trợ cấp BHXH', 'Quỹ BHXH', 'Không'],
    MEDICAL_EMERGENCY: ['Nghỉ BHXH (Sick Leave)', 'Hưởng trợ cấp BHXH', 'Quỹ BHXH', 'Không'],
    MATERNITY: ['Nghỉ BHXH (Maternity Leave)', 'Hưởng trợ cấp BHXH', 'Quỹ BHXH', 'Không'],
    STATUTORY_UNPAID: ['Nghỉ không lương (Statutory Unpaid Leave)', 'Không hưởng lương', '—', 'Không'],
    UNPAID_OTHER: ['Nghỉ không lương (Unpaid Leave)', 'Không hưởng lương', '—', 'Không']
  }[type];
  return fallback
    ? {tag: fallback[0], pay_type: fallback[1], payer: fallback[2], annual_balance: fallback[3], status: 'MAPPED'}
    : {tag: 'Chưa phân loại theo policy', pay_type: 'Chưa xác định', payer: 'Chưa xác định', annual_balance: 'Chưa xác định', status: 'UNMAPPED'};
}

function renderLeavePolicyTags(req, detail=false) {
  const tags = getLeavePolicyTags(req);
  const unknown = tags.status === 'UNMAPPED';
  const base = 'display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:999px;font-size:0.7rem;font-weight:600;line-height:1.25;';
  const tagStyle = `${base}background:${unknown ? '#fef3c7' : '#eff6ff'};color:${unknown ? '#92400e' : '#1d4ed8'};border:1px solid ${unknown ? '#fde68a' : '#bfdbfe'};`;
  const infoStyle = `${base}background:#f8fafc;color:#475569;border:1px solid #e2e8f0;`;
  const wrapper = detail ? 'display:flex;flex-wrap:wrap;gap:5px;margin-top:8px;' : 'display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;';
  return `<div style="${wrapper}" title="Phân loại theo policy">
    <span style="${tagStyle}">${escapeHtml(tags.tag)}</span>
    <span style="${infoStyle}">${escapeHtml(tags.pay_type)}</span>
    <span style="${infoStyle}">Chi: ${escapeHtml(tags.payer)}</span>
    <span style="${infoStyle}">Trừ quỹ phép: ${escapeHtml(tags.annual_balance)}</span>
  </div>`;
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

function slugifyPolicyHeading(text) {
  return String(text || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
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
      const headingText = h4 ? h4[1] : h3 ? h3[1] : h2 ? h2[1] : h1[1];
      const headingId = `policy-${slugifyPolicyHeading(headingText)}`;

      if (h4) out.push(`<h4 id="${headingId}" class="policy-h4">${inlineFormat(h4[1])}</h4>`);
      else if (h3) out.push(`<h3 id="${headingId}" class="policy-h3">${inlineFormat(h3[1])}</h3>`);
      else if (h2) out.push(`<h2 id="${headingId}" class="policy-h2">${inlineFormat(h2[1])}</h2>`);
      else if (h1) out.push(`<h1 id="${headingId}" class="policy-h1">${inlineFormat(h1[1])}</h1>`);
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
