"""
llm_client.py
Ollama LLM: qwen2.5:3b-instruct (cùng máy với VLM qwen2.5vl:7b).
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, Optional, Type
from urllib import error as urlerror
from pydantic import BaseModel

from ai_stack import (
    LLM_TARGET_MODEL,
    LLM_TIMEOUT_SEC,
    OLLAMA_BASE,
    OLLAMA_KEEP_ALIVE,
    has_model,
    ollama_chat,
    ollama_ps,
    ollama_tags,
)


_engine_instance = None
_engine_lock = threading.Lock()


class LocalQwenEngine:
    """Singleton gọi đúng một model LLM trên Ollama."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or LLM_TARGET_MODEL
        self.is_loading = False
        self.is_ready = False
        self.load_error = None
        self._lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        reachable, names, err = ollama_tags()
        pulled = has_model(names, self.model_name)
        resident = False
        size_vram = 0
        for m in ollama_ps():
            if has_model([m.get("name") or ""], self.model_name):
                resident = True
                size_vram = int(m.get("size_vram") or 0)
                break
        online = reachable and pulled
        with self._lock:
            loading = self.is_loading
            ready = self.is_ready or (online and resident and size_vram > 0)
            load_error = self.load_error or err
        return {
            "online": online,
            "ready": ready,
            "loading": loading,
            "model": self.model_name,
            "error": load_error if not online else None,
            "mode": f"Ollama {self.model_name}",
            "ollama_reachable": reachable,
            "model_pulled": pulled,
            "model_resident": resident,
            "size_vram": size_vram,
            "base_url": OLLAMA_BASE,
        }

    def load_model(self):
        with self._lock:
            if self.is_ready or self.is_loading:
                return
            self.is_loading = True
            self.load_error = None

        def _do_load():
            try:
                print(f"🧠 [LLM] Nạp {self.model_name} qua Ollama (keep_alive={OLLAMA_KEEP_ALIVE})...")
                reachable, names, err = ollama_tags()
                if not reachable:
                    raise RuntimeError(err or f"Không kết nối Ollama tại {OLLAMA_BASE}")
                if not has_model(names, self.model_name):
                    raise RuntimeError(f"Chưa pull {self.model_name}. Chạy: ollama pull {self.model_name}")
                ollama_chat(
                    {
                        "model": self.model_name,
                        "format": "json",
                        "messages": [
                            {"role": "user", "content": 'Trả JSON: {"ok": true}'},
                        ],
                        "options": {"num_predict": 16, "temperature": 0.0},
                    },
                    timeout=LLM_TIMEOUT_SEC,
                )
                with self._lock:
                    self.is_ready = True
                    self.is_loading = False
                print(f"✅ [LLM] {self.model_name} sẵn sàng trên Ollama.")
            except Exception as e:
                with self._lock:
                    self.load_error = str(e)
                    self.is_loading = False
                    self.is_ready = False
                print(f"❌ [LLM] Lỗi nạp {self.model_name}: {e}")

        threading.Thread(target=_do_load, daemon=True).start()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Optional[Type[BaseModel]] = None,
    ) -> Dict[str, Any]:
        if not self.is_ready:
            if not self.is_loading:
                self.load_model()
            import time
            wait_start = time.time()
            while not self.is_ready and (time.time() - wait_start < 60):
                time.sleep(0.4)
            if not self.is_ready:
                err_msg = self.load_error or "Hết thời gian chờ nạp model"
                raise RuntimeError(f"LLM {self.model_name} chưa sẵn sàng: {err_msg}")

        schema_hint = ""
        if response_model is not None:
            try:
                schema_hint = (
                    "\n\nJSON schema bắt buộc:\n"
                    + json.dumps(response_model.model_json_schema(), ensure_ascii=False)
                )
            except Exception:
                schema_hint = ""

        enhanced_system = (
            system_prompt
            + "\n\nQUAN TRỌNG: Chỉ trả về duy nhất 1 JSON object hợp lệ. "
            "Tuyệt đối không giải thích thêm, không thêm bất kỳ văn bản nào ngoài JSON."
            + schema_hint
        )
        try:
            body = ollama_chat(
                {
                    "model": self.model_name,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": enhanced_system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "options": {"num_predict": 512, "temperature": 0.0},
                },
                timeout=LLM_TIMEOUT_SEC,
            )
        except TimeoutError as e:
            raise RuntimeError(f"LLM timeout sau {LLM_TIMEOUT_SEC}s: {e}") from e
        except urlerror.URLError as e:
            raise RuntimeError(f"Lỗi mạng Ollama LLM: {e}") from e

        raw_content = ((body.get("message") or {}).get("content") or body.get("response") or "").strip()
        if "```" in raw_content:
            raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.MULTILINE)
            raw_content = re.sub(r"\s*```$", "", raw_content, flags=re.MULTILINE)
        json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if json_match:
            raw_content = json_match.group(0)
        try:
            parsed_data = json.loads(raw_content)
        except Exception:
            cleaned = re.sub(r",\s*([\]}])", r"\1", raw_content)
            parsed_data = json.loads(cleaned)

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
    def __init__(self, model: Optional[str] = None):
        self.engine = get_qwen_engine()
        if model and model != self.engine.model_name:
            self.engine.model_name = LLM_TARGET_MODEL

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Optional[Type[BaseModel]] = None,
    ) -> Dict[str, Any]:
        return self.engine.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
        )
