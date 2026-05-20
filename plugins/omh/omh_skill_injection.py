"""Custom skill auto-injection helpers for OMH.

OMC's core workflow auto-loads user/project skills based on trigger matches.
This module provides the same behavior for Hermes sessions by injecting a
bounded summary of matched custom skills into first-turn context.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_URL_RE = re.compile(r"https?://\S+")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class InjectedSkill:
    scope: str
    name: str
    path: Path
    triggers: tuple[str, ...]
    body_excerpt: str


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser().resolve()


def _custom_skill_roots() -> list[tuple[str, Path]]:
    return [
        ("project", Path.cwd() / ".omh" / "skills"),
        ("user", _hermes_home() / "skills" / "omh"),
    ]


def _candidate_skill_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for scope, root in _custom_skill_roots():
        if not root.exists():
            continue
        for item in sorted(root.iterdir()):
            if item.is_dir() and (item / "SKILL.md").exists():
                files.append((scope, item / "SKILL.md"))
            elif item.is_file() and item.suffix.lower() == ".md":
                files.append((scope, item))
    return files


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    frontmatter_raw = match.group(1)
    body = raw[match.end():]
    try:
        import yaml
        loaded = yaml.safe_load(frontmatter_raw) or {}
        if isinstance(loaded, dict):
            return loaded, body
    except Exception:
        pass
    return {}, body


def _extract_triggers(frontmatter: dict) -> list[str]:
    values: list[str] = []
    top = frontmatter.get("triggers")
    if isinstance(top, list):
        values.extend(str(v).strip() for v in top if str(v).strip())

    metadata = frontmatter.get("metadata")
    if isinstance(metadata, dict):
        hermes = metadata.get("hermes")
        if isinstance(hermes, dict):
            tags = hermes.get("tags")
            if isinstance(tags, list):
                values.extend(str(v).strip() for v in tags if str(v).strip())

    # Deduplicate case-insensitively, preserve order.
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _sanitize_prompt(prompt: str) -> str:
    text = _FENCE_RE.sub(" ", prompt)
    text = _INLINE_CODE_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip().lower()


def _trigger_matches(prompt: str, trigger: str) -> bool:
    trigger_norm = trigger.strip().lower()
    if not trigger_norm:
        return False
    if re.fullmatch(r"[a-z0-9_-]+", trigger_norm):
        return re.search(rf"(?<![a-z0-9]){re.escape(trigger_norm)}(?![a-z0-9])", prompt) is not None
    return trigger_norm in prompt


def matched_custom_skills(prompt: str, max_results: int = 3) -> list[InjectedSkill]:
    """Return up to max_results matched custom skills for prompt."""
    cleaned = _sanitize_prompt(prompt or "")
    if not cleaned:
        return []

    results: list[InjectedSkill] = []
    for scope, path in _candidate_skill_files():
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        frontmatter, body = _parse_frontmatter(raw)
        triggers = _extract_triggers(frontmatter)
        if not triggers:
            continue
        if not any(_trigger_matches(cleaned, trig) for trig in triggers):
            continue
        name = str(frontmatter.get("name") or path.parent.name or path.stem).strip()
        excerpt = _SPACE_RE.sub(" ", body).strip()[:900]
        results.append(InjectedSkill(
            scope=scope,
            name=name or path.stem,
            path=path,
            triggers=tuple(triggers),
            body_excerpt=excerpt,
        ))
        if len(results) >= max_results:
            break
    return results


def custom_skill_context(prompt: str, max_results: int = 3) -> str | None:
    """Build first-turn context for matched custom skills."""
    matches = matched_custom_skills(prompt, max_results=max_results)
    if not matches:
        return None

    lines = [
        "[OMH custom skill auto-inject]",
        f"Matched {len(matches)} custom skill(s) by trigger.",
    ]
    for idx, skill in enumerate(matches, start=1):
        trigger_line = ", ".join(skill.triggers[:8]) or "(none)"
        lines.extend([
            f"{idx}. {skill.name} [{skill.scope}]",
            f"   triggers: {trigger_line}",
            f"   path: {skill.path}",
            "   guidance:",
            f"   {skill.body_excerpt}",
        ])
    return "\n".join(lines)

