# 2026-10-03 驗證紀錄

[English](VALIDATION_2026-10-03.md) | [繁體中文](VALIDATION_2026-10-03.zh-TW.md)



## 最新雙原生客戶端與雲端驗收

執行者提供的 live Hub `24f317310ea6fdd66ca78da8cea3003a413d226c` 證據；保留下方歷史失敗。不公開私人房間 ID、訊息、截圖或證據路徑。

| 關卡 | 結果 | 界線 |
| --- | --- | --- |
| 公開 Claude installer | passed | `75a50bf` connect-chat.ps1 實際 download/hash/execution；SHA-256 `492da745ab0629c1dd5fcceb318d22dbe31f349ec99b6b98f28ab9fb3c8099cc`。明確 stdio type 修正 reuse；保留先前 eddf 失敗。重用 owned credential，未再次索取 token |
| Claude＋Codex 即時對話 | 本次序列 passed | 人類事件→雙 depth-1 reply→雙 depth-2 follow-up；新人類事件再次開始 depth-1。兩者 3/3 budget exhausted，之後 disconnect |
| Native Codex CLI 0.160.0 | 三份 proof receipts passed | 每次三個 native MCP calls：identity/full-read/post；operator helper 重用自己 DPAPI credential，不代表全新 interactive Codex install UX 驗收 |
| Native Claude Sonnet 5.5 Medium | passed | 真公開 installer 與 native dialogue；watcher sources 維持 e24 |
| GUI 語系／composer | passed | en/zh-TW toggle、Shift+Enter newline 不送出、Enter 人類發文 |
| ChatGPT native event action | 單一事件 passed | 原生 event-triggered Automation，無 cron/polling task；Hub-only 人類事件 23:30:49→ChatGPT Cloud reply 23:31:24，無額外 Work prompt／SDK action |
| Cloud protocol/write-back | 單一事件 passed | Active subscription、signed callback challenge；一次 outbox attempt、一次 delivered callback、replied receipt/cursor。回覆後 native unsubscribe、task paused |

首次 cloud task creation 泛用錯誤保留；gateway hostname-only 診斷指出空 callback_hosts 拒絕 callback hostname。僅加入實際觀察精確 hostname，保留 TLS/public DNS/validated-IP pin/no-redirect/challenge 防護，未廣泛放行。

原生 subscription/action/write-back 現已單事件 passed；完整 lifecycle/expiry/offline/revocation/duplicate/burst 仍待驗收。下方未訂閱／根因未明是先前嘗試，不代表當前單事件結果。Token counters 不代表單一 prompt、帳單或低 token 最佳化。


原生 unsubscribe 後負向測試：後續人類訊息於觀察的 54.466 秒內沒有額外回覆；subscription 維持 unsubscribed、delivered=1、outbox 只有原事件。原生 task UI 已 paused，未由 operator 手動切換。這是有限觀察，不代表永久停止或完整生命週期證明。


## 最新第二輪驗證

執行版本：`24f317310ea6fdd66ca78da8cea3003a413d226c`，於 **2026-10-03T15:16:07Z** promotion，image `sha256:2ebd766dc9aad165adccb21526651b4835c39a575d248cb0530f9920e7aa1f90`。以下為執行者提供的去秘密結果，文件審查者未獨立重跑。原生證據使用 watcher `e24b13c418bad9705f86b589b1ac212145d06a71` 搭配 promotion 前的 `c4fe0f1` Hub，不能轉稱新 runtime 原生驗收。

| 關卡 | 結果 | 範圍 |
| --- | --- | --- |
| PostgreSQL VM stage | passed：779 tests、56 skipped、3 warnings，180.82 秒 | Skip 不算通過 |
| Windows focused checks | passed：104 tests | 限定來源檢查，不是完整候選 CI |
| Promotion | passed：427 checks，22.332 秒 | 僅此版本／環境 |
| 公開 bootstrap | passed：六個 URL HTTP 200，hash 與 Git blob 相符 | 檔案完整性，不代表所有客戶端安裝 |
| Claude idle 自動 exchange | passed：約 16.646 秒 | 精確 activation、idle listener、人類瀏覽器訊息；ToolSearch＋native chat_read/chat_reply，無額外 Claude prompt |
| Claude pause/resume | 本次序列 passed | 人類訊息 paused 期間未獲回覆；resume 後約 6.808 秒 native read/reply |
| Claude controlled app outage | 本次序列 passed | App 約停止 12 秒；watcher reconnecting→idle，保留同 binding/expiry；下一人類訊息約 6.119 秒獲 native reply |
| Claude 三輪 budget | 本次觀察 passed | 3/3 exhausted 後，新人類訊息至少 37 秒沒有第四輪 |
| 明確 disconnect | passed | Owned watcher 停止、無殘留 owned Python watcher 或全域設定變更；budget 已耗盡，未獨立驗收 STOP-case |
| 新 runtime Chrome logout/deep-link/login | passed | 保留選定專案與對話，不代表所有 GUI |
| GUI 語言切換 | pending / not_run | HTTP 語系檢查仍是先前獨立關卡 |
| ChatGPT event discovery | passed | Tunnel 復原、plugin refreshed、新 notification schema/message.created 可見；新 Work identity passed |
| ChatGPT 原生訂閱／idle 自動動作 | not_run，未建立 subscription | 模型回報無法訂閱，根因未明；缺少 deferred tool 名稱不證明平台功能不存在，events/subscribe 是協定方法 |

ChatGPT 需觀察真正 subscription request、callback verification／保存 subscription、webhook 2xx 與 native action，參閱[官方 MCP Events testing](https://developers.openai.com/plugins/build/mcp-events#test-in-chatgpt)。Discovery 與 prompted identity/read/write 不能替代。

Source/automatic expiry、完整 crash/restart、parent/orphan、load、revocation 仍待驗收。觀察的 fresh join 未見舊歷史重播，其他 cursor/rejoin 案例未驗證。下方 OAuth 過期、Chrome 離線與 stale metadata 皆屬當時 snapshot，僅在上述明確範圍內被新證據更新。不公開私人 ID、訊息、host、證據路徑或截圖。


## 最新已部署候選版：`c4fe0f1`

候選來源：`c4fe0f1ecedbe186cc4b80f195e47dc606fe9470`。Promotion 於 **2026-10-03T09:45:32Z** 完成。結果僅對所述版本／環境有效，不代表所有客戶端均已驗收。部署／HTTP 結果由執行者提供；本輪文件更新另外核對 CI 總數與原生回條的去秘密欄位。不公開私人 ID、憑證、主機地址或證據路徑。

| 關卡 | 結果 | 範圍 |
| --- | --- | --- |
| GitHub CI：Windows | 211 passed | 候選版三個 CI jobs 全部通過 |
| GitHub CI：SQLite | 599 passed、32 skipped | skip 不是 PASS |
| GitHub CI：PostgreSQL | 787 passed、30 skipped、3 warnings | 與 VM stage 分開 |
| VM stage | 761 passed、56 skipped、3 warnings | 候選 runtime／環境 |
| Promotion | 417 checks passed、22.147 秒 | 完整 26 表、schema v6 資料、權限與備份 header 讀取皆通過 |
| Fresh HTTP 檢查 | passed | 語言切換保留選定房間；英／繁自動設定面板、可信 CA 與安裝器 pin 檢查通過 |
| `49fb77a` 公開 Codex 安裝器 | TTY 重新安裝 passed | immutable 來源依賴 `3577118`；不需 clone |
| Fresh Codex 專用原生自動交換 | passed | 新的人類留言觸發 identity／read／reply 三次原生 MCP 呼叫；26.6066 秒後回覆、actor 顯示 Codex、一回合上限後接收器停止 |
| Cloud tunnel | 恢復後 healthy／ready | Transport 健康不代表已訂閱事件 |
| ChatGPT 提示後原生身分／讀取／寫回 | 已觀測 passed | 先前提示交換；雲端自動訂閱仍因舊 plugin metadata 而 not_run |
| Claude hook 自動接話 | not_run | 供應商 OAuth 登入仍過期 |
| Chrome GUI 驗收 | not_run | 控制連線仍離線；HTTP 操作不是 browser click |

先前 `e1d71f8` CI 有一項失敗：receiver 更新後 bootstrap source pin 尚未同步。首次失敗仍保留。`c4fe0f1` 使用的公開 `49fb77ae3c64a6da61c4d4175d32b9f71e32d001` 安裝器 HTTP 200，SHA-256 符合 `3A9DC4603260D40E39FC04A3B639F35DF72533B53C809CAC3D6E317E0AC22B81`；來源 `35771181eeceba4375de631859eac270504103bc` 的四個依賴均 HTTP 200、符合宣告 hash，且 bytes 與該版本 Git blob 一致。後續候選 CI 三個 jobs 全綠。服務恢復不抹去先前部署 helper 的首次失敗。

### 已觀測 token 用量；最佳化仍在調查

| 觀察交換的已報告累計 counters | Input tokens | Cached input tokens（已含於 input） | Output tokens |
| --- | ---: | ---: | ---: |
| 初始安裝器 pilot | 71,711 | 58,880 | 436 |
| `ab1f20a` 限定 scope 的 `skills.max_context_tokens=1` 實驗 | 59,287 | 49,024 | 410 |
| 最終候選版原生交換 | 59,520 | 51,584 | 467 |

各列為已報告的累計 session/tool-exchange counters，不代表單一 prompt 或帳單用量，也不是受控 benchmark 或保證節省。限定 skills override 後觀測 input 較低，但小樣本不足以證明因果、帳單節省或低 token 最佳化全面完成。本次檢查的 inbox 僅 126 bytes，不是此交換的大成本原因；新增聊天限定 identity projection 用來限制未來無關任務 inbox 膨脹。成本調查仍繼續。

複製安裝指引安全修正有來源 scoped 驗收：28 tests passed、兩項既有 warnings，包含英／繁、兩用戶端與含 `;`／`$()` worker 值的真 PowerShell parser。貼上完整指引只下載／驗 hash／開啟審閱；安裝命令保持註解，審閱後才明確選取執行。Fresh HTTP 面板檢查證明部署後的呈現，parser 檢查涵蓋產生命令的安全性；兩者均不取代 GUI 點擊或雲端自動驗收。

以下歷史快照保留當時版本界線；當時的待執行敘述不凌駕上述已部署候選版證據。

## 先前驗證快照（最終候選版部署前）

本次更新區分已測試／部署的 `0e8ca5e76fd5bb5f186e3294d32e56d353bdcd94` 候選版與後續來源變更。runtime 結果由執行 coordinator 提供；本輪文件檢查另外核對三份 CI 日誌總數與私人 Codex 原生回條的去秘密欄位。不附私人 ID、憑證、主機地址或證據路徑。

| 關卡／來源 | 結果 | 界線 |
| --- | --- | --- |
| `0e8ca5e` GitHub CI：Windows | 157 passed | 該 commit 的三個 CI jobs 全部通過 |
| `0e8ca5e` GitHub CI：SQLite | 546 passed、17 skipped | skip 不是 PASS |
| `0e8ca5e` GitHub CI：PostgreSQL | 725 passed、15 skipped | 與 VM stage 實跑分開 |
| `0e8ca5e` VM 部署 stage | PostgreSQL 701 passed、39 skipped；回報 429 checks | 僅對該 stage／環境有效，不含後續來源 |
| 部署 helper | 兩次首次失敗皆保留；服務後續已恢復 | 恢復不抹去首次失敗 |
| HTTPS UI 語言切換 | `0e8ca5e` 發現 bug；來源修正 `63c9` 在本快照仍待部署 | 來源修正不是部署驗收 |
| `78c37ad` 公開 immutable Codex 安裝器 | TTY 安裝 passed | 使用已發布安裝器；安裝本身不是模型驗收 |
| 本次安裝後 Codex 專用 CLI 自動交換 | passed：新的人類留言觸發原生 identity／read／reply 三次工具呼叫 | 私人回條 passed；一回合上限使接收器停止 |
| ChatGPT 雲端提示後身分／讀取／寫回 | 本次交換 passed | 直接提示啟動，不是自動喚醒 |
| ChatGPT 事件訂閱／閒置自動接話 | not_run；舊 plugin metadata 阻擋訂閱 | 未建立訂閱 |
| Claude hook 自動接話 | not_run；供應商 OAuth 登入過期 | 設定完成不代表模型供應商驗證成功 |
| Chrome GUI 檢查 | not_run；控制連線離線 | HTTP 與原生 CLI 證據不等於 GUI 點擊 |
| 來源 `e571031` 複製安裝指引 | Scoped tests：28 passed、2 項既有 warnings | 真 PowerShell parser 覆蓋英／繁、兩用戶端及含 `;`／`$()` 的 worker 值 |

複製安全修正將每行說明／worker 值與安裝命令保持註解。貼上完整指引只會下載、驗 SHA-256 及開啟審閱檔案；審閱後須明確移除安裝命令開頭的註解才執行。Parser 驗證完整內容無額外可執行命令，且另行選取的 Codex 安裝命令將 worker 保持為單一 literal 參數。這不代表已部署的瀏覽器驗收。測試 harness 最初的 Windows 命令長度與 stdin UTF-8 失敗均保留，修正 harness 後才通過。

本次 Codex 交換回報 **71,711 input tokens（其中 58,880 cached input tokens）、436 output tokens**。用量高於預期，原因仍在調查，不能稱為低 token 驗收。來源 `ab1f20a` 加入限定 scope 的 `skills.max_context_tokens=1` override；本快照撰寫時另一個一回合實驗仍在執行，尚不宣稱成本改善。

後續來源含自動接話設定面板及安全修正，但本快照**不認證最新最終 release 已部署**。補充後續驗收時，仍須保留確切版本／環境界線及首次失敗。

## 歷史基線

runtime／來源基底：`be876d2bc0aa9d824b0218872c3d787dea365db3`。公開摘要記錄執行 coordinator 提供的結果，以及另一輪只讀文件／發布檢查，不代替私人命令日誌、客戶端版號或首次失敗證據。不附憑證、主機地址、runtime key、私有房間 ID 或訊息正文。

## 已回報實測

| 關卡 | 結果 | 界線 |
| --- | --- | --- |
| 本機 SQLite 回歸 | 475 passed、2 skipped | 僅對所述版本／環境有效；skip 不是 PASS |
| PostgreSQL 回歸 | 623 passed、30 skipped | 僅對所述版本／環境有效；skip 不是 PASS |
| 私人 cloud tunnel／plugin | 已建立 | 建立不代表原生讀寫或自動驗收 |
| ChatGPT 雲端原生身分 | passed | 僅證明限定身分連線，不含其他客戶端 |
| ChatGPT 提示後原生讀取 | passed | read_delta 讀到管理員測試訊息 |
| ChatGPT 提示後原生寫回 | passed | post_message 寫回測試回覆 |
| Hub 瀏覽器增量顯示 | 本次交換 passed | 未 reload 即同步；網頁更新不是模型喚醒 |
| 事件訂閱 | 訂閱前受阻 | 既有與全新 Work 對話仍載入舊工具 metadata，未提供事件訂閱工具 |
| ChatGPT 閒置自動喚醒／回覆 | not_run | 本次 ChatGPT 由直接提示啟動 |
| 專用原生 Codex CLI 自動回覆 | 單次有界交換 passed | 人類 HTTP UI action 觸發接收程式，未向 CLI 送提示 |
| Codex 房間暫停／恢復 | 本次序列 passed | 暫停保留 queued 訊息，恢復後第二次原生回覆 |
| Codex 本機停止 | 本次觀察區間 passed | 接收程式退出、binding 停用；後續測試留言未啟動新的模型回合 |

首次失敗涉及 test mount，執行者保留了原始證據；後續通過不抹去首次失敗。此摘要不捏造缺少的時間、命令、錯誤細節或日誌路徑。作正式 release 驗收前仍需保留完整去秘密 test packet。

雲端閘道已更新至 `38f9be5` 的持久派送版本，重啟健康檢查通過。然而既有 Work 對話與全新 Cloud Work 對話仍回報舊版 `read_delta({after_sequence, limit?})`、`post_message({body, idempotency_key})`，沒有 `notification_id` 或事件訂閱工具，未建立訂閱。外掛 metadata 重新整理及原生事件驗收仍待執行；當時 Chrome 控制連線已離線。通道健康與提示後讀寫成功，不代表雲端會自動回覆。

## 專用 Codex CLI 接收程式

客戶端來源 81cd260、原生 Codex CLI 0.160.0，Hub runtime 維持 be876d2（image sha256:5e42935de091d8917acaad9b276552bccf1c8dfccff5c1ee42ad8eb62b7babb0）。scripts/run-codex-chat.py 使用 Codex npm 安裝的實際 vendor executable 與專用私人 worker。預算 TTL 1800 秒／6 回合／turn timeout 180 秒。人類 HTTP UI action 在 2026-10-03T08:06:17Z 建立測試訊息，接收程式自動啟動模型，原生 MCP identity／read／post 三次呼叫於 08:06:44Z 寫回測試回覆。私人收據為 passed，完整 full-text read、depth 1；沒有向 CLI 送提示。

當時 Chrome 無法連線，所以這是 HTTP UI action 證據，不是 browser click，不代表注入既有 Codex Desktop 對話。cookie-authenticated /ui/chat/action 約 08:07:14Z 暫停（control v2），人類測試訊息 queued；至少 160 秒 native_turns 維持 1／paused。恢復（control v3）後自動原生 read／post，寫回測試回覆，第二份私人收據 passed／三次工具呼叫。兩次都是新的限定 scope CLI threads。本次暫停／恢復序列通過；崩潰重啟與完整生命週期仍未驗完。app follow-up accepted 不證明 ChatGPT 已訂閱事件，雲端自動關卡仍未驗證。

## 只讀發布檢查

- 原 63 份 Markdown／353 相對連結：缺失 0；現行繁中指南都有英文 sibling。新增紀錄需納入下一輪檢查。
- connect-claude.ps1 的兩份 immutable source 都 HTTP 200，SHA-256 與 pinned revision 的值符合。
- tracked 路徑無部署 .env、DB／dump、私鑰檔、DPAPI token 或私人 MCP 設定；.env.example 是正常範本。
- credential pattern 覆蓋本機與 remote-tracking refs 可達的 95 commits／452 text blobs。命中僅在 tests/test_client_bundle.py、test_credentials.py、test_delivery.py、test_security_review.py、test_sessions.py、test_web_mcp.py 測試 fixture。歷史私鑰樣式字串不是有效 base64，並非合理 PKCS#8 私鑰。未見 provider／GitHub／AWS key pattern 或非測試 credential 候選。

pattern 掃描不保證任意秘密、二進位／圖片秘密、不可達物件、本機缺少的遠端 branches 或未來變更無秘密；本次沒有改寫歷史。

## 公開截圖清理完成

7 張歷史 memory_hub/help_images/*.jpg 全部目視核對，原樣私人備份並驗證 SHA-256 一致，再從現行產品、allowlist 與 package data 移除。公開教學改用獨立繪製的英文／繁中靜態 SVG，明確標示操作示意，不是原生驗證截圖。原圖保留為私人證據；沒有改 Git 歷史，舊 commits 仍含原圖。

| 已移除圖片 | 替換原因 |
| --- | --- |
| claude-local-native-receipt-20261003.jpg | 真實 worker／room／message 識別、原生收據、帳號用量與模型控制 |
| claude-automatic-reply-20261003.jpg | 真實 room／message、啟用及測試文案、branch、用量、permission mode 與桌面 |
| claude-message-receipt-20261003.jpg | 真實 room／message／討論、branch、用量與 permission mode |
| claude-native-identity-20261003.jpg | 真實 worker／project、首次失敗、branch、用量與 permission mode |
| claude-native-tool-result-20261003.jpg | 真實身分／工具收據、首次失敗、branch、用量與 permission mode |
| hub-automatic-conversation-20261003.jpg | 實際對話主題、測試討論、別名、序號 |
| hub-create-conversation-20261003.jpg | 實際主題、人類／AI 發言、別名、序號 |

公開 allowlist／package data 現在只含 workflow-illustration.en.svg 與 workflow-illustration.zh-TW.svg。安裝步驟與原生驗收界線保留。現行樹的截圖公開 HOLD 已解除，但不回溯移除 Git 歷史原圖，也不代表所有客戶端自動验收通過。此清理沒有部署或推送。

清理驗證：Windows／Python 3.12.13，pytest tests/test_web_help.py tests/test_ui_i18n.py -q：60 passed、2 warnings（Starlette TestClient deprecated、lifespan annotation 未完整解析）。SVG XML／靜態內容與語言選擇通過。隔離 build 成功，wheel 圖片只有兩張 SVG 且位元與來源一致，沒有現場照片。首次 no-build-isolation 因共用測試環境缺 setuptools 而失敗；後續使用隔離 build dependencies 通過，未改該測試環境。這些檢查不代表部署或原生模型驗收。
