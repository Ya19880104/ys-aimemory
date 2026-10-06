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

## stdlib-safe Codex 安裝器的 exact-head CI

候選 `418173134fa1c6cce17e99830a5b5faebbc97475` 的兩次 CI 執行均於 attempt 1 完成，各自三個 job 全部 success：

| 執行（attempt 1） | windows-installer | sqlite | postgres |
| --- | --- | --- | --- |
| [Push 37418044541](https://github.com/Ya19880104/ys-aimemory/actions/runs/37418044541) | 449 passed、2 warnings | 1098 passed、53 skipped、3 warnings | 1394 passed、51 skipped、3 warnings |
| [PR 37418050461](https://github.com/Ya19880104/ys-aimemory/actions/runs/37418050461) | 449 passed、2 warnings | 1098 passed、53 skipped、3 warnings | 1394 passed、51 skipped、3 warnings |

限定本機測試為 **344 passed、2 warnings**。這是不同環境的結果，不能加成總數；skipped 仍是 skipped。此紀錄只更新前一來源檢查點對本候選尚待完成的 CI 狀態，不能證明公開安裝、原生執行或部署。

Codex 來源／bootstrap 鏈仍為 `3e6166789fa938afc58a78565c625fc73888acb9`／`d688fbfcd132ec8ed9b05937438320ab1c9b94a6`，bootstrap raw Git SHA-256 為 `edf5651aaae0a2cdf319d75b1bbdbf370972e7316f5cfa610d3873be518141a4`。

[`96177fe` 三項 Linux 失敗及 `a42630c` 成功修正](VALIDATION_2026-10-05.zh-TW.md)、[`c199d23` 第一次 failed／cancelled 與第二次成功](VALIDATION_2026-10-06.zh-TW.md)、[`38a49cf` 部署](VALIDATION_2026-10-06.zh-TW.md)，以及[已關閉的公開安裝失敗與已核發 Token 撤銷](VALIDATION_2026-10-06.zh-TW.md) 均不改寫。初次 `httpx` 回歸仍是 failed，後續限定 passed 有不同來源界線。

### C418 部署與全新公開安裝

部署後檢查點的本機候選、公開 PR18 head 與獨立確認的線上版本均為 `418173134fa1c6cce17e99830a5b5faebbc97475`。Stage 為 **1352 passed、93 skipped、3 warnings，251.18 秒**；promotion 通過 **483 項檢查，23.432 秒**，於 **2026-10-06 05:42:24.336493 UTC** 完成。回讀確認映像完全一致、應用程式／PostgreSQL 健康、TLS 通過、成對教學網址固定 C418、升級前備份可讀且前一版映像保留。

全新正常公開 Codex 安裝經真正的隱藏 Token 提示後 **passed**。公開收據與八個已安裝檔案符合來源／bootstrap／候選版本鏈及 **3600 秒／單一 turn／90 秒**限制；安裝器程序樹已退出、所屬 handle 已關閉。這只驗證安裝，不能證明模型 turn。

後續原生 guard 在聊天室 join／收訊前以 `cannot_hold_owned_process` **failed**。STOP 保留、未建立 binding、未送出 human stimulus。自動／原生收訊、完整讀取、回覆及原生 Job 退出為 **not_run**；完整 held-child 退出證據為 **failed**。官方停止通過；後續限定程序清單為空、已記錄程序身分不存在，但不將歷史退出證據升級為 passed。同一已核發及已安裝 Token 已撤銷（HTTP 303），以該已安裝 Token 配合嚴格 TLS 驗證得到 **HTTP 401**。試驗已關閉，不再重啟；較早被限流拒絕的閉包回讀仍保留。

全新 Cloud 自動收訊／無回覆完成、Gemini 完整原生生命週期、Claude／Codex／Gemini 同時對話與任務交接仍為 **not_run**。目前工具脈絡未提供必要的 Cloud／Gemini host 控制，不能推論整個帳號不可用。先前 Cloud 失敗仍為 failed；被特定 Auto 審查拒絕的 Claude adoption 未嘗試。PR18 維持 draft，不宣稱整體產品驗收通過。

### 第二次全新公開安裝與外層 Job 關閉

第二個全新公開安裝與八檔收據驗證，在同一 C418 部署及 S/B 安裝器版本鏈上通過。新的外部守衛以原子操作將公開收據程序建立於專屬 Windows Job 內，並保留根程序 handle。它在 join 前以 `HOLD_member_unavailable` 停止，未建立 binding、未送出人類測試訊息。原始固定錯誤子類未被記錄，因此原因仍未確認。

外層 Job 涵蓋五個程序，作用中程序數歸零、持有的根程序已退出、所屬 handle 已關閉。這份外層清理證據通過；原生收訊／完整讀取／回覆及接收器內層原生 Job 收據仍為 **not_run**。官方停止另外在專屬 Job 中執行並通過。同一已核發及已安裝 Token 已撤銷（HTTP 303），並在驗證 TLS 下遭拒（HTTP 401）。第二個 fixture 也已關閉，兩個失敗 fixture 均不會重啟。

外部守衛診斷屬私有測試工具工作，與產品 CI 分開。初始 deadline／GO 競態及 final callback 錯誤均在後續合成修正前保留。新的純來源 packet 不代表另一次安裝或原生驗收已完成。

## C418 的全新有界 Codex 原生生命週期

第三次獨立全新正常公開 Codex 安裝在 `418173134fa1c6cce17e99830a5b5faebbc97475` 上通過，使用不變的 S/B 安裝器鏈；八檔案收據與 **3600 秒／單一 turn／90 秒**限制均核對一致。一個全新 human 問題自動產生 **3 次原生 MCP 呼叫**：身分確認、完整 delivery 讀取及一則回覆。實際原生收據為 `passed/replied`，具有 `native_containment=windows_job` 與已驗證的原生程序樹退出；獨立 Hub 回讀對上同一 human／讀取／回覆收據，以及含本次 marker 的 324 字元回覆。沒有以追補模型提示或 SDK 替代來建立這項結果。

外層專屬 Job 的 **22 個程序**全部收束：active 為零、held root 已 signaled、Job 與所屬 handle 關閉。中繼資料辨識到 **16 個已觀察程序身分**；未觀察的身分仍為 **not_observed**。另行執行的官方停止及斷線 Job 也通過並收束各自程序樹。STOP 保留、binding 已 disconnected，native-active 狀態不存在。程序及服務端證據仍與實際原生收據分開。

同一已核發與已安裝 Token 已撤銷（HTTP 303）；使用該已安裝 Token 配合嚴格 TLS 驗證的認證檢查得到 **HTTP 401**。試驗現已關閉，STOP、journal 與原始嘗試均保留，不再重啟。

本紀錄的線上 Hub 與來源／CI／原生證據仍固定 C418。隨附的純文件修改具有不同的公開／本機 Git head，不代表新產品部署或另一次原生試驗。

這只通過本次觀察到的單一問題有界 Codex 流程。前兩次 guard failed／HOLD 試驗仍保留原結果及已關閉／撤銷狀態，個別清理證據不改寫。此候選的 Cloud 自動收訊／無回覆完成、Gemini 完整原生生命週期、三客戶端同時對話／任務交接、全新 peer no_reply、接收器重新啟動及無限期運行仍為 **not_run**。被特定 Auto 審查拒絕的 Claude adoption 未嘗試，不宣稱整體產品或 Token 成本驗收通過。
