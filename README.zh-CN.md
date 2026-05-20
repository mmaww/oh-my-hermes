[English](README.md) | [简体中文](README.zh-CN.md)

# Oh My Hermes (OMH)

[![GitHub stars](https://img.shields.io/github/stars/mmaww/oh-my-hermes?style=flat&color=yellow)](https://github.com/mmaww/oh-my-hermes/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/mmaww/oh-my-hermes?style=flat&color=blue)](https://github.com/mmaww/oh-my-hermes/network/members)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

面向 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的多智能体编排技能集，  
灵感来自 [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode)，并按 Hermes 原生机制重构。

OMH 的设计是「技能优先、插件可选」：
- 不装插件，技能也能跑。
- 装插件后，获得角色注入、状态工具、证据采集、关键词路由和 CLI 辅助能力。

[快速开始](#快速开始) • [工作流地图](#工作流地图) • [能力特性](#能力特性) • [文档](#文档)

---

## 快速开始

### 第一步：添加 tap 并安装技能

```bash
hermes skills tap add mmaww/oh-my-hermes
hermes skills install omh-deep-research omh-deep-interview omh-ralplan omh-ralplan-driver omh-ralph omh-ralph-driver omh-ralph-task omh-triage omh-triage-driver omh-autopilot
```

### 第二步：安装可选插件（推荐）

如果从当前 checkout 运行，推荐：

```bash
pip install -e .
omh setup
omh doctor
```

也可以手动 symlink：

```bash
mkdir -p ~/.hermes/plugins ~/.hermes/skills
ln -snf "$PWD/plugins/omh" ~/.hermes/plugins/omh
ln -snf "$PWD/plugins/omh/skills" ~/.hermes/skills/omh
```

然后重启 Hermes，让 hooks 和 tools 生效。

### 第三步：验证并开始使用

```bash
hermes skills list | rg '^omh-'
omh status
```

示例：
- `deep interview this project idea`
- `ralplan this feature with risks and tests`
- `ralph execute plan in .omh/plans/`
- `autopilot build this end-to-end`

## 工作流地图

陌生领域推荐路径：

```text
omh-deep-research -> omh-deep-interview -> omh-ralplan -> omh-ralph
```

核心技能与职责：

| 技能 | 作用 |
| --- | --- |
| `omh-deep-research` | 并行网页研究 + 综合 + 引用校验 |
| `omh-deep-interview` | 苏格拉底式需求澄清与规格确认 |
| `omh-ralplan` | Planner/Architect/Critic 共识规划 |
| `omh-ralph` | 证据驱动执行循环（执行-验证-修复） |
| `omh-triage` | Maintainer + Skeptic 共识分诊 backlog |
| `omh-autopilot` | 访谈/规划/执行/QA/验证的一体化流水线 |
| `omh-ultrawork` | 面向独立任务的并行 burst 执行 |
| `omh-team` | Hermes delegate batch 与 tmux provider workers |
| `omh-ccg` | Codex + Gemini advisor，再由 Hermes 综合 |

调度类技能：

| 调度技能 | 适用场景 |
| --- | --- |
| `omh-ralplan-driver` | 你在主持 ralplan 轮次，需要严格调度和蒸馏 |
| `omh-ralph-driver` | 你在主持 ralph 批处理与 verifier 门禁 |
| `omh-triage-driver` | 你在主持 issue/backlog 治理轮次 |
| `omh-ralph-task` | 你是单个 ralph 任务执行者，需遵守封套纪律 |

工具类技能：

| 工具技能 | 作用 |
| --- | --- |
| `omh-setup` | 安装/验证插件、bundled skills 和项目 `.omh/` 状态 |
| `omh-hud` | 查看 active modes、phase、stale state 和 locks |
| `omh-ask` | 调用本地 Claude/Codex/Gemini/Hermes CLI，并保存 artifact |
| `omh-cancel` | 给 active OMH modes 发取消信号 |
| `omh-skill` | 管理 project/user scope 的自定义技能 |

## 不知道先用哪个？

- 需求模糊：先 `omh-deep-interview`
- 目标明确但领域知识不确定：先 `omh-deep-research`
- 需要先把方案做扎实：`omh-ralplan`
- 已有方案，强调完成质量：`omh-ralph`
- 想一条链路自动推进：`omh-autopilot`

## 为什么是 OMH

- 不是单 Agent 猜方案，而是多角色共识规划。
- 不是口头“已完成”，而是证据优先的执行闭环。
- `.omh/` 状态持久化，支持中断恢复和跨轮推进。
- 插件 hooks 降低提示词样板并强化角色边界。
- 即便不装插件，也能使用技能主流程。

## 能力特性

### 编排模式

| 模式 | 本质 | 适合场景 |
| --- | --- | --- |
| `omh-deep-interview` | 需求访谈循环 | 目标不清、边界不明 |
| `omh-ralplan` | 多角色共识规划 | 中大型改动前的实施设计 |
| `omh-ralph` | 持续执行+验证循环 | 要求高可靠交付与证据闭环 |
| `omh-triage` | 共识式 backlog 治理 | 清理陈旧 issue、重铸有效需求 |
| `omh-autopilot` | 组合全流程 | 从想法到交付的一站式推进 |
| `omh-ultrawork` | 非 Team 并行 burst | 文件范围不重叠的独立修复/重构 |
| `omh-team` / `omh team` | 原生 delegate batch 或 tmux CLI workers | 多 provider review / execution lanes |
| `omh-ccg` | Codex + Gemini advisor 综合 | backend/UI 混合任务或高风险设计评审 |

### CLI 工具

```bash
omh setup
omh doctor
omh status
omh hud
omh ask codex --prompt "review this migration"
omh team 2:codex "review auth module"
omh cancel
omh skill list
```

运行材料写入 `.omh/`：

- `.omh/state/`：active mode state 和 advisory locks
- `.omh/artifacts/ask/`：provider advisor 记录
- `.omh/team/`：tmux worker 日志
- `.omh/skills/`：project scope 可复用技能

### 插件能力（可选）

`plugins/omh/` 提供：
- `omh_state`：状态、status snapshot、锁、取消信号、角色加载
- `omh_gather_evidence`：白名单验证命令采集
- `pre_llm_call`：`[omh-role:NAME]` 角色注入、active mode 提醒和 OMH 关键词路由
- `pre_tool_call`：角色标记预校验
- `on_session_end`：中断状态记录

详见：[`docs/plugin.md`](docs/plugin.md)

## 升级方式

若通过 Hermes hub/tap 安装：

```bash
hermes skills check
hermes skills update
```

若通过本地仓库 + symlink 运行：

```bash
git pull
# 插件代码改动后重启 Hermes
```

## 依赖要求

- Hermes Agent v0.7.0+
- Python 3.10+（插件模式）
- `pyyaml`（插件模式）

## 文档

- [`docs/concepts.md`](docs/concepts.md) - 技能组合方式与设计逻辑
- [`docs/plugin.md`](docs/plugin.md) - 插件 hooks、tools、角色注入机制
- [`docs/omh-delegate.md`](docs/omh-delegate.md) - delegation 封装与持久化契约
- [`docs/hermes-constraints.md`](docs/hermes-constraints.md) - Hermes 约束与 OMH 应对
- [`docs/omc-comparison.md`](docs/omc-comparison.md) - 与 OMC 的设计对比
- [`docs/gaps.md`](docs/gaps.md) - 已知缺口与扩展方向
- [`docs/strict-enforcement.md`](docs/strict-enforcement.md) - 严格执行与证据门禁规范
- [`ROADMAP.md`](ROADMAP.md) - 版本路线

## 贡献

开发与测试流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 许可证

MIT
