---
description: "SDD + TDD 開發行為規則指標檔。實際規則內容以 AGENTS.md 為單一事實來源。"
always_apply: true
---

# 開發行為規則（指標檔）

本檔案為 `.claude/rules/` 自動載入機制的進入點，**實際規則內容請一律以專案根目錄的 [`AGENTS.md`](../../AGENTS.md) 為準**，尤其是「SDD」、「Git 與文件同步規則」、「文件生命週期與分流」、「TDD」及「Workflows」章節。

保留此檔案只是為了讓 Claude Code 的 rules 自動載入機制能觸發；不在此重複規則內容，避免與 `AGENTS.md` 未來修改時各自為政、產生不一致。

若要調整通用規則，必須同步修改 `AGENTS.md` 與 `docs/templates/AGENTS-TEMPLATE.md`；不要在本檔案另行複製規則文字。
