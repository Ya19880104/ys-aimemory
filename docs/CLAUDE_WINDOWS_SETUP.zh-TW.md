# 本機 Claude：單一指令安裝與連線驗收

[English](CLAUDE_WINDOWS_SETUP.md) | [繁體中文](CLAUDE_WINDOWS_SETUP.zh-TW.md)

## 歷史驗證與目前狀態

2026-10-03 較早的手動測試回報原生身分、共享對話讀取與寫回成功，環境為 Windows 11／Python 3.12.13／Claude Desktop Code，Sonnet 5.5／Medium。原指南沒有記錄該次確切來源／runtime commit；這是歷史證據，不是目前安裝器或自動接收程式的驗收。

目前 Claude 自動模式驗收因模型供應商登入過期而維持 **not_run**。adapter 已設定或 Connected 不證明模型登入有效；帳號擁有人需先恢復正常登入，再重做原生驗收，不借用其他 worker 憑證或放寬工具／TLS 控制。詳見[目前限定驗證](VALIDATION_2026-10-03.zh-TW.md)與[自動對話](AUTOMATIC_CHAT.zh-TW.md)。本庫提供命令列安裝器，不是網頁一鍵或免前置準備的安裝包。

## 先準備四樣東西

1. 這台電腦已登入 Claude Desktop，在 **Code → Local** 選擇工作專案。記下這個資料夾；安裝時選同一個，否則新對話讀不到設定。不需要另登入 CLI。
2. Windows 已安裝 **Python 3.12**，並已下載本 GitHub 專案。安裝只需要 Python 標準函式庫，會自行建立獨立環境及安裝 adapter 依賴，不必先部署 Hub。
3. 從自己的 Hub「MCP 接入」下載 **`ys-memory-stdio-1.1.1.zip`**，解壓到新資料夾。必須有 `bridge.py`、`connection.json`、`ys-ai-memory-ca.crt`、`requirements.lock`、`README.txt` 五個檔案。先由可信通道核對公開 CA 的 **DER SHA-256** 指紋，並透過已驗證 HTTPS 下載；不能略過憑證警告。
4. 在 Hub 為這台 Claude 產生自己的 worker Token，授權需要的專案。網頁密碼、Claude 登入、worker Token 是三種不同用途；不要拿另一位 AI 的 Token 共用。

## 執行一個安裝命令

在 PowerShell 執行，將三個範例值換成自己的資料：

```powershell
py -3.12 "C:\src\ys-aimemory\scripts\setup-claude.py" --bundle "C:\Downloads\ys-memory-client" --project "C:\work\my-project" --expected-ca "管理員提供的64位DER_SHA256指紋"
```

出現 `Your Claude worker Token:` 後貼上 Token 並按 Enter。隱藏輸入不顯示字元是正常的，不必重複貼上。安裝會建立專用 Python 環境、保留其他 MCP 並加入專案 `.mcp.json`，最後印出安裝收據和實際路徑。**`installed_not_native_verified` 表示設定已完成，還要做下一步的 Claude 驗證。**

安裝器將 Token 存為只有目前 Windows 使用者可解密的 DPAPI 檔案；`.mcp.json` 不含 Token 明文，也不用到 Desktop 全域環境編輯器再填一次。MCP 子程序啟動時解密自己的 Token，實際呼叫工具時才連 Hub。它不改全域 Claude／Codex 設定、系統 CA、專案信任、工具權限或自動對話 Hooks。

已存在 `ys_memory` 時會停止，不覆寫或重複加入。其他 MCP 設定會保留；如原本有 `.mcp.json`，備份用同一 Windows 使用者加密保存為 `previous-mcp.dpapi`。安裝收據、Token 與環境放在本機 `%LOCALAPPDATA%\YS-AIMemory\clients` 下；Windows Store 程序可能映射到 LocalCache，以收據中的**實際路徑**為準。

## 在 Claude 確認真的接上

在同一個資料夾開 **新的 Local Code 對話**，依畫面審閱信任及 MCP 提示。將自己的專案 ID 填入這段文字，再貼給 Claude：

```text
請使用原生 YS Memory MCP 確認連線。
我的 project_id 是：填入自己的專案 ID。
先搜尋 memory_tools / memory_call，取得 get_worker_inbox 的 schema，
再依 schema 呼叫，保留 arguments 層級，回報實際 worker_id。
不要認領任務。找不到原生工具時回報 NOT_RUN，不用其他程式代替。
```

工具結果的 worker_id 必須等於自己在 Hub 建立的身分。接著到 Hub「共享對話」建立或選擇對話，按「複製加入指引」貼到 Claude，再說「只讀取最新訊息，回覆一句並真正寫回共享對話」。**網頁出現 Claude 身分、訊息 ID 和序號，才是完整讀寫驗收。** 不需再贴 Token，也不用先建立任務或交接。



## 卡住時看哪裡

| 狀況 | 處理方式 |
| --- | --- |
| `ys_memory already exists` | 本專案已有設定；先確認是不是已可用。換裝前備份並只處理這一個項目，不刪整份設定。 |
| `Invalid public bundle asset` | 重新解壓五個檔案，不要拿少了 README 的測試目錄。 |
| `FileNotFoundError` | 核對 bundle 和 project 都是這台電腦的實際資料夾。 |
| `CalledProcessError` | Python 環境、依賴安裝或 adapter 驗證失敗；核對 Python 3.12、套件下載網路及公開 CA。收據尚未完成前不要假定已連線。 |
| 工具找不到 | 確認新的 Local 工作選了同一個資料夾，核對 MCP 啟動路徑與核准狀態。 |
| `credential_launcher_stopped` | 確認使用原安裝的 Windows 帳號與電腦；DPAPI 密文不能當成可攜 Token 檔。 |
| `AUTH_REJECTED` | 核對 Claude worker 的 Token 和專案授權；撤銷或換 Token 後需重新配置。 |
| `TLS_VERIFY_FAILED` | 核對可信 CA 指紋、主機名與有效期，不關閉驗證。 |

換電腦、CA 輪替或 Token 更換時，在新環境重新安裝並更新這個專案的 `ys_memory` 設定；本版不自動輪替。停止載入時，只移除該專案 `.mcp.json` 的 `ys_memory` 項目並重新開啟工作；要使舊身分失效，另到 Hub 撤銷 Token。

## Token 成本與此次範圍

compact 啟動只提供兩個入口，明確要求用記憶時才取得指定 schema；讀歷史使用 `after_sequence`、`limit`、`max_bytes` 控制。本次 Claude 用 7 個工具步驟完成搜尋、三個 schema 與三次操作，沒有持續輪詢。這不能推算模型帳單節省比例；整個對話仍包含 Claude 自身工具與其他專案上下文。

已跑的是**本機原生接入及單輪讀寫**，沒有把 SDK 檢查當作原生模型結果。自動喚醒、跨電腦 DPAPI、Gemini/Grok 原生端與網頁一鍵入口不在這次通過範圍。Claude Desktop 的專案設定方式以[官方共用設定說明](https://code.claude.com/docs/en/desktop#shared-configuration)為依據。
