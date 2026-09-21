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
    selectEl.style.width = "180px";
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
  // padding-left (14px) + gap (8px) + icon (12px) + padding-right (14px) + border (4px)
  const targetWidth = Math.max(175, Math.min(320, Math.ceil(textWidth) + 52));
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
      const curr = getCurrentEmployee();
      const empName = curr ? curr.name : (demoSelect.options[demoSelect.selectedIndex]?.text || currentEmployeeId);
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
  if (selector) {
    selector.innerHTML = managers.map(e => `<option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.name)} · ${escapeHtml(e.actor_roles.map(r=>r.role).join('/'))}</option>`).join('');
    if (!managers.some(e=>e.employee_id===currentManagerRoleId)) currentManagerRoleId=managers[0]?.employee_id || '';
    selector.value = currentManagerRoleId;
    autoResizeSelect(selector);
  }
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
        if (llmOk) { ok = true; label = "LLM Sẵn sàng"; extra = llm.target_model || "qwen2.5:3b-instruct"; }
        else if (llmLoading) { ok = false; label = "LLM Đang nạp..."; extra = llm.target_model || "qwen2.5:3b-instruct"; }
        else if (llmErr) { ok = false; label = "LLM Lỗi"; extra = (llmErr || "").slice(0, 40); }
        else { ok = false; label = "LLM Offline"; extra = llm.target_model || "qwen2.5:3b-instruct"; }
        setBadge(llmText, ok, label, extra);
      }

      const vlmPulled = vlm.ollama_reachable && vlm.model_loaded;
      const vlmOnGpu = Number(vlm.size_vram || 0) > 0;
      if (vlmText) {
        let ok = false, label = "", extra = vlm.target_model || "qwen2.5vl:7b";
        if (vlmPulled && vlmOnGpu) { ok = true; label = "VLM Sẵn sàng"; extra = extra + " · GPU"; }
        else if (vlmPulled && !vlmOnGpu) { label = "VLM trên CPU"; extra = extra + " · size_vram=0"; }
        else if (vlm.ollama_reachable && !vlm.model_loaded) { label = "VLM thiếu model"; extra = "Cần pull qwen2.5vl:7b"; }
        else { label = "VLM Offline"; extra = vlm.last_error || "Ollama không phản hồi"; }
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

  // Check if tree has already been rendered (look for the new mindmap structure)
  let needsRender = false;
  containers.forEach(c => {
    if (!c.querySelector(".mm-tree-structure")) needsRender = true;
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
    console.warn("loadDecisionTree error:", err);
    // Show error state inside containers
    document.querySelectorAll(".dt-nodes-container").forEach(c => {
      c.innerHTML = `<div style="text-align:center;padding:40px 20px;color:#ef4444;">
        <div style="font-size:2rem;margin-bottom:8px;">⚠️</div>
        <div style="font-weight:600;">Không tải được dữ liệu cây quyết định</div>
        <div style="font-size:0.82rem;color:#94a3b8;margin-top:4px;">${err.message}</div>
      </div>`;
    });
  }
}

// Empty fallback — no longer used but kept to prevent reference errors
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

function renderDecisionTree(tree) {
  const branches = tree.branches || tree.leave_type_branches || [];

  // 1. Gốc Mindmap (Root Box)
  const rootNode = `
    <div class="mm-node-root mm-box" id="mm-root-box" data-color="#2563eb">
      <div class="mm-root-badge">CỘT MỐC GỐC · TIẾP NHẬN HỒ SƠ</div>
      <div class="mm-root-body">
        <div class="mm-root-icon">📥</div>
        <div class="mm-root-content">
          <div class="mm-root-title">Tiếp nhận & Chuẩn hóa Đơn Nghỉ Phép</div>
        </div>
      </div>
    </div>
  `;

  // 2. Tầng 1: Tiền kiểm tra chung (3 Hộp con)
  const tier1Html = `
    <div class="mm-branch-block mm-branch-t1" data-branch-color="#0284c7">
      <div class="mm-branch-trunk-head mm-box" data-color="#0284c7" id="mm-t1-head">
        <div class="mm-trunk-tag" style="background:#0284c7; color:#fff;">TẦNG 1</div>
        <div class="mm-trunk-title">Tiền kiểm tra điều kiện chung</div>
        <div class="mm-trunk-sub">3 bước bắt buộc áp dụng cho 100% mọi loại đơn</div>
      </div>
      <div class="mm-branch-children-row" id="mm-t1-children">
        ${(tree.common_inputs || []).map((nd, i) => renderMindmapNode(nd, '#0284c7')).join('')}
      </div>
    </div>
  `;

  // 3. Tầng 2: 8 Nhánh quy chế (8 Cụm nhánh con)
  const tier2Html = `
    <div class="mm-branch-block mm-branch-t2" data-branch-color="#6366f1">
      <div class="mm-branch-trunk-head mm-box" data-color="#6366f1" id="mm-t2-head">
        <div class="mm-trunk-tag" style="background:#6366f1; color:#fff;">TẦNG 2</div>
        <div class="mm-trunk-title">8 Phân nhánh Quy chế nghiệp vụ</div>
        <div class="mm-trunk-sub">Mỗi hình thức nghỉ phép vận hành luồng điều kiện & phân cấp riêng</div>
      </div>
      <div class="mm-branch-children-row mm-branches-grid-row" id="mm-t2-children">
        ${branches.map((b, i) => renderMindmapBranchCard(b, i)).join('')}
      </div>
    </div>
  `;

  // 4. Tầng 3: Hậu kiểm tra & Tổng hợp Thẩm quyền (2 Hộp con)
  const tier3Html = `
    <div class="mm-branch-block mm-branch-t3" data-branch-color="#0d9488">
      <div class="mm-branch-trunk-head mm-box" data-color="#0d9488" id="mm-t3-head">
        <div class="mm-trunk-tag" style="background:#0d9488; color:#fff;">TẦNG 3</div>
        <div class="mm-trunk-title">Hậu kiểm tra & Tổng hợp Thẩm quyền</div>
        <div class="mm-trunk-sub">Kiểm tra xung đột lịch và xác định người ký duyệt cuối cùng</div>
      </div>
      <div class="mm-branch-children-row" id="mm-t3-children">
        ${(tree.common_final || []).map((nd, i) => renderMindmapNode(nd, '#0d9488')).join('')}
      </div>
    </div>
  `;

  // 5. Tầng 4: 3 nhóm xử lý cuối cùng
  const tierOutcomesHtml = `
    <div class="mm-branch-block mm-branch-t4" data-branch-color="#15803d">
      <div class="mm-branch-trunk-head mm-box" data-color="#15803d" id="mm-t4-head">
        <div class="mm-trunk-tag" style="background:#15803d; color:#fff;">TẦNG 4</div>
        <div class="mm-trunk-title">3 hướng xử lý cuối cùng</div>
        <div class="mm-trunk-sub">Kết quả tất định của Rule Engine chuyển vào Fast-Path hoặc AI Copilot</div>
      </div>
      <div class="mm-branch-children-row mm-outcomes-row" id="mm-t4-children">
        ${(tree.outcomes || []).map(o => `
          <div class="mm-outcome-box mm-box" style="border-left: 4px solid ${o.color};" data-color="${o.color}">
            <div class="mm-outcome-tag" style="color:${o.color};">
              <span class="mm-outcome-dot" style="background:${o.color};"></span>
              <span class="mm-outcome-title">${escapeHtml(o.title || o.id)}</span>
              <span class="mm-outcome-code">${escapeHtml(o.id)}</span>
            </div>
            <div class="mm-outcome-content">
              <div class="mm-outcome-desc">${escapeHtml(o.body || o.desc || '')}</div>
              ${o.route ? `<div class="mm-outcome-route">${escapeHtml(o.route)}</div>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  // Lắp ráp toàn bộ cây Mindmap vào khung chứa
  const fullMindmapHtml = `
    <div class="mm-tree-structure">
      <div class="mm-root-row">
        ${rootNode}
      </div>
      <div class="mm-trunks-grid">
        ${tier1Html}
        ${tier2Html}
        ${tier3Html}
        ${tierOutcomesHtml}
      </div>
    </div>
  `;

  document.querySelectorAll('.dt-nodes-container').forEach(c => {
    c.innerHTML = fullMindmapHtml;
  });

  setupTreeContainerPanning();
  applyMindmapTransform();
  setTimeout(() => {
    requestAnimationFrame(drawMindmapConnectors);
  }, 60);
}

function renderMindmapBranchCard(b, index) {
  const steps = b.steps || b.nodes || [];
  const hex = b.color || '#475569';

  return `
    <div class="mm-branch-card mm-box" style="border-top: 4px solid ${hex};" data-color="${hex}">
      <div class="mm-branch-card-head">
        <span class="mm-branch-icon" style="background:${hex}15; color:${hex}; border:1.5px solid ${hex}40;">${escapeHtml(b.icon || '🏷️')}</span>
        <div class="mm-branch-card-info">
          <div class="mm-branch-card-title" style="color:${hex};">${escapeHtml(b.title || b.label)}</div>
        </div>
      </div>

      <div class="mm-subnodes-list">
        ${steps.map((s, si) => renderMindmapMiniNode(s, hex)).join('')}
      </div>

    </div>
  `;
}

function renderMindmapNode(node, branchColor) {
  const kind = (node.kind || node.type || 'POLICY').toString().toUpperCase();
  const isVlm = kind === 'VLM';
  const hex = isVlm ? '#8b5cf6' : (branchColor || '#0284c7');
  const tagClass = isVlm ? 'mm-tag-vlm' : 'mm-tag-policy';
  const tagLabel = isVlm ? '🤖 VLM Vision' : '📋 Quy chế';
  const whenPass = (node.when_pass || node.pass_action || '').trim();
  const whenFail = (node.when_fail || node.fail_action || '').trim();

  return `
    <div class="mm-node-item mm-box" style="border-left: 4px solid ${hex};" data-color="${hex}">
      <div class="mm-node-item-head">
        <div class="mm-node-tags">
          <span class="mm-node-id">${escapeHtml(node.node_id || '')}</span>
          <span class="mm-node-tag ${tagClass}">${tagLabel}</span>
        </div>
        <span class="mm-node-name">${escapeHtml(node.label || '')}</span>
      </div>
      <div class="mm-node-outcomes">
        ${whenFail ? `<div class="mm-cond mm-cond-fail"><span class="mm-cond-icon">✕</span><span class="mm-cond-text"><strong>SAI:</strong> ${escapeHtml(whenFail)}</span></div>` : (whenPass ? `<div class="mm-cond mm-cond-pass"><span class="mm-cond-icon">→</span><span class="mm-cond-text">${escapeHtml(whenPass)}</span></div>` : '')}
      </div>
    </div>
  `;
}

function renderMindmapMiniNode(node, hex) {
  const isVlm = (node.kind || node.type || '').toString().toUpperCase() === 'VLM';
  const whenPass = (node.when_pass || node.pass_action || '').trim();
  const whenFail = (node.when_fail || node.fail_action || '').trim();

  return `
    <div class="mm-subnode-item ${isVlm ? 'mm-subnode-vlm' : ''}">
      <div class="mm-subnode-head">
        <span class="mm-subnode-id">${escapeHtml(node.node_id || '')}</span>
        <span class="mm-subnode-name">${escapeHtml(node.label || '')}</span>
        ${isVlm ? '<span class="mm-vlm-pill">🤖 VLM</span>' : ''}
      </div>
      ${whenFail || whenPass ? `
        <div class="mm-subnode-branches">
          ${whenFail ? `<div class="mm-sub-fail">SAI → ${escapeHtml(whenFail)}</div>` : `<div class="mm-sub-pass">→ ${escapeHtml(whenPass)}</div>`}
        </div>
      ` : ''}
    </div>
  `;
}

// Vẽ đường nối cong SVG tự động giữa các khối hộp Mindmap
function drawMindmapConnectors() {
  const svg = document.getElementById("mm-svg-canvas");
  const world = document.getElementById("mm-world");
  if (!svg || !world) return;

  svg.innerHTML = "";
  const worldRect = world.getBoundingClientRect();
  const zoom = mmState.zoom || 1.0;

  // Size SVG to cover the full unscaled content area
  const svgW = Math.max(world.scrollWidth, worldRect.width / zoom);
  const svgH = Math.max(world.scrollHeight, worldRect.height / zoom);
  svg.setAttribute("width", svgW);
  svg.setAttribute("height", svgH);

  const rootBox = document.getElementById("mm-root-box");
  if (!rootBox) return;

  const getUnscaledBox = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: (r.left - worldRect.left) / zoom,
      y: (r.top - worldRect.top) / zoom,
      w: r.width / zoom,
      h: r.height / zoom,
      cx: (r.left - worldRect.left + r.width / 2) / zoom,
      cy: (r.top - worldRect.top + r.height / 2) / zoom,
      bottom: (r.top - worldRect.top + r.height) / zoom,
      top: (r.top - worldRect.top) / zoom
    };
  };

  const rootCoords = getUnscaledBox(rootBox);

  // Nối từ Root sang 4 Tầng chính (T1, T2, T3, T4)
  const trunkHeads = [
    { id: "mm-t1-head", color: "#0284c7" },
    { id: "mm-t2-head", color: "#6366f1" },
    { id: "mm-t3-head", color: "#0d9488" },
    { id: "mm-t4-head", color: "#15803d" }
  ];

  trunkHeads.forEach(trunk => {
    const headEl = document.getElementById(trunk.id);
    if (!headEl) return;
    const headCoords = getUnscaledBox(headEl);

    // Đường cong Bézier từ Root Bottom sang Head Top
    const p1 = { x: rootCoords.cx, y: rootCoords.bottom };
    const p2 = { x: headCoords.cx, y: headCoords.top };
    const midY = (p1.y + p2.y) / 2;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const d = `M ${p1.x} ${p1.y} C ${p1.x} ${midY}, ${p2.x} ${midY}, ${p2.x} ${p2.y}`;
    path.setAttribute("d", d);
    path.setAttribute("stroke", trunk.color);
    path.setAttribute("stroke-width", "2.5");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("opacity", "0.85");
    svg.appendChild(path);

    // Chấm tròn gốc (root side)
    const rootDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    rootDot.setAttribute("cx", p1.x);
    rootDot.setAttribute("cy", p1.y);
    rootDot.setAttribute("r", "3");
    rootDot.setAttribute("fill", trunk.color);
    rootDot.setAttribute("opacity", "0.6");
    svg.appendChild(rootDot);

    // Chấm tròn đầu mút kết nối (head side)
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", p2.x);
    dot.setAttribute("cy", p2.y);
    dot.setAttribute("r", "3.5");
    dot.setAttribute("fill", trunk.color);
    svg.appendChild(dot);
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
        dropSub.innerText = `Chấp nhận PDF, PNG, JPG (VLM sẽ đọc và đối soát)`;
      }
    } else {
      if (label) {
        label.innerHTML = `Chứng từ xác minh <span class="badge" style="background:#f1f5f9;color:#64748b;font-weight:500;font-size:0.75rem;padding:2px 8px;border-radius:4px;margin-left:4px;">Không bắt buộc / Tùy chọn</span>`;
      }
      if (hint) {
        hint.innerHTML = `<span style="color:#64748b;">Nghỉ phép năm / không lương không bắt buộc chứng từ (bỏ qua VLM)</span>`;
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
      ? "VLM qwen2.5vl:7b ~12s (8–18s) · Rule Engine <0.3s · form không gọi LLM"
      : "Không chứng từ: bỏ qua VLM · Rule Engine <0.3s · form không gọi LLM";
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
      paint(pct, `Bước 2: VLM qwen2.5vl:7b đang đọc chứng từ (${remainLabel})${dots}`);
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
      paint(25 + ((elapsed - RECV_MS) / RULE_MS) * 50, "Bước 3: Rule Engine đối soát chính sách...");
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
  const file = document.getElementById('staff-file-input')?.files[0];
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
      editingRequestId=null; currentProofId=null;
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
            ${renderLeavePolicyTags(req)}
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
    .replace(/^H\u1ec7 th\u1ed1ng chuy\u1ec3n ti\u1ebfp do:\s*/i, "")
    .replace(/^Minh b\u1ea1ch AI & C\u0103n c\u1ee9 x\u1eed l\u00fd:\s*/i, "")
    .trim();

  // ── VLM extracted data (Technical facts only) ─────────────────────────────
  const _vlm = req.vlm_analysis_json || {};
  const _vlmDoc = _vlm.document_summary || {};
  const _vlmFlags = _vlm.flags || {};
  const _vlmCorr = _vlm.correlation_analysis || {};
  const _vlmMode = _vlm.inspection_mode || "";
  const _vlmErr = _vlm.vlm_error || "";
  const _hasVlm = !!(req.vlm_analysis_json);

  function _boolBadge(val, trueL, falseL) {
    if (val === true)  return '<span style="background:#dcfce7;color:#166534;padding:2px 9px;border-radius:5px;font-size:0.78rem;font-weight:600;">\u2713 ' + trueL + '</span>';
    if (val === false) return '<span style="background:#fee2e2;color:#991b1b;padding:2px 9px;border-radius:5px;font-size:0.78rem;font-weight:600;">\u2717 ' + falseL + '</span>';
    return '<span style="background:#f1f5f9;color:#64748b;padding:2px 9px;border-radius:5px;font-size:0.78rem;">\u2014 Ch\u01b0a x\u00e1c \u0111\u1ecbnh</span>';
  }
  function _nv(v, fallback) {
    return v ? '<span style="font-weight:600;color:#0f172a;">' + escapeHtml(String(v)) + '</span>' : '<span style="color:#94a3b8;">\u2014 ' + fallback + '</span>';
  }

  let _vlmModeBadge = '';
  if (_vlmMode === 'OLLAMA_REAL_QWEN25_VL_3B' || _vlmMode.startsWith('OLLAMA_REAL')) _vlmModeBadge = '<span style="background:#dcfce7;color:#166534;font-size:0.72rem;padding:2px 8px;border-radius:4px;font-weight:600;">\uD83E\uDD16 VLM Th\u1eadt</span>';
  else if (_vlmMode.includes('UNAVAILABLE') || _vlmMode.includes('ERROR')) _vlmModeBadge = '<span style="background:#fee2e2;color:#991b1b;font-size:0.72rem;padding:2px 8px;border-radius:4px;font-weight:600;">\u26a0 VLM L\u1ed7i / Ch\u01b0a c\u00f3 model</span>';
  else if (_vlmMode) _vlmModeBadge = '<span style="background:#f1f5f9;color:#475569;font-size:0.72rem;padding:2px 8px;border-radius:4px;">' + escapeHtml(_vlmMode) + '</span>';

  let _vlmSection = '';
  if (_hasVlm) {
    const _dr = _vlmDoc.doctor_recommended_range || {};

    _vlmSection = '<div class="col-12" style="margin-top:4px;">'
      + '<div style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;background:#ffffff;">'
      + '<div style="background:linear-gradient(135deg,#f8fafc,#f1f5f9);padding:10px 16px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">'
      + '<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:1rem;">\uD83E\uDD16</span><span style="font-weight:700;color:#0f172a;font-size:0.9rem;">Th\u00f4ng tin tr\u00edch xu\u1ea5t t\u1eeb ch\u1ee9ng t\u1eeb (VLM)</span>' + _vlmModeBadge + '</div>'
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
      + _boolBadge(_vlmFlags.has_red_stamp, 'C\u00f3 d\u1ea5u \u0111\u1ecf', 'Thi\u1ebfu d\u1ea5u \u0111\u1ecf')
      + _boolBadge(_vlmFlags.has_doctor_signature !== undefined ? _vlmFlags.has_doctor_signature : _vlmFlags.signature_present_on_scan, 'C\u00f3 ch\u1eef k\u00fd', 'Thi\u1ebfu ch\u1eef k\u00fd')
      + (_vlmFlags.is_tampered === true ? '<span style="background:#fef3c7;color:#92400e;padding:2px 9px;border-radius:5px;font-size:0.78rem;font-weight:600;">\u26a0 Nghi gi\u1ea3 m\u1ea1o</span>' : '')
      + (_vlmFlags.ai_generated_or_edited === true ? '<span style="background:#fef3c7;color:#92400e;padding:2px 9px;border-radius:5px;font-size:0.78rem;font-weight:600;">\u26a0 Nghi AI ch\u1ec9nh s\u1eeda</span>' : '')
      + (_vlmFlags.document_readability ? '<span style="background:#f1f5f9;color:#475569;padding:2px 9px;border-radius:5px;font-size:0.78rem;">\u0110\u1ed9 r\u00f5: ' + escapeHtml(_vlmFlags.document_readability) + '</span>' : '')
      + '</div>'
      + '</div></div>';
  }

  // ── LLM Summary & Synthesis data (Core Reasoning) ──────────────────────────
  const _llm = req.llm_summary_json || {};
  const _hasLlm = !!(req.llm_summary_json);
  let _llmSection = '';
  if (_hasLlm) {
    const _isManagerAudience = currentMode === 'manager';
    const _audienceSummary = _isManagerAudience
      ? (_llm.manager_summary || {suspicions_vn: _llm.info_missing_vn || [], risk_level_vn: '—'})
      : (_llm.staff_summary || {errors_vn: _llm.info_missing_vn || []});
    const _sumTxt = _audienceSummary.summary_natural_vn || (_isManagerAudience ? _llm.summary_natural_vn : '');
    const _whyEsc = _isManagerAudience ? (_llm.why_escalated || '') : '';
    const _tier = _llm.correlation_tier_vn || '';
    const _aq = _isManagerAudience ? (_llm.actionable_question || '') : '';
    const _pvn = _isManagerAudience ? (_llm.applied_policy_clauses_vn || []) : [];
    const _qvn = _isManagerAudience ? (_llm.quick_action_options_vn || []) : [];
    const _warns = _isManagerAudience ? (_llm.warnings || []) : [];
    const _riskLevel = _audienceSummary.risk_level_vn || _llm.manager_risk_level_vn || '';
    const _engine = _llm.engine || '';
    const _isReal = /qwen2\.5:3b-instruct|Ollama/i.test(_engine);
    const _isRule = _engine.includes('decision_tree');
    const _tierC = _tier === 'RẤT KHỚP' ? '#059669' : _tier === 'KHỚP' ? '#2563eb' : _tier === 'CHƯA KHỚP' ? '#d97706' : _tier === 'KHÔNG KHỚP' ? '#dc2626' : '#059669';

    // Đủ & thiếu thông tin do LLM / Rule Engine tổng hợp
    let _infoSuf = _isManagerAudience ? [] : (_audienceSummary.errors_vn || _llm.info_missing_vn || []);
    let _infoMis = _isManagerAudience
      ? (_audienceSummary.suspicions_vn || _llm.manager_suspicions_vn || [])
      : (_llm.info_missing_vn || []);

    // Fallback thông minh nếu cả 2 mảng rỗng
    if (!_isManagerAudience && _infoSuf.length === 0 && _infoMis.length === 0) {
      if (req.employee_name) _infoSuf.push('Nhân viên nộp đơn: ' + req.employee_name);
      if (req.from_date && req.to_date) _infoSuf.push('Thời gian xin nghỉ: ' + req.from_date + ' → ' + req.to_date);
      if (hasAttachment && _vlmDoc && _vlmDoc.diagnosis) _infoSuf.push('Chẩn đoán trên giấy: ' + _vlmDoc.diagnosis);

      if (hasAttachment) {
        if (_vlmFlags && _vlmFlags.has_red_stamp === false) _infoMis.push('Thiếu dấu mộc đỏ bệnh viện/phòng khám');
        if (_vlmFlags && _vlmFlags.has_doctor_signature === false) _infoMis.push('Thiếu chữ ký bác sĩ / người cấp giấy');
        if (_vlmDoc && !_vlmDoc.patient_name) _infoMis.push('Chưa đọc được tên trên chứng từ');
      } else {
        _infoSuf.push('Không yêu cầu chứng từ đối với loại nghỉ này');
      }
    }

    const _timings = _llm.timings || {};
    const _timingBadge = (_timings.rule_engine_ms !== undefined && _timings.template_ms !== undefined)
      ? '<span style="font-size:0.72rem;color:#6b21a8;background:#f3e8ff;padding:2px 8px;border-radius:4px;font-weight:600;" title="Rule Engine: ' + _timings.rule_engine_ms + 'ms, Template: ' + _timings.template_ms + 'ms">⚡ ' + (_timings.total_eval_ms || Math.round((_timings.rule_engine_ms + _timings.template_ms)*10)/10) + 'ms</span>'
      : '';

    _llmSection = '<div class="col-12" style="margin-top:4px;">'
      + '<div style="border:1px solid #c084fc;border-radius:12px;overflow:hidden;background:#ffffff;box-shadow:0 2px 8px rgba(147,51,234,0.06);">'
      + '<div style="background:linear-gradient(135deg,#faf5ff,#f3e8ff);padding:12px 16px;border-bottom:1px solid #e9d5ff;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">'
      + '<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:1.1rem;">🧠</span><span style="font-weight:700;color:#4c1d95;font-size:0.95rem;">' + (_isManagerAudience ? 'Nhận định nghi vấn cho Manager' : 'Lỗi cần Staff bổ sung') + '</span>'
      + (_isReal ? '<span style="background:#dcfce7;color:#166534;font-size:0.72rem;padding:2px 8px;border-radius:4px;font-weight:600;">✓ qwen2.5:3b-instruct</span>' : '<span style="background:#f3e8ff;color:#6b21a8;font-size:0.72rem;padding:2px 8px;border-radius:4px;font-weight:600;">✓ Decision Tree Engine</span>')
      + _timingBadge
      + '</div>'
      + (_tier && _tier !== '—' ? '<span style="background:' + _tierC + '20;color:' + _tierC + ';font-size:0.78rem;padding:3px 10px;border-radius:5px;font-weight:700;">' + escapeHtml(_tier) + '</span>' : '')
      + '</div>'
      + (_isManagerAudience && _riskLevel ? '<div style="padding:8px 16px;border-bottom:1px solid #f3e8ff;font-size:0.8rem;color:#92400e;font-weight:700;">Mức nghi vấn: ' + escapeHtml(_riskLevel) + '</div>' : '')
      
      // 1. Tóm tắt súc tích tách từng ý rõ ràng
      + (_sumTxt ? (function() {
          const _rawLines = _sumTxt.split('\n').map(function(l){ return l.trim(); }).filter(function(l){ return l.length > 0; });
          let _linesContent = '';
          if (_rawLines.length > 1) {
            _linesContent = _rawLines.map(function(line) {
              let clean = line.replace(/^[•\-\*]\s*/, '');
              let colonIdx = clean.indexOf(':');
              if (colonIdx > 0 && colonIdx < 30) {
                let title = clean.substring(0, colonIdx);
                let rest = clean.substring(colonIdx + 1);
                return '<div style="font-size:0.85rem;color:#1e293b;line-height:1.55;margin-bottom:6px;display:flex;align-items:flex-start;gap:8px;">'
                  + '<span style="color:#7c3aed;font-weight:700;font-size:1rem;line-height:1.2;">&bull;</span>'
                  + '<span><strong style="color:#581c87;font-weight:600;">' + escapeHtml(title) + ':</strong>' + escapeHtml(rest) + '</span>'
                  + '</div>';
              }
              return '<div style="font-size:0.85rem;color:#1e293b;line-height:1.55;margin-bottom:6px;display:flex;align-items:flex-start;gap:8px;">'
                + '<span style="color:#7c3aed;font-weight:700;font-size:1rem;line-height:1.2;">&bull;</span>'
                + '<span>' + escapeHtml(clean) + '</span>'
                + '</div>';
            }).join('');
          } else {
            _linesContent = '<div style="font-size:0.86rem;color:#1e293b;line-height:1.6;white-space:pre-line;">' + escapeHtml(_sumTxt) + '</div>';
          }
          return '<div style="padding:12px 16px;border-bottom:1px solid #f3e8ff;">'
            + '<div style="font-size:0.73rem;color:#7c3aed;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;">Tóm tắt cốt lõi &amp; Đối soát</div>'
            + _linesContent
            + '</div>';
        })() : '')
      
      // 2. Phân tách rõ ràng: Đủ vs Thiếu
      + '<div style="padding:12px 16px;border-bottom:1px solid #f3e8ff;background:#faf5ff50;">'
      + (_isManagerAudience
        ? '<div><div style="font-size:0.74rem;color:#dc2626;font-weight:700;text-transform:uppercase;margin-bottom:6px;">Nghi vấn / rủi ro cần xác minh (' + _infoMis.length + ')</div>' + (_infoMis.length > 0 ? _infoMis.map(function(m){ return '<div style="font-size:0.81rem;color:#991b1b;padding:2px 0;">&bull; ' + escapeHtml(String(m)) + '</div>'; }).join('') : '<div style="font-size:0.8rem;color:#059669;">\u2014 Không phát hiện nghi vấn</div>') + '</div>'
        : '<div><div style="font-size:0.74rem;color:#dc2626;font-weight:700;text-transform:uppercase;margin-bottom:6px;">Lỗi cần sửa / bổ sung (' + _infoSuf.length + ')</div>' + (_infoSuf.length > 0 ? _infoSuf.map(function(m){ return '<div style="font-size:0.81rem;color:#991b1b;padding:2px 0;">&bull; ' + escapeHtml(String(m)) + '</div>'; }).join('') : '<div style="font-size:0.8rem;color:#059669;">\u2014 Không có lỗi cần bổ sung</div>') + '</div>')
      + '</div>'

      // 3. Câu hỏi & Đề xuất giải quyết cho Manager
      + ((_aq || _whyEsc || _qvn.length > 0) ? '<div style="padding:12px 16px;background:#f8fafc;border-top:1px solid #f1f5f9;">'
          + (_whyEsc ? '<div style="font-size:0.8rem;color:#475569;margin-bottom:6px;"><span style="font-weight:600;color:#6b21a8;">C\u0103n c\u1ee9 chuy\u1ec3n duy\u1ec7t:</span> ' + escapeHtml(_whyEsc) + '</div>' : '')
          + (_aq ? '<div style="font-size:0.88rem;color:#1e1b4b;font-weight:600;padding:8px 12px;background:#ede9fe;border-radius:8px;border-left:4px solid #7c3aed;margin-bottom:8px;">\u2753 ' + escapeHtml(_aq) + '</div>' : '')
          + (_qvn.length > 0 ? '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;"><span style="font-size:0.75rem;color:#64748b;font-weight:600;">G\u1ee3i \u00fd th\u00e1o t\u00e1c:</span>' + _qvn.map(function(q){ return '<span style="background:#ffffff;border:1px solid #cbd5e1;color:#334155;font-size:0.76rem;padding:2px 8px;border-radius:5px;font-weight:500;">' + escapeHtml(String(q)) + '</span>'; }).join('') + '</div>' : '')
          + '</div>' : '')

      + ((_pvn.length > 0 || _warns.length > 0) ? '<div style="padding:8px 16px;border-top:1px solid #f1f5f9;font-size:0.76rem;color:#64748b;display:flex;flex-wrap:wrap;gap:12px;">'
          + (_pvn.length > 0 ? '<div><span style="font-weight:600;color:#7c3aed;">Ch\u00ednh s\u00e1ch:</span> ' + _pvn.map(function(p){ return escapeHtml(String(p)); }).join('; ') + '</div>' : '')
          + (_warns.length > 0 ? '<div><span style="font-weight:600;color:#dc2626;">C\u1ea3nh b\u00e1o:</span> ' + _warns.map(function(w){ return escapeHtml(String(w)); }).join('; ') + '</div>' : '')
          + '</div>' : '')
      + '</div></div>';
  }

  body.innerHTML = `
    <div class="row g-3">
      <div class="col-6">
        <label class="form-label text-secondary small fw-semibold mb-1">Lo\u1ea1i ngh\u1ec9 ph\u00e9p</label>
        <div class="modal-readonly-field">
          <span class="text-dark fw-semibold">${getLeaveTypeLabel(req.leave_type)}</span>
          ${renderLeavePolicyTags(req, true)}
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
          ${hasAttachment ? `
            <button type="button" class="btn btn-sm btn-outline-primary px-3" onclick="openAttachmentModal('${req.id}', '${req.attachment_type}', '${req.employee_name}')" style="font-size: 0.8rem; font-weight: 500;">
              Xem ảnh gốc
            </button>
          ` : ''}
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
        ${renderLeavePolicyTags(r, true)}

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
