# ys-aimemory 0.3

[English](README.md) | [繁體中文](README.zh-TW.md)

已連線？使用簡短的[日常聊天指南](docs/START_CHATTING.zh-TW.md)。

四個 AI 官方客戶端共用的中央記憶、任務上下文、訊息與明確交接服務。以 Python、FastAPI、官方 MCP SDK 與 PostgreSQL 實作；支援 MCP Streamable HTTP 與 REST，提供繁體中文操作文件及 portable Skills。

這是可測試的原型與部署套件。部署、官方 SDK 與原生客戶端驗收須各自綁定確切版本及環境；功能說明不代表四個正式訂閱客戶端已完成端到端驗收。

Repository：[Ya19880104/ys-aimemory](https://github.com/Ya19880104/ys-aimemory)。Python distribution 名稱是 `ys-ai-memory-hub`，import 名稱是 `memory_hub`。請在 clone 後含 `pyproject.toml` 的根目錄執行命令。

## 安裝入口

一般操作順序：建立／選擇專案 → 新建／選擇對話 → 各 AI 專用 worker Token → 接上 MCP → 加入房間 → 視需要啟用有時間／回合上限的接收程式。普通聊天不需 task lease。

[完整雙語文件索引](docs/README.zh-TW.md)。[ChatGPT 私人 tunnel 試行](docs/CHATGPT_PRIVATE_TUNNEL.zh-TW.md)固定 worker 與單一房間，不是多使用者 OAuth 公開服務。

- **Windows 本機 Claude 快速設定：** [單一指令安裝與原生驗收步驟](docs/CLAUDE_WINDOWS_SETUP.zh-TW.md)。自動建立環境、合併專案 MCP，Token 用目前 Windows 使用者加密保存；設定完成後仍需在自己的原生客戶端驗證身分與讀寫；聊天室可複製限定房間安裝指引；須在本機執行並啟用（來源功能，部署狀態另行驗證）。
- **先選客戶端：** [Claude、Codex、Gemini 與 Grok 接入對照](docs/MULTI_CLIENT_SETUP.zh-TW.md)，包含快速命令、手動設定、給 AI 的安裝任務，以及內網和雲端的差異；Gemini／Grok 原生驗收尚未完成。
- **部署自己的伺服器：** [Ubuntu／Docker 從零部署](docs/QUICKSTART.zh-TW.md#部署-hub)。包含環境設定、HTTPS、建立記憶庫及 worker token。
- **Claude Code／Codex 接上已有的 Hub：** [客戶端安裝](docs/QUICKSTART.zh-TW.md#安裝與接線客戶端)。各自使用自己的身分，設定僅限選定專案。
- **讓 AI 協助安裝：** [可直接貼給 Claude／Codex 的安裝任務](docs/QUICKSTART.zh-TW.md#交給-claude-codex-協助安裝)。先填非秘密的環境資訊。
- **回報問題與分支開發：** [Issues](https://github.com/Ya19880104/ys-aimemory/issues)、[貢獻方式](CONTRIBUTING.zh-TW.md)。
- **第一次操作：** [完整操作教學入口與驗收](docs/OPERATION_MANUAL.zh-TW.md)，主機 `/help` 提供 CA、Token、IDE 接入及共同對話的逐步 HTML 教學。
- **人與 AI 共同討論：** [共享對話、成果與附件](docs/SHARED_SESSIONS.zh-TW.md)，後台 `/ui/chat`。
- **自動接話進度：** [限定房間的自動接收設定與驗收界線](docs/AUTOMATIC_CHAT.zh-TW.md)、[Windows Codex CLI 自動接話安裝](docs/CODEX_CHAT_SETUP.zh-TW.md)。已提供限定房間的原生接收設定與持久派送；整合版原生喚醒與雲端驗收分開，不能以原始碼宣稱通過。
- **有需要才讀記憶：** [Codex／Claude 按需接入與省 Token](docs/EFFICIENT_MCP.zh-TW.md)，支援兩工具 compact adapter。
- **確認模型真的連上：** [原生工具與共享對話驗收](docs/NATIVE_CLIENT_CHECK.zh-TW.md)，分辨 transport、SDK、工具核准與模型登入。

公開庫不提供可用的部署帳密、worker token、SSH／TLS 私鑰或資料庫。現行公開教學使用英文／繁中合成 SVG 操作示意，不是原生驗證截圖；現場原圖已從現行套件移除並私人備份，未改 Git 歷史。`MANIFEST.sha256.json` 與 `TEST_REPORT.zh-TW.md` 保存原交付基線，不是目前所有新增檔案的 manifest 或本次 CI 成績；最新 CI 請查看對應 commit 的 [Actions](https://github.com/Ya19880104/ys-aimemory/actions)。

## 已實作

- 專案隔離與服務端驗證的 worker 身分、安全角色
- 持久化 MCP 訊息：同專案有效身分可收發，每人僅讀本人寄出／收到的訊息，包含分頁、回覆關聯及冪等重試
- 管理者登錄來源快照、任務目標、路徑範圍與驗收條件
- prepare／claim／read／acknowledge／accept／validate 開工門檻
- 專案修訂失效、讀取收據、限時租約、續租、fencing token
- checkpoint、指定接手者、提案／核准、完成聲明與稽核
- 管理員可附原因與版本門檻重新分派離線／退役 worker 的任務，舊租約立即失效
- 共享 Session：管理員／成員與 AI 共用訊息紀錄（網頁增量同步；自動模式需另行明確綁定與驗收）、搜尋紀錄、保存文件／方案／摘要與提案，並分享有配額的附件
- DB 人類帳號：管理員／成員／唯讀、明確專案範圍、線上密碼與停用管理、權限變更後登入失效；帳號管理能力獨立
- PostgreSQL GIN／SQLite FTS5 索引搜尋，明確中文子字串回退
- 原子批次匯入、CAS 版本比較、冪等重試、來源歷史與索引健康／重建
- 資料庫保存 session、CSRF、操作 nonce 與登入節流，支援多 application instance
- 四 AI 的獨立 clone/worktree 與可輪替工作角色操作約定
- Codex／Claude Code 的 stdio → HTTPS 安裝包：獨立 Python 環境、公開 CA pin、專案設定與環境 token；compact 初始只提供兩個工具，實際呼叫才連 Hub

路徑範圍不能取代檔案系統隔離；讀取收據不能證明理解；完成聲明不能取代獨立驗收。兩個 AI 可各自透過 MCP 工具傳訊與讀取回覆；Hub 不呼叫模型、不保證自動喚醒對方，也不取得其他客戶端既有的聊天紀錄或模型供應商登入 cookie。訊息不等於授權、核准知識或任務交接。網頁使用獨立的 Hub 工作階段 cookie。

## 文件入口

1. [架構、信任邊界與限制](docs/ARCHITECTURE.zh-TW.md)
2. [四 AI 開工／交接／驗收手冊](docs/FOUR_AGENT_RUNBOOK.zh-TW.md)
3. [官方客戶端與 Skills 手動設定](docs/CLIENT_SETUP.zh-TW.md)
4. [API 契約與可執行演練](docs/API_EXAMPLES.zh-TW.md)
5. [驗收與失敗情境清單](docs/ACCEPTANCE_TESTS.zh-TW.md)
6. [Ubuntu／PVE 部署操作](docs/DEPLOYMENT.zh-TW.md)
7. [網頁管理與帳號密碼](docs/WEB_DASHBOARD.zh-TW.md)
8. [知識索引與查詢](docs/KNOWLEDGE_INDEX.zh-TW.md)
9. [匯入與更新記憶](docs/IMPORTING_MEMORY.zh-TW.md)
10. [0.2 驗收範圍](docs/V02_ACCEPTANCE.zh-TW.md)
11. [MCP 訊息與兩個 AI 對話](docs/MCP_MESSAGES.zh-TW.md)

一般 MCP 工具集隨版本更新，以目標伺服器 `tools/list` 核對。compact 模式只暴露 `memory_tools`／`memory_call`，需要時發現原工具。對話不需要 task lease，亦不改變專案 revision 或任務 lease／fence；任務寫入仍須完整開工流程。

## 本機開發

Python 3.11 以上；以下命令會安裝本專案依賴，請在專用虛擬環境執行：

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

測試使用隔離的測試憑證／資料庫，不供正式部署使用。若執行 PostgreSQL 整合測試，請閱讀 tests 中的環境要求並使用專用可拋棄資料庫。

開發伺服器需要人類先提供 `HUB_DATABASE_URL`、`HUB_AUTH_TOKENS`。沒有 token 不啟動，沒有內建管理者密碼。正式使用 PostgreSQL；`HUB_ALLOW_SQLITE=true` 只用於單機 demo／測試，不能當作四個客戶端的正式資料庫。

```sh
uvicorn memory_hub.app:create_app --factory --host 127.0.0.1 --port 8000
```

`GET /healthz` 為健康檢查。工具透過 `POST /v1/tools/{tool_name}` 或 MCP `/mcp` 呼叫，後者使用 Streamable HTTP。Claude Code／Codex 可由 HTTPS `/downloads/ys-memory-stdio-1.1.1.zip` 取得本機 stdio → HTTPS 轉接器；在自選新目錄建立 Python 3.12 環境，再手動合併專案設定，手動 adapter 從 `YS_AIMEMORY_TOKEN` 讀取；Windows 安裝器則由 DPAPI 加密保存並由 launcher 讀取。步驟與 CA name constraints 相容限制見[客戶端接線](docs/CLIENT_SETUP.zh-TW.md)及公開 `/help#clients`。安裝不修改全域設定，不自動授權模型或喚醒 AI；仍須分別驗收實際客戶端與雙向對話。

## 部署起點

在專用 Ubuntu VM 檢查 Docker／Compose 後，閱讀部署文件、複製 `.env.example`，由管理者填入自己的資料庫密碼與不同 worker 的 token。不要將 `.env`、TLS 私鑰或 token 加入 Git。範例不產生憑證、不修改防火牆、不直接對 LAN 或 Internet 開放。

預設只綁 loopback。LAN 使用需人工設定 TLS、可信憑證、主機 allowlist 和防火牆；10Gbps LAN 不代表可略過驗證。備份應先做獨立資料庫還原演練，再考慮正式啟用。

## Skills

- `skills/hub-task-start/SKILL.md`：開工、接手、重新驗證
- `skills/hub-task-handoff/SKILL.md`：checkpoint、證據與交接
- `skills/hub-review-accept/SKILL.md`：獨立審查與驗收
- `skills/ys-memory-chat/SKILL.md`：使用者要求時才加入共享 Session，按需讀取紀錄

`AGENTS.md` 與 `CLAUDE.md` 引導客戶端讀取這些原始檔。自動發現與安裝依實際官方客戶端而定，不宣稱已替任何帳號完成設定。

## 可重現測試版本

`requirements-tested.txt` 記錄此次乾淨 Python 3.12 環境實際通過的相依版本（非含雜湊的供應鏈鎖檔）。使用專用虛擬環境：

```sh
python -m pip install -r requirements-tested.txt
python -m pip install --no-deps .
python -m pytest -q
python scripts/test-deployment.py
```

原交付歷史結果見 [測試與交付報告](TEST_REPORT.zh-TW.md)；当前版本須另附 exact commit 的測試紀錄。雲端原生身分確認、共享讀寫與自動喚醒應分開驗收。

最新限定範圍證據：[2026-10-04 驗證](docs/VALIDATION_2026-10-04.zh-TW.md)，包含 2026-10-05 補充，另保留[先前 native 證據](docs/VALIDATION_2026-10-03.zh-TW.md)。來源檢查與 live 驗收各自保留版本界線。專用 native Codex 有界交換、暫停／恢復、觀察到的 idle restart 與真實 provider in-flight 有界防重派通過；完整自動復原仍 pending。

在 **2026-10-05 台北 02:06** 截止點，Cloud C 於已部署 `6d0ce27` 通過兩次自動完整讀取／回覆事件，中間有一次官方閒置 transport/gateway 重連，無中途 model prompt，核實 task pause／unsubscribe 及一次 runtime 關閉。這是一次有界試驗，不是模型 restart、crash／in-flight recovery 或長期生命週期驗收。歷史 Cloud A/B 自行停止失敗及 2026-10-04 自動失敗／手動通過分開保留。見[去秘密實測請求與觀察到的權限](docs/CHATGPT_PRIVATE_TUNNEL.zh-TW.md#有界請求與觀察到的權限)；英文請求為未執行的翻譯，既有帳號 run 後權限讀回不能證明全新安裝或任意帳號皆可重現。[操作者停止流程](docs/CHATGPT_PRIVATE_TUNNEL.zh-TW.md#停止狀態與限制)仍為必要步驟。可靠度與雲端 Token 成本未測量；事件上限不是成本上限。
