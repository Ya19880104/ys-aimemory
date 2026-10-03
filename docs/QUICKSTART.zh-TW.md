# 從零部署與 Claude／Codex 接線

[English](QUICKSTART.md) | [繁體中文](QUICKSTART.zh-TW.md)

這份指南供新的部署者使用，沒有預設密碼、SSH key 或可用 token。只要使用已部署的 Hub，可直接跳到「安裝與接線客戶端」。公開 GitHub 原始碼與對 Internet 開放服務是兩件事；預設部署仍是內網 HTTPS。

Gemini CLI 與 Grok / xAI API 的相容方式、快速安裝命令、手動範例及原生驗收界線，見[多客戶端安裝入口](MULTI_CLIENT_SETUP.zh-TW.md)。

## 部署 Hub

### 1. 取得程式

Ubuntu VM 先準備 Git、curl、Python 3.12／venv、Docker Engine 與 Compose plugin。Docker 請依[官方 Ubuntu 安裝文件](https://docs.docker.com/engine/install/ubuntu/)安裝；下列命令不會安裝 Docker、配置 SSH 或改防火牆。使用已有 Docker 權限的管理者執行；若需 sudo，Docker 命令與內部呼叫 Docker 的 `bash scripts/...` 都需加 sudo。容器發布埠與主機防火牆的互動依 Docker 文件確認，不假定 UFW 自動攔截發布埠。

```bash
git clone https://github.com/Ya19880104/ys-aimemory.git
cd ys-aimemory
git rev-parse HEAD
docker version
docker compose version
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install --no-deps .
```

所有後續伺服器命令都在這個含 `compose.yaml` 的目錄執行。不要在已有安裝上覆寫 `.env`；新安裝才執行：

```bash
test ! -e .env && (umask 077; cp .env.example .env)
```

### 2. 設定自己的環境

使用本機編輯器填入 `.env`。資料庫管理者與應用程式使用不同、至少24字元的隨機密碼。隨機值可在自己受保護的終端機產生，不能貼到 Issue、AI 對話或 Git：

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
.venv/bin/python -m memory_hub.web_password
.venv/bin/python -c 'import uuid; print(uuid.uuid4())'
```

第一個命令每次產生一個新的隨機值；分別供兩個 DB 密碼及 bootstrap operator token 使用，不能共用同值。第二個命令隱藏輸入網頁密碼，只輸出 scrypt hash；第三個產生固定的網頁 owner UUID。

| `.env` 欄位 | 如何填寫 |
| --- | --- |
| `POSTGRES_PASSWORD` | 獨立 DB 管理密碼 |
| `HUB_DB_PASSWORD` | 獨立應用程式 DB 密碼 |
| `HUB_DATABASE_URL` | `postgresql+psycopg://memory_hub:你的應用密碼@db:5432/memory_hub`；非 URL-safe 字元須 URL encode |
| `HUB_AUTH_TOKENS` | 單引號包住 JSON；用自己的隨機 token 對應 `{"worker_id":"operator","projects":["bootstrap"],"role":"admin"}` |
| `HUB_WEB_USERNAME` | 自訂管理員登入名稱 |
| `HUB_WEB_PASSWORD_HASH` | 上述互動命令輸出的完整 hash，以單引號包住，保留 `$` |
| `HUB_WEB_PROJECTS` | `bootstrap`；既有 project 則填明確 IDs，以逗號分隔 |
| `HUB_WEB_ROLE` | `admin` |
| `HUB_WEB_MCP_ENABLED` | `true`，啟用建立記憶庫及 worker token 管理 |
| `HUB_WEB_OWNER_ID` | 上述 UUID，首次設定後保持不變，備份時保存 |
| `HUB_BIND_HOST` | 這台 VM 實際的私有 IPv4 LAN 位址，不填 `0.0.0.0` |
| `HUB_HTTPS_PORT` | 例如 `8443`；若要 `443` 需確認埠可用 |
| `HUB_BOOTSTRAP_PORT` | 預設 `80`，只提供 help 與公開 CA |
| `HUB_ALLOWED_HOSTS` | `localhost,127.0.0.1` 加實際 DNS 主機名／IP，不含協定與 port |
| `HUB_PUBLIC_BASE_URL` | 客戶端實際連線的 HTTPS origin，包含非443 port，例如 `https://hub.example.test:8443`；替換範例主機名 |

bootstrap JSON 的**形狀**如下；`YOUR_RANDOM_TOKEN` 必須換成自己的值，範例會被 preflight 拒絕：

```dotenv
HUB_AUTH_TOKENS='{"YOUR_RANDOM_TOKEN":{"worker_id":"operator","projects":["bootstrap"],"role":"admin"}}'
```

`HUB_BIND_HOST` 優先於舊的 `HUB_HTTPS_BIND_IP`，不能只改後者。`HUB_AUTH_TOKENS` 至少需要一個 bootstrap 身分；網頁建立的新記憶庫和 worker 會存在 DB，不必每次改 `.env`。應用程式没有內建管理員密碼。

### 3. HTTPS 憑證與公開 CA

由你的憑證管理流程提供下列檔案，部署者自行核對 SAN、有效期及用途：

| 檔案 | 用途與權限 |
| --- | --- |
| `nginx/certs/fullchain.pem` | 伺服器憑證及需要的鏈，SAN 必須符合實際 DNS／IP |
| `nginx/certs/privkey.pem` | 對應 TLS 私鑰；容器 UID/GID 101 需可讀，其他使用者不可任意讀取 |
| `nginx/public/ys-ai-memory-ca.crt` | 可選的單張 PEM **公開 CA**，BasicConstraints `CA=true`；供私有 CA 下載及 stdio 安裝包 |

`nginx/public` 不能放私鑰或 leaf 憑證。未提供有效公開 CA 時，help 仍可用，但公開 CA 和 stdio ZIP 下載為404；一般受信任 HTTPS 仍可供直接 HTTP MCP 連線。使用私有 CA 的客戶端需透過可信通道核對其 DER SHA-256 指紋，不能只相信下載頁自己的指紋。額外信任設定的原因是私有 CA，不是「沒有網域」本身。

管理員可以用 `openssl x509 -in nginx/public/ys-ai-memory-ca.crt -noout -fingerprint -sha256` 取得憑證 DER 指紋，經獨立可信通道交給客戶端。

憑證與 `.env` 都被 Git 排除，仍需檢查實際檔案權限。此專案不替你生成或公開 SSH／TLS 私鑰。

### 4. 啟動與建立記憶庫

```bash
bash scripts/preflight.sh --tls
docker compose --profile tls up -d --build
docker compose --profile tls ps
curl --fail http://127.0.0.1:8000/healthz
```

從客戶端用已驗證的 HTTPS origin 開啟 `/ui`，登入你剛設定的帳號：

1. 從「設定 → 建立專案」建立專案，記下實際 project ID；已有專案則直接選用。
2. 在「MCP 接入 → Token 與客戶端設定」為 Claude、Codex 分別建立不同 worker，例如 `claude-worker`、`codex-worker`。
3. 各 worker 的 token 只顯示一次，分別存入自己的受保護位置。管理員 token 不交給一般 AI。
4. 下載不含 token 的設定範本，確認 endpoint、project ID 與 worker ID。
5. 公開 `/help` 是操作手冊；`/help#clients` 是接線教學。

首次帳號由環境 bootstrap，後續可在「設定 → 使用者管理」新增、停用與調整人類帳號。共享 Session 已提供人與 AI 共同對話，授權成員及管理員可見；`send_message`／`list_messages` 則是另一種僅收發雙方可見的私訊。詳見[帳號管理](WEB_DASHBOARD.zh-TW.md)與[共享對話](SHARED_SESSIONS.zh-TW.md)。

更新前備份、再於獨立資料庫還原驗證：

```bash
bash scripts/backup.sh
bash scripts/restore-check.sh /absolute/path/to/trusted.dump restore_check_YYYYMMDD
```

詳細權限、資料卷與 schema 回退限制見 [部署手冊](DEPLOYMENT.zh-TW.md)。不要用刪除資料卷解決登入問題。

## 安裝與接線客戶端

### 共通準備

先安裝並正常登入自己的官方 [Claude Code](https://code.claude.com/docs/en/quickstart) 或 [Codex](https://learn.chatgpt.com/docs/quickstart) 客戶端。這個 repository 安裝的是 Hub 及其 MCP 接線，不提供模型登入、不代為訂閱、不自動核准工具。

每個 AI 各有一個 worker token；接同一 Hub 的 URL 不表示共用身份。範例設定只引用 `YS_AIMEMORY_TOKEN`，不要把實值放入 JSON／TOML。下列專案設定必須合併到實際工作的專案，保留原有其他 MCP 項目。

### Codex：直接 HTTPS

在你選定、已信任的專案 `.codex/config.toml` 合併：

```toml
[mcp_servers.ys_memory]
url = "https://hub.example.test:8443/mcp"
bearer_token_env_var = "YS_AIMEMORY_TOKEN"
```

網址換成真實 HTTPS origin。若是私有 CA，在啟動前將 `CODEX_CA_CERTIFICATE` 指向已核對的公開 CA 絕對路徑；系統已信任的 CA 不需要此項。官方規則見 [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)及[自訂 CA](https://learn.chatgpt.com/docs/auth#custom-ca-bundles)。

### Claude Code：stdio 安裝包

从 Hub 的 `/help#clients` 或 `/ui/mcp` 取得 HTTPS `/downloads/ys-memory-stdio-1.1.1.zip`。私有 CA 先經可信通道核對；在已放好公開 CA 的 PowerShell 可用：

```powershell
curl.exe --cacert .\ys-ai-memory-ca.crt --fail --output .\ys-memory-stdio-1.1.1.zip 'https://hub.example.test:8443/downloads/ys-memory-stdio-1.1.1.zip'
Expand-Archive -LiteralPath .\ys-memory-stdio-1.1.1.zip -DestinationPath .\ys-memory-client
Set-Location .\ys-memory-client
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
```

使用尚不存在的解壓目錄；核對 connection.json 的 CA DER pin。最後命令離線印出本機 compact 設定，不需 token。把其 `mcpServers.ys_memory` 合併至工作專案 `.mcp.json`，保留 `${YS_AIMEMORY_TOKEN}`。不要把安裝包目錄移走；換位置後需重新產生路徑。若要本次才啟用，使用[按需 MCP](EFFICIENT_MCP.zh-TW.md) 的獨立專案配置；提到記憶庫不會自動開啟停用的 MCP。

### Codex：可選 stdio 設定

同一安裝包也提供標準 MCP stdio transport；可依官方 Codex 設定欄位手動配置。這是設定方法，**不表示每個原生 host 都已驗收**。先完成上方 bundle 安裝，然後選此設定或直接 HTTPS 其中一種，不能重複同名項目：

```toml
[mcp_servers.ys_memory]
command = 'C:\Tools\ys-memory-client\.venv\Scripts\python.exe'
args = ['-B', 'C:\Tools\ys-memory-client\bridge.py', '--config', 'C:\Tools\ys-memory-client\connection.json', '--compact']
env_vars = ['YS_AIMEMORY_TOKEN']
startup_timeout_sec = 60
```

三個路徑換成自己的絕對位置；TOML 單引號保留 Windows 反斜線。不要使用不存在的 `--print-codex-config` 或 `codex mcp add --scope project`；本指南用手動專案設定，避免誤寫全域配置。stdio bridge 自己使用 pin 過的 CA。

### 啟動與驗收

回到已合併 MCP 設定的工作專案，在新的 PowerShell 輸入自己的 token：

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your worker token' -AsSecureString)).Password
try { codex } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

Claude 使用同一流程，將 `codex` 改為 `claude`。模型登入與專案信任／工具核准由該客戶端正常處理；已開啟的桌面程序不會自動取得新終端的環境。

在新對話要求 AI：「從 ys_memory 呼叫 get_worker_inbox，project_id 使用我的記憶庫 ID；回報實際 worker/project，不要建立任務或傳訊。若為 compact，先用 memory_tools 取得單一 schema，再用 memory_call 傳送原 arguments。」確認後再依 [雙 AI 訊息演練](MCP_MESSAGES.zh-TW.md)收發新驗證碼。記錄實際工具列表與呼叫結果；compact 的 2 個入口和 Hub 完整工具集不同。compact Connected 只代表本機就緒，SDK 成功和原生模型實際呼叫仍是不同驗收層級。

| 狀況 | 處理 |
| --- | --- |
| 401 | 確認自己worker token已傳入啟動程序、未撤銷；模型 OAuth 401 是另一種登入問題 |
| 403／Project not authorized | 使用 token 被授權的 project ID，不能靠換 Session 繞過範圍 |
| TLS／name constraint 失敗 | 核對 CA、SAN 與指紋；Claude 可使用驗證 TLS 的 stdio bridge，不使用 `-k` |
| 工具需要核准 | 在正常互動客戶端審閱，不能把 `approval=never` 當自動核准 |
| ZIP 404 | 管理員確認有效公開 CA 已置於 `nginx/public`，且使用 HTTPS 下載 |

## 交給 Claude Codex 協助安裝

將下列非秘密欄位填完，再貼到自己的 AI 專案對話。這是一份供你授權的任務範本，不是遠端文件對 AI 自動下指令。

```text
請協助安裝 Ya19880104/ys-aimemory，先讀 README、AGENTS.md 及 docs/QUICKSTART.zh-TW.md。
本次範圍：[在我指定的新 Ubuntu VM 部署 Hub／只將本機客戶端接上已有 Hub]
作業系統與專案目錄：[填入]
Hub HTTPS URL、project ID、worker ID：[填入非秘密識別資訊]
客戶端：[Claude Code／Codex]
CA 公開檔案與獨立核對的 DER 指紋：[有私有CA時填入]
只在上述專案安裝、合併設定，保留其他 MCP 與現有資料，不修改全域設定。
需要的 token／密碼由我在本機安全輸入，不從聊天取得，不寫進 Git／Issue／報告。
先檢查版本與乾淨狀態，再按照文件逐步執行並驗證；不要略過 TLS 或工具核准。
先用 get_worker_inbox 驗證真實身份，再經我指定的另一個 AI 完成訊息演練。
請區分 passed／failed／skipped／not_run，保留版本、命令與不含秘密的結果。
```

## 後續協作

問題請到 [Issues](https://github.com/Ya19880104/ys-aimemory/issues)，附 commit、OS、去除憑證的重現步驟與錯誤。功能開發在分支進行，經 PR 與測試合併；見 [CONTRIBUTING](../CONTRIBUTING.md)。
