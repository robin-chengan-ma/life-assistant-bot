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

列出違規項目和改善建議。
