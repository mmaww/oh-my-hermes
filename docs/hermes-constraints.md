# Hermes Constraints

How OMH works around the limits of Hermes's subagent and lifecycle model.

> **Status note (2026-04-22):** This doc was originally written against an
> earlier Hermes feature surface. Several entries previously listed as hard
> constraints are now configurable defaults — see the *Defaults vs hard
> limits* section below and the empirical findings in
> [`research/hermes-multiagent.md`](research/hermes-multiagent.md).

## Defaults vs hard limits (read this first)

OMH targets **stock Hermes defaults** for portability — that's a deliberate
choice, not a forced one. Several "constraints" below are really *default
configurations OMH does not require the user to change*:

| Knob | Default | Cap | OMH posture |
|---|---|---|---|
| `delegation.max_concurrent_children` | 3 | None (floor 1) | OMH ships assuming 3; raise per-project to fan out wider validation phases |
| `delegation.max_spawn_depth` | 1 (flat) | 3 | OMH ships flat; nested orchestration is opt-in |
| `delegation.orchestrator_enabled` | true | — | Global kill-switch; OMH respects when false |
| `delegation.model` / `provider` | inherits parent | — | OMH ships inheriting; cheap-tier routing is a config preset |

True hard limits are documented in *Subagent isolation guarantees* below —
those are architectural and can't be turned off.

## Subagent and Lifecycle Constraints

| Constraint | Impact | How OMH Handles It |
|---|---|---|
| **Default 3 concurrent subagents** *(configurable, no hard cap)* | Stock OMH fans out 3 at a time; widening requires `max_concurrent_children` bump | Batch into groups of 3 by default; validation phase fits exactly. Raise `delegation.max_concurrent_children` to enable wider validation fanout (5-6 reviewers). |
| **Flat delegation by default** *(opt-in nesting via `role="orchestrator"` + `max_spawn_depth >= 2`)* | Stock OMH keeps all orchestration at the top level | Skills work flat out of the box. Nested-orchestration patterns are an opt-in v2 direction — see the candidate `omh-nested-orchestration` skill noted in [`research/hermes-multiagent.md`](research/hermes-multiagent.md). |
| No stop-prevention hook | Can't mechanically force continuation | One-task-per-invocation + state files for ralph; prompt-based for ralplan |
| Subagents lack `execute_code` | Children reason step-by-step | Orchestrator handles batch operations; subagents use tools directly |
| Subagents lack `memory` | Children can't write to shared memory | State passed via files and delegate_task context |

## Subagent isolation guarantees (true hard limits)

These are architectural properties of `delegate_task`, not knobs:

- **No conversation history** — subagents see only the `goal` + `context` the parent passes. Zero knowledge of prior tool calls or messages.
- **Final summary only** — intermediate tool calls never enter the parent's context. (This is *why* `omh_delegate` writes via subagent-persists contract — see [`omh-delegate.md`](omh-delegate.md).)
- **Blocked toolsets for leaves** — `delegation`, `clarify`, `memory`, `code_execution`, `send_message` are blocked for `role="leaf"` regardless of what the caller passes. `delegation` is re-added for `role="orchestrator"` children; the other four stay blocked at every depth.
- **Per-call `toolsets=[...]` is real and enforced** — pass `["file"]` to get a read-only worker. (Used by the omh-deep-research verifier; see A5 note in README.)
- **Interrupt propagation** — interrupting the parent cancels all active children and grandchildren.

## Capabilities Skills Alone Can't Provide

These require Hermes code changes or plugins (some of which the v2 plugin
already addresses; others remain open):

| Gap | What OMC Has | Why We Can't | Path Forward |
|-----|-------------|-------------|--------------|
| **Stop prevention** | `persistent-mode.cjs` — 1144 lines that mechanically block Claude Code from exiting | Hermes has no `Stop` lifecycle hook. Skills can instruct but can't enforce. | PR: `pre_session_end` veto hook. Our workaround: state files + re-invocation. |
| **LSP integration** | 12 IDE-grade tools (hover, references, rename, diagnostics) | Not a skill-level feature — requires tool registration or MCP server. | PR or MCP server package. We use terminal-based tools (ripgrep, linters). |
| **ast-grep** | Structural code search/replace using AST matching | Same — needs tool registration. | Terminal fallback: `ast-grep` CLI works if installed. |
| **Live statusline with token tracking** | Real-time statusline with token/cost and agent activity | No display API in Hermes skills. | Partial shipped: `omh status`, `omh hud`, and `omh_state(action="status")` expose mode/phase/lock status. Token/cost tracking still needs runtime hook support. |
| **Rate limit auto-resume** | `omc wait` daemon monitors for resets | No equivalent daemon mechanism. | Hermes has credential pool rotation, which handles most cases. |
