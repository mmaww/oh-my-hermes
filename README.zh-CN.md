[English](README.md) | [简体中文](README.zh-CN.md)

# Oh My Hermes (OMH)

[![GitHub stars](https://img.shields.io/github/stars/mmaww/oh-my-hermes?style=flat&color=yellow)](https://github.com/mmaww/oh-my-hermes/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/mmaww/oh-my-hermes?style=flat&color=blue)](https://github.com/mmaww/oh-my-hermes/network/members)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

面向 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的多智能体编排技能集，  
灵感来自 [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode)，并按 Hermes 原生机制重构。

OMH 的设计是「技能优先、插件可选」：
- 不装插件，技能也能跑。
- 装插件后，获得角色注入、状态工具、证据采集、关键词路由、CLI 辅助能力，以及严格反偷懒/证据门禁 hooks。

[快速开始](#快速开始) • [生产升级 Runbook](#cn-runbook) • [能力覆盖](#cn-coverage) • [严格门禁](#cn-enforcer) • [文档](#文档)

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

如果你之前用了独立 `omc-enforcer`，建议迁移到 OMH 内置强门禁：

```bash
hermes plugins disable omc-enforcer
hermes plugins enable omh
```

如果机器上有会强制回写插件配置的 `omc-guardian.timer`，需要先停用：

```bash
systemctl --user disable --now omc-guardian.timer
```

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

<a id="cn-runbook"></a>
## 生产升级 Runbook（Hermes Host）

下面这套命令是把独立 `omc-enforcer` 迁移到 OMH 内置门禁时的标准流程（VPS 场景）：

```bash
cd /root/.hermes/dev/oh-my-hermes
git pull --ff-only
pip install -e .
python3 -m plugins.omh.cli setup
python3 -m plugins.omh.cli doctor

hermes plugins disable omc-enforcer || true
hermes plugins enable omh

# 如果该 timer 存在，需要停掉，避免插件启停状态被回写。
systemctl --user disable --now omc-guardian.timer || true

hermes plugins list | rg 'omh|omc-enforcer'
python3 -m plugins.omh.cli status --json
```

期望结果：
- `hermes plugins list` 显示 `omh enabled`、`omc-enforcer disabled`。
- 严格门禁状态文件存在：`~/.hermes/state/omh-enforcer/workflow-state.json`。
- 工作流运行时，`status --json` 能看到 active mode 快照。

<a id="cn-coverage"></a>
## 核心能力覆盖（OMC -> OMH）

本仓库已把 OMC README 的核心面向落到 Hermes 原生能力上：

| OMC 核心面 | OMH 对应能力 | 实现位置 |
| --- | --- | --- |
| 安装与自检 | `omh setup`、`omh doctor`、`omh-setup` | `plugins/omh/cli.py`（`cmd_setup`、`cmd_doctor`） |
| 运行态可观测 | `omh status`、`omh hud`、`omh-hud` | `plugins/omh/cli.py`、`plugins/omh/omh_state.py` |
| 多 provider 顾问输出 | `omh ask`、`omh-ask` | `plugins/omh/cli.py`（`cmd_ask`），产物落 `.omh/artifacts/ask/` |
| tmux worker 编排 | `omh team`、`omh-team` | `plugins/omh/cli.py`（`cmd_team`），日志落 `.omh/team/` |
| 主工作流技能 | `omh-deep-interview`、`omh-ralplan`、`omh-ralph`、`omh-autopilot`、`omh-ultrawork`、`omh-pipeline`、`omh-triage` | `plugins/omh/skills/*/SKILL.md` |
| 角色注入 | `[omh-role:NAME]` 标记 + 自动加载角色 prompt | `plugins/omh/hooks/llm_hooks.py`、`plugins/omh/hooks/tool_hooks.py`、`plugins/omh/omh_roles.py` |
| 关键词路由 | `pre_llm_call` 首轮路由上下文注入 | `plugins/omh/omh_keywords.py`、`plugins/omh/hooks/llm_hooks.py` |
| 任务记忆与关键约束锚点 | 每个任务独立存储记忆，并在每次 `pre_llm_call` 中注入关键约束 | `plugins/omh/omh_task_memory.py`、`plugins/omh/hooks/llm_hooks.py` |
| 严格反偷懒/反伪完成 | `pre_llm_call` + `post_llm_call` + `pre_gateway_send` + 工具证据账本 | `plugins/omh/hooks/enforcer_hooks.py`、`plugins/omh/omh_enforcer_state.py` |
| 取消/等待/通知/自定义技能 | `omh cancel`、`omh wait`、`omh config-stop-callback`、`omh skill` | `plugins/omh/cli.py`、`plugins/omh/omh_skill_injection.py` |

范围说明：
- 当前内置 10 个角色 prompt；部分 OMC 长尾角色是刻意未迁移。见 [`docs/gaps.md`](docs/gaps.md)。

<a id="cn-enforcer"></a>
## 严格门禁到底拦什么

当 `OMH_ENFORCER_ENABLED=1`（默认）时，OMH 不是“提示词约束”，而是 hook 级硬门禁：

1. 阶段门禁：
`deep_interview -> ralplan -> ralph`，支持 `ralph:` / `ralplan:` / `deep-interview:` 快捷前缀。
2. 防中途请示门禁：
可逆动作场景下，拦截“要我继续吗”式停工交接。
3. 防伪完成门禁：
没有文件路径、命令输出、测试日志等证据的“已完成”会被打回。
4. 防缩范围门禁：
记录用户声明的批量规模/任务清单，关闭时若缩小范围会被拦截。
5. 证据账本门禁：
Ralph 关闭前必须有真实工具执行证据（`post_tool_call` 或 history 回填）。
6. 危险命令门禁：
`pre_tool_call` 拦截明显破坏性命令（例如 `rm -rf /`、`git reset --hard`、`drop table` 模式）。
7. 出站门禁：
`pre_gateway_send` 在消息发给用户前再做一次强校验。

运行控制：
- `OMH_ENFORCER_ENABLED`：设为 `0` 可关闭严格门禁。
- `OMH_ENFORCER_STATE_FILE`：覆盖账本路径。
- 默认账本路径：`~/.hermes/state/omh-enforcer/workflow-state.json`。
- `OMH_RALPH_NO_PROMPT=1`：在 Ralph 阶段跳过“中途停下来提问/放弃”硬拦截；其余“有证据闭环/完成门禁”依旧生效。

## 兼容与冲突矩阵

| 组合 | 结果 | 建议 |
| --- | --- | --- |
| 同时启用 `omh` 与独立 `omc-enforcer` | 容易出现双重门禁和策略冲突 | 关闭 `omc-enforcer`，仅保留 `omh` |
| `omh` + `omc-guardian.timer` 运行中 | timer 可能回写插件启停状态 | 停用 timer 或移除其回写规则 |
| `omh` 插件 + OMH 技能 | 完整支持，推荐 | 同时保留 |
| 只用 OMH 技能，不装插件 | 可运行，但没有 hook 级门禁/注入 | 仅适合轻量场景 |
| OMH + 现有自定义技能 | 支持，且内置 trigger 注入 | 自定义技能放 `.omh/skills` 或 `~/.omh/skills` |

## 验收与回滚

冒烟验证：

```bash
cd /root/.hermes/dev/oh-my-hermes
python3 -m pytest plugins/omh/tests/test_enforcer_hooks.py -q
python3 -m pytest plugins/omh/tests/test_enforcer_state.py -q
python3 -m pytest plugins/omh/tests/test_cli.py -q
```

需要回滚时：

```bash
hermes plugins disable omh
hermes plugins enable omc-enforcer
# 可选：仅当你的环境之前依赖 guardian
systemctl --user enable --now omc-guardian.timer
```

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
| `omh-pipeline` | 适合强顺序依赖任务的阶段化流水线 |
| `omh-ultrawork` | 面向独立任务的并行 burst 执行 |
| `omh-ultrapilot` | legacy 兼容入口，语义路由到 autopilot |
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
| `omh-wait` | 限流冷却窗口的 start/stop/status 辅助 |
| `omh-configure-notifications` | 配置 stop callback 的渠道标签与路由元信息 |
| `omh-cancel` | 给 active OMH modes 发取消信号 |
| `omh-skill` | 管理 project/user scope 的自定义技能（含 edit） |

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
| `omh-pipeline` | 强顺序阶段流水线 | 多步骤转换且阶段依赖严格 |
| `omh-ultrawork` | 非 Team 并行 burst | 文件范围不重叠的独立修复/重构 |
| `omh-ultrapilot` | autopilot 的 legacy 兼容别名 | 兼容旧提示词与旧习惯 |
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
omh wait --start --minutes 15 --resume-cmd "echo resume now"
omh config-stop-callback telegram --enable --token <token> --chat <chat> --tag-list "@alice,bob"
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
- `pre_tool_call`：角色标记预校验 + 危险命令阻断
- `post_llm_call`：反偷懒/反伪完成门禁 + Ralph 关闭评分
- `post_tool_call`：真实执行证据账本记录
- `on_session_start` + `on_session_end`/`on_session_finalize`/`on_session_reset`：工作流生命周期状态维护
- 兼容性 outbound guard hook `pre_gateway_send`（运行时支持时生效）

严格门禁相关环境变量：
- `OMH_ENFORCER_ENABLED`（默认 `1`）- 设为 `0` 可关闭严格门禁层
- `OMH_ENFORCER_STATE_FILE` - 覆盖状态账本路径（默认 `~/.hermes/state/omh-enforcer/workflow-state.json`）

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
