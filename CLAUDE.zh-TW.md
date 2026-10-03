# Claude Code 專案入口

[English](CLAUDE.md) | [繁體中文](CLAUDE.zh-TW.md)

請先讀本 repository 的 `AGENTS.md`，適用相同工作流程與限制。

本專案的 portable Skills 在 `skills/`：開工讀 hub-task-start、交接讀 hub-task-handoff、審查與測試讀 hub-review-accept。若客戶端未自動發現，請依檔案路徑明確讀取；不要假設已自動安裝或載入。

MCP 設定需人類在自己的客戶端完成。使用連線驗證的 worker 身分；不要把 coordinator、reviewer 等工作角色當成管理權限。遵循 `docs/FOUR_AGENT_RUNBOOK.zh-TW.md`，並以實際工具 schema 為準。
