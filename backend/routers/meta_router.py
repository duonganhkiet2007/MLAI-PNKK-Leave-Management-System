"""
meta_router.py
Router cung cấp dữ liệu tham chiếu: Danh sách nhân sự, số dư phép và tài liệu quy chế.
"""

import os
from fastapi import APIRouter, HTTPException
from database import get_all_employees

router = APIRouter(prefix="/api/meta", tags=["Metadata & Policy"])

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(backend_dir)
policy_path = os.path.join(root_dir, "Leave_Application", "policy_rules.md")


import urllib.request
import json

@router.get("/health", summary="Health check endpoint")
def health_check():
    return {"status": "ok", "service": "Leave Approval Backend API", "version": "1.0.0"}


@router.get("/llm-status", summary="Kiểm tra trạng thái thời gian thực của In-Process Qwen 7B")
def get_llm_status():
    try:
        from llm_client import get_qwen_engine
        engine = get_qwen_engine()
        return engine.get_status()
    except Exception as e:
        return {
            "online": False,
            "loading": False,
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "error": str(e),
            "mode": "In-Process (Port 8000)"
        }


@router.get("/debug-llm")
def debug_llm():
    import sys
    import llm_client
    engine = getattr(sys, "_GLOBAL_QWEN_ENGINE", None)
    return {
        "file": getattr(llm_client, "__file__", None),
        "engine_in_sys": engine is not None,
        "is_ready": engine.is_ready if engine else None,
        "is_loading": engine.is_loading if engine else None,
        "load_error": engine.load_error if engine else None,
        "model_loaded": (engine.model is not None) if engine else False
    }


@router.get("/cleanup-files")
def cleanup_files():
    removed = []
    sh_file = os.path.join(root_dir, "LLM-KIET", "run_qwen7b_vllm.sh")
    if os.path.exists(sh_file):
        os.remove(sh_file)
        removed.append("run_qwen7b_vllm.sh")
    return {"removed": removed}


@router.get("/test-custom-verify", summary="Test custom verify logic")

def test_custom_verify_endpoint(reason: str = "nghỉ vì lười biếng không thích làm việc nữa"):
    try:
        from agent_orchestrator import LeaveApprovalAgent
        agent = LeaveApprovalAgent()
        context = {
            "request_id": "TEST-REQ",
            "employee_id": "EMP_JUDGE",
            "employee_name": "Nguyen Van A",
            "department": "Engineering",
            "remaining_leave_days": 10.0,
            "from_date": "2026-09-21",
            "to_date": "2026-09-22"
        }
        input_text = f"Tôi là Nguyen Van A (Engineering), xin nghỉ từ 2026-09-21 đến 2026-09-22. Loại nghỉ: Annual. Lý do: {reason}."
        res = agent.run_full_pipeline(input_text, context)
        return {
            "final_decision": res.final_decision,
            "is_ambiguous": res.parsed_request.is_ambiguous,
            "ambiguity_reason": res.parsed_request.ambiguity_reason,
            "escalation": res.escalation_payload.model_dump() if res.escalation_payload else None
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}







from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class LeaveAllocationInput(BaseModel):
    target_type: str = Field(..., description="ALL, DEPARTMENT, EMPLOYEE")
    target_id: Optional[str] = Field(None, description="Tên phòng ban hoặc mã nhân viên")
    days: float = Field(..., description="Số ngày phép cộng thêm")
    reason: str = Field("Thưởng phép", description="Lý do cấp phát")

@router.get("/employees", summary="Danh sách nhân viên & số dư phép năm")
def list_employees():
    employees = get_all_employees()
    return {"success": True, "total": len(employees), "data": employees}


@router.post("/allocate-leave", summary="Cấp phát / cộng thêm ngày phép (Toàn công ty, Phòng ban hoặc Cá nhân)")
def allocate_leave_endpoint(payload: LeaveAllocationInput):
    from database import allocate_leave_days
    count = allocate_leave_days(payload.target_type, payload.target_id, payload.days, payload.reason)
    return {"success": True, "updated_count": count, "message": f"Đã cấp phát +{payload.days} ngày phép thành công cho {count} nhân sự!"}



@router.get("/policy", summary="Tài liệu quy chế phê duyệt nghỉ phép nội bộ (Ground Truth)")
def get_policy_document():
    if not os.path.exists(policy_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu quy chế policy_rules.md")
    with open(policy_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"success": True, "document_name": "QUY CHẾ PHÊ DUYỆT NGHỈ PHÉP NỘI BỘ", "content_markdown": content}


import subprocess

@router.get("/check-env", summary="Check installed packages")
def check_env():
    import sys
    try:
        import torch
        import transformers
        has_vllm = False
        try:
            import vllm
            has_vllm = True
        except:
            pass
        import time
        t0 = time.time()
        from transformers import AutoTokenizer
        t_tok = time.time() - t0
        return {
            "python": sys.executable,
            "cuda": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "tokenizer_import_time_sec": round(t_tok, 2),
            "cached_hf_models": cached
        }





    except Exception as e:
        return {"error": str(e)}


@router.get("/gpu", summary="Kiểm tra trạng thái GPU NVIDIA")
def get_gpu_status():

    try:
        gpu_info = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader"],
            text=True
        ).strip()
        apps_info = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
            text=True
        ).strip()
        return {
            "success": True,
            "gpu": gpu_info,
            "processes": apps_info
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/kill-tmux", summary="Kill all tmux sessions")
def kill_tmux_sessions():
    try:
        # Check current tmux sessions first
        ls_res = subprocess.run(["tmux", "ls"], capture_output=True, text=True)
        sessions_before = ls_res.stdout.strip() if ls_res.returncode == 0 else (ls_res.stderr.strip() or "No sessions")

        # Kill tmux server
        kill_res = subprocess.run(["tmux", "kill-server"], capture_output=True, text=True)

        # Also kill any orphan vllm if any
        subprocess.run(["pkill", "-f", "vllm.entrypoints"], capture_output=True)

        # Check GPU after killing
        gpu_info = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free", "--format=csv,noheader"],
            text=True
        ).strip()

        # Check processes of user
        ps_res = subprocess.check_output(["ps", "-u", "phongnh", "-o", "pid,cmd"], text=True).splitlines()
        filtered_ps = [l for l in ps_res if "python" in l or "tmux" in l or "vllm" in l]

        return {
            "success": True,
            "sessions_before": sessions_before,
            "gpu_status": gpu_info,
            "active_user_python_procs": filtered_ps,
            "message": "Đã dọn dẹp sạch toàn bộ tmux và tiến trình liên quan!"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


