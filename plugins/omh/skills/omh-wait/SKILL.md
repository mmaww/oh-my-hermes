---
name: omh-wait
description: "start/stop/status wait helper for rate-limit windows"
version: 1.0.0
metadata:
  hermes:
    tags: [wait, rate-limit, cooldown, resume]
    category: omh
    requires_toolsets: [terminal, omh]
---

# OMH Wait

用于在限流冷却窗口内保存等待状态，并在到点后执行恢复命令。

## 常用命令

```bash
omh wait --start --minutes 15 --resume-cmd "echo resume now"
omh wait
omh wait --stop
```

`--until` 支持绝对时间：

```bash
omh wait --start --until 2026-05-20T10:30:00+08:00
```

