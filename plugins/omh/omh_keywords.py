"""Keyword routing helpers for OMH.

Hermes does not have Claude Code's UserPromptSubmit hook, so OMH implements a
lightweight equivalent inside pre_llm_call. The hook does not execute skills by
itself; it injects routing context that tells the active agent which OMH skill
or CLI surface is the deterministic match for the user's first-turn prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KeywordRoute:
    name: str
    surface: str
    reason: str
    priority: int


_ROUTES: tuple[tuple[re.Pattern[str], KeywordRoute], ...] = (
    (re.compile(r"(?i)(^|\b)(cancelomc|stopomc|cancel\s+omh|stop\s+omh|取消\s*omh)(\b|$)"),
     KeywordRoute("cancel", "omh cancel", "stop active OMH modes", 100)),
    (re.compile(r"(?i)(^|\b)(autopilot|自动驾驶|全自动)(\b|:)"),
     KeywordRoute("autopilot", "omh-autopilot", "end-to-end autonomous execution", 90)),
    (re.compile(r"(?i)(^|\b)(ralph|persistent\s+mode|持续执行)(\b|:)"),
     KeywordRoute("ralph", "omh-ralph", "persistent execute/verify loop", 85)),
    (re.compile(r"(?i)(^|\b)(ultrawork|ulw|parallel\s+burst|最大并行)(\b|:)"),
     KeywordRoute("ultrawork", "omh-ultrawork", "parallel non-team execution", 80)),
    (re.compile(r"(?i)(^|\b)(ralplan|consensus\s+plan|共识计划)(\b|:)"),
     KeywordRoute("ralplan", "omh-ralplan", "multi-role consensus planning", 75)),
    (re.compile(r"(?i)(deep[-\s]?interview|需求访谈|深度访谈)"),
     KeywordRoute("deep-interview", "omh-deep-interview", "Socratic requirements clarification", 70)),
    (re.compile(r"(?i)(deep[-\s]?research|deepsearch|深入调研|深度研究)"),
     KeywordRoute("deep-research", "omh-deep-research", "multi-source research synthesis", 65)),
    (re.compile(r"(?i)(^|\b)(/team|team\s+\d+:[a-zA-Z0-9_-]+|omh\s+team)(\b|$)"),
     KeywordRoute("team", "omh-team / omh team", "team or tmux worker orchestration", 60)),
    (re.compile(r"(?i)(^|\b)(/ccg|ccg)(\b|:)"),
     KeywordRoute("ccg", "omh-ccg", "Codex + Gemini advisor synthesis", 55)),
    (re.compile(r"(?i)(^|\b)(hud|statusline|状态栏|运行状态)(\b|$)"),
     KeywordRoute("hud", "omh-hud / omh hud", "runtime visibility", 40)),
)


_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_URL_RE = re.compile(r"https?://\S+")


def _sanitize_prompt(prompt: str) -> str:
    text = _FENCE_RE.sub(" ", prompt)
    text = _INLINE_CODE_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    return text


def detect_keyword_routes(prompt: str) -> list[KeywordRoute]:
    """Return matching keyword routes ordered by priority."""
    text = _sanitize_prompt(prompt or "")
    matches = [route for pattern, route in _ROUTES if pattern.search(text)]
    return sorted(matches, key=lambda r: r.priority, reverse=True)


def keyword_routing_context(prompt: str) -> str | None:
    """Build hook context for first-turn prompt routing."""
    routes = detect_keyword_routes(prompt)
    if not routes:
        return None
    primary = routes[0]
    lines = [
        "[OMH keyword routing]",
        f"Detected: {primary.name}",
        f"Route: {primary.surface}",
        f"Reason: {primary.reason}",
    ]
    if len(routes) > 1:
        secondary = ", ".join(r.name for r in routes[1:])
        lines.append(f"Secondary matches: {secondary}")
    if primary.name == "cancel":
        lines.append("Action: inspect active state with omh_state(action='status'), then request cancellation with omh_state(action='cancel', mode=...).")
    elif primary.surface.startswith("omh-"):
        lines.append(f"Action: load and follow the `{primary.surface}` skill for this turn.")
    else:
        lines.append(f"Action: use `{primary.surface}` as the appropriate OMH surface.")
    return "\n".join(lines)
