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

logger = logging.getLogger("inspection_service")
VLM_MAX_CONCURRENCY = int(os.getenv("VLM_MAX_CONCURRENCY", "1"))
VLM_JOB_MAX_RETRIES = int(os.getenv("VLM_JOB_MAX_RETRIES", "2"))


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
        return recovered

    def enqueue_proof_inspection(
        self,
        proof_id: str,
        employee_id: str,
        proof_type_hint: Optional[str] = None,
        leave_type_hint: Optional[str] = None,
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
        leave_type_str = leave_type_hint or ""
        cached_result = None
        if file_hash:
            cached_result = _read_vlm_cache(file_hash, leave_type_str)
            if not cached_result:
                # Also check if another proof row in DB with identical sha256 is READY
                with st.readonly_connection() as conn:
                    matched = conn.execute(
                        "SELECT vlm_analysis_json FROM proof_documents WHERE file_sha256=? AND inspection_status='READY' AND id!=? AND vlm_analysis_json IS NOT NULL LIMIT 1",
                        (file_hash, proof_id),
                    ).fetchone()
                    if matched and matched["vlm_analysis_json"]:
                        try:
                            cached_result = json.loads(matched["vlm_analysis_json"])
                        except Exception:
                            pass

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
                """INSERT INTO proof_inspection_jobs(id, proof_id, employee_id, status, version, retry_count, max_retries, created_at)
                   VALUES(?,?,?,?,?,0,?,?)""",
                (job_id, proof_id, employee_id, "PENDING", curr_ver, VLM_JOB_MAX_RETRIES, st.now_iso()),
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

    def _process_single_job(self, job: Dict[str, Any]) -> None:
        """Runs the expensive VLM inference outside any database transaction."""
        proof_id = job["proof_id"]
        job_id = job["id"]
        storage_name = job.get("storage_name") or ""
        uploads_dir = Path(
            os.getenv("LEAVE_UPLOAD_DIR", str(Path(db.DB_PATH).parent / "uploads"))
        )
        file_path = str(uploads_dir / storage_name)

        t0 = time.perf_counter()
        GLOBAL_METRICS.record_vlm_call(is_cache_hit=False)

        try:
            # 1. Inspect outside DB transaction
            vlm_out: VLMInspectionOutput = inspect_document_with_vlm(
                leave_type="SICK_MEDICAL",
                employee_name=None,
                reason="",
                attachment_path_or_type=file_path,
                allow_mock_fallback=False,
            )
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
            err_msg = f"{type(exc).__name__}: {exc}"
            logger.warning(f"VLM inspection exception for job {job_id}: {err_msg}")
            self._apply_inspection_failure(job, err_msg)

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
        sig = flags.get("has_doctor_signature") or flags.get("signature_present_on_scan")
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
                return

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
                   digital_signature_present=COALESCE(?, digital_signature_present)
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
            _write_vlm_cache(file_hash, "SICK_MEDICAL", vlm_data)

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

        if retry_count < max_retries:
            # Requeue for retry
            with st.transaction() as conn:
                conn.execute(
                    "UPDATE proof_inspection_jobs SET status='PENDING', retry_count=retry_count+1, error_message=? WHERE id=?",
                    (error_msg, job_id),
                )
                conn.execute(
                    "UPDATE proof_documents SET inspection_status='PENDING', vlm_error=? WHERE id=?",
                    (error_msg, proof_id),
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
                   WHERE id=?""",
                (
                    error_msg,
                    now_str,
                    json.dumps(vlm_dict, ensure_ascii=False) if vlm_dict else None,
                    proof_id,
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
