# Windows Codex 自動對話安裝

[English](CODEX_CHAT_SETUP.md) | [繁體中文](CODEX_CHAT_SETUP.zh-TW.md)

本教學安裝一個專屬的**本機 Codex CLI 接收器**，綁定 YS Memory 的單一專案與對話。啟動後，聊天室的新訊息可觸發有時間及回合限制的原生模型回覆。它建立自己的私有安裝目錄，不會把訊息注入既有 Codex Desktop 對話、不會設定 Claude，也不會修改全域 Codex 設定。

一般按需使用 MCP 請看[客戶端接入](CLIENT_SETUP.zh-TW.md)；聊天室控制與投遞規則請看[自動對話](AUTOMATIC_CHAT.zh-TW.md)。

## 1. 準備 CLI 與聊天室

使用 Windows 與 Python 3.12，只有選擇 checkout 替代方式才需要 Git。先按照 [Codex CLI 官方教學](https://learn.chatgpt.com/docs/codex/cli)的 **Windows** 步驟安裝正式 CLI，再開啟新的 PowerShell 終端機。檢查安裝：

```powershell
Get-Command codex -All
codex --version
py -3.12 --version
```

安裝器會從 `PATH` 尋找 `codex.exe`。若為標準官方 npm 安裝、只公開 `codex.cmd`，會讀取該安裝的 package metadata，自動找到對應 Windows x64／arm64 原生相依套件；不會執行包裝器，也不需要猜應用程式資料夾。套件名稱、alias 版本、OS 與架構必須符合。非標準安裝可用 `--codex`（啟動腳本為 `-CodexPath`）指定已確認的原生執行檔。版本／help 預檢只檢查 CLI 功能，不呼叫模型。

沿用已登入的 CLI。若 CLI 尚未登入，請依[官方驗證教學](https://learn.chatgpt.com/docs/auth)自行完成 `codex login`。安裝器不會代為登入、複製模型憑證或更換帳號。下方的 Hub worker Token 是另一組獨立憑證。

在 Hub 選擇或建立專案、開啟一個對話，再透過 MCP 產生器為此 Codex 接收器建立專屬 worker Token，授權該 worker 存取此專案。不同 AI 應使用不同 worker 身分。準備以下資料：

| 值 | 來源與意義 |
| --- | --- |
| `--url` | 管理員確認過的 Hub HTTPS 網站位址，例如 `https://memory.example.internal:8443`；不要附上 `/mcp`、查詢參數、fragment 或 Token。 |
| `--expected-ca` | 從可信來源取得的公開 CA 憑證 **DER SHA-256** 指紋，共 64 個十六進位字元。 |
| `--project-id` | Hub 專案 ID，不是本機資料夾路徑或顯示名稱。 |
| `--session-id` | Hub 對話 ID，共 32 個小寫十六進位字元，不是 Codex 對話 ID。 |
| `--worker-id` | 與 Token 對應的 Codex 專屬 worker 身分，必須完全一致。 |
| Worker Token | Hub 核發給該 worker 的 Token，只在本機隱藏輸入提示中填入。 |

本機必須能連到 Hub 的 HTTP 80 公開 CA 下載、經驗證的 HTTPS 客戶端套件，以及套件使用的 Python 套件來源。只有公開 CA 透過 HTTP 下載；其指紋必須先符合可信指紋，後續才進行帶身分驗證的 HTTPS 操作。安裝器不會新增全域 CA 信任、不接受轉址，也不會對 Hub 請求使用環境代理設定。

## 2. 使用固定網址安裝，不需要 clone

下載並檢視這份固定版本腳本，雜湊核對通過後才執行：

```powershell
$Installer = Join-Path $env:TEMP ('ys-memory-codex-' + [Guid]::NewGuid().ToString('N') + '.ps1')
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/c609da7f849f8c73c3346deab8578ca1668418fa/scripts/connect-codex-chat.ps1' -OutFile $Installer
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne 'A7294C0826E45E076EF0EBBD9530BAA48F7E344BABCF482F74D53C4349F7C691') { throw 'Installer hash mismatch' }
notepad $Installer
```

檢視後換成自己的資料再安裝，使用 Codex 專屬 worker，不借用 Claude 的 Token：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer -Url 'https://YOUR-HUB' -ExpectedCa 'TRUSTED_CA_DER_SHA256' -ProjectId 'YOUR_PROJECT_ID' -SessionId 'YOUR_32_LOWERCASE_HEX_ROOM_ID' -WorkerId 'YOUR_CODEX_WORKER_ID' -Language zh-TW -Hours 1 -MaxTurns 20 -Print
```

預設 `-Print` 會安裝並核對授權，不啟動模型。於隱藏提示輸入 Token 後，依下方「啟動專用接收器」複製收據的完整 `start_command`。明確使用 `-Run` 則會安裝後立即啟動有限額接收器，兩個開關不可同時使用。`-PythonPath` 可指定既有 Python 3.12；`-TurnTimeout` 預設 90 秒。不需要填本機專案資料夾：接收器會建立私有空白工作目錄進行對話回合。

啟動腳本核對來源版本 `2e2739bf9307f02e42708209d987d888ab636eec` 的四個檔案，保留 `scripts/` 與 `memory_hub/` 目錄。共用的 `setup-claude.py` 只提供已驗證的安裝包／CA 函式；本流程不呼叫 Claude 安裝功能，也不寫入 `.mcp.json`。請閱讀下方安裝細節與限制；若已使用網址安裝，可跳過 checkout 指令。

### 替代方式：從 checkout 安裝

複製到**新目錄**，使用包含 `scripts/setup-codex-chat.py` 的版本：

```powershell
git clone https://github.com/Ya19880104/ys-aimemory.git 'C:\src\ys-aimemory'
Set-Location -LiteralPath 'C:\src\ys-aimemory'
git checkout --detach 2e2739bf9307f02e42708209d987d888ab636eec
git rev-parse HEAD
Test-Path -LiteralPath '.\scripts\setup-codex-chat.py'
```

記下顯示的 commit。若已有 checkout，保留既有工作並使用實際路徑。若找不到腳本，先取得包含它的發布版本，不要改用 Claude 安裝器或猜測下載指令。

替換範例值，在可互動輸入的 PowerShell 終端機執行：

```powershell
py -3.12 .\scripts\setup-codex-chat.py `
  --url 'https://memory.example.internal:8443' `
  --expected-ca 'YOUR_64_HEX_DER_SHA256' `
  --project-id 'YOUR_PROJECT_ID' `
  --session-id 'YOUR_32_LOWERCASE_HEX_ROOM_ID' `
  --worker-id 'YOUR_CODEX_WORKER_ID' `
  --language zh-TW --hours 1 --max-turns 20 --print
```

出現 `Your dedicated Codex worker Token (hidden):` 時貼入 Codex 專屬 worker Token，畫面不會回顯字元。不要把 Token 放進網址、命令列、原始碼或 Git commit。透過 pipe 或非互動終端機執行會被拒絕，因為無法提供必要的隱藏輸入提示。

**`--print` 會實際安裝，並不是 dry run。** 省略動作參數時也會採用相同行為。它下載並驗證 Hub 套件、透過 REST 核對 worker 及開啟中的聊天室、建立隔離的 Python 環境、使用目前 Windows 使用者的 DPAPI 儲存 Token，最後印出安裝回條。此時不會呼叫模型，也尚未開始自動回覆。

私有目錄預設為 `%LOCALAPPDATA%\YS-AIMemory\codex-clients\codex-<generated-id>`，請以回條記錄的實際路徑為準。裡面包含客戶端套件、私有執行環境、`worker.dpapi`、安裝器與接收器原始碼，以及 `codex-install.json`。此目錄應保留在 Git 之外，並使用同一個 Windows 帳號執行。

可用選項：`--language en|zh-TW`；`--hours 1..8`（預設 1）；`--max-turns 1..100`（預設 20）；`--turn-timeout 30..240` 秒（預設 90）。`--max-turns` 限制模型啟動次數，不是成功回覆次數。安裝檢查與原生驗收是不同結果。

## 3. 啟動專屬接收器

先核對回條的 `origin`、`project_id`、`session_id`、`worker_id` 是否符合本次用途。回條會標示：

```text
status: installed_not_native_verified
authorization_check: rest_identity_and_room_passed
native_acceptance: not_run
```

將回條中完整的 **`start_command`** 複製到 PowerShell 執行。它使用安裝目錄內的 Python 與腳本，帶入 `--receipt '<實際路徑>\codex-install.json' --run`。讓這個終端機／程序持續執行；這一步才會明確啟用有限度的模型執行。首次安裝指令若改用 `--run`，也能安裝後立即啟動；第一次操作建議採用兩步流程。

接收器只綁定指定聊天室。新綁定會從聊天室當下的訊息位置開始，請在線上後再發送**新**測試訊息。閒置時只檢查投遞，不呼叫模型。符合條件的投遞會啟動原生 `codex exec`，只提供 `get_worker_inbox`、`read_session`、`post_session_message` 三個 MCP 工具，核對身分、讀取該批訊息並允許一則對話回覆。這組工具不提供專案開發工作能力。原生非互動執行與已儲存 CLI 登入的使用方式，見[官方非互動模式教學](https://learn.chatgpt.com/docs/non-interactive-mode)。

此流程不會替你指定模型或修改已儲存的權限模式。專屬子程序使用自己的唯讀 sandbox 與限定範圍的 MCP 設定。模型回覆會使用 Codex 額度；閒置的網路檢查不是模型回合。

## 4. 用管理員留言驗收

1. 以管理員開啟同一個 Hub 對話，確認專屬 worker 已上線。
2. 發送新訊息，例如：**「Codex 連線測試：請只回覆一次，說明你的 worker 身分與這則訊息的主題。」** 不要另外要求 Codex 主動查詢。
3. 在 Hub 確認回覆出現在正確聊天室、作者為預期 worker、有新的訊息 ID／sequence，且沒有重複回覆。
4. 依安裝回條的 `state_directory` 檢查紀錄：`receiver-status.json` 是接收器狀態；`receipt-<delivery-id>.json` 是已完成原生工具呼叫、讀取、發文的證據，以及可取得的 Token 用量。失敗或逾時回合仍計入 Hub 的 `--max-turns`，只加總成功回條會低估用量。
5. 暫停聊天室自動投遞後發送測試訊息，確認暫停期間不會派送新的模型回覆。在原有預算內恢復後，再核對預期的投遞行為。

失敗的原生回合保留第一份 `native-failure-<delivery-id>.json`：只記固定錯誤／階段、已觀察的工具證據與已回報用量；未知用量為 `not_reported`，不是零。此本機未完成證據不能判定伺服器處置或授權重試，即使已觀察到回覆也一樣。被 fence 擋下的重啟另寫一份 `receiver-restart-failure.json`，保留上一份 `receiver-status.json`；明確恢復前須先核對伺服器並確認舊子程序已退出。

瀏覽器自動刷新或 `rest_identity_and_room_passed` 都不能證明原生自動回覆已成功。各項測試請分別記錄為 **passed / failed / skipped / not_run**，附上 checkout commit、接收器版本、聊天室與投遞／訊息 ID。即使後續已有執行回條，安裝回條仍只代表安裝結果。不要將私有回條或憑證公開到 issues。

## 5. 檢查、停止與建立下一次有限度執行

安裝輸出提供完整指令，請使用記錄的實際路徑，不必自行拼湊：

| 回條欄位 | 動作 |
| --- | --- |
| `inspect_command`（`--print`） | 驗證本安裝的檔案歸屬與完整性並印出回條，不啟動模型。執行狀態另看 `receiver-status.json`。 |
| `start_command`（`--run`） | 以回條原有的範圍與預算執行專屬接收器。 |
| `disconnect_command`（`--disconnect`） | 停止此安裝接收器並確認釋放同一 Hub 綁定；會讀取受保護的 Token。 |
| `stop_command`（`--stop`） | 建立此安裝狀態目錄中的 `STOP`，回傳 `stop_requested`，不需要讀取 Token。 |

在另一個終端機執行 `stop_command`。這是**非同步的本機停止請求**；其中 `running_turns_cancelled: false` 不代表正在執行的模型已停止。執行中的接收器察覺 STOP 後，會嘗試停用自己的 Hub 綁定。請核對本機與 Hub 狀態；若接收器沒有執行或網路無法連線，本機停止指令不能確認伺服器端已停用。管理員也可以在 Hub 暫停自動投遞。

停止不會恢復一般 MCP 工具、完全解除 worker 連線或移除安裝。本流程沒有替換既有 Desktop、Claude 或全域設定，因此也沒有這些設定需要還原。請保留 STOP 與執行證據。

時間預算從**接收器第一次啟動**開始，而非安裝時；到期時間儲存在 `receiver-config.json`。重新執行同一份回條，不會延長期限、重設 Hub 投遞預算或清除 STOP。使用回條時，覆寫範圍或預算的參數會被拒絕。停止、到期或預算用完後，若要繼續，請明確選定新預算並建立新的安裝；不要刪除狀態檔或修改回條來假裝重新開始。建立下一次執行前，先確認舊接收器已停止。

## 問題排查

| 結果 | 下一步 |
| --- | --- |
| `codex_exe_not_found_install_official_cli_or_use_codex_option` | 安裝官方原生 Windows CLI、重開 PowerShell，或用 `--codex` 指定已確認的執行檔路徑。 |
| `codex_cli_missing_required_features` | 依官方步驟更新 CLI；目前版本缺少接收器所需功能。 |
| `codex_npm_metadata_invalid`、`codex_npm_native_metadata_invalid` 或原生套件缺失 | 修復／重裝官方 npm 套件，不要猜執行檔或更改核對條件。支援標準 nested 與 hoisted optional dependency 目錄。 |
| CA／TLS 或公開下載失敗 | 核對管理員提供的網址／指紋與直接網路連線，不要關閉 TLS 驗證。 |
| `dedicated_worker_identity_mismatch` | 核對 worker ID 與 Hub 核發的專屬 Token 是否對應。 |
| `room_identity_or_active_state_mismatch` | 核對專案／對話 ID、worker 授權，並確認聊天室為開啟狀態。 |
| `owned_codex_install_modified` 或 `owned_codex_receipt_invalid` | 保留安裝目錄供查核，不要繞過歸屬或雜湊檢查。 |
| 安裝完成但沒有回覆 | 執行回條中的啟動指令，檢查 CLI 登入、聊天室暫停、新訊息、接收器狀態、預算與實際執行回條。 |
| `receiver_was_stopped_keep_evidence_and_provision_new_bounded_run` | 保留原 STOP 與證據，需要時明確建立新的有限度安裝。 |
| 回合失敗後，接收器以 `disabled` 狀態結束 | 原生回合失敗時，接收器會停用自己的 Hub 綁定，因此再次執行同一份回條會以 `disabled` 結束。請執行[唯讀恢復報告](#唯讀恢復報告)、保留狀態目錄，並交由管理員判斷。重新啟用綁定是[交付 API](DELIVERY_API.zh-TW.md) 所述的明確 Hub 控制，重啟不會做這件事。 |

本教學描述安裝器與接收器的行為，不表示某台電腦已通過原生執行、Desktop 訊息注入或 ChatGPT 雲端投遞驗收；這些項目需要各自的實測紀錄。

## 升級與回應遺失恢復

先升級 Hub，再停止舊接收器並使用本頁目前的固定版本安裝器。既有安裝不會自行更新；不要覆蓋仍在運作的接收器或刪除它的狀態檔。Claude 使用解除／續期流程，新版 Codex 使用中斷指令並確認釋放，再建立新的專用安裝並明確設定預算；缺少所有權證據的舊安裝須由管理員核對。

新版接收器先儲存領取請求，遇到暫時網路錯誤會在期限與停止控制內退避重試。相同請求只在尚未派送、沒有完整訊息讀取紀錄且租約有效時取回原通知，不重複扣交付嘗試或回合。已派送後重啟不會逕自再啟動同一輪模型；租約真正到期後重新交付仍有預算成本。這不保證模型恰好執行一次，也不代表已測完原生程序的所有中斷情境。

包含 unresolved-native guard 的接收器，在舊 native turn 尚未釐清時會於 Hub join 前停止。保留 `native-active.json` 與交付 journal；確認舊 child 已退出，核對 server delivery／binding 狀態後才進行經授權的重試，不得單純刪除 marker 繞過阻擋。Hard-crash 測試使用合成且存活的 CLI child，真實 provider in-flight recovery 仍 pending。詳見[2026-10-04 證據](VALIDATION_2026-10-04.zh-TW.md)。核對時可用[唯讀恢復報告](#唯讀恢復報告)查看 Hub 的紀錄。

綁定單純到期後可以一般手動發文；房間暫停、停用綁定、封存或撤銷權限仍然有效。過期自動回覆不得拔掉交付欄位改成手動重發。詳見[交付 API](DELIVERY_API.zh-TW.md)。

## 唯讀恢復報告

出現 `native_exit_unconfirmed_preserve_binding`、回合失敗，或任何不確定能否重啟的情況時，先比對接收器的本機 journal 與 Hub 的紀錄，再做決定。`scripts/inspect-codex-chat-recovery.py` 會印出這份比對。**它只是診斷，不是恢復。**

它不在已安裝的用戶端內。請從 repository checkout 以回條中的專用 Python 執行，並記下 checkout commit：

```powershell
& '回條中的_PYTHON_路徑' -B 'C:\src\ys-aimemory\scripts\inspect-codex-chat-recovery.py' --receipt '用戶端目錄\codex-install.json'
```

它做什麼、不做什麼：

- 以 `inspect_command` 所用的同一項檢查驗證回條，再以唯讀方式開啟 `state_directory` 內已知的 journal 檔。它不改變接收器或產品的狀態：不寫入 journal 檔、標記、執行回條或鎖檔，不取得接收器鎖，也絕不移除 `native-active.json`。指令中的 `-B` 請保留。工具會匯入安裝器、接收器與用戶端的 `bridge.py`；少了 `-B`，Python 會在這些檔案旁寫入 bytecode 快取，其中一份位於用戶端目錄內。
- 只送出一個請求：以此 worker 自己受保護的 Token、經固定的 CA，對回條的專案與聊天室呼叫 `GET /v1/chat/status`。傳輸層會拒絕其他方法或路徑。不 join、claim、發文、disconnect，不更動租約或期限，不啟動模型，也不檢查程序。
- 會驗證它所依據的 journal 檔：`receiver-config.json`、`receiver-binding.json`、`receiver-claim.json`、`receiver-delivery.json`、`receiver-status.json`，以及該筆交付自己的 `receipt-<delivery-id>.json`。其中任何一個是連結、格式錯誤、過大或屬於其他範圍時，報告為 `invalid-local-state` 或 `scope-mismatch`，且不再連線 Hub。
- `native-active.json` 與 `STOP` 的處理刻意不同，因為只使用它們是否存在。標記若是連結就不會跟隨，格式錯誤或過大時不採信其內容，但仍視為存在：報告維持 native 退出未確認，並照常向 Hub 查詢。`STOP` 若是連結，會顯示為 `linked`。目錄內的其他檔案（包含其他執行回條）不會開啟。
- 只輸出固定的狀態名稱與句子。Token、lease 與 request ID、回覆金鑰、native session ID、路徑與訊息內文都不會出現。32 字元的識別碼預設會縮短；需要私下核對時才加 `--full-ids`。

選項：`--offline`（只看本機 journal，不讀 Token、不連 Hub）、`--json`、`--language zh-TW`、`--full-ids`、`--timeout 1..30`。結束代碼 `0` 表示已產生報告，不論狀態為何；`1` 表示回條、參數或 journal 位置無法通過驗證，stderr 只會有一個固定代碼。

| 狀態 | 意義 | 依據 |
| --- | --- | --- |
| `server-replied` | Hub 已記錄此交付的回覆。細項 `local-completion-missing`：接收器沒有存下 `receipt-<delivery-id>.json`，缺的只是本機紀錄，不要重送。`local-completion-recorded`：兩份紀錄指向同一則訊息。`local-completion-mismatch`：兩份紀錄不一致。 | Hub 最新交付的 ID 相同、狀態為 `replied`，且有回覆訊息 ID 與 sequence。 |
| `server-read` | Hub 已透過工具回傳完整訊息，但沒有記錄回覆。已讀未回不是完成的回合。 | 相同的交付 ID，狀態為 `tool_read`。 |
| `unresolved` | 找不到可對應此交付的完整讀取或回覆：僅 leased 或 dispatched、已失敗，或 Hub 的最新交付是另一筆。 | 細項與「仍缺少的證據」清單。 |
| `stale-generation` | Hub 的 binding 已是另一個 generation，此 journal 不再擁有它；該交付的結果維持無法取得。 | `receiver-binding.json` 的 generation 與 Hub 比對。 |
| `disconnected` | Hub 的 binding 已釋放。 | Hub 狀態與 generation。 |
| `unavailable` | 未取得 Hub 證據：離線、逾時、HTTP 狀態、憑證或 TLS 失敗，或清單中沒有此 binding。只顯示本機事實。 | 固定的原因代碼。 |
| `no-delivery` | journal 內沒有已派送的交付。 | 本機 journal。 |
| `scope-mismatch`、`invalid-local-state` | journal 或 Hub binding 屬於其他專案、聊天室或 worker，或受驗證的 journal 檔之一不可信。請停止並交由管理員處理。 | 本機 journal 或 Hub binding。 |

必須記得的限制：

- 狀態路由只列出 binding 目前 generation 的最新交付。較舊的交付或前一個 generation 的交付，會列為缺少的證據。**Hub 游標越過某筆交付，絕不視為已回覆。**
- `native-active.json` 不含程序身分，報告只使用它是否存在。PID 不存在、存活或已結束，都不能證明原本的 child 已退出；因此報告不會說可以安全重試，也不會宣稱 native 已退出。
- 接收器執行中所產生的報告只是當下快照，檔案可能隨後改變。
- 判斷邏輯由 fixture 測試涵蓋，尚未以真實中斷的 native turn 驗收；驗收前請記為 `not_run`。

## 明確中斷與恢復手動發文

新版回條的 `disconnect_command`（`--disconnect`）會建立 STOP、等待最多 40 秒取得接收器鎖，並以目前版本釋放同一 binding generation。成功讀回 `disconnected` 才算完成；既有房間暫停、權限與其他 worker 的限制仍適用。它需要讀取同一 Windows 使用者保護的 Token，但不會啟動模型。`--stop` 仍只要求停止，不代表中斷或已取消模型。

若接收器仍在停止，稍後重試 disconnect。若留下 `native-active.json` 或缺少 `receiver-binding.json`，程序退出或舊版所有權未獲確認，必須保留證據並由管理員處理；不要刪檔繞過。已改變 generation 時也不會釋放新的連線。升級後須使用新版、重新釘選的安裝器；舊安裝不會自動取得此功能。

上方執行方式只對已驗證雜湊、人工檢閱的安裝腳本，在子 PowerShell 程序指定 ExecutionPolicy Bypass；不變更全域政策，且仍受 Group Policy 管理。若組織政策拒絕，請由管理員處理。
