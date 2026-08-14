---
description: "Spec-Driven Development (SDD) -- 啟動或繼續 spec 驅動開發流程。"
user-invocable: true
---

# /sdd [feature-name]

執行 AGENTS.md 中定義的 **Workflow: SDD** 流程。

若提供 feature-name，直接在 docs/specs/SPEC.md 裡搜尋對應的功能區塊。
若未提供，從當前對話推斷相關功能。

請立即開始執行 AGENTS.md 的 SDD workflow 步驟。

特別遵守：定案內容移入 SPEC 後必須從 DRAFT 移除；完成前同步 PROGRESS、適用 ADR 與 reference，並分開記錄 commit、push、部署狀態。
