# Architecture and Workflow

Tài liệu này mô tả đường chạy hiện tại, không dùng kiến trúc in-process 7B trong các docs legacy. Hai model đều được gọi qua Ollama; FastAPI vẫn phục vụ API/SPA trên port 8000.

## A. Overall workflow

```mermaid
flowchart TD
    E[Employee] --> I{Input mode}
    I -->|Structured form| F[RequestFacts validation]
    I -->|Free text| L[LLM parser<br/>qwen2.5:3b-instruct]
    L --> F
    F --> C[Load trusted context<br/>identity, balance, roles, overlap,<br/>quota, handover, proof status]
    C --> P{Attachment / proof present?}
    P -->|Yes| V[VLM fact extraction<br/>qwen2.5vl:7b]
    P -->|No| R[Deterministic Rule Engine]
    V --> U[Merge extracted facts as UNVERIFIED<br/>unless HR already verified]
    U --> R
    R --> D{Decision}
    D -->|AUTO_APPROVE| A[Atomic booking and annual debit if ANNUAL]
    D -->|NO_LEAVE_REQUIRED| N[Complete without booking/debit]
    D -->|AUTO_REJECT| X[Reject and audit]
    D -->|NEED_CORRECTION| CE[Employee corrects/resubmits]
    D -->|ESCALATE| Q[Persist target role,<br/>actionable question and approval steps]
    Q --> H[Authorized human / HR action]
    H --> RE[Reload trusted context and re-evaluate]
    CE --> RE
    RE --> R
```

Structured data đi thẳng vào schema; chỉ free text mới cần LLM parser. Backend không nhận identity, balance, authority hay proof verification từ model. Nếu có file, VLM trích facts trước khi rule engine chạy, nhưng proof vẫn chưa được tin cậy cho đến khi HR xác minh. Rule engine tạo một trong năm decision. Correction quay lại employee; escalation tạo bước human; mọi modification/approval hợp lệ đều dẫn tới re-evaluation trước commit.

## B. Component Architecture

```mermaid
flowchart LR
    subgraph Client
        FE[Static SPA<br/>Vietnamese staff/manager UI]
        APIClient[External API client]
    end

    subgraph FastAPI
        LR[leave_router]
        VR[verify_router]
        MR[meta_router]
        ORCH[LeaveOrchestratorService]
    end

    subgraph AI[Ollama service]
        LLM[LLM<br/>qwen2.5:3b-instruct]
        VLM[VLM<br/>qwen2.5vl:7b]
    end

    subgraph Deterministic
        RE[LeaveRuleEngine]
        CAL[CalendarService<br/>2026/2027 JSON]
    end

    subgraph State
        DB[(SQLite)]
        FS[(Local uploads)]
    end

    HUMAN[Employee / Manager /<br/>Department Head / HR / HRD / CEO]

    FE -->|HTTP + X-Actor-ID| LR
    FE --> MR
    FE --> VR
    APIClient --> LR
    LR --> ORCH
    ORCH -->|free-text facts / free-text action| LLM
    ORCH -->|image bytes/path| VLM
    ORCH -->|trusted LeaveRequest| RE
    RE -->|working dates / notice| CAL
    ORCH <-->|transactions, context,<br/>workflow, audit| DB
    LR -->|upload/read proof| FS
    DB -->|proof metadata/path| ORCH
    FS -->|proof file| VLM
    VR -->|isolated cases| RE
    MR -->|policy/options/calendar/status| FE
    HUMAN --> FE
    ORCH -->|decision, target, question| HUMAN
```

Frontend gọi ba router FastAPI. `leave_router` dùng orchestrator cho request lifecycle; `verify_router` gọi rule engine trực tiếp và không persist; `meta_router` cung cấp policy, calendar và AI status. Orchestrator là điểm ghép AI với trusted DB context. Rule engine chỉ nhận typed `LeaveRequest` và dùng CalendarService. SQLite lưu state/ledger/audit; file chứng từ nằm ở local uploads. Human tương tác qua UI/API, còn role luôn được lookup từ DB.

## C. Escalation flow

```mermaid
flowchart TD
    R[Rule Engine result] --> K{Result kind}
    K -->|Correctable facts| NC[NEED_CORRECTION<br/>UNCERTAIN_FACTS → EMPLOYEE]
    K -->|Operational/policy condition| OP[ESCALATE<br/>OUT_OF_POLICY]
    K -->|Authority threshold| AU[ESCALATE<br/>AUTHORITY_ESCALATION]
    K -->|Proof/legal/unsupported| HR[ESCALATE → HR]
    OP --> T[Resolve deterministic target role]
    AU --> T
    HR --> T
    T --> Q[Build deterministic actionable question<br/>and quick-action options]
    Q --> S[Persist PENDING_ESCALATION<br/>and approval_steps]
    S --> H{Human action}
    H -->|REQUEST_MORE_INFO| W[WAITING_EMPLOYEE]
    H -->|REJECT| X[REJECTED]
    H -->|MODIFY_CONDITIONAL| M[Update only editable fields<br/>new revision]
    H -->|APPROVE_OVERRIDE| G[Grant current role;<br/>waive notice/quota only]
    W --> RS[Employee resubmit]
    M --> RE[Re-evaluate]
    G --> RE
    RS --> RE
    RE --> R
```

Question và routing được tạo từ result của engine, không cần LLM. `NEED_CORRECTION` về employee; `ESCALATE` đi tới role xác định. Button action được xử lý trực tiếp, còn free-text action chỉ dùng LLM để map vào whitelist. Conditional modification chỉ sửa ngày hoặc người bàn giao. Approval chỉ waive notice/quota, rồi engine tải lại balance, overlap, proof và context trước khi quyết định bước tiếp.

## D1. Sequence: Structured Form không proof

```mermaid
sequenceDiagram
    actor E as Employee
    participant FE as Frontend
    participant API as FastAPI leave_router
    participant O as Orchestrator
    participant DB as SQLite
    participant R as Rule Engine
    participant C as Calendar

    E->>FE: Submit structured form
    FE->>API: POST /api/leave/request + X-Actor-ID
    API->>O: process_new_request(structured_data)
    O->>DB: Validate actor and load trusted context
    O->>R: evaluate(LeaveRequest)
    R->>C: working_dates / notice_days
    C-->>R: classified dates
    R-->>O: ApprovalResult
    alt AUTO_APPROVE
        O->>DB: Atomic booking + annual debit if ANNUAL
    else other decision
        O->>DB: Save state/steps/audit
    end
    O-->>API: Serialized request
    API-->>FE: Decision and explanation
```

Đường này có 0 LLM và 0 VLM call theo code/tests. Actor được xác thực ở mức demo và context lấy từ DB. Rule engine tính calendar, kiểm policy và trả structured result. Chỉ `AUTO_APPROVE` mới gọi commit; chỉ `ANNUAL` bị debit. Persistence và balance mutation nằm trong transaction `BEGIN IMMEDIATE`.

## D2. Sequence: Form có proof bắt buộc (medical/special-paid)

```mermaid
sequenceDiagram
    actor E as Employee
    participant API as FastAPI
    participant FS as Upload storage
    participant DB as SQLite
    participant O as Orchestrator
    participant V as VLM
    participant R as Rule Engine
    actor HR as HR reviewer

    E->>API: POST /api/leave/proofs (PDF/JPEG/PNG)
    API->>FS: Store file
    API->>DB: Store UNVERIFIED proof record
    E->>API: POST medical/special-paid request with proof_id
    API->>O: Evaluate request
    O->>DB: Load proof + trusted context
    O->>FS: Resolve file path
    O->>V: Extract proof facts (1 call)
    V-->>O: ProofExtraction + diagnostic signals
    O->>R: Evaluate with status still UNVERIFIED
    R-->>O: ESCALATE / HR / PROOF_REVIEW_REQUIRED
    O->>DB: Persist result and VLM fields
    HR->>API: POST /proofs/{id}/verify
    API->>DB: Save HR verification facts/status
    API->>O: Re-evaluate linked request
    O->>V: Inspect proof again for this evaluation
    V-->>O: Diagnostic/extracted output; HR verification remains authoritative
    O->>R: Evaluate with VERIFIED proof
    R-->>O: Policy/authority result
    O->>DB: Persist/commit as applicable
```

Upload được kiểm size và magic MIME. VLM chạy một lần trong mỗi lần `_evaluate` có proof/attachment; vì vậy một lifecycle gồm initial evaluation và các re-evaluation có thể có nhiều VLM calls. Output không tự biến thành verified proof. Với loại medical/special-paid cần proof, rule engine chuyển HR nếu proof chưa verified. HR ghi facts và verification status qua endpoint riêng, sau đó linked request được tăng revision và đánh giá lại; trạng thái HR đã ghi vẫn là authoritative. Proof gắn vào loại nghỉ khác vẫn có thể kích hoạt VLM, nhưng không tự tạo yêu cầu HR nếu rule của loại đó không dùng proof. VLM không xác nhận authenticity với issuer bên ngoài.

## D3. Sequence: Free text request

```mermaid
sequenceDiagram
    actor E as Employee
    participant API as FastAPI
    participant O as Orchestrator
    participant L as LLM parser
    participant DB as SQLite
    participant R as Rule Engine

    E->>API: POST request {raw_text}
    API->>O: process_new_request(raw_text)
    O->>DB: Validate actor exists before model call
    O->>L: Parse text to ParsedLeaveRequest (1 call)
    L-->>O: Dates/type/reason/handover/date_ambiguous
    O->>O: Force proof_id=null, attachment_type=none
    O->>DB: Load trusted context
    O->>R: Deterministic evaluate
    R-->>O: ApprovalResult
    O->>DB: Persist/commit/audit
    O-->>API: Serialized request
```

Free text dùng đúng một LLM call cho extraction. Pydantic `extra='forbid'` ngăn model thêm identity, balance, authority, decision hoặc proof verification. Backend chủ động xóa proof fields sau parse, nên free-text path hiện không thể nộp proof trong cùng request. Nếu model không sẵn sàng, API trả `MODEL_UNAVAILABLE`; không có heuristic parser fallback.

## D4. Sequence: Human approval flow

```mermaid
sequenceDiagram
    actor H as Authorized human
    participant API as FastAPI
    participant O as Orchestrator
    participant L as LLM action parser
    participant DB as SQLite
    participant R as Rule Engine

    H->>API: POST /{request_id}/human-decision
    API->>O: action_type button or feedback_text
    O->>DB: Read request, require target role, capture revision token
    alt Button action supplied
        O->>O: Map action deterministically (0 LLM)
    else Free-text feedback
        O->>L: Extract whitelisted action (1 LLM call)
        L-->>O: HumanFeedbackResolution
    end
    O->>DB: Lock transaction, recheck revision and role
    alt REQUEST_MORE_INFO
        O->>DB: WAITING_EMPLOYEE
    else REJECT
        O->>DB: REJECTED
    else MODIFY_CONDITIONAL
        O->>DB: Update editable fields, increment revision
        O->>R: Re-evaluate
        R-->>O: New result/route
    else APPROVE_OVERRIDE
        O->>DB: Load granted steps; audit approval
        O->>R: Re-evaluate fresh context; waive notice/quota only
        R-->>O: Complete or route next role
        O->>DB: Mark current step and commit if final
    end
    O-->>API: Current serialized state
```

Workflow dùng optimistic revision token kết hợp transaction lock để phát hiện thay đổi đồng thời. Người nộp không thể tự duyệt; role và department scope lấy từ DB. HR proof/legal/unsupported cases không thể bị `APPROVE_OVERRIDE` bỏ qua. Multi-step unpaid tiếp tục qua các role còn lại. Final approval vẫn kiểm balance, overlap và proof trước khi tạo ledger/booking.
