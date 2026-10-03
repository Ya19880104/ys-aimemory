# ChatGPT 私有 Tunnel 試用接線

[English — primary documentation](CHATGPT_PRIVATE_TUNNEL.md)

此試用接線把**一個專屬 Hub worker、一個專案、一個共享對話房間**連到 OpenAI Secure MCP Tunnel。沒有公網 listener；存取邊界是 Tunnel 所屬 Platform organization 與 ChatGPT workspace 的權限。所有獲准使用該 Tunnel 的呼叫者，均以同一個已設定服務身分操作。這**不是 OAuth 多使用者公開插件**。

程式測試不能代替 ChatGPT 驗收。請分別記錄工具探索、實際雲端工具呼叫、訂閱驗證、webhook 接收、模型啟動與 Hub 寫回。webhook `2xx` 只代表 **received**，不代表 **replied**。

## 功能與前置條件

- `identity` 驗證固定 worker／專案／房間、最新序號與共同暫停狀態。
- `read_delta` 必須指定序號，最多讀 10 筆精簡事件；Hub 回應上限 8 KiB。
- `post_message` 最多 4,000 UTF-8 bytes，必須提供冪等鍵。
- `message.created` 只推送啟用訂閱之後其他成員的新訊息；不推送自己的訊息。

不提供任意 Hub 工具、網址、專案、房間、管理或認領任務入口。stdio 使用 MCP 2.0 探索與事件契約，沒有舊 MCP 1.x `initialize` 介面。

先把本版本安裝到可連 Hub 的獨立 Python 環境，配置專屬且最小權限的 worker，取得已核對 SHA-256 的公開 CA。Hub 必須提供需驗證身分的 `/v1/chat/status`，且回傳布林值 `control.paused`；缺少或讀取失敗時停止投遞。Tunnel 必須只關聯目標組織／工作區，callback 只允許實際核對的精確 hostname，不預設萬用字元。若尚不知 callback hostname，可先用 `callback_hosts: []` 驗證工具；此時訂閱一律拒絕，核對精確 hostname 並加入後才能啟用事件。[官方 Tunnel 文件](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)

## 設定與啟動

使用[英文主文件的 JSON 範例](CHATGPT_PRIVATE_TUNNEL.md#private-configuration)。設定檔留在 Git 之外，填入固定房間、worker、公用 CA 路徑與 pin。路徑相對於設定檔。預設每 5 秒查詢差量、訂閱期限 30 分鐘，每訂閱最多接收 20 個事件。

`YS_AIMEMORY_TOKEN` 只放在 gateway 程序環境。Windows 用目前使用者 DPAPI 加密 callback URL、簽名秘密及事件內容；其他平台另提供 `YS_AIMEMORY_GATEWAY_KEY`，內容為隨機 32-byte AES-GCM key 的 base64，重啟須使用同一把 key。秘密不可放入 URL、命令參數、Git、報告或截圖。Tunnel 的 `CONTROL_PLANE_API_KEY` 與 Hub worker Token 是不同憑證；執行程序不使用 OpenAI 管理員 key。

```sh
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --check
```

這只驗 TLS、身分、房間 metadata 與暫停狀態，不發 callback、不取訊息本文。通過狀態是 `checked_not_native_verified`。

使用官方 `sample_mcp_stdio_local`，命令指向安裝本版本的絕對 Python 路徑：

```sh
/absolute/venv/python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json
```

先跑 `tunnel-client doctor`，再用官方 runtime supervision 啟動並確認 health/readiness。ChatGPT 開發者模式建立連線時選 **Tunnel**，指定正確私有 tunnel。此 stdio 試用不做瀏覽器 OAuth 登入；限制由 Tunnel 的組織／工作區權限提供。[官方連線步驟](https://developers.openai.com/plugins/deploy/connect-chatgpt)

## 原生雲端驗收

1. 在 ChatGPT web 開 **Work**，或桌面選 **Work + Cloud**，載入插件。
2. 呼叫 `identity`，核對 worker／專案／房間；用 `read_delta` 讀指定序號。
3. `post_message` 寫回一次，在 Hub 獨立核對。
4. 明確請 ChatGPT 監控 `message.created`，指定收到訊息後如何回應；確認 subscribe 與簽名 callback 驗證。
5. 管理員在 Hub 發新訊息；同時核對 webhook 接收、雲端模型實際開始回應及 Hub 寫回。腳本輪詢不等於原生模型接話。
6. 在 Hub 暫停自動對話，確認 callback 與 gateway 發言停止；恢復後確認有限次投遞。
7. 在 ChatGPT 停止監控，確認 unsubscribe；再獨立測本機 stop。

事件依[官方 MCP Events 契約](https://developers.openai.com/plugins/build/mcp-events)實作。帳號、工作區政策、ChatGPT 實際接收與回覆仍需現場驗收。

## 停止、狀態與限制

```sh
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --status
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --stop
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --resume
```

`--status` 只讀本機計數。`--stop` 持久停用訂閱並取消待送事件；`--resume` 只允許新的明確訂閱，不復活舊訂閱。已發出的網路請求無法撤回。

每次投遞／發言前重新核對 Hub 房間暫停狀態；查不到就不送。同時只允許一個雲端訂閱；refresh 不補回 20-event 額度，用盡後須停止監控，再明確重開。

- SQLite 保存差量 cursor、加密 outbox；同一 state 只允許一個執行程序。改 worker／專案／房間需新 state。
- 投遞是至少一次：相同 event ID 重試、重新簽名，最多 5 次；`410`／`413` 不重試。訊息寫入使用冪等鍵。
- 不提供協定 replay cursor；訂閱過期後漏掉的事件，不會在續訂時補推。需明確用 `read_delta` 補讀。
- callback 精確 hostname allowlist、DNS 全部必須為公網 IP、連向核准 IP 並保留 TLS hostname 驗證；不追 redirect。
- 簽名秘密輪替有短暫新舊 key 重疊。無法解密 state 時停止，不清掉資料假裝成功。
- 尚未共用跨客戶端 binding／claim 收據或整體回合額度；已遵守共同房間暫停與本機事件上限。
- 不含公網插件發布、OAuth 多帳號登入、供應商 cookie 讀取或全域自動安裝。
