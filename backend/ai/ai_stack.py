"""Canonical AI stack: only these two Ollama models are used."""
from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

OLLAMA_BASE = os.getenv("OLLAMA_BASE", os.getenv("VLM_OLLAMA_BASE", "http://localhost:11434")).rstrip("/")
LLM_TARGET_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b-instruct")
VLM_TARGET_MODEL = os.getenv("VLM_TARGET_MODEL", "qwen2.5vl:7b")

LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "60.0"))
VLM_TIMEOUT_SEC = float(os.getenv("VLM_TIMEOUT_SEC", "180.0"))


def keep_alive_value():
    """Ollama parses keep_alive as Go duration. String '-1' → HTTP 400; number -1 = never unload."""
    raw = str(os.getenv("OLLAMA_KEEP_ALIVE", "-1")).strip()
    if raw in {"-1", "forever", "infinite"}:
        return -1
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


OLLAMA_KEEP_ALIVE = keep_alive_value()


def has_model(names: list[str], target: str) -> bool:
    t = (target or "").strip()
    for n in names:
        if n == t or n.startswith(t + "-"):
            return True
    return False


def ollama_tags(timeout: float = 3.0) -> tuple[bool, list[str], Optional[str]]:
    try:
        with urlrequest.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode() or "{}")
        names = [m.get("name", "") for m in data.get("models", [])]
        return True, names, None
    except (urlerror.URLError, OSError, TimeoutError, ValueError) as e:
        return False, [], f"{type(e).__name__}: {e}"


def ollama_ps(timeout: float = 3.0) -> list[dict[str, Any]]:
    try:
        with urlrequest.urlopen(f"{OLLAMA_BASE}/api/ps", timeout=timeout) as r:
            data = json.loads(r.read().decode() or "{}")
        return list(data.get("models") or [])
    except Exception:
        return []


def _ollama_post(path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = dict(payload)
    body.setdefault("stream", False)
    body.setdefault("keep_alive", OLLAMA_KEEP_ALIVE)
    req = urlrequest.Request(
        f"{OLLAMA_BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urlerror.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            detail = str(e)
        raise RuntimeError(f"Ollama {path} HTTP {e.code}: {detail}") from e


def ollama_generate(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    return _ollama_post("/api/generate", payload, timeout)


def ollama_chat(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    return _ollama_post("/api/chat", payload, timeout)
