# 驗證紀錄：2026-10-05

[English](VALIDATION_2026-10-05.md) | [繁體中文](VALIDATION_2026-10-05.zh-TW.md)

證據截至台北時間17:10:17，包含17:07部署及隨後的瀏覽器核對。部署與原生客戶端測試分開記錄版本。先前試驗保留在 [2026-10-04 紀錄](VALIDATION_2026-10-04.zh-TW.md)；本頁更新目前部署狀態，不改寫歷史結果。

## 目前部署與說明連結核對

來源 **`2472280979733d4d08a1498b9318dba725209dff`** 已於台北時間 **17:07:25.683792** 完成一次promotion，**22.127秒 passed**；映像為 `sha256:5d3b1c78b153b56c7c7ccc3c3cc13ee3aae8882d07f18b222621d39cfe53c116`。**469項promotion checks全部passed**，備份、schema6、26tables、資料及package／image guards仍通過。部署前的隔離套件為 **1,254 passed／74 skipped／3 warnings，238.31秒**，disposable DB已移除。

本次將網站Cloud指南連結改為目前指南的固定版本；實際Chrome載入英繁 `/help` 後，兩種語言的Cloud指南連結都核對passed。此說明連結更新不新增原生接話驗收，也不改變下方公開安裝試驗使用Hub `fadee9d` 的版本界線。

該版本CI分別為Windows **358 passed／1 warning，13.46秒**；SQLite **1,017 passed／34 skipped／3 warnings，146.02秒**；PostgreSQL **1,296 passed／32 skipped／3 warnings，224.31秒**。不同環境counts不相加；下方歷史失敗及原生／Cloud限制均保留。

## 已部署的收據與客戶端修正

前次來源 **`fadee9d36025d6309c59859d48bacc86e9bcaacd`** 已於台北時間 **16:39:07.131–16:39:29.778** 執行一次promotion，**22.647秒 passed**。映像 `sha256:328c1dc26ef3fb91388085b0e4844a744d27aef2940288630bff47a1498c32e8`；**469項promotion checks全部passed**，備份、schema6、26tables、資料及package／image guards均已核對。封裝符合 **194個raw Git來源成員**。

Product修正來自來源 `7087bbf1beca7ba1d7965cd46ef9ab0315bdfd26`：只在真正read-budget錯誤時重試一次較大讀取，先驗證自動Cloud回覆收據再記錄完成。成功訊息提到錯誤不會觸發retry；收據不符時保留原請求意圖，不假稱成功或自動重送。這些修正不能解釋或證明已解決Cloud試驗缺少native event-tool呼叫的問題。

| 最終來源關卡 | 結果 | 範圍 |
| --- | --- | --- |
| CI Windows | 358 passed | Windows安裝器檢查 |
| CI SQLite | 1,017 passed／34 skipped／3 warnings | 獨立CI資料庫環境 |
| CI PostgreSQL | 1,296 passed／32 skipped／3 warnings | 獨立CI資料庫環境 |
| 部署主機隔離套件 | 1,254 passed／74 skipped／3 warnings；242.51秒 | Isolated stage，不是native client驗收 |
| 公開發布檔案 | 兩個bootstrap URL及九筆source entries均HTTP200，精確raw-byte hashes相符 | 公開位元組，不是安裝執行 |

安裝鏈固定上述product來源及bootstrap `07d575a3bce654bf572b430609a467d1879c6fc9`。16:39部署checkpoint時，全新公開互動安裝仍 **not_run**；之後的installation-only結果另記於下方。不同環境的counts不相加；skip及warning均保留。

先前 `7087bbf` CI在各環境都因過期bootstrap source assertion失敗：Windows **357 passed／1 failed**、SQLite **1,016 passed／1 failed**、PostgreSQL **1,295 passed／1 failed**。首次失敗與最終passing runs分別保留。原本local checks也分開：bridge／runner **127項**、gateway **120項**、client／bootstrap bundle **52項**、web／help／language **153項**。Deployment不將下方歷史native／Cloud結果升格成新版本驗收。

## 公開Codex僅安裝關卡

台北16:55:33，新的Windows安裝透過官方公開 `07d575a` bootstrap **passed**，下載四個固定 `7087bbf` 來源檔，連向Hub `fadee9d`。實際terminal的stdin／stdout為interactive，使用真正隱藏 `getpass` 提示，沒有替代或monkeypatch；操作員私下輸入新的測試worker Token。實測使用 `-Print`、明確核對的Codex／Python3.12執行檔、繁中、一小時、三回合及90秒turn timeout。

Installer exit0、REST worker／room核對passed，實際建立venv及pip dependencies、以目前使用者DPAPI保存憑證，八個安裝檔hash均passed。Installed官方 `--receipt --print` 也passed；receiver state目錄不存在，沒有Hub join或model turn。網站複製指令另通過bootstrap／hash／worker核對。這是真正互動installation關卡，不是native chat端到端驗收，也不證明預設PATH、自動啟動、全新帳號或無人值守安裝。

16:56:12，官方worker revoke回HTTP303；issued Token與installed DPAPI憑證相同，之後以同一Token做read-only authentication回HTTP401。測試憑證cleanup **passed**，受保護的local安裝檔保留為證據。此安裝的fresh native chat端到端仍 **not_run**。

## 已部署無回覆完成與有界原生試驗

來源 `6c359c5a7e8be2b9aab86de648ed1a7d3e3a4433` 已於台北時間14:19部署；映像 `sha256:ece6cf03802f28c81d431d3c747fc363d198df3461394135c1ecf938f567d551`。CI 記錄 Windows **351 passed**、SQLite **992 passed／34 skipped**、PostgreSQL **1,271 passed／32 skipped**；這是不同環境，不相加，也不是 Token 對照測試。部署主機隔離套件為 **1,229 passed／74 skipped**。Promotion V2 **23.024秒 passed**，保留 schema6、26tables、資料、package／image pins及備份。第一次 promotion 因私有檢查器仍預期38工具而在maintenance前失敗，原失敗保留；V2比對精確新舊工具集合，只允許新增 `complete_session_delivery`。

當時部署的公開安裝鏈使用來源 `a614e2d24e35734bfb0c64b1158a629689b30441`、bootstrap `ff7c276a763cfa6b4f6dad56e6b91426f941efd6`；實際公開下載符合兩個 bootstrap及九筆來源 entries。這只證明公開檔案位元組，不是全新公開互動安裝器 passed。試驗的 Codex 客戶端使用該來源、Gemini 使用已部署版本，product code一致。

一次有界Codex／Gemini試驗中，兩端自動回覆兩則人類問題，並各自全文讀取另一個AI的第一則回覆，以原生 `no_reply` 完成、不另貼確認訊息。兩端各三份原生完成及終端server收據均已核對。Gemini第二題工具輸出於稍後檢視，沒有新prompt或replay：已讀未截斷且ready，實際發文回傳 `replied`。這通過了所觀察的雙題及peer無回覆完成序列。

兩端各用了三回合：兩則人類問題及一次同儕完成；沒有另貼同儕確認訊息，silent completion也不退還已扣turn。預算用完後，網站顯示沒有active receiver。Codex guard已確認STOP、owned exit及disconnect；Gemini STOP與binding停用已核對，之後兩次精確kernel核對確認先前捕捉的guard身分已退出。這不證明未捕捉的receiver／probe身分、所有descendants或獨立persistent MCP連線已閉合。此有界觀察不證明無限運作、三客戶端驗收、Cloud no_reply或Token節省；下方歷史失敗不改寫。

## 四工具更新後的雲端試驗

既有外掛經官方重新整理、頁面更新及新對話後提供四工具，原生身分相符。新有界任務已訂閱，第一則網站新事件的 callback 收到 HTTP 200，但到期前沒有模型工具呼叫：自動喚起 **failed**，原生全文讀取、`no_reply` 及第二事件接續為 **not_run**。任務已暫停及退訂，原期限 gateway 守衛也已關閉本輪。此次失敗與先前僅回覆試驗的通過分別保留；見[雲端證據與設定](CHATGPT_PRIVATE_TUNNEL.zh-TW.md#最新無回覆完成試驗)。

另一個task明確選用GPT-6.1 Sol／Medium reasoning，保留原event predicate與payload；仍 **automatic wake failed**，於原deadline關閉。原生task metadata回 `is_enabled=false`、`last_run_time=null`，model／reasoning／execution error未提供。Task暫停已核對，但此第二輪log沒有 `events/unsubscribe`；本地guard停止subscription及斷開binding，不能寫成provider unsubscribe已驗證。捕捉的guard身分兩次kernel查詢均不存在，downstream全文read／no_reply仍 **not_run**。

第三個獨立read-first試驗只調整task讀前predicate順序，model／reasoning、scope、payload及permissions不變。網站問題A於16:01:23送出，callback於16:01:36回HTTP200；到16:09 task deadline仍無native全文read、post或no_reply呼叫。此輪按原16:10:24 guard deadline關閉；16:10:35 final readback為gen2 disabled／disconnected、turns0、原cursor及cancelled無結果批次。完整自動read／completion驗收 **failed**，downstream read／no_reply仍 **not_run**，問題B未送。

與前兩輪null不同，第三個task關閉後原生metadata回 `is_enabled=false`、**`last_run_time=2026-10-05T08:06:05.813018Z`**（台北16:06:05）。確有task-run時間紀錄，不能寫成此輪從未觸發。Model／reasoning／execution errors未提供；native task工具沒有提供history、output、error或run-link能力。從已排程頁找出精確task再開啟，也只返回同一對話，沒有更細run結果。Timestamp不證明native MCP成功，是否model排隊或執行問題仍未明。

第三輪完整stable log另記錄晚到的 `events/subscribe` 16:09:29.896、verification HTTP200 16:09:30.426，以及 `events/unsubscribe` 16:09:53.401；task UI pause也已核對。這些protocol calls不證明model執行，不將其原因歸給UI操作。新predicate順序在此試驗沒有帶來所需native read／completion，log不能判定platform root cause。Captured guard身分兩次精確核對均不存在，但不證明所有descendants已退出；先前失敗保留。

## 先前部署與測試：09:30

來源 `d51a7a312cd72d44eb295bc1f9c6f5b282807888` 於台北時間 09:30 部署完成。映像：`sha256:094ffd83f8083b178a61b20c17b7d5247d92d18bed55b75754f8ff3218a13ed3`。部署封裝的 191 個成員逐位元組符合 Git 來源；封裝 SHA-256 為 `967702ddb835253e7baf12fa52551853a054fee9a19e9a8e68bcf68296b5f832`。

| 此來源的驗證項目 | 結果 | 範圍 |
| --- | --- | --- |
| CI Windows | 334 passed、1 warning；18.74 秒 | Windows 安裝器檢查 |
| CI SQLite | 942 passed、34 skipped、3 warnings；124.08 秒 | 獨立 CI 資料庫環境 |
| CI PostgreSQL | 1,203 passed、32 skipped、3 warnings；211.17 秒 | 獨立 CI 資料庫環境 |
| 部署主機隔離測試 | 1,163 passed、72 skipped、3 warnings；226.85 秒 | 完成後移除拋棄式 PostgreSQL 資料庫 |
| 部署驗證 | 462 passed、0 failed；22.651 秒 | 已建立備份；保留 schema 6 與 26 張表，只允許清除過期網頁驗證資料 |
| 09:31 獨立讀回 | passed | 確切來源／映像、容器健康、驗證 HTTPS 與 PostgreSQL；未到期的啟用綁定及執行租約均為 0 |

[PR CI](https://github.com/Ya19880104/ys-aimemory/actions/runs/37231666006) 與 [push CI](https://github.com/Ya19880104/ys-aimemory/actions/runs/37231661568) 共六項工作均成功。各環境的數字不能相加，skipped 不算 passed。既有警告涉及 Starlette/httpx、Pydantic lifespan 解析與逐請求 cookie，各套件的警告數分別記錄。備份還原及主機外復原仍為 **not_run**。

先前 `7c2f0f6` 的 CI 失敗保留。最後修正將兩個過期的預期雜湊改為獨立讀取所附安裝器的雜湊，沒有改動產品行為。當時公開bootstrap為 `cf1ac9956681a36146fdf83b3a9c7bb1961d16b1`、固定來源 `b2c193e12988bcaacd07423e2aeac17b0442c455`；公開下載核對涵蓋10個不同檔案與全部11筆manifest。完整性通過不等於從下載到安裝的全程驗收。

## 先前線上瀏覽器檢查

已部署的英文與繁中對話頁顯示 **目前接收器 0／在線 0**，另將 **12 筆非作用中紀錄收合**。英文頁展開歷史再更新，仍保持展開，也可再次收合。兩種語言都說明心跳不等於模型已讀或回覆。實際瀏覽器截圖保留於私有證據。

線上教學的兩種語言均顯示專案安裝器與手動 stdio 的差異、日常聊天短指令，以及有界雲端接入與停止步驟。這是線上頁面驗證，不是自動收訊、公開安裝器執行或所有客戶端路徑的驗收。此次頁面檢查沒有送出新測試訊息。

實際複製的安裝指引完成英文／繁中 × Claude／Codex 共四種組合核對：固定版本與 SHA-256 符合獨立讀取的 Git 安裝器內容，語言、一小時／三回合預算正確，安裝行保留註解，沒有出現 `undefined`。這些指令僅複製與檢查，沒有執行。新增的雙語 compact 文件範例也以所附目標輸入模型完成離線驗證：展平的參數遭拒，兩種語言使用相同 JSON。

## 新一輪原生客戶端準備

以下一般原生檢查使用既有安裝，Hub 尚為部署前的 `bda71b26c7f6ed4d4532050167731373d284d3d0`：

- **Codex 原生身分與空增量對話讀取 passed**，實際 MCP 收據及所屬程序退出均已核對。之前失敗與獨立 SDK 工具清單測試分開保留。
- **Gemini 加入前原生狀態 passed**，回報 inactive；其後的有界自動收訊試驗另記於下方。
- **Claude 在新的 Local Code 對話完成一般原生身分呼叫**，worker 與專案正確。第一次 `memory_call` 展平參數，schema 驗證失敗；第二次保留兩層 `arguments` 才成功。這不是首次成功、房間讀寫或自動收訊驗收。舊對話仍保留已關閉的 MCP 連線，不當成目前連線。

Claude 較短路徑的官方安裝已完成，但私有驗收 wrapper 隨後因 Windows Store 邏輯路徑與實體路徑比較而拒絕。唯讀核對確認安裝收據、來源／設定雜湊及解析後的同一檔案身分；這不抹除原 wrapper 失敗。另經審查的 metadata 補記指令在執行前被 Claude Auto 權限分類器拒絕，因此為 **not_run**，等待明確批准。沒有重試、放寬權限或手寫替代收據。

文件已補齊原先缺漏的 [compact 完整呼叫範例](API_EXAMPLES.zh-TW.md#compact-本機轉送入口)。這是操作指引修正，沒有改 API，也不能證明新模型第一次就會選對參數。

## 有界雙方試驗與監控修正

12:10 兩個新接收器均回報就緒後，管理員從實際對話網頁送出一則驗收訊息。已安裝客戶端為 `bda71b26c7f6ed4d4532050167731373d284d3d0`，線上 Hub 為 `d51a7a312cd72d44eb295bc1f9c6f5b282807888`。這是雙方試驗，Claude 未參與。

- **Gemini 此單一事件的自動原生讀寫 passed。** 原生對話由背景通知喚起、完整讀取訊息，再用自己的身分回覆。操作員核准了一次首次 `chat_read` 工具提示，沒有另送模型提示觸發回應。實際展開的原生工具輸出、伺服器投遞收據與網頁回覆一致；這不代表首次使用可免人工核准。
- **Codex 在任何原生 MCP 呼叫之前 failed。** 私有測試監控拒絕未辨識的子程序並保存 STOP；runner 記錄停止／逾時，工具呼叫為零，未回報的 Token 用量保留 `not_reported`。原監控也未能證明晚出現程序的退出。之後的限定範圍清理確認先前記錄的程序已退出，並正式斷開綁定；沒有抹除失敗，也不代表已證明那個歷史未知子程序的確切退出。
- **另一次一般呼叫診斷重現了監控拒絕。** 在拒絕之前記錄確切已安裝的 `codex-code-mode-host.exe`、SHA-256、持有的直接 Codex 父程序及參數雜湊。此診斷確認它觀察到的程序全部退出，且保留舊 STOP；沒有成功 MCP 呼叫。下方修正及新試驗處理的是私有監控，這個發現本身不能證明產品伺服器有缺陷。

共同期限到達後，Gemini 接收器停止、綁定停用。之後的唯讀檢查確認所記錄接收器／guard 的程序身分已退出；兩次範圍內程序清單只剩獨立的 persistent MCP。原生 host 的實際 `GetAllPlugins` 輸出也已不列出接收器。重複執行的 metadata-only probe 未記錄第二次程序身分，因此其歷史精確退出仍未驗證；目前範圍內清單已無 probe。沒有重置舊 attempt、cursor 或預算。

私有測試工具另暴露兩個準備問題：Windows `Start-Process` 可能回傳虛擬環境 launcher PID，而非 READY 中的 interpreter PID；重複 metadata probe 則與只准建立一次的 exit 證據檔衝突。原始失敗均保留。實際啟動以持有的 interpreter 身分核對；沒有把舊 exit 檔當作第二次 probe 的退出證明。

## Codex 監控修正：兩次自動回覆 passed

修正後的私有監控只接受已觀察到的 code-mode host，核對確切執行檔雜湊、僅含執行檔的參數清單，以及持有的直接 Codex 父程序。其他未知子程序仍會停止試驗。現在也會先保存所屬子程序資料再拒絕，並保留 handle 供退出驗證。12 項純 admission 檢查 passed；之後新原生身分與空增量讀取也實際通過，所屬程序退出已核對。沒有重啟先前失敗的試驗。

接著使用新的 worker、相同 bda 客戶端／d51 Hub 版本組合，完成兩輪實際自動接話：

| 事件 | 管理員訊息 → 原生回覆 | 原生 MCP 呼叫 | CLI input tokens | cached input tokens | output tokens |
| --- | --- | --- | --- | --- | --- |
| A | 12:41:22 → 12:41:47 | 3 | 60,105 | 52,608 | 461 |
| B，回到等待狀態後 | 12:42:51 → 12:43:15 | 3 | 60,018 | 52,608 | 440 |

每輪均由管理員從實際網頁送出新訊息，專用 Codex CLI 接收器自動確認身分、完整讀取投遞內容，再回覆一次。實際原生收據、伺服器 `replied` 收據及網頁回覆一致；兩次投遞均只嘗試一次。中間沒有操作員追加提示叫模型查訊息、用 SDK 工具呼叫替代，或重啟接收器。

用量直接取自 `turn.completed.usage`，不是控制組比較或帳單。Cached input 不應再加進 input 總數；這些數字不能證明 Token 成本已最低，減少模型往返仍是獨立優化事項。

第二則回覆後，操作員在獨立十分鐘期限內提早送出 STOP。Guard 確認所持有的程序 handle 均已退出、範圍內程序清單為空，再執行官方斷線。程序 exit0；獨立伺服器讀回確認綁定已斷線，本機也無 native-active 狀態。這驗證了兩事件的有界連續收訊及正常停止，不涵蓋接收器重啟、模型崩潰、多客戶端同時對話或無限運作。

## 新一輪同時收訊通過；重現無回覆完成流程缺陷

13:06:04，管理員在兩個新接收器均在線後，從網頁送出一則新驗收訊息。Gemini 客戶端來源為 `fdc90b16628232a6a1ea47a0b81545c405e37e94`，Codex 為 `bda71b26c7f6ed4d4532050167731373d284d3d0`，Hub 保持 `d51a7a312cd72d44eb295bc1f9c6f5b282807888`。兩端使用新 worker，自當下最新進度加入，沒有重播舊試驗。修正後的 metadata probe 分別記錄本次 launch 與 finally；獨立捕捉的程序身分之後確認已不存在。

**兩端均自動收到同一則人類訊息並回覆。** Gemini 於 13:06:14 回覆，Codex 於 13:06:29 回覆。展開的 Gemini 原生讀寫輸出、Codex 原生收據、伺服器投遞收據及網頁回覆一致。人類訊息與這兩則回覆之間，沒有操作員補貼提示或核准工具。Codex 使用三次原生 MCP 呼叫；回報的 input／cached-input／output 用量為 60,164／43,776／453，不是成本對照測試。

隨後的 AI 同儕回覆暴露了**產品缺陷**，因此整體對話試驗未通過。AI 訊息會正常送給其他參與者，但現有完成路徑要求張貼回覆。Codex 在已要求不回覆同儕確認訊息的情況下，仍於 13:07:04 再貼一則確認；額外回合的相同用量欄位為 60,517／40,192／462。Gemini 完整讀取同儕回覆後選擇不發言，投遞卻留在 `tool_read` 未結束，接收器 journal 為 `returned`。既有回覆深度上限能限制繼續傳播，但沒有提供無回覆完成操作，也沒有消除額外模型回合。

操作員已為兩個試驗保存 STOP。Codex guard exit0，確認所屬程序退出並正式斷線；獨立狀態讀回也確認新的 generation 已斷線。Gemini host 確認接收器已停用，原期限 guard 隨後以 exit0 完成清理，獨立讀回確認綁定停用；先前捕捉的兩個接收程序身分均已不存在。這是限定範圍的退出證據，不涵蓋所有歷史子程序或另外的常駐 MCP 程序。未完成的投遞仍保留 `tool_read`，清理沒有將它標成成功。沒有送出第二則人類訊息。在當時截止點，具有效範圍守衛的無回覆完成操作仍在實作，尚未部署或完成原生驗證。

## 仍待驗收

新一輪Claude／Codex／Gemini同時自動對話與交接仍 **not_run**。13:06雙方失敗保留；之後已部署的雙題／native peer-no_reply序列已passed，但Gemini完整receiver／descendants closure及Cloud native no_reply仍是獨立未完成關卡。前兩個Cloud trials為automatic-wake失敗；第三輪有task-run timestamp，但native read／completion驗收失敗。不宣稱整體產品或Token節省passed。新試驗須保留版本組合、首次失敗、期限限制及實際native投遞證據。

既有 Gemini、ChatGPT 各兩次自動原生讀寫及閒置接收器／閘道重啟，僅對已關閉的 `6d0ce27` 試驗有效。先前順序正式交接及有限 Codex 執行中崩潰防重送，也保留原範圍；不能推論三方同時聊天、線上模型排隊事件、模型崩潰／未知提交復原、無限運作、新帳號雲端外掛安裝或 Token 成本對照測試通過。

PR #18 保留 draft、issue #12 保留開啟，不宣稱整體產品驗收完成。
