# 驗證紀錄：2026-10-06 接續開發

[English](VALIDATION_2026-10-06.md) | [繁體中文](VALIDATION_2026-10-06.zh-TW.md)

本紀錄分開保存來源、CI、部署與原生證據。接手核對時，公開 PR18 是 `c199d235b0ed34f0dd684d42fbf40655d4bba9a3`，健康運行的 Hub 是 `a42630cbe55d7671c680777c3e60d8648d861f6e`。原交接中的 PR `96177fe` 與部署 `2472280` 已是歷史狀態，詳見[先前部署紀錄](VALIDATION_2026-10-05.zh-TW.md)。

## 接手基線的 CI

`c199d23` 的兩個 workflow 第一次執行均失敗，部分 job 取消；原紀錄完整保留。第二次執行各自通過三個 job：

| Workflow | Windows | Linux／SQLite | Linux／PostgreSQL |
| --- | --- | --- | --- |
| [Push，37365441050，第 2 次](https://github.com/Ya19880104/ys-aimemory/actions/runs/37365441050/attempts/2) | 438 passed、2 warnings | 1091 passed、49 skipped、3 warnings | 1387 passed、47 skipped、3 warnings |
| [PR，37365446803，第 2 次](https://github.com/Ya19880104/ys-aimemory/actions/runs/37365446803/attempts/2) | 438 passed、2 warnings | 1091 passed、49 skipped、3 warnings | 1387 passed、47 skipped、3 warnings |

上述結果只適用於 `c199d23`，不能套用到後續修改。`96177fe` 先前三項 Linux 失敗仍是歷史 failed；後續成功不改寫它們。Skipped 不算 passed。原交付 manifest verifier 對演進後的 checkout 仍為 failed，歷史 manifest 保留；另行執行的接續交接完整性檢查，29 個記錄檔案全部相符。

## 新來源修正

Claude 解除連線可在部分設定還原後重試：接受已完整還原的原始 MCP 項目，不重寫已還原的檔案，最後以檢查過的原子替換更新綁定中繼資料。項目被修改、身分不明、Hub 釋放／回讀失敗或操作鎖仍有效時，仍會停止操作，保留 STOP 與重試證據。限定本機測試為 **92 passed、2 warnings**；初次兩項失敗回歸案例保留。

Gemini 的 Windows CLI 程序現在以單一操作建立為暫停狀態並加入專屬 Job Object，修正父程序當機可能遺留未綁定子程序的空窗。清理時保留並等待根程序 handle，包含建立階段失敗。限定本機測試在 Windows 11／Python 3.12 為 **48 passed、2 warnings**；原始孤兒程序重現與中途清理失敗仍保留 failed。這是合成程序測試；真實 Antigravity 與其他 Windows／Python 版本為 **not_run**。

整合來源：`1cb0e39d72fcd160b32b1fba220a03f44dbfa56a`。Claude bootstrap：`aba9a41017a853917e2464611d2a9e05955d9bbc`，SHA-256 為 `cfaafb60a49e152bad65e05a3b078d38ec435c9a6a2d753e446961957ba8c8b5`。[成對安裝教學](AUTOMATIC_CHAT.zh-TW.md) 與聊天室產生命令使用此 bootstrap。Codex 既有的不可變來源／bootstrap 鏈不變。

## 此來源檢查點尚待完成

- 整合候選 CI 與部署：**not_run**。上方基線 CI 不能單獨作為新候選的部署依據。
- 全新公開 Codex 安裝與原生 MCP 生命週期：**not_run**。新有界測試必須證實依收據啟動、完整讀取、回覆、所有所屬程序退出、停止／斷線，以及撤銷同一個已安裝 Token。離線 helper 或 SDK 呼叫不能替代。
- Cloud 自動不回覆完成、Gemini 完整原生生命週期、三客戶端同時對話／任務交接：對這些修改仍為 **not_run**；先前 Cloud 失敗仍保留 failed。
- 被特定拒絕的 Claude adoption 操作未嘗試。已關閉／撤銷的舊測試、STOP 與 journal 均保留。

憑證、機器設定、私有收據及程序證據均保存在公開 repository 之外。


## `38a49cf` 的部署與 CI

候選 `38a49cff112dfbe000926041ce680a912ee2fb92` 的兩次 CI 執行均於第一次 attempt 通過：

| Workflow | Windows | Linux／SQLite | Linux／PostgreSQL |
| --- | --- | --- | --- |
| [Push，37415389253](https://github.com/Ya19880104/ys-aimemory/actions/runs/37415389253) | 448 passed、2 warnings | 1098 passed、52 skipped、3 warnings | 1394 passed、50 skipped、3 warnings |
| [PR，37415393313](https://github.com/Ya19880104/ys-aimemory/actions/runs/37415393313) | 448 passed、2 warnings | 1098 passed、52 skipped、3 warnings | 1394 passed、50 skipped、3 warnings |

整合本機 Windows 執行為 **1148 passed、2 skipped、3 warnings**。全新部署封包以拋棄式資料庫通過 **1352 passed、92 skipped、3 warnings**，接著通過 **478 項 promotion 檢查**。部署於 **2026-10-06 05:00:33 UTC** 完成。獨立回讀確認候選與映像完全一致、應用程式及 PostgreSQL 健康、TLS 健康檢查通過、成對教學網址固定此版本、升級前備份可讀且前一版映像保留。上述結果適用於 `38a49cf`，不能驗證後續來源版本。

## Codex 公開安裝器相依套件修正

在 `38a49cf` 上建立的全新有界公開安裝，**於隱藏 Token 提示出現前 failed**。未輸入 Token、未產生客戶端收據、未啟動接收器，也未建立聊天室綁定。安裝器程序樹已退出，所有所屬 handle 已關閉。專用已核發 Token 已撤銷，另外以驗證 TLS 的請求確認 HTTP 401。試驗已關閉，失敗與診斷紀錄保留；已安裝 Token 驗證與原生 MCP 生命週期為 **not_run**。

不帶憑證的重現在真正的 base Python 3.12 使用 `-I -S`，得到 `ModuleNotFoundError: httpx`：setup 在安裝專用環境前就載入接收器。來源 `3e6166789fa938afc58a78565c625fc73888acb9` 將 HTTP 載入移至執行時的接收器／斷線函式。初次失敗回歸保留；限定本機測試為 **217 passed、1 warning**，包含不含第三方套件的實際公開 setup 載入路徑。原有 transport-error 與斷線測試均通過。

Codex bootstrap `d688fbfcd132ec8ed9b05937438320ab1c9b94a6` 的 raw Git SHA-256 為 `edf5651aaae0a2cdf319d75b1bbdbf370972e7316f5cfa610d3873be518141a4`，固定上述來源；成對教學與聊天室指令使用相同版本鏈。此來源檢查點的修正版新 CI、部署、公開安裝及原生驗收仍為 **not_run**，前次部署或 helper 測試不能替代。

已關閉 Cloud 日誌的診斷使用獨立記錄的 callback／guard 時間窗，保留無法解析的行，不代表原生執行或完成，也不改寫先前 failed。全新 Cloud 自動收訊、Gemini 原生生命週期與三客戶端對話／任務交接仍為 **not_run**。目前工作階段未提供必要的官方 host／事件控制工具；這不代表整個帳號都無法使用。
