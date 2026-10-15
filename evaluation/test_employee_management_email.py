"""Quản lý nhân viên: email liên lạc không bắt buộc, đúng định dạng và không trùng."""

M = {'X-Actor-ID': 'M'}


def _add(client, **body):
    return client.post('/api/management/employees', headers=M,
                       json={'name': 'Nguyễn Văn Mới', 'department': 'Engineering', **body})


def test_add_employee_without_email(client, isolated_db):
    res = _add(client)
    assert res.status_code == 201
    assert res.json()['data']['email'] is None


def test_add_employee_with_email_is_listed(client, isolated_db):
    res = _add(client, email='  Moi.Nguyen@Gmail.com ')
    assert res.status_code == 201
    assert res.json()['data']['email'] == 'moi.nguyen@gmail.com'
    listed = client.get('/api/management/employees', headers=M).json()['data']
    assert any(e['email'] == 'moi.nguyen@gmail.com' for e in listed)


def test_add_employee_rejects_invalid_email(client, isolated_db):
    res = _add(client, email='khong-phai-email')
    assert res.status_code == 422
    assert 'Email' in str(res.json()['detail'])


def test_add_employee_rejects_duplicate_email(client, isolated_db):
    assert _add(client, email='trung@gmail.com').status_code == 201
    res = _add(client, name='Người Khác', email='TRUNG@gmail.com')
    assert res.status_code == 409
    assert 'Email' in res.json()['detail']
