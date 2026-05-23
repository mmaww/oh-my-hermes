[English](README.md) | [简体中文](README.zh-CN.md)

# Oh My Hermes (OMH)

[![GitHub stars](https://img.shields.io/github/stars/mmaww/oh-my-hermes?style=flat&color=yellow)](https://github.com/mmaww/oh-my-hermes/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/mmaww/oh-my-hermes?style=flat&color=blue)](https://github.com/mmaww/oh-my-hermes/network/members)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Multi-agent orchestration skills for [Hermes Agent](https://github.com/NousResearch/hermes-agent),
inspired by [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) and rebuilt for Hermes-native primitives.

OMH is skill-first and plugin-optional:
- Skills work standalone.
- The optional plugin adds role injection, state tools, evidence tooling, keyword routing, CLI helpers, and strict anti-lazy/evidence enforcement hooks.

[Quick Start](#quick-start) • [Production Runbook](#production-upgrade-runbook-hermes-host) • [Capability Coverage](#core-capability-coverage-omc---omh) • [Strict Enforcer](#strict-enforcer-what-is-actually-enforced) • [Documentation](#documentation)

---

## Quick Start

### Step 1: Add tap and install OMH skills

```bash
hermes skills tap add mmaww/oh-my-hermes
hermes skills install omh-deep-research omh-deep-interview omh-ralplan omh-ralplan-driver omh-ralph omh-ralph-driver omh-ralph-task omh-triage omh-triage-driver omh-autopilot
```

### Step 2: Install the optional plugin (recommended)

If you are running from this checkout, the easiest path is:

```bash
pip install -e .
omh setup
omh doctor
```

Manual symlink install is still supported:

```bash
mkdir -p ~/.hermes/plugins ~/.hermes/skills
ln -snf "$PWD/plugins/omh" ~/.hermes/plugins/omh
ln -snf "$PWD/plugins/omh/skills" ~/.hermes/skills/omh
```

Then restart Hermes so hooks/tools are reloaded.

If you previously used another legacy external enforcer plugin, disable it before enabling OMH:

```bash
hermes plugins disable <legacy-plugin-name>
hermes plugins enable omh
```

If your host has a legacy guardian timer that rewrites plugin settings, disable that timer:

```bash
systemctl --user disable --now <legacy-guardian-timer>
```

### Step 3: Verify and run

```bash
hermes skills list | rg '^omh-'
omh status
```

Examples:
- `deep interview this project idea`
- `ralplan this feature with risks and tests`
- `ralph execute plan in .omh/plans/`
- `autopilot build this end-to-end`

## Production Upgrade Runbook (Hermes Host)

This is the exact sequence to move from a legacy external enforcer setup to OMH-native enforcement on a VPS host:

```bash
cd /root/.hermes/dev/oh-my-hermes
git pull --ff-only
pip install -e .
python3 -m plugins.omh.cli setup
python3 -m plugins.omh.cli doctor

hermes plugins disable <legacy-plugin-name> || true
hermes plugins enable omh

# If this timer exists, disable it to prevent plugin toggles from being rewritten.
systemctl --user disable --now <legacy-guardian-timer> || true

hermes plugins list
python3 -m plugins.omh.cli status --json
```

Expected end state:
- `hermes plugins list` shows `omh` enabled.
- No conflicting legacy external enforcer plugin or guardian timer is still active.
- Strict-enforcer state file exists at `~/.hermes/state/omh-enforcer/workflow-state.json`.
- `status --json` returns active mode snapshots when workflows are running.
- Task memory is persisted at `~/.hermes/state/task-memory*` (`.omh/state/task-memory*` for repo-local installs) and auto-injected in each `pre_llm_call` as `[OMH TASK MEMORY]`.

## Core Capability Coverage (OMC -> OMH)

This repo covers the core OMC README surface in Hermes-native form:

| OMC Core Surface | OMH Surface | Implementation |
| --- | --- | --- |
| Setup / install checks | `omh setup`, `omh doctor`, `omh-setup` | `plugins/omh/cli.py` (`cmd_setup`, `cmd_doctor`) |
| Runtime visibility | `omh status`, `omh hud`, `omh-hud` | `plugins/omh/cli.py`, `plugins/omh/omh_state.py` |
| Provider advisor artifacts | `omh ask`, `omh-ask` | `plugins/omh/cli.py` (`cmd_ask`), artifacts in `.omh/artifacts/ask/` |
| tmux worker orchestration | `omh team`, `omh-team` | `plugins/omh/cli.py` (`cmd_team`), logs in `.omh/team/` |
| Workflow skills | `omh-deep-interview`, `omh-ralplan`, `omh-ralph`, `omh-autopilot`, `omh-ultrawork`, `omh-pipeline`, `omh-triage` | `plugins/omh/skills/*/SKILL.md` |
| Role prompt injection | `[omh-role:NAME]` marker + automatic role loading | `plugins/omh/hooks/llm_hooks.py`, `plugins/omh/hooks/tool_hooks.py`, `plugins/omh/omh_roles.py` |
| Keyword routing | first-turn routing context in `pre_llm_call` | `plugins/omh/omh_keywords.py`, `plugins/omh/hooks/llm_hooks.py` |
| Task-level memory persistence | Per-task context snapshots persisted to state and injected on every `pre_llm_call` | `plugins/omh/hooks/llm_hooks.py`, `plugins/omh/omh_task_memory.py` |
| Strict anti-lazy / anti-fake-completion gate | `pre_llm_call` + `post_llm_call` + `pre_gateway_send` + tool evidence ledger | `plugins/omh/hooks/enforcer_hooks.py`, `plugins/omh/omh_enforcer_state.py` |
| Cancel / wait / stop-callback / custom skills | `omh cancel`, `omh wait`, `omh config-stop-callback`, `omh skill` | `plugins/omh/cli.py`, `plugins/omh/omh_skill_injection.py` |

Scope note:
- OMH currently ships 10 role prompts; some long-tail OMC roles remain intentionally unported. See [`docs/gaps.md`](docs/gaps.md).

## Strict Enforcer: What Is Actually Enforced

When `OMH_ENFORCER_ENABLED=1` (default), OMH enforces hard gates instead of only relying on prompt discipline:

1. Phase gate:
`deep_interview -> ralplan -> ralph` (quick prefixes `ralph:`, `ralplan:`, `deep-interview:` are supported).
2. Anti-lazy / anti-handoff gate:
blocks replies that stop with reversible "should I continue?" handoff.
3. Anti-fake-completion gate:
completion claims without file paths, command output, test logs, or other evidence are blocked.
4. Scope anti-shrink gate:
user-declared batch size / task manifest is stored, and closing with smaller scope is blocked.
5. Tool evidence ledger gate:
Ralph cannot close unless ledger evidence exists (`post_tool_call` / history backfill).
6. Destructive command gate:
obviously destructive commands are blocked in `pre_tool_call` (for example `rm -rf /`, `git reset --hard`, `drop table` patterns).
7. Outbound guard gate:
`pre_gateway_send` re-checks user-visible output before send.

Runtime controls:
- `OMH_ENFORCER_ENABLED`: set `0` to disable strict enforcer.
- `OMH_ENFORCER_STATE_FILE`: override ledger path.
- Default ledger path: `~/.hermes/state/omh-enforcer/workflow-state.json`.

## Compatibility and Conflict Matrix

| Combination | Result | Recommendation |
| --- | --- | --- |
| `omh` + another external enforcer plugin both enabled | Double enforcement and policy collisions are likely | Keep OMH as the single enforcement layer |
| `omh` + legacy guardian timer active | Timer may rewrite plugin enable/disable state | Disable timer or remove its rewrite rule |
| `omh` plugin + OMH skills | Supported and recommended | Keep both |
| OMH skills without plugin | Works, but no hook-level enforcement/injection | Use for lightweight runs only |
| OMH + existing custom skills | Supported; trigger-based custom-skill injection is built-in | Keep custom skills under `.omh/skills` or `~/.omh/skills` |

## Validation and Rollback

Smoke tests:

```bash
cd /root/.hermes/dev/oh-my-hermes
python3 -m pytest plugins/omh/tests/test_enforcer_hooks.py -q
python3 -m pytest plugins/omh/tests/test_enforcer_state.py -q
python3 -m pytest plugins/omh/tests/test_cli.py -q
```

Rollback (if needed):

```bash
hermes plugins disable omh
# optional: re-enable your previous external controls only if your environment requires them
# hermes plugins enable <legacy-plugin-name>
# systemctl --user enable --now <legacy-guardian-timer>
```

## Workflow Map

Recommended path for unfamiliar domains:

```text
omh-deep-research -> omh-deep-interview -> omh-ralplan -> omh-ralph
```

Core skills and their jobs:

| Skill | Job |
| --- | --- |
| `omh-deep-research` | Parallel web research with synthesis and citation verification |
| `omh-deep-interview` | Socratic requirements clarification and spec confirmation |
| `omh-ralplan` | Planner/Architect/Critic consensus implementation planning |
| `omh-ralph` | Evidence-driven execution loop with verify/fix progression |
| `omh-triage` | Backlog triage with Maintainer + Skeptic role pressure |
| `omh-autopilot` | End-to-end composition across interview/plan/execute/QA/validation |
| `omh-pipeline` | Sequential staged execution when ordering is strict |
| `omh-ultrawork` | Parallel burst execution for independent tasks |
| `omh-ultrapilot` | Legacy compatibility alias that routes to autopilot semantics |
| `omh-team` | Hermes delegate batches and tmux provider workers |
| `omh-ccg` | Codex + Gemini advisor pass with Hermes synthesis |

Driver/dispatcher skills:

| Driver Skill | Use when |
| --- | --- |
| `omh-ralplan-driver` | You are orchestrating a ralplan round and need strict dispatch discipline |
| `omh-ralph-driver` | You are orchestrating ralph tasks/batches and verifier gating |
| `omh-triage-driver` | You are orchestrating backlog grooming rounds |
| `omh-ralph-task` | You are the executor for one bounded ralph task envelope |

Utility skills:

| Utility Skill | Job |
| --- | --- |
| `omh-setup` | Install/verify the plugin, bundled skills, and project `.omh/` state |
| `omh-hud` | Show active modes, phases, stale state, and locks |
| `omh-ask` | Run local Claude/Codex/Gemini/Hermes CLI advisors and save artifacts |
| `omh-wait` | Start/stop/status helper for rate-limit cooldown windows |
| `omh-configure-notifications` | Configure stop-callback provider tags and routing metadata |
| `omh-cancel` | Request cancellation for active OMH modes |
| `omh-skill` | List, add, search, edit, and remove custom project/user skills |

## Not Sure Where to Start?

- Vague idea: run `omh-deep-interview` first.
- Clear problem but unknown domain facts: run `omh-deep-research`.
- Need a robust plan before coding: run `omh-ralplan`.
- Plan exists and execution quality matters: run `omh-ralph`.
- Want one pipeline to drive all phases: run `omh-autopilot`.

## Why OMH

- Consensus-first planning, not single-agent guesswork.
- Evidence-first execution with explicit verifier pressure.
- Stateful, resumable workflows under `.omh/`.
- Plugin hooks reduce prompt boilerplate and enforce role boundaries.
- Skills remain usable even without plugin installation.

## Features

### Orchestration Modes

| Mode | What it is | Use for |
| --- | --- | --- |
| `omh-deep-interview` | Requirements interview loop | Ambiguous user goals |
| `omh-ralplan` | Multi-role planning consensus | Medium/large implementation planning |
| `omh-ralph` | Persistent execute+verify cycle | Reliable delivery with completion evidence |
| `omh-triage` | Consensus issue/backlog grooming | Pruning stale items and recasting live issues |
| `omh-autopilot` | Composed full pipeline | End-to-end implementation from idea |
| `omh-pipeline` | Strict sequential pipeline | Multi-step transformations with hard ordering |
| `omh-ultrawork` | Parallel non-team burst | Independent fixes/refactors with disjoint file scopes |
| `omh-ultrapilot` | Legacy alias of autopilot | Compatibility with older prompts and habits |
| `omh-team` / `omh team` | Native delegate batches or tmux CLI workers | Multi-provider review/execution lanes |
| `omh-ccg` | Codex + Gemini advisor synthesis | Mixed backend/UI or high-risk design review |

### CLI Utilities

```bash
omh setup
omh doctor
omh status
omh hud
omh ask codex --prompt "review this migration"
omh team 2:codex "review auth module"
omh wait --start --minutes 15 --resume-cmd "echo resume now"
omh config-stop-callback telegram --enable --token <token> --chat <chat> --tag-list "@alice,bob"
omh cancel
omh skill list
```

Artifacts and runtime state are written under `.omh/`:

- `.omh/state/` — active mode state and advisory locks
- `.omh/artifacts/ask/` — provider advisor transcripts
- `.omh/team/` — tmux worker logs
- `.omh/skills/` — project-scoped reusable skills
- `.omh/state/task-memory-*` — per-task memory snapshots used to recover context across long conversations

### Plugin Infrastructure (optional)

The plugin at `plugins/omh/` provides:
- `omh_state` tool for workflow state, status snapshots, locks, cancel signals, and role loading
- `omh_gather_evidence` tool for allowlisted verification command capture
- `pre_llm_call` hook for `[omh-role:NAME]` role injection, active-mode reminders, and OMH keyword routing
- `pre_tool_call` hook for role marker validation and destructive command blocking
- `post_llm_call` hook for anti-lazy/false-completion gate and Ralph close scoring
- `post_tool_call` hook for evidence ledger persistence
- `on_session_start` + `on_session_end`/`on_session_finalize`/`on_session_reset` hooks for workflow lifecycle bookkeeping
- compatibility outbound guard hook `pre_gateway_send` (used where runtime supports it)

Strict-enforcer runtime controls:
- `OMH_ENFORCER_ENABLED` (`1` by default) — set `0` to disable strict enforcement layer
- `OMH_ENFORCER_STATE_FILE` — override state ledger path (default: `~/.hermes/state/omh-enforcer/workflow-state.json`)

See details: [`docs/plugin.md`](docs/plugin.md)

## Updating

If installed from Hermes hub/tap:

```bash
hermes skills check
hermes skills update
```

If running from a local clone + symlink:

```bash
git pull
# restart Hermes after plugin code changes
```

## Requirements

- Hermes Agent v0.7.0+
- Python 3.10+ (plugin mode)
- `pyyaml` (plugin mode)

## Documentation

- [`docs/concepts.md`](docs/concepts.md) - How skills compose and why the flow works
- [`docs/plugin.md`](docs/plugin.md) - Plugin hooks, tools, and role injection model
- [`docs/omh-delegate.md`](docs/omh-delegate.md) - Delegation wrapper and persistence contract
- [`docs/hermes-constraints.md`](docs/hermes-constraints.md) - Hermes runtime constraints and OMH workarounds
- [`docs/omc-comparison.md`](docs/omc-comparison.md) - Design comparison with OMC
- [`docs/gaps.md`](docs/gaps.md) - Known gaps and planned expansions
- [`docs/strict-enforcement.md`](docs/strict-enforcement.md) - Strict execution/evidence enforcement profile
- [`ROADMAP.md`](ROADMAP.md) - Version direction

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for local dev setup, testing, and symlink workflow.

## License

MIT
