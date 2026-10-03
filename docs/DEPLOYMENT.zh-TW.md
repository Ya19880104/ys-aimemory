# Ubuntu VM／PVE 部署與復原

[English](DEPLOYMENT.md) | [繁體中文](DEPLOYMENT.zh-TW.md)

這份指南是待操作的部署流程，不代表已經在你的主機安裝。先在隔離測試 VM 執行，再導入 LAN。公開 Internet 部署屬後續階段。

第一次從 GitHub 安裝，先讀 [從零部署與 Claude／Codex 接線](QUICKSTART.zh-TW.md)。公開原始碼不代表應將運行中的 Hub 開放到 Internet。

## 1. 準備

- Ubuntu VM 可起步配置 2–4 vCPU、4–8GB RAM、至少 40GB SSD；這是規劃值，依紀錄量與備份實測調整
- 由管理者安裝可信官方 Docker Engine 與 Compose plugin，設定 VM 時鐘、儲存和備份目的地
- PostgreSQL 留在容器內部網路；不開 5432 給 Windows 客戶端
- 只讓已授權 Windows 專用電腦／VM 透過 TLS 接 Hub；不要共用可寫 repository 或資料庫資料目錄

## 2. 配置（管理者操作）

在 repository 根目錄複製 `.env.example` 為 `.env` 並限制讀取權限。所有秘密由你自行提供，範例沒有可用 token。

- `POSTGRES_PASSWORD`：資料庫管理帳號密碼
- `HUB_DB_PASSWORD`：獨立低權限應用程式資料庫帳號密碼
- `HUB_DATABASE_URL`：`postgresql+psycopg://memory_hub:URL_ENCODED_APP_PASSWORD@db:5432/memory_hub`
- `HUB_AUTH_TOKENS`：每個身分不同、至少 24 字元 token，JSON 中明確 worker_id、projects、role
- `HUB_ALLOWED_HOSTS`：只列需要的 host；localhost／127.0.0.1 與自己的 TLS 主機名

資料庫兩種密碼分開，不把管理員權限交給 app。`scripts/init-db.sh` 僅在空資料卷首次初始化時建立 app role；改 `.env` 不會旋轉已存在資料庫的密碼。密碼輪替需管理者另行操作，不刪 volume 來解決登入失敗。

網頁登入設定見 [網頁指南](WEB_DASHBOARD.zh-TW.md)。Compose 固定啟用 Secure Cookie，因此網頁必須經 HTTPS；若尚未配置網頁三個必要欄位，可先只測試 API。所有 `.env` 值中的 `$` 須正確單引號保留，尤其密碼 hash；勿將 `docker compose config` 的完整含秘密輸出貼到聊天或日誌。

## 3. 僅本機健康檢查

```sh
bash scripts/preflight.sh
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8000/healthz
```

預設 app 僅發布 loopback。健康檢查通過不代表 MCP、網頁登入或四帳號都已驗證。不要以缺少健康狀態為理由放寬驗證或改用 SQLite 正式運行。

## 4. LAN TLS

先由管理者配置可信憑證與私鑰：`nginx/certs/fullchain.pem`、`nginx/certs/privkey.pem`。私鑰需可由容器 UID 101 讀取但不可 world-readable；不提交到 Git。用 LAN 對應的憑證主機名，不能繞過瀏覽器憑證警告。

在 `.env` 將 `HUB_BIND_HOST` 設為 VM 明確的私有 LAN IP；它優先於舊欄位 `HUB_HTTPS_BIND_IP`，只改舊欄位仍可能綁在 loopback。`HUB_HTTPS_PORT` 預設 8443，`HUB_PUBLIC_BASE_URL` 必須包含實際 HTTPS port，`HUB_ALLOWED_HOSTS` 加入憑證主機名或 IP（不帶協定與 port）。來源範圍由部署者依自己的內網決定；本套件不自動修改防火牆。

```sh
bash scripts/preflight.sh --tls
docker compose --profile tls up -d --build
```

從 Windows 瀏覽器開 `https://已驗證主機名:8443/ui`，支援 Streamable HTTP 的官方 AI 客戶端各接 `/mcp`。Claude Code 可從同一 HTTPS origin 的 `/downloads/ys-memory-stdio-1.1.1.zip` 下載 stdio → HTTPS 安裝包；CA 與專案設定步驟見 [客戶端接線](CLIENT_SETUP.zh-TW.md)。按 [演練](API_EXAMPLES.zh-TW.md) 與 [驗收清單](ACCEPTANCE_TESTS.zh-TW.md) 驗證身份隔離和交接，安裝不代表原生對話已通過。

## 5. 備份、還原演練與更新

```sh
bash scripts/backup.sh
bash scripts/restore-check.sh /path/to/trusted.dump restore_check_YYYYMMDD
```

只還原你信任的 dump；還原可能執行 dump 內的資料庫指令。restore-check 建立新的獨立資料庫，不覆寫 live DB；演練後按輸出的管理說明處理測試庫，不隨意刪生產 volume。dump 含專案內容，限制讀取並納入加密／異機備份。

更新前備份、記錄現有 image／commit、在測試 DB 驗證新版，再更新。VM snapshot 不是唯一備份；需實際還原與核對資料。schema／格式升級目前沒有完整 migration framework，先讀 release 變更並演練，不能假設可跨版本無損回退。

## 6. 現階段部署限制

Compose／Dockerfile 預設單 application worker。網頁 session、login CSRF、操作 nonce、flash、登入節流與設定版本保存在資料庫，以鎖定交易協調；共用同一資料庫與相同配置的 application instance 可共用這些狀態。資料庫與配置不變時，尚未到期的 session 不會只因應用程序重啟而失效；設定變更會永久撤銷舊登入，舊配置 instance 無法繼續使用舊 session。PostgreSQL 下多程序與正式多 worker 部署仍為 not_run，尚未驗收，不能由此宣稱已證明可生產水平擴展。

資料寫入集中 PostgreSQL，但讀取封包和稽核資料目前未設完整保留政策。實際容量、長期壓力、Windows 客戶端與 PVE 還原仍須在目標環境驗收。未來公網需額外身份管理、邊界防護與安全審查，不只是把綁定位址改為 0.0.0.0。


## 文件鏡像與離線 help

`HUB_DOCS_BASE_URL` 控制 Hub server-rendered guide links。未設定／空值保留 `https://github.com/Ya19880104/ys-aimemory/blob/main/docs`。可設 HTTPS directory（如 `https://docs.example.com/ys-memory`）或 root-relative directory（如 `/mirror/docs`）；連結追加選定英文／繁中 Markdown filename。鏡像檔案與 web-server mapping 由 operator 提供，Hub 不下載、代管或驗證內容；wheel 未包 Markdown guides。

離線 LAN 設 `HUB_DOCS_BASE_URL=/help`，連結使用既有語系 help landing page（`/help?lang=en`／`/help?lang=zh-TW`），不產生不存在的單份文件 route。這是內建摘要操作手冊，不是所有完整 guide 的副本。

只接受 HTTPS／root-relative directory；拒絕 credentials、query/fragment、百分比 escape、backslash、控制／非 ASCII 字元、重複 separator、dot traversal，URL 請用 ASCII/punycode。錯誤設定安全 fallback 到本地 `/help`，不令 UI request crash；尾端 slash 正規化。Compose 傳入此設定，部署修改後重啟 runtime。釘選 installer downloads 與 vendor references 獨立，此設定不改寫或授權 installer sources。

`HUB_DOCS_BASE_URL` 無效時退回對應語系的 `/help`，每次應用程式 middleware 啟動記錄一次警告；不會記錄遭拒絕的設定值。
