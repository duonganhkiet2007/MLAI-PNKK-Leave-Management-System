"""AI package (LLM agent, prompts, schemas, Ollama client).

Importing it makes the shared `Leave_Application` modules (domain, rule_engine,
taxonomy, ...) importable, so no manual PYTHONPATH is needed.
"""
import sys
from pathlib import Path

_LEAVE_APP = str(Path(__file__).resolve().parents[2] / "Leave_Application")
if _LEAVE_APP not in sys.path:
    sys.path.insert(0, _LEAVE_APP)
