# 驗證記錄：2026-10-04

[English](VALIDATION_2026-10-04.md) | [繁體中文](VALIDATION_2026-10-04.zh-TW.md)

本報告分開記錄來源檢查、部署及原生／瀏覽器驗收的版本界線。先前候選 `6ea3ca51a8863b38d0c8d85c1beb2c1f7392858f`（基線 `ee21c2dfccba1d7f60b44563880c8b6a864bf971`）曾在下方較早一輪檢查中部署；後續結果見下一節。較早的原生證據保留於[2026-10-03 記錄](VALIDATION_2026-10-03.zh-TW.md)。


## 後續候選來源與 Gemini 原生證據

候選來源 `8e7267f323e54c7b6f7731df866f9c9a7396e214` 與 live `7652f1d7f04ef4c00e8860217a0f732f98dcb58e` 分開。三項限定修正通過獨立審查：CLI 建立程序失敗、尚無 child 時，僅移除本次新建的 native-active marker；receiver journal 沒有任何先前 native attempt 時，才重試到期的 stale claim，保留有歧義的舊 journal；cloud subscription 遇允許清單內的 terminal reservation conflict 時停止，未知失敗則保留 request identity。這些是來源／fixture 結果，不是已部署恢復驗收。

在該精確候選僅執行一次隔離本機 Windows 完整 suite：**868 passed、2 skipped、3 warnings，422.92 秒**，exit 0，2026-10-04T13:32:03Z–13:39:11Z（臺北 21:32–21:39）。Stderr 為空，clone 維持 clean。兩項 skip 需要明確 opt-in 的可拋棄 PostgreSQL runtime；warnings 分別涉及 Starlette/httpx、Pydantic 未解析的 lifespan forward reference，以及 per-request cookies。本 suite 未執行 provider 或真實線上資料庫測試。

候選 Codex bootstrap 固定為 `2ab108a6522fe77617f68e198756121e408a0677`，四個來源檔固定於 `c8d32664b4970688e42d6532533611ca8322155a`；raw SHA-256 為 `54d7027effd8fa36f0ef5b424ca543b96142a9dd145e8f0e1bdc6778ddf47f84`。獨立 Git object 核對確認四個來源 hash，以及 UI／英文／繁中 consumer 的 revision／hash pins 相符。此本機完整性檢查不證明公開下載可用或安裝器完整執行；下方已部署 installer chain 保留獨立版本界線。

Coordinator 提供的 live 7652 原生證據確認 Gemini 連續 B、C 訊息：human sequence 55 → native reply 56，再 human 57 → native reply 58，均為 attempt 1，網站送出至回覆約 14、15 秒。兩則均使用實際 native `chat_read` 與 `chat_reply`，網站送出與回覆之間沒有手動 model prompt。Native UI、Hub replied 收據與兩筆 durable replied journal attempts 一致。此限定 fixture 的**連續原生收訊 passed**，不驗收後續候選修正。

**同 binding idle restart failed／incomplete**：切換 config 未重啟 host plugin；owned receiver 退出後，deadline 前未出現替代 receiver，不宣稱第三則回覆。獨立 deadline guard 已關閉新 fixture：寫入 STOP、移除 owned plugin／config、停用 binding，無 owned receiver 存活，cursor 58、turns 2 of 3、最新 delivery replied。較早的 permission-wait fixture 也已關閉，保留到期回覆失敗與原 journal，未重播。觀察到的 UI 與 bundled guidance 不同，支援的 live plugin reload／安裝路徑仍未驗證。

Gemini 正式 task／source／artifact／attachment 交接 **not_run**；同時三客戶端驗收 **not_run**。Cloud 自動事件在較早一輪仍為 **failed**，與 Gemini 本機原生 passed 分開。本補充不推進 live deployment、更廣 crash recovery 或 overall product acceptance。

## 現行部署來源與 installer chain

Live source：`7652f1d7f04ef4c00e8860217a0f732f98dcb58e`；image：`sha256:d4d2f2800c9f9c090f631aed807e7882aa7cbdfc1b15cc2b13765c1d81d2cab4`。隔離部署主機 suite：**1,010 passed、63 skipped、3 warnings，232.17 秒**。Promotion：**454 checks passed**，2026-10-04T11:45:02.755408Z–11:45:26.279132Z。保留 schema 6；26-table 比對僅允許 `web_auth_entries` 到期清理。已檢查 backup headers／hashes，restore／off-VM acceptance **not_run**。候選 CI：Windows **268 passed、1 warning**；SQLite **817 passed、32 skipped、3 warnings**；PostgreSQL **1,043 passed、30 skipped、3 warnings**。不同環境結果分開，skip 不算 passed。

現行 Codex bootstrap：`31a1db36e04d304c3e2823b31d5b175ab17e87e2`；四個來源固定為 `bd25c375bc6046c1cfbe488c859cde2c7e8a3421`；raw bootstrap SHA-256：`1a03b5a79ef9242f197962527320f5146ebdbb52b3619273afe44c2d94906e7c`。公開 raw bytes／四個 hash 均核對相符，published runner 在 join 前檢查未釐清 native state。線上 guide／clipboard 的 URL／hash 相符，仍須明確啟用。Python `setup.install` native-client preparation 路徑已測試，但下載的 PowerShell bootstrap 完整執行 **not_run**。Hash／準備通過不代表 native model delivery。Claude chain 另行保留：bootstrap `5f9400802ecdfe98f350a25a1f6848e1cf5ba1d0`、source `b168876f00f85ccb37e97bb11c3678d8cb9e6ae4`，與已部署 Claude guide 相同；不推導新的 Claude end-to-end 驗收。

Coordinator 提供的 native 證據：2026-10-04 臺北 20:17，實際 official Codex CLI 到達 tool_read gate，child 仍存活。強制終止實際 receiver，以相同參數／state 重啟，於 unresolved-native guard 以 exit code 1 停止。Binding、delivery、generation、turns（1 of 3）與 attempt（1）維持不變。Owned Job 程序全部停止，新 binding 已停用，cleanup errors 為空。限定真實 provider in-flight fence **passed**；post-commit-unknown 與完整 automatic resume **not_run**。獨立複核確認 before／after、六份 state hash 與受控程序識別證據相符。準備使用程式化 setup.install，未執行 PowerShell bootstrap。該較早截點的 Gemini 結果仍 pending；後續限定原生證據另記於上方。PR18 維持 draft、#12 open，不宣稱 overall product PASS；後續 native 結果須另附精確版本補充。

## 後續來源檢查與 cloud 最終驗收：2026-10-04

首次較完整 CI／staging 在 `bd25c375bc6046c1cfbe488c859cde2c7e8a3421` 的安裝來源 pin 檢查失敗：修正版 receiver 與舊 bootstrap 雜湊不符。已保留失敗，未升級該候選。Bootstrap 現在固定使用 `bd25c37` 的四個來源檔；網頁產生器與雙語教學固定下載 bootstrap `31a1db36e04d304c3e2823b31d5b175ab17e87e2` 並核對 SHA-256。完整性測試仍核對檔案，可於 shallow checkout 與無 Git 的 release archive 執行。修正後的 bootstrap、產生指令及教學檢查為 **70 passed、2 warnings，47.32 秒**；最終 7652 CI／部署結果另記於上方。

Coordinator 提供的來源證據：`07ff550c25dd0f8beb44338f943c56621762e78c` 包含 cloud trace `fd8d627c7b5856a9e03e63d5b2c826dd5e62a87e`、hard-crash fixture `a96ee30d68e54fd5e17a87b80ab374f25ff3ca24` 與 unresolved-native admission guard `07ff550`。限定 suite（`tests/test_codex_receiver_crash.py`、`tests/test_codex_chat_runner.py`、`tests/test_codex_chat_setup.py`、`tests/test_cloud_tunnel_gateway.py`）：**208 passed、1 項既有 Starlette warning，12.46 秒**。獨立來源審查：限定範圍 **GO**。該較早來源檢查截點的 live VM 為 `af79c01a24e96898125de42e8be0d596f869fb16`；上方後續 7652 promotion 已更新部署狀態。

合成 hard-crash 測試強制終止 receiver parent，保留存活的假 CLI child，驗證 unresolved-native fence 在 Hub join 前阻擋重啟。先前 native Codex idle restart 在觀察範圍內 passed；限定 fence 以外的完整真實 provider in-flight recovery 仍 pending。保留 `native-active.json` 與交付 journal，確認舊 child 已退出，核對 server delivery／binding 狀態後才進行經授權的重試；單純刪除 marker 不算恢復。

新的 cloud 最終驗收：首次 callback attempt 在 **2026-10-04 臺北 19:17:16（UTC 11:17:16）** 收到 HTTP 200；native task UI 回報 last_run 19:17:17，這不是執行證明；手動提示前，截至 19:20:20 未觀察到 gateway native read／post ingress。本次自動事件讀取／回覆 **failed**。明確的手動診斷提示後，19:20:36 出現 native `read_delta`／`tool_read`，19:20:42 出現 native `post_message`／`replied`。手動 native 讀寫 **passed**，與失敗的自動關卡分開。Trace 時間與相同 fingerprint 可區分 callback、首次 native ingress 與 receipt milestones，無須公開訊息正文或私人識別碼。

Task 在 19:20:45 暫停、19:20:50 unsubscribe；runtime 於 19:21 後停止，已確認程序退出。第二個事件與 restart 驗收 **not_run**。本輪 native UI tool-metadata refresh 失敗，但手動 native tools 仍可用。根因仍未釐清，範圍介於自動 task context 與首次 tool call 之間；未確認外部原因。歷史 native cloud 證據保留原版本界線。

## 歷史修改與契約

四項 P2 修正：舊 Claude bootstrap sources 保持 main 歷史可追溯；到期恢復一般手動發文但保留 pause/disable/archive/revocation；以持久化 receiver-specific request ID／binding generation 恢復已 commit 而回應遺失的 claim；文件連結支援經驗證 mirror 或真正語系 `/help` 入口。同步更新兩客戶端 installer、hash、UI 指令與雙語指南。

Replay 僅恢復原本 still-live、尚未 dispatch／記錄任何完整訊息讀取的 lease，不延長、不重複扣 attempt/turn。批次部分讀取也不可再次 ready；其他 receiver 不得取得該有效 lease。保留 generation、payload、admin fences；不保證模型恰好執行一次。Claim memo 僅 metadata、不含正文；idle/busy/paused polling 不新增 memo，歷史仍跨 renew 累積。私人 cloud pilot 保持 legacy claim 路徑。

## 歷史已記錄驗證

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

## 歷史公開 installer chain：較早 6ea3 檢查

| 客戶端 | Installer revision | Verified source revision |
| --- | --- | --- |
| Claude | 7b666c6dae39d49fbc700540ad2248829c133b80 | 5b54867a4204e8218a541b7d87039a2700bf22ac |
| Codex | bd8d4e684e0f510312cf491e015dbd1d3944fff4 | 4ed987759e3d83e8caa5788831de3544438172db |

Codex installer SHA-256：`F5E622AC3BC21CA06B311238C4B49491324FDD01C40F84FC97081913A4EBFDD7`。在該較早截點，[Codex setup](CODEX_CHAT_SETUP.zh-TW.md) 雙語與 UI pins 一致；[Claude setup](AUTOMATIC_CHAT.zh-TW.md) 保留獨立驗證 chain。既有安裝不自行更新；先升級 Hub、停止 owned receiver，再依明確 installer/renewal 流程操作，保留舊 state／證據。

## 歷史候選驗證：6ea3

- 6ea3ca5 隔離主機回歸：**901 passed、57 skipped、3 項既有 warnings**，199.64 秒；測試資料庫已移除。
- 部署：**433 項檢查通過**，22.22 秒；2026-10-03T17:37:27Z–17:37:49Z（臺北 2026-10-04 01:37）。Schema v6／26 張資料表維持不變。映像：`sha256:9b78fdb4574b50391b9147ea15ca13b41f239fe7aa5caf22280634f4c3667a4f`。
- 6ea3ca5 CI：push／PR 的 Windows installer、SQLite、PostgreSQL 六項工作全部 passed（[push](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140841102)、[PR](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140843688)）。
- 實際 Chrome：英文／繁中 × Claude／Codex **四組複製指引皆通過**。文字框與剪貼簿一致、無 `undefined`，安裝網址、SHA-256 與語言／客戶端對應教學正確；切換語言保留專案與對話。本項僅產生／複製指引，未執行安裝器或喚醒模型。

## 剩餘驗收界線

Issue #12 保持 open，追蹤更廣 lifecycle/capacity。完整 native model crash/restart、獨立 STOP、legacy cloud lost-claim、長期 subscription/expiry/offline/revocation/duplicates/bursts、memo retention/load、controlled cost benchmark 仍 pending。上方 7652 的限定原生崩潰防重送 PASS 不涵蓋這些待驗項目；cloud 自動事件仍未通過。

上述歷史部署均建立備份、核對 header/hash；restore／off-host acceptance not_run。歷史 manifest 只識別原交付，不驗證後續來源修改。公開報告不含憑證、host、私人身份、訊息正文或私人截圖。
