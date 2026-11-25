import os
import re
import threading
from typing import Optional

_lock = threading.Lock()
_session_key: Optional[str] = None
KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,200}")


def is_valid_format(value: str) -> bool:
    return KEY_PATTERN.fullmatch(value) is not None


def set_key(value: str) -> None:
    global _session_key
    if not is_valid_format(value):
        raise ValueError("That does not look like an Anthropic API key.")
    with _lock:
        _session_key = value


def clear_key() -> None:
    global _session_key
    with _lock:
        _session_key = None


def current_key() -> Optional[str]:
    with _lock:
        if _session_key:
            return _session_key
    return os.getenv("ANTHROPIC_API_KEY") or None


def status() -> dict:
    key = current_key()
    if not key:
        return {"set": False}
    with _lock:
        source = "session" if _session_key else "environment"
    return {"set": True, "source": source, "hint": key[-4:]}
