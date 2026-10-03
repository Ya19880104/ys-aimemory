# 有時間與回合上限的自動接話

[English](AUTOMATIC_CHAT.md) | [繁體中文](AUTOMATIC_CHAT.zh-TW.md)

Hub 保存房間訊息，已啟用的接收程式接收事件，綁定的原生客戶端啟動模型回合，以自己的 MCP 身分讀取及回覆。瀏覽器更新與 MCP 初始化不會呼叫模型或喚醒其他客戶端。歷史接線實驗只對当時版本有效；整合版原生喚醒、復原與雲端驗收仍是獨立關卡。

## Windows：不需要 clone，讓 Claude 接入指定聊天室

這個方式會安裝專案內的 MCP，並準備接入一個指定聊天室自動回覆。需有既有的本機 Claude Code 專案與 Python 3.12。先在 Hub 選好專案、聊天室，取得 **Claude 專屬 worker Token**，並複製專案 ID、聊天室／Session ID、HTTPS Hub 網址及可信的 **CA DER SHA-256 指紋**。聊天室 ID 與 Claude 原生對話 ID 不同。Token 留待隱藏提示輸入，不要放進網址或下方指令。

在 PowerShell 下載固定版本安裝器，核對雜湊並檢視內容：

```powershell
$Installer = Join-Path $env:TEMP ('ys-memory-chat-' + [Guid]::NewGuid().ToString('N') + '.ps1')
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/d62f1ccaf80a4ed0e56c71b9181e9e333d272ab8/scripts/connect-chat.ps1' -OutFile $Installer
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne '85337175B42B566797F7523F510086FE2D70AC653132B734A7846EBB35BD9876') { throw 'Installer hash mismatch' }
notepad $Installer
```

檢視後將參數換成自己的資料再執行。專案資料夾必須已存在，而且要與本機 Claude 開啟的目錄相同：

```powershell
& $Installer -Url 'https://YOUR-HUB' -ExpectedCa 'TRUSTED_CA_DER_SHA256' -Project 'C:\work\my-project' -ProjectId 'YOUR_PROJECT_ID' -SessionId 'YOUR_ROOM_ID' -Language zh-TW -Hours 8 -MaxTurns 20
```

找不到 Python 時可加上 `-PythonPath 'C:\Python312\python.exe'`。`Language` 支援 `en`／`zh-TW`，`Hours` 為 1–8 小時，`MaxTurns` 為 1–100 次啟動；預設為英文、8 小時、20 次。聊天室必須已存在；安裝器不會建立帳號或聊天室。

1. 首次安裝在終端機隱藏提示輸入 Claude 的 worker Token，畫面不會顯示輸入的字元。安裝器用 Windows 目前使用者的 DPAPI 保存，專案設定與收據不含 Token。已有驗證通過的安裝時，沿用加密憑證，設定過程不再詢問也不解密 Token。
2. 收據會顯示 `configured_waiting_for_native_hook`、到期時間、回合上限、停止檔位置與 **`activation_prompt`**。在相同專案開啟新的本機 Claude 對話，或透過客戶端重新載入該專案的 MCP 與 Hooks。將收據的完整 `activation_prompt` 貼到要接話的 Claude 對話。必須由 Claude 原樣回覆產生的 `YS_MEMORY_JOIN_...` 字串；不要自行替換原生對話 ID，也不要只把該字串當成人類留言貼上。
3. 回覆後到 Hub 聊天室核對參與者／接收程式狀態，新增一則人類訊息，讓 Claude 維持閒置。驗收必須看到真正的原生 `chat_read`、`chat_reply`，派送／讀取／回覆收據對應，且回覆出現在聊天室。安裝成功或接收程式在線上，都**不等於原生驗收通過**。新加入從最新訊息開始，所以測試留言要在啟用後才發送。

啟動腳本從固定來源版本 `38f9be5ec796be52cf0f8814ea2eb8fdb81d08d0` 下載五個經 SHA-256 核對的檔案，保留 `scripts/` 與 `memory_hub/` 目錄，再以固定 CA 驗證 Hub 安裝包；不需要 clone 原始碼。它只調整這個專案的 `ys_memory` 設定、有期限的 Stop hook，以及 `chat_status`、`chat_read`、`chat_reply` 三條精確權限，不更動全域設定、CA 信任、Claude 登入或權限模式。

已有 `ys_memory` 時，必須同時符合完整設定雜湊、原安裝收據、launcher、Hub／CA 與經驗證安裝包才能沿用。未知、被修改或已啟用聊天室的設定會原樣保留並拒絕覆寫，請勿刪除設定繞過檢查；應先檢視設定或使用原收據的解除流程。如果 MCP 已安裝完成、聊天室步驟才失敗，保留該 MCP 安裝供檢查；安裝器不會自行啟動模型回合。

收據也保存在顯示的 `bootstrap_sources` 目錄內，檔名為 `chat-bootstrap-receipt.json`，請保留該目錄。不需要 clone 即可停止／續期，使用收據中的實際 `lifecycle_python` 與 `lifecycle_script` 路徑：

```powershell
$Receipt = Get-Content -LiteralPath 'PASTE_BOOTSTRAP_SOURCES\chat-bootstrap-receipt.json' -Raw | ConvertFrom-Json
& $Receipt.lifecycle_python $Receipt.lifecycle_script --project 'C:\work\my-project' --disconnect
# 解除後重新接入，執行同一份安裝好的腳本，再貼上這次產生的新啟用提示：
& $Receipt.lifecycle_python $Receipt.lifecycle_script --project 'C:\work\my-project' --project-id 'YOUR_PROJECT_ID' --session-id 'YOUR_ROOM_ID' --hours 8 --max-turns 20 --language zh-TW
```

綁定仍存在而想一次完成解除再續期時，可在最後一條指令加上 `--renew`。解除需要安裝環境中已驗證的相依套件，所以使用收據的 Python 路徑。這個啟動腳本適用本機 Claude，不會安裝 Codex 接收程式或 ChatGPT 雲端 plugin。

## 從 checkout 綁定 Claude 專案

先完成[Windows 安裝](CLAUDE_WINDOWS_SETUP.zh-TW.md)與原生手動讀寫。於 repository 執行：

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --hours 8 --max-turns 20 --language zh-TW
```

語言支援 en／zh-TW。核對收據的到期、回合上限及停止檔路徑，重新載入專案 Hooks，將收據提供的完整啟用提示貼到指定 Claude 對話。隨機啟用回覆綁定該原生對話，不需自己找或借用 native ID；Hub session_id 是另一個識別碼。未指定游標的新加入從最新訊息開始。

自動模式只替換這個專案的 ys_memory 設定，提供 chat_status、chat_read、chat_reply 三個限定工具。bridge 注入房間、lease/fence、讀取游標與回覆去重資料，只允許這三條精確專案工具規則，不授予一般 memory_call。普通 compact MCP 為另一模式。請以安裝版本 --help 核對選項；設定成功不是原生驗收通過。已有綁定時先停止並核對。

## 停止、解除與續期

管理員房間暫停阻止新派送，無法撤回已啟動回合。收據的本機停止檔可停接收程式。支援生命週期控制的版本使用：

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --disconnect
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --renew --language zh-TW
```

解除會使 Hub 綁定失效，僅還原本安裝原有 MCP、Hook 與三條精確 permission，保留其他設定。續期先解除再綁定，保留伺服器游標，要求新的明確啟用。到期、預算、封存、撤銷與範圍變更需停止或重新核對派送。

## 其他客戶端與驗收

專用 Codex CLI 接收程式不等於已開啟的 Codex Desktop 對話。使用部署版本支援的接線說明；Claude 命令不是 Codex 安裝器。Gemini／Grok 接收程式不宣稱通過；[ChatGPT 私人 tunnel](CHATGPT_PRIVATE_TUNNEL.zh-TW.md)是分開的試行。

等待時不要反覆叫模型查空信箱；增量讀取新事件。不保證供應商零成本或固定節省比例。

验收需觀察閒置綁定客戶端收到網頁新留言且不用再貼提示；身分與房間正確；派送／已讀／回覆收據對應；預算、暫停、停止、撤銷、封存生效；崩潰重啟不重發、不漏人類訊息；AI 接續深度有界。記錄確切 commit、原生版本與 passed／failed／skipped／not_run。[派送 API](DELIVERY_API.zh-TW.md)定義持久契約；原始碼與測試不替代原生驗收。
