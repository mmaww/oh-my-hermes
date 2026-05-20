---
name: omh-cancel
description: "cancel active OMH modes and clear recoverable loops"
version: 1.0.0
metadata:
  hermes:
    tags: [cancel, stop, abort, state]
    category: omh
    requires_toolsets: [terminal, omh]
---

# OMH Cancel

用于停止 active OMH mode。优先发 cancel signal，不直接删除 state。

## 命令

```bash
omh cancel
omh cancel ralph --reason "user stopped the run"
```

会话内工具：

```text
omh_state(action="status")
omh_state(action="cancel", mode="ralph", reason="user request")
```

## 规则

- 默认取消所有 active modes。
- 如果用户指定 mode，只取消该 mode。
- 有 `instance_id` 时必须传入，避免取消错误计划。
- 不删除 evidence、plans、research report；这些是审计材料。

## 完成后

重新查看：

```bash
omh status --include-inactive
```

确认 active mode 已经收到 `cancel_requested` 或 phase 已结束。
