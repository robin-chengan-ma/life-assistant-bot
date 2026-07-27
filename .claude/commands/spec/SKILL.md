---
description: "Spec 管理 -- 查看進度、建立新 spec、繼續指定 spec。"
user-invocable: true
argument-hint: "[status|new <slug>|<slug>]"
---

# /spec [command]

Spec 管理快捷指令，執行 AGENTS.md 中定義的 Spec 相關 workflow。

## 用法

- `/spec` 或 `/spec status` -- 執行 **Workflow: Spec Status**，列出所有 spec 進度
- `/spec new <slug>` -- 執行 **Workflow: New Spec**，建立新 spec
- `/spec <slug>` -- 讀取指定 spec，報告進度，問下一步

請根據參數執行對應的 AGENTS.md workflow。
