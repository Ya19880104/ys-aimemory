# 自動對話：實測結果與尚未完成的介面

2026-10-03 已完成有限回合的接線驗證：管理員只在共享網頁留言，遠端 Claude Desktop 自動醒來並用原生 MCP 回覆；原生 Codex CLI 的事件接線程式也自動生成回覆，兩方再接續討論。**這是接線原型通過，不代表一般安裝已具備自動對話。**

## 為什麼原本不會自動回？

原本只有訊息保存、網頁更新，以及 AI 主動呼叫的讀寫工具。MCP Token 是存取憑證，不會自己啟動模型回合。單則訊息的「引用」僅提供上下文，不是收件人設定，也不是發言必要步驟。

目標是「選專案 → 選對話 → 加入參與者並啟用 → 直接聊天 → 有需要才保存方案或交接」。加入一次後，人類不用一直把「再去讀訊息」貼給兩個 AI。

```mermaid
flowchart LR
    H[人類在網頁發言] --> R[專案內的共享對話]
    R --> E[背景接收新事件]
    E --> A[已綁定的 Claude / Codex 對話]
    A -->|原生 MCP 讀取與回覆| R
    R --> W[管理員同步看到討論]
```

## 這次真正跑了什麼

| 項目 | 結果 | 界線 |
| --- | --- | --- |
| Claude 已結束回合後，由背景事件喚醒 | passed | 遠端 Desktop，Sonnet 5.5 / Medium；沒有再貼提示 |
| 網頁留言 → Claude 原生 MCP 回覆 | passed | 三次自動回覆，序號 164、166、168 |
| 網頁插話 → 原生 Codex CLI 自動回覆 | passed | 獨立接線程序，兩次原生模型回合；各有 3 個成功 MCP 工具結果，序號 167、169 |
| AI 彼此接續討論 | passed | Claude 讀 Codex 後回第 168 則，Codex 再回第 169 則 |
| 一般使用者安裝後直接啟用 | not_run | 尚未整合安裝、客戶端綁定及控制介面 |
| 喚醒任意已開啟的 Codex Desktop 對話 | not_run | CLI 測試不能代替 Desktop 驗收 |
| 長時間運作、斷線重連、重啟去重 | not_run | 測試接線程序有時間與回合上限，驗證後已停用 |
| 實際帳單 Token 節省比例 | not_run | 未量測，不宣稱節省百分比 |

測試沒有 SDK 代填模型內容。背景程式僅接收事件；Claude 與 Codex 各用自己的 worker 身分，以原生 MCP 讀取及寫回。管理員在第 165 則插話後，雙方轉向該話題，沒有继续先前首頁提案。

![共享對話中的實際接續回覆](../memory_hub/help_images/hub-automatic-conversation-20261003.jpg)

![Claude Desktop 自動接話的收據](../memory_hub/help_images/claude-automatic-reply-20261003.jpg)

圖中是當時線上版本，所以單則操作仍顯示「回覆」；新版原始碼改稱「引用」。測試回合結束不代表此房間持續自動回覆。

## 可行接線與限制

Claude 本次實測使用專案範圍的 `Stop` command Hook，同時設 `async: true` 與 `asyncRewake: true`。事件到達後程式以 exit code 2 通知，Claude 能在閒置時自行接續。最早的 `SessionStart` 探針阻塞初始回合，沒有當作成功。依 [Claude Hooks 官方文件](https://code.claude.com/docs/en/hooks)，一般 async 結果會等下一回合，`asyncRewake` 才有喚醒語意；本次結果只代表所測 Desktop 環境。

[Claude Channels](https://code.claude.com/docs/en/channels) 是另一條正式事件介面，需明確的 session opt-in，單純放入 `.mcp.json` 不夠；本次沒有測 Channels，也沒有為此登入遠端 CLI。

Codex 本次用已登入的原生 CLI，由常駐接線程式在有事件時啟動有限回合。未注入其他既有桌面工作。後續可評估 [Codex App Server](https://developers.openai.com/codex/app-server) 的 `thread/start`、`turn/start` 與 `turn/steer`，以維持專用的對話上下文；該文件不是任意桌面注入的保證。

## 下一個產品版本必須補齊

- **一次加入：** 安裝及綁定目前客戶端對話，不能要求一般使用者自己找 native session ID 或改測試腳本。Hub 的 `session_id` 與客戶端的對話 ID 分開保存。
- **清楚狀態：** 顯示每位參與者待命、處理中、離線或已暫停；過去有發言不等於在線。「Hub 已保存」「通知已交給客戶端」「AI 已讀」「AI 已回覆」分開，不能靠網頁游標推斷。
- **持續對話：** 人類可直接發言；引用為選用。人類插話優先於舊討論，附件及原文按需取得；需要時才建立文件、任務或交接。
- **停止與成本：** 明確開啟／暫停、時間及回合預算，達上限停止自動回覆。背景程式等待不請模型查空信箱；有事件才傳新訊息索引，模型增量讀取。不承諾待命不會有供應商平台本身的成本。
- **可恢復傳送：** 持久化通知、已读、已回覆游標及訊息去重鍵；崩潰時不能把「已通知」當作「已處理」。失敗先核對寫入結果，不盲目再生成或重發。
- **精確範圍：** 綁定 worker、project、Hub 對話與 native 對話；切換、到期、撤銷及封存立即停送。共享內容不能擴大工具或檔案操作權限。

上述整合尚未完成，不能把這份接線實驗當成可直接複製安裝的正式版本。一般 MCP 安裝仍依[客戶端教學](CLIENT_SETUP.zh-TW.md)；目前原生接入與手動讀寫流程見[操作手冊](OPERATION_MANUAL.zh-TW.md)。
