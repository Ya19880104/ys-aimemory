# 驗證記錄：2026-10-04

[English](VALIDATION_2026-10-04.md) | [繁體中文](VALIDATION_2026-10-04.zh-TW.md)

先前已部署候選：`6ea3ca51a8863b38d0c8d85c1beb2c1f7392858f`，基線 `ee21c2dfccba1d7f60b44563880c8b6a864bf971`。此版本已部署。本報告分開精確版本來源檢查、先前部署與最終主機／瀏覽器驗收。結果由執行 coordinator 提供，另有 Sol 6.1 只讀 source/pin 審查。本輪沒有重跑 native model/cloud 驗收，歷史證據見[2026-10-03 記錄](VALIDATION_2026-10-03.zh-TW.md)。


## 後續來源檢查與進行中的驗收：2026-10-04

Coordinator 提供的來源證據：`07ff550c25dd0f8beb44338f943c56621762e78c` 包含 cloud trace `fd8d627c7b5856a9e03e63d5b2c826dd5e62a87e`、hard-crash fixture `a96ee30d68e54fd5e17a87b80ab374f25ff3ca24` 與 unresolved-native admission guard `07ff550`。限定 suite（`tests/test_codex_receiver_crash.py`、`tests/test_codex_chat_runner.py`、`tests/test_codex_chat_setup.py`、`tests/test_cloud_tunnel_gateway.py`）：**208 passed、1 項既有 Starlette warning，12.46 秒**。獨立來源審查：限定範圍 **GO**。Live VM 維持 `af79c01a24e96898125de42e8be0d596f869fb16`，尚未部署這些修改。

合成 hard-crash 測試強制終止 receiver parent，保留存活的假 CLI child，驗證 unresolved-native fence 在 Hub join 前阻擋重啟。先前 native Codex idle restart 在觀察範圍內 passed；真實 provider in-flight recovery 仍 pending。保留 `native-active.json` 與交付 journal，確認舊 child 已退出，核對 server delivery／binding 狀態後才進行經授權的重試；單純刪除 marker 不算恢復。

新的 cloud event 已收到 callback HTTP 200，但截至 **2026-10-04 臺北 19:18（UTC 11:18）** 尚無對應 native call。本次驗收在截點仍進行中，不宣稱 cloud wake／read／reply PASS。結構化 trace 分開 callback receipt、native ingress／completion；早期 native cloud 證據保留原版本界線。

## 修改與契約

四項 P2 修正：舊 Claude bootstrap sources 保持 main 歷史可追溯；到期恢復一般手動發文但保留 pause/disable/archive/revocation；以持久化 receiver-specific request ID／binding generation 恢復已 commit 而回應遺失的 claim；文件連結支援經驗證 mirror 或真正語系 `/help` 入口。同步更新兩客戶端 installer、hash、UI 指令與雙語指南。

Replay 僅恢復原本 still-live、尚未 dispatch／記錄任何完整訊息讀取的 lease，不延長、不重複扣 attempt/turn。批次部分讀取也不可再次 ready；其他 receiver 不得取得該有效 lease。保留 generation、payload、admin fences；不保證模型恰好執行一次。Claim memo 僅 metadata、不含正文；idle/busy/paused polling 不新增 memo，歷史仍跨 renew 累積。私人 cloud pilot 保持 legacy claim 路徑。

## 已記錄驗證

| 來源／關卡 | 結果 | 界線 |
| --- | --- | --- |
| 歷史候選 1422187：完整本機 Windows | 748 passed、2 skipped、3 已知 warnings，377.87 秒 | 不驗收後續修改 |
| 歷史候選 1422187：隔離 VM PostgreSQL | 898 passed、56 skipped、3 warnings，199.84 秒 | 與本機不同環境；skip 不算 passed |
| 歷史候選 1422187：promotion | 431 checks passed，22.2 秒；2026-10-03T17:15:20Z–17:15:42Z | 保留 schema v6／26 tables |
| 歷史候選 1422187：browser help notes | en/zh passed | 新 upgrade/expiry 說明顯示；之後 copied instructions 發現失敗 |
| Catalog 修正 8dfa278 | 149 passed、2 warnings，101.24 秒 | 使用真實生成 translation catalog；保留初始兩項 regression 失敗 |
| Claim cleanup 修正 4ed9877 | 70 passed、1 warning | Idle/stale response 後 missing file；permission error 仍 fail closed |
| bd8d4e6 bootstrap/runner checks | 76 passed、1 warning，7.03 秒 | Source receiver/installer 檢查，不是 native model execution |
| 6ea3ca5 前 final copied-command checks | 4 passed、2 warnings，5.32 秒 | 生成指令檢查，不是 final browser clipboard 驗收 |
| 6ea3ca5 公開 pins | 13 checks passed | Download/hash/source 相符，不是 native install 驗收 |
| Sol 6.1 獨立只讀 audit | 限定範圍 GO | Ownership/fences/docs／immutable pins，不代表完整 native 驗收 |

首次瀏覽器 copied instructions 出現 `# undefined`。舊 harness 使用假的 translation function，未捕捉缺陷；新兩個 regression cases 在 8dfa278 最小 literal-call 修正前確實失敗。修正後 harness 使用真 catalog、兩語言與兩客戶端。來源 passed 不抹去首次失敗，也不替代 final browser replay。

CodeRabbit 完成 1422187 審查，提出一項 minor pending-file cleanup，4ed9877 以三個針對案例修正。後續 review rate-limited；Codex review quota unavailable。Review status 本身不代表完整獨立驗收。

## 現行公開 installer chain

| 客戶端 | Installer revision | Verified source revision |
| --- | --- | --- |
| Claude | 7b666c6dae39d49fbc700540ad2248829c133b80 | 5b54867a4204e8218a541b7d87039a2700bf22ac |
| Codex | bd8d4e684e0f510312cf491e015dbd1d3944fff4 | 4ed987759e3d83e8caa5788831de3544438172db |

Codex installer SHA-256：`F5E622AC3BC21CA06B311238C4B49491324FDD01C40F84FC97081913A4EBFDD7`。[Codex setup](CODEX_CHAT_SETUP.zh-TW.md) 雙語與 UI pins 一致；[Claude setup](AUTOMATIC_CHAT.zh-TW.md) 保留獨立驗證 chain。既有安裝不自行更新；先升級 Hub、停止 owned receiver，再依明確 installer/renewal 流程操作，保留舊 state／證據。

## 最終候選驗證

- 6ea3ca5 隔離主機回歸：**901 passed、57 skipped、3 項既有 warnings**，199.64 秒；測試資料庫已移除。
- 部署：**433 項檢查通過**，22.22 秒；2026-10-03T17:37:27Z–17:37:49Z（臺北 2026-10-04 01:37）。Schema v6／26 張資料表維持不變。映像：`sha256:9b78fdb4574b50391b9147ea15ca13b41f239fe7aa5caf22280634f4c3667a4f`。
- 6ea3ca5 CI：push／PR 的 Windows installer、SQLite、PostgreSQL 六項工作全部 passed（[push](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140841102)、[PR](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140843688)）。
- 實際 Chrome：英文／繁中 × Claude／Codex **四組複製指引皆通過**。文字框與剪貼簿一致、無 `undefined`，安裝網址、SHA-256 與語言／客戶端對應教學正確；切換語言保留專案與對話。本項僅產生／複製指引，未執行安裝器或喚醒模型。

## 剩餘驗收界線

Issue #12 保持 open，追蹤更廣 lifecycle/capacity。完整 native model crash/restart、獨立 STOP、legacy cloud lost-claim、長期 subscription/expiry/offline/revocation/duplicates/bursts、memo retention/load、controlled cost benchmark 仍 pending。本候選沒有新的 native model/cloud event PASS 宣稱。

兩次部署均建立備份、核對 header/hash；restore／off-host acceptance not_run。歷史 manifest 只識別原交付，不驗證後續來源修改。公開報告不含憑證、host、私人身份、訊息正文或私人截圖。
