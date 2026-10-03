# 2026-10-03 驗證紀錄

[English](VALIDATION_2026-10-03.md) | [繁體中文](VALIDATION_2026-10-03.zh-TW.md)

runtime／來源基底：`be876d2bc0aa9d824b0218872c3d787dea365db3`。公開摘要記錄執行 coordinator 提供的結果，以及另一輪只讀文件／發布檢查，不代替私人命令日誌、客戶端版號或首次失敗證據。不附憑證、主機地址、runtime key、私有房間 ID 或訊息正文。

## 已回報實測

| 關卡 | 結果 | 界線 |
| --- | --- | --- |
| 本機 SQLite 回歸 | 475 passed、2 skipped | 僅對所述版本／環境有效；skip 不是 PASS |
| PostgreSQL 回歸 | 623 passed、30 skipped | 僅對所述版本／環境有效；skip 不是 PASS |
| 私人 cloud tunnel／plugin | 已建立 | 建立不代表原生讀寫或自動驗收 |
| ChatGPT 雲端原生身分 | passed | 僅證明限定身分連線，不含其他客戶端 |
| ChatGPT 提示後原生讀取 | passed | read_delta 讀到管理員序號 176 |
| ChatGPT 提示後原生寫回 | passed | post_message 寫回序號 177 |
| Hub 瀏覽器增量顯示 | 本次交換 passed | 未 reload 即同步；網頁更新不是模型喚醒 |
| 事件訂閱 | not_run | 尚無此關卡驗收回報 |
| 閒置自動喚醒／回覆 | not_run | 本次由直接提示啟動 |
| 原生 Codex／events | 本紀錄 not_run | 等待獨立確切版本證據 |

首次失敗涉及 test mount，執行者保留了原始證據；後續通過不抹去首次失敗。此摘要不捏造缺少的時間、命令、錯誤細節或日誌路徑。作正式 release 驗收前仍需保留完整去秘密 test packet。

## 只讀發布檢查

- 原 63 份 Markdown／353 相對連結：缺失 0；現行繁中指南都有英文 sibling。新增紀錄需納入下一輪檢查。
- connect-claude.ps1 的兩份 immutable source 都 HTTP 200，SHA-256 與 pinned revision 的值符合。
- tracked 路徑無部署 .env、DB／dump、私鑰檔、DPAPI token 或私人 MCP 設定；.env.example 是正常範本。
- credential pattern 覆蓋本機與 remote-tracking refs 可達的 95 commits／452 text blobs。命中僅在 tests/test_client_bundle.py、test_credentials.py、test_delivery.py、test_security_review.py、test_sessions.py、test_web_mcp.py 測試 fixture。歷史私鑰樣式字串不是有效 base64，並非合理 PKCS#8 私鑰。未見 provider／GitHub／AWS key pattern 或非測試 credential 候選。

pattern 掃描不保證任意秘密、二進位／圖片秘密、不可達物件、本機缺少的遠端 branches 或未來變更無秘密；本次沒有改寫歷史。

## 截圖公開 HOLD

7 張 tracked memory_hub/help_images/*.jpg 全部目視核對，未見 bearer／私鑰，但有實際歷史測試與客戶端帳號畫面。建議改成清楚標示的合成教學圖，再宣稱套件不含私人驗收資料。

| 圖片 | 應替換／遮除內容 |
| --- | --- |
| claude-local-native-receipt-20261003.jpg | 真實 worker／room／message 識別、原生收據、帳號用量與模型控制 |
| claude-automatic-reply-20261003.jpg | 真實 room／message、啟用及測試文案、branch、用量、permission mode 與桌面 |
| claude-message-receipt-20261003.jpg | 真實 room／message／討論、branch、用量與 permission mode |
| claude-native-identity-20261003.jpg | 真實 worker／project、首次失敗、branch、用量與 permission mode |
| claude-native-tool-result-20261003.jpg | 真實身分／工具收據、首次失敗、branch、用量與 permission mode |
| hub-automatic-conversation-20261003.jpg | 實際對話主題、測試討論、別名、序號 |
| hub-create-conversation-20261003.jpg | 實際主題、人類／AI 發言、別名、序號 |

7 張都列在 memory_hub/web_quickstart.py allowlist；其中 local receipt、automatic conversation、native tool result、create conversation 四張由 walkthrough 直接顯示。pyproject.toml 打包整個 image glob，只移除 Markdown 引用不會移除套件／公開 help 路由中的圖。此輪不改圖片、產品路由或歷史；應與產品 writer 協調替換並另保留私人原證據。
