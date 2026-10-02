# 網頁管理與帳號密碼

ys-aimemory 的交接是系統功能：任務、讀取確認、租約、fence、指定接手者與稽核都在 Hub 保存，不只是本專案開發時的約定。網頁讓人類檢視這些狀態；AI 使用同一個服務的 MCP／REST。

## 啟用

沒有預設帳號密碼，未設定時不啟用網頁登入。由管理者自行設定：

- `HUB_WEB_USERNAME`：網頁登入名稱
- `HUB_WEB_PASSWORD_HASH`：互動式執行 `python -m memory_hub.web_password` 產生；要求至少 12 字元密碼，不將明文放入環境檔
- `HUB_WEB_PROJECTS`：明確逗號分隔可操作 project IDs，不支援 `*`
- `HUB_WEB_ROLE=read_only`：預設唯讀；部署者明確設 `admin` 才能透過網頁寫入指定專案
- `HUB_WEB_COOKIE_SECURE=true`：預設開啟，LAN 必須 HTTPS；只有隔離本機 HTTP 測試可設 false
- `HUB_WEB_SESSION_TTL=3600`：300–28800 秒

雜湊包含 `$`，在 Compose `.env` 中使用單引號保留原字元，不要讓插值破壞雜湊。雜湊同樣是敏感設定，別加入 Git。本交付沒有建立任何可用的登入密碼。

HTTPS 開啟 `/ui`，未登入會導向 `/login`。可檢視：

1. 專案上下文版本、來源與記憶提案狀態
2. 任務範圍、租約、接受狀態、checkpoint 與待接手人
3. 配置的 MCP worker 身分和服務觀察到的活動
4. 近期稽核紀錄

唯讀角色不能寫入。admin 可建立專案／來源／任務、貼上 JSON 批次匯入、核准提案及明確恢復／重新分派任務。寫入仍經相同 Hub 服務的角色與 project 驗證，另有 CSRF、一次性操作 nonce、版本比較與 POST/Redirect/GET。網頁不提供任意 MCP 權限更改或供應商帳號設定。瀏覽器 session 不是 MCP token，不能拿去呼叫受 bearer 保護的 API。

搜尋、分頁、任務明細與 inbox 可從管理導覽開啟。輸入錯誤或狀態已變更時，頁面會顯示結果；請重新確認目前 revision，不盲目重送。匯入資料格式見 IMPORTING_MEMORY.zh-TW.md。

## 連線狀態的解讀

MCP 採 stateless HTTP，工具請求不代表永遠在線。畫面上的已配置身分、最近操作時間或活動紀錄只能代表各自的觀察，不可據此宣稱四個客戶端即時在線、工具已成功載入或模型正在推論。尚無活動不是故障證明。

## 登入安全與目前限制

本版仍是單一操作員帳號與明確專案清單，不是多使用者帳號管理、OAuth 或企業 SSO。0.2 把 session、登入 CSRF、操作 nonce、提示訊息及登入節流移入資料庫，經鎖定交易協調，可跨 application instance 使用，程序重啟不會自行抹除 session。資料庫只保存不透明 cookie 的 SHA-256 key；不存可直接登入的原始 cookie。

Session 固定到期，不因讀取延長；登入 CSRF 為 600 秒，操作 nonce 為 900 秒且不能超過 session 到期。session／登入預備狀態各最多 1000 筆，操作 nonce 最多 2000 筆。登出在共用資料庫撤銷。啟動 worker 時若帳號、密碼 hash、角色、專案範圍或 cookie/TTL 設定變更，會在同一鎖定交易中永久撤銷全部既有 session、登入 CSRF 與操作 nonce；保留節流計數。設定從 A 改 B 再改回 A，也不會復活舊 cookie。舊設定的 worker 會拒絕服務（登入回應 503），須完整更新所有 worker，避免不同設定輪流啟動而反覆登出使用者。

登入限制為同一直接對端 IP 每 5 分鐘 5 次、全域每 5 分鐘 100 次。反向代理可能使多個人共用同一 peer IP 的限制；服務不任意信任使用者提供的 forwarded IP。此保護不是公網完整防禦方案。

先 LAN 驗證。未來公開需另行處理公開 DNS、TLS 更新、反向代理信任設定、邊界防火牆／速率限制、認證方案、備份與還原、認證生命週期、監控及安全審查，並取得明確部署授權。不要將測試設定直接改成綁定所有介面。
