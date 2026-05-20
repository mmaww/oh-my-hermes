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

[Quick Start](#quick-start) • [Workflow Map](#workflow-map) • [Features](#features) • [Documentation](#documentation)

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

If you previously used standalone `omc-enforcer`, migrate to OMH-native enforcement:

```bash
hermes plugins disable omc-enforcer
hermes plugins enable omh
```

If your host has an `omc-guardian.timer` that rewrites plugin settings, disable it:

```bash
systemctl --user disable --now omc-guardian.timer
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
