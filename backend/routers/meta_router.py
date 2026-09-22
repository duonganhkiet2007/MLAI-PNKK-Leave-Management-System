"""Reference data and policy metadata. No model calls for dashboards."""
import os
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

    def n(node_id, label, desc, kind=POLICY, when_pass='', when_fail='', waivable=False, hint='', clause='', doc_req='', pass_desc='', fail_desc=''):
        return {
            'node_id': node_id,
            'label': label,
            'note': desc,
            'hint': hint,
            'kind': kind,
            'when_pass': when_pass,
            'when_fail': when_fail,
            'waivable': bool(waivable),
            'clause': clause,
            'doc_req': doc_req,
            'pass_desc': pass_desc,
            'fail_desc': fail_desc,
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

    # --- 8 nhánh theo loại nghỉ với đầy đủ nội dung từ Quy chế số 18/2024/QC-NS & BLLĐ 2019 ---
    br_annual = branch(
        'ANNUAL', 'Nghỉ phép năm (hưởng lương)', '#3b82f6', '🕒',
        who='Nhân viên chính quy đã qua thời gian thử việc',
        what='Sử dụng số ngày phép năm đã tích lũy (mặc định 12 ngày/năm đối với nhân viên làm đủ 12 tháng)',
        how='Trừ trực tiếp vào ngân hàng phép; ưu tiên báo trước đúng hạn và giới hạn tỷ lệ vắng mặt phòng ban.',
        steps=[
            n('ANN_BAL', 'Kiểm tra số dư quỹ phép năm',
              'Số ngày xin nghỉ phải nhỏ hơn hoặc bằng số dư ngày phép năm khả dụng trong tài khoản nhân sự. Nhân viên chính quy làm việc đủ 12 tháng được hưởng 12 ngày phép năm.',
              clause='Điều 10.2 QC-NS',
              when_pass='Đạt số dư quỹ phép',
              pass_desc='Số dư quỹ phép năm hợp lệ; hệ thống tự động trừ quỹ phép khi đơn được phê duyệt.',
              when_fail='Từ chối tự động (Hết phép)',
              fail_desc='Số ngày xin nghỉ vượt quá số dư phép năm hiện có; yêu cầu giảm ngày hoặc chuyển sang Nghỉ không lương.'),
            n('ANN_NOTICE', 'Thời hạn nộp đơn báo trước theo số ngày',
              'Nghỉ 1–3 ngày: nộp trước ít nhất 1 ngày làm việc. Nghỉ 4–5 ngày: nộp trước ít nhất 3 ngày làm việc. Nghỉ trên 5 ngày: nộp trước ít nhất 7 ngày làm việc.',
              clause='Điều 10.1 QC-NS',
              waivable=True,
              hint='Quản lý trực tiếp có quyền đặc cách duyệt nếu nhân viên có việc gia đình đột xuất chính đáng.',
              when_pass='Đúng thời hạn quy định',
              pass_desc='Thời hạn nộp đơn đạt chuẩn quy chế; chuyển sang kiểm tra tỷ lệ nhân sự phòng ban.',
              when_fail='Nộp gấp · Quản lý xét đặc cách',
              fail_desc='Cảnh báo nộp gấp (OUT_OF_POLICY); chuyển Quản lý trực tiếp đánh giá mức độ cấp thiết để quyết định đặc cách.'),
            n('ANN_TEAM', 'Tỷ lệ nhân sự nghỉ đồng thời của phòng ban ≤ 30%',
              'Tỷ lệ nhân sự vắng mặt tại cùng phòng ban trong cùng thời điểm không vượt quá 30% tổng quân số nhằm đảm bảo tiến độ vận hành.',
              clause='Quy chuẩn vận hành',
              waivable=True,
              hint='Quản lý có thể chấp thuận nếu đã có phương án phân công người hỗ trợ công việc.',
              when_pass='Đảm bảo vận hành phòng ban',
              pass_desc='Tỷ lệ vắng mặt trong ngưỡng an toàn (≤ 30%); chuyển sang kiểm tra bàn giao công việc.',
              when_fail='Quá tải · Quản lý điều phối',
              fail_desc='Vượt trần 30% quân số; chuyển Quản lý trực tiếp cân nhắc tình hình dự án hoặc đàm phán đổi lịch nghỉ.'),
            n('ANN_ABUSE', 'Kiểm soát lạm dụng tách đơn phép năm',
              'Kiểm soát nhân viên nộp nhiều đơn phép năm đơn lẻ cộng dồn vượt quá 2 ngày trong cùng một tháng dương lịch.',
              clause='Chống lạm dụng tách đơn',
              when_pass='Không có dấu hiệu chia nhỏ',
              pass_desc='Đạt điều kiện tách đơn bình thường; cho phép áp dụng phê duyệt tự động nếu thời lượng ≤ 2 ngày.',
              when_fail='Cảnh báo tách đơn · Chuyển Quản lý',
              fail_desc='Kích hoạt cờ FLAG_ABUSE_PATTERN; không cho phép AI tự duyệt, chuyển Quản lý trực tiếp kiểm tra lý do.'),
            n('ANN_HO', 'Bàn giao công việc (khi nghỉ ≥ 3 ngày)',
              'Bắt buộc khi đơn xin nghỉ từ 3 ngày làm việc trở lên. Phải chỉ định đồng nghiệp cùng phòng ban đang làm việc, không tự bàn giao cho mình, không trùng lịch nghỉ.',
              clause='Điều 10.3 QC-NS',
              doc_req='Biên bản / Chỉ định nhân sự nhận bàn giao công việc cùng phòng ban',
              when_pass='Hoàn tất bàn giao công việc',
              pass_desc='Người nhận bàn giao hợp lệ và đã sẵn sàng tiếp nhận đầu việc trong thời gian nghỉ.',
              when_fail='Chưa đạt · Chỉ định lại người nhận',
              fail_desc='Người nhận bàn giao trùng lịch nghỉ hoặc không cùng bộ phận; yêu cầu chỉ định lại người nhận bàn giao.'),
        ],
        next_steps='1–2 ngày → duyệt tự động | 3–5 ngày → Quản lý trực tiếp | 6–19 ngày → Trưởng bộ phận | 20 ngày trở lên → Tổng giám đốc')

    br_unpaid = branch(
        'UNPAID_OTHER', 'Nghỉ không lương (thỏa thuận)', '#f59e0b', '💸',
        who='Nhân viên chính quy hoặc nhân viên thử việc cần nghỉ giải quyết việc cá nhân ngoài số phép năm',
        what='Không hưởng lương, không trừ phép năm; là thỏa thuận giữa người lao động và doanh nghiệp.',
        how='Bắt buộc có lý do rõ ràng; báo trước ít nhất 7 ngày làm việc kể cả 1 ngày nghỉ.',
        steps=[
            n('UN_RSN', 'Lý do giải quyết việc cá nhân chính đáng',
              'Bắt buộc giải trình cụ thể lý do cá nhân (việc gia đình, học tập nâng cao, nghỉ việc riêng cá nhân...). Tuyệt đối không được để trống.',
              clause='Điều 8.2 & Điều 18.2 QC-NS',
              when_pass='Lý do rõ ràng, minh bạch',
              pass_desc='Tiếp nhận hồ sơ nghỉ thỏa thuận không hưởng lương theo đúng quy trình.',
              when_fail='Yêu cầu bổ sung lý do',
              fail_desc='Lý do để trống hoặc chưa đủ thông tin; yêu cầu nhân viên cập nhật giải trình rõ ràng.'),
            n('UN_NOTICE', 'Thời hạn báo trước tối thiểu 7 ngày làm việc',
              'Do ảnh hưởng trực tiếp đến kế hoạch hoạt động của doanh nghiệp, bắt buộc nộp đơn trước ít nhất 7 ngày làm việc đối với mọi thời lượng (kể cả nghỉ 1 ngày).',
              clause='Quy chế vận hành',
              waivable=True,
              hint='Quản lý có thể duyệt đặc cách nếu phát sinh tình huống gia đình khẩn cấp ngoài tầm kiểm soát.',
              when_pass='Đúng thời hạn quy chuẩn',
              pass_desc='Đảm bảo đủ thời gian để bộ phận sắp xếp phương án nhân sự thay thế.',
              when_fail='Nộp gấp · Quản lý xét đặc cách',
              fail_desc='Nộp dưới 7 ngày làm việc; chuyển Quản lý trực tiếp đánh giá mức độ khẩn cấp để duyệt đặc cách.'),
            n('UN_TEAM', 'Đảm bảo vận hành phòng ban (≤ 30%)',
              'Tỷ lệ nghỉ đồng thời của phòng ban ≤ 30% quân số nhằm bảo đảm duy trì hoạt động bình thường.',
              clause='Quy chuẩn vận hành',
              waivable=True,
              when_pass='Đảm bảo vận hành',
              pass_desc='Phòng ban đủ nguồn lực đảm nhiệm công việc trong thời gian nhân viên vắng mặt.',
              when_fail='Cảnh báo thiếu hụt nhân sự',
              fail_desc='Chuyển Quản lý trực tiếp xem xét, ưu tiên sắp xếp người thay thế trước khi ký duyệt.'),
            n('UN_HO', 'Bắt buộc bàn giao công việc (kể cả 1 ngày)',
              'Mọi đơn xin nghỉ không lương (kể cả nghỉ 1 ngày) bắt buộc phải chỉ định nhân sự cùng bộ phận nhận bàn giao 100% công việc.',
              clause='Quy chuẩn bàn giao',
              doc_req='Chỉ định nhân sự tiếp nhận toàn bộ công việc tồn đọng',
              when_pass='Đã phân công người tiếp nhận',
              pass_desc='Đảm bảo toàn bộ nhiệm vụ và tiến độ dự án không bị gián đoạn.',
              when_fail='Yêu cầu chỉ định người nhận việc',
              fail_desc='Chưa có người nhận bàn giao hợp lệ; yêu cầu bổ sung trước khi chuyển cấp thẩm quyền.'),
            n('UN_HRD', 'Thẩm quyền đồng phê duyệt của Nhân sự (HRD)',
              'Đơn xin nghỉ không lương trên 5 ngày làm việc bắt buộc có sự tham gia phê duyệt của Trưởng phòng ban và Giám đốc Nhân sự (HRD); từ 20 ngày cần Tổng Giám đốc.',
              clause='Điều 18.2 QC-NS',
              when_pass='Đúng luồng phân cấp',
              pass_desc='Gắn thêm bước Giám đốc Nhân sự (HRD) vào quy trình phê duyệt trên hệ thống.',
              when_fail='Chặn luồng sai cấp',
              fail_desc='Không cho phép Quản lý cấp cơ sở tự phê duyệt đơn nghỉ không lương dài ngày.'),
        ],
        next_steps='1–5 ngày → Quản lý trực tiếp | 6–19 ngày → Trưởng bộ phận + Nhân sự | 20 ngày trở lên → Trưởng bộ phận + Nhân sự + Tổng giám đốc')

    br_special = branch(
        'SPECIAL_PAID', 'Nghỉ phúc lợi (hưởng lương 100%)', '#10b981', '💒',
        who='Nhân viên có sự kiện kết hôn hoặc tang sự trực hệ gia đình',
        what='Hưởng 100% nguyên lương do doanh nghiệp chi trả; không trừ quỹ phép năm theo Bộ luật Lao động.',
        how='Chia thành 6 sự kiện chuẩn, có số ngày cố định theo luật; bắt buộc đính kèm hồ sơ minh chứng.',
        steps=[
            n('SP_CAT', 'Thuộc danh mục 6 sự kiện luật định hưởng lương',
              '1. Bản thân kết hôn (3 ngày); 2. Con đẻ/con nuôi kết hôn (1 ngày); 3. Cha/mẹ đẻ, cha/mẹ nuôi mất (3 ngày); 4. Cha/mẹ vợ hoặc chồng mất (3 ngày); 5. Vợ hoặc chồng mất (3 ngày); 6. Con đẻ/con nuôi mất (3 ngày).',
              clause='Điều 15.1 QC-NS & Khoản 1 Điều 115 BLLĐ',
              when_pass='Hưởng 100% lương theo luật',
              pass_desc='Sự kiện thuộc diện nghỉ hưởng nguyên lương do doanh nghiệp chi trả; không trừ quỹ phép năm.',
              when_fail='Không thuộc diện có lương (Bẫy quy chế)',
              fail_desc='Ví dụ anh/chị/em ruột kết hôn không có lương; chuyển Quản lý hướng dẫn chuyển sang Nghỉ không lương hoặc Phép năm.'),
            n('SP_DOC', 'Hồ sơ, giấy tờ minh chứng bắt buộc',
              'Bắt buộc nộp kèm chứng từ hợp lệ tương ứng với từng sự kiện (kết hôn hoặc tang chế trực hệ).',
              clause='Điều 15.2 QC-NS',
              doc_req='Giấy đăng ký kết hôn, Thiệp báo hỷ, Giấy chứng tử hoặc Giấy trích lục khai tử / Cáo phó',
              when_pass='Đầy đủ hồ sơ minh chứng',
              pass_desc='Hồ sơ minh chứng được đính kèm đúng loại chứng từ theo yêu cầu quy chế.',
              when_fail='Thiếu hồ sơ minh chứng',
              fail_desc='Chưa nộp hoặc nộp sai loại giấy tờ; yêu cầu nhân viên đính kèm chứng từ hợp lệ.'),
            n('SP_ISSUE', 'Cơ quan cấp và ngày cấp rõ ràng',
              'Tổ chức cấp (UBND xã/phường, cơ quan tư pháp, bệnh viện) và ngày cấp phải hiển thị rõ ràng trên văn bản.',
              clause='Quy chuẩn thẩm định pháp lý',
              when_pass='Thông tin pháp lý minh bạch',
              pass_desc='Xác định được thẩm quyền của cơ quan cấp và thời điểm phát sinh sự kiện hợp lệ.',
              when_fail='Thông tin mờ hoặc thiếu nguồn gốc',
              fail_desc='Chứng từ cắt góc, thiếu ngày cấp hoặc nơi cấp; yêu cầu nhân viên cung cấp bản chụp đầy đủ.'),
            n('SP_SIG', 'Con dấu mộc tròn đỏ & Chữ ký hợp pháp',
              'Chứng từ phải có con dấu mộc tròn đỏ chính thức của cơ quan nhà nước / tư pháp và chữ ký người có thẩm quyền.',
              clause='Quy chuẩn xác thực văn bản',
              when_pass='Chứng từ có giá trị pháp lý',
              pass_desc='Đảm bảo tính xác thực, đủ điều kiện để Quản lý trực tiếp phê duyệt nghỉ có lương.',
              when_fail='Chuyển Quản lý xác minh đối chiếu',
              fail_desc='Chứng từ thiếu mộc đỏ hoặc sao chép mờ; chuyển Quản lý trực tiếp đối chiếu bản gốc trước khi duyệt.'),
        ],
        next_steps='Tất cả sự kiện hưởng lương → Quản lý trực tiếp phê duyệt (kèm chứng từ hợp lệ)')

    br_statutory = branch(
        'STATUTORY_UNPAID', 'Nghỉ luật định (không hưởng lương)', '#06b6d4', '⚰️',
        who='Nhân viên có sự kiện gia đình họ hàng theo Bộ luật Lao động',
        what='Luật Lao động Điều 115 khoản 2 quy định người sử dụng lao động có trách nhiệm cho nghỉ 01 ngày; không trả lương.',
        how='Công ty không được từ chối nếu có thông báo; nếu quan hệ chưa rõ thì chuyển Quản lý xác minh hỗ trợ.',
        steps=[
            n('ST_CAT', 'Thuộc 4 sự kiện luật định 01 ngày',
              '1. Ông/bà nội, ông/bà ngoại mất; 2. Anh, chị, em ruột mất; 3. Cha hoặc mẹ kết hôn lại (tái hôn); 4. Anh, chị, em ruột kết hôn. Doanh nghiệp có nghĩa vụ cho nghỉ 01 ngày.',
              clause='Khoản 2 Điều 115 BLLĐ 2019',
              when_pass='Đạt điều kiện luật định',
              pass_desc='Công ty bắt buộc giải quyết cho nghỉ 01 ngày làm việc; không hưởng lương; không trừ phép năm.',
              when_fail='Sự kiện hoặc quan hệ chưa rõ ràng',
              fail_desc='Không nằm trong 4 trường hợp luật định; chuyển Quản lý trực tiếp xác minh để hướng dẫn loại nghỉ phù hợp.'),
            n('ST_DOC', 'Thông báo trước & Bằng chứng quan hệ họ hàng',
              'Nhân viên có trách nhiệm thông báo trước cho công ty và cung cấp căn cứ chứng minh mối quan hệ họ hàng theo quy định.',
              clause='Khoản 2 Điều 115 BLLĐ 2019',
              doc_req='Thiệp cưới, Giấy báo tử, Sổ hộ khẩu / xác nhận cư trú hoặc giấy tờ chứng minh quan hệ họ hàng',
              when_pass='Quan hệ họ hàng rõ ràng',
              pass_desc='Chấp thuận quyền nghỉ theo quy định pháp luật; công ty không được từ chối.',
              when_fail='Quản lý hỗ trợ xác minh',
              fail_desc='Cho phép sai khác nhỏ trong tên gọi; Quản lý trực tiếp xác nhận hỗ trợ nhân viên, không gây khó khăn vô cớ.'),
        ],
        next_steps='Quan hệ rõ → Quản lý trực tiếp xác minh | Quan hệ không rõ → vẫn chuyển Quản lý để quyết định')

    br_sick = branch(
        'SICK_MEDICAL', 'Nghỉ ốm đau thông thường', '#a855f7', '🏥',
        who='Nhân viên bị ốm đau, có chứng từ khám bệnh / điều trị từ cơ sở y tế hợp pháp',
        what='Hệ thống ghi nhận nghỉ; trợ cấp tiền lương do Quỹ Bảo hiểm xã hội (BHXH) chi trả, công ty không trừ phép năm.',
        how='Thẩm định chứng từ y tế qua thị giác máy (VLM); kiểm tra mộc tròn đỏ, chữ ký bác sĩ và đối chiếu thời gian chỉ định.',
        steps=[
            n('SK_DOC', 'Chứng từ y tế hợp lệ theo danh mục',
              'Hồ sơ nghỉ ốm hợp lệ bắt buộc phải có Giấy ra viện (nội trú) hoặc Giấy khám bệnh / Tóm tắt bệnh án có đầy đủ con dấu mộc tròn của cơ sở y tế và chữ ký bác sĩ điều trị.',
              clause='Điều 14.2 QC-NS & Luật BHXH',
              doc_req='Giấy ra viện hoặc Giấy khám bệnh có con dấu mộc tròn của cơ sở y tế hợp pháp',
              when_pass='Đúng danh mục chứng từ y tế',
              pass_desc='Chứng từ thuộc danh mục hợp lệ; chuyển sang bước thẩm định thị giác AI VLM.',
              when_fail='Sai loại chứng từ',
              fail_desc='Nộp đơn thuốc, phiếu thu tiền hoặc giấy tờ không hợp chuẩn; yêu cầu nộp đúng danh mục chứng từ y tế.'),
            n('SK_OUTPATIENT', 'Chứng từ nghỉ việc hưởng BHXH (ngoại trú)',
              'Đối với các đợt điều trị ngoại trú, nhân viên bắt buộc nộp bản gốc Giấy chứng nhận nghỉ việc hưởng BHXH (Mẫu C65-HD hoặc CT07) cho bộ phận C&B trong vòng 3 ngày làm việc kể từ ngày đi làm lại.',
              clause='Điều 14.3 QC-NS',
              doc_req='Bản gốc Giấy chứng nhận nghỉ việc hưởng BHXH (Mẫu C65-HD hoặc CT07)',
              when_pass='Cam kết nộp bản gốc đúng hạn',
              pass_desc='Hệ thống ghi nhận chứng từ ngoại trú để C&B hoàn tất thủ tục thanh toán trợ cấp BHXH.',
              when_fail='Nhắc nhở nộp chứng từ bản gốc',
              fail_desc='Hệ thống gửi cảnh báo yêu cầu nộp bản gốc Mẫu C65-HD trong vòng 3 ngày sau khi đi làm lại.'),
            n('SK_VLM_CHECK', 'Kiểm định con dấu mộc tròn & Chống giả mạo (AI VLM)',
              'Mô hình thị giác AI (VLM) kiểm tra: Có con dấu mộc tròn đỏ hợp pháp? Có chữ ký bác sĩ? Có dấu hiệu cắt ghép, chỉnh sửa bằng AI hay photoshop?',
              clause='Quy chuẩn thẩm định AI VLM',
              kind=VLM,
              when_pass='Chứng từ nguyên bản, tin cậy',
              pass_desc='Đạt độ tin cậy cao; tự động trích xuất các trường dữ liệu y tế.',
              when_fail='Dấu hiệu bất thường · Nhân sự thẩm tra',
              fail_desc='Phát hiện chứng từ mờ, nghi vấn chỉnh sửa hoặc thiếu mộc đỏ; chuyển Chuyên viên Nhân sự thẩm tra thủ công.'),
            n('SK_MATCH', 'Trùng khớp họ tên và thời gian chỉ định của bác sĩ',
              'Họ tên bệnh nhân trên chứng từ phải khớp 100% với tên nhân viên; khoảng ngày xin nghỉ phải nằm trọn trong thời gian bác sĩ chỉ định nghỉ.',
              clause='Quy chuẩn đối chiếu hồ sơ',
              kind=VLM,
              when_pass='Thông tin hoàn toàn trùng khớp',
              pass_desc='Dữ liệu y tế và đơn xin nghỉ khớp tuyệt đối; chuyển phân cấp phê duyệt theo số ngày.',
              when_fail='Lệch tên hoặc ngoài thời gian bác sĩ cấp',
              fail_desc='Thời gian nghỉ vượt quá số ngày bác sĩ cho phép hoặc sai lệch tên bệnh nhân; yêu cầu nhân viên giải trình.'),
            n('SK_HO', 'Bàn giao công việc (khi nghỉ ≥ 3 ngày)',
              'Nghỉ ốm dài ngày từ 3 ngày làm việc trở lên bắt buộc phải chỉ định đồng nghiệp cùng bộ phận nhận bàn giao việc để tránh gián đoạn công việc.',
              clause='Quy chuẩn vận hành nhóm',
              when_pass='Đã hoàn tất bàn giao',
              pass_desc='Đảm bảo duy trì công việc của nhóm trong thời gian điều trị.',
              when_fail='Yêu cầu chỉ định người nhận bàn giao',
              fail_desc='Chưa có người tiếp nhận việc; yêu cầu nhân viên hoặc quản lý hỗ trợ chỉ định người nhận việc.'),
            n('SK_NOTICE', 'Thời hạn báo trước & Phân cấp phê duyệt',
              'Thông báo trước 08:30 sáng ngày nghỉ đầu tiên. Đơn 1 ngày có chứng từ hợp lệ → AI tự động phê duyệt; từ 2 ngày trở lên → Quản lý trực tiếp phê duyệt. Lương do Quỹ BHXH chi trả.',
              clause='Điều 14.1 & Điều 18.1 QC-NS',
              when_pass='Đủ điều kiện phê duyệt',
              pass_desc='1 ngày hợp lệ được duyệt tự động; từ 2 ngày trở lên chuyển Quản lý trực tiếp ký duyệt.',
              when_fail='Báo trễ giờ · Quản lý xem xét',
              fail_desc='Thông báo sau 08:30 sáng; chuyển Quản lý trực tiếp xem xét lý do bất khả kháng.'),
        ],
        next_steps='1 ngày (đủ chứng từ hợp lệ, báo trước 08:30) → duyệt tự động | 2 ngày trở lên → Quản lý trực tiếp')

    br_emergency = branch(
        'MEDICAL_EMERGENCY', 'Nghỉ cấp cứu / nhập viện', '#ef4444', '🚑',
        who='Nhân viên cấp cứu, nhập viện hoặc điều trị nội trú khẩn cấp',
        what='Hưởng trợ cấp ốm đau/cấp cứu do Quỹ BHXH chi trả; công ty hỗ trợ đặc biệt theo quy chế khẩn cấp.',
        how='Bỏ qua quy tắc báo trước giờ làm việc; thời hạn nộp chứng từ giãn ra 48 giờ; bộ phận Nhân sự chủ trì đầu tiên.',
        steps=[
            n('EM_HR', 'Quy trình ưu tiên sức khỏe · Nhân sự thụ lý đầu tiên',
              'Do tính chất cấp bách đe dọa sức khỏe, hệ thống ưu tiên hỗ trợ y tế cho nhân viên; bộ phận Nhân sự (C&B) luôn là đơn vị tiếp nhận và thụ lý hồ sơ đầu tiên.',
              clause='Quy trình xử lý khẩn cấp',
              when_pass='Kích hoạt luồng khẩn cấp',
              pass_desc='Hệ thống tự động kích hoạt chế độ hỗ trợ đặc biệt; thông báo tới Quản lý và Bộ phận Nhân sự.',
              when_fail='Nghiêm cấm từ chối tự động',
              fail_desc='Nghiêm cấm hệ thống tự động từ chối các trường hợp cấp cứu y tế phát sinh đột xuất.'),
            n('EM_TIME', 'Miễn báo trước & Gia hạn nộp chứng từ 48 giờ',
              'Miễn trừ quy định nộp đơn trước ca làm việc. Nhân viên hoặc người nhà có 48 giờ kể từ ngày bắt đầu điều trị để nộp bổ sung chứng từ y tế hợp pháp.',
              clause='Chính sách bảo vệ người lao động',
              doc_req='Giấy nhập viện, Giấy xác nhận cấp cứu hoặc Tóm tắt bệnh án nộp bổ sung trong 48h',
              when_pass='Gia hạn 48 giờ thành công',
              pass_desc='Đơn được giữ ở trạng thái bảo lưu quyền lợi chờ nhân viên hoặc người thân bổ sung chứng từ.',
              when_fail='Chờ bổ sung chứng từ y tế',
              fail_desc='Hết 48 giờ chưa có chứng từ; Chuyên viên Nhân sự liên hệ trực tiếp với nhân viên/người nhà để hỗ trợ.'),
            n('EM_MIN', 'Thẩm định nhận dạng tối thiểu (AI VLM)',
              'Không bắt buộc đủ 100% trường dữ liệu ngay; mô hình thị giác chỉ cần nhận diện tối thiểu Họ tên bệnh nhân và Cơ sở cấp cứu/điều trị.',
              clause='Quy chuẩn trích xuất khẩn cấp',
              kind=VLM,
              when_pass='Nhận diện tối thiểu thành công',
              pass_desc='Đủ điều kiện tiếp nhận ban đầu; bộ phận C&B sẽ hoàn tất hồ sơ đối soát với bệnh viện sau.',
              when_fail='Nhân sự hỗ trợ xác minh thủ công',
              fail_desc='Ảnh chụp cấp cứu bị mờ; chuyển Chuyên viên Nhân sự hỗ trợ liên hệ cơ sở y tế xác thực.'),
        ],
        next_steps='Luôn → Nhân sự (b1) + Trưởng bộ phận (≥ 7 ngày đồng duyệt)')

    br_accident = branch(
        'WORK_ACCIDENT', 'Nghỉ tai nạn lao động', '#ec4899', '⚒️',
        who='Nhân viên bị tai nạn trong giờ làm việc hoặc trên tuyến đường đi làm hợp lý',
        what='Doanh nghiệp chi trả chi phí y tế và tiền lương trong thời gian điều trị theo Luật ATVSLĐ; Quỹ bảo hiểm TNLĐ chi trả trợ cấp.',
        how='Bộ phận Nhân sự & HSE chủ trì thụ lý hồ sơ toàn diện; không áp dụng tự động phê duyệt.',
        steps=[
            n('WA_HR', 'Bộ hồ sơ Tai nạn lao động hợp lệ bắt buộc',
              'Bắt buộc phải có Biên bản điều tra TNLĐ do Hội đồng điều tra TNLĐ công ty/cơ quan có thẩm quyền lập, kèm chứng từ thương tích điều trị.',
              clause='Luật ATVSLĐ & Luật BHXH',
              doc_req='Biên bản điều tra tai nạn lao động + Giấy xác nhận thương tích / Giấy ra viện của bệnh viện',
              when_pass='Hồ sơ đầy đủ, hợp chuẩn',
              pass_desc='Bộ phận Nhân sự & HSE tiếp nhận hồ sơ làm thủ tục bồi thường và trợ cấp theo quy định.',
              when_fail='Thiếu biên bản điều tra',
              fail_desc='Chưa có biên bản điều tra hiện trường; yêu cầu phối hợp ngay với bộ phận An toàn lao động (HSE) để lập biên bản.'),
            n('WA_DUR', 'Quy trình thụ lý chuyên trách & Phân cấp phê duyệt',
              'Không áp dụng phê duyệt tự động; Bộ phận Nhân sự & HSE chủ trì thẩm định toàn diện. Nghỉ < 7 ngày: Trưởng bộ phận + Nhân sự; Nghỉ từ 7 ngày trở lên: Ban Giám đốc phê duyệt.',
              clause='Điều 18 QC-NS & Luật ATVSLĐ',
              when_pass='Đúng luồng thẩm quyền',
              pass_desc='Chuyển cấp thẩm quyền cao nhất để đảm bảo chế độ viện phí, tiền lương và trợ cấp suy giảm lao động.',
              when_fail='Chặn luồng sai thẩm quyền',
              fail_desc='Không cho phép quản lý cấp thấp tự ý kết luận hồ sơ tai nạn lao động.'),
        ],
        next_steps='Bước 1: Nhân sự xác minh hồ sơ | Bước 2: < 7 ngày → Trưởng bộ phận | 7 ngày trở lên → Trưởng bộ phận + Tổng giám đốc')

    br_maternity = branch(
        'MATERNITY', 'Nghỉ thai sản / sinh con', '#f43f5e', '🤰',
        who='Lao động nữ mang thai / sinh con (hoặc lao động nam có vợ sinh con theo Luật BHXH)',
        what='Hưởng trợ cấp 100% mức bình quân lương đóng BHXH do Quỹ thai sản BHXH chi trả; doanh nghiệp không trừ phép năm.',
        how='Nhân sự chủ trì toàn bộ quy trình; kiểm tra giấy chứng sinh, giấy khai sinh hoặc chỉ định dưỡng thai.',
        steps=[
            n('MA_LAW', 'Thời lượng nghỉ thai sản theo luật định',
              'Lao động nữ sinh con được nghỉ trước và sau khi sinh 06 tháng (sinh đôi trở lên, từ con thứ 2 cứ mỗi con được nghỉ thêm 01 tháng). Thời gian nghỉ trước sinh tối đa không quá 02 tháng.',
              clause='Điều 34 Luật BHXH 2024 & Điều 139 BLLĐ',
              when_pass='Đúng thời lượng luật định',
              pass_desc='Hưởng 100% mức bình quân tiền lương đóng BHXH 6 tháng liền kề do Quỹ BHXH chi trả; không trừ phép năm.',
              when_fail='Thời lượng không phù hợp',
              fail_desc='Nếu có nhu cầu đi làm trước khi hết hạn nghỉ thai sản, bắt buộc có giấy xác nhận của bác sĩ và người sử dụng lao động đồng ý.'),
            n('MA_DOC', 'Hồ sơ minh chứng thai sản theo giai đoạn',
              'Nghỉ dưỡng thai: có chỉ định của cơ sở y tế có thẩm quyền; Nghỉ sinh con: Bản sao Giấy khai sinh hoặc Giấy chứng sinh của con; Nghỉ khám thai: tối đa 5 lần (1-2 ngày/lần).',
              clause='Điều 101 Luật BHXH 2024',
              doc_req='Giấy chứng sinh / Bản sao Giấy khai sinh (sau sinh) hoặc Giấy chỉ định nghỉ dưỡng thai / Giấy khám thai',
              when_pass='Đầy đủ hồ sơ hợp lệ',
              pass_desc='Hồ sơ hợp chuẩn; chuyển bộ phận C&B hoàn thiện hồ sơ gửi cơ quan BHXH thanh toán trợ cấp thai sản.',
              when_fail='Hướng dẫn bổ sung hồ sơ',
              fail_desc='Hồ sơ chưa đủ điều kiện thanh toán BHXH; C&B trực tiếp hướng dẫn người lao động hoàn thiện hồ sơ.'),
            n('MA_HO', 'Kế hoạch bàn giao công việc trước kỳ nghỉ dài hạn',
              'Do kỳ nghỉ kéo dài 6 tháng, nhân viên có trách nhiệm lập kế hoạch bàn giao toàn diện các dự án/công việc đang phụ trách trước ngày bắt đầu nghỉ ít nhất 15 ngày.',
              clause='Quy chuẩn bàn giao thai sản',
              when_pass='Kế hoạch bàn giao được nghiệm thu',
              pass_desc='Quản lý trực tiếp nghiệm thu và phân bổ nhân sự kế cận đảm nhiệm các đầu việc.',
              when_fail='Chưa hoàn tất bàn giao',
              fail_desc='Quản lý trực tiếp đôn đốc và phối hợp cùng nhân viên hoàn tất phân giao nhiệm vụ.'),
            n('MA_AUTH', 'Thẩm quyền phê duyệt & Ban hành quyết định',
              'Bộ phận Nhân sự tiếp nhận hồ sơ pháp lý; Ban Giám đốc (CEO/HRD) ban hành quyết định phê duyệt nghỉ thai sản chính thức của doanh nghiệp.',
              clause='Điều 18.3 QC-NS',
              when_pass='Quyết định được phê duyệt',
              pass_desc='Hệ thống cập nhật trạng thái nghỉ thai sản chính thức; tự động tạm dừng tính chấm công thông thường.',
              when_fail='Chặn luồng sai cấp',
              fail_desc='Yêu cầu đầy đủ chữ ký của Ban Giám đốc và xác nhận của Phòng Nhân sự.'),
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
       'title': 'Không cần nghỉ',
       'body': 'Tất cả ngày xin nghỉ là cuối tuần/ngày lễ. Không tạo phép, không trừ quỹ, không chuyển cấp.',
       'route': 'Điều kiện: N = 0 ngày làm việc.'},
      {'id': 'AUTO_APPROVE', 'color': '#10b981',
       'title': 'Duyệt tự động',
       'body': 'Mọi node bắt buộc đều đạt: loại nghỉ hợp lệ, đủ quỹ, đúng hạn, chứng từ hợp lệ và không cần cấp duyệt.',
       'route': 'Ghi nhận ngay; chỉ ANNUAL mới trừ quỹ phép.'},
      {'id': 'ESCALATE', 'color': '#3b82f6',
       'title': 'Chuyển người có thẩm quyền duyệt',
       'body': 'Có lỗi cần người xử lý, ngoại lệ hoặc vượt ngưỡng tự động. Không tự kết luận khi còn điểm cần xác minh.',
       'route': 'Quản lý trực tiếp → Trưởng bộ phận → HR/HRD → CEO, tùy loại nghỉ và số ngày.'},
    ]

    def flatten_nodes(bs):
        return [nd for b in bs for nd in b.get('steps', [])]

    all_nodes = list(common_inputs) + flatten_nodes(branches) + list(common_final)
    vlm_total = sum(1 for x in all_nodes if x['kind'] == VLM)
    policy_total = sum(1 for x in all_nodes if x['kind'] == POLICY)

    # --- Cây dạng cha-con (dành cho vẽ cây thật - tree visual) ---
    def tnode(node_id, label, color='#475569', note='', children=None):
        return {'node_id': node_id, 'label': label, 'color': color,
                'note': note, 'children': children or []}

    branch_nodes = []
    for b in branches:
        leaves = []
        for s in b['steps']:
            c = '#a855f7' if s.get('kind') == VLM else '#64748b'
            leaves.append(tnode(f"{b['branch_id']}__{s['node_id']}", s['label'], c,
                                note='🤖 Máy đọc (VLM)' if s.get('kind') == VLM else s.get('hint','')))
        branch_nodes.append(tnode(b['branch_id'], b['title'], color=b.get('color') or '#475569',
                                  note=b.get('next') or '', children=leaves))

    final_nodes = [tnode(f"FIN__{x['node_id']}", x['label'], '#475569', note=x.get('hint','')) for x in common_final]

    outcome_nodes = [tnode(f"OUT__{o['id']}", o['title'], o['color'], note=o.get('body','')) for o in outcomes]

    tree_visual = tnode('ROOT', 'Tiếp nhận Đơn Nghỉ Phép', '#0f172a',
        children=[
            tnode('TIER_1', 'Bước chung mọi loại nghỉ', '#0ea5e9',
                  children=[tnode(f"T1__{x['node_id']}", x['label'], '#38bdf8', note=x.get('hint','')) for x in common_inputs]),
            tnode('TIER_2', '8 loại hình nghỉ phép (chia nhánh riêng)', '#6366f1',
                  children=branch_nodes),
            tnode('TIER_3', 'Bước chung cuối cùng', '#0ea5e9',
                  children=final_nodes),
            tnode('TIER_OUT', '3 hướng xử lý cuối cùng', '#1e293b',
                  children=outcome_nodes),
        ]
    )

    tree = {
        'version': '4.2.0',
        'layout': 'TIERED_FAN_OUT',
        'common_tier_title': 'Bước chung mọi loại nghỉ',
        'common_inputs': common_inputs,
        'branch_tier_title': '8 loại hình nghỉ phép (mỗi loại đi theo 1 nhánh riêng)',
        'branches': branches,
        'final_tier_title': 'Bước chung cuối cùng trước khi ra quyết định',
        'common_final': common_final,
        'outcomes_title': '3 hướng xử lý cuối cùng',
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
            'final_outcomes': len(outcomes),
        },
        # --- Dữ liệu dành cho vẽ cây thật (dạng cha-con, connector line tự vẽ) ---
        'tree_visual': tree_visual,
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
    from ai_stack import LLM_TARGET_MODEL
    status = get_qwen_engine().get_status()
    pulled = status.get('model_pulled')
    reachable = status.get('ollama_reachable')
    resident = status.get('model_resident')
    vram = status.get('size_vram') or 0
    ready = bool(reachable and pulled)
    if not reachable:
        mode = 'OLLAMA_NOT_RUNNING'
    elif not pulled:
        mode = 'MODEL_NOT_PULLED'
    elif vram <= 0 and not resident:
        mode = 'PULLED_NOT_RESIDENT'
    else:
        mode = 'READY'
    return {
        **status,
        'ready_for_inference': ready,
        'target_model': LLM_TARGET_MODEL,
        'last_error': status.get('error'),
        'mode': mode,
    }

@router.get('/vlm-status')
def get_vlm_status():
    from ai_stack import OLLAMA_BASE, VLM_TARGET_MODEL, has_model, ollama_ps, ollama_tags
    reachable, names, last_err = ollama_tags()
    pulled = has_model(names, VLM_TARGET_MODEL)
    resident = False
    size_vram = 0
    for m in ollama_ps():
        if has_model([m.get('name') or ''], VLM_TARGET_MODEL):
            resident = True
            size_vram = int(m.get('size_vram') or 0)
            break
    if not reachable:
        mode = 'OLLAMA_NOT_RUNNING'
    elif not pulled:
        mode = 'MODEL_NOT_PULLED'
    elif size_vram <= 0:
        mode = 'CPU_OR_NOT_RESIDENT'
    else:
        mode = 'READY'
    return {
        'ollama_reachable': reachable,
        'model_loaded': pulled,
        'model_resident': resident,
        'size_vram': size_vram,
        'target_model': VLM_TARGET_MODEL,
        'base_url': OLLAMA_BASE,
        'fallback_mode': not (reachable and pulled),
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

@router.post('/reset-database')
def reset_database():
    try:
        db.reset_all_data()
        return {'success': True, 'message': 'Đã khôi phục toàn bộ database về trạng thái demo ban đầu.'}
    except Exception as e:
        raise HTTPException(500, f'Lỗi khi reset database: {str(e)}')

@router.get('/server-logs')
def get_server_logs(lines: int = 100):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(current_dir, 'server.log'),
        os.path.join(os.path.dirname(current_dir), 'server.log'),
        '/workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/backend/server.log',
    ]
    log_path = None
    for p in candidates:
        if os.path.exists(p):
            log_path = p
            break
    if not log_path:
        return {'success': True, 'lines': [], 'total_lines': 0, 'message': 'Chưa có file log hoặc server vừa khởi động.'}
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
            return {
                'success': True,
                'total_lines': len(all_lines),
                'returned_lines': len(all_lines[-lines:]),
                'lines': [l.rstrip() for l in all_lines[-lines:]]
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}

@router.get('/cleanup-files')
@router.get('/kill-tmux')
def retired_process_controls():
    raise HTTPException(410,'Điều khiển/xóa tiến trình không thuộc API phê duyệt nghỉ phép.')

