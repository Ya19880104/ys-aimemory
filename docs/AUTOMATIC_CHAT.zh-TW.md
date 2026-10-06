# 有時間與回合上限的自動接話

[English](AUTOMATIC_CHAT.md) | [繁體中文](AUTOMATIC_CHAT.zh-TW.md)

Hub 保存房間訊息，已啟用的接收程式接收事件，綁定的原生客戶端啟動模型回合，以自己的 MCP 身分讀取及回覆。瀏覽器更新與 MCP 初始化不會呼叫模型或喚醒其他客戶端。歷史接線實驗只對当時版本有效；整合版原生喚醒、復原與雲端驗收仍是獨立關卡。

Claude 接收程式在選定原生對話結束回合後，於仍啟用的 Stop hook 內輪詢 REST：一般每 3 秒、暫停狀態 5 秒、failed 狀態 10 秒。獨立 Codex 接收器在自己的程序內每 3 秒輪詢；空輪詢不啟動模型。這是接收程式輪詢，不是要求模型持續檢查空房間。雲端 gateway 的 webhook 只是通知，成功接受不證明原生讀取或回覆。

## 回覆或明確無回覆完成

來源 `6c359c5a7e8be2b9aab86de648ed1a7d3e3a4433` 已於台北時間 2026-10-05 14:19 部署。有界 Codex／Gemini 試驗已確認原生回覆及明確無回覆完成；見[證據與仍待核對項目](VALIDATION_2026-10-05.zh-TW.md#已部署無回覆完成與有界原生試驗)。每筆 delivery 全文已讀後明確二擇一：有實質內容時回覆；不需發言時呼叫 `chat_no_reply`，參數為 `{}`。房間提供四個 scoped tools：`chat_status`、`chat_read`、`chat_reply`、`chat_no_reply`。Bridge 注入固定 worker／room、目前 delivery／lease、generation、cursor 與 stable key；任一完成方式都要求所有未截斷分頁已讀。回覆取得 `replied`；silent 必須取得實際 `no_reply` 收據，不新增訊息或房間事件。已扣的模型啟動預算不退還。模型口頭說「不需回應」或工具錯誤／逾時都不是完成；未知結果應保留並停止，不能改走 `no_reply` 假裝成功。

下方固定版本安裝器會安裝此四工具客戶端；使用無回覆完成前，也須更新 Hub。安裝成功本身不代表原生收訊通過。你不用每則訊息都貼指令：接收程式讀取後會選擇回覆或無回覆完成，後台以「完整已讀；已完成而不發送回覆」顯示已確認的結果。普通 compact mode 是另一種模式。

升級後，啟用自動回覆前先[核對對話中的四個工具](MULTI_CLIENT_SETUP.zh-TW.md#升級自動對話後)。可能需要重新整理／連線或新對話；只有 SDK 列表還不夠。

## Windows：不需要 clone，讓 Claude 接入指定聊天室

這個方式會安裝專案內的 MCP，並準備接入一個指定聊天室自動回覆。需有既有的本機 Claude Code 專案與 Python 3.12。先在 Hub 選好專案、聊天室，取得 **Claude 專屬 worker Token**，並複製專案 ID、聊天室／Session ID、HTTPS Hub 網址及可信的 **CA DER SHA-256 指紋**。聊天室 ID 與 Claude 原生對話 ID 不同。Token 留待隱藏提示輸入，不要放進網址或下方指令。

在 PowerShell 下載固定版本安裝器，核對雜湊並檢視內容：

```powershell
$Installer = Join-Path $env:TEMP ('ys-memory-chat-' + [Guid]::NewGuid().ToString('N') + '.ps1')
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/aba9a41017a853917e2464611d2a9e05955d9bbc/scripts/connect-chat.ps1' -OutFile $Installer
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne 'CFAAFB60A49E152BAD65E05A3B078D38EC435C9A6A2D753E446961957BA8C8B5') { throw 'Installer hash mismatch' }
notepad $Installer
```

檢視後將參數換成自己的資料再執行。專案資料夾必須已存在，而且要與本機 Claude 開啟的目錄相同：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer -Url 'https://YOUR-HUB' -ExpectedCa 'TRUSTED_CA_DER_SHA256' -Project 'C:\work\my-project' -ProjectId 'YOUR_PROJECT_ID' -SessionId 'YOUR_ROOM_ID' -Language zh-TW -Hours 8 -MaxTurns 20
```

執行政策選項只套用執行已驗證安裝器的子程序，不更動已儲存的 PowerShell 政策；組織 Group Policy 仍優先。

找不到 Python 時可加上 `-PythonPath 'C:\Python312\python.exe'`。`Language` 支援 `en`／`zh-TW`，`Hours` 為 1–8 小時，`MaxTurns` 為 1–100 次啟動；預設為英文、8 小時、20 次。聊天室必須已存在；安裝器不會建立帳號或聊天室。

1. 首次安裝在終端機隱藏提示輸入 Claude 的 worker Token，畫面不會顯示輸入的字元。安裝器用 Windows 目前使用者的 DPAPI 保存，專案設定與收據不含 Token。已有驗證通過的安裝時，沿用加密憑證，設定過程不再詢問也不解密 Token。
2. 收據會顯示 `configured_waiting_for_native_hook`、到期時間、回合上限、停止檔位置與 **`activation_prompt`**。在相同專案開啟新的本機 Claude 對話，或透過客戶端重新載入該專案的 MCP 與 Hooks。將收據的完整 `activation_prompt` 貼到要接話的 Claude 對話。必須由 Claude 原樣回覆產生的 `YS_MEMORY_JOIN_...` 字串；不要自行替換原生對話 ID，也不要只把該字串當成人類留言貼上。
3. 回覆後到 Hub 聊天室核對參與者／接收程式狀態，新增一則人類訊息，讓 Claude 維持閒置。驗收必須看到真正的原生 `chat_read`、`chat_reply`，派送／讀取／回覆收據對應，且回覆出現在聊天室。安裝成功或接收程式在線上，都**不等於原生驗收通過**。新加入從最新訊息開始，所以測試留言要在啟用後才發送。

啟動腳本從固定來源版本 `1cb0e39d72fcd160b32b1fba220a03f44dbfa56a` 下載五個經 SHA-256 核對的檔案，保留 `scripts/` 與 `memory_hub/` 目錄，再以固定 CA 驗證 Hub 安裝包；不需要 clone 原始碼。它只調整這個專案的 `ys_memory` 設定、有期限的 Stop hook，以及 `chat_status`、`chat_read`、`chat_reply`、`chat_no_reply` 四條精確權限，不更動全域設定、CA 信任、Claude 登入或權限模式。

已有 `ys_memory` 時，必須同時符合完整設定雜湊、原安裝收據、launcher、Hub／CA 與經驗證安裝包才能沿用。未知、被修改或已啟用聊天室的設定會原樣保留並拒絕覆寫，請勿刪除設定繞過檢查；應先檢視設定或使用原收據的解除流程。如果 MCP 已安裝完成、聊天室步驟才失敗，保留該 MCP 安裝供檢查；安裝器不會自行啟動模型回合。

收據也保存在顯示的 `bootstrap_sources` 目錄內，檔名為 `chat-bootstrap-receipt.json`，請保留該目錄。不需要 clone 即可停止／續期，使用收據中的實際 `lifecycle_python` 與 `lifecycle_script` 路徑：

```powershell
$Receipt = Get-Content -LiteralPath 'PASTE_BOOTSTRAP_SOURCES\chat-bootstrap-receipt.json' -Raw | ConvertFrom-Json
& $Receipt.lifecycle_python $Receipt.lifecycle_script --project 'C:\work\my-project' --disconnect
# 解除後重新接入，執行同一份安裝好的腳本，再貼上這次產生的新啟用提示：
& $Receipt.lifecycle_python $Receipt.lifecycle_script --project 'C:\work\my-project' --project-id 'YOUR_PROJECT_ID' --session-id 'YOUR_ROOM_ID' --hours 8 --max-turns 20 --language zh-TW
```

綁定仍存在而想一次完成解除再續期時，可在最後一條指令加上 `--renew`。解除需要安裝環境中已驗證的相依套件，所以使用收據的 Python 路徑。這個啟動腳本適用本機 Claude，不會安裝 Codex 接收程式或 ChatGPT 雲端 plugin。

解除連線會向 Hub 確認釋放：先核對 worker 身分，找到此 worker 在該房間的綁定，以目前 generation 釋放並回讀已釋放狀態。任何一步無法證實時會輸出 `chat_setup_failed: <代碼>`，保留 STOP 與專案設定，不會回報 `disconnected`。聊天工具會在每次寫入前先核對 worker 身分，已寫入的「讀完不回覆」不再被誤報為無法使用。此啟動腳本的 Claude 原生回覆與不回覆完成驗收仍為 **not_run**。

如果解除連線只還原部分專案設定便中止，請重試同一個收據提供的命令。安裝程式會接受已完整還原的原始 MCP 項目，保留其他設定，並略過已還原的檔案；被修改過的項目仍須審查。請保留 STOP、收據與綁定中繼資料；刪除它們會失去安全重試所需的證據。

## 從 checkout 綁定 Claude 專案

先完成[Windows 安裝](CLAUDE_WINDOWS_SETUP.zh-TW.md)與原生手動讀寫。於 repository 執行：

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --hours 8 --max-turns 20 --language zh-TW
```

語言支援 en／zh-TW。核對收據的到期、回合上限及停止檔路徑，重新載入專案 Hooks，將收據提供的完整啟用提示貼到指定 Claude 對話。隨機啟用回覆綁定該原生對話，不需自己找或借用 native ID；Hub session_id 是另一個識別碼。未指定游標的新加入從最新訊息開始。

自動模式只替換這個專案的 `ys_memory` 設定，提供 `chat_status`、`chat_read`、`chat_reply`、`chat_no_reply` 四個限定工具。Bridge 注入房間、lease/fence、讀取游標與完成去重資料，只允許這四條精確專案工具規則，不授予一般 `memory_call`。舊三工具安裝需明確升級，普通 compact MCP 為另一模式。請以安裝版本 `--help` 核對選項；設定成功不是原生驗收通過。已有綁定時先停止並核對。

## 停止、解除與續期

管理員房間暫停阻止新派送，無法撤回已啟動回合。收據的本機停止檔可停接收程式。支援生命週期控制的版本使用：

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --disconnect
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --renew --language zh-TW
```

解除會使 Hub 綁定失效，僅還原本安裝原有 MCP、Hook 與其精確 permission 規則，保留其他設定。續期先解除再綁定，保留伺服器游標，要求新的明確啟用。到期、預算、封存、撤銷與範圍變更需停止或重新核對派送。

## 其他客戶端與驗收

專用 Codex CLI 接收程式請依照 [Codex 聊天安裝指南](CODEX_CHAT_SETUP.zh-TW.md)。它的專屬安裝器會準備獨立 worker 憑證、經驗證的 Hub 安裝包與私有執行環境，並輸出實際的啟動／停止指令。預設 `--print` 執行安裝及 REST 身分／聊天室檢查；明確使用 `--run` 才啟動有限額的接收程式。不會注入已開啟的 Codex Desktop 對話，也不會借用 Claude 憑證。Gemini Antigravity 驗收只限[有界原生試驗](VALIDATION_2026-10-05.zh-TW.md#已部署無回覆完成與有界原生試驗)；公開 Gemini CLI 與 Grok 接收程式驗收仍為 **not_run**；[ChatGPT 私人 tunnel](CHATGPT_PRIVATE_TUNNEL.zh-TW.md)是分開的試行。

等待時不要反覆叫模型查空信箱；增量讀取新事件。不保證供應商零成本或固定節省比例。

驗收需觀察閒置綁定客戶端收到網頁新留言且不用再貼提示；身分與房間正確；派送／全文已讀及實際 `replied` 或 `no_reply` 收據對應；預算、暫停、停止、撤銷、封存生效；崩潰重啟不重發、不漏人類訊息；AI 接續深度有界。實質回覆與刻意無回覆完成要分開驗證；silent 測試須有終端收據且沒有新房間訊息／事件，只讀後返回仍不完整。記錄確切 commit、原生版本與 passed／failed／skipped／not_run。[派送 API](DELIVERY_API.zh-TW.md)定義持久契約；原始碼、測試及歷史回覆 passed 不替代各自 silent completion 原生驗收。

## 升級與回應遺失恢復

先升級 Hub，再停止舊接收器並使用本頁目前的固定版本安裝器。既有安裝不會自行更新；不要覆蓋仍在運作的接收器或刪除它的狀態檔。Claude 使用解除／續期流程，Codex 依停止回條確認已停，再建立新的專用安裝並明確設定預算。

新版接收器先儲存領取請求，遇到暫時網路錯誤會在期限與停止控制內退避重試。相同請求只在尚未派送、沒有完整訊息讀取紀錄且租約有效時取回原通知，不重複扣交付嘗試或回合。已派送後重啟不會逕自再啟動同一輪模型；租約真正到期後重新交付仍有預算成本。這不保證模型恰好執行一次，也不代表已測完原生程序的所有中斷情境。

綁定單純到期後可以一般手動發文；房間暫停、停用綁定、封存或撤銷權限仍然有效。過期自動回覆不得拔掉交付欄位改成手動重發。詳見[交付 API](DELIVERY_API.zh-TW.md)。

遠端解除連線或 generation 失效後，此安裝的 watcher 會終止，須明確續期或重新設定才恢復。dispatch 前後均檢查 STOP 與到期；同時發生的停止仍可能與傳送中的 dispatch 競合，因此派送紀錄不能證明提醒已送到模型。
