# 驗收與失敗情境

[English](ACCEPTANCE_TESTS.md) | [繁體中文](ACCEPTANCE_TESTS.zh-TW.md)

本清單是驗收設計，不代表每個環境都已實測。實際結果請記錄 commit、日期、命令、退出碼、環境與日誌；`pytest`、Docker、PostgreSQL、Windows 與正式客戶端要分別標示通過／失敗／未執行。

## 自動化與服務門檻

| 情境 | 操作 | 預期 |
|---|---|---|
| 缺少驗證設定 | 不設 HUB_AUTH_TOKENS 啟動 | 啟動失敗，不使用預設密碼 |
| 無效身分 | 未帶或帶錯 Bearer 呼叫工具 | 拒絕；healthz 例外 |
| 跨專案 | A worker 操作未授權 project | forbidden |
| 偽裝權限 | worker 登錄來源或核准提案 | forbidden |
| 少讀文件 | prepare 後不 read 全部就 acknowledge | unread_context |
| 未接受交接 | read/ack 後直接 checkpoint | handoff_not_accepted |
| 過期文件 | prepare 後管理者更新 source | 舊 packet 拒絕，須重讀 |
| 偽造 hash | checkpoint 帶其他／舊 hash | invalid_evidence |
| 同時認領 | 兩身分同時 claim 同任務 | 僅一個取得租約 |
| 租約過期 | 超過 lease_until 後寫入 | invalid_lease；新認領有新 fence |
| 續租 | 有效且已接受 packet 續租 | 截止延後；過期不能復活 |
| 舊持有者 | handoff 後原 worker 寫 checkpoint | 舊 fence 被拒絕 |
| 非指定接手者 | 交接給 B，C claim | wrong_recipient |
| 提前準備封包 | B 在交接前 prepare，交接後沿用 | task generation 不符，需新 prepare |
| 未核准提案 | proposal 後搜尋 | 明確 status=proposed，不當作 approved |
| 過期提案 | 提案之後來源更新再核准 | stale proposal/revision 拒絕 |
| 結案 | complete 後再寫或認領 | completed 拒絕 |
| 客戶端角色變動 | implementer 換 reviewer | 不增加 admin/approver 權限 |

以 `tests/` 的實際測試為已自動化覆蓋的依據；以上也包括應由正式環境演練的項目。不要為了讓測試成功關閉 auth、Origin/Host 驗證或改成共用 admin token。

## 四客戶端人工演練

1. 使用獨立 sandbox project 和四個明確 worker，各自客戶端完成 initialize、tools/list 與只讀 search。證明彼此不共用工作目錄／branch／身份。
2. coordinator 讀需求並分工；管理者建任務，implementer 完整開工後在允許路徑做小變更、測試、記錄確切 commit。
3. implementer 指定 reviewer 交接。tester 嘗試插隊應拒絕；reviewer 必須在交接後重新 prepare 並讀全部來源。
4. reviewer 驗 diff 與驗收條件後交給 tester；tester 對相同 commit 真正執行測試，記錄一個未測項，確認不會被摘要抹去。
5. 中途由管理者改來源，確認所有舊 packet 失效。各 worker 重新建立上下文，檢查改需求後的成果，而非只刷新數字。
6. 模擬一個客戶端關閉／額度耗盡：租約到期再由合法 worker claim；舊客戶端回來後寫入應被拒絕。
7. 用持有者身分記錄 complete，再由人類檢查 artifact 與同一 commit 決定正式驗收。不要自動合併／部署。

## 營運與已知邊界

- PostgreSQL 實際併發、重啟後資料保留、備份與獨立還原測試不能由 SQLite 測試代替
- TLS 驗證需由 Windows 主機、Windows VM 各測一次；不能忽略憑證警告
- 待接手者永久不可用：由 admin 以最新 project revision、task generation/fence 與非空理由呼叫 `recover_task`，重新指定已配置且獲授權的 worker，或解除指定；確認舊租約／fence 失效、新接手者須重做 prepare/claim/read/acknowledge/accept/validate，已完成任務不得重開。不可直接改 DB 假裝正常交接
- 同一 task 的 file paths 是約定；跨 task 的重疊路徑未形成伺服器檔案鎖，由 coordinator 和 Git／OS 控制預防
- approver/admin 可以批准自己提案，本版沒有「不得自我核准」的分權門檻；若需要四眼原則需擴充伺服器政策並測試
- 測試證據可被人寫假：hash 綁定只保證引用相同來源，不驗證語意或實際執行；正式驗收需可信 CI／獨立重跑

## Inbox、結構化交接與網頁

- B 不知道 task_id，使用 get_worker_inbox 仍可發現指定給自己的 pending_handoffs；A/C 的 inbox 不應冒充 B
- handoff 缺 next_steps、result_commit 或 test_results 時拒絕；not_run 保留理由，不自動改成 passed
- 未登入 /ui 需登入；錯誤密碼不透露是否存在其他帳號；登入失敗節流生效
- 成功登入只看 HUB_WEB_PROJECTS 指定專案；HTML 內容需 escape，不能把來源中的 script 執行
- 瀏覽器 session 不可呼叫 MCP/REST；worker token 不等同網頁 session
- session 到期或登出後須重新登入；同一資料庫與相同配置下，尚未到期的 session 應在應用重啟後繼續有效。設定輪替須撤銷舊 session／nonce，舊配置 instance 不可繼續使用舊登入；登入／登出 CSRF 防護按 web tests 驗證。PostgreSQL 下多程序與正式多 worker 部署仍為 not_run，須在目標環境另行驗收
- 網頁的 MCP 區塊區分配置身分與已觀察活動，不聲稱 stateless 客戶端即時在線

## 本次文件範例驗證

2026-09-30：在隔離 loopback FastAPI、可拋棄 SQLite 與僅程序存續的測試 token，實際執行 `python docs/demo_workflow.py`，退出碼 0。包含 A 的完整開工、checkpoint、結構化交接、B inbox 發現、重新開工與 complete。三個 Skill 通過 quick_validate。這是 REST 演練，不替代 MCP 傳輸測試、PostgreSQL 併發、Docker、PVE 或四個正式客戶端端到端驗收。
