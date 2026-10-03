# 2026-10-03 驗證紀錄

[English](VALIDATION_2026-10-03.md) | [繁體中文](VALIDATION_2026-10-03.zh-TW.md)

## 目前驗證快照（不是最終部署認證）

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
