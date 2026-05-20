---
name: omh-ultrapilot
description: "legacy alias that routes to OMH autopilot"
version: 1.0.0
metadata:
  hermes:
    tags: [ultrapilot, autopilot, legacy]
    category: omh
    requires_toolsets: [terminal, omh]
---

# OMH Ultrapilot (Legacy Alias)

`ultrapilot` 在 OMC 中是历史兼容模式。  
在 OMH 中保持兼容语义：默认路由到 `omh-autopilot`。

## 行为

- 接到 `ultrapilot` 请求时，按 `omh-autopilot` 的阶段化执行。
- 若用户明确要求顺序流水线，可改用 `omh-pipeline`。

