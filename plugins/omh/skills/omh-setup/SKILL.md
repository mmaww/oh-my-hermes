---
name: omh-setup
description: "install/verify OMH plugin, skills, and project state"
version: 1.0.0
metadata:
  hermes:
    tags: [setup, doctor, install, omh]
    category: omh
    requires_toolsets: [terminal, omh]
---

# OMH Setup

用于安装、刷新或诊断 Oh My Hermes。

## 何时使用

- 用户说 setup、install、doctor、verify install、插件没生效。
- 需要把当前 checkout 链接到 `~/.hermes/plugins/omh` 和 `~/.hermes/skills/omh`。
- 需要初始化当前项目的 `.omh/` 状态目录。

## 执行

优先使用 CLI：

```bash
omh setup
omh doctor
```

如果用户只想看将要发生什么：

```bash
omh setup --dry-run
```

`omh setup` 会：

1. 链接或复制 plugin 到 `~/.hermes/plugins/omh`。
2. 安装 bundled skills 到 `~/.hermes/skills/omh/`。
3. 初始化当前项目 `.omh/README.md`、`.omh/.gitignore` 和 `.omh/state/`。

完成后提醒用户重启 Hermes，让 hooks/tools/skills 重新加载。

## 诊断标准

`omh doctor` 的 required check 必须通过：

- Python 3.10+
- PyYAML 可 import
- `plugin.yaml` 和 `config.yaml` 存在
- bundled skills 可发现

`hermes`、`tmux`、`claude`、`codex`、`gemini` 是 optional check。缺失时只影响对应功能，不影响核心 skill/plugin。
