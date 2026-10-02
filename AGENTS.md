# ys-aimemory 協作規則

這是獨立中央記憶／MCP 專案，不是 ERP 或 AIOps。修改本專案時先讀 README 與相關 docs，不改不相干 repository。

對已透過 Hub 管理的工作，使用 `skills/hub-task-start/SKILL.md` 開工：prepare → claim → read required sources → acknowledge → accept → validate。只用自己的 worker 身分、有效租約與 fence。角色分工不等於安全權限。

每個 worker 有自己的 clone/worktree、branch 與明確路徑範圍，不共用可寫工作樹。來源過期、租約失效、scope 衝突就停止新的寫入，保留成果並重新核對上下文。長工作續租；交接後舊持有者停止寫入。

交付使用 `skills/hub-task-handoff/SKILL.md`；審查／測試使用 `skills/hub-review-accept/SKILL.md`。輸出確切 commit、實際測試、未測項、證據和下一步。待審 proposal 不得冒充權威來源。

不得把密碼、登入 cookie、API key 或實際 token 寫入 Git、Hub 知識或交接日誌。配置憑證、部署、對外發布與權限變更需另有明確授權。

Skills 是約定；伺服器只能把關經它的操作，不能阻止客戶端直接改本機檔案。沒有 Hub 連線時如實回報，不能聲稱已驗證、已認領或已取得鎖。
