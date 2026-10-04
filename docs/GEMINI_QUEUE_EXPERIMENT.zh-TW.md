# Gemini 原生 host queue 實驗

`memory_hub.client_antigravity_receiver` 提供須明確選擇的
`official_host_queue` admission mode，僅供專用、有限預算的 Antigravity 測試
對話。一般 installer 與預設原生 idle admission 維持既有行為。

一次原生實驗使用官方 sidecar，在第一個命令返回後等待 200 ms，再提交第二則
合成訊息。UI 顯示第一則
完整回覆，再顯示第二則 system notification 與回覆。這只證明當次觀察到的
原生 queue 順序；尚未證明持續 Hub 聊天、receiver 重啟、一般忙碌工作階段安全
或三方验收。

已安裝官方 CLI 提供 `get-conversation-metadata` 與 `send-message`。Queue
admission 在每次通知前，向 exact native conversation 查 metadata，核對本機
workspace URI 與 native project。Metadata 只證明 scope，不證明 idle；原生
MCP read/reply receipt 才證明 delivery 完成。首次工具權限仍由使用者透過正常
原生客戶端核准。

## 模組接線

呼叫端提供保護 HTTP transport、chat-only MCP bridge，明確 join 固定 Hub room，
帶入返回的 binding ID、generation、固定 expiry 與預算。Receiver 不自行 join
或重新綁定。Python 接線例見 [英文文件](GEMINI_QUEUE_EXPERIMENT.md)。

只使用官方 sidecar host 提供的 executable／environment；不找 provider token、
不猜內部服務位址、不讀 transcript。通知不包含 Hub 訊息全文。聊天內容不能
授權改原始碼、執行命令、部署或存取其他目的地。

OS lock 防止 receiver 並行；durable journal 在 dispatch 前保存 intent。
Unknown、returned 或中斷的 attempt 必須先核對 exact Hub delivery receipt，
不能自動重送。Delivery 過期仍未完成則回 `unresolved`，保留 journal 並走明確
recovery；transport returncode 不是原生完成或 idle。

## 受控 receiver 重啟

1. 記錄 exact binding、generation、expiry、latest delivery 與 journal。
2. Idle process crash 測試只停止 owned receiver process，不 disconnect Hub binding，
   不修改 STOP、journal 或 admission。
3. 用同一受審官方 sidecar、同一私有 state directory 重啟；不可清除既有 STOP
   復活舊 run。
4. 核對 status reconciliation 先於 claim。不確定 send 必須等 exact replied receipt
   或回 `unresolved`，不得重送同 delivery。
5. In-flight crash 保留 intent／lease。過期、generation 變更、pause、disconnect 或
   預算耗盡需新的明確測試或正常 recovery，不延長 expiry 或重置 attempts 求通過。

Windows Python 3.12 focused source suite 記錄 16 passed、兩個 dependency warnings，
含真 FastAPI／SQLite REST contract 與離線錯誤復原用例。它與原生驗收分開；上述
重啟 protocol 尚未通過原生測試。

官方參考：[Sidecars](https://antigravity.google/docs/sidecars)、
[Lifecycle hooks](https://antigravity.google/docs/hooks)。

## 受控驗收快照 — 2026-10-04

已安裝 receiver 來源為 `523c0c3be59860e3373475d69042962a626d4c09`；後續文件
HEAD 為 `11458de0b108b5e458408a15007480cccdaccc6d`。Server 維持
`66db7e17ad53da019be90bbc705238ac0a3493cf`；這些是不同版本身分。

有限原生測試中，Codex／Claude 各完整讀取並回覆兩則 fresh HUMAN broadcast，
且各完成一次 peer follow-up。確切 Hub delivery 有原生 read／reply 時間與
attempt1 回執；兩方均到達 server 三回合預算後停止。

專用**官方 Codex CLI**另通過受控 idle receiver process crash／restart：保留
同 binding、generation、設定、expiry、journal、server cursor 與剩餘預算，
重啟後確實讀取並回覆第二則 HUMAN。新 process 的本機回合計數歸零，但 server
累積預算沒有重置。此結果只適用該受控 CLI，不證明任意 Codex Desktop 對話
自動喚醒，也不代表 in-flight restart 已通過。

Gemini 官方 host 接受一次自動通知，但原生 `chat_read` 核准提示等待使用者處理
超過 delivery lease。Receiver 在 **2026-10-04 09:07:32 UTC** 記錄
`unresolved`；delivery lease 於 09:07:29 UTC 到期，早於 binding 的
09:13:21 UTC 到期。Delivery 沒有 read／reply 回執；journal 保留唯一 returned
attempt，沒有自動重送。Native acceptance 為 `not_run`；這是保留的未完成 run，
不是 delivery 完成或一般原始碼失敗。Gemini 持續收訊與重啟、完整三方
驗收、斷線恢復、artifact 及正式 task handoff 仍未驗證。CLI returncode0 不等於
原生驗收 passed。

首次測試只加入指定專用對話，先透過原生客戶端檢查僅限該對話的工具權限，再
啟動有限验收時間窗。允許 `chat_status` 不等於允許 `chat_read` 或 `chat_reply`；
客戶端可能逐項詢問，應由正常核准 UI 處理。若核准提示超過 delivery lease 或
測試 expiry，保留 journal 與回執，走明確 recovery；不能因稍後核准而自動重送、
清除 attempt history 或延長過期測試。
