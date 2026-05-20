# Strict Hermes Enforcement Layer

This fork adds a strict enforcement profile for Hermes deployments that need
OMC/Ralph/YOLO behavior to be enforced by runtime evidence instead of by prompt
style alone.

## Problem

Hermes can run OMH-style skills and workflows, but production gateways still
need a hard outbound guard. Without it, an agent can produce user-visible
messages that stop early, ask for permission on reversible work, or claim a task
is complete without matching tool evidence.

Observed failure modes on VPS143:

- Ralph/YOLO tasks ending with permission handoff text such as `要继续吗?`.
- Partial batch work being reported as a completed task.
- Completion claims that cite no file path, command output, test result, or log.
- Active Ralph state being lost or bypassed during gateway sends.
- Progress summaries that ask the user to decide the next safe reversible step.

## Strict profile goals

The strict profile should be installable as an OMH/Hermes plugin profile and
should enforce these invariants:

1. Every LLM call receives the default YOLO execution instruction.
2. Every assistant response is checked for lazy handoff, false completion, and
   missing evidence.
3. Every user-visible gateway send is checked again before it reaches Feishu,
   Telegram, or another messaging surface.
4. Ralph sessions remain active until a completion score of at least 99/100 is
   backed by task ledger evidence.
5. A completion claim must not exceed recorded tool evidence.
6. A failed task must include attempted commands, failure output, and the next
   viable non-destructive path.

## Required hooks

The strict profile must register at least these Hermes hooks:

```yaml
hooks:
  pre_llm_call:
    - command: hooks/pre-llm-call.sh
  post_llm_call:
    - command: hooks/post-llm-call.sh
  pre_gateway_send:
    - command: hooks/pre-gateway-send.sh
  on_session_end:
    - command: hooks/session-end.sh
```

`pre_gateway_send` is mandatory. A post-LLM guard alone is not enough because
final platform output can bypass or outlive the model-turn check.

## Evidence ledger

The strict profile should persist a ledger per session:

```json
{
  "session_id": "...",
  "phase": "ralph",
  "required_items": [],
  "evidence_records": [
    {
      "tool": "terminal",
      "command": "python3 script.py",
      "exit_code": 0,
      "paths": ["status/report.jsonl"],
      "counts": {"done": 10, "failed": 2}
    }
  ],
  "completion_verified": false
}
```

Gateway output may only claim work that is supported by this ledger.

## First implementation lane

1. Package the current VPS143 strict enforcer as an OMH optional plugin profile.
2. Add a doctor command that verifies hook registration and runs synthetic
   gateway-block tests.
3. Add regression tests for long report tails ending with `要继续吗?`.
4. Add a migration path from existing `/root/.hermes/plugins/omc-enforcer` state
   files to OMH-managed state.

## Non-goals for the first release

- Replacing Hermes core.
- Reimplementing the full oh-my-claudecode runtime.
- Deleting or rewriting existing OMH skills.

The first release should be a hard enforcement layer on top of OMH's current
Hermes-native skill and state model.
