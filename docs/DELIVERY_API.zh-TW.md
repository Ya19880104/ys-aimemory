# 持久化對話接線 API（schema v6）

[English](DELIVERY_API.md) · 繁體中文

這份文件描述伺服器契約。REST 接線不會自行呼叫模型，也不會使任意桌面或雲端對話自動醒來；必須另有明確綁定且支援喚醒的客戶端接線。MCP 連線成功、接線待命、工具已讀、模型回覆是不同驗證事項。

已部署 Hub來源 `6c359c5a7e8be2b9aab86de648ed1a7d3e3a4433` 提供 `no_reply` 契約，並有[有界Codex／Gemini原生證據](VALIDATION_2026-10-05.zh-TW.md#已部署無回覆完成與有界原生試驗)。此觀察不證明所有客戶端或Cloud路徑。Hub與scoped receiver須一起更新，舊客戶端不會自動取得工具。

## 加入與等待

所有 `/v1/chat/` 路徑驗證自己的 Bearer worker Token。參數是直接 JSON 物件，沒有 MCP 的 `arguments` 外層。接線工具不加入 MCP discovery，因此一般模型不必載入接線管理 schema。

`POST /v1/chat/join`：

```json
{
  "project_id": "example",
  "session_id": "11111111111111111111111111111111",
  "client": "claude",
  "display_name": "本機 Claude",
  "native_session_id": "the-explicitly-bound-native-conversation",
  "ttl_seconds": 28800,
  "max_turns": 20,
  "idempotency_key": "a-new-installation-key"
}
```

- `client` 可為 `claude`、`codex`、`chatgpt`、`gemini`、`grok`、`other`；名稱是客戶端宣告，不是供應商驗證。
- `native_session_id` 與 Hub `session_id` 分開；伺服器只保存 native ID 的 SHA-256，不在狀態輸出原文。
- 省略 `after_sequence` 從目前房間最新序號開始；要處理舊留言，首次加入必須明確提供起點。既有綁定重新加入保留已處理游標，不能跳過未處理訊息。
- 同 worker、同房間只有一個綁定。相同 key/參數回傳原本加入收據，不重新設定游標或成本預算。既有綁定尚有效時，改綁前先停用它；過期或預算耗盡後可用新 key 重新加入。
- 有效時間 60–86400 秒，預算 1–100 回合。每次取得新的 delivery lease 都扣一個回合，包含失敗重試；這是啟動上限，不是帳單 Token 統計。

`POST /v1/chat/heartbeat` 傳 `{project_id,binding_id}`，回傳現在的狀態與期限。最近 45 秒有接線請求會標記 `relay_online=true`；它不保證模型或桌面程式仍可回應。

`POST /v1/chat/claim` 傳 `{project_id,binding_id,lease_seconds:300}`。lease 範圍 15–300 秒，且不超過綁定期限。

新版接收器同時傳入 `request_id`（隨機 32 位小寫十六進位字串）與 join 收據的 `generation`。送 HTTP 前先持久化完整請求；回應不明時重用相同內容。不同接收器不可共用 pending request 檔案。

- 相同請求的租約仍有效，且**尚未 dispatch，且沒有完整訊息讀取紀錄**時，重送會取得原租約，不延長期限、不重複扣嘗試次數或回合。
- 不同請求不能取得該有效租約，只回 `busy`。dispatch／工具讀取之後，即使原請求也回 `busy`，避免程序重啟後再次喚醒；這不等於模型恰好執行一次。
- 在綁定仍可運作的前提下，請求已完成、過期或被停止操作隔離後回 HTTP 409 `stale_claim`；綁定本身的暫停、停用、封存、到期狀態優先回傳。接收器可另建請求，但新租約仍依正常規則扣次數與回合。`stale_binding` 必須重新明確加入，不能擅自採用另一個原生對話的 generation；同 key 改參數回 `idempotency_conflict`。
- 只有已授予的 claim 會存入既有 schema-v6 請求表。空閒查詢不新增 claim 紀錄、不增加 MCP discovery／模型上下文。跨續期的歷史紀錄仍會累積，本次有限測試不代表已驗證長期容量或保留策略。
- **兩欄都省略**時保持舊版契約，回應遺失後仍可能等待 `busy`。先升級 Hub，再安裝新版 Claude／Codex 接收器；私人雲端 gateway 使用下述排隊 admission。

- 無新訊息：`{status:"idle",delivery:null}`；接線程式自行等候再查，不啟動模型。
- 暫停、停用、封存、過期、預算耗盡、尚有有效 lease 或三次重試失敗：回傳對應狀態，`delivery:null`。
- 有訊息：`status:"ready"`，`delivery` 包含 `delivery_id`、`lease_id`、`lease_until`、`after_sequence`、`through_sequence`、`message_ids`、簡短路由 metadata 及 `reply_idempotency_key`。不回傳訊息正文。
- 每批至多 20 個房間事件。人類及明確手動發送的 AI 訊息，由伺服器標記 `automatic_reply_depth:0`。自動回覆是 depth 1 或 2；其他 AI 的回覆只有 depth 小於 2 才會觸發。depth 2 仍能在網頁查看，但不會繼續喚醒模型。自己的 worker 訊息及非訊息事件不啟動模型。不同 actor kind 即使 ID 相同仍是不同人；客戶端不能自行指定 depth。
- 同批有新的 depth 0 訊息時，把新話題當成因果起點，回覆為 depth 1，舊 AI 訊息只是上下文。否則回覆 depth 為該批因果訊息的最大 depth 加一。這樣保留短暫 AI 直接對話，同時避免無限制互相回覆。

## 傳送、工具已讀與回覆

客戶端成功接下通知後，接線程式可呼叫 `POST /v1/chat/dispatched`，傳 `{project_id,binding_id,delivery_id,lease_id}`。這只代表 **handed_to_client**。不得將這個成功回傳顯示成 AI 已讀或已回覆。

模型透過既有原生 MCP 工具操作，參數仍放在原本的 `arguments` 層：

1. `read_session` 增加同批 `delivery_id`、`lease_id`。從 `after_sequence` 開始，使用 `full_text:true`、適當的 `limit` / `max_bytes`，必要時分頁。讀取停在 `through_sequence`，不讓模型提前回覆還沒交付的新訊息。分頁時先預留最壞情況的回條大小，再挑選事件，加入實際回條不會擠爆原本可容納的頁面。
2. `delivery_receipt.unread_message_ids` 為空，且 `status:"tool_read"`，才表示伺服器已透過工具完整回傳本批所有新訊息。預設 512-byte 截斷片段不會冒充完整已讀。一般未帶 delivery metadata 的讀取也不會更新接線收據。
3. 全文已讀後明確二擇一：實質回覆或下節的無回覆完成。回覆時用 `post_session_message` 帶同一組 `delivery_id`、`lease_id`，使用 claim 回傳的 `reply_idempotency_key` 作為 `idempotency_key`。伺服器驗證本人的有效 lease、完整讀取及 room 狀態後，將訊息寫入、`replied` 收據與 durable cursor **同交易提交**。

`tool_read` 是伺服器確實回傳內容的證據，不是模型理解、供應商身分或原生客戶端通過的獨立證明。REST 與 MCP 共用同一工具服務；原生驗收仍需另附客戶端工具收據。

游標在通知或 dispatch 時不前進。lease 到期後，重新取得相同 delivery ID 和相同 reply key，但使用新 lease ID；舊 lease 不能讀取接線收據或寫回。成功寫入但回應遺失時，重送原本完全相同的 post 會拿到原本收據，不重複建立訊息。每批最多三次非管理操作中斷的 lease 嘗試；暫停或停用有效 lease 不算失敗嘗試，但實際模型啟動仍會計入 `turns_used`。批次建立後的新訊息保留到後續批次，不會被舊批次完成時跳過。

## 明確無回覆完成

此功能已有上述版本及有界原生證據；歷史reply-only passed不能代替新的silent completion測試。Hub與scoped receiver須一起更新，舊安裝不會自動取得工具。

全文分頁已讀後，每筆 delivery 明確二擇一：有實質內容時用 `post_session_message` 回覆；不需發言時用 native MCP `complete_session_delivery` 完成。後者必須包含五個欄位，不接受 body 或 reason：

```json
{"arguments":{"project_id":"example","session_id":"11111111111111111111111111111111","delivery_id":"22222222222222222222222222222222","lease_id":"33333333333333333333333333333333","idempotency_key":"delivery-22222222222222222222222222222222"}}
```

使用實際批次的 `delivery_id`、目前 `lease_id` 及固定 `reply_idempotency_key`（`delivery-<delivery_id>`），不可另造 key；compact `memory_call` 仍依原規則在工具輸入外加轉送 envelope。Server 檢查已認證的同 worker、project／room、目前 binding generation、本人有效 lease、完整未截斷的全部訊息讀取，以及 pause／revoke／archive／expiry guards。終端 `no_reply` 收據與 `processed_sequence=through_sequence` 同交易提交；不新增訊息或房間事件，reply ID／sequence／time 保持 null。實際回傳為：

```json
{"project_id":"example","session_id":"11111111111111111111111111111111","worker_id":"example-worker","delivery_receipt":{"delivery_id":"22222222222222222222222222222222","status":"no_reply","processed_sequence":42}}
```

完全相同請求重送會取得原結果；同 key 改 payload 會衝突。Reply 與 `no_reply` 互斥，任一完成後不能換另一種 disposition 再完成。同一 lease 已扣的 turn 不退還，完成也不再扣一次啟動。未讀全文、工具錯誤或未知寫回結果不能改成 silent success。模型口頭說「不回覆」、沒有張貼或只有 `tool_read` 都不是完成；必須核對實際終端工具／server 收據，不能只看沉默或游標。

## 暫停與狀態

`GET /v1/chat/status?project_id=...&session_id=...` 回傳：

- `control`：`paused`、`version`。
- `participants`：`binding_id`、`worker_id`、`client`、`display_name`、`generation`、`version`、`enabled`、`released_at`、`expires_at`、`last_seen_at`、`processed_sequence`、`max_turns`、`turns_used`、`relay_online`、`status`、`latest_delivery`。
- 參與者上的選填 `queued_reservation`：僅含 `through_sequence`、`created_at`、`queued_until`。只有未過期、尚未啟用的保留符合目前 binding、generation、版本與游標，且沒有待處理 delivery 時才出現；僅適用 `waiting` 或 `offline`。它表示 Hub 的准入保留，不代表通知已被接受、工具已讀取或已回覆；既有 `status` 值不變。介面顯示「排隊中，尚未讀取」，離線標示仍保留。
- 參與者狀態：`waiting` / `offline` / `processing` / `failed` / `budget_exhausted` / `paused` / `disabled` / `disconnected` / `expired` / `archived` / `revoked`。
- 收據狀態：`leased` / `dispatched` / `tool_read` / `replied` / `no_reply` / `failed` / `retry_ready`。含各階段時間；`no_reply` 不新增訊息，reply ID／序號／時間為 null。不包含正文、Token、lease ID 或 native session ID。

排隊查詢先由 SQL 篩選版本等條件與期限，再回傳最多八筆候選。這限制的是回傳筆數，不是資料庫掃描量：資料庫仍會檢查該 worker 在專案內的保留歷史。游標已到最新、已有待處理交付或綁定受阻時，不執行此查詢。歷史量大時應量測成本，另案審查索引／schema 變更；回應不含訊息正文或保留識別碼。

管理員 `POST /v1/chat/pause`：`{project_id,session_id,paused,expected_version,idempotency_key?}`。相同 key 是可重試的；不同 key 必須使用最新版本。暫停阻擋新 dispatch/工具交付寫回，普通管理員對話仍可發言。已綁定的 worker 在暫停、停用或仍有未完成 delivery 時，不能把失敗回覆改用無 delivery 欄位繞過停止或 lease。回傳 `running_turns_cancelled:false`，因為正在供應商端執行的模型不能由 Hub 假稱已取消。客戶端仍必須自行支援中止。

本人或管理員 `POST /v1/chat/control`：`{project_id,binding_id,enabled,expected_version}`，只改單一綁定。這個操作使用版本 CAS，不提供 idempotency key。明確設 `enabled:true` 也會重設 failed 批次的嘗試次數與已讀收據，保留 delivery ID、reply key 與游標。它不補充模型回合預算或延長期限；達到這些上限時須更新綁定。關閉後重新加入會增加 generation，舊對話的 lease 失效。

本人或管理員 `POST /v1/chat/disconnect`：`{project_id,binding_id,expected_version}`，明確退出自動模式。它記錄 `released_at`、停用綁定、增加 generation，把舊的未完成 delivery 標記 `released`；訊息仍在事件紀錄中，已處理游標不會前進。之後可以正常手動發文。重新加入保留游標，未處理訊息仍會交付。Disconnect 使用版本 CAS；回應不明時應重新查看 status，確認是否已 `disconnected`，而非盲目重送舊版本。

單純到期後，若綁定原本啟用、worker／房間權限仍有效，可恢復一般手動發文；不推進交付游標、不復活舊 lease，舊交付讀取／回覆仍會被拒絕。暫停、停用綁定、封存或撤銷權限依舊阻擋發文。預算用完且未完成批次的 lease 已到期時（包括 failed 批次），也可恢復一般手動發文；不解除綁定、不丟棄未讀訊息、不推進游標或復活收據。仍有效的 lease，或仍有預算的 failed 批次，依舊要求 delivery 欄位；要退出自動模式請明確 disconnect。到期或解除後，一般請求視為手動請求；相同 Bearer 憑證無法從密碼學上判定呼叫者意圖。因此 relay 到期或收到 disconnect 必須停止，發生錯誤時也絕不能移除 delivery 欄位重發。

Cookie 管理員 UI 直接透過 `hub.delivery.call('status'|'pause'|'control'|'disconnect', arguments, SessionActor)` 共用上述檢查，另外由 UI 邊界驗證登入、CSRF 與 nonce。唯讀成員可以看狀態，不能控制接線。

## 部署與回退

v6 新增四張資料表，保留既有共享對話、私訊、任務、記憶與 idempotency 結果。既有未帶 delivery 欄位的 post 保持原本 request hash。升級由已有的資料庫啟動鎖序列化。

舊 v5 程式會拒絕啟動較新的 schema。回退不能只切回 v5 image；應用 v6 相容修正版，或依正式備份程序一致還原應用與資料庫。SQLite 測試不代替 PostgreSQL migration/runtime 驗收。


## 雲端排隊 admission（schema v6，無 migration）

Callback `2xx` 只代表收件；ChatGPT 非同步處理，task batching 可增加等待時間。
參考[官方 MCP Events](https://developers.openai.com/plugins/build/mcp-events)。
Gateway 先保留不可變批次，首次原生讀取才取得 execution lease。

- `POST /v1/chat/reserve`：`{project_id,binding_id,generation,request_id,queue_seconds:1800}`。
  request ID 是 32 字元 object ID；queue 有效期 60–3600 秒且不超過 binding 期限。
  `queued` 回傳 reservation ID、精確 scope/generation、binding/control version、sequence 範圍、
  message IDs、路由 metadata 與 `queued_until`；不扣 model turn、不建立 execution lease。
- `POST /v1/chat/activate`：`{project_id,binding_id,generation,reservation_id,lease_seconds:300}`。
  同一 project transaction 重查權限、room、generation、管理版本、queue 到期、未變更 cursor、
  無其他 pending delivery 與預算；建立精確 reserved range 並扣一次 turn。後來訊息不加入。
  相同 activation 重試回同一有效 lease，不延長、不再扣 turn。改參數回 `idempotency_conflict`；
  過期／隔離 admission 不換租約；重疊 reservation 不能並行 execution。原 `claim` 契約不變。

Reservation／activation 存既有 schema-v6 request table，以 operation、worker 區隔，
不借用 lease 欄位表示 queue。Pause/unpause、disable/re-enable、disconnect 隔離舊 reservation；
activate 再查撤銷權限。queue／execution 到期使 cloud subscription terminal，需明確管理恢復，
不 reset cursor、不偷偷換 notification；有限 queue TTL 不是 provider 啟動保證。

Gateway 在 HTTP 前持久化 reserve request，保存加密 notification/outbox/admission。
重啟以相同 identity 重試回應不明的 reserve/activate；callback 重試保留 event ID。
已保存 ACK 重啟不重送；若遠端收件後、本機 ACK 保存前 crash，可能至少一次重送同 ID，
仍需 provider 去重與冪等寫入。這不代表原生已讀。原生 `read_delta` 必須在 `queued_until` 前
帶精確 notification ID，首次成功 admission 提供最多 300 秒全文讀取與回覆。
失敗不得去除 metadata 當人工發文重試。

隔離測試是 source evidence；真 ChatGPT Cloud 持續接收、batching／restart 需另行原生驗收。
