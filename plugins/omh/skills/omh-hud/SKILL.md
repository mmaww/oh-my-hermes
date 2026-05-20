---
name: omh-hud
description: "show OMH runtime status and active mode snapshot"
version: 1.0.0
metadata:
  hermes:
    tags: [hud, status, observability, state]
    category: omh
    requires_toolsets: [terminal, omh]
---

# OMH HUD

显示当前 `.omh/state/` 中的运行状态、active mode 和 advisory locks。

## 快速命令

```bash
omh hud
omh status
omh status --include-inactive
```

会话内也可以直接调用：

```text
omh_state(action="status")
```

## 输出解释

- `active_count`: 当前仍在运行或可恢复的 OMH mode 数量。
- `states`: 每个 mode / instance 的 phase、age、stale 状态。
- `locks`: ralph/autopilot 等流程的 advisory lock 状态。

## 使用纪律

在报告“任务完成”前，如果本轮使用了 OMH mode，先查看 status：

1. 没有遗留 active state。
2. 没有无主 lock。
3. 相关 mode phase 已经是 `complete`、`blocked` 或明确取消。
