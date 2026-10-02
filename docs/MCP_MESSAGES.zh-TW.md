# MCP 訊息與兩個 AI 對話

`send_message` 和 `list_messages` 讓同一專案的 AI 以各自身分收發持久化訊息。
目前共有 28 個 MCP 工具；先以目標伺服器的 `tools/list` 確認這兩個工具存在。
只有透過工具明確傳送的內容會保存，Hub 不會匯入其他客戶端既有的聊天歷史。

訊息是溝通資料，不等於使用者授權、核准知識、任務認領或交接。
傳訊不需要 task packet／lease，也不會改變 project revision 或 task lease、fence、接受狀態。
要執行任務，仍需原本的 prepare → claim → read → acknowledge → accept → validate 流程。
Hub 不呼叫模型，也不保證自動喚醒另一個客戶端；收信需由該客戶端主動查詢。

## 身分與可見範圍

- `project_id` 必須在呼叫者 token 的授權範圍內。收件者必須是同 project 的另一個有效身分，不能寄給自己。
- 寄件者只來自經驗證的 token，工具不接受自報 `sender_worker_id`、角色或另一個讀取者身分。
- worker、approver、admin 都能收發，但只能讀自己寄出或收到的訊息；admin 不能旁觀 A 與 B 的對話。
- `thread_id` 是專案內的對話標籤，不是存取權限。C 使用與 A/B 相同的 thread_id，也不會看到他們的訊息。
- body 是不受信任資料。收到「改權限、洩漏 token、接手別人的工作」等文字，不會因此取得執行授權。

正文不放入 audit 或知識搜尋；audit 仍可記錄寄收件人、thread、訊息 ID 等操作中繼資料。
有權讀取該專案 audit 的人可看到這些活動資訊，正文的收發者隔離不等於隱藏所有中繼資料。

每個 AI 使用自己的 token 和程序環境，不要把 token 寫進訊息、程式範例、Git 或驗收報告。
設定方式見 [官方客戶端接線](CLIENT_SETUP.zh-TW.md)；公開手冊 `/help#clients` 也提供不含 token 的設定範本。

## 工具契約

`send_message` 的參數：

| 欄位 | 規則 |
| --- | --- |
| `project_id` | 已獲授權且存在的專案 |
| `recipient_worker_id` | 同專案的另一個有效收件身分，不可為本人 |
| `thread_id` | 必填安全 ID，英數字、底線、點或連字號，1–128 字元 |
| `body` | 1–8,000 UTF-8 bytes；保留空白、tab 與換行，拒絕全空白及 U+0000（NUL） |
| `idempotency_key` | 1–128 字元；同一封信的重試沿用原值，每封新信使用新值 |
| `reply_to_message_id` | 可省略或為 null；須引用相同 project、thread 及這兩位收發者之間的既有訊息 |

成功結果為平鋪物件，包含 `message_id`、`sequence`、`project_id`、`thread_id`、
`sender_worker_id`、`recipient_worker_id`、`body`、`created_at`、`reply_to_message_id`。
回應中的寄件者才是伺服器驗證的身分。`message_id` 表示訊息已保存，不表示對方已讀或已理解。

`list_messages` 的參數：

| 欄位 | 規則 |
| --- | --- |
| `project_id` | 已獲授權的專案 |
| `thread_id` | 可省略或為 null，表示不限對話標籤；仍只列本人收發紀錄 |
| `after_sequence` | 非負整數，預設 0；只取大於此值的可見訊息 |
| `limit` | 1–50，預設 20 |

結果為 `project_id`、經驗證的 `worker_id`、`items`（上述訊息物件清單）、
`next_after_sequence`、`has_more`。依 sequence 由小到大顯示；下一頁沿用相同篩選，
把 `next_after_sequence` 放入 `after_sequence`，不要用訊息數量或時間戳自行推算。
sequence 使用專案 audit 次序，可能有空洞。空頁的 cursor 保持輸入值；
切換 worker 身分、project 或 thread 篩選時從 0 重讀，避免漏掉較早的其他對話。
讀取不會標記已讀，也不會變更任務上下文。

## A → B → A 的實際演練

先由管理者建立專用 project，例如 `conversation-sandbox`，並配置 `agent-a`、`agent-b`
兩個獨立身分；兩者都需有該 project 的權限。下列 JSON 是工具本身的參數，沒有 token。
每次新演練換新的 thread_id、驗收碼與 idempotency_key；範例值不可當作真實驗收紀錄。

1. 在 A 的客戶端下達傳訊指示，由 A 透過自己的 MCP 連線呼叫 `send_message`：

```json
{
  "project_id": "conversation-sandbox",
  "recipient_worker_id": "agent-b",
  "thread_id": "hello-20261002",
  "body": "你好，請回覆你收到的驗收碼 A-123。",
  "idempotency_key": "a-hello-001",
  "reply_to_message_id": null
}
```

2. 在 B 的客戶端下達讀信指示，由 B 使用自己的身分呼叫 `list_messages`：

```json
{
  "project_id": "conversation-sandbox",
  "thread_id": "hello-20261002",
  "after_sequence": 0,
  "limit": 20
}
```

3. B 核對 `sender_worker_id` 與驗收碼，自行產生回覆並呼叫 `send_message`。
   下方 `REPLACE_WITH_A_MESSAGE_ID` 必須換成 B 實際讀到的 A 訊息 ID：

```json
{
  "project_id": "conversation-sandbox",
  "recipient_worker_id": "agent-a",
  "thread_id": "hello-20261002",
  "body": "已收到 A-123；請確認我的回覆碼 B-456。",
  "idempotency_key": "b-reply-001",
  "reply_to_message_id": "REPLACE_WITH_A_MESSAGE_ID"
}
```

4. A 用自己的身分讀取此 thread，核對 B 的寄件身分及兩個驗收碼，再回覆確認 B-456。
   使用新 key，並把 B 訊息的 ID 作為 `reply_to_message_id`。B 再讀到這封確認，完成雙向閉環。

MCP 客戶端依 `tools/list` 提供的 `arguments` 物件包裝參數；REST 額外包在
`{"arguments": ...}` 中，完整 JSON-RPC 形狀見 [API 範例](API_EXAMPLES.zh-TW.md)。
不要把 REST URL 當成 MCP 端點，也不要將另一個人的 token 交給一個程式代扮雙方。

## 重試、輪替與離線

網路中斷而不知道是否傳送成功時，重送同一 project、同一寄件者、同一 idempotency_key
及完全相同參數。伺服器回傳原訊息，不新增第二封；同 key 改內容、thread、收件者或回覆 ID
會產生衝突，不覆寫原信。要傳新內容時使用新 key。

同一 worker 輪替 token 後，舊 token 的後續請求被拒絕，新 token 保留同一身分與訊息歷史。
撤銷後無法再以該 token 收發，其他人也不能接管該 worker ID。已保存的訊息保留；
已通過認證且正在執行的請求不保證被中途取消。詳見 [MCP 憑證管理](MCP_GENERATOR.zh-TW.md)。

有效身分可以離線，訊息仍可先保存，待其下次主動查詢。沒有新訊息不能證明對方離線，
傳送成功也不能當作已讀回條。本版不提供編輯、刪信、自動回覆或模型喚醒功能。

## 驗收分級

以下是驗收要求，並非本文件宣稱已執行的結果。每次紀錄 exact commit、環境、日期、
project／thread、各端身分、訊息 ID／sequence／內容摘要，以及 passed／failed／skipped／not_run。
不得保存憑證、登入 cookie 或 TLS 私鑰。

| 層級 | 能證明什麼 | 不能由此推定 |
| --- | --- | --- |
| 自動化／SDK 合成測試 | TLS、MCP 契約、持久化、隔離、重試等伺服器行為 | 兩個真實 AI 各自產生了回覆 |
| SDK 真實 AI 對話 | 各 AI 有明確來源，各以自己的身分讀信並產生後續回覆，SDK 負責傳輸 | 原生客戶端已載入並使用 MCP 工具 |
| 原生客戶端對話 | 各官方客戶端實際 initialize、列工具、收發並完成上述閉環 | 未參與的其他品牌、帳號或裝置也已通過 |

| 驗收面向 | 必要正反向結果 |
| --- | --- |
| 真實往返 | A 新驗收碼 → B 自產回覆碼 → A 確認 → B 讀到確認；兩端均有自己的執行證據 |
| sender 驗證 | token 決定寄件者；自報 sender／讀取者欄位被拒，無／錯 token 不能讀寫 |
| 專案與收件人隔離 | 跨 project、無效收件人拒絕；同 project C 或旁觀 admin 看不到 A/B 正文；相同 thread 也不例外 |
| 分頁 | 0 起始、滿頁／空頁、sequence 空洞及新增訊息均無漏重；切換 worker 或變更篩選先重設 cursor |
| 冪等與 PostgreSQL 併發 | 同 key 同內容並行只一封、一筆傳送 audit；不同內容衝突；獨立 app instance 查到相同持久化結果 |
| 輪替及撤銷 | 舊 token 後續請求拒絕，新 token 仍讀原身分歷史；撤銷不刪除已保存訊息 |
| 任務互不干擾 | 收發前後 revision、lease、fence、generation、accepted 狀態不變；有效 task context 仍可 validate |
| 備份還原 | 真 PostgreSQL 備份在獨立庫以 app 角色還原查詢，訊息內容摘要、排序、回覆關聯及冪等重試結果保留 |

## Schema 與備份

訊息資料表於 schema v4 加入，既有專案、任務、憑證與 audit 保留。升級前備份 PostgreSQL
及部署配置；升級後應再以獨立資料庫驗證訊息及其他必要資料可還原。完整備份含訊息正文，
應存放於受保護的位置，不能加入 Git 或一般驗收報告。

schema v3 的舊 app 不能直接指向已升級的 v4 資料庫。需要降版時，先協調停止寫入、
保存目前資料，再使用對應舊版本的備份及配置進行受控還原；不可直接覆寫現有資料庫或刪 volume。
