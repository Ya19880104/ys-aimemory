# Claude、Codex、Gemini 與 Grok 安裝入口

查核日期：2026-10-03。先辨認「模型」與「執行 MCP 的客戶端」：同一模型可以由不同程式使用，不能只看模型名稱就判定可連線。下列相容方式和原生實測分開記錄。

## 選擇接入方式

| 使用方式 | 接法 | 目前驗證界線 |
| --- | --- | --- |
| Claude Code / Codex 的本機 CLI 或 IDE host | 專案限定 HTTPS，或本機 compact stdio adapter → HTTPS | 已有套件、協定/SDK 測試；每台原生 host 的登入、工具核准及模型呼叫仍需驗收 |
| Gemini CLI | 專案 `.gemini/settings.json` 啟動同一個 compact stdio adapter | 官方支援 stdio；以下是相容設定範例，Gemini 原生模型呼叫 `not_run` |
| Gemini 網頁聊天介面 | 依該產品自己的 connector 功能 | 本專案尚未驗證，不能套用 CLI 步驟就宣稱可用 |
| Grok / xAI API Remote MCP | xAI 雲端連到可達的 HTTPS MCP URL | 官方支援，但本專案端到端 `not_run`；一般內網 IP 與私有 CA 不能直接當作雲端可用服務 |
| 本機程式使用 Grok 模型並執行 MCP | 本機程式負責 MCP、模型 API 與工具核准 | 可作為未來整合方向；本庫沒有提供此 agent host，不是現成 Grok 安裝器 |

Gemini CLI 支援 stdio 與 Streamable HTTP，`env` 可明確轉交秘密環境變數，`trust: false` 保留工具確認。[Gemini 官方 MCP 文件](https://geminicli.com/docs/tools/mcp-server/)

xAI Remote MCP 由雲端代連服務，支援 Streaming HTTP / SSE 及自訂驗證 header。這不證明 grok.com 網頁可安裝同一設定。若採用 API，模型 API key 與 Hub worker Token 是兩種不同憑證；API 使用也不由本專案提供。[xAI 官方 Remote MCP 文件](https://docs.x.ai/developers/tools/remote-mcp)

**內網部署的判斷：**本機 Gemini/Claude/Codex 可透過能到達 Hub 的主機執行 adapter；雲端 xAI 無法因為知道 `192.168.x.x` 就進入你的 LAN。需要另行設計可達網路、TLS 與最小權限入口，不能只把內網 URL 貼進雲端設定。本指南不修改防火牆、發布公網服務或關閉 TLS。

## GitHub 已提供哪些安裝材料

- [Hub 伺服器與 Docker 部署](QUICKSTART.zh-TW.md#部署-hub)：包含環境檔、憑證位置、preflight、啟動和備份。
- [Claude / Codex 手動設定](CLIENT_SETUP.zh-TW.md)：包含直接 HTTPS 與 stdio 設定。
- [按需載入與省 Token](EFFICIENT_MCP.zh-TW.md)：包含 compact 兩工具、專案範圍與增量讀取。
- 已部署主機的 `/help#clients`：HTML 教學與 `/downloads/ys-memory-stdio-1.1.1.zip` 安裝包。ZIP 由自己的 Hub 依部署網址及公開 CA 產生，不是帶著固定真實主機資訊的 GitHub release。
- [伺服器腳本](../scripts/)：preflight、備份、還原檢查；[套件產生程式](../memory_hub/client_bundle.py)負責提供 adapter 與公開連線配置。

目前有可逐步執行的命令與 adapter，**沒有自動覆寫各 AI 設定的一鍵安裝器**。設定合併和模型登入仍由使用者控制。使用已有 Hub 不需要再部署一套伺服器。

## Windows 客戶端快速安裝

前置：自己的 Python 3.12、能到達 Hub 的電腦，以及透過可信通道核對 DER SHA-256 指紋的公開 CA。管理員先在「設定 → 建立專案」選定專案，再到「MCP 接入 → Token 與客戶端設定」為每個 AI 產生不同的 worker Token。

在自選工作目錄執行，網址換成自己確認的 HTTPS origin。下方目的目錄必須尚未存在；不用 `-Force` 覆蓋已有安裝：

```powershell
if (Test-Path -LiteralPath .\ys-memory-client) { throw '安裝目錄已存在，請選另一個新目錄' }
if (Test-Path -LiteralPath .\ys-memory-stdio-1.1.1.zip) { throw '下載檔已存在，請另選目錄' }
curl.exe --cacert .\ys-ai-memory-ca.crt --fail --output .\ys-memory-stdio-1.1.1.zip 'https://YOUR_VERIFIED_HUB_HOST/downloads/ys-memory-stdio-1.1.1.zip'
if ($LASTEXITCODE -ne 0) { throw 'HTTPS 下載失敗' }
Expand-Archive -LiteralPath .\ys-memory-stdio-1.1.1.zip -DestinationPath .\ys-memory-client -ErrorAction Stop
Set-Location .\ys-memory-client -ErrorAction Stop
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw '建立 Python 環境失敗' }
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw '安裝依賴失敗' }
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
```

最後一行只列印本機路徑，不需要 Token、不連 Hub、不寫客戶端設定。Claude 使用輸出的項目；Codex 的 TOML 請依[快速指南](QUICKSTART.zh-TW.md#codex可選-stdio-設定)手動合併。保留既有 MCP，只有一個 `ys_memory` 項目。安裝目錄不加入 Git；移動後須重新產生絕對路徑。不要從瀏覽器安全警告跳過驗證下載。

## Gemini CLI 手動接入範例

完成上述 adapter 安裝後，在**實際開發專案**的 `.gemini/settings.json` 合併以下項目。三個 `C:/Tools/...` 路徑改成剛安裝的實際絕對位置；這是設定範例，尚未執行 Gemini 原生驗收：

```json
{
  "mcp": {"excluded": ["ys_memory"]},
  "mcpServers": {
    "ys_memory": {
      "command": "C:/Tools/ys-memory-client/.venv/Scripts/python.exe",
      "args": [
        "-B", "C:/Tools/ys-memory-client/bridge.py",
        "--config", "C:/Tools/ys-memory-client/connection.json", "--compact"
      ],
      "env": {"YS_AIMEMORY_TOKEN": "${YS_AIMEMORY_TOKEN}"},
      "trust": false
    }
  }
}
```

範例先在專案的 `mcp.excluded` 排除 `ys_memory`，避免無關工作載入。確定本次要使用時，僅從該陣列移除 `ys_memory`，保留其他項目，再啟動客戶端；不用時加回。合併設定時也要保留既有的 `mcp` 屬性。[Gemini 官方專案配置](https://geminicli.com/docs/tools/mcp-server/)

adapter 自己驗證公開 CA pin 與 HTTPS，不需要為此調整 Node 的 TLS 驗證。回到此開發專案的 PowerShell，將 **Gemini 自己的** Token 只交給這次程序：

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Gemini worker token' -AsSecureString)).Password
try { gemini } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

不要把 Token 實值寫到命令、JSON、聊天或 Git。Gemini 的模型登入另外由官方客戶端處理。使用 `/mcp` 查看連線；不能把自然語言提到「記憶」當作自動啟用保證。官方另有 enable/disable 命令，但預設會保存使用者層級啟停狀態；本指南採用上方專案配置，不自動改動全域設定。[Gemini MCP 設定及啟停](https://geminicli.com/docs/tools/mcp-server/)

## Grok 接入與 Token 成本

若未來另行部署 xAI 雲端可達的 MCP，先用官方 `server_url` / `server_label` 設定，Token 透過秘密配置轉為 Authorization header。先 allowlist `get_worker_inbox`、`get_project_summary` 等必要的唯讀工具；驗證後再按工作增加範圍。xAI 官方提醒：未指定 `allowed_tools` 時，會把服務提供的所有工具定義加入模型上下文。[Remote MCP 工具篩選](https://docs.x.ai/developers/tools/remote-mcp)

現有 `/mcp` 是 38 個完整工具；**兩工具 compact 是本機 stdio adapter，不是另一個已實作的 HTTP `/compact` 端點**。不能把 `memory_tools`、`memory_call` 直接填成目前遠端 `/mcp` 的工具清單。若要讓 Grok 也用 compact，需要能在本機執行它的 host，或另外實作與驗收 HTTP gateway；本次沒有安裝或開放 gateway。

本專案的省 Token 原則：

1. 無關工作先停用 MCP；已啟用的 compact 仍有兩個入口 schema，並非零 Token。
2. 明確要求加入專案對話時，先查單一工具 schema，再查摘要及新訊息。
3. `read_session` 使用伺服器回傳的 `next_after_sequence`；`limit`、`max_bytes`、`full_text:false` 限制結果。不要以自己發文序號跳過人類訊息。
4. 歷史全文、成果與附件只在需要時讀取，不做無限輪詢或每輪重送全部紀錄。
5. 工具 schema bytes、回傳 bytes 和實際模型 Token 分開測量；沒有量測就不宣稱固定節省百分比。工具總數減少也不保證總成本一定降低。

## 給 AI 的快速安裝任務

```text
請讀 https://github.com/Ya19880104/ys-aimemory 的 README、AGENTS.md、
docs/MULTI_CLIENT_SETUP.zh-TW.md 及 docs/CLIENT_SETUP.zh-TW.md。
本次只接入已有 Hub，不部署伺服器或修改全域設定。
客戶端：[Claude Code / Codex / Gemini CLI]；OS 與專案目錄：[填入]
Hub HTTPS origin、project ID、自己的 worker ID：[填入非秘密資訊]
公開 CA 檔案、由可信通道取得的 DER SHA-256 指紋：[填入]
確認實際客戶端版本；使用新目錄安裝 adapter，優先 compact。
合併指定專案設定並保留其他 MCP；先顯示將使用的路徑與設定。
Token 由我在自己的電腦安全輸入，不請我貼入對話，不借其他 AI 身份。
先做 initialize/tools-list，再由原生模型呼叫 get_worker_inbox 核對身分，
再用我指定的專案/對話測試摘要與增量讀取；要傳訊時使用唯一驗收碼。
不要建立正式任務、輪替憑證或改防火牆來讓測試通過。
回報實際版本、命令、passed/failed/skipped/not_run，區分 SDK 與原生驗收。
```

Grok 雲端 API 使用者先完成網路與 TLS 架構確認，再採用[官方配置](https://docs.x.ai/developers/tools/remote-mcp)，不要把此本機安裝任務當成 Grok 現成腳本。

## 最低驗收

依序確認：本機程序啟動 → MCP 工具列表 → 真實 Hub 身分／專案 → 原生模型工具呼叫 → 另一個 AI 獨立回覆新的驗收碼。每層留證據；Connected、SDK 成功、網頁能登入都不能代替後面幾層。共享對話會讓授權成員與管理員看到內容；與只有收發雙方可見的私訊不同，見[共享對話](SHARED_SESSIONS.zh-TW.md)。
