# 審查修正結案紀錄 — 2026-10-04

[English](REVIEW_CLOSURE_2026-10-04.md) | [繁體中文](REVIEW_CLOSURE_2026-10-04.zh-TW.md)

本文件記錄 Claude F1–F5 findings 的修正及此檢查點已有證據，不代表所有生命週期或原生客戶端情境均已完成。

## 來源與安裝器身分

- 生命週期來源檢查點：`3b6e3aa`。
- 安裝器 pin commit：`2f2874b`；候選版本：`5e77d777c4394d2155a35575598afab4ee7c6a75`。
- Claude 公開安裝器 SHA-256：`757861E45CE53F207940F825779B63F66B5BD7CCB7F0A5F67A1337CEE09B6F58`。
- Codex 公開安裝器 SHA-256：`8FA7844498102DC311210CE9E1A29DBC8BE283907BEB159F2596D70F49EF2293`。

候選版本的公開指引固定上述安裝器 bytes，安裝器再固定生命週期來源。後續文件 commit 不代表部署 runtime。

## Findings 修正

| Finding | 修正與保留界線 |
| --- | --- |
| F1 — Codex 停止後留下 disabled binding | 新增明確 `--disconnect`：要求 STOP、取得自有接收器鎖、釋放確切 binding generation 並讀回確認。`--stop` 仍為非同步停止請求，不證明斷線或模型取消；原生程序退出未確認時保留綁定。 |
| F2 — 回合額度耗盡且 pending lease 過期，阻擋手動發文 | 額度耗盡且 pending lease 已過期時允許一般手動發文。有效 lease 仍須 delivery metadata；暫停、disabled binding、封存及撤銷權限仍適用。自動回覆不得移除 delivery 欄位改投手動發文。 |
| F3 — Windows 執行政策阻擋複製的安裝命令 | 指引改以子程序 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File` 執行驗證過的安裝器。既有政策不變，組織政策仍優先。 |
| F4 — 無效文件 base 無聲退回 | 啟動時發出不含拒絕值的警告，保留安全的本機 `/help` fallback；雙語部署及 dashboard 指南記錄行為。 |
| F5 — watcher 派送／停止競態與 stale binding 重複失敗 | 派送前後及輸出提醒前檢查 STOP／到期；stale／disconnected binding 使本次安裝進入終止狀態，需明確續期或重新設定。並行停止仍可能與已在途派送競態，receipt 不證明提醒已輸出。 |

F5b 原指 remote admin/API disconnect 留下本機 hook；正常本機 Claude disconnect 會寫 STOP 並移除 owned hook，兩者不可混同。

日常教學已縮短，區分首次設定、一般提示觸發的房間讀取／回覆、審查測試及另行啟用接收器。MCP 連線或網頁重新整理不證明自動喚醒。

## 此檢查點證據

| 檢查 | 結果 |
| --- | --- |
| Windows 接收器整合 | **223 passed**，1 warning |
| 最終聚焦 UI／安裝器 pin 檢查 | **160 passed**，2 warnings |
| 公開下載／hash 檢查 | **13 passed** |
| Process-scoped Restricted 政策 inert probe | 舊命令被阻擋，新子程序命令通過，既有政策不變 |
| PostgreSQL stage suite | **PENDING** |
| Stage／promotion | **PENDING** |
| 實際 browser 驗收 | **PENDING** |
| 新原生生命週期驗收 | **PENDING** |

政策 probe 在現有電腦以 process-scoped Restricted 政策執行 inert script，不是全新 Windows VM 安裝測試。測試數據只適用各自已測來源檢查點；保留 warnings，不隱藏也不轉稱失敗。

## 保留限制與後續驗收

未聲稱完整程序樹取消證明。Issue **#12 保持 open**，涵蓋較廣的生命週期／crash／STOP、恢復及負載驗收。2026-10-04 Gemini Antigravity compact stdio 的提示觸發原生身分、完整讀取及同房回覆為歷史 PASS；自動閒置喚醒仍 **NOT RUN**。既有 Claude／Codex／cloud 證據保留原版本界線，此檢查點未增加新 cloud 證明或 token 成本量測。

待 PostgreSQL、promotion、browser 及原生驗收實際完成後，附確切來源／runtime 版本再更新狀態。來源測試、安裝器完整性及提示觸發的原生操作均不等於自動喚醒驗收。
