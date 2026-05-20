---
name: omh-pipeline
description: "sequential staged pipeline for tightly ordered work"
version: 1.0.0
metadata:
  hermes:
    tags: [pipeline, staged, ordered, sequential]
    category: omh
    requires_toolsets: [terminal, omh]
---

# OMH Pipeline

用于严格顺序执行的多阶段任务（例如：迁移 -> 校验 -> 发布说明）。

## 何时使用

- 任务阶段有硬依赖，不能并行乱序。
- 需要每阶段都有验证证据再进入下一阶段。
- 不需要 Team 重协调开销，但要比一次性 autopilot 更可控。

## 执行建议

1. 用 `omh-ralplan` 先产出阶段清单与验收条件。
2. 逐阶段执行，每阶段结束都运行验证并记录证据。
3. 若中途发现需求变化，回到 planning 阶段再继续。

可选 CLI 辅助：

```bash
omh status
omh hud
```

