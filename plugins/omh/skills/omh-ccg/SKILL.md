---
name: omh-ccg
description: "Codex + Gemini advisor pass, then Hermes synthesis"
version: 1.0.0
metadata:
  hermes:
    tags: [ccg, codex, gemini, synthesis, advisor]
    category: omh
    requires_toolsets: [terminal]
---

# OMH CCG

CCG 是轻量跨模型 advisor 流程：Codex 看代码/架构，Gemini 看 UI/长上下文/文档，然后当前 Hermes 会话综合。

## 流程

1. 调用 Codex：

```bash
omh ask codex --prompt "<task>"
```

2. 调用 Gemini：

```bash
omh ask gemini --prompt "<task>"
```

3. 读取两个 `.omh/artifacts/ask/*.md` artifact。
4. 综合为一个明确结论：采纳、拒绝、需要验证、冲突点。

## 何时使用

- backend + UI 同时影响的任务。
- 方案风险高，需要第二/第三模型挑战。
- 用户说 ccg、Codex + Gemini、三模型评审。

## 输出要求

最终输出必须列出两个 artifact 路径；如果某个 provider CLI 不存在，要明确说明该 advisor 缺席，不能补造意见。
