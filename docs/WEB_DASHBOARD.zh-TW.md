# 網頁管理與帳號密碼

ys-aimemory 的交接是系統功能：任務、讀取確認、租約、fence、指定接手者與稽核都在 Hub 保存，不只是本專案開發時的約定。網頁讓人類檢視這些狀態；AI 使用同一個服務的 MCP／REST。

## 啟用

沒有預設帳號密碼。首次啟用由部署者自行設定以下 bootstrap 帳號；升級至 schema 5 後一次性匯入資料庫，後续透過線上帳號管理更新：

- `HUB_WEB_USERNAME`：網頁登入名稱
- `HUB_WEB_PASSWORD_HASH`：互動式執行 `python -m memory_hub.web_password` 產生；密碼 12–1024 字元，不將明文放入環境檔
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

## 線上帳號管理

初始 admin 具有全站帳號管理能力，於 `/ui/users` 建立帳號、調整顯示名稱、角色及明確專案範圍，重設密碼或停用／啟用帳號。每個帳號最多 100 個專案授權；不支援萬用字元。不實體刪除身分，登入名稱不能更改，歷史作者以穩定 UUID 保留。使用者可在 `/ui/account/password` 提供目前密碼後自行變更。

`can_manage_users` 是獨立的全站管理能力，可以重設其他帳號密碼及更改授權，僅交給可信任的帳號管理者；能力本身不直接授予專案閱讀範圍。角色為 admin、member、read_only：member 可參與共享 Chat，不能修改原有專案／任務；read_only 不可發言或執行管理動作。系統防止停用或撤銷最後一位啟用中的帳號管理者。

每個 Cookie 請求都重新讀取有效帳號與權限。角色、範圍、密碼及啟用狀態更新使舊登入失效；nonce 綁定身分、操作、目標及版本。建立新記憶庫時 ownership 與建立者授權在同一交易寫入，保留該建立者目前的登入讓其立即使用，其他登入則失效。舊專案 ownership 只作歸屬，撤銷明確 grants 後不會因擁有者關係自動加回權限。

### 升級及重啟

首次 migration 保留原 owner UUID，將初始 scope 與既有 admin 所有專案寫成明確授權，保存永久 bootstrap 標記。舊版不帶使用者身分的 Cookie 失效。後續 DB 帳號是權威來源，環境中的舊 username、hash、role、scope 不會覆蓋線上修改，也不會自動重建已停用帳號。完成 bootstrap 後可以一起移除環境中的 username／hash／projects，既有 DB 帳號仍可登入；移除部分而留不完整 bootstrap 配置會被啟動檢查拒絕。全新 DB 若無 bootstrap 配置仍不啟用 Web。

升級前先備份並驗證還原。schema 5 與新程式須一起部署；舊程式會拒絕新版 schema。回退需使用備份恢復到獨立 DB 再切換，不能直接用舊 binary 連新版 DB。此版沒有忘記密碼寄信、OAuth／SSO或自動從環境重設管理員的功能；保留另一位可信帳號管理者與受保護的部署恢復流程。

## 登入安全與目前限制

Session、登入 CSRF、操作 nonce、提示訊息及登入節流在資料庫經鎖定交易協調，可跨 application instance 使用。資料庫只保存不透明 cookie 的 SHA-256 key，不存原始 cookie；帳號密碼保存 scrypt hash，回應及帳號 audit 不包含 hash 或明文。

Session 固定到期，不因讀取延長；登入 CSRF 為 600 秒，操作 nonce 為 900 秒且不能超過 session 到期。session／登入預備狀態各最多 1000 筆，操作 nonce 最多 2000 筆。登出在共用資料庫撤銷。Secure Cookie、TTL 或 MCP 功能旗標變更會撤銷全部既有 session、登入 CSRF 與 nonce，保留節流計數；舊 runtime policy 的 worker 拒絕服務，須完整更新所有 worker。帳號資料則以 DB 的 security_version 即時失效，不依賴重啟或環境配置輪替。

登入限制為同一直接對端 IP 每 5 分鐘 5 次、全域每 5 分鐘 100 次。反向代理可能使多個人共用同一 peer IP 的限制；服務不任意信任使用者提供的 forwarded IP。此保護不是公網完整防禦方案。

先 LAN 驗證。未來公開需另行處理公開 DNS、TLS 更新、反向代理信任設定、邊界防火牆／速率限制、認證方案、備份與還原、認證生命週期、監控及安全審查，並取得明確部署授權。不要將測試設定直接改成綁定所有介面。
