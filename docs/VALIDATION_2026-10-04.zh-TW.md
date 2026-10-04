# 驗證記錄：2026-10-04

[English](VALIDATION_2026-10-04.md) | [繁體中文](VALIDATION_2026-10-04.zh-TW.md)

## ChatGPT 雲端 idle restart 驗收：2026-10-05 臺北 02:06

在部署來源 `6d0ce27fd0d58745476dadd4cc6ca393fe8c339f`，新的限定雲端 fixture **通過兩次自動原生完整讀取／回覆，兩次之間執行一次官方 idle gateway stop/restart**。兩則新的人類訊息皆從網站送出；任務建立後沒有手動 model prompt、工具核准或權限修改。兩次 event callback 均在 attempt 1 回 HTTP 200；另以相同 fingerprint 的 native `read_delta`／`tool_read`、`post_message`／`replied`、兩筆 durable replied batch 及網站兩則回覆確認 delivery，沒有把 callback 接受當作已讀。

Idle restart 保留相同 binding、generation、subscription、expiry、原 deadline、cursor 與剩餘事件額度。Held-process 證據確認原 gateway 已退出才啟動替代程序，並核對替代程序的新 creation identity 與 executable。沒有 rejoin、renewal、舊事件重播或額度重設。保留的是 logical state 與第一筆 delivery digest，不宣稱 database／WAL 檔案 bytes 不變。這是 **gateway transport restart**，不是 ChatGPT 模型重啟或 crash-recovery 測試。

第二則回覆後，native task 自行暫停，operator 未按暫停；另行核對 `events/unsubscribe` 與持久化 unsubscribed state。Operator 隨後僅執行一次官方 runtime stop 與 Hub disconnect，均成功，02:06 確認 closure；該截點 deadline guard 程序退出仍須另驗。ChatGPT 敘述與 saved progress 仍顯示兩則中的一則，與兩筆實際 tool／server receipt 不符，列為 UI 報告落後。Gateway 與 Hub 時鐘約差 4.9 秒，不可將跨主機時間視為同一時鐘。

02:12 的唯讀程序檢查確認原 gateway、替代 gateway 及原 deadline guard 的 PID 均不存在；無法取得 exact exit codes，未 kill 或額外 stop。不宣稱其他 host 或 persistent MCP 程序皆已退出。

測完後讀回既有外掛的實際權限 UI，選中 **「允許低風險工具（預設）」**，未選允許所有工具；未修改權限。核對的範圍、保存的限定 prompt 及可重現界線見[私人雲端教學](CHATGPT_PRIVATE_TUNNEL.zh-TW.md)。這是既有帳號的一次驗收，不保證新帳號或所有權限設定皆相同。下方 A／B 的 self-stop 失敗仍保留，仍須 operator 獨立確認停止。模型 crash/restart、in-flight 或 unknown-commit recovery、無限持續運作、同時三客戶端 chat、controlled token-cost benchmark 在**本 fixture 仍 not_run**；不推導額外部署或完整 suite 通過。

## Gemini 原生 idle restart 驗收：2026-10-05 臺北 01:06

已部署來源 `6d0ce27fd0d58745476dadd4cc6ca393fe8c339f` 的 fresh bounded Gemini V6 fixture，**首次自動原生讀取／回覆、官方同 binding idle receiver 停止／重啟，以及重啟後第二次自動原生讀取／回覆皆 passed**。Coordinator 觀察實際 native `chat_read`／`chat_reply` 結果與網站對應回覆；兩筆 durable journal attempts 另記錄 `replied`、return code 0。兩次回覆均沒有透過中間手動 model prompt 提供。Native admission／status、私有 harness 檢查與實際 delivery 保持不同證據關卡。

首次 delivery 已 replied、沒有 unresolved delivery 後，透過官方 host lifecycle control 重啟。Idle restart 前後保留 binding 身分、generation、expiry、event budget、processed cursor 與 journal state，未 rejoin、重設 budget、延長 expiry 或重播舊事件。Held handles 證明原 receiver parent／child 在 enable 前已退出；替代 parent／child 具有新的 exact creation identity，executable 與 arguments 均已核對。Persistent MCP 程序排除於 receiver inventory；獨立 observer 另核對這些 receipts 與替代程序身分。私有 V6 file-URI normalization 修正的是驗收 controller 先前的 path 解讀，**不是產品 code recovery fix**；下方歷史失敗仍保留。

Main STOP 僅執行一次、exit 0，server binding 已停用。臺北 01:31 後續唯讀核對確認原／替代 receiver exact PIDs、deadline guards 與另列 auxiliary PID 均已不存在，無法取得 exact exit codes。Controller ready PID 亦不存在，但 ready receipt 未保存 creation identity。約 01:45 coordinator 展開 native tool 的官方 host inventory 實際輸出，確認 controller 已停用，不需要再停用一次。因 cleanup helper 要求的 held-process exit receipt 在程序消失後無法取得，保留未啟用且已釘選的 controller 檔案。**執行環境停止與官方停用讀回已確認；不宣稱已完整移除檔案。**程序不存在不替代 held-handle exit receipt；persistent MCP lifetime 另列。

本輪只驗收已觀察的 idle receiver lifecycle 與兩次自動 delivery。Native model crash、in-flight／unknown-commit recovery、無期限運行、第三次 delivery 及同時三客戶端 chat 均為**本 fixture not_run**；不推導新的產品部署或完整 suite passed。

## 歷史原生驗收補充：2026-10-05 臺北 00:52

以下觀察屬於已部署來源 `6d0ce27fd0d58745476dadd4cc6ca393fe8c339f`；後續文件與私有 harness revision 沒有改變已部署產品。不新增完整 suite、部署或 provider-recovery passed 宣稱。

Fresh bounded Cloud identity-only event trial **自動原生 identity 執行 passed**。事件 callback 約於臺北 00:27:19 收到 HTTP 200，實際 native `identity` ingress／completion 隨後於 00:27:47 出現。Coordinator 觀察原生結果與正確限定身分，獨立 observer 另以 gateway tool-call receipts 核對。事件至 identity 執行間沒有手動 model prompt；callback 接受本身不算原生執行。本輪沒有 `read_delta`／`post_message` ingress：**本輪自動完整讀取／回覆 not_run**，較早自動讀寫 failed 與手動 native passed 分開保留。另一次完整 read/post 比較記於下方；不宣稱完整 formal GPT 驗收。

Task 要求的自行停止 **failed**，仍為 enabled。Operator 透過官方 UI 暫停，unsubscribe 另獲核對。首次 runtime cleanup 在 local STOP 與 DB stopped 保存後 failed：官方 tunnel client 正規化兩個 own health/log profile path，私有 harness 的完整 profile byte pin 因此拒絕清理。另以經審查、僅執行一次的 cleanup 反轉這兩個 path 重建原完整 profile hash，重新核對 exact runtime ownership，再 disconnect Hub binding 並停止官方 runtime。最終 runtime readback 與本機 stopped state 於臺北 00:39 確認閉合。保留原失敗，不推導 guard exit-code 成功。這是私有驗收 harness 問題，不是產品 delivery defect 的證據。

後續 fresh bounded Cloud trial 在相同已部署來源、與 identity trial 相同 permission choice 下，**單一事件自動完整原生讀取／回覆 passed**，沒有改用「allow all tools」。臺北 00:46:23 送出 human 訊息，00:46:31 callback 收到 HTTP 200。實際 `read_delta` ingress／completion 為 00:47:01.923–00:47:01.994，receipt 為 `tool_read`；`post_message` ingress／completion 為 00:47:08.050–00:47:08.113，receipt 為 `replied`。Native UI 核對同一事件完整讀取、沒有 unread 或 truncated content，Coordinator 另在網站觀察對應回覆。Task 建立至 cleanup 間沒有手動 model prompt。這驗收單一事件自動關卡，不驗收 continuous delivery、第二事件、restart 或完整 formal GPT；較廣關卡仍 **not_run**，歷史失敗保留。

自行停止再次 **failed**：原保存 task instructions 明確要求 stop，model 後來卻聲稱應保留 trigger。臺北 00:48 已核對 operator UI pause；經審查的 exact-scope stop 僅執行一次、exit 0，閉合已確認。模型停止敘述不是 lifecycle 證據，仍須官方 pause／unsubscribe 與獨立 runtime closure。

相同已部署產品來源的 fresh Gemini 訊息約於臺北 00:06:41 **自動原生完整讀取／回覆 passed**，中間沒有手動 model prompt；native UI、Hub replied receipts 與 durable replied journal 均核對為首次 attempt。後續同 binding idle restart **在私有 controller、receiver-disable consume 前 failed**。Native 診斷確認 `GetAllPlugins` 回傳 `file:` URI，私有 controller 卻當一般 filesystem path 處理；此失敗不斷言產品 receiver bug。Receiver／controller／guard cleanup 已核對，該輪閉合、未重播。另建私有 versioned fix 加入 strict file-URI normalization 與診斷，十項離線 fixtures passed。**在此歷史截點，live restart 為 not_run**；後續 fresh V6 驗收另記於上方，不抹除本次失敗。

後續 fresh Gemini fixture 已 prepare 並 join，因使用者正在操作電腦，於臺北 00:39 停止。未安裝 receiver、未送 human test message。已記錄 metadata stop／exit，臺北 00:47 核對官方 native disabled readback。00:52:40、約 deadline 後 9.5 秒，先前核對身分的 exact guard parent、child 與另列 auxiliary process 自然消失，未 kill。Guard 記錄 cleanup exit 1：原成功 stop 已消耗 exclusive stop ledger，未准入新 control，原 stop／disable receipts 不變。程序消失後無法取得 exact exit codes，不宣稱 guard exit 0 或整個 host 程序閉合；persistent MCP lifetime 另列。這不是 delivery 或 restart passed。同時三客戶端 chat 與 overall acceptance 仍 pending。Native status、source fixtures、operator cleanup 與實際 model 讀寫保持不同關卡。

## 最新部署版本：臺北 23:02

2026-10-04 臺北 23:02，來源 `6d0ce27fd0d58745476dadd4cc6ca393fe8c339f` 取代 `7652f1d7f04ef4c00e8860217a0f732f98dcb58e`。核對運行中的 image 為 `sha256:bee084e88203ef1425f70a8d8f84cc8f783e112cfd04945c6cca5032aac5b09a`。後續文件 commit 與此部署版本分開。

隔離部署主機 PostgreSQL stage：**1,088 passed、63 skipped、3 warnings，216.14 秒**；image package inventory 亦 passed。Promotion：**457 checks passed**，**2026-10-04T15:02:25.457778Z–15:02:47.672031Z**，22.214 秒。保留 schema 6、全部 26 個 public tables、migration history、權限與工具目錄；僅允許 `web_auth_entries` 一般到期清理。受保護的升級前備份已核對 hash 與 archive 可讀性；live backup restore 與 off-VM transfer 仍 **not_run**。部署後 current source／image readback 相符，運行服務 healthy，PostgreSQL health 為 `ok`。

首次 stage 在 **build 與 live 變更之前**因來源 inventory 檢查失敗：Windows Git archive 將內容轉成 CRLF，但 inventory hashes 對應原始 LF Git blobs。保留此失敗；新的 LF archive 逐一核對全部成員與原始 Git inventory 後，另行 stage／promotion，沒有抹除或重播失敗 attempt。

| 精確 6d0ce27 公開 CI run | Windows installer | SQLite | PostgreSQL |
| --- | --- | --- | --- |
| [37209955545](https://github.com/Ya19880104/ys-aimemory/actions/runs/37209955545) | 326 passed、1 warning；16.52 秒 | 894 passed、32 skipped、3 warnings；135.64 秒 | 1,121 passed、30 skipped、3 warnings；199.23 秒 |
| [37209953630](https://github.com/Ya19880104/ys-aimemory/actions/runs/37209953630) | 326 passed、1 warning；15.89 秒 | 894 passed、32 skipped、3 warnings；124.72 秒 | 1,121 passed、30 skipped、3 warnings；141.66 秒 |

兩輪皆 completed／success。不同環境與輪次計數不相加，skip 仍是 skip。下方較早本機 924-test 結果只對應精確 product-code revision `225fc57844b36fb48caaf6815f88f053f1091fbf`。

公開 Codex bootstrap `c609da7f849f8c73c3346deab8578ca1668418fa` 的四個來源固定為 `2e2739bf9307f02e42708209d987d888ab636eec`；bootstrap raw SHA-256 為 `a7294c0826e45e076ef0ebbd9530baa48f7e344babcf482f74d53c4349f7c691`。四個公開 HTTP-200 下載來源與其 pins、Git-blob hashes 皆相符。Coordinator 另行核對已部署瀏覽器的英文／繁中 command generator；完整性與瀏覽器呈現不代表完整 bootstrap 執行或 native delivery 通過。

在歷史 23:02 截點，Native 關卡仍分開：下方限定的 Codex → Claude → Gemini 順序正式交接 passed；同時三方聊天仍 **not_run**；Gemini idle-restart recovery 沒有新的 passed 證據，較早一輪仍 **failed／incomplete**。保留後續 Gemini 原生 tool-read 成功、但工具核准延遲造成 `chat_delivery_expired`、未成功回覆的失敗；此處不宣稱更新的自動 delivery passed。Cloud 自動讀取／回覆仍 **failed**，與手動原生讀寫 passed 分開。部署、CI 與文件檢查不推進這些關卡。

本報告分開記錄來源檢查、部署及原生／瀏覽器驗收的版本界線。先前候選 `6ea3ca51a8863b38d0c8d85c1beb2c1f7392858f`（基線 `ee21c2dfccba1d7f60b44563880c8b6a864bf971`）曾在下方較早一輪檢查中部署；後續結果見下一節。較早的原生證據保留於[2026-10-03 記錄](VALIDATION_2026-10-03.zh-TW.md)。


## 歷史候選來源與限定原生證據（22:30 截點）

截至臺北 22:30 的證據截點，產品 code `225fc57844b36fb48caaf6815f88f053f1091fbf` **尚未發布、未部署**；當時 live 為 `7652f1d7f04ef4c00e8860217a0f732f98dcb58e`。獨立來源審查涵蓋 CLI 建立失敗的安全清理、保留舊 journal 的保守 stale-claim recovery、terminal cloud reservation conflict、有限 failed-native receipt、fenced restart 保留先前 status、callback counter 相容性及唯讀 recovery inspector。未知 token usage 維持 `not_reported`；不完整本機證據不授予 retry。這些來源／fixture 結果不驗收已部署恢復行為。

在該精確 code revision 僅執行一次本機 Windows／Python 3.12.13 完整 suite：**924 passed、2 skipped、3 warnings，403.75 秒**，exit 0，2026-10-04T14:11:52Z–14:18:40Z（臺北 22:11–22:18），stderr 為空。兩項 skip 需要明確 opt-in 的可拋棄 PostgreSQL runtime；warnings 涉及 Starlette/httpx、Pydantic 未解析的 lifespan forward reference 及 per-request cookies。Provider／真實線上資料庫驗收未執行；後續文件 revision 另列身分，不跨 suite 加總 counts。

候選 Codex bootstrap 固定為 `c609da7f849f8c73c3346deab8578ca1668418fa`，四個來源檔固定於 `2e2739bf9307f02e42708209d987d888ab636eec`；raw SHA-256 為 `a7294c0826e45e076ef0ebbd9530baa48f7e344babcf482f74d53c4349f7c691`。獨立 Git object 核對確認四個來源 hash 與候選，以及 UI／英文／繁中 consumer revision／hash pins 相符。這是本機完整性證據，不是公開下載或完整 installer 驗收。歷史 `8e7267f323e54c7b6f7731df866f9c9a7396e214` 記錄 **868 passed、2 skipped、3 warnings，422.92 秒**，UTC 13:32:03–13:39:11，另行核對 bootstrap `2ab108a6`／source `c8d32664`／raw SHA-256 `54d7027effd8fa36f0ef5b424ca543b96142a9dd145e8f0e1bdc6778ddf47f84`。該較早結果不驗收後續 runner 修改。

限定合成 fixture 的**正式 Codex → Claude → Gemini 順序交接 passed**：三次 fresh native admission、兩次結構化 handoff 及最終 Gemini checkpoint。唯一允許的 plan 檔維持 fixture commit `baa1df5ee146009ea993368f1d2915a442e7f765`；三個 clean workspace 獨立核對均為 1,725 bytes、SHA-256 `b82f94f67342c5c42d12282ed657bf3d0e6221690aceb5737ad7d6fa42d37bb4`。Native reports 記錄完整 source、既有 artifact（1,393 chars／1,725 UTF-8 bytes）及 attachment（解碼後 1,725 bytes）讀取，server digest 相符。Coordinator 觀察原生前段工具呼叫及最終輸出，再於網站核對最終 checkpoint entry 與兩次 handoff；未獨立展開每項工具回應。精確最終 checkpoint ID 由 native 回報，保存的網站證據呈現其敘述。Codex native Git／hash computation 仍 **not_run**，與 operator 核對分開。Task 仍 open；不代表產品、merge 或 release 驗收。**同時三客戶端 chat 仍 not_run。**

Recovery inspector source `71deeb8fc322160a5b49523e8cbc12e28542a4d1` 的 online／offline CLI 報告維持 client bytes／mtime 不變，但 receipt 預設 state path 未讀到 custom crash fixture，回報沒有本機 delivery；此負面結果保留。另以程式化方式讀取實際 custom state，搭配一次 own-worker status GET，回報 `server-read`，仍缺 `native_exit_unconfirmed` 與 `hub_reply_record`；before／after state snapshots 相符。不授予 retry、不證明 native exit，也不驗收 CLI custom-state 支援、server-replied 或自動恢復。該精確版本觀察不自動驗收較新 inspector revision。

先前 live 7652 的 Gemini B、C 訊息連續 passed：human sequence 55 → native reply 56，再 human 57 → native reply 58，均為 attempt 1，網站送出至回覆約 14、15 秒。兩則使用實際 native `chat_read`／`chat_reply`，送出與回覆間沒有手動 model prompt；native UI、Hub replied 收據與兩筆 durable replied journal attempts 一致。後續同 binding idle restart **failed／incomplete**：檔案 config 切換未 reload host，到期前未出現替代 receiver。該 fixture 與較早 permission-wait 到期 fixture 均已關閉，保留舊 journal、未重播。

較晚 fresh Gemini run 在臺北 22:22 收到自動通知，但 native `chat_read` 回 `chat_not_active`。Coordinator 於 22:29 的 server readback 為 `dispatched`，`read_at`／`replied_at` 皆 null；程序證據確認仍是較舊 MCP bridge，沒有對應 fresh bridge。22:30 STOP cleanup 成功：fresh binding 已停用、version 2，無 fresh receiver 存活。22:31 UI refresh 後，較舊 MCP bridge 仍運行。保留此 native-read failed 關卡；通知接受不代表 delivery，不宣稱新的 native idle-restart passed。支援的官方 host reload 仍未驗證。Cloud 自動事件在較早獨立一輪仍 **failed**，待使用者比較；這些結果不推進 live deployment、更廣 crash recovery 或 overall product acceptance。

## 歷史 7652 部署來源與 installer chain

Live source：`7652f1d7f04ef4c00e8860217a0f732f98dcb58e`；image：`sha256:d4d2f2800c9f9c090f631aed807e7882aa7cbdfc1b15cc2b13765c1d81d2cab4`。隔離部署主機 suite：**1,010 passed、63 skipped、3 warnings，232.17 秒**。Promotion：**454 checks passed**，2026-10-04T11:45:02.755408Z–11:45:26.279132Z。保留 schema 6；26-table 比對僅允許 `web_auth_entries` 到期清理。已檢查 backup headers／hashes，restore／off-VM acceptance **not_run**。候選 CI：Windows **268 passed、1 warning**；SQLite **817 passed、32 skipped、3 warnings**；PostgreSQL **1,043 passed、30 skipped、3 warnings**。不同環境結果分開，skip 不算 passed。

現行 Codex bootstrap：`31a1db36e04d304c3e2823b31d5b175ab17e87e2`；四個來源固定為 `bd25c375bc6046c1cfbe488c859cde2c7e8a3421`；raw bootstrap SHA-256：`1a03b5a79ef9242f197962527320f5146ebdbb52b3619273afe44c2d94906e7c`。公開 raw bytes／四個 hash 均核對相符，published runner 在 join 前檢查未釐清 native state。線上 guide／clipboard 的 URL／hash 相符，仍須明確啟用。Python `setup.install` native-client preparation 路徑已測試，但下載的 PowerShell bootstrap 完整執行 **not_run**。Hash／準備通過不代表 native model delivery。Claude chain 另行保留：bootstrap `5f9400802ecdfe98f350a25a1f6848e1cf5ba1d0`、source `b168876f00f85ccb37e97bb11c3678d8cb9e6ae4`，與已部署 Claude guide 相同；不推導新的 Claude end-to-end 驗收。

Coordinator 提供的 native 證據：2026-10-04 臺北 20:17，實際 official Codex CLI 到達 tool_read gate，child 仍存活。強制終止實際 receiver，以相同參數／state 重啟，於 unresolved-native guard 以 exit code 1 停止。Binding、delivery、generation、turns（1 of 3）與 attempt（1）維持不變。Owned Job 程序全部停止，新 binding 已停用，cleanup errors 為空。限定真實 provider in-flight fence **passed**；post-commit-unknown 與完整 automatic resume **not_run**。獨立複核確認 before／after、六份 state hash 與受控程序識別證據相符。準備使用程式化 setup.install，未執行 PowerShell bootstrap。該較早截點的 Gemini 結果仍 pending；後續限定原生證據另記於上方。PR18 維持 draft、#12 open，不宣稱 overall product PASS；後續 native 結果須另附精確版本補充。

## 後續來源檢查與 cloud 最終驗收：2026-10-04

首次較完整 CI／staging 在 `bd25c375bc6046c1cfbe488c859cde2c7e8a3421` 的安裝來源 pin 檢查失敗：修正版 receiver 與舊 bootstrap 雜湊不符。已保留失敗，未升級該候選。在該歷史部署截點，bootstrap 固定使用 `bd25c37` 的四個來源檔；網頁產生器與雙語教學固定下載 bootstrap `31a1db36e04d304c3e2823b31d5b175ab17e87e2` 並核對 SHA-256。完整性測試仍核對檔案，可於 shallow checkout 與無 Git 的 release archive 執行。修正後的 bootstrap、產生指令及教學檢查為 **70 passed、2 warnings，47.32 秒**；最終 7652 CI／部署結果另記於上方。

Coordinator 提供的來源證據：`07ff550c25dd0f8beb44338f943c56621762e78c` 包含 cloud trace `fd8d627c7b5856a9e03e63d5b2c826dd5e62a87e`、hard-crash fixture `a96ee30d68e54fd5e17a87b80ab374f25ff3ca24` 與 unresolved-native admission guard `07ff550`。限定 suite（`tests/test_codex_receiver_crash.py`、`tests/test_codex_chat_runner.py`、`tests/test_codex_chat_setup.py`、`tests/test_cloud_tunnel_gateway.py`）：**208 passed、1 項既有 Starlette warning，12.46 秒**。獨立來源審查：限定範圍 **GO**。該較早來源檢查截點的 live VM 為 `af79c01a24e96898125de42e8be0d596f869fb16`；上方後續 7652 promotion 已更新部署狀態。

合成 hard-crash 測試強制終止 receiver parent，保留存活的假 CLI child，驗證 unresolved-native fence 在 Hub join 前阻擋重啟。先前 native Codex idle restart 在觀察範圍內 passed；限定 fence 以外的完整真實 provider in-flight recovery 仍 pending。保留 `native-active.json` 與交付 journal，確認舊 child 已退出，核對 server delivery／binding 狀態後才進行經授權的重試；單純刪除 marker 不算恢復。

新的 cloud 最終驗收：首次 callback attempt 在 **2026-10-04 臺北 19:17:16（UTC 11:17:16）** 收到 HTTP 200；native task UI 回報 last_run 19:17:17，這不是執行證明；手動提示前，截至 19:20:20 未觀察到 gateway native read／post ingress。本次自動事件讀取／回覆 **failed**。明確的手動診斷提示後，19:20:36 出現 native `read_delta`／`tool_read`，19:20:42 出現 native `post_message`／`replied`。手動 native 讀寫 **passed**，與失敗的自動關卡分開。Trace 時間與相同 fingerprint 可區分 callback、首次 native ingress 與 receipt milestones，無須公開訊息正文或私人識別碼。

Task 在 19:20:45 暫停、19:20:50 unsubscribe；runtime 於 19:21 後停止，已確認程序退出。第二個事件與 restart 驗收 **not_run**。本輪 native UI tool-metadata refresh 失敗，但手動 native tools 仍可用。根因仍未釐清，範圍介於自動 task context 與首次 tool call 之間；未確認外部原因。歷史 native cloud 證據保留原版本界線。

## 歷史修改與契約

四項 P2 修正：舊 Claude bootstrap sources 保持 main 歷史可追溯；到期恢復一般手動發文但保留 pause/disable/archive/revocation；以持久化 receiver-specific request ID／binding generation 恢復已 commit 而回應遺失的 claim；文件連結支援經驗證 mirror 或真正語系 `/help` 入口。同步更新兩客戶端 installer、hash、UI 指令與雙語指南。

Replay 僅恢復原本 still-live、尚未 dispatch／記錄任何完整訊息讀取的 lease，不延長、不重複扣 attempt/turn。批次部分讀取也不可再次 ready；其他 receiver 不得取得該有效 lease。保留 generation、payload、admin fences；不保證模型恰好執行一次。Claim memo 僅 metadata、不含正文；idle/busy/paused polling 不新增 memo，歷史仍跨 renew 累積。私人 cloud pilot 保持 legacy claim 路徑。

## 歷史已記錄驗證

| 來源／關卡 | 結果 | 界線 |
| --- | --- | --- |
| 歷史候選 1422187：完整本機 Windows | 748 passed、2 skipped、3 已知 warnings，377.87 秒 | 不驗收後續修改 |
| 歷史候選 1422187：隔離 VM PostgreSQL | 898 passed、56 skipped、3 warnings，199.84 秒 | 與本機不同環境；skip 不算 passed |
| 歷史候選 1422187：promotion | 431 checks passed，22.2 秒；2026-10-03T17:15:20Z–17:15:42Z | 保留 schema v6／26 tables |
| 歷史候選 1422187：browser help notes | en/zh passed | 新 upgrade/expiry 說明顯示；之後 copied instructions 發現失敗 |
| Catalog 修正 8dfa278 | 149 passed、2 warnings，101.24 秒 | 使用真實生成 translation catalog；保留初始兩項 regression 失敗 |
| Claim cleanup 修正 4ed9877 | 70 passed、1 warning | Idle/stale response 後 missing file；permission error 仍 fail closed |
| bd8d4e6 bootstrap/runner checks | 76 passed、1 warning，7.03 秒 | Source receiver/installer 檢查，不是 native model execution |
| 6ea3ca5 前 final copied-command checks | 4 passed、2 warnings，5.32 秒 | 生成指令檢查，不是 final browser clipboard 驗收 |
| 6ea3ca5 公開 pins | 13 checks passed | Download/hash/source 相符，不是 native install 驗收 |
| Sol 6.1 獨立只讀 audit | 限定範圍 GO | Ownership/fences/docs／immutable pins，不代表完整 native 驗收 |

首次瀏覽器 copied instructions 出現 `# undefined`。舊 harness 使用假的 translation function，未捕捉缺陷；新兩個 regression cases 在 8dfa278 最小 literal-call 修正前確實失敗。修正後 harness 使用真 catalog、兩語言與兩客戶端。來源 passed 不抹去首次失敗，也不替代 final browser replay。

CodeRabbit 完成 1422187 審查，提出一項 minor pending-file cleanup，4ed9877 以三個針對案例修正。後續 review rate-limited；Codex review quota unavailable。Review status 本身不代表完整獨立驗收。

## 歷史公開 installer chain：較早 6ea3 檢查

| 客戶端 | Installer revision | Verified source revision |
| --- | --- | --- |
| Claude | 7b666c6dae39d49fbc700540ad2248829c133b80 | 5b54867a4204e8218a541b7d87039a2700bf22ac |
| Codex | bd8d4e684e0f510312cf491e015dbd1d3944fff4 | 4ed987759e3d83e8caa5788831de3544438172db |

Codex installer SHA-256：`F5E622AC3BC21CA06B311238C4B49491324FDD01C40F84FC97081913A4EBFDD7`。在該較早截點，[Codex setup](CODEX_CHAT_SETUP.zh-TW.md) 雙語與 UI pins 一致；[Claude setup](AUTOMATIC_CHAT.zh-TW.md) 保留獨立驗證 chain。既有安裝不自行更新；先升級 Hub、停止 owned receiver，再依明確 installer/renewal 流程操作，保留舊 state／證據。

## 歷史候選驗證：6ea3

- 6ea3ca5 隔離主機回歸：**901 passed、57 skipped、3 項既有 warnings**，199.64 秒；測試資料庫已移除。
- 部署：**433 項檢查通過**，22.22 秒；2026-10-03T17:37:27Z–17:37:49Z（臺北 2026-10-04 01:37）。Schema v6／26 張資料表維持不變。映像：`sha256:9b78fdb4574b50391b9147ea15ca13b41f239fe7aa5caf22280634f4c3667a4f`。
- 6ea3ca5 CI：push／PR 的 Windows installer、SQLite、PostgreSQL 六項工作全部 passed（[push](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140841102)、[PR](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140843688)）。
- 實際 Chrome：英文／繁中 × Claude／Codex **四組複製指引皆通過**。文字框與剪貼簿一致、無 `undefined`，安裝網址、SHA-256 與語言／客戶端對應教學正確；切換語言保留專案與對話。本項僅產生／複製指引，未執行安裝器或喚醒模型。

## 剩餘驗收界線

Issue #12 保持 open，追蹤更廣 lifecycle/capacity。Gemini idle receiver restart、cloud 兩次自動 delivery 及其中的 idle gateway restart 僅在上方限定 fixture passed。完整 native model crash/restart、更廣獨立 STOP lifecycle、legacy cloud lost-claim、長期 subscription/expiry/offline/revocation/duplicates/bursts、memo retention/load、controlled cost benchmark 仍 pending。7652 的限定原生崩潰防重送及本次兩事件驗收，不涵蓋這些較廣關卡或無限持續自動運作。

上述歷史部署均建立備份、核對 header/hash；restore／off-host acceptance not_run。歷史 manifest 只識別原交付，不驗證後續來源修改。公開報告不含憑證、host、私人身份、訊息正文或私人截圖。
