/* Directory administration. Existing test-case definitions are deliberately untouched. */
let managementEmployees = [];
let managementDepartments = [];
let managementLoadVersion = 0;
let employeeManagementMutationInFlight = false;

function employeeManagementMessage(message = '', success = false) {
  const target = document.getElementById('employee-management-message');
  if (target) { target.textContent = message; target.dataset.kind = success ? 'success' : 'error'; }
}

function hideEmployeeManagement() {
  ++managementLoadVersion;
}

async function showEmployeeManagement() {
  employeeManagementMessage();
  await loadEmployeeManagement();
}

function renderEmployeeManagement() {
  const body = document.getElementById('employee-management-rows');
  body.replaceChildren();
  for (const employee of managementEmployees) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    const title = document.createElement('strong'); title.textContent = employee.name;
    const id = document.createElement('small'); id.textContent = employee.employee_id;
    name.append(title, id);
    const dept = document.createElement('td'); dept.textContent = employee.department;
    const role = document.createElement('td'); role.textContent = employee.role || 'Nhân viên';
    const actions = document.createElement('td');
    const edit = document.createElement('button');
    edit.type = 'button'; edit.className = 'employee-management-edit'; edit.textContent = 'Sửa chức danh';
    edit.disabled = !employee.can_edit;
    edit.addEventListener('click', () => editManagedEmployeeTitle(employee, edit));
    actions.append(edit);
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'employee-management-delete'; button.textContent = employee.is_test_employee ? 'Đã khóa' : 'Xóa';
    button.disabled = !employee.can_delete;
    button.setAttribute('aria-label', `Xóa nhân viên ${employee.name}`);
    if (!employee.can_delete) button.title = employee.delete_lock_reason || 'Giữ tài khoản quản lý để duyệt đơn.';
    button.addEventListener('click', () => removeManagedEmployee(employee, button));
    actions.append(button); row.append(name, dept, role, actions); body.append(row);
  }
  if (!managementEmployees.length) {
    const row = document.createElement('tr'); const cell = document.createElement('td');
    cell.colSpan = 4; cell.className = 'employee-management-empty'; cell.textContent = 'Chưa có nhân viên trong phạm vi quản lý.';
    row.append(cell); body.append(row);
  }
  document.getElementById('employee-management-count').textContent = `${managementEmployees.length} nhân sự đang hoạt động`;
}

async function loadEmployeeManagement() {
  const version = ++managementLoadVersion;
  const actor = currentManagerRoleId;
  const submit = document.getElementById('employee-management-submit'); submit.disabled = true;
  try {
    const response = await apiFetch(`${API_BASE}/api/management/employees`);
    const data = await response.json();
    if (version !== managementLoadVersion || actor !== currentManagerRoleId) return;
    if (!response.ok) throw new Error(formatApiError(data.detail));
    managementEmployees = data.data; managementDepartments = data.departments;
    const select = document.getElementById('employee-management-department');
    const previous = select.value; select.replaceChildren();
    managementDepartments.forEach(dept => select.add(new Option(dept, dept)));
    if (managementDepartments.includes(previous)) select.value = previous;
    submit.disabled = !managementDepartments.length || employeeManagementMutationInFlight;
    renderEmployeeManagement();
  } catch (error) {
    if (version !== managementLoadVersion || actor !== currentManagerRoleId) return;
    managementEmployees = []; managementDepartments = [];
    document.getElementById('employee-management-department').replaceChildren();
    renderEmployeeManagement(); employeeManagementMessage(error.message || 'Không tải được danh sách nhân viên.');
  }
}

async function refreshEmployeePickers() {
  const previousEmployee = currentEmployeeId;
  await loadEmployees();
  if (previousEmployee !== currentEmployeeId) {
    editingRequestId = null; currentProofId = null; currentProofContext = null; selectedProofFile = null;
  }
  updateHandoverOptions();
  await loadEmployeeManagement();
}

async function addManagedEmployee(event) {
  event.preventDefault();
  if (employeeManagementMutationInFlight) return;
  const name = document.getElementById('employee-management-name');
  const department = document.getElementById('employee-management-department');
  const jobTitle = document.getElementById('employee-management-job-title');
  const submit = document.getElementById('employee-management-submit');
  const trimmed = name.value.trim();
  if (!trimmed || !managementDepartments.includes(department.value)) {
    employeeManagementMessage('Vui lòng nhập tên và chọn phòng ban hợp lệ.'); return;
  }
  employeeManagementMutationInFlight = true;
  submit.disabled = true; employeeManagementMessage();
  try {
    const response = await apiFetch(`${API_BASE}/api/management/employees`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: trimmed, department: department.value, job_title: jobTitle.value.trim() || 'Nhân viên'})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatApiError(data.detail));
    name.value = ''; jobTitle.value = ''; await refreshEmployeePickers();
    employeeManagementMessage(`Đã thêm ${data.data.name}. Có thể chọn nhân viên ở mục Staff.`, true);
  } catch (error) { employeeManagementMessage(error.message || 'Không thêm được nhân viên.'); }
  finally { employeeManagementMutationInFlight = false; submit.disabled = !managementDepartments.length; }
}

async function editManagedEmployeeTitle(employee, button) {
  if (employeeManagementMutationInFlight) return;
  const value = window.prompt(`Nhập chức danh cho ${employee.name}:`, employee.role || 'Nhân viên');
  if (value === null) return;
  const title = value.trim();
  if (!title || title.length > 100) { employeeManagementMessage('Chức danh cần từ 1 đến 100 ký tự.'); return; }
  employeeManagementMutationInFlight = true; button.disabled = true;
  try {
    const response = await apiFetch(`${API_BASE}/api/management/employees/${encodeURIComponent(employee.employee_id)}`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({job_title: title})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatApiError(data.detail));
    await refreshEmployeePickers();
    employeeManagementMessage(`Đã đổi chức danh của ${employee.name} thành ${data.data.role}.`, true);
  } catch (error) { employeeManagementMessage(error.message || 'Không sửa được chức danh.'); button.disabled = false; }
  finally { employeeManagementMutationInFlight = false; document.getElementById('employee-management-submit').disabled = !managementDepartments.length; }
}

async function removeManagedEmployee(employee, button) {
  if (employeeManagementMutationInFlight) return;
  if (!window.confirm(`Xóa ${employee.name} khỏi danh sách nhân viên?\n\nNhân viên sẽ không còn được chọn để nộp đơn hoặc nhận bàn giao. Hồ sơ cũ và test case vẫn giữ nguyên.`)) return;
  employeeManagementMutationInFlight = true;
  button.disabled = true; employeeManagementMessage();
  try {
    const response = await apiFetch(`${API_BASE}/api/management/employees/${encodeURIComponent(employee.employee_id)}`, {method: 'DELETE'});
    const data = await response.json();
    if (!response.ok) throw new Error(formatApiError(data.detail));
    // Update memory immediately so an unsuccessful refresh cannot re-enable the deleted identity.
    employeesCache = employeesCache.filter(e => e.employee_id !== employee.employee_id);
    delete authTokenCache[employee.employee_id];
    populateEmployeeDropdowns();
    await refreshEmployeePickers();
    employeeManagementMessage(`Đã xóa ${employee.name} khỏi danh sách chọn. Hồ sơ cũ được giữ nguyên.`, true);
  } catch (error) { employeeManagementMessage(error.message || 'Không xóa được nhân viên.'); button.disabled = false; }
  finally { employeeManagementMutationInFlight = false; document.getElementById('employee-management-submit').disabled = !managementDepartments.length; }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('employee-management-form')?.addEventListener('submit', addManagedEmployee);
  document.getElementById('manager-role-select')?.addEventListener('change', () => {
    if (currentMode === 'manager' && document.getElementById('tab-mgr-employees')?.classList.contains('active')) { employeeManagementMessage(); loadEmployeeManagement(); }
  });
});
