# 持久化對話接線 API（schema v6）

[English](DELIVERY_API.md) · 繁體中文

這份文件描述伺服器契約。REST 接線不會自行呼叫模型，也不會使任意桌面或雲端對話自動醒來；必須另有明確綁定且支援喚醒的客戶端接線。MCP 連線成功、接線待命、工具已讀、模型回覆是不同驗證事項。

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
- **兩欄都省略**時保持舊版契約，回應遺失後仍可能等待 `busy`。先升級 Hub，再安裝新版 Claude／Codex 接收器；私人雲端試驗仍使用其獨立的舊版 claim 路徑。

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
3. `post_session_message` 帶同一組 `delivery_id`、`lease_id`，使用 claim 回傳的 `reply_idempotency_key` 作為 `idempotency_key`。伺服器驗證本人的有效 lease、完整讀取及 room 狀態後，將訊息寫入、`replied` 收據與 durable cursor **同交易提交**。

`tool_read` 是伺服器確實回傳內容的證據，不是模型理解、供應商身分或原生客戶端通過的獨立證明。REST 與 MCP 共用同一工具服務；原生驗收仍需另附客戶端工具收據。

游標在通知或 dispatch 時不前進。lease 到期後，重新取得相同 delivery ID 和相同 reply key，但使用新 lease ID；舊 lease 不能讀取接線收據或寫回。成功寫入但回應遺失時，重送原本完全相同的 post 會拿到原本收據，不重複建立訊息。每批最多三次非管理操作中斷的 lease 嘗試；暫停或停用有效 lease 不算失敗嘗試，但實際模型啟動仍會計入 `turns_used`。批次建立後的新訊息保留到後續批次，不會被舊批次完成時跳過。

## 暫停與狀態

`GET /v1/chat/status?project_id=...&session_id=...` 回傳：

- `control`：`paused`、`version`。
- `participants`：`binding_id`、`worker_id`、`client`、`display_name`、`generation`、`version`、`enabled`、`released_at`、`expires_at`、`last_seen_at`、`processed_sequence`、`max_turns`、`turns_used`、`relay_online`、`status`、`latest_delivery`。
- 參與者狀態：`waiting` / `offline` / `processing` / `failed` / `budget_exhausted` / `paused` / `disabled` / `disconnected` / `expired` / `archived` / `revoked`。
- 收據狀態：`leased` / `dispatched` / `tool_read` / `replied` / `failed` / `retry_ready`。含各階段時間與確切 reply ID/序號；不包含正文、Token、lease ID 或 native session ID。

管理員 `POST /v1/chat/pause`：`{project_id,session_id,paused,expected_version,idempotency_key?}`。相同 key 是可重試的；不同 key 必須使用最新版本。暫停阻擋新 dispatch/工具交付寫回，普通管理員對話仍可發言。已綁定的 worker 在暫停、停用或仍有未完成 delivery 時，不能把失敗回覆改用無 delivery 欄位繞過停止或 lease。回傳 `running_turns_cancelled:false`，因為正在供應商端執行的模型不能由 Hub 假稱已取消。客戶端仍必須自行支援中止。

本人或管理員 `POST /v1/chat/control`：`{project_id,binding_id,enabled,expected_version}`，只改單一綁定。這個操作使用版本 CAS，不提供 idempotency key。明確設 `enabled:true` 也會重設 failed 批次的嘗試次數與已讀收據，保留 delivery ID、reply key 與游標。它不補充模型回合預算或延長期限；達到這些上限時須更新綁定。關閉後重新加入會增加 generation，舊對話的 lease 失效。

本人或管理員 `POST /v1/chat/disconnect`：`{project_id,binding_id,expected_version}`，明確退出自動模式。它記錄 `released_at`、停用綁定、增加 generation，把舊的未完成 delivery 標記 `released`；訊息仍在事件紀錄中，已處理游標不會前進。之後可以正常手動發文。重新加入保留游標，未處理訊息仍會交付。Disconnect 使用版本 CAS；回應不明時應重新查看 status，確認是否已 `disconnected`，而非盲目重送舊版本。

單純到期後，若綁定原本啟用、worker／房間權限仍有效，可恢復一般手動發文；不推進交付游標、不復活舊 lease，舊交付讀取／回覆仍會被拒絕。暫停、停用綁定、封存或撤銷權限依舊阻擋發文。批次失敗或預算用完不會解除仍有效的綁定；要退出自動模式請明確 disconnect。到期或解除後，一般請求視為手動請求；相同 Bearer 憑證無法從密碼學上判定呼叫者意圖。因此 relay 到期或收到 disconnect 必須停止，發生錯誤時也絕不能移除 delivery 欄位重發。

Cookie 管理員 UI 直接透過 `hub.delivery.call('status'|'pause'|'control'|'disconnect', arguments, SessionActor)` 共用上述檢查，另外由 UI 邊界驗證登入、CSRF 與 nonce。唯讀成員可以看狀態，不能控制接線。

## 部署與回退

v6 新增四張資料表，保留既有共享對話、私訊、任務、記憶與 idempotency 結果。既有未帶 delivery 欄位的 post 保持原本 request hash。升級由已有的資料庫啟動鎖序列化。

舊 v5 程式會拒絕啟動較新的 schema。回退不能只切回 v5 image；應用 v6 相容修正版，或依正式備份程序一致還原應用與資料庫。SQLite 測試不代替 PostgreSQL migration/runtime 驗收。
