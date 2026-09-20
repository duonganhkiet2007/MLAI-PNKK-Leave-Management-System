"""
llm_client.py
In-Process Local LLM Qwen 2.5 7B Engine.
Chạy trực tiếp trong tiến trình Backend trên DUY NHẤT 1 PORT 8000.
Không cần mở port phụ (8001, 8080), không cần server vLLM riêng, không cần tmux.
"""

import os
import re
import json
import threading
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel

_engine_instance = None
_engine_lock = threading.Lock()


class LocalQwenEngine:
    """Singleton quản lý model Qwen 2.5 7B chạy trực tiếp trong GPU RAM."""
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        self.model = None
        self.tokenizer = None
        self.is_loading = False
        self.is_ready = False
        self.load_error = None
        self._lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "online": self.is_ready,
                "loading": self.is_loading,
                "model": self.model_name,
                "error": self.load_error,
                "mode": "In-Process (Port 8000)"
            }

    def load_model(self):
        """Tải model vào GPU trong background thread để không chặn web server."""
        with self._lock:
            if self.is_ready or self.is_loading:
                return
            self.is_loading = True
            self.load_error = None

        def _do_load():
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer
                print(f"🚀 [In-Process LLM] Đang nạp {self.model_name} vào GPU RTX 4090...")
                tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
                    device_map="auto",
                    trust_remote_code=True
                )
                model.eval()
                with self._lock:
                    self.tokenizer = tokenizer
                    self.model = model
                    self.is_ready = True
                    self.is_loading = False
                print(f"✅ [In-Process LLM] {self.model_name} đã sẵn sàng trong GPU RAM!")
            except Exception as e:
                with self._lock:
                    self.load_error = str(e)
                    self.is_loading = False
                    self.is_ready = False
                print(f"❌ [In-Process LLM] Lỗi nạp model: {e}")

        t = threading.Thread(target=_do_load, daemon=True)
        t.start()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Optional[Type[BaseModel]] = None
    ) -> Dict[str, Any]:
        """Suy luận trực tiếp bằng model trong RAM GPU và trích xuất JSON chuẩn."""
        if not self.is_ready:
            if not self.is_loading:
                self.load_model()
            # Chờ tối đa 60 giây nếu model đang trong quá trình nạp
            import time
            wait_start = time.time()
            while not self.is_ready and (time.time() - wait_start < 60):
                time.sleep(1.0)
            if not self.is_ready:
                err_msg = self.load_error or "Hết thời gian chờ nạp model"
                raise RuntimeError(f"Model Qwen 2.5 7B chưa sẵn sàng: {err_msg}")


        import torch
        enhanced_system = (
            system_prompt +
            "\n\nQUAN TRỌNG: Chỉ trả về duy nhất 1 JSON object hợp lệ. "
            "Tuyệt đối không giải thích thêm, không thêm bất kỳ văn bản nào ngoài JSON."
        )

        messages = [
            {"role": "system", "content": enhanced_system},
            {"role": "user", "content": user_prompt}
        ]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                temperature=None,
                top_p=None
            )

        generated_ids = outputs[0][inputs.input_ids.shape[1]:]
        raw_content = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

        # Parse JSON
        if "```" in raw_content:
            raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.MULTILINE)
            raw_content = re.sub(r"\s*```$", "", raw_content, flags=re.MULTILINE)

        json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if json_match:
            raw_content = json_match.group(0)

        parsed_data = json.loads(raw_content)

        if response_model:
            validated = response_model.model_validate(parsed_data)
            return validated.model_dump()
        return parsed_data


def get_qwen_engine() -> LocalQwenEngine:
    import sys
    if getattr(sys, "_GLOBAL_QWEN_ENGINE", None) is None:
        sys._GLOBAL_QWEN_ENGINE = LocalQwenEngine()
    return sys._GLOBAL_QWEN_ENGINE


class LLMClient:
    """Lớp giao tiếp chính, đóng gói In-Process Local Qwen Engine."""
    def __init__(self, model: Optional[str] = None):
        self.engine = get_qwen_engine()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Optional[Type[BaseModel]] = None
    ) -> Dict[str, Any]:
        return self.engine.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model
        )

