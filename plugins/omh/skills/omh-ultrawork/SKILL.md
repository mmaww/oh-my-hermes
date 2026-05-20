---
name: omh-ultrawork
description: "parallel non-team execution for independent work items"
version: 1.0.0
metadata:
  hermes:
    tags: [ultrawork, parallel, execution, batch]
    category: omh
    requires_toolsets: [terminal, omh, delegation]
---

# OMH Ultrawork

用于一批相互独立、低耦合、可并行验证的任务。它不是 Team pipeline，也不是 ralph 的持久循环；它是一次并行 burst。

## 适用

- 多个互不重叠的小修复。
- 多文件 lint/type/test error 可以按目录切分。
- 文档、测试、样式、简单 bugfix 可并行推进。

## 不适用

- 需求不清楚：先 `omh-deep-interview`。
- 方案需要共识：先 `omh-ralplan`。
- 必须持续 verify/fix 到完成：用 `omh-ralph` 或 `omh-autopilot`。
- 多个任务会写同一文件：不要并行。

## 执行步骤

1. 列出任务清单，并为每项指定 owner、文件范围、验收标准。
2. 将任务分成最多 3 个并发 batch。
3. 对每个任务使用对应 role：

```text
delegate_task(tasks=[
  {"goal": "[omh-role:executor] Implement task A ...", "context": "file scope: src/a"},
  {"goal": "[omh-role:test-engineer] Add tests for B ...", "context": "file scope: tests/b"}
])
```

4. orchestrator 合并结果。
5. 运行 `omh_gather_evidence` 或本地测试。
6. 失败项进入第二轮；不要无界循环。

## 完成标准

- 每个任务都有 PASS/FAIL。
- 改动没有文件冲突。
- 失败项有具体 blocker 或下一步。
- 验证命令和输出已记录。
