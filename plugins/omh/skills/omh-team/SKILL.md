---
name: omh-team
description: "tmux-backed provider worker orchestration"
version: 1.0.0
metadata:
  hermes:
    tags: [team, tmux, workers, codex, gemini, claude]
    category: omh
    requires_toolsets: [terminal]
---

# OMH Team

OMH 的 Team surface 有两层：

1. 会话内：用 Hermes `delegate_task` 批量派发 1-3 个子任务。
2. 终端 CLI：用 `omh team` 启动 tmux worker panes，运行 `claude` / `codex` / `gemini` / `hermes` 等本地 CLI。

## CLI workers

```bash
omh team 2:codex "review auth module for security issues"
omh team 2:gemini "audit UI accessibility"
omh team 1:claude 1:codex "compare implementation risks"
omh team status
omh team shutdown <session>
```

每个 worker 的日志写到：

```text
.omh/team/<session>/worker-XX-<provider>.log
```

## 会话内批量委派

适合 Hermes 原生 delegate：

```text
delegate_task(tasks=[
  {"goal": "[omh-role:architect] Review module boundaries", "context": "..."},
  {"goal": "[omh-role:test-engineer] Identify missing tests", "context": "..."}
])
```

约束：

- 不超过 Hermes 当前并发上限。
- 每个任务必须有独立、可验证的输出。
- 共享文件写入必须由 orchestrator 合并，不让多个 worker 同时改同一文件。

## 完成标准

Team 不是“多叫几个模型”。完成前必须整合 worker 输出，去重冲突，保留证据路径，并跑本地验证。
