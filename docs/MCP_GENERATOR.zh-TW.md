# 記憶庫與 MCP 產生器

公開操作手冊為 `/help`，公開 CA 下載為
`/downloads/ys-ai-memory-ca.crt`；登入後的 `/ui/mcp` 提供建立記憶庫、
簽發 worker token、輪替、撤銷，以及 Codex／Claude Code 設定範本。
Claude stdio 安裝包下載為 HTTPS 的
`/downloads/ys-memory-stdio-1.1.1.zip`；公開手冊與後台提供入口。

部署需設定 `HUB_WEB_ROLE=admin`、`HUB_WEB_MCP_ENABLED=true`，以及固定的
`HUB_WEB_OWNER_ID` UUID。這個 UUID 代表本安裝的單一網頁管理帳號，
不隨使用者名稱或密碼變更；備份、還原或改名時必須保留。
`HUB_PUBLIC_BASE_URL` 必須是正確的 HTTPS origin；設定範本不信任傳入的 Host。

原本 `HUB_WEB_PROJECTS` 範圍繼續有效；啟用管理的 admin 額外取得由該
owner UUID 建立的記憶庫。唯讀帳號不會取得這個額外範圍。既有未授權
記憶庫不能被重新建立或認領。此功能沒有新增多帳號或密碼管理介面。

每個管理型 token 只對一個記憶庫授予 worker 角色。原始值只在簽發或
輪替的 POST 回應顯示一次，資料庫只存 SHA-256；重新整理不會重送原值。
下載的設定檔只引用 `YS_AIMEMORY_TOKEN` 環境變數，不含 token。
原始 token、登入 cookie、私鑰均不可放進 Git、Hub 來源或測試報告。

Claude stdio 安裝包使用官方 Python MCP SDK 將本機 stdio 轉送到此 Hub 的
HTTPS `/mcp`，保留 CA pin、憑證鏈與 hostname／name constraints 驗證。
本環境 Claude CLI 2.1.278 直接 HTTP 已遇到 `UNSUPPORTED_CONSTRAINT_TYPE`；
`NODE_EXTRA_CA_CERTS` 不能保證修復 TLS runtime 的限制，不可關閉 TLS。
Codex 的 HTTP 範本繼續提供；[按需 MCP](EFFICIENT_MCP.zh-TW.md) 另有專案限定 stdio 範例。設定範本不代表原生客戶端已驗收。

ZIP 包含 `bridge.py`、`connection.json`、公開 CA、`requirements.lock`、
`README.txt`。endpoint 與 CA 來自部署設定，不取自請求 Host，不帶 worker
token；CA 缺失或無效時下載不可用。Windows 使用者在自選新目錄解壓，
建立 Python 3.12 `.venv` 並安裝 `requirements.lock`，再執行
`.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config`。
此命令不連線、不需 token，只印出本機絕對路徑的設定；使用者手動合併到
自己專案 `.mcp.json` 的 `ys_memory` 項目，不覆寫其他 server 或全域設定。
完整步驟見 [客戶端接線](CLIENT_SETUP.zh-TW.md)。

`--compact` 使生成的設定加入相同旗標，本機只列 `memory_tools` 與 `memory_call`，初始化不連 Hub。只有明確工具請求才驗證上游與 worker token。compact 的 Connected 僅表示本機 adapter 就緒；需實際呼叫身份工具驗收。省略旗標仍為原本完整 relay；不要把通用 `memory_call` 標成唯讀，它也能轉送 token 已獲准的寫入。

啟動官方客戶端的程序需持有自己的 `YS_AIMEMORY_TOKEN`；設定只引用環境
變數名稱。下載或產生設定不會核准工具、替模型登入、修改既有聊天或自動
喚醒 AI。CA 更新需重新核對可信通道指紋與新安裝包；pin 不自動跟著更新。
設定、CLI Connected、SDK 唯讀、原生模型工具呼叫及雙 AI 對話須分別驗收。

同一記憶庫的兩個 AI 可各以自己的 token 呼叫 `send_message`／`list_messages`。
Hub 完整工具集請以目標 MCP 的 `tools/list` 核對版本；compact 本機列表則固定為 2 個入口。寄件者由 token
決定，所有角色都只能讀本人寄出／收到的訊息，admin 不會取得旁觀權限。
操作步驟見公開 `/help#messages` 與 [訊息手冊](MCP_MESSAGES.zh-TW.md)。

輪替及撤銷在資料庫交易中檢查版本，後續認證請求立即拒絕舊值。
它不會取消已通過認證且正在執行的請求，也不會自動恢復或移交任務；
需要時應從任務管理明確復原。撤銷的 worker ID 不可重新指派。
停用 `HUB_WEB_MCP_ENABLED` 僅關閉管理功能，不撤銷已發行的 token。
原有 `HUB_AUTH_TOKENS` 保持有效，並由部署管理者維護。

輪替保留 worker ID 與其訊息歷史。撤銷後該 token 的後續收發請求會被拒絕，
已保存的訊息不會被刪除。工具傳送成功表示伺服器已保存，不表示收件 AI
已讀取、理解或接受工作，也不會代替任務認領與交接。

管理權限與憑證資料表於 schema v3 加入；訊息資料表於 schema v4 加入，另外保存持久化紀錄。
升級前請備份 PostgreSQL 和部署環境，並以獨立資料庫驗證還原。舊 app
會拒絕比它更新的 schema；回退前先協調停止寫入，再還原對應版本的備份
與配置，不可直接將舊 app 指向已遷移的資料庫，亦不可覆寫或刪除現有 volume。

HTTP bootstrap 僅供 GET/HEAD `/help` 和公開 CA，其他路徑與方法拒絕；
stdio ZIP 只從 HTTPS 提供，不能改用 HTTP 下載。
公開 CA 掛載至 app 專用只讀目錄；TLS 私鑰只掛載到 nginx。HTTP 下載
仍需由可信通道核對憑證 DER 指紋；同一 HTTP 頁上的指紋不提供獨立信任。
私有 CA 是客戶端需要額外信任設定的原因，不是單純因為沒有網域。

操作手冊引用已查證的 [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、
[Codex CA](https://learn.chatgpt.com/docs/auth#custom-ca-bundles)、
[Claude Code MCP](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson)
及 [Claude Code CA](https://code.claude.com/docs/en/network-config#custom-ca-certificates)。
範本支援不代表每個桌面託管環境已完成原生 MCP 驗收；實測結果須另列。
