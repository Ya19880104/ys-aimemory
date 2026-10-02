---
name: hub-task-handoff
description: 為中央記憶 Hub 任務保存證據、checkpoint 與明確交接；用於換模型、換帳號、額度耗盡前或階段工作完成。
---

# 可接續的交接

先讀 `docs/FOUR_AGENT_RUNBOOK.zh-TW.md` 的交接欄位。使用自己的有效 packet/fence；`validate_task_context` 失敗則停止中央寫入並回到 hub-task-start。

- 核對實際 Git HEAD、dirty 狀態與修改檔案；不可覆蓋他人成果。未提交工作需明確說明保存位置，不能讓接手者以為已在 commit 內。
- 摘要包括目標、範圍、已完成、待辦、已知缺陷、確切 branch/commit、測試命令與退出碼、日誌位置、未測項與原因、接手者下一步。
- `evidence` 只填實際存在的 `{source_id, sha256}`；不捏造測試通過。外部 artifact 的位置與 digest 另在摘要記錄，必要時請管理者登錄為來源。
- `record_checkpoint(project_id, packet_id, fence, summary, evidence)` 成功後，呼叫 `handoff_task` 並加入 `to_worker`。不可拿轉移租約當成擴大 scope 的方式。
- `handoff_task` 必須填結構化 `changed_artifacts`（可空）、`result_commit`、`test_results`（每項 command/status/details；status 為 passed/failed/not_run）、`blockers`（可空）、非空 `next_steps`。摘要不能取代這些欄位。
- 交接成功即停止以舊 fence 寫入；告知接手者重新 prepare/read/acknowledge/accept/validate。不得傳遞帳號憑證或把前人的 packet 當自己的。
- 若工具回應不確定，先查任務狀態／最新 prepare 結果及 audit，避免重複交接；缺失的權限或失敗如實報告。

記憶修正使用 `propose_memory_change`，保留來源與理由，等待有權限者核准。不可直接聲稱提案已成正式知識。正常結案使用 `complete_task`，但這只記錄持有者的完成聲明，不能代替獨立驗收、合併或部署授權。
