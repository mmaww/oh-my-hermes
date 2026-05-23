"""Task-level memory persistence for OMH.

Every task gets its own JSON file under .omh/state so that long chats can
recover task intent even when prompt compression trims conversation history.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from .omh_state import state_read, state_write

TASK_MEMORY_MODE = "task-memory"
TASK_MEMORY_META_MODE = "task-memory-meta"
_TASK_MEMORY_SCHEMA = 2

_TASK_START_VERBS = (
    "implement", "implementing", "write", "create", "create", "build", "fix", "optimize",
    "implement", "implementing", "implementer",
)

_CN_TASK_START_VERBS = (
    "帮我", "请帮", "请你", "请", "写", "创建", "实现", "修复", "优化",
    "重构", "排查", "配置", "部署", "测试", "检查", "分析", "整理", "说明",
)

_TASK_PREFIXES = ("实现", "写", "创建", "修复", "优化", "重构", "写好", "做")

_TASK_LIST_RE = re.compile(
    r"(?m)^\s*(?:[-*+]\s+|\d+[.、)]\s+|[①②③④⑤⑥⑦⑧⑨⑩])\S+"
)

_NON_TASK_SMALL = {"hi", "ok", "你好", "嗨", "行", "好的", "okay", "thank you", "谢谢"}
_MAX_TURNS_PER_TASK = 12
_MAX_TURN_CHARS = 500
_MAX_CONTEXT_CHARS = 2400
_MAX_CRITICAL_ANCHORS = 12
_MAX_ANCHOR_CHARS = 150

_CRITICAL_KEYWORDS = (
    "必须",
    "务必",
    "一定",
    "不得",
    "不要",
    "禁止",
    "请确保",
    "至少",
    "最多",
    "并且",
    "只能",
    "每",
    "must",
    "must not",
    "at least",
    "no more than",
    "must include",
    "must avoid",
)

_CRITICAL_COUNT_RE = re.compile(
    r"(?:\d+|[一二三四五六七八九十百千万]+)\s*(?:遍|次|轮|回|份|项|张|条|秒|分钟|小时|天|周|月|个|个数|次序|场景|文件|路径)?"
)
_SENTENCE_SPLIT_RE = re.compile(r"[。！？；;!?\n\r]+")


def _normalize_anchor(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return " ".join(text.replace("\u0000", " ").split())


def _extract_critical_anchors(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    anchors: List[str] = []
    seen = set()
    for segment in _SENTENCE_SPLIT_RE.split(text):
        cleaned = _normalize_anchor(segment.strip("- \t"))
        if not cleaned or len(cleaned) < 6:
            continue
        lowered = cleaned.lower()
        if not _CRITICAL_COUNT_RE.search(cleaned) and not any(keyword in lowered for keyword in _CRITICAL_KEYWORDS):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        anchors.append(_truncate(cleaned, _MAX_ANCHOR_CHARS))
    return anchors


def _append_critical_anchors(task_record: Dict[str, Any], text: str) -> None:
    anchors = task_record.setdefault("critical_anchors", [])
    if not isinstance(anchors, list):
        anchors = []
    existing = [a for a in anchors if isinstance(a, str)]
    added = _extract_critical_anchors(text)
    if not added:
        task_record["critical_anchors"] = existing[-_MAX_CRITICAL_ANCHORS:]
        return

    merged = existing + added
    seen = []
    for item in merged:
        norm = item.strip()
        if not norm:
            continue
        if norm in seen:
            continue
        seen.append(norm)
    task_record["critical_anchors"] = seen[-_MAX_CRITICAL_ANCHORS:]


def _slugify(value: str, max_len: int = 80) -> str:
    if not isinstance(value, str):
        value = str(value)
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    value = value.strip("-")
    if not value:
        return "task"
    return value[:max_len]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _task_session_key(session_id: str) -> str:
    return _slugify(session_id or "default-session")


def _task_manifest_lines(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    out: List[str] = []
    for match in _TASK_LIST_RE.finditer(text):
        line = match.group(0).strip()
        if not line:
            continue
        out.append(line)
    return out[:20]


def _looks_like_new_task(text: str) -> bool:
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if lowered in _NON_TASK_SMALL:
        return False
    if "?" in stripped or "？" in stripped:
        return False
    if lowered.startswith(_TASK_PREFIXES):
        return True
    for prefix in _TASK_START_VERBS:
        if prefix in lowered:
            return True
    for prefix in _CN_TASK_START_VERBS:
        if prefix in text:
            return True
    return bool(_TASK_LIST_RE.search(text))


def _build_task_id(counter: int, text: str) -> str:
    manifest = _task_manifest_lines(text)
    if manifest:
        seed = manifest[0]
    else:
        # Keep only first short noun/verb run for deterministic names.
        seed = text.strip().split(" ", 1)[0] if text else "task"
    return f"task-{counter:03d}-{_slugify(seed, 24)}"


def _build_task_instance_id(session_key: str, task_id: str) -> str:
    return _slugify(f"{session_key}-{task_id}")


def _read_task_meta(session_key: str) -> Dict[str, Any]:
    result = state_read(TASK_MEMORY_META_MODE, instance_id=session_key)
    data = result.get("data", {})
    if not data:
        data = {
            "session_key": session_key,
            "task_counter": 0,
            "current_task_id": "",
            "updated_at": _now_iso(),
        }
    if "task_counter" not in data or not isinstance(data["task_counter"], int):
        data["task_counter"] = 0
    return data


def _write_task_meta(session_key: str, data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    if "schema_version" not in data:
        data["schema_version"] = _TASK_MEMORY_SCHEMA
    state_write(TASK_MEMORY_META_MODE, data, instance_id=session_key)


def _read_task_file(session_key: str, task_id: str) -> Dict[str, Any]:
    instance_id = _build_task_instance_id(session_key, task_id)
    result = state_read(TASK_MEMORY_MODE, instance_id=instance_id)
    data = result.get("data", {})
    if not isinstance(data, dict):
        return {}
    return data


def _write_task_file(session_key: str, task_id: str, data: Dict[str, Any]) -> None:
    if "schema_version" not in data:
        data["schema_version"] = _TASK_MEMORY_SCHEMA
    data["updated_at"] = _now_iso()
    if "task_id" not in data:
        data["task_id"] = task_id
    instance_id = _build_task_instance_id(session_key, task_id)
    state_write(TASK_MEMORY_MODE, data, instance_id=instance_id)


def _append_turn(task_record: Dict[str, Any], actor: str, text: str) -> None:
    turns = task_record.setdefault("turns", [])
    if not isinstance(turns, list):
        turns = []
        task_record["turns"] = turns

    turns.append({
        "actor": actor,
        "text": _truncate((text or "").strip(), _MAX_TURN_CHARS),
        "ts": _now_iso(),
        "seq": len(turns) + 1,
    })
    if len(turns) > _MAX_TURNS_PER_TASK:
        # Keep latest turns; older turns stay in file history if user compresses
        # history repeatedly and loses context, we still keep enough recency.
        task_record["turns"] = turns[-_MAX_TURNS_PER_TASK:]


def _build_memory_block(session_id: str, task_id: str, task_record: Dict[str, Any]) -> str:
    manifest = task_record.get("manifest", [])
    if isinstance(manifest, list):
        manifest_preview = "; ".join([str(x).strip() for x in manifest[:2] if str(x).strip()])
    else:
        manifest_preview = ""
    anchors = task_record.get("critical_anchors", [])
    anchor_lines: List[str] = []
    if isinstance(anchors, list):
        for anchor in anchors[-_MAX_CRITICAL_ANCHORS:]:
            anchor_lines.append(f"  - {str(anchor).strip()}")

    lines = [
        f"[OMH TASK MEMORY] session={session_id} task={task_id}",
    ]
    if manifest_preview:
        lines.append(f"- Manifest: {_truncate(manifest_preview, 300)}")
    if anchor_lines:
        lines.append("- Critical anchors (hard-to-drop):")
        lines.extend(anchor_lines)
    turns = task_record.get("turns", [])
    if turns:
        lines.append("- Recent turns:")
        for idx, item in enumerate(turns[-6:], start=1):
            actor = item.get("actor", "unknown")
            lines.append(f"  {idx}. {actor}: {_truncate(str(item.get('text', '')), 180)}")
    else:
        lines.append("- No turns recorded yet.")
    if task_record.get("summary"):
        lines.append(f"- Previous summary: {_truncate(str(task_record['summary']), 220)}")
    block = "\n".join(lines)
    return _truncate(block, _MAX_CONTEXT_CHARS)


def _ensure_task_context(
    session_id: str,
    user_message: str,
    is_first_turn: bool = False,
) -> Tuple[str, str]:
    """Create/continue task state and persist user turn.

    Returns (task_id, context_block) for prompt injection.
    """
    session_key = _task_session_key(session_id)
    meta = _read_task_meta(session_key)
    task_id = str(meta.get("current_task_id") or "")

    should_start_new = is_first_turn or not task_id or _looks_like_new_task(user_message)
    if should_start_new:
        meta["task_counter"] = int(meta.get("task_counter", 0)) + 1
        task_id = _build_task_id(meta["task_counter"], user_message)
        meta["current_task_id"] = task_id
        manifest = _task_manifest_lines(user_message)
        task_record = {
            "task_id": task_id,
            "created_at": _now_iso(),
            "manifest": manifest,
            "turns": [],
            "critical_anchors": [],
        }
        if manifest:
            task_record["summary"] = manifest[0]
        _write_task_file(session_key, task_id, task_record)
    else:
        task_record = _read_task_file(session_key, task_id)
        if not task_record:
            # Legacy repair for interrupted/missing task file.
            task_record = {
                "task_id": task_id,
                "created_at": _now_iso(),
                "turns": [],
            }
        if not task_record.get("task_id"):
            task_record["task_id"] = task_id
        if "critical_anchors" not in task_record:
            task_record["critical_anchors"] = []

    _append_critical_anchors(task_record, user_message)
    _append_turn(task_record, "user", user_message)

    _write_task_file(session_key, task_id, task_record)
    meta["current_task_id"] = task_id
    _write_task_meta(session_key, meta)
    return task_id, _build_memory_block(session_id, task_id, task_record)


def append_assistant_turn(session_id: str, assistant_response: str) -> None:
    """Persist assistant response to the current task memory file."""
    if not session_id:
        return
    session_key = _task_session_key(session_id)
    meta = _read_task_meta(session_key)
    task_id = str(meta.get("current_task_id") or "")
    if not task_id:
        return
    task_record = _read_task_file(session_key, task_id)
    if not task_record:
        return
    _append_turn(task_record, "assistant", assistant_response)
    _write_task_file(session_key, task_id, task_record)


def prepare_task_memory_context(session_id: str, user_message: str, is_first_turn: bool = False) -> str:
    """Write task state and return memory block for prompt injection."""
    if not session_id:
        return ""
    _, block = _ensure_task_context(session_id, user_message, is_first_turn=is_first_turn)
    return block
