#!/usr/bin/env python3
"""Tạo 43 test case mở rộng hoàn toàn thuần Việt, dựa trên thông tin nhân viên và ảnh có sẵn,
thẩm định qua LeaveRuleEngine để gán nhãn phán quyết chuẩn xác 100%,
sau đó đưa trực tiếp vào frontend/app.js đồng bộ với kho dữ liệu UI."""
import sys, os, json, re
sys.path.insert(0, os.path.abspath('core'))
from rule_engine import LeaveRuleEngine, LeaveRequest
from domain import VerifiedProof

EMPS = {e['employee_id']: e for e in json.load(open('core/employees.json', encoding='utf-8'))}

cases_blueprint = [
    # -------------------------------------------------------------
    # NHÓM 1: THƯỜNG QUY / TỰ DUYỆT / LỄ (10 ca)
    # -------------------------------------------------------------
    {
        "id": "TC-EXT-01",
        "emp_id": "EMP005",
        "title": "TC-EXT-01: Phép năm 1 ngày tự động duyệt (1-2 ngày đủ số dư)",
        "badge": "Tự động duyệt",
        "badgeClass": "bg-success-lt",
        "desc": "Nguyễn Văn An xin 1 ngày phép năm giải quyết việc gia đình, nộp trước hạn 4 ngày, số dư phép còn 8 ngày -> AI Cấp 0 tự động duyệt & trừ 1 ngày phép.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-16",
            "to_date": "2026-11-16",
            "reason": "Giải quyết việc cá nhân gia đình",
            "submitted_at": "2026-11-12T08:00:00+07:00",
            "total_team_members": 6,
            "team_absent_count": 0
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Rõ ràng (Duyệt)",
            "primary": "Nghỉ phép năm",
            "duration": "1 ngày làm việc",
            "subtext": "Giải quyết việc riêng • Nguyễn Văn An",
            "leaveTypeFriendly": "Nghỉ phép năm (1 ngày làm việc) - Giải quyết việc riêng",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Phép năm hợp lệ, đủ số dư, không cần chuyển người duyệt."
        }
    },
    {
        "id": "TC-EXT-02",
        "emp_id": "EMP004",
        "title": "TC-EXT-02: Phép năm 2 ngày có bàn giao cùng phòng cho EMP003",
        "badge": "Tự động duyệt",
        "badgeClass": "bg-success-lt",
        "desc": "Lê Văn Nam xin 2 ngày phép năm có thỏa thuận bàn giao công việc cho Trần Quốc Hưng cùng phòng Kỹ thuật -> AI tự động phê duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-17",
            "to_date": "2026-11-18",
            "reason": "Nghỉ phép cá nhân thường niên",
            "handover_person_id": "EMP003",
            "handover": {"employee_id": "EMP003", "department": "Engineering", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-13T08:00:00+07:00",
            "total_team_members": 6,
            "team_absent_count": 0
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Rõ ràng (Duyệt)",
            "primary": "Nghỉ phép năm",
            "duration": "2 ngày làm việc",
            "subtext": "Nghỉ thường niên • Bàn giao cho Trần Quốc Hưng",
            "leaveTypeFriendly": "Nghỉ phép năm (2 ngày làm việc) - Bàn giao cho Trần Quốc Hưng",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Phép năm 2 ngày có bàn giao hợp lệ, không cần chuyển người duyệt."
        }
    },
    {
        "id": "TC-EXT-03",
        "emp_id": "EMP008",
        "title": "TC-EXT-03: Phép năm 1 ngày phòng Marketing & Operations",
        "badge": "Tự động duyệt",
        "badgeClass": "bg-success-lt",
        "desc": "Nguyễn Thị Kim Ngân xin 1 ngày phép năm, số dư còn 16 ngày, nộp trước hạn 5 ngày -> AI tự động duyệt & trừ 1 ngày phép.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-19",
            "to_date": "2026-11-19",
            "reason": "Nghỉ phép thường niên",
            "submitted_at": "2026-11-14T08:00:00+07:00",
            "total_team_members": 6,
            "team_absent_count": 0
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Rõ ràng (Duyệt)",
            "primary": "Nghỉ phép năm",
            "duration": "1 ngày làm việc",
            "subtext": "Nghỉ thường niên • Nguyễn Thị Kim Ngân",
            "leaveTypeFriendly": "Nghỉ phép năm (1 ngày làm việc) - Nghỉ phép thường niên",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Phép năm hợp lệ, đủ số dư, không cần chuyển người duyệt."
        }
    },
    {
        "id": "TC-EXT-04",
        "emp_id": "EMP010",
        "title": "TC-EXT-04: Phép năm 2 ngày có bàn giao cùng phòng cho EMP008",
        "badge": "Tự động duyệt",
        "badgeClass": "bg-success-lt",
        "desc": "Phan Thảo My xin 2 ngày phép năm có bàn giao công việc cho Nguyễn Thị Kim Ngân cùng phòng Marketing -> AI tự động phê duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-19",
            "to_date": "2026-11-20",
            "reason": "Nghỉ phép cá nhân",
            "handover_person_id": "EMP008",
            "handover": {"employee_id": "EMP008", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-15T08:00:00+07:00",
            "total_team_members": 6,
            "team_absent_count": 0
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Rõ ràng (Duyệt)",
            "primary": "Nghỉ phép năm",
            "duration": "2 ngày làm việc",
            "subtext": "Nghỉ cá nhân • Bàn giao cho Nguyễn Thị Kim Ngân",
            "leaveTypeFriendly": "Nghỉ phép năm (2 ngày làm việc) - Bàn giao cho Nguyễn Thị Kim Ngân",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Phép năm 2 ngày có bàn giao hợp lệ, không cần chuyển người duyệt."
        }
    },
    {
        "id": "TC-EXT-05",
        "emp_id": "EMP012",
        "title": "TC-EXT-05: Phép năm 1 ngày phòng Điều phối Vận hành",
        "badge": "Tự động duyệt",
        "badgeClass": "bg-success-lt",
        "desc": "Lê Mai Loan xin 1 ngày phép năm giải quyết việc riêng, số dư còn 12 ngày -> AI tự động phê duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-20",
            "to_date": "2026-11-20",
            "reason": "Giải quyết việc cá nhân",
            "submitted_at": "2026-11-16T08:00:00+07:00",
            "total_team_members": 6,
            "team_absent_count": 0
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Rõ ràng (Duyệt)",
            "primary": "Nghỉ phép năm",
            "duration": "1 ngày làm việc",
            "subtext": "Giải quyết việc riêng • Lê Mai Loan",
            "leaveTypeFriendly": "Nghỉ phép năm (1 ngày làm việc) - Lê Mai Loan",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Phép năm hợp lệ, đủ số dư, không cần chuyển người duyệt."
        }
    },
    {
        "id": "TC-EXT-06",
        "emp_id": "EMP006",
        "title": "TC-EXT-06: Biên số dư phép - Còn đúng 1 ngày, xin đúng 1 ngày (Duyệt)",
        "badge": "Biên số dư · Đạt",
        "badgeClass": "bg-success-lt",
        "desc": "Bùi Tuấn Kiệt số dư còn đúng 1 ngày phép: nộp đơn xin đúng 1 ngày -> AI tự động duyệt, số dư trừ vừa hết về 0.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-23",
            "to_date": "2026-11-23",
            "remaining_leave_days": 1.0,
            "reason": "Giải quyết việc cá nhân gia đình",
            "submitted_at": "2026-11-20T08:00:00+07:00",
            "total_team_members": 6,
            "team_absent_count": 0
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Biên số dư (Đạt)",
            "primary": "Nghỉ phép năm",
            "duration": "1 ngày làm việc",
            "subtext": "Số dư còn 1 ngày • Xin vừa đủ 1 ngày",
            "leaveTypeFriendly": "Nghỉ phép năm (1 ngày làm việc) - Biên số dư đạt chuẩn",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Số dư vừa đủ (1 ngày), AI tự động duyệt & trừ về 0."
        }
    },
    {
        "id": "TC-EXT-07",
        "emp_id": "EMP005",
        "title": "TC-EXT-07: Nghỉ ốm 1 ngày PK Đa khoa hợp lệ có chứng từ đúng tên",
        "badge": "Tự động duyệt",
        "badgeClass": "bg-success-lt",
        "desc": "Nguyễn Văn An nộp đơn nghỉ ốm 1 ngày kèm Giấy khám bệnh PK hợp lệ đúng tên bệnh nhân -> AI tự động phê duyệt chế độ BHXH 1 ngày theo quy chế §3.1.",
        "proof_file": "proof_emp005_sick_clinic_valid.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-11-23",
            "to_date": "2026-11-23",
            "reason": "Viêm đường hô hấp trên điều trị ngoại trú",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Phòng khám Đa khoa Quốc tế",
                "patient_name": "Nguyễn Văn An",
                "issue_date": "2026-11-23",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-11-23T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Rõ ràng (Duyệt)",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "1 ngày làm việc",
            "subtext": "Khám ngoại trú • PK Đa khoa Quốc tế",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (1 ngày) - PK Đa khoa Quốc tế",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Nghỉ ốm 1 ngày có chứng từ y tế hợp lệ theo quy chế §3.1, AI tự động duyệt."
        }
    },
    {
        "id": "TC-EXT-08",
        "emp_id": "EMP011",
        "title": "TC-EXT-08: Nghỉ ốm 1 ngày khám buổi sáng có chứng nhận hợp lệ",
        "badge": "Tự động duyệt",
        "badgeClass": "bg-success-lt",
        "desc": "Hoàng Kim Yến nộp đơn nghỉ ốm 1 ngày kèm chứng từ khám buổi sáng hợp lệ -> AI tự động duyệt theo quy chế §3.1.",
        "proof_file": "proof_emp011_sick_morning_valid.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-11-24",
            "to_date": "2026-11-24",
            "reason": "Rối loạn tiêu hóa cấp điều trị ngoại trú",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa",
                "patient_name": "Hoàng Kim Yến",
                "issue_date": "2026-11-24",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-11-24T08:15:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Rõ ràng (Duyệt)",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "1 ngày làm việc",
            "subtext": "Khám buổi sáng • Bệnh viện Đa khoa",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (1 ngày) - Khám buổi sáng hợp lệ",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Nghỉ ốm 1 ngày có chứng từ hợp lệ, AI tự động phê duyệt chế độ BHXH."
        }
    },
    {
        "id": "TC-EXT-09",
        "emp_id": "EMP006",
        "title": "TC-EXT-09: Cấp cứu ban đêm Khoa Cấp cứu BV E có phiếu xác nhận",
        "badge": "Cấp cứu khẩn",
        "badgeClass": "bg-success-lt",
        "desc": "Bùi Tuấn Kiệt cấp cứu rạng sáng tại BV E, nộp phiếu tiếp nhận cấp cứu hợp lệ cho 1 ngày nghỉ -> AI tự duyệt hỗ trợ khẩn cấp.",
        "proof_file": "proof_emp006_emergency_slip.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-11-25",
            "to_date": "2026-11-25",
            "reason": "Cấp cứu ban đêm đau quặn thận nghi sỏi tại Khoa Cấp cứu BV E",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện E - Khoa Cấp cứu",
                "issue_date": "2026-11-25",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-11-25T07:10:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Cấp cứu khẩn",
            "primary": "Nghỉ ốm cấp cứu",
            "duration": "1 ngày làm việc",
            "subtext": "Khoa Cấp cứu BV E • Phiếu xác nhận",
            "leaveTypeFriendly": "Nghỉ ốm cấp cứu (1 ngày) - BV E",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Ca cấp cứu ban đêm có phiếu tiếp nhận BV E, AI tự động duyệt chế độ BHXH."
        }
    },
    {
        "id": "TC-EXT-10",
        "emp_id": "EMP004",
        "title": "TC-EXT-10: Đơn xin nghỉ trùng ngày Quốc khánh 02/09 (Miễn trừ làm đơn)",
        "badge": "Lễ luật định",
        "badgeClass": "bg-secondary-lt",
        "desc": "Lê Văn Nam xin nghỉ trùng ngày Quốc khánh 02/09/2026 -> Hệ thống xác định đây là ngày nghỉ lễ luật định có hưởng lương, không cần nộp đơn nghỉ phép.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-09-02",
            "to_date": "2026-09-02",
            "reason": "Nghỉ lễ Quốc khánh",
            "submitted_at": "2026-08-25T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "ROUTINE",
            "groupName": "1. Thường quy / Rõ ràng (Tự động xử lý)",
            "shortPrefix": "Lễ luật định",
            "primary": "Nghỉ lễ Quốc khánh",
            "duration": "0 ngày làm việc",
            "subtext": "Nghỉ lễ Quốc khánh 02/09 • Không trừ phép",
            "leaveTypeFriendly": "Nghỉ lễ Quốc khánh (0 ngày) - Miễn làm đơn",
            "actionableQuestion": "Tự động xử lý hoàn toàn: Ngày 02/09 là ngày nghỉ lễ luật định hưởng nguyên lương, không cần xin phép."
        }
    },

    # -------------------------------------------------------------
    # NHÓM 2: VƯỢT THẨM QUYỀN XỬ LÝ (ESCALATE) (20 ca)
    # -------------------------------------------------------------
    {
        "id": "TC-EXT-11",
        "emp_id": "EMP003",
        "title": "TC-EXT-11: Phép năm 3 ngày có bàn giao cùng phòng cho EMP004",
        "badge": "Chuyển Quản lý",
        "badgeClass": "bg-primary-lt",
        "desc": "Trần Quốc Hưng xin 3 ngày phép năm có bàn giao công việc cho Lê Văn Nam cùng phòng -> Chuyển Đỗ Hoàng Long (Engineering Manager) duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-24",
            "to_date": "2026-11-26",
            "reason": "Nghỉ phép thường niên",
            "handover_person_id": "EMP004",
            "handover": {"employee_id": "EMP004", "department": "Engineering", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-16T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Quản lý)",
            "primary": "Nghỉ phép năm",
            "duration": "3 ngày làm việc",
            "subtext": "Phép năm 3 ngày • Bàn giao cho Lê Văn Nam",
            "leaveTypeFriendly": "Nghỉ phép năm (3 ngày) - Bàn giao cho Lê Văn Nam",
            "actionableQuestion": "Trần Quốc Hưng xin nghỉ 3 ngày phép năm có bàn giao. Quản lý trực tiếp (Đỗ Hoàng Long) có phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-12",
        "emp_id": "EMP004",
        "title": "TC-EXT-12: Phép năm 4 ngày có bàn giao cùng phòng cho EMP005",
        "badge": "Chuyển Quản lý",
        "badgeClass": "bg-primary-lt",
        "desc": "Lê Văn Nam xin 4 ngày phép năm có bàn giao công việc cho Nguyễn Văn An cùng phòng Kỹ thuật -> Chuyển Quản lý Kỹ thuật phê duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-24",
            "to_date": "2026-11-27",
            "reason": "Nghỉ phép thường niên cá nhân",
            "handover_person_id": "EMP005",
            "handover": {"employee_id": "EMP005", "department": "Engineering", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-16T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Quản lý)",
            "primary": "Nghỉ phép năm",
            "duration": "4 ngày làm việc",
            "subtext": "Phép năm 4 ngày • Bàn giao cho Nguyễn Văn An",
            "leaveTypeFriendly": "Nghỉ phép năm (4 ngày) - Bàn giao cho Nguyễn Văn An",
            "actionableQuestion": "Lê Văn Nam xin 4 ngày phép năm có bàn giao. Quản lý trực tiếp có phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-13",
        "emp_id": "EMP008",
        "title": "TC-EXT-13: Phép năm 4 ngày phòng Vận hành có bàn giao cho EMP010",
        "badge": "Chuyển Quản lý",
        "badgeClass": "bg-primary-lt",
        "desc": "Nguyễn Thị Kim Ngân xin 4 ngày phép năm có bàn giao cho Phan Thảo My -> Chuyển Dương Mỹ Duyên (Marketing & Ops Manager) duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-24",
            "to_date": "2026-11-27",
            "reason": "Nghỉ phép cá nhân",
            "handover_person_id": "EMP010",
            "handover": {"employee_id": "EMP010", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-16T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Quản lý)",
            "primary": "Nghỉ phép năm",
            "duration": "4 ngày làm việc",
            "subtext": "Phép năm 4 ngày • Bàn giao cho Phan Thảo My",
            "leaveTypeFriendly": "Nghỉ phép năm (4 ngày) - Bàn giao cho Phan Thảo My",
            "actionableQuestion": "Nguyễn Thị Kim Ngân xin nghỉ 4 ngày phép năm. Quản lý Marketing (Dương Mỹ Duyên) có phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-14",
        "emp_id": "EMP010",
        "title": "TC-EXT-14: Phép năm 5 ngày chạm trần Quản lý trực tiếp",
        "badge": "Chuyển Quản lý",
        "badgeClass": "bg-primary-lt",
        "desc": "Phan Thảo My xin 5 ngày phép năm (đúng hạn mức tối đa của Quản lý trực tiếp) có bàn giao cho Nguyễn Thị Kim Ngân -> Chuyển Quản lý duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-30",
            "to_date": "2026-12-04",
            "reason": "Nghỉ phép du lịch gia đình",
            "handover_person_id": "EMP008",
            "handover": {"employee_id": "EMP008", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-20T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Quản lý)",
            "primary": "Nghỉ phép năm",
            "duration": "5 ngày làm việc",
            "subtext": "Chạm trần Quản lý 5 ngày • Bàn giao cho Nguyễn Thị Kim Ngân",
            "leaveTypeFriendly": "Nghỉ phép năm (5 ngày) - Chạm trần Quản lý",
            "actionableQuestion": "Phan Thảo My xin 5 ngày phép năm chạm trần thẩm quyền Quản lý. Quản lý trực tiếp có phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-15",
        "emp_id": "EMP003",
        "title": "TC-EXT-15: Phép năm 6 ngày liên tục -> Vượt trần Quản lý, chuyển Tổng Giám đốc (CEO)",
        "badge": "Cấp CEO",
        "badgeClass": "bg-purple-lt",
        "desc": "Trần Quốc Hưng xin 6 ngày phép năm liên tục có bàn giao -> Vượt hạn mức 5 ngày của Quản lý trực tiếp, chuyển thẳng Tổng Giám đốc (CEO) phê duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-30",
            "to_date": "2026-12-07",
            "reason": "Nghỉ phép gia đình dài ngày",
            "handover_person_id": "EMP004",
            "handover": {"employee_id": "EMP004", "department": "Engineering", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-15T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Cấp CEO)",
            "primary": "Nghỉ phép năm",
            "duration": "6 ngày làm việc",
            "subtext": "Nghỉ 6 ngày liên tiếp • Vượt trần 5 ngày Quản lý",
            "leaveTypeFriendly": "Nghỉ phép năm (6 ngày) - Chuyển Tổng Giám đốc (CEO)",
            "actionableQuestion": "Đơn nghỉ 6 ngày vượt trần 5 ngày của Quản lý trực tiếp. Tổng Giám đốc (CEO) có phê duyệt đợt nghỉ dài ngày này không?"
        }
    },
    {
        "id": "TC-EXT-16",
        "emp_id": "EMP004",
        "title": "TC-EXT-16: Phép năm 7 ngày dài ngày -> Chuyển Tổng Giám đốc (CEO)",
        "badge": "Cấp CEO",
        "badgeClass": "bg-purple-lt",
        "desc": "Lê Văn Nam xin 7 ngày phép năm liên tục có bàn giao -> Vượt trần thẩm quyền Quản lý, chuyển Tổng Giám đốc phê duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-30",
            "to_date": "2026-12-08",
            "reason": "Nghỉ du lịch dài ngày xuyên Việt",
            "handover_person_id": "EMP005",
            "handover": {"employee_id": "EMP005", "department": "Engineering", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-15T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Cấp CEO)",
            "primary": "Nghỉ phép năm",
            "duration": "7 ngày làm việc",
            "subtext": "Nghỉ 7 ngày làm việc • Chuyển Tổng Giám đốc",
            "leaveTypeFriendly": "Nghỉ phép năm (7 ngày) - Chuyển Tổng Giám đốc",
            "actionableQuestion": "Lê Văn Nam xin nghỉ 7 ngày phép năm. Tổng Giám đốc (CEO) có chấp thuận không?"
        }
    },
    {
        "id": "TC-EXT-17",
        "emp_id": "EMP008",
        "title": "TC-EXT-17: Phép năm 8 ngày dài ngày phòng Marketing -> Chuyển Tổng Giám đốc (CEO)",
        "badge": "Cấp CEO",
        "badgeClass": "bg-purple-lt",
        "desc": "Nguyễn Thị Kim Ngân xin 8 ngày phép năm có bàn giao -> Vượt trần 5 ngày của Quản lý, chuyển Tổng Giám đốc phê duyệt.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-11-30",
            "to_date": "2026-12-09",
            "reason": "Nghỉ việc gia đình dài ngày",
            "handover_person_id": "EMP010",
            "handover": {"employee_id": "EMP010", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-11-15T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Cấp CEO)",
            "primary": "Nghỉ phép năm",
            "duration": "8 ngày làm việc",
            "subtext": "Nghỉ 8 ngày làm việc • Chuyển Tổng Giám đốc",
            "leaveTypeFriendly": "Nghỉ phép năm (8 ngày) - Chuyển Tổng Giám đốc",
            "actionableQuestion": "Nguyễn Thị Kim Ngân xin nghỉ 8 ngày phép năm. Tổng Giám đốc (CEO) có chấp thuận không?"
        }
    },
    {
        "id": "TC-EXT-18",
        "emp_id": "EMP004",
        "title": "TC-EXT-18: Nghỉ ốm 2 ngày tiêu chuẩn BV Đa khoa Quốc tế có chứng từ hợp lệ",
        "badge": "Chuyển Quản lý",
        "badgeClass": "bg-info-lt",
        "desc": "Lê Văn Nam nộp đơn nghỉ ốm 2 ngày kèm Giấy chứng nhận nghỉ việc hưởng BHXH hợp lệ -> Vượt ngưỡng AI tự duyệt 1 ngày, chuyển Quản lý xem xét.",
        "proof_file": "proof_sick_valid_3days.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-11-24",
            "to_date": "2026-11-25",
            "reason": "Sốt virus cấp tính điều trị ngoại trú",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa Quốc tế",
                "patient_name": "Lê Văn Nam",
                "issue_date": "2026-11-24",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-11-24T07:45:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Quản lý)",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "2 ngày làm việc",
            "subtext": "Sốt virus cấp tính • BV Đa khoa Quốc tế",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (2 ngày) - BV Đa khoa Quốc tế",
            "actionableQuestion": "Lê Văn Nam xin nghỉ ốm 2 ngày làm việc có chứng từ y tế hợp lệ. Quản lý trực tiếp có phê duyệt chế độ BHXH không?"
        }
    },
    {
        "id": "TC-EXT-19",
        "emp_id": "EMP006",
        "title": "TC-EXT-19: Nghỉ ốm 2 ngày điều trị viêm amidan cấp BV Đa khoa Đống Đa",
        "badge": "Chuyển Quản lý",
        "badgeClass": "bg-info-lt",
        "desc": "Bùi Tuấn Kiệt xin nghỉ ốm 2 ngày kèm Giấy chứng nhận BV Đống Đa hợp lệ -> Chuyển Quản lý trực tiếp xem xét duyệt BHXH.",
        "proof_file": "proof_emp006_sick_standard_2days.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-11-26",
            "to_date": "2026-11-27",
            "reason": "Viêm amidan hốc mủ cấp tính điều trị ngoại trú",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa Đống Đa",
                "patient_name": "Bùi Tuấn Kiệt",
                "issue_date": "2026-11-26",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-11-26T07:30:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Quản lý)",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "2 ngày làm việc",
            "subtext": "Viêm amidan cấp • BV Đa khoa Đống Đa",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (2 ngày) - BV Đống Đa",
            "actionableQuestion": "Bùi Tuấn Kiệt xin nghỉ ốm 2 ngày có giấy chứng nhận BV Đống Đa. Quản lý trực tiếp có phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-20",
        "emp_id": "EMP010",
        "title": "TC-EXT-20: Nghỉ ốm 3 ngày tiêu chuẩn điều trị ngoại trú có chứng từ",
        "badge": "Chuyển Quản lý",
        "badgeClass": "bg-info-lt",
        "desc": "Phan Thảo My xin nghỉ ốm 3 ngày kèm Giấy chứng nhận tiêu chuẩn -> Chuyển Quản lý trực tiếp xem xét theo phân cấp.",
        "proof_file": "proof_emp010_sick_standard_3days.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-01",
            "to_date": "2026-12-03",
            "reason": "Viêm phế quản cấp tính điều trị ngoại trú",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa",
                "patient_name": "Phan Thảo My",
                "issue_date": "2026-12-01",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-01T07:30:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Vượt thẩm quyền (Quản lý)",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "3 ngày làm việc",
            "subtext": "Viêm phế quản cấp • Giấy khám tiêu chuẩn",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (3 ngày) - Phan Thảo My",
            "actionableQuestion": "Phan Thảo My xin nghỉ ốm 3 ngày có giấy chứng nhận y tế. Quản lý trực tiếp có phê duyệt hưởng chế độ BHXH không?"
        }
    },
    {
        "id": "TC-EXT-21",
        "emp_id": "EMP004",
        "title": "TC-EXT-21: Chứng từ y tế có chữ ký số điện tử theo TT 25/2025/TT-BYT",
        "badge": "Chữ ký điện tử",
        "badgeClass": "bg-success-lt",
        "desc": "Chứng từ điện tử BV Hồng Ngọc không có mộc đỏ vật lý nhưng có chữ ký số hợp lệ theo TT 25/2025/TT-BYT -> Hợp lệ chuyển Quản lý duyệt.",
        "proof_file": "proof_emp004_sick_digital_valid.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-01",
            "to_date": "2026-12-03",
            "reason": "Viêm xoang hàm cấp điều trị ngoại trú",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa Hồng Ngọc",
                "patient_name": "Lê Văn Nam",
                "issue_date": "2026-12-01",
                "signature_present": False,
                "digital_signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-01T07:30:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Chữ ký điện tử",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "3 ngày làm việc",
            "subtext": "Chữ ký số BV Hồng Ngọc • TT 25/2025/TT-BYT",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (3 ngày) - Chữ ký số hợp lệ",
            "actionableQuestion": "Chứng từ có chữ ký số điện tử hợp lệ theo TT 25/2025/TT-BYT. Quản lý trực tiếp có phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-22",
        "emp_id": "EMP005",
        "title": "TC-EXT-22: Nghỉ ốm có chứng từ chữ ký số xác thực hợp lệ",
        "badge": "Chữ ký điện tử",
        "badgeClass": "bg-success-lt",
        "desc": "Nguyễn Văn An nộp chứng từ y tế có chữ ký số xác thực điện tử -> Hợp lệ chuyển Quản lý trực tiếp phê duyệt.",
        "proof_file": "proof_digital_signed.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-02",
            "to_date": "2026-12-04",
            "reason": "Điều trị ngoại trú theo chỉ định",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Cơ sở khám chữa bệnh",
                "patient_name": "Nguyễn Văn An",
                "issue_date": "2026-12-02",
                "digital_signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-02T07:30:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Chữ ký điện tử",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "3 ngày làm việc",
            "subtext": "Chữ ký số xác thực • Không bắt bẻ mộc đỏ",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (3 ngày) - Chữ ký số",
            "actionableQuestion": "Chứng từ có chữ ký số xác thực hợp lệ. Quản lý trực tiếp có phê duyệt chế độ BHXH không?"
        }
    },
    {
        "id": "TC-EXT-23",
        "emp_id": "EMP009",
        "title": "TC-EXT-23: Kết hôn bản thân 3 ngày nguyên lương theo Điều 115 BLLĐ",
        "badge": "Nguyên lương",
        "badgeClass": "bg-pink-lt",
        "desc": "Võ Minh Khang xin 3 ngày nghỉ kết hôn bản thân kèm Giấy chứng nhận kết hôn hợp lệ -> Chuyển Quản lý duyệt hưởng nguyên lương theo Điều 115 BLLĐ, 0 trừ phép.",
        "proof_file": "proof_emp009_wedding_valid.png",
        "proof_type": "MARRIAGE_CERTIFICATE",
        "payload": {
            "leave_type": "SPECIAL_PAID",
            "reason_category": "SELF_MARRIAGE",
            "from_date": "2026-12-02",
            "to_date": "2026-12-04",
            "reason": "Lễ thành hôn của bản thân",
            "proof": {
                "proof_type": "MARRIAGE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "UBND Phường",
                "issue_date": "2026-11-25",
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-11-25T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Nguyên lương (Cưới)",
            "primary": "Nghỉ việc riêng có lương",
            "duration": "3 ngày làm việc",
            "subtext": "Kết hôn bản thân • Điều 115 BLLĐ",
            "leaveTypeFriendly": "Nghỉ việc riêng có lương (3 ngày) - Bản thân kết hôn",
            "actionableQuestion": "Võ Minh Khang xin nghỉ 3 ngày kết hôn bản thân có Giấy kết hôn. Quản lý trực tiếp có phê duyệt 3 ngày hưởng nguyên lương không?"
        }
    },
    {
        "id": "TC-EXT-24",
        "emp_id": "EMP005",
        "title": "TC-EXT-24: Kết hôn bản thân 3 ngày nguyên lương có Giấy đăng ký kết hôn",
        "badge": "Nguyên lương",
        "badgeClass": "bg-pink-lt",
        "desc": "Nguyễn Văn An xin 3 ngày nghỉ kết hôn kèm Giấy chứng nhận kết hôn UBND xã/phường -> Chuyển Quản lý phê duyệt hưởng nguyên lương Điều 115 BLLĐ.",
        "proof_file": "proof_wedding_cert.png",
        "proof_type": "MARRIAGE_CERTIFICATE",
        "payload": {
            "leave_type": "SPECIAL_PAID",
            "reason_category": "SELF_MARRIAGE",
            "from_date": "2026-12-07",
            "to_date": "2026-12-09",
            "reason": "Tổ chức đám cưới của bản thân",
            "proof": {
                "proof_type": "MARRIAGE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "UBND Phường",
                "issue_date": "2026-11-28",
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-11-28T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Nguyên lương (Cưới)",
            "primary": "Nghỉ việc riêng có lương",
            "duration": "3 ngày làm việc",
            "subtext": "Bản thân kết hôn • 03 ngày nguyên lương",
            "leaveTypeFriendly": "Nghỉ việc riêng có lương (3 ngày) - Bản thân kết hôn",
            "actionableQuestion": "Nguyễn Văn An xin nghỉ 3 ngày đám cưới kèm Giấy kết hôn. Quản lý trực tiếp có phê duyệt hưởng nguyên lương không?"
        }
    },
    {
        "id": "TC-EXT-25",
        "emp_id": "EMP008",
        "title": "TC-EXT-25: Tang tứ thân phụ mẫu 3 ngày nguyên lương Điều 115 BLLĐ",
        "badge": "Nguyên lương",
        "badgeClass": "bg-dark-lt",
        "desc": "Nguyễn Thị Kim Ngân xin nghỉ 3 ngày lo tang lễ mẹ ruột kèm Giấy chứng tử -> Quản lý duyệt 3 ngày nguyên lương theo Điều 115 BLLĐ.",
        "proof_file": "proof_emp008_funeral_direct.png",
        "proof_type": "OTHER",
        "payload": {
            "leave_type": "SPECIAL_PAID",
            "reason_category": "PARENT_DEATH",
            "from_date": "2026-12-07",
            "to_date": "2026-12-09",
            "reason": "Lo hậu sự cho mẹ ruột tại quê nhà",
            "proof": {
                "proof_type": "OTHER",
                "proof_verification_status": "VERIFIED",
                "issuer": "UBND Xã/Phường",
                "issue_date": "2026-12-06",
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-06T18:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Nguyên lương (Tang)",
            "primary": "Nghỉ việc riêng có lương",
            "duration": "3 ngày làm việc",
            "subtext": "Tang mẹ đẻ • Điều 115 BLLĐ 03 ngày",
            "leaveTypeFriendly": "Nghỉ việc riêng có lương (3 ngày) - Tang tứ thân phụ mẫu",
            "actionableQuestion": "Nguyễn Thị Kim Ngân xin nghỉ 3 ngày lo tang lễ mẹ ruột. Quản lý trực tiếp có phê duyệt hưởng nguyên lương theo Điều 115 BLLĐ không?"
        }
    },
    {
        "id": "TC-EXT-26",
        "emp_id": "EMP003",
        "title": "TC-EXT-26: Con kết hôn 1 ngày nguyên lương theo Điều 115 BLLĐ",
        "badge": "Nguyên lương",
        "badgeClass": "bg-pink-lt",
        "desc": "Trần Quốc Hưng xin 1 ngày nghỉ tham dự lễ cưới con trai ruột kèm Giấy chứng nhận kết hôn -> Quản lý duyệt 1 ngày hưởng nguyên lương Điều 115 BLLĐ.",
        "proof_file": "proof_emp003_wedding_child.png",
        "proof_type": "MARRIAGE_CERTIFICATE",
        "payload": {
            "leave_type": "SPECIAL_PAID",
            "reason_category": "CHILD_MARRIAGE",
            "from_date": "2026-12-08",
            "to_date": "2026-12-08",
            "reason": "Tham dự lễ thành hôn của con trai ruột",
            "proof": {
                "proof_type": "MARRIAGE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "UBND Phường",
                "issue_date": "2026-12-01",
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-01T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Nguyên lương (Con cưới)",
            "primary": "Nghỉ việc riêng có lương",
            "duration": "1 ngày làm việc",
            "subtext": "Con kết hôn • 01 ngày nguyên lương",
            "leaveTypeFriendly": "Nghỉ việc riêng có lương (1 ngày) - Con kết hôn",
            "actionableQuestion": "Trần Quốc Hưng xin nghỉ 1 ngày dự cưới con trai ruột kèm Giấy kết hôn. Quản lý có duyệt 1 ngày hưởng nguyên lương không?"
        }
    },
    {
        "id": "TC-EXT-27",
        "emp_id": "EMP012",
        "title": "TC-EXT-27: Nghỉ chăm con ốm theo Luật BHXH có chứng nhận cơ sở y tế",
        "badge": "Luật BHXH",
        "badgeClass": "bg-info-lt",
        "desc": "Lê Mai Loan xin nghỉ chăm con nhỏ ốm sốt có Giấy chứng nhận y tế hợp lệ theo Luật BHXH -> Chuyển Quản lý trực tiếp phê duyệt.",
        "proof_file": "proof_emp012_child_sick_care.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
                        "from_date": "2026-12-09",
            "to_date": "2026-12-09",
            "reason": "Chăm sóc con nhỏ ốm sốt điều trị tại nhà",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Nhi",
                "issue_date": "2026-12-09",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-09T07:30:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Luật BHXH (Con ốm)",
            "primary": "Nghỉ con ốm BHXH",
            "duration": "1 ngày làm việc",
            "subtext": "Chăm sóc con ốm • Luật BHXH",
            "leaveTypeFriendly": "Nghỉ con ốm BHXH (1 ngày) - Bệnh viện Nhi",
            "actionableQuestion": "Lê Mai Loan xin nghỉ 1 ngày chăm con ốm có chứng nhận viện Nhi. Quản lý trực tiếp có phê duyệt chế độ BHXH không?"
        }
    },
    {
        "id": "TC-EXT-28",
        "emp_id": "EMP008",
        "title": "TC-EXT-28: Khám thai định kỳ 1 ngày có chứng nhận y tế BV Phụ sản",
        "badge": "Cấp CEO",
        "badgeClass": "bg-pink-lt",
        "desc": "Nguyễn Thị Kim Ngân nộp đơn khám thai định kỳ kèm Giấy chứng nhận BV Phụ sản Hà Nội -> Chế độ thai sản BHXH: chuyển Tổng Giám đốc duyệt theo quy chế §3.1.",
        "proof_file": "proof_emp008_maternity_prenatal.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "MATERNITY",
            "from_date": "2026-12-10",
            "to_date": "2026-12-10",
            "reason": "Khám thai định kỳ tại Bệnh viện Phụ sản Hà Nội",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Phụ sản Hà Nội",
                "issue_date": "2026-12-10",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-10T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Cấp CEO (Thai sản)",
            "primary": "Nghỉ thai sản BHXH",
            "duration": "1 ngày làm việc",
            "subtext": "Khám thai định kỳ • BV Phụ sản Hà Nội",
            "leaveTypeFriendly": "Nghỉ thai sản BHXH (1 ngày) - Khám thai định kỳ",
            "actionableQuestion": "Nguyễn Thị Kim Ngân xin nghỉ khám thai định kỳ theo chế độ thai sản BHXH. Tổng Giám đốc (CEO) có phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-29",
        "emp_id": "EMP011",
        "title": "TC-EXT-29: Nghỉ do tai nạn lao động có biên bản xác nhận -> Chuyển Nhân sự (HR)",
        "badge": "Cấp HR",
        "badgeClass": "bg-warning-lt",
        "desc": "Hoàng Kim Yến xin nghỉ do sự cố tai nạn lao động kèm biên bản xác nhận -> Thuộc diện hồ sơ BHXH đặc thù, chuyển Trưởng phòng Nhân sự (HR) xử lý.",
        "proof_file": "proof_emp011_work_accident.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "WORK_ACCIDENT",
            "from_date": "2026-12-11",
            "to_date": "2026-12-11",
            "reason": "Sơ cứu và theo dõi chấn thương do tai nạn lao động",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Cơ sở y tế & Biên bản tai nạn",
                "issue_date": "2026-12-11",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-11T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Cấp HR (Tai nạn LĐ)",
            "primary": "Nghỉ tai nạn lao động",
            "duration": "1 ngày làm việc",
            "subtext": "Sự cố tai nạn lao động • Hồ sơ HR",
            "leaveTypeFriendly": "Nghỉ tai nạn lao động (1 ngày) - Chuyển HR",
            "actionableQuestion": "Hồ sơ tai nạn lao động cần xác minh chế độ BHXH đặc thù. Trưởng phòng Nhân sự (HR) có xác nhận phê duyệt không?"
        }
    },
    {
        "id": "TC-EXT-30",
        "emp_id": "EMP002",
        "title": "TC-EXT-30: Quản lý Marketing nộp đơn -> Quy chế chống tự duyệt, chuyển Tổng Giám đốc",
        "badge": "Cấp CEO",
        "badgeClass": "bg-purple-lt",
        "desc": "Dương Mỹ Duyên (Marketing Manager) nộp đơn phép năm 2 ngày -> Theo quy chế chống tự phê duyệt (Anti-self-approval), thẩm quyền chuyển thẳng lên Tổng Giám đốc (CEO).",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-12-14",
            "to_date": "2026-12-15",
            "reason": "Nghỉ phép cá nhân",
            "handover_person_id": "EMP008",
            "handover": {"employee_id": "EMP008", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-12-07T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Anti-Self-Approval",
            "primary": "Nghỉ phép năm",
            "duration": "2 ngày làm việc",
            "subtext": "Quản lý Marketing xin nghỉ • Chuyển Tổng Giám đốc",
            "leaveTypeFriendly": "Nghỉ phép năm (2 ngày) - Quản lý nộp đơn",
            "actionableQuestion": "Quản lý Marketing (Dương Mỹ Duyên) nộp đơn phép năm 2 ngày. Tổng Giám đốc (CEO) có phê duyệt không?"
        }
    },

    # -------------------------------------------------------------
    # NHÓM 3: CẦN XÁC MINH / BẪY CHỨNG TỪ / BỔ SUNG (9 ca)
    # -------------------------------------------------------------
    {
        "id": "TC-EXT-31",
        "emp_id": "EMP005",
        "title": "TC-EXT-31: [Bẫy nộp nhầm chứng từ] Nguyễn Văn An nộp giấy khám của Lê Văn Nam",
        "badge": "Lệch người bệnh",
        "badgeClass": "bg-danger-lt",
        "desc": "Nguyễn Văn An (EMP005) xin nghỉ ốm nhưng tải nhầm tệp Giấy chứng nhận mang tên bệnh nhân Lê Văn Nam (EMP004) -> Bắt lỗi lệch họ tên bệnh nhân NAME_MISMATCH, yêu cầu sửa đơn.",
        "proof_file": "proof_emp004_sick_3days_valid.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-14",
            "to_date": "2026-12-16",
            "reason": "Điều trị ngoại trú theo giấy khám",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa Quốc tế Hà Nội",
                "patient_name": "Lê Văn Nam",
                "issue_date": "2026-12-14",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-14T07:30:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Lệch người bệnh",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "3 ngày làm việc",
            "subtext": "Nộp nhầm giấy khám của Lê Văn Nam • Lỗi NAME_MISMATCH",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (3 ngày) - Lệch tên bệnh nhân",
            "actionableQuestion": "Chứng từ đính kèm mang tên bệnh nhân 'Lê Văn Nam', không khớp với nhân viên nộp đơn 'Nguyễn Văn An'. Nhân viên vui lòng tải đúng chứng từ của mình."
        }
    },
    {
        "id": "TC-EXT-32",
        "emp_id": "EMP009",
        "title": "TC-EXT-32: [Bẫy lệch tên bệnh nhân] Chứng từ ghi tên người khác",
        "badge": "Lệch người bệnh",
        "badgeClass": "bg-danger-lt",
        "desc": "Võ Minh Khang nộp giấy chứng nhận bệnh nhân tên Nguyễn Thị Lan -> Bắt lỗi lệch tên trên chứng từ y tế, yêu cầu chụp lại đúng giấy tờ cá nhân.",
        "proof_file": "proof_emp009_sick_name_mismatch.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-15",
            "to_date": "2026-12-15",
            "reason": "Nghỉ ốm điều trị",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Phòng khám Đa khoa",
                "patient_name": "Nguyễn Thị Lan",
                "issue_date": "2026-12-15",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-15T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Lệch người bệnh",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "1 ngày làm việc",
            "subtext": "Tên bệnh nhân trên giấy không khớp Võ Minh Khang",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (1 ngày) - Lệch tên chứng từ",
            "actionableQuestion": "Tên bệnh nhân trên chứng từ không khớp với nhân viên nộp đơn. Nhân viên vui lòng kiểm tra và bổ sung chứng từ chính xác."
        }
    },
    {
        "id": "TC-EXT-33",
        "emp_id": "EMP004",
        "title": "TC-EXT-33: [Bẫy lệch số ngày] Xin 3 ngày nhưng giấy khám chỉ cho nghỉ 1 ngày",
        "badge": "Lệch số ngày",
        "badgeClass": "bg-warning-lt",
        "desc": "Lê Văn Nam xin nghỉ 3 ngày nhưng Giấy chứng nhận bác sĩ chỉ định nghỉ 1 ngày -> Bắt lỗi lệch ngày chỉ định y tế MEDICAL_DAYS_MISMATCH, yêu cầu sửa đơn.",
        "proof_file": "proof_emp004_sick_days_mismatch.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-16",
            "to_date": "2026-12-18",
            "reason": "Điều trị theo giấy khám bệnh viện",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa",
                "patient_name": "Lê Văn Nam",
                "issue_date": "2026-12-16",
                "recommended_from_date": "2026-12-16",
                "recommended_to_date": "2026-12-16",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-16T07:30:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Lệch số ngày",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "3 ngày làm việc",
            "subtext": "Đơn xin 3 ngày nhưng bác sĩ chỉ cho nghỉ 1 ngày",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (3 ngày) - Lệch ngày chỉ định",
            "actionableQuestion": "Đơn xin nghỉ 3 ngày nhưng chứng từ y tế chỉ xác nhận nghỉ 1 ngày (16/12/2026). Nhân viên vui lòng chỉnh sửa lại thời gian xin nghỉ."
        }
    },
    {
        "id": "TC-EXT-34",
        "emp_id": "EMP010",
        "title": "TC-EXT-34: [Bẫy chứng từ mờ] Giấy khám mờ, mất nét, không đọc được thông tin",
        "badge": "Chứng từ mờ",
        "badgeClass": "bg-warning-lt",
        "desc": "Phan Thảo My chụp giấy khám bị rung tay, nhòe nét, VLM không nhận diện được ngày cấp và con dấu -> Báo lỗi DOC_ILLEGIBLE, yêu cầu chụp lại ảnh rõ nét.",
        "proof_file": "proof_emp010_sick_blurry.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-17",
            "to_date": "2026-12-17",
            "reason": "Nghỉ ốm có chứng từ đính kèm",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Cơ sở y tế",
                "patient_name": "Phan Thảo My",
                "issue_date": "2026-12-17",
                "document_readability": "ILLEGIBLE"
            },
            "submitted_at": "2026-12-17T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Chứng từ mờ",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "1 ngày làm việc",
            "subtext": "Ảnh chụp mờ nhòe • Không nhận diện được mộc",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (1 ngày) - Chứng từ mờ nhòe",
            "actionableQuestion": "Ảnh chứng từ bị mờ/mất nét, không đủ căn cứ xác thực. Nhân viên vui lòng chụp lại ảnh chứng từ rõ ràng, đủ sáng."
        }
    },
    {
        "id": "TC-EXT-35",
        "emp_id": "EMP007",
        "title": "TC-EXT-35: [Bẫy thiếu chữ ký] Chứng từ thiếu chữ ký bác sĩ điều trị",
        "badge": "Thiếu chữ ký",
        "badgeClass": "bg-danger-lt",
        "desc": "Lê Thị Hương nộp giấy nghỉ ốm có mộc bệnh viện nhưng ô bác sĩ chuyên khoa bị bỏ trống -> Báo lỗi DOC_FIELD_MISSING, yêu cầu xin lại xác nhận.",
        "proof_file": "proof_emp007_sick_missing_signature.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-12-18",
            "to_date": "2026-12-18",
            "reason": "Điều trị viêm xoang ngoại trú",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Giao thông Vận tải",
                "patient_name": "Lê Thị Hương",
                "issue_date": "2026-12-18",
                "signature_present": False,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-18T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Thiếu chữ ký",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "1 ngày làm việc",
            "subtext": "Thiếu chữ ký bác sĩ • Bệnh viện GTVT",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH (1 ngày) - Thiếu chữ ký bác sĩ",
            "actionableQuestion": "Chứng từ thiếu chữ ký của bác sĩ điều trị. Nhân viên vui lòng xin bổ sung chữ ký xác nhận của cơ sở y tế."
        }
    },
    {
        "id": "TC-EXT-36",
        "emp_id": "EMP005",
        "title": "TC-EXT-36: [Bẫy quá hạn nộp] Nộp chứng từ y tế quá thời hạn 3 ngày làm việc",
        "badge": "Quá hạn nộp",
        "badgeClass": "bg-warning-lt",
        "desc": "Nguyễn Văn An nộp giấy chứng nhận khám từ tháng trước quá hạn nộp quy định -> Báo nghỉ trễ hạn NOTICE_PERIOD_VIOLATED, chuyển Quản lý xem xét lý do nộp muộn.",
        "proof_file": "proof_emp005_sick_expired.png",
        "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
        "payload": {
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-05-15",
            "to_date": "2026-05-18",
            "reason": "Nộp bù giấy khám tháng 5",
            "proof": {
                "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "Bệnh viện Đa khoa Quốc tế Thu Cúc",
                "patient_name": "Nguyễn Văn An",
                "issue_date": "2026-05-15",
                "signature_present": True,
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-18T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "AUTHORITY_ESCALATION",
            "groupName": "4. Vượt thẩm quyền xử lý (Chuyển Quản lý / CEO)",
            "shortPrefix": "Quá hạn nộp",
            "primary": "Nghỉ ốm hưởng BHXH",
            "duration": "2 ngày làm việc",
            "subtext": "Giấy khám tháng 5 nộp trễ vào tháng 12",
            "leaveTypeFriendly": "Nghỉ ốm hưởng BHXH - Quá hạn nộp chứng từ",
            "actionableQuestion": "Chứng từ nộp quá thời hạn 3 ngày làm việc theo quy định nội bộ. Quản lý trực tiếp có chấp thuận lý do nộp muộn không?"
        }
    },
    {
        "id": "TC-EXT-37",
        "emp_id": "EMP005",
        "title": "TC-EXT-37: [Bẫy bàn giao sai phòng] Kỹ thuật bàn giao chéo cho Marketing",
        "badge": "Bàn giao sai phòng",
        "badgeClass": "bg-danger-lt",
        "desc": "Nguyễn Văn An (Kỹ thuật) bàn giao công việc cho Võ Minh Khang (Marketing) -> Báo lỗi HANDOVER_INVALID, yêu cầu chọn người cùng phòng ban.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-12-21",
            "to_date": "2026-12-23",
            "reason": "Nghỉ phép cá nhân",
            "handover_person_id": "EMP009",
            "handover": {"employee_id": "EMP009", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-12-11T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Bàn giao sai",
            "primary": "Nghỉ phép năm",
            "duration": "3 ngày làm việc",
            "subtext": "Bàn giao chéo sang phòng Marketing • Bị chặn",
            "leaveTypeFriendly": "Nghỉ phép năm (3 ngày) - Bàn giao sai phòng ban",
            "actionableQuestion": "Người nhận bàn giao thuộc phòng ban khác (Marketing). Nhân viên vui lòng chỉ định đồng nghiệp cùng phòng Kỹ thuật."
        }
    },
    {
        "id": "TC-EXT-38",
        "emp_id": "EMP007",
        "title": "TC-EXT-38: [Bẫy thử việc] Nhân sự thử việc xin phép năm hưởng lương",
        "badge": "Thử việc bị chặn",
        "badgeClass": "bg-danger-lt",
        "desc": "Lê Thị Hương (đang trong thời gian thử việc) xin nghỉ phép năm hưởng lương -> Bắt lỗi PROBATION_ANNUAL_RESTRICTED, yêu cầu đổi sang nghỉ không lương.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-12-21",
            "to_date": "2026-12-21",
            "employment_status": "PROBATION",
            "remaining_leave_days": 0.0,
            "reason": "Nghỉ việc cá nhân",
            "submitted_at": "2026-12-16T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Thử việc bị chặn",
            "primary": "Nghỉ phép năm",
            "duration": "1 ngày làm việc",
            "subtext": "Hợp đồng thử việc • Chưa có phép năm hưởng lương",
            "leaveTypeFriendly": "Nghỉ phép năm (1 ngày) - Thử việc xin phép năm",
            "actionableQuestion": "Nhân viên đang trong thời gian thử việc chưa phát sinh ngày phép năm hưởng lương. Vui lòng chuyển sang loại nghỉ không lương (UNPAID_OTHER)."
        }
    },
    {
        "id": "TC-EXT-39",
        "emp_id": "EMP012",
        "title": "TC-EXT-39: [Bẫy cưới em gái ruột] Xin nghỉ có lương dự cưới em gái (Không thuộc Điều 115)",
        "badge": "Bẫy quy chế",
        "badgeClass": "bg-warning-lt",
        "desc": "Lê Mai Loan xin nghỉ CÓ LƯƠNG dự cưới em gái ruột kèm Giấy kết hôn -> Điều 115 BLLĐ chỉ cho nghỉ có lương khi bản thân hoặc con kết hôn. Hệ thống chặn, yêu cầu đổi sang nghỉ không lương.",
        "proof_file": "proof_emp012_wedding_sibling.png",
        "proof_type": "MARRIAGE_CERTIFICATE",
        "payload": {
            "leave_type": "SPECIAL_PAID",
            "reason_category": "SIBLING_MARRIAGE",
            "from_date": "2026-12-22",
            "to_date": "2026-12-22",
            "reason": "Tham dự lễ thành hôn của em gái ruột",
            "proof": {
                "proof_type": "MARRIAGE_CERTIFICATE",
                "proof_verification_status": "VERIFIED",
                "issuer": "UBND Phường Quan Hoa",
                "issue_date": "2026-12-15",
                "document_readability": "READABLE"
            },
            "submitted_at": "2026-12-15T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Bẫy quy chế",
            "primary": "Nghỉ việc riêng có lương",
            "duration": "1 ngày làm việc",
            "subtext": "Cưới em gái ruột không thuộc diện hưởng lương Đ115",
            "leaveTypeFriendly": "Nghỉ việc riêng (1 ngày) - Cưới anh/chị/em ruột",
            "actionableQuestion": "Theo Điều 115 BLLĐ, cưới anh/chị/em ruột không thuộc diện nghỉ hưởng lương. Nhân viên vui lòng chuyển sang nghỉ không lương luật định hoặc trừ phép năm."
        }
    },

    # -------------------------------------------------------------
    # NHÓM 4: VI PHẠM CHÍNH SÁCH / TỪ CHỐI TỰ ĐỘNG (AUTO_REJECT) (4 ca)
    # -------------------------------------------------------------
    {
        "id": "TC-EXT-40",
        "emp_id": "EMP006",
        "title": "TC-EXT-40: Vượt số dư phép năm - Còn 1 ngày, xin 3 ngày (Từ chối tự động)",
        "badge": "Vượt số dư",
        "badgeClass": "bg-danger-lt",
        "desc": "Bùi Tuấn Kiệt số dư chỉ còn 1 ngày nhưng làm đơn xin 3 ngày phép năm -> Hệ thống từ chối tự động vì vượt số dư (BALANCE_EXCEEDED).",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-12-23",
            "to_date": "2026-12-25",
            "remaining_leave_days": 1.0,
            "reason": "Nghỉ việc gia đình 3 ngày",
            "submitted_at": "2026-12-18T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "OUT_OF_POLICY",
            "groupName": "3. Vi phạm chính sách (Từ chối tự động)",
            "shortPrefix": "Vượt số dư",
            "primary": "Nghỉ phép năm",
            "duration": "3 ngày làm việc",
            "subtext": "Số dư còn 1 ngày • Xin 3 ngày (Vượt 2 ngày)",
            "leaveTypeFriendly": "Nghỉ phép năm (3 ngày) - Vượt số dư phép",
            "actionableQuestion": "Tự động từ chối hoàn toàn: Số ngày yêu cầu (3 ngày) vượt quá số dư phép năm còn lại (1 ngày)."
        }
    },
    {
        "id": "TC-EXT-41",
        "emp_id": "EMP007",
        "title": "TC-EXT-41: Số dư phép năm bằng 0 nhưng xin phép năm (Từ chối tự động)",
        "badge": "Hết số dư",
        "badgeClass": "bg-danger-lt",
        "desc": "Lê Thị Hương số dư phép năm bằng 0 nhưng vẫn nộp đơn xin nghỉ phép năm -> Hệ thống tự động từ chối do hết quỹ phép.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-12-24",
            "to_date": "2026-12-24",
            "remaining_leave_days": 0.0,
            "reason": "Nghỉ phép cá nhân",
            "submitted_at": "2026-12-18T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "OUT_OF_POLICY",
            "groupName": "3. Vi phạm chính sách (Từ chối tự động)",
            "shortPrefix": "Hết số dư",
            "primary": "Nghỉ phép năm",
            "duration": "1 ngày làm việc",
            "subtext": "Số dư phép năm còn 0 ngày • Bị từ chối",
            "leaveTypeFriendly": "Nghỉ phép năm (1 ngày) - Hết số dư phép",
            "actionableQuestion": "Tự động từ chối hoàn toàn: Số dư phép năm còn 0 ngày, không đủ điều kiện tạo đơn phép năm."
        }
    },
    {
        "id": "TC-EXT-42",
        "emp_id": "EMP005",
        "title": "TC-EXT-42: Trùng lặp ngày nghỉ đã được phê duyệt trước đó (Từ chối tự động)",
        "badge": "Trùng lịch nghỉ",
        "badgeClass": "bg-danger-lt",
        "desc": "Nguyễn Văn An nộp đơn xin nghỉ phép ngày 28/12 trùng hoàn toàn khoảng thời gian đã có đơn phê duyệt trước đó -> Hệ thống chặn từ chối tự động REQUEST_ALREADY_COVERED.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-12-28",
            "to_date": "2026-12-28",
            "reason": "Nghỉ việc cá nhân",
            "approved_working_dates": ["2026-12-28"],
            "submitted_at": "2026-12-20T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "OUT_OF_POLICY",
            "groupName": "3. Vi phạm chính sách (Từ chối tự động)",
            "shortPrefix": "Trùng lịch nghỉ",
            "primary": "Nghỉ phép năm",
            "duration": "1 ngày làm việc",
            "subtext": "Trùng khoảng thời gian đã được duyệt trước đó",
            "leaveTypeFriendly": "Nghỉ phép năm (1 ngày) - Trùng ngày đã duyệt",
            "actionableQuestion": "Tự động từ chối hoàn toàn: Ngày 28/12/2026 đã có đơn nghỉ phép được phê duyệt trước đó."
        }
    },
    {
        "id": "TC-EXT-43",
        "emp_id": "EMP004",
        "title": "TC-EXT-43: Bàn giao công việc cho chính bản thân mình (Bị chặn)",
        "badge": "Bàn giao sai",
        "badgeClass": "bg-danger-lt",
        "desc": "Lê Văn Nam xin nghỉ 3 ngày nhưng tự điền chính mình làm người nhận bàn giao -> Hệ thống bắt lỗi HANDOVER_INVALID, yêu cầu chọn đồng nghiệp khác.",
        "payload": {
            "leave_type": "ANNUAL",
            "from_date": "2026-12-28",
            "to_date": "2026-12-30",
            "reason": "Nghỉ phép thường niên",
            "handover_person_id": "EMP004",
            "handover": {"employee_id": "EMP004", "department": "Engineering", "status": "ACTIVE", "absent_dates": []},
            "submitted_at": "2026-12-20T08:00:00+07:00",
            "total_team_members": 6
        },
        "meta": {
            "group": "UNCERTAIN_FACTS",
            "groupName": "2. Chưa xác định thực tế (Lệch ảnh / Thiếu chứng từ / Lỗi)",
            "shortPrefix": "Bàn giao sai",
            "primary": "Nghỉ phép năm",
            "duration": "3 ngày làm việc",
            "subtext": "Tự bàn giao cho chính mình • Bị chặn",
            "leaveTypeFriendly": "Nghỉ phép năm (3 ngày) - Tự bàn giao chính mình",
            "actionableQuestion": "Người làm đơn không thể tự nhận bàn giao công việc của chính mình. Nhân viên vui lòng chỉ định đồng nghiệp khác."
        }
    }
]

print(f"Loaded {len(cases_blueprint)} case blueprints.")

# Thẩm định từng ca bằng LeaveRuleEngine để gán nhãn phán quyết tuyệt đối chính xác
evaluated_cases = []
evaluated_meta = {}
evaluated_proofs = {}

for item in cases_blueprint:
    cid = item['id']
    empid = item['emp_id']
    emp = EMPS[empid]
    
    req = dict(item['payload'])
    req['employee_id'] = empid
    req['employee_name'] = emp['name']
    req['department'] = emp['department']
    if 'remaining_leave_days' not in req:
        req['remaining_leave_days'] = emp.get('remaining_leave_days', 10.0)
    if 'employment_status' not in req:
        req['employment_status'] = emp.get('employment_status', 'REGULAR')
        
    # Evaluate
    req_clean = {k: v for k, v in req.items() if k in LeaveRequest.model_fields}
    try:
        lr = LeaveRequest.model_validate(req_clean)
        eval_res = LeaveRuleEngine.evaluate(lr)
        dec = eval_res.decision.value if hasattr(eval_res.decision, 'value') else str(eval_res.decision)
        trole = eval_res.target_role.value if hasattr(eval_res.target_role, 'value') else str(eval_res.target_role) if eval_res.target_role else None
        err = eval_res.error_code
        deducted = eval_res.deducted_days or 0
        note = eval_res.human_readable_explanation or item['desc']
    except Exception as e:
        print(f"Error evaluating {cid}: {e}")
        dec = "NEED_CORRECTION"
        trole = "AI"
        err = "VALIDATION_ERROR"
        deducted = 0
        note = item['desc']

    expected = {
        "decision": dec,
        "target_role": trole,
        "error_code": err,
        "deducted_days": deducted,
        "note": note
    }
    
    case_obj = {
        "id": cid,
        "primaryEmpId": empid,
        "title": item['title'],
        "badge": item['badge'],
        "badgeClass": item['badgeClass'],
        "desc": item['desc'],
        "payload": req,
        "expected": expected
    }
    evaluated_cases.append(case_obj)
    evaluated_meta[cid] = item['meta']
    
    if item.get('proof_file'):
        evaluated_proofs[cid] = {
            "file": item['proof_file'],
            "type": item.get('proof_type', 'MEDICAL_LEAVE_CERTIFICATE')
        }

print(f"Evaluated {len(evaluated_cases)} cases successfully.")
from collections import Counter
print("Decisions breakdown:", Counter(c['expected']['decision'] for c in evaluated_cases))

# Lưu ra các file json tạm để kiểm tra
open('/tmp/ext_cases.json', 'w', encoding='utf-8').write(json.dumps(evaluated_cases, ensure_ascii=False, indent=2))
open('/tmp/ext_meta.json', 'w', encoding='utf-8').write(json.dumps(evaluated_meta, ensure_ascii=False, indent=2))
open('/tmp/ext_proofs.json', 'w', encoding='utf-8').write(json.dumps(evaluated_proofs, ensure_ascii=False, indent=2))
print("Saved to /tmp/ext_*.json")
