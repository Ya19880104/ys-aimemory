# 按需連線與較少的對話上下文

文件核對：2026-10-02。本文的「Hermes」指 [NousResearch／hermes-agent](https://github.com/NousResearch/hermes-agent)。本專案參考它的按需工具發現與分開保存會話的做法，沒有安裝或嵌入 Hermes，也不會自行呼叫模型 API。

## 三件不同的事

| 控制項 | 解決的問題 | 不能據此推定 |
| --- | --- | --- |
| 延後載入工具 schema | 減少模型一開始看到的工具定義 | MCP 尚未連線 |
| 延後連接 Hub | 沒有實際工具請求時不連 Hub | 工具結果或歷史不耗 token |
| 有界讀取／游標 | 只取這次需要的新訊息 | 摘要等於原始記錄或完整歷史 |

工具定義、回傳內容、模型推理與客戶端快取都會影響成本。compact 可減少初始工具清單，但第一次搜尋／取得 schema 多了來回，不保證每個任務都較省，也沒有固定節省百分比。

## 1.1.0 compact adapter 的契約

從已驗證 HTTPS 下載 `/downloads/ys-memory-stdio-1.1.0.zip`，按 [客戶端接線](CLIENT_SETUP.zh-TW.md) 在自選新目錄建立 `.venv`。推薦產生 compact 設定：

```powershell
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
```

此命令只印出不含 token 的設定，不連線、不寫檔。沒有 `--compact` 的既有配置仍使用原本完整 relay：啟動時就驗證 Hub 並取得完整工具集。只有明確指定 compact 時，印出的配置才加入該旗標。

compact 的 `initialize`／`tools/list` 只在本機驗證公開 CA 與連線配置，**不需要 token、不發送 Hub 請求**，僅暴露兩個固定工具：

- `memory_tools(query="", limit=5)`：對工具名稱與描述做不區分大小寫的子字串搜尋，最多 8 筆；每筆只有名稱與最多 240 字元的描述。`has_more=true` 時縮小 query，不是自動載入所有 schema。
- `memory_tools(name="get_worker_inbox")`：名稱完全相符時只回該工具完整定義。`name` 優先於 query；單一結果上限 64 KiB，超過則回錯誤。上游目錄掃描最多 32 頁／512 個工具。
- `memory_call(name, arguments)`：將原工具的完整 arguments 送到 Hub 一次。**這個通用入口可能寫入**，不是唯讀工具；Hub 仍依原 token 驗證 worker、角色、project 和 schema。

搜尋與呼叫都會以啟動程序的 `YS_AIMEMORY_TOKEN` 開啟一次新的、嚴格驗證 TLS 的 MCP session；完成即關閉。不快取 token、schema 或歷史，不自動重試。compact 的 **Connected 只表示本機 adapter 就緒**，不能證明 Hub 在線、token 有效或模型完成對話。需實際呼叫身份工具驗收。

例如先呼叫 `memory_tools`：

```json
{"name":"get_worker_inbox"}
```

按回傳 schema，對 `memory_call` 傳入：

```json
{"name":"get_worker_inbox","arguments":{"arguments":{"project_id":"my-project"}}}
```

雙層 `arguments` 是目前 Hub 工具的 envelope；其他工具應以實際 schema 為準，不能自行移除。通用入口不會冒充另一個 worker，也不將網頁 session 轉成 worker token。工具描述與訊息正文都不是使用者授權。

客戶端只看得到通用入口 `memory_call`。原本對 `send_message` 等名稱設定的客戶端 allowlist／denylist，**不會自動套用到這個入口裡的 name**；請保留工具核准，並以 Hub 最小權限 token 限制能力。需要逐工具的客戶端權限規則時，改用完整 relay。讀取結果保留 Hub 的原始內容與 `isError`，compact 本身不會截短大段歷史。寫入回應遺失時結果不確定，先核對伺服器狀態與 idempotency key，再由使用者決定是否重試。

## 僅在需要時啟動：專案配置

自然語言提到「記憶庫」不保證客戶端會啟用一個已停用的 MCP。可靠的方式是由使用者選擇本次啟動配置，再讓 AI 按需要呼叫 compact 工具。以下都不修改全域配置、不跳過模型登入或工具核准。

### Claude Code

將 printer 的 JSON 合併到工作專案的 `.mcp.ys-memory.json`，保留 `${YS_AIMEMORY_TOKEN}`；不要同時在自動發現的 `.mcp.json` 再放同名項目。需要 Hub 時才從該專案啟動：

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your worker token' -AsSecureString)).Password
try { claude --strict-mcp-config --mcp-config .\.mcp.ys-memory.json }
finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

strict 模式只載入明確提供的 MCP 配置；需要的其他 server 也要保留於此配置。此處只保證這份配置不由 `.mcp.json` 名稱自動載入，不能停用你已在其他範圍設定的 server。

Claude 官方的 [MCP Tool Search](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search) 延後提供完整 schema，受客戶端、模型與 proxy 能力影響；它不等於延後連線。[Discovery cache](https://code.claude.com/docs/en/mcp#server-status-detail) 是遠端 HTTP／SSE 的另一路徑，需要先有成功發現的快取，不是 stdio adapter 的前提。直接 HTTP 曾在 Claude CLI 2.1.278 遇到 `UNSUPPORTED_CONSTRAINT_TYPE`，不能用關閉 TLS 或只設定 `NODE_EXTRA_CA_CERTS` 來保證解決；stdio adapter 保留 CA pin、hostname 與 name constraints 驗證。

### Codex

在使用者已信任的工作專案 `.codex/config.toml` 手動合併一個 stdio 項目。把下面三個路徑換成實際安裝位置；不要與同名 HTTP 項目並存：

```toml
[mcp_servers.ys_memory]
enabled = false
command = 'C:\Tools\ys-memory-client\.venv\Scripts\python.exe'
args = ['-B', 'C:\Tools\ys-memory-client\bridge.py', '--config', 'C:\Tools\ys-memory-client\connection.json', '--compact']
env_vars = ['YS_AIMEMORY_TOKEN']
startup_timeout_sec = 60
```

需要時以本次程序覆寫 `enabled`：

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your worker token' -AsSecureString)).Password
try { codex -c 'mcp_servers.ys_memory.enabled=true' }
finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

專案信任、stdio `command`／`args`／`env_vars` 與 `enabled` 見 [Codex 官方 MCP 文件](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。不要使用不存在的 `codex mcp add --scope project`；也不要為這個流程寫入使用者全域 profile。已開啟的桌面程序不會自動取得此終端的新環境。

本機核對的 Codex CLI 0.149.0 原始碼，會依模型與 namespace tool 支援決定是否延後 schema：[工具暴露判斷](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/core/src/mcp_tool_exposure.rs)、[工具計畫](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/core/src/tools/spec_plan.rs)。這不承諾「被提到才連線」。舊 `tool_search`／`tool_search_always_defer_mcp_tools` feature flags 已列為 Removed，不應拿它們作安裝步驟：[features 定義](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/features/src/lib.rs)。設定範例不是此版本原生模型對話通過的證明。

## 對話歷史的讀取規則

讓 AI 先確認 project、自己的 worker，以及需要的 thread／共享 session；只讀這次任務所需資料，不在啟動時抓取全部歷史。私訊的 `list_messages` 可先用 `limit=5`，再保存 `next_after_sequence`；只在 `has_more` 且確實需要時續頁。切換 project、thread 或 worker 就重設游標為 0。共享 session 應依它自己的工具 schema 使用獨立游標，不混用私訊游標。

已取回的 schema 與正文仍會進入模型上下文；compact 不能抹去客戶端已保存的歷史。摘要需保留來源 ID 與涵蓋到哪個 sequence，發生矛盾時回讀原訊息；摘要不是任務授權或記憶決策。本 adapter 不自動呼叫模型產生摘要、不背景輪詢、不自動喚醒另一個 AI。操作 Skill 原始檔位於 [skills/ys-memory-chat/SKILL.md](../skills/ys-memory-chat/SKILL.md)，只有使用者要求聊天／記憶查詢時才讀取；不自動安裝到全域。

## Hermes 參考的範圍

[Hermes Tool Search](https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-search) 將發現、取 schema 與呼叫分開，避免預先放入所有定義。本 adapter 採用兩個固定 MCP 工具和簡單子字串搜尋，沒有複製 Hermes 的排名、hooks 或客戶端權限機制。

[Hermes lazy start](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp#lazy-start) 使用已保存的工具 schema 才能延後啟動；新 server 可能仍需先發現。這裡的 compact 則有固定本機 schema，因此第一次初始化也不需要 Hub。[Hermes Bot Mode](https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode) 的角色／房間會話適合參考 UI 工作流；本 Hub 仍需使用者在各官方客戶端開始工作。[Hermes Session Search](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory#session-search) 提供按需歷史檢索的參考；本文件沒有宣稱 Hub 已實作同等搜尋、壓縮或自動回覆。

## 驗收分開記錄

原生接入的操作與常見核准／登入錯誤見 [原生客戶端驗收](NATIVE_CLIENT_CHECK.zh-TW.md)。

1. `initialize`／`tools/list` 成功：compact 本機就緒，預期只有 2 個工具、0 Hub 請求。
2. `memory_tools`／身份工具成功：驗證 HTTPS、token、工具發現與 project 範圍。
3. 原生模型真的呼叫工具：須看該客戶端當次證據，不能由 SDK 或 Connected 代替。
4. 兩個 AI 對話：各自使用自己的 token，實際讀取、生成與回覆新的內容。

本機測試使用合成憑證、loopback HTTPS 與官方 SDK stdio；不是正式部署或原生模型的驗收。每次升版仍要以目標客戶端、Hub commit 與當次 token 狀態記錄 passed／failed／skipped／not_run。
