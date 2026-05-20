# Oh My Hermes (OMH)

[English](README.md) | [简体中文](README.zh-CN.md)

面向 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的多智能体编排技能集。  
项目灵感来自 [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode)，并基于 Hermes 原生能力重新实现。

OMH 提供可组合的技能，覆盖共识规划、需求澄清访谈、以及带证据的执行闭环；并提供可选插件用于 hook 注入、原子状态管理和证据采集。  
技能可独立运行，零额外依赖。

| 技能 | 作用 |
| --- | --- |
| **omh-deep-research** | 多阶段网络研究：问题拆解 → 并行检索 → 汇总综合 → 引用校验 |
| **omh-ralplan** | 共识规划：Planner → Architect → Critic 多轮辩证直到收敛 |
| **omh-ralplan-driver** | `omh-ralplan` 调度手册：上下文包、轮次调度、蒸馏汇总、最终复核 |
| **omh-deep-interview** | 苏格拉底式需求访谈，带覆盖追踪 |
| **omh-ralph** | 验证式执行：实现 → 验证 → 迭代直到完成 |
| **omh-ralph-driver** | `omh-ralph` 调度手册：计划成形、并行批处理、证据收集、验证纪律、分级处置、最终架构复核 |
| **omh-ralph-task** | 单任务执行纪律：任务封套、文件范围约束、与 HEAD 对照验证、提交作者控制、结构化回报 |
| **omh-triage** *(v0.1)* | 问题池共识分诊：Maintainer（代码锚定）+ Skeptic（去冗） |
| **omh-triage-driver** *(v0.1)* | `omh-triage` 调度手册：预检、角色轮次、蒸馏、用户签收门禁 |
| **omh-autopilot** | 端到端自动流水线，串联三大核心技能 |

推荐组合（陌生领域）：

```text
omh-deep-research → omh-deep-interview → omh-ralplan → omh-ralph
```

如果领域未知，也可以把 `omh-deep-research` 作为 `omh-autopilot` 的 Phase -1。

## 安装

```bash
hermes skills tap add witt3rd/oh-my-hermes
hermes skills install omh-deep-research omh-ralplan omh-ralplan-driver omh-deep-interview omh-ralph omh-ralph-driver omh-ralph-task omh-autopilot
```

也可手动复制 `skills/<name>/` 到 `~/.hermes/skills/omh/`。

可选插件安装路径：`plugins/omh/` -> `~/.hermes/plugins/omh/`  
插件依赖：Python 3.10+ 与 `pyyaml`。

本地开发（符号链接热更新）见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 快速选择

- 需要先补领域背景：`omh-deep-research`
- 只需要做计划：`omh-ralplan`
- 你自己主持 ralplan：`omh-ralplan-driver`（与 `omh-ralplan` 同载）
- 需求模糊：先 `omh-deep-interview`，再 `omh-ralplan`
- 已有计划，需要执行：`omh-ralph`
- 你自己主持 ralph：`omh-ralph-driver`（与 `omh-ralph` 同载）
- 需要整理 issue backlog：`omh-triage`（主持时加 `omh-triage-driver`）
- 端到端自动推进：`omh-autopilot`

首次运行（安装插件后），OMH 会在项目内自动初始化 `.omh/` 目录，包含说明文件和可选择性共享的 `.gitignore`。  
若需提前初始化，不跑流程也可调用：`omh_state(action="init")`。

## 已知缺口

- `omh-deep-research` 产出的研究结果，目前尚未完整接入 wiki / fact_store / memory 持久化。  
  v1 的稳定接口是确认报告哨兵：`.omh/research/{slug}-report.md`（`status: confirmed`）。
- `omh-deep-research` 的 verifier 在某些 Hermes 版本下可能不支持每次调用的工具隔离。  
  此时 READ-ONLY 约束由 `role-research-verifier.md` 的流程约束保障（A5）。

## 成本范围（omh-deep-research）

典型顺利路径约 **5-8 次 `delegate_task` 调用**  
（3-5 researcher + 0-1 followup + 1 synthesist + 1 verifier）。

若综合阶段重试一次，通常在 **10-12 次调用**；  
3-strike 上限场景约 **14-16 次调用** 后返回 BLOCKED。

## 环境要求

- Hermes Agent v0.7.0+
- 插件模式额外需要：Python 3.10+、`pyyaml`

## 文档

- [`docs/concepts.md`](docs/concepts.md) - 四个核心技能的工作方式
- [`docs/plugin.md`](docs/plugin.md) - v2 插件（角色、hooks、工具）
- [`docs/omh-delegate.md`](docs/omh-delegate.md) - 加固的 delegation 封装
- [`docs/omc-comparison.md`](docs/omc-comparison.md) - 与 OMC 的设计对比
- [`docs/hermes-constraints.md`](docs/hermes-constraints.md) - OMH 对 Hermes 约束的处理
- [`docs/gaps.md`](docs/gaps.md) - 当前未完成能力
- [`ROADMAP.md`](ROADMAP.md) - 版本规划与方向
- [`docs/strict-enforcement.md`](docs/strict-enforcement.md) - 严格执行与证据门禁规范

## 许可证

MIT
