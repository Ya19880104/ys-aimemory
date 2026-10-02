# ys-aimemory 0.2 — 開發與測試交付

驗證時間：2026-09-30 UTC。這是功能較完整的內網試用版程式，尚未完成使用者內網／正式客戶端的部署驗收。

## 本次完成

- 帳密網頁從唯讀擴充成明確 read_only/admin 角色：建立專案、來源與任務、批次記憶匯入、搜尋分頁、任務詳情、inbox、提案核准與交接恢復
- 網頁寫入使用 CSRF、一次性表單、POST/Redirect/GET 與共同 Hub 服務端權限；沒有任意角色提升或 token 顯示
- 資料庫保存 session、CSRF、操作 nonce 與登入節流，跨程序登入／登出一致；設定輪替永久撤銷舊狀態，舊設定 worker 拒絕服務
- PostgreSQL GIN／全文搜尋和 SQLite FTS5；中文採明確字面子字串回退
- 原子批次匯入、CAS revision、依專案與身分限制的冪等 key、来源版本和分頁中繼資料
- 新增衍生索引、交易內同步索引工作、健康檢查與重建；新增式鎖定 migration 保留 0.1 資料，拒絕未知未來版本
- 四個獨立 AI 身分透過 MCP 取得 inbox／必要來源、認領、確認閱讀、接受、驗證、交接與恢復
- 結構化交接保留成果 commit、變更檔案、實際測試、阻礙與下一步；管理員恢復有 revision/generation/fence 比較及理由稽核
- Docker／HTTPS 部署設定、角色預檢、固定相依版本、GitHub PostgreSQL CI、正式 PostgreSQL 套件驗證及可重現測試腳本

## 實際通過的驗證

| 驗證 | 結果 |
|---|---|
| 乾淨 Python 3.12 `python -m pytest -q` | 69 passed、2 skipped、3 warnings |
| `python scripts/test-deployment.py` | 11 passed |
| PostgreSQL 18.6 單使用者模式 | 42 個實際 SQL statements 通過 |
| Python 編譯、Shell 語法、相依套件相容性 | 通過 |
| 四 AI MCP 協定流程 | 已透過 TestClient 與官方 SDK 的 JSON-RPC 端點驗證 |

69 項包含來源／租約／交接／恢復既有回歸、索引搜尋與隔離、批次上限、UTF-8 bytes、相同請求重試、衝突 key、並行 CAS、索引錯誤交易回滾、索引修復、舊資料升級、管理網頁功能、XSS／CSRF／角色／範圍、跨 instance session／登出、並行登入節流、單次 nonce、設定 A→B→A 不復活舊 cookie。

PostgreSQL 單使用者驗證使用官方 PostgreSQL 18.6 套件，驗證雜湊後執行真正引擎。42 個 SQL statements 涵蓋生成的 schema／web-auth tables、重複 DDL 初始化、GIN／TSV、英文排名搜尋、中文 ILIKE、專案條件、更新與回滾。這不是 42 個獨立端到端測試。

修正的重要問題：舊交接封包重用、未知接手者、來源空白改變 hash、不完整索引被誤判健康、搜尋分頁、CSP 樣式、設定輪替後舊 session 可復活。均有對應回歸檢查。

## 未執行／尚未通過

- PostgreSQL server 的私有 Unix socket 在此環境回傳 EPERM，即使經允許的執行審查仍無法啟動；沒有繞過限制。故 psycopg 連線、PostgreSQL 並行交易、多程序 auth 的 PostgreSQL 實測、pg_dump/restore 未完成
- 2 項 disposable PostgreSQL runtime 測試因此 skip；其他 PostgreSQL 參數化對照也未啟用。已準備 GitHub PostgreSQL 18 service job，但尚未執行
- Docker 映像建置、Compose／TLS／備份還原服務、正式 PVE 及 Windows 四個 AI 客戶端尚未實測
- 真實瀏覽器連本機服務被環境阻擋。HTTP／HTML／表單與安全驗證已完成；視覺、RWD 與真正瀏覽器操作驗收仍未完成
- GitHub 儲存庫還未由本次工作建立／推送；等待使用者完成登入。2026-09-30 18:01 UTC，連接工具仍無法讀取目標 repository（404）

不能把 SQLite／TestClient 或單使用者 SQL 成功，改稱上述項目已通過。

## 使用與後續驗收

先閱讀 README、docs/DEPLOYMENT.zh-TW.md 與 docs/WEB_DASHBOARD.zh-TW.md。沒有預設管理員密碼或正式 token；部署者自行配置自己的帳號、密碼 hash 與各 AI 的最小權限身分。

在支援 socket 的授權測試環境，可執行 `scripts/postgres-test-runtime.sh` 搭配 pytest，或用提供的 GitHub PostgreSQL CI。這些腳本只應對可拋棄測試資料庫執行；正式環境另依部署與備份程序。

目前 canonical 專案資料仍是 JSON aggregate，尚未做大規模效能驗收。向量／語意搜尋、獨立背景索引 worker、自動抓取遠端 repository、多使用者帳號管理、OAuth、正式公網啟用不在此版完成範圍。Hub 保存 AI 的測試聲明與證據，但不能證明模型理解或阻止 AI 直接修改本機檔案。

所有正式程式與文件都在本包；不包含使用者的真實專案內容、帳密或登入 cookie。可重現相依版本見 requirements-tested.txt。
