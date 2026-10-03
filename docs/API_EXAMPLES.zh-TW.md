# API 契約與可執行範例

[English](API_EXAMPLES.md) | [繁體中文](API_EXAMPLES.zh-TW.md)

以程式碼 `memory_hub/models.py` 的工具模型與 MCP `tools/list` 為最終欄位依據。本版關閉 OpenAPI 公開路由。REST 與 MCP 共用 Hub 邏輯；REST 不是 MCP transport，不能將 `/v1/tools` 直接填成 MCP URL。

## REST

`POST /v1/tools/{tool_name}`，Bearer 驗證，JSON body：

```json
{"arguments":{"project_id":"sandbox"}}
```

管理者先 `create_project` → `register_source` → `create_task`。task 的 source_ids、goal、allowed_paths、acceptance_criteria 在建立時確定；本版沒有任務定義編輯工具。需求範圍改變時建立新 task，不偷偷沿用舊範圍。

工作流程：`prepare_task` → `claim_task` → 每份 `read_source` → `acknowledge_context` → `accept_handoff` → `validate_task_context` → checkpoint／proposal／handoff／complete。

- prepare：project_id、task_id、workspace、branch、commit；source 清單由 task 決定
- claim：project_id、task_id、lease_seconds（30–3600，預設 300）
- packet 操作：project_id、packet_id；read_source 加 source_id
- gated 操作：project_id、packet_id、fence
- checkpoint／complete：gated 欄位 + summary、至少一個 evidence
- handoff：checkpoint 欄位 + to_worker、changed_artifacts（字串清單，可空）、result_commit（字串）、test_results（至少一項 `{command,status,details}`，status 為 passed/failed/not_run）、blockers（字串清單，可空）、next_steps（非空字串清單）
- proposal：gated 欄位 + text、evidence
- approval：project_id、decision_id、expected_revision；僅 approver/admin
- renew：gated 欄位 + lease_seconds
- search：project_id、query、limit、offset；全文索引或明確字面回退，不是語意搜尋
- get_worker_inbox：project_id；身分由 bearer 決定，返回 worker_id、context_revision、pending_handoffs、owned_tasks、available_tasks
- send_message：project_id、recipient_worker_id、thread_id、body、idempotency_key，及可為 null 的 reply_to_message_id；寄件者由 bearer 決定
- list_messages：project_id、可為 null 的 thread_id、after_sequence（預設 0）、limit（預設 20，1–50）；僅本人收發紀錄
- audit：project_id；目前最多返回近期 200 筆，不是完整匯出介面

Evidence 必須是當前 packet.required_sources 中的 `{source_id, sha256}`；不能引用未列入該 task 的任意 source。URI 和 commit 為登錄者提供的追溯欄位，Hub 不抓遠端或驗證 Git。

## MCP 工具參數包裝

此版 FastMCP 的每個工具 inputSchema 有一個名為 `arguments` 的物件參數。因此標準 `tools/call` 的外層 `params.arguments` 內還有工具的 `arguments`：

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_worker_inbox","arguments":{"arguments":{"project_id":"sandbox"}}}}
```

由官方客戶端依 tools/list schema 建構，不以 REST 範例猜測 MCP 包裝。initialize／initialized 與協定標頭由 MCP 客戶端處理。

## MCP 訊息

工具集隨版本更新，以目標伺服器 tools/list 核對。以下是 `send_message` 的 REST body；目標 project 與收件人必須已存在且獲授權，每次新演練換 thread／key：

```json
{"arguments":{"project_id":"conversation-sandbox","recipient_worker_id":"agent-b","thread_id":"hello-20261002","body":"你好，請回覆驗收碼 A-123。","idempotency_key":"a-hello-001","reply_to_message_id":null}}
```

同一傳送透過 MCP 的 `tools/call` 形狀如下，Authorization 由客戶端秘密設定提供：

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"send_message","arguments":{"arguments":{"project_id":"conversation-sandbox","recipient_worker_id":"agent-b","thread_id":"hello-20261002","body":"你好，請回覆驗收碼 A-123。","idempotency_key":"a-hello-001","reply_to_message_id":null}}}}
```

成功結果為平鋪的 `message_id`、`sequence`、`project_id`、`thread_id`、`sender_worker_id`、`recipient_worker_id`、`body`、`created_at`、`reply_to_message_id`。回覆時使用新 key，將讀到的原訊息 ID 放入 `reply_to_message_id`。

`list_messages` 的 REST body：

```json
{"arguments":{"project_id":"conversation-sandbox","thread_id":"hello-20261002","after_sequence":0,"limit":20}}
```

結果包含 `project_id`、經驗證的 `worker_id`、`items`（相同訊息欄位）、`next_after_sequence`、`has_more`。下一頁使用回傳 cursor；空頁維持輸入 cursor。sequence 使用專案 audit 次序，可能有空洞。切換 worker 身分或變更 project／thread 篩選時從 0 開始，不能拿較窄篩選的 cursor 跳過其他對話。

body 保留空白、tab 與換行，拒絕 U+0000（NUL）、全空白或超過 8,000 UTF-8 bytes；thread_id 為最多 128 字元的安全 ID；idempotency_key 最多 128 字元。同一 project／寄件者／key 的相同請求回傳原結果，改參數則衝突，不覆寫原信。收件者不可為本人；回覆 ID 須屬於相同 project／thread／這兩位收發者。三種角色都能使用訊息工具，但只能讀本人寄出或收到的正文；audit 仍可記錄寄收件人及訊息 ID 等中繼資料。訊息不改變 project revision／task lease。詳細隔離、重試與雙向演練見 [MCP 訊息](MCP_MESSAGES.zh-TW.md)。

## 安全的首次演練

`docs/demo_workflow.py` 只建立測試 project/task 並執行交接，不呼叫模型、不部署、不修改工作樹。它會改動目標 Hub，僅對專用 sandbox 執行。管理者與 worker 的憑證需先由人類在服務端配置，三者都需允許同一個測試 project。

透過當前 shell 的環境設定 `HUB_URL`、`HUB_PROJECT`、`HUB_ADMIN_TOKEN`、`HUB_WORKER_A_TOKEN`、`HUB_WORKER_B_TOKEN`、`HUB_WORKER_B_ID`。秘密請用受保護的互動輸入，不放入 shell 歷史或本文件。然後在 repository 根目錄執行：

```sh
python docs/demo_workflow.py
```

程式每次使用新的 task/source ID；不刪除紀錄。只接受 HTTPS 或 loopback HTTP。實際正式 client 對接仍需另外驗證 tools/list 與同等流程。

## 管理員處理離線／退役的接手者

`recover_task` 只允許 admin。正常 worker 不能搶走指定交接；當接手身分離線或被移除，管理員明確提出原因後，可重新指定已設定的 worker，或解除指定讓其他人重新認領。

參數：`project_id`、`task_id`、`expected_revision`、`expected_generation`、`expected_fence`、非空 `reason`，以及 `to_worker`（已驗證身分字串或 null）。從新的 `prepare_task` 結果取得專案 revision 與 task generation/fence；若其他操作已改變狀態，三個比較門檻會原子拒絕舊請求。

成功時 generation 和 fence 都增加，舊租約／接受紀錄撤銷，所有舊 task packet 失效；下一位必須重新 prepare/read/acknowledge/accept。歷史不刪除，原因與操作人寫入 recovery 及 audit。已完成的任務不支援重新開啟。網頁僅顯示紀錄，沒有繞過驗證的管理按鈕。

## 0.2 知識工具

批次匯入 `import_sources`、來源 CAS 更新、冪等 key 與大小限制見 [匯入文件](IMPORTING_MEMORY.zh-TW.md)。新增分頁 `list_sources`／`list_tasks`、`get_source_metadata`、`get_project_summary`、`index_health` 與管理員 `reindex_project`，欄位與搜尋回應見 [索引文件](KNOWLEDGE_INDEX.zh-TW.md)。所有工具以 `tools/list` 的 schema 為實際契約。
