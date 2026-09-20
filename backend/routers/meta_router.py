"""Reference data and policy metadata. No model calls for dashboards."""
from pathlib import Path
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from routers.leave_router import actor
from rule_engine import RULE_STAGES
from domain import LeaveType, ReasonCategory, ProofType
from taxonomy import DecisionType, TargetApproverRole
from calendar_service import CalendarService, CalendarUnavailable
import database as db
import storage as st

router=APIRouter(prefix='/api/meta',tags=['Metadata & Policy'])
policy_path=Path(__file__).resolve().parents[2]/'Leave_Application'/'policy_rules.md'

@router.get('/health')
def health_check(): return {'status':'ok','service':'Leave Approval Backend API','version':'3.0.0'}

@router.get('/employees')
def list_employees():
    # Public demo actor directory. Not production authentication.
    try:
        db.seed_demo_request()
    except Exception as _e:
        pass
    with st.transaction() as conn:
        rows=[dict(r) for r in conn.execute('SELECT * FROM employees')]
        for row in rows:
            row['actor_roles']=[dict(r) for r in conn.execute('SELECT role,department_scope FROM actor_roles WHERE employee_id=?',(row['employee_id'],))]
        return {'success':True,'total':len(rows),'data':rows,'identity_mode':'DEMO'}

@router.get('/options')
def options():
    return {'leave_types':[x.value for x in LeaveType],'reason_categories':[x.value for x in ReasonCategory],
        'proof_types':[x.value for x in ProofType],'decisions':[x.value for x in DecisionType],
        'roles':[x.value for x in TargetApproverRole]}

@router.get('/policy')
def get_policy_document():
    return {'success':True,'document_name':'POL-HR-2026-03','version':'3.0.0','content_markdown':policy_path.read_text()}

@router.get('/decision-tree')
def get_decision_tree():
    POLICY = 'POLICY'
    VLM = 'VLM'

    def n(node_id, label, desc, kind=POLICY, when_pass='', when_fail='', waivable=False, hint=''):
        return {
            'node_id': node_id,
            'label': label,
            'note': desc,
            'hint': hint,
            'kind': kind,
            'when_pass': when_pass,
            'when_fail': when_fail,
            'waivable': bool(waivable),
        }

    # --- Tầng 1: bước chung mọi loại nghỉ ---
    common_inputs = [
        n('C1_DATES', 'Khoảng ngày nghỉ hợp lệ',
          'Nhận ngày bắt đầu / kết thúc, kiểm tra đúng định dạng, từ ngày <= đến ngày, không quá dài.',
          when_pass='Sang bước tính số ngày làm việc',
          when_fail='Yêu cầu nhập lại khoảng ngày'),
        n('C2_CALENDAR', 'Tính số ngày làm việc thực tế (N)',
          'Trừ thứ 7, chủ nhật, ngày lễ. Nếu toàn bộ là ngày nghỉ thì không cần phép.',
          when_pass='Xác định loại nghỉ phù hợp',
          when_fail='Đánh dấu không cần phép / chuyển nhân sự xem xét',
          hint='Từ số ngày N sẽ quyết định phân cấp duyệt sau này'),
        n('C3_LEAVE_TYPE', 'Xác định loại hình nghỉ phép',
          'Dựa vào lựa chọn của nhân viên hoặc nội dung tự do, gán vào 1 trong 8 loại hình.'),
    ]

    def branch(branch_id, title, color, icon, who, what, how, steps, next_steps):
        return {
            'branch_id': branch_id,
            'title': title,
            'color': color,
            'icon': icon,
            'who': who,
            'what': what,
            'how': how,
            'steps': steps,
            'next': next_steps,
        }

    # --- 8 nhánh theo loại nghỉ (ngắn gọn, văn phòng) ---
    br_annual = branch(
        'ANNUAL', 'Nghỉ phép năm (hưởng lương)', '#3b82f6', '🕒',
        who='Nhân viên thường đã qua thử việc',
        what='Sử dụng số ngày phép năm đã tích lũy (mặc định 12 ngày/năm)',
        how='Trừ trực tiếp vào ngân hàng phép; ưu tiên báo trước và giới hạn tỷ lệ phòng ban.',
        steps=[
            n('ANN_BAL', 'Số dư phép còn đủ N ngày',
              'Kiểm tra số ngày phép còn lại lớn hơn hoặc bằng số ngày yêu cầu.',
              when_pass='Sang kiểm tra thời gian báo trước',
              when_fail='Từ chối tự động (yêu cầu giảm ngày hoặc chọn nghỉ không lương riêng)'),
            n('ANN_NOTICE', 'Báo trước đủ thời gian',
              'Nhỏ hơn 4 ngày → 1 ngày trước, 4–5 ngày → 3 ngày, 6 ngày trở lên → 7 ngày.',
              when_pass='Sang kiểm tra năng lực đội nhóm',
              when_fail='Chuyển quản lý xem xét đặc cách',
              waivable=True, hint='Quản lý có thể bỏ qua nếu việc gấp'),
            n('ANN_TEAM', 'Tỷ lệ nghỉ đồng thời của phòng ≤ 30%',
              'Tránh tình trạng nhiều người cùng nghỉ làm ùng. Đếm số người đã duyệt + đơn hiện tại.',
              when_pass='Sang bước bàn giao công việc',
              when_fail='Chuyển quản lý xem xét, tổ chức hỗ trợ',
              waivable=True, hint='Quản lý có thể chấp nhận với lý do đặc biệt'),
            n('ANN_HO', 'Bàn giao công việc (khi nghỉ ≥ 3 ngày)',
              'Phải có người cùng phòng, đang làm việc, không tự mình, không nghỉ trùng.',
              when_fail='Yêu cầu chỉ định lại người nhận bàn giao'),
        ],
        next_steps='Nhỏ hơn 3 ngày → duyệt tự động | 3–5 ngày → Quản lý trực tiếp | 6–19 ngày → Trưởng bộ phận | 20 ngày trở lên → Tổng giám đốc')

    br_unpaid = branch(
        'UNPAID_OTHER', 'Nghỉ không lương (thỏa thuận)', '#f59e0b', '💸',
        who='Nhân viên cần nghỉ dài ngoài số phép năm',
        what='Không hưởng lương, không trừ phép; là thỏa thuận hai bên.',
        how='Bắt buộc có lý do rõ ràng; báo trước ít nhất 7 ngày kể cả 1 ngày nghỉ.',
        steps=[
            n('UN_RSN', 'Có lý do rõ ràng',
              'Lý do không được để trống, cần mô tả tình huống (đi du lịch, việc riêng, học thêm…).',
              when_fail='Yêu cầu bổ sung lý do'),
            n('UN_NOTICE', 'Báo trước tối thiểu 7 ngày',
              'Do ảnh hưởng tiến độ công ty, yêu cầu báo trước lâu hơn phép năm.',
              when_pass='Sang kiểm tra tỷ lệ đội nhóm',
              when_fail='Chuyển quản lý xem xét đặc cách',
              waivable=True),
            n('UN_TEAM', 'Tỷ lệ nghỉ đồng thời ≤ 30%',
              'Giới hạn tương tự phép năm để phòng ban vận hành ổn định.',
              waivable=True,
              when_fail='Chuyển quản lý xem xét, ưu tiên sắp xếp người thay thế'),
            n('UN_HO', 'Bàn giao công việc (bắt buộc kể cả 1 ngày)',
              'Do nghỉ không lương, phải đảm bảo có người nhận việc 100%.',
              when_fail='Yêu cầu chỉ định lại người nhận bàn giao'),
            n('UN_HRD', 'Thêm bộ phận nhân sự vào dòng duyệt (≥ 6 ngày)',
              'Nghỉ 6 ngày trở lên: bộ phận Nhân sự tham gia đồng duyệt.',
              when_pass='Gắn thêm bước Nhân sự vào quy trình phê duyệt'),
        ],
        next_steps='1–5 ngày → Quản lý trực tiếp | 6–19 ngày → Trưởng bộ phận + Nhân sự | 20 ngày trở lên → Trưởng bộ phận + Nhân sự + Tổng giám đốc')

    br_special = branch(
        'SPECIAL_PAID', 'Nghỉ phúc lợi (hưởng lương 100%)', '#10b981', '💒',
        who='Nhân viên có sự kiện gia đình (kết hôn / tang sự trực hệ)',
        what='Không trừ phép năm; công ty trả lương đầy đủ theo luật Điều 115 khoản 1.',
        how='Chia thành 6 sự kiện chuẩn, có số ngày cố định; cần giấy tờ chứng minh.',
        steps=[
            n('SP_CAT', 'Thuộc 1 trong 6 sự kiện hưởng lương',
              'Tự cưới 3 ngày / con cưới 1 ngày / bố mẹ mình hoặc bố mẹ vợ chồng mất 3 ngày / vợ chồng mất 3 ngày / con mất 3 ngày.',
              when_fail='Yêu cầu chọn đúng sự kiện hoặc gửi tách phần dư ra loại khác'),
            n('SP_DOC', 'Có giấy tờ chứng minh hợp lệ',
              'Kết hôn → giấy đăng ký / thiệp mời; tang sự → giấy chứng tử hoặc giấy báo tử.',
              when_pass='Sang kiểm tra nơi cấp / ngày cấp',
              when_fail='Yêu cầu bổ sung chứng từ'),
            n('SP_ISSUE', 'Giấy tờ có nơi cấp và ngày cấp rõ ràng',
              'Tổ chức cấp (phòng tư pháp / bệnh viện / cơ quan) và ngày cấp phải có mặt.',
              when_fail='Yêu cầu bổ sung thông tin trên chứng từ'),
            n('SP_SIG', 'Chứng từ có dấu đỏ hoặc chữ ký',
              'Đảm bảo tính chính thức của giấy tờ, tránh chứng từ trắng / sao chép không xác thực.',
              when_pass='Sang bước chung cuối (không trùng, phân cấp duyệt)',
              when_fail='Chuyển quản lý xem xét, chấp nhận hoặc yêu cầu bản rõ hơn'),
        ],
        next_steps='Con cưới 1 ngày → duyệt tự động | 3 ngày (tự cưới / tang sự trực hệ 4 loại / vợ chồng / con mất) → Quản lý trực tiếp | Thừa ngày → Trưởng bộ phận')

    br_statutory = branch(
        'STATUTORY_UNPAID', 'Nghỉ luật định (không hưởng lương)', '#06b6d4', '⚰️',
        who='Nhân viên có sự kiện gia đình họ hàng xa',
        what='Luật Điều 115 khoản 2 bắt buộc công ty cho nghỉ 1 ngày / sự kiện; không trả lương.',
        how='Công ty không được từ chối; chỉ cần xác minh mối quan hệ họ hàng là được.',
        steps=[
            n('ST_CAT', 'Thuộc 4 sự kiện luật định 1 ngày',
              'Ông bà nội ngoại mất / anh chị em mất / bố mẹ tái hôn / anh chị em kết hôn.',
              when_fail='Yêu cầu tách riêng phần dư ra nghỉ không lương thỏa thuận hoặc phép năm'),
            n('ST_DOC', 'Có bằng chứng về mối quan hệ họ hàng',
              'Có thể sử dụng giấy báo tử, giấy đăng ký kết hôn họ hàng; không yêu cầu nghiêm ngặt 100%.',
              when_pass='Sang bước chung cuối; công ty không được từ chối nghỉ',
              when_fail='Chuyển quản lý xem xét, xác minh quan hệ rồi cho nghỉ theo luật'),
        ],
        next_steps='Luôn → Quản lý trực tiếp xem xác minh 1 lần (không tự động duyệt; nhưng công ty phải cho nghỉ)')

    br_sick = branch(
        'SICK_MEDICAL', 'Nghỉ ốm đau thông thường', '#a855f7', '🏥',
        who='Nhân viên bị ốm, có giấy khám bệnh / giấy ra viện từ bệnh viện',
        what='Hệ thống ghi nhận nghỉ; quyền lợi tiền lương từ bảo hiểm xã hội, nhân sự xử lý riêng.',
        how='Yêu cầu 4 loại giấy tờ y tế; mô hình thị giác (VLM) kiểm tra độ tin cậy của chứng từ.',
        steps=[
            n('SK_DOC', 'Chứng từ thuộc nhóm giấy tờ y tế',
              'Giấy khám bệnh / Giấy ra viện / Tóm tắt bệnh án / Giấy xác nhận chấn thương.',
              when_fail='Yêu cầu nộp đúng loại chứng từ y tế'),
            n('SK_CLEAR', 'Chứng từ rõ nét, không mờ',
              'Máy đọc được chữ, không nghiêng, không bị che khuất phần quan trọng (tên bệnh nhân, ngày).',
              kind=VLM,
              when_pass='Trích xuất thông tin trên chứng từ',
              when_fail='Yêu cầu tải lại ảnh rõ hơn'),
            n('SK_TEXT', 'Đọc đủ thông tin trên chứng từ',
              'Tên bệnh nhân, nơi cấp, ngày cấp, chẩn đoán, khoảng ngày bác sĩ cho nghỉ, số ngày cấp.',
              kind=VLM,
              when_fail='Yêu cầu bổ sung, thiếu trường nào báo thiếu trường đó'),
            n('SK_CHECK', 'Kiểm tra dấu hiệu giả mạo',
              'Có dấu đỏ? có chữ ký bác sĩ? có dấu hiệu cắt ghép / chỉnh sửa bằng AI?',
              kind=VLM,
              when_fail='Chuyển nhân sự xem xét thủ công trước khi phê duyệt'),
            n('SK_MATCH', 'Chứng từ khớp với đơn nghỉ',
              'Tên bệnh nhân trùng tên người nghỉ; ngày nghỉ nằm trong khoảng bác sĩ chỉ định.',
              kind=VLM,
              when_fail='Yêu cầu nhân viên làm rõ (tên sai / ngày ra ngoài phạm vi bác sĩ)'),
            n('SK_HO', 'Bàn giao công việc (≥ 3 ngày ốm)',
              'Nếu nghỉ dài cần người nhận việc tránh gián đoạn công việc.',
              when_fail='Yêu cầu chỉ định lại người nhận bàn giao'),
            n('SK_WARN', 'Ghi chú tiền lương từ BHXH',
              'Thêm ghi chú cho nhân viên: tiền trợ cấp ốm đau nhân sự xử lý hồ sơ bảo hiểm riêng.'),
        ],
        next_steps='1–2 ngày (đủ chứng từ hợp lệ) → duyệt tự động | 3–6 ngày → Quản lý trực tiếp | 7–19 ngày → Trưởng bộ phận | 20 ngày trở lên → Tổng giám đốc')

    br_emergency = branch(
        'MEDICAL_EMERGENCY', 'Nghỉ cấp cứu / nhập viện', '#ef4444', '🚑',
        who='Nhân viên cấp cứu, nhập viện hoặc điều trị nội trú gấp',
        what='Luôn cần bộ phận nhân sự xem xét đầu tiên; bỏ qua quy tắc báo trước.',
        how='Thời gian nộp chứng từ giãn ra 48 giờ; máy đọc chỉ cần 2 thông tin tối thiểu.',
        steps=[
            n('EM_HR', 'Luôn chuyển nhân sự xem xét đầu tiên',
              'Do tính chất cấp cứu, không tự động duyệt, không quản lý trực tiếp duyệt đầu tay.'),
            n('EM_TIME', 'Thời hạn nộp chứng từ 48 giờ',
              'Nhân viên có 48 giờ kể từ ngày đầu tiên nghỉ để tải giấy ra viện / xác nhận cấp cứu.',
              when_fail='Chuyển trạng thái chờ nhân viên bổ sung'),
            n('EM_MIN', 'Đọc tối thiểu tên + chẩn đoán / nơi điều trị',
              'Không yêu cầu 100% thông tin; đủ nhận dạng bệnh nhân và chẩn đoán là được (nhân sự xem lại sau).',
              kind=VLM,
              when_fail='Chuyển nhân sự xem xét thủ công nếu chứng từ quá khó đọc'),
        ],
        next_steps='Luôn → Nhân sự (b1) + Trưởng bộ phận (≥ 7 ngày đồng duyệt)')

    br_accident = branch(
        'WORK_ACCIDENT', 'Nghỉ tai nạn lao động', '#ec4899', '⚒️',
        who='Nhân viên bị tai nạn trong giờ làm việc hoặc đường đi làm, có hồ sơ tai nạn lao động.',
        what='Quyền lợi từ bảo hiểm tai nạn lao động; công ty không trả lương trực tiếp.',
        how='Bước 1 luôn nhân sự xem đầy đủ bộ hồ sơ (bằng chứng chấn thương + quyết định tai nạn lao động).',
        steps=[
            n('WA_HR', 'Nhân sự kiểm tra đầy đủ bộ hồ sơ BHXH-TNLĐ',
              'Yêu cầu giấy xác nhận chấn thương + quyết định/phê duyệt tai nạn lao động.'),
            n('WA_DUR', 'Phân cấp theo thời gian nghỉ sau khi hồ sơ hợp lệ',
              'Sử dụng phân cấp của nghỉ ốm đau thông thường, nhưng luôn có bước nhân sự đầu tiên.'),
        ],
        next_steps='Bước 1: Nhân sự xác minh hồ sơ | Bước 2: < 7 ngày → Trưởng bộ phận | 7 ngày trở lên → Trưởng bộ phận + Tổng giám đốc')

    br_maternity = branch(
        'MATERNITY', 'Nghỉ thai sản / sinh con', '#f43f5e', '🤰',
        who='Nhân viên nữ mang thai / mới sinh; (vợ người lao động cũng có thể áp dụng phần trích theo luật).',
        what='Quyền lợi tiền từ bảo hiểm thai sản; nhân sự chủ trì toàn bộ quy trình.',
        how='Hỗ trợ nghỉ thành nhiều đợt (trước sinh / sau sinh); ngày nghỉ tổng cộng 4–6 tháng theo luật.',
        steps=[
            n('MA_HR', 'Luôn nhân sự chủ trì, không tự động duyệt',
              'Không AI hay quản lý trực tiếp duyệt thai sản; luôn cần bộ phận nhân sự kiểm tra.'),
            n('MA_PHASE', 'Thời gian nghỉ thành nhiều đợt được',
              'Có thể nghỉ trước sinh 1–2 tháng, phần còn lại sau sinh; nhân sự hướng dẫn thời gian cụ thể.'),
            n('MA_DOC', 'Có giấy xác nhận thai sản / giấy khai sinh',
              'Giấy từ bệnh viện / phòng khám sản khoa; ghi rõ ngày dự sinh hoặc ngày sinh thực tế.'),
        ],
        next_steps='Luôn → Nhân sự (b1) + Tổng giám đốc nếu lần nghỉ ≥ 30 ngày')

    branches = [br_annual, br_unpaid, br_special, br_statutory, br_sick, br_emergency, br_accident, br_maternity]

    # --- Tầng 3: bước chung cuối sau khi ra khỏi 8 nhánh ---
    common_final = [
        n('F1_OVERLAP', 'Không trùng với đơn đã duyệt',
          'Nếu ngày nghỉ nằm hoàn toàn trong đơn đã duyệt → từ chối tự động (không bị trừ phép lần 2); nếu trùng 1 phần → yêu cầu sửa.',
          when_pass='Sang bước phân cấp người duyệt',
          when_fail='Yêu cầu sửa lại khoảng ngày / từ chối nếu đã được duyệt toàn bộ'),
        n('F2_AUTHORITY', 'Phân cấp người duyệt cuối cùng',
          'Tổng hợp phân cấp từ từng loại nghỉ + các bước quản lý đã đồng ý đặc cách; nếu không ai cần duyệt → duyệt tự động.',
          when_pass='Ghi nhận nghỉ phép; cập nhật số dư phép nếu cần',
          when_fail='Chuyển cho người đầu tiên trong dòng phê duyệt xem xét'),
    ]

    outcomes = [
        {'id': 'NO_LEAVE_REQUIRED', 'color': '#64748b',
         'title': 'Không cần nghỉ phép',
         'body': 'Toàn bộ ngày yêu cầu đã là thứ 7 / chủ nhật / ngày lễ nên đóng đơn, không trừ gì cả.'},
        {'id': 'AUTO_APPROVE', 'color': '#10b981',
         'title': 'Duyệt tự động',
         'body': 'Tất cả các bước đều đạt, không còn người cần phê duyệt. Hệ thống ghi nhận phép, cập nhật số dư phép nếu là phép năm.'},
        {'id': 'AUTO_REJECT', 'color': '#ef4444',
         'title': 'Từ chối tự động',
         'body': 'Số dư phép âm, đơn đã tồn tại ngày trùng 100%, hoặc chứng từ đã bị từ chối lần trước.'},
        {'id': 'NEED_CORRECTION', 'color': '#f59e0b',
         'title': 'Yêu cầu sửa / bổ sung',
         'body': 'Nhân viên cần sửa ngày, thêm lý do, hoặc tải lại chứng từ phù hợp.'},
        {'id': 'ESCALATE', 'color': '#3b82f6',
         'title': 'Chuyển người có thẩm quyền duyệt',
         'body': 'Đơn hợp lệ nhưng cần Quản lý / Trưởng bộ phận / Nhân sự / Tổng giám đốc xem xét và phê duyệt.'},
    ]

    def flatten_nodes(bs):
        return [nd for b in bs for nd in b.get('steps', [])]

    all_nodes = list(common_inputs) + flatten_nodes(branches) + list(common_final)
    vlm_total = sum(1 for x in all_nodes if x['kind'] == VLM)
    policy_total = sum(1 for x in all_nodes if x['kind'] == POLICY)

    tree = {
        'version': '4.1.0',
        'layout': 'TIERED_FAN_OUT',
        'common_tier_title': 'Bước chung mọi loại nghỉ',
        'common_inputs': common_inputs,
        'branch_tier_title': '8 loại hình nghỉ phép (mỗi loại đi theo 1 nhánh riêng)',
        'branches': branches,
        'final_tier_title': 'Bước chung cuối cùng trước khi ra quyết định',
        'common_final': common_final,
        'outcomes_title': '5 kết quả cuối cùng hệ thống trả về',
        'outcomes': outcomes,
        'legend': {
            'PASS': 'Điều kiện đạt → tiếp tục sang bước kế tiếp',
            'FAIL': 'Điều kiện chưa đạt → yêu cầu sửa hoặc chuyển người xem xét',
            'WAIVABLE': 'Quản lý có thể chấp nhận đặc cách nếu tình huống xứng đáng',
            'VLM': 'Máy (mô hình nhìn thấy) phân tích chứng từ thay cho người đọc',
        },
        'stats': {
            'total_steps': len(all_nodes),
            'visual_check_steps': vlm_total,
            'policy_steps': policy_total,
            'leave_types': len(branches),
            'final_outcomes': 5,
        }
    }
    return {'success': True, 'tree': tree}

@router.get('/calendar')
def calendar(from_date: date,to_date: date):
    if from_date>to_date or (to_date-from_date).days>3660: raise ValueError('Khoảng ngày không hợp lệ.')
    try:
        days=CalendarService().days(from_date,to_date)
        return {'success':True,'requested_calendar_days':len(days),
            'requested_working_days':sum(k.value=='WORKING_DAY' for _,k in days),
            'days':[{'date':d.isoformat(),'day_type':k.value} for d,k in days]}
    except CalendarUnavailable as exc:
        return {'success':False,'decision':'ESCALATE','error_code':'LEGAL_REVIEW_REQUIRED',
            'uncertainty_category':'OUT_OF_POLICY','target_role':'HR','detail':str(exc)}

@router.get('/llm-status')
def get_llm_status():
    from llm_client import get_qwen_engine
    status=get_qwen_engine().get_status()
    return {**status,'ready_for_inference':status['online'],'target_model':status['model'],'last_error':status['error']}

@router.get('/vlm-status')
def get_vlm_status():
    import os
    import json
    from urllib import request as urlrequest
    from urllib import error as urlerror
    base = os.getenv("VLM_OLLAMA_BASE", "http://localhost:11434")
    model = os.getenv("VLM_TARGET_MODEL", "qwen2.5-vl:3b")
    reachable = False
    loaded = False
    models_list = []
    last_err = None
    try:
        with urlrequest.urlopen(f"{base}/api/tags", timeout=3.0) as r:
            reachable = r.status == 200
            data = json.loads(r.read().decode() or "{}")
            models_list = [m.get("name", "") for m in data.get("models", [])]
            loaded = any(model in m for m in models_list)
    except (urlerror.URLError, OSError, ValueError, TimeoutError) as e:
        last_err = f"{type(e).__name__}: {e}"
    mode = "READY" if (reachable and loaded) else (
        "OLLAMA_NOT_RUNNING" if not reachable else "MODEL_NOT_PULLED"
    )
    return {
        'ollama_reachable': reachable,
        'model_loaded': loaded,
        'target_model': model,
        'base_url': base,
        'available_models': models_list,
        'fallback_mode': not (reachable and loaded),
        'mode': mode,
        'last_error': last_err,
    }

@router.get('/ai-stack-status')
def get_ai_stack_status():
    return {'llm':get_llm_status(),'vlm':get_vlm_status(),'system':{'backend':'ok','db':'ok','version':'3.0.0'}}

class LeaveAllocationInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    target_type: str
    target_id: str | None = None
    days: float = Field(gt=0,allow_inf_nan=False)
    reason: str = Field(min_length=1)

@router.post('/allocate-leave')
def allocate_leave_endpoint(payload: LeaveAllocationInput,actor_id=Depends(actor)):
    with st.transaction() as conn:
        if not st.has_role(conn,actor_id,'HRD'): raise st.AccessDenied('Chỉ HRD được cấp phép.')
        query="SELECT employee_id FROM employees WHERE status='ACTIVE'"
        args=[]
        if payload.target_type=='EMPLOYEE': query+=' AND employee_id=?';args=[payload.target_id]
        elif payload.target_type=='DEPARTMENT': query+=' AND department=?';args=[payload.target_id]
        elif payload.target_type!='ALL': raise ValueError('target_type không hợp lệ.')
        rows=conn.execute(query,args).fetchall()
        import uuid
        allocation='ALLOC-'+uuid.uuid4().hex
        for row in rows:
            conn.execute('UPDATE employees SET remaining_leave_days=remaining_leave_days+? WHERE employee_id=?',(payload.days,row[0]))
            conn.execute("INSERT INTO leave_transactions(request_id,employee_id,kind,amount,created_at) VALUES(?,?,'ALLOCATION',?,?)",(allocation,row[0],payload.days,st.now_iso()))
        st.audit(conn,allocation,'ALLOCATION',actor_id+': '+payload.reason)
        return {'success':True,'updated_count':len(rows),'message':f'Đã cấp {payload.days} ngày cho {len(rows)} nhân sự.'}

@router.get('/gpu')
def get_gpu_status():
    import subprocess
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.used','--format=csv,noheader'],capture_output=True,text=True,timeout=3)
        return {'success':result.returncode==0,'gpu':result.stdout}
    except (OSError,subprocess.TimeoutExpired): return {'success':False,'gpu':None}

@router.get('/debug-llm')
@router.get('/check-env')
def debug_status(): return get_llm_status()

@router.get('/cleanup-files')
@router.get('/kill-tmux')
def retired_process_controls():
    raise HTTPException(410,'Điều khiển/xóa tiến trình không thuộc API phê duyệt nghỉ phép.')
