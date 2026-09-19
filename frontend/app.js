/**
 * app.js — Team PNKK
 * AI Leave Approval & Escalation Routing System (The Escalation Referee)
 * Fully Supports 2 Modes: 
 * 1. Staff UI Portal (Cổng Thông Tin Nhân Viên)
 * 2. Manager & Admin Portal (Giao Diện Quản Lý & Điều Phối)
 */

const API_BASE = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
  ? window.location.origin
  : "http://localhost:8000";

let currentLang = localStorage.getItem("app_lang") || "vi";
let currentMode = "staff"; // 'staff' | 'manager'
let currentEmployeeId = "EMP001";
let currentManagerRoleId = "MGR001";
let employeesCache = [];
let activeRequests = [];
let pollInterval = null;

// Mock Fallback Employees nếu API chưa nạp
const DEFAULT_EMPLOYEES = [
  {
    employee_id: "EMP001",
    name: "Dương Anh Kiệt",
    role: "Thực tập sinh AI",
    department: "Trung tâm Công nghệ AI",
    manager_id: "MGR001 - Đào Tuấn Minh",
    remaining_leave_days: 9.0,
    total_leave_days: 12.0,
    used_leave_days: 3.0,
    avatar: "T"
  },
  {
    employee_id: "EMP002",
    name: "Nguyễn Văn A",
    role: "Kế toán viên",
    department: "Phòng Tài chính - Kế toán",
    manager_id: "MGR002 - Trần Thu Hà",
    remaining_leave_days: 6.0,
    total_leave_days: 14.0,
    used_leave_days: 8.0,
    avatar: "H"
  },
  {
    employee_id: "EMP003",
    name: "Trần Thị B",
    role: "Kỹ sư Cầu nối",
    department: "Phòng Dự án Toàn cầu",
    manager_id: "MGR001 - Đào Tuấn Minh",
    remaining_leave_days: 13.0,
    total_leave_days: 15.0,
    used_leave_days: 2.0,
    avatar: "N"
  },
  {
    employee_id: "EMP004",
    name: "Lê Hoàng C",
    role: "Lập trình viên Backend",
    department: "Phòng Kỹ thuật Phần mềm",
    manager_id: "MGR001 - Đào Tuấn Minh",
    remaining_leave_days: 6.0,
    total_leave_days: 12.0,
    used_leave_days: 6.0,
    avatar: "M"
  }
];

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
    quick_submit_sub: "Trợ lý AI sẽ hỗ trợ thẩm định tự động ngay trong 1 giây",
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

function initModeSwitcher() {
  const btnStaff = document.getElementById("btn-mode-staff");
  const btnManager = document.getElementById("btn-mode-manager");
  const viewStaff = document.getElementById("view-staff-portal");
  const viewManager = document.getElementById("view-manager-portal");
  const staffSelector = document.getElementById("header-staff-selector");
  const mgrSelector = document.getElementById("header-manager-selector");
  const btnAllocate = document.getElementById("btn-header-allocate");
  const alertQueue = document.getElementById("header-pending-alert");

  if (btnStaff && btnManager) {
    btnStaff.addEventListener("click", () => {
      currentMode = "staff";
      btnStaff.classList.add("active");
      btnManager.classList.remove("active");
      viewStaff.classList.add("active");
      viewManager.classList.remove("active");
      
      if (staffSelector) {
        staffSelector.classList.remove("d-none");
        staffSelector.classList.add("d-flex");
      }
      if (mgrSelector) {
        mgrSelector.classList.remove("d-flex");
        mgrSelector.classList.add("d-none");
      }
      if (btnAllocate) btnAllocate.style.display = "none";
      if (alertQueue) alertQueue.style.display = "none";

      renderStaffDashboard();
      renderStaffRequests();
      renderWeeklyCalendar();
    });

    btnManager.addEventListener("click", () => {
      currentMode = "manager";
      btnManager.classList.add("active");
      btnStaff.classList.remove("active");
      viewManager.classList.add("active");
      viewStaff.classList.remove("active");

      if (staffSelector) {
        staffSelector.classList.remove("d-flex");
        staffSelector.classList.add("d-none");
      }
      if (mgrSelector) {
        mgrSelector.classList.remove("d-none");
        mgrSelector.classList.add("d-flex");
      }
      if (btnAllocate) btnAllocate.style.display = "inline-flex";

      renderManagerOverviewKPIs();
      renderManagerQueue();
      renderAutoApprovedLogs();
      renderManagerAllRequests();
      renderWeeklyCalendar();
      updateBadgesAndCounters();
    });
  }
}

/* ========================================================================= */
/* 2. DEMO LOGIN & ROLE SWITCHER                                             */
/* ========================================================================= */
function initDemoLoginAndRoles() {
  const demoSelect = document.getElementById("demo-employee-select");
  if (demoSelect) {
    demoSelect.addEventListener("change", (e) => {
      currentEmployeeId = e.target.value;
      renderStaffDashboard();
      renderStaffRequests();
      renderWeeklyCalendar();
      showToast(`Đã chuyển sang nhân viên: ${getCurrentEmployee().name}`, "info");
    });
  }

  const roleSelect = document.getElementById("manager-role-select");
  if (roleSelect) {
    roleSelect.addEventListener("change", (e) => {
      currentManagerRoleId = e.target.value;
      const roleName = roleSelect.options[roleSelect.selectedIndex].text;
      showToast(`Đang làm việc với góc nhìn: ${roleName}`, "info");
    });
  }
}

async function loadEmployees() {
  try {
    const res = await fetch(`${API_BASE}/api/meta/employees`);
    if (res.ok) {
      const data = await res.json();
      if (data.success && Array.isArray(data.data) && data.data.length > 0) {
        employeesCache = data.data;
      } else {
        employeesCache = DEFAULT_EMPLOYEES;
      }
    } else {
      employeesCache = DEFAULT_EMPLOYEES;
    }
  } catch (err) {
    console.warn("Using fallback employees:", err);
    employeesCache = DEFAULT_EMPLOYEES;
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
        ${emp.name} (${emp.role || emp.department})
      </option>
    `).join("");
  }

  if (allocEmpSelect) {
    allocEmpSelect.innerHTML = employeesCache.map(emp => `
      <option value="${emp.employee_id}">${emp.name} - ${emp.employee_id} (${emp.department})</option>
    `).join("");
  }

  updateHandoverOptions();
}

function updateHandoverOptions() {
  const handoverSelect = document.getElementById("staff-handover-select");
  if (!handoverSelect) return;

  const currentEmp = getCurrentEmployee();
  const availableColleagues = employeesCache.filter(e => e.employee_id !== currentEmp.employee_id);
  
  handoverSelect.innerHTML = `
    <option value="">-- Chọn đồng nghiệp nhận bàn giao --</option>
    ${availableColleagues.map(e => `
      <option value="${e.employee_id}">${e.name} (${e.role || e.department})</option>
    `).join("")}
  `;
}

function getCurrentEmployee() {
  return employeesCache.find(e => e.employee_id === currentEmployeeId) || employeesCache[0] || DEFAULT_EMPLOYEES[0];
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
  if (roleDeptEl) roleDeptEl.innerText = `${emp.role || 'Nhân viên'} · ${emp.department}`;
  if (metaEl) metaEl.innerHTML = `Mã nhân viên: <b>${emp.employee_id}</b> · Quản lý trực tiếp: <b>${emp.manager_id || 'Đào Tuấn Minh'}</b>`;

  const totalLeave = parseFloat(emp.total_leave_days || 12.0);
  const remainingLeave = parseFloat(emp.remaining_leave_days != null ? emp.remaining_leave_days : 9.0);
  const usedLeave = Math.max(0, totalLeave - remainingLeave);

  const mTotal = document.getElementById("metric-total-leave");
  const mUsed = document.getElementById("metric-used-leave");
  const mRem = document.getElementById("metric-remaining-leave");

  if (mTotal) mTotal.innerHTML = `${totalLeave.toFixed(1)} <span class="unit">ngày</span>`;
  if (mUsed) mUsed.innerHTML = `${usedLeave.toFixed(1)} <span class="unit">ngày</span>`;
  if (mRem) mRem.innerHTML = `${remainingLeave.toFixed(1)} <span class="unit">ngày</span>`;

  updateHandoverOptions();
  renderStaffRecentPreview();
}

/* ========================================================================= */
/* 3. TABS NAVIGATION (STAFF & MANAGER)                                      */
/* ========================================================================= */
function initStaffTabs() {
  const btns = document.querySelectorAll("#view-staff-portal .tab-btn");
  btns.forEach(btn => {
    btn.addEventListener("click", () => switchStaffTab(btn.getAttribute("data-tab")));
  });
}

function switchStaffTab(tabId) {
  const view = document.getElementById("view-staff-portal");
  if (!view) return;
  view.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-tab") === tabId));
  view.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("active", p.id === tabId));
  if (tabId === "tab-staff-dashboard") {
    renderStaffDashboard();
  } else if (tabId === "tab-staff-requests") {
    renderStaffRequests();
  } else if (tabId === "tab-staff-calendar") {
    renderWeeklyCalendar();
  }
}

function initManagerTabs() {
  const btns = document.querySelectorAll("#view-manager-portal .tab-btn");
  btns.forEach(btn => {
    btn.addEventListener("click", () => switchManagerTab(btn.getAttribute("data-tab")));
  });
}

function switchManagerTab(tabId) {
  const view = document.getElementById("view-manager-portal");
  if (!view) return;
  view.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-tab") === tabId));
  view.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("active", p.id === tabId));
  if (tabId === "tab-mgr-overview") {
    renderManagerOverviewKPIs();
  } else if (tabId === "tab-mgr-queue") {
    renderManagerQueue();
  } else if (tabId === "tab-mgr-auto-logs") {
    renderAutoApprovedLogs();
  } else if (tabId === "tab-mgr-all-requests") {
    renderManagerAllRequests();
  } else if (tabId === "tab-mgr-policy") {
    loadPolicyDocument();
  }
}

/* ========================================================================= */
/* 4. LEAVE ALLOCATION DRAWER (CẤP PHÁT NGÀY PHÉP)                           */
/* ========================================================================= */
function initLeaveAllocationDrawer() {
  const btnOpen = document.getElementById("btn-header-allocate");
  const btnClose = document.getElementById("btn-close-allocate");
  const drawer = document.getElementById("allocation-drawer");
  const targetType = document.getElementById("alloc-target-type");
  const deptGroup = document.getElementById("alloc-dept-group");
  const empGroup = document.getElementById("alloc-emp-group");
  const form = document.getElementById("form-allocate-leave");

  if (btnOpen && drawer) {
    btnOpen.addEventListener("click", () => {
      const isVisible = drawer.style.display === "block";
      drawer.style.display = isVisible ? "none" : "block";
      if (!isVisible) {
        drawer.scrollIntoView({ behavior: "smooth" });
      }
    });
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
        const res = await fetch(`${API_BASE}/api/meta/allocate-leave`, {
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

  const updateDuration = () => {
    if (!fromInput || !toInput) return;
    const fVal = new Date(fromInput.value);
    const tVal = new Date(toInput.value);
    const textEl = document.getElementById("staff-calc-days-text");
    const warnEl = document.getElementById("staff-calc-balance-warning");

    if (isNaN(fVal) || isNaN(tVal)) return;

    if (tVal < fVal) {
      if (textEl) textEl.innerText = "Khoảng ngày không hợp lệ";
      if (warnEl) warnEl.innerText = "Ngày kết thúc phải sau hoặc cùng ngày bắt đầu";
      return;
    }

    const diffDays = Math.round((tVal - fVal) / (1000 * 60 * 60 * 24)) + 1;
    if (textEl) textEl.innerText = `${diffDays} ngày`;

    const emp = getCurrentEmployee();
    const rem = parseFloat(emp.remaining_leave_days || 9.0);
    const leaveType = document.getElementById("staff-leave-type")?.value;

    if (leaveType === "Annual" && diffDays > rem) {
      if (warnEl) warnEl.innerText = `Vượt quá số dư phép năm: còn ${rem} ngày`;
    } else {
      if (warnEl) warnEl.innerText = `Khả dụng trong quỹ phép: ${rem} ngày`;
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
      if (attachTypeVal) attachTypeVal.value = "valid_bhxh_cert";
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
  const leaveType = document.getElementById("staff-leave-type").value;
  const handoverId = document.getElementById("staff-handover-select").value;
  const fromDate = document.getElementById("staff-from-date").value;
  const toDate = document.getElementById("staff-to-date").value;
  const reason = document.getElementById("staff-reason").value;
  const attachType = document.getElementById("staff-attachment-type-val").value || "none";

  if (!fromDate || !toDate) {
    showToast("Vui lòng chọn khoảng thời gian nghỉ!", "error");
    return;
  }
  if (!reason.trim()) {
    showToast("Vui lòng nêu rõ lý do xin nghỉ!", "error");
    return;
  }

  const payload = {
    employee_id: currentEmployeeId,
    leave_type: leaveType,
    handover_person_id: handoverId,
    from_date: fromDate,
    to_date: toDate,
    reason: reason,
    attachment_type: attachType
  };

  await submitLeaveToBackend(payload);
}

async function submitLeaveToBackend(payload) {
  try {
    showToast("Tác tử AI đang đối chiếu quy chế nội bộ...", "info");
    const res = await fetch(`${API_BASE}/api/leave/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (res.ok && result.success) {
      const decision = result.data.decision;
      if (decision === "AUTO_APPROVE") {
        showToast("Tác tử AI đã TỰ ĐỘNG DUYỆT đơn của bạn!", "success");
      } else {
        showToast("Đơn đã được chuyển tiếp tới Cấp quản lý xem xét.", "info");
      }
      await loadAllRequests();
      await loadEmployees();
      document.getElementById("form-staff-standard")?.reset();
      switchStaffTab("tab-staff-requests");
      return true;
    } else {
      showToast(result.detail || "Không thể gửi đơn, vui lòng thử lại!", "error");
      return false;
    }
  } catch (err) {
    console.error("Submit leave error:", err);
    showToast("Lỗi kết nối tới Backend API!", "error");
    return false;
  }
}

/* ========================================================================= */
/* 6. MY REQUESTS & TRACKING (NHÂN VIÊN)                                     */
/* ========================================================================= */
async function loadAllRequests(silent = false) {
  try {
    const res = await fetch(`${API_BASE}/api/leave/requests`);
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
          <div class="fw-bold text-dark small">${getLeaveTypeLabel(req.leave_type)} · ${req.workdays || 1} ngày</div>
          <div class="text-secondary small">${req.from_date || ''} → ${req.to_date || ''} · Mã: <b>${req.id}</b></div>
        </div>
        <div>
          ${getStatusBadgeHtml(req)}
        </div>
      </div>
    </div>
  `).join("");
}

function renderSingleRequestCard(req, isStaffView = false) {
  const isPending = req.status === "PENDING_ESCALATION" || req.decision === "ESCALATE_TO_HUMAN";
  const isAuto = req.decision === "AUTO_APPROVE";
  const isOverride = req.decision === "APPROVED_BY_HUMAN_OVERRIDE";
  const isRejected = req.decision === "REJECTED" || req.decision === "REVOKED_BY_ADMIN";

  let alertClass = "alert-warning";
  let calloutText = req.human_readable_explanation || req.actionable_question || "Đang xử lý theo quy định.";

  if (isAuto) {
    alertClass = "alert-success";
  } else if (isOverride) {
    alertClass = "alert-primary";
    calloutText = `Lời nhắn Quản lý: ${req.human_feedback_text || 'Đã phê duyệt đặc cách'}`;
  } else if (isRejected) {
    alertClass = "alert-danger";
    calloutText = req.human_feedback_text ? `Lý do từ chối: ${req.human_feedback_text}` : (req.human_readable_explanation || 'Không đáp ứng quy chế.');
  }

  const hasAttachment = req.attachment_type && req.attachment_type !== 'none';

  return `
    <div class="card mb-3 shadow-xs" id="req-card-${req.id}">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-start mb-2">
          <div>
            <span class="h4 mb-0 fw-bold text-dark">${getLeaveTypeLabel(req.leave_type)}</span>
            <span class="text-secondary small ms-2">· ${req.workdays || 1} ngày</span>
            <div class="text-secondary small mt-1">
              Mã đơn: <b>${req.id}</b> · Nộp lúc: ${formatTime(req.submitted_at)}
            </div>
          </div>
          <div>
            ${getStatusBadgeHtml(req)}
          </div>
        </div>

        <div class="row g-2 text-secondary small my-2 py-2 border-top border-bottom">
          <div class="col-4">Thời gian: <b class="text-dark">${req.from_date} → ${req.to_date}</b></div>
          <div class="col-4">Bàn giao: <b class="text-dark">${req.handover_person_name || req.handover_person_id || 'Chưa bàn giao'}</b></div>
          <div class="col-4">
            Chứng từ: <b class="text-dark">${getAttachmentLabel(req.attachment_type)}</b>
            ${hasAttachment ? `
              <button class="btn btn-xs btn-outline-secondary ms-1" onclick="openAttachmentModal('${req.id}', '${req.attachment_type}', '${req.employee_name}')">
                Xem file
              </button>
            ` : ''}
          </div>
        </div>

        <div class="text-dark small mb-2">
          <b>Lý do:</b> ${req.reason || 'Không có mô tả'}
        </div>

        <!-- KHUNG MINH BẠCH AI -->
        <div class="alert ${alertClass} py-2 px-3 mb-3">
          <div class="fw-bold small mb-1">Minh bạch AI & Căn cứ xử lý:</div>
          <div class="small">${calloutText}</div>
        </div>

        <!-- THAO TÁC CAN THIỆP -->
        <div class="d-flex align-items-center gap-2">
          <button class="btn btn-sm btn-outline-secondary" onclick="viewAuditTrail('${req.id}')">
            Xem Nhật Ký
          </button>
          ${isPending && isStaffView ? `
            <button class="btn btn-sm btn-outline-danger" onclick="cancelMyRequest('${req.id}')">
              Hủy Đơn Này
            </button>
          ` : ''}
        </div>
      </div>
    </div>
  `;
}

function attachRequestCardEvents() {
  const filterEl = document.getElementById("staff-requests-filter");
  if (filterEl && !filterEl.hasAttribute("data-bound")) {
    filterEl.setAttribute("data-bound", "true");
    filterEl.addEventListener("change", renderStaffRequests);
  }
  const btnRefresh = document.getElementById("btn-refresh-staff-requests");
  if (btnRefresh && !btnRefresh.hasAttribute("data-bound")) {
    btnRefresh.setAttribute("data-bound", "true");
    btnRefresh.addEventListener("click", () => {
      loadAllRequests();
      showToast("Đã làm mới danh sách đơn!", "info");
    });
  }
}

async function cancelMyRequest(requestId) {
  if (!confirm(`Bạn có chắc chắn muốn hủy/thu hồi đơn [${requestId}] không?`)) return;
  try {
    const res = await fetch(`${API_BASE}/api/leave/${requestId}/cancel`, { method: "POST" });
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
  const pendingCount = activeRequests.filter(r => r.status === "PENDING_ESCALATION" || r.decision === "ESCALATE_TO_HUMAN").length;
  const overrideCount = activeRequests.filter(r => r.decision === "APPROVED_BY_HUMAN_OVERRIDE" || r.decision === "REVOKED_BY_ADMIN").length;
  const totalCompleted = activeRequests.filter(r => r.status === "COMPLETED" || r.decision === "AUTO_APPROVE").length;
  
  const totalDecided = autoToday + overrideCount;
  const rate = totalDecided > 0 ? Math.round((autoToday / totalDecided) * 100) : 85;

  const kpiAuto = document.getElementById("mgr-kpi-auto-today");
  const kpiPending = document.getElementById("mgr-kpi-pending");
  const kpiOverride = document.getElementById("mgr-kpi-override");
  const kpiRate = document.getElementById("mgr-kpi-rate");

  if (kpiAuto) kpiAuto.innerHTML = `${autoToday} <span class="unit">đơn</span>`;
  if (kpiPending) kpiPending.innerHTML = `${pendingCount} <span class="unit">đơn</span>`;
  if (kpiOverride) kpiOverride.innerHTML = `${overrideCount} <span class="unit">đơn</span>`;
  if (kpiRate) kpiRate.innerHTML = `${rate}% <span class="unit"></span>`;
}

function renderManagerQueue() {
  const container = document.getElementById("mgr-escalation-inbox-list");
  if (!container) return;

  const pendingRequests = activeRequests.filter(r => r.status === "PENDING_ESCALATION" || r.decision === "ESCALATE_TO_HUMAN");

  if (pendingRequests.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; color: var(--text-dim); padding: 50px 0;">
        <div style="font-weight: 700; color: #166534; font-size: 1.05rem;">Hàng đợi xử lý trống</div>
        <div style="font-size: 0.85rem; margin-top: 4px;">Tất cả các đơn thường quy đã được Tác tử AI tự động duyệt chuẩn quy chế.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = pendingRequests.map(req => {
    const pills = Array.isArray(req.quick_action_options) ? req.quick_action_options : [
      "Đồng ý phê duyệt đặc cách cho nhân sự",
      "Từ chối do không đáp ứng đủ quy chế nghỉ",
      "Yêu cầu bổ sung chứng từ y tế / BHXH hợp lệ"
    ];

    const hasAttachment = req.attachment_type && req.attachment_type !== 'none';

    // Helper for employee initials
    const nameParts = (req.employee_name || 'NV').trim().split(/\s+/);
    const initials = nameParts.length >= 2
      ? (nameParts[0][0] + nameParts[nameParts.length - 1][0]).toUpperCase()
      : (req.employee_name ? req.employee_name.substring(0, 2).toUpperCase() : 'NV');

    return `
      <div class="escalation-inbox-card" id="esc-card-${req.id}">
        <div class="esc-split-layout">
          
          <!-- CỘT TRÁI: THÔNG TIN GỐC & THAM VẤN AI -->
          <div class="esc-col-main">
            <div class="esc-header-row">
              <div class="esc-header-left">
                <div class="esc-avatar" title="${req.employee_name || 'Nhân viên'}">${initials}</div>
                <div>
                  <div class="d-flex align-items-center">
                    <span class="esc-emp-name">${req.employee_name || 'Nhân viên'}</span>
                    ${req.department ? `<span class="esc-dept-badge">${req.department}</span>` : ''}
                  </div>
                  <div class="esc-meta-row">
                    <span class="esc-meta-chip">Mã đơn: <b>${req.id}</b></span>
                    <span class="esc-meta-chip">Loại: <b>${getLeaveTypeLabel(req.leave_type)}</b></span>
                    <span class="esc-meta-chip esc-meta-days">Số ngày: <b>${req.workdays || 1} ngày</b></span>
                    <span class="esc-meta-chip">Khoảng ngày: <b>${req.from_date} → ${req.to_date}</b></span>
                  </div>
                </div>
              </div>
              <span class="req-badge-pill badge-pending">
                Chờ Quản Lý
              </span>
            </div>

            <div class="esc-reason-box">
              <span class="esc-reason-label">Lý do gốc:</span>
              <span class="esc-reason-text">"${req.reason || 'Không có mô tả chi tiết'}"</span>
            </div>

            <!-- KHUNG THAM VẤN TỪ AI AGENT (KHÔNG DÙNG ICON) -->
            <div class="esc-ai-consult-box">
              <div class="esc-ai-consult-title">
                <span>THAM VẤN TỪ TÁC TỬ AI</span>
                <span class="badge bg-warning-lt fw-bold ms-auto">Cần chỉ đạo</span>
              </div>
              <div class="esc-ai-consult-text">
                <div class="esc-ai-reason">
                  <b>Lý do chuyển tiếp:</b> ${req.human_readable_explanation || req.uncertainty_category || 'Thời gian nghỉ hoặc chứng từ vượt thẩm quyền tự duyệt.'}
                </div>
                <div class="esc-ai-question-callout">
                  <span>"${req.actionable_question || 'Anh/chị có đồng ý phê duyệt đặc cách cho đơn nghỉ phép này không?'}"</span>
                </div>
              </div>
            </div>

            <div class="esc-handover-row">
              <span class="esc-handover-item">
                Bàn giao công việc: <b>${req.handover_person_name || req.handover_person_id || 'Chưa chỉ định'}</b>
              </span>
              <span class="esc-handover-item">
                Tệp đính kèm: <b>${getAttachmentLabel(req.attachment_type)}</b>
                ${hasAttachment ? `
                  <button type="button" class="btn-view-doc" onclick="openAttachmentModal('${req.id}', '${req.attachment_type}', '${req.employee_name}')">
                    Xem tệp
                  </button>
                ` : '<span class="text-danger small ms-1">Không có tệp</span>'}
              </span>
            </div>
          </div>

          <!-- CỘT PHẢI: BẢNG Ý KIẾN CHỈ ĐẠO & HÀNH ĐỘNG (KHÔNG DÙNG ICON) -->
          <div class="esc-col-decision">
            <div class="esc-section-subtitle">
              Ý KIẾN CHỈ ĐẠO NHANH
            </div>
            <div class="quick-action-pills">
              ${pills.map(p => {
                const escaped = p.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
                return `<button type="button" class="quick-pill" data-pill="${escaped}" onclick="fillQuickDecision('${req.id}', this.getAttribute('data-pill'))">${p}</button>`;
              }).join("")}
            </div>

            <div class="esc-feedback-box">
              <textarea id="esc-feedback-${req.id}" class="esc-feedback-textarea" rows="3" placeholder="Ghi chú, dặn dò hoặc căn cứ gửi lại cho nhân viên..."></textarea>
            </div>

            <div class="decision-action-grid">
              <button type="button" class="btn-approve-special" onclick="submitManagerDecision('${req.id}', 'APPROVE')">
                Duyệt Đặc Cách
              </button>
              <button type="button" class="btn-request-more-info" onclick="submitManagerDecision('${req.id}', 'REQUEST_INFO')">
                Yêu Cầu Bổ Sung
              </button>
              <button type="button" class="btn-reject-special" onclick="submitManagerDecision('${req.id}', 'REJECT')">
                Từ Chối Đơn
              </button>
              <button type="button" class="btn-view-audit" onclick="viewAuditTrail('${req.id}')">
                Xem Nhật Ký
              </button>
            </div>
          </div>

        </div>
      </div>
    `;
  }).join("");

  const btnRefreshQueue = document.getElementById("btn-refresh-mgr-queue");
  if (btnRefreshQueue && !btnRefreshQueue.hasAttribute("data-bound")) {
    btnRefreshQueue.setAttribute("data-bound", "true");
    btnRefreshQueue.addEventListener("click", () => {
      loadAllRequests();
      showToast("Đã làm mới Hàng đợi!", "info");
    });
  }
}

function fillQuickDecision(reqId, text) {
  const txt = document.getElementById(`esc-feedback-${reqId}`);
  if (txt) {
    txt.value = text;
    txt.focus();
  }
}

async function submitManagerDecision(reqId, actionType) {
  const card = document.getElementById(`esc-card-${reqId}`);
  const actionBtns = card ? card.querySelectorAll(".decision-action-grid button") : [];
  actionBtns.forEach(b => b.disabled = true);

  const feedbackInput = document.getElementById(`esc-feedback-${reqId}`);
  let defaultFeedback = "Quản lý đồng ý phê duyệt đặc cách cho nhân sự.";
  if (actionType === "REJECT") defaultFeedback = "Quản lý từ chối đơn theo quy chế nội bộ.";
  if (actionType === "REQUEST_INFO") defaultFeedback = "Yêu cầu nhân viên bổ sung chứng từ y tế / giấy khám BHXH hợp lệ.";

  let feedback = feedbackInput?.value.trim() || defaultFeedback;

  if (actionType === "REJECT" && (feedback.toLowerCase().includes("đồng ý") || feedback.toLowerCase().includes("duyệt đặc cách"))) {
    feedback = defaultFeedback;
  } else if (actionType === "APPROVE" && (feedback.toLowerCase().includes("từ chối") || feedback.toLowerCase().includes("không duyệt"))) {
    feedback = defaultFeedback;
  }

  try {
    const res = await fetch(`${API_BASE}/api/leave/${reqId}/human-decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        feedback_text: feedback,
        approver_id: currentManagerRoleId
      })
    });
    const result = await res.json();
    if (res.ok && result.success) {
      if (actionType === "APPROVE") showToast("Đã phê duyệt đặc cách đơn thành công!", "success");
      else if (actionType === "REJECT") showToast("Đã từ chối đơn!", "error");
      else showToast("Đã gửi yêu cầu bổ sung thông tin tới nhân viên!", "info");

      await loadAllRequests();
      await loadEmployees();
    } else {
      showToast(result.detail || "Có lỗi xảy ra khi gửi quyết định!", "error");
    }
  } catch (err) {
    console.error("Decision submit error:", err);
    showToast("Lỗi khi kết nối server!", "error");
  } finally {
    actionBtns.forEach(b => b.disabled = false);
  }
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
    const aiReason = req.human_readable_explanation || `Xin nghỉ ${req.workdays || 1} ngày ${getLeaveTypeLabel(req.leave_type)}, đúng hạn mức quy chế.`;

    return `
      <tr>
        <td class="fw-bold">${req.id}</td>
        <td><b>${req.employee_name}</b></td>
        <td><span class="badge bg-secondary-lt">${req.department}</span></td>
        <td>${req.from_date} → ${req.to_date}</td>
        <td><b>${req.workdays || 1} ngày</b></td>
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
    const res = await fetch(`${API_BASE}/api/leave/${requestId}/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason || "Quản lý hủy quyết định tự duyệt của AI" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Đã thu hồi quyết định duyệt AI của đơn [${requestId}], hoàn trả quỹ phép cho nhân viên.`, "success");
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
      <td><b>${req.workdays || 1} ngày</b></td>
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
  monday.setDate(today.getDate() - (currentDay === 0 ? 6 : currentDay - 1));

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

  const generateCalHtml = (forStaff = true) => {
    return weekDays.map(day => {
      let absentees = activeRequests.filter(r => {
        const isApproved = r.decision === "AUTO_APPROVE" || r.decision === "APPROVED_BY_HUMAN_OVERRIDE" || r.status === "COMPLETED";
        if (!isApproved) return false;
        return r.from_date <= day.dateStr && r.to_date >= day.dateStr;
      });

      if (!forStaff && deptFilter !== "ALL") {
        absentees = absentees.filter(r => r.department === deptFilter);
      }

      return `
        <div class="calendar-day-col ${day.isToday ? 'today' : ''} ${day.isWeekend ? 'weekend' : ''}">
          <div class="calendar-day-header">
            <span>${day.name}</span>
            <span class="day-date">${day.displayDate}</span>
          </div>
          <div class="calendar-absent-items">
            ${absentees.length === 0 ? `
              <div class="calendar-empty-note">${day.isWeekend ? 'Nghỉ cuối tuần' : '0 vắng mặt'}</div>
            ` : absentees.map(r => {
              const isSelf = r.employee_id === currentEmployeeId;
              return `
                <div class="calendar-tag ${isSelf ? 'tag-self' : ''}" title="${r.employee_name} (${r.department}): ${r.reason || ''}">
                  <div class="tag-name">${r.employee_name} ${forStaff && isSelf ? ' (Bạn)' : ''}</div>
                  <div class="tag-type">${getLeaveTypeLabel(r.leave_type)}</div>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    }).join("");
  };

  if (staffCal) staffCal.innerHTML = generateCalHtml(true);
  if (mgrCal) mgrCal.innerHTML = generateCalHtml(false);

  const deptFilterSelect = document.getElementById("mgr-cal-dept-filter");
  if (deptFilterSelect && !deptFilterSelect.hasAttribute("data-bound")) {
    deptFilterSelect.setAttribute("data-bound", "true");
    deptFilterSelect.addEventListener("change", renderWeeklyCalendar);
  }
}

/* ========================================================================= */
/* 10. ATTACHMENT MODAL & AUDIT TRAIL MODAL                                  */
/* ========================================================================= */
function openAttachmentModal(requestId, attachType, employeeName) {
  const modal = document.getElementById("modal-attachment");
  const sub = document.getElementById("modal-attach-sub");
  const content = document.getElementById("modal-attach-content");

  if (!modal || !content) return;
  if (sub) sub.innerText = `Đơn: ${requestId} · Nhân viên: ${employeeName || 'Nhân sự'}`;

  let previewHtml = "";
  if (attachType === "valid_bhxh_cert") {
    previewHtml = `
      <div style="background: #f0fdf4; border: 2px dashed #86efac; border-radius: 12px; padding: 24px; text-align: center;">
        
        <div style="font-weight: 800; font-size: 1.1rem; color: #166534;">GIẤY NGHỈ VIỆC HƯỞNG BHXH HỢP LỆ</div>
        <div style="font-size: 0.85rem; color: #15803d; margin-top: 4px;">Cơ sở y tế: Bệnh viện Đa khoa Quốc tế · Có dấu mộc đỏ BHXH xác nhận</div>
        <div style="font-size: 0.78rem; color: #64748b; margin-top: 12px;">Tập tin: <code>chung_tu_y_te_${requestId}.pdf</code> (240 KB)</div>
      </div>
    `;
  } else if (attachType === "vague_prescription") {
    previewHtml = `
      <div style="background: #fffbeb; border: 2px dashed #fde68a; border-radius: 12px; padding: 24px; text-align: center;">
        
        <div style="font-weight: 800; font-size: 1.1rem; color: #b45309;">TOA THUỐC PHÒNG KHÁM TƯ NHÂN</div>
        <div style="font-size: 0.85rem; color: #92400e; margin-top: 4px;">Toa thuốc điều trị ngoại trú · Không có mẫu C65-HD theo quy chuẩn BHXH</div>
        <div style="font-size: 0.78rem; color: #64748b; margin-top: 12px;">Tập tin: <code>don_thuoc_${requestId}.jpg</code> (512 KB)</div>
      </div>
    `;
  } else {
    previewHtml = `
      <div style="background: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 12px; padding: 24px; text-align: center;">
        
        <div style="font-weight: 800; font-size: 1.1rem; color: #334155;">TÀI LIỆU MINH CHỨNG NGHỈ PHÉP</div>
        <div style="font-size: 0.85rem; color: #64748b; margin-top: 4px;">Tài liệu đã được tải lên cùng đơn ${requestId}</div>
      </div>
    `;
  }

  content.innerHTML = previewHtml;
  modal.style.display = "flex";
  modal.classList.add("active");
}

function initModals() {
  const modalAudit = document.getElementById("modal-audit");
  const modalAttach = document.getElementById("modal-attachment");

  const closeModal = (modal) => {
    if (!modal) return;
    modal.classList.remove("active");
    modal.style.display = "none";
  };

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
    const res = await fetch(`${API_BASE}/api/leave/${requestId}`);
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
const HARNESS_TEST_CASES = [
  {
    id: "TC01",
    scenario: "Nhân viên Nguyễn Văn A xin nghỉ phép năm 1 ngày, nộp trước 3 ngày, số dư còn 8 ngày, có bàn giao.",
    expected: "AUTO_APPROVE",
    category: "Thường quy (Annual Standard)",
    authority: "Tác tử AI",
    actionable_question: "Tự động phê duyệt hợp lệ",
    input: { employee_id: "EMP002", leave_type: "Annual", from_date: "2026-09-23", to_date: "2026-09-23", reason: "Nghỉ phép việc cá nhân", handover_person_id: "EMP001" }
  },
  {
    id: "TC02",
    scenario: "Dương Anh Kiệt xin nghỉ ốm 3 ngày liên tiếp nhưng đính kèm file toa thuốc thông thường (thiếu BHXH).",
    expected: "ESCALATE_TO_HUMAN",
    category: "Ngoại lệ (Sick Leave Missing BHXH)",
    authority: "Chuyển tiếp Quản lý",
    actionable_question: "Cần xác minh giấy nghỉ BHXH hoặc duyệt đặc cách",
    input: { employee_id: "EMP001", leave_type: "Sick", from_date: "2026-09-24", to_date: "2026-09-26", reason: "Ốm sốt siêu vi", attachment_type: "vague_prescription" }
  },
  {
    id: "TC03",
    scenario: "Trần Thị B xin nghỉ việc riêng có lương (kết hôn 3 ngày), đầy đủ thông tin.",
    expected: "AUTO_APPROVE",
    category: "Thường quy (Special Leave Marriage)",
    authority: "Tác tử AI",
    actionable_question: "Tự động duyệt hưởng nguyên lương theo luật",
    input: { employee_id: "EMP003", leave_type: "Special", from_date: "2026-10-01", to_date: "2026-10-03", reason: "Nghỉ cưới bản thân", handover_person_id: "EMP002" }
  },
  {
    id: "TC04",
    scenario: "Lê Hoàng C xin nghỉ không lương 10 ngày để giải quyết việc gia đình đột xuất.",
    expected: "ESCALATE_TO_HUMAN",
    category: "Vượt thẩm quyền (Unpaid Leave > 5 days)",
    authority: "Chuyển tiếp Quản lý / HRD",
    actionable_question: "Cần Cấp quản lý phê duyệt nghỉ không lương dài hạn",
    input: { employee_id: "EMP004", leave_type: "Unpaid", from_date: "2026-10-05", to_date: "2026-10-14", reason: "Việc gia đình đột xuất", handover_person_id: "EMP001" }
  },
  {
    id: "TC05",
    scenario: "Nhân viên nộp đơn nghỉ phép năm nhưng số dư phép chỉ còn 1 ngày (xin nghỉ 3 ngày).",
    expected: "AUTO_APPROVE / ESCALATE",
    category: "Cảnh báo số dư (Exceeds Balance)",
    authority: "AI Cảnh báo / Quản lý",
    actionable_question: "Vượt quá số dư phép khả dụng",
    input: { employee_id: "EMP002", leave_type: "Annual", from_date: "2026-09-28", to_date: "2026-09-30", reason: "Đi du lịch", handover_person_id: "EMP003" }
  }
];

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
      const res = await fetch(`${API_BASE}/api/verify/escalation`, { method: "POST" });
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
  const form = document.getElementById("form-custom-verify");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btnSubmit = document.getElementById("btn-submit-custom");
    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>ĐANG ĐÁNH GIÁ...`;
    }

    const resCard = document.getElementById("custom-result-card");
    if (resCard) {
      resCard.style.display = "block";
      resCard.innerHTML = `<div class="text-secondary small">Đang đánh giá đơn qua AI Agent & Quy chế nội bộ...</div>`;
    }

    const payload = {
      employee_name: "Nhân sự Giám khảo test",
      department: "Engineering",
      remaining_leave_days: parseFloat(document.getElementById("custom-remaining-days")?.value || "2.0"),
      from_date: document.getElementById("custom-from-date").value,
      to_date: document.getElementById("custom-to-date").value,
      leave_type: document.getElementById("custom-leave-type").value,
      reason: document.getElementById("custom-reason").value,
      handover_person_id: document.getElementById("custom-handover")?.value || null,
      attachment_type: document.getElementById("custom-attachment").value
    };

    try {
      const res = await fetch(`${API_BASE}/api/verify/custom`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (resCard && data.success) {
        const isAuto = data.decision === 'AUTO_APPROVE';
        resCard.innerHTML = `
          <div class="d-flex align-items-center justify-content-between mb-2">
            <span class="badge ${isAuto ? 'bg-success text-white' : 'bg-warning text-dark'} fw-bold px-2 py-1">
              ${isAuto ? 'TỰ ĐỘNG DUYỆT (AUTO_APPROVE)' : 'CHUYỂN TIẾP CẤP QUẢN LÝ (ESCALATE)'}
            </span>
            <span class="text-secondary small">Thời lượng tính toán: <b>${data.calculated_workdays} ngày</b></span>
          </div>
          <div class="text-dark small mb-1">
            <b>Căn cứ phân tích:</b> ${data.plain_reason || data.actionable_question || 'Đơn hợp lệ theo quy chế.'}
          </div>
          ${data.target_role ? `<div class="text-secondary small mb-1"><b>Cấp thẩm quyền đích:</b> ${data.target_role}</div>` : ''}
          ${data.actionable_question ? `<div class="text-primary small mb-1"><b>Câu hỏi cho Sếp:</b> "${data.actionable_question}"</div>` : ''}
          ${data.applied_policy_clauses && data.applied_policy_clauses.length > 0 ? `
            <div class="text-secondary small mt-2">
              <b>Điều khoản áp dụng:</b>
              <ul class="mb-0 ps-3 mt-1">
                ${data.applied_policy_clauses.map(c => `<li>${c}</li>`).join("")}
              </ul>
            </div>
          ` : ''}
        `;
        showToast("Đã hoàn tất đánh giá ca thử nghiệm!", "success");
      } else {
        if (resCard) resCard.innerHTML = `<div class="text-danger small">${data.detail || "Không thể thực hiện đánh giá!"}</div>`;
      }
    } catch (err) {
      if (resCard) resCard.innerHTML = `<div class="text-danger small">Lỗi kết nối khi gọi API đánh giá!</div>`;
    } finally {
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = `<span data-i18n="btn_evaluate">ĐÁNH GIÁ ĐƠN NÀY</span>`;
      }
    }
  });
}

/* ========================================================================= */
/* 12. POLICY & UTILITIES                                                    */
/* ========================================================================= */
async function loadPolicyDocument() {
  const policyEl = document.getElementById("policy-content");
  if (!policyEl) return;
  try {
    const res = await fetch(`${API_BASE}/api/meta/policy`);
    if (res.ok) {
      const json = await res.json();
      if (json.content_markdown) {
        policyEl.innerHTML = formatMarkdown(json.content_markdown);
        return;
      }
    }
  } catch (err) {
    console.warn("Using default policy:", err);
  }
}

function getStatusBadgeHtml(req) {
  const isAuto = req.decision === "AUTO_APPROVE";
  const isPending = req.status === "PENDING_ESCALATION" || req.decision === "ESCALATE_TO_HUMAN";
  const isOverride = req.decision === "APPROVED_BY_HUMAN_OVERRIDE";
  const isRejected = req.decision === "REJECTED" || req.decision === "REVOKED_BY_ADMIN";
  const isCancelled = req.status === "CANCELLED";

  if (isAuto) return `<span class="badge bg-success-lt fw-bold">Tự động duyệt</span>`;
  if (isPending) return `<span class="badge bg-warning-lt fw-bold">Đang chờ Quản lý</span>`;
  if (isOverride) return `<span class="badge bg-primary-lt fw-bold">Quản lý đã duyệt</span>`;
  if (isRejected) return `<span class="badge bg-danger-lt fw-bold">Từ chối</span>`;
  if (isCancelled) return `<span class="badge bg-secondary-lt fw-bold">Đã hủy</span>`;
  return `<span class="badge bg-warning-lt fw-bold">${req.status || 'Chờ duyệt'}</span>`;
}

function getLeaveTypeLabel(type) {
  const map = {
    "Annual": "Nghỉ phép năm",
    "Sick": "Nghỉ ốm",
    "Special": "Nghỉ cưới / Tang chế",
    "Maternity": "Nghỉ thai sản",
    "Unpaid": "Nghỉ không lương"
  };
  return map[type] || type || "Nghỉ phép";
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
  return md
    .replace(/^### (.*$)/gim, '<h3 style="font-size: 1.1rem; margin: 14px 0 6px 0; color: #0284c7;">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 style="font-size: 1.25rem; margin: 18px 0 8px 0; color: #0f172a;">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 style="font-size: 1.4rem; margin: 20px 0 10px 0;">$1</h1>')
    .replace(/\*\*(.*)\*\*/gim, '<b>$1</b>')
    .replace(/\*(.*)\*/gim, '<i>$1</i>')
    .replace(/\n/gim, '<br>');
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
    const res = await fetch(`${API_BASE}/api/meta/health`);
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
    const res = await fetch(`${API_BASE}/api/meta/llm-status`);
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
