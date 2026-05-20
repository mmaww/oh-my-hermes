---
name: omh-ask
description: "ask local Claude/Codex/Gemini/Hermes CLI and save artifact"
version: 1.0.0
metadata:
  hermes:
    tags: [ask, advisor, codex, gemini, claude, cross-check]
    category: omh
    requires_toolsets: [terminal]
---

# OMH Ask

Provider advisor：调用本地 provider CLI，并把结果保存为可复用 artifact。

## 命令

```bash
omh ask codex --prompt "review this architecture"
omh ask gemini --prompt "polish this UI plan"
omh ask claude --agent-prompt architect --prompt "challenge this migration"
```

artifact 默认写到：

```text
.omh/artifacts/ask/YYYYMMDDTHHMMSSZ-<provider>-<slug>.md
```

## Provider

- `claude`: 默认命令 `claude -p <prompt>`
- `codex`: 默认命令 `codex exec <prompt>`
- `gemini`: 默认命令 `gemini -p <prompt>`
- `hermes`: 默认命令 `hermes -p <prompt>`

如果本机 CLI 参数不同，用 `--command` 覆盖：

```bash
omh ask codex --command "codex exec {prompt}" --prompt "review"
```

## 何时使用

- 需要第二模型做 architecture、security、UI、review 交叉验证。
- ralplan/ralph 的关键决策需要外部批判。
- 用户明确说 ask codex / ask gemini / ccg。

## 证据纪律

最终回答必须引用 artifact 路径和 exit code。provider CLI 不存在时，artifact 仍会记录失败，不能假装已经获得外部意见。
