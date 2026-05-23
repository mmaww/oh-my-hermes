
"""
OMH Enforcer hooks - strict OMC-style anti-lazy enforcement for OMH.

This plugin ensures every non-trivial task follows the OMC workflow:
  1. deep-interview — Socratic clarification
  2. ralplan — Iterative planning with ADR
  3. ralph — Execution with verify/fix loop

Quick commands:
  - "ralph: <task>" → Skip to Phase 3 execution
  - "ralplan: <task>" → Skip to Phase 2 planning
  - "deep-interview:" → Start Phase 1

Technical approach:
  - on_session_start: Initialize state
  - pre_llm_call: Check workflow state, inject reminders
  - post_llm_call: Validate each phase output
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from ..omh_enforcer_state import (
    clear_state,
    get_state,
    increment_ralph_close_checks,
    increment_violation,
    mark_completed,
    mark_shortcut_detected,
    mark_skills_loaded,
    record_required_item_count,
    record_task_manifest,
    record_tool_evidence,
    record_tool_intent,
    reset_ralph_close_checks,
    request_cancel,
    set_phase,
)

logger = logging.getLogger("plugins.omh.enforcer")


def _enforcer_enabled() -> bool:
    """Feature flag for strict enforcer hooks (enabled by default)."""
    raw = (
        os.environ.get("OMH_ENFORCER_ENABLED")
        or os.environ.get("OMC_ENFORCER_ENABLED")
        or "1"
    )
    return str(raw).strip().lower() not in {"0", "false", "no", "off", "disable", "disabled"}


class WorkflowPhase:
    NOT_STARTED = "not_started"
    DEEP_INTERVIEW = "deep_interview"
    RALPLAN = "ralplan"
    RALPH = "ralph"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Quick command prefixes that skip phases
QUICK_COMMANDS = {
    "ralph:": WorkflowPhase.RALPH,
    "ralplan:": WorkflowPhase.RALPLAN,
    "deep-interview:": WorkflowPhase.DEEP_INTERVIEW,
    "ralph：": WorkflowPhase.RALPH,  # Chinese colon
    "ralplan：": WorkflowPhase.RALPLAN,
}

WORKFLOW_REMINDER = """
⚠️ OMC Workflow Enforcement Active

You are in Phase: {phase}

Required workflow for non-trivial tasks:
1. **deep-interview** — Ask clarifying questions (Socratic method)
2. **ralplan** — Create plan with ADR (Architectural Decision Record)
3. **ralph** — Execute with verify/fix loop

Quick commands:
- "ralph: <task>" → Skip to execution
- "ralplan: <task>" → Skip to planning
- "deep-interview:" → Start clarification

⚠️ DO NOT skip phases unless user uses quick command prefix.
"""

# Initial system prompt for session start
OMC_SYSTEM_PROMPT = """
══════════════════════════════════════════════
OMC WORKFLOW ENFORCEMENT
══════════════════════════════════════════════

You are operating under OMC (Observe-Model-Code) 3-phase workflow enforcement.

**Phase 1: deep-interview**
- Ask clarifying questions ONE AT A TIME
- Use Socratic method — guide user to clarify intent
- DO NOT ask about codebase facts (check yourself)
- Focus on: preferences, priorities, constraints, scope

**Phase 2: ralplan**
- Present >= 2 options with trade-offs
- Document decision with ADR format
- Get user confirmation before proceeding

**Phase 3: ralph**
- Execute with verify/fix loop
- Each step must be verified before next
- Report progress after each step

**Trigger:** User gives a task → Start Phase 1
**Quick commands:** User says "ralph: task" → Skip to Phase 3

⚠️ **CRITICAL**: Skipping workflow causes false-completion and lazy-handoff failures.

══════════════════════════════════════════════
"""


TASK_AUDIT_SUPERVISOR_PROMPT = """
══════════════════════════════════════════════
HERMES TASK AUDIT SUPERVISOR - ALWAYS ACTIVE
══════════════════════════════════════════════

你是 Hermes 的严格任务模块。你的职责是确保任务在处理任务时不偷懒、不应付、不撒谎，并提供可验证依据。请遵循以下规则：

1. 执行核验
   - 对每条任务或请求的完成情况，必须明确指出是否已经完成。
   - 所有回答必须包含具体依据：操作步骤、数据、逻辑推导或可验证结果。
   - 如果无法确认完成，必须回复“无法确认，缺乏证据”，不得虚构完成状态。

2. 偷懒检测
   - 检测典型偷懒行为：
     - 拒绝尝试（如“我不会”“无法处理”）
     - 模糊或重复模板回答
     - 回避任务或延迟操作
   - 对检测到的偷懒行为：
     - 强制尝试至少一个可行操作
     - 在回复中说明尝试步骤与依据
     - 记录日志以便审计

3. 应付与撒谎检测
   - 如果回复声称已完成，但没有操作证据或数据支撑，即判定为应付或撒谎。
   - 必须提供操作日志、数据引用或明确逻辑作为证据，否则标记未完成。

4. 行为强化
   - 对每条任务，重复检查是否符合以上规范。
   - 如果发现问题，重复提示“请提供具体执行步骤或证据”。
   - 尝试自我修正（可执行可行操作），并附上操作依据和结果。

5. 输出格式
   - **结论**：任务是否完成
   - **依据**：数据、步骤、逻辑或文献引用
   - **修正/建议**：发现偷懒、应付、遗漏或错误的处理方式

This supervisor prompt is injected on every LLM call by omh-enforcer. Treat it as mandatory policy for this turn.
══════════════════════════════════════════════
"""


TASK_AUDIT_GUARDRAIL_PROMPT = """
══════════════════════════════════════════════
HERMES TASK AUDIT GUARDRAIL
══════════════════════════════════════════════

你是 Hermes 的任务质量护栏。保持正常用户回复格式，不要强制套用“结论/依据/修正/建议”模板。

必须遵守：
- 声称完成、修复或验证时，给出可核验依据，例如文件路径、命令输出、测试结果或日志位置。
- 批量任务必须按用户原始数量闭环；不得把 100 件、1188 DOI 等范围缩成更小子集后宣称完成。
- Ralph 关闭必须匹配 OMC ledger：用户任务清单/数量、真实工具执行证据、测试或日志证据、无待办/无已知错误。
- 不能用口头“继续自救”“已执行”“装好了”替代真实操作；缺少工具/日志证据时必须继续执行或明确“无法确认，缺乏证据”。
- 如果无法完成，说明已经尝试的路径、失败证据和可行替代方案。
- 对安全、可逆、已明确要求的下一步，不要用“要我继续吗”中途停下。
- 只有删除、覆盖、生产重启、付费、凭证等高风险分支才停下来询问。

严格三段式审计格式仅在 OMC_REQUIRE_AUDIT_FORMAT=1 或 HERMES_REQUIRE_AUDIT_FORMAT=1 时启用。
══════════════════════════════════════════════
"""


def _strict_audit_format_enabled() -> bool:
    """Return true only when strict final-answer audit formatting is explicitly enabled."""
    value = os.environ.get("OMC_REQUIRE_AUDIT_FORMAT") or os.environ.get("HERMES_REQUIRE_AUDIT_FORMAT")
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "strict"}


NON_TASK_SHORT_GREETINGS = {
    "hi", "ok", "yes", "no", "hey", "hello", "你好", "在", "嗯", "好", "行"
}

TASK_PREFIXES = (
    "实现", "写", "创建", "修复", "优化", "重构",
    "implement", "write", "create", "fix", "optimize", "refactor", "resolve", "upgrade", "add", "build",
)

_BUNDLED_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

REQUIRED_SKILLS = {
    "omh-deep-interview": [
        Path.home() / ".hermes" / "skills" / "omh" / "omh-deep-interview" / "SKILL.md",
        _BUNDLED_SKILLS_DIR / "omh-deep-interview" / "SKILL.md",
    ],
    "omh-ralplan": [
        Path.home() / ".hermes" / "skills" / "omh" / "omh-ralplan" / "SKILL.md",
        _BUNDLED_SKILLS_DIR / "omh-ralplan" / "SKILL.md",
    ],
    "omh-ralph": [
        Path.home() / ".hermes" / "skills" / "omh" / "omh-ralph" / "SKILL.md",
        _BUNDLED_SKILLS_DIR / "omh-ralph" / "SKILL.md",
    ],
}


def _resolve_skill_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _detect_quick_command(user_message: str) -> Optional[str]:
    """Check if user message starts with quick command prefix."""
    if not user_message:
        return None
    text = user_message.strip().lower()
    for prefix, phase in QUICK_COMMANDS.items():
        if text.startswith(prefix.lower()):
            return phase
    return None


def _is_likely_task(user_message: str) -> bool:
    """Heuristic used by tests and pre-LLM enforcement."""
    if not isinstance(user_message, str):
        return False

    msg = user_message.strip()
    if not msg:
        return False

    # Questions are treated as not task-by-default for OMC gate.
    if "?" in msg or "？" in msg:
        return False

    lowered = msg.lower()
    if lowered in NON_TASK_SHORT_GREETINGS:
        return False

    if lowered.startswith(TASK_PREFIXES):
        return True

    for token in TASK_PREFIXES:
        if token in lowered:
            return True

    # Soft task-intent cues + action verbs (reduce false positives on long chit-chat)
    intent_prefixes = (
        "please", "请", "能否", "可以", "我想", "我希望", "请帮", "帮我", "我需要", "需要"
    )
    if not any(t in lowered for t in intent_prefixes):
        return False

    intent_verbs = (
        "读", "看", "检查", "分析", "审查", "排查", "调试", "配置", "安装", "部署", "验证",
        "对比", "迁移", "测试", "优化", "整理", "说明", "总结", "解答", "查找", "定位",
    )
    return any(v in lowered for v in intent_verbs)


_TASK_COUNT_UNITS = (
    "件", "个", "项", "条", "篇", "份", "张", "批",
    "doi", "paper", "papers", "pdf", "pdfs", "file", "files",
    "文件", "任务", "记录", "样本", "论文",
)


def _extract_user_required_item_count(user_message: str) -> int:
    """Infer the user-declared task size from the user's own message only."""
    if not isinstance(user_message, str) or not user_message.strip():
        return 0

    counts = []
    unit_pattern = "|".join(re.escape(u) for u in _TASK_COUNT_UNITS)
    for match in re.finditer(rf"(?<!\d)(\d{{1,6}})\s*(?:{unit_pattern})", user_message, re.I):
        try:
            value = int(match.group(1))
        except ValueError:
            continue
        # Ignore obvious years and tiny incidental counts.
        if 2 <= value <= 100000 and not re.search(rf"{value}\s*年", user_message):
            counts.append(value)

    # Numbered/bulleted user task lists are also a scope declaration.
    task_lines = re.findall(r"(?m)^\s*(?:[-*+]\s+|\d+[.、)]\s+|[①②③④⑤⑥⑦⑧⑨⑩])\S", user_message)
    if len(task_lines) >= 3:
        counts.append(len(task_lines))

    return max(counts) if counts else 0


def _extract_user_task_manifest(user_message: str) -> list[str]:
    """Extract an explicit user-owned numbered/bulleted task manifest."""
    if not isinstance(user_message, str) or not user_message.strip():
        return []
    items = []
    for match in re.finditer(
        r"(?m)^\s*(?:[-*+]\s+|\d+[.、)]\s+|[①②③④⑤⑥⑦⑧⑨⑩])(.+?)\s*$",
        user_message,
    ):
        item = match.group(1).strip()
        if item:
            items.append(item)
    return items


def _remember_user_task_scope(session_id: str, user_message: str) -> int:
    """Update the OMC-owned task ledger from user input, never assistant output."""
    manifest = _extract_user_task_manifest(user_message)
    if len(manifest) >= 2:
        record_task_manifest(session_id, manifest, user_message.strip())
    count = _extract_user_required_item_count(user_message)
    if count >= 2:
        return record_required_item_count(session_id, count, user_message.strip())
    if len(manifest) >= 2:
        return len(manifest)
    return 0


def _is_cancel_request(user_message: str) -> bool:
    """Return true only for explicit user cancellation/stop commands."""
    if not isinstance(user_message, str):
        return False
    text = user_message.strip().lower()
    if not text:
        return False
    exact = {
        "cancel", "/cancel", "stop", "abort", "quit", "exit",
        "取消", "停止", "终止", "停下", "别做了", "不用做了",
    }
    if text in exact:
        return True
    return bool(re.fullmatch(r"(取消|停止|终止|abort|cancel|stop)\s+(ralph|omc|任务|workflow)", text))


def _build_forced_skill_context(session_id: str = "") -> str:
    """Inject required skill contents directly instead of asking the model to load them."""
    sections = [
        "[OMH ENFORCER] REQUIRED SKILLS PRELOADED",
        "The plugin hook has loaded these SKILL.md files directly into this turn.",
        "Treat them as already active. Do not ask the user whether to load them and do not merely say you loaded them.",
    ]
    loaded_all = True

    for name, candidates in REQUIRED_SKILLS.items():
        path = _resolve_skill_path(candidates)
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            loaded_all = False
            logger.error("[omh-enforcer] required skill missing: %s (%s)", name, path)
            sections.append(
                f"\n<required_skill name=\"{name}\" status=\"missing\" path=\"{path}\">\n"
                "ERROR: required skill file is missing. Report this as a blocker with the path above.\n"
                f"</required_skill>"
            )
            continue
        except Exception as exc:
            loaded_all = False
            logger.exception("[omh-enforcer] failed to load required skill %s from %s", name, path)
            sections.append(
                f"\n<required_skill name=\"{name}\" status=\"error\" path=\"{path}\">\n"
                f"ERROR: failed to read required skill: {exc}\n"
                f"</required_skill>"
            )
            continue

        sections.append(
            f"\n<required_skill name=\"{name}\" status=\"loaded\" path=\"{path}\">\n"
            f"{content.rstrip()}\n"
            f"</required_skill>"
        )

    if session_id:
        mark_skills_loaded(session_id, loaded_all)

    return "\n\n".join(sections)


def _with_forced_skills(session_id: str = "", *parts: str) -> Dict[str, str]:
    """Return pre_llm_call context with quality guardrails and required skills hard-injected."""
    strict = _strict_audit_format_enabled()
    logger.info(
        "[omh-enforcer] injecting task audit %s (session=%s)",
        "supervisor" if strict else "guardrail",
        session_id or "<none>",
    )
    context_parts = [_build_forced_skill_context(session_id)]
    context_parts.extend(part.strip() for part in parts if part and part.strip())
    return {
        "system_context": (
            TASK_AUDIT_SUPERVISOR_PROMPT if strict else TASK_AUDIT_GUARDRAIL_PROMPT
        ).strip(),
        "context": "\n\n".join(context_parts),
    }

def _on_session_start(session_id: str = "", user_metadata: Dict[str, Any] = None, **kwargs) -> None:
    """Initialize workflow state and load required skills.

    This hook fires when a new session starts.
    """
    if not _enforcer_enabled():
        return None
    if user_metadata is None:
        user_metadata = {}

    logger.info("[omh-enforcer] Session started: %s", session_id)

    # Initialize session state using global state store.
    if session_id:
        set_phase(session_id, None)
        mark_skills_loaded(session_id, False)

    # Keep metadata hint for adapters that inspect it.
    user_metadata["omh_workflow_required"] = True
    user_metadata["omh_skills_required"] = list(REQUIRED_SKILLS.keys())
    user_metadata["omc_workflow_required"] = True

    return None


def _pre_llm_call(
    user_message: str = "",
    session_id: str = "",
    user_metadata: Dict[str, Any] = None,
    conversation_history: list = None,
    is_first_turn: bool = False,
    **kwargs
) -> Optional[Dict[str, str]]:
    """Inject OMC context/reminders before LLM call."""
    if not _enforcer_enabled():
        return None
    if user_metadata is None:
        user_metadata = {}

    if session_id:
        _remember_user_task_scope(session_id, user_message)

    if session_id and _is_cancel_request(user_message):
        request_cancel(session_id, user_message.strip())
        return _with_forced_skills(
            session_id,
            "[OMH ENFORCER] User explicitly cancelled the active workflow. "
            "Acknowledge cancellation only; do not claim task completion.",
        )

    quick_phase = _detect_quick_command(user_message)

    if is_first_turn:
        if session_id:
            set_phase(session_id, quick_phase if quick_phase else None)
            if quick_phase:
                mark_shortcut_detected(session_id, True)
        quick_note = (
            f"[OMH ENFORCER] Quick command detected; starting in phase: {quick_phase}."
            if quick_phase else ""
        )
        return _with_forced_skills(session_id, OMC_SYSTEM_PROMPT, quick_note)

    if not session_id:
        logger.info("[omh-enforcer] pre_llm_call without session_id; injecting audit supervisor only")
        return _with_forced_skills("")

    if quick_phase:
        logger.info("[omh-enforcer] Quick command detected → %s", quick_phase)
        set_phase(session_id, quick_phase)
        mark_shortcut_detected(session_id, True)
        return _with_forced_skills(
            session_id,
            f"[OMH ENFORCER] Quick command detected; starting in phase: {quick_phase}.",
        )

    state = get_state(session_id)
    phase = state.current_phase

    logger.info("[omh-enforcer] pre_llm_call - Phase: %s", phase)

    # Skip if already in workflow.
    if phase in [WorkflowPhase.DEEP_INTERVIEW, WorkflowPhase.RALPLAN, WorkflowPhase.RALPH]:
        return _with_forced_skills(
            session_id,
            f"[OMH ENFORCER] Workflow phase active: {phase}. Continue under the preloaded required skills.",
        )

    if _is_likely_task(user_message) and phase in (None, WorkflowPhase.NOT_STARTED):
        set_phase(session_id, WorkflowPhase.DEEP_INTERVIEW)
        return _with_forced_skills(
            session_id,
            WORKFLOW_REMINDER.format(phase=WorkflowPhase.DEEP_INTERVIEW),
        )

    return _with_forced_skills(
        session_id,
        "[OMH ENFORCER] No workflow phase change for this turn. Continue under the always-active audit supervisor and preloaded required skills.",
    )


def _on_session_end(session_id: str = "", user_metadata: Dict[str, Any] = None, **kwargs) -> None:
    """Cleanup when session ends."""
    if not _enforcer_enabled():
        return None
    logger.info("[omh-enforcer] Session ended: %s", session_id)
    if session_id:
        state = get_state(session_id)
        if state.current_phase == WorkflowPhase.RALPH:
            logger.warning("[omh-enforcer] preserving active ralph state on session_end: %s", session_id)
            return None
        clear_state(session_id)
    return None


def _dangerous_tool_command(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    """Return a reason for obviously destructive tool calls."""
    if not isinstance(args, dict):
        args = {}
    command = ""
    for key in ("command", "cmd", "shell_command", "input", "script"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            command = value.strip()
            break
    haystack = f"{tool_name} {command}".lower()
    destructive = (
        r"rm\s+-rf\s+/(?:\s|$)",
        r"git\s+reset\s+--hard",
        r"git\s+clean\s+-fdx",
        r"mkfs\.",
        r"dd\s+if=.*\sof=/dev/",
        r"drop\s+table",
        r"truncate\s+table",
        r"shutdown\s+(?:-h|now)",
        r"poweroff\b",
        r":\(\)\s*\{\s*:\|:",
    )
    for pattern in destructive:
        if re.search(pattern, haystack, re.I):
            return f"destructive command matched: {pattern}"
    return None


def _on_pre_tool_call(
    tool_name: str = "",
    args: Dict[str, Any] = None,
    session_id: str = "",
    tool_call_id: str = "",
    **kwargs,
) -> Optional[Dict[str, str]]:
    """Audit proposed tool calls and block only obviously destructive operations."""
    if not _enforcer_enabled():
        return None
    args = args if isinstance(args, dict) else {}
    if session_id:
        record_tool_intent(session_id, tool_name, args, tool_call_id=tool_call_id)

    reason = _dangerous_tool_command(tool_name, args)
    if reason:
        logger.warning("[omh-enforcer] BLOCKED dangerous tool=%s session=%s reason=%s", tool_name, session_id, reason)
        return {
            "action": "block",
            "message": (
                "[OMC TOOL AUDIT] Tool call blocked because it appears destructive. "
                f"Reason: {reason}. Use a non-destructive inspection/backup path first."
            ),
        }
    return None


def _on_post_tool_call(
    tool_name: str = "",
    args: Dict[str, Any] = None,
    result: Any = None,
    session_id: str = "",
    tool_call_id: str = "",
    is_error: Optional[bool] = None,
    **kwargs,
) -> None:
    """Persist real tool output as completion evidence."""
    if not _enforcer_enabled():
        return None
    if session_id:
        record_tool_evidence(
            session_id,
            tool_name,
            args if isinstance(args, dict) else {},
            result,
            tool_call_id=tool_call_id,
            is_error=is_error,
        )
    return None


def _resume_ralph_after_block(session_id: str, phase: Optional[str], result: Dict[str, Any]) -> None:
    """Keep/reopen Ralph when a blocked response indicates execution drift."""
    block_type = str(result.get("type") or "")
    resume_tokens = (
        "stopped_to_ask",
        "known_invalid_stopped",
        "giveup",
        "claimed_done_no_evidence",
        "premature_close",
        "missing_audit_format",
    )
    should_resume = (
        phase in (WorkflowPhase.RALPH, WorkflowPhase.COMPLETED)
        or any(token in block_type for token in resume_tokens)
    )
    if not session_id or not should_resume:
        return

    set_phase(session_id, WorkflowPhase.RALPH)
    result["resume_phase"] = WorkflowPhase.RALPH
    result["message"] = (
        f"{result.get('message', '')}\n"
        "Ralph恢复: 已将会话重新置为 ralph 执行态；禁止关闭 Ralph，"
        "必须继续执行安全可逆动作并提供文件、命令、测试或日志证据。"
    )
    logger.warning("[omh-enforcer] resumed ralph after block: session=%s type=%s", session_id, block_type)


def _on_pre_gateway_send(
    platform: str = "",
    chat_id: str = "",
    content: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    operation: str = "send",
    **kwargs,
) -> Optional[Dict[str, Any]]:
    """Final outbound gate: every user-visible gateway message is checked before send."""
    if not _enforcer_enabled():
        return None
    if not isinstance(content, str) or not content.strip():
        return None
    metadata = metadata if isinstance(metadata, dict) else {}
    if metadata.get("omc_skip_outbound_guard"):
        return None

    session_id = str(metadata.get("hermes_session_id") or metadata.get("session_id") or "")
    phase = get_state(session_id).current_phase if session_id else None

    result = None
    if session_id and phase == WorkflowPhase.RALPH:
        result = _check_ralph_v2(content, session_id)
        current_phase = get_state(session_id).current_phase
        if not result and current_phase == WorkflowPhase.RALPH:
            result = {
                "block": True,
                "type": "ralph:active_output",
                "message": (
                    "[OMC Phase 3] Ralph 仍处于执行态，用户可见输出已被打回。"
                    "不要输出进度总结、继续确认或无关闭证据的回复；"
                    "继续执行安全可逆动作。只有 completion_score >=99/100 "
                    "且包含改动文件、命令/测试/日志证据、验证通过、"
                    "无待办/无已知错误声明时，才允许输出关闭报告。"
                ),
            }
    if not result:
        result = _check_general_anti_lazy(content)
    if not result:
        return None

    if session_id:
        _resume_ralph_after_block(session_id, phase, result)
        increment_violation(session_id)
    result["gateway_blocked"] = True
    result["operation"] = operation
    logger.warning(
        "[omh-enforcer] BLOCKED outbound platform=%s chat=%s op=%s type=%s",
        platform,
        chat_id,
        operation,
        result.get("type"),
    )
    return result


# ─────────────────────────────────────────────────────────────
# post_llm_call: 三阶段强制拦截
# ┈────────────────────────────────────────────────────────────

def _on_post_llm_call(
    user_message: str = "",
    assistant_response: str = "",
    session_id: str = "",
    conversation_history: list = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    三阶段强制 Hook。

    Returns:
        {"block": True, "type": "...", "message": "..."}  拦截并触发重试
        None  放行
    """
    if not _enforcer_enabled():
        return None
    if not session_id:
        return None

    state = get_state(session_id)
    phase = state.current_phase

    resp = assistant_response or ""
    _record_history_tool_evidence(session_id, conversation_history)

    if phase == WorkflowPhase.RALPH:
        ralph_result = _check_ralph_v2(resp, session_id)
        if ralph_result and ralph_result.get("block"):
            _resume_ralph_after_block(session_id, phase, ralph_result)
            increment_violation(session_id)
            logger.warning("[omh-enforcer] BLOCKED phase=%s type=%s", phase, ralph_result.get("type"))
            return ralph_result

    global_result = _check_general_anti_lazy(resp)
    if global_result:
        _resume_ralph_after_block(session_id, phase, global_result)
        increment_violation(session_id)
        logger.warning("[omh-enforcer] BLOCKED global type=%s", global_result.get("type"))
        return global_result

    if _strict_audit_format_enabled():
        audit_format_result = _check_required_audit_format(resp)
        if audit_format_result:
            increment_violation(session_id)
            logger.warning("[omh-enforcer] BLOCKED global type=%s", audit_format_result.get("type"))
            return audit_format_result

    if phase in (None, WorkflowPhase.NOT_STARTED, WorkflowPhase.COMPLETED, WorkflowPhase.CANCELLED):
        return None

    result = None
    if phase == WorkflowPhase.DEEP_INTERVIEW:
        result = _check_deep_interview(resp)
        if not result:
            set_phase(session_id, WorkflowPhase.RALPLAN)
            logger.info("[omh-enforcer] Advanced from deep_interview -> ralplan")
    elif phase == WorkflowPhase.RALPLAN:
        result = _check_ralplan(resp)
        if not result:
            set_phase(session_id, WorkflowPhase.RALPH)
            logger.info("[omh-enforcer] Advanced from ralplan -> ralph")
    else:
        result = None

    if result and result.get("block"):
        _resume_ralph_after_block(session_id, phase, result)
        increment_violation(session_id)
        logger.warning("[omh-enforcer] BLOCKED phase=%s type=%s", phase, result.get("type"))
        return result

    return None

def _check_deep_interview(resp: str) -> Optional[Dict[str, Any]]:
    """Phase 1: LLM 必须提问，不能直接执行"""
    if not resp:
        return {"block": True, "type": "deep_interview:empty",
                "message": "[OMC Phase 1] Ask ONE clarifying question. Do NOT execute."}
    rl = resp.lower()
    direct = ["我来实现", "开始写", "开始创建", "已经创建", "我来写", "让我来", "马上做", "这就",
              "let me implement", "i'll create", "i'll write", "here's the code", "here is the"]
    if any(p in rl for p in direct):
        return {"block": True, "type": "deep_interview:executing",
                "message": (
                    "[OMC Phase 1] You are in the INTERVIEW phase. Ask ONE clarifying question ONLY. "
                    "Do NOT execute, do NOT plan, do NOT present solutions."
                )}
    return None


def _check_ralplan(resp: str) -> Optional[Dict[str, Any]]:
    """Phase 2: 必须有 >=2 方案 + ADR，不能直接执行"""
    if not resp:
        return {"block": True, "type": "ralplan:empty",
                "message": "[OMC Phase 2] Present >=2 options with ADR. Do NOT execute."}
    rl = resp.lower()
    direct = ["我来实现", "开始写", "开始创建", "已经创建", "我来写", "让我来", "马上做",
              "let me implement", "i'll create", "i'll write"]
    has_options = bool(re.search(r'(option|方案|approach)\s*[12]', rl))
    if any(p in rl for p in direct) and not has_options:
        return {"block": True, "type": "ralplan:executing_no_options",
                "message": (
                    "[OMC Phase 2] Present >=2 options with trade-offs. "
                    "Include Principles, Decision Drivers, Options table, ADR."
                )}
    return None


def _has_evidence(resp: str) -> bool:
    path_like = re.search(
        r"(?:(?:/|~/?|\./|\.\./)[\w.\- \u4e00-\u9fff/]+|[\w.\- \u4e00-\u9fff]+/[\w.\- \u4e00-\u9fff/]+)"
        r"\.(?:py|js|ts|tsx|md|json|yaml|yml|sh|txt|log|pdf|html|css)(?::\d+)?",
        resp,
    )
    command_result = re.search(
        r"(?i)(pytest|python3? -m|npm (?:test|run)|pnpm (?:test|run)|uv run|git (?:status|diff)|"
        r"curl |ssh |scp |rg |sed |exit code|process exited|tests? passed|测试输出|验证输出|命令输出|日志)",
        resp,
    )
    changed_files = re.search(r"(改动文件|修改文件|changed files?|files changed|验证|tested|not-tested|测试):", resp, re.I)
    return bool(path_like or command_result or changed_files)


def _has_blocker_evidence(resp: str) -> bool:
    blocker = re.search(
        r"(?i)(permission denied|operation not permitted|http\s*(401|403|404|429|5\d\d)|"
        r"traceback|exception|error:|errno|timed out|timeout|connection refused|no such file|"
        r"missing credential|api key|exit code\s*[1-9]|失败输出|错误输出)",
        resp,
    )
    attempted = re.search(r"(尝试|重试|换用|fallback|alternative|tried|retry|再次|另一路径)", resp, re.I)
    return bool(blocker and (attempted or _has_evidence(resp)))


def _message_text(value: Any) -> str:
    """Best-effort extraction of text from Hermes/OpenAI-style message content."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        return "\n".join(parts)
    if value is None:
        return ""
    return str(value)


def _record_history_tool_evidence(session_id: str, conversation_history: list = None) -> None:
    """Backfill ledger evidence from conversation history when callbacks are unavailable."""
    if not session_id or not isinstance(conversation_history, list):
        return
    for msg in conversation_history[-80:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in {"tool", "function"}:
            continue
        content = _message_text(msg.get("content") or msg.get("result"))
        if not content.strip():
            continue
        tool_name = str(msg.get("name") or msg.get("tool_name") or "tool")
        tool_call_id = str(msg.get("tool_call_id") or msg.get("id") or "")
        record_tool_evidence(
            session_id,
            tool_name,
            {},
            content,
            tool_call_id=tool_call_id,
            source="conversation_history",
        )


def _successful_ledger_records(session_id: str) -> list[Dict[str, Any]]:
    state = get_state(session_id)
    records = getattr(state, "evidence_records", []) or []
    successful = []
    for record in records[-80:]:
        if not isinstance(record, dict):
            continue
        if record.get("is_error"):
            continue
        text = " ".join(
            str(record.get(key) or "")
            for key in ("tool_name", "args_preview", "result_preview")
        )
        if text.strip():
            successful.append(record)
    return successful


def _ledger_evidence_summary(session_id: str) -> str:
    records = _successful_ledger_records(session_id)
    if not records:
        return "no successful tool evidence in OMC ledger"
    tail = []
    for record in records[-3:]:
        tool = str(record.get("tool_name") or "tool")
        digest = str(record.get("result_sha256") or "")[:10]
        preview = str(record.get("result_preview") or "").replace("\n", " ")[:120]
        tail.append(f"{tool}#{digest}: {preview}")
    return " | ".join(tail)


def _check_ledger_evidence(session_id: str) -> Optional[Dict[str, Any]]:
    if _successful_ledger_records(session_id):
        return None
    return {
        "block": True,
        "type": "ralph:no_ledger_evidence",
        "message": (
            "[OMC Phase 3] Ralph 关闭被拦截: OMC evidence ledger 中没有真实工具/日志结果。"
            "不能只在回复里写“已完成/测试通过”。继续执行可验证工具调用，"
            "让 post_tool_call 记录命令输出、文件路径、测试日志或失败证据后再关闭。"
        ),
    }


def _independent_verifier_rejects_close(resp: str, session_id: str, score: int) -> Optional[Dict[str, Any]]:
    """Independent heuristic verifier: judge against OMC-owned state, not assistant claims alone."""
    failures = []
    state = get_state(session_id)

    if score < 99:
        failures.append(f"completion_score={score}/100")
    if not _successful_ledger_records(session_id):
        failures.append("缺少 OMC tool evidence ledger")
    if not _has_evidence(resp):
        failures.append("回复缺少文件/命令/日志证据")
    if not re.search(r"(?i)(pytest|tests? passed|passed in|exit code 0|测试通过|验证通过|命令输出|日志)", resp):
        failures.append("回复缺少测试或日志结果")
    if not re.search(r"(无待办|没有待办|无已知错误|没有已知错误|zero known errors|no pending work)", resp, re.I):
        failures.append("没有明确无待办/无已知错误")

    expected = int(getattr(state, "required_item_count", 0) or 0)
    if expected >= 2:
        mentions_expected = str(expected) in resp
        if not mentions_expected and not re.search(rf"{expected}\s*/\s*{expected}", resp):
            failures.append(f"没有覆盖用户声明范围 expected={expected}")

    if failures:
        return {
            "block": True,
            "type": "ralph:verifier_rejected",
            "message": (
                "[OMC Phase 3] 独立 verifier 拒绝关闭 Ralph: "
                + "；".join(failures)
                + "。继续执行并补充真实工具证据、范围证据、测试/日志证据。"
            ),
        }
    return None


def _check_required_audit_format(resp: str) -> Optional[Dict[str, Any]]:
    """Strict mode: require conclusion/evidence/correction fields in final answers."""
    if not resp or not resp.strip():
        return None
    has_conclusion = bool(re.search(r"(?:\*\*)?结论(?:\*\*)?\s*[:：]", resp))
    has_evidence = bool(re.search(r"(?:\*\*)?依据(?:\*\*)?\s*[:：]", resp))
    has_correction = bool(re.search(r"(?:\*\*)?修正\s*/\s*建议(?:\*\*)?\s*[:：]|(?:\*\*)?修正建议(?:\*\*)?\s*[:：]", resp))
    if has_conclusion and has_evidence and has_correction:
        return None
    missing = []
    if not has_conclusion:
        missing.append("结论")
    if not has_evidence:
        missing.append("依据")
    if not has_correction:
        missing.append("修正/建议")
    return {
        "block": True,
        "type": "omc:missing_audit_format",
        "message": (
            "必须重写本轮回复，输出标准监督格式：**结论**、**依据**、**修正/建议**。"
            f"缺失字段：{', '.join(missing)}。"
        ),
    }


def _is_destructive_or_credential_question(resp: str) -> bool:
    return bool(
        re.search(
            r"(删除|清空|覆盖|重置|重启|停机|生产|线上|付款|付费|扣费|凭证|密码|密钥|token|"
            r"rm\s+-rf|drop\s+table|reset\s+--hard)",
            resp,
            re.I,
        )
    )


def _question_escape(resp: str) -> bool:
    if _is_destructive_or_credential_question(resp) or len(resp) > 1400:
        return False
    return bool(
        re.search(
            r"(要我|需要我|是否需要我|要不要我|我可以|我能不能|可以继续|继续吗|是否继续).{0,80}[？?吗]",
            resp,
        )
    )


def _handoff_choice_escape(resp: str) -> bool:
    if _is_destructive_or_credential_question(resp) or len(resp) > 3000:
        return False
    option_block = re.search(
        r"(?ms)(下一步方向|下一步策略|后续方向|方案|选项|策略).{0,900}"
        r"^\s*(?:1[.、)]|①).{0,900}"
        r"^\s*(?:2[.、)]|②)",
        resp,
    )
    handoff_question = re.search(
        r"(老大)?(怎么推进|如何推进|下一步怎么|下一步.*(?:选|做|处理|推进)|"
        r"选哪|选择哪|走哪条|要走哪|你来定|您来定).{0,80}[？?]?",
        resp,
    )
    return bool(option_block and handoff_question)


def _check_general_anti_lazy(resp: str) -> Optional[Dict[str, Any]]:
    if not resp:
        return None
    checks = [
        (
            "known_invalid_stopped",
            bool(
                re.search(
                    r"(假阳性|跑偏|检测的是|不是原始|不是论文原文|输入对象|本轮.*无效|评分.*作废|"
                    r"结论.*作废|证据不足以|我错了|误判|不适用)",
                    resp,
                )
                and (
                    _question_escape(resp)
                    or (
                        len(resp) < 1600
                        and not re.search(r"(已作废|已撤销|已重跑|已改|已修复|已标记|已阻止|重新运行|改成|更正为)", resp)
                        and not _has_evidence(resp)
                    )
                )
            ),
            "已经识别本轮结论/输入无效，却停在请示或没有执行纠偏。",
        ),
        (
            "stopped_to_ask",
            _question_escape(resp) or _handoff_choice_escape(resp),
            "可逆任务中途停下来问“要不要/需要我”或列选项让用户决策，没有继续执行。",
        ),
        (
            "giveup_without_evidence",
            bool(
                re.search(
                    r"(无法完成|无法解决|无法继续|无法访问|无法连接|不能访问|不能完成|做不了|没法处理|"
                    r"暂时无法|目前无法|未能成功|建议你手动|需要手动|需要人工干预|超出我的能力|我不能)",
                    resp,
                )
                and not ("无法评估" in resp and re.search(r"(缺少|未提供|需要补充|证据不足|无法核验)", resp))
                and not _has_blocker_evidence(resp)
            ),
            "报告无法完成但缺少失败证据、重试记录或替代路径。",
        ),
        (
            "claimed_done_no_evidence",
            bool(
                re.search(
                    r"(我已|已经|已)(完成|实现|创建|修复|解决|添加|更新|部署|验证|接入|集成)|"
                    r"(完成了|修好了|解决了|搞定了|测试通过)",
                    resp,
                )
                and not _has_evidence(resp)
            ),
            "宣称完成/修复/验证，但没有文件路径、命令输出或测试证据。",
        ),
    ]
    for kind, matched, reason in checks:
        if matched:
            return {
                "block": True,
                "type": f"omc:{kind}",
                "message": (
                    f"违规类型: {kind}\n"
                    f"原因: {reason}\n"
                    "要求: 禁止只输出纠偏口号或模板话；"
                    "必须先执行至少一个安全可逆且可验证的纠偏动作；"
                    "无法完成要给失败证据和替代路径；已完成要给文件路径、命令输出、测试或日志证据。"
                ),
            }
    return None


def _is_ralph_close_claim(resp: str) -> bool:
    return bool(
        re.search(
            r"(ralph\s*(?:完成|关闭|结束|complete|done|close)|"
            r"(?:任务|本轮|全部|整体).{0,12}(?:完成|结束|收尾)|"
            r"(?:已|已经).{0,8}(?:全部|完全|整体)?.{0,8}(?:完成|修复完成|验证完成)|"
            r"可以结束|可以关闭|收工)",
            resp,
            re.I,
        )
    )


def _extract_completion_counts(resp: str) -> Dict[str, Any]:
    """Extract assistant-claimed completion counts from a closing report."""
    ratios = []
    scalar_counts = []

    for done, total in re.findall(r"(?<!\d)(\d{1,6})\s*/\s*(\d{1,6})(?!\d)", resp):
        try:
            ratios.append((int(done), int(total)))
        except ValueError:
            continue

    unit_pattern = "|".join(re.escape(u) for u in _TASK_COUNT_UNITS)
    completion_patterns = (
        rf"(?:已完成|完成|处理完成|验证完成|入库|下载|生成|修复)\D{{0,16}}(\d{{1,6}})\s*(?:{unit_pattern})",
        rf"(\d{{1,6}})\s*(?:{unit_pattern})\D{{0,16}}(?:已完成|完成|处理完成|验证完成|入库|下载|生成|修复)",
    )
    for pattern in completion_patterns:
        for match in re.finditer(pattern, resp, re.I):
            try:
                scalar_counts.append(int(match.group(1)))
            except ValueError:
                continue

    return {"ratios": ratios, "counts": scalar_counts}


def _check_ralph_scope_completion(resp: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Block scope shrinkage: assistant completion cannot reduce user-declared task size."""
    state = get_state(session_id)
    expected = int(getattr(state, "required_item_count", 0) or 0)
    if expected < 2:
        return None

    extracted = _extract_completion_counts(resp)
    ratios = extracted["ratios"]
    counts = extracted["counts"]
    mentions_expected = str(expected) in resp

    for done, total in ratios:
        if total < expected:
            return {
                "block": True,
                "type": "ralph:scope_mismatch",
                "message": (
                    f"[OMC Phase 3] 任务规模被缩小: OMC ledger expected={expected}，"
                    f"回复只声明 {done}/{total}。禁止把用户原始任务缩成更小范围后关闭 Ralph。"
                ),
            }
        if total >= expected and done < expected:
            return {
                "block": True,
                "type": "ralph:scope_incomplete",
                "message": (
                    f"[OMC Phase 3] 批量任务未完成: OMC ledger expected={expected}，"
                    f"回复声明 {done}/{total}。继续执行剩余项并提供失败/完成证据。"
                ),
            }

    if counts:
        max_count = max(counts)
        if max_count < expected and not mentions_expected:
            return {
                "block": True,
                "type": "ralph:scope_mismatch",
                "message": (
                    f"[OMC Phase 3] 任务规模被缩小: OMC ledger expected={expected}，"
                    f"回复最大完成数只有 {max_count}。禁止用局部完成冒充全部完成。"
                ),
            }

    if not mentions_expected and not any(total >= expected for _, total in ratios):
        return {
            "block": True,
            "type": "ralph:scope_unproven",
            "message": (
                f"[OMC Phase 3] 缺少全量范围证据: OMC ledger expected={expected}，"
                "关闭报告没有证明覆盖该数量。必须给出 expected/expected、全量清单路径、"
                "批处理日志或等价证据后才允许关闭 Ralph。"
            ),
        }

    return None


def _ralph_completion_score(resp: str) -> int:
    """Heuristic close gate: only 99+ can close Ralph."""
    score = 0
    if _is_ralph_close_claim(resp):
        score += 20
    if _has_evidence(resp):
        score += 20
    if re.search(r"(?i)(pytest|tests? passed|passed in|exit code 0|测试通过|验证通过|命令输出|日志)", resp):
        score += 25
    if re.search(r"(改动文件|修改文件|changed files?|/[\w.\- \u4e00-\u9fff/]+\.(?:py|js|ts|md|json|yaml|yml|sh|txt|log))", resp, re.I):
        score += 20
    if re.search(r"(无待办|没有待办|无已知错误|没有已知错误|zero known errors|no pending work|remaining risks?|剩余风险)", resp, re.I):
        score += 15
    return min(score, 100)


def _check_ralph_v2(resp: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Phase 3: 禁止放弃、禁止问问题、禁止谎称完成"""
    if not resp:
        return {"block": True, "type": "ralph:empty",
                "message": "[OMC Phase 3] Continue executing. Do NOT give up."}

    rl = resp.lower().strip()

    if "?" in rl or "？" in rl:
        reset_ralph_close_checks(session_id)
        return {
            "block": True,
            "type": "ralph:question_mark",
            "message": "[OMC Phase 3] 回复包含问号会被打回。Ralph 阶段不能提问，必须继续执行。",
        }

    # 停下来问问题
    ask = ["请问您", "您希望", "您想要", "您可以", "能否告诉我", "能否确认", "是否需要", "我想确认一下", "需要我", "需要您", "我可以继续吗",
           "这样做可以吗", "我有一个问题", "有个疑问", "想问一下"]
    for p in ask:
        if p in rl and len(resp) < 500:
            reset_ralph_close_checks(session_id)
            return {"block": True, "type": "ralph:stopped_to_ask",
                    "message": "[OMC Phase 3] DO NOT stop to ask questions. Continue executing with tool calls."}

    if _is_ralph_close_claim(resp):
        scope_result = _check_ralph_scope_completion(resp, session_id)
        if scope_result:
            reset_ralph_close_checks(session_id)
            return scope_result
        ledger_result = _check_ledger_evidence(session_id)
        if ledger_result:
            reset_ralph_close_checks(session_id)
            return ledger_result
        score = _ralph_completion_score(resp)
        if score < 99:
            reset_ralph_close_checks(session_id)
            return {
                "block": True,
                "type": "ralph:premature_close",
                "message": (
                    f"[OMC Phase 3] Ralph 关闭被拦截: completion_score={score}/100。"
                    "只有 >=99/100 且包含改动文件、命令/测试/日志证据、验证通过、"
                    "无待办/无已知错误声明时才允许关闭 Ralph。请恢复执行。"
                ),
            }
        verifier_result = _independent_verifier_rejects_close(resp, session_id, score)
        if verifier_result:
            reset_ralph_close_checks(session_id)
            return verifier_result
        close_checks = increment_ralph_close_checks(session_id)
        if close_checks < 3:
            return {
                "block": True,
                "type": "ralph:close_check_not_enough",
                "message": f"[OMC Phase 3] Ralph 关闭通过核验不足 {close_checks}/3，继续执行并补充可验证证据，给出第3次核验收官。",
            }
        mark_completed(session_id, f"score={score}; evidence={_ledger_evidence_summary(session_id)}")
        logger.info("[omh-enforcer] Ralph completed with score=%s session=%s", score, session_id)
        return None

    # 放弃
    giveup = ["我放弃了", "放弃尝试", "无法完成", "无法解决", "超出了我的能力", "建议你手动", "需要人工干预", "需要手动", "暂时无法", "目前无法", "未能成功", "超出我的能力"]
    for p in giveup:
        if p in rl and len(resp) < 600:
            has_hw = any(hw in rl for hw in ["硬件", "物理设备", "传感器", "实际设备"])
            if not has_hw:
                return {"block": True, "type": "ralph:giveup",
                        "message": "[OMC Phase 3] Don't give up. Try a different approach."}

    # 谎称完成但无证据
    claims = ["已经完成", "已完成", "已经实现", "已经创建", "已经修复", "已经解决", "已经添加"]
    for c in claims:
        if c in rl:
            reset_ralph_close_checks(session_id)
            has_ev = (bool(re.search(r'[~/][a-zA-Z0-9/_-]+', resp)) or
                      '```' in resp or
                      any(cmd in resp for cmd in ['mkdir', 'touch', 'write_file', 'terminal', 'curl']))
            if not has_ev:
                return {"block": True, "type": "ralph:claimed_done_no_evidence",
                        "message": "[OMC Phase 3] You claimed completion but provided no evidence. Show file paths or command output."}
    return None


# Public aliases used by plugins/omh/__init__.py registration.
enforcer_on_session_start = _on_session_start
enforcer_pre_llm_call = _pre_llm_call
enforcer_post_llm_call = _on_post_llm_call
enforcer_pre_tool_call = _on_pre_tool_call
enforcer_post_tool_call = _on_post_tool_call
enforcer_pre_gateway_send = _on_pre_gateway_send
enforcer_on_session_end = _on_session_end


__all__ = [
    "WorkflowPhase",
    "enforcer_on_session_start",
    "enforcer_pre_llm_call",
    "enforcer_post_llm_call",
    "enforcer_pre_tool_call",
    "enforcer_post_tool_call",
    "enforcer_pre_gateway_send",
    "enforcer_on_session_end",
    "_detect_quick_command",
    "_is_likely_task",
]
