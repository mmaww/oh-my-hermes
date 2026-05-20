# Honest Gaps

OMH now covers the core OMC README surface in Hermes-native form: setup/doctor,
status/HUD, ask artifacts, tmux-backed team workers, keyword routing, custom
skill management, and the main orchestration modes. This document tracks what
is still intentionally incomplete or limited by Hermes runtime constraints.

For gaps that require Hermes-level changes (LSP, stop prevention, HUD), see
[`hermes-constraints.md`](hermes-constraints.md).

## Could Be Skills (Not Yet Built)

| Gap | What OMC Has | Priority | Effort |
|-----|-------------|----------|--------|
| **19 more agent roles** | designer, qa-tester, scientist, git-master, tracer, vision, product-manager, ux-researcher, etc. We have 10 of OMC's 29. | Medium | Low per role — add as needed |
| **Deslop pass** | `ai-slop-cleaner` as mandatory post-process in ralph | Medium | New skill |
| **Model tier routing** | Auto-routes Haiku/Sonnet/Opus by task complexity. We use one model for all. | Low-Medium | **Native via `delegation.model` / `delegation.provider` config** — see [`research/hermes-multiagent.md`](research/hermes-multiagent.md) §5. OMH should ship recommended config presets (cheap-tier for verifier/deslop leaves) rather than build its own router. Per-task routing within a single batch is not yet supported by the public schema. |
| **Ontology extraction** | Tracks entities across interview rounds with stability ratios | Medium-High | Deep-interview v1.1 |
| **Brownfield explore-first** | Scans codebase before asking the user | Medium | Deep-interview v1.1 |

## Shipped Since This Gap List Was First Written

| Former gap | Current OMH surface |
| --- | --- |
| Setup / doctor | `omh setup`, `omh doctor`, `omh-setup` |
| HUD / observability | `omh status`, `omh hud`, `omh_state(action="status")`, `omh-hud` |
| Provider advisor | `omh ask`, `omh-ask`, artifacts under `.omh/artifacts/ask/` |
| tmux multi-provider workers | `omh team`, `omh-team`, logs under `.omh/team/` |
| CCG advisor flow | `omh-ccg` |
| Ultrawork burst mode | `omh-ultrawork` |
| Cancellation utility | `omh cancel`, `omh-cancel` |
| Custom skill management | `omh skill`, `omh-skill`, project/user skill scopes |
| Custom skill auto-inject | `pre_llm_call` injects matched project/user custom skills by trigger |
| Magic keyword routing | `pre_llm_call` first-turn keyword routing context |
| Rate-limit wait helper | `omh wait`, `omh-wait` |
| Stop callback config surface | `omh config-stop-callback`, `omh-configure-notifications` |
| Pipeline / Ultrapilot compatibility | `omh-pipeline`, `omh-ultrapilot` |
