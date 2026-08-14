---
description: "效率紀律 -- 檢查目前 session 是否違反效率規則。"
user-invocable: true
---

# /efficiency

檢查目前 session 是否有違反 AGENTS.md 效率紀律的行為：

1. 同一檔案重複讀取 > 1 次？
2. 同一指令 retry > 1 次？
3. 可平行的操作串行執行？
4. 回覆超過實際需要的長度？
5. SPEC 與 DRAFT 是否保留重複的有效需求？
6. 是否把同一內容無差別重複寫入 PROGRESS、ADR 與 reference？
7. 文件連結或寫死行號是否已經失效？

列出違規項目和改善建議。
