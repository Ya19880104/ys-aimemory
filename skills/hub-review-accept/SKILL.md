---
name: hub-review-accept
description: 依中央記憶 Hub 最新需求和確切 commit 審查或測試交付，記錄驗收證據並區分工作完成與正式核准。
---

# 審查與驗收

用 hub-task-start 取得自己的上下文與租約。reviewer/tester 是本次工作角色，不是安全權限。

1. 讀原始需求、allowed_paths、acceptance_criteria、核准來源、交接摘要、基底與交付 commit。不要只靠上一位 AI 的摘要。
2. 審查實際 diff；逐項核對 scope、行為、失敗路徑、安全邊界與證據。測試在隔離 clone/worktree 執行並記錄實際命令、環境、退出碼和 commit。
3. 未跑的測試寫「未執行」並說原因；靜態閱讀不等於實際驗證。來源改版、工作 commit 改變或租約失效時重新建立對應的證據，不沿用舊通過結果。
4. 發現問題記錄檔案／行號、影響、重現、預期與實際行為。要修復就另行確認 scope 與唯一寫入者，不一邊審查一邊偷偷改他人的分支。
5. checkpoint 記錄每項驗收條件的通過／失敗／未測與證據。需要修復就 handoff 回指定 worker。
6. `complete_task` 只能如實記錄此任務完成；不宣稱人類已接受、受保護分支已合併或已部署。記憶 proposal 的核准需獨立 approver/admin 權限與最新 expected_revision，不因當了 reviewer 就可呼叫。

讀取與 evidence hash 檢查不是語意正確性保證；拒絕以「其他三個 AI 都同意」取代可重現的證據。
