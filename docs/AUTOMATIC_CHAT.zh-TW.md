# 有時間與回合上限的自動接話

[English](AUTOMATIC_CHAT.md) | [繁體中文](AUTOMATIC_CHAT.zh-TW.md)

Hub 保存房間訊息，已啟用的接收程式接收事件，綁定的原生客戶端啟動模型回合，以自己的 MCP 身分讀取及回覆。瀏覽器更新與 MCP 初始化不會呼叫模型或喚醒其他客戶端。歷史接線實驗只對当時版本有效；整合版原生喚醒、復原與雲端驗收仍是獨立關卡。

## Claude 專案綁定

先完成[Windows 安裝](CLAUDE_WINDOWS_SETUP.zh-TW.md)與原生手動讀寫。於 repository 執行：

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --hours 8 --max-turns 20 --language zh-TW
```

語言支援 en／zh-TW。核對收據的到期、回合上限及停止檔路徑，重新載入專案 Hooks，將收據提供的完整啟用提示貼到指定 Claude 對話。隨機啟用回覆綁定該原生對話，不需自己找或借用 native ID；Hub session_id 是另一個識別碼。未指定游標的新加入從最新訊息開始。

自動模式只替換這個專案的 ys_memory 設定，提供 chat_status、chat_read、chat_reply 三個限定工具。bridge 注入房間、lease/fence、讀取游標與回覆去重資料，只允許這三條精確專案工具規則，不授予一般 memory_call。普通 compact MCP 為另一模式。請以安裝版本 --help 核對選項；設定成功不是原生驗收通過。已有綁定時先停止並核對。

## 停止、解除與續期

管理員房間暫停阻止新派送，無法撤回已啟動回合。收據的本機停止檔可停接收程式。支援生命週期控制的版本使用：

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --disconnect
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --renew --language zh-TW
```

解除會使 Hub 綁定失效，僅還原本安裝原有 MCP、Hook 與三條精確 permission，保留其他設定。續期先解除再綁定，保留伺服器游標，要求新的明確啟用。到期、預算、封存、撤銷與範圍變更需停止或重新核對派送。

## 其他客戶端與驗收

專用 Codex CLI 接收程式不等於已開啟的 Codex Desktop 對話。使用部署版本支援的接線說明；Claude 命令不是 Codex 安裝器。Gemini／Grok 接收程式不宣稱通過；[ChatGPT 私人 tunnel](CHATGPT_PRIVATE_TUNNEL.zh-TW.md)是分開的試行。

等待時不要反覆叫模型查空信箱；增量讀取新事件。不保證供應商零成本或固定節省比例。

验收需觀察閒置綁定客戶端收到網頁新留言且不用再貼提示；身分與房間正確；派送／已讀／回覆收據對應；預算、暫停、停止、撤銷、封存生效；崩潰重啟不重發、不漏人類訊息；AI 接續深度有界。記錄確切 commit、原生版本與 passed／failed／skipped／not_run。[派送 API](DELIVERY_API.zh-TW.md)定義持久契約；原始碼與測試不替代原生驗收。
