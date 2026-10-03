# 官方客戶端接線與訂閱使用

文件更新：2026-10-03。版本與帳號可用功能可能不同，安裝前以實際官方客戶端的 help、設定畫面和以下官方文件核對。設定範例與實際連線驗收分開記錄。Gemini CLI、Grok / xAI API 的接入界線、快速安裝命令與手動範例見[多客戶端安裝入口](MULTI_CLIENT_SETUP.zh-TW.md)。

## 已登入 Claude Desktop，為什麼貼設定仍連不上？

Windows 可先使用[單一指令安裝器](CLAUDE_WINDOWS_SETUP.zh-TW.md)，它會完成 adapter、專案設定及目前使用者加密 Token 儲存；**採用此方法不必再填 Desktop 全域環境變數**。以下保留手動安裝方式，兩者擇一，不要重複建立 `ys_memory`。

一次設定後，日常只需貼「加入指定專案／對話」指引。但第一次須完成三件事：**安裝 adapter → 合併 MCP 設定 → 提供自己的 worker Token**。把 JSON 或 MCP 網址貼到聊天，本身不會完成客戶端設定；Claude 模型登入也不會提供 Hub Token。

1. 在 Desktop 的 Code 分頁使用 **Local**，選真正的開發專案，將 `--compact --print-claude-config` 輸出合併到該目錄的 `.mcp.json`。保留其他 MCP，Python／bridge／connection 三個路徑必須在執行 Claude 的那台電腦存在。
2. 保留 `.mcp.json` 中的 `${YS_AIMEMORY_TOKEN:-}` 引用。到 **新對話的環境選單 → Local 旁齒輪 → 環境編輯器**，新增名稱 `YS_AIMEMORY_TOKEN`，值填入 **Claude 專屬 worker Token** 並保存。這裡填真正的 Token，不是引用文字；不用貼到聊天或共享設定檔。
3. 儲存後開新本機 Code 對話；如果版本仍用舊環境，保存工作再重啟 Desktop。依畫面審閱專案信任與 MCP 核准。**不用另外登入 CLI**，也不要為了測試改成繞過權限。
4. 請 AI：「用 YS Memory 的 `memory_tools` 取得 `get_worker_inbox` schema，再以指定 project_id 呼叫，回報 worker_id；不要認領任務。」工具結果身分正確後，才貼共享對話的加入指引。

環境編輯器加密保存，但會套用所有新本機工作。需要各專案不同 Token 時，改用各自受保護的啟動環境，不能讓不同 worker 混用。`.mcp.json` 的 `${...}` 引用只會取值，不會產生 Token；另一個 PowerShell 設定的變數也不會注入已開啟的 Desktop。**不要把實際 Token 寫進可能共享的 `.mcp.json`；即使加入 `.gitignore`，已追蹤的檔案仍會被提交。** 官方說明見 [Desktop 本機環境](https://code.claude.com/docs/en/desktop#local-sessions)與[共用 MCP 設定](https://code.claude.com/docs/en/desktop#shared-configuration)。

1.1.1 輸出 `${YS_AIMEMORY_TOKEN:-}` 空值預設；未設定時 adapter 回 `TOKEN_MISSING`，不把未展開的引用送到主機。不同 Claude 版本對缺值引用的行為可能不同，不能拿「env 欄位非空」當作 Token 已傳入。詳見[官方環境展開規則](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson)。

| 看到的狀況 | 下一步 |
| --- | --- |
| 找不到 `memory_tools` / `memory_call` | 核對 Local 專案、`.mcp.json`、路徑、核准與重新載入；先不用測 Token |
| Connected，但 `TOKEN_MISSING` | Token 沒進 MCP 子程序，或仍是引用文字；補上實際秘密環境值 |
| `AUTH_REJECTED` | 主機拒絕身分；核對 Token 是否有效、是否屬於這個 Hub |
| `TLS_VERIFY_FAILED` | 核對公開 CA、指紋、主機名與憑證有效期；勿關閉 TLS 驗證 |
| `UPSTREAM_FAILED` | 核對主機可達、服務狀態與 connection.json；不要把所有失敗都當 Token 問題 |
| `outcome unconfirmed` | 工具請求可能已送出；寫入先查結果及冪等鍵，不自動重送 |

`Hub tool not invoked` 表示尚未送出 Hub 業務工具；可能已嘗試初始化或唯讀工具發現。1.1.0 只有泛用失敗訊息，請下載 1.1.1 到新目錄再更新專案路徑；既有安裝不會自動升級。

2026-10-03 遠端 Desktop 實測：原先只有環境引用且程序缺 Token；測試者確認專案設定未被 Git 追蹤且已忽略後，填入自己的臨時測試 Token、開新 Code 對話，Sonnet 5.5 / Medium 已透過原生 MCP 回傳正確 worker 身分。這是受控測試方式，不是建議公開專案照貼 Token；上述一般安裝採環境編輯器。本輪沒有另行驗收環境編輯器的持久化行為。第一次錯誤參數與修正後成功均保留。

## 訂閱優先

使用 Codex 官方客戶端的 ChatGPT 登入或 Claude Code 官方支援的訂閱登入，各自保留帳號界線。本專案不供應模型 key、不共用四個帳號的 cookie，也不把 ChatGPT 訂閱視為可任意呼叫的 OpenAI API 額度。Codex 官方文件區分訂閱登入與按量 API key：[驗證說明](https://developers.openai.com/codex/auth)。

Hub 保存工具操作與共享狀態，包含 AI 明確傳送的訊息，不會自行喚醒其他 AI；人類在各客戶端下達開始、讀信或接手指示。未來要排程或自動代理模型，需要另行確認官方支援、帳號規則、費用與權限。Grok 的官方 Remote MCP API 路徑已確認，但本專案尚未原生驗收；內網部署需要另外解決雲端可達性，詳見[多客戶端指南](MULTI_CLIENT_SETUP.zh-TW.md)，不以瀏覽器自動化冒充 MCP。

## 本版傳輸

本版實作 Streamable HTTP `/mcp`。四個支援它的客戶端可連同一個 TLS URL，使用各自的 worker 身分。不能把普通 REST 路由當成 MCP；請以 initialize、tools/list、tools/call 實際確認。

Hub 的完整工具集包含 `send_message` 與 `list_messages`；數量以目標版本 `tools/list` 為準。compact adapter 只列出 2 個入口，再按需查詢 Hub 工具。同一 project 的兩個有效 worker 可收發持久化私訊；私訊正文只對寄件者和收件者可見，admin 也不能旁觀其他人的私訊。操作與欄位見 [訊息手冊](MCP_MESSAGES.zh-TW.md)。

MCP 標準的 stdio 是由客戶端啟動子程序並透過 stdin/stdout 傳遞 JSON-RPC；它不等於一個可填寫的 LAN URL。本版另提供可下載的 stdio → HTTPS 客戶端轉接器；伺服器仍接收 HTTPS Streamable HTTP。Codex 可用下方 HTTP 設定，或採用[專案限定的 compact stdio 設定](EFFICIENT_MCP.zh-TW.md)。舊 HTTP+SSE 不應與 Streamable HTTP 混淆。[官方傳輸規範](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

## Codex

先由人類核對 HTTPS 主機名、可信憑證與最小權限 worker token。把下列項目合併到你選擇並信任的專案 `.codex/config.toml`，替換成已確認網址。本流程不寫全域設定。本 Hub 需要 Bearer 驗證，不實作 OAuth；token 從程序環境讀取，勿貼進共享設定或 Git：

```toml
[mcp_servers.ys_memory]
url = "https://YOUR_VERIFIED_HUB_HOST/mcp"
bearer_token_env_var = "YS_AIMEMORY_TOKEN"
```

環境變數必須存在於啟動客戶端的程序環境。不要把不同 worker 的環境／profile 混用。設定、儲存憑證與權限提示由人類明確完成，然後測試只讀搜尋再做 sandbox 演練。[Codex MCP 官方文件](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

使用實際 `HUB_PUBLIC_BASE_URL` 的 authority；非標準 HTTPS port 需保留 port。若已有 `ys_memory`，更新同一項目，避免重複連線。以上 TOML 不含 token 值，可合併到你選定的設定範圍；不要由代理自動改寫全域設定。私有 CA 的程序設定與指紋核對請見伺服器 `/help#clients`，Codex CLI 可於啟動前設定 `CODEX_CA_CERTIFICATE`。[官方自訂 CA 說明](https://learn.chatgpt.com/docs/auth#custom-ca-bundles)

## Claude Code：stdio 安裝包

本環境的 Claude CLI 2.1.278 直接 HTTP 連線實測回報 `UNSUPPORTED_CONSTRAINT_TYPE: unsupported name constraint type`。這是 TLS runtime 對目前 CA name constraints 的相容問題，設定 `NODE_EXTRA_CA_CERTS` 不保證能解決；不可關閉 TLS、主機名驗證或移除 CA 限制來繞過。

在伺服器的 `/help#clients` 或登入後 `/ui/mcp` 取得版本化安裝包：
`https://YOUR_VERIFIED_HUB_HOST/downloads/ys-memory-stdio-1.1.1.zip`。
下載只走 HTTPS；HTTP bootstrap 不提供 ZIP。先透過可信通道取得並核對公開 CA 的 **DER SHA-256** 指紋。同一個 HTTP 頁面上的指紋不構成獨立信任；不要把 PEM 檔案雜湊誤當成 DER 指紋。

若瀏覽器尚未信任 CA，可在放有已核對公開 CA 的 PowerShell 目錄，以它驗證 HTTPS 下載：

```powershell
curl.exe --cacert .\ys-ai-memory-ca.crt --fail --output .\ys-memory-stdio-1.1.1.zip "https://YOUR_VERIFIED_HUB_HOST/downloads/ys-memory-stdio-1.1.1.zip"
```

ZIP 平鋪包含 `bridge.py`、`connection.json`、`ys-ai-memory-ca.crt`、`requirements.lock`、`README.txt`。`connection.json` 記錄部署的 HTTPS endpoint、公開 CA 相對檔名與小寫 DER SHA-256 pin；沒有 token、TLS 私鑰或模型登入資料。轉接器固定使用這份連線配置，核對 CA pin、憑證鏈、IP／hostname 與 name constraints，不跟隨 redirect、不使用環境代理或 TLS keylog，也不自動重試寫入。

1. 選擇自己的新安裝目錄並解壓，保留上述檔案在同一層；不要覆寫既有安裝。安裝目錄與 `.venv` 不加入專案 Git。
2. 主要目標為 Windows Python 3.12。在解壓目錄開啟 PowerShell，執行下列命令；套件只安裝到此處的專用虛擬環境。
3. 最後一個命令只印出 Claude 設定，不需 token、不連線。手動將 `mcpServers.ys_memory` 合併到你選定專案的 `.mcp.json`。保留其他 MCP 項目及 `${YS_AIMEMORY_TOKEN}` 引用；已有 `ys_memory` 時更新同一項目，避免同名 HTTP／stdio 並存。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
```

輸出的 `command` 使用目前虛擬環境的 Python，`args` 使用 bridge 與 connection 的本機絕對路徑。預設連線設定是 bridge 同目錄的 `connection.json`，可用 `--config PATH` 明確選擇另一份已核對的配置。安裝包不寫入任何 AI 設定；移動目錄或換電腦後須在新位置重新建立環境、產生並合併設定，不能直接沿用別台電腦的絕對路徑。

1.1.1 建議加入 `--compact`：初始化只暴露 `memory_tools`／`memory_call`，不連 Hub、不需 token；只有明確呼叫工具才以嚴格 TLS 連線。**compact 的 Connected 只代表本機就緒**。省略此旗標仍是原本啟動即連線、提供完整工具集的 relay，既有配置不自動改變。工具名稱搜尋、單一 schema、原參數傳送，以及不自動載入的專案配置，見 [按需 MCP](EFFICIENT_MCP.zh-TW.md)。通用 `memory_call` 可能寫入，原本逐工具的客戶端權限規則不會自動套用到內部工具名稱。

到已合併 `.mcp.json` 的專案目錄開啟自己的 PowerShell。從受保護位置取出該 AI 的 worker token，以隱藏輸入供給本次程序；不要把實值寫入指令、`.env`、設定檔或聊天：

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
try { claude } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

由使用者審閱官方客戶端的 project 信任和工具權限。`--print-claude-config` 不會核可工具、啟動模型、接管已登入的聊天或喚醒另一個 AI。新程序環境不會自動注入已開啟的桌面／遠端 host；保存工作後依該客戶端的專案載入方式重新開啟。用 `/mcp` 檢查，再實際呼叫 `get_worker_inbox` 和 `get_project_summary` 核對 worker／project；compact 模式先用 `memory_tools(name=...)` 取得 schema，再經 `memory_call` 呼叫。各客戶端使用自己的模型登入，本安裝包不提供或複製 provider 憑證。[Claude Code MCP 官方文件](https://code.claude.com/docs/en/mcp)

CA 輪替時重新取得安裝包及可信通道的指紋，核對後在新目錄安裝並更新專案設定；不自動更新 pin 或全域信任庫。Linux／macOS 可依同一腳本與依賴使用 `.venv/bin/python`，但仍須獨立驗證依賴安裝、原生 host 及權限；本文件不宣稱它們已通過原生驗收。

## Claude Code：其他已確認相容的 HTTP 環境

只有目標客戶端已證實支援該 CA 時，才使用直接 HTTP。可以在專案 `.mcp.json` 合併以下內容，保留環境變數引用，不要替換成 token 明文；不要與同名 stdio 項目並存：

```json
{
  "mcpServers": {
    "ys_memory": {
      "type": "http",
      "url": "https://YOUR_VERIFIED_HUB_HOST/mcp",
      "headers": {"Authorization": "Bearer ${YS_AIMEMORY_TOKEN}"}
    }
  }
}
```

私有 CA 可在本機互動式 Claude Code 啟動前透過 `NODE_EXTRA_CA_CERTS` 指向已核對的公開 CA。每個 AI 程序各持自己的 `YS_AIMEMORY_TOKEN`，設定範本不會替已開啟的程序載入環境。不要關閉 TLS 驗證。[官方 CA 說明](https://code.claude.com/docs/en/network-config#custom-ca-certificates)及[環境變數展開](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson)

出現 `UNSUPPORTED_CONSTRAINT_TYPE` 時改用上方保留 TLS 驗證的安裝包。既有 fixture 的 CLI transport／SDK 唯讀成功，不能代替新安裝包在該主機的原生模型呼叫或兩個 AI 對話驗收；也不能由設定檔或 Connected 推定通過。

## 兩個 AI 的對話驗收

在同一個 sandbox project 建立兩個獨立身分。A 用 `send_message` 傳一段新的驗收碼；B 自己用 `list_messages` 讀取，再產生含該驗收碼的回覆；A 讀取並確認，B 再讀到 A 的確認。每封新信使用新 idempotency_key，重試原信才沿用原 key。完整範例、cursor 與權限規則見 [MCP 訊息手冊](MCP_MESSAGES.zh-TW.md)。

分別記錄協定測試、SDK 真實 AI 對話與原生客戶端驗收：官方 SDK 傳輸成功不等於原生客戶端已載入工具；單一程式切換兩個 token 也不等於兩個 AI 已各自讀取並產生回覆。原生尚未實測時標記 `not_run`，不能由設定檔推定通過。

## Skills 與四個工作區

`skills/` 中的資料夾是 portable Skill 原始檔，不代表客戶端已自動安裝。`ys-memory-chat` 只在使用者要求聊天或記憶查詢時適用，不會啟用已停用的 MCP 或背景輪詢。保留在專案並以 `AGENTS.md`／`CLAUDE.md` 明確引導讀取即可；要自動發現，依各客戶端當前官方 Skill 安裝方式，經使用者同意複製到它所支援的專案目錄。不要自動覆寫使用者全域設定。

每個 clone 都應有相同版本的協作檔案與 Skills，但使用不同 worker 身分、branch 和本機目錄。先做兩個身分的接手驗證，再擴至四個；不可把「可連線」當成「已證明四客戶端端到端協作」。
