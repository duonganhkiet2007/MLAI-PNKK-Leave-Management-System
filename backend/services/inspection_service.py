"""
inspection_service.py
Durable SQLite-backed asynchronous proof inspection queue and worker.
Executes Qwen2.5-VL inference outside any open database transaction, eliminates SQLite lock contention,
enforces single-concurrency GPU protection, bounded retries, restart recovery, and auto-resumes
pending leave requests.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import database as db
import storage as st
from metrics import GLOBAL_METRICS
from vlm_inspector import (
    ProofType,
    VLMInspectionOutput,
    _compute_file_sha256,
    _read_vlm_cache,
    _write_vlm_cache,
    inspect_document_with_vlm,
)
from domain import LeaveType, ReasonCategory

logger = logging.getLogger("inspection_service")
VLM_MAX_CONCURRENCY = int(os.getenv("VLM_MAX_CONCURRENCY", "1"))
VLM_JOB_MAX_RETRIES = int(os.getenv("VLM_JOB_MAX_RETRIES", "2"))

_PROOF_TYPE_LEAVE_TYPE = {
    "MEDICAL_LEAVE_CERTIFICATE": "SICK_MEDICAL",
    "MEDICAL_RECORD_SUMMARY": "SICK_MEDICAL",
    "LAB_RESULT": "SICK_MEDICAL",
    "HOSPITAL_DISCHARGE": "SICK_MEDICAL",
    "EMERGENCY_ADMISSION": "MEDICAL_EMERGENCY",
    "SURGERY_NOTICE": "MEDICAL_EMERGENCY",
    "MARRIAGE_CERTIFICATE": "SPECIAL_PAID",
    "WEDDING_INVITATION": "SPECIAL_PAID",
    "DEATH_CERTIFICATE": "SPECIAL_PAID",
    "FUNERAL_DECISION": "SPECIAL_PAID",
    "FAMILY_EVENT_LETTER": "STATUTORY_UNPAID",
    "MATERNITY_CERTIFICATE": "MATERNITY",
    "ACCIDENT_CERTIFICATE": "WORK_ACCIDENT",
    "ACCIDENT_REPORT": "WORK_ACCIDENT",
    "INJURY_CERTIFICATE": "WORK_ACCIDENT",
    "IDENTITY_CARD": "UNPAID_OTHER",
    "VISA_OR_TRAVEL_DOC": "UNPAID_OTHER",
    "OTHER_ADMINISTRATIVE": "UNPAID_OTHER",
}


def _enum_hint(value: Any, enum_type) -> Optional[str]:
    raw = getattr(value, "value", value)
    if raw is None:
        return None
    try:
        return enum_type(str(raw).strip().upper()).value
    except ValueError:
        return None


def _default_leave_type(proof_type: Optional[str]) -> str:
    return _PROOF_TYPE_LEAVE_TYPE.get(str(proof_type or "").strip().upper(), "UNPAID_OTHER")


class ProofInspectionService:
    def __init__(self):
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._orchestrator = None
        self._active_jobs_lock = threading.Lock()

    def set_orchestrator(self, orchestrator) -> None:
        self._orchestrator = orchestrator

    def start_worker(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self.recover_interrupted_jobs()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="ProofInspectionWorker", daemon=True
        )
        self._worker_thread.start()
        logger.info("🚀 [ProofInspectionService] Background worker started.")

    def stop_worker(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
        logger.info("🛑 [ProofInspectionService] Background worker stopped.")

    def recover_interrupted_jobs(self) -> int:
        """Reset jobs left in PROCESSING from a prior crash or restart back to PENDING."""
        recovered = 0
        try:
            with st.transaction() as conn:
                rows = conn.execute(
                    "SELECT id, proof_id, retry_count, max_retries FROM proof_inspection_jobs WHERE status='PROCESSING'"
                ).fetchall()
                for r in rows:
                    if r["retry_count"] >= r["max_retries"]:
                        conn.execute(
                            "UPDATE proof_inspection_jobs SET status='FAILED', error_message='Interrupted job exceeded max retries', completed_at=? WHERE id=?",
                            (st.now_iso(), r["id"]),
                        )
                        conn.execute(
                            "UPDATE proof_documents SET inspection_status='FAILED', vlm_error='Interrupted job exceeded max retries' WHERE id=?",
                            (r["proof_id"],),
                        )
                    else:
                        conn.execute(
                            "UPDATE proof_inspection_jobs SET status='PENDING', retry_count=retry_count+1 WHERE id=?",
                            (r["id"],),
                        )
                        conn.execute(
                            "UPDATE proof_documents SET inspection_status='PENDING' WHERE id=?",
                            (r["proof_id"],),
                        )
                        recovered += 1
            if recovered > 0:
                logger.warning(
                    f"🔄 [ProofInspectionService] Recovered {recovered} interrupted inspection jobs."
                )
        except Exception as e:
            logger.error(f"Error during job recovery: {e}")
        self._recover_stranded_requests()
        return recovered

    def _recover_stranded_requests(self) -> None:
        """Sau khi khởi động lại: đánh thức các đơn còn PROCESSING / PENDING_INSPECTION.
        - Chứng từ đã READY/FAILED (lỡ tín hiệu đánh thức, hoặc job vừa bị đánh FAILED khi phục hồi) → đánh giá lại ngay.
        - Chứng từ chưa xong mà không còn job nào đang chờ → xếp lại job kiểm định."""
        try:
            with st.readonly_connection() as conn:
                rows = conn.execute(
                    """SELECT r.id AS request_id, r.employee_id, r.proof_id, r.facts_json,
                              p.inspection_status, p.proof_type,
                              (SELECT COUNT(*) FROM proof_inspection_jobs j
                               WHERE j.proof_id = r.proof_id AND j.status IN ('PENDING','PROCESSING')) AS active_jobs
                       FROM leave_requests r LEFT JOIN proof_documents p ON p.id = r.proof_id
                       WHERE r.status IN ('PROCESSING','PENDING_INSPECTION')"""
                ).fetchall()
            done_proofs, requeue = set(), {}
            for r in rows:
                if not r["proof_id"] or r["inspection_status"] in ("READY", "FAILED", None):
                    done_proofs.add(r["proof_id"])
                elif not r["active_jobs"]:
                    requeue[r["proof_id"]] = r
            for proof_id, r in requeue.items():
                try:
                    facts = json.loads(r["facts_json"] or "{}")
                except (TypeError, ValueError):
                    facts = {}
                self.enqueue_proof_inspection(proof_id, r["employee_id"], r["proof_type"],
                                              facts.get("leave_type"), facts.get("reason_category"))
            if done_proofs or requeue:
                logger.warning(f"🔄 [ProofInspectionService] Resuming {len(rows)} stranded leave request(s) after restart.")
            for proof_id in done_proofs:
                if proof_id:
                    self.resume_pending_requests_for_proof(proof_id)
        except Exception as e:
            logger.error(f"Error recovering stranded requests: {e}")

    def enqueue_proof_inspection(
        self,
        proof_id: str,
        employee_id: str,
        proof_type_hint: Optional[str] = None,
        leave_type_hint: Optional[str] = None,
        reason_category_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist inspection job and check instant SHA-256 cache.
        Returns proof inspection status dict.
        """
        # 1. Read proof row and storage info
        with st.readonly_connection() as conn:
            p_row = conn.execute("SELECT * FROM proof_documents WHERE id=?", (proof_id,)).fetchone()
            if not p_row:
                raise LookupError(f"Chứng từ {proof_id} không tồn tại.")
            proof_dict = dict(p_row)

        storage_name = proof_dict.get("storage_name") or ""
        uploads_dir = Path(
            os.getenv("LEAVE_UPLOAD_DIR", str(Path(db.DB_PATH).parent / "uploads"))
        )
        file_path = uploads_dir / storage_name

        # 2. Check / compute SHA-256 hash
        file_hash = proof_dict.get("file_sha256")
        if not file_hash and file_path.is_file():
            try:
                file_hash = _compute_file_sha256(str(file_path))
                if file_hash:
                    with st.transaction() as conn:
                        conn.execute(
                            "UPDATE proof_documents SET file_sha256=? WHERE id=?",
                            (file_hash, proof_id),
                        )
            except Exception:
                pass

        # 3. Fast cache check (<1ms)
        leave_type_str = (
            _enum_hint(leave_type_hint, LeaveType)
            or _default_leave_type(proof_dict.get("proof_type") or proof_type_hint)
        )
        reason_category_str = _enum_hint(reason_category_hint, ReasonCategory) or ""
        cached_result = None
        if file_hash:
            if _read_vlm_cache(file_hash, leave_type_str, reason_category_str) and file_path.is_file():
                # Bản lưu sẵn là bản đọc thô của VLM inspector (không mang nhãn "đọc thật"); ghi thẳng bản thô thì lúc
                # xét đơn nó bị coi như dữ liệu giả lập và các trường VLM không đọc được bị điền bằng dữ liệu của đơn.
                # Dựng kết quả qua đúng hàm worker dùng: inspector tự lấy bản lưu sẵn (không gọi GPU), cùng định dạng.
                vlm_out = self._inspect_file(str(file_path), leave_type_str, reason_category_str or None)
                cached_result = None if vlm_out.vlm_error else vlm_out.vlm_analysis_json
            if not cached_result:
                # Also check if another proof row in DB with identical sha256 is READY
                with st.readonly_connection() as conn:
                    matches = conn.execute(
                        "SELECT proof_type, vlm_analysis_json FROM proof_documents WHERE file_sha256=? AND inspection_status='READY' AND id!=? AND vlm_analysis_json IS NOT NULL",
                        (file_hash, proof_id),
                    ).fetchall()
                    for matched in matches:
                        try:
                            candidate = json.loads(matched["vlm_analysis_json"])
                            if "proof_extra" in candidate and "document_summary" not in candidate:
                                continue  # bản lưu sẵn thô từng bị ghi thẳng vào DB (thiếu nhãn đọc thật): không tái sử dụng
                            context = candidate.get("_inspection_context") or {}
                            context_matches = (
                                context.get("leave_type") == leave_type_str
                                and (context.get("reason_category") or "") == reason_category_str
                            )
                            legacy_context_matches = (
                                not context
                                and not reason_category_str
                                and _default_leave_type(matched["proof_type"]) == leave_type_str
                            )
                            if context_matches or legacy_context_matches:
                                cached_result = candidate
                                break
                        except Exception:
                            continue

        if cached_result:
            GLOBAL_METRICS.record_vlm_call(is_cache_hit=True)
            self._apply_inspection_success(proof_id, cached_result, from_cache=True)
            return {
                "proof_id": proof_id,
                "inspection_status": "READY",
                "cached": True,
            }

        # 4. Deduplicate active jobs for this proof_id
        with st.transaction() as conn:
            existing_active = conn.execute(
                "SELECT id, status FROM proof_inspection_jobs WHERE proof_id=? AND status IN ('PENDING', 'PROCESSING')",
                (proof_id,),
            ).fetchone()
            if existing_active:
                self._wake_event.set()
                return {
                    "proof_id": proof_id,
                    "job_id": existing_active["id"],
                    "inspection_status": existing_active["status"],
                    "deduplicated": True,
                }

            # Enqueue new job atomically
            job_id = f"JOB-{uuid.uuid4().hex[:12].upper()}"
            curr_ver = int(proof_dict.get("inspection_version") or 1)
            conn.execute(
                """INSERT INTO proof_inspection_jobs(
                       id, proof_id, employee_id, status, version, retry_count, max_retries,
                       created_at, leave_type_hint, reason_category_hint
                   ) VALUES(?,?,?,?,?,0,?,?,?,?)""",
                (
                    job_id, proof_id, employee_id, "PENDING", curr_ver,
                    VLM_JOB_MAX_RETRIES, st.now_iso(), leave_type_str, reason_category_str or None,
                ),
            )
            conn.execute(
                "UPDATE proof_documents SET inspection_status='PENDING' WHERE id=?",
                (proof_id,),
            )

        self._wake_event.set()
        return {
            "proof_id": proof_id,
            "job_id": job_id,
            "inspection_status": "PENDING",
        }

    def _worker_loop(self) -> None:
        """Main loop of the background queue worker."""
        while not self._stop_event.is_set():
            job = self._claim_next_job()
            if not job:
                self._wake_event.wait(timeout=1.0)
                self._wake_event.clear()
                continue

            self._process_single_job(job)

    def _claim_next_job(self) -> Optional[Dict[str, Any]]:
        """Atomically claim a single PENDING job in a short write transaction (~1ms)."""
        try:
            with st.transaction() as conn:
                row = conn.execute(
                    """SELECT j.*, p.storage_name, p.original_name, p.mime_type, p.proof_type, p.inspection_version
                       FROM proof_inspection_jobs j
                       JOIN proof_documents p ON j.proof_id = p.id
                       WHERE j.status='PENDING'
                       ORDER BY j.created_at ASC LIMIT 1"""
                ).fetchone()
                if not row:
                    return None
                job = dict(row)
                conn.execute(
                    "UPDATE proof_inspection_jobs SET status='PROCESSING', started_at=? WHERE id=? AND status='PENDING'",
                    (st.now_iso(), job["id"]),
                )
                conn.execute(
                    "UPDATE proof_documents SET inspection_status='PROCESSING' WHERE id=?",
                    (job["proof_id"],),
                )
                return job
        except Exception as e:
            logger.error(f"Error claiming job: {e}")
            return None

    @staticmethod
    def _inspect_file(file_path: str, leave_type: str, reason_category: Optional[str]) -> VLMInspectionOutput:
        """Đọc chứng từ qua VLM inspector. Dùng chung cho worker và nhánh có bản lưu sẵn để hai đường cho cùng
        một kết quả (inspector tự lấy bản lưu sẵn nếu có và gắn nhãn VLM_CACHE_HIT)."""
        vlm_out: VLMInspectionOutput = inspect_document_with_vlm(
            leave_type=leave_type,
            employee_name=None,
            reason="",
            attachment_path_or_type=file_path,
            allow_mock_fallback=False,
            reason_category=reason_category,
        )
        vlm_out.vlm_analysis_json["_inspection_context"] = {
            "leave_type": leave_type,
            "reason_category": reason_category,
        }
        return vlm_out

    def _process_single_job(self, job: Dict[str, Any]) -> None:
        """Runs the expensive VLM inference outside any database transaction."""
        proof_id = job["proof_id"]
        job_id = job["id"]
        storage_name = job.get("storage_name") or ""
        uploads_dir = Path(
            os.getenv("LEAVE_UPLOAD_DIR", str(Path(db.DB_PATH).parent / "uploads"))
        )
        file_path = str(uploads_dir / storage_name)
        leave_type = (
            _enum_hint(job.get("leave_type_hint"), LeaveType)
            or _default_leave_type(job.get("proof_type"))
        )
        reason_category = _enum_hint(job.get("reason_category_hint"), ReasonCategory)

        # A leave request may have been linked after upload but before this job starts.
        with st.readonly_connection() as conn:
            linked_request = conn.execute(
                """SELECT facts_json FROM leave_requests
                   WHERE proof_id=? AND status IN ('PROCESSING', 'PENDING_INSPECTION')
                   ORDER BY submitted_at DESC LIMIT 1""",
                (proof_id,),
            ).fetchone()
        if linked_request and linked_request["facts_json"]:
            try:
                facts = json.loads(linked_request["facts_json"])
                leave_type = _enum_hint(facts.get("leave_type"), LeaveType) or leave_type
                reason_category = _enum_hint(facts.get("reason_category"), ReasonCategory) or reason_category
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        t0 = time.perf_counter()
        GLOBAL_METRICS.record_vlm_call(is_cache_hit=False)

        try:
            # 1. Inspect outside DB transaction
            vlm_out = self._inspect_file(file_path, leave_type, reason_category)
            vlm_sec = time.perf_counter() - t0
            GLOBAL_METRICS.record_vlm_duration(vlm_sec)

            vlm_dict = vlm_out.vlm_analysis_json
            if vlm_out.vlm_error:
                # Handled VLM failure (timeout, network, unreadable)
                self._apply_inspection_failure(
                    job, vlm_out.vlm_error, vlm_dict=vlm_dict
                )
            else:
                self._apply_inspection_success(proof_id, vlm_dict, job_id=job_id, job_version=job["version"])

        except Exception as exc:
            vlm_sec = time.perf_counter() - t0
            GLOBAL_METRICS.record_vlm_duration(vlm_sec)
            err_type = type(exc).__name__
            logger.warning(f"VLM inspection exception for job {job_id}: {err_type}")
            self._apply_inspection_failure(job, err_type)

    def _apply_inspection_success(
        self,
        proof_id: str,
        vlm_data: Dict[str, Any],
        from_cache: bool = False,
        job_id: Optional[str] = None,
        job_version: Optional[int] = None,
    ) -> None:
        """Persist inspection results in a short atomic write transaction and auto-resume pending requests."""
        now_str = st.now_iso()
        doc_sum = vlm_data.get("document_summary") or {}
        flags = vlm_data.get("flags") or {}
        readability = flags.get("document_readability") or "UNKNOWN"
        p_name = doc_sum.get("patient_name")
        diag = doc_sum.get("diagnosis")
        issuer = doc_sum.get("issuer")
        issue_d = doc_sum.get("issue_date")
        drange = doc_sum.get("doctor_recommended_range") or {}
        rec_from = drange.get("from")
        rec_to = drange.get("to")
        sig = flags.get("has_doctor_signature")
        if sig is None:
            sig = flags.get("signature_present_on_scan")
        dig_sig = flags.get("digital_signature_present")

        with st.transaction() as conn:
            # Check version to prevent stale overwrite
            current = conn.execute(
                "SELECT inspection_version FROM proof_documents WHERE id=?",
                (proof_id,),
            ).fetchone()
            if current and job_version is not None and current["inspection_version"] != job_version:
                logger.warning(
                    f"Stale worker tried to overwrite proof {proof_id} (version {job_version} vs current {current['inspection_version']}). Skipping."
                )
                # Khép job cũ lại, không để treo ở PROCESSING
                if job_id:
                    conn.execute(
                        "UPDATE proof_inspection_jobs SET status='SUPERSEDED', completed_at=?, error_message=? WHERE id=?",
                        (now_str, f"Superseded by proof version {current['inspection_version']}", job_id),
                    )
                return

            # Ghi thêm dữ liệu VLM đọc được (ngày mất/tang lễ, ngày tai nạn, quan hệ...) vào hồ sơ chứng từ
            # để màn hình và HR đọc lại vẫn thấy, không chỉ nằm trong vlm_analysis_json.
            facts_row = conn.execute(
                "SELECT facts_json FROM proof_documents WHERE id=?", (proof_id,)
            ).fetchone()
            try:
                facts = json.loads(facts_row["facts_json"]) if facts_row and facts_row["facts_json"] else {}
            except (TypeError, ValueError):
                facts = {}
            for key, value in (
                ("patient_name", p_name),
                ("issuer", issuer),
                ("issue_date", issue_d),
                ("recommended_from_date", rec_from),
                ("recommended_to_date", rec_to),
                ("days_granted_by_doctor", doc_sum.get("days_granted_by_doctor")),
                ("deceased_name", doc_sum.get("deceased_name")),
                ("subject_name", doc_sum.get("subject_name")),
                ("date_of_death", doc_sum.get("date_of_death")),
                ("funeral_date", doc_sum.get("funeral_date")),
                ("injury_date", doc_sum.get("injury_date")),
                ("event_date", doc_sum.get("event_date")),
                ("relationship_label", doc_sum.get("relationship_label")),
                ("relationship_to_employee", doc_sum.get("relationship_to_employee")),
            ):
                if value not in (None, "") and not facts.get(key):
                    facts[key] = value

            conn.execute(
                """UPDATE proof_documents SET
                   inspection_status='READY',
                   vlm_analysis_json=?,
                   vlm_error=NULL,
                   inspected_at=?,
                   document_readability=?,
                   patient_name=COALESCE(?, patient_name),
                   issuer=COALESCE(?, issuer),
                   issue_date=COALESCE(?, issue_date),
                   recommended_from_date=COALESCE(?, recommended_from_date),
                   recommended_to_date=COALESCE(?, recommended_to_date),
                   signature_present=COALESCE(?, signature_present),
                   digital_signature_present=COALESCE(?, digital_signature_present),
                   facts_json=?
                   WHERE id=?""",
                (
                    json.dumps(vlm_data, ensure_ascii=False),
                    now_str,
                    readability,
                    p_name,
                    issuer,
                    issue_d,
                    rec_from,
                    rec_to,
                    1 if sig is True else (0 if sig is False else None),
                    1 if dig_sig is True else (0 if dig_sig is False else None),
                    json.dumps(facts, ensure_ascii=False),
                    proof_id,
                ),
            )
            if job_id:
                conn.execute(
                    "UPDATE proof_inspection_jobs SET status='COMPLETED', completed_at=? WHERE id=?",
                    (now_str, job_id),
                )

        # Write to cache if hash present
        file_hash = vlm_data.get("_file_hash")
        if file_hash:
            context = vlm_data.get("_inspection_context") or {}
            _write_vlm_cache(
                file_hash,
                context.get("leave_type", ""),
                vlm_data,
                context.get("reason_category", "") or "",
            )

        # Auto-resume any pending leave requests waiting for this proof
        self.resume_pending_requests_for_proof(proof_id)

    def _apply_inspection_failure(
        self,
        job: Dict[str, Any],
        error_msg: str,
        vlm_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Handle failure with bounded retries."""
        proof_id = job["proof_id"]
        job_id = job["id"]
        retry_count = int(job.get("retry_count") or 0)
        max_retries = int(job.get("max_retries") or VLM_JOB_MAX_RETRIES)
        now_str = st.now_iso()
        job_version = job.get("version")

        # Job cũ (version khác) hoặc chứng từ đã READY (vd nhờ cache): bỏ job lỗi, không ghi đè trạng thái mới.
        with st.transaction() as conn:
            current = conn.execute(
                "SELECT inspection_version, inspection_status FROM proof_documents WHERE id=?", (proof_id,)
            ).fetchone()
            stale = bool(current) and (
                (job_version is not None and current["inspection_version"] != job_version)
                or current["inspection_status"] == "READY"
            )
            if stale:
                conn.execute(
                    "UPDATE proof_inspection_jobs SET status='SUPERSEDED', completed_at=?, error_message=? WHERE id=?",
                    (now_str, f"Discarded stale failure: {error_msg}", job_id),
                )
        if stale:
            logger.warning(f"Discarded stale failure of job {job_id} for proof {proof_id}.")
            return

        if retry_count < max_retries:
            # Requeue for retry
            with st.transaction() as conn:
                conn.execute(
                    "UPDATE proof_inspection_jobs SET status='PENDING', retry_count=retry_count+1, error_message=? WHERE id=?",
                    (error_msg, job_id),
                )
                conn.execute(
                    "UPDATE proof_documents SET inspection_status='PENDING', vlm_error=? WHERE id=? AND inspection_version=? AND inspection_status!='READY'",
                    (error_msg, proof_id, job_version),
                )
            logger.info(f"Requeued job {job_id} for retry ({retry_count + 1}/{max_retries}).")
            return

        # Final failure
        with st.transaction() as conn:
            conn.execute(
                "UPDATE proof_inspection_jobs SET status='FAILED', completed_at=?, error_message=? WHERE id=?",
                (now_str, error_msg, job_id),
            )
            conn.execute(
                """UPDATE proof_documents SET
                   inspection_status='FAILED',
                   vlm_error=?,
                   inspected_at=?,
                   vlm_analysis_json=?
                   WHERE id=? AND inspection_version=? AND inspection_status!='READY'""",
                (
                    error_msg,
                    now_str,
                    json.dumps(vlm_dict, ensure_ascii=False) if vlm_dict else None,
                    proof_id,
                    job_version,
                ),
            )

        logger.warning(f"Proof inspection FAILED for {proof_id}: {error_msg}")
        # Auto-resume waiting leave requests using failure fallback
        self.resume_pending_requests_for_proof(proof_id)

    def resume_pending_requests_for_proof(self, proof_id: str) -> None:
        """Finds any leave requests waiting for this proof and evaluates them."""
        with st.readonly_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM leave_requests WHERE proof_id=? AND status IN ('PROCESSING', 'PENDING_INSPECTION')",
                (proof_id,),
            ).fetchall()
            req_ids = [r["id"] for r in rows]

        if not req_ids:
            return

        logger.info(f"Auto-resuming {len(req_ids)} pending leave request(s) for proof {proof_id}...")
        orchestrator = self._orchestrator
        if not orchestrator:
            from services.orchestration import LeaveOrchestratorService
            orchestrator = LeaveOrchestratorService()

        for rid in req_ids:
            try:
                orchestrator.resume_pending_request(rid)
            except Exception as e:
                logger.error(f"Error resuming request {rid}: {e}")


# Singleton instance
GLOBAL_INSPECTION_SERVICE = ProofInspectionService()
