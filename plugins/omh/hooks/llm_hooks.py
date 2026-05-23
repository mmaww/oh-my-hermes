"""
pre_llm_call hook — inject OMH mode awareness and role prompts into each turn.

On the first turn of a session:
  - If user_message contains an [omh-role:NAME] marker: inject the full role prompt.
  - If OMH modes are active: inject full context listing all active modes.
On subsequent turns: brief reminder with current mode/phase/iteration.
Returns None when neither role markers nor active modes are present (zero overhead).
"""

import logging
import os
from typing import Any

from ..omh_roles import debug_print, extract_role_marker, load_role_prompt
from ..omh_state import state_list_active
from ..omh_task_memory import append_assistant_turn, prepare_task_memory_context
from ..omh_keywords import keyword_routing_context
from ..omh_skill_injection import custom_skill_context

logger = logging.getLogger(__name__)


def _resolve_session_id(kwargs: dict[str, Any]) -> str:
    """Best-effort session_id resolution from runtime kwargs / metadata / env.

    This keeps task-memory injection stable even when adapters use alternate
    field names for session correlation.
    """
    for key in ("session_id", "hermes_session_id", "conversation_id", "chat_id"):
        value = kwargs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = kwargs.get("user_metadata")
    if isinstance(metadata, dict):
        for key in ("hermes_session_id", "session_id", "conversation_id", "chat_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    value = os.environ.get("HERMES_SESSION_ID")
    if isinstance(value, str) and value.strip():
        return value.strip()

    return ""


def pre_llm_call(**kwargs) -> dict | None:
    """Inject role prompt and/or OMH mode context before each LLM call."""
    is_first_turn = kwargs.get("is_first_turn", False)
    session_id = _resolve_session_id(kwargs)
    if is_first_turn:
        preview = (kwargs.get("user_message") or "")[:80].replace("\n", "\\n")
        debug_print(f"pre_llm_call: first_turn user_message preview: {preview!r}")
    if not is_first_turn and "is_first_turn" not in kwargs:
        logger.debug(
            "pre_llm_call: 'is_first_turn' kwarg not provided by Hermes runtime; "
            "first-turn full-context branch inactive for this call"
        )

    context_parts = []

    # --- Role prompt injection (first turn only) ---
    if is_first_turn:
        user_message = kwargs.get("user_message", "") or ""
        route_context = keyword_routing_context(user_message)
        if route_context is not None:
            debug_print("pre_llm_call: injecting keyword routing context")
            context_parts.append(route_context)
        skill_context = custom_skill_context(user_message)
        if skill_context is not None:
            debug_print("pre_llm_call: injecting custom skill context")
            context_parts.append(skill_context)
        role_name = extract_role_marker(user_message)
        if role_name is not None:
            role_prompt = load_role_prompt(role_name)
            if role_prompt is not None:
                debug_print(f"pre_llm_call: injecting role '{role_name}' into subagent system prompt")
                context_parts.append(f"[OMH Role: {role_name}]\n{role_prompt}")
            else:
                from ..omh_roles import get_role_catalog
                available = ", ".join(sorted(get_role_catalog().keys())) or "(none)"
                logger.warning(
                    "pre_llm_call: unknown role '%s' requested via marker. Available: %s",
                    role_name, available,
                )
                debug_print(f"pre_llm_call: unknown role '{role_name}' — no injection. Available: {available}")
                context_parts.append(
                    f"[OMH WARNING] Unknown role '{role_name}' requested. "
                    f"Available roles: {available}. No role prompt was injected."
                )

    # --- Mode awareness injection ---
    try:
        active = state_list_active()
    except Exception as e:
        logger.debug("pre_llm_call: state_list_active error: %s", e)
        active = {}

    if active.get("modes"):
        if is_first_turn:
            lines = ["[OMH] Active modes detected — read state before proceeding:"]
            for m in active["modes"]:
                age = m.get("age_seconds", "?")
                phase = m.get("phase") or "?"
                lines.append(f"  - {m['mode']}: phase={phase}, age={age}s")
            lines.append(
                "Use omh_state(action='read', mode='<mode>') to load current state "
                "and continue from where you left off."
            )
            context_parts.append("\n".join(lines))
        else:
            modes = active["modes"]
            if len(modes) == 1:
                mode = modes[0]
                mode_str = f"{mode['mode']} (phase: {mode.get('phase') or '?'})"
            else:
                parts = [f"{m['mode']}:{m.get('phase') or '?'}" for m in modes]
                mode_str = ", ".join(parts)
            first_mode = modes[0]["mode"]
            context_parts.append(
                f"[OMH] Active: {mode_str}. "
                f"Use omh_state(action='cancel_check', mode='{first_mode}') "
                f"to check for cancellation before continuing. "
                f"Use omh_state(action='read', mode='<mode>') to reload state if needed."
            )

    # --- Task memory (must inject per task on every call when session_id is present) ---
    if session_id:
        try:
            user_message = kwargs.get("user_message") or ""
            memory_context = prepare_task_memory_context(
                session_id=session_id,
                user_message=user_message,
                is_first_turn=is_first_turn,
            )
            if memory_context:
                context_parts.append(memory_context)
        except Exception as e:
            logger.warning(
                "pre_llm_call: failed to load task memory (session=%s): %s",
                session_id,
                e,
            )

    if not context_parts:
        return None
    return {"context": "\n\n".join(context_parts)}


def post_llm_call(**kwargs) -> None:
    """Persist assistant response into the active task-memory file."""
    session_id = _resolve_session_id(kwargs)
    assistant_response = kwargs.get("assistant_response", "")
    if not session_id:
        return None
    try:
        append_assistant_turn(session_id, assistant_response)
    except Exception as e:
        logger.warning(
            "post_llm_call: failed to persist task memory (session=%s): %s",
            session_id,
            e,
        )
    return None
