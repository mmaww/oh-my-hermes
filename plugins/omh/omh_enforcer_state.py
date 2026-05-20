"""Workflow state management for OMH strict enforcer hooks.

Tracks per-session workflow state including current phase, skill loading status,
violation counts, and last check metadata.

This module uses a thread-safe global dictionary keyed by session_id,
bypassing Hermes' user_metadata (which is not passed to plugin hooks).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowState:
    """Per-session workflow state."""

    current_phase: Optional[str] = None
    """Current workflow phase (e.g., 'not_started', 'deep_interview', 'ralplan', 'ralph', 'completed')."""

    skills_loaded: bool = False
    """Whether required OMH workflow skills were loaded into this turn."""

    last_check: Optional[datetime] = None
    """Timestamp of last workflow check."""

    shortcut_detected: bool = False
    """Whether a shortcut command (ralph:, ralplan:, deep-interview:) was detected."""

    violation_count: int = 0
    """Number of Ralph-phase violations (stopping mid-way, false completion claims)."""

    required_item_count: int = 0
    """Largest user-declared task item count observed for this session."""

    required_item_source: str = ""
    """Short excerpt from the user message that established required_item_count."""

    required_items: List[str] = field(default_factory=list)
    """User-owned item manifest. Assistants may satisfy it, but may not shrink it."""

    progress_items: Dict[str, str] = field(default_factory=dict)
    """Item-level progress ledger keyed by manifest item or stable item id."""

    evidence_records: List[Dict[str, Any]] = field(default_factory=list)
    """Recent tool/log evidence records captured from real execution."""

    tool_intents: List[Dict[str, Any]] = field(default_factory=list)
    """Recent pre-tool audit records."""

    completion_verified: bool = False
    """Whether the enforcer accepted this session as verified complete."""

    cancel_requested: bool = False
    """Whether the user explicitly cancelled the workflow."""

    terminal_reason: str = ""
    """Reason recorded when the workflow enters a terminal state."""


# Global state store, keyed by session_id
_workflow_states: Dict[str, WorkflowState] = {}
_loaded_state_file: Optional[str] = None

# Thread-safe access
_lock = RLock()


def _state_file() -> Path:
    """Return the durable state file path."""
    override = os.environ.get("OMH_ENFORCER_STATE_FILE") or os.environ.get("OMC_STATE_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".hermes" / "state" / "omh-enforcer" / "workflow-state.json"


def _dt_to_json(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _dt_from_json(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _state_to_dict(state: WorkflowState) -> Dict[str, Any]:
    return {
        "current_phase": state.current_phase,
        "skills_loaded": state.skills_loaded,
        "last_check": _dt_to_json(state.last_check),
        "shortcut_detected": state.shortcut_detected,
        "violation_count": state.violation_count,
        "required_item_count": state.required_item_count,
        "required_item_source": state.required_item_source,
        "required_items": list(state.required_items),
        "progress_items": dict(state.progress_items),
        "evidence_records": list(state.evidence_records),
        "tool_intents": list(state.tool_intents),
        "completion_verified": state.completion_verified,
        "cancel_requested": state.cancel_requested,
        "terminal_reason": state.terminal_reason,
    }


def _state_from_dict(data: Dict[str, Any]) -> WorkflowState:
    if not isinstance(data, dict):
        return WorkflowState()
    return WorkflowState(
        current_phase=data.get("current_phase"),
        skills_loaded=bool(data.get("skills_loaded", False)),
        last_check=_dt_from_json(data.get("last_check")),
        shortcut_detected=bool(data.get("shortcut_detected", False)),
        violation_count=int(data.get("violation_count") or 0),
        required_item_count=int(data.get("required_item_count") or 0),
        required_item_source=str(data.get("required_item_source") or ""),
        required_items=list(data.get("required_items") or []),
        progress_items=dict(data.get("progress_items") or {}),
        evidence_records=list(data.get("evidence_records") or []),
        tool_intents=list(data.get("tool_intents") or []),
        completion_verified=bool(data.get("completion_verified", False)),
        cancel_requested=bool(data.get("cancel_requested", False)),
        terminal_reason=str(data.get("terminal_reason") or ""),
    )


def _load_from_disk_locked() -> None:
    """Load durable state once per active state file path."""
    global _loaded_state_file
    path = _state_file()
    path_key = str(path)
    if _loaded_state_file == path_key:
        return

    _workflow_states.clear()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            for session_id, payload in raw.items():
                if isinstance(session_id, str):
                    _workflow_states[session_id] = _state_from_dict(payload)
    _loaded_state_file = path_key


def _save_to_disk_locked() -> None:
    """Persist all workflow state atomically."""
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {sid: _state_to_dict(state) for sid, state in _workflow_states.items()}
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _touch(state: WorkflowState) -> None:
    state.last_check = datetime.now()


def _preview(value: Any, limit: int = 4000) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            text = repr(value)
    text = text.replace("\x00", "")
    return text[:limit]


def _looks_error(text: str) -> bool:
    lower = text.lower()
    markers = (
        "traceback", "exception", "error:", "permission denied", "timed out",
        "timeout", "connection refused", "no such file", "exit code 1",
        "exit code 2", "exit code 127", "failed", "失败", "错误",
    )
    return any(marker in lower for marker in markers)


def get_state(session_id: str) -> WorkflowState:
    """Get or create workflow state for a session.

    Args:
        session_id: Unique session identifier.

    Returns:
        WorkflowState for the session (creates new if not exists).
    """
    with _lock:
        _load_from_disk_locked()
        if session_id not in _workflow_states:
            _workflow_states[session_id] = WorkflowState()
        return _workflow_states[session_id]


def set_phase(session_id: str, phase: Optional[str]) -> None:
    """Update the current workflow phase for a session.

    Args:
        session_id: Unique session identifier.
        phase: New phase value (e.g., 'deep_interview', 'ralplan', 'ralph', None).
    """
    with _lock:
        state = get_state(session_id)
        state.current_phase = phase
        if phase not in {"completed", "cancelled"}:
            state.completion_verified = False
            state.terminal_reason = ""
        _touch(state)
        _save_to_disk_locked()


def mark_skills_loaded(session_id: str, loaded: bool = True) -> None:
    """Mark that skills have been loaded for a session.

    Args:
        session_id: Unique session identifier.
        loaded: Whether skills are loaded (default True).
    """
    with _lock:
        state = get_state(session_id)
        state.skills_loaded = loaded
        _touch(state)
        _save_to_disk_locked()


def mark_shortcut_detected(session_id: str, detected: bool = True) -> None:
    """Mark that a shortcut command was detected.

    Args:
        session_id: Unique session identifier.
        detected: Whether a shortcut was detected (default True).
    """
    with _lock:
        state = get_state(session_id)
        state.shortcut_detected = detected
        _touch(state)
        _save_to_disk_locked()


def increment_violation(session_id: str) -> int:
    """Increment violation count for a session.

    Args:
        session_id: Unique session identifier.

    Returns:
        New violation count.
    """
    with _lock:
        state = get_state(session_id)
        state.violation_count += 1
        _touch(state)
        _save_to_disk_locked()
        return state.violation_count


def record_required_item_count(session_id: str, count: int, source: str = "") -> int:
    """Record the user-declared task size without allowing assistant-side shrinkage.

    Completion must be judged against the largest scope stated by the user.
    Later assistant responses cannot reduce this ledger by claiming a smaller
    completed count.
    """
    if not session_id or count <= 0:
        return 0
    with _lock:
        state = get_state(session_id)
        if count > state.required_item_count:
            state.required_item_count = count
            state.required_item_source = (source or "")[:240]
            _touch(state)
            _save_to_disk_locked()
        return state.required_item_count


def record_task_manifest(session_id: str, items: List[str], source: str = "") -> int:
    """Record a user-owned item manifest without allowing assistant shrinkage."""
    if not session_id or not items:
        return 0
    normalized: List[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        text = text[:240]
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    if not normalized:
        return 0
    with _lock:
        state = get_state(session_id)
        if len(normalized) > len(state.required_items):
            state.required_items = normalized
            if len(normalized) > state.required_item_count:
                state.required_item_count = len(normalized)
                state.required_item_source = (source or "user manifest")[:240]
            _touch(state)
            _save_to_disk_locked()
        return len(state.required_items)


def record_progress_item(session_id: str, item: str, status: str) -> None:
    """Record item-level progress."""
    if not session_id or not item:
        return
    with _lock:
        state = get_state(session_id)
        state.progress_items[str(item)[:240]] = str(status or "")[:240]
        _touch(state)
        _save_to_disk_locked()


def record_tool_intent(
    session_id: str,
    tool_name: str,
    args: Any = None,
    tool_call_id: str = "",
    source: str = "pre_tool_call",
) -> int:
    """Record that a tool call was proposed before execution."""
    if not session_id:
        return 0
    record = {
        "ts": datetime.now().isoformat(),
        "source": source,
        "tool_call_id": str(tool_call_id or ""),
        "tool_name": str(tool_name or ""),
        "args_preview": _preview(args, 1200),
    }
    with _lock:
        state = get_state(session_id)
        state.tool_intents.append(record)
        state.tool_intents = state.tool_intents[-120:]
        _touch(state)
        _save_to_disk_locked()
        return len(state.tool_intents)


def record_tool_evidence(
    session_id: str,
    tool_name: str,
    args: Any = None,
    result: Any = None,
    tool_call_id: str = "",
    is_error: Optional[bool] = None,
    source: str = "post_tool_call",
) -> int:
    """Record verifiable tool output evidence for completion checks."""
    if not session_id:
        return 0
    result_preview = _preview(result)
    args_preview = _preview(args, 1200)
    full = result_preview.encode("utf-8", errors="ignore")
    error_flag = bool(is_error) if is_error is not None else _looks_error(result_preview)
    record = {
        "ts": datetime.now().isoformat(),
        "source": source,
        "tool_call_id": str(tool_call_id or ""),
        "tool_name": str(tool_name or ""),
        "args_preview": args_preview,
        "result_preview": result_preview,
        "result_sha256": hashlib.sha256(full).hexdigest(),
        "is_error": error_flag,
    }
    with _lock:
        state = get_state(session_id)
        state.evidence_records.append(record)
        state.evidence_records = state.evidence_records[-160:]
        _touch(state)
        _save_to_disk_locked()
        return len(state.evidence_records)


def mark_completed(session_id: str, reason: str = "") -> None:
    """Mark a session as verified complete."""
    with _lock:
        state = get_state(session_id)
        state.current_phase = "completed"
        state.completion_verified = True
        state.cancel_requested = False
        state.terminal_reason = str(reason or "verified complete")[:500]
        _touch(state)
        _save_to_disk_locked()


def request_cancel(session_id: str, reason: str = "") -> None:
    """Mark a session as explicitly cancelled by the user."""
    with _lock:
        state = get_state(session_id)
        state.current_phase = "cancelled"
        state.cancel_requested = True
        state.terminal_reason = str(reason or "user cancelled")[:500]
        _touch(state)
        _save_to_disk_locked()


def clear_state(session_id: str) -> None:
    """Remove state for a session (cleanup on session end).

    Args:
        session_id: Unique session identifier.
    """
    with _lock:
        _load_from_disk_locked()
        _workflow_states.pop(session_id, None)
        _save_to_disk_locked()


def has_state(session_id: str) -> bool:
    """Check if state exists for a session.

    Args:
        session_id: Unique session identifier.

    Returns:
        True if state exists, False otherwise.
    """
    with _lock:
        _load_from_disk_locked()
        return session_id in _workflow_states


def reset_state_for_tests() -> None:
    """Clear in-memory and durable state for tests."""
    global _loaded_state_file
    with _lock:
        _workflow_states.clear()
        path = _state_file()
        _loaded_state_file = str(path)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
