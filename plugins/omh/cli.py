"""Command line surface for Oh My Hermes.

The CLI intentionally stays small and dependency-free. It mirrors the OMC
README's outer surfaces for Hermes users:

  omh setup      install plugin and bundled skills
  omh doctor     validate the local install
  omh status     inspect .omh runtime state
  omh hud        one-line status summary
  omh ask        run a local provider CLI and save an artifact
  omh team       launch tmux-backed provider workers
  omh cancel     request cancellation for active OMH modes
  omh skill      manage project/user skill files
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .omh_roles import load_role_prompt
from .omh_state import state_cancel, state_init, state_status


PLUGIN_DIR = Path(__file__).resolve().parent
REPO_ROOT = PLUGIN_DIR.parent.parent
SKILLS_DIR = PLUGIN_DIR / "skills"
ROLE_DIR = PLUGIN_DIR / "references"


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str, default: str = "task", max_len: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        slug = default
    return slug[:max_len].strip("-") or default


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser().resolve()


def _json_or_print(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    for line in payload.get("lines", []):
        print(line)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _install_link(src: Path, dest: Path, *, copy: bool, force: bool,
                  dry_run: bool) -> dict:
    src = src.resolve()
    dest = dest.expanduser().resolve()
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() and dest.resolve() == src:
            return {"target": str(dest), "status": "already-linked"}
        if not force:
            return {"target": str(dest), "status": "exists", "hint": "use --force to replace"}
        if not dry_run:
            _remove_path(dest)

    if dry_run:
        return {"target": str(dest), "status": "would-copy" if copy else "would-link"}

    dest.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        return {"target": str(dest), "status": "copied"}

    dest.symlink_to(src, target_is_directory=src.is_dir())
    return {"target": str(dest), "status": "linked"}


def cmd_setup(args: argparse.Namespace) -> int:
    home = _hermes_home()
    plugin_dest = home / "plugins" / "omh"
    skills_dest = home / "skills" / "omh"

    actions: list[dict] = []
    actions.append(_install_link(
        PLUGIN_DIR, plugin_dest, copy=args.copy, force=args.force, dry_run=args.dry_run,
    ))

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        actions.append(_install_link(
            skill_dir,
            skills_dest / skill_dir.name,
            copy=args.copy,
            force=args.force,
            dry_run=args.dry_run,
        ))

    init_result = None
    if not args.no_project_init and not args.dry_run:
        init_result = state_init()

    payload = {
        "success": True,
        "hermes_home": str(home),
        "plugin": str(plugin_dest),
        "skills_root": str(skills_dest),
        "actions": actions,
        "project_init": init_result,
        "lines": [
            f"OMH setup target: {home}",
            f"Plugin: {actions[0]['status']} -> {plugin_dest}",
            f"Skills processed: {len(actions) - 1}",
        ],
    }
    if init_result:
        payload["lines"].append(f"Project .omh: {init_result['omh_dir']}")
    payload["lines"].append("Restart Hermes so plugin hooks and bundled skills are reloaded.")
    _json_or_print(payload, args.json)
    return 0


def _check(name: str, ok: bool, detail: str = "", required: bool = True) -> dict:
    return {"name": name, "ok": ok, "detail": detail, "required": required}


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[dict] = []
    checks.append(_check("python>=3.10", sys.version_info >= (3, 10),
                         f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))
    try:
        import yaml  # noqa: F401
        checks.append(_check("pyyaml", True, "import ok"))
    except Exception as exc:
        checks.append(_check("pyyaml", False, str(exc)))

    checks.append(_check("plugin.yaml", (PLUGIN_DIR / "plugin.yaml").is_file(),
                         str(PLUGIN_DIR / "plugin.yaml")))
    checks.append(_check("config.yaml", (PLUGIN_DIR / "config.yaml").is_file(),
                         str(PLUGIN_DIR / "config.yaml")))
    skill_count = len([p for p in SKILLS_DIR.iterdir() if p.is_dir()]) if SKILLS_DIR.exists() else 0
    checks.append(_check("bundled skills", skill_count > 0, f"{skill_count} found"))

    home = _hermes_home()
    checks.append(_check("installed plugin", (home / "plugins" / "omh").exists(),
                         str(home / "plugins" / "omh"), required=False))
    checks.append(_check("installed skills", (home / "skills" / "omh").exists(),
                         str(home / "skills" / "omh"), required=False))

    for exe in ["hermes", "tmux", "claude", "codex", "gemini"]:
        checks.append(_check(f"optional cli: {exe}", shutil.which(exe) is not None,
                             shutil.which(exe) or "not found", required=False))

    ok = all(c["ok"] for c in checks if c["required"])
    payload = {"success": ok, "checks": checks}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for c in checks:
            mark = "ok" if c["ok"] else ("warn" if not c["required"] else "fail")
            print(f"[{mark}] {c['name']}: {c['detail']}")
    return 0 if ok else 1


def _format_status(snapshot: dict) -> list[str]:
    lines = [
        f"state_dir: {snapshot.get('state_dir')}",
        f"active_count: {snapshot.get('active_count', 0)}",
    ]
    states = snapshot.get("states") or []
    if not states:
        lines.append("states: none")
    else:
        lines.append("states:")
        for st in states:
            ident = st["mode"] + (f"/{st.get('instance_id')}" if st.get("instance_id") else "")
            phase = st.get("phase") or "?"
            active = "active" if st.get("active") else "inactive"
            stale = ", stale" if st.get("stale") else ""
            lines.append(f"  - {ident}: {active}, phase={phase}, age={st.get('age_seconds')}s{stale}")

    locks = snapshot.get("locks")
    if locks is not None:
        held = [l for l in locks if l.get("held")]
        lines.append(f"locks: {len(held)} held / {len(locks)} total")
    return lines


def cmd_status(args: argparse.Namespace) -> int:
    snapshot = state_status(
        include_inactive=args.include_inactive,
        include_locks=not args.no_locks,
    )
    if args.json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    else:
        print("\n".join(_format_status(snapshot)))
    return 0


def cmd_hud(args: argparse.Namespace) -> int:
    snapshot = state_status(include_inactive=False, include_locks=True)
    states = snapshot.get("states") or []
    modes = ", ".join(
        s["mode"] + (f"/{s.get('instance_id')}" if s.get("instance_id") else "")
        for s in states
    ) or "idle"
    held_locks = sum(1 for l in snapshot.get("locks", []) if l.get("held"))
    line = f"OMH active={snapshot.get('active_count', 0)} locks={held_locks} modes={modes}"
    if args.json:
        print(json.dumps({"hud": line, "snapshot": snapshot}, indent=2, ensure_ascii=False))
    else:
        print(line)
    return 0


def _provider_command(provider: str, prompt: str, command_override: str | None = None) -> list[str]:
    if command_override:
        if "{prompt}" in command_override:
            return shlex.split(command_override.format(prompt=prompt))
        return shlex.split(command_override) + [prompt]

    commands = {
        "claude": ["claude", "-p", prompt],
        "codex": ["codex", "exec", prompt],
        "gemini": ["gemini", "-p", prompt],
        "hermes": ["hermes", "-p", prompt],
    }
    if provider not in commands:
        raise ValueError(f"unknown provider: {provider}")
    return commands[provider]


def _with_role_prompt(prompt: str, role: str | None) -> str:
    if not role:
        return prompt
    role_prompt = load_role_prompt(role)
    if role_prompt is None:
        raise ValueError(f"unknown OMH role: {role}")
    return f"[OMH role: {role}]\n\n{role_prompt}\n\n[Task]\n{prompt}"


def _artifact_dir(project_root: Path) -> Path:
    out = project_root / ".omh" / "artifacts" / "ask"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _write_ask_artifact(project_root: Path, provider: str, prompt: str,
                        command: list[str], result: dict) -> Path:
    slug = _slugify(prompt)
    path = _artifact_dir(project_root) / f"{_now_compact()}-{provider}-{slug}.md"
    cmd_display = " ".join(shlex.quote(part) for part in command)
    body = textwrap.dedent(f"""\
    ---
    provider: {provider}
    exit_code: {result.get('exit_code')}
    generated_at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}
    ---

    # OMH Ask Artifact

    ## Prompt

    ```text
    {prompt}
    ```

    ## Command

    ```bash
    {cmd_display}
    ```

    ## stdout

    ```text
    {result.get('stdout', '')}
    ```

    ## stderr

    ```text
    {result.get('stderr', '')}
    ```
    """)
    path.write_text(body, encoding="utf-8")
    return path


def cmd_ask(args: argparse.Namespace) -> int:
    prompt = args.prompt or " ".join(args.prompt_parts or [])
    if not prompt.strip():
        print("omh ask: prompt is required", file=sys.stderr)
        return 2

    project_root = Path(args.workdir or os.getcwd()).resolve()
    full_prompt = _with_role_prompt(prompt, args.agent_prompt)
    command = _provider_command(args.provider, full_prompt, args.command)

    result = {"exit_code": None, "stdout": "", "stderr": "", "dry_run": args.dry_run}
    if args.dry_run:
        result["exit_code"] = 0
        result["stdout"] = "dry run; command not executed"
    elif shutil.which(command[0]) is None:
        result["exit_code"] = 127
        result["stderr"] = f"provider executable not found: {command[0]}"
    else:
        try:
            proc = subprocess.run(
                command,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=args.timeout,
                shell=False,
            )
            result.update({
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
        except subprocess.TimeoutExpired as exc:
            result.update({
                "exit_code": 124,
                "stdout": exc.stdout or "",
                "stderr": f"TIMEOUT after {args.timeout}s",
            })

    artifact = _write_ask_artifact(project_root, args.provider, prompt, command, result)
    payload = {**result, "artifact": str(artifact), "command": command}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"artifact: {artifact}")
        print(f"exit_code: {result['exit_code']}")
        if result["stderr"] and result["exit_code"] != 0:
            print(result["stderr"], file=sys.stderr)
    return int(result["exit_code"] or 0)


def _team_specs(tokens: list[str]) -> tuple[list[tuple[int, str]], list[str]]:
    specs: list[tuple[int, str]] = []
    rest: list[str] = []
    spec_re = re.compile(r"^(\d+):([a-zA-Z0-9_-]+)$")
    for token in tokens:
        match = spec_re.match(token)
        if match and not rest:
            count = int(match.group(1))
            if count <= 0:
                raise ValueError("worker count must be positive")
            specs.append((count, match.group(2)))
        else:
            rest.append(token)
    return specs, rest


def _parse_team_options(tokens: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(prog="omh team", add_help=False)
    parser.add_argument("--session")
    parser.add_argument("--workdir", default=os.getcwd())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    opts, remaining = parser.parse_known_args(tokens)
    return opts, remaining


def _worker_shell(provider: str, prompt: str, log_path: Path,
                  index: int, total: int, command_override: str | None = None) -> str:
    worker_prompt = (
        f"[OMH team worker {index}/{total}; provider={provider}]\n\n"
        f"{prompt}\n\nReturn a concise report with findings, files touched, tests run, and blockers."
    )
    try:
        command = _provider_command(provider, worker_prompt, command_override)
    except ValueError:
        command = [provider, worker_prompt]
    if shutil.which(command[0]) is None:
        body = f"echo 'provider executable not found: {shlex.quote(command[0])}'"
    else:
        body = " ".join(shlex.quote(part) for part in command)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return (
        "bash -lc "
        + shlex.quote(
            "set -o pipefail; "
            f"echo '[OMH team] worker {index}/{total} provider={provider}'; "
            f"({body}) 2>&1 | tee {shlex.quote(str(log_path))}; "
            "echo '[OMH team] worker finished; press Ctrl-D to close shell'; "
            "exec bash"
        )
    )


def _tmux_sessions() -> list[str]:
    proc = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def cmd_team(args: argparse.Namespace) -> int:
    tokens = list(args.team_args or [])
    if not tokens:
        print("usage: omh team [status|shutdown] OR omh team N:provider 'task'", file=sys.stderr)
        return 2

    action = tokens[0]
    if action in {"status", "list"}:
        if shutil.which("tmux") is None:
            print("tmux not found", file=sys.stderr)
            return 127
        sessions = [s for s in _tmux_sessions() if s.startswith("omh-")]
        print(json.dumps({"sessions": sessions}, indent=2) if "--json" in tokens else "\n".join(sessions or ["no OMH tmux sessions"]))
        return 0

    if action in {"shutdown", "kill"}:
        if len(tokens) < 2:
            print("omh team shutdown requires a session name", file=sys.stderr)
            return 2
        if shutil.which("tmux") is None:
            print("tmux not found", file=sys.stderr)
            return 127
        proc = subprocess.run(["tmux", "kill-session", "-t", tokens[1]], capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode

    opts = args
    specs, prompt_tokens = _team_specs(tokens)
    if not specs:
        print("omh team: at least one N:provider spec is required", file=sys.stderr)
        return 2
    prompt = " ".join(prompt_tokens).strip()
    if not prompt:
        print("omh team: task prompt is required", file=sys.stderr)
        return 2

    workdir = Path(opts.workdir).resolve()
    session = opts.session or f"omh-{_slugify(prompt, max_len=36)}-{_now_compact()}"
    total = sum(count for count, _ in specs)
    team_dir = workdir / ".omh" / "team" / session
    team_dir.mkdir(parents=True, exist_ok=True)

    commands: list[str] = []
    worker_index = 0
    for count, provider in specs:
        for _ in range(count):
            worker_index += 1
            log_path = team_dir / f"worker-{worker_index:02d}-{provider}.log"
            commands.append(_worker_shell(provider, prompt, log_path, worker_index, total))

    plan = {"session": session, "workdir": str(workdir), "workers": total, "logs": str(team_dir)}
    if opts.dry_run:
        print(json.dumps({**plan, "commands": commands}, indent=2, ensure_ascii=False))
        return 0

    if shutil.which("tmux") is None:
        print("tmux not found; install tmux or run with --dry-run", file=sys.stderr)
        return 127

    first, *rest = commands
    proc = subprocess.run(["tmux", "new-session", "-d", "-s", session, "-c", str(workdir), first],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode
    for command in rest:
        subprocess.run(["tmux", "split-window", "-t", session, "-c", str(workdir), command],
                       check=False)
        subprocess.run(["tmux", "select-layout", "-t", session, "tiled"], check=False)

    if opts.json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(f"tmux session: {session}")
        print(f"attach: tmux attach -t {session}")
        print(f"logs: {team_dir}")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    targets: list[tuple[str, str | None]] = []
    if args.mode:
        targets.append((args.mode, args.instance_id))
    else:
        snapshot = state_status(include_inactive=False, include_locks=False)
        targets = [(s["mode"], s.get("instance_id")) for s in snapshot.get("states", []) if s.get("active")]

    results = []
    for mode, instance_id in targets:
        results.append({
            "mode": mode,
            "instance_id": instance_id,
            **state_cancel(mode, reason=args.reason, requested_by="omh-cli", instance_id=instance_id),
        })

    payload = {"cancelled": results, "count": len(results)}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if not results:
            print("No active OMH modes found.")
        for item in results:
            ident = item["mode"] + (f"/{item['instance_id']}" if item.get("instance_id") else "")
            print(f"cancel requested: {ident}")
    return 0


def _skill_roots(scope: str | None = None) -> list[tuple[str, Path]]:
    roots = [
        ("project", Path.cwd() / ".omh" / "skills"),
        ("user", _hermes_home() / "skills" / "omh"),
        ("bundled", SKILLS_DIR),
    ]
    if scope:
        roots = [r for r in roots if r[0] == scope]
    return roots


def _iter_skills(scope: str | None = None) -> Iterable[dict]:
    for root_name, root in _skill_roots(scope):
        if not root.exists():
            continue
        for item in sorted(root.iterdir()):
            if item.is_dir() and (item / "SKILL.md").exists():
                yield {"scope": root_name, "name": item.name, "path": str(item / "SKILL.md")}
            elif item.is_file() and item.suffix == ".md":
                yield {"scope": root_name, "name": item.stem, "path": str(item)}


def _skill_dest(scope: str, name: str) -> Path:
    slug = _slugify(name, default="custom-skill")
    if scope == "project":
        return Path.cwd() / ".omh" / "skills" / slug / "SKILL.md"
    if scope == "user":
        return _hermes_home() / "skills" / "omh" / slug / "SKILL.md"
    raise ValueError("scope must be project or user")


def cmd_skill(args: argparse.Namespace) -> int:
    if args.skill_action == "list":
        skills = list(_iter_skills(args.scope))
        if args.json:
            print(json.dumps({"skills": skills}, indent=2, ensure_ascii=False))
        else:
            for skill in skills:
                print(f"{skill['scope']}: {skill['name']} -> {skill['path']}")
        return 0

    if args.skill_action == "search":
        needle = args.query.lower()
        matches = []
        for skill in _iter_skills(args.scope):
            text = Path(skill["path"]).read_text(encoding="utf-8", errors="ignore")
            if needle in skill["name"].lower() or needle in text.lower():
                matches.append(skill)
        if args.json:
            print(json.dumps({"matches": matches}, indent=2, ensure_ascii=False))
        else:
            for skill in matches:
                print(f"{skill['scope']}: {skill['name']} -> {skill['path']}")
        return 0

    if args.skill_action == "add":
        dest = _skill_dest(args.scope, args.name)
        if dest.exists() and not args.force:
            print(f"skill already exists: {dest}", file=sys.stderr)
            return 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        triggers = [t.strip() for t in (args.triggers or "").split(",") if t.strip()]
        trigger_yaml = "[" + ", ".join(json.dumps(t) for t in triggers) + "]"
        body = textwrap.dedent(f"""\
        ---
        name: {dest.parent.name}
        description: {args.description or 'Custom OMH skill'}
        triggers: {trigger_yaml}
        source: custom
        ---

        # {args.name}

        Describe the reusable workflow here.
        """)
        dest.write_text(body, encoding="utf-8")
        print(dest)
        return 0

    if args.skill_action == "remove":
        removed = []
        for skill in _iter_skills(args.scope):
            if skill["name"] == args.name:
                path = Path(skill["path"])
                target = path.parent if path.name == "SKILL.md" else path
                if skill["scope"] == "bundled" and not args.force:
                    print("refusing to remove bundled skill without --force", file=sys.stderr)
                    return 1
                _remove_path(target)
                removed.append(str(target))
        print(json.dumps({"removed": removed}, indent=2) if args.json else "\n".join(removed or ["not found"]))
        return 0

    print("unknown skill action", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omh", description="Oh My Hermes CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup", help="install plugin and bundled skills")
    p.add_argument("--copy", action="store_true", help="copy instead of symlink")
    p.add_argument("--force", action="store_true", help="replace existing targets")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-project-init", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("doctor", help="validate local OMH installation")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("status", help="show OMH runtime state")
    p.add_argument("--include-inactive", action="store_true")
    p.add_argument("--no-locks", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("hud", help="print one-line OMH runtime status")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_hud)

    p = sub.add_parser("ask", help="run a provider CLI and save an ask artifact")
    p.add_argument("provider", choices=["claude", "codex", "gemini", "hermes"])
    p.add_argument("prompt_parts", nargs="*")
    p.add_argument("--prompt")
    p.add_argument("--agent-prompt", help="prepend an OMH role prompt")
    p.add_argument("--command", help="override provider command; may contain {prompt}")
    p.add_argument("--workdir")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("team", help="launch tmux provider workers")
    p.add_argument("--session")
    p.add_argument("--workdir", default=os.getcwd())
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("team_args", nargs="*")
    p.set_defaults(func=cmd_team)

    p = sub.add_parser("cancel", help="request cancellation for active modes")
    p.add_argument("mode", nargs="?")
    p.add_argument("--instance-id")
    p.add_argument("--reason", default="user request")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("skill", help="manage project/user OMH skills")
    skill_sub = p.add_subparsers(dest="skill_action", required=True)
    sp = skill_sub.add_parser("list")
    sp.add_argument("--scope", choices=["project", "user", "bundled"])
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_skill)
    sp = skill_sub.add_parser("search")
    sp.add_argument("query")
    sp.add_argument("--scope", choices=["project", "user", "bundled"])
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_skill)
    sp = skill_sub.add_parser("add")
    sp.add_argument("name")
    sp.add_argument("--scope", choices=["project", "user"], default="project")
    sp.add_argument("--description")
    sp.add_argument("--triggers")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_skill)
    sp = skill_sub.add_parser("remove")
    sp.add_argument("name")
    sp.add_argument("--scope", choices=["project", "user", "bundled"])
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_skill)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
