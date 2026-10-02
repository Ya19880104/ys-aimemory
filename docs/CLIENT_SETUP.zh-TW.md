# 官方客戶端接線與訂閱使用

文件更新：2026-10-02。版本與帳號可用功能可能不同，安裝前以實際官方客戶端的 help、設定畫面和以下官方文件核對。設定範例與實際連線驗收分開記錄。

## 訂閱優先

使用 Codex 官方客戶端的 ChatGPT 登入或 Claude Code 官方支援的訂閱登入，各自保留帳號界線。本專案不供應模型 key、不共用四個帳號的 cookie，也不把 ChatGPT 訂閱視為可任意呼叫的 OpenAI API 額度。Codex 官方文件區分訂閱登入與按量 API key：[驗證說明](https://developers.openai.com/codex/auth)。

Hub 保存工具操作與共享狀態，包含 AI 明確傳送的訊息，不會自行喚醒其他 AI；人類在各客戶端下達開始、讀信或接手指示。未來要排程或自動代理模型，需要另行確認官方支援、帳號規則、費用與權限。Grok 留待有可驗證的官方客戶端相容路徑後再接，不以瀏覽器自動化冒充 MCP。

## 本版傳輸

本版實作 Streamable HTTP `/mcp`。四個支援它的客戶端可連同一個 TLS URL，使用各自的 worker 身分。不能把普通 REST 路由當成 MCP；請以 initialize、tools/list、tools/call 實際確認。

目前有 28 個工具，包含 `send_message` 與 `list_messages`。同一 project 的兩個有效 worker 可收發持久化訊息；訊息正文只對寄件者和收件者可見，admin 也不能旁觀其他人的對話。操作與欄位見 [訊息手冊](MCP_MESSAGES.zh-TW.md)。

MCP 標準的 stdio 是由客戶端啟動子程序並透過 stdin/stdout 傳遞 JSON-RPC；它不等於一個可填寫的 LAN URL。本版另提供可下載的 stdio → HTTPS 客戶端轉接器，供 Claude Code 的 CA 相容需求使用；伺服器仍接收 HTTPS Streamable HTTP。Codex 本輪維持下方 HTTP 設定。舊 HTTP+SSE 不應與 Streamable HTTP 混淆。[官方傳輸規範](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

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
`https://YOUR_VERIFIED_HUB_HOST/downloads/ys-memory-stdio-1.0.0.zip`。
下載只走 HTTPS；HTTP bootstrap 不提供 ZIP。先透過可信通道取得並核對公開 CA 的 **DER SHA-256** 指紋。同一個 HTTP 頁面上的指紋不構成獨立信任；不要把 PEM 檔案雜湊誤當成 DER 指紋。

若瀏覽器尚未信任 CA，可在放有已核對公開 CA 的 PowerShell 目錄，以它驗證 HTTPS 下載：

```powershell
curl.exe --cacert .\ys-ai-memory-ca.crt --fail --output .\ys-memory-stdio-1.0.0.zip "https://YOUR_VERIFIED_HUB_HOST/downloads/ys-memory-stdio-1.0.0.zip"
```

ZIP 平鋪包含 `bridge.py`、`connection.json`、`ys-ai-memory-ca.crt`、`requirements.lock`、`README.txt`。`connection.json` 記錄部署的 HTTPS endpoint、公開 CA 相對檔名與小寫 DER SHA-256 pin；沒有 token、TLS 私鑰或模型登入資料。轉接器固定使用這份連線配置，核對 CA pin、憑證鏈、IP／hostname 與 name constraints，不跟隨 redirect、不使用環境代理或 TLS keylog，也不自動重試寫入。

1. 選擇自己的新安裝目錄並解壓，保留上述檔案在同一層；不要覆寫既有安裝。安裝目錄與 `.venv` 不加入專案 Git。
2. 主要目標為 Windows Python 3.12。在解壓目錄開啟 PowerShell，執行下列命令；套件只安裝到此處的專用虛擬環境。
3. 最後一個命令只印出 Claude 設定，不需 token、不連線。手動將 `mcpServers.ys_memory` 合併到你選定專案的 `.mcp.json`。保留其他 MCP 項目及 `${YS_AIMEMORY_TOKEN}` 引用；已有 `ys_memory` 時更新同一項目，避免同名 HTTP／stdio 並存。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe .\bridge.py --print-claude-config
```

輸出的 `command` 使用目前虛擬環境的 Python，`args` 使用 bridge 與 connection 的本機絕對路徑。預設連線設定是 bridge 同目錄的 `connection.json`，可用 `--config PATH` 明確選擇另一份已核對的配置。安裝包不寫入任何 AI 設定；移動目錄或換電腦後須在新位置重新建立環境、產生並合併設定，不能直接沿用別台電腦的絕對路徑。

到已合併 `.mcp.json` 的專案目錄開啟自己的 PowerShell。從受保護位置取出該 AI 的 worker token，以隱藏輸入供給本次程序；不要把實值寫入指令、`.env`、設定檔或聊天：

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
try { claude } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

由使用者審閱官方客戶端的 project 信任和工具權限。`--print-claude-config` 不會核可工具、啟動模型、接管已登入的聊天或喚醒另一個 AI。新程序環境不會自動注入已開啟的桌面／遠端 host；保存工作後依該客戶端的專案載入方式重新開啟。用 `/mcp` 檢查，再實際呼叫 `get_worker_inbox` 和 `get_project_summary` 核對 worker／project。各客戶端使用自己的模型登入，本安裝包不提供或複製 provider 憑證。[Claude Code MCP 官方文件](https://code.claude.com/docs/en/mcp)

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

`skills/` 中的三個資料夾是 portable Skill 原始檔，不代表客戶端已自動安裝。保留在專案並以 `AGENTS.md`／`CLAUDE.md` 明確引導讀取即可；要自動發現，依各客戶端當前官方 Skill 安裝方式，經使用者同意複製到它所支援的專案目錄。不要自動覆寫使用者全域設定。

每個 clone 都應有相同版本的協作檔案與 Skills，但使用不同 worker 身分、branch 和本機目錄。先做兩個身分的接手驗證，再擴至四個；不可把「可連線」當成「已證明四客戶端端到端協作」。
