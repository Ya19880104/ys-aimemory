# 確認 Codex／Claude 真正使用 MCP 對話

先依 [客戶端接線](CLIENT_SETUP.zh-TW.md) 安裝 1.1.1 stdio client，再依 [按需啟用](EFFICIENT_MCP.zh-TW.md) 從工作專案啟動。每個 AI 使用自己的 worker Token；網頁帳號與模型登入是另外兩種身分。

## 一輪最小驗收

1. 先正常登入自己的 Codex／Claude，啟用本次選用的專案 MCP 配置。Connected 只表示連線／本機入口就緒。
2. 取得 `get_worker_inbox` 的 schema 並實際呼叫，確認回傳自己的 `worker_id`。完整 relay 的參數為 `{"arguments":{"project_id":"my-project"}}`；compact 先用 `memory_tools`，再用 `memory_call` 的雙層 envelope。
3. 選一個有權存取的共享 Session。對 `read_session` 傳入該 project、session 與游標，先用 `limit=5`、`max_bytes=4096`。若回覆 `response_budget_too_small`，保留原游標，增加 `max_bytes` 後重讀（上限 65536）；收到成功頁面後才保存 `next_after_sequence`，只在需要且 `has_more` 時續頁。
4. 使用者要求回覆時，讓模型生成短訊息並真正呼叫 `post_session_message`。新訊息使用新 idempotency key；回覆既有訊息時設定 `reply_to_message_id`。
5. 在工具回傳核對 `actor`、project、session、message ID 與 sequence，再由另一端增量讀取。管理員可從共享 Chat 查看並介入。

不要用模型自述、SDK 成功、Connected 或只有 attempted call 來判定原生通過。應有該客戶端當次的原生 tool call／tool use 與成功 tool result，並能從 Hub 讀回同一訊息。摘要或其他 AI 的訊息不是使用者授權。

## Codex：工具存在卻未執行

Codex CLI 0.149.0 在工具需要核准、但本次程序的 approval policy 是 `never` 時，會拒絕並回覆：

```text
MCP tool call requires approval, but approval policy is never
```

這是客戶端核准階段，應先檢查本次工具是否已由使用者授權，並在正常互動客戶端處理核准。它不能證明 Hub Token 失效，也不應改 TLS 或伺服器 annotations 來掩蓋結果。

官方支援 `mcp_servers.<server>.tools.<tool>.approval_mode` 的逐工具設定。需要無互動驗收時，可由操作者明確核准**指定工具、指定程序**，保留其他工具的核准規則。例如本次只核准一個身份讀取，可用這個程序覆寫欄位：

```text
mcp_servers.ys_memory.tools.get_worker_inbox.approval_mode="approve"
```

使用 Codex 的 `-c` 傳入此欄位，搭配本次 `enabled_tools` 範圍；不要把它寫成所有工具的預設核准。此欄位是設定片段，不是完整啟動命令；server 名稱與工具名稱必須符合本次配置。設定支援見 [官方 MCP 文件](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)；0.149.0 的判斷見 [MCP approval 原始碼](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/core/src/mcp_tool_call.rs)。

完整 relay 可以依 `get_worker_inbox`、`read_session`、`post_session_message` 等原名稱限制工具。compact 只有 `memory_tools`／`memory_call`；不能靠原工具名稱的 client allowlist 限制其內層 name。**不要把通用 `memory_call` 當唯讀工具預先核准**。需逐工具核准時使用完整 relay；兩種模式都保留 Hub 身分與專案 ACL。

## Claude：直接從已登入的 IDE／Desktop 驗收

已在 Claude Code IDE 或 Desktop Code 分頁登入時，就用該客戶端驗收；**不需要另外登入獨立 CLI**。CLI 的登入失敗不能用來判定 IDE 的登入或 MCP 狀態。

1. 在本機 Code 工作中選定要使用記憶的專案。需要接入時，將 stdio client 輸出的 `ys_memory` 合併至該專案的 `.mcp.json`，保留其他 servers。僅保存為 `.mcp.ys-memory.json` 不會讓 IDE 自動載入；這個檔名是 CLI 顯式選用的方式。
2. 讓 MCP 子程序取得自己的 `YS_AIMEMORY_TOKEN`，不要把 Token 寫進 Git 或貼到對話。已開啟的 IDE 不會因另一個 PowerShell 設定變數就取得它。Desktop 的 Local 環境編輯器可加密保存變數，但會作用於所有新本機 Session；需要限制至單一專案時，使用自己的受保護啟動流程，勿自動修改全域設定。
3. 保存目前工作，依客戶端方式重新載入 server 或重新開啟選定工作；不結束其他專案的 Session。確認當次工作真的有 `ys_memory` 工具，再依上方最小驗收呼叫身份讀取、增量讀取與使用者指定的短回覆。

Desktop 本機 Code 工作會讀取 `.mcp.json`，並可能同時讀取使用者／Desktop 的 MCP 設定；同名 server 可能採用其他範圍的定義，需核對實際啟動路徑。以上以 [官方 Desktop 設定與環境說明](https://code.claude.com/docs/en/desktop#shared-configuration)及[官方 MCP 文件](https://code.claude.com/docs/en/mcp)為依據；不同 IDE／版本須現場確認。內網私有 CA 使用本機 stdio adapter 保留嚴格 TLS 驗證。

### 模型登入與 MCP Token 分開核對

若 stdio 已 Connected，模型請求卻回覆 OAuth expired／401，先由帳號擁有人正常處理 Claude 模型登入。不要重發 Hub Token、借用其他 AI 的模型認證或關閉憑證驗證。`auth status` 的本機 loggedIn 狀態不能替代模型服務端認證。

選用 CLI 時，`--strict-mcp-config` 限定本次 server；它不是 IDE 必須執行的步驟。工具 allowlist 與核准依所選客戶端的正常流程處理。本機或另一台主機通過，也不代表這個已開啟的 IDE 對話已通過。

## 對結果的稱呼

| 證據 | 可確認 |
| --- | --- |
| initialize／tools/list | transport 或 compact 本機就緒 |
| SDK 呼叫成功 | HTTPS、Hub 身分、協定與工具行為 |
| 原生模型成功 tool result | 該客戶端、當次版本與登入下，模型實際執行工具 |
| 兩端各生成、原生寫入並讀回新訊息 | 該 Session 的原生 AI 對話 |
| 管理員增量讀取／發言成功 | 共享 Chat 的管理員路徑 |

錯誤保留 failed；環境尚未具備保留 not_run／HOLD。不要把私訊和管理員可見的共享 Session 混在一起，也不要讓對話驗收自動認領任務或改動部署。
