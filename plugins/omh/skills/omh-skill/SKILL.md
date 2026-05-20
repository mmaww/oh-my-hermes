---
name: omh-skill
description: "list, add, search, and remove custom OMH skills"
version: 1.0.0
metadata:
  hermes:
    tags: [skill, custom-skills, reuse, workflow]
    category: omh
    requires_toolsets: [terminal]
---

# OMH Skill

管理 project/user scope 的自定义技能。

## 命令

```bash
omh skill list
omh skill list --scope bundled
omh skill search proxy
omh skill add fix-proxy --description "aiohttp proxy crash fix" --triggers "proxy,aiohttp,disconnect"
omh skill remove fix-proxy --scope project
```

## Scope

- project: `.omh/skills/<name>/SKILL.md`
- user: `~/.hermes/skills/omh/<name>/SKILL.md`
- bundled: `plugins/omh/skills/<name>/SKILL.md`

project skills 可以随项目提交，适合沉淀本仓库经验。user skills 是个人全局经验。

## 编写要求

自定义 skill 必须包含：

- 触发条件
- 不适用条件
- 可执行步骤
- 验证标准
- 失败/阻塞时如何报告

不要把一次性聊天记录当 skill；只有可复用的工作流才沉淀。
