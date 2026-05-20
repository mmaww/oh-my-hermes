---
name: omh-configure-notifications
description: "configure stop callback providers and tag lists"
version: 1.0.0
metadata:
  hermes:
    tags: [notifications, stop-callback, telegram, discord, slack]
    category: omh
    requires_toolsets: [terminal, omh]
---

# OMH Configure Notifications

配置会话停止回调渠道与 @tag 列表。

## 示例

```bash
omh config-stop-callback telegram --enable --token <bot_token> --chat <chat_id> --tag-list "@alice,bob"
omh config-stop-callback discord --enable --webhook <url> --tag-list "@here,role:123456"
omh config-stop-callback telegram --add-tag charlie
omh config-stop-callback discord --remove-tag @here
omh config-stop-callback slack --clear-tags
```

